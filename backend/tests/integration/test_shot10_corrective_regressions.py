"""Integration regression tests for SHOT-10 corrective issues."""

from datetime import date
import json
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from django.db import connection

from authentication.errors import ContractAPIException
from backend.tests.integration.test_shot09_documentary import (
    FakeStorage,
    _seed_project,
    _tenant,
    as_user,
    documentary_tenant as documentary_tenant,
)
from dekopen_engine.commercial import PricingError
from documents.artifacts import generate_artifact
from documents.repository import DocumentaryError, documentary_backend, one
from documents.service import (
    freeze_revision_a,
    prepare_documentary_inputs,
    save_documentary_inputs,
    revision_snapshot,
)
from pricing.repository import commercial_backend
from pricing.service import apply_operation, preview
from projects import service
from catalogs import service as catalog_service

pytestmark = pytest.mark.rls_integration
D = Decimal


def price_current(org, actor, role, project_id):
    with commercial_backend():
        operation = preview(
            org,
            _tenant(org, role),
            {
                "project_id": project_id,
                "pricing_mode": "COST_PLUS_MARGIN",
                "context_code": "DEFAULT",
                "currency": "CLP",
                "effective_date": date.today().isoformat(),
                "discount_pct": D("0.0000"),
                "target_margin": D("0.35"),
                "segment": "RETAIL",
                "reason": "Corrective test quote",
                "confirmed": False,
                "_actor_id": actor,
            },
        )
        apply_operation(
            org,
            actor,
            role,
            UUID(operation["id"]),
            "Commercial quote apply",
            False,
        )
    return UUID(operation["id"])


def test_missing_workshop_freeze_allows_doc01_blocks_doc03_doc05_doc06(
    documentary_tenant, monkeypatch: pytest.MonkeyPatch
):
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)

    # 1. Verify prepare_documentary_inputs does NOT invent authority (drains, polishing edges)
    raw_project_id, _, _ = _seed_project(org, owner, valid_annotations=False)
    with as_user(owner):
        with documentary_backend():
            one(
                "UPDATE public.position_documentary_inputs SET glass_polishing='[]'::jsonb WHERE project_id=%s RETURNING id",
                [raw_project_id],
            )
        prepared = prepare_documentary_inputs(org_id=org, project_id=raw_project_id)
        assert len(prepared["positions"]) == 1
        pos_inputs = prepared["positions"][0]
        # Absence must be preserved: no synthesized coordinates or false-edge dictionaries
        assert pos_inputs["workshop_annotations"] == []
        assert pos_inputs["glass_polishing"] == []
        assert pos_inputs["structural_inputs"] == []
        assert pos_inputs["handle_intents"] == []

    # 2. Freeze project with missing workshop annotations directly
    project_id, _, operation_id = _seed_project(org, owner, valid_annotations=False)

    with as_user(owner):
        # Without allow_incomplete_workshop, red inspector blocks freeze
        with pytest.raises(DocumentaryError, match="inspector_red_blocks"):
            freeze_revision_a(
                org_id=org,
                actor_id=owner,
                project_id=project_id,
                pricing_operation_id=operation_id,
                confirmed=True,
                allow_incomplete_workshop=False,
            )

        # With allow_incomplete_workshop=True, quotation freeze succeeds with production_allowed=False
        frozen = freeze_revision_a(
            org_id=org,
            actor_id=owner,
            project_id=project_id,
            pricing_operation_id=operation_id,
            confirmed=True,
            allow_incomplete_workshop=True,
        )
        assert frozen["production_allowed"] is False
        assert frozen["documentary_complete"] is False

        # DOC-01 (commercial quote) must succeed without monkeypatching
        doc01, created = generate_artifact(
            org_id=org,
            actor_id=owner,
            role="OWNER",
            project_version_id=UUID(frozen["id"]),
            order_id=None,
            document_type="DOC-01",
            file_format="PDF",
        )
        assert doc01["document_type"] == "DOC-01"

        # Production / workshop artifacts must fail closed
        for doc_type in ("DOC-03", "DOC-05", "DOC-06"):
            with pytest.raises(DocumentaryError) as exc_info:
                generate_artifact(
                    org_id=org,
                    actor_id=owner,
                    role="OWNER",
                    project_version_id=UUID(frozen["id"]),
                    order_id=None,
                    document_type=doc_type,
                    file_format="PDF",
                )
            assert str(exc_info.value) == "production_document_blocked"


