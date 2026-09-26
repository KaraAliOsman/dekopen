"""Flow payment links: dispatch claims, verified settlement, recovery."""

from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from billing.flow import FlowError
from projects import payment_links


@contextmanager
def _noop():
    yield


class _Client:
    def __init__(self, *, api_url="https://sandbox.flow.cl/api", behavior=None):
        self.api_url = api_url
        self.behavior = behavior or {}
        self.calls = []

    def create_payment(self, **kwargs):
        self.calls.append(("create", kwargs))
        if self.behavior.get("create_error"):
            raise FlowError("flow_unavailable", uncertain=True)
        return {"url": "https://sandbox.flow.cl/pay", "token": "tok-1", "flowOrder": 99}

    def redirect_url(self, response):
        return "https://sandbox.flow.cl/pay?token=tok-1"

    def payment_status(self, token):
        self.calls.append(("status", token))
        return self.behavior.get(
            "status",
            {"flowOrder": 99, "status": 2, "commerceOrder": "op-link-1",
             "amount": "250000", "currency": "CLP"},
        )

    def payment_by_order(self, order):
        self.calls.append(("by_order", order))
        return self.behavior.get(
            "by_order",
            {"flowOrder": 99, "status": 2, "commerceOrder": "op-link-1",
             "amount": "250000", "currency": "CLP"},
        )


def _integration(**over):
    return {
        "org_id": uuid4(),
        "provider": "FLOW",
        "api_url": "https://sandbox.flow.cl/api",
        "api_key": "AB12CD34EF56",
        "secret_key": "S3CR3T-KEY-0987",
        "payer_return_url": "https://app.test/pago/retorno",
        "enabled": True,
        "created_at": "2026-09-23T10:00:00+00:00",
        "updated_at": "2026-09-23T10:00:00+00:00",
        **over,
    }


def _link(**over):
    return {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "operation_key": "op-link-1",
        "kind": "ANTICIPO",
        "amount": Decimal("250000"),
        "payer_email": "cliente@correo.cl",
        "subject": "Ventanales — anticipo",
        "status": "PENDING",
        "environment": "sandbox",
        "flow_order": "99",
        "flow_token": "tok-1",
        "url": "https://sandbox.flow.cl/pay?token=tok-1",
        "project_payment_id": None,
        "deal_total": Decimal("250000"),
        "deal_currency": "CLP",
        "created_by": uuid4(),
        "created_at": "2026-09-23T10:00:00+00:00",
        "updated_at": "2026-09-23T10:00:00+00:00",
        **over,
    }


def _payment_row(**over):
    return {
        "id": uuid4(),
        "kind": "ANTICIPO",
        "amount": Decimal("250000"),
        "method": "OTHER",
        "reference": "FLOW 99",
        "note": "Cobro en línea",
        "recorded_by": None,
        "recorded_at": "2026-09-23T10:00:00+00:00",
        "voided_at": None,
        "void_reason": None,
        "created_at": "2026-09-23T10:00:00+00:00",
        **over,
    }


def _patch_env(monkeypatch, rows_impl, client=None):
    monkeypatch.setattr(payment_links, "documentary_backend", _noop)
    monkeypatch.setattr(payment_links.transaction, "atomic", _noop)

    def with_collected(sql, params=None):
        if "COALESCE(SUM(amount)" in sql:
            return [{"collected": Decimal("0")}]
        return rows_impl(sql, params)

    monkeypatch.setattr(payment_links, "rows", with_collected)
    monkeypatch.setattr(
        payment_links, "project_row", staticmethod(lambda *a, **k: {"name": "P-1"})
    )
    monkeypatch.setattr(
        payment_links,
        "_deal",
        lambda *a, **k: {
            "total": Decimal("250000"),
            "currency": "CLP",
            "sealed_revision": "REV-A",
        },
    )
    receipts = []
    monkeypatch.setattr(
        payment_links,
        "issue_receipt",
        lambda **kwargs: receipts.append(kwargs) or {},
    )
    if client is not None:
        monkeypatch.setattr(payment_links, "_client", lambda integration: client)
    return receipts


