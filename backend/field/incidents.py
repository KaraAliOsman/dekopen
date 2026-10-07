"""Incidencias de obra (P23).

Daño, medida incorrecta, faltante o regulación — siempre amarrada a la OT
(posición) y, cuando la etiqueta se escanea, a la unidad o pieza. La
resolución desde la oficina es una de: remake (OT -RM sobre la misma
versión), solicitud de compra (SC-), ticket de postventa (PV-) o cierre
sin acción. Todo con foto y nota; nada free-text sin trazabilidad.
"""

from __future__ import annotations

import json
from uuid import UUID

from django.db import transaction

from authentication.errors import contract_error
from documents.repository import (
    DocumentaryError,
    documentary_backend,
    next_human_code,
    one,
    rows,
)
from pricing.service import decoded

from .evidence import validated_photos

_KINDS = ("DAMAGE", "WRONG_MEASURE", "MISSING", "ADJUSTMENT")
_RESOLUTIONS = ("REMAKE", "PURCHASE", "SERVICE", "NONE")


def incident_public(
    row: dict, *, order_code: str | None = None, project_code: str | None = None,
    resolution_ref_code: str | None = None,
) -> dict:
    return {
        "id": str(row["id"]),
        "code": row["code"],
        "order_id": str(row["order_id"]),
        "order_code": row.get("order_code") or order_code,
        "project_code": row.get("project_code") or project_code,
        "delivery_id": str(row["delivery_id"]) if row["delivery_id"] else None,
        "unit_index": row["unit_index"],
        "piece_code": row["piece_code"],
        "kind": row["kind"],
        "note": row["note"],
        "photos": decoded(row["photos"]) or [],
        "status": row["status"],
        "resolution_kind": row["resolution_kind"],
        "resolution_note": row["resolution_note"],
        "resolution_ref_id": (
            str(row["resolution_ref_id"]) if row["resolution_ref_id"] else None
        ),
        "resolution_ref_code": resolution_ref_code,
        "reported_by": str(row["reported_by"]) if row["reported_by"] else None,
        "reported_at": row["reported_at"].isoformat(),
        "resolved_by": str(row["resolved_by"]) if row["resolved_by"] else None,
        "resolved_at": (
            row["resolved_at"].isoformat() if row["resolved_at"] else None
        ),
        "created_at": row["created_at"].isoformat(),
    }


def list_incidents(
    *,
    org_id: UUID,
    status: str | None = None,
    kind: str | None = None,
    order_id: UUID | None = None,
) -> dict:
    clauses = ["i.org_id = %s"]
    params: list = [str(org_id)]
    if status in ("OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"):
        clauses.append("i.status = %s")
        params.append(status)
    if kind in _KINDS:
        clauses.append("i.kind = %s")
        params.append(kind)
    if order_id is not None:
        clauses.append("i.order_id = %s")
        params.append(str(order_id))
    with documentary_backend():
        found = rows(
            f"""
            SELECT i.*, o.order_code, p.code AS project_code,
                   COALESCE(rm.order_code, pr.code, st.code) AS resolution_ref_code
            FROM public.site_incidents i
            JOIN public.orders o ON o.id = i.order_id AND o.org_id = i.org_id
            JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
            LEFT JOIN public.orders rm ON rm.id = i.resolution_ref_id
            LEFT JOIN public.field_purchase_requests pr
                ON pr.id = i.resolution_ref_id
            LEFT JOIN public.service_tickets st
                ON st.id = i.resolution_ref_id
            WHERE {' AND '.join(clauses)}
            ORDER BY i.status IN ('OPEN','IN_PROGRESS') DESC,
                     i.reported_at DESC
            LIMIT 400
            """,
            params,
        )
    return {
        "incidents": [
            incident_public(row, resolution_ref_code=row.get("resolution_ref_code"))
            for row in found
        ]
    }


