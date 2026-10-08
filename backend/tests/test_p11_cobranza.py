"""P11 — cobranza: calendario de cuotas, timeline de movimientos, vencimiento
de links, honestidad SII en los PDF, proveedor Flow simulado y recordatorio
de cobranza preparado por IA (enviar siempre exige un clic)."""

from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import APIException

from billing.flow import FlowError, MockFlowClient
from documents import renderers
from projects import payment_links, payments, reminders, sii_envio


@contextmanager
def _noop():
    yield


# ── Calendario de cuotas ──────────────────────────────────────────────────

def test_anticipo_pct_reads_terms():
    pct, source = payments._anticipo_pct("50% anticipo, 50% contra entrega")
    assert (pct, source) == (Decimal("50"), "terms")


def test_anticipo_pct_respects_other_explicit_share():
    pct, source = payments._anticipo_pct("30% anticipo, resto contra entrega")
    assert (pct, source) == (Decimal("30"), "terms")


def test_anticipo_pct_falls_back_to_default():
    assert payments._anticipo_pct(None) == (Decimal("50"), "default")
    assert payments._anticipo_pct("contado") == (Decimal("50"), "default")


def _schedule_env(monkeypatch, *, approval=None, emitted=None, delivery=None):
    monkeypatch.setattr(payments, "documentary_backend", _noop)

    def fake_rows(sql, params=None):
        if "FROM public.customer_approvals" in sql:
            return list(approval or [])
        if "FROM public.project_versions" in sql:
            return list(emitted or [])
        if "FROM public.deliveries" in sql:
            return list(delivery or [])
        return []

    monkeypatch.setattr(payments, "rows", fake_rows)


def test_schedule_50_50_marks_anticipo_paid_and_saldo_pending(monkeypatch):
    _schedule_env(
        monkeypatch,
        approval=[{"decided_at": timezone.now()}],
        delivery=[{"scheduled_date": date.today() + timedelta(days=10),
                   "status": "SCHEDULED", "order_type": "INSTALLATION"}],
    )
    deal = {"total": Decimal("1000000"), "currency": "CLP", "sealed_revision": "REV-A"}
    ledger = [
        {"kind": "ANTICIPO", "amount": Decimal("500000"), "voided_at": None},
    ]
    schedule = payments._schedule(
        org_id=uuid4(), project_id=uuid4(), deal=deal,
        payments=ledger, payment_terms="50% anticipo, 50% contra entrega",
    )
    anticipo, saldo = schedule
    assert anticipo["key"] == "ANTICIPO" and anticipo["amount"] == "500000"
    assert anticipo["covered"] == "500000" and anticipo["state"] == "PAID"
    assert anticipo["due_basis"] == "al aprobar"
    assert saldo["key"] == "SALDO" and saldo["amount"] == "500000"
    assert saldo["covered"] == "0" and saldo["state"] == "PENDING"
    assert saldo["due_basis"] == "contra entrega"


def test_schedule_marks_overdue_when_anchor_passed(monkeypatch):
    _schedule_env(
        monkeypatch,
        emitted=[{"emitted_at": timezone.now() - timedelta(days=20)}],
    )
    deal = {"total": Decimal("100000"), "currency": "CLP", "sealed_revision": "REV-A"}
    schedule = payments._schedule(
        org_id=uuid4(), project_id=uuid4(), deal=deal,
        payments=[], payment_terms="50% anticipo",
    )
    assert schedule[0]["state"] == "OVERDUE"
    # Sin entrega programada ni entregada, el saldo no tiene fecha — «contra
    # entrega» no se vence solo.
    assert schedule[1]["due_at"] is None and schedule[1]["state"] == "PENDING"


def test_schedule_voided_payment_does_not_cover(monkeypatch):
    _schedule_env(monkeypatch, approval=[{"decided_at": timezone.now()}])
    deal = {"total": Decimal("200000"), "currency": "CLP", "sealed_revision": "REV-A"}
    ledger = [
        {"kind": "ANTICIPO", "amount": Decimal("100000"),
         "voided_at": "2026-10-01T00:00:00+00:00"},
    ]
    schedule = payments._schedule(
        org_id=uuid4(), project_id=uuid4(), deal=deal,
        payments=ledger, payment_terms=None,
    )
    assert schedule[0]["covered"] == "0" and schedule[0]["state"] == "PENDING"


def test_schedule_empty_without_sealed_revision(monkeypatch):
    _schedule_env(monkeypatch)
    deal = {"total": Decimal("100000"), "currency": "CLP", "sealed_revision": None}
    assert payments._schedule(
        org_id=uuid4(), project_id=uuid4(), deal=deal,
        payments=[], payment_terms=None,
    ) == []


