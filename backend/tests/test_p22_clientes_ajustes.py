"""P22 — clientes extendidos (RUT, duplicados, fusión, notas) y ajustes por
dominio (snapshot, validaciones comerciales, numeración solo lectura)."""

from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from projects import clients, org_settings


def _client(**over):
    row = {
        "id": uuid4(),
        "name": "Constructora Andina",
        "rut": "11.111.111-1",
        "email": "obras@andina.cl",
        "phone": None,
        "address": None,
        "giro": "Construcción",
        "comuna": None,
        "kind": "COMPANY",
        "merged_into": None,
        "merged_at": None,
        "is_active": True,
        "created_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
    }
    row.update(over)
    return row


def _no_db(monkeypatch, module):
    monkeypatch.setattr(
        module, "transaction", SimpleNamespace(atomic=lambda: nullcontext())
    )


def test_rut_validation_rejects_bad_check_digit():
    with pytest.raises(APIException) as raised:
        clients._validate_rut("76.543.210-1")
    assert raised.value.status_code == 400
    assert raised.value.contract_code == "client_rut_invalid"


def test_rut_validation_accepts_valid_and_empty():
    assert clients._validate_rut("11.111.111-1") == "11.111.111-1"
    assert clients._validate_rut("") is None
    assert clients._validate_rut(None) is None


def test_duplicates_groups_same_normalized_rut(monkeypatch):
    first = {"id": uuid4(), "name": "A", "rut": "76.123.456-7", "email": None,
             "created_at": datetime(2026, 9, 20, tzinfo=timezone.utc)}
    second = {"id": uuid4(), "name": "B", "rut": "76123456-7", "email": None,
              "created_at": datetime(2026, 9, 21, tzinfo=timezone.utc)}
    other = {"id": uuid4(), "name": "C", "rut": "11.111.111-1", "email": None,
             "created_at": datetime(2026, 9, 22, tzinfo=timezone.utc)}
    monkeypatch.setattr(clients, "rows", lambda q, p=(): [first, second, other])
    groups = clients.duplicates(uuid4())
    assert len(groups) == 1
    assert {item["name"] for item in groups[0]["clients"]} == {"A", "B"}


def test_merge_same_client_rejected():
    identity = uuid4()
    with pytest.raises(APIException) as raised:
        clients.merge_clients(uuid4(), identity, identity, uuid4(), "x")
    assert raised.value.status_code == 400


def test_merge_moves_children_and_audits(monkeypatch):
    org, survivor_id, merged_id = uuid4(), uuid4(), uuid4()
    survivor = _client(id=survivor_id, name="Sobreviviente")
    merged = _client(id=merged_id, name="Absorbido")
    calls = []

    def fake_rows(query, parameters=()):
        sql = str(query)
        calls.append((sql, parameters))
        if "FROM public.clients" in sql:
            # Two FOR UPDATE fetches: survivor then merged.
            return [survivor if "%s" in sql and len(calls) == 1 else merged]
        return []

    # client_row is called twice with distinct ids — answer by parameter.
    def fake_rows_by_param(query, parameters=()):
        sql = str(query)
        calls.append((sql, parameters))
        if "FROM public.clients" in sql and parameters and parameters[0] == survivor_id:
            return [survivor]
        if "FROM public.clients" in sql and parameters and parameters[0] == merged_id:
            return [merged]
        return [{"id": uuid4()}]

    monkeypatch.setattr(clients, "rows", fake_rows_by_param)
    monkeypatch.setattr(
        clients, "write", lambda q, p=(): calls.append((str(q), p)) or 1
    )
    monkeypatch.setattr(
        clients, "one_count", lambda q, p=(): {"n": 2}
    )
    # The merge returns the refreshed ficha — outside this test's scope.
    monkeypatch.setattr(clients, "client_detail", lambda org, cid: {"id": cid})
    _no_db(monkeypatch, clients)
    clients.merge_clients(org, survivor_id, merged_id, uuid4(), "dueño")

    sql_text = "\n".join(sql for sql, _ in calls)
    assert "UPDATE public.projects SET client_id=%s" in sql_text
    assert "UPDATE public.client_contacts SET client_id=%s" in sql_text
    assert "UPDATE public.client_addresses SET client_id=%s" in sql_text
    assert "UPDATE public.client_notes SET client_id=%s" in sql_text
    assert "UPDATE public.projects SET client_name=%s" in sql_text
    assert "is_active=FALSE, merged_into=%s" in sql_text
    assert "INSERT INTO public.client_merges" in sql_text
    audit = next(params for sql, params in calls if "client_merges" in sql)
    assert audit[1] == survivor_id and audit[2] == merged_id


def test_add_note_rejects_merged_client(monkeypatch):
    merged = _client(merged_into=uuid4())
    monkeypatch.setattr(clients, "rows", lambda q, p=(): [merged])
    with pytest.raises(APIException) as raised:
        clients.add_note(uuid4(), merged["id"], uuid4(), "autor", "hola")
    assert raised.value.status_code == 409


