"""Automation job handlers — the durable half of §08's domain automations.

Each handler re-reads committed domain state inside its own transaction: the
payload carries refs only, so a job that retries after the event already moved
on still computes against live truth. The role list governs API enqueue/retry: automation types are read-only
report jobs over data these roles already reach, so a member-triggered
refresh is benign and a failed row stays retryable by the people who would
act on it.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import connection, transaction

from authentication.rls import authenticated_rls_context
from jobs.handlers import _claims_for
from jobs.registry import JobContext, JobPermanentError, ProgressReporter, register

from automations.serializers import (
    CatalogTaskSerializer,
    CommercialRefreshSerializer,
    OrderRefsSerializer,
    StepAdvanceSerializer,
    VersionRefsSerializer,
)

_AUTOMATION_ROLES = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")


def _job_claims(context: JobContext) -> dict[str, Any]:
    if context.created_by is None:
        raise JobPermanentError("automation_actor_required")
    return _claims_for(str(context.created_by), context)


def _set_claims(context: JobContext) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            [json.dumps(_job_claims(context))],
        )


def _shortage_lines(lines: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    return [
        {
            "purchasing_sku": line["purchasing_sku"],
            "order_type": line.get("order_type"),
            "category": line.get("category"),
            "unit": line["unit"],
            "required": line["required"],
            "available": line["available"],
            "shortage": line["shortage"],
            "recommended_purchase": line["recommended_purchase"],
        }
        for line in lines
        if Decimal(str(line.get("shortage") or "0")) > 0
    ][:limit]


@register(
    "automation.prep_forecast",
    roles=_AUTOMATION_ROLES,
    payload_serializer=VersionRefsSerializer,
    label="Pronóstico de materiales",
)
def prep_forecast(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    """Freeze/approval → coverage forecast for the sealed version: which
    requirement lines are covered by stock and which come up short, stamped
    once per version so prep doesn't wait for a human to open production."""
    from documents.repository import documentary_backend, one
    from inventory.production_stock import coverage_for_version

    report(10)
    version_id = UUID(str(payload["version_id"]))
    with transaction.atomic():
        _set_claims(context)
        with documentary_backend():
            version = one(
                "SELECT project_id, revision_code, production_allowed "
                "FROM public.project_versions WHERE id=%s AND org_id=%s",
                [str(version_id), str(context.org_id)],
                "version_not_found",
            )
            project = one(
                "SELECT code FROM public.projects WHERE id=%s AND org_id=%s",
                [str(version["project_id"]), str(context.org_id)],
                "project_not_found",
            )
            coverage = coverage_for_version(org_id=context.org_id, version_id=version_id)
    report(90)
    lines = coverage["lines"]
    shortage_lines = _shortage_lines(lines)
    return {
        "project_id": str(version["project_id"]),
        "project_code": project.get("code"),
        "revision_code": version.get("revision_code"),
        "production_allowed": bool(version.get("production_allowed")),
        "requirement_lines": len(lines),
        "covered": len(lines) - len(shortage_lines),
        "shortages": int(coverage.get("shortages") or 0),
        "shortage_lines": shortage_lines,
    }


