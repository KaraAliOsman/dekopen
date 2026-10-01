"""Analytics aggregates: org-scoped reads of the live operational tables."""

from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from analytics import service


@contextmanager
def _atomic():
    yield


class _FakeTs:
    def isoformat(self) -> str:
        return "2026-09-23T00:00:00+00:00"


def test_operational_summary_aggregates_live_tables(monkeypatch) -> None:
    org_id = uuid4()
    seen_params: list[list] = []
    seen_sql: list[str] = []

    def fake_rows(sql_text: str, params: list) -> list[dict]:
        lowered = " ".join(sql_text.lower().split())
        seen_params.append(list(params))
        if "order_type = 'workshop_ot'" in lowered:
            return [{"status": "INSTALLED", "n": 2}]
        if "order_type <> 'workshop_ot'" in lowered:
            return [{"status": "FULFILLED", "n": 1}]
        if "document_artifacts" in lowered:
            return [{"document_type": "DOC-03", "n": 4}]
        if "limit 10" in lowered:
            return [
                {
                    "event": "WO_INSTALLED",
                    "order_code": "OT-1",
                    "created_at": _FakeTs(),
                }
            ]
        return []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        seen_params.append(list(params))
        if "extract(epoch" in lowered:
            return {"release_to_dispatch_hours": 4.26}
        if "wo_dispatched" in lowered:
            return {"dispatched_30d": 3, "installed_30d": 2, "completed_30d": 2}
        if "inventory_items" in lowered:
            return {"n": 7}
        if "offcut_inventory" in lowered:
            return {"n": 2}
        if "production_allowed" in lowered:
            return {
                "versions_ready": 2,
                "work_orders_shortage": 1,
                "dispatch_ready": 1,
                "catalog_gaps": 0,
            }
        if "deliveries" in lowered:
            seen_sql.append(lowered)
            return {"today": 2, "overdue": 1}
        if "projects" in lowered:
            return {"projects": 5, "positions": 9, "sealed_versions": 3}
        raise AssertionError(f"unexpected one(): {lowered}")

    monkeypatch.setattr("analytics.service.rows", fake_rows)
    monkeypatch.setattr("analytics.service.one", fake_one)
    with patch("analytics.service.transaction.atomic", side_effect=_atomic), patch(
        "analytics.service.documentary_backend", side_effect=_atomic
    ):
        out = service.operational_summary(org_id=org_id)

    assert out["work_orders"] == {"INSTALLED": 2}
    assert out["supplier_orders"] == {"FULFILLED": 1}
    assert out["throughput_30d"]["dispatched_30d"] == 3
    assert out["avg_release_to_dispatch_hours"] == 4.3
    assert out["inventory"] == {"items": 7, "offcuts": 2}
    assert out["prep"]["versions_ready"] == 2
    assert out["prep"]["work_orders_shortage"] == 1
    assert out["prep"]["dispatch_ready"] == 1
    assert out["deliveries"] == {"today": 2, "overdue": 1}
    assert out["documents"] == {"DOC-03": 4}
    assert out["projects"]["sealed_versions"] == 3
    assert out["recent_events"][0]["event"] == "WO_INSTALLED"
    # every aggregate ran org-scoped
    assert seen_params and all(set(p) == {str(org_id)} for p in seen_params)
    # the "business day" is the organization's own timezone, never UTC or a
    # hardcoded locale — deliveries classify at the tenant's local midnight
    assert seen_sql and all(
        "tenancy_organizations" in sql and "org.timezone" in sql for sql in seen_sql
    )


def test_failed_jobs_count_runs_org_scoped(monkeypatch) -> None:
    """job_runs is service-owned: the count must run outside the member-facing
    RLS context (the view calls it after documentary_scope exits) — here we
    only pin the org-scoped query itself."""
    org_id = uuid4()

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        assert "job_runs" in lowered
        assert params == [str(org_id)]
        return {"n": 3}

    monkeypatch.setattr("analytics.service.one", fake_one)
    assert service.failed_jobs_count(org_id=org_id) == 3
