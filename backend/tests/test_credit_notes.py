"""Nota de crédito emission — replay, sealed invoice reference, and storage."""

import json
from contextlib import contextmanager
from uuid import uuid4

import pytest

from projects import credit_notes, sii_envio


class _Storage:
    def __init__(self):
        self.uploads = []
        self.deleted = []

    def upload_immutable(self, object_key, content, content_type):
        self.uploads.append((object_key, content, content_type))

    def delete_object(self, object_key):
        self.deleted.append(object_key)

    def signed_url(self, object_key, expires_in=None):
        return f"https://storage.test/{object_key}?exp={expires_in}"


@contextmanager
def _noop(*args, **kwargs):
    yield


def _invoice_row(over=None):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "invoice_code": "FAC-0001",
        "payload_json": {
            "invoice_code": "FAC-0001",
            "issued_at": "2026-10-01T10:00:00+00:00",
            "revision_code": "REV-A",
            "project": {
                "code": "PRY-001",
                "name": "Edificio Norte",
                "client_name": "Constructora Andina",
                "client_rut": "76.543.210-1",
                "delivery_address": "Av. Providencia 1234",
                "currency": "CLP",
                "payment_terms": "Contado",
            },
            "deal": {
                "total_net": "1000000",
                "total_tax": "190000",
                "total_gross": "1190000",
            },
            "positions": [
                {"position_index": 1, "typology": "SLIDING_2L", "quantity": 2}
            ],
        },
        "created_at": "2026-10-01T10:00:00+00:00",
    }
    row.update(over or {})
    return row


def _note_row(over=None):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "invoice_id": uuid4(),
        "credit_code": "NC-0001",
        "payload_json": {"invoice": {"invoice_code": "FAC-0001"}},
        "storage_bucket": "documents",
        "storage_object_key": "org_x/projects/y/credit-notes/nc-0001_ab.pdf",
        "file_sha256": "b" * 64,
        "media_type": "application/pdf",
        "byte_size": 1024,
        "created_by": uuid4(),
        "created_at": "2026-10-02T10:00:00+00:00",
    }
    row.update(over or {})
    return row


def _project():
    return {
        "id": uuid4(),
        "code": "PRY-001",
        "name": "Edificio Norte",
        "client_name": "Constructora Andina",
        "client_rut": "76.543.210-1",
        "delivery_address": "Av. Providencia 1234",
    }


def _patch_env(monkeypatch, storage, *, invoice=None, existing=None, count=0, stamped=None):
    one_calls = []

    def fake_one(sql, params=None, **kw):
        text = str(sql)
        one_calls.append((text, params))
        if "INSERT INTO public.project_credit_notes" in text:
            return _note_row({"payload_json": json.loads(params[4])})
        if "COUNT(*)" in text:
            return {"n": count}
        if "pg_advisory_xact_lock" in text:
            return {"pg_advisory_xact_lock": None}
        return {}

    def fake_rows(sql, params=None):
        if "FROM public.project_invoices" in sql:
            return [invoice] if invoice else []
        if "FROM public.project_dtes" in sql:
            return list(stamped or [])
        if "FROM public.project_credit_notes" in sql:
            return list(existing or [])
        return []

    monkeypatch.setattr(credit_notes, "one", fake_one)
    monkeypatch.setattr(credit_notes, "rows", fake_rows)
    monkeypatch.setattr(credit_notes, "SupabaseDocumentStorage", lambda: storage)
    monkeypatch.setattr(credit_notes.transaction, "atomic", _noop)
    monkeypatch.setattr(credit_notes, "documentary_backend", _noop)
    # P11 — la leyenda tributaria sella el estado SII al emitir la NC;
    # el import es perezoso (evita el ciclo projects.sii ↔ sii_envio), así
    # que el stub va sobre el módulo origen.
    monkeypatch.setattr(
        sii_envio,
        "integration_state",
        lambda *, org_id: {"adapter": "none", "certified": False,
                           "certificate": False, "caf_available": False},
    )
    return one_calls


def test_issue_credit_note_seals_invoice_reference_and_reason(monkeypatch):
    storage = _Storage()
    invoice = _invoice_row()
    one_calls = _patch_env(monkeypatch, storage, invoice=invoice)
    out = credit_notes.issue_credit_note(
        org_id=uuid4(),
        project=_project(),
        invoice_id=invoice["id"],
        actor_id=uuid4(),
        reason="Error de facturación",
    )
    assert out["credit_code"] == "NC-0001"
    assert len(storage.uploads) == 1
    object_key, content, media = storage.uploads[0]
    assert "credit-notes/nc-0001_" in object_key
    assert content.startswith(b"%PDF-")
    assert media == "application/pdf"

    insert = next(
        params
        for sql, params in one_calls
        if "INSERT INTO public.project_credit_notes" in sql
    )
    payload = json.loads(insert[4])
    assert payload["credit_code"] == "NC-0001"
    assert payload["reason"] == "Error de facturación"
    assert payload["invoice"]["id"] == str(invoice["id"])
    assert payload["invoice"]["invoice_code"] == "FAC-0001"
    # The counter-document inherits the invoice's frozen deal — the NC can
    # never restate totals the factura didn't carry.
    assert payload["deal"]["total_gross"] == "1190000"
    assert payload["project"]["client_name"] == "Constructora Andina"
    assert payload["revision_code"] == "REV-A"


