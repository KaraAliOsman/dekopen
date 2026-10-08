"""«Hoy» — the per-role action queue behind the Inicio surface.

One item = one thing this person can act on right now: a business-language
phrase, the human code of the entity it belongs to, the reason it matters
and a deep link that already carries the right filter. Every query runs
inside the caller's tenant/RLS context — the frontend never aggregates,
it only renders what the backend decided is pending.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db import transaction

from documents.repository import documentary_backend, rows

_URGENCY_ORDER = {"overdue": 0, "today": 1, "soon": 2, "when_free": 3}

# Ungrouped nav surfaces the queue deep-links into — the filter a counter
# opens is part of the contract (the frontend tests these stay routable).
_LINK_PRODUCTION = "/production"
_LINK_DELIVERIES_TODAY = "/deliveries?when=today"
_LINK_DELIVERIES_OPEN = "/deliveries?when=open"


def _fmt_money(amount: object, currency: object) -> str:
    """§3.3 — CLP se escribe $1.435.471 (punto miles, sin decimales)."""
    value = Decimal(str(amount)).quantize(Decimal("1"))
    grouped = f"{int(value):,}".replace(",", ".")
    return f"${grouped}" if str(currency) == "CLP" else f"{currency} {grouped}"


def _fmt_pct(fraction: object) -> str:
    """0.35 → «35 %» (§3.3: coma decimal, espacio antes del %)."""
    value = Decimal(str(fraction)) * 100
    value = value.quantize(Decimal("0.1")).normalize()
    text = f"{value:f}".replace(".", ",")
    return f"{text} %"


def _fmt_date(day: date | None) -> str:
    return day.strftime("%d-%m-%Y") if day else "—"


def _day_words(days: int) -> str:
    if days <= 0:
        return "hoy"
    if days == 1:
        return "mañana"
    return f"en {days} días"


def _item(
    kind: str,
    urgency: str,
    phrase: str,
    *,
    reason: str | None = None,
    entity_code: str | None = None,
    entity_label: str | None = None,
    to: str,
    cta: str,
    count: int | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "urgency": urgency,
        "phrase": phrase,
        "reason": reason,
        "entity_code": entity_code,
        "entity_label": entity_label,
        "to": to,
        "cta": cta,
        "count": count,
    }


def _local_state(org_id: UUID) -> tuple[ZoneInfo, date, datetime, str]:
    """Org-local clock + moneda: «hoy» se decide en la zona de la organización
    y los montos se formatean en su moneda (CLP por defecto)."""
    row = rows(
        "SELECT timezone, currency::text AS currency "
        "FROM public.tenancy_organizations WHERE id = %s",
        [str(org_id)],
    )
    zone = ZoneInfo(str(row[0]["timezone"])) if row else ZoneInfo("America/Santiago")
    currency = str(row[0]["currency"]) if row else "CLP"
    now = datetime.now(zone)
    return zone, now.date(), now, currency


def _project_link(project_id: object) -> str:
    return f"/projects/{project_id}"


def _estimator_items(
    org_id: UUID, user_id: UUID, today: date, zone: ZoneInfo
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    # Cotizaciones al cliente — el enlace vigente de la revisión actual.
    approvals = rows(
        """
        SELECT a.id, a.status::text AS status, a.expires_at, a.view_count,
               a.decided_by, a.decided_note,
               p.id AS project_id, p.code AS project_code, p.name AS project_name
        FROM public.customer_approvals a
        JOIN public.project_versions v ON v.id = a.project_version_id
            AND v.org_id = a.org_id
        JOIN public.projects p ON p.id = a.project_id AND p.org_id = a.org_id
        WHERE a.org_id = %s
          AND v.revision_code = p.current_revision
          AND a.status IN ('PENDING', 'DECLINED', 'CHANGES_REQUESTED')
          AND p.status::text <> 'CANCELLED'
        ORDER BY a.created_at DESC
        """,
        [str(org_id)],
    )
    for approval in approvals:
        expires = approval["expires_at"]
        expires_date = (
            expires.astimezone(zone).date() if isinstance(expires, datetime) else None
        )
        days = (expires_date - today).days if expires_date else None
        name = str(approval["project_name"])
        views = int(approval.get("view_count") or 0)
        if approval["status"] == "DECLINED":
            note = str(approval.get("decided_note") or "").strip()
            items.append(
                _item(
                    "changes_requested",
                    "today",
                    f"El cliente rechazó la cotización de {name}",
                    reason=(
                        f"«{note[:140]}»"
                        if note
                        else "No dejó comentario — conviene llamar para entender qué cambió"
                    ),
                    entity_code=str(approval["project_code"]),
                    entity_label=name,
                    to=_project_link(approval["project_id"]),
                    cta="Retomar",
                )
            )
        elif approval["status"] == "CHANGES_REQUESTED":
            note = str(approval.get("decided_note") or "").strip()
            items.append(
                _item(
                    "changes_requested",
                    "today",
                    f"El cliente pidió cambios en la cotización de {name}",
                    reason=(
                        f"«{note[:140]}»"
                        if note
                        else "Sin comentario — revisa la propuesta y emite la siguiente revisión"
                    ),
                    entity_code=str(approval["project_code"]),
                    entity_label=name,
                    to=_project_link(approval["project_id"]),
                    cta="Revisar",
                )
            )
        elif days is not None and days < 0:
            items.append(
                _item(
                    "quote_expired",
                    "overdue",
                    f"El enlace de cotización de {name} venció",
                    reason=f"Venció el {_fmt_date(expires_date)} — el cliente ya no puede abrirlo; emite uno nuevo",
                    entity_code=str(approval["project_code"]),
                    entity_label=name,
                    to=_project_link(approval["project_id"]),
                    cta="Emitir enlace",
                )
            )
        elif days is not None and days <= 3:
            items.append(
                _item(
                    "quote_expiring",
                    "today" if days <= 1 else "soon",
                    f"La cotización de {name} vence {_day_words(days)}",
                    reason=(
                        f"El cliente la abrió {views} veces sin decidir"
                        if views > 0
                        else "El cliente aún no la abre"
                    ),
                    entity_code=str(approval["project_code"]),
                    entity_label=name,
                    to=_project_link(approval["project_id"]),
                    cta="Revisar",
                )
            )
        elif views > 0:
            items.append(
                _item(
                    "proposal_viewed",
                    "soon",
                    f"El cliente abrió la cotización de {name}",
                    reason=f"La vio {views} veces sin decidir — una llamada puede cerrarla",
                    entity_code=str(approval["project_code"]),
                    entity_label=name,
                    to=_project_link(approval["project_id"]),
                    cta="Ver proyecto",
                )
            )

    # Decisiones de precio sobre operaciones que pidió este estimador: solo
    # la última decisión por proyecto es accionable (una re-cotización ya
    # aprobada hace irrelevante un rechazo anterior).
    decisions = rows(
        """
        SELECT DISTINCT ON (o.project_id)
               o.state::text AS state, p.id AS project_id, p.code AS project_code,
               p.name AS project_name, p.status::text AS project_status
        FROM public.pricing_operations o
        JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
        WHERE o.org_id = %s AND o.requested_by = %s
          AND o.state IN ('APPLIED', 'REJECTED')
        ORDER BY o.project_id,
                 o.approved_at DESC NULLS LAST, o.created_at DESC
        """,
        [str(org_id), str(user_id)],
    )
    for decision in decisions:
        name = str(decision["project_name"])
        if decision["state"] == "REJECTED":
            items.append(
                _item(
                    "price_rejected",
                    "today",
                    f"Tu precio para {name} fue rechazado",
                    reason="Ajusta el margen y vuelve a cotizar para destrabar la venta",
                    entity_code=str(decision["project_code"]),
                    entity_label=name,
                    to=f"/projects/{decision['project_id']}/pricing",
                    cta="Recotizar",
                )
            )
        elif decision["project_status"] == "DRAFT":
            items.append(
                _item(
                    "price_approved",
                    "soon",
                    f"Tu precio para {name} quedó aprobado",
                    reason="El margen está firmado — emite la cotización para enviarla al cliente",
                    entity_code=str(decision["project_code"]),
                    entity_label=name,
                    to=_project_link(decision["project_id"]),
                    cta="Emitir cotización",
                )
            )

    # Posiciones que el inspector técnico bloqueó — cotizarlas sería
    # prometer algo que la fábrica no puede producir.
    blocked = rows(
        """
        SELECT pos.id, pos.location_tag, pos.position_index,
               p.id AS project_id, p.code AS project_code, p.name AS project_name
        FROM public.project_positions pos
        JOIN public.projects p ON p.id = pos.project_id AND p.org_id = pos.org_id
        WHERE pos.org_id = %s AND pos.inspector_status::text = 'RED'
          AND p.status::text IN ('DRAFT', 'QUOTED')
        ORDER BY p.code, pos.position_index
        LIMIT 6
        """,
        [str(org_id)],
    )
    for position in blocked:
        name = str(position["project_name"])
        tag = str(position["location_tag"] or f"Pos. {position['position_index']:02d}")
        items.append(
            _item(
                "position_blocked",
                "soon",
                f"La posición «{tag}» de {name} no puede fabricarse",
                reason="El inspector técnico marcó hallazgos — revísala en el editor antes de cotizar",
                entity_code=str(position["project_code"]),
                entity_label=name,
                to=f"/projects/{position['project_id']}/positions/{position['id']}/edit",
                cta="Revisar posición",
            )
        )
    return items


def _owner_items(
    org_id: UUID, today: date, currency: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []

    pending = rows(
        """
        SELECT o.project_id, o.request ->> 'target_margin' AS target_margin,
               p.code AS project_code, p.name AS project_name
        FROM public.pricing_operations o
        JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
        WHERE o.org_id = %s AND o.state = 'PENDING'
        ORDER BY o.created_at
        """,
        [str(org_id)],
    )
    for operation in pending:
        name = str(operation["project_name"])
        margin = operation.get("target_margin")
        items.append(
            _item(
                "margin_approval",
                "today",
                f"Aprobar el margen de {name}",
                reason=(
                    f"El cotizador pidió {_fmt_pct(margin)} — el proyecto no avanza sin tu decisión"
                    if margin
                    else "El cotizador espera tu decisión — el proyecto no avanza sin ella"
                ),
                entity_code=str(operation["project_code"]),
                entity_label=name,
                to=f"/projects/{operation['project_id']}/pricing",
                cta="Decidir",
            )
        )

    receivables = rows(
        """
        SELECT p.id, p.code AS project_code, p.name AS project_name,
               p.status::text AS status, p.total_price_gross,
               COALESCE(pay.collected, 0) AS collected,
               (rem.drafted IS TRUE) AS reminder_drafted
        FROM public.projects p
        LEFT JOIN LATERAL (
            SELECT COALESCE(sum(pay.amount), 0) AS collected
            FROM public.project_payments pay
            WHERE pay.project_id = p.id AND pay.org_id = p.org_id
              AND pay.voided_at IS NULL
        ) pay ON TRUE
        LEFT JOIN LATERAL (
            SELECT TRUE AS drafted
            FROM public.ai_audit_logs rem
            WHERE rem.org_id = p.org_id
              AND rem.tool_name = 'collection_reminder'
              AND rem.input_payload->>'project_id' = p.id::text
            ORDER BY rem.created_at DESC
            LIMIT 1
        ) rem ON TRUE
        WHERE p.org_id = %s
          AND p.status::text IN ('APPROVED', 'IN_PRODUCTION', 'COMPLETED')
          AND p.total_price_gross > COALESCE(pay.collected, 0)
        ORDER BY p.updated_at DESC
        """,
        [str(org_id)],
    )
    outstanding_total = Decimal("0")
    for project in receivables:
        outstanding = Decimal(str(project["total_price_gross"])) - Decimal(
            str(project["collected"])
        )
        outstanding_total += outstanding
        name = str(project["project_name"])
        reminder_note = (
            " — el recordatorio al cliente ya está preparado, revísalo en Cobranza"
            if project["reminder_drafted"]
            else ""
        )
        cobranza_link = f"{_project_link(project['id'])}?section=payments"
        if project["status"] == "COMPLETED":
            items.append(
                _item(
                    "collection_overdue",
                    "overdue",
                    f"Cobrar el saldo de {name}",
                    reason=(
                        f"Quedan {_fmt_money(outstanding, currency)} por cobrar "
                        f"y la obra ya fue entregada e instalada{reminder_note}"
                    ),
                    entity_code=str(project["project_code"]),
                    entity_label=name,
                    to=cobranza_link,
                    cta="Ver cobro",
                )
            )
        elif project["status"] == "IN_PRODUCTION":
            items.append(
                _item(
                    "collection_open",
                    "soon",
                    f"Saldo por cobrar de {name}",
                    reason=(
                        f"Quedan {_fmt_money(outstanding, currency)} — "
                        f"el convenio es contra entrega{reminder_note}"
                    ),
                    entity_code=str(project["project_code"]),
                    entity_label=name,
                    to=cobranza_link,
                    cta="Ver cobro",
                )
            )
        else:
            items.append(
                _item(
                    "deposit_pending",
                    "soon",
                    f"Falta el anticipo de {name}",
                    reason=(
                        f"Quedan {_fmt_money(outstanding, currency)} por cobrar "
                        f"antes de liberar a taller{reminder_note}"
                    ),
                    entity_code=str(project["project_code"]),
                    entity_label=name,
                    to=cobranza_link,
                    cta="Ver cobro",
                )
            )

    risk = rows(
        """
        SELECT
            count(*) FILTER (WHERE o.status::text = 'HOLD') AS held,
            count(*) FILTER (
                WHERE o.payload_json -> 'remake_of' IS NOT NULL
                  AND o.status::text IN ('RELEASED', 'IN_PROGRESS', 'HOLD')
            ) AS remakes
        FROM public.orders o
        WHERE o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
        """,
        [str(org_id)],
    )[0]
    held = int(risk["held"])
    if held:
        items.append(
            _item(
                "ot_held",
                "today",
                f"{held} OT{'s' if held > 1 else ''} detenida{'s' if held > 1 else ''} en el taller",
                reason="Material o calidad pendiente — un OT parado ocupa banca y atrasa entregas",
                to="/production?blocked=1",
                cta="Ver cola",
                count=held,
            )
        )

    deliveries = rows(
        """
        SELECT
            count(*) FILTER (WHERE d.scheduled_date < %s
                AND d.status IN ('SCHEDULED', 'ON_ROUTE', 'FAILED')) AS overdue,
            count(*) FILTER (WHERE d.scheduled_date = %s
                AND d.status IN ('SCHEDULED', 'ON_ROUTE', 'FAILED')) AS today
        FROM public.deliveries d
        WHERE d.org_id = %s
        """,
        [today, today, str(org_id)],
    )[0]
    overdue = int(deliveries["overdue"])
    due_today = int(deliveries["today"])
    if overdue:
        items.append(
            _item(
                "deliveries_overdue",
                "overdue",
                f"{overdue} entrega{'s' if overdue > 1 else ''} atrasada{'s' if overdue > 1 else ''}",
                reason="La fecha pactada ya pasó — hay que reagendar o despachar hoy",
                to="/deliveries?when=overdue",
                cta="Reagendar",
                count=overdue,
            )
        )
    if due_today:
        items.append(
            _item(
                "deliveries_today",
                "today",
                f"{due_today} entrega{'s' if due_today > 1 else ''} programada{'s' if due_today > 1 else ''} para hoy",
                reason="El chofer y el cliente esperan confirmación",
                to=_LINK_DELIVERIES_TODAY,
                cta="Ver entregas",
                count=due_today,
            )
        )

    # Pipeline por fase — el monto real cotizado/vendido/por cobrar.
    funnel = rows(
        """
        SELECT p.status::text AS status,
               count(*) AS n, COALESCE(sum(p.total_price_gross), 0) AS total
        FROM public.projects p
        WHERE p.org_id = %s AND p.status::text IN
              ('QUOTED', 'APPROVED', 'IN_PRODUCTION', 'COMPLETED')
        GROUP BY p.status
        """,
        [str(org_id)],
    )
    stage_rows: dict[str, dict[str, Any]] = {}
    for row in funnel:
        key = str(row["status"])
        bucket = stage_rows.setdefault(
            key, {"count": 0, "total": Decimal("0")}
        )
        bucket["count"] += int(row["n"])
        bucket["total"] += Decimal(str(row["total"]))
    panels: list[dict[str, Any]] = []
    pipeline_rows = []
    for status, label in (
        ("QUOTED", "Cotizado"),
        ("APPROVED", "Aprobado"),
        ("IN_PRODUCTION", "En producción"),
        ("COMPLETED", "Entregado"),
    ):
        bucket = stage_rows.get(status)
        if bucket:
            pipeline_rows.append(
                {
                    "label": label,
                    "value": _fmt_money(bucket["total"], currency),
                    "count": bucket["count"],
                }
            )
    if outstanding_total > 0:
        pipeline_rows.append(
            {
                "label": "Por cobrar",
                "value": _fmt_money(outstanding_total, currency),
                "count": len(receivables),
            }
        )
    if pipeline_rows:
        panels.append(
            {
                "kind": "pipeline",
                "title": "Pipeline",
                "rows": pipeline_rows,
            }
        )
    return items, panels


def _manager_items(
    org_id: UUID, today: date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []

    orders = rows(
        """
        SELECT
            count(*) FILTER (WHERE o.status::text = 'HOLD') AS held,
            count(*) FILTER (
                WHERE o.payload_json -> 'remake_of' IS NOT NULL
                  AND o.status::text IN ('RELEASED', 'IN_PROGRESS', 'HOLD')
            ) AS remakes
        FROM public.orders o
        WHERE o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
        """,
        [str(org_id)],
    )[0]
    held = int(orders["held"])
    remakes = int(orders["remakes"])

    deliveries = rows(
        """
        SELECT
            count(*) FILTER (WHERE d.scheduled_date < %s
                AND d.status IN ('SCHEDULED', 'ON_ROUTE', 'FAILED')) AS overdue,
            count(*) FILTER (WHERE d.scheduled_date = %s
                AND d.status IN ('SCHEDULED', 'ON_ROUTE')) AS today
        FROM public.deliveries d
        WHERE d.org_id = %s
        """,
        [today, today, str(org_id)],
    )[0]
    overdue = int(deliveries["overdue"])
    due_today = int(deliveries["today"])
    if overdue:
        items.append(
            _item(
                "deliveries_overdue",
                "overdue",
                f"{overdue} entrega{'s' if overdue > 1 else ''} atrasada{'s' if overdue > 1 else ''}",
                reason="La fecha pactada ya pasó — reagenda antes de que el cliente llame",
                to="/deliveries?when=overdue",
                cta="Ver entregas",
                count=overdue,
            )
        )
    if due_today:
        items.append(
            _item(
                "deliveries_today",
                "today",
                f"{due_today} entrega{'s' if due_today > 1 else ''} sale{'n' if due_today > 1 else ''} hoy",
                reason="Verifica embalaje y guía antes de que salga el camión",
                to=_LINK_DELIVERIES_TODAY,
                cta="Ver entregas",
                count=due_today,
            )
        )
    if held:
        items.append(
            _item(
                "ot_held",
                "today",
                f"{held} OT{'s' if held > 1 else ''} en espera",
                reason="Pasos bloqueados o faltantes — desbloquearlas destraba la cola",
                to="/production?blocked=1",
                cta="Ver bloqueadas",
                count=held,
            )
        )
    # Faltante real: la misma señal que expone el taller — prep.shortages de
    # la versión y las reservas de stock con «short» que dejó la optimización.
    shortage = rows(
        """
        SELECT count(*) AS n FROM public.orders o
        WHERE o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
          AND o.status::text IN ('RELEASED', 'IN_PROGRESS', 'HOLD')
          AND (
              COALESCE(
                  CASE WHEN (o.payload_json -> 'prep' ->> 'shortages') ~ '^\\d+(\\.\\d+)?$'
                       THEN (o.payload_json -> 'prep' ->> 'shortages')::numeric
                       ELSE 0 END,
                  0
              ) > 0
              OR EXISTS (
                  SELECT 1 FROM jsonb_array_elements(
                      COALESCE(
                          o.payload_json -> 'optimization' -> 'stock_reservations',
                          '[]'::jsonb
                      )
                  ) r
                  WHERE (r ->> 'short') ~ '^\\d+(\\.\\d+)?$'
                    AND (r ->> 'short')::numeric > 0
              )
          )
        """,
        [str(org_id)],
    )[0]["n"]
    shortage_n = int(shortage)
    if shortage_n:
        items.append(
            _item(
                "ot_shortage",
                "today",
                f"{shortage_n} OT{'s' if shortage_n > 1 else ''} con faltante de material",
                reason="No pueden terminar sin compra — la recepción pendiente decide",
                to="/production?shortage=1",
                cta="Ver faltantes",
                count=shortage_n,
            )
        )
    if remakes:
        items.append(
            _item(
                "remakes_open",
                "soon",
                f"{remakes} remake{'s' if remakes > 1 else ''} abierto{'s' if remakes > 1 else ''}",
                reason="El fallo de calidad ya está pagado — que no se duplique en despacho",
                to=_LINK_PRODUCTION,
                cta="Ver remakes",
                count=remakes,
            )
        )

    # P23 — incidencias de obra abiertas y solicitudes de compra de
    # terreno: el jefe decide el remake, la compra o la visita.
    field = (rows(
        """
        SELECT
            (SELECT count(*) FROM public.site_incidents i
             WHERE i.org_id = %s AND i.status IN ('OPEN','IN_PROGRESS')) AS incidents,
            (SELECT count(*) FROM public.field_purchase_requests r
             WHERE r.org_id = %s AND r.status = 'PENDING') AS purchases,
            (SELECT count(*) FROM public.service_tickets t
             WHERE t.org_id = %s AND t.status IN ('OPEN','SCHEDULED','IN_PROGRESS')) AS tickets,
            (SELECT count(*) FROM public.service_tickets t
             WHERE t.org_id = %s AND t.status = 'SCHEDULED'
               AND t.scheduled_visit_at::date = %s) AS visits_today,
            (SELECT count(*) FROM public.service_tickets t
             WHERE t.org_id = %s AND t.status <> 'CLOSED' AND t.status <> 'CANCELLED'
               AND t.warranty_until IS NOT NULL
               AND t.warranty_until <= %s + INTERVAL '30 days') AS warranties_expiring
        """,
        [str(org_id), str(org_id), str(org_id), str(org_id), today, str(org_id), today],
    ) or [{}])[0]
    open_incidents = int(field.get("incidents") or 0)
    if open_incidents:
        items.append(
            _item(
                "site_incidents_open",
                "today",
                f"{open_incidents} incidencia{'s' if open_incidents > 1 else ''} de obra abierta{'s' if open_incidents > 1 else ''}",
                reason="Daño, faltante o medida — cada una decide remake, compra o servicio",
                to="/field/incidents",
                cta="Ver incidencias",
                count=open_incidents,
            )
        )
    pending_purchases = int(field.get("purchases") or 0)
    if pending_purchases:
        items.append(
            _item(
                "field_purchases_pending",
                "today",
                f"{pending_purchases} solicitud{'es' if pending_purchases > 1 else ''} de compra de terreno",
                reason="La obra espera el material — confirma o rechaza cada solicitud",
                to="/field/incidents?tab=purchases",
                cta="Ver solicitudes",
                count=pending_purchases,
            )
        )
    visits_today = int(field.get("visits_today") or 0)
    if visits_today:
        items.append(
            _item(
                "service_visits_today",
                "today",
                f"{visits_today} visita{'s' if visits_today > 1 else ''} de postventa hoy",
                reason="La cuadrilla sale a terreno — confirma dirección y hora",
                to="/field/service",
                cta="Ver postventa",
                count=visits_today,
            )
        )
    warranties = int(field.get("warranties_expiring") or 0)
    if warranties:
        items.append(
            _item(
                "warranties_expiring",
                "soon",
                f"{warranties} garantía{'s' if warranties > 1 else ''} por vencer",
                reason="Vencen dentro de 30 días — decide visita preventiva o cierre",
                to="/field/service?expiring=1",
                cta="Ver garantías",
                count=warranties,
            )
        )

    # Cola por estación — lo que cada puesto tiene esperando ahora.
    from production.service import station_queue

    stations = station_queue(org_id=org_id)["stations"]
    by_load = sorted(
        stations,
        key=lambda s: (-int(s["blocked"]), -int(s["pending"]), str(s["label"])),
    )
    for station in by_load[:3]:
        pending = int(station["pending"])
        blocked = int(station["blocked"])
        in_progress = int(station["in_progress"])
        if not (pending or blocked or in_progress):
            continue
        parts = [f"{pending} pendiente{'s' if pending > 1 else ''}"] if pending else []
        if in_progress:
            parts.append(f"{in_progress} en curso")
        if blocked:
            parts.append(f"{blocked} bloqueado{'s' if blocked > 1 else ''}")
        items.append(
            _item(
                "station_backlog",
                "today" if blocked else "soon",
                f"{station['label']}: {' · '.join(parts)}",
                reason="La estación define el ritmo del taller — vaciarla primero",
                to=_LINK_PRODUCTION,
                cta="Ver cola",
                count=pending + in_progress + blocked,
            )
        )
    return items, []


def _operator_items(
    org_id: UUID, user_id: UUID
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    mine = rows(
        """
        SELECT s.id, s.label, s.code::text AS code, o.order_code, o.id AS order_id
        FROM public.production_steps s
        JOIN public.orders o ON o.id = s.order_id AND o.org_id = s.org_id
        WHERE s.org_id = %s AND s.actor_id = %s AND s.status::text = 'IN_PROGRESS'
        ORDER BY s.started_at NULLS LAST, s.sequence
        """,
        [str(org_id), str(user_id)],
    )
    for step in mine:
        items.append(
            _item(
                "step_in_progress",
                "today",
                f"Continúa «{step['label']}» de {step['order_code']}",
                reason="Quedó en curso a tu nombre — ciérralo o bloquéalo con motivo",
                entity_code=str(step["order_code"]),
                to=_LINK_PRODUCTION,
                cta="Retomar paso",
            )
        )
    from production.service import station_queue

    stations = station_queue(org_id=org_id)["stations"]
    queued = [s for s in stations if int(s["pending"]) or int(s["in_progress"])]
    for station in queued[:3]:
        pending = int(station["pending"])
        in_progress = int(station["in_progress"])
        items.append(
            _item(
                "station_queue",
                "soon",
                f"{station['label']}: {pending + in_progress} paso{'s' if pending + in_progress > 1 else ''} en cola",
                reason="El próximo paso disponible está marcado en la cola",
                to=_LINK_PRODUCTION,
                cta="Ir a la estación",
                count=pending + in_progress,
            )
        )
    if not items:
        items.append(
            _item(
                "station_idle",
                "when_free",
                "La cola de estaciones está vacía",
                reason="Cuando el jefe libere trabajo aparece aquí",
                to=_LINK_PRODUCTION,
                cta="Ver producción",
            )
        )
    return items


def _installer_items(
    org_id: UUID, user_id: UUID, today: date
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    # P23 — la agenda del día manda: paradas asignadas al instalador
    # (o a su cuadrilla) antes que el listado genérico.
    my_stops = rows(
        """
        SELECT d.id, d.time_window, d.address, o.order_code,
               p.name AS project_name
        FROM public.deliveries d
        JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id
        JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
        WHERE d.org_id = %s AND d.scheduled_date = %s
          AND d.status IN ('SCHEDULED','ON_ROUTE')
          AND (d.installer_user_id = %s OR d.installer_user_id IS NULL)
        ORDER BY d.route_order NULLS LAST, d.time_window, o.order_code
        LIMIT 6
        """,
        [str(org_id), today, str(user_id)],
    )
    for stop in my_stops:
        items.append(
            _item(
                "my_install_today",
                "today",
                f"Instalar en {stop['address']}",
                reason="Tu parada de hoy — medición, checklist y firma en la ficha",
                entity_code=str(stop["order_code"]),
                entity_label=str(stop["project_name"]),
                to="/field/agenda",
                cta="Abrir agenda",
            )
        )
    # Visitas de postventa agendadas para hoy.
    visits = rows(
        """
        SELECT t.code, t.scheduled_visit_at, p.name AS project_name
        FROM public.service_tickets t
        JOIN public.projects p ON p.id = t.project_id AND p.org_id = t.org_id
        WHERE t.org_id = %s AND t.status = 'SCHEDULED'
          AND t.scheduled_visit_at::date = %s
        ORDER BY t.scheduled_visit_at
        LIMIT 4
        """,
        [str(org_id), today],
    )
    for visit in visits:
        items.append(
            _item(
                "my_service_visit",
                "today",
                f"Visita de postventa {visit['code']}",
                reason="Ticket de garantía/servicio agendado hoy",
                entity_code=str(visit["code"]),
                entity_label=str(visit["project_name"]),
                to="/field/service",
                cta="Ver postventa",
            )
        )
    deliveries = rows(
        """
        SELECT d.id, d.scheduled_date, d.time_window, d.status, d.address,
               d.installer_name, d.notes,
               o.order_code, o.status::text AS order_status,
               p.code AS project_code, p.name AS project_name
        FROM public.deliveries d
        JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id
        JOIN public.projects p ON p.id = o.project_id AND p.org_id = o.org_id
        WHERE d.org_id = %s
          AND (
              d.status IN ('SCHEDULED', 'ON_ROUTE', 'FAILED')
              OR (d.status = 'DELIVERED' AND o.status::text = 'DISPATCHED')
          )
        ORDER BY d.scheduled_date, d.time_window, o.order_code
        LIMIT 8
        """,
        [str(org_id)],
    )
    for delivery in deliveries:
        scheduled = delivery["scheduled_date"]
        scheduled_date = (
            scheduled if isinstance(scheduled, date) else date.fromisoformat(str(scheduled))
        )
        days = (scheduled_date - today).days
        address = str(delivery["address"])
        window = str(delivery["time_window"])
        if delivery["status"] == "FAILED":
            items.append(
                _item(
                    "delivery_failed",
                    "overdue",
                    f"La entrega en {address} falló",
                    reason="Hay que reagendar — el cliente ya esperó una vez",
                    entity_code=str(delivery["order_code"]),
                    entity_label=str(delivery["project_name"]),
                    to=_LINK_DELIVERIES_OPEN,
                    cta="Reagendar",
                )
            )
        elif delivery["status"] == "DELIVERED":
            items.append(
                _item(
                    "install_pending",
                    "today",
                    f"Instalar en {address}",
                    reason="La entrega está firmada — falta confirmar la instalación",
                    entity_code=str(delivery["order_code"]),
                    entity_label=str(delivery["project_name"]),
                    to=f"/production?order={delivery['order_code']}",
                    cta="Confirmar instalación",
                )
            )
        else:
            items.append(
                _item(
                    "delivery_due",
                    "overdue" if days < 0 else "today" if days == 0 else "soon",
                    f"Entrega {window} en {address}",
                    reason=(
                        f"Estaba agendada para {_fmt_date(scheduled_date)}"
                        if days < 0
                        else f"Agendada {_day_words(days)} — sale del taller hacia obra"
                    ),
                    entity_code=str(delivery["order_code"]),
                    entity_label=str(delivery["project_name"]),
                    to=_LINK_DELIVERIES_TODAY
                    if days == 0
                    else _LINK_DELIVERIES_OPEN,
                    cta="Ver despacho",
                )
            )
    if not items:
        items.append(
            _item(
                "no_deliveries",
                "when_free",
                "No hay entregas programadas",
                reason="Cuando el taller agende un despacho aparece aquí",
                to=_LINK_DELIVERIES_OPEN,
                cta="Ver despachos",
            )
        )
    return items


def today_queue(*, org_id: UUID, role: str, user_id: UUID) -> dict[str, Any]:
    """Cola de acciones del rol para hoy — ordenada por consecuencia."""
    with transaction.atomic(), documentary_backend():
        zone, today, _now, currency = _local_state(org_id)
        panels: list[dict[str, Any]] = []
        if role == "ESTIMATOR":
            items = _estimator_items(org_id, user_id, today, zone)
        elif role == "OWNER":
            items, panels = _owner_items(org_id, today, currency)
        elif role == "WORKSHOP_MANAGER":
            items, panels = _manager_items(org_id, today)
        elif role == "OPERATOR":
            items = _operator_items(org_id, user_id)
        elif role == "INSTALLER":
            items = _installer_items(org_id, user_id, today)
        else:
            items = []
    # Stable sort: urgency bucket first, the builder's own order inside.
    items.sort(key=lambda item: _URGENCY_ORDER.get(str(item["urgency"]), 9))
    return {
        "schema": "today_queue_v1",
        "role": role,
        "date": today.isoformat(),
        "items": items,
        "panels": panels,
    }