# ── Movimientos ───────────────────────────────────────────────────────────

def test_movements_normalize_union_rows(monkeypatch):
    monkeypatch.setattr(payments, "documentary_backend", _noop)
    captured = {}

    def fake_rows(sql, params=None):
        captured["sql"] = sql
        return [
            {"type": "payment", "id": uuid4(), "kind": "ANTICIPO",
             "amount": Decimal("250000"), "method": "TRANSFER",
             "voided": False, "at": timezone.now(),
             "actor": "dueno@taller.cl", "code": "RC-0001",
             "document_id": uuid4(), "status": None},
            {"type": "envio", "id": uuid4(), "kind": None, "amount": None,
             "method": None, "voided": False, "at": "2026-10-02T10:00:00+00:00",
             "actor": "dueno@taller.cl", "code": "DTE 33 · folio 1",
             "document_id": uuid4(), "status": "OBSERVED"},
        ]

    monkeypatch.setattr(payments, "rows", fake_rows)
    movements = payments._movements(uuid4(), uuid4())
    # La línea de tiempo cruza pagos, anulaciones, links, facturas, notas de
    # crédito y envíos SII — una sola consulta, actor resuelto en SQL y el
    # estado aparte del código humano del documento (nunca enums crudos).
    assert "UNION ALL" in captured["sql"] and "private.user_email" in captured["sql"]
    assert "e.sent_by" in captured["sql"]
    payment, envio = movements
    assert payment["type"] == "payment" and payment["amount"] == "250000"
    assert payment["actor"] == "dueno@taller.cl" and payment["code"] == "RC-0001"
    assert envio["type"] == "envio" and envio["status"] == "OBSERVED"
    assert envio["code"] == "DTE 33 · folio 1" and envio["actor"] == "dueno@taller.cl"


# ── Resumen: forma nueva del payload ──────────────────────────────────────

def test_summary_carries_schedule_movements_sii_and_reminder(monkeypatch):
    monkeypatch.setattr(payments, "documentary_backend", _noop)
    monkeypatch.setattr(payments.transaction, "atomic", _noop)
    monkeypatch.setattr(
        payments, "project_row",
        staticmethod(lambda *a, **k: {"name": "P-1", "code": "DKP-0001"}),
    )
    monkeypatch.setattr(payments.sii, "dtes_by_invoice",
                        lambda *, org_id, project_id: {})
    monkeypatch.setattr(payments.sii, "dtes_by_credit_note",
                        lambda *, org_id, project_id: {})
    monkeypatch.setattr(
        payments.reminders, "latest_draft",
        lambda *, org_id, project_id: {"subject": "s", "body": "b",
                                       "model": "mock", "created_at": "x"},
    )
    monkeypatch.setattr(
        sii_envio, "integration_state",
        lambda *, org_id: {"adapter": "none", "certified": False,
                           "certificate": False, "caf_available": False},
    )

    def fake_rows(sql, params=None):
        if "FROM public.project_versions" in sql and "snapshot_json" in sql:
            return [{
                "revision_code": "REV-0001",
                "snapshot_json": '{"project": {"total_price_gross": "583520",'
                                 ' "currency": "CLP",'
                                 ' "payment_terms": "50% anticipo"}}',
            }]
        if "FROM public.project_payments" in sql and "ORDER BY recorded_at,id" in sql:
            return [{
                "id": uuid4(), "org_id": uuid4(), "project_id": uuid4(),
                "operation_key": "op-1", "kind": "ANTICIPO",
                "amount": Decimal("291760"), "method": "TRANSFER",
                "reference": "T-1", "note": None, "recorded_by": uuid4(),
                "recorded_at": "2026-09-20T10:00:00+00:00",
                "voided_at": None, "voided_by": None, "void_reason": None,
                "created_at": "2026-09-20T10:00:00+00:00",
            }]
        if "FROM public.customer_approvals" in sql:
            return [{"decided_at": timezone.now() - timedelta(days=2)}]
        return []

    monkeypatch.setattr(payments, "rows", fake_rows)
    summary = payments._summary(uuid4(), uuid4(), _project_stub())
    assert summary["schedule"][0]["state"] == "PAID"
    assert summary["schedule"][1]["key"] == "SALDO"
    assert summary["sii"]["adapter"] == "none" and summary["sii"]["certified"] is False
    assert summary["reminder"]["subject"] == "s"
    assert summary["status"] == "PARTIAL"
    assert summary["balance"] == "291760"
    assert isinstance(summary["movements"], list)


def _project_stub():
    return {"id": str(uuid4()), "status": "APPROVED",
            "total_price_gross": Decimal("0")}


