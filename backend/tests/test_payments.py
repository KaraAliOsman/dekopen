"""Cobranza ledger: idempotent recording, voiding, and sealed-deal balance."""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

from projects import payments, views as project_views
from projects.serializers import PaymentRecordSerializer


@contextmanager
def _noop():
    yield


def _project(**over):
    return {
        "id": uuid4(),
        "status": "APPROVED",
        "total_price_gross": Decimal("1000000"),
        **over,
    }


def _payment_row(**over):
    return {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "operation_key": "op-12345678",
        "kind": "ANTICIPO",
        "amount": Decimal("400000"),
        "method": "TRANSFER",
        "reference": "TRX-1",
        "note": None,
        "recorded_by": uuid4(),
        "recorded_at": "2026-09-20T10:00:00+00:00",
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
        "created_at": "2026-09-20T10:00:00+00:00",
        **over,
    }


def _runner(captured, existing=None, payments_list=None, sealed_gross=None,
            sealed_currency="CLP", applied=True, invoices_list=None,
            envios_list=None):
    def fake_rows(sql, params=None):
        captured.append((sql, params))
        if "SELECT * FROM public.project_payments WHERE org_id=%s AND operation_key=%s" in sql:
            return list(existing or [])
        if "FROM public.project_versions" in sql:
            if sealed_gross is None:
                return []
            return [
                {
                    "revision_code": "REV-A",
                    "snapshot_json": {
                        "project": {
                            "total_price_gross": str(sealed_gross),
                            "currency": sealed_currency,
                        }
                    },
                }
            ]
        if "private.applied_pricing_currency" in sql:
            return [{"currency": "CLP"}] if applied else []
        if "FROM public.tenancy_organizations" in sql:
            return [{"currency": "CLP"}]
        if "COALESCE(SUM(amount)" in sql:
            return [
                {
                    "collected": sum(
                        (p["amount"] for p in (payments_list or []) if p["voided_at"] is None),
                        Decimal("0"),
                    )
                }
            ]
        if "FROM public.project_payments" in sql and "ORDER BY recorded_at,id" in sql:
            return list(payments_list or [])
        if "FROM public.project_invoices" in sql:
            return list(invoices_list or [])
        if "FROM public.sii_envios" in sql:
            return list(envios_list or [])
        if "INSERT INTO public.project_payments" in sql:
            return [] if existing else [_payment_row(project_id=params[1])]
        if "UPDATE public.project_payments" in sql:
            return [_payment_row(voided_at="2026-09-21T10:00:00+00:00")]
        return []

    return fake_rows


@pytest.fixture
def env(monkeypatch):
    captured = []
    monkeypatch.setattr(payments, "documentary_backend", _noop)
    monkeypatch.setattr(payments.transaction, "atomic", _noop)
    monkeypatch.setattr(
        payments, "project_row", staticmethod(lambda org_id, project_id, **kw: _project())
    )
    monkeypatch.setattr(
        payments.sii,
        "dtes_by_invoice",
        lambda *, org_id, project_id: {},
    )
    monkeypatch.setattr(
        payments.sii,
        "dtes_by_credit_note",
        lambda *, org_id, project_id: {},
    )
    monkeypatch.setattr(
        payments,
        "issue_receipt",
        lambda **kw: {
            "id": str(uuid4()),
            "receipt_code": "RC-0001",
            "payment_id": str(kw["payment"]["id"]),
            "created_at": "2026-09-20T10:00:00+00:00",
        },
    )
    return captured


def _patch_rows(monkeypatch, captured, **kwargs):
    monkeypatch.setattr(payments, "rows", _runner(captured, **kwargs))


def test_summary_invoice_dte_carries_envio_badge(monkeypatch, env):
    """The cobranza listing is where the envío chip lives — the summary must
    attach the same envío badge the invoice listing builds."""
    invoice = {
        "id": uuid4(),
        "invoice_code": "FAC-0001",
        "payload_json": {"revision_code": "REV-A"},
        "created_at": "2026-09-20T10:00:00+00:00",
    }
    dte = {"id": str(uuid4()), "folio": 7}
    envio_row = {
        "id": uuid4(),
        "invoice_id": invoice["id"],
        "status": "PENDING",
        "track_id": None,
        "attempted": True,
    }
    _patch_rows(
        monkeypatch,
        env,
        invoices_list=[invoice],
        envios_list=[envio_row],
        sealed_gross=Decimal("800000"),
    )
    monkeypatch.setattr(
        payments.sii,
        "dtes_by_invoice",
        lambda *, org_id, project_id: {str(invoice["id"]): dte},
    )
    out = payments.list_payments(org_id=uuid4(), project_id=uuid4())
    assert out["invoices"][0]["dte"]["envio"] == {
        "id": str(envio_row["id"]),
        "status": "PENDING",
        "track_id": None,
        "attempted": True,
    }


