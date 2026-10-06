"""Despachos: la lista transversal filtra en la zona de la organización y
considera «abierta» una entrega DELIVERED cuya instalación sigue pendiente
(OT en DISPATCHED) — la verdad que el equipo de instalación ve a diario."""

from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from production import deliveries


@contextmanager
def _atomic():
    yield


class _Ts:
    def isoformat(self):
        return "2026-10-06T00:00:00+00:00"


def test_list_deliveries_open_includes_pending_install(monkeypatch):
    org_id = uuid4()
    captured: list[str] = []
    row = {
        "id": uuid4(),
        "order_id": uuid4(),
        "order_code": "OT-P-000005-REV-A-03",
        "order_status": "DISPATCHED",
        "project_id": uuid4(),
        "project_code": "P-000005",
        "project_name": "Casa Colcura",
        "client_name": "María Soto",
        "scheduled_date": "2026-10-06",
        "time_window": "AM",
        "status": "DELIVERED",
        "address": "Camino Penco km 8",
        "contact_name": None,
        "contact_phone": None,
        "installer_name": "Cuadrilla A",
        "notes": None,
        "unit_indexes": None,
        "created_at": _Ts(),
        "updated_at": _Ts(),
    }

    def fake_rows(sql_text: str, params: list = ()):
        lowered = " ".join(sql_text.lower().split())
        captured.append(lowered)
        assert str(org_id) in params
        return [row]

    monkeypatch.setattr("production.deliveries.rows", fake_rows)
    with patch(
        "production.deliveries.transaction.atomic", side_effect=_atomic
    ), patch("production.deliveries.documentary_backend", side_effect=_atomic):
        out = deliveries.list_deliveries(org_id=org_id, when="open")

    sql = captured[0]
    # Una DELIVERED con la OT en DISPATCHED sigue abierta (falta instalar).
    assert "d.status = 'delivered' and o.status::text = 'dispatched'" in sql
    # El «hoy» del despacho es el de la zona del tenant, no UTC.
    assert "org.timezone" in sql and "local_today" in sql
    item = out["items"][0]
    assert item["order_code"] == "OT-P-000005-REV-A-03"
    assert item["project_code"] == "P-000005"
    assert item["client_name"] == "María Soto"


def test_list_deliveries_when_filters(monkeypatch):
    org_id = uuid4()
    seen: list[str] = []
    monkeypatch.setattr(
        "production.deliveries.rows",
        lambda sql, params=(): (seen.append(" ".join(sql.lower().split())), [])[1],
    )
    with patch(
        "production.deliveries.transaction.atomic", side_effect=_atomic
    ), patch("production.deliveries.documentary_backend", side_effect=_atomic):
        deliveries.list_deliveries(org_id=org_id, when="today")
        deliveries.list_deliveries(org_id=org_id, when="overdue")
        deliveries.list_deliveries(org_id=org_id, when="all", status="FAILED")
        deliveries.list_deliveries(org_id=org_id, when="bogus")

    today_sql, overdue_sql, failed_sql, default_sql = seen
    assert "d.scheduled_date = zone.local_today" in today_sql
    assert "d.scheduled_date < zone.local_today" in overdue_sql
    assert "d.status = %s" in failed_sql
    # `when` inválido cae al abierto — nunca una respuesta vacía confusa.
    assert "scheduled' , 'on_route" in default_sql or "on_route" in default_sql
