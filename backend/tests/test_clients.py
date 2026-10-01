"""Client registry: org-scoped CRUD, snapshot semantics on projects."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from django.db import IntegrityError
from rest_framework.exceptions import APIException

from projects import clients, service


def _row(**over):
    row = {
        "id": uuid4(),
        "name": "Constructora Andina",
        "rut": "76.543.210-1",
        "email": "obras@andina.cl",
        "phone": "+56 2 2345 6789",
        "address": "Av. Providencia 1234, Santiago",
        "giro": "Construcción",
        "comuna": "Providencia",
        "notes": None,
        "is_active": True,
        "created_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
    }
    row.update(over)
    return row


def _runner(captured, **routes):
    def run(query, parameters=()):
        sql = str(query)
        captured.append((sql, parameters))
        for marker, value in routes.items():
            if marker in sql:
                return value
        return []

    return run


def test_create_client_inserts_and_returns_public(monkeypatch):
    org, actor = uuid4(), uuid4()
    row = _row()
    calls = []

    def fake_rows(query, parameters=()):
        sql = str(query)
        calls.append((sql, parameters))
        if "INSERT INTO public.clients" in sql:
            return [{"id": "x"}]
        return [row]

    monkeypatch.setattr(clients, "rows", fake_rows)
    result = clients.create_client(
        org,
        actor,
        {"name": "Constructora Andina", "rut": "76.543.210-1", "email": "obras@andina.cl"},
    )
    insert = calls[0]
    assert insert[1][0] == result["id"] or insert[1][1] == org
    assert insert[1][1] == org and insert[1][2] == actor
    # Blank optional fields are normalized to NULL (never '') so the
    # (org_id, rut) unique key treats them as absent.
    assert insert[1][4] == "76.543.210-1"
    assert insert[1][6] is None  # phone
    assert result["name"] == "Constructora Andina"


def test_create_client_rut_conflict_raises_409(monkeypatch):
    def dup(query, parameters=()):
        raise IntegrityError("duplicate key")

    monkeypatch.setattr(clients, "rows", dup)
    with pytest.raises(APIException) as raised:
        clients.create_client(uuid4(), uuid4(), {"name": "X", "rut": "1-9"})
    assert raised.value.status_code == 409
    assert raised.value.contract_code == "client_rut_conflict"


def test_client_row_missing_raises_404(monkeypatch):
    monkeypatch.setattr(clients, "rows", _runner([]))
    with pytest.raises(APIException) as raised:
        clients.client_row(uuid4(), uuid4())
    assert raised.value.status_code == 404


def test_update_client_is_sparse(monkeypatch):
    row = _row()
    calls = []

    def fake_rows(query, parameters=()):
        sql = str(query)
        calls.append(sql)
        return [row]

    monkeypatch.setattr(clients, "rows", fake_rows)
    clients.update_client(
        row["id"], uuid4(), {"expected_updated_at": row["updated_at"], "phone": "+56 9 111"}
    )
    update = [sql for sql in calls if sql.startswith("UPDATE")]
    assert "phone=%s" in update[0]
    assert "rut=%s" not in update[0]


def test_update_client_stale_raises_409(monkeypatch):
    row = _row()
    monkeypatch.setattr(clients, "rows", _runner([], **{"FROM public.clients": [row]}))
    with pytest.raises(APIException) as raised:
        clients.update_client(
            row["id"],
            uuid4(),
            {"expected_updated_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "phone": "x"},
        )
    assert raised.value.status_code == 409
    assert raised.value.contract_code == "stale_edit"


def test_deactivate_keeps_the_record(monkeypatch):
    calls = []
    row = _row()
    monkeypatch.setattr(clients, "rows", _runner(calls, **{"SELECT": [row]}))
    clients.deactivate_client(uuid4(), row["id"])
    assert any("is_active=FALSE" in sql and "DELETE" not in sql for sql, _ in calls)


def test_list_orders_active_first(monkeypatch):
    active = _row(name="Activo")
    inactive = _row(name="Inactivo", is_active=False)
    monkeypatch.setattr(
        clients, "rows", _runner([], **{"FROM public.clients": [active, inactive]})
    )
    items = clients.list_clients(uuid4())
    assert [item["name"] for item in items] == ["Activo", "Inactivo"]
    assert items[0]["is_active"] is True


def test_create_project_validates_client_scope(monkeypatch):
    captured = []
    linked = _row()
    monkeypatch.setattr(service, "linkable_client", lambda org, cid: None)
    monkeypatch.setattr(service, "project_row", lambda org, pid: {"id": pid})
    monkeypatch.setattr(service, "project_public", lambda org, row, detail=False: row)
    monkeypatch.setattr(service, "rows", _runner(captured, **{
        "INSERT INTO public.projects": [{"id": "x"}],
        "nextval": [{"seq": 7}],
    }))
    service.create_project(uuid4(), uuid4(), {"name": "P", "client_id": linked["id"]})
    insert = next(sql for sql, _ in captured if "INSERT INTO public.projects" in sql)
    assert "client_id" in insert
    assert linked["id"] in next(params for sql, params in captured if sql == insert)


def test_create_project_foreign_client_rejected(monkeypatch):
    def missing_client(org, cid):
        raise APIException()

    monkeypatch.setattr(service, "linkable_client", missing_client)
    monkeypatch.setattr(service, "rows", _runner([], **{"nextval": [{"seq": 7}]}))
    with pytest.raises(APIException):
        service.create_project(uuid4(), uuid4(), {"name": "P", "client_id": uuid4()})


def test_update_project_can_unlink_client(monkeypatch):
    captured = []
    monkeypatch.setattr(
        service,
        "editable",
        lambda org, pid: {"id": pid, "current_revision": "REV-A", "updated_at": None},
    )
    monkeypatch.setattr(service, "unchanged", lambda row, expected: None)
    monkeypatch.setattr(service, "project_row", lambda org, pid: {"id": pid})
    monkeypatch.setattr(service, "project_public", lambda org, row, detail=False: row)
    monkeypatch.setattr(service, "linkable_client", lambda org, cid: None)
    monkeypatch.setattr(service, "rows", _runner(captured, **{"UPDATE public.projects": [{"id": "x"}]}))
    service.update_project(
        uuid4(),
        uuid4(),
        {"expected_updated_at": datetime.now(timezone.utc), "client_id": None},
    )
    sql, params = captured[0]
    assert "Identifier('client_id')" in sql
    assert params[0] is None
