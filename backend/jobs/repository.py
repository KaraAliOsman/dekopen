"""Raw access to public.job_runs — a service-owned table reached only as the
connection owner. Every query binds org_id explicitly; RLS is never relied on
here because worker claims and service reads bypass it by design."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from django.db import connection, DatabaseError
from psycopg import sql

from pricing.repository import json_text, rows

STALE_LOCK_SECONDS = 600

_JSON_COLUMNS = frozenset({"payload", "result", "error"})


class LockLostError(DatabaseError):
    """The row was reclaimed by another worker mid-execution."""


def _decode(record: dict[str, object]) -> dict[str, object]:
    for key in record.keys() & _JSON_COLUMNS:
        if isinstance(record[key], str):
            record[key] = json.loads(record[key])
    return record


def insert_job(
    *,
    org_id: UUID,
    job_type: str,
    payload: dict[str, object],
    idempotency_key: str | None,
    max_attempts: int,
    run_after: datetime,
    created_by: UUID | None,
) -> tuple[dict[str, object], bool]:
    """Insert a queued job; on idempotency conflict return the live row."""
    # ON CONFLICT DO NOTHING never aborts the enclosing transaction (unlike a
    # 23505 exception, after which any follow-up SELECT raises 25P02) — the
    # emitter may legitimately share a transaction with the event it records.
    record = rows(
        """
        INSERT INTO public.job_runs
            (org_id, type, payload, idempotency_key, max_attempts, run_after, created_by)
        VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
        ON CONFLICT (org_id, type, idempotency_key) WHERE idempotency_key IS NOT NULL
        DO NOTHING
        RETURNING *
        """,
        [
            str(org_id),
            job_type,
            json_text(payload),
            idempotency_key,
            max_attempts,
            run_after,
            str(created_by) if created_by else None,
        ],
    )
    if record:
        return _decode(record[0]), True
    existing = get_job_by_key(org_id=org_id, job_type=job_type, key=idempotency_key)
    if existing is None:
        raise DatabaseError("job_idempotency_conflict_unresolved")
    return existing, False


def requeue_terminal(
    *,
    org_id: UUID,
    job_id: UUID,
    payload: dict[str, object],
    max_attempts: int,
    run_after: datetime,
    created_by: UUID | None,
) -> dict[str, object] | None:
    """Requeue a terminally failed/canceled job in place — a replayed
    idempotent enqueue restarts the same row carrying the *new* request's
    validated payload, retry budget and actor, with a fresh attempt budget.
    Returns None when the row already left the terminal states (another
    request or the worker won the race), so the caller dedupes instead."""
    record = rows(
        """
        UPDATE public.job_runs
        SET state = 'QUEUED',
            payload = %s::jsonb,
            attempt = 0,
            max_attempts = %s,
            progress = 0,
            progress_phase = NULL,
            error = NULL,
            result = NULL,
            locked_by = NULL,
            locked_at = NULL,
            run_after = %s,
            started_at = NULL,
            completed_at = NULL,
            created_by = %s,
            updated_at = NOW()
        WHERE org_id = %s AND id = %s AND state IN ('FAILED', 'CANCELED')
        RETURNING *
        """,
        [
            json_text(payload),
            max_attempts,
            run_after,
            str(created_by) if created_by else None,
            str(org_id),
            str(job_id),
        ],
    )
    return _decode(record[0]) if record else None


def get_job(*, org_id: UUID, job_id: UUID) -> dict[str, object] | None:
    record = rows(
        "SELECT * FROM public.job_runs WHERE org_id = %s AND id = %s",
        [str(org_id), str(job_id)],
    )
    return _decode(record[0]) if record else None


def get_job_by_key(*, org_id: UUID, job_type: str, key: str) -> dict[str, object] | None:
    record = rows(
        """
        SELECT * FROM public.job_runs
        WHERE org_id = %s AND type = %s AND idempotency_key = %s
        """,
        [str(org_id), job_type, key],
    )
    return _decode(record[0]) if record else None


def list_jobs(
    *,
    org_id: UUID,
    job_type: str | None = None,
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, object]]:
    clauses = ["org_id = %s"]
    parameters: list[object] = [str(org_id)]
    if job_type:
        clauses.append("type = %s")
        parameters.append(job_type)
    if state:
        clauses.append("state = %s")
        parameters.append(state)
    parameters.extend([limit, offset])
    return [
        _decode(record)
        for record in rows(
            f"""
            SELECT id, type, state, progress, result, error, attempt,
                   max_attempts, created_at, started_at, completed_at,
                   /* The AI run's own job id lets the jobs list deep-link to
                    * the assistant workspace — expose just the id, not the
                    * service-owned payload. */
                   CASE WHEN type = 'ai.agent.run'
                        THEN payload->>'ai_job_id'
                        ELSE NULL
                   END AS ai_job_id
            FROM public.job_runs
            WHERE {" AND ".join(clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            parameters,
        )
    ]


