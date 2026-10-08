"""Project invoices: sealed factura emission + access."""

import json
from contextlib import contextmanager
from uuid import uuid4

import pytest

from projects import invoices


@contextmanager
def _noop():
    yield


class _Storage:
    def __init__(self):
        self.uploads = []
        self.deleted = []

    def upload_immutable(self, object_key, content, content_type):
        self.uploads.append((object_key, content, content_type))

    def delete_object(self, object_key):
        self.deleted.append(object_key)

    def signed_url(self, object_key, expires_in=None):
        return f"https://signed.example/{object_key}"


def _invoice_row(**over):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "project_version_id": uuid4(),
        "invoice_code": "FAC-0001",
        "payload_json": {"revision_code": "REV-A"},
        "storage_bucket": "documents",
        "storage_object_key": "org_x/projects/y/invoices/fac-0001_ab.pdf",
        "file_sha256": "a" * 64,
        "media_type": "application/pdf",
        "byte_size": 1024,
        "created_by": uuid4(),
        "created_at": "2026-09-20T10:00:00+00:00",
    }
    row.update(over)
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


def _snapshot():
    return {
        "project": {
            "code": "PRY-001",
            "name": "Edificio Norte",
            "client_name": "Constructora Andina",
            "client_rut": "76.543.210-1",
            "delivery_address": "Av. Providencia 1234",
            "total_price_net": "1000000",
            "total_price_tax": "190000",
            "total_price_gross": "1190000",
            "currency": "CLP",
            "payment_terms": "50% anticipo, saldo contra entrega",
        },
        "positions": [
            {
                "position_index": 1,
                "typology": "SLIDING_2L",
                "quantity": 2,
                "width_mm": "2400",
                "height_mm": "1500",
                "location_tag": "Living",
            }
        ],
    }


def _patch_env(monkeypatch, storage, *, snapshot=None, count=0, collected="0"):
    one_calls = []

    def fake_one(sql, params=None, **kw):
        text = str(sql)
        one_calls.append((text, params))
        if "INSERT INTO public.project_invoices" in text:
            return _invoice_row()
        if "COUNT(*)" in text:
            return {"n": count}
        if "COALESCE(SUM(amount)" in text:
            return {"collected": collected}
        return {}

    def fake_rows(sql, params=None):
        if "FROM public.project_versions" in sql:
            if snapshot is None:
                return []
            return [
                {
                    "id": uuid4(),
                    "revision_code": "REV-A",
                    "snapshot_json": json.dumps(snapshot),
                }
            ]
        return []

    monkeypatch.setattr(invoices, "one", fake_one)
    monkeypatch.setattr(invoices, "rows", fake_rows)
    monkeypatch.setattr(invoices, "SupabaseDocumentStorage", lambda: storage)
    monkeypatch.setattr(invoices.transaction, "atomic", _noop)
    monkeypatch.setattr(invoices, "documentary_backend", _noop)
    # P11 — la leyenda tributaria sella el estado SII de la org al emitir;
    # en unidad ese estado es un stub honesto «no certificado».
    monkeypatch.setattr(
        invoices,
        "integration_state",
        lambda *, org_id: {"adapter": "none", "certified": False,
                           "certificate": False, "caf_available": False},
    )
    return one_calls


def test_issue_invoice_renders_uploads_and_inserts(monkeypatch):
    storage = _Storage()
    one_calls = _patch_env(monkeypatch, storage, snapshot=_snapshot())
    org, project, actor = uuid4(), _project(), uuid4()
    out = invoices.issue_invoice(org_id=org, project=project, actor_id=actor)
    assert out["invoice_code"] == "FAC-0001"
    assert out["revision_code"] == "REV-A"
    assert len(storage.uploads) == 1
    object_key, content, media = storage.uploads[0]
    assert object_key.startswith(
        f"org_{org}/projects/{project['id']}/invoices/fac-0001_"
    )
    assert content.startswith(b"%PDF-")
    assert media == "application/pdf"

    # Org-wide sequence serialized by an org-scoped advisory lock —
    # the code must satisfy UNIQUE (org_id, invoice_code).
    assert any("pg_advisory_xact_lock" in s for s, _ in one_calls)
    count_sql, count_params = next(
        (s, p) for s, p in one_calls if "COUNT(*)" in s
    )
    assert "project_id" not in count_sql
    assert count_params == [str(org)]