def test_invalid_annotation_target_fails_closed(documentary_tenant):
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, position_id, _ = _seed_project(org, owner, valid_annotations=True)

    with as_user(owner), documentary_backend():
        policies = one(
            "SELECT placement.id AS placement_id, handles.id AS handle_id, steel.id AS steel_id "
            "FROM public.profile_systems system "
            "JOIN public.manufacturing_placement_policies placement ON placement.system_id=system.id "
            "JOIN public.handle_requirement_policies handles ON handles.system_id=system.id "
            "JOIN public.reinforcement_cut_policies steel ON steel.system_id=system.id "
            "WHERE placement.org_id IS NULL AND handles.org_id IS NULL AND steel.org_id IS NULL "
        "AND placement.version=(SELECT max(p2.version) FROM public.manufacturing_placement_policies p2 "
            "WHERE p2.system_id=placement.system_id AND p2.org_id IS NULL) "
            "AND steel.version=(SELECT max(s2.version) FROM public.reinforcement_cut_policies s2 "
            "WHERE s2.system_id=steel.system_id AND s2.org_id IS NULL) "
            "AND handles.version=(SELECT max(h2.version) FROM public.handle_requirement_policies h2 "
        "WHERE h2.system_id=handles.system_id AND h2.org_id IS NULL) LIMIT 1"
        )
        # Invalid bay_id "B99" that does not exist in single bay geometry
        with pytest.raises(DocumentaryError) as exc_info:
            save_documentary_inputs(
                org_id=org,
                actor_id=owner,
                project_id=project_id,
                data={
                    "payment_terms": "Contado",
                    "quotation_valid_until": date(2030, 12, 31),
                    "positions": [{
                        "position_id": position_id,
                        "manufacturing_placement_policy_id": policies["placement_id"],
                        "handle_requirement_policy_id": policies["handle_id"],
                        "reinforcement_cut_policy_id": policies["steel_id"],
                        "workshop_annotations": [{
                            "bay_id": "B99",
                            "leaf_id": None,
                            "bottom_drain_holes_mm": [D("100")],
                            "closing_points_perimeter_mm": None,
                            "continuous_width_mm": D("1000"),
                            "finish_class": "WHITE",
                            "has_coupler": False,
                        }],
                        "structural_inputs": [],
                        "glass_polishing": [],
                        "handle_intents": [],
                        "accessory_schedule": {"schema_version": 1, "coverage": "NONE_REQUIRED", "items": []},
                        "legacy_handle_migration_confirmed": False,
                    }],
                },
            )
        assert str(exc_info.value) == "workshop_annotation_target_invalid"


def test_successor_stale_replay_rejected_with_409(documentary_tenant):
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, _, op_a = _seed_project(org, owner, valid_annotations=True)

    with as_user(owner):
        # Freeze REV-A
        freeze_revision_a(
            org_id=org,
            actor_id=owner,
            project_id=project_id,
            pricing_operation_id=op_a,
            confirmed=True,
        )

        # Open REV-B with expected_current_revision="REV-A"
        succ_b = service.start_successor(org, project_id, expected_current_revision="REV-A")
        assert succ_b["successor_created"] is True
        assert succ_b["current_revision"] == "REV-B"
        assert succ_b["status"] == "DRAFT"

        # Idempotent retry with same expected_current_revision="REV-A" succeeds without re-creating
        retry_b = service.start_successor(org, project_id, expected_current_revision="REV-A")
        assert retry_b["successor_created"] is False
        assert retry_b["current_revision"] == "REV-B"

        # Freeze REV-B
        op_b = price_current(org, owner, "OWNER", project_id)
        freeze_revision_a(
            org_id=org,
            actor_id=owner,
            project_id=project_id,
            pricing_operation_id=op_b,
            confirmed=True,
        )

        # Now project is at REV-B (QUOTED). Replaying stale expected_current_revision="REV-A" must fail closed with 409
        with pytest.raises(ContractAPIException) as exc_info:
            service.start_successor(org, project_id, expected_current_revision="REV-A")
        assert exc_info.value.status_code == 409
        assert exc_info.value.contract_code == "successor_source_stale"


def test_partial_project_update_and_empty_delta(documentary_tenant):
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]

    with as_user(owner):
        project = service.create_project(org, owner, {"name": "Proyecto Para Patch"})
        project_id = project["id"]
        # Update only notes_commercial
        updated = service.update_project(
            org,
            project_id,
            {
                "expected_updated_at": project["updated_at"],
                "notes_commercial": "Condiciones especiales actualizadas",
            },
        )
        assert updated["notes_commercial"] == "Condiciones especiales actualizadas"
        assert updated["name"] == project["name"]

        # Update with only expected_updated_at (empty delta)
        fresh = service.project_row(org, project_id)
        noop = service.update_project(
            org,
            project_id,
            {"expected_updated_at": fresh["updated_at"]},
        )
        assert UUID(str(noop["id"])) == project_id


