"""AI gateway HTTP edge — the only entry point for provider calls (PRD-13)."""

from __future__ import annotations

import json

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_gateway import service
from ai_gateway import jobs
from ai_gateway.metrics import ai_metrics
from ai_gateway.assist import ask, list_turns
from ai_gateway.context import _ContextError, stable_refs
from ai_gateway.providers import ProviderError
from ai_gateway.serializers import (
    AiAgentAcceptedSerializer,
    AiAgentRequestSerializer,
    AiAskRequestSerializer,
    AiAskResponseSerializer,
    AiAskTurnSerializer,
    AiInvokeRequestSerializer,
    AiInvokeResponseSerializer,
    AiJobDetailSerializer,
    AiJobMessageSerializer,
    AiJobOutcomeResponseSerializer,
    AiJobOutcomeSerializer,
    AiJobSerializer,
    AiMetricsSerializer,
)
from ai_gateway.context import REQUIRED_REFS as AGENT_REQUIRED_REFS
from authentication.errors import ContractAPIException, contract_error
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from documents.views import ERRORS, documentary_scope, validate
from jobs import service as job_service

# Ask and invoke answer inside the caller's RLS projection exactly like the
# agent loop — a workshop manager who may run the agent must also be able to
# ask, or the two AI surfaces contradict each other (review WM6).
_AGENT_CALLERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")
_CALLERS = _AGENT_CALLERS
# Generic invoke exists for the member-facing raw capabilities only. Every
# richer capability has its own validated endpoint — letting a caller pick
# 'agent'/'catalog_compile' here would bypass context builders and output
# validation while spending org credits.
_MEMBER_CAPABILITIES = frozenset({"nlp_command", "discount_suggest"})


def _raise_agent_error(error: Exception):
    if isinstance(error, _ContextError):
        if error.code == "ai_context_ref_invalid":
            raise contract_error(
                400,
                "ai_context_ref_invalid",
                "La referencia de contexto no es válida.",
            ) from None
        raise contract_error(
            404,
            "ai_context_not_found",
            "El contexto solicitado no existe o no está disponible.",
        ) from None
    if isinstance(error, ProviderError):
        raise contract_error(
            503,
            error.code,
            "El proveedor de IA no está disponible en este momento.",
        ) from None
    if isinstance(error, ValueError) and str(error) == "ai_job_terminal":
        raise contract_error(
            409, "ai_job_terminal", "El trabajo ya terminó."
        ) from None
    raise error


class AiInvokeView(APIView):
    @extend_schema(
        operation_id="ai_invoke",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=AiInvokeRequestSerializer,
        responses={200: AiInvokeResponseSerializer, **ERRORS},
        tags=["ai"],
    )
    def post(self, request):
        data = validate(AiInvokeRequestSerializer, request.data)
        if str(data["capability"]) not in _MEMBER_CAPABILITIES:
            raise contract_error(
                422,
                "ai_capability_forbidden",
                "Esa capacidad se usa desde su propia superficie.",
            )
        with documentary_scope(request, _CALLERS) as (token, _, org_id):
            try:
                return Response(
                    service.invoke(
                        org_id=org_id,
                        user_id=token.user_id,
                        capability=str(data["capability"]),
                        operation_key=str(data["operation_key"]),
                        input_payload=dict(data["input_payload"]),
                        # tool_name is audit attribution — the member cannot
                        # relabel a row as another tool (review AI-05).
                        tool_name=None,
                    )
                )
            except ProviderError as error:
                raise contract_error(
                    503,
                    error.code,
                    "El proveedor de IA no está disponible en este momento.",
                ) from None


