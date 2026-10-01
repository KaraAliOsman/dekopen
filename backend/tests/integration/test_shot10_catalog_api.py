from contextlib import contextmanager
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
import pytest
from rest_framework.test import APIClient

from authentication.rls import authenticated_rls_context
from backend.tests.integration.test_rls_context_integration import (
    real_rows as real_rows,
)

pytestmark = pytest.mark.rls_integration


@pytest.fixture(autouse=True)
def database_access(django_db_blocker):
    with django_db_blocker.unblock():
        with transaction.atomic():
            yield
            transaction.set_rollback(True)


def set_role(rows, role, *, active=True, user="A", org="A"):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE public.tenancy_memberships "
            "SET role=%s, is_active=%s WHERE user_id=%s AND org_id=%s",
            [role, active, rows.tokens[user].user_id, rows.organizations[org]],
        )


def client_for(rows, user="A", org="A"):
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {rows.tokens[user].access_token}",
        HTTP_X_ORGANIZATION_ID=str(rows.organizations[org]),
    )
    return client


@contextmanager
def rejected_sql():
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            yield


@pytest.mark.parametrize("role", ["WORKSHOP_MANAGER", "INSTALLER"])
def test_successor_roles_are_denied_before_project_lookup(real_rows, role):
    set_role(real_rows, role)
    response = client_for(real_rows).post(
        f"/api/v1/projects/{uuid4()}/successor/",
        {"confirmed": True},
        format="json",
    )
    assert response.status_code == 403
    assert response.data["error"]["code"] == "pricing_permission_denied"


