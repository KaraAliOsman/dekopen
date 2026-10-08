"""Escaneo de carga P23: una etiqueta de unidad bien formada pero fuera
del manifiesto del viaje cuenta como ``unexpected`` — nunca como «cargada»."""

import json
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from field import service


@contextmanager
def _atomic():
    yield


def _delivery(order_code="OT-P-P23-REV-A-01", *, unit_indexes=(1, 2), quantity=3):
    return {
        "id": uuid4(),
        "order_id": uuid4(),
        "org_id": uuid4(),
        "order_code": order_code,
        "status": "SCHEDULED",
        "unit_indexes": list(unit_indexes),
        "payload_json": json.dumps(
            {
                "quantity": quantity,
                "packing": {
                    "schema": "work_order_packing_v1",
                    "units": [
                        {"unit_index": index, "label_code": f"{order_code}-U{index:02d}"}
                        for index in range(1, quantity + 1)
                    ],
                },
            }
        ),
    }


def _run(monkeypatch, delivery, scanned):
    updates: list[str] = []

    def fake_rows(sql_text: str, params: list = ()):
        lowered = " ".join(sql_text.lower().split())
        if "from public.deliveries" in lowered:
            return [delivery]
        return []

    def fake_one(sql_text: str, params: list = (), error: str = ""):
        lowered = " ".join(sql_text.lower().split())
        if "update public.deliveries" in lowered:
            updates.append(lowered)
            return {"id": delivery["id"]}
        raise AssertionError(f"unexpected one(): {lowered}")

    monkeypatch.setattr("field.service.rows", fake_rows)
    monkeypatch.setattr("field.service.one", fake_one)
    with patch(
        "field.service.transaction.atomic", side_effect=_atomic
    ), patch("field.service.documentary_backend", side_effect=_atomic):
        out = service.load_check(
            org_id=delivery["org_id"],
            delivery_id=delivery["id"],
            scanned_codes=scanned,
            actor_id=uuid4(),
        )
    return out, updates


def test_load_check_flags_unit_outside_trip(monkeypatch):
    org_id = uuid4()
    delivery = _delivery(unit_indexes=(1, 2))
    delivery["org_id"] = org_id
    out, updates = _run(
        monkeypatch,
        delivery,
        ["OT-P-P23-REV-A-01-U01", "OT-P-P23-REV-A-01-U99"],
    )
    assert out["load_checked"] is False
    assert out["missing"] == [2]
    assert out["unexpected"] == ["OT-P-P23-REV-A-01-U99"]
    assert updates == []


def test_load_check_flags_qr_unit_outside_trip(monkeypatch):
    org_id = uuid4()
    delivery = _delivery(unit_indexes=(1, 2))
    delivery["org_id"] = org_id
    out, updates = _run(
        monkeypatch,
        delivery,
        ["DEKOPEN|OT-P-P23-REV-A-01|OT-P-P23-REV-A-01-U03|8"],
    )
    # U03 existe en la OT pero no en este viaje — no es una carga válida.
    assert out["load_checked"] is False
    assert out["missing"] == [1, 2]
    assert out["unexpected"] == ["DEKOPEN|OT-P-P23-REV-A-01|OT-P-P23-REV-A-01-U03|8"]
    assert updates == []


def test_load_check_completes_with_every_unit(monkeypatch):
    org_id = uuid4()
    delivery = _delivery(unit_indexes=(1, 2))
    delivery["org_id"] = org_id
    out, updates = _run(
        monkeypatch,
        delivery,
        [
            "DEKOPEN|OT-P-P23-REV-A-01|OT-P-P23-REV-A-01-U01|8",
            "OT-P-P23-REV-A-01-U02",
        ],
    )
    assert out["load_checked"] is True
    assert out["missing"] == []
    assert out["unexpected"] == []
    assert len(updates) == 1