# ── Links de pago: vencimiento ────────────────────────────────────────────

def test_public_link_marks_expired_only_for_live_statuses():
    past = timezone.now() - timedelta(hours=1)
    row = {
        "id": uuid4(), "operation_key": "op", "kind": "SALDO",
        "amount": Decimal("100"), "payer_email": "c@c.cl", "subject": "s",
        "status": "PENDING", "environment": "sandbox",
        "url": "https://x", "expires_at": past,
        "flow_order": "1", "flow_token": "t", "project_payment_id": None,
        "deal_total": Decimal("100"), "deal_currency": "CLP",
        "created_at": timezone.now(), "updated_at": timezone.now(),
    }
    assert payment_links._public_link(row)["expired"] is True
    assert {**row, "status": "PAID"} and \
        payment_links._public_link({**row, "status": "PAID"})["expired"] is False
    assert payment_links._public_link({**row, "expires_at": None})["expired"] is False


# ── Proveedor Flow simulado ───────────────────────────────────────────────

def test_mock_flow_mints_sim_charge_and_checkout_url(monkeypatch):
    monkeypatch.setenv("FLOW_SIM_ORIGIN", "http://127.0.0.1:8000")
    client = MockFlowClient(api_url="https://sandbox.flow.cl/api",
                          api_key="x", secret_key="y")
    created = client.create_payment(
        order="op-1", subject="Saldo", amount=Decimal("291760"),
        email="c@c.cl", confirmation_url="https://x/confirm",
        return_url="https://x/return",
    )
    assert created["token"].startswith("sim-")
    assert "/api/v1/billing/flow-sim/" in created["url"]
    status = client.payment_status(created["token"])
    assert status["status"] == 1 and status["commerceOrder"] == "op-1"
    MockFlowClient.decide(created["token"], 2)
    assert client.payment_status(created["token"])["status"] == 2


def test_mock_flow_unknown_token_never_reports_paid():
    client = MockFlowClient(api_url="https://sandbox.flow.cl/api",
                          api_key="x", secret_key="y")
    with pytest.raises(FlowError):
        client.payment_status("sim-inexistente")
    with pytest.raises(FlowError):
        client.payment_by_order("orden-inexistente")


def test_confirm_simulated_requires_mock_enabled(monkeypatch):
    monkeypatch.delenv("FLOW_WS_MOCK", raising=False)
    with pytest.raises(FlowError):
        payment_links.confirm_simulated(token="sim-x")


# ── Honestidad tributaria ─────────────────────────────────────────────────

def test_tributary_notice_internal_when_not_certified():
    notice = renderers._tributary_notice({"tributary": {"certified": False}})
    assert "no válido como documento tributario" in notice


def test_tributary_notice_internal_when_marker_missing():
    notice = renderers._tributary_notice({})
    assert "no válido como documento tributario" in notice


def test_tributary_notice_names_dte_when_certified():
    notice = renderers._tributary_notice({"tributary": {"certified": True}})
    assert "respaldo tributario" in notice
    assert "no válido como documento tributario" not in notice


def test_integration_state_mock_is_never_certified(monkeypatch):
    monkeypatch.setenv("SII_WS_ENVIO_MOCK", "1")
    monkeypatch.delenv("SII_WS_ENVIO_URL", raising=False)
    monkeypatch.delenv("SII_WS_TOKEN", raising=False)
    monkeypatch.setattr(sii_envio, "documentary_backend", _noop)
    monkeypatch.setattr(
        sii_envio, "rows",
        lambda sql, params=None: [{"valid_from": timezone.now() - timedelta(days=1),
                                   "valid_to": timezone.now() + timedelta(days=30)}]
        if "sii_certificates" in sql else [],
    )
    monkeypatch.setattr(
        sii_envio, "one",
        lambda sql, params=None: {"n": 5},
    )
    state = sii_envio.integration_state(org_id=uuid4())
    # El mock recorre el flujo de punta a punta, pero jamás certifica —
    # nada simulado puede parecer documento tributario.
    assert state["adapter"] == "mock"
    assert state["certified"] is False
    assert state["certificate"] is True and state["caf_available"] is True


def test_integration_state_none_without_adapters(monkeypatch):
    for var in ("SII_WS_ENVIO_URL", "SII_WS_TOKEN", "SII_WS_ENVIO_MOCK"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sii_envio, "documentary_backend", _noop)
    monkeypatch.setattr(sii_envio, "rows", lambda *a, **k: [])
    monkeypatch.setattr(sii_envio, "one", lambda *a, **k: {"n": 0})
    state = sii_envio.integration_state(org_id=uuid4())
    assert state == {"adapter": "none", "certified": False,
                     "certificate": False, "caf_available": False}


