"""product-v2 assembly positions through the documentary freeze (real PostgreSQL).

A bow must price, seal, and quote like any other position — per-module
inspector/manufacturing evidence, honest ``production_allowed=False`` until
per-position workshop inputs exist, and no workshop order without them.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.db import connection, transaction

from dekopen_engine.snapshot import calculation_response
from engine_api.adapter import evaluate_assembly_from_api, parse_product_model
from engine_api.repository import SystemParamsRepository
from pricing.repository import admin_write, commercial_backend, json_text, one
from pricing.service import apply_operation, preview

import documents.service as documents_service
from documents.repository import DocumentaryError, documentary_backend
from documents.renderers import _doc01, _doc03
from documents.service import revision_snapshot, save_documentary_inputs
from tests.integration.test_shot09_documentary import (
    _tenant,
    as_user,
)

pytestmark = pytest.mark.rls_integration
D = Decimal


@pytest.fixture
def documentary_tenant(django_db_blocker):
    with django_db_blocker.unblock():
        if connection.vendor != "postgresql":
            pytest.fail("assembly documentary tests require real PostgreSQL")
        with transaction.atomic():
            org, other = uuid4(), uuid4()
            users = {
                role: uuid4()
                for role in ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER")
            }
            other_user = uuid4()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO public.tenancy_organizations(id,name,tax_id) VALUES(%s,%s,%s),(%s,%s,%s)",
                    [org, "Documentary A", str(org), other, "Documentary B", str(other)],
                )
                for role, user_id in users.items():
                    cursor.execute(
                        "INSERT INTO public.tenancy_memberships(org_id,user_id,role) VALUES(%s,%s,%s)",
                        [org, user_id, role],
                    )
                cursor.execute(
                    "INSERT INTO public.tenancy_memberships(org_id,user_id,role) VALUES(%s,%s,'OWNER')",
                    [other, other_user],
                )
            yield org, other, users, other_user
            transaction.set_rollback(True)


def _bow_tree(
    coupler_sku: str = "COPLE-60", operable: bool = False
) -> dict[str, object]:
    def module(index: int) -> dict[str, object]:
        return {
            "id": f"m{index}",
            "width_mm": "700.00",
            "height_mm": "1400.00",
            "tree": {
                "id": "B1",
                "type": "BAY",
                "opening_type": "TURN_LEFT" if operable and index == 2 else "FIXED",
                "glass_spec": "4-12-4 Float Incoloro",
                "glass_thickness_mm": "24.00",
                "glass_article_sku": "GLASS-BASE",
            },
        }

    return {
        "version": "product-v2",
        "assembly": {
            "modules": [module(1), module(2), module(3)],
            "couplings": [
                {"id": "c1", "angle_deg": "15", "coupler_profile_sku": coupler_sku},
                {"id": "c2", "angle_deg": "15", "coupler_profile_sku": coupler_sku},
            ],
        },
    }


def _seed_bow_project(
    org: UUID,
    owner: UUID,
    *,
    workshop: dict[str, object] | None = None,
    operable: bool = False,
) -> tuple[UUID, UUID, UUID, dict[str, object]]:
    system_id = UUID(str(one(
        "SELECT id FROM public.profile_systems WHERE code='DEMO_60'"
    )["id"]))
    project_id = UUID(str(one(
        "INSERT INTO public.projects(org_id,code,name,client_name,client_rut,client_email,"
        "client_phone,delivery_address,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        [org, f"P-{uuid4().hex[:8]}", "Proyecto bow", "Cliente Bow", "1-9",
         "bow@example.test", "+56900000000", "Obra Sur", owner],
    )["id"]))
    tree = _bow_tree(operable=operable)
    with as_user(owner):
        params = SystemParamsRepository().load_visible(system_id, org)
        evaluation = evaluate_assembly_from_api(
            product=parse_product_model(tree),
            color="WHITE",
            params=params,
            coupler_articles=SystemParamsRepository().load_coupler_articles(system_id, org),
        )
    assert evaluation.status.value == "VALID" and evaluation.bom is not None
    design = {
        "system_id": str(system_id),
        "parametric_tree": tree,
        "nominal_width_mm": D("2100.00"),
        "nominal_height_mm": D("1400.00"),
        "color": "WHITE",
    }
    bom_response = calculation_response(design, evaluation.bom)
    position_id = UUID(str(one(
        "INSERT INTO public.project_positions(org_id,project_id,position_index,location_tag,quantity,"
        "typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot) "
        "VALUES(%s,%s,1,NULL,1,'BOW',%s,2100.00,1400.00,%s::jsonb,%s::jsonb) RETURNING id",
        [org, project_id, system_id, json_text(tree), json_text(bom_response)],
    )["id"]))
    with as_user(owner):
        cost_list = admin_write(
            "cost-lists", org,
            {"supplier_name": "Fixture", "currency": "CLP", "valid_from": date(2026, 9, 1)},
            "assembly fixture list",
        )
        for sku, unit in (
            ("DEMO-BAR-MARCO", "BAR"),
            ("DEMO-BAR-JQ-10", "BAR"),
            ("DEMO-BAR-JQ-24", "BAR"),
            ("DEMO-STEEL-BAR-MARCO", "BAR"),
            ("DEMO-BAR-COPLE-60", "BAR"),
            ("DEMO-BAR-HOJA", "BAR"),
            ("DEMO-STEEL-BAR-HOJA", "BAR"),
            ("KIT-TURN", "KIT"),
            ("GLASS-BASE", "M2"),
        ):
            admin_write(
                "cost-items", org,
                {"cost_list_id": cost_list["id"], "sku": sku, "item_type": "FIXTURE",
                 "unit": unit, "unit_cost": D("100.0000")},
                "assembly fixture item",
            )
        admin_write(
            "rules", org,
            {"pricing_mode": "COST_PLUS_MARGIN", "default_margin_pct": D("0.3500"),
             "tax_rate_pct": D("0.1900"), "waste_factor_pct": D("0.0800"),
             "labor_rate_per_m2": D("15.00"), "installation_rate_per_m2": D("12.00")},
            "assembly fixture rules",
        )
        with commercial_backend():
            operation = preview(org, _tenant(org, "OWNER"), {
                "project_id": project_id,
                "pricing_mode": "COST_PLUS_MARGIN",
                "currency": "CLP",
                "effective_date": date(2026, 9, 10),
                "context_code": "DEFAULT",
                "discount_pct": D("0"),
                "target_margin": D("0.35"),
                "segment": "RETAIL",
                "confirmed": False,
                "reason": "assembly preview",
                "_actor_id": owner,
            })
            apply_operation(
                org, owner, "OWNER", UUID(operation["id"]),
                "assembly apply", False,
            )
    operation_id = UUID(operation["id"])
    with as_user(owner), documentary_backend():
        policies = one(
            "SELECT placement.id AS placement_id,handles.id AS handle_id,steel.id AS steel_id "
            "FROM public.profile_systems system "
            "JOIN public.manufacturing_placement_policies placement ON placement.system_id=system.id "
            "JOIN public.handle_requirement_policies handles ON handles.system_id=system.id "
            "JOIN public.reinforcement_cut_policies steel ON steel.system_id=system.id "
            "WHERE system.id=%s AND placement.org_id IS NULL AND handles.org_id IS NULL "
            "AND steel.org_id IS NULL "
            "AND handles.version=(SELECT max(h2.version) FROM public.handle_requirement_policies h2 "
            "WHERE h2.system_id=handles.system_id AND h2.org_id IS NULL) ",
            [system_id],
        )
        save_documentary_inputs(
            org_id=org,
            actor_id=owner,
            project_id=project_id,
            data={
                "payment_terms": "Contado",
                "quotation_valid_until": date(2026, 10, 14),
                "positions": [{
                    "position_id": position_id,
                    "calculation_hash": bom_response["calculation_hash"],
                    "location_tag": "BOW-SUR",
                    "manufacturing_placement_policy_id": policies["placement_id"],
                    "handle_requirement_policy_id": policies["handle_id"],
                    "reinforcement_cut_policy_id": policies["steel_id"],
                    "workshop_annotations": [] if workshop is None else [workshop],
                    "structural_inputs": [],
                    "glass_polishing": [],
                    "handle_intents": [],
                    "accessory_schedule": None,
                    "legacy_handle_migration_confirmed": False,
                }],
            },
        )
    return project_id, position_id, operation_id, tree


def _freeze(org: UUID, owner: UUID, project_id: UUID, operation_id: UUID, *, incomplete: bool):
    with as_user(owner):
        return documents_service.freeze_revision_a(
            org_id=org, actor_id=owner, project_id=project_id,
            pricing_operation_id=operation_id, confirmed=True,
            allow_incomplete_workshop=incomplete,
        )


def _policies(org: UUID) -> dict[str, object]:
    system_id = UUID(str(one(
        "SELECT id FROM public.profile_systems WHERE code='DEMO_60'"
    )["id"]))
    return one(
        "SELECT placement.id AS placement_id,handles.id AS handle_id,steel.id AS steel_id "
        "FROM public.profile_systems system "
        "JOIN public.manufacturing_placement_policies placement ON placement.system_id=system.id "
        "JOIN public.handle_requirement_policies handles ON handles.system_id=system.id "
        "JOIN public.reinforcement_cut_policies steel ON steel.system_id=system.id "
        "WHERE system.id=%s AND placement.org_id IS NULL AND handles.org_id IS NULL "
        "AND steel.org_id IS NULL "
            "AND handles.version=(SELECT max(h2.version) FROM public.handle_requirement_policies h2 "
            "WHERE h2.system_id=handles.system_id AND h2.org_id IS NULL) ",
        [system_id],
    )


def test_assembly_position_prices_and_freezes_quote_only(documentary_tenant) -> None:
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, position_id, operation_id, _ = _seed_bow_project(org, owner)

    # Strict freeze refuses honestly incomplete production data.
    with pytest.raises(DocumentaryError, match="inspector_red_blocks_documentary_freeze"):
        _freeze(org, owner, project_id, operation_id, incomplete=False)

    sealed = _freeze(org, owner, project_id, operation_id, incomplete=True)
    version_id = UUID(str(sealed["id"]))

    with as_user(owner):
        _, snapshot = revision_snapshot(version_id, org)
    assert snapshot["production_allowed"] is False
    assert snapshot["documentary_complete"] is False
    evidence = [
        item
        for item in snapshot["inspector"]
        if item["position_id"] == str(position_id)
    ]
    assert {item["module_id"] for item in evidence} == {"m1", "m2", "m3"}
    manufacturing = [
        item
        for item in snapshot["manufacturing"]
        if item.get("module_id") is not None
    ]
    assert {item["module_id"] for item in manufacturing} == {"m1", "m2", "m3"}

    # Modules share an identical local tree, so manufacturing identities must be
    # namespaced per module: every physical member is a distinct frozen part.
    member_ids = [
        member["member_id"]
        for unit in snapshot["manufacturing"]
        for member in unit["members"]
    ]
    assert len(member_ids) == len(set(member_ids))

    # The commercial quote renders; the workshop order stays honestly blocked.
    html = _doc01(snapshot)
    assert "<svg" in html and "m1" in html and "15°" in html
    with pytest.raises(DocumentaryError, match="production_document_blocked"):
        _doc03(snapshot)


def test_assembly_freeze_tolerates_unsaved_handle_intents(documentary_tenant) -> None:
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, position_id, operation_id, _ = _seed_bow_project(
        org, owner, operable=True
    )

    # m2 is an operable leaf with no saved handle intent: the quote-only
    # freeze seals incomplete instead of blocking the commercial quote on
    # manufacturing projection.
    sealed = _freeze(org, owner, project_id, operation_id, incomplete=True)
    version_id = UUID(str(sealed["id"]))
    with as_user(owner):
        _, snapshot = revision_snapshot(version_id, org)
    assert snapshot["documentary_complete"] is False
    assert snapshot["production_allowed"] is False
    projected = {item["module_id"] for item in snapshot["manufacturing"]}
    assert projected == {"m1", "m3"}
    evidence = {
        item["module_id"]
        for item in snapshot["inspector"]
        if item["position_id"] == str(position_id)
    }
    assert evidence == {"m1", "m2", "m3"}
    html = _doc01(snapshot)
    assert "<svg" in html


def test_save_documentary_inputs_validates_namespaced_targets(documentary_tenant) -> None:
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    system_id = UUID(str(one(
        "SELECT id FROM public.profile_systems WHERE code='DEMO_60'"
    )["id"]))
    tree = _bow_tree()
    project_id = UUID(str(one(
        "INSERT INTO public.projects(org_id,code,name,client_name,client_rut,client_email,"
        "client_phone,delivery_address,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        [org, f"P-{uuid4().hex[:8]}", "Bow inputs", "Cliente Demo", "1-9",
         "cliente@example.test", "+56900000000", "Obra Norte", owner],
    )["id"]))
    with as_user(owner):
        params = SystemParamsRepository().load_visible(system_id, org)
        evaluation = evaluate_assembly_from_api(
            product=parse_product_model(tree),
            color="WHITE",
            params=params,
            coupler_articles=SystemParamsRepository().load_coupler_articles(system_id, org),
        )
        design = {
            "parametric_tree": tree,
            "nominal_width_mm": D("2100.00"),
            "nominal_height_mm": D("1400.00"),
            "color": "WHITE",
            "system_id": str(system_id),
        }
        bom_response = calculation_response(design, evaluation.bom)
        position_id = UUID(str(one(
            "INSERT INTO public.project_positions(org_id,project_id,position_index,quantity,"
            "typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot) "
            "VALUES(%s,%s,1,1,'BOW',%s,2100.00,1400.00,%s::jsonb,%s::jsonb) RETURNING id",
            [org, project_id, system_id, json_text(tree), json_text(bom_response)],
        )["id"]))
    policies = _policies(org)
    with as_user(owner), documentary_backend():
        bad = {
            "position_id": position_id,
            "calculation_hash": "",
            "location_tag": "",
            "manufacturing_placement_policy_id": policies["placement_id"],
            "handle_requirement_policy_id": policies["handle_id"],
            "reinforcement_cut_policy_id": policies["steel_id"],
            "workshop_annotations": [{"bay_id": "m9|m9", "leaf_id": None}],
            "structural_inputs": [],
            "glass_polishing": [],
            "handle_intents": [],
            "accessory_schedule": None,
            "legacy_handle_migration_confirmed": False,
        }
        with pytest.raises(DocumentaryError, match="workshop_annotation_target_invalid"):
            save_documentary_inputs(
                org_id=org, actor_id=owner, project_id=project_id,
                data={
                    "payment_terms": "",
                    "quotation_valid_until": date(2026, 10, 14),
                    "positions": [bad],
                },
            )
        bad["workshop_annotations"] = []
        bad["handle_intents"] = [{"bay_id": "m1|B1", "leaf_id": None}]
        with pytest.raises(DocumentaryError, match="handle_intent_target_invalid"):
            save_documentary_inputs(
                org_id=org, actor_id=owner, project_id=project_id,
                data={
                    "payment_terms": "",
                    "quotation_valid_until": date(2026, 10, 14),
                    "positions": [bad],
                },
            )
