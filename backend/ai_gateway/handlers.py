"""Agent runs on the durable worker — the POST enqueues and returns; the
handler claims the ai_jobs row and runs the observe → plan loop inside one
transaction, mirroring the request path's all-or-rollback semantics (a
failed run keeps billing consistent because the debit unwinds with it)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.db import connection, transaction

from jobs.handlers import _claims_for
from jobs.registry import JobContext, JobPermanentError, ProgressReporter, register
from ai_gateway.serializers import AiAgentRunSerializer

_AGENT_CALLERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")


class _Unclaimable(Exception):
    """The row moved before the worker claimed it (canceled while queued, a
    concurrent follow-up won the resume race) — leave its state as the
    surface shows it instead of writing over a different lifecycle."""


def _claims(context: JobContext) -> str:
    return json.dumps(_claims_for(str(context.created_by), context))


def _set_claims(cursor: Any, context: JobContext) -> None:
    cursor.execute(
        "SELECT set_config('request.jwt.claims', %s, true)", [_claims(context)]
    )


def _error_code(error: Exception) -> str:
    return str(
        getattr(error, "contract_code", None)
        or getattr(error, "code", None)
        or "ai_job_failed"
    )[:120]


@register(
    "ai.agent.run",
    roles=_AGENT_CALLERS,
    payload_serializer=AiAgentRunSerializer,
    label="Ejecutar tarea del agente",
)
def ai_agent_run(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    from ai_gateway import jobs
    from ai_gateway.agent import JobCanceledError, act

    if context.created_by is None:
        raise JobPermanentError("job_requires_actor")
    org_id = context.org_id
    user_id = context.created_by
    ai_job_id = UUID(str(payload["ai_job_id"]))
    mode = str(payload["mode"])
    goal = str(payload["goal"])
    report(5)

    with transaction.atomic():
        with connection.cursor() as cursor:
            _set_claims(cursor, context)
            # Re-verify the submitter's membership at run time — a queued job
            # must not outlive revoked access (same contract as ingest).
            cursor.execute(
                "SELECT role FROM public.tenancy_memberships "
                "WHERE user_id=%s AND org_id=%s AND is_active",
                [str(user_id), str(org_id)],
            )
            row = cursor.fetchone()
    if row is None or str(row[0]) not in _AGENT_CALLERS:
        raise JobPermanentError("ai_membership_revoked")
    report(10)

    transcript_before: list = []
    try:
        # The claim and the run-marker commit in their own short
        # transactions so mid-run the row shows PLANNING/RUNNING instead of
        # the previous round's settled state — the act transaction still
        # holds only the transcript/result writes it owns. Each commit also
        # makes crash recovery possible: a run stranded by a worker death
        # is re-claimable because the claim guards accept PLANNING/RUNNING
        # and serialize on the row lock a live act still holds.
        with transaction.atomic():
            with connection.cursor() as cursor:
                _set_claims(cursor, context)
            if mode == "resume":
                prior = jobs.get_job(org_id=org_id, user_id=user_id, job_id=ai_job_id)
                if prior is None:
                    raise _Unclaimable
                transcript_before = list(prior.get("transcript") or [])
                # A retry replays the message of the FAILED round — the view
                # resolves it from the transcript and sends it as the payload
                # goal; replay only marks the transcript turn for the UI.
                try:
                    claimed = jobs.resume_job(
                        job_id=ai_job_id,
                        transcript=transcript_before,
                        org_id=org_id,
                        user_id=user_id,
                    )
                except ValueError:
                    raise _Unclaimable from None
            else:
                claimed = jobs.claim_queued_job(
                    job_id=ai_job_id, org_id=org_id, user_id=user_id
                )
                if claimed is None:
                    raise _Unclaimable
            # A signal from the queue window — a cancel posted between the
            # submit and the claim should not still run the provider.
            if jobs.cancel_requested(job_id=ai_job_id):
                raise JobCanceledError()
        with transaction.atomic():
            with connection.cursor() as cursor:
                _set_claims(cursor, context)
            if not jobs.mark_running(
                job_id=ai_job_id, org_id=org_id, user_id=user_id
            ):
                raise _Unclaimable
        with transaction.atomic():
            with connection.cursor() as cursor:
                _set_claims(cursor, context)
            # A cancel that found the row free between the marker and this
            # transaction wrote CANCELED directly — no signal row exists for
            # that path, only the state itself.
            if jobs.job_state(job_id=ai_job_id) != "RUNNING":
                raise JobCanceledError()
            act(
                org_id=org_id,
                user_id=user_id,
                surface=str(payload["surface"]),
                refs=dict(payload.get("refs") or {}),
                goal=goal,
                product=payload.get("product"),
                history=list(payload.get("history") or []),
                operation_key=str(payload["operation_key"]),
                job=claimed,
                replay=bool(payload.get("replay")),
                product_sig=str(payload.get("product_sig") or ""),
                # Only a resume payload's history is trustworthy — the view
                # rebuilt it from the stored transcript. First-run history
                # is client input and must not enter the grounding set.
                history_trusted=mode == "resume",
                progress=report,
            )
        report(95)
    except _Unclaimable:
        raise JobPermanentError("ai_job_unclaimable") from None
    except JobCanceledError:
        # The rollback restored the pre-claim state; finish it as CANCELED
        # from a clean transaction so the rail reflects the user's choice.
        with transaction.atomic():
            with connection.cursor() as cursor:
                _set_claims(cursor, context)
            jobs.cancel_job(job_id=ai_job_id, org_id=org_id, user_id=user_id)
            jobs.clear_cancel_signal(job_id=ai_job_id)
        raise JobPermanentError("ai_job_canceled") from None
    except Exception as error:
        # Same post-rollback bookkeeping the request path used — the failure
        # must outlive the round that produced it.
        code = _error_code(error)
        with transaction.atomic():
            with connection.cursor() as cursor:
                _set_claims(cursor, context)
            if jobs.job_state(job_id=ai_job_id) == "CANCELED":
                # A mid-run cancel landed during the last provider call:
                # finish_job then finds no RUNNING row. Report the user's
                # cancel — not a phantom ai_job_terminal over a state the
                # user already committed.
                jobs.clear_cancel_signal(job_id=ai_job_id)
                raise JobPermanentError("ai_job_canceled") from error
            if mode == "resume":
                jobs.record_failure(
                    job_id=ai_job_id,
                    transcript_before=transcript_before,
                    goal=goal,
                    error_code=code,
                )
            else:
                jobs.fail_queued_job(
                    job_id=ai_job_id, goal=goal, error_code=code
                )
        raise JobPermanentError(code) from error
    finally:
        # A signal sent between the last round and finish_job would otherwise
        # linger and cancel the NEXT round on a resumed run.
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    _set_claims(cursor, context)
                jobs.clear_cancel_signal(job_id=ai_job_id)
        except Exception:
            pass
    return {"ai_job_id": str(ai_job_id)}
