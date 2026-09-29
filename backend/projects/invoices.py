"""Project invoices — a sealed factura per explicit emission on the deal.

An invoice is issued by a human click against the project's latest sealed
revision: ``payload_json`` freezes the revision code, the project header,
the deal totals, the position lines, and the collected balance AT THE TIME
OF ISSUE into an immutable PDF. A project without a sealed revision has no
invoiceable deal — emission is a 409, never an invented total.

An emitted invoice is evidence: it is never updated or deleted. Correcting
a wrong emission is a credit note, a separate document type.
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from authentication.errors import contract_error
from documents.repository import documentary_backend
from documents.renderers import render_project_invoice
from documents.storage import SupabaseDocumentStorage
from pricing.repository import one, rows
from projects import org_branding, sii, sii_envio

logger = logging.getLogger(__name__)

SIGNED_URL_TTL_SECONDS = 600


def _invoice_public(
    row, credit_note: dict | None = None, dte: dict | None = None
) -> dict:
    return {
        "id": str(row["id"]),
        "invoice_code": row["invoice_code"],
        "project_id": str(row["project_id"]),
        "revision_code": row["payload_json"].get("revision_code")
        if isinstance(row["payload_json"], dict)
        else json.loads(row["payload_json"]).get("revision_code"),
        "credit_note": credit_note,
        "dte": dte,
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
    }


def _credit_note_public(row, invoice, dte: dict | None = None) -> dict:
    """The annulment chip attached to an invoice — same public shape the
    payments summary joins, so every surface reports the same state."""
    return {
        "id": str(row["id"]),
        "credit_code": row["credit_code"],
        "invoice_id": str(row["invoice_id"]),
        "invoice_code": invoice["invoice_code"],
        "project_id": str(row["project_id"]),
        "dte": dte,
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
    }


def _credit_notes_by_invoice(org_id: UUID, project_id: UUID) -> dict:
    return {
        str(note["invoice_id"]): note
        for note in rows(
            "SELECT id,invoice_id,project_id,credit_code,created_at "
            "FROM public.project_credit_notes "
            "WHERE org_id=%s AND project_id=%s",
            [str(org_id), str(project_id)],
        )
    }


def _collected(org_id: UUID, project_id: UUID) -> Decimal:
    total = one(
        "SELECT COALESCE(SUM(amount), 0) AS collected FROM public.project_payments "
        "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
        [str(org_id), str(project_id)],
    )["collected"]
    return Decimal(str(total))


def _sealed_deal(org_id: UUID, project_id: UUID) -> dict | None:
    """The invoiceable deal: the latest sealed revision only. A live priced
    total that never froze is not a document the company may charge on."""
    version = rows(
        "SELECT id,revision_code,snapshot_json::text AS snapshot_json "
        "FROM public.project_versions "
        "WHERE org_id=%s AND project_id=%s ORDER BY emitted_at DESC,id DESC LIMIT 1",
        [str(org_id), str(project_id)],
    )
    if not version:
        return None
    version = version[0]
    snapshot = version["snapshot_json"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    project = snapshot.get("project") if isinstance(snapshot, dict) else None
    gross = (project or {}).get("total_price_gross")
    if gross is None:
        return None
    positions = snapshot.get("positions")
    return {
        "version_id": version["id"],
        "revision_code": version["revision_code"],
        "project": project,
        "net": Decimal(str(project.get("total_price_net") or "0")),
        "tax": Decimal(str(project.get("total_price_tax") or "0")),
        "gross": Decimal(str(gross)),
        "currency": project.get("currency") or "CLP",
        "payment_terms": project.get("payment_terms"),
        "positions": positions if isinstance(positions, list) else [],
    }


def issue_invoice(*, org_id: UUID, project: dict, actor_id: UUID) -> dict:
    """Seal a factura against the latest sealed revision. Called from the
    emit endpoint inside a transaction: an org-scoped advisory lock
    serializes the FAC sequence across every project of the org."""
    org_id_s, project_id_s = str(org_id), str(project["id"])
    object_key: str | None = None
    try:
        with transaction.atomic(), documentary_backend():
            deal = _sealed_deal(org_id, UUID(project_id_s))
            if deal is None:
                raise contract_error(
                    409,
                    "invoice_no_sealed_deal",
                    "El proyecto no tiene una revisión emitida para facturar.",
                )
            one(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                [f"project_invoices:{org_id_s}"],
            )
            sequence = int(
                one(
                    "SELECT COUNT(*) AS n FROM public.project_invoices WHERE org_id=%s",
                    [org_id_s],
                )["n"]
            )
            invoice_code = f"FAC-{sequence + 1:04d}"
            collected = _collected(org_id, UUID(project_id_s))
            # Every revision-bound field comes from the frozen header — a
            # successor may have already rewritten the live project's client
            # data, and the invoice must never mix two different states.
            sealed_project = deal["project"]
            payload = {
                "invoice_code": invoice_code,
                "organization": org_branding.branding_for_snapshot(org_id=org_id),
                "issued_at": timezone.now().isoformat(),
                "revision_code": deal["revision_code"],
                "project": {
                    "code": sealed_project.get("code"),
                    "name": sealed_project.get("name"),
                    "client_name": sealed_project.get("client_name"),
                    "client_rut": sealed_project.get("client_rut"),
                    "client_giro": sealed_project.get("client_giro"),
                    "client_comuna": sealed_project.get("client_comuna"),
                    "client_address": sealed_project.get("client_address"),
                    "delivery_address": sealed_project.get("delivery_address"),
                    "currency": deal["currency"],
                    "payment_terms": deal["payment_terms"],
                },
                "positions": [
                    {
                        "position_index": position.get("position_index"),
                        "typology": position.get("typology"),
                        "quantity": position.get("quantity"),
                        "width_mm": str(position.get("width_mm"))
                        if position.get("width_mm") is not None
                        else None,
                        "height_mm": str(position.get("height_mm"))
                        if position.get("height_mm") is not None
                        else None,
                        "location_tag": position.get("location_tag"),
                        # Frozen line net so the DTE can itemize per position
                        # (F24) — None for snapshots that predate the column.
                        "price_net": str(position.get("price_net"))
                        if position.get("price_net") is not None
                        else None,
                    }
                    for position in deal["positions"]
                ],
                "deal": {
                    "total_net": str(deal["net"]),
                    "total_tax": str(deal["tax"]),
                    "total_gross": str(deal["gross"]),
                    "currency": deal["currency"],
                },
                "balance": {
                    "collected": str(collected),
                    "amount_due": str(deal["gross"] - collected),
                },
            }
            identifier = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            content, media_type = render_project_invoice(
                payload, pdf_identifier=identifier
            )
            content_hash = hashlib.sha256(content).hexdigest()
            object_key = (
                f"org_{org_id_s}/projects/{project_id_s}/invoices/"
                f"{invoice_code.lower()}_{content_hash[:16]}.pdf"
            )
            storage = SupabaseDocumentStorage()
            try:
                storage.upload_immutable(object_key, content, media_type)
                row = one(
                    "INSERT INTO public.project_invoices("
                    "org_id,project_id,project_version_id,invoice_code,payload_json,"
                    "storage_bucket,storage_object_key,file_sha256,media_type,"
                    "byte_size,created_by) "
                    "VALUES(%s,%s,%s,%s,%s::jsonb,'documents',%s,%s,%s,%s,%s) "
                    "RETURNING *",
                    [
                        org_id_s,
                        project_id_s,
                        str(deal["version_id"]),
                        invoice_code,
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
                    object_key = None
                except Exception:  # noqa: BLE001 — cleanup must not mask the real failure
                    pass
                raise
    except Exception:
        # A rolled-back emission leaves the upload orphaned — purge it under
        # the same org slot so a retry is the only factura that exists.
        if object_key is not None:
            _purge_unreferenced_invoice(org_id=org_id, object_key=object_key)
        raise
    return _invoice_public(row)


def _purge_unreferenced_invoice(*, org_id: UUID, object_key: str) -> None:
    """Compensating delete for a rolled-back emission: serialize on the org
    slot shared with issue_invoice — a committed row that references the key
    wins, an orphan is removed without masking the original failure."""
    try:
        with transaction.atomic(), documentary_backend():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    [f"project_invoices:{org_id}"],
                )
            referenced = rows(
                "SELECT id FROM public.project_invoices "
                "WHERE org_id=%s AND storage_object_key=%s",
                [str(org_id), object_key],
            )
            if referenced:
                return
            SupabaseDocumentStorage().delete_object(object_key)
    except Exception as cleanup_error:  # noqa: BLE001
        logger.warning(
            "project_invoice_cleanup_failed",
            extra={"storage_object_key": object_key, "cleanup_error": str(cleanup_error)},
        )


def _dte_with_envio(dte, envios, invoice_id) -> dict | None:
    if dte is None:
        return None
    return {**dte, "envio": envios.get(str(invoice_id))}


def list_invoices(*, org_id: UUID, project_id: UUID) -> list[dict]:
    with documentary_backend():
        credit_notes = _credit_notes_by_invoice(org_id, project_id)
        dtes = sii.dtes_by_invoice(org_id=org_id, project_id=project_id)
        nc_dtes = sii.dtes_by_credit_note(org_id=org_id, project_id=project_id)
        envios = sii_envio.envios_by_invoice(org_id=org_id, project_id=project_id)
        nc_envios = sii_envio.envios_by_credit_note(
            org_id=org_id, project_id=project_id
        )
        return [
            _invoice_public(
                row,
                _credit_note_public(
                    credit_notes[str(row["id"])],
                    row,
                    (
                        {
                            **nc_dtes[str(credit_notes[str(row["id"])]["id"])],
                            "envio": nc_envios.get(
                                str(credit_notes[str(row["id"])]["id"])
                            ),
                        }
                        if str(credit_notes[str(row["id"])]["id"]) in nc_dtes
                        else None
                    ),
                )
                if str(row["id"]) in credit_notes
                else None,
                _dte_with_envio(dtes.get(str(row["id"])), envios, row["id"]),
            )
            for row in rows(
                "SELECT * FROM public.project_invoices "
                "WHERE org_id=%s AND project_id=%s ORDER BY created_at,id",
                [str(org_id), str(project_id)],
            )
        ]


def invoice_access(*, org_id: UUID, project_id: UUID, invoice_id: UUID) -> dict:
    with documentary_backend():
        invoice = rows(
            "SELECT * FROM public.project_invoices "
            "WHERE org_id=%s AND project_id=%s AND id=%s",
            [str(org_id), str(project_id), str(invoice_id)],
        )
        if not invoice:
            raise contract_error(
                404, "invoice_not_found", "La factura no está disponible."
            )
        invoice = invoice[0]
        credit_note = rows(
            "SELECT id,invoice_id,project_id,credit_code,created_at "
            "FROM public.project_credit_notes "
            "WHERE org_id=%s AND invoice_id=%s",
            [str(org_id), str(invoice_id)],
        )
        nc_dtes = sii.dtes_by_credit_note(org_id=org_id, project_id=project_id)
        storage = SupabaseDocumentStorage()
        signed_url = storage.signed_url(
            str(invoice["storage_object_key"]), expires_in=SIGNED_URL_TTL_SECONDS
        )
        # The customer-facing PDF carries the DTE's fiscal identity when the
        # factura is stamped; an internal copy stays byte-exact sealed.
        repr_row = rows(
            "SELECT repr_storage_object_key FROM public.project_dtes "
            "WHERE org_id=%s AND invoice_id=%s AND credit_note_id IS NULL",
            [str(org_id), str(invoice_id)],
        )
        tributario_signed_url = (
            storage.signed_url(
                str(repr_row[0].get("repr_storage_object_key")),
                expires_in=SIGNED_URL_TTL_SECONDS,
            )
            if repr_row and repr_row[0].get("repr_storage_object_key")
            else None
        )
    return {
        **_invoice_public(
            invoice,
            _credit_note_public(
                credit_note[0],
                invoice,
                nc_dtes.get(str(credit_note[0]["id"])),
            )
            if credit_note
            else None,
        ),
        "signed_url": signed_url,
        "tributario_signed_url": tributario_signed_url,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }
