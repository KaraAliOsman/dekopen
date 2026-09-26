"""§08 measurement — outcome recording + org-level AI metrics."""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_gateway import jobs, metrics


def _job(**over):
    job = {
        "surface": "position",
        "state": "SUCCEEDED",
        "error_code": None,
        "plan": [],
        "transcript": [],
        "artifacts": [],
        "outcomes": [],
        "result": {"reply": "ok", "steps": []},
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=2),
        "completed_at": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    job.update(over)
    return job


def _audit(**over):
    audit = {
        "model_used": "mimo",
        "points_debited": 3,
        "tokens_prompt": 10,
        "tokens_completion": 20,
        "latency_ms": 5,
    }
    audit.update(over)
    return audit


def _patch_rows(monkeypatch, job_rows, audit_rows):
    queries = iter([job_rows, audit_rows])

    def fake_rows(query, parameters=()):
        return queries.__next__()

    monkeypatch.setattr(metrics, "rows", fake_rows)


def test_metrics_empty_window(monkeypatch):
    _patch_rows(monkeypatch, [], [])
    out = metrics.ai_metrics(org_id=uuid4(), days=30)
    assert out["jobs"]["total"] == 0
    assert out["jobs"]["completion_rate"] is None
    assert out["commands"]["proposed"] == 0
    assert out["cost"]["calls"] == 0
    assert out["time_saved"]["is_estimate"] is True


def test_metrics_counts_states_surfaces_and_failures(monkeypatch):
    _patch_rows(
        monkeypatch,
        [
            _job(),
            _job(state="FAILED", error_code="provider_timeout"),
            _job(state="FAILED_RETRYABLE", error_code="provider_timeout"),
            _job(state="CANCELED", surface="project"),
        ],
        [],
    )
    out = metrics.ai_metrics(org_id=uuid4(), days=30)
    assert out["jobs"]["total"] == 4
    assert out["jobs"]["by_state"]["SUCCEEDED"] == 1
    assert out["jobs"]["by_surface"]["project"] == 1
    assert out["jobs"]["failure_reasons"][0]["code"] == "provider_timeout"
    # 1 succeeded of 4 finished -> 0.25
    assert out["jobs"]["completion_rate"].startswith("0.25")


def test_metrics_proposed_vs_outcomes(monkeypatch):
    steps = [
        {"kind": "ops", "ops": [{"op": "a"}, {"op": "b"}]},
        {"kind": "batch_ops", "items": [{"ops": [{"op": "c"}]}]},
        {"kind": "navigate", "path": "/x"},  # not counted
    ]
    _patch_rows(
        monkeypatch,
        [
            _job(
                result={"steps": steps},
                outcomes=[
                    {"action": "applied", "ops": ["a", "b"]},
                    {"action": "declined", "ops": ["c"]},
                    {"action": "apply_failed", "ops": ["z"]},
                ],
            ),
            _job(state="SUCCEEDED"),  # no proposal
        ],
        [_audit(), _audit(points_debited=5, model_used="other")],
    )
    out = metrics.ai_metrics(org_id=uuid4(), days=30)
    assert out["commands"]["proposed"] == 3
    assert out["commands"]["applied"] == 2
    assert out["commands"]["declined"] == 1
    assert out["commands"]["apply_failed"] == 1
    assert out["commands"]["apply_rate"] == "0.6666666666666666666666666667"
    assert out["approvals"]["requested"] == 1
    assert out["approvals"]["decided"] == 1
    assert out["cost"]["points_debited"] == 8
    assert out["cost"]["by_model"][0]["model"] == "other"
    assert out["time_saved"]["seconds"] == 2 * metrics._SECONDS_PER_APPLIED_OP