@register(
    "automation.purchase_task",
    roles=_AUTOMATION_ROLES,
    payload_serializer=OrderRefsSerializer,
    label="Tarea de compra por faltantes",
)
def purchase_task(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    """Missing material → purchase task. Prefers the order's own reservation
    shorts once it is optimized; before that it reports the version coverage
    forecast so the task exists the moment a shortage is known."""
    from decimal import Decimal as _D

    from documents.repository import documentary_backend, one
    from inventory.production_stock import coverage_for_version
    from production.service import _decoded

    report(10)
    order_id = UUID(str(payload["order_id"]))
    with transaction.atomic():
        _set_claims(context)
        with documentary_backend():
            order = one(
                "SELECT id, order_code, payload_json::text AS payload_json "
                "FROM public.orders WHERE id=%s AND org_id=%s "
                "AND order_type='WORKSHOP_OT'",
                [str(order_id), str(context.org_id)],
                "work_order_not_found",
            )
            order_payload = _decoded(order.get("payload_json"))
            reservations = (order_payload.get("optimization") or {}).get(
                "stock_reservations"
            ) or []
            short_entries = [
                {
                    "sku": entry.get("sku"),
                    "name": entry.get("name"),
                    "category": entry.get("category"),
                    "unit": entry.get("unit"),
                    "needed": entry.get("needed"),
                    "reserved": entry.get("reserved"),
                    "short": entry.get("short"),
                }
                for entry in reservations
                if _D(str(entry.get("short") or "0")) > 0
            ]
            source = "order_reservations" if reservations else "version_forecast"
            forecast_lines: list[dict[str, Any]] = []
            if not reservations and order_payload.get("version_id"):
                coverage = coverage_for_version(
                    org_id=context.org_id,
                    version_id=UUID(str(order_payload["version_id"])),
                )
                forecast_lines = _shortage_lines(coverage["lines"])
    report(90)
    lines = short_entries or forecast_lines
    return {
        "order_id": str(order_id),
        "order_code": order.get("order_code"),
        "source": source,
        "shortage_count": len(lines),
        "purchase_lines": lines,
    }


@register(
    "automation.catalog_task",
    roles=_AUTOMATION_ROLES,
    payload_serializer=CatalogTaskSerializer,
    label="Resolver autoridad de catálogo",
)
def catalog_task(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    """Missing catalog authority → review task: the system's readiness ladder
    with the exact blockers (entity, missing authority, consequence, resolve
    action) the catalog owner must clear."""
    from catalogs.readiness import catalog_readiness
    from documents.repository import one

    report(10)
    system_id = UUID(str(payload["system_id"]))
    with authenticated_rls_context(_job_claims(context)):
        system = one(
            # Positions may reference global catalog systems (org_id IS NULL) —
            # a task on one is still this org's work.
            "SELECT name FROM public.profile_systems "
            "WHERE id=%s AND (org_id=%s OR org_id IS NULL)",
            [str(system_id), str(context.org_id)],
            "system_not_found",
        )
        readiness = catalog_readiness(system_id, context.org_id)
    report(90)
    blockers = [
        {
            "level": level["level"],
            "code": blocker["code"],
            "missing_authority": blocker["missing_authority"],
            "affected": blocker["affected"],
            "why": blocker["why"],
            "action": blocker["action"],
        }
        for level in readiness.get("levels") or []
        for blocker in level.get("blockers") or []
    ]
    return {
        "system_id": str(system_id),
        "system_name": system.get("name"),
        "level": readiness.get("level"),
        "blockers": blockers,
        "blocker_count": len(blockers),
    }


@register(
    "automation.commercial_refresh",
    roles=_AUTOMATION_ROLES,
    payload_serializer=CommercialRefreshSerializer,
    label="Actualizar estado comercial",
)
def commercial_refresh(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    """Payment recorded/voided/settled → recomputed cobranza state: deal
    total, collected, balance, ledger status — the commercial timeline moves
    without anyone reopening the project."""
    from projects.payments import list_payments

    report(10)
    with transaction.atomic():
        _set_claims(context)
        summary = list_payments(
            org_id=context.org_id, project_id=UUID(str(payload["project_id"]))
        )
    report(90)
    return {
        "project_id": str(payload["project_id"]),
        "payment_id": str(payload["payment_id"]) if payload.get("payment_id") else None,
        "status": summary["status"],
        "quote_total_gross": summary["quote_total_gross"],
        "collected": summary["collected"],
        "balance": summary["balance"],
        "currency": summary["currency"],
        "payments": len(summary["payments"]),
        "sealed_revision": summary["sealed_revision"],
    }


@register(
    "automation.step_advance",
    roles=_AUTOMATION_ROLES,
    payload_serializer=StepAdvanceSerializer,
    label="Avance de estación",
)
def step_advance(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    """Station complete → what runs next. The answer is read fresh: a queued
    job that retries after a later transition still reports the true next
    step, never the state the event saw."""
    from documents.repository import documentary_backend, one, rows

    report(10)
    order_id = UUID(str(payload["order_id"]))
    with transaction.atomic():
        _set_claims(context)
        with documentary_backend():
            order = one(
                "SELECT order_code, status::text FROM public.orders "
                "WHERE id=%s AND org_id=%s AND order_type='WORKSHOP_OT'",
                [str(order_id), str(context.org_id)],
                "work_order_not_found",
            )
            pending = rows(
                "SELECT code, label, sequence, status::text "
                "FROM public.production_steps "
                "WHERE order_id=%s AND org_id=%s AND status<>'DONE' "
                "ORDER BY sequence LIMIT 1",
                [str(order_id), str(context.org_id)],
            )
    report(90)
    next_step = pending[0] if pending else None
    return {
        "order_id": str(order_id),
        "order_code": order.get("order_code"),
        "order_status": order.get("status"),
        "completed_step": payload.get("step_code"),
        "next_step": next_step,
    }
