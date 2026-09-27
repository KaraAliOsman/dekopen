"""Dispatch notes: sealed guía de despacho emission + access."""

import json
from uuid import uuid4

import pytest

from production import dispatch_notes


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


def _note_row(**over):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "work_order_id": uuid4(),
        "note_code": "GD-0001",
        "payload_json": {},
        "storage_bucket": "documents",
        "storage_object_key": "org_x/projects/y/dispatch-notes/gd-0001_ab.pdf",
        "file_sha256": "a" * 64,
        "media_type": "application/pdf",
        "byte_size": 1024,
        "created_by": uuid4(),
        "created_at": "2026-09-20T10:00:00+00:00",
    }
    row.update(over)
    return row


def _order(**over):
    order = {
        "id": uuid4(),
        "order_code": "OT-P-1-REV-A-01",
        "status": "COMPLETED",
        "project_id": uuid4(),
        "payload_json": {
            "position_id": "pos-1",
            "quantity": 2,
            "packing": {
                "schema": "work_order_packing_v1",
                "units": [
                    {
                        "unit_index": 1,
                        "label_code": "OT-P-1-REV-A-01-U01",
                        "profiles": 12,
                        "reinforcements": 6,
                        "glasses": 3,
                        "panels": 0,
                        "hardware": 8,
                    },
                    {
                        "unit_index": 2,
                        "label_code": "OT-P-1-REV-A-01-U02",
                        "profiles": 10,
                        "reinforcements": 5,
                        "glasses": 3,
                        "panels": 1,
                        "hardware": 7,
                    },
                ],
            },
        },
    }
    order.update(over)
    return order


def _project():
    return {
        "code": "PRY-001",
        "name": "Edificio Norte",
        "client_name": "Constructora Andina",
        "client_rut": "76.543.210-1",
        "delivery_address": "Av. Providencia 1234",
    }


def _patch_env(monkeypatch, storage, *, existing=None, count=0):
    one_calls = []

    def fake_rows(sql, params=None):
        if "FROM public.dispatch_notes WHERE work_order_id" in sql:
            return [existing] if existing else []
        return []

    def fake_one(sql, params=None, **kw):
        text = str(sql)
        one_calls.append((text, params))
        if "INSERT INTO public.dispatch_notes" in text:
            return _note_row()
        if "COUNT(*)" in text:
            return {"n": count}
        return {}

    monkeypatch.setattr(dispatch_notes, "rows", fake_rows)
    monkeypatch.setattr(dispatch_notes, "one", fake_one)
    monkeypatch.setattr(dispatch_notes, "SupabaseDocumentStorage", lambda: storage)
    return one_calls


def test_issue_dispatch_note_renders_uploads_and_inserts(monkeypatch):
    storage = _Storage()
    one_calls = _patch_env(monkeypatch, storage)
    org, order, actor = uuid4(), _order(), uuid4()
    out = dispatch_notes.issue_dispatch_note(
        org_id=org,
        order=order,
        project=_project(),
        actor_id=actor,
        note="Camión 12",
    )
    assert out["note_code"] == "GD-0001"
    assert len(storage.uploads) == 1
    object_key, content, media = storage.uploads[0]
    assert object_key.startswith(
        f"org_{org}/projects/{order['project_id']}/dispatch-notes/gd-0001_"
    )
    assert content.startswith(b"%PDF-")
    assert media == "application/pdf"
    insert = next(
        (sql, params)
        for sql, params in one_calls
        if "INSERT INTO public.dispatch_notes" in sql
    )
    assert "payload_json" in insert[0]

    # The sequence is organization-wide — the code must satisfy
    # UNIQUE (org_id, note_code) across every project — and it is
    # serialized by an org-scoped advisory lock, not the order row.
    lock = next(s for s, _ in one_calls if "pg_advisory_xact_lock" in s)
    assert lock is not None
    count_sql, count_params = next(
        (s, p) for s, p in one_calls if "COUNT(*)" in s
    )
    assert "project_id" not in count_sql
    assert "work_order_id" not in count_sql
    assert count_params == [str(org)]


def test_issue_dispatch_note_payload_seals_manifest_and_destination(monkeypatch):
    storage = _Storage()
    one_calls = _patch_env(monkeypatch, storage)
    org, order = uuid4(), _order()
    dispatch_notes.issue_dispatch_note(
        org_id=org, order=order, project=_project(), actor_id=uuid4(), note=None
    )
    insert = next(
        params
        for sql, params in one_calls
        if "INSERT INTO public.dispatch_notes" in sql
    )
    payload = json.loads(insert[4])
    assert payload["note_code"] == "GD-0001"
    assert payload["delivery"]["address"] == "Av. Providencia 1234"
    assert payload["order"]["code"] == "OT-P-1-REV-A-01"
    assert len(payload["units"]) == 2
    assert payload["units"][0]["label_code"] == "OT-P-1-REV-A-01-U01"
    assert payload["totals"]["profiles"] == 22
    assert payload["totals"]["glasses"] == 6
    assert payload["totals"]["panels"] == 1
    assert payload["totals"]["units"] == 2


def test_issue_dispatch_note_without_manifest_still_seals(monkeypatch):
    """A dispatched order without a packing manifest still gets a guía —
    the PDF reports the honest 'sin manifiesto' state, never invents units."""
    storage = _Storage()
    one_calls = _patch_env(monkeypatch, storage)
    order = _order(payload_json={"position_id": "pos-1", "quantity": 3})
    dispatch_notes.issue_dispatch_note(
        org_id=uuid4(), order=order, project=_project(), actor_id=uuid4(), note=None
    )
    insert = next(
        params
        for sql, params in one_calls
        if "INSERT INTO public.dispatch_notes" in sql
    )
    payload = json.loads(insert[4])
    assert payload["units"] == []
    assert payload["totals"]["units"] == 3
    assert len(storage.uploads) == 1


def test_issue_dispatch_note_replay_returns_existing_without_upload(monkeypatch):
    storage = _Storage()
    existing = _note_row()
    _patch_env(monkeypatch, storage, existing=existing)
    out = dispatch_notes.issue_dispatch_note(
        org_id=uuid4(),
        order=_order(id=existing["work_order_id"]),
        project=_project(),
        actor_id=uuid4(),
        note=None,
    )
    assert out["note_code"] == "GD-0001"
    assert storage.uploads == []


def test_dispatch_note_access_signs_the_stored_object(monkeypatch):
    row = _note_row()
    monkeypatch.setattr(dispatch_notes, "rows", lambda sql, params=None: [row])
    from contextlib import contextmanager

    @contextmanager
    def _noop():
        yield

    monkeypatch.setattr(dispatch_notes, "documentary_backend", _noop)
    monkeypatch.setattr(dispatch_notes, "SupabaseDocumentStorage", lambda: _Storage())
    out = dispatch_notes.dispatch_note_access(
        org_id=row["org_id"], order_id=row["work_order_id"]
    )
    assert out["note_code"] == "GD-0001"
    assert out["signed_url"].startswith("https://signed.example/")
    assert out["expires_in"] == dispatch_notes.SIGNED_URL_TTL_SECONDS


def test_dispatch_note_access_missing_raises_404(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def _noop():
        yield

    monkeypatch.setattr(dispatch_notes, "documentary_backend", _noop)
    monkeypatch.setattr(dispatch_notes, "rows", lambda sql, params=None: [])
    with pytest.raises(Exception) as raised:
        dispatch_notes.dispatch_note_access(org_id=uuid4(), order_id=uuid4())
    assert raised.value.contract_code == "dispatch_note_not_found"