def test_manager_crud_and_exact_contents(real_rows):
    set_role(real_rows, "WORKSHOP_MANAGER")
    client = client_for(real_rows)
    root = "/api/v1/catalogs"

    system_payload = {
        "name": "Manual fixture",
        "code": "MANUAL-TEST",
        "depth_mm": "60.00",
        "material": "PVC",
        "chamber_count": 3,
        "rail_type": "dual",
        "version": 1,
        "is_active": False,
    }
    for name in (
        "sash_overlap_mm",
        "glass_clearance_white_mm",
        "glass_clearance_foil_mm",
        "pulley_height_mm",
        "central_overlap_mm",
        "sliding_lateral_clearance_mm",
        "sliding_end_add_mm",
        "corner_bracket_loss_mm",
        "hook_depth_mm",
        "door_threshold_mm",
        "door_bottom_clearance_mm",
        "sliding_glazing_deduction_width_mm",
        "sliding_glazing_deduction_height_mm",
        "door_leaf_side_clearance_mm",
    ):
        system_payload[name] = "1.00"

    response = client.post(f"{root}/systems/", system_payload, format="json")
    assert response.status_code == 201, response.data
    system_id = response.data["id"]

    article_payload = {
        "system_id": system_id,
        "sku": "BEAD",
        "name": "Test bead",
        "role": "GLAZING_BEAD",
        "material": "PVC",
        "face_width_mm": "20.00",
        "commercial_length_mm": "6000.00",
        "welding_loss_mm": "0.00",
        "reinforcement_gap_mm": "0.00",
        "weight_kg_m": "1.0001",
        "steel_weight_kg_m": "0.0000",
    }
    response = client.post(f"{root}/articles/", article_payload, format="json")
    assert response.status_code == 201, response.data
    article_id = response.data["id"]

    response = client.post(
        f"{root}/glazing/",
        {
            "system_id": system_id,
            "bead_article_id": article_id,
            "glass_thickness_mm": "24.00",
            "bead_width_mm": "20.00",
            "gasket_interior_mm": "3.00",
            "gasket_exterior_mm": "3.00",
            "cut_add_mm": "9.00",
            "is_active": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    bead_id = response.data["id"]

    kit_payload = {
        "system_id": system_id,
        "sku": "KIT",
        "name": "Test kit",
        "opening_type": "AWNING",
        "min_leaf_width_mm": "100.00",
        "max_leaf_width_mm": "1000.00",
        "min_leaf_height_mm": "100.00",
        "max_leaf_height_mm": "1000.00",
        "max_leaf_weight_kg": "50.00",
        "rail_type": "dual",
        "carriages_qty": 0,
        "stay_arms_qty": 2,
        "contents": [
            {
                "sku": "PART",
                "name": "Part",
                "qty": "1.00000000000000000001",
                "unit": "unit",
            }
        ],
        "is_active": True,
    }
    response = client.post(f"{root}/hardware-kits/", kit_payload, format="json")
    assert response.status_code == 201, response.data
    kit_id = response.data["id"]
    assert response.data["contents"][0]["qty"] == "1.00000000000000000001"

    for resource, row_id, change in (
        ("systems", system_id, {"name": "Edited system"}),
        ("articles", article_id, {"face_width_mm": "20.01"}),
        ("glazing", bead_id, {"cut_add_mm": "9.01"}),
        ("hardware-kits", kit_id, {"name": "Edited kit"}),
    ):
        path = f"{root}/{resource}/{row_id}/"
        current = client.get(path)
        assert current.status_code == 200, current.data
        response = client.patch(
            path,
            change,
            format="json",
            HTTP_IF_MATCH=f'"{current.data["revision"]}"',
        )
        assert response.status_code == 200, response.data
        reopened = client.get(path)
        assert reopened.status_code == 200
        for key, value in change.items():
            assert reopened.data[key] == value
        stale = client.patch(path, change, format="json", HTTP_IF_MATCH=f'"{current.data["revision"]}"')
        assert stale.status_code == 409
        assert client.get(path).data == reopened.data

    # The existing bead FK prevents removing its referenced article.
    article_path = f"{root}/articles/{article_id}/"
    bead_path = f"{root}/glazing/{bead_id}/"
    kit_path = f"{root}/hardware-kits/{kit_id}/"
    system_path = f"{root}/systems/{system_id}/"
    article_revision = client.get(article_path).data["revision"]
    assert client.delete(
        article_path, HTTP_IF_MATCH=f'"{article_revision}"',
    ).status_code == 409
    bead_revision = client.get(bead_path).data["revision"]
    assert client.delete(
        bead_path, HTTP_IF_MATCH=f'"{bead_revision}"',
    ).status_code == 204
    article_revision = client.get(article_path).data["revision"]
    assert client.delete(
        article_path, HTTP_IF_MATCH=f'"{article_revision}"',
    ).status_code == 204
    kit_revision = client.get(kit_path).data["revision"]
    assert client.delete(
        kit_path, HTTP_IF_MATCH=f'"{kit_revision}"',
    ).status_code == 204
    system_revision = client.get(system_path).data["revision"]
    assert client.delete(
        system_path, HTTP_IF_MATCH=f'"{system_revision}"',
    ).status_code == 204


@pytest.mark.parametrize("role", ["ESTIMATOR", "INSTALLER", "OWNER"])
@pytest.mark.parametrize("resource", ["systems", "articles", "glazing", "hardware-kits"])
def test_management_roles_and_owner_aal1_denied(real_rows, role, resource):
    set_role(real_rows, role)
    client = client_for(real_rows)
    # Estimators read the catalog to quote; management is still denied to
    # them, and non-reader roles are denied entirely.
    expected = 200 if role == "ESTIMATOR" else 403
    assert client.get(f"/api/v1/catalogs/{resource}/").status_code == expected
    assert client.post(f"/api/v1/catalogs/{resource}/", {}).status_code == 403


@pytest.mark.parametrize("role", ["ESTIMATOR", "INSTALLER", "OWNER"])
@pytest.mark.parametrize(
    "table",
    [
        "profile_systems",
        "profile_articles",
        "glazing_bead_matrix",
        "hardware_kits",
    ],
)
def test_direct_mutation_denied_for_non_manager_roles(real_rows, role, table):
    set_role(real_rows, role)
    org_id = real_rows.organizations["A"]
    system_id = real_rows.systems["A"]

    # Privileged setup; protected operations below use authenticated RLS.
    with connection.cursor() as cursor:
        if table == "profile_systems":
            row_id = system_id
        elif table == "profile_articles":
            cursor.execute(
                "SELECT id FROM public.profile_articles WHERE system_id=%s LIMIT 1",
                [system_id],
            )
            row_id = cursor.fetchone()[0]
        elif table == "hardware_kits":
            cursor.execute(
                "INSERT INTO public.hardware_kits "
                "(org_id,system_id,sku,name,opening_type,min_leaf_width_mm,"
                "max_leaf_width_mm,min_leaf_height_mm,max_leaf_height_mm,"
                "max_leaf_weight_kg) "
                "VALUES(%s,%s,'DIRECT','Direct','AWNING',1,2,1,2,3) RETURNING id",
                [org_id, system_id],
            )
            row_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                "INSERT INTO public.profile_articles "
                "(org_id,system_id,sku,name,role,face_width_mm) "
                "VALUES(%s,%s,'DIRECT-BEAD','Bead','GLAZING_BEAD',20) RETURNING id",
                [org_id, system_id],
            )
            article_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO public.glazing_bead_matrix "
                "(org_id,system_id,glass_thickness_mm,bead_article_id,"
                "bead_width_mm,cut_add_mm) "
                "VALUES(%s,%s,24,%s,20,9) RETURNING id",
                [org_id, system_id, article_id],
            )
            row_id = cursor.fetchone()[0]

    with authenticated_rls_context(real_rows.tokens["A"].claims):
        with connection.cursor() as cursor:
            # CAT-01: members hold only column-scoped write grants. Probe a
            # writable column so the policy layer does the denying (non-managers
            # silently affect zero rows); DELETE is likewise policy-filtered.
            writable = "glass_thickness_mm" if table == "glazing_bead_matrix" else "name"
            cursor.execute(
                f"UPDATE public.{table} SET {writable}={writable} WHERE id=%s", [row_id])
            assert cursor.rowcount == 0
            cursor.execute(f"DELETE FROM public.{table} WHERE id=%s", [row_id])
            assert cursor.rowcount == 0


