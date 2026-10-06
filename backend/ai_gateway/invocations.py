"""§IA3 — durable AI invocation log and provider spend accounting.

`ai_invocations` is the row the /jobs activity panel and the settings
consumption view read: one row per committed provider call (plus the error
and budget-blocked rows a failed run records post-rollback). Content-free
by design — capability, public model, tokens, latency, credits, estimated
USD, status. Never prompts, outputs, or client payloads.

Write semantics: `record` joins the caller's transaction when one is live
(a success row lands iff the outer commit lands — the debit and the log
stay atomic together), and commits on its own when no transaction is live
(the post-rollback error paths). Failed rows ride `error.invocation` from
service.invoke to whoever owns the post-rollback write.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from django.db import DatabaseError, connection, transaction

from authentication.rls import tx_aborted
from pricing.repository import rows

# Per-job structured line: the ops channel mirrors the same row the
# activity panel reads — no sensitive content, ever.
calls_logger = logging.getLogger("ai_gateway.calls")

_INSERT_SQL = (
    "INSERT INTO public.ai_invocations("
    "org_id, user_id, kind, capability, tool_name, operation_key, mode,"
    " public_model, tokens_prompt, tokens_completion, latency_ms, credits,"
    " est_cost_usd, status, error_code)"
    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id"
)


def build_entry(
    *,
    org_id: UUID,
    user_id: UUID | None,
    capability: str,
    tool_name: str | None = None,
    operation_key: str | None = None,
    kind: str = "call",
    mode: str = "live",
    public_model: str | None = None,
    tokens_prompt: int = 0,
    tokens_completion: int = 0,
    latency_ms: int = 0,
    credits: int = 0,
    est_cost_usd: Any = None,
    status: str = "ok",
    error_code: str | None = None,
) -> dict:
    return {
        "org_id": str(org_id),
        "user_id": str(user_id) if user_id else None,
        "kind": kind[:16],
        "capability": str(capability)[:100],
        "tool_name": (str(tool_name)[:100] if tool_name else None),
        "operation_key": (str(operation_key)[:200] if operation_key else None),
        "mode": mode[:12],
        "public_model": (str(public_model)[:120] if public_model else None),
        "tokens_prompt": int(tokens_prompt or 0),
        "tokens_completion": int(tokens_completion or 0),
        "latency_ms": int(latency_ms or 0),
        "credits": int(credits or 0),
        "est_cost_usd": (
            str(est_cost_usd) if est_cost_usd is not None else None
        ),
        "status": status[:12],
        "error_code": (str(error_code)[:120] if error_code else None),
    }


def _insert(entry: dict) -> None:
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE ai_backend")
            cursor.execute("SELECT current_setting('request.jwt.claims', true)")
            existing = cursor.fetchone()[0]
            if not existing:
                # Post-commit and post-rollback writes have no live claims —
                # the row's own user anchors the org-membership check.
                cursor.execute(
                    "SELECT set_config('request.jwt.claims', %s, true)",
                    [
                        json.dumps(
                            {
                                "sub": entry["user_id"],
                                "aud": "authenticated",
                                "role": "authenticated",
                            }
                        )
                    ],
                )
    rows(
        _INSERT_SQL,
        [
            entry["org_id"],
            entry["user_id"],
            entry["kind"],
            entry["capability"],
            entry["tool_name"],
            entry["operation_key"],
            entry["mode"],
            entry["public_model"],
            entry["tokens_prompt"],
            entry["tokens_completion"],
            entry["latency_ms"],
            entry["credits"],
            entry["est_cost_usd"],
            entry["status"],
            entry["error_code"],
        ],
    )


def record(entry: dict) -> bool:
    """Persist one invocation row. Inside a live transaction this joins it
    (savepoint) — the row lands iff the outer commit does; outside, it opens
    its own transaction and commits immediately. False on a dead
    transaction, so the caller's post-rollback path can re-record."""
    if tx_aborted():
        return False
    try:
        with transaction.atomic():
            _insert(entry)
        return True
    except DatabaseError:
        return False


def record_attached(error: BaseException) -> bool:
    """The invocation metadata service.invoke stashes on a failed call —
    `error.invocation`. Called once the surrounding transaction rolled
    back so the failure itself becomes durable."""
    entry = getattr(error, "invocation", None)
    if entry is None:
        return False
    return record(entry)


@contextmanager
def error_recorder():
    """View-level wrapper: captures `error.invocation` from any provider or
    contract failure that propagates through the request scope and writes
    the rows after the scope's transaction unwinds — the same post-rollback
    durability pattern the job handler uses for ai_jobs failures.

        with invocations.error_recorder() as capture:
            with documentary_scope(...) as ...:
                try:
                    service.invoke(...)
                except ProviderError as error:
                    capture(error)
                    raise contract_error(...)
    """
    entries: list[dict] = []

    def capture(error: BaseException) -> None:
        entry = getattr(error, "invocation", None)
        if entry is not None:
            entries.append(entry)

    try:
        yield capture
    except BaseException as error:
        # Contract errors raised inside the scope (budget block, entitlement)
        # may carry the row directly.
        capture(error)
        raise
    finally:
        for entry in entries:
            record(entry)


def monthly_budget(org_id: UUID) -> int | None:
    """The org's monthly AI ceiling in wallet credits; None = no cap."""
    found = rows(
        "SELECT monthly_credit_budget FROM public.ai_org_settings"
        " WHERE org_id = %s",
        [str(org_id)],
    )
    if not found or found[0]["monthly_credit_budget"] is None:
        return None
    return int(found[0]["monthly_credit_budget"])


def month_credits_spent(org_id: UUID) -> int:
    """Credits debited this calendar month — read from the sealed audit
    rows so the budget check runs inside the billing transaction."""
    found = rows(
        "SELECT COALESCE(SUM(points_debited), 0) AS total"
        " FROM public.ai_audit_logs"
        " WHERE org_id = %s AND created_at >= date_trunc('month', NOW())",
        [str(org_id)],
    )
    return int(found[0]["total"] or 0)


def month_usage(org_id: UUID) -> dict:
    """The settings consumption block: calls, tokens, credits and estimated
    USD this month, plus per-user and per-capability breakdowns. est_cost_usd
    aggregates honestly — NULL when no priced model contributed."""
    found = rows(
        "SELECT COUNT(*)::int AS calls,"
        " COALESCE(SUM(tokens_prompt),0)::bigint AS tokens_prompt,"
        " COALESCE(SUM(tokens_completion),0)::bigint AS tokens_completion,"
        " COALESCE(SUM(credits),0)::bigint AS credits,"
        " SUM(est_cost_usd) AS est_cost_usd,"
        " COALESCE(SUM(CASE WHEN status='error' THEN 1 ELSE 0 END),0)::int"
        "   AS errors"
        " FROM public.ai_invocations"
        " WHERE org_id = %s AND kind = 'call'"
        " AND created_at >= date_trunc('month', NOW())",
        [str(org_id)],
    )[0]
    by_user = rows(
        "SELECT i.user_id, MAX(m.role::text) AS member_role,"
        " COUNT(*)::int AS calls,"
        " COALESCE(SUM(i.credits),0)::bigint AS credits,"
        " COALESCE(SUM(i.tokens_prompt + i.tokens_completion),0)::bigint"
        "   AS tokens"
        " FROM public.ai_invocations i"
        " LEFT JOIN public.tenancy_memberships m"
        "   ON m.org_id = i.org_id AND m.user_id = i.user_id"
        " WHERE i.org_id = %s AND i.kind = 'call'"
        " AND i.created_at >= date_trunc('month', NOW())"
        " GROUP BY i.user_id ORDER BY credits DESC LIMIT 8",
        [str(org_id)],
    )
    by_capability = rows(
        "SELECT capability, COUNT(*)::int AS calls,"
        " COALESCE(SUM(credits),0)::bigint AS credits"
        " FROM public.ai_invocations"
        " WHERE org_id = %s AND kind = 'call'"
        " AND created_at >= date_trunc('month', NOW())"
        " GROUP BY capability ORDER BY credits DESC",
        [str(org_id)],
    )
    return {
        "calls": int(found["calls"]),
        "tokens_prompt": int(found["tokens_prompt"]),
        "tokens_completion": int(found["tokens_completion"]),
        "credits": int(found["credits"]),
        "est_cost_usd": (
            str(found["est_cost_usd"])
            if found["est_cost_usd"] is not None
            else None
        ),
        "errors": int(found["errors"]),
        "by_user": [
            {
                "user_id": str(row["user_id"]) if row["user_id"] else None,
                "member_role": row["member_role"],
                "calls": int(row["calls"]),
                "credits": int(row["credits"]),
                "tokens": int(row["tokens"]),
            }
            for row in by_user
        ],
        "by_capability": [
            {
                "capability": str(row["capability"]),
                "calls": int(row["calls"]),
                "credits": int(row["credits"]),
            }
            for row in by_capability
        ],
    }