@pytest.mark.parametrize(
    "role",
    ["FRAME", "SASH", "MULLION_V", "MULLION_H", "INVERSOR", "ADDITIONAL", "THRESHOLD"],
)
def test_catalog_singleton_role_uniqueness(documentary_tenant, role):
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]

    with as_user(owner):
        # Create a private system
        system = catalog_service.create(
            catalog_service.SYSTEMS,
            org,
            {
                "name": "Sistema Singleton Test",
                "code": f"SYS-{uuid4().hex[:6].upper()}",
                "depth_mm": D("60.00"),
                "material": "PVC",
                "chamber_count": 3,
                "sash_overlap_mm": D("8.00"),
                "glass_clearance_white_mm": D("4.00"),
                "glass_clearance_foil_mm": D("4.00"),
                "pulley_height_mm": D("0.00"),
                "central_overlap_mm": D("0.00"),
                "sliding_lateral_clearance_mm": D("0.00"),
                "sliding_end_add_mm": D("0.00"),
                "corner_bracket_loss_mm": D("0.00"),
                "hook_depth_mm": D("0.00"),
                "door_threshold_mm": D("0.00"),
                "door_bottom_clearance_mm": D("0.00"),
                "rail_type": "dual",
                "sliding_glazing_deduction_width_mm": D("0.00"),
                "sliding_glazing_deduction_height_mm": D("0.00"),
                "door_leaf_side_clearance_mm": D("0.00"),
                "chamber_clearance_mm": None,
                "version": 1,
                "is_active": True,
            },
        )

        first = catalog_service.create(
            catalog_service.ARTICLES,
            org,
            {
                "system_id": system["id"],
                "sku": f"{role}-{uuid4().hex[:6].upper()}",
                "name": "Perfil Principal",
                "role": role,
                "material": "PVC",
                "face_width_mm": D("60.00"),
                "commercial_length_mm": D("6000.00"),
                "welding_loss_mm": D("6.00"),
                "reinforcement_sku": None,
                "reinforcement_gap_mm": D("15.00"),
                "weight_kg_m": D("1.2000"),
                "steel_weight_kg_m": D("0.0000"),
            },
        )
        assert first["role"] == role

        # Every non-bead role resolves to one effective article per system.
        with pytest.raises(ContractAPIException) as exc_info:
            catalog_service.create(
                catalog_service.ARTICLES,
                org,
                {
                    "system_id": system["id"],
                    "sku": f"{role}-2-{uuid4().hex[:6].upper()}",
                    "name": "Segundo Perfil",
                    "role": role,
                    "material": "PVC",
                    "face_width_mm": D("60.00"),
                    "commercial_length_mm": D("6000.00"),
                    "welding_loss_mm": D("6.00"),
                    "reinforcement_sku": None,
                    "reinforcement_gap_mm": D("15.00"),
                    "weight_kg_m": D("1.2000"),
                    "steel_weight_kg_m": D("0.0000"),
                },
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.contract_code == "catalog_write_conflict"


@pytest.mark.parametrize("missing", ["accessories", "polishing", "both"])
def test_absent_authority_is_never_synthesized(documentary_tenant, monkeypatch, missing):
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, _, operation_id = _seed_project(org, owner)
    monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)
    with as_user(owner), documentary_backend():
        if missing in ("accessories", "both"):
            one("UPDATE public.position_documentary_inputs SET accessory_schedule=NULL "
                "WHERE project_id=%s RETURNING id", [project_id])
        if missing in ("polishing", "both"):
            one("UPDATE public.position_documentary_inputs SET glass_polishing='[]' "
                "WHERE project_id=%s RETURNING id", [project_id])
        prepared = prepare_documentary_inputs(org_id=org, project_id=project_id)
        if missing in ("accessories", "both"):
            assert prepared["positions"][0]["accessory_schedule"] is None
        else:
            assert prepared["positions"][0]["accessory_schedule"]["coverage"] == "NONE_REQUIRED"
        with pytest.raises(DocumentaryError, match="purchase_authority_incomplete"):
            freeze_revision_a(org_id=org, actor_id=owner, project_id=project_id,
                              pricing_operation_id=operation_id, confirmed=True)
        frozen = freeze_revision_a(org_id=org, actor_id=owner, project_id=project_id,
                                  pricing_operation_id=operation_id, confirmed=True,
                                  allow_incomplete_workshop=True)
        assert not frozen["documentary_complete"] and not frozen["production_allowed"]
        _, snapshot = revision_snapshot(UUID(frozen["id"]), org)
        assert snapshot["purchase_requirements"] is None
        if missing in ("polishing", "both"):
            assert snapshot["positions"][0]["glass_polishing"] == []
        if missing in ("accessories", "both"):
            assert snapshot["positions"][0]["accessory_schedule"] is None
        with documentary_backend():
            assert one("SELECT count(*) AS n FROM public.purchase_projections "
                       "WHERE project_version_id=%s", [frozen["id"]])["n"] == 0
        artifact, _ = generate_artifact(org_id=org, actor_id=owner, role="OWNER",
            project_version_id=UUID(frozen["id"]), order_id=None,
            document_type="DOC-01", file_format="PDF")
        assert artifact["document_type"] == "DOC-01"
        for kind, fmt, order in (("DOC-02", "XLSX", uuid4()), ("DOC-04", "PDF", uuid4()),
                                 ("DOC-03", "PDF", None), ("DOC-05", "PDF", None)):
            with pytest.raises(DocumentaryError, match="production_document_blocked"):
                generate_artifact(org_id=org, actor_id=owner, role="OWNER",
                    project_version_id=UUID(frozen["id"]), order_id=order,
                    document_type=kind, file_format=fmt)


def test_same_bay_geometry_change_invalidates_documentary_authority(documentary_tenant):
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, position_id, operation_id = _seed_project(org, owner)
    with as_user(owner):
        freeze_revision_a(org_id=org, actor_id=owner, project_id=project_id,
                          pricing_operation_id=operation_id, confirmed=True)
        service.start_successor(org, project_id, expected_current_revision="REV-A")
        previous = prepare_documentary_inputs(org_id=org, project_id=project_id)
        current = service.position_public(service.position_row(org, position_id))
        design = dict(current["design"])
        design["nominal_width_mm"] = D("1500")
        design["nominal_height_mm"] = D(design["nominal_height_mm"])
        service.save_position(org, project_id, {
            "expected_updated_at": current["updated_at"], "location_tag": "FACHADA-NORTE",
            "quantity": current["quantity"], "design": design,
        }, position_id=position_id)
        prepared = prepare_documentary_inputs(org_id=org, project_id=project_id)
        evidence = prepared["positions"][0]
        assert evidence["calculation_hash"] != previous["positions"][0]["calculation_hash"]
        # WM3: a surviving bay keeps its recorded workshop annotations across a
        # re-prepare — the stale-identity guard below is what blocks saving the
        # old evidence against the new calculation.
        assert len(evidence["workshop_annotations"]) == 1
        assert evidence["workshop_annotations"][0]["bay_id"] == "B1"
        assert len(evidence["glass_polishing"]) == 1
        assert evidence["accessory_schedule"] is not None
        assert prepared["payment_terms"] == previous["payment_terms"]
        old_input = {key: value for key, value in previous["positions"][0].items()
                     if key not in ("system_name", "placement_options", "handle_options", "reinforcement_options")}
        with pytest.raises(DocumentaryError, match="documentary_calculation_identity_stale"):
            save_documentary_inputs(org_id=org, actor_id=owner, project_id=project_id,
                data={"payment_terms": previous["payment_terms"],
                      "quotation_valid_until": previous["quotation_valid_until"],
                      "positions": [old_input]})
        operation = price_current(org, owner, "OWNER", project_id)
        with pytest.raises(DocumentaryError, match="documentary_calculation_identity_stale"):
            freeze_revision_a(org_id=org, actor_id=owner, project_id=project_id,
                              pricing_operation_id=operation, confirmed=True,
                              allow_incomplete_workshop=True)


def test_catalog_mutation_after_applied_cannot_strand_project(documentary_tenant):
    from django.db import connection, DatabaseError, transaction
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, position_id, operation_id = _seed_project(org, owner)
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
    with pytest.raises(DatabaseError, match="catalog_authority_referenced"), transaction.atomic():
        one("UPDATE public.profile_articles SET welding_loss_mm=welding_loss_mm+1 "
            "WHERE system_id=(SELECT system_id FROM public.project_positions WHERE id=%s) "
            "AND role='FRAME' RETURNING id", [position_id])
    with as_user(owner):
        frozen = freeze_revision_a(org_id=org, actor_id=owner, project_id=project_id,
                                  pricing_operation_id=operation_id, confirmed=True)
        assert frozen["documentary_complete"]
        assert service.project_row(org, project_id)["status"] == "QUOTED"


