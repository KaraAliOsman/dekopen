"""D01 golden coverage: fabrication families, declared cut rules,
reinforcement as data, and per-typology dimensional limits.

Every assertion here is catalog-behaviour the engine only executes: the
rule tables are data, the tests freeze the deterministic outcomes.
"""

from decimal import Decimal as D

import pytest

from dekopen_engine.geometry import (
    DimensionalLimitError,
    IncompatibleTypologyError,
    calculate_geometry,
    compute_geometry,
)
from dekopen_engine.models import (
    EngineResult,
    ParametricNode,
    BayOpeningType,
    FAMILY_OPENINGS,
    ProfileCutRule,
    ProfileRole,
    ReinforcementRule,
    SystemFamily,
    SystemParams,
    openings_for_family,
)
from dekopen_engine.product import IssueCode, evaluate_product
from engine.tests.test_shot06_core import core_node


def _sliding_node() -> ParametricNode:
    """The frozen sliding reference: G5, a 2 000 × 2 100 2-leaf corredera."""
    return core_node("G5")


# ---------------------------------------------------------------------
# Family ↔ typology compatibility
# ---------------------------------------------------------------------


def test_family_opening_sets_cover_the_declared_universe() -> None:
    # Every family can build a fixed lite; every opening belongs somewhere.
    union: set[BayOpeningType] = set()
    for family, openings in FAMILY_OPENINGS.items():
        assert BayOpeningType.FIXED in openings
        union |= set(openings)
    assert union == set(BayOpeningType)
    assert BayOpeningType.SLIDING in FAMILY_OPENINGS[SystemFamily.SLIDING]
    assert BayOpeningType.SLIDING_2L not in FAMILY_OPENINGS[SystemFamily.CASEMENT]
    assert BayOpeningType.TURN_LEFT not in FAMILY_OPENINGS[SystemFamily.SLIDING]


def test_openings_for_family_returns_the_catalogue_set() -> None:
    assert openings_for_family(SystemFamily.DOOR) == frozenset(
        {BayOpeningType.FIXED, BayOpeningType.DOOR_ENTRY, BayOpeningType.DOOR_DOUBLE}
    )


def test_casement_system_rejects_sliding_typology_in_spanish(
    demo_60_params: SystemParams,
) -> None:
    with pytest.raises(IncompatibleTypologyError) as excinfo:
        calculate_geometry(core_node("G5"), demo_60_params)
    error = excinfo.value
    assert error.code == "typology_family_incompatible"
    assert "incompatible" in str(error)
    assert "SLIDING_2L" in error.params["opening"]
    # The message names the families that CAN fabricate the typology.
    assert "SLIDING" in error.params["compatible_families"]
    assert "sistemas compatibles" in str(error)


def test_aluminium_casement_also_rejects_sliding(alu_65_params: SystemParams) -> None:
    with pytest.raises(IncompatibleTypologyError):
        calculate_geometry(core_node("G5"), alu_65_params)


def test_sliding_system_rejects_hinged_leaf(
    demo_corredera_60_params: SystemParams,
) -> None:
    with pytest.raises(IncompatibleTypologyError):
        calculate_geometry(core_node("G6"), demo_corredera_60_params)


def test_product_evaluation_surfaces_incompatibility_as_issue(
    demo_60_params: SystemParams,
) -> None:
    from dekopen_engine.models import NodeType, ParametricNode
    from dekopen_engine.product import (
        CoupledAssembly,
        ProductModel,
        ProductModule,
    )

    product = ProductModel(
        version="product-v2",
        assembly=CoupledAssembly(
            modules=[
                ProductModule(
                    id="m",
                    width_mm=D("1800"),
                    height_mm=D("1500"),
                    tree=ParametricNode(
                        id="m",
                        type=NodeType.BAY,
                        opening_type=BayOpeningType.SLIDING_2L,
                        glass_thickness_mm=D("20.00"),
                        glass_spec="4-12-4",
                    ),
                )
            ],
            couplings=[],
        ),
    )
    evaluation = evaluate_product(product, demo_60_params)
    module = evaluation.modules[0]
    assert module.result is None
    assert [i.code for i in module.issues] == [
        IssueCode.TYPOLOGY_FAMILY_INCOMPATIBLE.value
    ]
    assert module.issues[0].params["family"] == "CASEMENT"