class AiAskView(APIView):
    """Contextual "Preguntar a DEKOPEN" — the question and surface come from
    the client; every fact in the context is queried server-side under the
    caller's RLS. The provider answers inside that projection only."""

    @extend_schema(
        operation_id="ai_ask",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=AiAskRequestSerializer,
        responses={200: AiAskResponseSerializer, **ERRORS},
        tags=["ai"],
    )
    def post(self, request):
        data = validate(AiAskRequestSerializer, request.data)
        with documentary_scope(request, _CALLERS) as (token, _, org_id):
            try:
                return Response(
                    ask(
                        org_id=org_id,
                        user_id=token.user_id,
                        surface=str(data["surface"]),
                        refs=dict(data.get("refs") or {}),
                        question=str(data["question"]),
                        operation_key=str(data["operation_key"]),
                    )
                )
            except ProviderError as error:
                raise contract_error(
                    503,
                    error.code,
                    "El proveedor de IA no está disponible en este momento.",
                ) from None

    @extend_schema(
        operation_id="ai_ask_thread",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "surface", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True,
            ),
            OpenApiParameter(
                "refs", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True,
                description="Context refs as a JSON object — the same "
                "identifier map the ask call carries.",
            ),
        ],
        responses={200: AiAskTurnSerializer(many=True), **ERRORS},
        tags=["ai"],
    )
    def get(self, request):
        """The durable ask thread for this context — the dock restores it
        after reload so a conversation survives instead of resetting."""
        with documentary_scope(request, _CALLERS) as (token, _, org_id):
            surface = str(request.query_params.get("surface") or "")
            raw_refs = str(request.query_params.get("refs") or "{}")
            try:
                refs = json.loads(raw_refs)
            except json.JSONDecodeError:
                raise contract_error(
                    400, "ai_context_ref_invalid",
                    "La referencia de contexto no es válida.",
                ) from None
            if not isinstance(refs, dict):
                raise contract_error(
                    400, "ai_context_ref_invalid",
                    "La referencia de contexto no es válida.",
                )
            if surface not in AGENT_REQUIRED_REFS:
                raise contract_error(
                    400, "ai_surface_unknown",
                    "La superficie indicada no existe.",
                )
            return Response(
                list_turns(
                    org_id=org_id,
                    user_id=token.user_id,
                    surface=surface,
                    refs=refs,
                )
            )


class AiAgentView(APIView):
    """The agent surface: a goal becomes a bounded observe → plan → propose
    loop. Queries run server-side inside typed projections; every emitted
    step is validated before it reaches the client, and nothing consequential
    executes without the human clicking on the real surface."""

    @extend_schema(
        operation_id="ai_agent",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=AiAgentRequestSerializer,
        responses={202: AiAgentAcceptedSerializer, **ERRORS},
        tags=["ai"],
    )
    def post(self, request):
        data = validate(AiAgentRequestSerializer, request.data)
        surface = str(data["surface"])
        refs = dict(data.get("refs") or {})
        # The run executes on the durable worker: the POST only creates the
        # QUEUED job row and enqueues its execution, so the client reaches
        # the live transcript (and the cancel affordance) instead of
        # blocking a request thread for the whole provider loop.
        with documentary_scope(request, _AGENT_CALLERS) as (token, _, org_id):
            # An unknown surface must fail here — a typo otherwise lands a
            # QUEUED job whose context build errors inside the worker,
            # off-screen from the caller who sent it.
            if surface not in AGENT_REQUIRED_REFS:
                raise contract_error(
                    400,
                    "ai_surface_unknown",
                    "La superficie indicada no existe.",
                )
            missing_refs = [
                name
                for name in AGENT_REQUIRED_REFS.get(surface, ())
                if name not in refs
            ]
            if missing_refs:
                raise contract_error(
                    400,
                    "ai_context_ref_required",
                    f"Esta superficie requiere la referencia '{missing_refs[0]}'.",
                )
            operation_key = str(data["operation_key"])
            try:
                # The job row's refs are the conversation's identity —
                # volatile pointer refs (a live canvas selection) stay in the
                # run payload for context but never key the durable job, or
                # every selection change would mint a new conversation.
                job = jobs.enqueue_job(
                    org_id=org_id,
                    user_id=token.user_id,
                    surface=surface,
                    refs=stable_refs(refs),
                    goal=str(data["goal"]),
                    operation_key=operation_key,
                )
            except ValueError as error:
                # A recycled operation_key carrying a different goal/refs is
                # a client bug — refuse it instead of silently replaying.
                raise contract_error(
                    409,
                    "ai_operation_key_conflict",
                    "La clave de operación ya fue usada con otra solicitud.",
                ) from error
            try:
                # job_runs is service-owned — the enqueue runs under the same
                # role switch the ingest path uses, or the request scope's
                # documentary_backend role is refused with 42501.
                with job_service.job_backend():
                    job_service.enqueue(
                        org_id=org_id,
                        job_type="ai.agent.run",
                        payload={
                            "ai_job_id": job["id"],
                            "mode": "new",
                            "surface": surface,
                            "refs": refs,
                            "goal": str(data["goal"]),
                            "product": data.get("product"),
                            "product_sig": str(data.get("product_sig") or ""),
                            "history": list(data.get("history") or []),
                            "operation_key": operation_key,
                        },
                        idempotency_key=f"ai:{operation_key}",
                        created_by=token.user_id,
                    )
            except job_service.JobServiceError as error:
                raise contract_error(
                    409, error.code, "No se pudo encolar la tarea del agente."
                ) from error
            return Response(
                {"job_id": job["id"], "state": job["state"]},
                status=status.HTTP_202_ACCEPTED,
            )


