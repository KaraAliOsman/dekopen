"""Postventa — tickets de garantía y servicio (P23).

Un ticket amarra cliente, obra, posición (vía la OT) y pieza cuando hay
escaneo; el plazo de garantía viene del sello de la revisión aprobada
(``snapshot.project.warranty_months``, meses sobre la fecha de
instalación). El ciclo es OPEN → SCHEDULED → IN_PROGRESS → CLOSED, con
diagnóstico, visita agendada (cuadrilla) y nota de cierre.
"""

from __future__ import annotations

import json
from datetime import date, datetime
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
from .service import _days_in_month, _payload

_NEXT = {
    "SCHEDULED": ("OPEN",),
    "IN_PROGRESS": ("SCHEDULED",),
    "CLOSED": ("IN_PROGRESS", "SCHEDULED", "OPEN"),
    "CANCELLED": ("OPEN", "SCHEDULED", "IN_PROGRESS"),
}


def _in_warranty(ticket: dict, today: date) -> bool:
    until = ticket.get("warranty_until")
    if until is None:
        return False
    return until >= today


def ticket_public(row: dict, *, today: date | None = None) -> dict:
    today = today or date.today()
    return {
        "id": str(row["id"]),
        "code": row["code"],
        "project_id": str(row["project_id"]),
        "project_code": row.get("project_code"),
        "project_name": row.get("project_name"),
        "client_name": row.get("client_name"),
        "site_address": row.get("site_address"),
        "order_id": str(row["order_id"]) if row["order_id"] else None,
        "order_code": row.get("order_code"),
        "unit_index": row["unit_index"],
        "piece_code": row["piece_code"],
        "incident_id": str(row["incident_id"]) if row["incident_id"] else None,
        "kind": row["kind"],
        "description": row["description"],
        "diagnosis": row["diagnosis"],
        "photos": decoded(row["photos"]) or [],
        "warranty_until": (
            str(row["warranty_until"]) if row["warranty_until"] else None
        ),
        "warranty_months": row["warranty_months"],
        "in_warranty": _in_warranty(row, today),
        "status": row["status"],
        "scheduled_visit_at": (
            row["scheduled_visit_at"].isoformat()
            if row["scheduled_visit_at"] else None
        ),
        "scheduled_crew_id": (
            str(row["scheduled_crew_id"]) if row["scheduled_crew_id"] else None
        ),
        "crew_name": row.get("crew_name"),
        "visit_note": row["visit_note"],
        "close_note": row["close_note"],
        "closed_at": row["closed_at"].isoformat() if row["closed_at"] else None,
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


_TICKET_SELECT = """
    SELECT t.*, p.code AS project_code, p.name AS project_name,
           p.client_name, p.delivery_address AS site_address,
           o.order_code, c.name AS crew_name
    FROM public.service_tickets t
    JOIN public.projects p ON p.id = t.project_id AND p.org_id = t.org_id
    LEFT JOIN public.orders o ON o.id = t.order_id AND o.org_id = t.org_id
    LEFT JOIN public.field_crews c ON c.id = t.scheduled_crew_id
"""


def list_tickets(
    *,
    org_id: UUID,
    status: str | None = None,
    project_id: UUID | None = None,
) -> dict:
    clauses = ["t.org_id = %s"]
    params: list = [str(org_id)]
    if status in ("OPEN", "SCHEDULED", "IN_PROGRESS", "CLOSED", "CANCELLED"):
        clauses.append("t.status = %s")
        params.append(status)
    if project_id is not None:
        clauses.append("t.project_id = %s")
        params.append(str(project_id))
    with documentary_backend():
        found = rows(
            _TICKET_SELECT
            + f"WHERE {' AND '.join(clauses)} "
            + "ORDER BY t.status IN ('OPEN','SCHEDULED','IN_PROGRESS') DESC,"
              " t.created_at DESC LIMIT 300",
            params,
        )
    today = _org_today(org_id)
    return {"tickets": [ticket_public(row, today=today) for row in found]}


def get_ticket(*, org_id: UUID, ticket_id: UUID) -> dict:
    with documentary_backend():
        found = rows(
            _TICKET_SELECT + "WHERE t.id=%s AND t.org_id=%s",
            [str(ticket_id), str(org_id)],
        )
    if not found:
        raise DocumentaryError("service_ticket_not_found")
    return {"ticket": ticket_public(found[0], today=_org_today(org_id))}


def _org_today(org_id) -> date:
    row = one(
        "SELECT (CURRENT_TIMESTAMP AT TIME ZONE timezone)::date AS today "
        "FROM public.tenancy_organizations WHERE id=%s",
        [str(org_id)],
        "organization_not_found",
    )
    return row["today"]


def _warranty_for_order(*, org_id: UUID, order_id: UUID, order_payload: dict) -> tuple:
    """(months, until) — meses sellados en la revisión aprobada sobre la
    fecha de instalación; None si el sello no declara plazo."""
    months = None
    version_id = None
    order = rows(
        "SELECT project_version_id FROM public.orders WHERE id=%s AND org_id=%s",
        [str(order_id), str(org_id)],
    )
    if order:
        version_id = order[0]["project_version_id"]
    if version_id:
        found = rows(
            "SELECT snapshot_json->'project'->>'warranty_months' AS months "
            "FROM public.project_versions WHERE id=%s AND org_id=%s",
            [str(version_id), str(org_id)],
        )
        if found and found[0]["months"] is not None:
            try:
                months = int(found[0]["months"])
            except (TypeError, ValueError):
                months = None
    until = None
    if months is not None:
        event = rows(
            "SELECT created_at FROM public.production_step_events "
            "WHERE org_id=%s AND order_id=%s AND event='WO_INSTALLED' "
            "ORDER BY created_at DESC LIMIT 1",
            [str(org_id), str(order_id)],
        )
        base = event[0]["created_at"] if event else None
        if base is not None:
            base_day = base.date() if isinstance(base, datetime) else base
            year = base_day.year + (base_day.month + months - 1) // 12
            month = (base_day.month + months - 1) % 12 + 1
            day = min(base_day.day, _days_in_month(year, month))
            until = date(year, month, day)
    return months, until


def create_ticket(
    *,
    org_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    kind: str,
    description: str,
    operation_key: str,
    order_id: UUID | None = None,
    unit_index: int | None = None,
    piece_code: str | None = None,
    incident_id: UUID | None = None,
    diagnosis: str | None = None,
    photos: list | None = None,
    scheduled_visit_at=None,
    scheduled_crew_id=None,
) -> dict:
    operation_key = (operation_key or "").strip()
    if not operation_key:
        raise contract_error(
            400, "operation_key_required", "El ticket necesita su clave de operación."
        )
    if kind not in ("WARRANTY", "SERVICE"):
        raise contract_error(400, "ticket_kind_invalid", "El tipo de ticket no es válido.")
    if not (description or "").strip():
        raise contract_error(400, "ticket_description_required", "El ticket necesita descripción.")
    photo_entries = validated_photos(org_id=org_id, raw=photos)
    with transaction.atomic(), documentary_backend():
        replay = rows(
            "SELECT * FROM public.service_tickets "
            "WHERE org_id=%s AND operation_key=%s",
            [str(org_id), operation_key],
        )
        if replay:
            return {"ticket": get_ticket(org_id=org_id, ticket_id=replay[0]["id"])["ticket"],
                    "replayed": True}
        project = rows(
            "SELECT id FROM public.projects WHERE id=%s AND org_id=%s",
            [str(project_id), str(org_id)],
        )
        if not project:
            raise DocumentaryError("project_not_found")
        order_payload = {}
        if order_id is not None:
            order = rows(
                "SELECT id, payload_json::text AS payload_json "
                "FROM public.orders WHERE id=%s AND org_id=%s "
                "AND order_type='WORKSHOP_OT'",
                [str(order_id), str(org_id)],
            )
            if not order:
                raise contract_error(
                    400, "work_order_not_found", "La OT no pertenece a esta obra."
                )
            order_payload = _payload(order[0])
        warranty_months, warranty_until = (None, None)
        if order_id is not None and kind == "WARRANTY":
            warranty_months, warranty_until = _warranty_for_order(
                org_id=org_id, order_id=order_id, order_payload=order_payload
            )
        status = "SCHEDULED" if scheduled_visit_at else "OPEN"
        code = next_human_code(org_id, "service_tickets")
        row = one(
            """
            INSERT INTO public.service_tickets
                (org_id, code, project_id, order_id, unit_index, piece_code,
                 incident_id, kind, description, diagnosis, photos,
                 warranty_until, warranty_months, status,
                 scheduled_visit_at, scheduled_crew_id, operation_key, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            [
                str(org_id),
                code,
                str(project_id),
                str(order_id) if order_id else None,
                unit_index,
                (piece_code or "").strip() or None,
                str(incident_id) if incident_id else None,
                kind,
                (description or "").strip(),
                (diagnosis or "").strip() or None,
                json.dumps(photo_entries),
                warranty_until,
                warranty_months,
                status,
                scheduled_visit_at,
                str(scheduled_crew_id) if scheduled_crew_id else None,
                operation_key,
                str(actor_id),
            ],
            "service_ticket_rejected",
        )
        if order_id is not None:
            rows(
                """
                INSERT INTO public.production_step_events
                    (org_id, order_id, event, actor_id, payload)
                VALUES (%s,%s,'WO_SERVICE_OPENED',%s,%s::jsonb) RETURNING id
                """,
                [
                    str(org_id),
                    str(order_id),
                    str(actor_id),
                    json.dumps({"ticket_code": code, "kind": kind}),
                ],
            )
    return {"ticket": get_ticket(org_id=org_id, ticket_id=row["id"])["ticket"],
            "replayed": False}


def transition_ticket(
    *,
    org_id: UUID,
    ticket_id: UUID,
    actor_id: UUID,
    to_status: str,
    scheduled_visit_at=None,
    scheduled_crew_id=None,
    visit_note: str | None = None,
    diagnosis: str | None = None,
    close_note: str | None = None,
) -> dict:
    target = str(to_status or "").upper()
    if target not in _NEXT:
        raise contract_error(400, "ticket_transition_invalid", "La transición no es válida.")
    with transaction.atomic(), documentary_backend():
        ticket = rows(
            "SELECT * FROM public.service_tickets WHERE id=%s AND org_id=%s FOR UPDATE",
            [str(ticket_id), str(org_id)],
        )
        if not ticket:
            raise DocumentaryError("service_ticket_not_found")
        ticket = ticket[0]
        current = str(ticket["status"])
        if current == target:
            return {"ticket": get_ticket(org_id=org_id, ticket_id=ticket_id)["ticket"]}
        if current not in _NEXT[target]:
            raise contract_error(
                409,
                "ticket_transition_invalid",
                "El ticket no puede pasar de su estado actual al destino.",
            )
        if target == "SCHEDULED" and scheduled_visit_at is None:
            raise contract_error(
                400, "ticket_visit_required", "Agendar requiere la fecha de visita."
            )
        if target == "CLOSED" and not (close_note or visit_note or "").strip():
            raise contract_error(
                400, "ticket_close_note_required", "El cierre necesita una nota de resolución."
            )
        if scheduled_crew_id is not None:
            crew = rows(
                "SELECT id FROM public.field_crews WHERE id=%s AND org_id=%s AND active",
                [str(scheduled_crew_id), str(org_id)],
            )
            if not crew:
                raise contract_error(
                    400, "crew_not_found", "La cuadrilla no existe o está inactiva."
                )
        assignments = ["status=%s", "updated_at=NOW()"]
        params: list = [target]
        if target == "SCHEDULED":
            assignments += ["scheduled_visit_at=%s"]
            params.append(scheduled_visit_at)
            if scheduled_crew_id is not None:
                assignments += ["scheduled_crew_id=%s"]
                params.append(str(scheduled_crew_id))
        if visit_note is not None:
            assignments += ["visit_note=%s"]
            params.append(visit_note.strip() or None)
        if diagnosis is not None:
            assignments += ["diagnosis=%s"]
            params.append(diagnosis.strip() or None)
        if target == "CLOSED":
            assignments += ["close_note=%s", "closed_at=NOW()", "closed_by=%s"]
            params += [(close_note or visit_note or "").strip() or None, str(actor_id)]
        one(
            "UPDATE public.service_tickets SET " + ", ".join(assignments)
            + " WHERE id=%s AND org_id=%s RETURNING id",
            [*params, str(ticket_id), str(org_id)],
            "service_ticket_not_found",
        )
        if ticket["order_id"] and target in ("SCHEDULED", "CLOSED"):
            event = (
                "WO_SERVICE_VISIT" if target == "SCHEDULED" else "WO_SERVICE_CLOSED"
            )
            rows(
                """
                INSERT INTO public.production_step_events
                    (org_id, order_id, event, actor_id, payload)
                VALUES (%s,%s,%s,%s,%s::jsonb) RETURNING id
                """,
                [
                    str(org_id),
                    str(ticket["order_id"]),
                    event,
                    str(actor_id),
                    json.dumps({"ticket_code": ticket["code"], "to": target}),
                ],
            )
    return {"ticket": get_ticket(org_id=org_id, ticket_id=ticket_id)["ticket"]}
