from decimal import Decimal

import pytest
from pydantic import ValidationError

from dekopen_engine import BayOpeningType, MaterialType, ParametricNode, ProductModel, ProfileRole, RailType, SystemParams, calculate_geometry
from dekopen_engine.geometry import compute_geometry
from dekopen_engine.hardware import AmbiguousHardwareKit, NoCompatibleHardwareKit, normalize_opening_type, resolve_hardware_kit
from dekopen_engine.weight import ExactLeafWeight, base_leaf_weight, with_hardware_weight
from engine.tests.test_shot06_core import core_node

D = Decimal


@pytest.mark.parametrize("opening,normalized", [
    (BayOpeningType.TURN_LEFT, "TURN"), (BayOpeningType.TURN_RIGHT, "TURN"),
    (BayOpeningType.TILT_TURN_LEFT, "TILT_TURN"), (BayOpeningType.TILT_TURN_RIGHT, "TILT_TURN"),
    (BayOpeningType.SLIDING_2L, "SLIDING"), (BayOpeningType.SLIDING_3L, "SLIDING"),
    (BayOpeningType.SLIDING_4L, "SLIDING"), (BayOpeningType.DOOR_ENTRY, "DOOR"),
    (BayOpeningType.DOOR_DOUBLE, "DOOR"), (BayOpeningType.AWNING, "AWNING"),
    (BayOpeningType.FIXED, "FIXED"),
])
def test_opening_normalization(opening: BayOpeningType, normalized: str) -> None:
    assert normalize_opening_type(opening) == normalized


def test_explicit_sku_and_ambiguity_are_order_independent(
    demo_60_params: SystemParams, g3_node: ParametricNode,
) -> None:
    kit = next(k for k in demo_60_params.available_hardware_kits if k.sku == "KIT-TILT-TURN")
    alternate = kit.model_copy(update={"sku": "OTHER-OB"})
    for kits in ([kit, alternate], [alternate, kit]):
        params = demo_60_params.model_copy(update={"available_hardware_kits": kits})
        with pytest.raises(AmbiguousHardwareKit):
            calculate_geometry(g3_node, params)
        result = calculate_geometry(g3_node.model_copy(update={"hardware_set_sku": "OTHER-OB"}), params)
        assert result.hardware_items[0].kit_sku == "OTHER-OB"
    for sku in ("ABSENT", "KIT-AWNING-16"):
        with pytest.raises(NoCompatibleHardwareKit):
            calculate_geometry(g3_node.model_copy(update={"hardware_set_sku": sku}), demo_60_params)


@pytest.mark.parametrize("updates", [
    {"min_leaf_width_mm": D("896.01")}, {"max_leaf_width_mm": D("895.99")},
    {"min_leaf_height_mm": D("1296.01")}, {"max_leaf_height_mm": D("1295.99")},
    {"max_leaf_weight_kg": D("30.34")}, {"rail_type": RailType.MONO},
    {"opening_type": "TURN"},
])
def test_rejects_each_incompatible_criterion_even_with_explicit_sku(
    demo_60_params: SystemParams, g3_node: ParametricNode, updates: dict[str, object],
) -> None:
    kit = next(k for k in demo_60_params.available_hardware_kits if k.sku == "KIT-TILT-TURN")
    params = demo_60_params.model_copy(update={"available_hardware_kits": [kit.model_copy(update=updates)]})
    for node in (g3_node, g3_node.model_copy(update={"hardware_set_sku": kit.sku})):
        with pytest.raises(NoCompatibleHardwareKit):
            calculate_geometry(node, params)


def test_finished_dimensions_and_weight_limits_are_inclusive(
    demo_corredera_60_params: SystemParams,
) -> None:
    kit = next(
        k for k in demo_corredera_60_params.available_hardware_kits
        if k.sku == "KIT-SLIDING-CORR"
    )
    exact_kit = kit.model_copy(update={
        "min_leaf_width_mm": D("972.50"), "max_leaf_width_mm": D("972.50"),
        "min_leaf_height_mm": D("1966"), "max_leaf_height_mm": D("1966"),
        "max_leaf_weight_kg": D("49.98305"),
    })
    params = demo_corredera_60_params.model_copy(update={"available_hardware_kits": [exact_kit]})
    assert len(calculate_geometry(core_node("G5"), params).hardware_items) == 2
    with pytest.raises(NoCompatibleHardwareKit):
        calculate_geometry(core_node("G5"), params.model_copy(update={"available_hardware_kits": []}))


def test_capacity_uses_exact_mass_before_rounding(demo_60_params: SystemParams) -> None:
    kit = next(k for k in demo_60_params.available_hardware_kits if k.sku == "KIT-AWNING-16")
    params = demo_60_params.model_copy(update={"available_hardware_kits": [
        kit.model_copy(update={"max_leaf_weight_kg": D("21.69")}),
    ]})
    # G6 displays 21.70 but weighs exactly 21.69752, which exceeds this capacity.
    with pytest.raises(NoCompatibleHardwareKit):
        calculate_geometry(core_node("G6"), params)


def test_each_candidate_contributes_its_own_hardware_mass(demo_60_params: SystemParams) -> None:
    kit = next(k for k in demo_60_params.available_hardware_kits if k.sku == "KIT-AWNING-16")
    # 19.20 kg leaf + 26 kg of hardware exceeds the 45 kg kit capacity; the
    # 2.50 kg kit alone stays compatible.
    heavy = kit.model_copy(update={"sku": "HEAVY", "weight_kg": D("26.00")})
    params = demo_60_params.model_copy(update={"available_hardware_kits": [heavy, kit]})
    assert calculate_geometry(core_node("G6"), params).hardware_items[0].kit_sku == kit.sku


@pytest.mark.parametrize("profile_missing,steel_missing", [(False, False), (True, False), (False, True), (True, True)])
def test_article_weights_report_missing_authority_as_unknown(
    demo_60_params: SystemParams, g3_node: ParametricNode,
    profile_missing: bool, steel_missing: bool,
) -> None:
    result = calculate_geometry(g3_node, demo_60_params)
    articles = dict(demo_60_params.effective_profile_articles)
    articles[ProfileRole.SASH] = articles[ProfileRole.SASH].model_copy(update={
        "weight_kg_m": None if profile_missing else D("2.0000"),
        "steel_weight_kg_m": None if steel_missing else D("3.0000"),
    })
    params = demo_60_params.model_copy(update={"effective_profile_articles": articles})
    mass = base_leaf_weight(profile_cuts=result.profile_cuts, reinforcements=result.reinforcements,
                            infill_weight_kg=D("18.251520"), params=params)
    assert mass.pvc_weight_kg == (None if profile_missing else D("8.8160"))
    # Only the ≥1000 mm member is reinforced under the declared rule.
    assert mass.steel_weight_kg == (None if steel_missing else D("7.5960"))
    expected_reasons = ([f"missing_profile_mass:{articles[ProfileRole.SASH].sku}"] * profile_missing +
                        [f"missing_steel_mass:{articles[ProfileRole.SASH].sku}"] * steel_missing)
    assert list(mass.weight_unknown_reasons) == expected_reasons
    assert mass.total_weight_kg is None if expected_reasons else True


def test_persisted_and_missing_hardware_weights(demo_60_params: SystemParams) -> None:
    base = ExactLeafWeight(D("5"), D("7"), D("18"))
    kit = demo_60_params.available_hardware_kits[0]
    persisted = with_hardware_weight(base, kit, demo_60_params)
    missing = with_hardware_weight(base, kit.model_copy(update={"weight_kg": None}), demo_60_params)
    assert persisted.hardware_weight_kg == D("2.50") and persisted.weight_unknown_reasons == ()
    assert missing.hardware_weight_kg is None
    assert missing.weight_unknown_reasons == (f"missing_hardware_mass:{kit.sku}",)
    cap_kit = kit.model_copy(update={"max_leaf_weight_kg": D("32.60"), "weight_kg": None})
    with pytest.raises(NoCompatibleHardwareKit):
        resolve_hardware_kit(opening_group="TURN", opening_label="TURN_LEFT", width_mm=D("800"), height_mm=D("1200"),
                             base_weight=base, params=demo_60_params.model_copy(update={"available_hardware_kits": [cap_kit]}))