class AiJobCollectionView(APIView):
    """The caller's recent AI jobs — the workspace's left rail."""

    @extend_schema(
        operation_id="ai_job_list",
        parameters=[
            OpenApiParameter(
                "before", OpenApiTypes.DATETIME, OpenApiParameter.QUERY,
                description="Cursor: return jobs created before this timestamp "
                "(the last row's created_at) — older pages of the job rail.",
            ),
            OpenApiParameter(
                "before_id", OpenApiTypes.UUID, OpenApiParameter.QUERY,
                description="Tie-breaker: the last row's id — jobs sharing the "
                "cursor's timestamp paginate by id so nothing falls between pages.",
            ),
        ],
        responses={200: AiJobSerializer(many=True), **ERRORS},
        tags=["ai"],
    )
    def get(self, request):
        with documentary_scope(request, _AGENT_CALLERS) as (token, _, org_id):
            return Response(
                jobs.list_jobs(
                    org_id=org_id,
                    user_id=token.user_id,
                    before=request.query_params.get("before"),
                    before_id=request.query_params.get("before_id"),
                )
            )


class AiJobView(APIView):
    """One job with its full transcript; DELETE cancels a live run."""

    @extend_schema(
        operation_id="ai_job_retrieve",
        responses={200: AiJobDetailSerializer, **ERRORS},
        tags=["ai"],
    )
    def get(self, request, job_id):
        with documentary_scope(request, _AGENT_CALLERS) as (token, _, org_id):
            job = jobs.get_job(
                org_id=org_id, user_id=token.user_id, job_id=job_id
            )
            if job is None:
                raise contract_error(
                    404, "ai_job_not_found", "El trabajo no existe."
                )
            return Response(job)

    @extend_schema(
        operation_id="ai_job_cancel",
        responses={200: AiJobSerializer, **ERRORS},
        tags=["ai"],
    )
    def delete(self, request, job_id):
        with documentary_scope(request, _AGENT_CALLERS) as (token, _, org_id):
            job = jobs.get_job(
                org_id=org_id, user_id=token.user_id, job_id=job_id
            )
            if job is None:
                raise contract_error(
                    404, "ai_job_not_found", "El trabajo no existe."
                )
            outcome = jobs.request_cancel(
                job_id=job_id, org_id=org_id, user_id=token.user_id
            )
            if outcome == "terminal":
                raise contract_error(
                    409, "ai_job_terminal", "El trabajo ya terminó."
                )
            job["cancel_signaled"] = outcome == "signaled"
            return Response(job)


