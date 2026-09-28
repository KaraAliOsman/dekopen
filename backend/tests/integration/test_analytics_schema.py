"""Operational summary must execute against the real migrated schema.

The unit test mocks ``rows``/``one`` so it can never notice a column the SQL
references that no migration creates (the ``projects.currency`` regression —
SQLSTATE 42703 reached the dashboard as a permanent 409). Running the real
service on the real database is the only honest check: an org with no data
still parses and executes every aggregate."""

from __future__ import annotations

from uuid import uuid4

from django.db import connection
import pytest

from analytics.service import operational_summary

pytestmark = pytest.mark.rls_integration


def test_operational_summary_executes_on_the_real_schema(django_db_blocker) -> None:
    if connection.vendor != "postgresql":
        pytest.fail("Real schema gate requires the local Supabase DATABASE_URL")
    with django_db_blocker.unblock():
        output = operational_summary(org_id=uuid4())
    assert output["schema"] == "operational_summary_v1"
    assert output["projects"]["projects"] == 0
    assert output["commercial"] == []
    assert output["inventory"] == {"items": 0, "offcuts": 0}
