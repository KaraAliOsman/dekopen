"""Owner-approved Inspector boundaries; synthetic facts never activate geometry gates."""

from dataclasses import replace
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from dekopen_engine.geometry import calculate_geometry, compute_geometry
from dekopen_engine.hardware import NoCompatibleHardwareKit
from dekopen_engine.inspection_models import (
    InspectionMode, InspectorConfig, InspectorInput, RuleEvaluationStatus,
    StructuralInput, WorkshopAnnotations,
)
from dekopen_engine.inspector import apply_inspector_diff, inspect
from dekopen_engine.models import BayOpeningType, HardwareKitRule, RailType, SystemParams
from dekopen_engine.technical_facts import (
    GeometryComputation, InfillTechnicalFacts, LeafTechnicalFacts, OpeningTechnicalFacts,
    SpanTechnicalFacts,
)
from dekopen_engine.weight import ExactLeafWeight
from engine.tests.test_shot06_core import core_node


@pytest.fixture
def config() -> InspectorConfig:
    return InspectorConfig.model_validate({
        "R01": {}, "R02": {"min_ratio": "0.4000", "max_ratio": "2.5000", "suggested_ratio": "1.5000"},
        "R03": {"min_width_mm": "350", "max_width_mm": "1600", "max_height_mm": "2400"},
        "R04": {"monolithic_4_max_area_m2": "1.8000", "dvh_4_any_4_max_area_m2": "2.6000"},
        "R05": {"span_trigger_mm": "1800"}, "R06": {},
        "R07": {"width_trigger_mm": "800", "required_bottom_drains": "3"},
        "R08": {"max_spacing_mm": "800"},
        "R09": {"white_limit_mm": "4000", "foiled_limit_mm": "3000"},
        "R10": {"tolerance_mm": "1.50"},
        "R11": {"expected_mm": "12", "tolerance_mm": "1.50", "suggested_sash_overlap_mm": "8"},
        "R12": {"width_trigger_mm": "4500", "minimum_ix_cm4": "45.0000"},
        "R13": {"height_trigger_mm": "1200", "required_stay_arms": "2"},
        "R14": {"weight_trigger_kg": "150", "required_carriages": "4", "minimum_capacity_kg": "80"},
    })


def leaf(w: str = "1000", h: str = "1000", mass: str = "100") -> LeafTechnicalFacts:
    kit = HardwareKitRule(
        sku="SYNTHETIC-TEST", name="Synthetic rule fixture", opening_type="TURN",
        min_leaf_width_mm=D("100"), max_leaf_width_mm=D("2000"),
        min_leaf_height_mm=D("100"), max_leaf_height_mm=D("3000"),
        max_leaf_weight_kg=D("100"), weight_kg=D("0"),
    )
    exact = ExactLeafWeight(D("0"), D("0"), D(mass))
    return LeafTechnicalFacts("B", None, BayOpeningType.TURN_LEFT, RailType.DUAL,
                              D(w), D(h), exact, [], kit, exact)


def data_with_leaf(value: LeafTechnicalFacts) -> InspectorInput:
    return InspectorInput(GeometryComputation(leaves=[value]), D("12"))


def state(data: InspectorInput, config: InspectorConfig, rule: str) -> str:
    evaluations = [e for e in inspect(data, config).evaluations if e.rule_id.value == rule]
    assert len(evaluations) == 1
    return evaluations[0].status.value


@pytest.mark.parametrize("mass,expected", [("100", "PASS"), ("100.01", "FAIL"),
                                           ("100.00001", "FAIL")])
def test_r01_exact_mass(config: InspectorConfig, mass: str, expected: str) -> None:
    assert state(data_with_leaf(leaf(mass=mass)), config, "R01") == expected


@pytest.mark.parametrize("w,h,expected", [("400", "1000", "PASS"), ("1000", "400", "PASS"),
                                          ("400", "1000.01", "FAIL"), ("1000", "399.99", "FAIL")])
def test_r02_finished_ratio(config: InspectorConfig, w: str, h: str, expected: str) -> None:
    assert state(data_with_leaf(leaf(w, h)), config, "R02") == expected


