from __future__ import annotations

from decimal import Decimal
import json

from dekopen_engine import (
    EffectiveProfileArticle,
    MaterialType,
    ProfileRole,
    SystemParams,
    calculate_geometry,
    welding_loss_per_end,
)
from dekopen_engine.models import ParametricNode


def test_system_params_contract_has_exactly_30_fields() -> None:
    assert len(SystemParams.model_fields) == 30
    assert "frame_face_width_mm" not in SystemParams.model_fields
    assert "sash_face_width_mm" not in SystemParams.model_fields
    assert "mullion_face_width_mm" not in SystemParams.model_fields
    assert "steel_gap_corner_mm" not in SystemParams.model_fields
    assert "steel_gap_mullion_mm" not in SystemParams.model_fields
    assert "finishes" in SystemParams.model_fields
    # No fabricated weight authorities may ever reappear.
    assert "pvc_weight_kg_m" not in SystemParams.model_fields
    assert "steel_weight_kg_m" not in SystemParams.model_fields
    assert "hardware_kit_weight_kg" not in SystemParams.model_fields


def test_welding_loss_is_derived_independently_per_effective_article() -> None:
    frame = EffectiveProfileArticle(
        sku="FRAME-ASYM",
        material=MaterialType.PVC,
        role=ProfileRole.FRAME,
        face_width_mm=Decimal("60.00"),
        welding_loss_mm=Decimal("6.00"),
        reinforcement_gap_mm=Decimal("15.00"),
        weight_kg_m=Decimal("1.2000"),
        steel_weight_kg_m=Decimal("1.7000"),
    )
    sash = EffectiveProfileArticle(
        sku="SASH-ASYM",
        material=MaterialType.PVC,
        role=ProfileRole.SASH,
        face_width_mm=Decimal("75.00"),
        welding_loss_mm=Decimal("5.00"),
        reinforcement_gap_mm=Decimal("12.00"),
        weight_kg_m=Decimal("1.2000"),
        steel_weight_kg_m=Decimal("1.7000"),
    )

    assert welding_loss_per_end(frame) == Decimal("3.00")
    assert welding_loss_per_end(sash) == Decimal("2.50")


def test_engine_result_is_json_serializable(
    demo_60_params: SystemParams,
    g1_node: ParametricNode,
) -> None:
    result = calculate_geometry(g1_node, demo_60_params)
    payload = json.loads(result.model_dump_json())

    assert isinstance(payload["profile_cuts"], list)
    assert isinstance(payload["reinforcements"], list)
    assert isinstance(payload["glasses"], list)
    assert payload["hardware_items"] == []
    assert payload["profile_cuts"][0]["length_mm"] == "1006.00"


def test_one_calculation_preserves_asymmetric_frame_and_sash_welding(
    demo_60_params: SystemParams,
    g2_node: ParametricNode,
) -> None:
    articles = dict(demo_60_params.effective_profile_articles)
    articles[ProfileRole.SASH] = articles[ProfileRole.SASH].model_copy(
        update={"welding_loss_mm": Decimal("5.00")}
    )
    asymmetric_params = demo_60_params.model_copy(update={"effective_profile_articles": articles})

    result = calculate_geometry(g2_node, asymmetric_params)
    frame_lengths = sorted(
        cut.length_mm for cut in result.profile_cuts if cut.role is ProfileRole.FRAME
    )
    sash_lengths = sorted(
        cut.length_mm for cut in result.profile_cuts if cut.role is ProfileRole.SASH
    )

    assert frame_lengths == [Decimal("806.00"), Decimal("1206.00")]
    assert sash_lengths == [Decimal("701.00"), Decimal("1101.00")]


def test_glazing_bead_cut_uses_selected_rule_instead_of_a_hardcoded_addition(
    demo_60_params: SystemParams,
    g1_node: ParametricNode,
) -> None:
    rules = dict(demo_60_params.glazing_bead_rules)
    rules[Decimal("4.00")] = rules[Decimal("4.00")].model_copy(
        update={"cut_add_mm": Decimal("7.00")}
    )
    params = demo_60_params.model_copy(update={"glazing_bead_rules": rules})

    result = calculate_geometry(g1_node, params)
    bead_lengths = sorted(
        cut.length_mm for cut in result.profile_cuts if cut.role is ProfileRole.GLAZING_BEAD
    )

    assert bead_lengths == [Decimal("917.00"), Decimal("917.00")]