def claim_next(*, worker_id: str) -> dict[str, object] | None:
    """Atomically claim the single oldest runnable job; one worker wins.

    Jobs are claimed one at a time, right before execution — a row can never
    sit inside a claimed batch waiting for earlier work while its lock ages
    toward the stale cutoff."""
    if connection.vendor == "postgresql":
        record = rows(
            """
            UPDATE public.job_runs
            SET state = 'RUNNING',
                locked_by = %s,
                locked_at = NOW(),
                attempt = attempt + 1,
                started_at = COALESCE(started_at, NOW()),
                updated_at = NOW()
            WHERE id = (
                SELECT id FROM public.job_runs
                WHERE state = 'QUEUED' AND run_after <= NOW()
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING *
            """,
            [worker_id],
        )
        return _decode(record[0]) if record else None
    # Development fallback (sqlite): single-process claim without SKIP LOCKED.
    record = rows(
        """
        SELECT id FROM public.job_runs
        WHERE state = 'QUEUED' AND run_after <= %s
        ORDER BY created_at
        LIMIT 1
        """,
        [datetime.now(timezone.utc).isoformat()],
    )
    if not record:
        return None
    claimed = rows(
        """
        UPDATE public.job_runs
        SET state = 'RUNNING',
            locked_by = %s,
            locked_at = %s,
            attempt = attempt + 1,
            started_at = COALESCE(started_at, %s),
            updated_at = %s
        WHERE id = %s AND state = 'QUEUED'
        RETURNING *
        """,
        [
            worker_id,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            str(record[0]["id"]),
        ],
    )
    return _decode(claimed[0]) if claimed else None


def renew_lock(*, job_id: UUID, worker_id: str) -> bool:
    """Refresh the lease; running handlers keep ownership through long work.
    Returns False when the lease is already gone (job reclaimed or requeued)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE public.job_runs
            SET locked_at = NOW(), updated_at = NOW()
            WHERE id = %s AND locked_by = %s AND state = 'RUNNING'
            """,
            [str(job_id), worker_id],
        )
        return cursor.rowcount > 0


def release_stale(*, now: datetime | None = None) -> int:
    """Requeue RUNNING jobs whose worker disappeared (crash recovery)."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=STALE_LOCK_SECONDS)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE public.job_runs
            SET state = CASE WHEN attempt >= max_attempts THEN 'FAILED' ELSE 'QUEUED' END,
                progress_phase = NULL,
                locked_by = NULL,
                locked_at = NULL,
                completed_at = CASE WHEN attempt >= max_attempts THEN NOW() ELSE completed_at END,
                error = CASE WHEN attempt >= max_attempts
                        THEN '{"code":"job_lease_expired"}'::jsonb ELSE error END,
                updated_at = NOW()
            WHERE state = 'RUNNING' AND locked_at < %s
            RETURNING CASE WHEN state = 'FAILED' AND type = 'ai.agent.run'
                          THEN payload->>'ai_job_id' ELSE NULL END AS ai_job_id
            """,
            [cutoff],
        )
        released = cursor.rowcount
        # A terminal ai.agent.run never reaches its handler, so nothing else
        # settles the ai_jobs row — without this the assistant card hangs in
        # PLANNING/RUNNING forever. FAILED_RETRYABLE keeps the workspace's
        # resume path open. ai_jobs grants sit on ai_backend/postgres, not
        # service_role — RESET ROLE reaches the session owner (the table
        # owner bypasses RLS and owns the ai_backend membership).
        stranded = [row[0] for row in cursor.fetchall() if row[0]]
        if stranded:
            cursor.execute("SELECT current_setting('role')")
            previous = str(cursor.fetchone()[0])
            cursor.execute("RESET ROLE")
            cursor.execute(
                """
                UPDATE public.ai_jobs SET state = 'FAILED_RETRYABLE',
                    error_code = 'job_lease_expired', updated_at = NOW()
                WHERE id = ANY(%s::uuid[])
                  AND state IN ('QUEUED','PLANNING','RUNNING')
                """,
                [stranded],
            )
            if previous != "none":
                cursor.execute(
                    sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(previous))
                )
        return released