# ---------------------------------------------------------------------
# Declared cut rules — golden per role on both casement systems + sliding
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "role", "angle", "welded"),
    [
        ("G6", ProfileRole.FRAME, D("45"), 2),
        ("G6", ProfileRole.SASH, D("45"), 2),
        ("G7", ProfileRole.DOOR_SASH, D("45"), 2),
        ("G7", ProfileRole.THRESHOLD, D("90"), None),
        ("G6", ProfileRole.GLAZING_BEAD, D("45"), None),
    ],
)
def test_demo_60_declared_cut_rules_match_the_cuts(
    demo_60_params: SystemParams, case: str, role: ProfileRole, angle: D, welded: int | None
) -> None:
    result = calculate_geometry(core_node(case), demo_60_params)
    cuts = [c for c in result.profile_cuts if c.role is role]
    assert cuts, f"no cuts for {role}"
    declared = demo_60_params.cut_rules[role]
    for cut in cuts:
        assert cut.angle_left == declared.cut_angle_deg
        assert cut.angle_right == declared.cut_angle_deg
        if role is ProfileRole.GLAZING_BEAD or role is ProfileRole.THRESHOLD:
            continue
        assert declared.welded_ends == welded


def _alu_turn_node(width: str) -> ParametricNode:
    """800 × 1 200 practicable leaf with ALU 24 mm termopanel."""
    from dekopen_engine.models import NodeType, ParametricNode

    return ParametricNode(
        id="alu",
        type=NodeType.BAY,
        width_mm=D(width),
        height_mm=D("1200.00"),
        opening_type=BayOpeningType.TURN_LEFT,
        glass_thickness_mm=D("24.00"),
        glass_spec="4-16-4",
        glass_article_sku="DVH-24",
    )


def test_alu_65_cut_rules_are_mechanical_not_welded(alu_65_params: SystemParams) -> None:
    assert all(
        rule.welded_ends is None for rule in alu_65_params.cut_rules.values()
    )
    result = calculate_geometry(_alu_turn_node("800.00"), alu_65_params)
    for role in (ProfileRole.FRAME, ProfileRole.SASH):
        assert all(
            c.angle_left == D("45") for c in result.profile_cuts if c.role is role
        )


def test_corredera_cut_rules_cover_every_declared_sliding_role(
    demo_corredera_60_params: SystemParams,
) -> None:
    declared = demo_corredera_60_params.cut_rules
    assert declared[ProfileRole.RAIL].welded_ends == 2
    assert declared[ProfileRole.INTERLOCK].interlock_deduction_mm == D("18.00")
    result = calculate_geometry(_sliding_node(), demo_corredera_60_params)
    rail_cuts = [c for c in result.profile_cuts if c.role is ProfileRole.RAIL]
    assert rail_cuts and all(c.angle_left == D("45") for c in rail_cuts)


def test_interlock_deduction_shortens_meeting_stile(
    demo_corredera_60_params: SystemParams,
) -> None:
    result = calculate_geometry(_sliding_node(), demo_corredera_60_params)
    sash_verticals = sorted(
        c.length_mm for c in result.profile_cuts if c.role is ProfileRole.SLIDING_SASH
    )
    interlocks = sorted(
        c.length_mm for c in result.profile_cuts if c.role is ProfileRole.INTERLOCK
    )
    deduction = demo_corredera_60_params.cut_rules[
        ProfileRole.INTERLOCK
    ].interlock_deduction_mm
    assert interlocks == [sash_verticals[-1] - deduction, sash_verticals[-1] - deduction]


def test_rounding_rule_quantizes_the_cut(demo_60_params: SystemParams) -> None:
    params = demo_60_params.model_copy(
        update={
            "cut_rules": {
                **demo_60_params.cut_rules,
                ProfileRole.FRAME: ProfileCutRule(
                    role=ProfileRole.FRAME,
                    cut_angle_deg=D("45.0"),
                    welded_ends=2,
                    rounding_mm=D("5.00"),
                ),
            }
        }
    )
    result = calculate_geometry(core_node("G6"), params)
    frame_cuts = [c for c in result.profile_cuts if c.role is ProfileRole.FRAME]
    assert frame_cuts
    for cut in frame_cuts:
        assert cut.length_mm % D("5.00") == 0
    base = calculate_geometry(core_node("G6"), demo_60_params)
    base_frames = sorted(c.length_mm for c in base.profile_cuts if c.role is ProfileRole.FRAME)
    rounded = sorted(c.length_mm for c in frame_cuts)
    for raw, quantized in zip(base_frames, rounded, strict=True):
        assert quantized >= raw
        assert quantized - raw < D("5.00")


# ---------------------------------------------------------------------
# Reinforcement as data — finish class + length decide, never code
# ---------------------------------------------------------------------


def _steel(result: EngineResult, role: ProfileRole) -> list[D]:
    return sorted(p.length_mm for p in result.reinforcements if p.role is role)


def _small_leaf() -> ParametricNode:
    """900 × 700 leaf whose every member is under the 1 000 mm WHITE minimum."""
    from dekopen_engine.models import NodeType, ParametricNode

    return ParametricNode(
        id="small",
        type=NodeType.BAY,
        width_mm=D("900.00"),
        height_mm=D("700.00"),
        opening_type=BayOpeningType.TURN_LEFT,
        glass_thickness_mm=D("20.00"),
        glass_spec="4-12-4",
    )


def test_white_short_member_stays_unreinforced(demo_60_params: SystemParams) -> None:
    # Every member of a 900 × 700 leaf is < 1 000 mm → the WHITE rule never
    # fires; the whole piece ships without steel.
    result = calculate_geometry(_small_leaf(), demo_60_params)
    assert result.reinforcements == []


def test_foiled_same_member_is_always_reinforced(demo_60_params: SystemParams) -> None:
    white = calculate_geometry(_small_leaf(), demo_60_params)
    assert white.reinforcements == []
    foiled = calculate_geometry(_small_leaf(), demo_60_params, is_foiled=True)
    # NON_WHITE min_length 0: the exact same leaf is fully reinforced.
    assert _steel(foiled, ProfileRole.SASH) != []
    assert _steel(foiled, ProfileRole.FRAME) != []


def test_white_long_member_is_reinforced(demo_60_params: SystemParams) -> None:
    # G7 door leaf verticals exceed 1 m → WHITE rule fires.
    result = calculate_geometry(core_node("G7"), demo_60_params)
    assert _steel(result, ProfileRole.DOOR_SASH) != []


def test_reinforcement_screws_land_in_bom(demo_60_params: SystemParams) -> None:
    result = calculate_geometry(core_node("G7"), demo_60_params)
    screws = [f for f in result.fittings if f.sku == "TORNILLO-4X16"]
    assert screws, "declared screws_per_m must emit REINFORCEMENT_SCREW pieces"
    assert all(s.qty > 0 for s in screws)


def test_cut_deduction_shortens_steel_not_profile(
    demo_60_params: SystemParams,
) -> None:
    def with_deduction(deduction: D) -> list[D]:
        params = demo_60_params.model_copy(
            update={
                "reinforcement_rules": [
                    ReinforcementRule(
                        role=ProfileRole.DOOR_SASH,
                        finish_class="WHITE",
                        min_length_mm=D("0"),
                        cut_deduction_mm=deduction,
                    )
                ]
            }
        )
        return _steel(
            calculate_geometry(core_node("G7"), params), ProfileRole.DOOR_SASH
        )

    plain = with_deduction(D("0"))
    deducted = with_deduction(D("10.00"))
    assert deducted == [length - D("10.00") for length in plain]
    # The profile member keeps its full length; only the steel shortens.
    assert plain


def test_no_declared_rule_keeps_legacy_unconditional_steel() -> None:
    from engine.tests.catalog import demo_60_params as _d

    params = _d().model_copy(update={"reinforcement_rules": []})
    result = calculate_geometry(core_node("G6"), params)
    assert _steel(result, ProfileRole.SASH) != []


