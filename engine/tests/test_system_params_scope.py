"""Canonical SHOT-06 scope: 32 mapped, 27 consumed, 2 metadata, 3 reserved."""

import ast
from collections.abc import Callable
from decimal import Decimal
import inspect

import pytest

from dekopen_engine import ParametricNode, SystemParams, calculate_geometry
from dekopen_engine import geometry, hardware
from engine.tests.test_shot06_core import core_node

# Sliding-geometry fields are consumed through the grouped `params.sliding`
# view (D01): the consumer binds `sliding = params.sliding` and reads
# `sliding.<field>` — the AST check below counts those reads too.
CORE_CONSUMERS: dict[str, Callable[..., object]] = {
    "material": geometry.compute_geometry,
    "system_family": geometry.assert_opening_allowed,
    "effective_profile_articles": geometry._article,
    "glazing_bead_rules": geometry.resolve_bead_rule,
    "rebate_depth_mm": geometry.rebate_depth,
    "end_milling_overlap_mm": geometry._end_milling_overlap,
    "sash_overlap_mm": geometry.single_rectangular_sash_geometry,
    "glass_clearance_white_mm": geometry.compute_geometry,
    "glass_clearance_foil_mm": geometry.compute_geometry,
    "pulley_height_mm": geometry._append_sliding,
    "central_overlap_mm": geometry._append_sliding,
    "sliding_end_add_mm": geometry._append_sliding,
    "door_threshold_mm": geometry._append_door,
    "door_bottom_clearance_mm": geometry._append_door,
    "rail_type": hardware.evaluate_hardware_candidates,
    "available_hardware_kits": hardware.evaluate_hardware_candidates,
    "sliding_glazing_deduction_width_mm": geometry._append_leaf,
    "sliding_glazing_deduction_height_mm": geometry._append_leaf,
    "door_leaf_side_clearance_mm": geometry._append_door,
    "available_panel_rules": geometry._append_leaf,
    "rail_count": geometry.rail_count,
    "cut_rules": geometry._append_leaf,
    "reinforcement_rules": geometry._append_profile,
    "typology_limits": geometry._append_leaf,
    # D02 glass authorities: products, safety rules and type limits are
    # consumed inside the per-piece glass evaluation pass.
    "glass_products": geometry._evaluate_glass,
    "glass_safety_rules": geometry._evaluate_glass,
    "glass_type_limits": geometry._evaluate_glass,
}
METADATA = {"system_code", "depth_mm"}
RESERVED = {"sliding_lateral_clearance_mm", "corner_bracket_loss_mm", "hook_depth_mm"}
# Input-validity authority consumed by the API adapter (finish membership gates
# `color`), not a formula input — `backend/engine_api/adapter.py` reads it.
API_BOUNDARY = {"finishes"}

# Names that alias `params` inside a consumer's body (`x = params.<group>`).
_GROUPED_BINDINGS = ("sliding",)


def _param_reads(consumer: Callable[..., object]) -> set[str]:
    tree = ast.parse(inspect.getsource(consumer))
    bound = {"params"} | set(_GROUPED_BINDINGS)
    return {
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        and node.value.id in bound and isinstance(node.ctx, ast.Load)
    }


def test_every_system_parameter_has_an_explicit_scope() -> None:
    assert (
        len(CORE_CONSUMERS) == 27
        and len(METADATA) == 2
        and len(RESERVED) == 3
        and len(API_BOUNDARY) == 1
    )
    assert (
        set(CORE_CONSUMERS) | METADATA | RESERVED | API_BOUNDARY
        == set(SystemParams.model_fields)
    )
    for field, consumer in CORE_CONSUMERS.items():
        assert field in _param_reads(consumer), (
            f"{field} has lost its real consumer {consumer.__name__}"
        )


@pytest.mark.parametrize("field", sorted(RESERVED))
@pytest.mark.parametrize("case", ["G3", "G5", "G6", "G7"])
def test_reserved_parameters_do_not_change_core_results(
    field: str, case: str, demo_60_params: SystemParams,
    demo_corredera_60_params: SystemParams, g3_node: ParametricNode,
) -> None:
    node = g3_node if case == "G3" else core_node(case)
    params = demo_corredera_60_params if case == "G5" else demo_60_params
    before = calculate_geometry(node, params)
    changed = params.model_copy(update={field: Decimal("123.45")})
    assert calculate_geometry(node, changed) == before
