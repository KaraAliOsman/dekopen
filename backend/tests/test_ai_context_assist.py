"""Contextual Ask: typed projections, server-owned context, answer contract."""

import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from ai_gateway import assist, context


def _org_row(**over):
    row = {
        "name": "Demo Org",
        "subscription_tier": "PRO",
        "credits_balance": 500,
        "currency": "CLP",
    }
    row.update(over)
    return row


def _envelope(output: str):
    return {
        "audit_id": str(uuid4()),
        "capability": "context_assist",
        "model": "mock-context-1",
        "output": output,
        "tokens_prompt": 10,
        "tokens_completion": 10,
        "latency_ms": 1,
        "credits_debited": 2,
    }


def _patch(monkeypatch, *, rows_impl=None, output=None):
    calls = []
    monkeypatch.setattr(
        context,
        "rows",
        rows_impl
        or (lambda sql, params=None: [_org_row()] if "tenancy_organizations" in sql else []),
    )
    monkeypatch.setattr(
        assist.gateway,
        "invoke",
        lambda **kwargs: calls.append(kwargs) or _envelope(output or _good_output()),
    )
    return calls


def _good_output() -> str:
    return json.dumps(
        {
            "answer": "El contexto muestra el estado actual del proyecto.",
            "actions": [{"kind": "navigate", "path": "/projects", "label": "Ver proyectos"}],
            "warnings": [],
        },
        ensure_ascii=False,
    )


def test_ask_dashboard_projects_context_into_payload(monkeypatch):
    org_id = uuid4()

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "SELECT " in sql and "count(*)" in sql:
            return [
                {
                    "projects": 4,
                    "positions": 9,
                    "work_orders_open": 2,
                    "clients": 1,
                    "profile_systems": 3,
                }
            ]
        if "ORDER BY updated_at DESC LIMIT 5" in sql:
            return [
                {
                    "id": uuid4(),
                    "code": "OB-1",
                    "name": "Edificio Sur",
                    "client_name": "Concesionaria X",
                    "status": "DRAFT",
                }
            ]
        return []

    calls = _patch(monkeypatch, rows_impl=fake_rows)
    result = assist.ask(
        org_id=org_id,
        user_id=uuid4(),
        surface="dashboard",
        refs={},
        question="¿Cuántos proyectos hay?",
        operation_key="ask-1",
    )
    assert result["answer"] == "El contexto muestra el estado actual del proyecto."
    assert result["actions"] == [
        {"kind": "navigate", "path": "/projects", "label": "Ver proyectos"}
    ]
    payload = calls[0]["input_payload"]
    assert payload["surface"] == "dashboard"
    assert payload["context"]["counts"]["projects"] == 4
    assert payload["context"]["recent_projects"][0]["code"] == "OB-1"
    # List entries expose their ids — drill-down queries key on them (§07-C).
    assert payload["context"]["recent_projects"][0]["id"]
    assert payload["context"]["organization"]["name"] == "Demo Org"


def test_ask_unknown_surface_rejected(monkeypatch):
    _patch(monkeypatch)
    with pytest.raises(APIException) as error:
        assist.ask(
            org_id=uuid4(),
            user_id=uuid4(),
            surface="payroll",
            refs={},
            question="hola",
            operation_key="ask-1",
        )
    assert error.value.get_codes() == "ai_surface_unknown"
    assert error.value.status_code == 400


def test_ask_missing_ref_rejected_before_provider(monkeypatch):
    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "FROM public.projects" in sql:
            return []
        return []

    calls = _patch(monkeypatch, rows_impl=fake_rows)
    with pytest.raises(APIException) as error:
        assist.ask(
            org_id=uuid4(),
            user_id=uuid4(),
            surface="project",
            refs={"project_id": str(uuid4())},
            question="¿estado?",
            operation_key="ask-1",
        )
    assert error.value.get_codes() == "ai_context_not_found"
    assert error.value.status_code == 404
    # The entity miss happens before any provider call — no debit.
    assert calls == []