class AiJobMessagesView(APIView):
    """§07-B follow-up instructions: appends a user turn and runs the agent
    again inside the same job — transcript, plan and artifacts keep
    accumulating; the earlier result is never deleted."""

    @extend_schema(
        operation_id="ai_job_message_create",
        request=AiJobMessageSerializer,
        responses={202: AiAgentAcceptedSerializer, **ERRORS},
        tags=["ai"],
    )
    def post(self, request, job_id):
        data = validate(AiJobMessageSerializer, request.data)
        # The claim and run happen in the worker — the POST validates,
        # enqueues a resume round, and returns 202 so the workspace polls
        # the live transcript instead of blocking on the provider loop.
        try:
            with documentary_scope(request, _AGENT_CALLERS) as (token, _, org_id):
                job = jobs.get_job(
                    org_id=org_id, user_id=token.user_id, job_id=job_id
                )
                if job is None:
                    raise contract_error(
                        404, "ai_job_not_found", "El trabajo no existe."
                    )
                if job["state"] in ("FAILED", "CANCELED"):
                    raise contract_error(
                        409, "ai_job_terminal", "El trabajo ya terminó."
                    )
                if job["state"] in ("QUEUED", "PLANNING", "RUNNING"):
                    raise contract_error(
                        409,
                        "ai_job_running",
                        "Ya hay una instrucción en curso en este trabajo.",
                    )
                def _history_entry(turn: dict) -> dict:
                    content = str(
                        turn.get("text") or turn.get("reply") or ""
                    )
                    if turn.get("role") == "agent":
                        # The model must see what it already proposed —
                        # stripped history let follow-ups re-emit a duplicate
                        # ops/prepare step as if it were new.
                        proposed = [
                            str(step.get("label") or step.get("kind") or "")
                            for step in (turn.get("steps") or [])
                            if isinstance(step, dict)
                        ][:6]
                        artifacts = [
                            str(art.get("title") or art.get("kind") or "")
                            for art in (turn.get("artifacts") or [])
                            if isinstance(art, dict)
                        ][:6]
                        digest = [
                            item for item in (*proposed, *artifacts) if item
                        ]
                        if digest:
                            content = (
                                f"{content} [propuso: {'; '.join(digest)}]"
                            )
                    return {
                        "role": turn.get("role"),
                        # Replies outlive the run serializer's per-turn cap —
                        # truncate here or every later follow-up wedges the
                        # job on job_payload_invalid.
                        "content": content[:2000],
                    }

                history = [
                    _history_entry(turn)
                    for turn in job.get("transcript") or []
                    # Only roles the run serializer accepts; error turns and
                    # empty entries would otherwise reject the whole
                    # follow-up as job_payload_invalid.
                    if isinstance(turn, dict)
                    and turn.get("role") in ("user", "agent")
                    and str(turn.get("text") or turn.get("reply") or "").strip()
                ][-22:]  # the run serializer caps history at 24 — trim here
                # so a long-lived job's payload never crosses the bound.
                operation_key = str(
                    request.headers.get("X-Operation-Key")
                    or f"{job_id}:{len(history)}"
                )
                # Flip the row to QUEUED *before* the run becomes claimable —
                # the worker polls job_runs continuously and would otherwise
                # claim a run whose ai_job still reads SUCCEEDED, fail the
                # claim, and leave this job wedged in QUEUED with no live run.
                # The flip is also the mutex: only the request that moves a
                # settled state to QUEUED may enqueue — a loser that saw the
                # same settled state leaves with a conflict, not a second run.
                previous = jobs.mark_queued(
                    job_id=job_id, org_id=org_id, user_id=token.user_id
                )
                if previous is None:
                    raise contract_error(
                        409,
                        "ai_job_running",
                        "Ya hay una instrucción en curso en este trabajo.",
                    )
                try:
                    with job_service.job_backend():
                        queued, created = job_service.enqueue(
                            org_id=org_id,
                            job_type="ai.agent.run",
                            payload={
                                "ai_job_id": str(job["id"]),
                                "mode": "resume",
                                "surface": str(job["surface"]),
                                # Live refs from the caller refresh volatile
                                # pointers (selection); the stored row keeps
                                # stable identity refs only.
                                "refs": dict(data.get("refs") or job.get("refs") or {}),
                                "goal": str(data["message"]),
                                # The product rides with each message — the
                                # client sends the position's live
                                # representation, so design ops evaluate the
                                # current design, never a snapshot stored at
                                # job creation.
                                "product": data.get("product"),
                                "product_sig": str(data.get("product_sig") or ""),
                                "history": history,
                                # Server-rebuilt from the stored transcript —
                                # its numbers may ground the follow-up.
                                "history_trusted": True,
                                "operation_key": operation_key,
                            },
                            idempotency_key=f"ai:{operation_key}",
                            created_by=token.user_id,
                        )
                except job_service.JobServiceError as error:
                    # The QUEUED mark committed in autocommit — restore the
                    # pre-mark state or the job wedges QUEUED with no run.
                    jobs.restore_queued(job_id=job_id, previous=previous)
                    raise contract_error(
                        409, error.code,
                        "No se pudo encolar la instrucción del agente.",
                    ) from error
                # The key is the dedupe boundary for RETRIES of one message —
                # reusing it with different text must not silently replay the
                # stored instruction while claiming the new one is queued.
                stored = queued.get("payload") or {}
                if (
                    not created
                    and queued.get("state") not in ("FAILED", "CANCELED")
                    and str(stored.get("goal") or "") != str(data["message"])
                ):
                    jobs.restore_queued(job_id=job_id, previous=previous)
                    raise contract_error(
                        409,
                        "operation_conflict",
                        "Esta clave de operación ya fue usada con una instrucción distinta.",
                    )
                return Response(
                    {"job_id": str(job["id"]), "state": "QUEUED"},
                    status=status.HTTP_202_ACCEPTED,
                )
        except ContractAPIException:
            # The claim happens in the worker now — errors before the enqueue
            # (404, conflicts, validation) leave the job untouched.
            raise
        except Exception as failure:
            _raise_agent_error(failure)


