"""Despachos — lista transversal de entregas e instalaciones.

La hoja de ruta del despacho: cada entrega con su OT, su proyecto y su
estado real. ``when`` filtra en la zona horaria de la organización (la
misma regla «hoy» que usa el resumen operacional y la cola de Hoy).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction

from documents.repository import documentary_backend, rows

_WHEN = ("open", "today", "overdue", "all")
_DELIVERY_STATUSES = ("SCHEDULED", "ON_ROUTE", "DELIVERED", "FAILED")


def list_deliveries(
    *, org_id: UUID, when: str = "open", status: str | None = None
) -> dict[str, Any]:
    if when not in _WHEN:
        when = "open"
    if status is not None and status not in _DELIVERY_STATUSES:
        status = None

    clauses = ["d.org_id = %s"]
    params: list[Any] = [str(org_id)]
    if when == "today":
        clauses.append("d.scheduled_date = zone.local_today")
    elif when == "overdue":
        clauses.append(
            "d.scheduled_date < zone.local_today AND d.status <> 'DELIVERED'"
        )
    elif when == "open":
        # Abierto = aún hay algo por hacer: la entrega no cerró, o cerró y
        # la instalación sigue pendiente (la OT quedó DISPATCHED).
        clauses.append(
            "(d.status IN ('SCHEDULED', 'ON_ROUTE', 'FAILED')"
            " OR (d.status = 'DELIVERED' AND o.status::text = 'DISPATCHED'))"
        )
    if status:
        clauses.append("d.status = %s")
        params.append(status)

    with transaction.atomic(), documentary_backend():
        items = rows(
            f"""
            SELECT d.id, d.order_id, d.scheduled_date, d.time_window, d.status,
                   d.address, d.contact_name, d.contact_phone, d.installer_name,
                   d.notes, d.unit_indexes, d.created_at, d.updated_at,
                   o.order_code, o.status::text AS order_status,
                   p.id AS project_id, p.code AS project_code,
                   p.name AS project_name, p.client_name
            FROM public.deliveries d
            JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id
            JOIN public.projects p ON p.id = o.project_id AND p.org_id = p.org_id,
            LATERAL (
                SELECT (CURRENT_TIMESTAMP AT TIME ZONE org.timezone)::date
                       AS local_today
                FROM public.tenancy_organizations AS org
                WHERE org.id = %s
            ) AS zone
            WHERE {' AND '.join(clauses)}
            ORDER BY d.scheduled_date DESC, d.time_window, o.order_code
            LIMIT 300
            """,
            [str(org_id), *params],
        )
    return {
        "items": [
            {
                "id": str(d["id"]),
                "order_id": str(d["order_id"]),
                "order_code": d["order_code"],
                "order_status": d["order_status"],
                "project_id": str(d["project_id"]),
                "project_code": d["project_code"],
                "project_name": d["project_name"],
                "client_name": d["client_name"],
                "scheduled_date": str(d["scheduled_date"]),
                "time_window": d["time_window"],
                "status": d["status"],
                "address": d["address"],
                "contact_name": d["contact_name"],
                "contact_phone": d["contact_phone"],
                "installer_name": d["installer_name"],
                "notes": d["notes"],
                "unit_indexes": d["unit_indexes"],
                "created_at": d["created_at"].isoformat(),
                "updated_at": d["updated_at"].isoformat(),
            }
            for d in items
        ]
    }
