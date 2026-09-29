"""§07-B/G — durable AI jobs: every agent run persists as a job row carrying
its goal, plan, transcript (user turns + model rounds), typed projections
consulted, artifacts emitted, warnings and final result. The row is the UI's
truth — a settled job resumes with follow-up instructions, and artifacts stay
inspectable after the chat scrolls away.

States: RUNNING while a round executes; SUCCEEDED on a grounded reply;
WAITING_FOR_USER when the reply asks for missing input; WAITING_FOR_APPROVAL
when it proposes consequential actions; FAILED_RETRYABLE on a transient
provider/validity failure; FAILED on exhaustion; CANCELED by the user.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import DatabaseError, connection, transaction

from authentication.rls import tx_aborted
from pricing.repository import rows, write


@contextmanager
def _ai_backend():
    """Job writes execute under the dedicated backend role: member-facing
    `authenticated` lost INSERT/UPDATE on ai_jobs so PostgREST cannot rewrite
    job state, transcripts, artifacts or results — the API is the only write
    path and it runs inside the same org/user RLS policies under this role.
    Mirrors commercial_backend: claims and policies stay unchanged.
    SQLite has no roles — the context is a no-op there."""
    if connection.vendor != "postgresql":
        yield
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('role', true)")
        previous = cursor.fetchone()[0]
        cursor.execute("SET LOCAL ROLE ai_backend")
    try:
        yield
    except DatabaseError:
        raise
    except BaseException:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE %s", [previous])
        raise
    else:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE %s", [previous])

MAX_GOAL = 2000
MAX_ARTIFACT_TITLE = 120
MAX_ARTIFACT_BYTES = 32768
MAX_CLAIM = 240
MAX_CLAIMS = 8
MAX_REFERENCE = 120
MAX_REFERENCES = 12
MAX_ARTIFACTS_PER_RUN = 6
# The job-level artifact list accumulates across rounds — a follow-up turn
# must not erase drafts an earlier round produced. Bounded so a long-lived
# job can't grow the row without limit; oldest drafts age out first.
MAX_ARTIFACTS_TOTAL = 48

TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELED"})
OPEN_STATES = frozenset(
    {"QUEUED", "PLANNING", "RUNNING", "WAITING_FOR_USER",
     "WAITING_FOR_APPROVAL", "FAILED_RETRYABLE"}
)

# §07-G — artifact kinds are inspectable drafts. None of them mutate
# anything: a draft travels to the surface that owns the mutation, where a
# human confirms. Kinds mirror what the agent can actually produce today.
ARTIFACT_KINDS = frozenset(
    {
        "product_draft",
        "project_draft",
        "quote_draft",
        "catalog_candidates",
        "catalog_review",
        "purchase_plan",
        "production_plan",
        "message",
        "comparison",
        "document_preview",
    }
)


def _dump(value: Any) -> str:
    return json.dumps(value, default=str)


_JOB_COLUMNS = (
    "id, org_id, user_id, surface, refs, goal, state, plan,"
    " transcript, artifacts, warnings, result, error_code, outcomes,"
    " operation_key, created_at, updated_at, completed_at"
)


def create_job(*, org_id: UUID, user_id: UUID, surface: str,
               refs: dict, goal: str) -> dict:
    with _ai_backend():
        record = rows(
            "INSERT INTO public.ai_jobs"
            " (org_id, user_id, surface, refs, goal, state)"
            " VALUES (%s, %s, %s, %s::jsonb, %s, 'RUNNING')"
            f" RETURNING {_JOB_COLUMNS}",
            [str(org_id), str(user_id), surface, _dump(refs or {}),
             goal[:MAX_GOAL]],
        )[0]
    return _decode(record)


def enqueue_job(*, org_id: UUID, user_id: UUID, surface: str,
                refs: dict, goal: str, operation_key: str) -> dict:
    """Submit-side job row in QUEUED — the worker claims it. Idempotent on
    (org, user, operation_key): a retried POST replays to the in-flight row
    instead of leaving an orphan that can never be claimed."""
    with _ai_backend():
        record = rows(
            "INSERT INTO public.ai_jobs"
            " (org_id, user_id, surface, refs, goal, state, operation_key)"
            " VALUES (%s, %s, %s, %s::jsonb, %s, 'QUEUED', %s)"
            " ON CONFLICT (org_id, user_id, operation_key)"
            " WHERE operation_key IS NOT NULL DO NOTHING"
            f" RETURNING {_JOB_COLUMNS}",
            [str(org_id), str(user_id), surface, _dump(refs or {}),
             goal[:MAX_GOAL], operation_key[:200]],
        )
        if not record:
            record = rows(
                f"SELECT {_JOB_COLUMNS} FROM public.ai_jobs"
                " WHERE org_id = %s AND user_id = %s AND operation_key = %s",
                [str(org_id), str(user_id), operation_key[:200]],
            )
        existing = _decode(record[0])
        # The key binds the request itself: a retried POST replays to the
        # same row, but a different goal, refs or surface under a recycled
        # key is a collision, not a replay — refusing it keeps one key from
        # quietly running someone else's goal under an existing job.
        if (
            str(existing.get("goal") or "") != goal[:MAX_GOAL]
            or (existing.get("refs") or {}) != (refs or {})
            or str(existing.get("surface") or "") != surface
        ):
            raise ValueError("ai_operation_key_conflict")
    return existing


def claim_queued_job(*, job_id: UUID, org_id: UUID, user_id: UUID) -> dict | None:
    """The worker's atomic claim, committed on its own so the row shows
    PLANNING while the run's transaction works — mid-run readers then see a
    real lifecycle instead of the previous round's terminal state. QUEUED is
    the normal entry; PLANNING/RUNNING re-claim a run stranded by a worker
    crash (the row lock serializes a live act transaction, so a re-claim
    waits for it and then fails the state check — it can never run twice)."""
    with _ai_backend():
        record = rows(
            "UPDATE public.ai_jobs SET state = 'PLANNING', updated_at = NOW()"
            " WHERE id = %s AND org_id = %s AND user_id = %s"
            " AND state IN ('QUEUED','PLANNING','RUNNING')"
            f" RETURNING {_JOB_COLUMNS}",
            [str(job_id), str(org_id), str(user_id)],
        )
    return _decode(record[0]) if record else None


def mark_running(*, job_id: UUID, org_id: UUID, user_id: UUID) -> bool:
    """Second committed state step — the act loop owns the row now. Keeping
    this its own commit makes every state honest: QUEUED → PLANNING →
    RUNNING → terminal is the visible progression while job_runs carries
    the finer progress inside RUNNING."""
    with _ai_backend():
        return bool(
            rows(
                "UPDATE public.ai_jobs SET state = 'RUNNING', updated_at = NOW()"
                " WHERE id = %s AND org_id = %s AND user_id = %s"
                " AND state = 'PLANNING' RETURNING id",
                [str(job_id), str(org_id), str(user_id)],
            )
        )


def job_state(*, job_id: UUID) -> str | None:
    """Bare state read for the worker's own gap checks — a free-row cancel
    between the committed marks and the act transaction writes CANCELED
    directly, and only the state itself tells that story (no signal row)."""
    if connection.vendor != "postgresql":
        return None
    found = rows(
        "SELECT state FROM public.ai_jobs WHERE id = %s", [str(job_id)]
    )
    return str(found[0]["state"]) if found else None


# A job that keeps failing its rounds is terminal, not retryable forever —
# consecutive error turns past this budget flip FAILED_RETRYABLE to FAILED.
MAX_ERROR_TURNS = 3


def fail_queued_job(*, job_id: UUID, goal: str, error_code: str) -> dict | None:
    """Failure bookkeeping for a first run whose transaction rolled back the
    claim — the row is still QUEUED; mark it FAILED_RETRYABLE so the
    workspace can resume it instead of showing a stuck queue entry."""
    with _ai_backend():
        record = rows(
            "UPDATE public.ai_jobs SET state = 'FAILED_RETRYABLE',"
            " transcript = %s::jsonb, error_code = %s, updated_at = NOW()"
            " WHERE id = %s AND state IN ('QUEUED','PLANNING','RUNNING')"
            " RETURNING id",
            [_dump(_failure_turns(goal, error_code)), error_code[:120],
             str(job_id)],
        )
    return {"id": str(record[0]["id"])} if record else None


def cancel_requested(*, job_id: UUID) -> bool:
    """Cooperative cancel read. Two channels: the signals table (a cancel
    that found the row locked) and the job's own state — the row is NOT held
    for the whole run, so a mid-loop cancel usually lands as a direct
    CANCELED write with no signal row. Checking only the signals table would
    let the loop burn every remaining provider round."""
    if connection.vendor != "postgresql":
        return False
    with _ai_backend():
        return bool(
            rows(
                "SELECT 1 FROM public.ai_job_cancel_signals WHERE job_id = %s"
                " UNION ALL SELECT 1 FROM public.ai_jobs"
                " WHERE id = %s AND state = 'CANCELED' LIMIT 1",
                [str(job_id), str(job_id)],
            )
        )


def clear_cancel_signal(*, job_id: UUID) -> None:
    if connection.vendor != "postgresql":
        return
    with _ai_backend():
        rows(
            "DELETE FROM public.ai_job_cancel_signals WHERE job_id = %s"
            " RETURNING job_id",
            [str(job_id)],
        )


def request_cancel(*, job_id: UUID, org_id: UUID, user_id: UUID) -> str:
    """'canceled' — the row flipped immediately; 'signaled' — the run holds
    the row lock, so a signal row asks the worker to abort between rounds;
    'terminal' — nothing live to cancel."""
    with transaction.atomic():
        with _ai_backend():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '800ms'")
                cursor.execute("SAVEPOINT ai_cancel")
                try:
                    cursor.execute(
                        "UPDATE public.ai_jobs SET state = 'CANCELED',"
                        " updated_at = NOW(), completed_at = NOW() WHERE id = %s"
                        " AND org_id = %s AND user_id = %s"
                        " AND state NOT IN ('SUCCEEDED','FAILED','CANCELED')"
                        " RETURNING id",
                        [str(job_id), str(org_id), str(user_id)],
                    )
                    landed = cursor.fetchone() is not None
                    cursor.execute("RELEASE SAVEPOINT ai_cancel")
                except DatabaseError as error:
                    cursor.execute("ROLLBACK TO SAVEPOINT ai_cancel")
                    sqlstate = getattr(error, "sqlstate", None) or getattr(
                        getattr(error, "__cause__", None), "sqlstate", None
                    )
                    if sqlstate != "55P03":
                        raise
                    # Lock timeout — the row was busy inside one of the
                    # worker's short commit windows; the signal row asks it
                    # to abort between rounds instead of waiting it out.
                    landed = False
                if landed:
                    return "canceled"
                # 0 rows without a lock means terminal — confirm the job is
                # still live before signaling a run that isn't.
                cursor.execute(
                    "SELECT state FROM public.ai_jobs"
                    " WHERE id = %s AND org_id = %s AND user_id = %s",
                    [str(job_id), str(org_id), str(user_id)],
                )
                found = cursor.fetchone()
                if found is None or str(found[0]) in TERMINAL_STATES:
                    return "terminal"
                cursor.execute(
                    "INSERT INTO public.ai_job_cancel_signals"
                    " (job_id, org_id, user_id) VALUES (%s, %s, %s)"
                    " ON CONFLICT (job_id) DO NOTHING",
                    [str(job_id), str(org_id), str(user_id)],
                )
                return "signaled"


def live_runs(*, org_id: UUID, job_ids: list) -> dict:
    """Latest worker-run state per ai_job — the only signal visible while a
    run is in flight, because the run's own ai_jobs writes stay uncommitted
    until it finishes. job_runs progress updates commit immediately (the
    worker reports them outside the handler's atomic), so the rail can show
    real mid-run progress instead of a frozen QUEUED. job_runs is
    service-owned: the read borrows the same role switch the enqueue path
    uses."""
    if connection.vendor != "postgresql" or not job_ids:
        return {}
    from jobs import service as job_service  # lazy — avoids the import cycle

    with job_service.job_backend():
        found = rows(
            "SELECT payload->>'ai_job_id' AS ai_job_id, state, progress,"
            " updated_at FROM public.job_runs"
            " WHERE org_id = %s AND type = 'ai.agent.run'"
            " AND payload->>'ai_job_id' = ANY(%s::text[])"
            " ORDER BY created_at DESC",
            [str(org_id), [str(jid) for jid in job_ids]],
        )
    latest: dict = {}
    for run in found:
        key = str(run["ai_job_id"])
        if key in latest:
            continue
        latest[key] = {
            "state": run["state"],
            "progress": float(run["progress"] or 0),
            "updated_at": str(run["updated_at"]),
        }
    return latest


def get_job(*, org_id: UUID, user_id: UUID, job_id: UUID) -> dict | None:
    found = rows(
        "SELECT id, org_id, user_id, surface, refs, goal, state, plan,"
        " transcript, artifacts, warnings, result, error_code, outcomes,"
        " created_at, updated_at, completed_at"
        " FROM public.ai_jobs WHERE id = %s AND org_id = %s AND user_id = %s",
        [str(job_id), str(org_id), str(user_id)],
    )
    if not found:
        return None
    job = _decode(found[0])
    job["live"] = live_runs(org_id=org_id, job_ids=[job_id]).get(job["id"])
    return job


def list_jobs(
    *,
    org_id: UUID,
    user_id: UUID,
    limit: int = 30,
    before: str | None = None,
    before_id: str | None = None,
) -> list[dict]:
    params: list[object] = [str(org_id), str(user_id)]
    if before_id:
        try:
            UUID(str(before_id))
        except ValueError:
            before_id = None
    cursor = ""
    if before and before_id:
        # Composite keyset: ties on created_at paginate by id so rows sharing
        # the page-edge timestamp can't fall between pages.
        cursor = " AND (created_at < %s OR (created_at = %s AND id < %s::uuid))"
        params += [before, before, before_id]
    elif before:
        cursor = " AND created_at < %s"
        params.append(before)
    params.append(limit)
    decoded = [
        _decode(row)
        for row in rows(
            "SELECT id, org_id, user_id, surface, refs, goal, state, plan,"
            " artifacts, warnings, result, error_code, outcomes,"
            " created_at, updated_at, completed_at"
            " FROM public.ai_jobs WHERE org_id = %s AND user_id = %s"
            + cursor
            + " ORDER BY created_at DESC, id DESC LIMIT %s",
            params,
        )
    ]
    live = live_runs(org_id=org_id, job_ids=[row["id"] for row in decoded])
    for row in decoded:
        row["live"] = live.get(row["id"])
    return decoded


def finish_job(*, job_id: UUID, state: str, transcript: list, plan: list,
               artifacts: list, warnings: list, result: dict | None,
               error_code: str | None = None) -> dict:
    with _ai_backend():
        record = rows(
        "UPDATE public.ai_jobs SET state = %s, transcript = %s::jsonb,"
        # The plan column mirrors the latest round that produced one — a
        # question-only follow-up keeps the last real plan visible instead
        # of blanking the rail.
        " plan = CASE WHEN %s::jsonb <> '[]'::jsonb THEN %s::jsonb ELSE plan END,"
        " artifacts = %s::jsonb, warnings = %s::jsonb, result = %s::jsonb,"
        " error_code = %s, updated_at = NOW(),"
        " completed_at = CASE WHEN %s IN ('SUCCEEDED','FAILED','CANCELED')"
        " THEN NOW() ELSE completed_at END"
        " WHERE id = %s AND state = 'RUNNING' RETURNING id",
        [
            state, _dump(transcript), _dump(plan), _dump(plan),
            _dump(artifacts), _dump(warnings),
            _dump(result) if result is not None else None, error_code,
            state, str(job_id),
        ],
        )
    if not record:
        raise ValueError("ai_job_terminal")
    return {"id": str(record[0]["id"])}


def mark_queued(*, job_id: UUID, org_id: UUID, user_id: UUID) -> str | None:
    """A follow-up was accepted and its worker run enqueued — flip the row to
    QUEUED in the request's own transaction so polls reflect the pending
    round immediately instead of the settled state until the worker claims
    (the claim's own state write is invisible until it commits anyway).
    Returns the state the job was flipped FROM — the caller restores it if
    the enqueue that follows fails, because this write commits in the
    request's autocommit and an orphaned QUEUED would wedge the job — and
    None when the atomic guard lost the race (already claimed)."""
    with _ai_backend():
        record = rows(
            "WITH prev AS (SELECT id, state FROM public.ai_jobs"
            " WHERE id = %s AND org_id = %s AND user_id = %s)"
            " UPDATE public.ai_jobs SET state = 'QUEUED', updated_at = NOW()"
            " FROM prev WHERE ai_jobs.id = prev.id AND ai_jobs.state IN"
            " ('WAITING_FOR_USER','WAITING_FOR_APPROVAL',"
            " 'FAILED_RETRYABLE','SUCCEEDED') RETURNING prev.state",
            [str(job_id), str(org_id), str(user_id)],
        )
    return str(record[0]["state"]) if record else None


def restore_queued(*, job_id: UUID, previous: str) -> bool:
    """Compensate a mark_queued whose enqueue failed — put the job back in
    the state it left. Guarded on still-QUEUED: once a worker claimed the
    row, the run is real and the flip must stand."""
    if previous not in (
        "WAITING_FOR_USER",
        "WAITING_FOR_APPROVAL",
        "FAILED_RETRYABLE",
        "SUCCEEDED",
    ):
        return False
    with _ai_backend():
        return bool(
            rows(
                "UPDATE public.ai_jobs SET state = %s, updated_at = NOW()"
                " WHERE id = %s AND state = 'QUEUED' RETURNING id",
                [previous, str(job_id)],
            )
        )


def resume_job(*, job_id: UUID, transcript: list, org_id: UUID, user_id: UUID) -> dict:
    """Claim a settled job for a new round. The UPDATE itself is the lock:
    only the QUEUED mark the submitting request left can be claimed — a
    resume must never steal a live PLANNING/RUNNING row (two provider loops
    would then append to one transcript) nor resurrect a settled state
    directly (the request's mark_queued is the single transition into a new
    round). A stranded live row is recovered by cancel + new job, not by
    double-running it."""
    with _ai_backend():
        record = rows(
            "UPDATE public.ai_jobs SET state = 'PLANNING',"
            " transcript = %s::jsonb, result = NULL, error_code = NULL,"
            " completed_at = NULL, updated_at = NOW()"
            " WHERE id = %s AND org_id = %s AND user_id = %s"
            " AND state = 'QUEUED'"
            " RETURNING id",
            [_dump(transcript), str(job_id), str(org_id), str(user_id)],
        )
    if record:
        # act() rebuilds the transcript off the claimed row — carrying the
        # transcript we just wrote keeps earlier rounds; returning only the
        # id would make the round start from an empty thread and clobber
        # the conversation at finish.
        return {"id": str(record[0]["id"]), "transcript": transcript}
    state = rows(
        "SELECT state FROM public.ai_jobs WHERE id = %s", [str(job_id)]
    )
    if state and state[0]["state"] in TERMINAL_STATES:
        raise ValueError("ai_job_terminal")
    raise ValueError("ai_job_running")


def _failure_turns(goal: str, error_code: str) -> list[dict]:
    return [
        {"role": "user", "text": goal[:MAX_GOAL]},
        {"role": "error", "code": error_code[:120]},
    ]


def create_failed_job(*, org_id: UUID, user_id: UUID, surface: str,
                      refs: dict, goal: str, error_code: str) -> dict:
    """§07-B — a failed first round outlives the rolled-back request: after
    the scope unwinds, the caller re-enters its RLS context and records the
    job here, so the workspace shows a resumable FAILED_RETRYABLE row
    instead of nothing at all."""
    with _ai_backend():
        record = rows(
            "INSERT INTO public.ai_jobs"
            " (org_id, user_id, surface, refs, goal, state, transcript, error_code)"
            " VALUES (%s, %s, %s, %s::jsonb, %s, 'FAILED_RETRYABLE',"
            " %s::jsonb, %s) RETURNING id",
            [
                str(org_id), str(user_id), surface, _dump(refs or {}),
                goal[:MAX_GOAL], _dump(_failure_turns(goal, error_code)),
                error_code[:120],
            ],
        )
    return {"id": str(record[0]["id"])}


def record_failure(*, job_id: UUID, transcript_before: list, goal: str,
                   error_code: str) -> dict | None:
    """A failed follow-up lands on the existing job after its round rolled
    back: the user turn stays in the transcript and the row goes
    FAILED_RETRYABLE. The WHERE clause binds the write to the generation
    this round actually claimed — post-rollback the row still carries the
    transcript we resumed, so an exact match means the record can never
    overwrite a different round's claim or committed result (their
    transcript has moved on)."""
    with _ai_backend():
        found = rows(
        # Past the retry budget the job goes terminal — the error count is
        # computed from the transcript being written, so the bound holds
        # even if older rounds' failures are interleaved with successes.
        "UPDATE public.ai_jobs SET state ="
        " CASE WHEN (SELECT count(*) FROM jsonb_array_elements("
        " transcript || %s::jsonb) e WHERE e->>'role' = 'error') >= %s"
        " THEN 'FAILED' ELSE 'FAILED_RETRYABLE' END,"
        " transcript = transcript || %s::jsonb, result = NULL, error_code = %s,"
        " updated_at = NOW()"
        # Post-rollback the row shows this round's committed claim mark —
        # PLANNING or RUNNING, never a settled state (another lifecycle
        # landing first also rewrote the transcript, so the match fails). A
        # free-row cancel wrote CANCELED and must not be revived.
        " WHERE id = %s AND state IN ('PLANNING','RUNNING')"
        " AND transcript = %s::jsonb"
        " RETURNING id",
        [_dump(_failure_turns(goal, error_code)), MAX_ERROR_TURNS,
         _dump(_failure_turns(goal, error_code)), error_code[:120],
         str(job_id), _dump(transcript_before)],
    )
    return {"id": str(found[0]["id"])} if found else None


def cancel_job(*, job_id: UUID, org_id: UUID, user_id: UUID) -> bool:
    with _ai_backend():
        return bool(
            rows(
                "UPDATE public.ai_jobs SET state = 'CANCELED',"
                " updated_at = NOW(), completed_at = NOW() WHERE id = %s"
                " AND org_id = %s AND user_id = %s"
                " AND state NOT IN ('SUCCEEDED','FAILED','CANCELED')"
                " RETURNING id",
                [str(job_id), str(org_id), str(user_id)],
            )
        )


def record_outcome(
    *, org_id: UUID, user_id: UUID, job_id: UUID, entry: dict
) -> dict | None:
    """§08 measurement — record what the human did with a proposed step
    (applied / declined / apply_failed). Dedupe on the (turn, step, action)
    triple so a retried report can never double-count a click."""
    recorded = {
        "turn_index": int(entry["turn_index"]),
        "step_index": int(entry["step_index"]),
        "action": str(entry["action"]),
        "ops": [str(op)[:80] for op in (entry.get("ops") or [])][:200],
        "recorded_by": str(user_id),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    dedupe = [
        {
            "turn_index": recorded["turn_index"],
            "step_index": recorded["step_index"],
            "action": recorded["action"],
        }
    ]
    with _ai_backend():
        # The reported step must actually exist in the transcript — a client
        # may only record outcomes against steps the run proposed, or any
        # index the UI never showed becomes fabricable telemetry.
        job = get_job(org_id=org_id, user_id=user_id, job_id=job_id)
        if job is None:
            return None
        transcript = job.get("transcript") or []
        turn = (
            transcript[recorded["turn_index"]]
            if 0 <= recorded["turn_index"] < len(transcript)
            else None
        )
        steps = (turn or {}).get("steps") or []
        step = (
            steps[recorded["step_index"]]
            if 0 <= recorded["step_index"] < len(steps)
            else None
        )
        if step is None or step.get("kind") not in ("ops", "batch_ops", "prepare"):
            return None
        found = rows(
            "UPDATE public.ai_jobs SET outcomes = outcomes || %s::jsonb,"
            " updated_at = NOW()"
            " WHERE id = %s AND org_id = %s AND user_id = %s"
            " AND NOT outcomes @> %s::jsonb"
            # A terminal decision (applied/declined) can't be contradicted by a
            # second one on the same step — a race or a stale card must never
            # record 'applied' and 'declined' together. apply_failed is not
            # terminal: retrying a failed apply is the whole point.
            " AND (%s NOT IN ('applied','declined') OR NOT EXISTS ("
            "   SELECT 1 FROM jsonb_array_elements(outcomes) o"
            "   WHERE (o->>'turn_index')::int = %s AND (o->>'step_index')::int = %s"
            "     AND o->>'action' IN ('applied','declined')))"
            " RETURNING id",
            [
                _dump([recorded]),
                str(job_id),
                str(org_id),
                str(user_id),
                _dump(dedupe),
                recorded["action"],
                recorded["turn_index"],
                recorded["step_index"],
            ],
        )
        if found and job.get("state") == "WAITING_FOR_APPROVAL":
            # The wait is resolvable: once every gated step the transcript
            # proposed has at least one recorded outcome, the job succeeded —
            # decisions on later rounds can't reopen a resolved approval.
            pending = [
                (turn_index, step_index)
                for turn_index, turn_row in enumerate(transcript)
                for step_index, step_row in enumerate(turn_row.get("steps") or [])
                if step_row.get("kind") in ("ops", "batch_ops", "prepare")
            ]
            resolved = {
                (outcome["turn_index"], outcome["step_index"])
                for outcome in (job.get("outcomes") or [])
            }
            resolved.add((recorded["turn_index"], recorded["step_index"]))
            if pending and all(pair in resolved for pair in pending):
                write(
                    "UPDATE public.ai_jobs SET state = 'SUCCEEDED',"
                    " updated_at = NOW()"
                    " WHERE id = %s AND state = 'WAITING_FOR_APPROVAL'",
                    [str(job_id)],
                )
    return {"id": str(found[0]["id"]), "recorded": True} if found else {"id": str(job_id), "recorded": False}


# ----------------------------------------------------------------- contract


def _references(raw: Any, allowed: frozenset[str]) -> list[str]:
    """§07-F references point at entity ids the context actually showed."""
    out: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        token = str(item).strip()[:MAX_REFERENCE]
        if token and token in allowed and token not in out:
            out.append(token)
        if len(out) >= MAX_REFERENCES:
            break
    return out


def claims_and_references(
    raw_claims: Any, allowed: frozenset[str]
) -> tuple[list[dict], list[str], int]:
    """A claim is answer text backed by references — entity ids/values that
    literally appear in the projections served to the model. Claims citing
    nothing, or citing ids the context never showed, are dropped and counted
    so the caller can surface honesty instead of a silent invention."""
    claims: list[dict] = []
    references: list[str] = []
    dropped = 0
    for item in raw_claims if isinstance(raw_claims, list) else []:
        if len(claims) >= MAX_CLAIMS or not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()[:MAX_CLAIM]
        if not text:
            continue
        refs = _references(item.get("evidence"), allowed)
        if not refs:
            dropped += 1
            continue
        claims.append({"text": text, "evidence": refs})
        references.extend(ref for ref in refs if ref not in references)
    return claims, references[:MAX_REFERENCES], dropped


def artifacts(raw: Any, allowed: frozenset[str]) -> list[dict]:
    """Validate artifact steps — kind from the allowlist, a title, a bounded
    JSON payload, and references to ids the context exposed. Anything else
    is dropped: an artifact is a draft proposal, never a mutation."""
    out: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if len(out) >= MAX_ARTIFACTS_PER_RUN:
            break
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        title = str(item.get("title") or "").strip()[:MAX_ARTIFACT_TITLE]
        payload = item.get("payload")
        if (
            kind not in ARTIFACT_KINDS
            or not title
            or not isinstance(payload, dict)
            or len(_dump(payload)) > MAX_ARTIFACT_BYTES
        ):
            continue
        out.append(
            {
                "kind": kind,
                "title": title,
                "payload": payload,
                "references": _references(item.get("references"), allowed),
            }
        )
    return out


def _decode(record: dict[str, object]) -> dict[str, object]:
    out = dict(record)
    for name in (
        "refs", "plan", "transcript", "artifacts", "warnings", "result",
        "outcomes",
    ):
        value = out.get(name)
        if isinstance(value, str):
            out[name] = json.loads(value, parse_float=Decimal, parse_int=Decimal)
    for name in ("id", "org_id", "user_id"):
        if out.get(name) is not None:
            out[name] = str(out[name])
    return out
