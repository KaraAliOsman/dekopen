"""Transaction-local propagation of verified JWT claims into PostgreSQL RLS."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import json

from django.db import connection, transaction


def tx_aborted() -> bool:
    """True when issuing SQL would fail with 25P02 'current transaction is
    aborted'. Django's `needs_rollback` flag only flips inside
    Atomic.__exit__ — while an exception is still unwinding through a context
    manager's try/finally it reads False although Postgres already rejects
    commands, so the live driver status (psycopg's INERROR) is checked too."""
    if connection.needs_rollback:
        return True
    inner = getattr(connection, "connection", None)
    if inner is None:
        return False
    status = getattr(getattr(inner, "info", None), "transaction_status", None)
    # psycopg3: pq.TransactionStatus.INERROR == 3; drivers without .info
    # (sqlite, test doubles) never report an aborted transaction.
    return status is not None and int(status) == 3


def _restore_role_and_claims(previous_role: str, previous_claims: str | None) -> None:
    """Undo a transaction-local role/claims switch. SET LOCAL survives
    savepoints, so without this the switched role leaks into the caller's
    outer transaction (e.g. a job worker's progress writes then run as
    `authenticated` and get permission-denied)."""
    if tx_aborted():
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('role', %s, true)", [previous_role])
        cursor.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            [previous_claims or ""],
        )


def _current_role_and_claims(cursor) -> tuple[str, str | None]:
    cursor.execute(
        "SELECT current_setting('role', true), "
        "current_setting('request.jwt.claims', true)"
    )
    role, claims = cursor.fetchone()
    return str(role or "none"), (str(claims) if claims else None)


@contextmanager
def catalog_backend() -> Iterator[None]:
    """Catalog writes run under the dedicated backend role: member-facing
    `authenticated` holds only column-wise grants over the writable fields, so
    provenance, review stamps and section revisions are exclusively API-written
    under this role. Org/user RLS policies and request.jwt.claims are
    unchanged. No-op where roles do not exist (SQLite unit tests)."""
    if connection.vendor != "postgresql":
        yield
        return
    with connection.cursor() as cursor:
        previous_role, _ = _current_role_and_claims(cursor)
        cursor.execute("SET LOCAL ROLE catalog_backend")
    try:
        yield
    finally:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('role', %s, true)", [previous_role])


@contextmanager
def worker_claims(claims: Mapping[str, object]) -> Iterator[None]:
    """Session-scoped request.jwt.claims for job handlers.

    A handler spans several transactions (membership check, provider call,
    status writes), so the transaction-local GUC used by the request path
    evaporates before the real work — the role's RLS then reads empty
    current_user_org_ids() and every row operation matches nothing. Session
    scope survives across those transactions; the prior value is restored on
    exit so the worker connection never carries claims into another job.
    """
    if connection.vendor != "postgresql":
        yield
        return
    claims_json = json.dumps(dict(claims), separators=(",", ":"), sort_keys=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('request.jwt.claims', true)")
        previous = cursor.fetchone()[0]
        cursor.execute(
            "SELECT set_config('request.jwt.claims', %s, false)", [claims_json]
        )
    try:
        yield
    finally:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('request.jwt.claims', %s, false)",
                    [str(previous) if previous else ""],
                )


@contextmanager
def authenticated_rls_context(claims: Mapping[str, object]) -> Iterator[None]:
    claims_json = json.dumps(dict(claims), separators=(",", ":"), sort_keys=True)
    with transaction.atomic():
        with connection.cursor() as cursor:
            previous_role, previous_claims = _current_role_and_claims(cursor)
            cursor.execute(
                "SELECT set_config('request.jwt.claims', %s, true)",
                [claims_json],
            )
            cursor.execute("SET LOCAL ROLE authenticated")
        try:
            yield
        finally:
            _restore_role_and_claims(previous_role, previous_claims)
