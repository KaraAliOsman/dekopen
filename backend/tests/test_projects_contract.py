"""Manual project inputs cannot supply technical results, costs or tenant IDs."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal

import pytest
from rest_framework.exceptions import APIException

from backend.tests.factories import ORG_A_ID, demo_60_params
from backend.tests.test_engine_api import g1_request
from engine_api.repository import SystemParamsRepository
from engine_api.serializers import EngineCalculateRequestSerializer
from pricing.serializers import DraftPositionSerializer
from projects.serializers import PositionWriteSerializer, ProjectWriteSerializer
from projects.service import calculate_design, next_revision_code, unchanged
from projects import service
from projects.typology import derive_typology


@pytest.mark.parametrize(
    "key,value",
    [
        ("org_id", "00000000-0000-0000-0000-000000000001"),
        ("total_cost_net", "10"),
        ("total_price_gross", "1"),
        ("status", "APPROVED"),
    ],
)
def test_project_rejects_tenant_price_and_state_injection(key, value):
    serializer = ProjectWriteSerializer(data={"name": "Casa", "client_name": "Cliente", key: value})
    assert not serializer.is_valid()


@pytest.mark.parametrize("dimension", [1000, 1000.0, "249.99", "NaN", "Infinity"])
def test_position_requires_exact_valid_dimension(dimension):
    design = {**g1_request(), "nominal_width_mm": dimension}
    serializer = PositionWriteSerializer(
        data={"location_tag": "Cocina", "quantity": 1, "design": design}
    )
    assert not serializer.is_valid()


def test_position_rejects_client_bom():
    serializer = PositionWriteSerializer(
        data={
            "location_tag": "Cocina",
            "quantity": 1,
            "design": g1_request(),
            "bom": {},
        }
    )
    assert not serializer.is_valid()


def test_persisted_quotation_inputs_carry_a_bounded_finish_string():
    """Finishes moved from a WHITE-only constant to the system's declared
    `finishes` list: write serializers bound the field by shape, and the
    engine adapter enforces membership at calculation time."""
    foiled = {**g1_request(), "color": "FOILED"}
    assert EngineCalculateRequestSerializer(data=foiled).is_valid()
    assert PositionWriteSerializer(
        data={"location_tag": "Cocina", "quantity": 1, "design": foiled}
    ).is_valid()
    assert DraftPositionSerializer(
        data={**foiled, "position_index": 1, "quantity": 1, "typology": "FIXED"}
    ).is_valid()
    # the shape is still bounded — blank or overlong finish strings are refused
    blank = {**g1_request(), "color": ""}
    assert not PositionWriteSerializer(
        data={"location_tag": "Cocina", "quantity": 1, "design": blank}
    ).is_valid()
    overlong = {**g1_request(), "color": "X" * 60}
    assert not DraftPositionSerializer(
        data={**overlong, "position_index": 1, "quantity": 1, "typology": "FIXED"}
    ).is_valid()


def test_calculation_matches_engine_and_inputs_are_not_changed(monkeypatch):
    monkeypatch.setattr(SystemParamsRepository, "load_visible", lambda *_: demo_60_params())
    serializer = PositionWriteSerializer(
        data={"location_tag": "Cocina", "quantity": 1, "design": g1_request()}
    )
    assert serializer.is_valid(), serializer.errors
    design = serializer.validated_data["design"]
    before = deepcopy(design)
    result = calculate_design(ORG_A_ID, design)
    assert result["glasses"][0]["width_mm"] == "910.00"
    assert result["glasses"][0]["height_mm"] == "910.00"
    assert result["calculation_hash"].startswith("sha256:")
    assert design == before
    assert isinstance(design["nominal_width_mm"], Decimal)


def test_stale_edit_is_a_conflict_not_last_writer_wins():
    current = datetime(2026, 9, 18, 12, 0, 1, tzinfo=timezone.utc)
    prior = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    unchanged({"updated_at": current}, current)
    with pytest.raises(APIException) as caught:
        unchanged({"updated_at": current}, prior)
    assert caught.value.status_code == 409


def test_invalid_engine_geometry_returns_domain_error_without_raw_tree_details(monkeypatch):
    monkeypatch.setattr(SystemParamsRepository, "load_visible", lambda *_: demo_60_params())

    def reject(**kwargs):
        raise ValueError("SPLIT_V node-private produces a non-positive BAY width")

    monkeypatch.setattr(service, "calculate_from_api", reject)
    with pytest.raises(APIException) as caught:
        calculate_design(ORG_A_ID, g1_request())
    assert caught.value.status_code == 400
    assert "SPLIT_V" not in str(caught.value)
    assert "node-private" not in str(caught.value)
    assert "divisiones" in str(caught.value)


@pytest.mark.parametrize(
    "opening,typology",
    [
        ("FIXED", "FIXED"),
        ("TURN_LEFT", "TURN"),
        ("TURN_RIGHT", "TURN"),
        ("TILT_TURN_LEFT", "TILT_TURN"),
        ("TILT_TURN_RIGHT", "TILT_TURN"),
        ("SLIDING_2L", "SLIDING_2L"),
        ("SLIDING_3L", "SLIDING_3L"),
        ("SLIDING_4L", "SLIDING_4L"),
        ("SLIDING", "SLIDING"),
        ("AWNING", "AWNING"),
        ("DOOR_ENTRY", "DOOR_ENTRY"),
    ],
)
def test_undivided_typology_is_derived_from_opening(opening, typology):
    assert derive_typology({"id": "B1", "type": "BAY", "opening_type": opening}) == typology


@pytest.mark.parametrize("split_type", ["SPLIT_V", "SPLIT_H"])
def test_any_structural_division_is_composite(split_type):
    tree = {
        "id": "S1",
        "type": split_type,
        "children": [
            {"id": "B1", "type": "BAY", "opening_type": "FIXED"},
            {"id": "B2", "type": "BAY", "opening_type": "TURN_LEFT"},
        ],
    }
    assert derive_typology(tree) == "COMPOSITE"
    tree["children"][1]["opening_type"] = "FIXED"
    assert derive_typology(tree) == "COMPOSITE"


def test_revision_sequence_is_excel_style_without_skips():
    assert next_revision_code("REV-A") == "REV-B"
    assert next_revision_code("REV-Z") == "REV-AA"
    assert next_revision_code("REV-AA") == "REV-AB"


def test_unassigned_couplers_save_as_manufacturing_incomplete(monkeypatch):
    """Declared-but-unassigned couplers are warnings: the BOM is complete
    structurally, so the position persists as a draft. Sealing/production
    stay gated downstream."""
    from backend.tests.factories import SYSTEM_ID
    from backend.tests.test_engine_assembly import bow_product

    monkeypatch.setattr(
        SystemParamsRepository, "load_visible", lambda *_: demo_60_params()
    )
    monkeypatch.setattr(
        SystemParamsRepository, "load_coupler_articles", lambda *_: {}
    )
    design = {
        "system_id": SYSTEM_ID,
        "nominal_width_mm": Decimal("2100.00"),
        "nominal_height_mm": Decimal("1400.00"),
        "color": "WHITE",
        "parametric_tree": bow_product(),
    }
    result = calculate_design(ORG_A_ID, design)
    assert result["calculation_hash"].startswith("sha256:")


def test_valid_assembly_saves_with_prefixed_bom(monkeypatch):
    from backend.tests.factories import SYSTEM_ID
    from backend.tests.test_engine_assembly import COUPLER_ARTICLE, bow_product

    monkeypatch.setattr(
        SystemParamsRepository, "load_visible", lambda *_: demo_60_params()
    )
    monkeypatch.setattr(
        SystemParamsRepository,
        "load_coupler_articles",
        lambda *_: {"ACOPLE-60": COUPLER_ARTICLE},
    )
    design = {
        "system_id": SYSTEM_ID,
        "nominal_width_mm": Decimal("2100.00"),
        "nominal_height_mm": Decimal("1400.00"),
        "color": "WHITE",
        "parametric_tree": bow_product(coupler_sku="ACOPLE-60"),
    }
    result = calculate_design(ORG_A_ID, design)
    assert result["calculation_hash"].startswith("sha256:")
    assert design["nominal_width_mm"] == Decimal("2100.00")
    assert any(
        (cut["bay_id"] or "").startswith("m1|") for cut in result["profile_cuts"]
    )


def test_assembly_save_rejects_conflicting_nominal_dimensions(monkeypatch):
    from backend.tests.factories import SYSTEM_ID
    from backend.tests.test_engine_assembly import COUPLER_ARTICLE, bow_product

    monkeypatch.setattr(
        SystemParamsRepository, "load_visible", lambda *_: demo_60_params()
    )
    monkeypatch.setattr(
        SystemParamsRepository,
        "load_coupler_articles",
        lambda *_: {"ACOPLE-60": COUPLER_ARTICLE},
    )
    design = {
        "system_id": SYSTEM_ID,
        "nominal_width_mm": Decimal("2200.00"),
        "nominal_height_mm": Decimal("1400.00"),
        "color": "WHITE",
        "parametric_tree": bow_product(coupler_sku="ACOPLE-60"),
    }
    with pytest.raises(APIException) as caught:
        calculate_design(ORG_A_ID, design)
    assert caught.value.status_code == 400
    assert caught.value.get_codes() == "validation_error"


def test_position_public_preserves_pre_upgrade_glass_metadata_hash():
    """BOMs sealed before GlassPiece carried spec/sku must still validate:
    absent keys stay absent (canonical identity unchanged)."""
    import json as _json
    from dekopen_engine.snapshot import calculation_hash

    stored_glasses = [
        {
            "bay_id": "bay_1",
            "leaf_id": None,
            "width_mm": "680.00",
            "height_mm": "1310.00",
            "area_m2": "0.8908",
            "weight_kg": "17.82",
            "thickness_net_mm": "8.00",
        }
    ]
    stored_bom = {
        "profile_cuts": [],
        "reinforcements": [],
        "glasses": stored_glasses,
        "panels": [],
        "hardware_items": [],
        "leaf_weights": [],
    }
    design = {
        "system_id": str(uuid4()),
        "nominal_width_mm": "1400.00",
        "nominal_height_mm": "1200.00",
        "color": "WHITE",
        "parametric_tree": {"kind": "window", "width_mm": "1400", "height_mm": "1200"},
    }
    expected = calculation_hash(design, stored_bom)
    row = {
        "id": uuid4(),
        "project_id": uuid4(),
        "position_index": 0,
        "location_tag": "",
        "quantity": 1,
        "typology": "FIXED",
        "system_id": design["system_id"],
        "width_mm": Decimal("1400.00"),
        "height_mm": Decimal("1200.00"),
        "color_interior": "WHITE",
        "color_exterior": "WHITE",
        "parametric_tree": _json.dumps(design["parametric_tree"]),
        "bom_snapshot": _json.dumps({**stored_bom, "calculation_hash": expected}),
        "cost_net": Decimal("0"),
        "price_net": Decimal("0"),
        "discount_pct": Decimal("0"),
        "updated_at": "2026-09-23T00:00:00Z",
    }
    public = service.position_public(row)
    assert public["bom"]["calculation_hash"] == expected
    assert public["bom"]["glasses"] == stored_glasses  # no injected null keys


def test_position_public_reads_new_glass_metadata_fields():
    """Post-upgrade BOMs hash with their explicit spec/sku keys present."""
    import json as _json
    from dekopen_engine.snapshot import calculation_hash

    stored_glasses = [
        {
            "bay_id": "bay_1",
            "leaf_id": "leaf_1",
            "width_mm": "680.00",
            "height_mm": "1310.00",
            "area_m2": "0.8908",
            "weight_kg": "17.82",
            "thickness_net_mm": "8.00",
            "glass_spec": "4-16-4 Float Incoloro",
            "article_sku": "GLS-441",
        }
    ]
    stored_bom = {
        "profile_cuts": [],
        "reinforcements": [],
        "glasses": stored_glasses,
        "panels": [],
        "hardware_items": [],
        "leaf_weights": [],
    }
    design = {
        "system_id": str(uuid4()),
        "nominal_width_mm": "1400.00",
        "nominal_height_mm": "1200.00",
        "color": "WHITE",
        "parametric_tree": {"kind": "window", "width_mm": "1400", "height_mm": "1200"},
    }
    expected = calculation_hash(design, stored_bom)
    row = {
        "id": uuid4(),
        "project_id": uuid4(),
        "position_index": 0,
        "location_tag": "",
        "quantity": 1,
        "typology": "FIXED",
        "system_id": design["system_id"],
        "width_mm": Decimal("1400.00"),
        "height_mm": Decimal("1200.00"),
        "color_interior": "WHITE",
        "color_exterior": "WHITE",
        "parametric_tree": _json.dumps(design["parametric_tree"]),
        "bom_snapshot": _json.dumps({**stored_bom, "calculation_hash": expected}),
        "cost_net": Decimal("0"),
        "price_net": Decimal("0"),
        "discount_pct": Decimal("0"),
        "updated_at": "2026-09-23T00:00:00Z",
    }
    public = service.position_public(row)
    assert public["bom"]["calculation_hash"] == expected
    assert public["bom"]["glasses"] == stored_glasses


def test_manufacturing_incomplete_assembly_saves_as_draft(monkeypatch):
    """An arch (member_bending_required warnings) carries a complete BOM —
    it persists as a draft position while INVALID evaluations still refuse.
    Sealing/production stay gated downstream."""
    from backend.tests.factories import SYSTEM_ID
    from backend.tests.test_engine_assembly import contour_product

    monkeypatch.setattr(
        SystemParamsRepository, "load_visible", lambda *_: demo_60_params()
    )
    monkeypatch.setattr(
        SystemParamsRepository, "load_coupler_articles", lambda *_: {}
    )
    design = {
        "system_id": SYSTEM_ID,
        "nominal_width_mm": Decimal("2400.00"),
        "nominal_height_mm": Decimal("1400.00"),
        "color": "WHITE",
        "parametric_tree": contour_product(
            [("0", "0"), ("2400", "0"), ("2400", "1400"), ("0", "1400")],
            [None, None, "300.00", None],
        ),
    }
    result = calculate_design(ORG_A_ID, design)
    assert result["calculation_hash"].startswith("sha256:")
    assert any(cut.get("sagitta_mm") for cut in result["profile_cuts"])


def test_operable_contour_intent_refuses_to_save(monkeypatch):
    """A contour module whose bay declares an operable opening still
    evaluates: the engine emits the frame + infill it can build and warns
    contour_opening_unsupported. Persisting that would seal a fixed-pane
    BOM under a tilt-turn intent — the saved product would misdescribe
    itself, so persistence refuses until the leaf is honestly fixed."""
    from backend.tests.factories import SYSTEM_ID
    from backend.tests.test_engine_assembly import contour_product

    monkeypatch.setattr(
        SystemParamsRepository, "load_visible", lambda *_: demo_60_params()
    )
    monkeypatch.setattr(
        SystemParamsRepository, "load_coupler_articles", lambda *_: {}
    )
    product = contour_product(
        [("0", "0"), ("2400", "0"), ("2200", "1400"), ("200", "1400")],
        [None, None, None, None],
    )
    product["assembly"]["modules"][0]["tree"]["opening_type"] = (
        "TILT_TURN_LEFT"
    )
    design = {
        "system_id": SYSTEM_ID,
        "nominal_width_mm": Decimal("2400.00"),
        "nominal_height_mm": Decimal("1400.00"),
        "color": "WHITE",
        "parametric_tree": product,
    }
    with pytest.raises(APIException) as caught:
        calculate_design(ORG_A_ID, design)
    assert caught.value.status_code == 400
    assert caught.value.get_codes() == "manufacturing_incomplete"


def test_invalid_assembly_still_refuses_to_save(monkeypatch):
    """A disconnected assembly (a module no coupling reaches) is INVALID —
    persistence must refuse it even though a partial BOM exists."""
    from backend.tests.factories import SYSTEM_ID
    from backend.tests.test_engine_assembly import bow_product

    monkeypatch.setattr(
        SystemParamsRepository, "load_visible", lambda *_: demo_60_params()
    )
    monkeypatch.setattr(
        SystemParamsRepository, "load_coupler_articles", lambda *_: {}
    )
    product = bow_product()
    product["assembly"]["modules"].append(
        {
            "id": "m4",
            "width_mm": "700.00",
            "height_mm": "1400.00",
            "tree": {
                "id": "m4",
                "type": "BAY",
                "opening_type": "FIXED",
                "glass_thickness_mm": "4.00",
                "glass_spec": "4",
            },
        }
    )
    design = {
        "system_id": SYSTEM_ID,
        "nominal_width_mm": Decimal("2800.00"),
        "nominal_height_mm": Decimal("1400.00"),
        "color": "WHITE",
        "parametric_tree": product,
    }
    with pytest.raises(APIException) as caught:
        calculate_design(ORG_A_ID, design)
    assert caught.value.status_code == 400
    assert caught.value.get_codes() == "manufacturing_incomplete"


def test_module_geometry_failure_refuses_to_save(monkeypatch):
    """A module whose evaluation produced no result is absent from the
    aggregated BOM — saving it would persist a partial BOM as complete.
    MANUFACTURING_INCOMPLETE only tolerates warnings that leave every
    module's output whole (couplers, bending, unsupported contour leaves)."""
    from backend.tests.factories import SYSTEM_ID
    from backend.tests.test_engine_assembly import bow_product

    monkeypatch.setattr(
        SystemParamsRepository, "load_visible", lambda *_: demo_60_params()
    )
    monkeypatch.setattr(
        SystemParamsRepository, "load_coupler_articles", lambda *_: {}
    )
    product = bow_product()
    product["assembly"]["modules"].append(
        {
            "id": "m4",
            "width_mm": "700.00",
            "height_mm": "1400.00",
            "tree": {
                "id": "m4",
                "type": "BAY",
                "opening_type": "FIXED",
                "glass_thickness_mm": "4.00",
                # no glass_spec — the leaf cannot resolve a recipe
            },
        }
    )
    # A module added but never coupled stays disconnected → INVALID covers
    # it; couple it so only the geometry failure remains.
    product["assembly"]["couplings"].append(
        {"id": "c4", "kind": "INLINE", "modules": ["m3", "m4"], "angle_deg": "0"}
    )
    design = {
        "system_id": SYSTEM_ID,
        "nominal_width_mm": Decimal("2800.00"),
        "nominal_height_mm": Decimal("1400.00"),
        "color": "WHITE",
        "parametric_tree": product,
    }
    with pytest.raises(APIException) as caught:
        calculate_design(ORG_A_ID, design)
    assert caught.value.status_code == 400
    assert caught.value.get_codes() == "manufacturing_incomplete"