class AiJobRetryView(APIView):
    """Re-run a retryable failed round. The goal is the FAILED round's own
    message — the last user turn in the transcript — not the job's original
    goal, so a retry of a failed follow-up doesn't silently re-execute the
    first request and emit a duplicate proposal. The payload's replay flag
    makes the transcript turn read as a re-run, not a new message."""

    @extend_schema(
        operation_id="ai_job_retry",
        request=None,
        responses={202: AiJobSerializer, **ERRORS},
        tags=["ai"],
    )
    def post(self, request, job_id):
        with documentary_scope(request, _AGENT_CALLERS) as (token, _, org_id):
            job = jobs.get_job(
                org_id=org_id, user_id=token.user_id, job_id=job_id
            )
            if job is None:
                raise contract_error(
                    404, "ai_job_not_found", "El trabajo no existe."
                )
            if job["state"] != "FAILED_RETRYABLE":
                raise contract_error(
                    409,
                    "ai_job_not_retryable",
                    "El trabajo no está en un estado reintentable.",
                )
            # The FAILED round's own message is what replays — the last
            # user turn the transcript recorded before the error. The job
            # row's goal is only the first round's request.
            failed_message = next(
                (
                    str(turn.get("text") or "").strip()
                    for turn in reversed(job.get("transcript") or [])
                    if isinstance(turn, dict)
                    and turn.get("role") == "user"
                    and str(turn.get("text") or "").strip()
                ),
                str(job["goal"]),
            )
            # Idempotent per attempt: mark_queued bumps updated_at, so the
            # derived key is unique per retry — a double POST of the same
            # click lands on one worker run.
            if (
                jobs.mark_queued(
                    job_id=job_id, org_id=org_id, user_id=token.user_id
                )
                is None
            ):
                raise contract_error(
                    409,
                    "ai_job_running",
                    "Ya hay una instrucción en curso en este trabajo.",
                )
            retry_key = f"retry:{job_id}:{job['updated_at']}"
            try:
                with job_service.job_backend():
                    job_service.enqueue(
                        org_id=org_id,
                        job_type="ai.agent.run",
                        payload={
                            "ai_job_id": str(job["id"]),
                            "mode": "resume",
                            "surface": str(job["surface"]),
                            "refs": dict(job.get("refs") or {}),
                            "goal": failed_message,
                            "history": [],
                            "operation_key": retry_key,
                            "replay": True,
                        },
                        idempotency_key=f"ai:{retry_key}",
                        created_by=token.user_id,
                    )
            except job_service.JobServiceError as error:
                raise contract_error(
                    409, error.code, "No se pudo reintentar el trabajo."
                ) from error
            job["state"] = "QUEUED"
            return Response(job, status=status.HTTP_202_ACCEPTED)


class AiJobOutcomeView(APIView):
    """§08 measurement — the client reports what the human did with a
    proposed step. Idempotent: a retried report dedupes on
    (turn, step, action) and answers 200 with recorded=false instead of
    double-counting."""

    @extend_schema(
        operation_id="ai_job_outcome_create",
        request=AiJobOutcomeSerializer,
        responses={200: AiJobOutcomeResponseSerializer, **ERRORS},
        tags=["ai"],
    )
    def post(self, request, job_id):
        data = validate(AiJobOutcomeSerializer, request.data)
        with documentary_scope(request, _AGENT_CALLERS) as (token, _, org_id):
            job = jobs.get_job(
                org_id=org_id, user_id=token.user_id, job_id=job_id
            )
            if job is None:
                raise contract_error(
                    404, "ai_job_not_found", "El trabajo no existe."
                )
            result = jobs.record_outcome(
                org_id=org_id,
                user_id=token.user_id,
                job_id=job_id,
                entry=data,
            )
            return Response(result)


class AiMetricsView(APIView):
    """§08 measurement — org-level AI metrics over the trailing window."""

    @extend_schema(
        operation_id="ai_metrics",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "days", OpenApiTypes.INT, location=OpenApiParameter.QUERY
            ),
        ],
        responses={200: AiMetricsSerializer, **ERRORS},
        tags=["ai"],
    )
    def get(self, request):
        try:
            days = int(request.query_params.get("days") or 30)
        except (TypeError, ValueError):
            raise contract_error(
                400, "ai_metrics_days_invalid", "El período no es válido."
            ) from None
        if not 1 <= days <= 365:
            raise contract_error(
                400, "ai_metrics_days_invalid", "El período no es válido."
            )
        with documentary_scope(request, _AGENT_CALLERS) as (_, _, org_id):
            return Response(ai_metrics(org_id=org_id, days=days))