def report_progress(
    *,
    job_id: UUID,
    worker_id: str,
    progress: float,
    phase: str | None = None,
) -> None:
    """Record progress and renew the lease in one write; raises LockLostError
    when the lease is gone so the handler aborts instead of finishing a job
    that now belongs to another worker. `phase` is the named intermediate
    state (IA3: "consulting"/"engine"/"proposal") the UI renders next to the
    numeric percent — NULL keeps the last reported phase."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE public.job_runs
            SET progress = %s,
                progress_phase = COALESCE(%s, progress_phase),
                locked_at = NOW(), updated_at = NOW()
            WHERE id = %s AND locked_by = %s AND state = 'RUNNING'
            """,
            [progress, phase, str(job_id), worker_id],
        )
        if cursor.rowcount == 0:
            raise LockLostError(job_id)


def _terminal_update(
    *, job_id: UUID, worker_id: str, set_clause: str, parameters: list[object]
) -> None:
    """Write a terminal state only while this worker still owns the lease —
    a requeued row belongs to its new claimer and must not be overwritten."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE public.job_runs
            SET {set_clause}
            WHERE id = %s AND locked_by = %s AND state = 'RUNNING'
            """,
            [*parameters, str(job_id), worker_id],
        )
        if cursor.rowcount == 0:
            raise LockLostError(f"job {job_id} lock lost before terminal write")


def succeed(*, job_id: UUID, worker_id: str, result: dict[str, object]) -> None:
    _terminal_update(
        job_id=job_id,
        worker_id=worker_id,
        set_clause="""
            state = 'SUCCEEDED',
            progress = 100.00,
            progress_phase = NULL,
            result = %s::jsonb,
            error = NULL,
            locked_by = NULL,
            locked_at = NULL,
            completed_at = NOW(),
            updated_at = NOW()
        """,
        parameters=[json_text(result)],
    )


def fail_or_retry(
    *,
    job_id: UUID,
    worker_id: str,
    error: dict[str, object],
    attempt: int,
    max_attempts: int,
) -> str:
    """Requeue with quadratic backoff, or mark FAILED after the last attempt."""
    terminal = attempt >= max_attempts
    state_update = "state = 'FAILED', completed_at = NOW()" if terminal else "state = 'QUEUED'"
    _terminal_update(
        job_id=job_id,
        worker_id=worker_id,
        set_clause=f"""
            {state_update},
            progress_phase = NULL,
            error = %s::jsonb,
            locked_by = NULL,
            locked_at = NULL,
            run_after = NOW() + (%s || ' seconds')::interval,
            updated_at = NOW()
        """,
        parameters=[json_text(error), str(15 * attempt * attempt)],
    )
    return "FAILED" if terminal else "QUEUED"


def fail_permanent(*, job_id: UUID, worker_id: str, error: dict[str, object]) -> None:
    """Terminal failure regardless of remaining attempts: contract violations
    (permission denied, not found, invalid payload) never succeed on retry."""
    _terminal_update(
        job_id=job_id,
        worker_id=worker_id,
        set_clause="""
            state = 'FAILED',
            progress_phase = NULL,
            error = %s::jsonb,
            locked_by = NULL,
            locked_at = NULL,
            completed_at = NOW(),
            updated_at = NOW()
        """,
        parameters=[json_text(error)],
    )
