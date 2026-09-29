from decimal import Decimal
import json

import pytest

from catalogs.serializers import (
    KIT_OPENING_TYPES,
    KitWriteSerializer,
    ArticleWriteSerializer,
    CatalogHardwareComponentSerializer,
    ProfileSectionSerializer,
    SystemWriteSerializer,
)
from catalogs.service import _contents_json, _jsonb, catalog_revision, require_revision
from authentication.errors import ContractAPIException
from engine_api.repository import (
    UnsupportedCatalogContract,
    _hardware_contents,
    _section,
)


def test_component_round_trip_remains_engine_decimal():
    serializer = CatalogHardwareComponentSerializer(
        data={
            "sku": "COMPONENT",
            "name": 'Component "quoted"',
            "qty": "1.00000000000000000001",
            "unit": "unit",
        }
    )
    assert serializer.is_valid(), serializer.errors
    persisted = _contents_json([serializer.validated_data])
    loaded = _hardware_contents(persisted)
    assert loaded[0].qty == Decimal("1.00000000000000000001")
    assert loaded[0].name == 'Component "quoted"'


def test_catalog_revision_rejects_stale_or_missing_copy_without_rounding():
    original = {"contents": [{"qty": Decimal("1.00000000000000000001")}], "name": "Kit"}
    changed = {"contents": [{"qty": Decimal("1.00000000000000000002")}], "name": "Kit"}
    revision = catalog_revision(original)
    assert revision != catalog_revision(changed)
    assert revision == catalog_revision(dict(reversed(list(original.items()))))
    require_revision({"revision": revision}, f'"{revision}"')
    for token in (None, revision, f'"{catalog_revision(changed)}"'):
        with pytest.raises(ContractAPIException) as error:
            require_revision({"revision": revision}, token)
        assert error.value.status_code == 409


@pytest.mark.parametrize("quantity", [True, "NaN", "Infinity", "0", "-1", {}])
def test_invalid_component_quantity(quantity):
    serializer = CatalogHardwareComponentSerializer(
        data={
            "sku": "C",
            "name": "Component",
            "qty": quantity,
            "unit": "unit",
        }
    )
    assert not serializer.is_valid()


def test_kit_opening_choices_match_current_operable_engine():
    assert set(KIT_OPENING_TYPES) == {
        "TURN",
        "TILT_TURN",
        "SLIDING",
        "AWNING",
        "DOOR",
    }


@pytest.mark.parametrize("opening", ["TURN_LEFT", "SLIDING_2L", "FIXED", "OTHER"])
def test_kit_rejects_noncanonical_opening(opening):
    serializer = KitWriteSerializer(
        data={"opening_type": opening},
        partial=True,
    )
    assert not serializer.is_valid()


@pytest.mark.parametrize("value", ["0", "-1", "100000000.00", "6000.001"])
def test_stock_length_rejects_invalid_engine_or_storage_range(value):
    serializer = ArticleWriteSerializer(
        data={"commercial_length_mm": value},
        partial=True,
    )
    assert not serializer.is_valid()