def test_create_link_requires_integration(monkeypatch):
    _patch_env(monkeypatch, lambda sql, params=None: [])
    with pytest.raises(APIException) as failure:
        payment_links.create_link(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            data={
                "operation_key": "op-link-1",
                "kind": "ANTICIPO",
                "amount": Decimal("250000"),
                "payer_email": "a@b.cl",
            },
        )
    assert failure.value.contract_code == "flow_not_configured"


def test_create_link_replay_returns_existing(monkeypatch):
    link = _link()

    def fake_rows(sql, params=None):
        if "FROM public.org_payment_integrations" in sql:
            return [_integration()]
        if "FROM public.project_payment_links" in sql:
            return [link]
        return []

    _patch_env(monkeypatch, fake_rows, client=_Client())
    out = payment_links.create_link(
        org_id=link["org_id"],
        project_id=link["project_id"],
        actor_id=uuid4(),
        data={
            "operation_key": "op-link-1",
            "kind": "ANTICIPO",
            "amount": Decimal("250000"),
            "payer_email": "a@b.cl",
        },
    )
    assert out["link"]["id"] == str(link["id"])


def test_create_link_dispatches_and_stores_redirect(monkeypatch):
    integration = _integration()
    client = _Client()
    calls = []

    def fake_rows(sql, params=None):
        calls.append(sql)
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "INSERT INTO public.project_payment_links" in sql:
            return [_link(status="DISPATCHING")]
        if "UPDATE public.project_payment_links" in sql:
            return [_link()]
        return []

    _patch_env(monkeypatch, fake_rows, client=client)
    out = payment_links.create_link(
        org_id=integration["org_id"],
        project_id=uuid4(),
        actor_id=uuid4(),
        data={
            "operation_key": "op-link-1",
            "kind": "ANTICIPO",
            "amount": Decimal("250000"),
            "payer_email": "a@b.cl",
        },
    )
    assert client.calls[0][0] == "create"
    assert client.calls[0][1]["order"] == "op-link-1"
    assert client.calls[0][1]["amount"] == Decimal("250000")
    assert out["link"]["status"] == "PENDING"
    assert out["link"]["url"].startswith("https://sandbox.flow.cl")


def test_create_link_marks_uncertain_on_provider_failure(monkeypatch):
    integration = _integration()
    updates = []

    def fake_rows(sql, params=None):
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "INSERT INTO public.project_payment_links" in sql:
            return [_link(status="DISPATCHING")]
        if "UPDATE public.project_payment_links" in sql:
            updates.append(sql)
            return [_link(status="UNCERTAIN")]
        return []

    _patch_env(monkeypatch, fake_rows, client=_Client(behavior={"create_error": True}))
    with pytest.raises(APIException) as failure:
        payment_links.create_link(
            org_id=integration["org_id"],
            project_id=uuid4(),
            actor_id=uuid4(),
            data={
                "operation_key": "op-link-1",
                "kind": "ANTICIPO",
                "amount": Decimal("250000"),
                "payer_email": "a@b.cl",
            },
        )
    assert failure.value.contract_code == "payment_link_dispatch_failed"
    assert any("UNCERTAIN" in sql for sql in updates)


def test_confirm_settles_payment_into_ledger(monkeypatch):
    link = _link()
    integration = _integration(org_id=link["org_id"])
    inserts = []

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        if "INSERT INTO public.project_payments" in sql:
            inserts.append(sql)
            return [_payment_row()]
        if "UPDATE public.project_payment_links" in sql:
            return [_link(status="PAID", project_payment_id=uuid4())]
        return []

    client = _Client()
    receipts = _patch_env(monkeypatch, fake_rows, client=client)
    out = payment_links.confirm_link(link_id=link["id"], token="tok-1")
    assert out["link"]["status"] == "PAID"
    assert len(inserts) == 1
    assert "ON CONFLICT" in inserts[0]
    assert len(receipts) == 1
    assert receipts[0]["actor_id"] == link["created_by"]
    assert receipts[0]["deal"] == {"total": Decimal("250000"), "currency": "CLP"}