def test_ask_missing_ref_field_rejected_before_provider(monkeypatch):
    calls = _patch(monkeypatch)
    with pytest.raises(APIException) as error:
        assist.ask(
            org_id=uuid4(),
            user_id=uuid4(),
            surface="project",
            refs={},
            question="hola",
            operation_key="ask-1",
        )
    assert error.value.get_codes() == "ai_context_ref_required"
    assert error.value.status_code == 400
    assert calls == []


def test_ask_malformed_output_refused(monkeypatch):
    _patch(monkeypatch, output="no soy json")
    with pytest.raises(APIException) as error:
        assist.ask(
            org_id=uuid4(),
            user_id=uuid4(),
            surface="dashboard",
            refs={},
            question="hola",
            operation_key="ask-1",
        )
    assert error.value.get_codes() == "ai_assist_bad_output"
    assert error.value.status_code == 502


def test_ask_actions_allowlist_strips_bad_paths(monkeypatch):
    output = json.dumps(
        {
            "answer": "ok",
            "actions": [
                {"kind": "navigate", "path": "javascript:alert(1)", "label": "evil"},
                {"kind": "navigate", "path": "https://evil.example/x", "label": "evil"},
                {"kind": "navigate", "path": "//evil.example", "label": "evil"},
                {"kind": "delete_project", "path": "/projects", "label": "bad kind"},
                {"kind": "navigate", "path": "/projects/abc", "label": "Ver proyecto"},
            ],
            "warnings": "not-a-list",
        }
    )
    _patch(monkeypatch, output=output)
    result = assist.ask(
        org_id=uuid4(),
        user_id=uuid4(),
        surface="dashboard",
        refs={},
        question="hola",
        operation_key="ask-1",
    )
    assert result["actions"] == [
        {"kind": "navigate", "path": "/projects/abc", "label": "Ver proyecto"}
    ]
    assert result["warnings"] == []


def test_ask_project_surface_builds_projected_context(monkeypatch):
    org_id = uuid4()
    project_id = uuid4()
    position_id = uuid4()

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "FROM public.projects WHERE id=%s AND org_id=%s" in sql:
            return [
                {
                    "id": project_id,
                    "code": "OB-1",
                    "name": "Edificio Sur",
                    "client_name": "Concesionaria X",
                    "status": "DRAFT",
                    "current_revision": "REV-A",
                    "total_price_net": "100.00",
                    "total_price_tax": "19.00",
                    "total_price_gross": "119.00",
                }
            ]
        if "FROM public.project_positions" in sql:
            return [
                {
                    "id": position_id,
                    "position_index": 1,
                    "location_tag": "Fachada",
                    "typology": "VENTANA",
                    "width_mm": "1200.00",
                    "height_mm": "1400.00",
                }
            ]
        if "FROM public.project_versions" in sql:
            return [
                {
                    "revision_code": "REV-A",
                    "documentary_complete": True,
                    "production_allowed": True,
                }
            ]
        if "FROM public.project_payments" in sql:
            return [{"count": 1, "collected": "50.00"}]
        return []

    calls = _patch(monkeypatch, rows_impl=fake_rows)
    assist.ask(
        org_id=org_id,
        user_id=uuid4(),
        surface="project",
        refs={"project_id": str(project_id)},
        question="¿cuánto se ha cobrado?",
        operation_key="ask-1",
    )
    ctx = calls[0]["input_payload"]["context"]
    assert ctx["code"] == "OB-1"
    assert ctx["payments"]["payments_collected"] == "50.00"
    assert ctx["latest_version"]["revision"] == "REV-A"
    assert ctx["positions"][0]["typology"] == "VENTANA"
    assert ctx["positions"][0]["id"] == str(position_id)