def activity(
    org_id: UUID,
    *,
    capability: str | None = None,
    status: str | None = None,
    limit: int = 30,
    before: str | None = None,
) -> list[dict]:
    """The /jobs AI activity feed — newest first, optionally narrowed by
    capability and status. Keyset pagination on created_at like list_jobs."""
    where = " WHERE org_id = %s"
    params: list[Any] = [str(org_id)]
    if capability:
        where += " AND capability = %s"
        params.append(capability[:100])
    if status in ("ok", "error", "blocked"):
        where += " AND status = %s"
        params.append(status)
    if before:
        where += " AND created_at < %s"
        params.append(before)
    params.append(min(max(int(limit), 1), 100))
    return [
        {
            "id": str(row["id"]),
            "kind": str(row["kind"]),
            "capability": str(row["capability"]),
            "tool_name": row["tool_name"],
            "operation_key": row["operation_key"],
            "mode": str(row["mode"]),
            "public_model": row["public_model"],
            "tokens_prompt": int(row["tokens_prompt"]),
            "tokens_completion": int(row["tokens_completion"]),
            "latency_ms": int(row["latency_ms"]),
            "credits": int(row["credits"]),
            "est_cost_usd": (
                str(row["est_cost_usd"])
                if row["est_cost_usd"] is not None
                else None
            ),
            "status": str(row["status"]),
            "error_code": row["error_code"],
            "user_id": str(row["user_id"]) if row["user_id"] else None,
            "created_at": row["created_at"].isoformat()
            if hasattr(row["created_at"], "isoformat")
            else str(row["created_at"]),
        }
        for row in rows(
            "SELECT id, kind, capability, tool_name, operation_key, mode,"
            " public_model, tokens_prompt, tokens_completion, latency_ms,"
            " credits, est_cost_usd, status, error_code, created_at, user_id"
            " FROM public.ai_invocations" + where +
            " ORDER BY created_at DESC, id DESC LIMIT %s",
            params,
        )
    ]


def job_cost(org_id: UUID, operation_key: str) -> dict | None:
    """Spend attributed to one job — the invocations whose operation_key
    shares the job's key prefix (rounds carry :rN/:gN suffixes)."""
    # Rounds carry the job key plus a ':rN'/':gN' suffix — a bare LIKE
    # prefix would also catch unrelated keys that share the head. The key
    # itself is client input, so LIKE wildcards in it must be escaped.
    head = (
        operation_key[:170].replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    found = rows(
        "SELECT COUNT(*)::int AS calls,"
        " COALESCE(SUM(tokens_prompt + tokens_completion),0)::bigint AS tokens,"
        " COALESCE(SUM(credits),0)::bigint AS credits,"
        " SUM(est_cost_usd) AS est_cost_usd"
        " FROM public.ai_invocations"
        " WHERE org_id = %s"
        " AND (operation_key = %s OR operation_key LIKE %s ESCAPE '\\')",
        [str(org_id), operation_key[:170], head + ":%"],
    )
    if not found or not found[0]["calls"]:
        return None
    row = found[0]
    return {
        "calls": int(row["calls"]),
        "tokens": int(row["tokens"]),
        "credits": int(row["credits"]),
        "est_cost_usd": (
            str(row["est_cost_usd"]) if row["est_cost_usd"] is not None else None
        ),
    }


def log_call(entry: dict) -> None:
    """One structured line per call — mirrors the durable row without any
    sensitive content (no prompts, no outputs, no payloads)."""
    calls_logger.info(
        "ai.invoke %s",
        json.dumps(
            {
                "org_id": entry["org_id"],
                "user_id": entry["user_id"],
                "capability": entry["capability"],
                "tool_name": entry["tool_name"],
                "operation_key": entry["operation_key"],
                "mode": entry["mode"],
                "model": entry["public_model"],
                "tokens_prompt": entry["tokens_prompt"],
                "tokens_completion": entry["tokens_completion"],
                "latency_ms": entry["latency_ms"],
                "credits": entry["credits"],
                "est_cost_usd": entry["est_cost_usd"],
                "status": entry["status"],
                "error_code": entry["error_code"],
            },
            default=str,
        ),
    )


__all__ = [
    "activity",
    "build_entry",
    "error_recorder",
    "job_cost",
    "log_call",
    "month_credits_spent",
    "month_usage",
    "monthly_budget",
    "record",
    "record_attached",
]