def test_record_payment_inserts_and_returns_sealed_balance(monkeypatch, env):
    sealed_row = _payment_row()
    _patch_rows(
        monkeypatch,
        env,
        payments_list=[sealed_row],
        sealed_gross=Decimal("800000"),
    )
    out = payments.record_payment(
        org_id=uuid4(),
        project_id=uuid4(),
        actor_id=uuid4(),
        data={
            "operation_key": "op-12345678",
            "kind": "ANTICIPO",
            "amount": Decimal("400000"),
            "method": "TRANSFER",
            "reference": "TRX-1",
        },
    )
    inserts = [sql for sql, _ in env if "INSERT INTO public.project_payments" in sql]
    assert len(inserts) == 1
    assert out["collected"] == "400000"
    assert out["quote_total_gross"] == "800000"
    assert out["balance"] == "400000"
    assert out["status"] == "PARTIAL"
    assert out["payment"]["kind"] == "ANTICIPO"


def test_record_payment_replay_returns_existing_without_insert(monkeypatch, env):
    existing = _payment_row()
    _patch_rows(monkeypatch, env, existing=[existing], payments_list=[existing])
    out = payments.record_payment(
        org_id=uuid4(),
        project_id=existing["project_id"],
        actor_id=uuid4(),
        data={"operation_key": "op-12345678", "kind": "ANTICIPO",
              "amount": Decimal("400000"), "method": "TRANSFER"},
    )
    inserts = [sql for sql, _ in env if "INSERT INTO public.project_payments" in sql]
    assert inserts == []
    assert out["payment"]["id"] == str(existing["id"])


def test_record_payment_replay_survives_pricing_reset(monkeypatch, env):
    existing = _payment_row()
    # applied=False: the live deal retired after the payment was recorded —
    # the replay still returns the committed row instead of payment_requires_deal.
    _patch_rows(
        monkeypatch, env, existing=[existing], payments_list=[existing], applied=False
    )
    out = payments.record_payment(
        org_id=uuid4(),
        project_id=existing["project_id"],
        actor_id=uuid4(),
        data={"operation_key": "op-12345678", "kind": "ANTICIPO",
              "amount": Decimal("400000"), "method": "TRANSFER"},
    )
    assert out["payment"]["id"] == str(existing["id"])


def test_record_payment_rejects_fractional_clp(monkeypatch, env):
    _patch_rows(monkeypatch, env, sealed_gross=Decimal("800000"))
    with pytest.raises(APIException) as failure:
        payments.record_payment(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            data={"operation_key": "op-12345678", "kind": "ANTICIPO",
                  "amount": Decimal("0.01"), "method": "TRANSFER"},
        )
    assert failure.value.contract_code == "payment_fractional_currency"


def test_record_payment_allows_fractional_usd(monkeypatch, env):
    _patch_rows(
        monkeypatch, env, sealed_gross=Decimal("1250.50"), sealed_currency="USD"
    )
    out = payments.record_payment(
        org_id=uuid4(),
        project_id=uuid4(),
        actor_id=uuid4(),
        data={"operation_key": "op-12345678", "kind": "ANTICIPO",
              "amount": Decimal("250.50"), "method": "TRANSFER"},
    )
    assert out["payment"]["amount"] == "400000"  # row written by the mock
    inserts = [sql for sql, _ in env if "INSERT INTO public.project_payments" in sql]
    assert len(inserts) == 1


def test_record_payment_rejects_future_recorded_at(monkeypatch, env):
    _patch_rows(monkeypatch, env, sealed_gross=Decimal("800000"))
    with pytest.raises(APIException) as failure:
        payments.record_payment(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            data={
                "operation_key": "op-12345678",
                "kind": "ANTICIPO",
                "amount": Decimal("400000"),
                "method": "TRANSFER",
                "recorded_at": timezone.now() + timedelta(days=1),
            },
        )
    assert failure.value.contract_code == "payment_recorded_in_future"


def test_record_payment_operation_key_conflict_on_other_project(monkeypatch, env):
    existing = _payment_row()
    _patch_rows(monkeypatch, env, existing=[existing])
    with pytest.raises(APIException) as failure:
        payments.record_payment(
            org_id=uuid4(),
            project_id=uuid4(),  # a different project than the stored row
            actor_id=uuid4(),
            data={"operation_key": "op-12345678", "kind": "ANTICIPO",
                  "amount": Decimal("400000"), "method": "TRANSFER"},
        )
    assert failure.value.contract_code == "payment_operation_conflict"


def test_void_excludes_payment_from_collected(monkeypatch, env):
    voided = _payment_row(voided_at="2026-09-21T10:00:00+00:00")
    _patch_rows(monkeypatch, env, payments_list=[voided])
    out = payments.void_payment(
        org_id=uuid4(),
        project_id=voided["project_id"],
        payment_id=voided["id"],
        actor_id=uuid4(),
        data={"reason": "Duplicado"},
    )
    assert out["collected"] == "0"
    assert out["status"] == "PENDING"
    assert out["payments"][0]["voided_at"] is not None