@pytest.mark.parametrize(
    "opening,expected",
    [
        ("SLIDING_3L", "SLIDING_3L"),
        ("SLIDING_4L", "SLIDING_4L"),
        ("SLIDING", "SLIDING"),
    ],
)
def test_sliding_openings_survive_save_typology(opening, expected, monkeypatch):
    """New sliding openings must reach persistence: a successful calculation
    whose typology previously fell to 422 now derives a real label."""
    from engine.tests.catalog import demo_corredera_60_params

    monkeypatch.setattr(
        SystemParamsRepository,
        "load_visible",
        lambda *_: demo_corredera_60_params(),
    )
    monkeypatch.setattr(
        SystemParamsRepository, "load_coupler_articles", lambda *_: {}
    )
    design = g1_request()
    # Wide enough that every preset's leaf lands inside the sliding kit's
    # envelope (KIT-SLIDING-CORR on DEMO_CORREDERA_60 — a sliding-family
    # system, since D01 families reject sliding openings on DEMO_60).
    design["nominal_width_mm"] = Decimal("2400.00")
    design["nominal_height_mm"] = Decimal("1400.00")
    design["parametric_tree"]["opening_type"] = opening
    if opening == "SLIDING":
        design["parametric_tree"]["sliding_layout"] = {
            "tracks": 2,
            "panels": [
                {"slot": "izq", "kind": "MOVING", "track": 0},
                {"slot": "der", "kind": "MOVING", "track": 1},
            ],
        }
    result = calculate_design(ORG_A_ID, design)
    assert result["calculation_hash"].startswith("sha256:")
    assert service._typology(design["parametric_tree"]) == expected