def test_projects_list_context_exposes_drilldown_ids(monkeypatch):
    """§07-C — a list result without ids can never be drilled into: the
    observed-ref guard would reject every follow-up query on those rows."""
    org_id = uuid4()
    project_id = uuid4()

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "FROM public.projects p" in sql:
            return [
                {
                    "id": project_id,
                    "code": "OB-1",
                    "name": "Edificio Sur",
                    "client_name": "Concesionaria X",
                    "status": "QUOTED",
                    "positions": 3,
                }
            ]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    ctx = context.build_context(org_id, "projects", {})
    assert ctx["projects"][0]["id"] == str(project_id)


def test_mock_provider_context_assist_shape():
    from ai_gateway.providers import MockProvider

    out = MockProvider().invoke(
        route={
            "id": uuid4(),
            "capability": "context_assist",
            "public_name": "DEKOPEN Asistente Contextual™",
            "provider": "MOCK",
            "provider_model": "mock-context-1",
            "prompt_version": "v1.0",
            "credits_cost": 2,
            "enabled": True,
        },
        capability="context_assist",
        input_payload={
            "question": "hola",
            "surface": "dashboard",
            "context": {
                "surface": "dashboard",
                "organization": {"name": "Demo", "plan": "PRO"},
                "counts": {"projects": 2, "work_orders_open": 1},
            },
        },
    )
    document = json.loads(out["output"])
    assert document["answer"].startswith("Estás en la superficie 'dashboard'")
    assert document["actions"] == []
    assert "2 proyectos" in document["answer"]