def test_applied_draft_recovery_preserves_history_and_requires_repricing(documentary_tenant):
    from pricing.repository import rows
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, position_id, operation_id = _seed_project(org, owner)
    with as_user(owner):
        with pytest.raises(PricingError, match="commercial_revision_required"):
            price_current(org, owner, "OWNER", project_id)
        with commercial_backend():
            previous = one("SELECT * FROM public.pricing_operations WHERE id=%s", [operation_id])
        reset = service.reset_draft_pricing(org, project_id, operation_id, "Correct technical inputs")
        assert not reset["pricing_current"]
        with commercial_backend():
            assert one("SELECT * FROM public.pricing_operations WHERE id=%s", [operation_id]) == previous
        audit = rows("SELECT new_record->>'pricing_reset_at' AS reset_at FROM public.price_audit_logs WHERE entity_id=%s "
                     "AND reason='Correct technical inputs'", [project_id])
        assert audit and audit[-1]["reset_at"] is not None
        service.editable(org, project_id)
        with pytest.raises(DocumentaryError, match="applied_pricing_authority_required"):
            freeze_revision_a(org_id=org, actor_id=owner, project_id=project_id,
                              pricing_operation_id=operation_id, confirmed=True)
        operation = price_current(org, owner, "OWNER", project_id)
        with pytest.raises(ContractAPIException, match="Recarga"):
            service.reset_draft_pricing(org, project_id, operation_id, "Stale replay")
        frozen = freeze_revision_a(org_id=org, actor_id=owner, project_id=project_id,
                                  pricing_operation_id=operation, confirmed=True)
        assert frozen["documentary_complete"]
        with pytest.raises(ContractAPIException):
            service.reset_draft_pricing(org, project_id, operation, "Cannot reset history")


def test_backend_readiness_excludes_incomplete_system(documentary_tenant):
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    org, other, users, _ = documentary_tenant
    system = copy_fixed_catalog(org)
    with as_user(users["OWNER"]):
        readiness = catalog_readiness(system, org)
        assert not readiness["quote_ready"]
        # The clone carries the full technical catalog — only fabrication
        # authorities and manufacturing policies stay incomplete.
        assert readiness["reasons"] == ["manufacturing"]
        assert not catalog_readiness(system, other)["quote_ready"]
        demo = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")["id"]
        assert catalog_readiness(demo, org)["quote_ready"]


@pytest.mark.parametrize("coverage", ["NONE_REQUIRED", "DECLARED"])
def test_explicit_accessory_coverage_survives_prepare_and_freeze(documentary_tenant, coverage):
    from pricing.repository import json_text
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project, _, operation = _seed_project(org, owner)
    schedule = {"schema_version": 1, "coverage": coverage, "items": []}
    if coverage == "DECLARED":
        schedule["items"] = [{"obligation_id": "seal", "obligation_kind": "SEALING",
            "technical_sku": "SEAL", "purchasing_sku": "BUY-SEAL", "manufacturer_name": "Fixture",
            "order_type": "SUPPLIER_PROFILE_PO", "unit": "EA", "quantity_per_position_unit": 1,
            "description": "Explicit sealing"}]
    with as_user(owner), documentary_backend():
        one("UPDATE public.position_documentary_inputs SET accessory_schedule=%s::jsonb "
            "WHERE project_id=%s RETURNING id", [json_text(schedule), project])
        assert prepare_documentary_inputs(org_id=org, project_id=project)["positions"][0]["accessory_schedule"] == schedule
        frozen = freeze_revision_a(org_id=org, actor_id=owner, project_id=project,
                                  pricing_operation_id=operation, confirmed=True)
        _, snapshot = revision_snapshot(UUID(frozen["id"]), org)
        assert snapshot["positions"][0]["accessory_schedule"]["coverage"] == coverage


def test_pricing_reset_marker_cannot_be_written_directly(documentary_tenant):
    from django.db import DatabaseError, transaction
    org, _, users, _ = documentary_tenant
    project, _, _ = _seed_project(org, users["OWNER"])
    with as_user(users["OWNER"]), pytest.raises(DatabaseError), transaction.atomic():
        one("UPDATE public.projects SET pricing_reset_at=clock_timestamp() WHERE id=%s RETURNING id", [project])


@pytest.mark.parametrize("case", ["null_tenant", "installer", "other_tenant"])
def test_catalog_reservation_requires_editing_membership(documentary_tenant, case):
    from django.db import DatabaseError, transaction
    org, other, users, _ = documentary_tenant
    demo = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")["id"]
    actor = users["INSTALLER"] if case == "installer" else users["OWNER"]
    tenant = None if case == "null_tenant" else other if case == "other_tenant" else org
    with as_user(actor), pytest.raises(DatabaseError), transaction.atomic():
        one("SELECT private.reserve_catalog_authority(%s,%s)", [demo, tenant])


