"""§IA3 — owner-facing provider status, settings and usage.

The surfaces this feeds: Settings › Inteligencia artificial (OWNER) and the
"Modo de prueba" badge. ai_routes is sealed platform config — reads run under
ai_backend so member roles can never join provider internals; the endpoint
exposes only public_name plus the effective model label the route declares.
The API key is never read, logged or serialized — "configured" is a boolean
derived from env presence.
"""

from __future__ import annotations

import os
import time
from uuid import UUID, uuid4

from django.db import connection

from ai_gateway import invocations
from ai_gateway.jobs import _ai_backend
from ai_gateway.providers import ProviderError, provider_for
from pricing.repository import rows

# The capability set the product exposes (matches ai_routes seed rows).
_VISIBLE_CAPABILITIES = (
    "design_assist",
    "design_alternatives",
    "context_assist",
    "agent",
    "catalog_compile",
    "nlp_command",
    "discount_suggest",
)


def _env_flag(name: str) -> str:
    return os.environ.get(name, "").lower()


def provider_mode(provider: str) -> str:
    """'live' | 'test' | 'unconfigured' for one provider id — env presence
    only, never a value."""
    name = str(provider).upper()
    if name == "MOCK":
        return "test" if _mock_serving() else "unconfigured"
    configured = bool(
        os.environ.get(f"AI_GATEWAY_{name}_API_KEY", "").strip()
        and os.environ.get(f"AI_GATEWAY_{name}_BASE_URL", "").strip()
    )
    return "live" if configured else "unconfigured"


def _mock_serving() -> bool:
    from ai_gateway.providers import _mock_enabled

    return _mock_enabled()


def _routes() -> list[dict]:
    """Enabled capability routes — sealed platform config, backend read."""
    if connection.vendor != "postgresql":
        return []
    with _ai_backend():
        return rows(
            "SELECT capability, public_name, provider, provider_model,"
            " credits_cost, timeout_s, retry_max, tools_enabled, enabled"
            " FROM public.ai_routes ORDER BY capability",
            [],
        )


def member_status() -> dict:
    """The member-facing mode read — the "Modo de prueba" badge needs only
    the serving mode. Provider/model stay sealed: members see `mode` and
    `mock`, never the route internals."""
    status = provider_status()
    return {
        "mode": status["mode"],
        "mock": status["mode"] == "test"
        or any(
            item["provider"] == "MOCK" and item["enabled"]
            for item in status["capabilities"]
        ),
    }


def provider_status() -> dict:
    """Full status for the owner — mode plus the per-capability map. Model
    names are the route's provider_model (ops-facing label), not the sealed
    public_name alias — the settings page is the place the owner verifies
    which model actually serves."""
    capabilities = []
    for route in _routes():
        provider = str(route["provider"]).upper()
        mode = provider_mode(provider)
        model = str(route["provider_model"] or "")
        override = os.environ.get(f"AI_GATEWAY_{provider}_MODEL", "")
        if provider != "MOCK" and override:
            model = override
        capabilities.append(
            {
                "capability": str(route["capability"]),
                "provider": provider,
                "model": model,
                "public_name": str(route["public_name"]),
                "mode": mode,
                "credits_cost": int(route["credits_cost"] or 0),
                "timeout_s": (
                    int(route["timeout_s"]) if route["timeout_s"] else None
                ),
                "retry_max": int(route["retry_max"] or 0),
                "tools_enabled": bool(route["tools_enabled"]),
                "enabled": bool(route["enabled"]),
            }
        )
    # Overall mode: test only when a MOCK route is actually serving; live
    # when every enabled route resolves a configured provider; otherwise the
    # org sees "unconfigured" with per-capability detail.
    modes = {item["mode"] for item in capabilities if item["enabled"]}
    if not modes:
        mode = "unconfigured"
    elif "live" in modes:
        mode = "live" if modes == {"live"} else "partial"
    else:
        mode = "test" if modes == {"test"} else "partial"
    return {"mode": mode, "capabilities": capabilities}


