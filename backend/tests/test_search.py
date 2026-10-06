"""§7 global search: deterministic grouped results, org-scoped, read-only."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest

from search import service


@pytest.fixture
def fake_rows(monkeypatch):
    calls: list[tuple[str, list]] = []
    responses: list[list[dict]] = []
    documentary: list[bool] = []

    def _rows(sql, params=()):
        calls.append((sql, list(params)))
        return responses.pop(0) if responses else []

    @contextmanager
    def _documentary():
        documentary.append(True)
        yield

    monkeypatch.setattr(service, "rows", _rows)
    monkeypatch.setattr(service, "documentary_backend", _documentary)
    return calls, responses, documentary


def _seed(responses):
    pid, pos, aid = uuid4(), uuid4(), uuid4()
    responses.extend(
        [
            [{"id": pid, "code": "PRJ-1", "name": "Hotel Sur", "client_name": "Inmobiliaria"}],
            [{"id": uuid4(), "name": "Inmobiliaria Sur", "rut": "76.123.456-7"}],
            [
                {
                    "id": pid,
                    "code": "PRJ-1",
                    "name": "Hotel Sur",
                    "client_name": "Inmobiliaria",
                    "current_revision": "B",
                }
            ],
            [
                {
                    "id": pos,
                    "project_id": pid,
                    "location_tag": "D101",
                    "typology": "FIXED",
                    "project_code": "PRJ-1",
                    "project_name": "Hotel Sur",
                }
            ],
            [{"id": aid, "code": "DEMO_60", "name": "Demo 60"}],
            [{"id": aid, "sku": "MRC-100", "name": "Marco", "system_code": "DEMO_60"}],
            [{"id": aid, "sku": "GL-44", "name": "4+4 incoloro", "kind": "GLASS"}],
            [
                {
                    "id": uuid4(),
                    "order_code": "OT-9",
                    "kind": "WORKSHOP_OT",
                    "status": "IN_PROGRESS",
                }
            ],
            [
                {
                    "id": uuid4(),
                    "remnant_code": "RT-000045",
                    "kind": "SHEET",
                    "status": "AVAILABLE",
                    "sheet_workshop_sku": "CH-44",
                }
            ],
            [
                {
                    "id": uuid4(),
                    "receipt_code": "REC-000012",
                    "order_code": "OC-000123",
                }
            ],
            [{"id": uuid4(), "invoice_code": "FAC-3", "project_id": pid, "project_code": "PRJ-1"}],
            [{"id": uuid4(), "note_code": "GD-2", "order_code": "OT-9"}],
            [{"id": aid, "sku": "SIL-1", "name": "Silicona", "category": "SUPPLY"}],
        ]
    )
    return pid, pos


def test_short_or_empty_query_returns_nothing(fake_rows):
    calls, _, _ = fake_rows
    assert service.search(uuid4(), " a ") == {"results": []}
    assert calls == []


def test_every_group_maps_row_to_result(fake_rows):
    calls, responses, _ = fake_rows
    pid, pos = _seed(responses)
    out = service.search(uuid4(), "hotel")
    by_group = {}
    for item in out["results"]:
        by_group.setdefault(item["group"], []).append(item)
    assert by_group["projects"][0]["title"] == "PRJ-1 · Hotel Sur"
    assert by_group["projects"][0]["path"] == f"/projects/{pid}"
    assert by_group["clients"][0]["title"] == "Inmobiliaria Sur"
    assert by_group["quotations"][0]["title"] == "PRJ-1 · B"
    assert by_group["quotations"][0]["path"] == f"/projects/{pid}"
    assert by_group["positions"][0]["path"] == f"/projects/{pid}/positions/{pos}/edit"
    assert by_group["systems"][0]["title"] == "DEMO_60 · Demo 60"
    assert len(by_group["articles"]) == 2
    assert by_group["orders"][0]["path"] == "/production"
    assert by_group["remnants"][0]["title"] == "RT-000045"
    assert by_group["remnants"][0]["subtitle"] == "SHEET · AVAILABLE · CH-44"
    assert by_group["receipts"][0]["title"] == "REC-000012"
    assert by_group["receipts"][0]["path"] == "/purchasing"
    assert by_group["documents"][0]["title"] == "FAC-3"
    assert by_group["documents"][1]["title"] == "GD-2"
    assert by_group["inventory"][0]["path"] == "/purchasing"


def test_queries_are_org_scoped_and_pattern_safe(fake_rows):
    calls, responses, _ = fake_rows
    org = uuid4()
    _seed(responses)
    service.search(org, "%_;DROP--")
    for sql, params in calls:
        # org binding is a %s parameter in every query — bare "org_id=%s" for
        # tenant-only tables, the canonical visibility rule for catalog ones.
        # Queries joining a parent table bind it again for parent scope.
        assert "org_id=%s" in sql or "org_id = %s" in sql
        assert params[0] == str(org)
        assert "POSITION" in sql
        assert all(p == "%_;drop--" or p == str(org) for p in params[1:]), params
        assert any(p == "%_;drop--" for p in params)


def test_catalog_queries_use_canonical_visibility(fake_rows):
    """Systems/articles/infills must resolve through the same
    org-or-global-system rule the catalog service exposes — not a bare
    org_id filter that would hide global catalog rows."""
    calls, _, _ = fake_rows
    service.search(uuid4(), "ma")
    global_aware = [sql for sql, _ in calls if "is_global" in sql]
    assert len(global_aware) == 3
    for sql in global_aware:
        assert "org_id = %s OR" in sql


def test_joined_parents_are_tenant_scoped(fake_rows):
    """A child row matching the caller's org must not leak a parent that
    belongs to another tenant through the subtitle join."""
    calls, _, _ = fake_rows
    service.search(uuid4(), "ma")
    joins = {
        "project_positions": "JOIN public.projects pr ON pr.id = p.project_id",
        "profile_articles": "JOIN public.profile_systems s ON s.id = a.system_id",
        "project_invoices": "JOIN public.projects pr ON pr.id = i.project_id",
        "dispatch_notes": "JOIN public.orders o ON o.id = d.work_order_id",
    }
    for marker in joins.values():
        sql = next(s for s, _ in calls if marker in s)
        assert sql.count("org_id") >= 2, sql


def test_supplier_folios_resolve_under_documentary_role(fake_rows):
    """OC-/REC- are only visible through the documentary role: the orders RLS
    exposes just WORKSHOP_OT to `authenticated`, so purchasing-capable roles
    must run those two groups under `documentary_backend`."""
    calls, responses, documentary = fake_rows
    _seed(responses)
    out = service.search(uuid4(), "oc-000123")
    assert documentary == [True, True]  # orders + receipts only
    assert "documentary" not in "".join(sql.lower() for sql, _ in calls)
    by_group = {item["group"]: item for item in out["results"]}
    assert by_group["receipts"]["title"] == "REC-000012"


def test_installer_stays_in_member_scope(fake_rows):
    calls, responses, documentary = fake_rows
    _seed(responses)
    del responses[8]  # receipts group is not queried outside purchasing roles
    out = service.search(uuid4(), "ot-9", role="INSTALLER")
    assert documentary == []
    groups = {item["group"] for item in out["results"]}
    assert "receipts" not in groups
    assert groups.isdisjoint({"clients", "documents"})
