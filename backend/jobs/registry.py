"""Job-type registry: which durable jobs exist, who may enqueue them, and how
their payloads are validated. Handlers register themselves at import time via
the `register` decorator (see jobs.handlers, imported at app ready)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from rest_framework import serializers


class JobRegistryError(ValueError):
    pass


class JobPermanentError(Exception):
    """Handler-side signal that the failure is a contract violation —
    permission denied, target not found, invalid state — and retrying the
    same payload can never succeed. The worker marks the job FAILED at once
    instead of burning retries."""


@dataclass(frozen=True)
class JobContext:
    """What a running handler knows about the row it was claimed for."""

    job_id: UUID
    org_id: UUID
    created_by: UUID | None
    attempt: int
    max_attempts: int
    payload: dict[str, Any]


class ProgressReporter(Protocol):
    """The worker's progress channel. `phase` (IA3) is the named intermediate
    state the UI renders next to the percent — None leaves it unchanged."""

    def __call__(self, progress: float, phase: str | None = None) -> None: ...


JobRunner = Callable[[dict[str, Any], JobContext, ProgressReporter], dict[str, Any]]
PayloadAuthorizer = Callable[[dict[str, Any], str], bool]


@dataclass(frozen=True)
class JobSpec:
    job_type: str
    roles: tuple[str, ...]
    payload_serializer: type[serializers.Serializer]
    run: JobRunner
    label: str
    # Optional payload-aware authorization on top of the job-type role list —
    # e.g. one job type covering several operations whose allowed roles differ
    # per payload. Checked at enqueue so a forbidden request is a 403, not a
    # job that retries to a guaranteed failure.
    authorize: PayloadAuthorizer | None = None


_REGISTRY: dict[str, JobSpec] = {}


def register(
    job_type: str,
    *,
    roles: tuple[str, ...],
    payload_serializer: type[serializers.Serializer],
    label: str = "",
    authorize: PayloadAuthorizer | None = None,
) -> Callable[[JobRunner], JobRunner]:
    def decorator(run: JobRunner) -> JobRunner:
        if job_type in _REGISTRY:
            raise JobRegistryError(f"duplicate job type: {job_type}")
        _REGISTRY[job_type] = JobSpec(
            job_type=job_type,
            roles=roles,
            payload_serializer=payload_serializer,
            run=run,
            label=label or job_type,
            authorize=authorize,
        )
        return run

    return decorator


def spec_for(job_type: str) -> JobSpec | None:
    return _REGISTRY.get(job_type)


def public_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def reset_registry() -> None:
    _REGISTRY.clear()
