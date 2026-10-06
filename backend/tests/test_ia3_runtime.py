"""§IA3 — real-provider runtime: transient retries, timeout, tool calling,
strict-JSON fallback, budget soft block, prod MOCK gate, key hygiene."""

import json
from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from rest_framework.exceptions import APIException

from ai_gateway import invocations, service
from ai_gateway.providers import (
    HttpProvider,
    MockProvider,
    OpenAICompatibleProvider,
    ProviderError,
    provider_for,
)


@contextmanager
def _atomic():
    yield


def _route(**over):
    route = {
        "id": uuid4(),
        "capability": "nlp_command",
        "public_name": "DEKOPEN Neural Core™",
        "provider": "MOCK",
        "provider_model": "mock-neural-1",
        "prompt_version": "v1.0",
        "credits_cost": 5,
        "enabled": True,
    }
    route.update(over)
    return route


def _org(**over):
    org = {
        "id": uuid4(),
        "subscription_tier": "PRO",
        "subscription_active": True,
        "credits_balance": 500,
    }
    org.update(over)
    return org


def _patch_service(monkeypatch, *, org=None, route=None, rows_impl=None, provider=None):
    """Same fake environment as test_ai_gateway but with budget hooks intact —
    the real invocations.monthly_budget/month_credits_spent read through the
    faked `rows` so a test can drive them via rows_impl."""
    monkeypatch.setattr(service.wallet, "financial_transaction", lambda org_id: _atomic())
    monkeypatch.setattr(
        service.wallet,
        "reconcile",
        lambda org_id: org if org is not None else _org(),
    )
    debited: list[dict] = []
    monkeypatch.setattr(
        service.wallet,
        "debit",
        lambda org_id, credits, audit_id: debited.append(
            {"org_id": org_id, "credits": credits, "audit_id": audit_id}
        ),
    )

    def default_rows(sql, params=None):
        if "FROM public.ai_routes" in sql:
            return [route] if route is not None else [_route()]
        if "INSERT INTO public.ai_audit_logs" in sql:
            return [{"id": uuid4()}]
        return []

    impl = rows_impl or default_rows
    monkeypatch.setattr(service, "rows", impl)
    monkeypatch.setattr(invocations, "rows", impl)
    monkeypatch.setattr(invocations, "log_call", lambda entry: None)
    monkeypatch.setattr(invocations, "record", lambda entry: True)
    # transaction.on_commit in service would schedule the record — no real
    # DB here, so drop the callback.
    monkeypatch.setattr(service.transaction, "on_commit", lambda fn: None)
    if provider is not None:
        monkeypatch.setattr(service, "provider_for", lambda route: provider)
    return debited


def _allow_dns(monkeypatch):
    import socket as _socket

    monkeypatch.setattr(
        "ai_gateway.providers.socket.getaddrinfo",
        lambda *a, **k: [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _openai_body(text: str, **extra) -> bytes:
    return json.dumps(
        {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 7},
            **extra,
        }
    ).encode()


def _no_sleep(monkeypatch):
    monkeypatch.setattr("ai_gateway.providers.time.sleep", lambda seconds: None)


# ---------------------------------------------------------------------------
# Transient retries
# ---------------------------------------------------------------------------


def test_transient_5xx_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_RT_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_RT_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, content=b"busy")
        return httpx.Response(200, content=b'{"output": "ok", "usage": {}}')

    out = HttpProvider(provider="RT").invoke(
        route=_route(),
        capability="nlp_command",
        input_payload={},
        client=_client(handler),
    )
    assert out["output"] == "ok"
    assert len(calls) == 2


def test_retry_budget_is_bounded(monkeypatch):
    """A permanently failing endpoint gets first attempt + retry_max tries —
    not an unbounded loop."""
    monkeypatch.setenv("AI_GATEWAY_RB_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_RB_BASE_URL", "https://provider.example")
    monkeypatch.setenv("AI_GATEWAY_RB_RETRIES", "2")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []
    client = _client(lambda request: calls.append(request) or httpx.Response(503, content=b"x"))
    with pytest.raises(ProviderError) as failure:
        HttpProvider(provider="RB").invoke(
            route=_route(), capability="nlp_command", input_payload={}, client=client
        )
    assert failure.value.code == "ai_provider_error"
    assert failure.value.transient is True
    assert len(calls) == 3  # first + 2 retries


