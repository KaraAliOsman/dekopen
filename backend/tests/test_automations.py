"""§08 domain automations — emit discipline + handler contracts."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from automations import service as automations_service
from automations import handlers


@pytest.fixture(autouse=True)
def _reregister_handlers():
    """test_jobs' `reset_registry` wipes import-time registrations for the
    whole pytest process; reload the handlers module so every automations
    test sees the built-in job types regardless of file ordering."""
    import importlib

    from jobs import registry

    registry.reset_registry()
    importlib.reload(handlers)
    yield


@contextmanager
def _atomic(*args, **kwargs):
    yield


def _context(created_by=None):
    return SimpleNamespace(
        job_id=uuid4(),
        org_id=uuid4(),
        created_by=created_by or uuid4(),
        attempt=1,
        max_attempts=3,
        payload={},
    )


# --- emit -------------------------------------------------------------------


def test_emit_enqueues_under_service_role_with_idempotency():
    org_id, actor_id = uuid4(), uuid4()
    job_row = {"id": str(uuid4()), "state": "QUEUED"}
    seen = {}

    @contextmanager
    def _job_backend():
        yield

    def _enqueue(**kwargs):
        seen.update(kwargs)
        return job_row, True

    order_id = uuid4()
    with patch("jobs.service.job_backend", side_effect=_job_backend), patch(
        "automations.service._service_claims", side_effect=_atomic
    ), patch("automations.service.transaction.atomic", _atomic), patch(
        "jobs.service.enqueue", side_effect=_enqueue
    ):
        result = automations_service.emit(
            "automation.step_advance",
            org_id=org_id,
            actor_id=actor_id,
            idempotency_key="auto:step:x:done",
            order_id=str(order_id),
            step_code="CUT",
        )
    assert result == {"job_id": job_row["id"], "created": True}
    assert seen["idempotency_key"] == "auto:step:x:done"
    assert seen["payload"] == {"order_id": str(order_id), "step_code": "CUT"}
    assert seen["created_by"] == actor_id


def test_emit_never_propagates_queue_faults():
    """A queue hiccup must not roll back the freeze/payment it rode on."""

    @contextmanager
    def _job_backend():
        yield

    with patch("jobs.service.job_backend", side_effect=_job_backend), patch(
        "automations.service._service_claims", side_effect=_atomic
    ), patch("jobs.service.enqueue", side_effect=RuntimeError("queue down")):
        result = automations_service.emit(
            "automation.step_advance",
            org_id=uuid4(),
            actor_id=uuid4(),
            idempotency_key="k",
            order_id=str(uuid4()),
            step_code="CUT",
        )
    assert result is None


def test_service_claims_overrides_and_restores():
    cursor = MagicMock()
    cursor.fetchone.return_value = ('{"sub":"user-1"}',)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.needs_rollback = False
    with patch("automations.service.connection", connection):
        with automations_service._service_claims():
            pass
    calls = [str(c.args[0]) for c in cursor.execute.call_args_list]
    assert any("service_role" in str(c.args[1]) for c in cursor.execute.call_args_list if len(c.args) > 1)
    # restore ran last with the captured claims
    assert cursor.execute.call_args_list[-1].args[1] == ['{"sub":"user-1"}']
    assert calls


def test_service_claims_restores_empty_when_unset():
    cursor = MagicMock()
    cursor.fetchone.return_value = (None,)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.needs_rollback = False
    with patch("automations.service.connection", connection):
        with automations_service._service_claims():
            pass
    assert cursor.execute.call_args_list[-1].args[1] == ["{}"]


# --- registry contract ------------------------------------------------------


def test_automation_types_registered_and_role_gated():
    from jobs.registry import spec_for

    for job_type in (
        "automation.prep_forecast",
        "automation.purchase_task",
        "automation.catalog_task",
        "automation.commercial_refresh",
        "automation.step_advance",
    ):
        spec = spec_for(job_type)
        assert spec is not None, job_type
        # Retry stays open to the roles that would act on the task; the
        # payload is refs-only so enqueueing carries no domain authority.
        assert "WORKSHOP_MANAGER" in spec.roles


def test_handlers_require_an_actor():
    from jobs.registry import JobPermanentError

    context = _context(created_by=None)
    context.created_by = None
    with pytest.raises(JobPermanentError, match="automation_actor_required"):
        handlers._job_claims(context)


# --- prep_forecast ----------------------------------------------------------


def test_prep_forecast_reports_coverage_and_project():
    context = _context()
    version_id = uuid4()
    coverage = {
        "version_id": str(version_id),
        "shortages": 1,
        "lines": [
            {"purchasing_sku": "P-60", "order_type": "PROFILE", "category": "X",
             "unit": "BAR", "required": "10", "available": "4",
             "shortage": "6", "recommended_purchase": "6"},
            {"purchasing_sku": "V-4", "order_type": "GLASS", "category": "X",
             "unit": "EA", "required": "2", "available": "9",
             "shortage": "0", "recommended_purchase": "0"},
        ],
    }

    def _one(query, params, code="x"):
        if "project_versions" in query:
            return {"project_id": str(uuid4()), "revision_code": "A",
                    "production_allowed": True}
        return {"code": "PRY-0042"}

    with patch("automations.handlers.transaction.atomic", side_effect=_atomic), patch(
        "automations.handlers._set_claims"
    ), patch(
        "documents.repository.documentary_backend", side_effect=_atomic
    ), patch("documents.repository.one", side_effect=_one), patch(
        "inventory.production_stock.coverage_for_version", return_value=coverage
    ):
        result = handlers.prep_forecast(
            {"version_id": str(version_id)}, context, lambda p: None
        )
    assert result["shortages"] == 1
    assert result["covered"] == 1
    assert result["shortage_lines"][0]["purchasing_sku"] == "P-60"
    assert result["revision_code"] == "A"


# --- purchase_task ----------------------------------------------------------


def test_purchase_task_prefers_order_reservation_shorts():
    context = _context()
    order_payload = {
        "version_id": str(uuid4()),
        "optimization": {
            "stock_reservations": [
                {"sku": "P-60", "name": "Marco", "category": "PROFILE",
                 "unit": "BAR", "needed": "10", "reserved": "4", "short": "6"},
                {"sku": "V-4", "name": "Vidrio", "category": "GLASS",
                 "unit": "EA", "needed": "2", "reserved": "2", "short": "0"},
            ]
        },
    }
    with patch("automations.handlers.transaction.atomic", side_effect=_atomic), patch(
        "automations.handlers._set_claims"
    ), patch(
        "documents.repository.documentary_backend", side_effect=_atomic
    ), patch(
        "documents.repository.one",
        return_value={"id": "o1", "order_code": "OT-7", "payload_json": order_payload},
    ), patch(
        "inventory.production_stock.coverage_for_version"
    ) as cov:
        result = handlers.purchase_task({"order_id": str(uuid4())}, context, lambda p: None)
    cov.assert_not_called()
    assert result["source"] == "order_reservations"
    assert result["shortage_count"] == 1
    assert result["purchase_lines"][0]["sku"] == "P-60"


def test_purchase_task_falls_back_to_version_forecast():
    context = _context()
    order_payload = {"version_id": str(uuid4())}
    coverage = {"lines": [
        {"purchasing_sku": "P-60", "order_type": "PROFILE", "category": "X",
         "unit": "BAR", "required": "10", "available": "0",
         "shortage": "10", "recommended_purchase": "10"},
    ], "shortages": 1}
    with patch("automations.handlers.transaction.atomic", side_effect=_atomic), patch(
        "automations.handlers._set_claims"
    ), patch(
        "documents.repository.documentary_backend", side_effect=_atomic
    ), patch(
        "documents.repository.one",
        return_value={"id": "o1", "order_code": "OT-9", "payload_json": order_payload},
    ), patch(
        "inventory.production_stock.coverage_for_version", return_value=coverage
    ):
        result = handlers.purchase_task({"order_id": str(uuid4())}, context, lambda p: None)
    assert result["source"] == "version_forecast"
    assert result["purchase_lines"][0]["purchasing_sku"] == "P-60"


# --- catalog_task -----------------------------------------------------------


def test_catalog_task_flattens_readiness_blockers():
    context = _context()
    readiness = {
        "level": "MANUFACTURING_INCOMPLETE",
        "levels": [
            {"level": "DESIGN_VALID", "ok": True, "blockers": []},
            {"level": "MANUFACTURING_INCOMPLETE", "ok": False, "blockers": [
                {"code": "rebate_missing", "missing_authority": "rebaje mm",
                 "affected": "SYS-1", "why": "sin rebaje no hay cálculo",
                 "action": "declarar rebaje"},
            ]},
        ],
    }
    with patch(
        "automations.handlers.authenticated_rls_context", side_effect=_atomic
    ), patch(
        "documents.repository.one", return_value={"name": "Sistema X"}
    ), patch(
        "catalogs.readiness.catalog_readiness", return_value=readiness
    ):
        result = handlers.catalog_task(
            {"system_id": str(uuid4()), "version_id": str(uuid4())},
            context, lambda p: None,
        )
    assert result["blocker_count"] == 1
    assert result["blockers"][0]["code"] == "rebate_missing"
    assert result["system_name"] == "Sistema X"


# --- commercial_refresh -----------------------------------------------------


def test_commercial_refresh_returns_ledger_state():
    context = _context()
    summary = {
        "payments": [{"id": "p1"}, {"id": "p2"}],
        "invoices": [],
        "collected": "500",
        "quote_total_gross": "1000",
        "balance": "500",
        "currency": "CLP",
        "status": "PARTIAL",
        "sealed_revision": "B",
    }
    with patch("automations.handlers.transaction.atomic", side_effect=_atomic), patch(
        "automations.handlers._set_claims"
    ), patch("projects.payments.list_payments", return_value=summary):
        result = handlers.commercial_refresh(
            {"project_id": str(uuid4()), "payment_id": str(uuid4())},
            context, lambda p: None,
        )
    assert result["status"] == "PARTIAL"
    assert result["collected"] == "500"
    assert result["payments"] == 2


# --- step_advance -----------------------------------------------------------


def test_step_advance_reports_true_successor():
    context = _context()
    with patch("automations.handlers.transaction.atomic", side_effect=_atomic), patch(
        "automations.handlers._set_claims"
    ), patch(
        "documents.repository.documentary_backend", side_effect=_atomic
    ), patch(
        "documents.repository.one",
        return_value={"order_code": "OT-3", "status": "IN_PROGRESS"},
    ), patch(
        "documents.repository.rows",
        return_value=[{"code": "GLAZE", "label": "Vidriado", "sequence": 4,
                       "status": "READY"}],
    ):
        result = handlers.step_advance(
            {"order_id": str(uuid4()), "step_code": "HARDWARE"},
            context, lambda p: None,
        )
    assert result["completed_step"] == "HARDWARE"
    assert result["next_step"]["code"] == "GLAZE"


def test_step_advance_terminal_order_has_no_next_step():
    context = _context()
    with patch("automations.handlers.transaction.atomic", side_effect=_atomic), patch(
        "automations.handlers._set_claims"
    ), patch(
        "documents.repository.documentary_backend", side_effect=_atomic
    ), patch(
        "documents.repository.one",
        return_value={"order_code": "OT-4", "status": "COMPLETED"},
    ), patch("documents.repository.rows", return_value=[]):
        result = handlers.step_advance(
            {"order_id": str(uuid4()), "step_code": "PACK"},
            context, lambda p: None,
        )
    assert result["next_step"] is None