def test_stock_length_accepts_exact_storage_boundary():
    serializer = ArticleWriteSerializer(
        data={"commercial_length_mm": "99999999.99"},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors


def test_patch_checks_interval_against_existing_other_endpoint():
    serializer = KitWriteSerializer(
        instance={
            "min_leaf_width_mm": Decimal("400"),
            "max_leaf_width_mm": Decimal("1200"),
        },
        data={"max_leaf_width_mm": "399.99"},
        partial=True,
    )
    assert not serializer.is_valid()


def test_equal_interval_endpoints_are_valid():
    serializer = KitWriteSerializer(
        instance={"min_leaf_width_mm": Decimal("400")},
        data={"max_leaf_width_mm": "400.00"},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("field", ["org_id", "is_global", "is_demo", "id"])
def test_system_rejects_authority_injection(field):
    serializer = SystemWriteSerializer(data={field: "injected"}, partial=True)
    assert not serializer.is_valid()


def test_dimensions_never_round_excess_precision():
    serializer = ArticleWriteSerializer(
        data={"face_width_mm": "60.001"},
        partial=True,
    )
    assert not serializer.is_valid()


def test_new_system_requires_explicit_added_geometry():
    serializer = SystemWriteSerializer(data={})
    assert not serializer.is_valid()
    assert {
        "sliding_glazing_deduction_width_mm",
        "sliding_glazing_deduction_height_mm",
        "door_leaf_side_clearance_mm",
    } <= set(serializer.errors)


def test_component_rejects_untyped_extra_content():
    serializer = CatalogHardwareComponentSerializer(
        data={
            "sku": "C",
            "name": "Component",
            "qty": "1",
            "unit": "unit",
            "price": "1000",
        }
    )
    assert not serializer.is_valid()


SECTION_POLYGON = {
    "source": "POLYGON",
    "polygon": [
        {"x_mm": "0", "y_mm": "0"},
        {"x_mm": "60", "y_mm": "0"},
        {"x_mm": "60", "y_mm": "60"},
        {"x_mm": "0", "y_mm": "60"},
    ],
    "depth_mm": "60.00",
    "axes": [{"name": "GLAZING", "y_mm": "24.00"}],
}


def test_article_section_round_trip_preserves_engine_decimal():
    serializer = ArticleWriteSerializer(data={"section": SECTION_POLYGON}, partial=True)
    assert serializer.is_valid(), serializer.errors
    section = _section(_jsonb(serializer.validated_data["section"]))
    assert section is not None
    assert section.source == "POLYGON"
    assert section.depth_mm == Decimal("60.00")
    assert section.polygon[0].x_mm == Decimal("0")
    assert section.axes[0].y_mm == Decimal("24.00")


@pytest.mark.parametrize(
    "mutated",
    [
        {**SECTION_POLYGON, "polygon": SECTION_POLYGON["polygon"][:2]},
        {**SECTION_POLYGON, "depth_mm": "0"},
        {**SECTION_POLYGON, "source": "TRACING"},
        {k: v for k, v in SECTION_POLYGON.items() if k != "polygon"},
        # degenerate shapes: repeated vertices and a collinear chain enclose
        # nothing — they must not pass as declared sections.
        {**SECTION_POLYGON, "polygon": [{"x_mm": "0", "y_mm": "0"}] * 3},
        {
            **SECTION_POLYGON,
            "polygon": [
                {"x_mm": "0", "y_mm": "0"},
                {"x_mm": "30", "y_mm": "0"},
                {"x_mm": "60", "y_mm": "0"},
            ],
        },
        # a manufacturer-drawing provenance without its drawing reference is
        # an unverifiable claim, not an exact section.
        {**SECTION_POLYGON, "source": "DXF_REFERENCE"},
        {**SECTION_POLYGON, "source": "DXF_REFERENCE", "drawing_ref": "   "},
        # partial payloads: the column is replaced wholesale — a present
        # section must carry its complete shape.
        {"depth_mm": "70"},
    ],
)
def test_article_section_rejects_noncanonical_shapes(mutated):
    serializer = ProfileSectionSerializer(data=mutated)
    assert not serializer.is_valid()


@pytest.mark.parametrize(
    "section",
    [
        {**SECTION_POLYGON, "polygon": SECTION_POLYGON["polygon"][:2] + [{"x_mm": "0"}]},
        {**SECTION_POLYGON, "axes": [{"name": "GLAZING"}]},
    ],
)
def test_article_section_partial_patch_rejects_incomplete_rows(section):
    # `partial=True` propagates into the nested serializers — incomplete
    # vertices/axes must still refuse (400, never a KeyError 500 or a stored
    # row the engine decode rejects later).
    serializer = ArticleWriteSerializer(data={"section": section}, partial=True)
    assert not serializer.is_valid()


def test_article_section_accepts_referenced_dxf():
    serializer = ProfileSectionSerializer(
        data={**SECTION_POLYGON, "source": "DXF_REFERENCE", "drawing_ref": "catalog.pdf#p4"}
    )
    assert serializer.is_valid(), serializer.errors


def test_engine_rejects_a_degenerate_stored_section():
    with pytest.raises(Exception):
        _section(
            '{"source": "POLYGON", "polygon": ['
            '{"x_mm": 0, "y_mm": 0}, {"x_mm": 60, "y_mm": 0}, {"x_mm": 120, "y_mm": 0}],'
            '"depth_mm": 60}'
        )


def test_section_orientation_and_origin_default_and_round_trip():
    serializer = ProfileSectionSerializer(data=SECTION_POLYGON)
    assert serializer.is_valid(), serializer.errors
    section = _section(_jsonb(serializer.validated_data))
    assert section.orientation == "EXTERIOR_DOWN"
    assert section.local_origin == "TOP_LEFT"
    serializer = ProfileSectionSerializer(
        data={
            **SECTION_POLYGON,
            "orientation": "EXTERIOR_LEFT",
            "local_origin": "CENTROID",
        }
    )
    assert serializer.is_valid(), serializer.errors
    section = _section(_jsonb(serializer.validated_data))
    assert section.orientation == "EXTERIOR_LEFT"
    assert section.local_origin == "CENTROID"


def test_section_rejects_undeclared_orientation_and_origin():
    for field, bad in (("orientation", "INSIDE_OUT"), ("local_origin", "MIDDLE")):
        serializer = ProfileSectionSerializer(data={**SECTION_POLYGON, field: bad})
        assert not serializer.is_valid()


def test_section_stamp_tracks_geometry_changes_only():
    from catalogs.service import _json_value, _stamp_section

    validated = ProfileSectionSerializer(data=SECTION_POLYGON)
    assert validated.is_valid()
    section = validated.validated_data

    values = {"section": section}
    _stamp_section(values, None, "u1")
    assert values["section_revision"] == 1
    assert values["section_revised_by"] == "u1"
    assert values["section_revised_at"] is not None

    # Identical geometry on a later write: no stamp, revision untouched.
    current = {
        "section": json.loads(_json_value(section), parse_float=Decimal),
        "section_revision": 3,
    }
    values = {"section": section}
    _stamp_section(values, current, "u2")
    assert "section_revision" not in values

    # A real shape change bumps the counter and stamps the actor.
    changed = ProfileSectionSerializer(
        data={**SECTION_POLYGON, "depth_mm": "70"}
    )
    assert changed.is_valid()
    values = {"section": changed.validated_data}
    _stamp_section(values, current, "u2")
    assert values["section_revision"] == 4
    assert values["section_revised_by"] == "u2"

    # Declaring a section where none existed starts at revision 1.
    values = {"section": section}
    _stamp_section(values, {"section": None, "section_revision": 1}, "u3")
    assert values["section_revision"] == 1


def test_section_decoder_passes_absent_and_rejects_decoded_json():
    assert _section(None) is None
    with pytest.raises(UnsupportedCatalogContract):
        _section({"source": "POLYGON"})


def test_system_accepts_nullable_fabrication_fields():
    serializer = SystemWriteSerializer(
        data={"rebate_depth_mm": "20.00", "end_milling_overlap_mm": None},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["rebate_depth_mm"] == Decimal("20.00")
    assert serializer.validated_data["end_milling_overlap_mm"] is None


@pytest.mark.parametrize(
    "field",
    ["data_provenance", "technical_reviewed_at", "technical_reviewed_by", "review_pending"],
)
@pytest.mark.parametrize(
    "serializer_type",
    [SystemWriteSerializer, ArticleWriteSerializer, KitWriteSerializer],
)
def test_write_serializers_reject_provenance_injection(serializer_type, field):
    assert not serializer_type(data={field: "injected"}, partial=True).is_valid()


def test_response_serializers_emit_provenance_triple():
    from catalogs.serializers import SystemResponseSerializer

    serializer = SystemResponseSerializer(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "org_id": "22222222-2222-2222-2222-222222222222",
            "name": "S",
            "code": "S",
            "depth_mm": "60.00",
            "material": "PVC",
            "chamber_count": 3,
            "sash_overlap_mm": "8.00",
            "glass_clearance_white_mm": "5.00",
            "glass_clearance_foil_mm": "5.00",
            "pulley_height_mm": "12.00",
            "central_overlap_mm": "3.00",
            "sliding_lateral_clearance_mm": "2.50",
            "sliding_end_add_mm": "6.00",
            "corner_bracket_loss_mm": "10.00",
            "hook_depth_mm": "12.00",
            "door_threshold_mm": "50.00",
            "door_bottom_clearance_mm": "10.00",
            "rail_type": "dual",
            "sliding_glazing_deduction_width_mm": "0.00",
            "sliding_glazing_deduction_height_mm": "0.00",
            "door_leaf_side_clearance_mm": "0.00",
            "version": 1,
            "is_active": True,
            "is_global": False,
            "is_demo": False,
            "read_only": False,
            "data_provenance": "LEGACY_UNVERIFIED",
            "technical_reviewed_at": None,
            "technical_reviewed_by": None,
            "review_pending": True,
            "readiness": {"quote_ready": False, "scope": "s", "reasons": []},
            "revision": "sha256:x",
        }
    )
    output = serializer.data
    assert output["data_provenance"] == "LEGACY_UNVERIFIED"
    assert output["technical_reviewed_at"] is None
    assert output["technical_reviewed_by"] is None
    assert output["review_pending"] is True


def test_review_requires_matching_revision(monkeypatch):
    """CAT-07: a review stamps what the reviewer read — If-Match is mandatory."""
    import catalogs.service as service
    from authentication.errors import ContractAPIException

    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "org_id": "22222222-2222-2222-2222-222222222222",
        "read_only": False,
        "revision": "sha256:current",
    }
    monkeypatch.setattr(service, "retrieve", lambda *args, **kwargs: dict(row))

    with pytest.raises(ContractAPIException) as missing:
        service.review(service.ARTICLES, row["org_id"], row["id"], row["id"])
    assert missing.value.contract_code == "catalog_stale_edit"
    assert missing.value.status_code == 409

    with pytest.raises(ContractAPIException):
        service.review(
            service.ARTICLES, row["org_id"], row["id"], row["id"],
            expected_revision='"sha256:older"',
        )


def test_bead_resource_is_reviewable():
    import catalogs.service as service

    assert service.BEADS.extra_columns == (
        "data_provenance",
        "technical_reviewed_at",
        "technical_reviewed_by",
        "review_pending",
    )


def test_engine_result_serializers_carry_unknown_weight():
    from engine_api.serializers import GlassPieceSerializer, LeafWeightSerializer

    leaf = LeafWeightSerializer(
        {
            "bay_id": "b1",
            "leaf_id": None,
            "pvc_weight_kg": None,
            "steel_weight_kg": None,
            "infill_weight_kg": "4.00",
            "hardware_weight_kg": None,
            "total_weight_kg": None,
            "weight_unknown_reasons": ["missing_profile_mass:SASH-1"],
        }
    )
    output = leaf.data
    assert output["total_weight_kg"] is None
    assert output["weight_unknown_reasons"] == ["missing_profile_mass:SASH-1"]
    assert "used_fallback" not in output

    glass = GlassPieceSerializer(
        {
            "bay_id": "b1",
            "leaf_id": None,
            "width_mm": "100.00",
            "height_mm": "100.00",
            "shape": None,
            "area_m2": "0.0100",
            "weight_kg": None,
            "thickness_net_mm": None,
            "glass_spec": "weird-spec",
            "article_sku": None,
            "exposed_edges": None,
        }
    )
    assert glass.data["weight_kg"] is None
