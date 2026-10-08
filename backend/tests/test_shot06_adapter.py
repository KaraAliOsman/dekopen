from decimal import Decimal

import pytest
from pydantic import ValidationError
from rest_framework.test import APIClient

from backend.tests.test_engine_api import configure_api
from dekopen_engine import SystemParams
from engine.tests.catalog import demo_60_params, demo_corredera_60_params
from engine.tests.test_shot06_core import core_node
from engine_api.repository import (
    SystemParamsRepository,
    UnsupportedCatalogContract,
    _decimal,
    _hardware_contents,
)


def test_json_hardware_quantities_never_pass_through_binary_float() -> None:
    contents = _hardware_contents('[{"sku":"A","name":"A","qty":0.1234567890123456789,"unit":"m"},{"sku":"B","name":"B","qty":2,"unit":"unit"}]')
    assert [p.sku for p in contents] == ["A", "B"]
    assert contents[0].qty == Decimal("0.1234567890123456789")
    assert contents[1].qty == Decimal("2")
    assert all(isinstance(p.qty, Decimal) for p in contents)


@pytest.mark.parametrize("payload", [
    '{}', '[{"sku":"A","name":"A","qty":true,"unit":"unit"}]',
    '[{"sku":"A","name":"A","qty":"NaN","unit":"unit"}]',
    '[{"sku":"A","name":"A","unit":"unit"}]',
])
def test_invalid_hardware_contents_fail_closed(payload: str) -> None:
    with pytest.raises((UnsupportedCatalogContract, ValidationError)):
        _hardware_contents(payload)


@pytest.mark.parametrize("value", [None, True, 0.1, "NaN", "Infinity"])
def test_loader_cannot_invent_or_approximate_numeric_authority(value: object) -> None:
    with pytest.raises(UnsupportedCatalogContract):
        _decimal(value)


@pytest.mark.parametrize("case,kit,weight", [
    ("G5", "KIT-SLIDING-CORR", "49.98"), ("G6", "KIT-AWNING-16", "21.70"),
    ("G7", "KIT-DOOR-MULTIPOINT", "35.81"),
])
def test_core_response_is_typed_and_complete(
    monkeypatch: pytest.MonkeyPatch, case: str, kit: str, weight: str,
) -> None:
    node = core_node(case)
    payload = {
        "system_id": "3067da09-3119-5ad0-a1d5-498cd2dfd753",
        "nominal_width_mm": str(node.width_mm), "nominal_height_mm": str(node.height_mm),
        "color": "WHITE", "parametric_tree": node.model_dump(mode="json", exclude_none=True),
    }
    client = APIClient()
    configure_api(client, monkeypatch)
    if case == "G5":
        # Sliding openings need a sliding-family system since D01.
        monkeypatch.setattr(
            SystemParamsRepository, "load_visible",
            lambda self, system_id, active_org_id: demo_corredera_60_params(),
        )
    response = client.post("/api/v1/engine/calculate/", payload, format="json")
    assert response.status_code == 200
    actual = response.json()
    assert set(actual) == {
        "profile_cuts", "reinforcements", "glasses", "panels", "hardware_items",
        "leaf_weights", "fittings", "calculation_hash",
        "finish_class", "finish_key", "finish_label", "color_surcharges",
        "extra_lines",
    }
    assert actual["hardware_items"][0]["kit_sku"] == kit
    assert actual["leaf_weights"][0]["total_weight_kg"] == weight
    assert all("material" in p and "leaf_id" in p for p in actual["profile_cuts"])
    if case == "G7":
        assert actual["glasses"] == [] and len(actual["panels"]) == 1
        assert actual["hardware_items"][0]["contents"][0]["qty"] == "1"


def test_system_params_contract_accounts_for_every_field() -> None:
    # This is transport coverage. Reserved parameters do not gain invented Core formulas.
    assert set(SystemParams.model_fields) == {
        "system_code", "depth_mm", "material", "effective_profile_articles", "glazing_bead_rules",
        "rebate_depth_mm", "end_milling_overlap_mm", "sash_overlap_mm", "glass_clearance_white_mm",
        "glass_clearance_foil_mm", "pulley_height_mm", "central_overlap_mm", "sliding_lateral_clearance_mm",
        "sliding_end_add_mm", "corner_bracket_loss_mm", "hook_depth_mm", "door_threshold_mm",
        "door_bottom_clearance_mm", "rail_type", "available_hardware_kits",
        "sliding_glazing_deduction_width_mm",
        "sliding_glazing_deduction_height_mm", "door_leaf_side_clearance_mm", "available_panel_rules",
        "rail_count", "finishes",
        "system_family", "cut_rules", "reinforcement_rules", "typology_limits",
        "glass_products", "glass_safety_rules", "glass_type_limits",
        "hardware_families", "hardware_options",
        "opening_capabilities",
        "color_options", "bicolor_allowed",
        # D06: catalog-provided accessory articles the position pass prices
        # and cuts against (extras.py inside evaluate_product).
        "extra_articles",
        # D08: clearances the advanced typologies consume from the catalog.
        "fold_guide_clearance_mm", "fold_leaf_clearance_mm", "pivot_clearance_mm",
    }
    assert len(demo_60_params().model_dump()) == 42
