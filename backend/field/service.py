"""P23 — Cuadrillas, planificación de despacho y agenda de terreno.

La planificación cruza día × cuadrilla/vehículo con las paradas de cada
reparto; la agenda del instalador lee los deliveries del día asignados a
él (installer_user_id) o a su cuadrilla, con la medición, el checklist y
las incidencias abiertas de cada posición.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import transaction

from authentication.errors import contract_error
from documents.repository import DocumentaryError, documentary_backend, one, rows


_WEEKDAY_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _crew_public(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "kind": row["kind"],
        "plate": row["plate"],
        "active": bool(row["active"]),
        "created_at": row["created_at"].isoformat(),
    }


def list_crews(*, org_id: UUID, include_inactive: bool = False) -> dict:
    clause = "" if include_inactive else " AND active"
    with documentary_backend():
        found = rows(
            f"SELECT * FROM public.field_crews WHERE org_id=%s{clause} "
            "ORDER BY kind, name",
            [str(org_id)],
        )
    return {"crews": [_crew_public(row) for row in found]}


def save_crew(*, org_id: UUID, data: dict, crew_id: UUID | None = None) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise contract_error(400, "crew_name_required", "La cuadrilla o vehículo necesita un nombre.")
    kind = str(data.get("kind") or "").upper()
    if kind not in ("VEHICLE", "TEAM"):
        raise contract_error(400, "crew_kind_invalid", "El tipo debe ser vehículo o cuadrilla.")
    plate = (data.get("plate") or "").strip().upper() or None
    with transaction.atomic(), documentary_backend():
        if crew_id is None:
            row = one(
                """
                INSERT INTO public.field_crews (org_id, name, kind, plate)
                VALUES (%s, %s, %s, %s) RETURNING *
                """,
                [str(org_id), name, kind, plate],
                "crew_save_failed",
            )
        else:
            assignments = ["name=%s", "kind=%s", "plate=%s", "updated_at=NOW()"]
            params: list[Any] = [name, kind, plate]
            if "active" in data:
                assignments.append("active=%s")
                params.append(bool(data["active"]))
            row = one(
                "UPDATE public.field_crews SET " + ", ".join(assignments)
                + " WHERE id=%s AND org_id=%s RETURNING *",
                [*params, str(crew_id), str(org_id)],
                "crew_not_found",
            )
    return {"crew": _crew_public(row), "crews": list_crews(org_id=org_id)["crews"]}


def _manifest_units(payload) -> set[int]:
    packing = (payload or {}).get("packing") or {}
    units = {
        int(unit["unit_index"])
        for unit in packing.get("units") or []
        if unit.get("unit_index") is not None
    }
    if units:
        return units
    quantity = int((payload or {}).get("quantity") or 1)
    return set(range(1, quantity + 1))


def dispatch_plan(*, org_id: UUID, start: date | None, days: int) -> dict:
    """Calendario día × cuadrilla: cada día lista las paradas planificadas
    (deliveries programados o en ruta) agrupadas por cuadrilla, más las OT
    embaladas listas para despachar."""
    days = max(1, min(int(days or 5), 14))
    start = start or _org_today(org_id)
    end = start + timedelta(days=days - 1)
    with documentary_backend():
        deliveries = rows(
            """
            SELECT d.id, d.order_id, d.scheduled_date, d.time_window, d.status,
                   d.address, d.installer_name, d.installer_user_id,
                   d.unit_indexes, d.crew_id, d.route_order, d.load_checked_at,
                   o.order_code, o.payload_json::text AS payload_json,
                   p.code AS project_code, p.name AS project_name, p.client_name,
                   (dn.id IS NOT NULL AND dn.voided_at IS NULL) AS note_issued
            FROM public.deliveries d
            JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id
            JOIN public.projects p ON p.id = o.project_id AND p.org_id = d.org_id
            LEFT JOIN public.dispatch_notes dn
                ON dn.work_order_id = o.id AND dn.org_id = o.org_id
            WHERE d.org_id = %s
              AND d.scheduled_date BETWEEN %s AND %s
              AND d.status IN ('SCHEDULED', 'ON_ROUTE', 'DELIVERED')
            ORDER BY d.scheduled_date, d.crew_id NULLS LAST,
                     d.route_order NULLS LAST, d.time_window, o.order_code
            """,
            [str(org_id), start, end],
        )
        ready = rows(
            """
            SELECT o.id, o.order_code, o.payload_json::text AS payload_json,
                   p.code AS project_code, p.client_name, p.delivery_address
            FROM public.orders o
            JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
            LEFT JOIN public.deliveries d
                ON d.order_id = o.id AND d.org_id = o.org_id
               AND d.status IN ('SCHEDULED', 'ON_ROUTE')
            WHERE o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
              AND o.status = 'COMPLETED'
              AND o.payload_json->'packing'->'units' IS NOT NULL
              AND d.id IS NULL
            ORDER BY o.order_code
            """,
            [str(org_id)],
        )
        crews = rows(
            "SELECT * FROM public.field_crews WHERE org_id=%s AND active ORDER BY kind, name",
            [str(org_id)],
        )
    days_out = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        stops = []
        for delivery in deliveries:
            if delivery["scheduled_date"] != day:
                continue
            manifest = _manifest_units(_payload(delivery))
            units = delivery["unit_indexes"]
            stops.append(
                {
                    "delivery_id": str(delivery["id"]),
                    "order_id": str(delivery["order_id"]),
                    "order_code": delivery["order_code"],
                    "project_code": delivery["project_code"],
                    "project_name": delivery["project_name"],
                    "client_name": delivery["client_name"],
                    "address": delivery["address"],
                    "time_window": delivery["time_window"],
                    "status": delivery["status"],
                    "route_order": delivery["route_order"],
                    "installer_name": delivery["installer_name"],
                    "installer_user_id": (
                        str(delivery["installer_user_id"])
                        if delivery["installer_user_id"] else None
                    ),
                    "units": (
                        sorted(int(i) for i in units) if units is not None else None
                    ),
                    "manifest_total": len(manifest),
                    "load_checked": delivery["load_checked_at"] is not None,
                    "note_issued": bool(delivery["note_issued"]),
                    "crew_id": (
                        str(delivery["crew_id"]) if delivery["crew_id"] else None
                    ),
                }
            )
        grouped: dict[str, list] = {}
        for stop in stops:
            grouped.setdefault(str(stop["crew_id"] or ""), []).append(stop)
        crew_slots = [
            {
                "crew_id": crew_key or None,
                "stops": grouped[crew_key],
            }
            for crew_key in grouped
        ]
        days_out.append(
            {
                "date": day.isoformat(),
                "weekday": _WEEKDAY_ES[day.weekday()],
                "today": day == date.today(),
                "crews": crew_slots,
            }
        )
    return {
        "days": days_out,
        "crews": [_crew_public(row) for row in crews],
        "ready": [
            {
                "order_id": str(order["id"]),
                "order_code": order["order_code"],
                "project_code": order["project_code"],
                "client_name": order["client_name"],
                "delivery_address": order["delivery_address"],
                "units": len(_manifest_units(_payload(order))),
            }
            for order in ready
        ],
    }


def _payload(order_row: dict) -> dict:
    import json

    raw = order_row.get("payload_json")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or {}


def _org_today(org_id) -> date:
    row = one(
        "SELECT (CURRENT_TIMESTAMP AT TIME ZONE timezone)::date AS today "
        "FROM public.tenancy_organizations WHERE id=%s",
        [str(org_id)],
        "organization_not_found",
    )
    return row["today"]


def field_agenda(*, org_id: UUID, user_id: UUID, day: date | None, mine_only: bool) -> dict:
    """La agenda del día: paradas del instalador (asignadas por
    installer_user_id o, si el jefe no asignó, todas las del día) con
    medición, checklist e incidencias abiertas por posición."""
    target = day or _org_today(org_id)
    member = rows(
        "SELECT role FROM public.tenancy_memberships "
        "WHERE user_id=%s AND org_id=%s AND is_active LIMIT 1",
        [str(user_id), str(org_id)],
    )
    role = member[0]["role"] if member else None
    sees_all = role in ("OWNER", "WORKSHOP_MANAGER") or not mine_only
    clauses = ["d.org_id = %s", "d.scheduled_date = %s",
               "d.status IN ('SCHEDULED', 'ON_ROUTE', 'DELIVERED', 'FAILED')"]
    params: list[Any] = [str(org_id), target]
    if not sees_all:
        clauses.append("d.installer_user_id = %s")
        params.append(str(user_id))
    with documentary_backend():
        deliveries = rows(
            f"""
            SELECT d.*, o.order_code, o.status::text AS order_status,
                   o.payload_json::text AS payload_json,
                   p.code AS project_code, p.name AS project_name, p.client_name,
                   pos.id AS position_id, pos.location_tag, pos.measurement_state
            FROM public.deliveries d
            JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id
            JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
            LEFT JOIN public.project_positions pos
                ON pos.id::text = o.payload_json->>'position_id' AND pos.org_id = o.org_id
            WHERE {' AND '.join(clauses)}
            ORDER BY d.route_order NULLS LAST, d.time_window, o.order_code
            """,
            params,
        )
        order_ids = [str(d["order_id"]) for d in deliveries]
        checks = (
            rows(
                "SELECT order_id, count(*) AS done "
                "FROM public.installation_checks WHERE org_id=%s AND order_id = ANY(%s) "
                "GROUP BY order_id",
                [str(org_id), order_ids],
            )
            if order_ids
            else []
        )
        incidents = (
            rows(
                "SELECT order_id, count(*) AS open "
                "FROM public.site_incidents WHERE org_id=%s AND order_id = ANY(%s) "
                "AND status IN ('OPEN','IN_PROGRESS') GROUP BY order_id",
                [str(org_id), order_ids],
            )
            if order_ids
            else []
        )
        confirmations = (
            rows(
                "SELECT order_id FROM public.delivery_confirmations "
                "WHERE org_id=%s AND order_id = ANY(%s)",
                [str(org_id), order_ids],
            )
            if order_ids
            else []
        )
        visits = rows(
            """
            SELECT t.id, t.code, t.scheduled_visit_at, t.status,
                   p.code AS project_code, p.client_name, p.delivery_address,
                   c.name AS crew_name
            FROM public.service_tickets t
            JOIN public.projects p ON p.id = t.project_id AND p.org_id = t.org_id
            LEFT JOIN public.field_crews c ON c.id = t.scheduled_crew_id
            WHERE t.org_id = %s AND t.status = 'SCHEDULED'
              AND t.scheduled_visit_at::date = %s
            ORDER BY t.scheduled_visit_at
            """,
            [str(org_id), target],
        )
    checks_by_order = {row["order_id"]: int(row["done"]) for row in checks}
    incidents_by_order = {row["order_id"]: int(row["open"]) for row in incidents}
    confirmed_orders = {row["order_id"] for row in confirmations}
    items = []
    for delivery in deliveries:
        payload = _payload(delivery)
        manifest = _manifest_units(payload)
        units = delivery["unit_indexes"]
        items.append(
            {
                "delivery_id": str(delivery["id"]),
                "order_id": str(delivery["order_id"]),
                "order_code": delivery["order_code"],
                "status": delivery["status"],
                "time_window": delivery["time_window"],
                "address": delivery["address"],
                "contact_name": delivery["contact_name"],
                "contact_phone": delivery["contact_phone"],
                "project_code": delivery["project_code"],
                "project_name": delivery["project_name"],
                "client_name": delivery["client_name"],
                "position_id": (
                    str(delivery["position_id"]) if delivery["position_id"] else None
                ),
                "location_tag": delivery["location_tag"],
                "units": (
                    sorted(int(i) for i in units) if units is not None else None
                ),
                "manifest_total": len(manifest),
                "notes": delivery["notes"],
                "crew_id": str(delivery["crew_id"]) if delivery["crew_id"] else None,
                "route_order": delivery["route_order"],
                "checklists_done": checks_by_order.get(delivery["order_id"], 0),
                "checks_total": len(manifest),
                "measurement_state": delivery["measurement_state"],
                "open_incidents": incidents_by_order.get(delivery["order_id"], 0),
                "confirmed": delivery["order_id"] in confirmed_orders,
            }
        )
    return {
        "date": target.isoformat(),
        "mine_only": not sees_all,
        "items": items,
        "service_visits": [
            {
                "ticket_id": str(visit["id"]),
                "code": visit["code"],
                "scheduled_visit_at": visit["scheduled_visit_at"].isoformat(),
                "project_code": visit["project_code"],
                "client_name": visit["client_name"],
                "address": visit["delivery_address"],
                "crew_name": visit["crew_name"],
            }
            for visit in visits
        ],
    }


def field_order_card(*, org_id: UUID, order_id: UUID) -> dict:
    """Una posición, una pantalla (F9): la OT con su obra, la posición y su
    medición D07, el viaje del día, el checklist, incidencias y la garantía."""
    with documentary_backend():
        order_row = rows(
            """
            SELECT o.id, o.order_code, o.status::text AS status,
                   o.project_id, o.project_version_id,
                   o.payload_json::text AS payload_json, o.created_at
            FROM public.orders o
            WHERE o.id = %s AND o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
            """,
            [str(order_id), str(org_id)],
        )
        if not order_row:
            raise DocumentaryError("work_order_not_found")
        order = order_row[0]
        payload = _payload(order)
        project_row = rows(
            """
            SELECT id, code, name, client_name, client_rut, client_phone,
                   delivery_address, status::text AS status, current_revision
            FROM public.projects WHERE id = %s AND org_id = %s
            """,
            [str(order["project_id"]), str(org_id)],
        )
        position_row = None
        position_id = payload.get("position_id")
        if position_id:
            found = rows(
                """
                SELECT id, location_tag, width_mm, height_mm, system_id,
                       quantity, measurement_state, rough_opening_input,
                       mounting_rule_id, fabrication_lock,
                       measurement_confirmed_at, measurement_confirmed_by
                FROM public.project_positions
                WHERE id = %s AND org_id = %s
                """,
                [str(position_id), str(org_id)],
            )
            position_row = found[0] if found else None
        delivery_rows = rows(
            """
            SELECT * FROM public.deliveries
            WHERE order_id = %s AND org_id = %s
            ORDER BY created_at DESC LIMIT 5
            """,
            [str(order_id), str(org_id)],
        )
        checklist_rows = rows(
            "SELECT * FROM public.installation_checks "
            "WHERE order_id = %s AND org_id = %s ORDER BY unit_index NULLS FIRST",
            [str(order_id), str(org_id)],
        )
        incident_rows = rows(
            "SELECT * FROM public.site_incidents "
            "WHERE order_id = %s AND org_id = %s ORDER BY reported_at DESC",
            [str(order_id), str(org_id)],
        )
        # Garantía: meses sellados en la revisión aprobada + fecha de
        # instalación/recepción de la OT.
        warranty = _warranty_block(org_id=org_id, order=order)
    project = project_row[0] if project_row else {}
    manifest = _manifest_units(payload)
    delivery = _delivery_field_public(delivery_rows[0]) if delivery_rows else None
    position_public = None
    measurement_public = None
    if position_row is not None:
        from projects.measurement import resolve_position_measurement

        measurement_public = resolve_position_measurement(org_id, position_row)
        position_public = {
            "id": str(position_row["id"]),
            "location_tag": position_row["location_tag"],
            "width_mm": str(position_row["width_mm"]),
            "height_mm": str(position_row["height_mm"]),
            "quantity": position_row["quantity"],
            "system_id": str(position_row["system_id"]),
            "mounting_rule_id": (
                str(position_row["mounting_rule_id"])
                if position_row["mounting_rule_id"] else None
            ),
            "measurement_state": position_row["measurement_state"],
        }
    return {
        "order": {
            "id": str(order["id"]),
            "order_code": order["order_code"],
            "status": order["status"],
            "quantity": int(payload.get("quantity") or len(manifest) or 1),
            "manifest_units": sorted(manifest),
            "position_id": position_id,
            "remake_of": payload.get("remake_of"),
            "address": (payload.get("site") or {}).get("address"),
        },
        "project": {
            "id": str(project.get("id")),
            "code": project.get("code"),
            "name": project.get("name"),
            "client_name": project.get("client_name"),
            "client_rut": project.get("client_rut"),
            "client_phone": project.get("client_phone"),
            "delivery_address": project.get("delivery_address"),
            "status": project.get("status"),
            "current_revision": project.get("current_revision"),
        },
        "position": position_public,
        "delivery": delivery,
        "measurement": measurement_public,
        "checklists": [_check_public(row) for row in checklist_rows],
        "incidents": [_incident_public(row, order["order_code"], project.get("code"))
                      for row in incident_rows],
        "warranty": warranty,
    }


def _delivery_field_public(delivery: dict) -> dict:
    units = delivery.get("unit_indexes")
    return {
        "id": str(delivery["id"]),
        "status": delivery["status"],
        "scheduled_date": str(delivery["scheduled_date"]),
        "time_window": delivery["time_window"],
        "address": delivery["address"],
        "contact_name": delivery["contact_name"],
        "contact_phone": delivery["contact_phone"],
        "installer_name": delivery["installer_name"],
        "crew_id": str(delivery["crew_id"]) if delivery["crew_id"] else None,
        "route_order": delivery["route_order"],
        "load_checked": delivery["load_checked_at"] is not None,
        "units": sorted(int(i) for i in units) if units is not None else None,
        "notes": delivery["notes"],
    }


def _check_public(row: dict) -> dict:
    from .checklists import check_public

    return check_public(row)


def _incident_public(row: dict, order_code: str, project_code) -> dict:
    from .incidents import incident_public

    return incident_public(row, order_code=order_code, project_code=project_code)


def _warranty_block(*, org_id: UUID, order: dict) -> dict | None:
    """Meses de garantía sellados en la revisión + fecha de instalación.
    Sin sello (órdenes pre-P23) el campo es 'Sin dato' — nunca inventado."""
    version_id = order.get("project_version_id")
    if not version_id:
        return {"months": None, "until": None, "installed_at": None}
    found = rows(
        """
        SELECT snapshot_json->'project'->>'warranty_months' AS months
        FROM public.project_versions
        WHERE id = %s AND org_id = %s
        """,
        [str(version_id), str(org_id)],
    )
    months = None
    if found and found[0]["months"] is not None:
        try:
            months = int(found[0]["months"])
        except (TypeError, ValueError):
            months = None
    installed_at = None
    event = rows(
        """
        SELECT created_at FROM public.production_step_events
        WHERE org_id=%s AND order_id=%s AND event='WO_INSTALLED'
        ORDER BY created_at DESC LIMIT 1
        """,
        [str(org_id), str(order["id"])],
    )
    if event:
        installed_at = event[0]["created_at"]
    until = None
    if months is not None and installed_at is not None:
        base = installed_at.date() if isinstance(installed_at, datetime) else installed_at
        year = base.year + (base.month + months - 1) // 12
        month = (base.month + months - 1) % 12 + 1
        day = min(base.day, _days_in_month(year, month))
        until = date(year, month, day).isoformat()
    return {
        "months": months,
        "until": until,
        "installed_at": installed_at.isoformat() if installed_at else None,
    }


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


_UNIT_LABEL_RE = re.compile(r"^([A-Z0-9-]+)-U(\d{2})$")
_QR_RE = re.compile(r"^DEKOPEN\|([^|]+)\|([^|]+)\|")


def load_check(*, org_id: UUID, delivery_id: UUID, scanned_codes: list[str], actor_id: UUID) -> dict:
    """Escaneo de bultos contra el manifiesto del viaje: la etiqueta de
    unidad ``<OT>-U<nn>`` (o el QR DEKOPEN|<OT>|<etiqueta>|… de la unidad)
    debe corresponder a una unidad del viaje. Con todo escaneado la carga
    queda marcada load_checked_at/by."""
    with transaction.atomic(), documentary_backend():
        delivery = rows(
            """
            SELECT d.*, o.order_code, o.payload_json::text AS payload_json
            FROM public.deliveries d
            JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id
            WHERE d.id = %s AND d.org_id = %s FOR UPDATE
            """,
            [str(delivery_id), str(org_id)],
        )
        if not delivery:
            raise DocumentaryError("delivery_not_found")
        delivery = delivery[0]
        if delivery["status"] not in ("SCHEDULED", "ON_ROUTE"):
            raise DocumentaryError("delivery_load_closed")
        payload = _payload(delivery)
        manifest = _manifest_units(payload)
        trip_units = (
            {int(i) for i in delivery["unit_indexes"]}
            if delivery["unit_indexes"] is not None
            else set(manifest)
        )
        order_code = delivery["order_code"]
        # Etiquetas de unidad → índice de manifiesto. El QR DEKOPEN|OT|PACK|…
        # cubre el bulto completo; la etiqueta impresa <OT>-U<nn> una unidad.
        scanned_units: set[int] = set()
        unexpected: list[str] = []
        labels = {
            str(label.get("code"))
            for label in (payload.get("packing") or {}).get("labels") or []
            if label.get("code")
        }
        for code in scanned_codes:
            text = (code or "").strip()
            unit_match = _UNIT_LABEL_RE.match(text)
            if unit_match and unit_match.group(1) == order_code:
                scanned_units.add(int(unit_match.group(2)))
                continue
            qr_match = _QR_RE.match(text)
            if qr_match and qr_match.group(1) == order_code:
                label_code = qr_match.group(2)
                if label_code in labels or label_code == "PACK":
                    scanned_units |= trip_units
                    continue
                unit_label = _UNIT_LABEL_RE.match(label_code)
                if unit_label:
                    scanned_units.add(int(unit_label.group(2)))
                    continue
            unexpected.append(text)
        missing = sorted(trip_units - scanned_units)
        complete = not missing and not unexpected
        if complete:
            one(
                """
                UPDATE public.deliveries
                SET load_checked_at = NOW(), load_checked_by = %s
                WHERE id = %s AND org_id = %s RETURNING id
                """,
                [str(actor_id), str(delivery_id), str(org_id)],
                "delivery_not_found",
            )
    return {
        "delivery_id": str(delivery_id),
        "load_checked": complete,
        "missing": missing,
        "unexpected": unexpected,
    }
