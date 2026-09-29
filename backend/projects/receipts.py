"""Payment receipts — a sealed comprobante per ledger payment.

The receipt is issued inside ``record_payment``'s transaction the moment the
payment row lands: same atomicity, same idempotency (UNIQUE payment_id — a
replayed insert returns the already-sealed row, never a re-render). The PDF
freezes project, payment, and the balance AT THE TIME OF ISSUE into
payload_json; the immutable storage object is written under the same
documents bucket policy as every sealed artifact.

Voiding a payment marks the payment row — the receipt stays, because in the
real world an issued comprobante cannot be un-issued.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from authentication.errors import contract_error
from documents.repository import documentary_backend, decoded
from documents.renderers import render_payment_receipt
from documents.storage import SupabaseDocumentStorage
from pricing.repository import one, rows
from projects import org_branding

SIGNED_URL_TTL_SECONDS = 600


def _file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _receipt_public(row) -> dict:
    return {
        "id": str(row["id"]),
        "receipt_code": row["receipt_code"],
        "payment_id": str(row["payment_id"]),
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
    }


def _collected(org_id: UUID, project_id: UUID) -> Decimal:
    total = one(
        "SELECT COALESCE(SUM(amount), 0) AS collected FROM public.project_payments "
        "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
        [str(org_id), str(project_id)],
    )["collected"]
    return Decimal(str(total))


def issue_receipt(
    *,
    org_id: UUID,
    project: dict,
    payment: dict,
    actor_id: UUID,
    deal: dict,
) -> dict:
    """Seal the comprobante for a freshly inserted payment. Must run inside
    the caller's transaction: an org-scoped advisory lock serializes the
    receipt sequence, which is per-organization — the code must satisfy
    UNIQUE (org_id, receipt_code) across every project."""
    org_id_s, project_id_s = str(org_id), str(payment["project_id"])
    existing = rows(
        "SELECT * FROM public.payment_receipts WHERE payment_id=%s AND org_id=%s",
        [str(payment["id"]), org_id_s],
    )
    if existing:
        return _receipt_public(existing[0])

    one(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        [f"payment_receipts:{org_id_s}"],
    )
    sequence = int(
        one(
            "SELECT COUNT(*) AS n FROM public.payment_receipts WHERE org_id=%s",
            [org_id_s],
        )["n"]
    )
    receipt_code = f"RC-{sequence + 1:04d}"
    collected = _collected(org_id, UUID(project_id_s))
    payload = {
        "receipt_code": receipt_code,
        "organization": org_branding.branding_for_snapshot(org_id=org_id),
        "issued_at": timezone.now().isoformat(),
        "project": {
            "code": project["code"],
            "name": project["name"],
            "client_name": project["client_name"],
            "client_rut": project["client_rut"],
            "delivery_address": project["delivery_address"],
            "currency": deal["currency"],
        },
        "payment": {
            "kind": payment["kind"],
            "amount": str(payment["amount"]),
            "method": payment["method"],
            "reference": payment["reference"],
            "note": payment["note"],
            "recorded_at": payment["recorded_at"].isoformat()
            if hasattr(payment["recorded_at"], "isoformat")
            else payment["recorded_at"],
            "operation_key": payment["operation_key"],
        },
        "balance": {
            "deal_total": str(deal["total"]) if deal["total"] is not None else None,
            "collected": str(collected),
            "remaining": str(deal["total"] - collected)
            if deal["total"] is not None
            else None,
        },
    }
    identifier = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    content, media_type = render_payment_receipt(payload, pdf_identifier=identifier)
    content_hash = _file_sha256(content)
    object_key = (
        f"org_{org_id_s}/projects/{project_id_s}/receipts/"
        f"{receipt_code.lower()}_{content_hash[:16]}.pdf"
    )
    storage = SupabaseDocumentStorage()
    try:
        storage.upload_immutable(object_key, content, media_type)
        row = one(
            "INSERT INTO public.payment_receipts("
            "org_id,project_id,payment_id,receipt_code,payload_json,storage_bucket,"
            "storage_object_key,file_sha256,media_type,byte_size,created_by) "
            "VALUES(%s,%s,%s,%s,%s,'documents',%s,%s,%s,%s,%s) RETURNING *",
            [
                org_id_s,
                project_id_s,
                str(payment["id"]),
                receipt_code,
                json.dumps(payload),
                object_key,
                content_hash,
                media_type,
                len(content),
                str(actor_id),
            ],
        )
    except Exception:
        try:
            storage.delete_object(object_key)
        except Exception:  # noqa: BLE001 — evidence cleanup must not mask the real failure
            pass
        raise
    return _receipt_public(row)


def receipt_access(
    *, org_id: UUID, project_id: UUID, payment_id: UUID
) -> dict:
    with documentary_backend():
        receipt = rows(
            "SELECT receipt.*, payment.voided_at AS payment_voided_at,"
            " payment.void_reason AS payment_void_reason"
            " FROM public.payment_receipts receipt"
            " JOIN public.project_payments payment"
            " ON payment.id=receipt.payment_id AND payment.org_id=receipt.org_id"
            " WHERE receipt.org_id=%s AND receipt.project_id=%s AND receipt.payment_id=%s",
            [str(org_id), str(project_id), str(payment_id)],
        )
        if not receipt:
            raise contract_error(
                404, "payment_receipt_not_found", "El comprobante no está disponible."
            )
        receipt = receipt[0]
        storage = SupabaseDocumentStorage()
        object_key = str(receipt["storage_object_key"])
        # A voided payment's original artifact stays sealed and untouched — the
        # annulled render is created lazily alongside and served instead.
        if receipt.get("payment_voided_at") and not receipt.get("annulled_object_key"):
            payload = decoded(str(receipt["payload_json"]))
            payload["voided"] = {
                "at": receipt["payment_voided_at"].isoformat()
                if hasattr(receipt["payment_voided_at"], "isoformat")
                else receipt["payment_voided_at"],
                "reason": receipt["payment_void_reason"],
            }
            identifier = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            content, media_type = render_payment_receipt(
                payload, pdf_identifier=identifier
            )
            annulled_key = object_key.replace(".pdf", "_anulado.pdf")
            storage.upload_immutable(annulled_key, content, media_type)
            try:
                one(
                    "UPDATE public.payment_receipts SET annulled_object_key=%s,"
                    " annulled_file_sha256=%s, annulled_byte_size=%s"
                    " WHERE id=%s AND org_id=%s AND annulled_object_key IS NULL"
                    " RETURNING id",
                    [annulled_key, _file_sha256(content), len(content),
                     str(receipt["id"]), str(org_id)],
                )
                object_key = annulled_key
            except Exception:
                try:
                    storage.delete_object(annulled_key)
                except Exception:  # noqa: BLE001
                    pass
                raise
        elif receipt.get("annulled_object_key"):
            object_key = str(receipt["annulled_object_key"])
        signed_url = storage.signed_url(
            object_key, expires_in=SIGNED_URL_TTL_SECONDS
        )
    return {
        **_receipt_public(receipt),
        "signed_url": signed_url,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }
