from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine import BayOpeningType, NodeType, ParametricNode, SystemParams
from engine.tests.catalog import (
    alu_65_params as build_alu_65_params,
    demo_60_params as build_demo_60_params,
    demo_corredera_60_params as build_demo_corredera_60_params,
)


def d(value: str) -> Decimal:
    return Decimal(value)


@pytest.fixture(scope="session")
def demo_60_params() -> SystemParams:
    return build_demo_60_params()


@pytest.fixture(scope="session")
def demo_corredera_60_params() -> SystemParams:
    return build_demo_corredera_60_params()


@pytest.fixture(scope="session")
def alu_65_params() -> SystemParams:
    return build_alu_65_params()


def bay_node(
    *,
    case_id: str,
    width_mm: str,
    height_mm: str,
    opening_type: BayOpeningType,
    glass_thickness_mm: str,
    glass_spec: str,
) -> ParametricNode:
    return ParametricNode(
        id=case_id,
        type=NodeType.BAY,
        width_mm=d(width_mm),
        height_mm=d(height_mm),
        opening_type=opening_type,
        glass_thickness_mm=d(glass_thickness_mm),
        glass_spec=glass_spec,
    )


@pytest.fixture(scope="session")
def g1_node() -> ParametricNode:
    return bay_node(
        case_id="g1",
        width_mm="1000.00",
        height_mm="1000.00",
        opening_type=BayOpeningType.FIXED,
        glass_thickness_mm="4.00",
        glass_spec="4",
    )


@pytest.fixture(scope="session")
def g2_node() -> ParametricNode:
    return bay_node(
        case_id="g2",
        width_mm="800.00",
        height_mm="1200.00",
        opening_type=BayOpeningType.TURN_LEFT,
        glass_thickness_mm="24.00",
        glass_spec="4-16-4",
    )


@pytest.fixture(scope="session")
def g3_node() -> ParametricNode:
    return bay_node(
        case_id="g3",
        width_mm="1000.00",
        height_mm="1400.00",
        opening_type=BayOpeningType.TILT_TURN_LEFT,
        glass_thickness_mm="20.00",
        glass_spec="4-12-4",
    )


@pytest.fixture(scope="session")
def g4_node() -> ParametricNode:
    return ParametricNode(
        id="g4",
        type=NodeType.SPLIT_V,
        width_mm=d("1800.00"),
        height_mm=d("1500.00"),
        split_offset_mm=d("900.00"),
        mullion_profile_sku="POSTE-V",
        children=[
            ParametricNode(
                id="bay_fixed",
                type=NodeType.BAY,
                opening_type=BayOpeningType.FIXED,
                glass_thickness_mm=d("24.00"),
                glass_spec="4-16-4 Float Incoloro",
            ),
            ParametricNode(
                id="bay_ob",
                type=NodeType.BAY,
                opening_type=BayOpeningType.TILT_TURN_RIGHT,
                glass_thickness_mm=d("20.00"),
                glass_spec="4-12-4 Float Incoloro",
            ),
        ],
    )
