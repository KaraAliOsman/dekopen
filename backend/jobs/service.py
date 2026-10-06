"""Enqueue/read orchestration for the durable job queue."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from uuid import UUID

from django.db import connection
from psycopg import sql

from authentication.rls import tx_aborted
from jobs import registry, repository


@contextmanager
def job_backend() -> Iterator[None]:
    """job_runs is a service-owned table — only ``service_role`` holds its
    grants. Same save/restore pattern as ``documentary_backend`` so the
    enqueue can run inside a request transaction without widening tenant
    grants on the queue."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('role')")
        previous = str(cursor.fetchone()[0])
        if previous == "none":
            previous = "authenticated"
        cursor.execute("SET LOCAL ROLE service_role")
    try:
        yield
    finally:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(previous)))


@contextmanager
def job_owner() -> Iterator[None]:
    """Read job_runs as the connection owner from INSIDE a member-facing RLS
    scope. ``documentary_backend`` has no grant on the table and ``service_role``
    needs matching JWT claims, so neither reaches it here — but the analytics
    view reads the same count at the ambient role after its scope exits, where
    the session user (the table owner) bypasses RLS. ``RESET ROLE`` restores
    exactly that user; the explicit org filter in the caller's query remains
    the tenant boundary. Same save/restore discipline as ``job_backend``."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('role')")
        previous = str(cursor.fetchone()[0])
        cursor.execute("RESET ROLE")
    try:
        yield
    finally:
        if not tx_aborted():
            with connection.cursor() as cursor:
                if previous == "none":
                    cursor.execute("RESET ROLE")
                else:
                    cursor.execute(
                        sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(previous))
                    )


class JobServiceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def enqueue(
    *,
    org_id: UUID,
    job_type: str,
    payload: dict[str, object],
    idempotency_key: str | None = None,
    max_attempts: int = 3,
    run_after: datetime | None = None,
    created_by: UUID | None = None,
    role: str | None = None,
) -> tuple[dict[str, object], bool]:
    spec = registry.spec_for(job_type)
    if spec is None:
        raise JobServiceError("job_type_unknown")
    serializer = spec.payload_serializer(data=payload)
    if not serializer.is_valid():
        raise JobServiceError("job_payload_invalid")
    validated = dict(serializer.validated_data)
    if spec.authorize is not None:
        # An authorize callback is a role contract — skipping it on role=None
        # would let a future internal enqueue bypass the check silently.
        if role is None or not spec.authorize(validated, role):
            raise JobServiceError("job_permission_denied")
    job, created = repository.insert_job(
        org_id=org_id,
        job_type=job_type,
        payload=validated,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
        run_after=run_after or datetime.now(timezone.utc),
        created_by=created_by,
    )
    # A replayed enqueue asks for a runnable job: a terminal row no longer
    # satisfies that, so requeue it in place with this request's payload and
    # actor — a retry with corrected inputs runs the correction, not the old
    # row. SUCCEEDED stays deduped — the original result is the answer.
    job_id = job.get("id")
    if (
        not created
        and idempotency_key is not None
        and job.get("state") in ("FAILED", "CANCELED")
        and job_id is not None
    ):
        requeued = repository.requeue_terminal(
            org_id=org_id,
            job_id=UUID(str(job_id)),
            payload=validated,
            max_attempts=max_attempts,
            run_after=run_after or datetime.now(timezone.utc),
            created_by=created_by,
        )
        if requeued is not None:
            return requeued, True
        # Lost the race: another request or the worker already moved the row.
        # Return its live state so the caller polls the running retry instead
        # of treating the pre-update FAILED snapshot as terminal.
        live = repository.get_job_by_key(org_id=org_id, job_type=job_type, key=idempotency_key)
        if live is not None:
            return live, False
    return job, created


def get(*, org_id: UUID, job_id: UUID) -> dict[str, object] | None:
    return repository.get_job(org_id=org_id, job_id=job_id)


def list_recent(
    *, org_id: UUID, job_type: str | None, state: str | None, limit: int, offset: int = 0
) -> list[dict[str, object]]:
    items = repository.list_jobs(
        org_id=org_id, job_type=job_type, state=state, limit=limit, offset=offset
    )
    for item in items:
        # §P17 — la etiqueta en español sale del registro del tipo; un tipo
        # sin registrar (demo) conserva su nombre técnico.
        spec = registry.spec_for(str(item.get("type") or ""))
        item["label"] = spec.label if spec is not None else str(item.get("type") or "")
    return items


def retry(
    *, org_id: UUID, job_id: UUID, actor_id: UUID, role: str
) -> dict[str, object]:
    """Requeue a terminally failed/canceled job with its stored payload —
    same input the failed run carried, re-authorized as the retrying actor.
    A job that already left the terminal states (worker or another retry
    won the race) returns its live row instead of a phantom retry."""
    job = repository.get_job(org_id=org_id, job_id=job_id)
    if job is None:
        raise JobServiceError("job_not_found")
    if job["state"] not in ("FAILED", "CANCELED"):
        raise JobServiceError("job_not_terminal")
    spec = registry.spec_for(str(job["type"]))
    if spec is None:
        raise JobServiceError("job_type_unknown")
    if role not in spec.roles:
        raise JobServiceError("job_permission_denied")
    payload = job.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    # The stored payload was validated at enqueue — but specs evolve, so a
    # historical row can hold a shape today's serializer rejects. Revalidate
    # against the CURRENT contract before requeueing: an invalid job must
    # not reach the worker just because it ran under an older spec.
    serializer = spec.payload_serializer(data=payload)
    if not serializer.is_valid():
        raise JobServiceError("job_payload_invalid")
    validated = dict(serializer.validated_data)
    if spec.authorize is not None and not spec.authorize(validated, role):
        raise JobServiceError("job_permission_denied")
    job_id = UUID(str(job["id"]))
    attempts = job.get("max_attempts")
    requeued = repository.requeue_terminal(
        org_id=org_id,
        job_id=job_id,
        payload=validated,
        max_attempts=int(str(attempts or "0")),
        run_after=datetime.now(timezone.utc),
        created_by=actor_id,
    )
    if requeued is None:
        live = repository.get_job(org_id=org_id, job_id=job_id)
        return live if live is not None else job
    return requeued