def test_readiness_requires_default_frame_reinforcement(documentary_tenant):
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    from pricing.repository import rows
    org, _, users, _ = documentary_tenant
    # The clone already carries the system's glass purchase authorities.
    system = copy_fixed_catalog(org)
    one("UPDATE public.profile_articles SET reinforcement_sku=NULL "
        "WHERE system_id=%s AND role='FRAME' RETURNING id", [system])
    with as_user(users["OWNER"]):
        assert "purchase" not in catalog_readiness(system, org)["reasons"]
    # The fixture delete must run as postgres: as_user leaves
    # SET LOCAL ROLE authenticated for the rest of the transaction, and
    # member deletes on reinforcement_articles are policy-filtered now.
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
    rows("DELETE FROM public.reinforcement_articles WHERE system_id=%s RETURNING id", [system])
    with as_user(users["OWNER"]):
        assert "purchase" in catalog_readiness(system, org)["reasons"]


@pytest.mark.parametrize("column", ["welding_loss_mm", "reinforcement_gap_mm"])
def test_readiness_flags_missing_fabrication_authority(documentary_tenant, column):
    """A PVC catalog that never declared weld loss or reinforcement gap must
    read as incomplete — the alternative is a quote that fails mid-geometry."""
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    org, _, users, _ = documentary_tenant
    system = copy_fixed_catalog(org)
    from pricing.repository import rows
    rows(f"UPDATE public.profile_articles SET {column}=NULL "
         "WHERE system_id=%s RETURNING id", [system])
    with as_user(users["OWNER"]):
        assert "fabrication" in catalog_readiness(system, org)["reasons"]


def test_readiness_skips_unwelded_and_fabrication_free_articles(documentary_tenant):
    """Readiness mirrors the engine's consumption rules: a THRESHOLD is appended
    unwelded, and only the effective SASH mass feeds leaf weight — so UNKNOWN
    weld/gap there and UNKNOWN mass on members the engine never weighs must
    not block an otherwise complete PVC catalog."""
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    org, _, users, _ = documentary_tenant
    system = copy_fixed_catalog(org)
    from pricing.repository import rows
    rows("UPDATE public.profile_articles SET welding_loss_mm=NULL,"
         "reinforcement_gap_mm=NULL WHERE system_id=%s AND role='THRESHOLD'"
         " RETURNING id", [system])
    rows("UPDATE public.profile_articles SET weight_kg_m=NULL"
         " WHERE system_id=%s AND role <> 'SASH' RETURNING id", [system])
    with as_user(users["OWNER"]):
        assert "fabrication" not in catalog_readiness(system, org)["reasons"]


def test_readiness_flags_reinforced_coupler_fabrication(documentary_tenant):
    """A reinforced coupler runs reinforcement_cut_length even though it loads
    outside the effective role map — UNKNOWN weld/gap on it must block."""
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    org, _, users, _ = documentary_tenant
    system = copy_fixed_catalog(org)
    from pricing.repository import rows
    rows("UPDATE public.profile_articles SET reinforcement_sku='ST-TEST',"
         " reinforcement_gap_mm=NULL WHERE system_id=%s AND role='COUPLER'"
         " RETURNING id", [system])
    with as_user(users["OWNER"]):
        assert "fabrication" in catalog_readiness(system, org)["reasons"]
    rows("UPDATE public.profile_articles SET reinforcement_sku=''"
         " WHERE system_id=%s AND role='COUPLER' RETURNING id", [system])
    with as_user(users["OWNER"]):
        # A blank SKU is unreinforced — the engine skips its steel cut math,
        # so UNKNOWN weld/gap must not block the whole catalog.
        assert "fabrication" not in catalog_readiness(system, org)["reasons"]


@pytest.mark.parametrize("role,flagged", [("SASH", True), ("FRAME", False)])
def test_readiness_nonpvc_weight_scoped_to_leaf_articles(documentary_tenant, role, flagged):
    """Non-PVC mass is consumed only by leaf weight, so only the effective
    SASH's missing density flags fabrication — a frame's does not."""
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    org, _, users, _ = documentary_tenant
    system = copy_fixed_catalog(org, code="ALU_65")
    from pricing.repository import rows
    rows("UPDATE public.profile_articles SET weight_kg_m=NULL"
         " WHERE system_id=%s AND role=%s RETURNING id", [system, role])
    with as_user(users["OWNER"]):
        assert ("fabrication" in catalog_readiness(system, org)["reasons"]) is flagged


