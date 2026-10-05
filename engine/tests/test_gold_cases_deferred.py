from __future__ import annotations

import pytest


from dekopen_engine import RailType, SystemParams, calculate_geometry
from dekopen_engine.geometry import SlidingLayoutError
from dekopen_engine.models import (
    BayOpeningType,
    ParametricNode,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
)
from engine.tests.test_shot06_core import core_node


def test_g8_sliding_3l_evaluates(demo_corredera_60_params: SystemParams) -> None:
    # 2440x2100 on a dual rail: three moving panels alternating tracks.
    result = calculate_geometry(core_node("G8"), demo_corredera_60_params)
    leaf_ids = [cut.leaf_id for cut in result.profile_cuts]
    assert {leaf_id for leaf_id in leaf_ids if leaf_id} == {
        "G8:L1",
        "G8:L2",
        "G8:L3",
    }
    assert {(item.kit_sku, item.leaf_id) for item in result.hardware_items} == {
        ("KIT-SLIDING-CORR", "G8:L1"),
        ("KIT-SLIDING-CORR", "G8:L2"),
        ("KIT-SLIDING-CORR", "G8:L3"),
    }
    assert len(result.glasses) == 3


def test_g9_sliding_4l_evaluates(demo_corredera_60_params: SystemParams) -> None:
    # 3240x2100 on a dual rail: four moving panels alternating tracks.
    result = calculate_geometry(core_node("G9"), demo_corredera_60_params)
    leaf_ids = {cut.leaf_id for cut in result.profile_cuts if cut.leaf_id}
    assert leaf_ids == {"G9:L1", "G9:L2", "G9:L3", "G9:L4"}
    assert len(result.hardware_items) == 4
    assert len(result.glasses) == 4


def test_g10_monorail_rejects_dual_track_layouts(demo_corredera_60_params: SystemParams) -> None:
    # SLIDING_2L's preset needs two rails — a monorail system refuses with the
    # dedicated topology error, never a blanket NotImplementedError.
    node = core_node("G5").model_copy(update={"id": "G10"})
    params = demo_corredera_60_params.model_copy(update={"rail_type": RailType.MONO})
    with pytest.raises(SlidingLayoutError) as error:
        calculate_geometry(node, params)
    assert error.value.code == "sliding_tracks_unsupported"


def test_g10_monorail_evaluates_a_single_track_layout(
    demo_corredera_60_params: SystemParams,
) -> None:
    # O/X/O on one rail: the two fixed panes glaze in-frame and the single
    # moving leaf rides track 0 — real monorail geometry, not a deferral.
    node = core_node("G5").model_copy(
        update={
            "id": "G10",
            "opening_type": BayOpeningType.SLIDING,
            "sliding_layout": SlidingLayout(
                tracks=1,
                panels=[
                    SlidingPanel(slot="left", kind=SlidingPanelKind.FIXED),
                    SlidingPanel(
                        slot="mid", kind=SlidingPanelKind.MOVING, track=0
                    ),
                    SlidingPanel(slot="right", kind=SlidingPanelKind.FIXED),
                ],
            ),
        }
    )
    params = demo_corredera_60_params.model_copy(update={"rail_type": RailType.MONO})
    result = calculate_geometry(node, params)
    leaf_ids = {cut.leaf_id for cut in result.profile_cuts if cut.leaf_id}
    # Fixed panes carry their own {bay}:{slot} identity — two fixed panes
    # sharing (bay, None) would collide downstream.
    assert leaf_ids == {"G10:L2", "G10:left", "G10:right"}
    assert [(item.kit_sku, item.leaf_id) for item in result.hardware_items] == [
        ("KIT-SLIDING-CORR-MONO", "G10:L2")
    ]
    assert len(result.glasses) == 3  # 2 fixed panes + 1 leaf glass


@pytest.mark.xfail(
    strict=True,
    reason="G11 double-door geometry not yet supported",
)
def test_g11_double_door_is_declared_deferred() -> None:
    raise NotImplementedError("G11 double-door is not yet supported")


@pytest.mark.xfail(
    strict=True,
    reason="G12 large-fixed geometry not yet supported",
)
def test_g12_large_fixed_is_declared_deferred() -> None:
    raise NotImplementedError("G12 large-fixed is not yet supported")


def _sliding_node(layout: SlidingLayout) -> ParametricNode:
    return core_node("G5").model_copy(
        update={
            "id": "GX",
            "opening_type": BayOpeningType.SLIDING,
            "sliding_layout": layout,
        }
    )


@pytest.mark.parametrize(
    "panels",
    [
        [
            SlidingPanel(slot="a", kind=SlidingPanelKind.MOVING, track=0),
            SlidingPanel(slot="a", kind=SlidingPanelKind.MOVING, track=1),
        ],
        [
            SlidingPanel(slot="a", kind=SlidingPanelKind.MOVING, track=5),
            SlidingPanel(slot="b", kind=SlidingPanelKind.MOVING, track=1),
        ],
        [
            SlidingPanel(slot="a", kind=SlidingPanelKind.FIXED, track=0),
            SlidingPanel(slot="b", kind=SlidingPanelKind.MOVING, track=1),
        ],
        [
            SlidingPanel(slot="a", kind=SlidingPanelKind.FIXED),
            SlidingPanel(slot="b", kind=SlidingPanelKind.FIXED),
            SlidingPanel(slot="c", kind=SlidingPanelKind.MOVING, track=0),
        ],
        [
            SlidingPanel(slot="a", kind=SlidingPanelKind.MOVING, track=0),
            SlidingPanel(slot="b", kind=SlidingPanelKind.MOVING, track=0),
        ],
    ],
)
def test_sliding_layout_rules_reject(
    panels: list[SlidingPanel], demo_corredera_60_params: SystemParams
) -> None:
    with pytest.raises(SlidingLayoutError) as error:
        calculate_geometry(
            _sliding_node(SlidingLayout(tracks=2, panels=panels)),
            demo_corredera_60_params,
        )
    assert error.value.code == "sliding_layout_invalid"


def test_sliding_layout_rejects_zero_moving_panels(
    demo_corredera_60_params: SystemParams,
) -> None:
    all_fixed = SlidingLayout(
        tracks=1,
        panels=[SlidingPanel(slot="only", kind=SlidingPanelKind.FIXED)],
    )
    mono = demo_corredera_60_params.model_copy(update={"rail_type": RailType.MONO})
    with pytest.raises(SlidingLayoutError) as error:
        calculate_geometry(_sliding_node(all_fixed), mono)
    assert error.value.code == "sliding_layout_invalid"
    assert "moving" in str(error.value)


def test_sliding_bay_needs_a_declared_layout(
    demo_corredera_60_params: SystemParams,
) -> None:
    node = core_node("G5").model_copy(
        update={"id": "GX", "opening_type": BayOpeningType.SLIDING}
    )
    with pytest.raises(SlidingLayoutError) as error:
        calculate_geometry(node, demo_corredera_60_params)
    assert error.value.code == "sliding_layout_invalid"
