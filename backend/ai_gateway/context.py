"""Typed context projections for the contextual assistant (M3 §3).

Every surface maps to a bounded, curated view of the organization's data —
never a client-supplied context blob and never a table dump. All queries run
under the caller's RLS (the endpoint wraps the whole pipeline in
authenticated_rls_context), so a projection can only see what the caller's
role already sees, and it can never reach another tenant's rows.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from authentication.errors import ContractAPIException
from documents.repository import documentary_backend, one
from jobs.service import job_owner
from pricing.repository import commercial_backend, rows

MAX_LIST = 20
MAX_FIELD = 120

# Surface → required ref names. A surface that names a ref without a matching
# tenant-scoped row raises the same 404 the feature's own endpoint would.
REQUIRED_REFS: dict[str, tuple[str, ...]] = {
    "dashboard": (),
    "projects": (),
    "project": ("project_id",),
    "position": ("position_id",),
    "quotation": ("project_id",),
    "catalog": (),
    "production": (),
    "work_order": ("work_order_id",),
    "clients": (),
    "client": ("client_id",),
    "purchasing": (),
    "settings": (),
    "morning_brief": (),
    "purchase_plan": (),
    "production_plan": (),
    "quotation_complete": ("project_id",),
    "project_from_documents": ("project_id",),
    "catalog_compiler": (),
    "customer_comms": ("project_id",),
    # Route surfaces whose work is org-level — they reuse the dashboard
    # projection but keep their own surface name so a job started on the
    # jobs list or the assistant workspace reads truthfully.
    "assistant": (),
    "jobs": (),
    "onboarding": (),
}


class _ContextError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _jsonb(value: Any) -> Any:
    """Raw cursors return jsonb columns as text — decode before the shape
    checks or a real dict/list payload silently collapses to None."""
    if isinstance(value, str):
        try:
            return json.loads(value, parse_float=Decimal)
        except json.JSONDecodeError:
            return None
    return value


def _cut(value: Any, limit: int = MAX_FIELD) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _positive(value: Any) -> bool:
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, ValueError):
        return False


def _ref(refs: dict[str, Any], name: str) -> UUID:
    raw = refs.get(name)
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        raise _ContextError("ai_context_ref_invalid") from None


def _organization(org_id: UUID) -> dict:
    result = rows(
        "SELECT name, subscription_tier, credits_balance, currency "
        "FROM public.tenancy_organizations WHERE id=%s",
        [org_id],
    )
    if not result:
        raise _ContextError("ai_context_not_found")
    org = result[0]
    return {
        "name": _cut(org["name"]),
        "plan": _cut(org.get("subscription_tier")),
        "credits_balance": _cut(org.get("credits_balance")),
        "currency": _cut(org.get("currency")),
    }


def _dashboard(org_id: UUID) -> dict:
    counts = rows(
        "SELECT "
        "(SELECT count(*) FROM public.projects WHERE org_id=%(o)s) AS projects, "
        "(SELECT count(*) FROM public.project_positions WHERE org_id=%(o)s) AS positions, "
        "(SELECT count(*) FROM public.orders WHERE org_id=%(o)s "
        " AND order_type='WORKSHOP_OT' AND status NOT IN ('COMPLETED','INSTALLED'))"
        " AS work_orders_open, "
        "(SELECT count(*) FROM public.clients WHERE org_id=%(o)s AND is_active)"
        " AS clients, "
        "(SELECT count(*) FROM public.profile_systems WHERE org_id=%(o)s OR "
        " (org_id IS NULL AND is_global)) AS profile_systems",
        {"o": org_id},
    )
    recent = rows(
        "SELECT id, code, name, client_name, status "
        "FROM public.projects WHERE org_id=%s ORDER BY updated_at DESC LIMIT 5",
        [org_id],
    )
    return {
        "counts": {key: int(value) for key, value in (counts[0] if counts else {}).items()},
        "recent_projects": [
            {
                # List entries expose their ids — the agent's drill-down
                # queries are identified by them, not by name or code.
                "id": str(p["id"]),
                "code": _cut(p["code"]),
                "name": _cut(p["name"]),
                "client": _cut(p["client_name"]),
                "status": _cut(p["status"]),
            }
            for p in recent
        ],
    }


def _brief(org_id: UUID) -> dict:
    """§08-WH — the morning brief's attention board. Counts reuse the §03
    operational-summary predicates verbatim so the brief's numbers are the
    dashboard's numbers; each category also exposes up to three ids so a
    line of the brief can drill into the entity it cites. job_runs is
    service-owned and no member-facing role holds its grant, so its count
    follows the documented exception: read as the connection owner (the
    session user, same as the analytics view's ambient read) with the
    explicit org filter — member-facing information the dashboard shows."""
    counts = one(
        """
        SELECT
            (SELECT count(*) FROM public.profile_systems s
             WHERE s.org_id = %(o)s
               AND (s.rebate_depth_mm IS NULL
                    OR s.end_milling_overlap_mm IS NULL)) AS catalog_gaps,
            (SELECT count(*) FROM public.production_steps s
             JOIN public.orders o ON o.id = s.order_id AND o.org_id = s.org_id
             WHERE s.org_id = %(o)s AND s.status = 'BLOCKED'
               AND o.status NOT IN ('CANCELLED', 'INSTALLED')) AS steps_blocked,
            (SELECT count(DISTINCT a.project_id) FROM public.customer_approvals a
             JOIN public.project_versions v
               ON v.id = a.project_version_id AND v.org_id = a.org_id
             JOIN public.projects p
               ON p.id = a.project_id AND p.org_id = a.org_id
             WHERE a.org_id = %(o)s AND a.status = 'PENDING'
               AND a.expires_at > now()
               AND p.current_revision = v.revision_code
               AND p.status = 'QUOTED') AS approvals_pending,
            (SELECT count(*) FROM public.projects p
             WHERE p.org_id = %(o)s AND p.status = 'QUOTED'
               AND NOT EXISTS (
                   SELECT 1 FROM public.customer_approvals a
                   JOIN public.project_versions v
                     ON v.id = a.project_version_id AND v.org_id = a.org_id
                   WHERE a.org_id = p.org_id AND a.project_id = p.id
                     AND v.revision_code = p.current_revision))
                AS quotes_unsent,
            (SELECT count(*) FROM public.projects p
             WHERE p.org_id = %(o)s AND p.status = 'QUOTED'
               AND EXISTS (
                   SELECT 1 FROM public.customer_approvals a
                   JOIN public.project_versions v
                     ON v.id = a.project_version_id AND v.org_id = a.org_id
                   WHERE a.org_id = p.org_id AND a.project_id = p.id
                     AND v.revision_code = p.current_revision)
               AND NOT EXISTS (
                   SELECT 1 FROM public.customer_approvals a
                   JOIN public.project_versions v
                     ON v.id = a.project_version_id AND v.org_id = a.org_id
                   WHERE a.org_id = p.org_id AND a.project_id = p.id
                     AND v.revision_code = p.current_revision
                     AND (a.status = 'APPROVED'
                          OR (a.status = 'PENDING' AND a.expires_at > now()))))
                AS quotes_stale,
            (SELECT count(*) FROM public.project_versions v
             WHERE v.org_id = %(o)s AND v.production_allowed
               AND NOT EXISTS (
                   SELECT 1 FROM public.orders o
                   WHERE o.org_id = v.org_id AND o.project_version_id = v.id
                     AND o.order_type = 'WORKSHOP_OT')) AS versions_ready,
            (SELECT count(*) FROM public.orders o
             WHERE o.org_id = %(o)s AND o.order_type = 'WORKSHOP_OT'
               AND o.status NOT IN ('CANCELLED', 'INSTALLED')
               AND (COALESCE((o.payload_json->'prep'->>'shortages')::int, 0) > 0
                    OR EXISTS (
                        SELECT 1 FROM jsonb_array_elements(
                            COALESCE(o.payload_json->'optimization'->'stock_reservations',
                                     '[]'::jsonb)) r
                        WHERE COALESCE((r->>'short')::numeric, 0) > 0)))
                AS work_orders_shortage,
            (SELECT count(*) FROM public.orders o
             WHERE o.org_id = %(o)s AND o.order_type = 'WORKSHOP_OT'
               AND o.status = 'COMPLETED' AND o.payload_json ? 'packing'
               AND NOT EXISTS (
                   SELECT 1 FROM public.dispatch_notes dn
                   WHERE dn.org_id = o.org_id AND dn.work_order_id = o.id
                     AND dn.voided_at IS NULL))
                AS dispatch_ready
        """,
        {"o": str(org_id)},
    )
    deliveries = one(
        """
        SELECT
            count(*) FILTER (WHERE scheduled_date = local_today
                AND status IN ('SCHEDULED','ON_ROUTE','FAILED')) AS today,
            count(*) FILTER (WHERE scheduled_date < local_today
                AND status IN ('SCHEDULED','ON_ROUTE','FAILED')) AS overdue
        FROM public.deliveries,
            LATERAL (
                SELECT (CURRENT_TIMESTAMP AT TIME ZONE org.timezone)::date AS local_today
                FROM public.tenancy_organizations AS org
                WHERE org.id = %s
            ) AS zone
        WHERE org_id = %s
        """,
        [str(org_id), str(org_id)],
    )
    with job_owner():
        failed_jobs = one(
            "SELECT count(*) AS n FROM public.job_runs "
            "WHERE org_id = %s AND state = 'FAILED'",
            [str(org_id)],
        )["n"]
        failed_job_items = rows(
            "SELECT id, type, completed_at FROM public.job_runs "
            "WHERE org_id = %s AND state = 'FAILED' "
            "ORDER BY completed_at DESC LIMIT 3",
            [str(org_id)],
        )
    return {
        "attention": {
            "quotes_unsent": int(counts["quotes_unsent"]),
            "quotes_stale": int(counts["quotes_stale"]),
            "approvals_pending": int(counts["approvals_pending"]),
            "versions_ready": int(counts["versions_ready"]),
            "work_orders_shortage": int(counts["work_orders_shortage"]),
            "steps_blocked": int(counts["steps_blocked"]),
            "dispatch_ready": int(counts["dispatch_ready"]),
            "catalog_gaps": int(counts["catalog_gaps"]),
            "deliveries_today": int(deliveries["today"]),
            "deliveries_overdue": int(deliveries["overdue"]),
            "failed_jobs": int(failed_jobs),
        },
        "items": {
            "quotes_unsent": [
                {"id": str(row["id"]), "code": _cut(row["code"]), "name": _cut(row["name"])}
                for row in rows(
                    "SELECT p.id, p.code, p.name FROM public.projects p "
                    "WHERE p.org_id=%s AND p.status='QUOTED' AND NOT EXISTS ("
                    "  SELECT 1 FROM public.customer_approvals a"
                    "  JOIN public.project_versions v"
                    "    ON v.id=a.project_version_id AND v.org_id=a.org_id"
                    "  WHERE a.org_id=p.org_id AND a.project_id=p.id"
                    "    AND v.revision_code=p.current_revision) "
                    "ORDER BY p.updated_at DESC LIMIT 3",
                    [org_id],
                )
            ],
            "approvals_pending": [
                {"id": str(row["id"]), "code": _cut(row["code"]), "name": _cut(row["name"])}
                for row in rows(
                    "SELECT DISTINCT p.id, p.code, p.name, p.updated_at "
                    "FROM public.projects p "
                    "JOIN public.customer_approvals a"
                    "  ON a.project_id=p.id AND a.org_id=p.org_id "
                    "JOIN public.project_versions v"
                    "  ON v.id=a.project_version_id AND v.org_id=a.org_id "
                    "WHERE p.org_id=%s AND a.status='PENDING' "
                    "  AND a.expires_at>now() "
                    "  AND p.current_revision=v.revision_code "
                    "  AND p.status='QUOTED' "
                    "ORDER BY p.updated_at DESC LIMIT 3",
                    [org_id],
                )
            ],
            "work_orders_shortage": [
                {"id": str(row["id"]), "order_code": _cut(row["order_code"])}
                for row in rows(
                    "SELECT o.id, o.order_code FROM public.orders o "
                    "WHERE o.org_id=%s AND o.order_type='WORKSHOP_OT' "
                    "  AND o.status NOT IN ('CANCELLED','INSTALLED') "
                    "  AND (COALESCE((o.payload_json->'prep'->>'shortages')::int,0)>0"
                    "   OR EXISTS (SELECT 1 FROM jsonb_array_elements("
                    "       COALESCE(o.payload_json->'optimization'->'stock_reservations',"
                    "                '[]'::jsonb)) r"
                    "    WHERE COALESCE((r->>'short')::numeric,0)>0)) "
                    "ORDER BY o.updated_at DESC LIMIT 3",
                    [org_id],
                )
            ],
            "steps_blocked": [
                {"id": str(row["id"]), "order_code": _cut(row["order_code"])}
                for row in rows(
                    "SELECT s.id, o.order_code FROM public.production_steps s "
                    "JOIN public.orders o ON o.id=s.order_id AND o.org_id=s.org_id "
                    "WHERE s.org_id=%s AND s.status='BLOCKED' "
                    "  AND o.status NOT IN ('CANCELLED','INSTALLED') "
                    "ORDER BY s.updated_at DESC LIMIT 3",
                    [org_id],
                )
            ],
            "deliveries": [
                {
                    "id": str(row["id"]),
                    "order_code": _cut(row["order_code"]),
                    "scheduled_date": _cut(row["scheduled_date"]),
                    "status": _cut(row["status"]),
                }
                for row in rows(
                    "SELECT d.id, d.scheduled_date::text AS scheduled_date, "
                    "       d.status, o.order_code "
                    "FROM public.deliveries d "
                    "JOIN public.orders o ON o.id=d.order_id AND o.org_id=d.org_id, "
                    "LATERAL (SELECT (CURRENT_TIMESTAMP AT TIME ZONE org.timezone)::date"
                    "         AS local_today FROM public.tenancy_organizations org"
                    "         WHERE org.id=%s) zone "
                    "WHERE d.org_id=%s "
                    "  AND d.status IN ('SCHEDULED','ON_ROUTE','FAILED') "
                    "  AND d.scheduled_date <= zone.local_today "
                    "ORDER BY d.scheduled_date ASC LIMIT 3",
                    [str(org_id), str(org_id)],
                )
            ],
            "failed_jobs": [
                {
                    "id": str(row["id"]),
                    "type": _cut(row["type"]),
                    "completed_at": row["completed_at"].isoformat()
                    if row["completed_at"] is not None
                    else None,
                }
                for row in failed_job_items
            ],
        },
    }


def _projects(org_id: UUID) -> dict:
    result = rows(
        "SELECT p.id, p.code, p.name, p.client_name, p.status, "
        "(SELECT count(*) FROM public.project_positions pp "
        " WHERE pp.project_id=p.id AND pp.org_id=%s) AS positions "
        "FROM public.projects p WHERE p.org_id=%s "
        "ORDER BY p.updated_at DESC LIMIT %s",
        [org_id, org_id, MAX_LIST],
    )
    return {
        "projects": [
            {
                "id": str(p["id"]),
                "code": _cut(p["code"]),
                "name": _cut(p["name"]),
                "client": _cut(p["client_name"]),
                "status": _cut(p["status"]),
                "positions": int(p["positions"]),
            }
            for p in result
        ],
        "truncated": len(result) == MAX_LIST,
    }


def _project_row(org_id: UUID, project_id: UUID) -> dict:
    result = rows(
        "SELECT id, code, name, client_id, client_name, status, current_revision, "
        "total_price_net, total_price_tax, total_price_gross "
        "FROM public.projects WHERE id=%s AND org_id=%s",
        [project_id, org_id],
    )
    if not result:
        raise _ContextError("ai_context_not_found")
    return result[0]


def _payments(org_id: UUID, project_id: UUID) -> dict:
    result = rows(
        "SELECT count(*) AS count, COALESCE(SUM(amount),0) AS collected "
        "FROM public.project_payments "
        "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
        [org_id, project_id],
    )
    return {
        "payments_count": int(result[0]["count"]),
        "payments_collected": _cut(result[0]["collected"]),
    }


def _project(org_id: UUID, refs: dict) -> dict:
    project = _project_row(org_id, _ref(refs, "project_id"))
    positions = rows(
        "SELECT id, position_index, location_tag, typology, width_mm, height_mm "
        "FROM public.project_positions WHERE org_id=%s AND project_id=%s "
        "ORDER BY position_index LIMIT %s",
        [org_id, project["id"], MAX_LIST],
    )
    versions = rows(
        "SELECT revision_code, documentary_complete, production_allowed "
        "FROM public.project_versions WHERE org_id=%s AND project_id=%s "
        "ORDER BY emitted_at DESC LIMIT 1",
        [org_id, project["id"]],
    )
    context: dict[str, Any] = {
        "id": str(project["id"]),
        "code": _cut(project["code"]),
        "name": _cut(project["name"]),
        "client": _cut(project["client_name"]),
        "status": _cut(project["status"]),
        "current_revision": _cut(project["current_revision"]),
        "totals": {
            "net": _cut(project["total_price_net"]),
            "tax": _cut(project["total_price_tax"]),
            "gross": _cut(project["total_price_gross"]),
        },
        "payments": _payments(org_id, project["id"]),
        "positions": [
            {
                "id": str(p["id"]),
                "index": int(p["position_index"]),
                "location": _cut(p["location_tag"]),
                "typology": _cut(p["typology"]),
                "width_mm": _cut(p["width_mm"]),
                "height_mm": _cut(p["height_mm"]),
            }
            for p in positions
        ],
    }
    if versions:
        context["latest_version"] = {
            "revision": _cut(versions[0]["revision_code"]),
            "documentary_complete": bool(versions[0]["documentary_complete"]),
            "production_allowed": bool(versions[0]["production_allowed"]),
        }
    # Positions are writable only while the current revision is unsealed —
    # batch design ops are only offerable when this reads true.
    context["editable"] = project["status"] == "DRAFT" and not (
        versions and versions[0]["revision_code"] == project["current_revision"]
    )
    return context


def _module_intent(module: dict) -> dict:
    """Batch-edit targeting surface: each module's declared openings and
    commercial glass SKU — 'todas las fijas a abatible' or 'copia el vidrio
    de esta posición' can only be proposed against this information, never
    guessed (§08-WC). Walks the module's intent tree for BAY nodes."""
    openings: list[str] = []
    glass_skus: list[str] = []

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "BAY":
            opening = node.get("opening_type")
            sku = node.get("glass_article_sku")
            if isinstance(opening, str) and opening not in openings:
                openings.append(opening)
            if isinstance(sku, str) and sku and sku not in glass_skus:
                glass_skus.append(sku)
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                walk(child)

    tree = module.get("tree")
    if isinstance(tree, dict):
        walk(tree)
    return {"openings": openings, "glass_skus": glass_skus}


# Refs that describe the user's current pointer rather than the conversation's
# object — they reach the context projection but never identity a thread or
# job, or every click on the canvas would orphan the dock.
VOLATILE_REFS = frozenset({"selection"})


def stable_refs(refs: dict) -> dict:
    return {key: value for key, value in refs.items() if key not in VOLATILE_REFS}


def _position(org_id: UUID, refs: dict) -> dict:
    result = rows(
        "SELECT p.id, p.project_id, p.position_index, p.location_tag, p.typology, "
        "p.width_mm, p.height_mm, p.parametric_tree, "
        "s.code AS system_code, s.name AS system_name, s.material, "
        "pr.code AS project_code, pr.name AS project_name "
        "FROM public.project_positions p "
        "LEFT JOIN public.profile_systems s ON s.id = p.system_id "
        "  AND (s.org_id = p.org_id OR (s.org_id IS NULL AND s.is_global)) "
        "JOIN public.projects pr ON pr.id = p.project_id AND pr.org_id = p.org_id "
        "WHERE p.id=%s AND p.org_id=%s",
        [_ref(refs, "position_id"), org_id],
    )
    if not result:
        raise _ContextError("ai_context_not_found")
    position = result[0]
    tree = _jsonb(position.get("parametric_tree"))
    assembly = tree.get("assembly") if isinstance(tree, dict) else None
    modules = assembly.get("modules") if isinstance(assembly, dict) else None
    couplings = assembly.get("couplings") if isinstance(assembly, dict) else None
    if modules is None and isinstance(tree, dict) and tree:
        # Single-module positions persist the module's own tree without an
        # assembly envelope — surface one module carrying the position's dims.
        modules = [
            {
                "single": True,
                "width_mm": position["width_mm"],
                "height_mm": position["height_mm"],
                # Single-module positions persist the module's own tree —
                # without it the intent surface would report no openings.
                "tree": tree,
            }
        ]
    projected_modules = (
        [
            {
                "id": _cut(m.get("id"), 40),
                "width_mm": _cut(m.get("width_mm")),
                "height_mm": _cut(m.get("height_mm")),
                **_module_intent(m),
                **({"single": True} if m.get("single") else {}),
            }
            for m in modules[:MAX_LIST]
            if isinstance(m, dict)
        ]
        if isinstance(modules, list)
        else None
    )
    # §11: the canvas publishes the selected element's id as `selection` —
    # resolve it against the module list so "this sash" / "muévela" binds to
    # a concrete element instead of the assistant guessing.
    selection_id = refs.get("selection")
    selected = None
    if selection_id and projected_modules:
        module_ids = {m["id"] for m in projected_modules}
        head = str(selection_id).split("/", 1)[0]
        if selection_id in module_ids:
            selected = {"id": _cut(selection_id, 80), "kind": "module"}
        elif head in module_ids:
            # A sub-element (bay/sash) inside a module — keep the module
            # scope visible so ops target the right container.
            selected = {
                "id": _cut(selection_id, 80),
                "kind": "element",
                "module_id": head,
            }
        elif isinstance(couplings, list) and any(
            c.get("id") == selection_id for c in couplings if isinstance(c, dict)
        ):
            selected = {"id": _cut(selection_id, 80), "kind": "coupling"}
    return {
        "id": str(position["id"]),
        "project": {
            "id": str(position["project_id"]),
            "code": _cut(position["project_code"]),
            "name": _cut(position["project_name"]),
        },
        "index": int(position["position_index"]),
        "location": _cut(position["location_tag"]),
        "typology": _cut(position["typology"]),
        "system": {
            "code": _cut(position["system_code"]),
            "name": _cut(position["system_name"]),
            "material": _cut(position["material"]),
        },
        "width_mm": _cut(position["width_mm"]),
        "height_mm": _cut(position["height_mm"]),
        "modules": projected_modules,
        "couplings": len(couplings) if isinstance(couplings, list) else None,
        "selected": selected,
    }


def _quotation(org_id: UUID, refs: dict) -> dict:
    project = _project_row(org_id, _ref(refs, "project_id"))
    versions = rows(
        "SELECT revision_code, documentary_complete, production_allowed, "
        "bom_hash IS NOT NULL AS frozen "
        "FROM public.project_versions WHERE org_id=%s AND project_id=%s "
        "ORDER BY emitted_at DESC LIMIT 3",
        [org_id, project["id"]],
    )
    positions = rows(
        "SELECT count(*) AS total FROM public.project_positions "
        "WHERE org_id=%s AND project_id=%s",
        [org_id, project["id"]],
    )
    # Priced state = an APPLIED pricing_operations row on the current
    # revision — pricing_operations is service-owned, so the read follows
    # the same documented exception as job_runs: the pricing role with the
    # explicit org filter (mirrors _pricing_authority's predicate exactly).
    with commercial_backend():
        priced = rows(
            "SELECT request->>'currency' AS currency "
            "FROM public.pricing_operations "
            "WHERE org_id=%s AND project_id=%s AND state='APPLIED' "
            "AND COALESCE(revision_code,'REV-A')=%s "
            "AND ((SELECT pricing_reset_at FROM public.projects WHERE id=%s) IS NULL "
            "OR approved_at > (SELECT pricing_reset_at FROM public.projects WHERE id=%s)) "
            "ORDER BY approved_at DESC, id DESC LIMIT 1",
            [
                org_id, project["id"], project["current_revision"],
                project["id"], project["id"],
            ],
        )
    approval = rows(
        "SELECT a.status::text AS status, a.expires_at > now() AS live "
        "FROM public.customer_approvals a "
        "JOIN public.project_versions v "
        "  ON v.id = a.project_version_id AND v.org_id = a.org_id "
        "WHERE a.org_id=%s AND a.project_id=%s AND v.revision_code=%s "
        "ORDER BY a.created_at DESC LIMIT 1",
        [org_id, project["id"], project["current_revision"]],
    )
    # Document counts deliberately don't query document_artifacts: the sealed
    # evidence table is revoked from `authenticated` and served only through
    # documentary_backend — a caller-scoped projection must not proxy it.
    return {
        "project": {
            "id": str(project["id"]),
            "code": _cut(project["code"]),
            "name": _cut(project["name"]),
            "status": _cut(project["status"]),
        },
        "current_revision": _cut(project["current_revision"]),
        "positions": {"total": int(positions[0]["total"])},
        "priced": (
            {"currency": _cut(priced[0]["currency"])} if priced else None
        ),
        "approval": (
            {
                "status": _cut(approval[0]["status"]),
                "live": bool(approval[0]["live"]),
            }
            if approval
            else None
        ),
        "totals": {
            "net": _cut(project["total_price_net"]),
            "tax": _cut(project["total_price_tax"]),
            "gross": _cut(project["total_price_gross"]),
        },
        "payments": _payments(org_id, project["id"]),
        "versions": [
            {
                "revision": _cut(v["revision_code"]),
                "documentary_complete": bool(v["documentary_complete"]),
                "production_allowed": bool(v["production_allowed"]),
                "frozen": bool(v["frozen"]),
            }
            for v in versions
        ],
    }


def _catalog(org_id: UUID, refs: dict) -> dict:
    """§06-H catalog assistant context. Without a system ref: every visible
    system plus the review-queue signals a triage answer needs. With
    system_id: the workspace aggregate projected down — readiness ladder
    with exact blockers (explain), provenance/review state (evidence),
    compact entity rosters (relationships, dedupe) and revisions."""
    raw = refs.get("system_id")
    if raw:
        return _catalog_system(org_id, _ref(refs, "system_id"))
    systems = rows(
        "SELECT id, code, name, material::text AS material, is_global, "
        "is_active AS active, is_global AS read_only, data_provenance::text AS provenance, "
        "review_pending "
        "FROM public.profile_systems "
        "WHERE org_id=%s OR (org_id IS NULL AND is_global) "
        "ORDER BY code LIMIT %s",
        [org_id, MAX_LIST],
    )
    return {
        "systems": [
            {
                "id": str(s["id"]),
                "code": _cut(s["code"]),
                "name": _cut(s["name"]),
                "material": _cut(s["material"]),
                "is_global": bool(s["is_global"]),
                "read_only": bool(s["read_only"]),
                "provenance": _cut(s["provenance"]),
                "review_pending": bool(s["review_pending"]),
                "active": bool(s["active"]),
            }
            for s in systems
        ],
        "truncated": len(systems) == MAX_LIST,
    }


def _catalog_system(org_id: UUID, system_id: UUID) -> dict:
    from catalogs.readiness import catalog_readiness
    from catalogs.service import system_workspace

    try:
        workspace = system_workspace(org_id, system_id)
    except ContractAPIException as error:
        if getattr(error, "status_code", None) == 404:
            raise _ContextError("ai_context_not_found") from None
        raise
    system = workspace["system"]

    def entities(rows_: list[dict], fields: tuple[str, ...]) -> list[dict]:
        return [
            {name: _cut(row.get(name)) if not isinstance(row.get(name), bool) else row.get(name) for name in fields}
            for row in rows_[:MAX_LIST]
        ]

    review_queue = [
        {"kind": kind, "id": str(row.get("id")), "label": _cut(row.get("sku") or row.get("code") or row.get("name"))}
        for kind, rows_ in (
            ("system", [system]),
            ("article", workspace["articles"]),
            ("bead", workspace["beads"]),
            ("kit", workspace["kits"]),
        )
        for row in rows_
        if row.get("review_pending") or row.get("data_provenance") == "LEGACY_UNVERIFIED"
    ][:MAX_LIST]

    try:
        readiness = catalog_readiness(system_id, org_id)
    except Exception:
        readiness = None

    return {
        "system": {
            "id": str(system["id"]),
            "code": _cut(system.get("code")),
            "name": _cut(system.get("name")),
            "material": _cut(system.get("material")),
            "manufacturer": _cut(system.get("manufacturer")),
            "family": _cut(system.get("family")),
            "read_only": bool(system.get("read_only")),
            "provenance": _cut(system.get("data_provenance")),
            "review_pending": bool(system.get("review_pending")),
            "revision": _cut(system.get("revision")),
        },
        "readiness": readiness,
        "counts": {
            "articles": len(workspace["articles"]),
            "beads": len(workspace["beads"]),
            "kits": len(workspace["kits"]),
            "reinforcements": len(workspace["reinforcements"]),
            "purchase_mappings": len(workspace["purchase_mappings"]),
            "sections_declared": sum(
                1 for a in workspace["articles"] if a.get("section")
            ),
            "sections_dxf": sum(
                1
                for a in workspace["articles"]
                if isinstance(a.get("section"), dict)
                and a["section"].get("source") == "DXF_REFERENCE"
            ),
        },
        "articles": entities(
            workspace["articles"],
            ("id", "sku", "name", "role", "review_pending",
             "revision", "section_revision", "section_revised_by"),
        ),
        "beads": entities(workspace["beads"], ("id", "sku", "name")),
        "kits": entities(workspace["kits"], ("id", "code", "label", "review_pending")),
        "purchase_mappings": entities(
            workspace["purchase_mappings"],
            ("id", "profile_article_id", "commercial_sku", "manufacturer_name", "supplier_name"),
        ),
        "reinforcements": entities(
            workspace["reinforcements"], ("id", "sku", "commercial_sku", "name")
        ),
        "process_profile": (
            {
                "code": _cut(workspace["process_profile"].get("code")),
                "label": _cut(workspace["process_profile"].get("label")),
                "version": _cut(workspace["process_profile"].get("version")),
            }
            if workspace.get("process_profile")
            else None
        ),
        "review_queue": review_queue,
        "truncated": any(
            len(workspace[key]) > MAX_LIST
            for key in ("articles", "beads", "kits", "purchase_mappings", "reinforcements")
        ),
    }


def _project_docs(org_id: UUID, refs: dict) -> dict:
    """§08-WA project-from-documents: the project's document imports with
    their extraction candidates, the active catalog systems for typology
    mapping, and the positions that already exist so the draft doesn't
    duplicate them. Candidates are review data — the human confirms them
    on the import surface, never the agent."""
    project = _project_row(org_id, _ref(refs, "project_id"))
    imports = rows(
        "SELECT id, file_name, kind, status, candidates, warnings, error_code "
        "FROM public.document_imports "
        "WHERE org_id=%s AND project_id=%s "
        "ORDER BY created_at DESC LIMIT %s",
        [org_id, project["id"], 6],
    )
    systems = rows(
        "SELECT id, code, name, material::text AS material, "
        "manufacturer, family "
        "FROM public.profile_systems "
        "WHERE (org_id=%s OR (org_id IS NULL AND is_global)) AND is_active "
        "ORDER BY code LIMIT %s",
        [org_id, MAX_LIST],
    )
    positions = rows(
        "SELECT position_index, location_tag, typology, width_mm, height_mm "
        "FROM public.project_positions WHERE org_id=%s AND project_id=%s "
        "ORDER BY position_index LIMIT %s",
        [org_id, project["id"], MAX_LIST],
    )
    # Candidates are capped across imports — a document can carry hundreds
    # of rows; the draft proposes what fits and the rest stays in review.
    budget = 24
    documents = []
    for imp in imports:
        raw = _jsonb(imp["candidates"])
        cands = raw if isinstance(raw, list) else []
        take = cands[: max(budget, 0)]
        budget -= len(take)
        documents.append(
            {
                "id": str(imp["id"]),
                "file_name": _cut(imp["file_name"]),
                "kind": _cut(imp["kind"]),
                "status": _cut(imp["status"]),
                "error_code": _cut(imp["error_code"]),
                "candidates_total": len(cands),
                "candidates": [
                    {
                        "key": _cut(c.get("key"), 40),
                        "label": _cut(c.get("label")),
                        "width_mm": _cut(c.get("width_mm")),
                        "height_mm": _cut(c.get("height_mm")),
                        "quantity": _cut(c.get("quantity")),
                        "opening_type": _cut(c.get("opening_type")),
                        "confidence": _cut(c.get("confidence")),
                        "warnings": [
                            _cut(w)
                            for w in (c.get("warnings") or [])[:4]
                            if isinstance(w, str)
                        ],
                    }
                    for c in take
                    if isinstance(c, dict)
                ],
                "warnings": [
                    _cut(w)
                    for w in (_jsonb(imp["warnings"]) or [])[:6]
                    if isinstance(w, str)
                ],
            }
        )
    return {
        "project": {
            "id": str(project["id"]),
            "code": _cut(project["code"]),
            "name": _cut(project["name"]),
            "status": _cut(project["status"]),
        },
        "documents": documents,
        "systems": [
            {
                "id": str(s["id"]),
                "code": _cut(s["code"]),
                "name": _cut(s["name"]),
                "material": _cut(s["material"]),
                "manufacturer": _cut(s.get("manufacturer")),
                "family": _cut(s.get("family")),
            }
            for s in systems
        ],
        "positions": [
            {
                "index": int(p["position_index"]),
                "location": _cut(p["location_tag"]),
                "typology": _cut(p["typology"]),
                "width_mm": _cut(p["width_mm"]),
                "height_mm": _cut(p["height_mm"]),
            }
            for p in positions
        ],
    }


def _production(org_id: UUID) -> dict:
    orders = rows(
        "SELECT o.id, o.order_code, o.status::text AS status, "
        "COUNT(s.id) AS steps_total, "
        "COUNT(s.id) FILTER (WHERE s.status='DONE') AS steps_done "
        "FROM public.orders o "
        "LEFT JOIN public.production_steps s ON s.order_id=o.id AND s.org_id=o.org_id "
        "WHERE o.org_id=%s AND o.order_type='WORKSHOP_OT' "
        "GROUP BY o.id ORDER BY o.created_at DESC LIMIT %s",
        [org_id, MAX_LIST],
    )
    return {
        "work_orders": [
            {
                "id": str(o["id"]),
                "code": _cut(o["order_code"]),
                "status": _cut(o["status"]),
                "steps_done": int(o["steps_done"]),
                "steps_total": int(o["steps_total"]),
            }
            for o in orders
        ],
        "truncated": len(orders) == MAX_LIST,
    }


def _work_order(org_id: UUID, refs: dict) -> dict:
    order_id = _ref(refs, "work_order_id")
    order = rows(
        "SELECT o.order_code, o.status::text AS status, "
        "o.payload_json->'optimization'->'stock_reservations' AS reservations "
        "FROM public.orders o "
        "WHERE o.id=%s AND o.org_id=%s AND o.order_type='WORKSHOP_OT'",
        [order_id, org_id],
    )
    if not order:
        raise _ContextError("ai_context_not_found")
    steps = rows(
        "SELECT sequence, code, label, status FROM public.production_steps "
        "WHERE org_id=%s AND order_id=%s ORDER BY sequence LIMIT %s",
        [org_id, order_id, MAX_LIST * 2],
    )
    reservations = _jsonb(order[0].get("reservations"))
    shortages = (
        sum(1 for entry in reservations if isinstance(entry, dict) and _positive(entry.get("short")))
        if isinstance(reservations, list)
        else 0
    )
    # §21: the assistant reads canonical CNC truth — per-member machining
    # verdicts against the org's real machines — so "why is M-07 blocked"
    # is answered from engine validation, never invented.
    cnc: dict[str, Any] = {}
    try:
        from production.cnc import cnc_readiness

        readiness = cnc_readiness(org_id=org_id, order_id=order_id)
        members = readiness.get("members", [])
        cnc = {
            "issues": [
                _cut(str(issue.get("detail", issue.get("code", ""))))
                for issue in readiness.get("issues", [])[:MAX_LIST]
                if isinstance(issue, dict)
            ],
            "members": [
                {
                    "member": _cut(str(m.get("member_label", ""))),
                    "kinds": m.get("kinds", []),
                    "machines": [
                        {
                            "machine": _cut(str(mc.get("machine_code", ""))),
                            "verdict": mc.get("verdict"),
                            "blockers": [
                                _cut(str(b.get("detail", b.get("code", ""))))
                                for b in (mc.get("blockers") or [])[:5]
                                if isinstance(b, dict)
                            ],
                        }
                        for mc in m.get("machines", [])[:5]
                    ],
                }
                for m in members[:MAX_LIST]
                if isinstance(m, dict)
            ],
            "programs": [
                {
                    "program_no": _cut(str(p.get("program_no", ""))),
                    "machine": _cut(str(p.get("machine_code", ""))),
                    "status": p.get("status"),
                }
                for p in readiness.get("programs", [])[:MAX_LIST]
                if isinstance(p, dict)
            ],
        }
    except Exception:  # noqa: BLE001 — CNC truth must never break the projection
        cnc = {}
    return {
        "id": str(order_id),
        "order_code": _cut(order[0]["order_code"]),
        "status": _cut(order[0]["status"]),
        "shortages": shortages,
        "steps": [
            {
                "sequence": int(s["sequence"]),
                "code": _cut(s["code"]),
                "label": _cut(s["label"]),
                "status": _cut(s["status"]),
            }
            for s in steps
        ],
        "cnc": cnc,
    }


def _clients(org_id: UUID) -> dict:
    result = rows(
        "SELECT id, name, rut, email, phone FROM public.clients "
        "WHERE org_id=%s AND is_active ORDER BY name LIMIT %s",
        [org_id, MAX_LIST],
    )
    return {
        "clients": [
            {
                # The id is what drill-down refs need; email/phone let the
                # comms surface cite real contact data instead of inventing it.
                "id": str(c["id"]),
                "name": _cut(c["name"]),
                "rut": _cut(c["rut"]),
                "email": _cut(c["email"]),
                "phone": _cut(c["phone"]),
            }
            for c in result
        ],
        "truncated": len(result) == MAX_LIST,
    }


def _client(org_id: UUID, refs: dict) -> dict:
    """One client's desk: identity + their projects — the detail route's
    assistant must answer about THIS client, not the org aggregate."""
    client = rows(
        "SELECT id, name, rut, email, phone, address, notes, is_active"
        " FROM public.clients WHERE id=%s AND org_id=%s",
        [refs["client_id"], org_id],
    )
    if not client:
        raise _ContextError("ai_ref_not_found")
    client = client[0]
    projects = rows(
        "SELECT id, code, name, status, current_revision"
        " FROM public.projects WHERE client_id=%s AND org_id=%s"
        " ORDER BY updated_at DESC LIMIT %s",
        [refs["client_id"], org_id, MAX_LIST],
    )
    return {
        "client": {
            "id": str(client["id"]),
            "name": _cut(client["name"]),
            "rut": _cut(client["rut"]),
            "email": _cut(client["email"]),
            "phone": _cut(client["phone"]),
            "address": _cut(client["address"]),
            "active": bool(client["is_active"]),
        },
        "projects": [
            {
                "id": str(p["id"]),
                "code": _cut(p["code"]),
                "name": _cut(p["name"]),
                "status": _cut(p["status"]),
                "revision": _cut(p["current_revision"]),
            }
            for p in projects
        ],
    }


def _purchasing(org_id: UUID) -> dict:
    orders = rows(
        "SELECT id, order_code, order_type::text AS order_type, status::text AS status, "
        "supplier_name FROM public.orders "
        "WHERE org_id=%s AND order_type::text LIKE 'SUPPLIER%%' "
        "ORDER BY created_at DESC LIMIT %s",
        [org_id, MAX_LIST],
    )
    # Real stock, not just the order ledger — a 'what can we buy' answer
    # without on-hand balances would be guessing. inventory_stock is granted
    # to documentary_backend already, so the ambient role reads it.
    stock = rows(
        "SELECT item_id, sku, name, category, unit, on_hand_qty, reserved_qty"
        " FROM public.inventory_stock WHERE org_id=%s"
        " ORDER BY sku LIMIT %s",
        [org_id, MAX_LIST],
    )
    return {
        "supplier_orders": [
            {
                "id": str(o["id"]),
                "code": _cut(o["order_code"]),
                "type": _cut(o["order_type"]),
                "status": _cut(o["status"]),
                "supplier": _cut(o["supplier_name"]),
            }
            for o in orders
        ],
        "stock": [
            {
                "item_id": str(s["item_id"]),
                "sku": _cut(s["sku"]),
                "name": _cut(s["name"]),
                "category": _cut(s["category"]),
                "unit": _cut(s["unit"]),
                "on_hand": str(s["on_hand_qty"]),
                "reserved": str(s["reserved_qty"]),
            }
            for s in stock
        ],
        "truncated": len(orders) == MAX_LIST or len(stock) == MAX_LIST,
    }


def _purchase_plan(org_id: UUID) -> dict:
    """§08-WE — what a purchase decision actually needs: requirement lines on
    each project's latest documentary version that no allocation covers, the
    supplier options those versions declared eligible, and the purchase
    orders already open. A draft plan can only restate these rows — it
    never invents supplier prices or lead times."""
    latest = (
        "SELECT DISTINCT ON (project_id) id FROM public.project_versions "
        "WHERE org_id=%s AND authority_version IN ('SHOT09_V1','SHOT10_V1') "
        "ORDER BY project_id, emitted_at DESC"
    )
    # Purchase-authority tables are revoked from member roles — the reads run
    # under the documentary role with the explicit org filter (same documented
    # exception as the brief's job_runs count). Coverage joins are only
    # verifiable for roles the allocations/eligibility policies list (OWNER,
    # WORKSHOP_MANAGER); for anyone else the allocation join is silently empty
    # and would fabricate "uncovered" — so the probe runs first and the
    # projection reports coverage as unverifiable instead.
    with documentary_backend():
        coverage = rows(
            "SELECT private.documentary_role(%s, ARRAY['OWNER','WORKSHOP_MANAGER']) "
            "AS can_verify",
            [org_id],
        )
        can_verify = bool(coverage and coverage[0]["can_verify"])
        uncovered = []
        uncovered_total = 0
        suppliers = []
        if can_verify:
            uncovered = rows(
                "SELECT line.id, line.requirement_key, "
                "line.order_type::text AS order_type, line.category, "
                "line.purchasing_sku, line.unit, line.quantity, "
                "v.project_id, v.id AS version_id, p.code AS project_code "
                "FROM public.purchase_requirement_lines line "
                "JOIN public.project_versions v "
                "  ON v.id = line.project_version_id AND v.org_id = line.org_id "
                "JOIN public.projects p ON p.id = v.project_id AND p.org_id = v.org_id "
                "LEFT JOIN public.purchase_allocations a "
                "  ON a.requirement_line_id = line.id AND a.org_id = line.org_id "
                f"WHERE line.org_id = %s AND a.id IS NULL AND v.id IN ({latest}) "
                "ORDER BY v.emitted_at DESC, line.order_type, "
                "line.requirement_key LIMIT 12",
                [org_id, org_id],
            )
            uncovered_total = int(
                rows(
                    "SELECT count(*) AS n "
                    "FROM public.purchase_requirement_lines line "
                    "JOIN public.project_versions v "
                    "  ON v.id = line.project_version_id AND v.org_id = line.org_id "
                    "LEFT JOIN public.purchase_allocations a "
                    "  ON a.requirement_line_id = line.id AND a.org_id = line.org_id "
                    f"WHERE line.org_id = %s AND a.id IS NULL AND v.id IN ({latest})",
                    [org_id, org_id],
                )[0]["n"]
            )
            suppliers = rows(
                "SELECT DISTINCT e.order_type::text AS order_type, e.supplier_name "
                "FROM public.supplier_eligibility_versions e "
                f"WHERE e.org_id = %s AND e.project_version_id IN ({latest}) "
                "ORDER BY e.order_type, e.supplier_name LIMIT %s",
                [org_id, org_id, MAX_LIST],
            )
    open_pos = rows(
        "SELECT id, order_code, order_type::text AS order_type, status::text AS status, "
        "supplier_name FROM public.orders "
        "WHERE org_id=%s AND order_type::text LIKE 'SUPPLIER%%' "
        "  AND status::text NOT IN ('RECEIVED','CANCELLED') "
        "ORDER BY created_at DESC LIMIT 10",
        [org_id],
    )
    return {
        "uncovered_lines": [
            {
                "id": str(row["id"]),
                "requirement_key": _cut(row["requirement_key"]),
                "order_type": _cut(row["order_type"]),
                "category": _cut(row["category"]),
                "sku": _cut(row["purchasing_sku"]),
                "unit": _cut(row["unit"]),
                "quantity": _cut(row["quantity"]),
                "project_id": str(row["project_id"]),
                "version_id": str(row["version_id"]),
                "project_code": _cut(row["project_code"]),
            }
            for row in uncovered
        ],
        "uncovered_total": uncovered_total,
        "truncated": uncovered_total > len(uncovered),
        "coverage_verified": can_verify,
        "suppliers": (
            [
                {
                    "order_type": _cut(row["order_type"]),
                    "supplier": _cut(row["supplier_name"]),
                }
                for row in suppliers
            ]
            if can_verify
            else None
        ),
        "open_purchase_orders": [
            {
                "id": str(row["id"]),
                "code": _cut(row["order_code"]),
                "type": _cut(row["order_type"]),
                "status": _cut(row["status"]),
                "supplier": _cut(row["supplier_name"]),
            }
            for row in open_pos
        ],
    }


def _production_plan(org_id: UUID) -> dict:
    """§08-WF — what a proposed production schedule can restate: every open
    work order with its station queue, material state, and delivery pressure.
    A plan orders these rows and names the next concrete step — it never
    invents dates, durations, or station capacity."""
    orders = rows(
        """
        SELECT o.id, o.order_code, o.status::text AS status,
               p.code AS project_code, o.created_at,
               d.scheduled_date AS delivery_date, d.status::text AS delivery_status,
               EXISTS (
                   SELECT 1 FROM jsonb_array_elements(
                       COALESCE(o.payload_json->'optimization'->'stock_reservations',
                                '[]'::jsonb)) r
                   WHERE COALESCE((r->>'short')::numeric, 0) > 0
               ) AS short
        FROM public.orders o
        JOIN public.project_versions v
          ON v.id = o.project_version_id AND v.org_id = o.org_id
        JOIN public.projects p
          ON p.id = v.project_id AND p.org_id = v.org_id
        LEFT JOIN public.deliveries d
          ON d.order_id = o.id AND d.org_id = o.org_id
        WHERE o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
          AND o.status NOT IN ('CANCELLED', 'INSTALLED')
        ORDER BY o.created_at DESC LIMIT %s
        """,
        [org_id, MAX_LIST],
    )
    order_ids = [str(o["id"]) for o in orders]
    queues: dict[str, list[dict]] = {}
    if order_ids:
        # Per-order cap via ROW_NUMBER — a global limit would starve the
        # latest orders (they'd show fewer steps or no next_step at all).
        steps = rows(
            """
            SELECT order_id, sequence, code, label, status
            FROM (
                SELECT order_id, sequence, code, label, status,
                       ROW_NUMBER() OVER (
                           PARTITION BY order_id ORDER BY sequence
                       ) AS rn
                FROM public.production_steps
                WHERE org_id = %s AND order_id = ANY(%s::uuid[])
            ) s
            WHERE rn <= 160
            ORDER BY order_id, sequence
            """,
            [org_id, order_ids],
        )
        for step in steps:
            queues.setdefault(str(step["order_id"]), []).append(
                {
                    "sequence": int(step["sequence"]),
                    # The step's station kind IS its code — production_steps
                    # has no kind column (kind lives on work_centers).
                    "kind": _cut(step["code"]),
                    "code": _cut(step["code"]),
                    "label": _cut(step["label"]),
                    "status": _cut(step["status"]),
                }
            )
    out: list[dict] = []
    for order in orders:
        queue = queues.get(str(order["id"]), [])
        pending = next(
            (step for step in queue if step["status"] not in ("DONE", "SKIPPED")),
            None,
        )
        out.append(
            {
                "id": str(order["id"]),
                "code": _cut(order["order_code"]),
                "status": _cut(order["status"]),
                "project_code": _cut(order["project_code"]),
                "created_at": str(order["created_at"])[:10],
                "delivery_date": (
                    str(order["delivery_date"])[:10]
                    if order["delivery_date"]
                    else None
                ),
                "delivery_status": _cut(order["delivery_status"]),
                "material_short": bool(order["short"]),
                "steps_done": sum(
                    1 for s in queue if s["status"] in ("DONE", "SKIPPED")
                ),
                "steps_total": len(queue),
                "next_step": pending,
                "blocked_steps": [s for s in queue if s["status"] == "BLOCKED"],
            }
        )
    return {"work_orders": out, "truncated": len(orders) == MAX_LIST}


def _customer_comms(org_id: UUID, refs: dict) -> dict:
    """§08-WG customer communications: every project fact one of the five
    communications may cite — contact, quote state, collected vs pending,
    production/delivery state, recent revisions for change summaries. The
    message the model drafts is still a draft artifact the human reviews;
    nothing sends."""
    project = _project_row(org_id, _ref(refs, "project_id"))
    client = (
        rows(
            "SELECT name, email, phone FROM public.clients "
            "WHERE id=%s AND org_id=%s",
            [project["client_id"], org_id],
        )
        if project.get("client_id")
        else []
    )
    approval = rows(
        "SELECT a.status::text AS status, a.expires_at > now() AS live "
        "FROM public.customer_approvals a "
        "JOIN public.project_versions v "
        "  ON v.id = a.project_version_id AND v.org_id = a.org_id "
        "WHERE a.org_id=%s AND a.project_id=%s AND v.revision_code=%s "
        "ORDER BY a.created_at DESC LIMIT 1",
        [org_id, project["id"], project["current_revision"]],
    )
    payments = rows(
        "SELECT kind, amount, method, reference, created_at "
        "FROM public.project_payments "
        "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL "
        "ORDER BY created_at DESC LIMIT %s",
        [org_id, project["id"], 8],
    )
    orders = rows(
        """
        SELECT o.order_code, o.status::text AS status,
               d.scheduled_date AS delivery_date,
               d.status::text AS delivery_status,
               (SELECT s.label FROM public.production_steps s
                 WHERE s.order_id = o.id AND s.org_id = o.org_id
                   AND s.status NOT IN ('DONE', 'SKIPPED')
                 ORDER BY s.sequence LIMIT 1) AS next_step
        FROM public.orders o
        JOIN public.project_versions v
          ON v.id = o.project_version_id AND v.org_id = o.org_id
        LEFT JOIN public.deliveries d
          ON d.order_id = o.id AND d.org_id = o.org_id
        WHERE o.org_id=%s AND v.project_id=%s
          AND o.order_type='WORKSHOP_OT'
          AND o.status NOT IN ('CANCELLED', 'INSTALLED')
        ORDER BY o.created_at DESC LIMIT %s
        """,
        [org_id, project["id"], 8],
    )
    versions = rows(
        "SELECT revision_code, emitted_at, documentary_complete "
        "FROM public.project_versions WHERE org_id=%s AND project_id=%s "
        "ORDER BY emitted_at DESC LIMIT 3",
        [org_id, project["id"]],
    )
    positions = rows(
        "SELECT count(*) AS total FROM public.project_positions "
        "WHERE org_id=%s AND project_id=%s",
        [org_id, project["id"]],
    )
    # collected vs gross — a payment reminder only makes sense against a
    # real pending balance, so the projection carries both numbers.
    collected = sum(
        Decimal(str(p["amount"])) for p in payments if p["amount"] is not None
    )
    gross = Decimal(str(project["total_price_gross"])) if project["total_price_gross"] is not None else None
    return {
        "project": {
            "id": str(project["id"]),
            "code": _cut(project["code"]),
            "name": _cut(project["name"]),
            "status": _cut(project["status"]),
        },
        "current_revision": _cut(project["current_revision"]),
        "client": (
            {
                "name": _cut(client[0]["name"]),
                "email": _cut(client[0]["email"]),
                "phone": _cut(client[0]["phone"]),
            }
            if client
            else None
        ),
        "approval": (
            {
                "status": _cut(approval[0]["status"]),
                "live": bool(approval[0]["live"]),
            }
            if approval
            else None
        ),
        "totals": {
            "net": _cut(project["total_price_net"]),
            "tax": _cut(project["total_price_tax"]),
            "gross": _cut(project["total_price_gross"]),
            "collected": str(collected),
            "pending": str(gross - collected) if gross is not None else None,
        },
        "positions_total": int(positions[0]["total"]),
        "payments": [
            {
                "kind": _cut(p["kind"]),
                "amount": _cut(p["amount"]),
                "method": _cut(p["method"]),
                "reference": _cut(p["reference"]),
                "created_at": str(p["created_at"])[:10],
            }
            for p in payments
        ],
        "work_orders": [
            {
                "code": _cut(o["order_code"]),
                "status": _cut(o["status"]),
                "next_step": _cut(o["next_step"]),
                "delivery_date": (
                    str(o["delivery_date"])[:10] if o["delivery_date"] else None
                ),
                "delivery_status": _cut(o["delivery_status"]),
            }
            for o in orders
        ],
        "versions": [
            {
                "revision": _cut(v["revision_code"]),
                "emitted_at": str(v["emitted_at"])[:10],
                "documentary_complete": bool(v["documentary_complete"]),
            }
            for v in versions
        ],
    }


def _catalog_compiler(org_id: UUID) -> dict:
    """§08-WD catalog compiler: the org's catalog imports with their article
    candidates — extract→classify→map→compare already ran deterministic
    reconciliation (_reconcile marks conflicts + the existing article each
    collides with, and series gaps land on the import's warnings). What
    remains genuinely human: uncertain/high-impact rows. The compiler
    surfaces exactly that queue, plus every tenant-owned system a confirmed
    article could target. Candidates stay review data — only the confirm
    endpoint writes catalog authority."""
    imports = rows(
        "SELECT id, file_name, status, system_id, candidates, warnings, "
        "result, error_code, created_at "
        "FROM public.catalog_imports "
        "WHERE org_id=%s "
        "ORDER BY created_at DESC LIMIT %s",
        [org_id, 6],
    )
    systems = rows(
        "SELECT id, code, name, material::text AS material, "
        "manufacturer, family "
        "FROM public.profile_systems "
        "WHERE org_id=%s AND is_active "
        "ORDER BY code LIMIT %s",
        [org_id, MAX_LIST],
    )
    budget = 24
    documents = []
    for imp in imports:
        raw = _jsonb(imp["candidates"])
        cands = raw if isinstance(raw, list) else []
        take = cands[: max(budget, 0)]
        budget -= len(take)
        confirmed = {
            str(entry.get("key"))
            for entry in (_jsonb(imp["result"]) or [])
            if isinstance(entry, dict)
        }
        documents.append(
            {
                "id": str(imp["id"]),
                "file_name": _cut(imp["file_name"]),
                "status": _cut(imp["status"]),
                "error_code": _cut(imp["error_code"]),
                "system_id": str(imp["system_id"]) if imp["system_id"] else None,
                "created_at": str(imp["created_at"])[:10],
                "candidates_total": len(cands),
                "confirmed_keys": sorted(confirmed),
                "candidates": [
                    {
                        "key": _cut(c.get("key"), 40),
                        "sku": _cut(c.get("sku")),
                        "name": _cut(c.get("name")),
                        "role": _cut(c.get("role")),
                        "face_width_mm": _cut(c.get("face_width_mm")),
                        "confidence": _cut(c.get("confidence")),
                        "conflict": bool(c.get("conflict")),
                        "existing": [
                            {
                                "id": str(e.get("id")),
                                "role": _cut(e.get("role")),
                                "system_code": _cut(e.get("system_code")),
                            }
                            for e in (c.get("existing") or [])[:3]
                            if isinstance(e, dict)
                        ],
                        "warnings": [
                            _cut(w)
                            for w in (c.get("warnings") or [])[:4]
                            if isinstance(w, str)
                        ],
                    }
                    for c in take
                    if isinstance(c, dict)
                ],
                "warnings": [
                    _cut(w)
                    for w in (_jsonb(imp["warnings"]) or [])[:6]
                    if isinstance(w, str)
                ],
            }
        )
    return {
        "imports": documents,
        "systems": [
            {
                "id": str(s["id"]),
                "code": _cut(s["code"]),
                "name": _cut(s["name"]),
                "material": _cut(s["material"]),
                "manufacturer": _cut(s["manufacturer"]),
                "family": _cut(s["family"]),
            }
            for s in systems
        ],
    }


def _settings(org_id: UUID) -> dict:
    # The admin surface's real questions are "what is configured and what is
    # missing" — project exactly that: team size, white-label presence, and
    # SII readiness (certificate + CAF coverage per DTE type). Everything is
    # already readable under the ambient role, so no grant widening.
    members = rows(
        "SELECT count(*) AS n FROM public.tenancy_memberships"
        " WHERE org_id=%s AND is_active",
        [org_id],
    )
    org = rows(
        "SELECT brand_logo_key IS NOT NULL AS branded"
        " FROM public.tenancy_organizations WHERE id=%s",
        [org_id],
    )
    cert = rows(
        "SELECT count(*) AS n FROM public.sii_certificates"
        " WHERE org_id=%s",
        [org_id],
    )
    cafs = rows(
        "SELECT tipo_dte, folio_desde, folio_hasta, folio_actual"
        " FROM public.sii_cafs WHERE org_id=%s ORDER BY tipo_dte LIMIT %s",
        [org_id, MAX_LIST],
    )
    return {
        "members_active": int(members[0]["n"]) if members else 0,
        "branding_configured": bool(org and org[0]["branded"]),
        "sii_certificates": int(cert[0]["n"]) if cert else 0,
        "caf_pools": [
            {
                "dte_type": str(c["tipo_dte"]),
                "from": str(c["folio_desde"]),
                "to": str(c["folio_hasta"]),
                "current": str(c["folio_actual"]),
            }
            for c in cafs
        ],
    }


_BUILDERS = {
    "dashboard": _dashboard,
    "projects": _projects,
    "project": _project,
    "position": _position,
    "quotation": _quotation,
    "catalog": _catalog,
    "production": _production,
    "work_order": _work_order,
    "clients": _clients,
    "client": _client,
    "purchasing": _purchasing,
    "settings": _settings,
    "morning_brief": _brief,
    "purchase_plan": _purchase_plan,
    "production_plan": _production_plan,
    "quotation_complete": _quotation,
    "project_from_documents": _project_docs,
    "catalog_compiler": _catalog_compiler,
    "customer_comms": _customer_comms,
    "assistant": _dashboard,
    "jobs": _dashboard,
    "onboarding": _dashboard,
}

_REF_BUILDERS = {
    "project",
    "position",
    "quotation",
    "work_order",
    "catalog",
    "client",
    "quotation_complete",
    "project_from_documents",
    "customer_comms",
}


def build_context(org_id: UUID, surface: str, refs: dict | None) -> dict:
    """Surface → bounded typed projection. The client supplies only the
    surface name and identity refs; every value the model sees is queried
    server-side under the caller's RLS context."""
    builder = _BUILDERS.get(surface)
    if builder is None:
        raise _ContextError("ai_surface_unknown")
    refs = dict(refs or {})
    if surface in _REF_BUILDERS:
        context = builder(org_id, refs)
    else:
        context = builder(org_id)
    context["surface"] = surface
    context["organization"] = _organization(org_id)
    context["context_version"] = 1
    return context


__all__ = ["REQUIRED_REFS", "build_context", "_ContextError"]