def test_void_missing_payment_raises_404(monkeypatch, env):
    def no_rows(sql, params=None):
        env.append((sql, params))
        return []

    monkeypatch.setattr(payments, "rows", no_rows)
    with pytest.raises(APIException) as failure:
        payments.void_payment(
            org_id=uuid4(), project_id=uuid4(), payment_id=uuid4(),
            actor_id=uuid4(), data={},
        )
    assert failure.value.contract_code == "payment_not_found"


def test_balance_uses_live_totals_when_no_sealed_version(monkeypatch, env):
    _patch_rows(monkeypatch, env, payments_list=[_payment_row(amount=Decimal("1000000"))])
    out = payments.list_payments(org_id=uuid4(), project_id=uuid4())
    assert out["quote_total_gross"] == "1000000"  # live project total
    assert out["balance"] == "0"
    assert out["status"] == "PAID"


def test_project_without_pricing_authority_reports_no_deal(monkeypatch, env):
    _patch_rows(monkeypatch, env, applied=False)
    out = payments.list_payments(org_id=uuid4(), project_id=uuid4())
    assert out["status"] == "NO_DEAL"
    assert out["quote_total_gross"] is None
    assert out["balance"] is None


def test_record_payment_rejected_without_pricing_authority(monkeypatch, env):
    _patch_rows(monkeypatch, env, applied=False)
    with pytest.raises(APIException) as failure:
        payments.record_payment(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            data={"operation_key": "op-12345678", "kind": "ANTICIPO",
                  "amount": Decimal("100"), "method": "TRANSFER"},
        )
    assert failure.value.contract_code == "payment_requires_deal"


def test_deal_currency_comes_from_sealed_snapshot(monkeypatch, env):
    _patch_rows(monkeypatch, env, sealed_gross=Decimal("1250.50"), sealed_currency="USD")
    out = payments.list_payments(org_id=uuid4(), project_id=uuid4())
    assert out["currency"] == "USD"
    assert out["quote_total_gross"] == "1250.50"


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "ANTICIPO", "amount": Decimal("100"), "method": "TRANSFER"},
        {"operation_key": "op-12345678", "kind": "BAD", "amount": Decimal("100"), "method": "TRANSFER"},
        {"operation_key": "op-12345678", "kind": "ANTICIPO", "amount": Decimal("0"), "method": "TRANSFER"},
        {"operation_key": "op-12345678", "kind": "ANTICIPO", "amount": Decimal("100"), "method": "GOLD"},
        {"operation_key": "op-12345678", "kind": "ANTICIPO", "amount": Decimal("100"), "method": "TRANSFER", "org_id": str(uuid4())},
    ],
)
def test_record_serializer_rejects_invalid(data):
    assert not PaymentRecordSerializer(data=data).is_valid()


def _client(monkeypatch, role: str):
    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        if role not in allowed:
            raise APIException(code="pricing_permission_denied", detail="denied")
        yield token, SimpleNamespace(), org_id

    monkeypatch.setattr(project_views, "scope", fake_scope)
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True), token=object())
    return client, token, org_id


def test_payments_list_requires_reader_role(monkeypatch):
    client, _, org_id = _client(monkeypatch, "WORKSHOP_MANAGER")
    monkeypatch.setattr(
        payments, "list_payments", lambda **kw: {"payments": [], "collected": "0"}
    )
    assert client.get(f"/api/v1/projects/{uuid4()}/payments/").status_code == 200


def test_payments_record_forbidden_for_installer(monkeypatch):
    client, _, org_id = _client(monkeypatch, "INSTALLER")
    calls = []
    monkeypatch.setattr(
        payments, "record_payment", lambda **kw: calls.append(kw) or {}
    )
    response = client.post(
        f"/api/v1/projects/{uuid4()}/payments/",
        {
            "operation_key": "op-12345678",
            "kind": "ANTICIPO",
            "amount": "100.00",
            "method": "CASH",
        },
        format="json",
    )
    assert calls == []
    assert response.status_code >= 400


def test_record_payment_requires_sealed_deal(monkeypatch, env):
    """Applied pricing without a sealed revision is not collectible (F18)."""
    _patch_rows(monkeypatch, env, applied=True, sealed_gross=None)
    with pytest.raises(APIException) as failure:
        payments.record_payment(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            data={"operation_key": "op-12345678", "kind": "ANTICIPO",
                  "amount": Decimal("100"), "method": "TRANSFER"},
        )
    assert failure.value.contract_code == "payment_requires_sealed_deal"


def test_record_payment_rejects_over_collection(monkeypatch, env):
    """A payment must fit inside the outstanding balance (F19)."""
    _patch_rows(
        monkeypatch,
        env,
        sealed_gross="400000",
        payments_list=[_payment_row(amount=Decimal("350000"))],
    )
    with pytest.raises(APIException) as failure:
        payments.record_payment(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            data={"operation_key": "op-99999999", "kind": "SALDO",
                  "amount": Decimal("60000"), "method": "TRANSFER"},
        )
    assert failure.value.contract_code == "payment_exceeds_balance"
