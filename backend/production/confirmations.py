"""Delivery confirmations — the sealed comprobante de entrega per work order.

The truck arriving is when the platform closes two loops at once: the
receiver's signature seals an immutable POD PDF, and — for
contado-contra-entrega deals — the cash collected at the door lands in the
project's cobranza ledger in the SAME transaction. No re-entering between
departments: delivery → ledger is one atomic act.

A confirmation is sealed evidence: ``UNIQUE(order_id)`` makes a retried
confirm replay the already-sealed row, never a second document; the
signature PNG and the rendered PDF are both immutable objects whose hashes
ride in ``payload_json``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import zlib
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from authentication.errors import contract_error
from documents.repository import DocumentaryError, documentary_backend
from documents.renderers import render_delivery_pod
from documents.storage import SupabaseDocumentStorage
from pricing.repository import one, rows
from projects import org_branding
from projects.sii_envio import integration_state
from projects.payments import resolve_or_insert_payment
from projects.receipts import issue_receipt
from projects.service import project_row

SIGNED_URL_TTL_SECONDS = 600

_MANIFEST_SCHEMA = "work_order_packing_v1"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_SIGNATURE_BYTES = 200_000
_PAYMENT_KINDS = {"ANTICIPO", "PARCIAL", "SALDO"}
_PAYMENT_METHODS = {"TRANSFER", "CASH", "CARD", "CHECK", "OTHER"}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _pod_currency(org_id: UUID, project_id, deal: dict | None) -> str:
    """Currency printed on the POD — the same sources the payment deal
    resolves (sealed snapshot → org) so a replayed cobro still renders the
    money in the project's own currency rather than a non-CLP dash."""
    if deal is not None:
        return deal["currency"]
    versions = rows(
        "SELECT snapshot_json::text AS snapshot_json "
        "FROM public.project_versions "
        "WHERE org_id=%s AND project_id=%s ORDER BY emitted_at DESC,id DESC LIMIT 1",
        [str(org_id), str(project_id)],
    )
    if versions:
        snapshot = versions[0]["snapshot_json"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        sealed = snapshot.get("project") if isinstance(snapshot, dict) else None
        if (sealed or {}).get("currency"):
            return sealed["currency"]
    org = rows("SELECT currency FROM public.tenancy_organizations WHERE id=%s", [str(org_id)])
    return org[0]["currency"] if org else "CLP"


def _confirmation_public(row) -> dict:
    return {
        "id": str(row["id"]),
        "confirmation_code": row["confirmation_code"],
        "order_id": str(row["order_id"]),
        "delivery_id": str(row["delivery_id"]),
        "payment_id": str(row["payment_id"]) if row["payment_id"] else None,
        "issued_at": row["issued_at"].isoformat()
        if hasattr(row["issued_at"], "isoformat")
        else row["issued_at"],
    }


def _manifest_units(order_payload: dict) -> list[dict]:
    packing = (order_payload or {}).get("packing") or {}
    if packing.get("schema") != _MANIFEST_SCHEMA:
        return []
    return [
        {
            "unit_index": unit.get("unit_index"),
            "label_code": unit.get("label_code"),
            "profiles": unit.get("profiles"),
            "reinforcements": unit.get("reinforcements"),
            "glasses": unit.get("glasses"),
            "panels": unit.get("panels"),
            "hardware": unit.get("hardware"),
            "fittings": unit.get("fittings"),
        }
        for unit in packing.get("units") or []
    ]


def _decode_signature(raw: str) -> bytes:
    """Structure-checked PNG: magic + first chunk IHDR with a valid CRC +
    trailing IEND — a payload that merely carries the magic bytes never
    reaches the image decoder or immutable storage."""
    try:
        png = base64.b64decode(raw, validate=True)
    except Exception as error:
        raise DocumentaryError("signature_invalid") from error
    if not _is_png(png):
        raise DocumentaryError("signature_invalid")
    return png


def _is_png(png: bytes) -> bool:
    # 8-byte magic, then chunks [len:4][type:4][data][crc:4]; the first
    # chunk must be a 13-byte IHDR and the stream must end in IEND.
    if len(png) < 8 + 25 + 12 or len(png) > _MAX_SIGNATURE_BYTES:
        return False
    if not png.startswith(_PNG_MAGIC):
        return False
    if int.from_bytes(png[8:12], "big") != 13 or png[12:16] != b"IHDR":
        return False
    if zlib.crc32(png[12:29]) != int.from_bytes(png[29:33], "big"):
        return False
    return png[-8:-4] == b"IEND" and int.from_bytes(png[-12:-8], "big") == 0


def _payment_kwargs(payment: dict) -> dict:
    """Normalize the optional cobro block; bad money never seals a POD."""
    try:
        amount = Decimal(str(payment["amount"]))
    except (KeyError, InvalidOperation, TypeError) as error:
        raise DocumentaryError("payment_invalid") from error
    kind = str(payment.get("kind") or "SALDO").upper()
    method = str(payment.get("method") or "").upper()
    if (
        not amount.is_finite()
        or amount <= 0
        or kind not in _PAYMENT_KINDS
        or method not in _PAYMENT_METHODS
    ):
        raise DocumentaryError("payment_invalid")
    return {
        "amount": amount,
        "kind": kind,
        "method": method,
        "reference": payment.get("reference"),
        "note": payment.get("note"),
    }


def confirm_delivery(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    receiver_name: str,
    receiver_rut: str | None,
    signature_b64: str,
    payment: dict | None,
    observations: str | None = None,
) -> dict:
    """Seal the comprobante de entrega (and its cobro, if any) as one atomic
    act. The org advisory slot serializes CE codes; ``UNIQUE(order_id)``
    replays a retried confirm instead of splitting it into two documents."""
    org_id_s, order_id_s = str(org_id), str(order_id)
    receiver = (receiver_name or "").strip()
    if not receiver:
        raise DocumentaryError("receiver_required")
    signature_png = _decode_signature(signature_b64 or "")
    payment_kwargs = _payment_kwargs(payment) if payment else None
    object_keys: list[str] = []
    try:
        with transaction.atomic(), documentary_backend():
            order = one(
                """
                SELECT id, order_code, project_id, status::text, payload_json::text AS payload_json
                FROM public.orders
                WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
                FOR UPDATE
                """,
                [order_id_s, org_id_s],
                "work_order_not_found",
            )
            # The trip being signed is the open one (ON_ROUTE preferred;
            # DELIVERED only reachable on replay). Partial deliveries sign
            # one comprobante per trip — replays key on delivery_id.
            # A completed earlier trip also matches the filter — LIMIT after
            # the ON_ROUTE-first ordering picks the trip being signed (an
            # extra DELIVERED row must not explode one() into
            # ambiguous_authority).
            delivery = one(
                """
                SELECT * FROM public.deliveries
                WHERE order_id = %s AND org_id = %s
                  AND status IN ('ON_ROUTE', 'DELIVERED')
                ORDER BY CASE WHEN status='ON_ROUTE' THEN 0 ELSE 1 END,
                         created_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                [order_id_s, org_id_s],
                "delivery_not_found",
            )
            delivery_id_s = str(delivery["id"])
            # Replay wins over lifecycle checks: a lost-response retry after
            # installation still returns the sealed row, never an error.
            existing = rows(
                "SELECT * FROM public.delivery_confirmations "
                "WHERE delivery_id=%s AND org_id=%s",
                [delivery_id_s, org_id_s],
            )
            if existing:
                return _confirmation_public(existing[0])
            if str(order["status"]) != "DISPATCHED":
                raise DocumentaryError("delivery_requires_dispatched")
            if str(delivery["status"]) not in ("ON_ROUTE", "DELIVERED"):
                raise DocumentaryError("delivery_transition_invalid")
            one(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                [f"delivery_confirmations:{org_id_s}"],
            )
            sequence = int(
                one(
                    "SELECT COUNT(*) AS n FROM public.delivery_confirmations WHERE org_id=%s",
                    [org_id_s],
                )["n"]
            )
            confirmation_code = f"CE-{sequence + 1:04d}"
            issued_at = timezone.now()

            # Lock the project's concurrency point only when the cobro writes
            # the ledger: the deal check and the row must agree on one deal
            # generation. A signature-only POD just projects the header —
            # under FOR UPDATE an INSTALLER would hit
            # project_documentary_backend_lock (ledger roles only) and the
            # field signature could never seal (phase-10 defect).
            project = project_row(
                org_id, order["project_id"], lock=payment_kwargs is not None
            )
            payment_id = None
            payment_payload = None
            deal = None
            if payment_kwargs is not None:
                # The cobro goes through the cobranza ledger primitive so the
                # same deal, currency, project and replay rules apply — the
                # pod:<delivery> key dedupes a retried confirm like every
                # other payment.
                payment_row, deal = resolve_or_insert_payment(
                    org_id=org_id,
                    project_id=order["project_id"],
                    project=project,
                    actor_id=actor_id,
                    data={
                        "operation_key": f"pod:{delivery_id_s}",
                        "kind": payment_kwargs["kind"],
                        "amount": payment_kwargs["amount"],
                        "method": payment_kwargs["method"],
                        "reference": payment_kwargs["reference"],
                        "note": payment_kwargs["note"],
                        "recorded_at": issued_at,
                    },
                )
                # A `pod:` collision under the same project still must be the
                # same collection — different amount/kind/method is a
                # caller-supplied-key conflict, never silent adoption.
                if (
                    str(payment_row["kind"]) != payment_kwargs["kind"]
                    or str(payment_row["method"]) != payment_kwargs["method"]
                    or Decimal(str(payment_row["amount"])) != payment_kwargs["amount"]
                ):
                    raise contract_error(
                        409,
                        "payment_operation_conflict",
                        "El cobro registrado para esta entrega no coincide.",
                    )
                payment_id = payment_row["id"]
                # Every ledger payment seals a comprobante — the POD cobro is
                # no exception; a replayed settle finds the existing receipt
                # via UNIQUE(payment_id) and returns it unchanged.
                issue_receipt(
                    org_id=org_id,
                    project=project,
                    payment={
                        "project_id": order["project_id"],
                        **payment_row,
                    },
                    actor_id=actor_id,
                    deal=deal if deal is not None else {"total": None, "currency": "CLP"},
                )
                payment_payload = {
                    "id": str(payment_row["id"]),
                    "kind": payment_row["kind"],
                    "method": payment_row["method"],
                    "amount": str(payment_row["amount"]),
                    "reference": payment_kwargs["reference"],
                    "note": payment_kwargs["note"],
                    "recorded_at": payment_row["recorded_at"].isoformat()
                    if hasattr(payment_row["recorded_at"], "isoformat")
                    else str(payment_row["recorded_at"]),
                }

            order_payload = (
                order["payload_json"]
                if isinstance(order["payload_json"], dict)
                else json.loads(order["payload_json"] or "{}")
            )
            trip_units = (
                {int(i) for i in delivery["unit_indexes"]}
                if delivery.get("unit_indexes") is not None
                else None
            )
            units = [
                unit
                for unit in _manifest_units(order_payload)
                if trip_units is None or int(unit.get("unit_index") or 0) in trip_units
            ]
            currency = _pod_currency(org_id, order["project_id"], deal)
            signature_hash = _sha256(signature_png)
            payload = {
                "confirmation_code": confirmation_code,
                "organization": org_branding.branding_for_snapshot(org_id=org_id),
                "issued_at": issued_at.isoformat(),
                "tributary": integration_state(org_id=org_id),
                "receiver": {
                    "name": receiver,
                    "rut": (receiver_rut or "").strip() or None,
                },
                "signature_sha256": signature_hash,
                "order": {
                    "id": order_id_s,
                    "code": order["order_code"],
                    "position_id": order_payload.get("position_id"),
                    "quantity": order_payload.get("quantity"),
                },
                "project": {
                    "code": project["code"],
                    "name": project["name"],
                    "client_name": project["client_name"],
                    "client_rut": project["client_rut"],
                    "currency": currency,
                },
                "delivery": {
                    "id": delivery_id_s,
                    "unit_indexes": (
                        sorted(trip_units) if trip_units is not None else None
                    ),
                    "scheduled_date": str(delivery["scheduled_date"]),
                    "time_window": delivery["time_window"],
                    "address": delivery["address"],
                    "contact_name": delivery["contact_name"],
                    "installer_name": delivery["installer_name"],
                },
                "units": units,
                "totals": {
                    "units": len(units) if units else order_payload.get("quantity"),
                    "profiles": sum(int(u.get("profiles") or 0) for u in units),
                    "reinforcements": sum(int(u.get("reinforcements") or 0) for u in units),
                    "glasses": sum(int(u.get("glasses") or 0) for u in units),
                    "panels": sum(int(u.get("panels") or 0) for u in units),
                    "hardware": sum(int(u.get("hardware") or 0) for u in units),
                    "fittings": sum(int(u.get("fittings") or 0) for u in units),
                },
                "payment": payment_payload,
                # P23 — observaciones de la recepción en obra: quedan
                # selladas en el acta junto a la firma.
                "observations": (observations or "").strip() or None,
            }

            storage = SupabaseDocumentStorage()
            signature_key = (
                f"org_{org_id_s}/projects/{order['project_id']}/"
                f"delivery-confirmations/{confirmation_code.lower()}_"
                f"signature_{signature_hash[:16]}.png"
            )
            try:
                storage.upload_immutable(
                    signature_key, signature_png, "image/png"
                )
                object_keys.append(signature_key)
                identifier = hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode("utf-8")
                ).hexdigest()
                content, media_type = render_delivery_pod(
                    payload,
                    signature_png=signature_png,
                    pdf_identifier=identifier,
                )
                content_hash = _sha256(content)
                object_key = (
                    f"org_{org_id_s}/projects/{order['project_id']}/"
                    f"delivery-confirmations/{confirmation_code.lower()}_"
                    f"{content_hash[:16]}.pdf"
                )
                storage.upload_immutable(object_key, content, media_type)
                object_keys.append(object_key)
                row = one(
                    "INSERT INTO public.delivery_confirmations("
                    "org_id,order_id,delivery_id,payment_id,confirmation_code,"
                    "payload_json,signature_object_key,storage_bucket,"
                    "storage_object_key,file_sha256,media_type,byte_size,"
                    "issued_by,issued_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,'documents',%s,%s,%s,%s,%s,%s) "
                    "RETURNING *",
                    [
                        org_id_s,
                        order_id_s,
                        delivery_id_s,
                        str(payment_id) if payment_id else None,
                        confirmation_code,
                        json.dumps(payload),
                        signature_key,
                        object_key,
                        content_hash,
                        media_type,
                        len(content),
                        str(actor_id),
                        issued_at,
                    ],
                )
            except Exception:
                failed_keys = []
                for key in object_keys:
                    try:
                        storage.delete_object(key)
                    except Exception:  # noqa: BLE001 — retry after transaction rollback
                        failed_keys.append(key)
                object_keys = failed_keys
                raise

            if str(delivery["status"]) != "DELIVERED":
                rows(
                    "UPDATE public.deliveries SET status='DELIVERED', updated_at=%s "
                    "WHERE id=%s AND org_id=%s RETURNING id",
                    [issued_at, delivery_id_s, org_id_s],
                )
                rows(
                    "INSERT INTO public.production_step_events("
                    "org_id, order_id, event, actor_id, payload) "
                    "VALUES (%s, %s, 'WO_DELIVERY_DELIVERED', %s, %s::jsonb) "
                    "RETURNING id",
                    [
                        org_id_s,
                        order_id_s,
                        str(actor_id),
                        json.dumps({"order_code": order["order_code"]}),
                    ],
                )
            rows(
                "INSERT INTO public.production_step_events("
                "org_id, order_id, event, actor_id, payload) "
                "VALUES (%s, %s, 'WO_DELIVERY_CONFIRMED', %s, %s::jsonb) "
                "RETURNING id",
                [
                    org_id_s,
                    order_id_s,
                    str(actor_id),
                    json.dumps(
                        {
                            "order_code": order["order_code"],
                            "confirmation_code": confirmation_code,
                        }
                    ),
                ],
            )
            object_keys = []
    except Exception:
        for key in object_keys:
            _purge_unreferenced_confirmation(org_id=org_id, object_key=key)
        raise
    return _confirmation_public(row)


def _purge_unreferenced_confirmation(*, org_id: UUID, object_key: str) -> None:
    """Compensating delete for a rolled-back confirmation: the org slot
    serializes against confirm_delivery — a committed row referencing the
    key wins, an orphan is removed without masking the original failure."""
    import logging

    try:
        with transaction.atomic(), documentary_backend():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    [f"delivery_confirmations:{org_id}"],
                )
            referenced = rows(
                "SELECT id FROM public.delivery_confirmations "
                "WHERE org_id=%s AND (storage_object_key=%s OR signature_object_key=%s)",
                [str(org_id), object_key, object_key],
            )
            if referenced:
                return
            SupabaseDocumentStorage().delete_object(object_key)
    except Exception as cleanup_error:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "delivery_confirmation_cleanup_failed",
            extra={"storage_object_key": object_key, "cleanup_error": str(cleanup_error)},
        )


def confirmation_access(
    *, org_id: UUID, order_id: UUID, delivery_id: UUID | None = None
) -> dict:
    with documentary_backend():
        clause = ""
        params: list = [str(org_id), str(order_id)]
        if delivery_id is not None:
            clause = " AND delivery_id=%s"
            params.append(str(delivery_id))
        found = rows(
            "SELECT * FROM public.delivery_confirmations "
            f"WHERE org_id=%s AND order_id=%s{clause} "
            "ORDER BY created_at DESC",
            params,
        )
        if not found:
            raise DocumentaryError("delivery_confirmation_not_found")
        found = found[0]
        signed_url = SupabaseDocumentStorage().signed_url(
            str(found["storage_object_key"]), expires_in=SIGNED_URL_TTL_SECONDS
        )
    return {
        **_confirmation_public(found),
        "signed_url": signed_url,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }
