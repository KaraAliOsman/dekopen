"""Credit notes — the only way to annul an emitted factura.

An invoice is sealed evidence: it is never updated or deleted. The
counter-document that cancels it is a nota de crédito, itself sealed
and immutable — ``payload_json`` freezes the annulled invoice's code,
the project header, the position lines, the credited totals and the
human-recorded reason at issue time.

One total credit note per invoice: ``UNIQUE(invoice_id)`` makes a
retried emission idempotent — the replay returns the already-sealed
row, never a re-render.
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
from documents.renderers import render_credit_note
from documents.storage import SupabaseDocumentStorage
from pricing.repository import one, rows
from projects import org_branding

logger = logging.getLogger(__name__)

SIGNED_URL_TTL_SECONDS = 600


def _credit_note_public(row) -> dict:
    payload = (
        row["payload_json"]
        if isinstance(row["payload_json"], dict)
        else json.loads(row["payload_json"])
    )
    return {
        "id": str(row["id"]),
        "credit_code": row["credit_code"],
        "invoice_id": str(row["invoice_id"]),
        "invoice_code": payload.get("invoice", {}).get("invoice_code"),
        "project_id": str(row["project_id"]),
        "partial": payload.get("credit_partial") is True,
        "credit_amount_gross": payload.get("credit_amount_gross"),
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
    }


def issue_credit_note(
    *,
    org_id: UUID,
    project: dict,
    invoice_id: UUID,
    actor_id: UUID,
    reason: str | None,
    amount: Decimal | None = None,
) -> dict:
    """Seal a nota de crédito annulling ``invoice_id``. Called from the emit
    endpoint inside a transaction: an org-scoped advisory lock serializes
    every credit-note emission across the org, so two clicks can never
    split into two counter-documents; UNIQUE(invoice_id) is the backstop."""
    org_id_s, project_id_s = str(org_id), str(project["id"])
    object_key: str | None = None
    try:
        with transaction.atomic(), documentary_backend():
            invoice = rows(
                "SELECT * FROM public.project_invoices "
                "WHERE id=%s AND org_id=%s AND project_id=%s",
                [str(invoice_id), org_id_s, project_id_s],
            )
            if not invoice:
                raise contract_error(
                    404, "invoice_not_found", "La factura no está disponible."
                )
            invoice = invoice[0]
            invoice_payload = invoice["payload_json"]
            if isinstance(invoice_payload, str):
                invoice_payload = json.loads(invoice_payload)
            # The org slot serializes every credit-note emission: the
            # check-then-insert below can never race a second click on the
            # same invoice, and UNIQUE(invoice_id) is the hard backstop.
            one(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                [f"project_credit_notes:{org_id_s}"],
            )
            # Share the DTE-33 folio lock before the stamped check: a timbraje
            # in flight can't race this annulment decision.
            one(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                [f"sii_folios:{org_id_s}:33"],
            )
            stamped = rows(
                "SELECT id FROM public.project_dtes "
                "WHERE org_id=%s AND invoice_id=%s AND credit_note_id IS NULL "
                "LIMIT 1",
                [org_id_s, str(invoice_id)],
            )
            if stamped:
                raise contract_error(
                    409,
                    "invoice_already_stamped",
                    "La factura ya tiene un DTE-33 — se anula timbrando una nota "
                    "de crédito electrónica (DTE-61), no con una nota interna.",
                )
            existing = rows(
                "SELECT * FROM public.project_credit_notes "
                "WHERE invoice_id=%s AND org_id=%s",
                [str(invoice_id), org_id_s],
            )
            if existing:
                return _credit_note_public(existing[0])
            credit_amount: Decimal | None = None
            if amount is not None:
                invoice_deal = invoice_payload.get("deal") or {}
                raw_total = invoice_deal.get("total_gross")
                if raw_total is None:
                    raise contract_error(
                        422,
                        "credit_note_amount_unverifiable",
                        "La factura no tiene un total verificable para un "
                        "crédito parcial.",
                    )
                total_gross = Decimal(str(raw_total))
                if amount > total_gross:
                    raise contract_error(
                        422,
                        "credit_note_amount_exceeds",
                        "El monto acredita más que el total de la factura.",
                    )
                credit_amount = amount
            row, object_key = seal_credit_note(
                invoice=invoice,
                org_id_s=org_id_s,
                project_id_s=project_id_s,
                project=project,
                reason=reason,
                actor_id=actor_id,
                credit_amount=credit_amount,
            )
    except Exception:
        if object_key is not None:
            _purge_unreferenced_credit_note(org_id=org_id, object_key=object_key)
        raise
    return _credit_note_public(row)


def seal_credit_note(
    *,
    invoice: dict,
    org_id_s: str,
    project_id_s: str,
    project: dict,
    reason: str | None,
    actor_id: UUID,
    credit_amount: Decimal | None = None,
) -> tuple[dict, str]:
    """Render, upload and insert the sealed counter-document for ``invoice``.

    Runs inside the caller's org-serialized transaction and returns
    ``(row, object_key)`` — the caller keeps the key in its own compensating
    purge so a rollback later in the same flow can't leave an orphan."""
    invoice_payload = invoice["payload_json"]
    if isinstance(invoice_payload, str):
        invoice_payload = json.loads(invoice_payload)
    sequence = int(
        one(
            "SELECT COUNT(*) AS n FROM public.project_credit_notes WHERE org_id=%s",
            [org_id_s],
        )["n"]
    )
    credit_code = f"NC-{sequence + 1:04d}"
    reason_text = (reason or "").strip() or None
    payload = {
        "credit_code": credit_code,
        "organization": org_branding.branding_for_snapshot(org_id=UUID(org_id_s)),
        "issued_at": timezone.now().isoformat(),
        "reason": reason_text,
        "invoice": {
            "id": str(invoice["id"]),
            "invoice_code": invoice["invoice_code"],
            "issued_at": invoice_payload.get("issued_at"),
        },
        "revision_code": invoice_payload.get("revision_code"),
        "project": invoice_payload.get("project") or {
            "code": project["code"],
            "name": project["name"],
            "client_name": project["client_name"],
            "client_rut": project["client_rut"],
        },
        "positions": invoice_payload.get("positions") or [],
        "deal": invoice_payload.get("deal") or {},
        "credit_amount_gross": (
            str(credit_amount)
            if credit_amount is not None
            else None
        ),
        "credit_partial": (
            credit_amount is not None
            and (invoice_payload.get("deal") or {}).get("total_gross") is not None
            and credit_amount
            < Decimal(str(invoice_payload["deal"]["total_gross"]))
        ),
    }
    identifier = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    content, media_type = render_credit_note(payload, pdf_identifier=identifier)
    content_hash = hashlib.sha256(content).hexdigest()
    object_key = (
        f"org_{org_id_s}/projects/{project_id_s}/credit-notes/"
        f"{credit_code.lower()}_{content_hash[:16]}.pdf"
    )
    storage = SupabaseDocumentStorage()
    try:
        storage.upload_immutable(object_key, content, media_type)
        row = one(
            "INSERT INTO public.project_credit_notes("
            "org_id,project_id,invoice_id,credit_code,payload_json,"
            "storage_bucket,storage_object_key,file_sha256,media_type,"
            "byte_size,created_by) "
            "VALUES(%s,%s,%s,%s,%s::jsonb,'documents',%s,%s,%s,%s,%s) "
            "RETURNING *",
            [
                org_id_s,
                project_id_s,
                str(invoice["id"]),
                credit_code,
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
    return row, object_key


def _purge_unreferenced_credit_note(*, org_id: UUID, object_key: str) -> None:
    """Compensating delete for a rolled-back emission: serialize on the org
    slot shared with issue_credit_note — a committed row that references
    the key wins, an orphan is removed without masking the original failure."""
    try:
        with transaction.atomic(), documentary_backend():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    [f"project_credit_notes:{org_id}"],
                )
            referenced = rows(
                "SELECT id FROM public.project_credit_notes "
                "WHERE org_id=%s AND storage_object_key=%s",
                [str(org_id), object_key],
            )
            if referenced:
                return
            SupabaseDocumentStorage().delete_object(object_key)
    except Exception as cleanup_error:  # noqa: BLE001
        logger.warning(
            "project_credit_note_cleanup_failed",
            extra={"storage_object_key": object_key, "cleanup_error": str(cleanup_error)},
        )


def list_credit_notes(*, org_id: UUID, project_id: UUID) -> list[dict]:
    with documentary_backend():
        return [
            _credit_note_public(row)
            for row in rows(
                "SELECT * FROM public.project_credit_notes "
                "WHERE org_id=%s AND project_id=%s ORDER BY created_at,id",
                [str(org_id), str(project_id)],
            )
        ]


def credit_note_access(*, org_id: UUID, project_id: UUID, credit_note_id: UUID) -> dict:
    with documentary_backend():
        note = rows(
            "SELECT * FROM public.project_credit_notes "
            "WHERE org_id=%s AND project_id=%s AND id=%s",
            [str(org_id), str(project_id), str(credit_note_id)],
        )
        if not note:
            raise contract_error(
                404, "credit_note_not_found", "La nota de crédito no está disponible."
            )
        note = note[0]
        storage = SupabaseDocumentStorage()
        signed_url = storage.signed_url(
            str(note["storage_object_key"]), expires_in=SIGNED_URL_TTL_SECONDS
        )
        repr_row = rows(
            "SELECT repr_storage_object_key FROM public.project_dtes "
            "WHERE org_id=%s AND credit_note_id=%s",
            [str(org_id), str(credit_note_id)],
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
        **_credit_note_public(note),
        "signed_url": signed_url,
        "tributario_signed_url": tributario_signed_url,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }
