from __future__ import annotations

from contextlib import nullcontext
import json

import pytest

import authentication.rls
from authentication.rls import authenticated_rls_context


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.calls.append((sql, params))

    def fetchone(self) -> tuple[str, str | None]:
        # Mimics Postgres answering the role/claims probe — the context
        # manager restores these captured values on exit.
        return ("none", None)


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self.recording_cursor = cursor
        self.needs_rollback = False

    def cursor(self) -> RecordingCursor:
        return self.recording_cursor


def test_verified_claims_and_authenticated_role_are_transaction_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = RecordingCursor()
    monkeypatch.setattr(authentication.rls, "connection", RecordingConnection(cursor))
    monkeypatch.setattr(authentication.rls.transaction, "atomic", nullcontext)
    claims = {"sub": "10000000-0000-0000-0000-000000000001", "role": "authenticated"}

    with authenticated_rls_context(claims):
        pass

    assert cursor.calls[0][0] == (
        "SELECT current_setting('role', true), "
        "current_setting('request.jwt.claims', true)"
    )
    assert cursor.calls[1][0] == "SELECT set_config('request.jwt.claims', %s, true)"
    assert json.loads(cursor.calls[1][1][0]) == claims
    assert cursor.calls[2] == ("SET LOCAL ROLE authenticated", None)
    # The switch is restored on exit — SET LOCAL is transaction-scoped, so a
    # savepoint never rolls it back for the caller.
    assert cursor.calls[3][0] == "SELECT set_config('role', %s, true)"
    assert cursor.calls[3][1] == ["none"]