def test_reviewed_catalog_edit_reopens_readiness(documentary_tenant):
    """Devin Review: a reviewed row's technical edit cleared its stamps but
    kept MANUAL provenance — readiness still passed with unverified values.
    review_pending records the stale review so the gate re-opens, while a
    never-reviewed authored edit stays eligible."""
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    from pricing.repository import rows

    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    system = copy_fixed_catalog(org)
    article_id = rows(
        "SELECT id FROM public.profile_articles"
        " WHERE system_id=%s AND org_id=%s AND role='FRAME' LIMIT 1",
        [system, org],
    )[0]["id"]

    def flagged() -> bool:
        with as_user(owner):
            return "catalog_review" in catalog_readiness(system, org)["reasons"]

    # Legacy row → gates until reviewed; review clears both gates.
    rows(
        "UPDATE public.profile_articles SET data_provenance='LEGACY_UNVERIFIED'"
        " WHERE id=%s RETURNING id",
        [article_id],
    )
    assert flagged()
    with as_user(owner):
        row = catalog_service.retrieve(catalog_service.ARTICLES, org, article_id)
        catalog_service.review(
            catalog_service.ARTICLES, org, article_id, owner, f'"{row["revision"]}"'
        )
    assert not flagged()

    # Editing the reviewed row's technical values reopens the gate.
    with as_user(owner):
        row = catalog_service.retrieve(catalog_service.ARTICLES, org, article_id)
        catalog_service.update(
            catalog_service.ARTICLES, org, article_id,
            {"weight_kg_m": "1.2345"}, f'"{row["revision"]}"',
        )
    assert flagged()

    # Reviewing again clears it; a further technical edit reopens again.
    with as_user(owner):
        row = catalog_service.retrieve(catalog_service.ARTICLES, org, article_id)
        catalog_service.review(
            catalog_service.ARTICLES, org, article_id, owner, f'"{row["revision"]}"'
        )
    assert not flagged()

    # A never-reviewed authored row (provenance MANUAL, no prior review)
    # stays eligible after edits — the gate only tracks stale reviews.
    other_id = rows(
        "SELECT id FROM public.profile_articles"
        " WHERE system_id=%s AND org_id=%s AND role='SASH' LIMIT 1",
        [system, org],
    )[0]["id"]
    with as_user(owner):
        row = catalog_service.retrieve(catalog_service.ARTICLES, org, other_id)
        catalog_service.update(
            catalog_service.ARTICLES, org, other_id,
            {"weight_kg_m": "2.0000"}, f'"{row["revision"]}"',
        )
        assert catalog_service.retrieve(catalog_service.ARTICLES, org, other_id)[
            "review_pending"
        ] is False
    assert not flagged()


def test_readiness_levels_report_exact_blockers(documentary_tenant):
    """§E: the levels ladder names the missing authority, what it affects and
    the action that resolves it — quote_ready keeps its legacy contract."""
    from catalogs.readiness import catalog_readiness
    org, _, users, _ = documentary_tenant
    demo = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")["id"]

    with as_user(users["OWNER"]):
        readiness = catalog_readiness(demo, org)
    levels = {level["level"]: level for level in readiness["levels"]}
    assert levels["DESIGN_VALID"]["ok"] is True
    assert levels["QUOTE_READY"]["ok"] is True
    assert levels["MANUFACTURING_INCOMPLETE"]["state"] == "COMPLETE"
    # Fresh orgs have no work centers until a production release seeds them.
    assert levels["PRODUCTION_READY"]["ok"] is False
    blocker = levels["PRODUCTION_READY"]["blockers"][0]
    assert blocker["code"] == "work_centers"
    assert blocker["missing_authority"]
    assert blocker["affected"]
    assert blocker["why"]
    assert blocker["action"]
    assert readiness["process_via"] is not None
    # quote_ready must not absorb the new production/CNC blockers.
    assert readiness["quote_ready"] is True

    with as_user(users["WORKSHOP_MANAGER"]), documentary_backend():
        for code, name, kind, order in (
            ("CUT_SAW", "Sierra", "CUT", 10),
            ("MACHINING_CENTER", "Mecanizado", "MACHINING", 15),
            ("WELDER", "Soldadora", "WELDING", 20),
            ("CLEANING_STATION", "Limpiadora", "CLEANING", 25),
            ("SASH_BENCH", "Armado hojas", "SASH_ASSEMBLY", 30),
            ("HW_BENCH", "Herrajes", "HARDWARE", 32),
            ("GLAZE_BENCH", "Vidriado", "GLAZING", 40),
            ("QC_STATION", "Control", "QC", 50),
            ("PACK_STATION", "Embalaje", "PACK", 60),
        ):
            one(
                "INSERT INTO public.work_centers(org_id, code, name, kind, display_order) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                [org, code, name, kind, order],
            )
    with as_user(users["OWNER"]):
        ready = catalog_readiness(demo, org)
    levels = {level["level"]: level for level in ready["levels"]}
    assert levels["PRODUCTION_READY"]["ok"] is True
    assert levels["CNC_READY"]["ok"] is True


def test_readiness_levels_flag_unmapped_machine_ops(documentary_tenant):
    """A bound profile whose operation→station map can't route a machine
    operation the system emits stays CNC-incomplete — the UI fallback is
    never the authority."""
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    from catalogs.readiness import catalog_readiness
    org, _, users, _ = documentary_tenant
    # The clone is org-scoped so member writes can bind process profiles —
    # global demo systems are member-immutable by policy.
    demo = copy_fixed_catalog(org)
    # The clone skips the policy tables by design; a fully-ready system needs
    # the global manufacturing policies copied for it (postgres-level fixture
    # writes — they run before any member context locks the role).
    from pricing.repository import json_text, rows as pg_rows
    global_demo = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60' AND is_global")["id"]
    for table in ("manufacturing_placement_policies", "handle_requirement_policies",
                  "reinforcement_cut_policies"):
        jsonb_cols = {
            row["column_name"]
            for row in pg_rows(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s AND data_type='jsonb'",
                [table],
            )
        }
        for row in pg_rows(
            f"SELECT * FROM public.{table} WHERE system_id=%s AND org_id IS NULL",
            [global_demo],
        ):
            row = {key: value for key, value in row.items() if key != "id"}
            for column in jsonb_cols:
                if isinstance(row.get(column), str):
                    row[column] = json.loads(row[column])
            one(
                f"INSERT INTO public.{table} SELECT (jsonb_populate_record("
                f"NULL::public.{table}, %s::jsonb)).* RETURNING id",
                [json_text({**row, "id": str(uuid4()), "system_id": str(demo)})],
            )
    pvc = one(
        "SELECT id FROM public.manufacturing_process_profiles WHERE code='PVC_WELDED'"
    )["id"]
    frameless = one(
        "SELECT id FROM public.manufacturing_process_profiles WHERE code='FRAMELESS_GLASS'"
    )["id"]
    try:
        with as_user(users["WORKSHOP_MANAGER"]), documentary_backend():
            for code, kind in (
                ("CUT_SAW", "CUT"), ("WELDER", "WELDING"), ("CLEANING_STATION", "CLEANING"),
                ("QC_STATION", "QC"), ("PACK_STATION", "PACK"), ("MACHINING_CELL", "MACHINING"),
                ("SASH_BENCH", "SASH_ASSEMBLY"), ("HW_BENCH", "HARDWARE"), ("GLAZE_BENCH", "GLAZING"),
            ):
                one(
                    "INSERT INTO public.work_centers(org_id, code, name, kind, display_order) "
                    "VALUES (%s,%s,%s,%s,10) RETURNING id",
                    [org, code, code, kind],
                )
        with as_user(users["WORKSHOP_MANAGER"]):
            one(
                "UPDATE public.profile_systems SET process_profile_id=%s WHERE id=%s RETURNING id",
                [pvc, demo],
            )
            readiness = catalog_readiness(demo, org)
        levels = {level["level"]: level for level in readiness["levels"]}
        assert levels["PRODUCTION_READY"]["ok"] is True
        assert levels["CNC_READY"]["ok"] is True
        assert readiness["process_via"] == "system_declared"

        # The clone has mullions → END_MACHINING; the frameless profile routes
        # only SAW_CUT and HANDLE_PREP, so binding it must surface the gap.
        # Blocker text is user-facing: ops are named by their localized
        # label (R6 — no machine keys in copy).
        with as_user(users["WORKSHOP_MANAGER"]):
            one(
                "UPDATE public.profile_systems SET process_profile_id=%s WHERE id=%s RETURNING id",
                [frameless, demo],
            )
            readiness = catalog_readiness(demo, org)
        levels = {level["level"]: level for level in readiness["levels"]}
        assert levels["CNC_READY"]["ok"] is False
        blocker = next(
            b for b in levels["CNC_READY"]["blockers"]
            if b["code"] == "station_map"
        )
        assert "mecanizado de extremo" in blocker["affected"]
        assert "END_MACHINING" not in blocker["affected"]
    finally:
        with as_user(users["WORKSHOP_MANAGER"]):
            one(
                "UPDATE public.profile_systems SET process_profile_id=NULL WHERE id=%s RETURNING id",
                [demo],
            )


def test_global_search_uses_canonical_catalog_visibility(documentary_tenant):
    """A member searching a global system's code must find the system and
    its NULL-org articles — identical to what the catalog service lists."""
    from search.service import search
    org, _, users, _ = documentary_tenant
    with as_user(users["ESTIMATOR"]):
        systems = search(org, "demo_60")["results"]
        articles = search(org, "marco demo")["results"]
    assert any(r["group"] == "systems" and "DEMO_60" in r["title"] for r in systems)
    assert any(r["group"] == "articles" and r["title"] == "MARCO" for r in articles)
