"""P05 — parity contract for opening symbology.

Every JSON under ``engine/tests/fixtures/symbols/`` pins the primitives
and the canonical path data the elevation renderers must produce, for
both interior and exterior view. The TypeScript twin
(``frontend/src/features/canvas/openingSymbols.ts``) is exercised
against the same files by ``openingSymbols.test.ts`` — a divergence on
either side fails the suite. Regenerate fixtures ONLY via
``scripts/gen_symbol_fixtures.py`` and review the diff.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dekopen_engine.geometry import (
    SlidingLayoutError,
    panel_travel,
    resolved_sliding_layout,
    travel_inferred,
    validate_sliding_layout,
)
from dekopen_engine.models import (
    BayOpeningType,
    HingeSide,
    LeafRole,
    Opening,
    OpeningDirection,
    OpeningMovement,
    NodeType,
    ParametricNode,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
    SlidingTravel,
    SystemParams,
    UnitKind,
)
from dekopen_engine.opening_symbols import (
    GlyphPrimitive,
    glyph_paths,
    leaf_primitives,
    sliding_primitives,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "symbols"
FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))

# The contract covers the 13 base cases of the encargo (fixed, casement
# L/R + outward variant, tilt-turn L/R, awning, sliding 2/3/4 leaves,
# O/X/X/O, inferred travel, single door, double door) × both views.
assert len(FIXTURES) >= 13


def _build_opening(leaf: dict[str, Any]) -> Opening:
    return Opening(
        movement=OpeningMovement(leaf["movement"]),
        hinge_side=HingeSide(leaf["hinge_side"]),
        direction=OpeningDirection(leaf["direction"]) if leaf["direction"] else None,
        leaf_role=LeafRole(leaf.get("leaf_role", "SINGLE")),
    )


def _build_layout(inp: dict[str, Any]) -> SlidingLayout:
    return SlidingLayout(
        tracks=inp["tracks"],
        panels=[
            SlidingPanel(
                slot=panel["slot"],
                kind=SlidingPanelKind(panel["kind"]),
                track=panel["track"],
                travel=SlidingTravel(panel["travel"]) if panel["travel"] else None,
            )
            for panel in inp["panels"]
        ],
    )


def _canon(value: Any) -> Any:
    """Decimales del motor serializan como string JSON ("0.4", "1050") —
    la comparación los normaliza a número igual que el test de TS."""
    if isinstance(value, str):
        try:
            return int(value) if "." not in value else float(value)
        except ValueError:
            return value
    if isinstance(value, list):
        return [_canon(v) for v in value]
    if isinstance(value, dict):
        return {k: _canon(v) for k, v in value.items()}
    return value


def _dump(prims: list[GlyphPrimitive]) -> list[dict[str, Any]]:
    return [
        _canon(json.loads(prim.model_dump_json())) for prim in prims
    ]


def _paths(
    prims: list[GlyphPrimitive], x: float, y: float, w: float, h: float
) -> list[dict[str, Any]]:
    return [
        {"d": d, "dash": dash}
        for d, dash in glyph_paths(
            prims,
            Decimal(str(x)),
            Decimal(str(y)),
            Decimal(str(w)),
            Decimal(str(h)),
            leaf_bottom=Decimal(str(y + h)),
        )
    ]


def _actual(fixture: dict[str, Any], view: str) -> dict[str, Any]:
    inp = fixture["input"]
    box = fixture["box"]
    if inp["kind"] == "leaves":
        leaves = inp["leaves"]
        n = len(leaves)
        leaf_w = box["w"] / n
        return {
            "stiles": max(0, n - 1),
            "leaves": [
                {
                    "prims": _dump(
                        prims := leaf_primitives(
                            _build_opening(leaf),
                            view,  # type: ignore[arg-type]
                            unit=UnitKind(inp["unit"]),
                            handle_mm=(
                                Decimal(str(leaf["handle_mm"]))
                                if leaf.get("handle_mm") is not None
                                else None
                            ),
                            axis_mm=(
                                Decimal(str(leaf["axis_offset_mm"]))
                                if leaf.get("axis_offset_mm") is not None
                                else None
                            ),
                            slot=leaf.get("slot"),
                        )
                    ),
                    "paths": _paths(
                        prims,
                        box["x"] + leaf_w * index,
                        box["y"],
                        leaf_w,
                        box["h"],
                    ),
                }
                for index, leaf in enumerate(leaves)
            ],
        }
    layout = _build_layout(inp)
    all_prims = sliding_primitives(
        layout,
        view,  # type: ignore[arg-type]
        movement=OpeningMovement(inp.get("movement") or "SLIDE"),
    )
    n = len(all_prims)
    leaf_w = box["w"] / n
    return {
        "stiles": 0,
        "leaves": [
            {
                "prims": _dump(prims),
                "paths": _paths(
                    prims,
                    box["x"] + leaf_w * index,
                    box["y"],
                    leaf_w,
                    box["h"],
                ),
            }
            for index, prims in enumerate(all_prims)
        ],
    }


class TestSymbolFixtures:
    """Every fixture × both views must reproduce primitives and path
    data exactly — this is the parity half that runs on Python."""

    @pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
    def test_fixture_views(self, path: Path) -> None:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        for view in ("interior", "exterior"):
            assert _actual(fixture, view) == _canon(fixture["views"][view]), (
                f"{fixture['id']} diverges in {view} view — regenerate "
                "fixtures via scripts/gen_symbol_fixtures.py and review"
            )


def _node(layout: SlidingLayout | None, opening: BayOpeningType = BayOpeningType.SLIDING) -> ParametricNode:
    return ParametricNode(
        id="b1",
        type=NodeType.BAY,
        opening_type=opening,
        sliding_layout=layout,
    )


class TestSlidingTravel:
    """P05 model rules: declared travel, inference, and the jamb rule."""

    @staticmethod
    def _params(demo_corredera_60_params: SystemParams) -> SystemParams:
        return demo_corredera_60_params

    def test_presets_declare_travel(self) -> None:
        for opening in (
            BayOpeningType.SLIDING_2L,
            BayOpeningType.SLIDING_3L,
            BayOpeningType.SLIDING_4L,
        ):
            layout = resolved_sliding_layout(_node(None, opening))
            assert all(p.travel is not None for p in layout.panels)

    def test_missing_travel_resolves_convention_and_flags_inferred(self) -> None:
        panel = SlidingPanel(
            slot="S1", kind=SlidingPanelKind.MOVING, track=0
        )
        assert travel_inferred(panel)
        assert panel_travel(panel, 0, 2) is SlidingTravel.RIGHT
        assert panel_travel(panel, 1, 2) is SlidingTravel.LEFT
        declared = SlidingPanel(
            slot="S2", kind=SlidingPanelKind.MOVING, track=1,
            travel=SlidingTravel.LEFT,
        )
        assert not travel_inferred(declared)

    def test_fixed_panel_rejects_travel(self) -> None:
        with pytest.raises(ValueError):
            SlidingPanel(
                slot="O1", kind=SlidingPanelKind.FIXED, track=None,
                travel=SlidingTravel.RIGHT,
            )

    def test_travel_toward_jamb_without_space_rejected(self, demo_corredera_60_params: SystemParams) -> None:
        # Slot 0 traveling LEFT hits the left jamb; the last slot
        # traveling RIGHT hits the right one.
        for index, travel in ((0, SlidingTravel.LEFT),):
            layout = SlidingLayout(
                tracks=2,
                panels=[
                    SlidingPanel(
                        slot=f"S{i + 1}", kind=SlidingPanelKind.MOVING,
                        track=i % 2,
                        travel=travel if i == index else (
                            SlidingTravel.RIGHT if i * 2 < 2 else SlidingTravel.LEFT
                        ),
                    )
                    for i in range(2)
                ],
            )
            with pytest.raises(SlidingLayoutError) as error:
                validate_sliding_layout(layout, demo_corredera_60_params)
            assert "jamb" in str(error.value)

        layout = SlidingLayout(
            tracks=2,
            panels=[
                SlidingPanel(slot="S1", kind=SlidingPanelKind.MOVING, track=0,
                             travel=SlidingTravel.RIGHT),
                SlidingPanel(slot="S2", kind=SlidingPanelKind.MOVING, track=1,
                             travel=SlidingTravel.RIGHT),
            ],
        )
        with pytest.raises(SlidingLayoutError) as error:
            validate_sliding_layout(layout, demo_corredera_60_params)
        assert "jamb" in str(error.value)

    def test_travel_over_neighbouring_slot_valid(self, demo_corredera_60_params: SystemParams) -> None:
        layout = SlidingLayout(
            tracks=2,
            panels=[
                SlidingPanel(slot="S1", kind=SlidingPanelKind.MOVING, track=0,
                             travel=SlidingTravel.RIGHT),
                SlidingPanel(slot="S2", kind=SlidingPanelKind.MOVING, track=1,
                             travel=SlidingTravel.LEFT),
            ],
        )
        validate_sliding_layout(layout, demo_corredera_60_params)

    def test_primary_index_roundtrips(self) -> None:
        layout = SlidingLayout(
            tracks=2,
            primary_index=1,
            panels=[
                SlidingPanel(slot="S1", kind=SlidingPanelKind.MOVING, track=0,
                             travel=SlidingTravel.RIGHT),
                SlidingPanel(slot="S2", kind=SlidingPanelKind.MOVING, track=1,
                             travel=SlidingTravel.LEFT),
            ],
        )
        assert layout.primary_index == 1
        dumped = layout.model_dump(mode="json")
        assert dumped["primary_index"] == 1
        assert dumped["panels"][0]["travel"] == "RIGHT"
