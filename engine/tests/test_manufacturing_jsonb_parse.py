"""Catalog-authority JSONB → policy model parsers.

``authority`` columns store plain JSON: enum fields arrive as strings and
historic rows stored numerics as string decimals. The strict engine models
can't model_validate that shape, so these parsers do field-level coercion —
and they must keep reading legacy string-numeric payloads so older policy
versions remain loadable on un-repaired databases.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from typing import Any

from dekopen_engine.manufacturing import (
    ManufacturingAuthorityError,
    handle_policy_from_json,
    placement_policy_from_json,
    reinforcement_policy_from_json,
)
from dekopen_engine.manufacturing_trace import MemberSide
from dekopen_engine.models import BayOpeningType

_HANDLE: dict[str, Any] = {
    "schema_version": 1,
    "policy_id": "P1",
    "version": 2,
    "slots": [
        {
            "opening_type": "TURN_LEFT",
            "leaf_slot": None,
            "leaf_handedness": None,
            "handle_domain_slot": "PRIMARY",
            "host_member_side": "RIGHT",
            "horizontal_reference": "HOST_MEMBER_AXIS",
            "horizontal_offset_mm": Decimal("-10.00"),
            "permitted_vertical_references": ["OUTER_TOP", "LEAF_TOP"],
            "mounting_min_from_leaf_top_mm": Decimal("0.00"),
            "mounting_max_from_leaf_top_mm": Decimal("3000.00"),
        }
    ],
}

_PLACEMENT: dict[str, Any] = {
    "schema_version": 1,
    "policy_id": "PP1",
    "version": 2,
    "sliding_leaf_offsets": {"L1": {"x_mm": 0, "y_mm": 0, "x_pitches": 0}},
    "sliding_infill_offsets": {"L1": {"x_mm": Decimal("70"), "y_mm": Decimal("70"), "x_pitches": 0}},
    "bead_offsets": {
        "TOP": {"x_mm": 0, "y_mm": 0},
        "RIGHT": {"x_mm": 0, "y_mm": 0},
        "BOTTOM": {"x_mm": 0, "y_mm": 0},
        "LEFT": {"x_mm": 0, "y_mm": 0},
    },
}

_REINFORCEMENT: dict[str, Any] = {
    "schema_version": 1,
    "policy_id": "R1",
    "version": 1,
    "rules": [
        {
            "role": "FRAME",
            "profile_angle_left": Decimal("45.0"),
            "profile_angle_right": Decimal("45.0"),
            "reinforcement_angle_left": Decimal("90.0"),
            "reinforcement_angle_right": Decimal("90.0"),
            "length_authority": "EXISTING_ENGINE",
            "compatible_with_existing_length": True,
        }
    ],
}


def _stringify_numerics(value: object) -> object:
    if isinstance(value, dict):
        return {k: _stringify_numerics(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_numerics(v) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


def test_handle_policy_parses_native_numerics() -> None:
    policy = handle_policy_from_json(_HANDLE)
    assert policy.version == 2
    assert policy.slots[0].opening_type is BayOpeningType.TURN_LEFT
    assert policy.slots[0].host_member_side is MemberSide.RIGHT
    assert policy.slots[0].horizontal_offset_mm == Decimal("-10.00")


def test_handle_policy_parses_legacy_string_numerics() -> None:
    policy = handle_policy_from_json(_stringify_numerics(_HANDLE))
    assert policy.slots[0].horizontal_offset_mm == Decimal("-10.00")
    assert policy.slots[0].mounting_max_from_leaf_top_mm == Decimal("3000.00")


def test_placement_policy_parses_native_and_legacy() -> None:
    native = placement_policy_from_json(_PLACEMENT)
    assert native.bead_offsets[MemberSide.TOP].x_mm == 0
    legacy = placement_policy_from_json(_stringify_numerics(_PLACEMENT))
    assert legacy.sliding_infill_offsets["L1"].x_mm == Decimal("70")


def test_reinforcement_policy_parses_native_and_legacy() -> None:
    assert reinforcement_policy_from_json(_REINFORCEMENT).rules[0].role.value == "FRAME"
    legacy = reinforcement_policy_from_json(_stringify_numerics(_REINFORCEMENT))
    assert legacy.rules[0].profile_angle_left == Decimal("45.0")


def test_parsers_reject_malformed_payloads() -> None:
    for parse, payload in (
        (handle_policy_from_json, {"slots": "nope"}),
        (handle_policy_from_json, {"slots": [{"opening_type": "BOGUS"}]}),
        (handle_policy_from_json, "not-a-dict"),
        (placement_policy_from_json, {"sliding_leaf_offsets": []}),
        (placement_policy_from_json, None),
        (reinforcement_policy_from_json, {"rules": [{"role": "FRAME"}]}),
        (reinforcement_policy_from_json, {"rules": [
            {**_REINFORCEMENT["rules"][0], "length_authority": "INVENTED"}]}),
    ):
        with pytest.raises(ManufacturingAuthorityError):
            parse(payload)
