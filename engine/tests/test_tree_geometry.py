from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine import (
    BayOpeningType,
    NodeType,
    ParametricNode,
    ProfileRole,
    SystemParams,
    calculate_geometry,
)


def _fixed_bay(bay_id: str) -> ParametricNode:
    return ParametricNode(
        id=bay_id,
        type=NodeType.BAY,
        opening_type=BayOpeningType.FIXED,
        glass_thickness_mm=Decimal("4.00"),
        glass_spec="4",
    )


def test_root_wrapper_normalizes_without_changing_semantics(
    demo_60_params: SystemParams,
    g1_node: ParametricNode,
) -> None:
    wrapper = ParametricNode(
        id="root",
        type=NodeType.ROOT,
        width_mm=Decimal("1000.00"),
        height_mm=Decimal("1000.00"),
        children=[g1_node.model_copy(update={"width_mm": None, "height_mm": None})],
    )

    direct = calculate_geometry(g1_node, demo_60_params)
    wrapped = calculate_geometry(wrapper, demo_60_params)

    assert wrapped == direct


def test_horizontal_mullion_uses_parent_clear_width_and_article_gap(
    demo_60_params: SystemParams,
) -> None:
    split = ParametricNode(
        id="horizontal_split",
        type=NodeType.SPLIT_H,
        width_mm=Decimal("1000.00"),
        height_mm=Decimal("1000.00"),
        split_offset_mm=Decimal("500.00"),
        mullion_profile_sku="POSTE-H",
        children=[_fixed_bay("top"), _fixed_bay("bottom")],
    )

    result = calculate_geometry(split, demo_60_params)
    mullion = [
        cut for cut in result.profile_cuts if cut.role is ProfileRole.MULLION_H
    ]
    reinforcement = [
        piece
        for piece in result.reinforcements
        if piece.role is ProfileRole.MULLION_H
    ]

    assert len(mullion) == 1
    assert mullion[0].length_mm == Decimal("880.00")
    # 880 mm stays bare under the declared white-member rule (steel ≥ 1000 mm).
    assert reinforcement == []


def test_child_dimensions_cannot_become_a_second_authority(
    demo_60_params: SystemParams,
) -> None:
    child_with_dimensions = _fixed_bay("left").model_copy(
        update={"width_mm": Decimal("1.00"), "height_mm": Decimal("1.00")}
    )
    split = ParametricNode(
        id="invalid_split",
        type=NodeType.SPLIT_V,
        width_mm=Decimal("1000.00"),
        height_mm=Decimal("1000.00"),
        split_offset_mm=Decimal("500.00"),
        mullion_profile_sku="POSTE-V",
        children=[child_with_dimensions, _fixed_bay("right")],
    )

    with pytest.raises(ValueError, match="dimensions are derived"):
        calculate_geometry(split, demo_60_params)


def test_bom_output_order_is_deterministic(
    demo_60_params: SystemParams,
    g4_node: ParametricNode,
) -> None:
    first = calculate_geometry(g4_node, demo_60_params)
    second = calculate_geometry(g4_node, demo_60_params)

    assert first.model_dump() == second.model_dump()
    assert [cut.role for cut in first.profile_cuts] == [
        ProfileRole.FRAME,
        ProfileRole.FRAME,
        ProfileRole.MULLION_V,
        ProfileRole.SASH,
        ProfileRole.SASH,
        ProfileRole.GLAZING_BEAD,
        ProfileRole.GLAZING_BEAD,
        ProfileRole.GLAZING_BEAD,
        ProfileRole.GLAZING_BEAD,
    ]
