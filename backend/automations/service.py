"""Emit side of the domain automations.

``emit`` runs INSIDE the caller's domain transaction so the queued job exists
only if the triggering event commits. The job_runs INSERT is service_role-only,
so the enqueue momentarily overrides the member-facing claims — the same
save/restore discipline ``job_backend`` uses for the role itself.

The emit is best-effort on purpose: a queue fault must never roll back a
freeze, a payment, or a step transition. Failures are logged with the job type
and refs so a lost automation is diagnosable rather than silent.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from django.db import connection, transaction

logger = logging.getLogger(__name__)


@contextmanager
def _service_claims() -> Iterator[None]:
    """Assert service_role claims for the duration of the job_runs INSERT.

    job_runs' insert policy requires ``auth.jwt()->>'role'='service_role'``;
    inside a member-facing transaction the claims carry the user. The previous
    claims are restored on exit exactly as set_config(true) scoped them."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('request.jwt.claims', true)")
        previous = cursor.fetchone()[0]
        cursor.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            [json.dumps({"role": "service_role"})],
        )
    try:
        yield
    finally:
        if not connection.needs_rollback:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('request.jwt.claims', %s, true)",
                    [previous or "{}"],
                )


def emit(
    job_type: str,
    *,
    org_id: UUID,
    actor_id: UUID | None,
    idempotency_key: str,
    **refs: object,
) -> dict[str, object] | None:
    """Queue a domain-automation job next to the committing event.

    ``idempotency_key`` is required: automation emissions dedupe by logical
    event (``auto:<kind>:<entity>[:<variant>]``) so a replayed freeze or a
    double-submitted transition never double-books the follow-up work.
    """
    from jobs.service import enqueue, job_backend

    try:
        # Savepoint: emit() runs inside the caller's transaction (e.g. the
        # documentary freeze); a failed enqueue must roll back only this
        # statement, never poison the whole commit it rides on.
        with transaction.atomic(), job_backend(), _service_claims():
            job, created = enqueue(
                org_id=org_id,
                job_type=job_type,
                payload=refs,
                idempotency_key=idempotency_key,
                created_by=actor_id,
            )
    except Exception:
        logger.exception(
            "automation_emit_failed type=%s org=%s key=%s",
            job_type, org_id, idempotency_key,
        )
        return None
    return {"job_id": str(job.get("id")), "created": created}