def test_issue_invoice_payload_seals_deal_positions_and_balance(monkeypatch):
    storage = _Storage()
    one_calls = _patch_env(
        monkeypatch, storage, snapshot=_snapshot(), collected="500000"
    )
    invoices.issue_invoice(
        org_id=uuid4(), project=_project(), actor_id=uuid4()
    )
    insert = next(
        params
        for sql, params in one_calls
        if "INSERT INTO public.project_invoices" in sql
    )
    payload = json.loads(insert[4])
    assert payload["invoice_code"] == "FAC-0001"
    assert payload["revision_code"] == "REV-A"
    assert payload["deal"]["total_gross"] == "1190000"
    assert payload["deal"]["total_tax"] == "190000"
    assert payload["balance"]["collected"] == "500000"
    assert payload["balance"]["amount_due"] == "690000"
    assert len(payload["positions"]) == 1
    assert payload["positions"][0]["typology"] == "SLIDING_2L"
    assert payload["positions"][0]["width_mm"] == "2400"
    assert payload["project"]["payment_terms"] == (
        "50% anticipo, saldo contra entrega"
    )


def test_issue_invoice_seals_frozen_header_not_live_project(monkeypatch):
    """A successor may rewrite the live project's client data — the invoice
    must seal the header frozen inside the chosen revision, never mix states."""
    storage = _Storage()
    one_calls = _patch_env(monkeypatch, storage, snapshot=_snapshot())
    live = _project()
    live["client_name"] = "Constructora Norte"
    live["client_rut"] = "77.111.222-3"
    live["delivery_address"] = "Cambio 999"
    invoices.issue_invoice(org_id=uuid4(), project=live, actor_id=uuid4())
    insert = next(
        params
        for sql, params in one_calls
        if "INSERT INTO public.project_invoices" in sql
    )
    payload = json.loads(insert[4])
    assert payload["project"]["client_name"] == "Constructora Andina"
    assert payload["project"]["client_rut"] == "76.543.210-1"
    assert payload["project"]["delivery_address"] == "Av. Providencia 1234"


def test_issue_invoice_without_sealed_revision_raises_409(monkeypatch):
    storage = _Storage()
    _patch_env(monkeypatch, storage, snapshot=None)
    with pytest.raises(Exception) as raised:
        invoices.issue_invoice(
            org_id=uuid4(), project=_project(), actor_id=uuid4()
        )
    assert raised.value.contract_code == "invoice_no_sealed_deal"
    assert storage.uploads == []


def test_invoice_access_signs_the_stored_object(monkeypatch):
    row = _invoice_row()
    monkeypatch.setattr(invoices, "documentary_backend", _noop)
    monkeypatch.setattr(
        invoices.sii,
        "dtes_by_credit_note",
        lambda *, org_id, project_id: {},
    )
    monkeypatch.setattr(
        invoices,
        "rows",
        lambda sql, params=None: []
        if "project_credit_notes" in sql
        else [row],
    )
    monkeypatch.setattr(invoices, "SupabaseDocumentStorage", lambda: _Storage())
    out = invoices.invoice_access(
        org_id=row["org_id"],
        project_id=row["project_id"],
        invoice_id=row["id"],
    )
    assert out["invoice_code"] == "FAC-0001"
    assert out["signed_url"].startswith("https://signed.example/")
    assert out["expires_in"] == invoices.SIGNED_URL_TTL_SECONDS


def test_invoice_access_missing_raises_404(monkeypatch):
    monkeypatch.setattr(invoices, "documentary_backend", _noop)
    monkeypatch.setattr(invoices, "rows", lambda sql, params=None: [])
    with pytest.raises(Exception) as raised:
        invoices.invoice_access(
            org_id=uuid4(), project_id=uuid4(), invoice_id=uuid4()
        )
    assert raised.value.contract_code == "invoice_not_found"