def test_auth_failure_never_retries(monkeypatch):
    """401 is terminal — retrying a bad credential only burns the window."""
    monkeypatch.setenv("AI_GATEWAY_NA_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_NA_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []
    client = _client(lambda request: calls.append(request) or httpx.Response(401, content=b"x"))
    with pytest.raises(ProviderError) as failure:
        HttpProvider(provider="NA").invoke(
            route=_route(), capability="nlp_command", input_payload={}, client=client
        )
    assert failure.value.code == "ai_provider_auth"
    assert failure.value.transient is False
    assert len(calls) == 1


def test_bare_429_is_terminal_quota(monkeypatch):
    """Quota exhausted without Retry-After is a billing fact, not a blip —
    no retry, callers surface 'cuota' not 'try again'."""
    monkeypatch.setenv("AI_GATEWAY_QT_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_QT_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []
    client = _client(
        lambda request: calls.append(request)
        or httpx.Response(429, content=b'{"error":"quota"}')
    )
    with pytest.raises(ProviderError) as failure:
        HttpProvider(provider="QT").invoke(
            route=_route(), capability="nlp_command", input_payload={}, client=client
        )
    assert failure.value.code == "ai_provider_quota"
    assert failure.value.transient is False
    assert len(calls) == 1


def test_429_with_retry_after_is_transient(monkeypatch):
    """A rate-limit answer carrying Retry-After is transient — the provider
    itself told us when to come back."""
    monkeypatch.setenv("AI_GATEWAY_RL_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_RL_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, content=b"x")
        return httpx.Response(200, content=b'{"output": "ok", "usage": {}}')

    out = HttpProvider(provider="RL").invoke(
        route=_route(), capability="nlp_command", input_payload={}, client=_client(handler)
    )
    assert out["output"] == "ok"
    assert len(calls) == 2


def test_transport_timeout_retries_then_fails_transient(monkeypatch):
    """A timeout mid-request retries inside the bounded budget, then surfaces
    as a transient error the job can requeue."""
    monkeypatch.setenv("AI_GATEWAY_TO_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_TO_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as failure:
        HttpProvider(provider="TO").invoke(
            route=_route(), capability="nlp_command", input_payload={}, client=_client(handler)
        )
    assert failure.value.transient is True
    assert len(calls) == 3  # default retry budget: 1 + 2


def test_malformed_retry_env_refuses_provider(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_BADR_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_BADR_BASE_URL", "https://provider.example")
    monkeypatch.setenv("AI_GATEWAY_BADR_RETRIES", "forever")
    _allow_dns(monkeypatch)
    with pytest.raises(ProviderError) as failure:
        HttpProvider(provider="BADR")
    assert failure.value.code == "ai_provider_unavailable"


# ---------------------------------------------------------------------------
# Tool calling + strict-JSON fallback
# ---------------------------------------------------------------------------


def _tool_specs():
    return [
        {
            "type": "function",
            "function": {
                "name": "query_projects",
                "description": "Consulta proyectos",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def test_tools_and_tool_choice_reach_the_wire(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_TW_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_TW_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    calls: list[httpx.Request] = []
    client = _client(
        lambda request: calls.append(request)
        or httpx.Response(200, content=_openai_body("ok"))
    )
    OpenAICompatibleProvider(provider="TW").invoke(
        route=_route(provider_model="mimo-x"),
        capability="agent",
        input_payload={"goal": "x"},
        provider_options={"tools": _tool_specs(), "tool_choice": "auto"},
        client=client,
    )
    body = json.loads(calls[0].content)
    assert body["tools"][0]["function"]["name"] == "query_projects"
    assert body["tool_choice"] == "auto"


def test_tool_calls_parse_into_normalized_triples(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_TC_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_TC_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    payload = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "query_projects",
                                    "arguments": '{"limit": 3}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
    ).encode()
    client = _client(lambda request: httpx.Response(200, content=payload))
    out = OpenAICompatibleProvider(provider="TC").invoke(
        route=_route(provider_model="mimo-x"),
        capability="agent",
        input_payload={},
        provider_options={"tools": _tool_specs(), "tool_choice": "auto"},
        client=client,
    )
    assert out["tool_calls"] == [
        {"id": "call_1", "name": "query_projects", "arguments": {"limit": 3}}
    ]
    assert out["assistant_message"]["tool_calls"][0]["id"] == "call_1"


def test_rejected_tools_degrade_once_to_strict_json(monkeypatch):
    """A provider that answers 400 to the tools parameter gets exactly one
    strict-JSON retry — the same document contract without tool calling."""
    monkeypatch.setenv("AI_GATEWAY_SF_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_SF_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        if "tools" in json.loads(request.content):
            return httpx.Response(400, content=b'{"error":"tools not supported"}')
        return httpx.Response(200, content=_openai_body('{"answer": "sin herramientas"}'))

    out = OpenAICompatibleProvider(provider="SF").invoke(
        route=_route(provider_model="mimo-x"),
        capability="agent",
        input_payload={},
        provider_options={"tools": _tool_specs(), "tool_choice": "auto"},
        client=_client(handler),
    )
    assert len(calls) == 2
    retry_body = json.loads(calls[1].content)
    assert "tools" not in retry_body
    assert "tool_choice" not in retry_body
    assert retry_body["response_format"] == {"type": "json_object"}
    assert out["tools_fallback"] is True


def test_rejected_without_tools_is_terminal(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_RJ_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_RJ_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    _no_sleep(monkeypatch)
    calls: list[httpx.Request] = []
    client = _client(
        lambda request: calls.append(request) or httpx.Response(400, content=b"x")
    )
    with pytest.raises(ProviderError) as failure:
        OpenAICompatibleProvider(provider="RJ").invoke(
            route=_route(provider_model="m"),
            capability="agent",
            input_payload={},
            provider_options={"tools": _tool_specs()},
            client=client,
        )
    # The strict-JSON fallback itself got rejected — the loop stops.
    assert failure.value.code == "ai_provider_rejected"
    assert len(calls) == 2


def test_route_tools_disabled_strips_wire_options(monkeypatch):
    """tools_enabled=false on the route gates the feature server-side even
    when the caller asked for tools."""
    _patch_service(monkeypatch, route=_route(tools_enabled=False))
    sent: list[dict] = []

    def spy(**kwargs):
        sent.append(kwargs)
        return {"output": "ok", "tokens_prompt": 1, "tokens_completion": 1, "latency_ms": 1}

    monkeypatch.setattr(service, "provider_for", lambda route: type("P", (), {"invoke": staticmethod(spy)})())
    service.invoke(
        org_id=uuid4(),
        user_id=uuid4(),
        capability="nlp_command",
        operation_key="op-tools-off",
        input_payload={},
        provider_options={"tools": _tool_specs(), "tool_choice": "auto"},
    )
    assert "tools" not in sent[0]["provider_options"]
    assert "tool_choice" not in sent[0]["provider_options"]


# ---------------------------------------------------------------------------
# Monthly budget soft block
# ---------------------------------------------------------------------------


def test_budget_exceeded_blocks_before_provider_and_records(monkeypatch):
    route = _route(provider="MIMO", provider_model="mimo-v2.6-pro")

    def fake_rows(sql, params=None):
        if "FROM public.ai_routes" in sql:
            return [route]
        if "FROM public.ai_org_settings" in sql:
            return [{"monthly_credit_budget": 10}]
        if "SUM(points_debited)" in sql:
            return [{"total": 9}]  # 9 spent + 5 needed > 10 cap
        return []

    _patch_service(monkeypatch, route=route, rows_impl=fake_rows)
    called = []
    monkeypatch.setattr(
        service, "provider_for", lambda route: called.append(route) or MockProvider()
    )
    with pytest.raises(APIException) as failure:
        service.invoke(
            org_id=uuid4(),
            user_id=uuid4(),
            capability="nlp_command",
            operation_key="op-budget",
            input_payload={},
        )
    assert failure.value.contract_code == "ai_budget_exceeded"
    assert called == []  # provider request never existed
    # The blocked row rides the exception for the post-rollback recorder.
    entry = failure.value.invocation
    assert entry["status"] == "blocked"
    assert entry["error_code"] == "ai_budget_exceeded"
    assert entry["mode"] == "live"
    assert entry["capability"] == "nlp_command"


def test_budget_none_allows_the_call(monkeypatch):
    _patch_service(monkeypatch)
    out = service.invoke(
        org_id=uuid4(),
        user_id=uuid4(),
        capability="nlp_command",
        operation_key="op-nobudget",
        input_payload={},
    )
    assert out["credits_debited"] == 5


def test_insufficient_credits_records_a_blocked_row(monkeypatch):
    _patch_service(monkeypatch, org=_org(credits_balance=2))
    with pytest.raises(APIException) as failure:
        service.invoke(
            org_id=uuid4(),
            user_id=uuid4(),
            capability="nlp_command",
            operation_key="op-broke",
            input_payload={},
        )
    assert failure.value.contract_code == "insufficient_credits"
    assert failure.value.invocation["status"] == "blocked"
    assert failure.value.invocation["error_code"] == "insufficient_credits"


def test_provider_error_records_an_error_row(monkeypatch):
    _patch_service(monkeypatch)

    def boom(**kwargs):
        raise ProviderError("ai_provider_quota")

    monkeypatch.setattr(
        service, "provider_for", lambda route: type("P", (), {"invoke": staticmethod(boom)})()
    )
    # The entry rides the exception for the caller's post-rollback write.
    with pytest.raises(ProviderError) as failure:
        service.invoke(
            org_id=uuid4(),
            user_id=uuid4(),
            capability="nlp_command",
            operation_key="op-fail",
            input_payload={},
        )
    assert failure.value.invocation["status"] == "error"
    assert failure.value.invocation["error_code"] == "ai_provider_quota"


# ---------------------------------------------------------------------------
# Estimated cost sealed with the audit
# ---------------------------------------------------------------------------


def test_estimated_cost_from_price_sheet(monkeypatch):
    route = _route(provider="MIMO", provider_model="mimo-v2.6-pro")

    def fake_rows(sql, params=None):
        if "FROM public.ai_routes" in sql:
            return [route]
        if "FROM public.ai_model_prices" in sql:
            assert params == ["MIMO", "mimo-v2.6-pro"]
            return [{"usd_per_mtok_input": "1.00", "usd_per_mtok_output": "4.00"}]
        if "INSERT INTO public.ai_audit_logs" in sql:
            est = params[15]
            assert isinstance(est, Decimal)
            # tokens_prompt/tokens_completion from the mock derive from the
            # payload — assert only the shape lands.
            assert est >= 0
            return [{"id": uuid4()}]
        return []

    _patch_service(
        monkeypatch, route=route, rows_impl=fake_rows, provider=MockProvider()
    )
    service.invoke(
        org_id=uuid4(),
        user_id=uuid4(),
        capability="nlp_command",
        operation_key="op-priced",
        input_payload={"texto": "hola"},
    )


def test_unpriced_model_seals_null_cost(monkeypatch):
    """No price row = honest absence, not an estimate from nothing."""
    route = _route(provider="MIMO", provider_model="mimo-v2.6-pro")

    def fake_rows(sql, params=None):
        if "FROM public.ai_routes" in sql:
            return [route]
        if "FROM public.ai_model_prices" in sql:
            return []
        if "INSERT INTO public.ai_audit_logs" in sql:
            assert params[15] is None
            return [{"id": uuid4()}]
        return []

    _patch_service(
        monkeypatch, route=route, rows_impl=fake_rows, provider=MockProvider()
    )
    service.invoke(
        org_id=uuid4(),
        user_id=uuid4(),
        capability="nlp_command",
        operation_key="op-unpriced",
        input_payload={},
    )


# ---------------------------------------------------------------------------
# MOCK in production + key hygiene
# ---------------------------------------------------------------------------


def test_mock_refused_in_production_without_explicit_flag(monkeypatch):
    """DEBUG or a stray pytest process can never enable MOCK in prod — only
    the explicit AI_GATEWAY_MOCK_ENABLED flag opens 'Modo de prueba'."""
    monkeypatch.delenv("AI_GATEWAY_MOCK_ENABLED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "1")  # the trap: dev flag present in prod
    with pytest.raises(ProviderError) as failure:
        provider_for(_route())
    assert failure.value.code == "ai_provider_mock_disabled"


def test_mock_serves_with_explicit_flag_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_GATEWAY_MOCK_ENABLED", "1")
    provider = provider_for(_route())
    assert isinstance(provider, MockProvider)


def test_provider_key_never_reaches_response_or_log(monkeypatch, caplog):
    """The wire credential is sent as a bearer and appears nowhere else —
    not in the invoke envelope, not in the structured call line, not even
    in a failure's sanitized error."""
    secret = "test-key-" + "a" * 32
    monkeypatch.setenv("AI_GATEWAY_LEAK_API_KEY", secret)
    monkeypatch.setenv("AI_GATEWAY_LEAK_BASE_URL", "https://provider.example")
    _allow_dns(monkeypatch)
    calls: list[httpx.Request] = []
    client = _client(
        lambda request: calls.append(request)
        or httpx.Response(200, content=b'{"output": "ok", "usage": {}}')
    )
    with caplog.at_level("WARNING", "ai_gateway.providers"):
        out = HttpProvider(provider="LEAK").invoke(
            route=_route(),
            capability="nlp_command",
            input_payload={},
            client=client,
        )
    assert calls[0].headers["Authorization"] == f"Bearer {secret}"
    assert secret not in json.dumps(out)
    assert secret not in caplog.text

    # Failure paths are sanitized the same way.
    error_client = _client(lambda request: httpx.Response(401, content=b"x"))
    with caplog.at_level("WARNING", "ai_gateway.providers"):
        with pytest.raises(ProviderError):
            HttpProvider(provider="LEAK").invoke(
                route=_route(),
                capability="nlp_command",
                input_payload={},
                client=error_client,
            )
    assert secret not in caplog.text


def test_structured_call_log_carries_no_payload_or_key(monkeypatch, caplog):
    """The per-job log line mirrors the durable row — no prompts, outputs,
    payloads, or credentials."""
    entry = invocations.build_entry(
        org_id=uuid4(),
        user_id=uuid4(),
        capability="agent",
        tool_name="ai_agent",
        operation_key="op-log",
        mode="live",
        public_model="DEKOPEN Neural Core™",
        tokens_prompt=10,
        tokens_completion=20,
        latency_ms=12,
        credits=5,
        est_cost_usd=Decimal("0.000123"),
        status="ok",
    )
    with caplog.at_level("INFO", "ai_gateway.calls"):
        invocations.log_call(entry)
    line = caplog.text
    assert '"capability": "agent"' in line
    assert '"status": "ok"' in line
    assert "input_payload" not in line
    assert "output" not in line
    assert "AI_GATEWAY" not in line


def test_record_attached_writes_only_error_invocation(monkeypatch):
    """record_attached is a no-op on errors that carry no row."""
    recorded: list[dict] = []
    monkeypatch.setattr(invocations, "record", lambda entry: recorded.append(entry) or True)
    assert invocations.record_attached(ValueError("plain")) is False
    assert recorded == []

    error = ProviderError("ai_provider_error")
    error.invocation = {"status": "error"}
    assert invocations.record_attached(error) is True
    assert recorded == [{"status": "error"}]


def test_job_cost_sql_binds_the_suffix_wildcard(monkeypatch):
    """BUG (E2E): `LIKE %s || ':%'` left a literal `%'` in the SQL — psycopg
    rejected the query client-side, so every job detail 409'd. The wildcard
    must live in the bound parameter, never in the statement."""
    captured: dict = {}

    def _spy(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params or []
        return [{"calls": 2, "tokens": 30, "credits": 8, "est_cost_usd": None}]

    monkeypatch.setattr(invocations, "rows", _spy)
    out = invocations.job_cost(uuid4(), "job:abc:100%")
    assert out is not None and out["calls"] == 2
    # No bare %' may survive in the statement — only %s placeholders.
    sql = captured["sql"].replace("%s", "")
    assert "%" not in sql
    # The LIKE parameter carries the ':suffix' wildcard itself, and the
    # caller's own %/_ metacharacters are escaped first.
    like_param = captured["params"][2]
    assert like_param.endswith(":%")
    assert "\\%" in like_param