def report_incident(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    kind: str,
    operation_key: str,
    delivery_id: UUID | None,
    unit_index: int | None,
    piece_code: str | None,
    note: str | None,
    photos: list | None,
) -> dict:
    operation_key = (operation_key or "").strip()
    if not operation_key:
        raise contract_error(
            400, "operation_key_required", "La operación de terreno necesita su clave."
        )
    if kind not in _KINDS:
        raise contract_error(400, "incident_kind_invalid", "El tipo de incidencia no es válido.")
    photo_entries = validated_photos(org_id=org_id, raw=photos)
    with transaction.atomic(), documentary_backend():
        replay = rows(
            "SELECT * FROM public.site_incidents "
            "WHERE org_id=%s AND operation_key=%s",
            [str(org_id), operation_key],
        )
        if replay:
            return {"incident": incident_public(replay[0]), "replayed": True}
        order = rows(
            """
            SELECT o.id, o.order_code, o.status::text AS status,
                   o.payload_json::text AS payload_json,
                   p.code AS project_code
            FROM public.orders o
            JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
            WHERE o.id = %s AND o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
            FOR UPDATE OF o
            """,
            [str(order_id), str(org_id)],
        )
        if not order:
            raise DocumentaryError("work_order_not_found")
        order = order[0]
        if str(order["status"]) not in ("COMPLETED", "DISPATCHED", "INSTALLED"):
            raise contract_error(
                409,
                "incident_order_state",
                "La incidencia se reporta sobre una OT terminada, despachada o instalada.",
            )
        if unit_index is not None:
            payload = order["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            from .service import _manifest_units

            if int(unit_index) not in _manifest_units(payload):
                raise contract_error(
                    400, "incident_unit_invalid", "La unidad no pertenece a la OT."
                )
        if delivery_id is not None:
            found = rows(
                "SELECT id FROM public.deliveries WHERE id=%s AND org_id=%s AND order_id=%s",
                [str(delivery_id), str(org_id), str(order_id)],
            )
            if not found:
                raise contract_error(
                    400, "delivery_not_found", "El viaje no corresponde a esta OT."
                )
        code = next_human_code(org_id, "site_incidents")
        row = one(
            """
            INSERT INTO public.site_incidents
                (org_id, code, order_id, delivery_id, unit_index, piece_code,
                 kind, note, photos, operation_key, reported_by, reported_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,NOW())
            RETURNING *
            """,
            [
                str(org_id),
                code,
                str(order_id),
                str(delivery_id) if delivery_id else None,
                unit_index,
                (piece_code or "").strip() or None,
                kind,
                (note or "").strip() or None,
                json.dumps(photo_entries),
                operation_key,
                str(actor_id),
            ],
            "site_incident_rejected",
        )
        rows(
            """
            INSERT INTO public.production_step_events
                (org_id, order_id, event, actor_id, payload)
            VALUES (%s,%s,'WO_INCIDENT_REPORTED',%s,%s::jsonb) RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps(
                    {
                        "order_code": order["order_code"],
                        "incident_code": code,
                        "kind": kind,
                        "unit_index": unit_index,
                        "piece_code": row["piece_code"],
                    }
                ),
            ],
        )
    return {
        "incident": incident_public(
            row, order_code=order["order_code"], project_code=order["project_code"]
        ),
        "replayed": False,
    }


def _purchase_public(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "code": row["code"],
        "incident_id": str(row["incident_id"]),
        "incident_code": row.get("incident_code"),
        "item": row["item"],
        "quantity": str(row["quantity"]) if row["quantity"] is not None else None,
        "unit": row["unit"],
        "supplier_hint": row["supplier_hint"],
        "needed_at": str(row["needed_at"]) if row["needed_at"] else None,
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def resolve_incident(
    *,
    org_id: UUID,
    incident_id: UUID,
    actor_id: UUID,
    resolution_kind: str,
    note: str | None,
    purchase: dict | None,
) -> dict:
    """Resolución del jefe: remake (OT -RM), compra (SC-), servicio (PV-)
    o cierre sin acción. La incidencia queda RESOLVED y su destino enlazado."""
    if resolution_kind not in _RESOLUTIONS:
        raise contract_error(400, "incident_resolution_invalid", "La resolución no es válida.")
    with transaction.atomic(), documentary_backend():
        incident = rows(
            """
            SELECT i.*, o.order_code, p.code AS project_code, o.project_id,
                   o.payload_json::text AS payload_json
            FROM public.site_incidents i
            JOIN public.orders o ON o.id = i.order_id AND o.org_id = i.org_id
            JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
            WHERE i.id = %s AND i.org_id = %s FOR UPDATE OF i
            """,
            [str(incident_id), str(org_id)],
        )
        if not incident:
            raise DocumentaryError("incident_not_found")
        incident = incident[0]
        if incident["status"] == "RESOLVED":
            return {
                "incident": incident_public(incident),
                "remake_order_id": (
                    incident["resolution_ref_id"]
                    if incident["resolution_kind"] == "REMAKE" else None
                ),
                "remake_order_code": None,
                "purchase_request_code": None,
                "ticket_code": None,
                "replayed": True,
            }
        if incident["status"] == "CANCELLED":
            raise contract_error(
                409, "incident_cancelled", "La incidencia está anulada."
            )
        ref_id = None
        remake_order_id = None
        remake_order_code = None
        purchase_request_code = None
        ticket_code = None
        if resolution_kind == "REMAKE":
            from production.service import create_remake

            remake_order = create_remake(
                org_id=org_id,
                order_id=incident["order_id"],
                actor_id=actor_id,
                note=(note or "").strip()
                or f"Incidencia {incident['code']} ({incident['kind']})",
                remake_reason={
                    "kind": "SITE_INCIDENT",
                    "incident_code": incident["code"],
                    "incident_kind": incident["kind"],
                    "note": (note or "").strip() or None,
                },
            )
            ref_id = remake_order.get("id")
            remake_order_id = ref_id
            remake_order_code = remake_order.get("order_code")
        elif resolution_kind == "PURCHASE":
            item = ((purchase or {}).get("item") or "").strip()
            if not item:
                raise contract_error(
                    400, "purchase_item_required", "La solicitud de compra necesita el ítem."
                )
            request_code = next_human_code(org_id, "field_purchase_requests")
            purchase_row = one(
                """
                INSERT INTO public.field_purchase_requests
                    (org_id, code, incident_id, item, quantity, unit,
                     supplier_hint, needed_at, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                [
                    str(org_id),
                    request_code,
                    str(incident_id),
                    item,
                    (purchase or {}).get("quantity"),
                    ((purchase or {}).get("unit") or "").strip() or None,
                    ((purchase or {}).get("supplier_hint") or "").strip() or None,
                    (purchase or {}).get("needed_at"),
                    str(actor_id),
                ],
                "purchase_request_rejected",
            )
            ref_id = purchase_row["id"]
            purchase_request_code = request_code
            rows(
                """
                INSERT INTO public.production_step_events
                    (org_id, order_id, event, actor_id, payload)
                VALUES (%s,%s,'WO_PURCHASE_REQUESTED',%s,%s::jsonb) RETURNING id
                """,
                [
                    str(org_id),
                    str(incident["order_id"]),
                    str(actor_id),
                    json.dumps(
                        {
                            "order_code": incident["order_code"],
                            "incident_code": incident["code"],
                            "request_code": request_code,
                            "item": item,
                        }
                    ),
                ],
            )
        elif resolution_kind == "SERVICE":
            from .tickets import create_ticket

            ticket = create_ticket(
                org_id=org_id,
                project_id=incident["project_id"],
                actor_id=actor_id,
                kind="WARRANTY",
                description=(
                    (note or "").strip()
                    or f"Postventa desde incidencia {incident['code']}"
                ),
                operation_key=f"incident:{incident['code']}",
                order_id=incident["order_id"],
                unit_index=incident["unit_index"],
                piece_code=incident["piece_code"],
                incident_id=incident["id"],
                photos=decoded(incident["photos"]) or [],
            )
            ref_id = ticket["ticket"]["id"]
            ticket_code = ticket["ticket"]["code"]
        row = one(
            """
            UPDATE public.site_incidents
            SET status='RESOLVED', resolution_kind=%s, resolution_note=%s,
                resolution_ref_id=%s, resolved_by=%s, resolved_at=NOW(),
                updated_at=NOW()
            WHERE id=%s AND org_id=%s RETURNING *
            """,
            [
                resolution_kind,
                (note or "").strip() or None,
                ref_id,
                str(actor_id),
                str(incident_id),
                str(org_id),
            ],
            "incident_not_found",
        )
        rows(
            """
            INSERT INTO public.production_step_events
                (org_id, order_id, event, actor_id, payload)
            VALUES (%s,%s,'WO_INCIDENT_RESOLVED',%s,%s::jsonb) RETURNING id
            """,
            [
                str(org_id),
                str(incident["order_id"]),
                str(actor_id),
                json.dumps(
                    {
                        "order_code": incident["order_code"],
                        "incident_code": incident["code"],
                        "resolution": resolution_kind,
                        "remake": remake_order_code,
                        "purchase_request": purchase_request_code,
                        "ticket": ticket_code,
                    }
                ),
            ],
        )
    return {
        "incident": incident_public(
            row,
            order_code=incident["order_code"],
            project_code=incident["project_code"],
            resolution_ref_code=(
                remake_order_code or purchase_request_code or ticket_code
            ),
        ),
        "remake_order_id": remake_order_id,
        "remake_order_code": remake_order_code,
        "purchase_request_code": purchase_request_code,
        "ticket_code": ticket_code,
    }


def list_purchase_requests(*, org_id: UUID, status: str | None = None) -> dict:
    clauses = ["r.org_id = %s"]
    params: list = [str(org_id)]
    if status in ("PENDING", "ORDERED", "RECEIVED", "CANCELLED"):
        clauses.append("r.status = %s")
        params.append(status)
    with documentary_backend():
        found = rows(
            f"""
            SELECT r.*, i.code AS incident_code
            FROM public.field_purchase_requests r
            JOIN public.site_incidents i ON i.id = r.incident_id AND i.org_id = r.org_id
            WHERE {' AND '.join(clauses)}
            ORDER BY r.status = 'PENDING' DESC, r.created_at DESC
            LIMIT 300
            """,
            params,
        )
    return {"items": [_purchase_public(row) for row in found]}


def mark_purchase_request(
    *, org_id: UUID, request_id: UUID, status: str, actor_id: UUID
) -> dict:
    if status not in ("ORDERED", "RECEIVED", "CANCELLED"):
        raise contract_error(400, "purchase_status_invalid", "El estado no es válido.")
    allowed = {
        "ORDERED": ("PENDING",),
        "RECEIVED": ("PENDING", "ORDERED"),
        "CANCELLED": ("PENDING", "ORDERED"),
    }
    with transaction.atomic(), documentary_backend():
        row = one(
            """
            UPDATE public.field_purchase_requests
            SET status=%s, updated_at=NOW()
            WHERE id=%s AND org_id=%s AND status = ANY(%s)
            RETURNING *, (SELECT code FROM public.site_incidents WHERE id=incident_id) AS incident_code
            """,
            [status, str(request_id), str(org_id), list(allowed[status])],
            "purchase_request_not_found",
        )
    return {"item": _purchase_public(row)}
