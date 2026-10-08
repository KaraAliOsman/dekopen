"""P02 — org-scoped human folios: concurrent allocators cannot collide.

Two transactions claiming the same org's counter at the same instant must
land distinct consecutive folios (the advisory lock serializes them and
the second count runs after the first commits). A different org counts
independently. A rolled-back allocation frees the lock without burning a
number — the next claimant reuses it (gap policy: folios are contiguous
by design, a crash cannot leave a hole that reads as a lost record).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection, transaction

pytestmark = pytest.mark.rls_integration


@pytest.fixture
def concurrent_orgs(django_db_blocker):
    """Autocommitted orgs so worker-thread connections can see them."""
    with django_db_blocker.unblock():
        if connection.vendor != "postgresql":
            pytest.fail("P02 requires real PostgreSQL; never skipped")
        org_a, org_b = uuid4(), uuid4()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.tenancy_organizations(id,name,tax_id)"
                " VALUES(%s,%s,%s),(%s,%s,%s)",
                [org_a, "P02 concurrency A", str(org_a),
                 org_b, "P02 concurrency B", str(org_b)],
            )
        try:
            yield org_a, org_b
        finally:
            connection.close()
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM public.inventory_remnants"
                    " WHERE org_id IN (%s,%s)",
                    [org_a, org_b],
                )
                cursor.execute(
                    "DELETE FROM public.tenancy_organizations"
                    " WHERE id IN (%s,%s)",
                    [org_a, org_b],
                )


def _claim_bar_remnant(org_id: object, barrier: Barrier, commit: bool) -> str:
    """One transaction: take the folio then write the row it names — the same
    order the service does (counter first, row second, single commit)."""
    close_old_connections()
    code = ""
    try:
        try:
            with transaction.atomic():
                barrier.wait(timeout=15)  # both txs race the allocator
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT private.next_human_code(%s::uuid,%s)",
                        [str(org_id), "inventory_remnants"],
                    )
                    code = cursor.fetchone()[0]
                    cursor.execute(
                        "INSERT INTO public.inventory_remnants"
                        "(org_id,kind,stock_authority_id,length_mm,remnant_code)"
                        " VALUES(%s,'BAR',%s::uuid,1200,%s)",
                        [str(org_id), str(uuid4()), code],
                    )
                if not commit:
                    transaction.set_rollback(True)
        except transaction.TransactionManagementError:
            pass
        return code
    finally:
        close_old_connections()


def test_concurrent_allocators_get_distinct_consecutive_codes(concurrent_orgs) -> None:
    org_a, _ = concurrent_orgs
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(
            pool.map(lambda _: _claim_bar_remnant(org_a, barrier, True), range(2))
        )
    assert sorted(codes) == ["RT-000001", "RT-000002"], codes


def test_orgs_count_independently_and_rollback_reuses(concurrent_orgs) -> None:
    org_a, org_b = concurrent_orgs
    solo = Barrier(1)
    # Different orgs: independent sequences, both start at 1.
    assert _claim_bar_remnant(org_a, solo, True) == "RT-000001"
    assert _claim_bar_remnant(org_b, solo, True) == "RT-000001"
    # Rolled-back claim frees the advisory lock and burns nothing: the next
    # allocation in the same org reuses the folio (contiguous by design).
    assert _claim_bar_remnant(org_a, solo, False) == "RT-000002"
    assert _claim_bar_remnant(org_a, solo, True) == "RT-000002"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT remnant_code FROM public.inventory_remnants"
            " WHERE org_id=%s ORDER BY remnant_code",
            [str(org_a)],
        )
        assert [row[0] for row in cursor.fetchall()] == ["RT-000001", "RT-000002"]
