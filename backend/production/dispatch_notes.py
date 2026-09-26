"""Dispatch notes — a sealed guía de despacho per work order.

The note is issued inside ``dispatch_work_order``'s transaction the moment
the order flips to DISPATCHED: same atomicity, same idempotency (UNIQUE
work_order_id — a replayed dispatch finds the already-sealed row, never a
re-render). The PDF freezes the order, the destination, and the packing
manifest AT THE TIME OF ISSUE into payload_json; the immutable storage
object is written under the same documents bucket policy as every sealed
artifact.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from django.utils import timezone

from authentication.errors import contract_error
from documents.repository import documentary_backend
from documents.renderers import render_dispatch_note
from documents.storage import SupabaseDocumentStorage
from pricing.repository import one, rows
from projects import org_branding

SIGNED_URL_TTL_SECONDS = 600

_MANIFEST_SCHEMA = "work_order_packing_v1"


def _file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _note_public(row) -> dict:
    return {
        "id": str(row["id"]),
        "note_code": row["note_code"],
        "work_order_id": str(row["work_order_id"]),
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
        "voided_at": (
            row["voided_at"].isoformat()
            if row.get("voided_at") is not None
            else None
        ),
        "voided_reason": row.get("voided_reason"),
    }


def _manifest_units(payload: dict) -> list[dict]:
    packing = (payload or {}).get("packing") or {}
    if packing.get("schema") != _MANIFEST_SCHEMA:
        return []
    units = []
    for unit in packing.get("units") or []:
        units.append(
            {
                "label_code": unit.get("label_code"),
                "profiles": unit.get("profiles"),
                "reinforcements": unit.get("reinforcements"),
                "glasses": unit.get("glasses"),
                "panels": unit.get("panels"),
                "hardware": unit.get("hardware"),
                "fittings": unit.get("fittings"),
            }
        )
    return units


def issue_dispatch_note(
    *,
    org_id: UUID,
    order: dict,
    project: dict,
    actor_id: UUID,
    note: str | None,
) -> dict:
    """Seal the guía de despacho for a freshly dispatched work order. Must
    run inside the caller's transaction: an org-scoped advisory lock
    serializes the note sequence, which is per-organization — the code must
    satisfy UNIQUE (org_id, note_code) across every project."""
    org_id_s, order_id_s = str(org_id), str(order["id"])
    existing = rows(
        "SELECT * FROM public.dispatch_notes "
        "WHERE work_order_id=%s AND org_id=%s AND voided_at IS NULL",
        [order_id_s, org_id_s],
    )
    if existing:
        return _note_public(existing[0])

    one(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        [f"dispatch_notes:{org_id_s}"],
    )
    sequence = int(
        one(
            "SELECT COUNT(*) AS n FROM public.dispatch_notes WHERE org_id=%s",
            [org_id_s],
        )["n"]
    )
    note_code = f"GD-{sequence + 1:04d}"
    order_payload = order["payload_json"] if isinstance(order["payload_json"], dict) else json.loads(order["payload_json"] or "{}")
    units = _manifest_units(order_payload)
    payload = {
        "note_code": note_code,
        "organization": org_branding.branding_for_snapshot(org_id=org_id),
        "issued_at": timezone.now().isoformat(),
        "order": {
            "code": order["order_code"],
            "id": order_id_s,
            "position_id": order_payload.get("position_id"),
            "quantity": order_payload.get("quantity"),
        },
        "project": {
            "code": project["code"],
            "name": project["name"],
            "client_name": project["client_name"],
            "client_rut": project["client_rut"],
            "delivery_address": project["delivery_address"],
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
        "dispatch": {
            "dispatched_by": str(actor_id),
            "note": note,
        },
    }
    identifier = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    content, media_type = render_dispatch_note(payload, pdf_identifier=identifier)
    content_hash = _file_sha256(content)
    object_key = (
        f"org_{org_id_s}/projects/{order['project_id']}/dispatch-notes/"
        f"{note_code.lower()}_{content_hash[:16]}.pdf"
    )
    storage = SupabaseDocumentStorage()
    try:
        storage.upload_immutable(object_key, content, media_type)
        row = one(
            "INSERT INTO public.dispatch_notes("
            "org_id,project_id,work_order_id,note_code,payload_json,storage_bucket,"
            "storage_object_key,file_sha256,media_type,byte_size,created_by) "
            "VALUES(%s,%s,%s,%s,%s,'documents',%s,%s,%s,%s,%s) RETURNING *",
            [
                org_id_s,
                str(order["project_id"]),
                order_id_s,
                note_code,
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
    return _note_public(row)


def dispatch_note_access(*, org_id: UUID, order_id: UUID) -> dict:
    with documentary_backend():
        note = rows(
            "SELECT * FROM public.dispatch_notes "
            "WHERE org_id=%s AND work_order_id=%s "
            "ORDER BY created_at DESC",
            [str(org_id), str(order_id)],
        )
        if not note:
            raise contract_error(
                404, "dispatch_note_not_found", "La guía de despacho no está disponible."
            )
        note = note[0]
        storage = SupabaseDocumentStorage()
        signed_url = storage.signed_url(
            str(note["storage_object_key"]), expires_in=SIGNED_URL_TTL_SECONDS
        )
        repr_row = rows(
            "SELECT repr_storage_object_key FROM public.project_dtes "
            "WHERE org_id=%s AND dispatch_note_id=%s",
            [str(org_id), str(note["id"])],
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
        **_note_public(note),
        "signed_url": signed_url,
        "tributario_signed_url": tributario_signed_url,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }
