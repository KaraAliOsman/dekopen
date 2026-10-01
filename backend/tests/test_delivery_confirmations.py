"""Delivery confirmations: sealed comprobante de entrega + cobro."""

import base64
import json
import zlib
from contextlib import contextmanager
from uuid import uuid4

import pytest

from production import confirmations


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


def _chunk(ctype: bytes, data: bytes) -> bytes:
    return (
        len(data).to_bytes(4, "big")
        + ctype
        + data
        + zlib.crc32(ctype + data).to_bytes(4, "big")
    )


_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + _chunk(
        b"IHDR",
        (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00",
    )
    + _chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    + _chunk(b"IEND", b"")
)
_SIG_B64 = base64.b64encode(_PNG).decode("ascii")


@contextmanager
def _noop():
    yield


def _order(**over):
    row = {
        "id": uuid4(),
        "order_code": "OT-P-1-REV-A-01",
        "project_id": uuid4(),
        "status": "DISPATCHED",
        "payload_json": json.dumps(
            {
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
                        }
                    ],
                },
            }
        ),
    }
    row.update(over or {})
    return row


def _delivery(**over):
    row = {
        "id": uuid4(),
        "order_id": uuid4(),
        "org_id": uuid4(),
        "scheduled_date": "2026-09-24",
        "time_window": "AM",
        "address": "Av. Matta 123, Santiago",
        "contact_name": "Cliente",
        "contact_phone": "+56911112222",
        "installer_name": "Cuadrilla 1",
        "notes": None,
        "status": "ON_ROUTE",
    }
    row.update(over or {})
    return row


def _confirmation_row(**over):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "order_id": uuid4(),
        "delivery_id": uuid4(),
        "payment_id": None,
        "confirmation_code": "CE-0001",
        "payload_json": {},
        "signature_object_key": "org_x/projects/y/delivery-confirmations/ce-0001_signature_z.png",
        "storage_bucket": "documents",
        "storage_object_key": "org_x/projects/y/delivery-confirmations/ce-0001_ab.pdf",
        "file_sha256": "a" * 64,
        "media_type": "application/pdf",
        "byte_size": 2048,
        "issued_by": uuid4(),
        "issued_at": "2026-09-24T11:00:00+00:00",
        "created_at": "2026-09-24T11:00:00+00:00",
    }
    row.update(over or {})
    return row


def _patch_env(monkeypatch, storage, *, order=None, delivery=None, existing=None):
    order = order if order is not None else _order()
    delivery = delivery if delivery is not None else _delivery()

    def fake_one(sql, params=None, not_found=None):
        if "FROM public.orders" in sql:
            if order is None:
                raise RuntimeError(not_found or "missing")
            return order
        if "FROM public.deliveries" in sql:
            if delivery is None:
                raise RuntimeError(not_found or "missing")
            return delivery
        if "COUNT(*)" in sql:
            return {"n": 0}
        if "INSERT INTO public.delivery_confirmations" in sql:
            return _confirmation_row(
                order_id=order["id"], delivery_id=delivery["id"]
            )
        if "INSERT INTO public.production_step_events" in sql:
            return {"id": uuid4()}
        return {}

    def fake_rows(sql, params=None):
        if "FROM public.delivery_confirmations" in sql:
            return list(existing or [])
        if "UPDATE public.deliveries" in sql:
            return [{"id": delivery["id"]}]
        if "INSERT INTO public.production_step_events" in sql:
            return [{"id": uuid4()}]
        return []

    def fake_resolve(*, org_id, project_id, project, actor_id, data):
        storage.payment_data.append(data)
        return (
            {
                "id": uuid4(),
                "kind": data["kind"],
                "method": data["method"],
                "amount": data["amount"],
                "recorded_at": data["recorded_at"],
            },
            None,
        )

    storage.payment_data = []
    storage.receipt_calls = []
    monkeypatch.setattr(
        confirmations,
        "issue_receipt",
        lambda *, org_id, project, payment, actor_id, deal: storage.receipt_calls.append(
            {"payment_id": payment["id"], "deal": deal}
        ),
    )
    monkeypatch.setattr(confirmations, "one", fake_one)
    monkeypatch.setattr(confirmations, "rows", fake_rows)
    monkeypatch.setattr(
        confirmations,
        "project_row",
        lambda *a, **k: {
            "id": order["project_id"],
            "code": "P-0001",
            "name": "Manillas E2E",
            "client_name": "Cliente SpA",
            "client_rut": "76.123.456-7",
        },
    )
    monkeypatch.setattr(
        confirmations, "resolve_or_insert_payment", fake_resolve
    )
    monkeypatch.setattr(confirmations, "SupabaseDocumentStorage", lambda: storage)
    monkeypatch.setattr(confirmations.transaction, "atomic", _noop)
    monkeypatch.setattr(confirmations, "documentary_backend", _noop)
    return order, delivery


def test_confirm_seals_pod_and_uploads_both_objects(monkeypatch):
    storage = _Storage()
    order, delivery = _patch_env(monkeypatch, storage)
    out = confirmations.confirm_delivery(
        org_id=uuid4(),
        order_id=order["id"],
        actor_id=uuid4(),
        receiver_name="  Juan Pérez ",
        receiver_rut="12.345.678-9",
        signature_b64=_SIG_B64,
        payment=None,
    )
    assert out["confirmation_code"] == "CE-0001"
    assert len(storage.uploads) == 2
    sig_key, sig_content, sig_type = storage.uploads[0]
    assert sig_type == "image/png" and "signature" in sig_key
    pdf_key, pdf_content, pdf_type = storage.uploads[1]
    assert pdf_type == "application/pdf" and pdf_content.startswith(b"%PDF-")


def test_confirm_with_payment_inserts_cobro(monkeypatch):
    storage = _Storage()
    order, delivery = _patch_env(monkeypatch, storage)
    out = confirmations.confirm_delivery(
        org_id=uuid4(),
        order_id=order["id"],
        actor_id=uuid4(),
        receiver_name="Juan Pérez",
        receiver_rut=None,
        signature_b64=_SIG_B64,
        payment={"amount": "50000", "method": "CASH", "kind": "SALDO"},
    )
    assert out["confirmation_code"] == "CE-0001"
    assert len(storage.uploads) == 2
    assert len(storage.payment_data) == 1
    cobro = storage.payment_data[0]
    assert cobro["operation_key"].startswith("pod:")
    assert cobro["amount"] == 50000 and cobro["kind"] == "SALDO"


def test_confirm_open_trip_query_tolerates_a_delivered_sibling(monkeypatch):
    """Partial deliveries leave a DELIVERED trip beside the ON_ROUTE one —
    the select must LIMIT to the preferred row or the second confirm dies
    on ambiguous_authority (phase-10 live defect)."""
    storage = _Storage()
    order, _delivery = _patch_env(monkeypatch, storage)
    captured = []
    base_one = confirmations.one

    def recording_one(sql, params=None, not_found=None):
        if "FROM public.deliveries" in sql:
            captured.append(sql)
        return base_one(sql, params, not_found)

    monkeypatch.setattr(confirmations, "one", recording_one)
    confirmations.confirm_delivery(
        org_id=uuid4(),
        order_id=order["id"],
        actor_id=uuid4(),
        receiver_name="Juan Pérez",
        receiver_rut=None,
        signature_b64=_SIG_B64,
        payment=None,
    )
    (delivery_sql,) = [s for s in captured if "ON_ROUTE" in s]
    assert "LIMIT 1" in delivery_sql


def test_confirm_signature_only_pod_does_not_lock_project(monkeypatch):
    """INSTALLER signs PODs — FOR UPDATE on projects would hit the
    ledger-role lock policy. Only a cobro needs the lock."""
    storage = _Storage()
    order, _delivery = _patch_env(monkeypatch, storage)
    locks = []
    base_row = confirmations.project_row
    monkeypatch.setattr(
        confirmations,
        "project_row",
        lambda *a, lock=False, **k: (locks.append(lock), base_row(*a, **k))[1],
    )
    confirmations.confirm_delivery(
        org_id=uuid4(),
        order_id=order["id"],
        actor_id=uuid4(),
        receiver_name="Juan Pérez",
        receiver_rut=None,
        signature_b64=_SIG_B64,
        payment=None,
    )
    assert locks == [False]

    storage2 = _Storage()
    order2, _d2 = _patch_env(monkeypatch, storage2)
    locks.clear()
    monkeypatch.setattr(
        confirmations,
        "project_row",
        lambda *a, lock=False, **k: (locks.append(lock), base_row(*a, **k))[1],
    )
    confirmations.confirm_delivery(
        org_id=uuid4(),
        order_id=order2["id"],
        actor_id=uuid4(),
        receiver_name="Juan Pérez",
        receiver_rut=None,
        signature_b64=_SIG_B64,
        payment={"amount": "50000", "method": "CASH", "kind": "SALDO"},
    )
    assert locks == [True]


def test_confirm_replays_existing_row_without_rerender(monkeypatch):
    storage = _Storage()
    order, delivery = _patch_env(
        monkeypatch, storage, existing=[_confirmation_row(confirmation_code="CE-0007")]
    )
    out = confirmations.confirm_delivery(
        org_id=uuid4(),
        order_id=order["id"],
        actor_id=uuid4(),
        receiver_name="Juan Pérez",
        receiver_rut=None,
        signature_b64=_SIG_B64,
        payment={"amount": "99999", "method": "TRANSFER"},
    )
    assert out["confirmation_code"] == "CE-0007"
    assert storage.uploads == []


def test_confirm_rejects_scheduled_delivery(monkeypatch):
    storage = _Storage()
    order, _ = _patch_env(
        monkeypatch, storage, delivery=_delivery(status="SCHEDULED")
    )
    with pytest.raises(Exception) as raised:
        confirmations.confirm_delivery(
            org_id=uuid4(),
            order_id=order["id"],
            actor_id=uuid4(),
            receiver_name="Juan",
            receiver_rut=None,
            signature_b64=_SIG_B64,
            payment=None,
        )
    assert raised.value.code == "delivery_transition_invalid"
    assert storage.uploads == []


def test_confirm_rejects_bad_signature_and_bad_payment(monkeypatch):
    storage = _Storage()
    order, _ = _patch_env(monkeypatch, storage)
    with pytest.raises(Exception) as raised:
        confirmations.confirm_delivery(
            org_id=uuid4(),
            order_id=order["id"],
            actor_id=uuid4(),
            receiver_name="Juan",
            receiver_rut=None,
            signature_b64=base64.b64encode(b"not-a-png").decode(),
            payment=None,
        )
    assert raised.value.code == "signature_invalid"
    with pytest.raises(Exception) as raised:
        confirmations.confirm_delivery(
            org_id=uuid4(),
            order_id=order["id"],
            actor_id=uuid4(),
            receiver_name="Juan",
            receiver_rut=None,
            signature_b64=_SIG_B64,
            payment={"amount": "-5", "method": "CASH"},
        )
    assert raised.value.code == "payment_invalid"
    with pytest.raises(Exception) as raised:
        confirmations.confirm_delivery(
            org_id=uuid4(),
            order_id=order["id"],
            actor_id=uuid4(),
            receiver_name="Juan",
            receiver_rut=None,
            signature_b64=_SIG_B64,
            payment={"amount": "NaN", "method": "CASH"},
        )
    assert raised.value.code == "payment_invalid"
    assert storage.uploads == []


def test_confirmation_access_signs_stored_object(monkeypatch):
    row = _confirmation_row()
    monkeypatch.setattr(confirmations, "documentary_backend", _noop)
    monkeypatch.setattr(confirmations, "rows", lambda sql, params=None: [row])
    monkeypatch.setattr(
        confirmations, "SupabaseDocumentStorage", lambda: _Storage()
    )
    out = confirmations.confirmation_access(
        org_id=row["org_id"], order_id=row["order_id"]
    )
    assert out["confirmation_code"] == "CE-0001"
    assert out["signed_url"].startswith("https://signed.example/")
    assert out["expires_in"] == confirmations.SIGNED_URL_TTL_SECONDS