def test_ask_answer_citing_uncited_number_refused(monkeypatch):
    """§5: a number nowhere in the context or the question is an invention —
    the answer is refused rather than passed off as an explanation."""
    _patch(
        monkeypatch,
        output=json.dumps(
            {
                "answer": "El consumo estimado es 3,2 barras.",
                "actions": [],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )
    with pytest.raises(APIException) as error:
        assist.ask(
            org_id=uuid4(),
            user_id=uuid4(),
            surface="dashboard",
            refs={},
            question="¿cuántas barras necesito?",
            operation_key="ask-1",
        )
    assert error.value.get_codes() == "ai_assist_ungrounded"
    assert error.value.status_code == 502


def test_ask_answer_may_cite_context_and_question_numbers(monkeypatch):
    """A projected value is a citation; the user's own number in the question
    grounds too ('2.400' in a 2.400 mm paño). Both must come through."""

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "count(*)" in sql:
            return [
                {
                    "projects": 4,
                    "positions": 9,
                    "work_orders_open": 2,
                    "clients": 20,
                    "profile_systems": 3,
                }
            ]
        return []

    _patch(
        monkeypatch,
        rows_impl=fake_rows,
        output=json.dumps(
            {
                "answer": "Tienes ~20 clientes y preguntas por un paño de 2.400 mm.",
                "actions": [],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )
    result = assist.ask(
        org_id=uuid4(),
        user_id=uuid4(),
        surface="dashboard",
        refs={},
        question="¿qué paño de 2.400 mm conviene?",
        operation_key="ask-1",
    )
    assert result["answer"].startswith("Tienes ~20 clientes")


def test_mock_provider_refuses_when_disabled(monkeypatch):
    """§9: a production stack can never answer silently with fabricated
    content — MOCK off fails visibly instead of serving."""
    from ai_gateway.providers import ProviderError, provider_for

    monkeypatch.setenv("AI_GATEWAY_MOCK_ENABLED", "0")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    with pytest.raises(ProviderError) as failure:
        provider_for({"provider": "MOCK"})
    assert failure.value.code == "ai_provider_mock_disabled"
    monkeypatch.setenv("AI_GATEWAY_MOCK_ENABLED", "1")
    provider_for({"provider": "MOCK"})


def test_provider_timeout_env_overrides_and_fails_visibly(monkeypatch):
    from ai_gateway.providers import HttpProvider, ProviderError

    monkeypatch.setenv("AI_GATEWAY_TO_API_KEY", "k")
    monkeypatch.setenv("AI_GATEWAY_TO_BASE_URL", "https://9.9.9.9/v1")
    monkeypatch.setenv("AI_GATEWAY_TO_TIMEOUT_S", "12.5")
    assert HttpProvider(provider="TO").timeout == 12.5
    monkeypatch.setenv("AI_GATEWAY_TO_TIMEOUT_S", "abc")
    with pytest.raises(ProviderError) as failure:
        HttpProvider(provider="TO")
    assert failure.value.code == "ai_provider_unavailable"
    monkeypatch.setenv("AI_GATEWAY_TO_TIMEOUT_S", "0")
    with pytest.raises(ProviderError):
        HttpProvider(provider="TO")


def test_ask_navigation_actions_grounded_to_context_ids(monkeypatch):
    """A provider can propose navigation — but only to entities the context
    literally carries: a deep link to an id it never saw is dropped, not
    passed through. Root section paths stay allowed."""
    org_id, project_id, intruder_id = uuid4(), uuid4(), uuid4()

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "FROM public.projects" in sql:
            return [
                {
                    "id": project_id,
                    "code": "PRJ-1",
                    "name": "P",
                    "client_name": "C",
                    "status": "DRAFT",
                    "current_revision": None,
                    "total_price_net": 0,
                    "total_price_tax": 0,
                    "total_price_gross": 0,
                }
            ]
        if "FROM public.project_payments" in sql:
            return [{"count": 0, "collected": 0}]
        return []

    output = json.dumps(
        {
            "answer": "Ok.",
            "actions": [
                {
                    "kind": "navigate",
                    "path": f"/projects/{project_id}",
                    "label": "Este proyecto",
                },
                {
                    "kind": "navigate",
                    "path": f"/projects/{intruder_id}",
                    "label": "Otro proyecto",
                },
                {"kind": "navigate", "path": "/production", "label": "Producción"},
            ],
            "warnings": [],
        },
        ensure_ascii=False,
    )
    _patch(monkeypatch, rows_impl=fake_rows, output=output)
    result = assist.ask(
        org_id=org_id,
        user_id=uuid4(),
        surface="project",
        refs={"project_id": str(project_id)},
        question="navega",
        operation_key="ask-ids",
    )
    paths = [a["path"] for a in result["actions"]]
    assert paths == [f"/projects/{project_id}", "/production"]


def _position_row(position_id, project_id, parametric_tree):
    return {
        "id": position_id,
        "project_id": project_id,
        "position_index": 1,
        "location_tag": "Fachada",
        "typology": "VENTANA",
        "width_mm": "2400.00",
        "height_mm": "1500.00",
        "parametric_tree": parametric_tree,
        "system_code": "DEMO_60",
        "system_name": "Demo 60",
        "material": "PVC",
        "project_code": "OB-1",
        "project_name": "Edificio",
    }


def test_position_context_decodes_jsonb_parametric_tree(monkeypatch):
    """Raw cursors hand jsonb back as text — undecoded, modules/couplings
    would collapse to None forever."""
    org_id = uuid4()
    position_id = uuid4()
    project_id = uuid4()

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "FROM public.project_positions" in sql:
            return [
                _position_row(
                    position_id,
                    project_id,
                    json.dumps(
                        {
                            "assembly": {
                                "modules": [
                                    {"id": "m1", "width_mm": "1200", "height_mm": "1500"},
                                    {"id": "m2", "width_mm": "1200", "height_mm": "1500"},
                                ],
                                "couplings": [{"id": "c1", "modules": ["m1", "m2"]}],
                            }
                        }
                    ),
                )
            ]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    ctx = context.build_context(org_id, "position", {"position_id": str(position_id)})
    assert ctx["modules"] == [
        {
            "id": "m1",
            "width_mm": "1200",
            "height_mm": "1500",
            "openings": [],
            "glass_skus": [],
        },
        {
            "id": "m2",
            "width_mm": "1200",
            "height_mm": "1500",
            "openings": [],
            "glass_skus": [],
        },
    ]
    assert ctx["couplings"] == 1


def test_position_context_wraps_single_module_tree(monkeypatch):
    """A single-module position persists its module's own tree — no assembly
    envelope — so the projection surfaces it as one module with real dims."""
    org_id = uuid4()
    position_id = uuid4()
    project_id = uuid4()

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "FROM public.project_positions" in sql:
            return [
                _position_row(
                    position_id,
                    project_id,
                    json.dumps({"bays": [{"id": "b1"}], "leaves": []}),
                )
            ]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    ctx = context.build_context(org_id, "position", {"position_id": str(position_id)})
    assert ctx["modules"] == [
        {
            "id": None,
            "width_mm": "2400.00",
            "height_mm": "1500.00",
            "single": True,
            "openings": [],
            "glass_skus": [],
        }
    ]
    assert ctx["couplings"] is None


def test_work_order_context_decodes_jsonb_reservations(monkeypatch):
    """payload_json->'optimization'->'stock_reservations' arrives as text —
    shortages must count real entries, not silently read 0."""
    org_id = uuid4()
    order_id = uuid4()

    def fake_rows(sql, params=None):
        if "tenancy_organizations" in sql:
            return [_org_row()]
        if "FROM public.orders" in sql:
            return [
                {
                    "id": order_id,
                    "order_code": "OT-1",
                    "status": "RELEASED",
                    "reservations": json.dumps(
                        [{"sku": "S1", "short": "3"}, {"sku": "S2", "short": "0"}]
                    ),
                }
            ]
        if "FROM public.production_steps" in sql:
            return [{"sequence": 1, "code": "CUT", "label": "Corte", "status": "PENDING"}]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    ctx = context.build_context(org_id, "work_order", {"work_order_id": str(order_id)})
    assert ctx["shortages"] == 1


def test_brief_projection_attention_and_item_ids(monkeypatch):
    """§08-WH — the brief surface returns the attention counts plus
    drill-down ids per category; job_runs is read under the documented
    connection-owner exception, so it is stubbed as its own calls."""
    import contextlib

    org_id = uuid4()
    project_id = uuid4()
    order_id = uuid4()
    job_id = uuid4()

    def fake_one(sql, params=None):
        if "job_runs" in sql:
            return {"n": 2}
        if "public.deliveries" in sql:
            return {"today": 1, "overdue": 0}
        return {
            "catalog_gaps": 1,
            "steps_blocked": 0,
            "approvals_pending": 1,
            "quotes_unsent": 2,
            "quotes_stale": 0,
            "versions_ready": 0,
            "work_orders_shortage": 1,
            "dispatch_ready": 0,
        }

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "job_runs" in sql:
            return [
                {
                    "id": job_id,
                    "type": "catalog_import",
                    "completed_at": datetime.fromisoformat(
                        "2026-09-25T08:00:00+00:00"
                    ),
                }
            ]
        if "FROM public.projects p" in sql and "NOT EXISTS" in sql:
            return [{"id": project_id, "code": "OB-1", "name": "Edificio Sur"}]
        if "FROM public.projects p" in sql and "DISTINCT" in sql:
            return [{"id": project_id, "code": "OB-1", "name": "Edificio Sur"}]
        if "FROM public.orders o" in sql:
            return [{"id": order_id, "order_code": "OT-9"}]
        return []

    monkeypatch.setattr(context, "rows", fake_rows)
    monkeypatch.setattr(context, "one", fake_one)
    monkeypatch.setattr(
        context,
        "job_owner",
        lambda: contextlib.nullcontext(),
    )
    ctx = context.build_context(org_id, "morning_brief", {})
    assert ctx["surface"] == "morning_brief"
    assert ctx["attention"]["quotes_unsent"] == 2
    assert ctx["attention"]["failed_jobs"] == 2
    assert ctx["attention"]["deliveries_today"] == 1
    assert ctx["items"]["quotes_unsent"][0]["id"] == str(project_id)
    assert ctx["items"]["work_orders_shortage"][0]["order_code"] == "OT-9"
    assert ctx["items"]["failed_jobs"][0]["id"] == str(job_id)


def test_purchase_plan_projection_uncovered_lines(monkeypatch):
    """§08-WE — the purchase_plan surface serves only uncovered requirement
    lines on the latest documentary versions, the declared-eligible
    suppliers, and the open purchase orders — everything a draft plan can
    cite, and nothing it can't."""
    org_id = uuid4()
    line_id = uuid4()
    version_id = uuid4()
    project_id = uuid4()
    po_id = uuid4()

    import contextlib

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "private.documentary_role" in sql:
            return [{"can_verify": True}]
        if "count(*) AS n" in sql:
            return [{"n": 1}]
        if "purchase_requirement_lines" in sql:
            return [
                {
                    "id": line_id,
                    "requirement_key": "REQ-1",
                    "order_type": "SUPPLIER_PROFILE_PO",
                    "category": "PROFILE",
                    "purchasing_sku": "MARCO-60",
                    "unit": "m",
                    "quantity": Decimal("48.000"),
                    "project_id": project_id,
                    "version_id": version_id,
                    "project_code": "OB-1",
                }
            ]
        if "supplier_eligibility_versions" in sql:
            return [
                {
                    "order_type": "SUPPLIER_PROFILE_PO",
                    "supplier_name": "Perfiles SA",
                }
            ]
        if "LIKE 'SUPPLIER" in sql:
            return [
                {
                    "id": po_id,
                    "order_code": "OC-7",
                    "order_type": "SUPPLIER_PROFILE_PO",
                    "status": "SENT",
                    "supplier_name": "Perfiles SA",
                }
            ]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    monkeypatch.setattr(
        context,
        "documentary_backend",
        lambda: contextlib.nullcontext(),
    )
    ctx = context.build_context(org_id, "purchase_plan", {})
    assert ctx["surface"] == "purchase_plan"
    assert ctx["uncovered_total"] == 1
    assert ctx["coverage_verified"] is True
    assert ctx["truncated"] is False
    line = ctx["uncovered_lines"][0]
    assert line["id"] == str(line_id)
    assert line["requirement_key"] == "REQ-1"
    assert line["version_id"] == str(version_id)
    assert ctx["suppliers"][0] == {
        "order_type": "SUPPLIER_PROFILE_PO",
        "supplier": "Perfiles SA",
    }
    assert ctx["open_purchase_orders"][0]["id"] == str(po_id)


def test_production_plan_projection_open_orders(monkeypatch):
    """§08-WF — the production_plan surface serves open work orders with
    their station queue, material flag and delivery pressure — everything a
    proposed schedule can restate, and nothing it can't."""
    org_id = uuid4()
    order_id = uuid4()

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "FROM public.production_steps" in sql:
            return [
                {
                    "order_id": order_id,
                    "sequence": 1,
                    "kind": "CUT",
                    "code": "CUT-01",
                    "label": "Corte de perfiles",
                    "status": "DONE",
                },
                {
                    "order_id": order_id,
                    "sequence": 2,
                    "kind": "GLAZING",
                    "code": "GLZ-01",
                    "label": "Acristalamiento",
                    "status": "PENDING",
                },
            ]
        if "FROM public.orders o" in sql:
            return [
                {
                    "id": order_id,
                    "order_code": "OT-9",
                    "status": "IN_PROGRESS",
                    "project_code": "OB-1",
                    "created_at": "2026-09-24T10:00:00",
                    "delivery_date": "2026-09-30",
                    "delivery_status": "SCHEDULED",
                    "short": True,
                }
            ]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    ctx = context.build_context(org_id, "production_plan", {})
    assert ctx["surface"] == "production_plan"
    order = ctx["work_orders"][0]
    assert order["id"] == str(order_id)
    assert order["material_short"] is True
    assert order["delivery_date"] == "2026-09-30"
    assert order["steps_done"] == 1
    assert order["steps_total"] == 2
    assert order["next_step"]["code"] == "GLZ-01"
    assert order["blocked_steps"] == []


def test_quotation_complete_projection_priced_approval_state(monkeypatch):
    """§08-WB — the complete-quotation projection carries the checklist the
    workflow narrates: position count, priced revision state (read via the
    documented commercial_backend exception), approval link state on the
    current revision, version documentary state, totals and payments."""
    import contextlib

    org_id = uuid4()
    project_id = uuid4()

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "FROM public.pricing_operations" in sql:
            return [{"currency": "CLP"}]
        if "FROM public.projects WHERE id" in sql:
            return [
                {
                    "id": project_id,
                    "code": "OB-1",
                    "name": "Edificio Sur",
                    "client_name": "Cliente Uno",
                    "status": "QUOTED",
                    "current_revision": "REV-A",
                    "total_price_net": Decimal("1000"),
                    "total_price_tax": Decimal("190"),
                    "total_price_gross": Decimal("1190"),
                }
            ]
        if "bom_hash IS NOT NULL" in sql:
            return [
                {
                    "revision_code": "REV-A",
                    "documentary_complete": True,
                    "production_allowed": False,
                    "frozen": True,
                }
            ]
        if "FROM public.project_positions" in sql:
            return [{"total": 3}]
        if "FROM public.customer_approvals" in sql:
            return [{"status": "PENDING", "live": True}]
        if "FROM public.project_payments" in sql:
            return [{"count": 2, "collected": Decimal("7000")}]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    monkeypatch.setattr(
        context,
        "commercial_backend",
        lambda: contextlib.nullcontext(),
    )
    ctx = context.build_context(
        org_id, "quotation_complete", {"project_id": str(project_id)}
    )
    assert ctx["surface"] == "quotation_complete"
    assert ctx["project"]["code"] == "OB-1"
    assert ctx["project"]["status"] == "QUOTED"
    assert ctx["positions"]["total"] == 3
    assert ctx["priced"] == {"currency": "CLP"}
    assert ctx["approval"] == {"status": "PENDING", "live": True}
    assert ctx["versions"][0]["frozen"] is True
    assert ctx["payments"]["payments_count"] == 2


def test_quotation_complete_projection_unpriced(monkeypatch):
    """§08-WB — no APPLIED pricing row → priced null, approval null; the
    workflow's checklist reports them missing instead of inventing state."""
    import contextlib

    org_id = uuid4()
    project_id = uuid4()

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "FROM public.pricing_operations" in sql:
            return []
        if "FROM public.projects WHERE id" in sql:
            return [
                {
                    "id": project_id,
                    "code": "OB-2",
                    "name": "Casa Norte",
                    "client_name": "Cliente Dos",
                    "status": "DRAFT",
                    "current_revision": "REV-A",
                    "total_price_net": Decimal("0"),
                    "total_price_tax": Decimal("0"),
                    "total_price_gross": Decimal("0"),
                }
            ]
        if "bom_hash IS NOT NULL" in sql:
            return []
        if "FROM public.project_positions" in sql:
            return [{"total": 1}]
        if "FROM public.project_payments" in sql:
            return [{"count": 0, "collected": Decimal("0")}]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    monkeypatch.setattr(
        context,
        "commercial_backend",
        lambda: contextlib.nullcontext(),
    )
    ctx = context.build_context(
        org_id, "quotation_complete", {"project_id": str(project_id)}
    )
    assert ctx["priced"] is None
    assert ctx["approval"] is None
    assert ctx["versions"] == []


def test_purchase_plan_projection_coverage_unverifiable(monkeypatch):
    """§08-WE + r10 — an estimator can't see allocations/eligibility rows
    under the documentary policies; the projection must report coverage as
    unverifiable instead of fabricating uncovered lines and suppliers."""
    import contextlib

    org_id = uuid4()

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "private.documentary_role" in sql:
            return [{"can_verify": False}]
        if "LIKE 'SUPPLIER" in sql:
            return []
        if "purchase_requirement_lines" in sql:
            raise AssertionError("coverage query must not run for this role")
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    monkeypatch.setattr(
        context,
        "documentary_backend",
        lambda: contextlib.nullcontext(),
    )
    ctx = context.build_context(org_id, "purchase_plan", {})
    assert ctx["coverage_verified"] is False
    assert ctx["uncovered_lines"] == []
    assert ctx["uncovered_total"] == 0
    assert ctx["suppliers"] is None
    assert ctx["truncated"] is False


def test_project_from_documents_projection_candidates(monkeypatch):
    """§08-WA — the project-from-documents projection carries each import's
    extraction candidates (key/label/dims/opening/confidence), the active
    catalog systems for typology mapping, and existing positions so the
    draft can't duplicate them."""
    org_id = uuid4()
    project_id = uuid4()
    import_id = uuid4()
    system_id = uuid4()

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "FROM public.projects WHERE id" in sql:
            return [
                {
                    "id": project_id,
                    "code": "OB-9",
                    "name": "Torre",
                    "client_name": "C",
                    "status": "DRAFT",
                    "current_revision": "REV-A",
                    "total_price_net": Decimal("0"),
                    "total_price_tax": Decimal("0"),
                    "total_price_gross": Decimal("0"),
                }
            ]
        if "FROM public.document_imports" in sql:
            return [
                {
                    "id": import_id,
                    "file_name": "planilla.pdf",
                    "kind": "PDF",
                    "status": "REVIEW_READY",
                    "error_code": None,
                    "candidates": json.dumps(
                        [
                            {
                                "key": "c1",
                                "label": "V-1",
                                "width_mm": "1200",
                                "height_mm": "1400",
                                "quantity": "2",
                                "opening_type": "TILT_TURN_LEFT",
                                "confidence": "0.92",
                                "warnings": ["low_confidence_system"],
                            }
                        ]
                    ),
                    "warnings": "[]",
                }
            ]
        if "FROM public.profile_systems" in sql:
            return [
                {
                    "id": system_id,
                    "code": "DEMO_60",
                    "name": "Demo 60",
                    "material": "PVC",
                    "manufacturer": "Demo",
                    "family": "60",
                }
            ]
        if "FROM public.project_positions" in sql:
            return [
                {
                    "position_index": 1,
                    "location_tag": "V-0",
                    "typology": "VENTANA",
                    "width_mm": "900",
                    "height_mm": "1000",
                }
            ]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    ctx = context.build_context(
        org_id, "project_from_documents", {"project_id": str(project_id)}
    )
    assert ctx["surface"] == "project_from_documents"
    doc = ctx["documents"][0]
    assert doc["id"] == str(import_id)
    assert doc["status"] == "REVIEW_READY"
    assert doc["candidates_total"] == 1
    cand = doc["candidates"][0]
    assert cand["key"] == "c1"
    assert cand["opening_type"] == "TILT_TURN_LEFT"
    assert cand["confidence"] == "0.92"
    assert ctx["systems"][0]["id"] == str(system_id)
    assert ctx["positions"][0]["location"] == "V-0"


def test_project_from_documents_projection_empty_project(monkeypatch):
    """§08-WA — no imports → empty documents list; the draft reports there
    is nothing to compile instead of fabricating candidates."""
    org_id = uuid4()
    project_id = uuid4()

    def fake_rows(sql, params=None):
        if "SELECT name, subscription_tier" in sql:
            return [_org_row()]
        if "FROM public.projects WHERE id" in sql:
            return [
                {
                    "id": project_id,
                    "code": "OB-2",
                    "name": "Casa",
                    "client_name": "C",
                    "status": "DRAFT",
                    "current_revision": "REV-A",
                    "total_price_net": Decimal("0"),
                    "total_price_tax": Decimal("0"),
                    "total_price_gross": Decimal("0"),
                }
            ]
        return []

    _patch(monkeypatch, rows_impl=fake_rows)
    ctx = context.build_context(
        org_id, "project_from_documents", {"project_id": str(project_id)}
    )
    assert ctx["documents"] == []
    assert ctx["systems"] == []
    assert ctx["positions"] == []
