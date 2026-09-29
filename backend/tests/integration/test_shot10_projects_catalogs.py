"""Real PostgreSQL proof for manual projects and catalog permissions."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from django.db import DatabaseError, transaction

from authentication.errors import ContractAPIException
from backend.tests.integration.test_shot09_documentary import (
    documentary_tenant as documentary_tenant,
    as_user,
    _seed_project,
    _freeze,
)
from dekopen_engine.snapshot import canonical_json, calculation_response
from documents.repository import documentary_backend
from engine_api.adapter import calculate_from_api
from engine_api.repository import SystemParamsRepository
from pricing.repository import one, rows
from projects import service
from projects.serializers import PositionWriteSerializer

pytestmark = pytest.mark.rls_integration


@contextmanager
def rejected(status, code):
    with pytest.raises(ContractAPIException) as caught:
        yield
    assert caught.value.status_code == status
    assert caught.value.contract_code == code


def position_data(system_id, width="1000.00"):
    serializer = PositionWriteSerializer(
        data={
            "location_tag": "Cocina",
            "quantity": 2,
            "design": {
                "system_id": str(system_id),
                "nominal_width_mm": width,
                "nominal_height_mm": "1000.00",
                "color": "WHITE",
                "parametric_tree": {
                    "id": "B1",
                    "type": "BAY",
                    "opening_type": "FIXED",
                    "glass_spec": "4-12-4 Float Incoloro",
                    "glass_thickness_mm": "24.00",
                    "glass_article_sku": "VIDRIO-BASE",
                },
            },
        }
    )
    assert serializer.is_valid(), serializer.errors
    return serializer.validated_data


@pytest.fixture
def manual_pair(documentary_tenant):
    org, other, users, other_user = documentary_tenant
    system = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60' AND is_global")["id"]
    result = []
    for tenant, actor in ((org, users["OWNER"]), (other, other_user)):
        with as_user(actor):
            project = service.create_project(
                tenant,
                actor,
                {"name": "Casa", "client_name": "Cliente"},
            )
            position = service.save_position(
                tenant,
                project["id"],
                position_data(system),
            )
            result.append((tenant, actor, project["id"], position["id"]))
    return result, users, system


def test_tenants_cannot_read_or_update_each_other(manual_pair):
    pair, _, _ = manual_pair
    for own, foreign in ((pair[0], pair[1]), (pair[1], pair[0])):
        org, actor, project_id, position_id = own
        foreign_org, _, foreign_project, foreign_position = foreign
        with as_user(actor):
            assert {p["id"] for p in service.list_projects(org)} == {project_id}
            assert service.position_row(org, position_id)["id"] == position_id

            # Both explicit active-org filtering and PostgreSQL RLS.
            for supplied_org in (org, foreign_org):
                with rejected(404, "project_not_found"):
                    service.project_row(supplied_org, foreign_project)
                with rejected(404, "project_not_found"):
                    service.position_row(supplied_org, foreign_position)
                with rejected(404, "project_not_found"):
                    service.update_project(supplied_org, foreign_project, {})

            for table, identity in (
                ("projects", foreign_project),
                ("project_positions", foreign_position),
            ):
                assert (
                    rows(
                        f"SELECT id FROM public.{table} WHERE id=%s",
                        [identity],
                    )
                    == []
                )
                assert (
                    rows(
                        f"UPDATE public.{table} SET updated_at=clock_timestamp() "
                        "WHERE id=%s RETURNING id",
                        [identity],
                    )
                    == []
                )


def test_save_update_reopen_matches_engine_exactly(manual_pair):
    pair, users, system = manual_pair
    org, _, project_id, position_id = pair[0]

    with as_user(users["ESTIMATOR"]):
        before = service.position_row(org, position_id)
        data = position_data(system, "1200.00")
        data["expected_updated_at"] = before["updated_at"]
        design = data["design"]
        result = calculate_from_api(
            params=SystemParamsRepository().load_visible(system, org),
            **{
                key: design[key]
                for key in (
                    "parametric_tree",
                    "nominal_width_mm",
                    "nominal_height_mm",
                    "color",
                )
            },
        )
        expected = calculation_response(
            {**design, "system_id": str(system)},
            result,
        )
        saved = service.save_position(
            org,
            project_id,
            data,
            position_id=position_id,
        )
        assert saved["bom"] == expected

        # A second request with the old timestamp must not overwrite the save.
        with rejected(409, "stale_edit"):
            service.save_position(
                org,
                project_id,
                data,
                position_id=position_id,
            )

        project = service.project_row(org, project_id)
        changed = service.update_project(
            org,
            project_id,
            {
                "name": "Casa actualizada",
                "expected_updated_at": project["updated_at"],
            },
        )
        assert changed["name"] == "Casa actualizada"

    # Reopen under a fresh authenticated context, reading actual stored JSONB.
    with as_user(users["OWNER"]):
        reopened = service.position_public(
            service.position_row(org, position_id),
        )
        persisted = one(
            "SELECT parametric_tree::text AS tree, bom_snapshot::text AS bom "
            "FROM public.project_positions WHERE id=%s AND org_id=%s",
            [position_id, org],
        )
        from pricing.service import decoded

        assert reopened["design"]["parametric_tree"] == design["parametric_tree"]
        assert reopened["design"]["nominal_width_mm"] == "1200.00"
        assert reopened["design"]["nominal_height_mm"] == "1000.00"
        assert reopened["design"]["system_id"] == system
        assert reopened["design"]["color"] == "WHITE"
        assert decoded(persisted["tree"]) == design["parametric_tree"]
        assert canonical_json(decoded(persisted["bom"])) == canonical_json(expected)
        assert reopened == saved


def assert_no_costs(value):
    forbidden = {
        "cost_net",
        "total_cost_net",
        "unit_cost",
        "cost_lines",
        "applied_total_cost_net",
        "input_snapshot",
    }
    if isinstance(value, dict):
        assert not forbidden.intersection(value)
        for child in value.values():
            assert_no_costs(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_costs(child)


def test_cloned_draft_has_independent_inputs_and_no_shared_history(manual_pair):
    pair, users, system = manual_pair
    org, actor, project_id, position_id = pair[0]
    with as_user(actor):
        original = service.project_public(org, service.project_row(org, project_id), detail=True)
        copied = service.clone_draft(
            org,
            actor,
            project_id,
            {
                "expected_updated_at": original["updated_at"],
            },
        )
        assert copied["id"] != original["id"]
        assert copied["status"] == "DRAFT"
        assert copied["pricing_current"] is False
        assert copied["total_price_gross"] == "0.00"
        assert copied["current_revision"] == "REV-A"
        assert copied["client_name"] == original["client_name"]
        assert len(copied["positions"]) == 1
        clone_position = copied["positions"][0]
        assert clone_position["id"] != position_id
        assert clone_position["project_id"] == copied["id"]
        assert clone_position["design"] == original["positions"][0]["design"]
        assert clone_position["bom"] == original["positions"][0]["bom"]
        changed = position_data(system, "1500.00")
        changed["expected_updated_at"] = clone_position["updated_at"]
        service.save_position(org, copied["id"], changed, position_id=clone_position["id"])
        assert (
            service.project_public(org, service.project_row(org, project_id), detail=True)
            == original
        )
        assert (
            rows("SELECT id FROM public.project_versions WHERE project_id=%s", [copied["id"]]) == []
        )
        with documentary_backend():
            assert rows("SELECT id FROM public.orders WHERE project_id=%s", [copied["id"]]) == []


def test_estimator_cost_columns_denied_and_response_omits_costs(documentary_tenant):
    org, _, users, _ = documentary_tenant
    project_id, _, _ = _seed_project(org, users["OWNER"])

    with as_user(users["ESTIMATOR"]):
        detail = service.project_public(
            org,
            service.project_row(org, project_id),
            detail=True,
        )
        assert detail["pricing_current"] is True
        assert detail["positions"]
        assert_no_costs(detail)

        for query in (
            "SELECT total_cost_net FROM public.projects WHERE id=%s",
            "SELECT cost_net FROM public.project_positions WHERE project_id=%s",
        ):
            with pytest.raises(DatabaseError) as caught:
                with transaction.atomic():
                    rows(query, [project_id])
            assert caught.value.__cause__.sqlstate == "42501"


@pytest.mark.parametrize("mutation", ["design", "cost"])
def test_reopen_rejects_stale_hash_or_injected_cost(manual_pair, mutation):
    pair, _, _ = manual_pair
    org, actor, _, position_id = pair[0]
    with as_user(actor):
        if mutation == "design":
            rows(
                "UPDATE public.project_positions SET width_mm=1100.00 WHERE id=%s RETURNING id",
                [position_id],
            )
        else:
            rows(
                "UPDATE public.project_positions SET bom_snapshot="
                'bom_snapshot || \'{"total_cost_net":"987654"}\'::jsonb '
                "WHERE id=%s RETURNING id",
                [position_id],
            )
        with rejected(409, "stored_calculation_invalid"):
            service.position_public(service.position_row(org, position_id))


@pytest.mark.parametrize("role", ["ESTIMATOR", "INSTALLER"])
def test_catalog_write_denied_in_postgresql(documentary_tenant, role):
    org, other, users, _ = documentary_tenant
    catalog_id = uuid4()

    # Copy a complete technical seed only to construct this test's catalog row.
    # CAT-01: member roles no longer hold any INSERT privilege on catalog
    # tables, so the fixture row is created as the connection owner.
    rows(
        "INSERT INTO public.profile_systems "
        "SELECT (jsonb_populate_record(NULL::public.profile_systems, "
        "to_jsonb(s) || jsonb_build_object("
        "'id',%s::text,'org_id',%s::text,'code',%s::text,"
        "'is_global',false,'is_demo',false,'technical_locked',false))).* "
        "FROM public.profile_systems s WHERE code='DEMO_60' AND is_global "
        "RETURNING id",
        [str(catalog_id), str(org), f"TEST-{catalog_id.hex}"],
    )

    with as_user(users[role]):
        assert rows(
            "SELECT id FROM public.profile_systems WHERE id=%s",
            [catalog_id],
        ) == [{"id": catalog_id}]
        assert (
            rows(
                "UPDATE public.profile_systems SET name='Unauthorized' WHERE id=%s RETURNING id",
                [catalog_id],
            )
            == []
        )
        assert (
            rows(
                "DELETE FROM public.profile_systems WHERE id=%s RETURNING id",
                [catalog_id],
            )
            == []
        )

    # Positive control: the policy actually permits its authorized actor.
    with as_user(users["WORKSHOP_MANAGER"]):
        assert rows(
            "UPDATE public.profile_systems SET name='Authorized' WHERE id=%s RETURNING id",
            [catalog_id],
        ) == [{"id": catalog_id}]

    with as_user(users["OWNER"]):
        with pytest.raises(DatabaseError) as caught:
            with transaction.atomic():
                rows(
                    "UPDATE public.profile_systems SET org_id=%s WHERE id=%s RETURNING id",
                    [other, catalog_id],
                )
        assert caught.value.__cause__.sqlstate in {"23514", "42501"}
        assert one(
            "SELECT name,org_id FROM public.profile_systems WHERE id=%s",
            [catalog_id],
        ) == {"name": "Authorized", "org_id": org}


def test_frozen_project_rejects_edits_and_preserves_evidence(documentary_tenant):
    org, _, users, _ = documentary_tenant
    actor = users["OWNER"]
    project_id, position_id, operation_id = _seed_project(org, actor)
    frozen = _freeze(org, actor, project_id, operation_id)

    with as_user(actor):
        project = service.project_row(org, project_id)
        position = service.position_row(org, position_id)
        data = position_data(position["system_id"])
        data["expected_updated_at"] = position["updated_at"]

        with documentary_backend():
            evidence = one(
                "SELECT snapshot_json::text AS snapshot,bom_hash,snapshot_sha256 "
                "FROM public.project_versions WHERE id=%s",
                [frozen["id"]],
            )

        with rejected(409, "revision_required"):
            service.update_project(
                org,
                project_id,
                {
                    "name": "Forbidden",
                    "expected_updated_at": project["updated_at"],
                },
            )
        with rejected(409, "revision_required"):
            service.save_position(org, project_id, data, position_id=position_id)
        with rejected(409, "revision_required"):
            service.delete_position(org, position_id, position["updated_at"])

        for query, identity in (
            ("UPDATE public.projects SET name='Forbidden' WHERE id=%s RETURNING id", project_id),
            (
                "UPDATE public.project_positions SET width_mm=1100 WHERE id=%s RETURNING id",
                position_id,
            ),
            (
                "UPDATE public.project_versions SET snapshot_json='{}' WHERE id=%s RETURNING id",
                frozen["id"],
            ),
        ):
            with pytest.raises(DatabaseError) as caught:
                with transaction.atomic():
                    rows(query, [identity])
            assert caught.value.__cause__.sqlstate == "42501"

        assert service.project_row(org, project_id) == project
        assert service.position_row(org, position_id) == position
        with documentary_backend():
            assert (
                one(
                    "SELECT snapshot_json::text AS snapshot,bom_hash,snapshot_sha256 "
                    "FROM public.project_versions WHERE id=%s",
                    [frozen["id"]],
                )
                == evidence
            )


def test_project_creator_cannot_be_forged(documentary_tenant):
    org, _, users, _ = documentary_tenant
    with as_user(users["ESTIMATOR"]):
        with pytest.raises(DatabaseError) as caught:
            with transaction.atomic():
                rows(
                    "INSERT INTO public.projects(org_id,code,name,client_name,created_by) "
                    "VALUES(%s,%s,'Casa','Cliente',%s) RETURNING id",
                    [org, f"FORGED-{uuid4().hex}", users["OWNER"]],
                )
        assert caught.value.__cause__.sqlstate == "42501"
        project = service.create_project(org, users["ESTIMATOR"], {
            "name": "Casa", "client_name": "Cliente",
        })
        assert one("SELECT created_by FROM public.projects WHERE id=%s", [project["id"]])["created_by"] == users["ESTIMATOR"]
