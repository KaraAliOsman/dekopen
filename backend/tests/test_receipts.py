"""Payment receipts: sealed comprobante emission + access."""

from decimal import Decimal
from uuid import uuid4

import pytest

from projects import payments, receipts


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


def _receipt_row(**over):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "payment_id": uuid4(),
        "receipt_code": "RC-0001",
        "payload_json": {},
        "storage_bucket": "documents",
        "storage_object_key": "org_x/projects/y/receipts/rc-0001_ab.pdf",
        "file_sha256": "a" * 64,
        "media_type": "application/pdf",
        "byte_size": 1024,
        "created_by": uuid4(),
        "created_at": "2026-09-20T10:00:00+00:00",
    }
    row.update(over)
    return row


def _runner(captured, **routes):
    def fake_rows(sql, params=None):
        captured.append((sql, params))
        for marker, value in routes.items():
            if marker in sql:
                return value
        return []

    return fake_rows


def test_issue_receipt_renders_uploads_and_inserts(monkeypatch):
    captured = []
    storage = _Storage()
    monkeypatch.setattr(
        receipts,
        "rows",
        _runner(
            captured,
            **{
                "FROM public.payment_receipts WHERE payment_id": [],
                "COUNT(*) AS n": [{"n": 0}],
                "INSERT INTO public.payment_receipts": [_receipt_row()],
            },
        ),
    )
    one_calls = []

    def fake_one(sql, params=None, **kw):
        text = str(sql)
        one_calls.append((text, params))
        if "INSERT INTO" in text:
            return _receipt_row()
        if "COUNT(*)" in text:
            return {"n": 0}
        return {"collected": Decimal("400000")}

    monkeypatch.setattr(receipts, "one", fake_one)
    monkeypatch.setattr(receipts, "SupabaseDocumentStorage", lambda: storage)
    org, actor = uuid4(), uuid4()
    payment = {
        "id": uuid4(),
        "project_id": uuid4(),
        "kind": "ANTICIPO",
        "amount": Decimal("400000"),
        "method": "TRANSFER",
        "reference": "TRX-1",
        "note": None,
        "recorded_at": "2026-09-20T10:00:00+00:00",
        "operation_key": "op-12345678",
    }
    out = receipts.issue_receipt(
        org_id=org,
        project={
            "code": "PRY-001",
            "name": "Edificio Norte",
            "client_name": "Constructora Andina",
            "client_rut": "76.543.210-1",
            "delivery_address": "Av. Providencia 1234",
        },
        payment=payment,
        actor_id=actor,
        deal={"total": Decimal("800000"), "currency": "CLP"},
    )
    assert out["receipt_code"] == "RC-0001"
    assert len(storage.uploads) == 1
    object_key, content, media = storage.uploads[0]
    assert object_key.startswith(f"org_{org}/projects/{payment['project_id']}/receipts/rc-0001_")
    assert content.startswith(b"%PDF-")
    assert media == "application/pdf"
    insert = next(
        (sql, params)
        for sql, params in one_calls
        if "INSERT INTO public.payment_receipts" in sql
    )
    assert "payload_json" in insert[0]

    # The sequence is organization-wide — the code must satisfy
    # UNIQUE (org_id, receipt_code) across every project — and it is
    # serialized by an org-scoped advisory lock, not the project row.
    lock = next(s for s, _ in one_calls if "pg_advisory_xact_lock" in s)
    assert lock is not None
    count_sql, count_params = next(
        (s, p) for s, p in one_calls if "COUNT(*)" in s
    )
    assert "project_id" not in count_sql
    assert count_params == [str(org)]


def test_issue_receipt_replay_returns_existing_without_upload(monkeypatch):
    captured = []
    storage = _Storage()
    existing = _receipt_row()
    monkeypatch.setattr(
        receipts,
        "rows",
        _runner(captured, **{"FROM public.payment_receipts WHERE payment_id": [existing]}),
    )
    monkeypatch.setattr(receipts, "SupabaseDocumentStorage", lambda: storage)
    out = receipts.issue_receipt(
        org_id=uuid4(),
        project={"code": "P", "name": "N", "client_name": "C",
                 "client_rut": "1-9", "delivery_address": "A"},
        payment={"id": existing["payment_id"], "project_id": existing["project_id"]},
        actor_id=uuid4(),
        deal={"total": Decimal("1"), "currency": "CLP"},
    )
    assert out["receipt_code"] == "RC-0001"
    assert storage.uploads == []
    assert not any("INSERT INTO public.payment_receipts" in sql for sql, _ in captured)