@pytest.mark.parametrize("w,h,expected", [("350", "2400", "PASS"), ("1600", "2400", "PASS"),
                                          ("349.99", "1000", "FAIL"), ("1600.01", "1000", "FAIL"),
                                          ("1000", "2400.01", "FAIL")])
def test_r03_system_and_kit_intersection(config: InspectorConfig, w: str, h: str, expected: str) -> None:
    assert state(data_with_leaf(leaf(w, h)), config, "R03") == expected
    item = leaf("1000")
    assert item.selected_kit is not None
    item = replace(item, selected_kit=item.selected_kit.model_copy(update={"max_leaf_width_mm": D("999.99")}))
    assert state(data_with_leaf(item), config, "R03") == "FAIL"


@pytest.mark.parametrize("spec,area,expected", [("4", "1.8", "PASS"), ("4", "1.800001", "FAIL"),
    ("4-12-4", "2.6", "PASS"), ("4-16-4", "2.600001", "FAIL"), ("6", "1", "MISSING_INPUT")])
def test_r04_exact_area_class(config: InspectorConfig, spec: str, area: str, expected: str) -> None:
    infill = InfillTechnicalFacts("B", None, "GLASS", D("4"), spec, D("1000"),
                                  D(area) * D("1000"), D(area), True)
    data = InspectorInput(GeometryComputation(infills=[infill]), D("12"))
    assert state(data, config, "R04") == expected
    assert state(replace(data, computation=GeometryComputation(infills=[replace(infill, kind="PANEL")])),
                 config, "R04") == "NOT_APPLICABLE"


@pytest.mark.parametrize("span,ix,requirement,expected", [("1800", None, None, "NOT_APPLICABLE"),
    ("1800.01", "45", None, "MISSING_INPUT"), ("1800.01", "45", "45", "PASS"),
    ("1800.01", "44.9999", "45", "FAIL")])
def test_r05_verifies_external_requirement_only(config: InspectorConfig, span: str,
    ix: str | None, requirement: str | None, expected: str) -> None:
    data = InspectorInput(GeometryComputation(spans=[SpanTechnicalFacts("T", "MULLION", D(span))]),
        D("12"), structural_inputs=[StructuralInput(target_id="T",
        required_ix_cm4=None if requirement is None else D(requirement), structural_basis="Owner synthetic structural requirement")],
        reinforcement_ix_by_target={"T": None if ix is None else D(ix)})
    assert state(data, config, "R05") == expected
    assert all("Cumple NCh" not in f.diagnosis for f in inspect(data, config).findings)


@pytest.mark.parametrize("kind", ["GLASS", "PANEL"])
@pytest.mark.parametrize("supported,expected", [(True, "PASS"), (False, "FAIL")])
def test_r06_retained_infill(config: InspectorConfig, kind: str, supported: bool, expected: str) -> None:
    infill = InfillTechnicalFacts("B", None, kind, D("24"), "4-16-4", D("1000"), D("1000"), D("1"), supported)
    assert state(InspectorInput(GeometryComputation(infills=[infill]), D("12")), config, "R06") == expected


def opening_data(width: str = "1000", **annotations: object) -> InspectorInput:
    return InspectorInput(GeometryComputation(openings=[OpeningTechnicalFacts("B", D(width), D("1000"))]),
        D("12"), annotations=[WorkshopAnnotations.model_validate({"bay_id": "B", **annotations})])


def test_r07_real_diff_and_idempotence(config: InspectorConfig) -> None:
    data = opening_data(bottom_drain_holes_mm=[D("100"), D("900")],
                        continuous_width_mm=D("1000"), finish_class="WHITE", has_coupler=False)
    result = inspect(data, config)
    assert result.status == "YELLOW" and result.production_allowed
    finding = next(f for f in result.findings if f.rule_id.value == "R07")
    assert finding.fix is not None
    assert finding.fix.operations[0].new_value == [D("100"), D("500"), D("900")]
    draft = apply_inspector_diff(data.annotations, finding.fix, D("1000"))
    assert data.annotations[0].bottom_drain_holes_mm == [D("100"), D("900")]
    assert state(replace(data, annotations=draft), config, "R07") == "PASS"
    assert inspect(replace(data, annotations=draft), config).status == "GREEN"
    with pytest.raises(ValueError):
        apply_inspector_diff(draft, finding.fix, D("1000"))
    with pytest.raises(ValueError):
        apply_inspector_diff(data.annotations, finding.fix, D("1000.01"))
    assert draft[0].bottom_drain_holes_mm == [D("100"), D("500"), D("900")]
    assert state(opening_data("800"), config, "R07") == "PASS"
    assert state(opening_data("800.01"), config, "R07") == "MISSING_INPUT"


