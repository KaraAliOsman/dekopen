"""Arnés de ejecución: corre un caso YAML por la MISMA ruta que usa la UI.

- via `design_assist` → `projects.design_assist.assist` (el endpoint del
  panel del editor, POST /positions/{id}/design-assist/).
- via `agent` → `ai_gateway.agent._act` (el job detrás de POST /ai/agent/;
  se omite la persistencia del job, que es contexto, no conducta del modelo).
- via `ask` → `ai_gateway.assist.ask` (el dock Preguntar, POST /ai/ask/).

Lo único simulado son los bordes de I/O que dependen de Postgres: la
invocación al proveedor (reemplazada por una que respeta la misma firma,
ruta, system prompt y opciones), la carga de contexto (proyecciones fixture
idénticas a las que `build_context` produce), la fila de la posición, el
catálogo del sistema y el lote de posiciones del batch. Los prompts, el
validador de ops, el grounding, las consultas multi-ronda y la máquina de
estados corren sobre el código real del producto.
"""

from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID

from decimal import Decimal

from ai_gateway import agent, assist as ask_assist
from ai_gateway import tools as agent_tools
from ai_gateway.context import _ContextError, REQUIRED_REFS
from ai_gateway.providers import ProviderError, provider_for
from authentication.errors import ContractAPIException
from pricing import service as pricing_service
from projects import design_assist, service as projects_service

from . import fixtures


# ---------------------------------------------------------------------------
# Proveedor por capacidad — emula service.invoke sin la persistencia.
# ---------------------------------------------------------------------------

_CAPABILITIES = ("design_assist", "agent", "context_assist", "design_alternatives")

# Pin de provider_model por proveedor cuando no hay `AI_GATEWAY_{P}_MODEL` —
# el valor que las migraciones fijan en ai_routes (vigente:
# 20261230003000_ia2_mimo_wire_model):
# el endpoint de la credencial sirve `mimo-v2.6-pro`; el pin primalabs que
# reemplazó responde 400 en este endpoint (causa raíz IA1-1).
_WIRE_MODEL_PINS = {"MIMO": "mimo-v2.6-pro"}


def configured_provider_names() -> list[str]:
    """Proveedores reales con credencial completa en el entorno
    (`AI_GATEWAY_{P}_API_KEY` + `AI_GATEWAY_{P}_BASE_URL`)."""
    found = []
    for key in os.environ:
        if key.startswith("AI_GATEWAY_") and key.endswith("_API_KEY"):
            name = key[len("AI_GATEWAY_") : -len("_API_KEY")]
            if name == "MOCK":
                continue
            if os.environ.get(f"AI_GATEWAY_{name}_BASE_URL"):
                found.append(name)
    return sorted(set(found))


