"""IA2 §6 — métricas por job del runtime del agente.

Un contador en memoria por proceso (el worker solo registra; el panel de
telemetría org-level ya lo cubre ``ai_gateway.metrics`` — esto es el
diagnóstico por job). Cada job reporta: rondas usadas, consultas y
herramientas ejecutadas, pasos propuestos/aceptados/rechazados, créditos
debitados, tiempo total y resultado final. Nada de esto viaja al modelo.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

_lock = threading.Lock()
_jobs: dict[str, "JobMetrics"] = {}

# Ventana acotada — el registro es diagnóstico del proceso, no archivo:
# jobs viejos se podan para que el dict no crezca sin límite.
MAX_TRACKED_JOBS = 500


@dataclass
class JobMetrics:
    job_id: str
    surface: str
    started_at: float = field(default_factory=time.monotonic)
    rounds: int = 0
    queries: int = 0
    tool_calls: int = 0
    steps_proposed: int = 0
    steps_accepted: int = 0
    steps_rejected: int = 0
    credits_debited: int = 0
    clarify_count: int = 0
    finished_at: float | None = None
    outcome: str | None = None

    def snapshot(self) -> dict[str, Any]:
        elapsed = (self.finished_at or time.monotonic()) - self.started_at
        return {
            "job_id": self.job_id,
            "surface": self.surface,
            "elapsed_s": round(elapsed, 3),
            "rounds": self.rounds,
            "queries": self.queries,
            "tool_calls": self.tool_calls,
            "steps_proposed": self.steps_proposed,
            "steps_accepted": self.steps_accepted,
            "steps_rejected": self.steps_rejected,
            "credits_debited": self.credits_debited,
            "clarify_count": self.clarify_count,
            "outcome": self.outcome,
        }


def begin(job_id: UUID | str | None, surface: str) -> JobMetrics | None:
    if job_id is None:
        return None
    with _lock:
        if len(_jobs) >= MAX_TRACKED_JOBS:
            oldest = min(_jobs.values(), key=lambda item: item.started_at)
            _jobs.pop(oldest.job_id, None)
        metrics = JobMetrics(job_id=str(job_id), surface=surface)
        _jobs[metrics.job_id] = metrics
        return metrics


def record(metrics: JobMetrics | None, **deltas: int) -> None:
    """Suma contadores: record(m, rounds=1, queries=2)."""
    if metrics is None:
        return
    with _lock:
        for key, delta in deltas.items():
            if hasattr(metrics, key):
                setattr(metrics, key, getattr(metrics, key) + delta)


def finish(metrics: JobMetrics | None, outcome: str) -> None:
    if metrics is None:
        return
    with _lock:
        metrics.finished_at = time.monotonic()
        metrics.outcome = outcome


def snapshot(job_id: UUID | str) -> dict[str, Any] | None:
    with _lock:
        metrics = _jobs.get(str(job_id))
        return metrics.snapshot() if metrics is not None else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        return [
            item.snapshot()
            for item in sorted(
                _jobs.values(), key=lambda entry: entry.started_at, reverse=True
            )[:limit]
        ]