def test_confirm_seals_frozen_total_when_repriced(monkeypatch):
    """The comprobante reflects the total the link presented to the payer:
    repricing between mint and settle must not rewrite the frozen deal."""
    link = _link()
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        if "INSERT INTO public.project_payments" in sql:
            return [_payment_row()]
        if "UPDATE public.project_payment_links" in sql:
            return [_link(status="PAID", project_payment_id=uuid4())]
        return []

    client = _Client()
    receipts = _patch_env(monkeypatch, fake_rows, client=client)
    monkeypatch.setattr(
        payment_links,
        "_deal",
        lambda *a, **k: {"total": Decimal("400000"), "currency": "CLP"},
    )
    out = payment_links.confirm_link(link_id=link["id"], token="tok-1")
    assert out["link"]["status"] == "PAID"
    assert receipts[0]["deal"] == {"total": Decimal("250000"), "currency": "CLP"}


def test_confirm_settles_on_frozen_deal_when_pricing_reset(monkeypatch):
    """A verified payment must never strand: if the live deal is gone, the
    receipt falls back to the snapshot frozen on the link at creation."""
    link = _link()
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        if "INSERT INTO public.project_payments" in sql:
            return [_payment_row()]
        if "UPDATE public.project_payment_links" in sql:
            return [_link(status="PAID", project_payment_id=uuid4())]
        return []

    client = _Client()
    receipts = _patch_env(monkeypatch, fake_rows, client=client)
    monkeypatch.setattr(payment_links, "_deal", lambda *a, **k: None)
    out = payment_links.confirm_link(link_id=link["id"], token="tok-1")
    assert out["link"]["status"] == "PAID"
    assert len(receipts) == 1
    assert receipts[0]["deal"] == {"total": Decimal("250000"), "currency": "CLP"}


def test_confirm_settles_on_live_deal_for_legacy_link(monkeypatch):
    """Links minted before the freeze carry no snapshot: the live deal is
    used when it exists."""
    link = _link(deal_total=None, deal_currency=None)
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        if "INSERT INTO public.project_payments" in sql:
            return [_payment_row()]
        if "UPDATE public.project_payment_links" in sql:
            return [_link(status="PAID", project_payment_id=uuid4())]
        return []

    client = _Client()
    receipts = _patch_env(monkeypatch, fake_rows, client=client)
    out = payment_links.confirm_link(link_id=link["id"], token="tok-1")
    assert out["link"]["status"] == "PAID"
    assert receipts[0]["deal"] == {
        "total": Decimal("250000"),
        "currency": "CLP",
        "sealed_revision": "REV-A",
    }


def test_confirm_settles_without_any_deal(monkeypatch):
    """Links minted before the deal freeze carry no snapshot — the charge
    still settles and the comprobante renders an empty balance."""
    link = _link(deal_total=None, deal_currency=None)
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        if "INSERT INTO public.project_payments" in sql:
            return [_payment_row()]
        if "UPDATE public.project_payment_links" in sql:
            return [_link(status="PAID", project_payment_id=uuid4())]
        return []

    client = _Client()
    receipts = _patch_env(monkeypatch, fake_rows, client=client)
    monkeypatch.setattr(payment_links, "_deal", lambda *a, **k: None)
    out = payment_links.confirm_link(link_id=link["id"], token="tok-1")
    assert out["link"]["status"] == "PAID"
    assert receipts[0]["deal"] == {"total": None, "currency": "CLP"}


def test_confirm_rejects_binding_mismatch(monkeypatch):
    link = _link()
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        return []

    client = _Client(
        behavior={
            "status": {"flowOrder": 99, "status": 2, "commerceOrder": "OTHER-ORDER",
                       "amount": "250000", "currency": "CLP"}
        }
    )
    _patch_env(monkeypatch, fake_rows, client=client)
    with pytest.raises(FlowError, match="flow_payment_binding_mismatch"):
        payment_links.confirm_link(link_id=link["id"], token="tok-1")