class ProviderBroker:
    """Resuelve rutas e invoca al proveedor seleccionado una vez por llamada,
    registrando latencia/tokens/rondas — la métrica que el informe reporta."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.calls: list[dict] = []
        if provider != "MOCK" and provider not in configured_provider_names():
            raise ProviderError("ai_provider_unavailable")

    def route_for(self, capability: str) -> dict:
        if self.provider == "MOCK":
            provider = "MOCK"
            model = "mock"
        else:
            provider = self.provider
            # Pin de ai_routes (migración 20261203 primalabs_mimo_pin): el
            # modelo wire real, no un placeholder — el sobre del proveedor
            # exige route["provider_model"].
            model = os.environ.get(f"AI_GATEWAY_{provider}_MODEL") or _WIRE_MODEL_PINS.get(
                provider, "configured"
            )
        return {
            "id": "eval-route",
            "capability": capability,
            "provider": provider,
            "provider_model": model,
            "public_name": f"{provider} (eval)",
            "prompt_version": 1,
            "credits_cost": 0,
        }

    def invoke(
        self,
        *,
        org_id: UUID,
        user_id: UUID,
        capability: str,
        operation_key: str,
        input_payload: dict,
        tool_name: str | None = None,
        provider_options: dict | None = None,
        document_path: str | None = None,
    ) -> dict:
        """Misma firma que `service.invoke`: resuelve la ruta, llama al
        proveedor real y devuelve el sobre que las rutas esperan."""
        route = self.route_for(capability)
        provider = provider_for(route)
        call = {"capability": capability, "operation_key": operation_key}
        try:
            result = provider.invoke(
                route=route,
                capability=capability,
                input_payload=input_payload,
                provider_options=provider_options,
                document_path=document_path,
                operation_key=f"{org_id}:{operation_key}",
            )
        except ProviderError as error:
            call["error"] = error.code
            self.calls.append(call)
            raise
        call.update(
            {
                "tokens_prompt": int(result["tokens_prompt"]),
                "tokens_completion": int(result["tokens_completion"]),
                "latency_ms": int(result["latency_ms"]),
            }
        )
        self.calls.append(call)
        return {
            "audit_id": f"eval-{len(self.calls)}",
            "capability": capability,
            "model": result.get("model") or route["public_name"],
            "output": result["output"],
            "tokens_prompt": int(result["tokens_prompt"]),
            "tokens_completion": int(result["tokens_completion"]),
            "latency_ms": int(result["latency_ms"]),
            "credits_debited": 0,
        }

    def metrics(self, start: int = 0) -> dict:
        """Métricas del tramo `start:` de self.calls — `run_case` captura el
        índice al empezar para que cada caso reporte SUS llamadas, no las
        acumuladas de la suite."""
        calls = self.calls[start:]
        return {
            "provider_calls": len(calls),
            "rounds": len(
                [
                    c
                    for c in calls
                    if ":r" in c["operation_key"]
                    or c["capability"] == "design_assist"
                    or c["capability"] == "context_assist"
                ]
            ),
            "latency_ms": sum(c.get("latency_ms", 0) for c in calls),
            "tokens_prompt": sum(c.get("tokens_prompt", 0) for c in calls),
            "tokens_completion": sum(c.get("tokens_completion", 0) for c in calls),
            "provider_errors": [c["error"] for c in calls if "error" in c],
        }


# ---------------------------------------------------------------------------
# Parches del borde de I/O — los únicos sustitutos de Postgres.
# ---------------------------------------------------------------------------


def _context_lookup(given: dict):
    contexts: dict[str, list[dict]] = {
        surface: list(entries) for surface, entries in (given.get("contexts") or {}).items()
    }

    def fake_build_context(org_id: UUID, surface: str, refs: dict | None) -> dict:
        refs = dict(refs or {})
        entries = contexts.get(surface)
        if entries is None:
            raise _ContextError("ai_surface_unknown")
        missing = [name for name in REQUIRED_REFS.get(surface, ()) if name not in refs]
        if missing and all(entry["refs"] for entry in entries):
            raise _ContextError("ai_context_ref_invalid")
        for entry in entries:
            wanted = entry.get("refs") or {}
            if all(str(refs.get(key)) == str(value) for key, value in wanted.items()):
                return json.loads(json.dumps(entry["context"], default=str))
        # Una referencia que ninguna entrada declara no existe para el llamante.
        if entries and all(not entry.get("refs") for entry in entries):
            return json.loads(json.dumps(entries[0]["context"], default=str))
        raise _ContextError("ai_context_not_found")

    return fake_build_context


def _catalog_lookup(given: dict):
    def fake_catalog(system_id: UUID, org_id: UUID) -> dict | None:
        catalog = fixtures.catalog_for(system_id)
        return dict(catalog) if catalog else None

    return fake_catalog


def _position_row_lookup(given: dict):
    def fake_position_row(org_id: UUID, position_id: Any, lock: bool = False) -> dict:
        position = given.get("position")
        if position is None or str(position.get("id")) != str(position_id):
            raise _ContextError("ai_context_not_found")
        return dict(position)

    return fake_position_row


def _tools_rows(given: dict):
    """Réplica de las consultas SQL que `ai_gateway.tools` hace (§2) — las
    mismas filas fixture que las proyecciones de contexto, resueltas por
    tabla y por el primer parámetro (id de posición o project_id)."""

    def fake_rows(sql: str, params: list | tuple | None = None):
        params = list(params or [])
        if "public.pricing_rules" in sql:
            rules = given.get("pricing_rules")
            return [dict(rules)] if rules else []
        if "tenancy_organizations" in sql:
            currency = (given.get("pricing_rules") or {}).get("currency", "CLP")
            return [{"currency": currency}]
        if "public.project_positions" in sql:
            rows_ = [dict(row) for row in given.get("positions") or []]
            if given.get("position"):
                rows_.append(dict(given["position"]))
            if "WHERE id=%s" in sql and params:
                return [row for row in rows_ if str(row.get("id")) == str(params[0])]
            if "project_id=%s" in sql and len(params) >= 2:
                return [
                    row
                    for row in rows_
                    if str(row.get("project_id") or "") == str(params[1])
                ]
            return rows_
        if "public.profile_systems" in sql:
            systems = given.get("systems") or []
            if "WHERE id=%s" in sql and params:
                return [row for row in systems if str(row.get("id")) == str(params[0])]
            return [dict(row) for row in systems]
        if "public.project_versions" in sql:
            return [dict(row) for row in given.get("versions") or []]
        if "public.pricing_operations" in sql:
            return [dict(row) for row in given.get("pricing_operations") or []]
        return []

    return fake_rows


def _project_row_lookup(given: dict):
    """projects_service.project_row para get_blockers — status y revisión
    del contexto fixture del proyecto."""

    def fake_project_row(org_id: UUID, project_id: Any) -> dict:
        entries = (given.get("contexts") or {}).get("project") or []
        context = (entries[0].get("context") or {}) if entries else {}
        if not context:
            raise _ContextError("ai_context_not_found")
        return {
            "id": str(project_id),
            "status": context.get("status"),
            "current_revision": context.get("current_revision"),
        }

    return fake_project_row


def _fake_opening_options(org_id: UUID, position: dict) -> list[dict]:
    """`tools._system_opening_options` sobre el fixture: las mismas opciones
    D03 que el catálogo fixture declara, sin tocar Postgres."""
    catalog = fixtures.catalog_for(position.get("system_uuid"))
    return list(catalog["openings"]) if catalog else []


def _fake_position_cost(repo: Any, position: dict, rules: dict):
    """Réplica determinista de `pricing.service.position_cost` — el motor
    real exige Postgres+RLS; la vara del arnés sólo necesita un costo
    monótono en área/hojas para que «la más cara» sea verificable."""
    width = Decimal(str(position.get("width_mm") or "0"))
    height = Decimal(str(position.get("height_mm") or "0"))
    area = (width * height / Decimal("1000000")).quantize(Decimal("0.0001"))
    leaves = max(1, len(fixtures._bay_ids(position.get("parametric_tree"))))
    cost = Decimal("120000") * area + Decimal("45000") * (leaves - 1) + Decimal("60000")
    formation = {
        "composition": [
            {
                "kind": "profile",
                "sku": "MARCO-60",
                "quantity": str(area),
                "unit": "m2",
                "cost": str(cost.quantize(Decimal("0.01"))),
            }
        ],
        "materials_cost": str(cost.quantize(Decimal("0.01"))),
        "area_m2": str(area),
    }
    return cost, area, None, formation


def _batch_positions_lookup(given: dict):
    """Réplica de agent._batch_positions sobre las filas fixture — mismo
    contrato de errores y límites."""
    from ai_gateway.agent import MAX_BATCH_POSITIONS, _PATH_UUID

    def fake_batch_positions(
        org_id: UUID, project_id: str, targets: dict, observed_refs: frozenset[str]
    ) -> tuple[list[dict], str | None]:
        position_ids = targets.get("position_ids")
        if position_ids is not None:
            if not isinstance(position_ids, list) or not position_ids:
                return [], "batch_targets_invalid"
            seen: list[str] = []
            for value in position_ids:
                if (
                    not isinstance(value, str)
                    or not _PATH_UUID.fullmatch(value)
                    or value not in observed_refs
                ):
                    return [], "unobserved_ref"
                if value not in seen:
                    seen.append(value)
            if len(seen) > MAX_BATCH_POSITIONS:
                return [], "batch_too_large"
        positions = [dict(row) for row in given.get("positions") or []]
        if position_ids is not None:
            positions = [row for row in positions if row["id"] in set(position_ids)]
        typology = targets.get("typology")
        if typology is not None and (not isinstance(typology, str) or not typology.strip()):
            return [], "batch_targets_invalid"
        wanted = typology.strip().upper() if isinstance(typology, str) else None
        matched = [
            row
            for row in positions
            if wanted in (None, "ALL") or (row["typology"] or "").upper() == wanted
        ]
        return matched[:MAX_BATCH_POSITIONS], None

    return fake_batch_positions


# ---------------------------------------------------------------------------
# Ejecución de un caso
# ---------------------------------------------------------------------------


def _error_dict(error: Exception) -> dict:
    if isinstance(error, ProviderError):
        return {"code": error.code, "kind": "provider"}
    if isinstance(error, ContractAPIException):
        return {
            "code": error.contract_code,
            "status": error.status_code,
            "detail": str(error.public_detail)[:300],
            "kind": "contract",
        }
    return {"code": type(error).__name__, "detail": str(error)[:300], "kind": "internal"}


def run_case(case: dict, *, broker: ProviderBroker) -> dict:
    """Ejecuta el caso por su ruta y devuelve el registro de resultado
    (outcome completo + métricas). No evalúa — eso es `expect.evaluate`."""
    call_start = len(broker.calls)
    given = fixtures.given(
        case.get("fixture") or "editor",
        product_variant=case.get("product_variant") or "vacia",
    )
    via = case["via"]
    started = time.monotonic()
    record: dict[str, Any] = {
        "id": case["id"],
        "via": via,
        "surface": case.get("surface"),
        "outcome": {},
        "error": None,
        "sandbox": {},
    }
    org_id = fixtures.ORG_ID
    user_id = fixtures.USER_ID
    product_json = given.get("product")
    wire = fixtures.wire_product(product_json) if product_json else None
    refs = case.get("refs") or {}
    fake_context = _context_lookup(given)
    fake_catalog = _catalog_lookup(given)

    try:
        if via == "design_assist":
            with (
                patch.object(design_assist, "gateway", SimpleNamespace(invoke=broker.invoke)),
                patch.object(design_assist, "_catalog", fake_catalog),
            ):
                result = design_assist.assist(
                    org_id=org_id,
                    user_id=user_id,
                    position=given["position"],
                    product=wire,
                    prompt=case["prompt"],
                    operation_key=f"eval:{case['id']}",
                    system_id=UUID(str(given["position"]["system_id"])),
                )
            record["outcome"] = {
                "ops_proposed": (result.get("ops") or []) + (result.get("rejected") or []),
                "ops_accepted": result.get("ops") or [],
                "rejected": result.get("rejected") or [],
                "notes": result.get("notes"),
                "model": result.get("model"),
                "clarify": result.get("clarify"),
                "simulation": result.get("simulation"),
            }
        elif via == "agent":
            surface = case["surface"]
            with (
                patch.object(agent, "gateway", SimpleNamespace(invoke=broker.invoke)),
                patch.object(agent, "build_context", fake_context),
                patch.object(design_assist, "_catalog", fake_catalog),
                patch.object(projects_service, "position_row", _position_row_lookup(given)),
                patch.object(projects_service, "project_row", _project_row_lookup(given)),
                patch.object(agent, "_batch_positions", _batch_positions_lookup(given)),
                # IA2 §2 — el borde de I/O de las herramientas del motor:
                # mismas filas fixture, motor de precio determinista.
                patch.object(agent_tools, "rows", _tools_rows(given)),
                patch.object(
                    agent_tools, "_system_opening_options", _fake_opening_options
                ),
                patch.object(pricing_service, "position_cost", _fake_position_cost),
            ):
                result = agent._act(
                    org_id=org_id,
                    user_id=user_id,
                    surface=surface,
                    refs=refs,
                    goal=case["prompt"],
                    product=wire,
                    history=[],
                    operation_key=f"eval:{case['id']}",
                )
            pending = any(
                step.get("kind") in ("prepare", "ops", "batch_ops")
                for step in result.get("steps") or []
            )
            state = (
                "WAITING_FOR_USER"
                if result.get("questions") or result.get("clarify")
                else "WAITING_FOR_APPROVAL"
                if pending
                else "SUCCEEDED"
            )
            record["outcome"] = {
                **result,
                "state": state,
                "ops_proposed": [
                    op
                    for step in result.get("steps") or []
                    if step.get("kind") == "ops"
                    for op in step.get("ops") or []
                ]
                + [
                    op
                    for step in result.get("steps") or []
                    if step.get("kind") == "batch_ops"
                    for item in step.get("items") or []
                    for op in item.get("ops") or []
                ],
                "ops_accepted": [
                    op
                    for step in result.get("steps") or []
                    if step.get("kind") == "ops"
                    for op in step.get("ops") or []
                ],
                "dropped_ungrounded": sum(
                    1 for w in result.get("warnings") or [] if "descartad" in str(w)
                ),
            }
        elif via == "ask":
            surface = case["surface"]
            with (
                patch.object(ask_assist, "gateway", SimpleNamespace(invoke=broker.invoke)),
                patch.object(ask_assist, "build_context", fake_context),
            ):
                result = ask_assist.ask(
                    org_id=org_id,
                    user_id=user_id,
                    surface=surface,
                    refs=refs,
                    question=case["prompt"],
                    operation_key=f"eval:{case['id']}",
                )
            record["outcome"] = {
                **result,
                "reply": result.get("answer"),
                "ops_proposed": [],
                "ops_accepted": [],
            }
        else:
            raise ValueError(f"via desconocida: {via}")
    except (ProviderError, ContractAPIException) as error:
        record["error"] = _error_dict(error)
    except Exception as error:  # noqa: BLE001 — un error interno también es evidencia
        record["error"] = _error_dict(error)

    record["metrics"] = {
        **broker.metrics(call_start),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    record["given"] = {"product": product_json, "positions": len(given.get("positions") or [])}
    return record