def test_mock_sii_verdict_observed(monkeypatch):
    monkeypatch.setenv("SII_WS_ENVIO_MOCK_VERDICT", "OBSERVED")
    client = sii_envio._MockSiiClient()
    assert client.query_status(track_id="T-1", rut_emisor="1-9")["status"] == "OBSERVED"
    monkeypatch.setenv("SII_WS_ENVIO_MOCK_VERDICT", "inventado")
    # Un veredicto desconocido nunca llega como estado — cae al default.
    assert client.query_status(track_id="T-1", rut_emisor="1-9")["status"] == "ACCEPTED"


# ── Recordatorio de cobranza ──────────────────────────────────────────────

def _reminder_facts_env(monkeypatch, *, collected="0", client_email="c@c.cl"):
    monkeypatch.setattr(reminders, "documentary_backend", _noop)
    monkeypatch.setattr(reminders.transaction, "atomic", _noop)
    monkeypatch.setattr(
        reminders, "project_row",
        staticmethod(lambda *a, **k: {
            "id": str(uuid4()), "code": "DKP-0001", "name": "Ventanal norte",
            "client_name": "Cliente Uno", "client_email": client_email,
        }),
    )
    monkeypatch.setattr(
        reminders.org_branding, "branding_for_snapshot",
        lambda *, org_id: {"name": "Ventanas del Sur SpA"},
    )

    def fake_rows(sql, params=None):
        if "COALESCE(SUM(amount)" in sql:
            return [{"collected": Decimal(collected)}]
        if "FROM public.project_versions" in sql:
            return [{"snapshot_json": '{"project": {"total_price_gross": "583520",'
                                      ' "currency": "CLP",'
                                      ' "payment_terms": "50% anticipo"}}'}]
        return []

    monkeypatch.setattr(reminders, "rows", fake_rows)


def test_draft_reminder_returns_audited_draft(monkeypatch):
    _reminder_facts_env(monkeypatch, collected="291760")
    monkeypatch.setattr(
        reminders.gateway, "invoke",
        lambda **kw: {"output": '{"subject": "Saldo pendiente",'
                               ' "body": "Estimado cliente…"}',
                      "audit_id": "a-1", "model": "mock-cobranza-1",
                      "credits_debited": 2},
    )
    draft = reminders.draft_reminder(
        org_id=uuid4(), project_id=uuid4(), actor_id=uuid4(), operation_key="op-1"
    )
    assert draft["subject"] == "Saldo pendiente"
    assert draft["amount_due"] == "291760" and draft["currency"] == "CLP"
    assert draft["client_email"] == "c@c.cl"


def test_draft_reminder_rejects_non_json_output(monkeypatch):
    _reminder_facts_env(monkeypatch)
    monkeypatch.setattr(
        reminders.gateway, "invoke",
        lambda **kw: {"output": "no es json", "audit_id": "a-1",
                      "model": "mock", "credits_debited": 2},
    )
    with pytest.raises(APIException) as info:
        reminders.draft_reminder(
            org_id=uuid4(), project_id=uuid4(), actor_id=uuid4(),
            operation_key="op-1",
        )
    assert info.value.status_code == 502


def test_send_reminder_requires_client_email(monkeypatch):
    _reminder_facts_env(monkeypatch, client_email=None)
    with pytest.raises(APIException) as info:
        reminders.send_reminder(
            org_id=uuid4(), project_id=uuid4(), actor_id=uuid4(),
            subject="s", body="b",
        )
    assert info.value.status_code == 422


def test_send_reminder_rejects_empty_message(monkeypatch):
    _reminder_facts_env(monkeypatch)
    with pytest.raises(APIException) as info:
        reminders.send_reminder(
            org_id=uuid4(), project_id=uuid4(), actor_id=uuid4(),
            subject=" ", body="",
        )
    assert info.value.status_code == 422


def test_send_reminder_enqueues_client_mail(monkeypatch):
    _reminder_facts_env(monkeypatch)
    sent = {}
    monkeypatch.setattr(
        reminders.mail_service, "deliver_client_message",
        lambda **kw: sent.update(kw) or {"id": uuid4(), "status": "QUEUED"},
    )
    result = reminders.send_reminder(
        org_id=uuid4(), project_id=uuid4(), actor_id=uuid4(),
        subject="Saldo pendiente", body="Estimado cliente…",
    )
    assert result["status"] == "QUEUED" and result["to"] == "c@c.cl"
    assert sent["template"] == "collection_reminder"
    assert sent["to_email"] == "c@c.cl"