@pytest.mark.parametrize(
    "table",
    [
        "profile_systems",
        "profile_articles",
        "glazing_bead_matrix",
        "hardware_kits",
    ],
)
def test_manager_cannot_mutate_global_rows_directly(real_rows, table):
    set_role(real_rows, "WORKSHOP_MANAGER")
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        with connection.cursor() as cursor:
            # Writable-column probe: the policy, not the privilege layer, keeps
            # global rows out of a manager's reach (CAT-01).
            writable = "glass_thickness_mm" if table == "glazing_bead_matrix" else "name"
            cursor.execute(
                f"UPDATE public.{table} SET {writable}={writable} WHERE org_id IS NULL")
            assert cursor.rowcount == 0
            cursor.execute(f"DELETE FROM public.{table} WHERE org_id IS NULL")
            assert cursor.rowcount == 0


def test_own_global_child_allowed_foreign_parent_denied(real_rows):
    set_role(real_rows, "WORKSHOP_MANAGER", user="both", org="A")
    set_role(real_rows, "WORKSHOP_MANAGER", user="both", org="B")

    org_a = real_rows.organizations["A"]
    # This permission test needs an unreferenced global catalog. DEMO may already
    # be reserved by persisted technical work from earlier integration scenarios.
    global_system = uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.profile_systems SELECT (jsonb_populate_record("
            "NULL::public.profile_systems,to_jsonb(source)||jsonb_build_object("
            "'id',%s::uuid,'code',%s::text,'technical_locked',false,'is_demo',false))).* "
            "FROM public.profile_systems source WHERE id=%s",
            [global_system, f"GLOBAL-{global_system.hex}", real_rows.demo_system],
        )
    with authenticated_rls_context(real_rows.tokens["both"].claims):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.profile_articles "
                "(org_id,system_id,sku,name,role,face_width_mm) "
                "VALUES(%s,%s,'TENANT-BEAD','Tenant bead','GLAZING_BEAD',20) "
                "RETURNING id",
                [org_a, global_system],
            )
            article_id = cursor.fetchone()[0]

        with rejected_sql():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO public.profile_articles "
                    "(org_id,system_id,sku,name,role,face_width_mm) "
                    "VALUES(%s,%s,'FOREIGN','Foreign','FRAME',60)",
                    [org_a, real_rows.systems["B"]],
                )

    # A global parent must not make A's child visible to B.
    with authenticated_rls_context(real_rows.tokens["B"].claims):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM public.profile_articles WHERE id=%s",
                [article_id],
            )
            assert cursor.fetchone() is None

    # Membership in both tenants must not bypass the API's active-org filter.
    client = client_for(real_rows, user="both", org="B")
    response = client.get(f"/api/v1/catalogs/articles/{article_id}/")
    assert response.status_code == 404


def test_direct_hardware_contents_reject_string_quantity(real_rows):
    set_role(real_rows, "WORKSHOP_MANAGER")
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        with rejected_sql():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO public.hardware_kits "
                    "(org_id,system_id,sku,name,opening_type,min_leaf_width_mm,"
                    "max_leaf_width_mm,min_leaf_height_mm,max_leaf_height_mm,"
                    "max_leaf_weight_kg,contents) "
                    "VALUES(%s,%s,'BAD','Bad','AWNING',1,2,1,2,3,%s::jsonb)",
                    [
                        real_rows.organizations["A"],
                        real_rows.systems["A"],
                        '[{"sku":"P","name":"Part","qty":"1.1","unit":"unit"}]',
                    ],
                )


def test_global_catalog_api_is_read_only_for_manager(real_rows):
    set_role(real_rows, "WORKSHOP_MANAGER")
    client = client_for(real_rows)
    path = f"/api/v1/catalogs/systems/{real_rows.demo_system}/"
    assert client.get(path).status_code == 200
    assert client.patch(path, {}, format="json").status_code == 403
    assert client.patch(path, {"name": "Changed"}, format="json").status_code == 403
    assert client.delete(path).status_code == 403