def test_add_note_inserts_author_and_body(monkeypatch):
    row = _client()
    calls = []
    monkeypatch.setattr(
        clients, "rows", lambda q, p=(): calls.append((str(q), p)) or [row]
    )
    monkeypatch.setattr(
        clients, "write", lambda q, p=(): calls.append((str(q), p)) or 1
    )
    clients.add_note(row["id"], uuid4(), uuid4(), "María", "  nota importante  ")
    insert = next(
        params for sql, params in calls if "INSERT INTO public.client_notes" in sql
    )
    assert insert[3] == "María"
    assert insert[4] == "nota importante"


def test_settings_snapshot_buckets(monkeypatch):
    monkeypatch.setattr(
        org_settings,
        "_organization",
        lambda org: {
            "name": "Vidriería Sur",
            "tax_id": "11.111.111-1",
            "currency": "CLP",
            "doc_paper_size": "LETTER",
            "doc_terms": {"pago": "50 % anticipo"},
            "doc_dekopen_credit": True,
            "doc_validity_days": 15,
            "require_totp": False,
            "remnant_alert_days": 45,
        },
    )
    monkeypatch.setattr(
        org_settings,
        "_rules",
        lambda org: {
            "tax_rate_pct": Decimal("0.1900"),
            "default_margin_pct": Decimal("0.35"),
            "discount_approval_threshold_pct": Decimal("0.10"),
        },
    )
    monkeypatch.setattr(
        org_settings,
        "documentary_backend",
        lambda: nullcontext(),
    )
    monkeypatch.setattr(
        org_settings,
        "commercial_backend",
        lambda: nullcontext(),
    )
    snapshot = org_settings.settings_snapshot(uuid4())
    assert snapshot["company"]["name"] == "Vidriería Sur"
    assert snapshot["commercial"]["doc_validity_days"] == 15
    assert snapshot["commercial"]["tax_rate_pct"] == "0.1900"
    assert snapshot["documents"]["doc_paper_size"] == "LETTER"
    assert snapshot["production"]["remnant_alert_days"] == 45
    assert snapshot["security"]["require_totp"] is False


def test_commercial_margin_band_inversion_rejected(monkeypatch):
    monkeypatch.setattr(org_settings, "commercial_backend", lambda: nullcontext())
    monkeypatch.setattr(org_settings, "documentary_backend", lambda: nullcontext())
    monkeypatch.setattr(org_settings, "_rules", lambda org: {"id": "r1"})
    _no_db(monkeypatch, org_settings)
    with pytest.raises(APIException) as raised:
        org_settings.save_commercial(
            uuid4(), {"margin_min_pct": "0.40", "margin_max_pct": "0.20"}
        )
    assert raised.value.status_code == 400
    assert raised.value.contract_code == "margin_band_invalid"


def test_commercial_fraction_out_of_range_rejected(monkeypatch):
    _no_db(monkeypatch, org_settings)
    with pytest.raises(APIException) as raised:
        org_settings.save_commercial(uuid4(), {"tax_rate_pct": "1.50"})
    assert raised.value.contract_code == "commercial_rule_invalid"


def test_numbering_is_read_only_and_counts(monkeypatch):
    monkeypatch.setattr(org_settings, "documentary_backend", lambda: nullcontext())
    monkeypatch.setattr(
        org_settings,
        "one",
        lambda q, p=(), code=None: {
            "projects": 3,
            "orders": 5,
            "workshop_orders": 2,
            "remnants": 1,
            "receipts": 4,
            "dispatch_notes": 0,
            "invoices": 7,
            "payment_receipts": 9,
            "credit_notes": 0,
        },
    )
    result = org_settings.numbering(uuid4())
    assert result["read_only"] is True
    by_kind = {item["kind"]: item for item in result["items"]}
    assert by_kind["projects"]["next"] == 4
    assert by_kind["purchase_orders"]["next"] == 6
    assert by_kind["payment_receipts"]["prefix"] == "RC-"


def test_company_rut_invalid_rejected():
    with pytest.raises(APIException) as raised:
        org_settings.save_company(uuid4(), {"tax_id": "76.543.210-1"})
    assert raised.value.contract_code == "organization_tax_id_invalid"


def test_company_name_required():
    with pytest.raises(APIException) as raised:
        org_settings.save_company(uuid4(), {"name": "   "})
    assert raised.value.contract_code == "organization_name_invalid"


def test_document_preview_returns_real_markup(monkeypatch):
    monkeypatch.setattr(
        org_settings.org_branding,
        "get_branding",
        lambda org_id: {
            "name": "Vidriería Sur",
            "commercial_name": "",
            "giro": "Ventanas",
            "brand_address": "Calle 1",
            "brand_phone": "",
            "brand_email": "",
            "brand_logo_url": None,
            "brand_color": "#1F6FEB",
            "doc_dekopen_credit": False,
            "doc_paper_size": "LETTER",
            "doc_terms": {"pago": "Anticipo 50 %"},
        },
    )
    html = org_settings.document_preview(uuid4(), {"doc_terms": {"garantia": "2 años"}})
    assert "<style>" in html
    assert "Vidriería Sur" in html
    assert "garantia" in html.lower() or "2 años" in html
