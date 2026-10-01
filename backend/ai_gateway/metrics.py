"""§08 measurement — org-level AI operating metrics, computed from the two
durable records the gateway already keeps: ``ai_jobs`` (job lifecycle,
proposals, outcomes) and ``ai_audit_logs`` (provider calls, cost, latency).

Honesty rules: no synthetic precision — apply/decline rates only cover the
ops the client reported back, and 'time saved' is a labeled estimate keyed
to applied operations, never presented as a measured duration.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from ai_gateway.jobs import _ai_backend
from pricing.repository import rows

# A rough per-op keystroke baseline — labeled as an estimate in the response.
_SECONDS_PER_APPLIED_OP = 45


def _step_ops(step: Any) -> list[Any]:
    if not isinstance(step, dict):
        return []
    if str(step.get("kind")) not in ("prepare", "ops", "batch_ops"):
        return []
    ops = step.get("ops")
    if isinstance(ops, list):
        return ops
    items = step.get("items")
    if isinstance(items, list):
        return [
            op
            for item in items
            if isinstance(item, dict)
            for op in (item.get("ops") or [])
        ]
    return []


def _proposed_ops(job: dict[str, Any]) -> int:
    """Ops offered to the human: from the latest result steps, else the
    transcript's agent rounds (a resumed job clears result each round)."""
    result = job.get("result")
    sources: list[list[Any]] = []
    if isinstance(result, dict) and isinstance(result.get("steps"), list):
        sources.append(result["steps"])
    else:
        for turn in job.get("transcript") or []:
            if isinstance(turn, dict) and turn.get("role") == "agent":
                steps = turn.get("steps")
                if isinstance(steps, list):
                    sources.append(steps)
    return sum(len(_step_ops(step)) for steps in sources for step in steps)


def ai_metrics(*, org_id: UUID, days: int) -> dict[str, Any]:
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with _ai_backend():
        jobs = rows(
            "SELECT surface, state, error_code, plan, transcript, artifacts,"
            " outcomes, result, created_at, completed_at"
            " FROM public.ai_jobs WHERE org_id = %s AND created_at >= %s",
            [str(org_id), since],
        )
        audits = rows(
            "SELECT model_used, points_debited, tokens_prompt,"
            " tokens_completion, latency_ms"
            " FROM public.ai_audit_logs WHERE org_id = %s AND created_at >= %s",
            [str(org_id), since],
        )

    by_state: Counter[str] = Counter()
    by_surface: Counter[str] = Counter()
    failure_reasons: Counter[str] = Counter()
    durations: list[float] = []
    proposed = applied = declined = apply_failed = 0
    jobs_with_proposal = jobs_with_decision = artifacts_count = 0
    for job in jobs:
        state = str(job["state"])
        by_state[state] += 1
        by_surface[str(job["surface"])] += 1
        if state in ("FAILED", "FAILED_RETRYABLE") and job.get("error_code"):
            failure_reasons[str(job["error_code"])] += 1
        if state == "SUCCEEDED" and job.get("completed_at") and job.get("created_at"):
            durations.append(
                (job["completed_at"] - job["created_at"]).total_seconds()
            )
        proposed += _proposed_ops(job)
        had_proposal = _proposed_ops(job) > 0
        if had_proposal:
            jobs_with_proposal += 1
        outcomes = job.get("outcomes") or []
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        had_decision = False
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            ops = outcome.get("ops")
            count = len(ops) if isinstance(ops, list) else 1
            action = outcome.get("action")
            if action == "applied":
                applied += count
                had_decision = True
            elif action == "declined":
                declined += count
                had_decision = True
            elif action == "apply_failed":
                apply_failed += count
        if had_decision:
            jobs_with_decision += 1
        artifacts = job.get("artifacts") or []
        artifacts_count += len(artifacts)

    finished = sum(
        by_state[s]
        for s in ("SUCCEEDED", "FAILED", "FAILED_RETRYABLE", "CANCELED")
    )
    cost_points = sum(int(a.get("points_debited") or 0) for a in audits)
    tokens_prompt = sum(int(a.get("tokens_prompt") or 0) for a in audits)
    tokens_completion = sum(int(a.get("tokens_completion") or 0) for a in audits)
    by_model: dict[str, dict[str, Any]] = {}
    for audit in audits:
        bucket = by_model.setdefault(
            str(audit["model_used"]),
            {"model": str(audit["model_used"]), "calls": 0, "points": 0,
             "tokens_prompt": 0, "tokens_completion": 0},
        )
        bucket["calls"] += 1
        bucket["points"] += int(audit.get("points_debited") or 0)
        bucket["tokens_prompt"] += int(audit.get("tokens_prompt") or 0)
        bucket["tokens_completion"] += int(audit.get("tokens_completion") or 0)

    decided = applied + declined
    return {
        "window_days": days,
        "jobs": {
            "total": len(jobs),
            "by_state": dict(sorted(by_state.items())),
            "by_surface": dict(sorted(by_surface.items())),
            "completion_rate": (
                str(Decimal(by_state["SUCCEEDED"]) / Decimal(finished))
                if finished
                else None
            ),
            "avg_seconds": (
                str(Decimal(sum(durations) / len(durations)).quantize(Decimal("1")))
                if durations
                else None
            ),
            "failure_reasons": [
                {"code": code, "count": count}
                for code, count in failure_reasons.most_common(10)
            ],
        },
        "commands": {
            "proposed": proposed,
            "applied": applied,
            "declined": declined,
            "apply_failed": apply_failed,
            "apply_rate": (
                str(Decimal(applied) / Decimal(decided)) if decided else None
            ),
        },
        "approvals": {
            "requested": jobs_with_proposal,
            "decided": jobs_with_decision,
        },
        "artifacts_produced": artifacts_count,
        "cost": {
            "points_debited": cost_points,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "calls": len(audits),
            "by_model": sorted(by_model.values(), key=lambda m: -m["points"]),
        },
        "time_saved": {
            "is_estimate": True,
            "basis": "applied_ops * 45s",
            "seconds": applied * _SECONDS_PER_APPLIED_OP,
        },
    }