def test_metrics_falls_back_to_transcript_when_result_cleared(monkeypatch):
    """A resumed job nulls result — proposals are counted from the
    transcript's agent rounds so the ratio stays honest."""
    _patch_rows(
        monkeypatch,
        [
            _job(
                result=None,
                transcript=[
                    {"role": "user", "text": "hi"},
                    {"role": "agent", "steps": [{"kind": "ops", "ops": [{"op": "a"}]}]},
                ],
            )
        ],
        [],
    )
    out = metrics.ai_metrics(org_id=uuid4(), days=30)
    assert out["commands"]["proposed"] == 1


def test_metrics_parses_outcomes_stored_as_text(monkeypatch):
    _patch_rows(
        monkeypatch,
        [_job(outcomes=json.dumps([{"action": "applied", "ops": ["a"]}]))],
        [],
    )
    out = metrics.ai_metrics(org_id=uuid4(), days=30)
    assert out["commands"]["applied"] == 1


def test_record_outcome_writes_deduped_entry(monkeypatch):
    captured = {}

    def fake_rows(query, parameters=()):
        captured["query"] = query
        captured["parameters"] = parameters
        return [{"id": str(parameters[1])}]

    # The step must exist in the transcript — outcomes can only be recorded
    # against steps the run actually proposed.
    monkeypatch.setattr(
        jobs,
        "get_job",
        lambda **kw: {
            "transcript": [
                {"role": "agent", "steps": [
                    {"kind": "navigate"}, {"kind": "ops"},
                ]}
            ]
        },
    )
    monkeypatch.setattr(jobs, "rows", fake_rows)
    out = jobs.record_outcome(
        org_id=uuid4(),
        user_id=uuid4(),
        job_id=uuid4(),
        entry={"turn_index": 0, "step_index": 1, "action": "applied",
               "ops": ["change_opening"]},
    )
    assert out["recorded"] is True
    entry = json.loads(captured["parameters"][0])[0]
    assert entry["action"] == "applied"
    assert entry["ops"] == ["change_opening"]
    dedupe = json.loads(captured["parameters"][4])
    assert dedupe == [
        {"turn_index": 0, "step_index": 1, "action": "applied"}
    ]
    assert "NOT outcomes @>" in captured["query"]


def test_record_outcome_dedupe_returns_unrecorded(monkeypatch):
    monkeypatch.setattr(
        jobs,
        "get_job",
        lambda **kw: {
            "transcript": [
                {"role": "agent", "steps": [
                    {"kind": "navigate"}, {"kind": "ops"},
                ]}
            ]
        },
    )
    monkeypatch.setattr(jobs, "rows", lambda *a, **k: [])
    out = jobs.record_outcome(
        org_id=uuid4(),
        user_id=uuid4(),
        job_id=uuid4(),
        entry={"turn_index": 0, "step_index": 1, "action": "applied", "ops": []},
    )
    assert out["recorded"] is False


def test_record_outcome_rejects_fabricated_step(monkeypatch):
    """An outcome naming a turn/step the transcript never proposed is not
    telemetry — refuse it instead of counting a phantom click."""
    monkeypatch.setattr(
        jobs,
        "get_job",
        lambda **kw: {
            "transcript": [
                {"role": "agent", "steps": [{"kind": "navigate"}]}
            ]
        },
    )
    monkeypatch.setattr(jobs, "rows", lambda *a, **k: [{"id": "x"}])
    assert (
        jobs.record_outcome(
            org_id=uuid4(),
            user_id=uuid4(),
            job_id=uuid4(),
            entry={"turn_index": 0, "step_index": 0, "action": "applied"},
        )
        is None
    )  # navigate is not an actionable step
    monkeypatch.setattr(
        jobs,
        "get_job",
        lambda **kw: {"transcript": [{"role": "agent", "steps": []}]},
    )
    assert (
        jobs.record_outcome(
            org_id=uuid4(),
            user_id=uuid4(),
            job_id=uuid4(),
            entry={"turn_index": 0, "step_index": 3, "action": "applied"},
        )
        is None
    )