def test_missing_infill_authority_surfaces_unknown_mass(
    demo_60_params: SystemParams, g3_node: ParametricNode,
) -> None:
    # Strict mode refuses: the compatibility decision cannot be certified.
    panels = {sku: p.model_copy(update={"weight_kg_m2": None}) for sku, p in demo_60_params.available_panel_rules.items()}
    with pytest.raises(NoCompatibleHardwareKit, match="undecidable.*missing_panel_mass"):
        calculate_geometry(core_node("G7"), demo_60_params.model_copy(update={"available_panel_rules": panels}))
    # Diagnostic mode degrades: the computation is invalid and the leaf's
    # technical facts carry the UNKNOWN mass + the missing authority's name.
    computation = compute_geometry(
        core_node("G7"), demo_60_params.model_copy(update={"available_panel_rules": panels}),
        diagnostic=True,
    )
    assert computation.result is None  # contract invalid → no certified BOM
    base = computation.leaves[0].base_weight
    assert base.total_weight_kg is None
    assert base.infill_weight_kg is None
    assert "missing_panel_mass:PANEL-SANDWICH-DEMO-24" in base.weight_unknown_reasons
    with pytest.raises(ValueError, match="requires panel_article_sku"):
        calculate_geometry(core_node("G7").model_copy(update={"panel_article_sku": None}), demo_60_params)
    # A non-PVC article without declared mass reports the same authority gap.
    result = calculate_geometry(g3_node, demo_60_params)
    articles = dict(demo_60_params.effective_profile_articles)
    articles[ProfileRole.SASH] = articles[ProfileRole.SASH].model_copy(update={"weight_kg_m": None, "material": MaterialType.ALUMINIUM})
    mass = base_leaf_weight(profile_cuts=result.profile_cuts, reinforcements=result.reinforcements,
                            infill_weight_kg=D("18.251520"), params=demo_60_params.model_copy(update={"effective_profile_articles": articles}))
    assert mass.pvc_weight_kg is None
    assert list(mass.weight_unknown_reasons) == [f"missing_profile_mass:{articles[ProfileRole.SASH].sku}"]


def test_total_rounds_once_half_up_and_excludes_static_bom(demo_60_params: SystemParams) -> None:
    exact = ExactLeafWeight(D("1.004"), D("2.004"), D("3.004"), D("4.003"))
    public = exact.public_result("test", None)
    assert public.total_weight_kg == D("10.02")
    components = (
        public.pvc_weight_kg, public.steel_weight_kg,
        public.infill_weight_kg, public.hardware_weight_kg,
    )
    assert all(component is not None for component in components)
    assert sum(
        (component for component in components if component is not None),
        D("0"),
    ) == D("10.00")
    baseline = calculate_geometry(core_node("G7"), demo_60_params)
    # Frame/bead/threshold masses are static-BOM facts and never enter the
    # leaf total — leaf roles (SASH/DOOR_SASH here) do, by definition.
    _leaf_roles = {
        ProfileRole.SASH, ProfileRole.SLIDING_SASH,
        ProfileRole.INTERLOCK, ProfileRole.DOOR_SASH,
    }
    articles = {role: article.model_copy(update={"weight_kg_m": D("9999")})
                if role not in _leaf_roles else article
                for role, article in demo_60_params.effective_profile_articles.items()}
    beads = {t: rule.model_copy(update={"bead_article": rule.bead_article.model_copy(update={"weight_kg_m": D("9999")})})
             for t, rule in demo_60_params.glazing_bead_rules.items()}
    changed = calculate_geometry(core_node("G7"), demo_60_params.model_copy(update={"effective_profile_articles": articles, "glazing_bead_rules": beads}))
    assert changed.leaf_weights == baseline.leaf_weights