def ai_settings(org_id: UUID) -> dict:
    """The Settings › IA payload: provider/capability map + budget + this
    month's consumption."""
    budget = invocations.monthly_budget(org_id)
    spent = invocations.month_credits_spent(org_id)
    usage = invocations.month_usage(org_id)
    return {
        **provider_status(),
        "budget": {
            "monthly_credit_budget": budget,
            "spent_this_month": spent,
            "exceeded": budget is not None and spent >= budget,
        },
        "usage": usage,
    }


def save_budget(org_id: UUID, user_id: UUID, value: int | None) -> dict:
    """Upsert the org's monthly credit budget. Writes under ai_backend —
    members can read the row but only the API may change it."""
    if value is not None and not 0 <= int(value) <= 10_000_000:
        raise ValueError("ai_budget_invalid")
    if connection.vendor == "postgresql":
        with _ai_backend():
            rows(
                "INSERT INTO public.ai_org_settings"
                " (org_id, monthly_credit_budget, updated_by)"
                " VALUES(%s, %s, %s)"
                " ON CONFLICT (org_id) DO UPDATE SET"
                " monthly_credit_budget = EXCLUDED.monthly_credit_budget,"
                " updated_by = EXCLUDED.updated_by, updated_at = NOW()"
                " RETURNING monthly_credit_budget",
                [str(org_id), value, str(user_id)],
            )
    return {"monthly_credit_budget": value}


def probe(org_id: UUID, user_id: UUID) -> dict:
    """"Probar conexión" — one minimal live call on the cheapest enabled
    route. No wallet lock, no audit row, no debit: the call records as a
    kind='probe' invocation so the activity panel shows it honestly."""
    route = _cheapest_live_route()
    started = time.monotonic()
    if route is None:
        return {
            "ok": False,
            "error_code": "ai_provider_unconfigured",
            "latency_ms": 0,
        }
    provider = str(route["provider"]).upper()
    capability = str(route["capability"])
    mode = "test" if provider == "MOCK" else "live"
    entry = invocations.build_entry(
        org_id=org_id,
        user_id=user_id,
        kind="probe",
        capability=capability,
        tool_name="provider_check",
        operation_key=f"probe:{uuid4().hex[:16]}",
        mode=mode,
        public_model=str(route["public_name"]),
    )
    try:
        result = provider_for(route).invoke(
            route=route,
            capability=capability,
            input_payload={
                "probe": True,
                "instruction": 'Responde {"ok": true}',
            },
            provider_options={
                "system": 'Eres un endpoint de verificación. Responde solo {"ok": true}.',
                "json_output": True,
            },
            operation_key=str(entry["operation_key"]),
        )
    except ProviderError as error:
        entry["status"] = "error"
        entry["error_code"] = error.code
        entry["latency_ms"] = int((time.monotonic() - started) * 1000)
        invocations.record(entry)
        invocations.log_call(entry)
        return {
            "ok": False,
            "error_code": error.code,
            "latency_ms": entry["latency_ms"],
            "model": str(route["public_name"]),
        }
    entry["status"] = "ok"
    entry["latency_ms"] = int(result["latency_ms"])
    entry["tokens_prompt"] = int(result["tokens_prompt"])
    entry["tokens_completion"] = int(result["tokens_completion"])
    invocations.record(entry)
    invocations.log_call(entry)
    return {
        "ok": True,
        "error_code": None,
        "latency_ms": entry["latency_ms"],
        "model": str(route["public_name"]),
    }


def _cheapest_live_route() -> dict | None:
    """The cheapest enabled route whose provider can actually serve — the
    probe exercises the real transport without paying a full agent round."""
    candidates = [
        route
        for route in _routes()
        if route["enabled"] and provider_mode(route["provider"]) != "unconfigured"
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda route: int(route["credits_cost"] or 0))


__all__ = [
    "ai_settings",
    "member_status",
    "probe",
    "provider_mode",
    "provider_status",
    "save_budget",
]