@pytest.mark.parametrize("points,expected", [(["0", "800", "1600", "2400", "3200"], "PASS"),
    (["0", "800.01", "1600", "2400", "3200"], "FAIL"),
    (["100", "800", "1600", "2400", "3200"], "FAIL")])
def test_r08_including_wrap(config: InspectorConfig, points: list[str], expected: str) -> None:
    data = replace(data_with_leaf(leaf()), annotations=[WorkshopAnnotations(bay_id="B",
                    closing_points_perimeter_mm=[D(p) for p in points])])
    assert state(data, config, "R08") == expected


@pytest.mark.parametrize("finish,width,expected", [("WHITE", "4000", "PASS"),
    ("WHITE", "4000.01", "FAIL"), ("FOILED", "3000", "PASS"), ("FOILED", "3000.01", "FAIL")])
def test_r09_pure_finish_fixtures(config: InspectorConfig, finish: str, width: str, expected: str) -> None:
    data = opening_data(continuous_width_mm=D(width), finish_class=finish, has_coupler=False)
    assert state(data, config, "R09") == expected


@pytest.mark.parametrize("delta,expected", [("1.50", "PASS"), ("1.51", "FAIL")])
def test_r10_measured_qc_only(config: InspectorConfig, delta: str, expected: str) -> None:
    data = opening_data(measured_d1_mm=D("1400"), measured_d2_mm=D("1400") + D(delta))
    assert state(data, config, "R10") == "NOT_APPLICABLE"
    assert state(replace(data, mode=InspectionMode.WORKSHOP_QC), config, "R10") == expected


@pytest.mark.parametrize("clearance,expected", [("10.50", "PASS"), ("13.50", "PASS"),
                                              ("10.49", "FAIL"), ("13.51", "FAIL")])
def test_r11_explicit_clearance(config: InspectorConfig, clearance: str, expected: str) -> None:
    assert state(replace(data_with_leaf(leaf()), chamber_clearance_mm=D(clearance)), config, "R11") == expected


@pytest.mark.parametrize("width,ix,expected", [("4500", "44", "NOT_APPLICABLE"),
    ("4500.01", "45", "PASS"), ("4500.01", "44.9999", "FAIL")])
def test_r12_pure_without_g8(config: InspectorConfig, width: str, ix: str, expected: str) -> None:
    data = data_with_leaf(replace(leaf(), opening_type=BayOpeningType.SLIDING_3L))
    data.computation.openings.append(OpeningTechnicalFacts("B", D(width), D("1000")))
    assert state(replace(data, reinforcement_ix_by_target={"B": D(ix)}), config, "R12") == expected


@pytest.mark.parametrize("height,stays,expected", [("1200", 1, "PASS"),
    ("1200.01", 1, "FAIL"), ("1200.01", 2, "PASS")])
def test_r13_awning(config: InspectorConfig, height: str, stays: int, expected: str) -> None:
    item = leaf(h=height)
    assert item.selected_kit is not None
    item = replace(item, opening_type=BayOpeningType.AWNING,
                   selected_kit=item.selected_kit.model_copy(update={"stay_arms_qty": stays}))
    assert state(data_with_leaf(item), config, "R13") == expected


@pytest.mark.parametrize("mass,qty,capacity,expected", [("150", 2, None, "PASS"),
    ("150.01", 3, "80", "FAIL"), ("150.01", 4, "79.99", "FAIL"),
    ("150.01", 4, "80", "PASS"), ("150.01", 4, None, "MISSING_INPUT")])
def test_r14_pure_without_g10(config: InspectorConfig, mass: str, qty: int,
                            capacity: str | None, expected: str) -> None:
    item = leaf(mass=mass)
    assert item.selected_kit is not None
    item = replace(item, rail_type=RailType.MONO, selected_kit=item.selected_kit.model_copy(update={
        "carriages_qty": qty, "carriage_capacity_kg": None if capacity is None else D(capacity)}))
    assert state(data_with_leaf(item), config, "R14") == expected


