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

from ai_gateway import agent, assist as ask_assist
from ai_gateway.context import _ContextError, REQUIRED_REFS
from ai_gateway.providers import ProviderError, provider_for
from authentication.errors import ContractAPIException
from projects import design_assist, service as projects_service

from . import fixtures


# ---------------------------------------------------------------------------
# Proveedor por capacidad — emula service.invoke sin la persistencia.
# ---------------------------------------------------------------------------

_CAPABILITIES = ("design_assist", "agent", "context_assist", "design_alternatives")

# Pin de provider_model por proveedor cuando no hay `AI_GATEWAY_{P}_MODEL` —
# el valor que las migraciones fijan en ai_routes (última: 20261203).
_WIRE_MODEL_PINS = {"MIMO": "primalabs-ai/MiMo-V2.6-Pro-RL"}


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

    def metrics(self) -> dict:
        return {
            "provider_calls": len(self.calls),
            "rounds": len(
                [
                    c
                    for c in self.calls
                    if ":r" in c["operation_key"]
                    or c["capability"] == "design_assist"
                    or c["capability"] == "context_assist"
                ]
            ),
            "latency_ms": sum(c.get("latency_ms", 0) for c in self.calls),
            "tokens_prompt": sum(c.get("tokens_prompt", 0) for c in self.calls),
            "tokens_completion": sum(c.get("tokens_completion", 0) for c in self.calls),
            "provider_errors": [c["error"] for c in self.calls if "error" in c],
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
            }
        elif via == "agent":
            surface = case["surface"]
            with (
                patch.object(agent, "gateway", SimpleNamespace(invoke=broker.invoke)),
                patch.object(agent, "build_context", fake_context),
                patch.object(design_assist, "_catalog", fake_catalog),
                patch.object(projects_service, "position_row", _position_row_lookup(given)),
                patch.object(agent, "_batch_positions", _batch_positions_lookup(given)),
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
                if result.get("questions")
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
        **broker.metrics(),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    record["given"] = {"product": product_json, "positions": len(given.get("positions") or [])}
    return record