# ---------------------------------------------------------------------
# Dimensional limits per system × typology
# ---------------------------------------------------------------------


def _wide_turn_leaf(width: str) -> ParametricNode:
    from dekopen_engine.models import NodeType, ParametricNode

    return ParametricNode(
        id="w",
        type=NodeType.BAY,
        width_mm=D(width),
        height_mm=D("1500.00"),
        opening_type=BayOpeningType.TURN_LEFT,
        glass_thickness_mm=D("20.00"),
        glass_spec="4-12-4",
    )


def _params_with_wide_kit(demo_60_params: SystemParams) -> SystemParams:
    """Hardware envelope relaxed so the *declared typology limit* is the
    bound that actually rejects — kits no longer veto first."""
    kits = [
        kit.model_copy(
            update={
                "min_leaf_width_mm": D("50.00"),
                "max_leaf_width_mm": D("5000.00"),
                "min_leaf_height_mm": D("50.00"),
                "max_leaf_height_mm": D("5000.00"),
            }
        )
        for kit in demo_60_params.available_hardware_kits
    ]
    return demo_60_params.model_copy(update={"available_hardware_kits": kits})


def test_oversized_leaf_is_rejected_with_limit_details(
    demo_60_params: SystemParams,
) -> None:
    params = _params_with_wide_kit(demo_60_params)
    node = _wide_turn_leaf("1600.00")  # leaf > 1 400 max
    with pytest.raises(DimensionalLimitError) as excinfo:
        calculate_geometry(node, params)
    error = excinfo.value
    assert error.code == "leaf_dimensional_limit"
    assert error.params["opening"] == "TURN_LEFT"
    assert "max_leaf_width_mm" in error.params["violations"]


def test_undersized_leaf_is_rejected_too(demo_60_params: SystemParams) -> None:
    params = _params_with_wide_kit(demo_60_params)
    node = _wide_turn_leaf("400.00")  # 400 mm bay → leaf ~290 mm < 350 min
    with pytest.raises(DimensionalLimitError):
        calculate_geometry(node, params)


def test_declared_bounds_are_inclusive(demo_60_params: SystemParams) -> None:
    # Derive a node whose finished leaf lands exactly on the declared max.
    node = _wide_turn_leaf("1200.00")
    computation = compute_geometry(node, demo_60_params)
    finished = computation.leaves[0].finished_width_mm
    limit = demo_60_params.typology_limits["TURN_LEFT"].model_copy(
        update={"max_leaf_width_mm": None}
    )
    params_at = demo_60_params.model_copy(
        update={
            "typology_limits": {
                **demo_60_params.typology_limits,
                "TURN_LEFT": limit.model_copy(update={"max_leaf_width_mm": finished}),
            }
        }
    )
    assert calculate_geometry(node, params_at) is not None
    params_below = demo_60_params.model_copy(
        update={
            "typology_limits": {
                **demo_60_params.typology_limits,
                "TURN_LEFT": limit.model_copy(
                    update={"max_leaf_width_mm": finished - D("0.01")}
                ),
            }
        }
    )
    with pytest.raises(DimensionalLimitError):
        calculate_geometry(node, params_below)


def test_alu_65_enforces_its_own_tighter_limits(alu_65_params: SystemParams) -> None:
    # Leaf ~1 092 mm: inside KIT-A-TURN's 1 100 envelope but past ALU_65's
    # declared 1 000 mm TURN maximum — the catalog limit, not hardware, rejects.
    node = _alu_turn_node("1190.00")
    with pytest.raises(DimensionalLimitError):
        calculate_geometry(node, alu_65_params)


def test_system_without_declared_limit_computes(
    demo_corredera_60_params: SystemParams,
) -> None:
    # No TILT_TURN limit declared on the sliding fixture — and its family
    # rejects the typology anyway. G5 stays computable because sliding
    # limits were declared for it.
    result = calculate_geometry(_sliding_node(), demo_corredera_60_params)
    assert result is not None