def test_record_payment_issues_receipt_with_the_deal(monkeypatch):
    captured = []
    calls = []

    def fake_rows(sql, params=None):
        captured.append((sql, params))
        if "operation_key=%s" in sql:
            return []
        if "COALESCE(SUM(amount)" in sql:
            return [{"collected": Decimal("0")}]
        if "FROM public.project_versions" in sql:
            return [{
                "revision_code": "REV-A",
                "snapshot_json": {
                    "project": {"total_price_gross": "800000", "currency": "CLP"}
                },
            }]
        if "FROM public.project_payments" in sql:
            return []
        if "INSERT INTO public.project_payments" in sql:
            row = {
                "id": uuid4(),
                "project_id": params[1],
                "operation_key": params[2],
                "kind": params[3],
                "amount": params[4],
                "method": params[5],
                "reference": params[6],
                "note": params[7],
                "recorded_by": params[8],
                "recorded_at": "2026-09-20T10:00:00+00:00",
                "voided_at": None,
                "voided_by": None,
                "void_reason": None,
                "created_at": "2026-09-20T10:00:00+00:00",
            }
            return [row]
        return []

    from contextlib import contextmanager

    @contextmanager
    def _noop():
        yield

    project_row = {
        "id": uuid4(),
        "status": "APPROVED",
        "total_price_gross": Decimal("800000"),
    }
    monkeypatch.setattr(payments, "documentary_backend", _noop)
    monkeypatch.setattr(payments.transaction, "atomic", _noop)
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
        payments, "project_row", staticmethod(lambda *a, **kw: project_row)
    )
    monkeypatch.setattr(payments, "rows", fake_rows)
    monkeypatch.setattr(payments, "issue_receipt", lambda **kw: calls.append(kw) or {
        "id": str(uuid4()),
        "receipt_code": "RC-0001",
        "payment_id": str(kw["payment"]["id"]),
        "created_at": "2026-09-20T10:00:00+00:00",
    })
    out = payments.record_payment(
        org_id=uuid4(),
        project_id=project_row["id"],
        actor_id=uuid4(),
        data={
            "operation_key": "op-12345678",
            "kind": "ANTICIPO",
            "amount": Decimal("400000"),
            "method": "TRANSFER",
        },
    )
    assert len(calls) == 1
    assert calls[0]["deal"]["total"] == Decimal("800000")
    assert out["receipt"]["receipt_code"] == "RC-0001"
    assert out["payment"]["receipt_code"] == "RC-0001"


def test_receipt_access_signs_the_stored_object(monkeypatch):
    row = _receipt_row()
    monkeypatch.setattr(receipts, "rows", lambda sql, params=None: [row])
    from contextlib import contextmanager

    @contextmanager
    def _noop():
        yield

    monkeypatch.setattr(receipts, "documentary_backend", _noop)
    monkeypatch.setattr(receipts, "SupabaseDocumentStorage", lambda: _Storage())
    out = receipts.receipt_access(
        org_id=row["org_id"], project_id=row["project_id"], payment_id=row["payment_id"]
    )
    assert out["receipt_code"] == "RC-0001"
    assert out["signed_url"].startswith("https://signed.example/")
    assert out["expires_in"] == receipts.SIGNED_URL_TTL_SECONDS


def test_receipt_access_missing_raises_404(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def _noop():
        yield

    monkeypatch.setattr(receipts, "documentary_backend", _noop)
    monkeypatch.setattr(receipts, "rows", lambda sql, params=None: [])
    with pytest.raises(Exception) as raised:
        receipts.receipt_access(org_id=uuid4(), project_id=uuid4(), payment_id=uuid4())
    assert raised.value.contract_code == "payment_receipt_not_found"