@pytest.mark.parametrize("field", ["sliding_glazing_deduction_width_mm", "sliding_glazing_deduction_height_mm"])
def test_missing_sliding_authority_is_rejected(
    demo_corredera_60_params: SystemParams, field: str,
) -> None:
    # Sliding families cannot be constructed without their deductions (D01).
    values = demo_corredera_60_params.model_dump()
    del values[field]
    with pytest.raises(ValidationError, match="sliding_glazing_deduction"):
        SystemParams.model_validate(values)


def test_missing_door_authority_is_rejected(demo_60_params: SystemParams) -> None:
    # Optional on the contract (casement-only series never declare it); the
    # engine refuses when a door actually needs the value.
    from dekopen_engine.weight import MissingFabricationAuthority

    params = demo_60_params.model_copy(update={"door_leaf_side_clearance_mm": None})
    with pytest.raises(MissingFabricationAuthority, match="door_leaf_side_clearance_mm"):
        calculate_geometry(core_node("G7"), params)


def _assembly_product(width_mm: str, opening: BayOpeningType) -> ProductModel:
    from dekopen_engine.models import NodeType

    return ProductModel.model_validate(
        {
            "version": "product-v2",
            "assembly": {
                "modules": [
                    {
                        "id": "m1",
                        "width_mm": D(width_mm),
                        "height_mm": D("1400"),
                        "tree": ParametricNode.model_validate(
                            {
                                "id": "B1",
                                "type": NodeType.BAY,
                                "opening_type": opening,
                                "glass_spec": "4-16-4",
                                "glass_thickness_mm": D("24"),
                                "glass_article_sku": "DVH-4-16-4",
                            }
                        ),
                    }
                ],
                "couplings": [],
            },
        }
    )


def test_undersized_leaf_emits_typed_hardware_issue_with_envelope(
    demo_60_params: SystemParams,
) -> None:
    """The designer-report defect: a leaf under the kit's minimum width must
    surface as a typed issue naming the real envelope — not an opaque
    "revisa los parámetros" geometry failure."""
    from dekopen_engine.product import evaluate_product

    evaluation = evaluate_product(
        _assembly_product("300", BayOpeningType.TILT_TURN_LEFT), demo_60_params
    )
    issue = next(
        item for item in evaluation.issues if item.code == "hardware_kit_incompatible"
    )
    assert issue.severity.value == "error"
    assert issue.target == "module:m1"
    assert issue.params["axis"] == "size"
    assert issue.params["kit_min_width_mm"] == "450"
    assert issue.params["kit_max_width_mm"] == "1400"
    assert issue.params["kit_min_height_mm"] == "600"
    assert issue.params["kit_max_height_mm"] == "2400"
    assert issue.params["opening"] == "TILT_TURN_LEFT"
    assert D(issue.params["leaf_width_mm"]) < D("450")


def test_opening_mismatch_without_kit_stays_a_reasoned_failure(
    demo_60_params: SystemParams,
) -> None:
    """No opening+rail match at all → no dimensional envelope to cite; the
    issue falls back to module_geometry_failed with the reason param."""
    from dekopen_engine.product import evaluate_product

    only_sliding = demo_60_params.model_copy(
        update={
            "available_hardware_kits": [
                kit for kit in demo_60_params.available_hardware_kits if kit.sku == "KIT-SLIDING"
            ]
        }
    )
    evaluation = evaluate_product(
        _assembly_product("900", BayOpeningType.TILT_TURN_LEFT), only_sliding
    )
    issue = next(item for item in evaluation.issues if item.code == "module_geometry_failed")
    assert "No compatible hardware kit" in issue.params["reason"]