def test_confirm_paid_link_is_idempotent(monkeypatch):
    link = _link(status="PAID", project_payment_id=uuid4())
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        return []

    _patch_env(monkeypatch, fake_rows, client=_Client())
    out = payment_links.confirm_link(link_id=link["id"], token="tok-1")
    assert out["link"]["status"] == "PAID"


def test_confirm_failed_observation_marks_link_failed(monkeypatch):
    link = _link()
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "SELECT org_id FROM public.project_payment_links" in sql:
            return [{"org_id": link["org_id"]}]
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FOR UPDATE" in sql:
            return [link]
        if "UPDATE public.project_payment_links" in sql:
            return [_link(status="FAILED")]
        return []

    client = _Client(
        behavior={
            "status": {"flowOrder": 99, "status": 3, "commerceOrder": "op-link-1",
                       "amount": "250000", "currency": "CLP"}
        }
    )
    _patch_env(monkeypatch, fake_rows, client=client)
    out = payment_links.confirm_link(link_id=link["id"], token="tok-1")
    assert out["link"]["status"] == "FAILED"


def test_recover_link_uses_order_lookup(monkeypatch):
    link = _link(status="UNCERTAIN", flow_order=None)
    integration = _integration(org_id=link["org_id"])

    def fake_rows(sql, params=None):
        if "FROM public.org_payment_integrations" in sql:
            return [integration]
        if "FROM public.project_payment_links" in sql:
            return [link]
        if "INSERT INTO public.project_payments" in sql:
            return [_payment_row()]
        if "UPDATE public.project_payment_links" in sql:
            return [_link(status="PAID")]
        return []

    client = _Client()
    _patch_env(monkeypatch, fake_rows, client=client)
    out = payment_links.recover_link(org_id=link["org_id"], link_id=link["id"])
    assert client.calls[0] == ("by_order", "op-link-1")
    assert out["link"]["status"] == "PAID"


def test_integration_status_never_leaks_secret(monkeypatch):
    def fake_rows(sql, params=None):
        if "FROM public.org_payment_integrations" in sql:
            return [_integration()]
        return []

    _patch_env(monkeypatch, fake_rows)
    status = payment_links.get_integration(org_id=uuid4())
    assert status["configured"] is True
    assert status["api_key_preview"] == "AB12…56"
    assert "secret" not in repr(status)


def test_save_integration_keeps_stored_secret_on_update(monkeypatch):
    captured = []

    def fake_rows(sql, params=None):
        captured.append((sql, params))
        if "SELECT secret_key FROM public.org_payment_integrations" in sql:
            return [{"secret_key": "S3CR3T-KEY-0987"}]
        if "INSERT INTO public.org_payment_integrations" in sql:
            return [{"org_id": params[0]}]
        if "FROM public.org_payment_integrations" in sql:
            return [_integration()]
        return []

    monkeypatch.setattr(payment_links, "documentary_backend", _noop)
    monkeypatch.setattr(payment_links.transaction, "atomic", _noop)
    monkeypatch.setattr(payment_links, "rows", fake_rows)
    payment_links.save_integration(
        org_id=uuid4(),
        data={
            "api_url": "https://www.flow.cl/api",
            "api_key": "NEWKEY123456",
            "payer_return_url": "",
            "enabled": True,
        },
    )
    insert = [p for s, p in captured if "INSERT INTO public.org_payment_integrations" in s]
    assert insert[0][3] == "S3CR3T-KEY-0987"  # stored secret survives the update


def test_save_integration_requires_secret_for_new_org(monkeypatch):
    monkeypatch.setattr(payment_links, "documentary_backend", _noop)
    monkeypatch.setattr(payment_links.transaction, "atomic", _noop)
    monkeypatch.setattr(payment_links, "rows", lambda *_a, **_k: [])
    with pytest.raises(APIException) as failure:
        payment_links.save_integration(
            org_id=uuid4(),
            data={
                "api_url": "https://sandbox.flow.cl/api",
                "api_key": "NEWKEY123456",
            },
        )
    assert failure.value.contract_code == "flow_secret_required"
