"""IA2 §2 — herramientas del motor que el agente invoca como pasos
{"kind":"tool","name":...,"args":{...}}: cada salida es un número que el
modelo puede citar sin inventarlo (el grounding ya admite números que el
contexto u observaciones mostraron, así que la respuesta queda citables).

Las herramientas leen proyecciones del servidor — BOM persistido,
reglas de precio, catálogo de la serie — nunca llaman al proveedor ni
escriben nada. `simulate_ops` reusa el validador del asistente de diseño
para que una propuesta se pruebe antes de presentarse.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from ai_gateway.context import _cut, _jsonb, _system_opening_options
from pricing.repository import PricingRepository, rows
from projects import design_assist, service as projects_service

# Las líneas del BOM que el agente puede citar — mismas proyecciones que
# la vista de posición ya expone al canvas.

MAX_LIST = 24

# El paso declara una de estas herramientas; el nombre es el contrato
# transcript↔UI (la tarjeta muestra la herramienta real que corrió).
TOOL_NAMES = (
    "calculate_position",
    "validate_position",
    "price_position",
    "price_project",
    "explain_price_delta",
    "list_catalog_options",
    "get_blockers",
    "simulate_ops",
)


def _position(org_id: UUID, position_id: str) -> dict | None:
    found = rows(
        "SELECT id, project_id, position_index, location_tag, typology, "
        "quantity, width_mm, height_mm, system_id, color_interior, "
        "color_exterior, parametric_tree, bom_snapshot "
        "FROM public.project_positions WHERE id=%s AND org_id=%s",
        [position_id, org_id],
    )
    return found[0] if found else None


def _bom(position: dict) -> dict:
    stored = _jsonb(position.get("bom_snapshot"))
    return stored if isinstance(stored, dict) else {}


def _issues(bom: dict) -> list[dict]:
    """Los bloqueos/avises que el motor ya emitió — la misma lista que la
    validación del guardado produjo (NUNCA re-derivada por texto)."""
    items = []
    for issue in (bom.get("issues") or [])[:MAX_LIST]:
        if isinstance(issue, dict):
            items.append(
                {
                    "code": _cut(str(issue.get("code") or ""), 80),
                    "severity": _cut(str(issue.get("severity") or ""), 20),
                    "detail": _cut(str(issue.get("detail") or ""), 240),
                    "bay_id": _cut(str(issue.get("bay_id") or ""), 60)
                    if issue.get("bay_id")
                    else None,
                }
            )
        elif isinstance(issue, str):
            items.append({"code": _cut(issue, 80), "severity": None, "detail": None})
    return items


def _leaf_weights(bom: dict) -> list[dict]:
    return [
        {
            "bay_id": _cut(str(item.get("bay_id") or ""), 60),
            "leaf_id": _cut(str(item.get("leaf_id") or ""), 60),
            "total_weight_kg": _cut(str(item.get("total_weight_kg") or ""), 20),
            "weight_unknown_reasons": item.get("weight_unknown_reasons") or [],
        }
        for item in (bom.get("leaf_weights") or [])[:MAX_LIST]
        if isinstance(item, dict)
    ]


def calculate_position(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """El BOM persistido de la posición — pesos por hoja, cortes y vidrios
    que el motor ya calculó al guardar (fuente citable de e09)."""
    position = _position(org_id, str(args.get("position_id") or ""))
    if position is None:
        return {"ok": False, "error": "position_not_found"}
    bom = _bom(position)
    if not bom:
        return {
            "ok": True,
            "position_id": str(position["id"]),
            "index": int(position["position_index"]),
            "has_bom": False,
            "detail": "sin cálculo persistido — la posición aún no se ha guardado con diseño",
        }
    return {
        "ok": True,
        "position_id": str(position["id"]),
        "index": int(position["position_index"]),
        "has_bom": True,
        "nominal_width_mm": _cut(str(position["width_mm"]), 20),
        "nominal_height_mm": _cut(str(position["height_mm"]), 20),
        "leaf_weights": _leaf_weights(bom),
        "profile_cuts": int(len(bom.get("profile_cuts") or [])),
        "glasses": int(len(bom.get("glasses") or [])),
        "panels": int(len(bom.get("panels") or [])),
        "hardware_items": int(len(bom.get("hardware_items") or [])),
        "issues": _issues(bom),
    }


def validate_position(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """La lista exacta de issues que el motor reporta para la posición —
    "por qué no puedo guardar" se responde con esto, no con memoria."""
    position = _position(org_id, str(args.get("position_id") or ""))
    if position is None:
        return {"ok": False, "error": "position_not_found"}
    bom = _bom(position)
    issues = _issues(bom)
    blockers = [
        issue
        for issue in issues
        if issue.get("severity") in ("ERROR", "BLOCKER") or "error" in str(
            issue.get("severity") or ""
        ).lower()
    ]
    return {
        "ok": True,
        "position_id": str(position["id"]),
        "index": int(position["position_index"]),
        "valid": not blockers,
        "issues": issues,
        "blockers": blockers,
    }


def _rules_and_repo(org_id: UUID) -> tuple[dict, Any, str]:
    """La autoridad de precio como la usa la vista de precios: reglas del
    tenant convertidas a la moneda declarada de la organización — la
    misma construcción que design_batch_preview."""
    rules_row = rows("SELECT * FROM public.pricing_rules WHERE org_id=%s", [org_id])
    if not rules_row:
        return {}, None, ""
    organization = rows(
        "SELECT currency FROM public.tenancy_organizations WHERE id=%s", [org_id]
    )[0]
    repo = PricingRepository(org_id, date.today(), organization["currency"], None)
    rules = {
        **rules_row[0],
        "labor_rate_per_m2": repo.convert(
            rules_row[0]["labor_rate_per_m2"], organization["currency"]
        ),
        "installation_rate_per_m2": repo.convert(
            rules_row[0]["installation_rate_per_m2"], organization["currency"]
        ),
    }
    return rules, repo, organization["currency"]


def price_position(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """Costo unitario + línea de la posición con las reglas vigentes —
    el MISMO position_cost que la cotización usa (j04)."""
    position = _position(org_id, str(args.get("position_id") or ""))
    if position is None:
        return {"ok": False, "error": "position_not_found"}
    rules, repo, currency = _rules_and_repo(org_id)
    if not rules:
        return {"ok": False, "error": "pricing_rules_not_found"}
    from pricing.service import position_cost

    cost, _area, _result, formation = position_cost(repo, position, rules)
    quantity = int(position["quantity"] or 1)
    return {
        "ok": True,
        "position_id": str(position["id"]),
        "index": int(position["position_index"]),
        "currency": currency,
        "unit_cost": str(cost.quantize(Decimal("0.01"))),
        "quantity": quantity,
        "line_cost": str((cost * quantity).quantize(Decimal("0.01"))),
        "composition": [
            {
                "kind": _cut(str(line.get("kind") or ""), 20),
                "sku": _cut(str(line.get("sku") or ""), 60),
                "quantity": _cut(str(line.get("quantity") or ""), 20),
                "unit": _cut(str(line.get("unit") or ""), 10),
                "cost": _cut(str(line.get("cost") or ""), 20),
            }
            for line in (formation.get("composition") or [])[:MAX_LIST]
            if isinstance(line, dict)
        ],
        "materials_cost": formation.get("materials_cost"),
        "area_m2": formation.get("area_m2"),
    }


def price_project(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """Costo por posición de TODO el proyecto — j04 ("la posición más cara")
    se responde ordenando esta lista, nunca adivinando."""
    project_id = str(args.get("project_id") or "")
    positions = rows(
        "SELECT id, project_id, position_index, location_tag, typology, "
        "quantity, width_mm, height_mm, system_id, color_interior, "
        "color_exterior, parametric_tree, bom_snapshot "
        "FROM public.project_positions WHERE org_id=%s AND project_id=%s "
        "ORDER BY position_index",
        [org_id, project_id],
    )
    if not positions:
        return {"ok": False, "error": "project_positions_empty"}
    rules, repo, currency = _rules_and_repo(org_id)
    if not rules:
        return {"ok": False, "error": "pricing_rules_not_found"}
    from pricing.service import position_cost

    items = []
    total = Decimal("0")
    for position in positions[:MAX_LIST]:
        try:
            cost, _area, _result, _formation = position_cost(repo, position, rules)
        except Exception:  # noqa: BLE001 — una posición incalculable se reporta, no aborta
            items.append(
                {
                    "position_id": str(position["id"]),
                    "index": int(position["position_index"]),
                    "ok": False,
                    "error": "position_cost_failed",
                }
            )
            continue
        quantity = int(position["quantity"] or 1)
        line = cost * quantity
        total += line
        items.append(
            {
                "position_id": str(position["id"]),
                "index": int(position["position_index"]),
                "location": _cut(position["location_tag"]),
                "ok": True,
                "unit_cost": str(cost.quantize(Decimal("0.01"))),
                "quantity": quantity,
                "line_cost": str(line.quantize(Decimal("0.01"))),
            }
        )
    return {
        "ok": True,
        "project_id": project_id,
        "currency": currency,
        "positions": items,
        "total_cost": str(total.quantize(Decimal("0.01"))),
        "truncated": len(positions) > MAX_LIST,
    }


def explain_price_delta(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """Δ entre la última autoridad de precio APLICADA y el costo actual —
    "por qué cambió" se explica con las líneas que el motor compone, no
    con una narrativa."""
    project_id = str(args.get("project_id") or "")
    applied = rows(
        "SELECT id, result FROM public.pricing_operations "
        "WHERE org_id=%s AND project_id=%s AND state='APPLIED' "
        "ORDER BY approved_at DESC NULLS LAST, id DESC LIMIT 1",
        [org_id, project_id],
    )
    current = price_project(org_id, {"project_id": project_id}, observed)
    if not current.get("ok"):
        return current
    applied_lines: dict[str, Decimal] = {}
    if applied:
        result = _jsonb(applied[0].get("result"))
        for line in (result or {}).get("cost_lines") or []:
            if isinstance(line, (list, tuple)) and len(line) == 2:
                try:
                    applied_lines[str(line[0])] = Decimal(str(line[1]))
                except Exception:  # noqa: BLE001
                    continue
    deltas = []
    for item in current.get("positions") or []:
        if not item.get("ok"):
            continue
        before = applied_lines.get(str(item["index"]))
        after = Decimal(str(item["line_cost"]))
        deltas.append(
            {
                "position_id": item["position_id"],
                "index": item["index"],
                "line_cost_applied": str(before) if before is not None else None,
                "line_cost_current": str(after.quantize(Decimal("0.01"))),
                "delta": (
                    str((after - before).quantize(Decimal("0.01")))
                    if before is not None
                    else None
                ),
            }
        )
    return {
        "ok": True,
        "project_id": project_id,
        "currency": current.get("currency"),
        "has_applied": bool(applied),
        "positions": deltas,
    }


def list_catalog_options(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """Opciones reales del catálogo — aperturas declaradas, vidrios,
    acabados, series elegibles — para que la IA elija entre lo que EXISTE
    (nunca un SKU inventado)."""
    system_id = str(args.get("system_id") or "")
    kind = str(args.get("kind") or "")
    if system_id:
        system_rows = rows(
            "SELECT id, code, system_family FROM public.profile_systems "
            "WHERE id=%s AND (org_id=%s OR org_id IS NULL)",
            [system_id, org_id],
        )
        if not system_rows:
            return {"ok": False, "error": "system_not_found"}
        system = system_rows[0]
        catalog = design_assist._catalog(UUID(system_id), org_id)
        return {
            "ok": True,
            "system_id": system_id,
            "openings": _system_opening_options(
                org_id,
                {
                    "system_uuid": system["id"],
                    "system_family": system["system_family"],
                },
            )[:MAX_LIST]
            if kind in ("", "openings")
            else None,
            "glass_skus": sorted(catalog["glass_skus"])[:MAX_LIST]
            if kind in ("", "glass")
            else None,
            "glass_recipes": {
                sku: recipe
                for sku, recipe in sorted((catalog.get("glass_recipes") or {}).items())[:MAX_LIST]
            }
            if kind in ("", "glass")
            else None,
            "panel_skus": sorted(catalog["panel_skus"])[:MAX_LIST]
            if kind in ("", "panels")
            else None,
            "finishes": sorted(catalog["finishes"])
            if kind in ("", "finishes")
            else None,
            "mullions": {
                axis: {"sku": spec["sku"], "face_mm": str(spec["face_mm"])}
                for axis, spec in catalog["mullions"].items()
            }
            if kind in ("", "mullions")
            else None,
        }
    # Sin sistema: las series elegibles del tenant.
    systems = rows(
        "SELECT id, code, name, system_family, material FROM public.profile_systems "
        "WHERE (org_id=%s OR org_id IS NULL) AND is_active ORDER BY code LIMIT %s",
        [org_id, MAX_LIST],
    )
    return {
        "ok": True,
        "systems": [
            {
                "id": str(item["id"]),
                "code": _cut(item["code"]),
                "name": _cut(item["name"]),
                "system_family": _cut(item["system_family"]),
                "material": _cut(item["material"]),
            }
            for item in systems
        ],
    }


def get_blockers(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """Bloqueos que impiden avanzar: issues del motor en una posición, o la
    revisión/emisión del proyecto cuando la meta es emitir (j07)."""
    position_id = str(args.get("position_id") or "")
    if position_id:
        return validate_position(org_id, {"position_id": position_id}, observed)
    project_id = str(args.get("project_id") or "")
    if not project_id:
        return {"ok": False, "error": "ref_required"}
    project = projects_service.project_row(org_id, project_id)
    sealed = rows(
        "SELECT revision_code, documentary_complete, production_allowed "
        "FROM public.project_versions WHERE org_id=%s AND project_id=%s "
        "ORDER BY emitted_at DESC LIMIT 1",
        [org_id, project_id],
    )
    positions = rows(
        "SELECT id, position_index, bom_snapshot FROM public.project_positions "
        "WHERE org_id=%s AND project_id=%s ORDER BY position_index",
        [org_id, project_id],
    )
    position_issues = []
    for position in positions[:MAX_LIST]:
        issues = _issues(_bom(position))
        if issues:
            position_issues.append(
                {
                    "position_index": int(position["position_index"]),
                    "issues": issues[:5],
                }
            )
    applied = rows(
        "SELECT id FROM public.pricing_operations WHERE org_id=%s "
        "AND project_id=%s AND state='APPLIED' "
        "AND COALESCE(revision_code,'REV-A')=%s LIMIT 1",
        [org_id, project_id, project["current_revision"]],
    )
    missing = []
    if not positions:
        missing.append("sin_posiciones")
    if not applied:
        missing.append("precio_no_aplicado")
    if not sealed:
        missing.append("revision_no_emitida")
    elif not sealed[0]["documentary_complete"]:
        missing.append("documental_incompleta")
    elif not sealed[0]["production_allowed"]:
        missing.append("produccion_no_habilitada")
    return {
        "ok": True,
        "project_id": project_id,
        "status": project["status"],
        "current_revision": project["current_revision"],
        "missing": missing,
        "position_issues": position_issues,
    }


def simulate_ops(org_id: UUID, args: dict, observed: frozenset[str]) -> dict:
    """La propuesta aplicada en arena — mismo validador del asistente:
    ops aceptadas, rechazadas y la proyección estructural resultante.
    Nunca escribe; es la forma honesta de probar una edición antes de
    presentarla (IA2 §4)."""
    position_id = str(args.get("position_id") or "")
    ops = args.get("ops")
    if not isinstance(ops, list) or not ops:
        return {"ok": False, "error": "ops_required"}
    position = _position(org_id, position_id)
    if position is None:
        return {"ok": False, "error": "position_not_found"}
    summary = design_assist._summary(
        _jsonb(position.get("parametric_tree")),
        width_mm=position.get("width_mm"),
        height_mm=position.get("height_mm"),
    )
    if summary is None:
        return {"ok": False, "error": "unsupported_product"}
    try:
        catalog = design_assist._catalog(UUID(str(position["system_id"])), org_id)
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "catalog_unavailable"}
    citable = design_assist._citable_values(
        set(), design_assist._context_numbers(summary, catalog)
    )
    accepted, rejected, simulation = design_assist._validate_ops(
        ops, summary, catalog, citable
    )
    return {
        "ok": True,
        "position_id": position_id,
        "accepted": accepted,
        "rejected": rejected,
        "simulation": simulation,
    }


TOOL_IMPLS = {
    "calculate_position": calculate_position,
    "validate_position": validate_position,
    "price_position": price_position,
    "price_project": price_project,
    "explain_price_delta": explain_price_delta,
    "list_catalog_options": list_catalog_options,
    "get_blockers": get_blockers,
    "simulate_ops": simulate_ops,
}
