"""A concurrent catalog writer cannot make a stale calculation persist."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event, Lock
from uuid import uuid4

from django.db import connection, transaction, close_old_connections, DatabaseError
import pytest

from authentication.errors import ContractAPIException
from backend.tests.integration.catalog_fixture import (
    copy_fixed_catalog,
    decode_jsonb_columns,
)
from backend.tests.integration.test_shot08_pricing import (
    committed_commercial_rows as committed_commercial_rows,
    as_user,
)
from backend.tests.integration.test_shot10_projects_catalogs import position_data
from catalogs import service as catalog_service
from projects import service
from pricing.repository import json_text, one

pytestmark = pytest.mark.rls_integration


def test_concurrent_catalog_change_rejects_stale_save(committed_commercial_rows):
    org, _, users = committed_commercial_rows
    owner = users["OWNER"]
    system = copy_fixed_catalog(org)
    with as_user(owner):
        project = service.create_project(org, owner, {"name": "Concurrent catalog"})["id"]
    ready, changed = Event(), Event()

    def old_snapshot():
        close_old_connections()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                with as_user(owner):
                    one("SELECT id FROM public.profile_systems WHERE id=%s", [system])
                    ready.set()
                    assert changed.wait(10)
                    service.save_position(org, project, position_data(system))
        except DatabaseError as error:
            return error.__cause__.sqlstate
        finally:
            close_old_connections()
        return "unexpected success"

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(old_snapshot)
        assert ready.wait(10)
        try:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("UPDATE public.profile_articles SET welding_loss_mm=welding_loss_mm+1 "
                               "WHERE system_id=%s AND role='FRAME'", [system])
        finally:
            changed.set()
        assert pending.result(10) == "40001"
    with as_user(owner):
        assert service.positions(org, project) == []
        saved = service.save_position(org, project, position_data(system))
        assert saved["bom"]["calculation_hash"].startswith("sha256:")


def _bare_system(org):
    source = one("SELECT * FROM public.profile_systems WHERE code='DEMO_60' AND is_global")
    identity = uuid4()
    one(
        "INSERT INTO public.profile_systems SELECT (jsonb_populate_record("
        "NULL::public.profile_systems,%s::jsonb)).* RETURNING id",
        [json_text(decode_jsonb_columns("profile_systems", {
            **source, "id": identity, "org_id": org, "code": f"RACE-{identity.hex}",
            "is_global": False, "is_demo": False, "technical_locked": False}))],
    )
    return identity


def _article(system, sku, role):
    return {
        "system_id": system,
        "sku": sku,
        "name": sku,
        "role": role,
        "material": "PVC",
        "face_width_mm": Decimal("60.00"),
        "commercial_length_mm": Decimal("6000.00"),
        "welding_loss_mm": Decimal("6.00"),
        "reinforcement_gap_mm": Decimal("10.00"),
        "weight_kg_m": Decimal("1.0000"),
        "steel_weight_kg_m": Decimal("0.0000"),
    }


@pytest.mark.parametrize("operation", ["create", "update"])
def test_concurrent_singleton_role_writes_are_serialized(
    committed_commercial_rows, monkeypatch, operation
):
    org, _, users = committed_commercial_rows
    owner = users["OWNER"]
    system = _bare_system(org)
    targets = []
    if operation == "update":
        with as_user(owner):
            targets = [
                catalog_service.create(
                    catalog_service.ARTICLES, org, _article(system, f"JQ-{index}", "GLAZING_BEAD")
                )
                for index in range(2)
            ]

    reached_write = Event()
    release_write = Event()
    second_done = Event()
    claim_lock = Lock()
    first_call = True
    original_parameters = catalog_service._parameters

    def gated_parameters(values):
        nonlocal first_call
        with claim_lock:
            wait = first_call
            first_call = False
        if wait:
            reached_write.set()
            assert release_write.wait(10)
        return original_parameters(values)

    monkeypatch.setattr(catalog_service, "_parameters", gated_parameters)

    def write(index):
        close_old_connections()
        try:
            with as_user(owner):
                if operation == "create":
                    catalog_service.create(
                        catalog_service.ARTICLES, org, _article(system, f"FRAME-{index}", "FRAME")
                    )
                else:
                    target = targets[index]
                    catalog_service.update(
                        catalog_service.ARTICLES,
                        org,
                        target["id"],
                        {"role": "FRAME"},
                        f'"{target["revision"]}"',
                    )
            return "success"
        except ContractAPIException as error:
            return error.contract_code
        finally:
            if index == 1:
                second_done.set()
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write, 0)
        assert reached_write.wait(10)
        second = pool.submit(write, 1)
        try:
            assert not second_done.wait(1)
        finally:
            release_write.set()
        assert first.result(10) == "success"
        assert second.result(10) == "catalog_write_conflict"

    assert one(
        "SELECT count(*) AS count FROM public.profile_articles "
        "WHERE system_id=%s AND role='FRAME'",
        [system],
    )["count"] == 1


def _unreferenced_global_system(role):
    source = one("SELECT * FROM public.profile_systems WHERE code='DEMO_60' AND is_global")
    identity = uuid4()
    one(
        "INSERT INTO public.profile_systems SELECT (jsonb_populate_record("
        "NULL::public.profile_systems,%s::jsonb)).* RETURNING id",
        [json_text(decode_jsonb_columns("profile_systems", {
            **source, "id": identity, "code": f"GLOB-{identity.hex}",
            "is_demo": False, "technical_locked": False}))],
    )
    one(
        "INSERT INTO public.profile_articles(system_id,sku,name,role,material,face_width_mm) "
        "VALUES(%s,%s,%s,%s,'PVC',60.00) RETURNING id",
        [identity, f"G-{role}", f"Global {role}", role],
    )
    return identity


def test_direct_cross_scope_singleton_write_is_rejected(committed_commercial_rows):
    org, _, users = committed_commercial_rows
    owner = users["OWNER"]
    system = _unreferenced_global_system("FRAME")
    try:
        with as_user(owner):
            # A tenant FRAME beside the global FRAME on a global system is ambiguous
            # for every viewer, so the database rejects it without the service.
            with pytest.raises(DatabaseError, match="catalog_singleton_role_conflict"):
                with transaction.atomic():
                    one(
                        "INSERT INTO public.profile_articles(system_id,org_id,sku,name,role,face_width_mm) "
                        "VALUES(%s,%s,'TENANT-FRAME','Tenant frame','FRAME',60.00) RETURNING id",
                        [system, org],
                    )
            # A tenant may still extend a global system with a role it lacks.
            created = one(
                "INSERT INTO public.profile_articles(system_id,org_id,sku,name,role,face_width_mm) "
                "VALUES(%s,%s,'TENANT-COUPLER','Tenant coupler','COUPLER',60.00) RETURNING id",
                [system, org],
            )
            assert created["id"]
    finally:
        # Global catalog rows are visible to every tenant; remove the fixture so
        # later gates keep their canonical global counts.
        one("DELETE FROM public.profile_systems WHERE id=%s RETURNING id", [system])
