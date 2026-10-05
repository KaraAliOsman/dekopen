from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine import (
    EngineResult,
    ParametricNode,
    ProfileRole,
    SystemParams,
    calculate_geometry,
)


def _assert_exact_mm(actual: Decimal, expected: str) -> None:
    discrepancy_mm = abs(actual - Decimal(expected))
    assert discrepancy_mm == Decimal("0.00"), (
        f"expected {expected} mm, got {actual} mm; discrepancy={discrepancy_mm} mm"
    )


def _profile_lengths(result: EngineResult, role: ProfileRole) -> list[Decimal]:
    return sorted(cut.length_mm for cut in result.profile_cuts if cut.role is role)


def _reinforcement_lengths(result: EngineResult, role: ProfileRole) -> list[Decimal]:
    return sorted(
        piece.length_mm for piece in result.reinforcements if piece.role is role
    )


def test_g1_fixed_is_exactly_zero_mm(
    demo_60_params: SystemParams,
    g1_node: ParametricNode,
) -> None:
    result = calculate_geometry(g1_node, demo_60_params)

    frame_lengths = _profile_lengths(result, ProfileRole.FRAME)
    assert len(frame_lengths) == 2
    for actual in frame_lengths:
        _assert_exact_mm(actual, "1006.00")
    frame_steel = _reinforcement_lengths(result, ProfileRole.FRAME)
    assert len(frame_steel) == 2
    for actual in frame_steel:
        _assert_exact_mm(actual, "970.00")
    glass = result.glasses[0]
    _assert_exact_mm(glass.width_mm, "910.00")
    _assert_exact_mm(glass.height_mm, "910.00")
    bead_lengths = _profile_lengths(result, ProfileRole.GLAZING_BEAD)
    assert len(bead_lengths) == 2
    for actual in bead_lengths:
        _assert_exact_mm(actual, "919.00")
    frame_cuts = [cut for cut in result.profile_cuts if cut.role is ProfileRole.FRAME]
    assert all(cut.sku == "MARCO" and cut.qty == 2 for cut in frame_cuts)
    assert all(
        cut.angle_left == Decimal("45.0") and cut.angle_right == Decimal("45.0")
        for cut in frame_cuts
    )
    bead_cuts = [
        cut for cut in result.profile_cuts if cut.role is ProfileRole.GLAZING_BEAD
    ]
    assert all(cut.sku == "JQ-24" and cut.bay_id == "g1" for cut in bead_cuts)
    assert result.hardware_items == []


def test_g2_turn_is_exactly_zero_mm(
    demo_60_params: SystemParams,
    g2_node: ParametricNode,
) -> None:
    result = calculate_geometry(g2_node, demo_60_params)

    sash_lengths = _profile_lengths(result, ProfileRole.SASH)
    _assert_exact_mm(sash_lengths[0], "702.00")
    _assert_exact_mm(sash_lengths[1], "1102.00")
    # The declared white-member rule reinforces only members ≥ 1000 mm: the
    # 702 mm horizontal stays bare.
    sash_steel = _reinforcement_lengths(result, ProfileRole.SASH)
    assert len(sash_steel) == 1
    _assert_exact_mm(sash_steel[0], "1066.00")
    glass = result.glasses[0]
    _assert_exact_mm(glass.width_mm, "576.00")
    _assert_exact_mm(glass.height_mm, "976.00")
    assert len(result.hardware_items) == 1


def test_g3_tilt_turn_geometry_is_exactly_zero_mm(
    demo_60_params: SystemParams,
    g3_node: ParametricNode,
) -> None:
    result = calculate_geometry(g3_node, demo_60_params)

    sash_lengths = _profile_lengths(result, ProfileRole.SASH)
    _assert_exact_mm(sash_lengths[0], "902.00")
    _assert_exact_mm(sash_lengths[1], "1302.00")
    glass = result.glasses[0]
    _assert_exact_mm(glass.width_mm, "776.00")
    _assert_exact_mm(glass.height_mm, "1176.00")
    assert len(result.hardware_items) == 1


def test_g4_fixed_tilt_turn_with_mullion_is_exactly_zero_mm(
    demo_60_params: SystemParams,
    g4_node: ParametricNode,
) -> None:
    result = calculate_geometry(g4_node, demo_60_params)

    mullion_lengths = _profile_lengths(result, ProfileRole.MULLION_V)
    assert len(mullion_lengths) == 1
    _assert_exact_mm(mullion_lengths[0], "1380.00")
    mullion_steel = _reinforcement_lengths(result, ProfileRole.MULLION_V)
    assert len(mullion_steel) == 1
    _assert_exact_mm(mullion_steel[0], "1370.00")

    glasses = {glass.bay_id: glass for glass in result.glasses}
    _assert_exact_mm(glasses["bay_fixed"].width_mm, "830.00")
    _assert_exact_mm(glasses["bay_fixed"].height_mm, "1410.00")
    _assert_exact_mm(glasses["bay_ob"].width_mm, "696.00")
    _assert_exact_mm(glasses["bay_ob"].height_mm, "1276.00")
    mullion_cut = next(
        cut for cut in result.profile_cuts if cut.role is ProfileRole.MULLION_V
    )
    assert mullion_cut.sku == "POSTE-V"
    assert mullion_cut.qty == 1
    assert mullion_cut.angle_left == Decimal("90.0")
    assert mullion_cut.angle_right == Decimal("90.0")
    sash_cuts = [cut for cut in result.profile_cuts if cut.role is ProfileRole.SASH]
    assert all(cut.bay_id == "bay_ob" for cut in sash_cuts)
    assert len(result.hardware_items) == 1


def test_exact_assertion_rejects_a_point_zero_one_mm_mutation() -> None:
    with pytest.raises(AssertionError):
        _assert_exact_mm(Decimal("1006.01"), "1006.00")