def test_issue_credit_note_replay_returns_existing(monkeypatch):
    storage = _Storage()
    invoice = _invoice_row()
    existing = _note_row({"invoice_id": invoice["id"]})
    _patch_env(monkeypatch, storage, invoice=invoice, existing=[existing])
    out = credit_notes.issue_credit_note(
        org_id=uuid4(),
        project=_project(),
        invoice_id=invoice["id"],
        actor_id=uuid4(),
        reason=None,
    )
    assert out["credit_code"] == "NC-0001"
    assert out["id"] == str(existing["id"])
    assert storage.uploads == []


def test_issue_credit_note_missing_invoice_raises_404(monkeypatch):
    storage = _Storage()
    _patch_env(monkeypatch, storage, invoice=None)
    from authentication.errors import ContractAPIException

    with pytest.raises(ContractAPIException) as excinfo:
        credit_notes.issue_credit_note(
            org_id=uuid4(),
            project=_project(),
            invoice_id=uuid4(),
            actor_id=uuid4(),
            reason=None,
        )
    assert excinfo.value.contract_code == "invoice_not_found"
    assert storage.uploads == []


def test_credit_note_access_signs_the_stored_object(monkeypatch):
    storage = _Storage()
    note = _note_row()
    _patch_env(monkeypatch, storage, existing=[note])
    out = credit_notes.credit_note_access(
        org_id=uuid4(), project_id=note["project_id"], credit_note_id=note["id"]
    )
    assert out["signed_url"].startswith("https://storage.test/")
    assert out["expires_in"] == 600
    assert out["invoice_code"] == "FAC-0001"


def test_credit_note_access_missing_raises_404(monkeypatch):
    _patch_env(monkeypatch, _Storage())
    from authentication.errors import ContractAPIException

    with pytest.raises(ContractAPIException) as excinfo:
        credit_notes.credit_note_access(
            org_id=uuid4(), project_id=uuid4(), credit_note_id=uuid4()
        )
    assert excinfo.value.contract_code == "credit_note_not_found"


def test_issue_credit_note_refuses_stamped_invoice(monkeypatch):
    from authentication.errors import ContractAPIException

    storage = _Storage()
    invoice = _invoice_row()
    _patch_env(monkeypatch, storage, invoice=invoice, stamped=[{"id": uuid4()}])
    with pytest.raises(ContractAPIException) as excinfo:
        credit_notes.issue_credit_note(
            org_id=invoice["org_id"],
            project=_project(),
            invoice_id=invoice["id"],
            actor_id=uuid4(),
            reason="Error",
        )
    assert excinfo.value.contract_code == "invoice_already_stamped"
    assert storage.uploads == []


def test_issue_credit_note_partial_marks_amount_and_renders_balance(monkeypatch):
    from decimal import Decimal

    storage = _Storage()
    invoice = _invoice_row()
    one_calls = _patch_env(monkeypatch, storage, invoice=invoice)
    out = credit_notes.issue_credit_note(
        org_id=uuid4(),
        project=_project(),
        invoice_id=invoice["id"],
        actor_id=uuid4(),
        reason=None,
        amount=Decimal("500000"),
    )
    assert out["partial"] is True
    insert = next(
        params
        for sql, params in one_calls
        if "INSERT INTO public.project_credit_notes" in sql
    )
    payload = json.loads(insert[4])
    assert payload["credit_partial"] is True
    assert payload["credit_amount_gross"] == "500000"


def test_issue_credit_note_amount_exceeds_invoice_raises_422(monkeypatch):
    from decimal import Decimal

    from authentication.errors import ContractAPIException

    storage = _Storage()
    invoice = _invoice_row()
    _patch_env(monkeypatch, storage, invoice=invoice)
    with pytest.raises(ContractAPIException) as excinfo:
        credit_notes.issue_credit_note(
            org_id=uuid4(),
            project=_project(),
            invoice_id=invoice["id"],
            actor_id=uuid4(),
            reason=None,
            amount=Decimal("1190001"),
        )
    assert excinfo.value.contract_code == "credit_note_amount_exceeds"
    assert storage.uploads == []


def test_issue_credit_note_amount_unverifiable_raises_422(monkeypatch):
    from decimal import Decimal

    from authentication.errors import ContractAPIException

    storage = _Storage()
    invoice = _invoice_row()
    invoice["payload_json"]["deal"]["total_gross"] = None
    _patch_env(monkeypatch, storage, invoice=invoice)
    with pytest.raises(ContractAPIException) as excinfo:
        credit_notes.issue_credit_note(
            org_id=uuid4(),
            project=_project(),
            invoice_id=invoice["id"],
            actor_id=uuid4(),
            reason=None,
            amount=Decimal("500000"),
        )
    assert excinfo.value.contract_code == "credit_note_amount_unverifiable"
    assert storage.uploads == []