def test_diagnostic_facts_do_not_relax_strict_calculation(demo_60_params: SystemParams,
                                                        config: InspectorConfig) -> None:
    kit = next(k for k in demo_60_params.available_hardware_kits if k.sku == "KIT-AWNING-16")
    for changes, rule in [({"max_leaf_weight_kg": D("21.69")}, "R01"),
                           ({"max_leaf_width_mm": D("1")}, "R03")]:
        params = demo_60_params.model_copy(update={"available_hardware_kits": [kit.model_copy(update=changes)]})
        with pytest.raises(NoCompatibleHardwareKit):
            calculate_geometry(core_node("G6"), params)
        facts = compute_geometry(core_node("G6"), params, diagnostic=True)
        assert facts.result is None
        assert state(InspectorInput(facts, D("12")), config, rule) == "FAIL"
    params = demo_60_params.model_copy(update={"glazing_bead_rules": {}})
    with pytest.raises(ValueError):
        calculate_geometry(core_node("G7"), params)
    facts = compute_geometry(core_node("G7"), params, diagnostic=True)
    assert facts.result is None
    assert any(e.rule_id.value == "R06" and e.status is RuleEvaluationStatus.FAIL
               for e in inspect(InspectorInput(facts, D("12")), config).evaluations)


@pytest.mark.parametrize("number", range(1, 15))
def test_all_fourteen_configs_are_required(config: InspectorConfig, number: int) -> None:
    raw = config.model_dump()
    del raw[f"R{number:02d}"]
    with pytest.raises(ValidationError):
        InspectorConfig.model_validate(raw)


@pytest.mark.parametrize("basis,ix", [(None, D("45")), (" ", D("45")), ("External", None)])
def test_r05_missing_structural_authority_is_red(config: InspectorConfig,
                                               basis: str | None, ix: D | None) -> None:
    data = InspectorInput(GeometryComputation(spans=[SpanTechnicalFacts("T", "MULLION", D("1800.01"))]),
        D("12"), structural_inputs=[StructuralInput(target_id="T", required_ix_cm4=D("45"),
                                                    structural_basis=basis)],
        reinforcement_ix_by_target={"T": ix})
    result = inspect(data, config)
    assert state(data, config, "R05") == "MISSING_INPUT"
    assert result.status == "RED" and not result.production_allowed
    assert result.findings[0].fixability.value == "BLOCKED_MISSING_AUTHORITY"


@pytest.mark.parametrize("holes", [[], [D("100")], [D("100"), D("500")]])
def test_r07_never_invents_lateral_positions(config: InspectorConfig, holes: list[D]) -> None:
    result = inspect(opening_data(bottom_drain_holes_mm=holes), config)
    finding = next(f for f in result.findings if f.rule_id.value == "R07")
    assert finding.fix is None and finding.fixability.value == "SUGGESTION_ONLY"


def test_missing_observations_and_coupler(config: InspectorConfig) -> None:
    assert state(data_with_leaf(leaf()), config, "R08") == "MISSING_INPUT"
    assert state(replace(data_with_leaf(leaf()), chamber_clearance_mm=None), config, "R11") == "MISSING_INPUT"
    assert state(opening_data(), config, "R09") == "MISSING_INPUT"
    assert state(replace(opening_data(), mode=InspectionMode.WORKSHOP_QC), config, "R10") == "MISSING_INPUT"
    assert state(opening_data(continuous_width_mm=D("4000.01"), finish_class="WHITE",
                              has_coupler=True), config, "R09") == "PASS"


def test_duplicate_observation_targets_and_invalid_coordinates_fail_closed(config: InspectorConfig) -> None:
    data = opening_data(bottom_drain_holes_mm=[D("100"), D("900")])
    with pytest.raises(ValueError, match="Duplicate annotation"):
        inspect(replace(data, annotations=data.annotations * 2), config)
    for holes in ([D("-0.01")], [D("100"), D("100.00")]):
        with pytest.raises(ValidationError):
            WorkshopAnnotations(bay_id="B", bottom_drain_holes_mm=holes)
    with pytest.raises(ValueError, match="outside"):
        inspect(opening_data(bottom_drain_holes_mm=[D("1000.01")]), config)
