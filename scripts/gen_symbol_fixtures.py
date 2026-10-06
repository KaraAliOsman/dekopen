"""P05 — regenerate the shared opening-symbol fixtures.

The JSON files under ``engine/tests/fixtures/symbols/`` are the parity
contract between the TypeScript elevation renderer
(``frontend/src/features/canvas/openingSymbols.ts``) and the PDF
renderer (``backend/documents/renderers.py``): each case pins the
expected primitives AND the canonical path data for a reference leaf
box, in both interior and exterior view. Both test suites compare
against these files — regenerate them ONLY via this script and review
the diff like a golden case (``make goldgen`` precedent):

    PYTHONPATH=engine/src .venv/bin/python scripts/gen_symbol_fixtures.py
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from dekopen_engine.models import (  # noqa: E402
    HingeSide,
    LeafRole,
    Opening,
    OpeningDirection,
    OpeningMovement,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
    SlidingTravel,
    UnitKind,
)
from dekopen_engine.opening_symbols import (  # noqa: E402
    glyph_paths,
    leaf_primitives,
    sliding_primitives,
)

OUT_DIR = ROOT / "engine" / "tests" / "fixtures" / "symbols"


def _leaf(movement: str, hinge: str, direction: str | None,
          role: str = "SINGLE", handle_mm: float | None = None) -> dict[str, Any]:
    return {
        "movement": movement,
        "hinge_side": hinge,
        "direction": direction,
        "leaf_role": role,
        "handle_mm": handle_mm,
    }


def _panel(slot: str, kind: str, track: int | None,
           travel: str | None = None) -> dict[str, Any]:
    return {"slot": slot, "kind": kind, "track": track, "travel": travel}


# The 13 base cases of the symbology contract (+door-double): every case
# ships a reference leaf box and the input tree fragment the renderers
# consume. Doors are taller (leaf box 800x1400); every other case uses
# the canonical 800x1200 lite.
CASES: list[dict[str, Any]] = [
    {
        "id": "fixed",
        "name": "Fijo",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1200},
        "input": {
            "kind": "leaves",
            "unit": "WINDOW",
            "leaves": [_leaf("FIXED", "NONE", None)],
        },
    },
    {
        "id": "casement-left",
        "name": "Abatible izquierda",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1200},
        "input": {
            "kind": "leaves",
            "unit": "WINDOW",
            "leaves": [_leaf("TURN", "LEFT", "INWARD", handle_mm=1050)],
        },
    },
    {
        "id": "casement-right",
        "name": "Abatible derecha",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1200},
        "input": {
            "kind": "leaves",
            "unit": "WINDOW",
            "leaves": [_leaf("TURN", "RIGHT", "INWARD", handle_mm=1050)],
        },
    },
    {
        "id": "casement-left-outward",
        "name": "Abatible izquierda apertura exterior",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1200},
        "input": {
            "kind": "leaves",
            "unit": "WINDOW",
            "leaves": [_leaf("TURN", "LEFT", "OUTWARD", handle_mm=1050)],
        },
    },
    {
        "id": "tilt-turn-left",
        "name": "Oscilobatiente izquierda",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1200},
        "input": {
            "kind": "leaves",
            "unit": "WINDOW",
            "leaves": [_leaf("TILT_TURN", "LEFT", "INWARD", handle_mm=1050)],
        },
    },
    {
        "id": "tilt-turn-right",
        "name": "Oscilobatiente derecha",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1200},
        "input": {
            "kind": "leaves",
            "unit": "WINDOW",
            "leaves": [_leaf("TILT_TURN", "RIGHT", "INWARD", handle_mm=1050)],
        },
    },
    {
        "id": "awning",
        "name": "Proyectante (awning)",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1200},
        "input": {
            "kind": "leaves",
            "unit": "WINDOW",
            "leaves": [_leaf("TOP_HUNG", "TOP", "OUTWARD", handle_mm=900)],
        },
    },
    {
        "id": "sliding-2l",
        "name": "Corredera 2 hojas",
        "box": {"x": 0, "y": 0, "w": 1600, "h": 1200},
        "input": {
            "kind": "sliding",
            "unit": "WINDOW",
            "tracks": 2,
            "panels": [
                _panel("S1", "MOVING", 0, "RIGHT"),
                _panel("S2", "MOVING", 1, "LEFT"),
            ],
        },
    },
    {
        "id": "sliding-3l",
        "name": "Corredera 3 hojas",
        "box": {"x": 0, "y": 0, "w": 2400, "h": 1200},
        "input": {
            "kind": "sliding",
            "unit": "WINDOW",
            "tracks": 2,
            "panels": [
                _panel("S1", "MOVING", 0, "RIGHT"),
                _panel("S2", "MOVING", 1, "RIGHT"),
                _panel("S3", "MOVING", 0, "LEFT"),
            ],
        },
    },
    {
        "id": "sliding-4l",
        "name": "Corredera 4 hojas",
        "box": {"x": 0, "y": 0, "w": 3200, "h": 1200},
        "input": {
            "kind": "sliding",
            "unit": "WINDOW",
            "tracks": 2,
            "panels": [
                _panel("S1", "MOVING", 0, "RIGHT"),
                _panel("S2", "MOVING", 1, "RIGHT"),
                _panel("S3", "MOVING", 0, "LEFT"),
                _panel("S4", "MOVING", 1, "LEFT"),
            ],
        },
    },
    {
        "id": "sliding-oxxo",
        "name": "Corredera O/X/X/O",
        "box": {"x": 0, "y": 0, "w": 3200, "h": 1200},
        "input": {
            "kind": "sliding",
            "unit": "WINDOW",
            "tracks": 2,
            "panels": [
                _panel("O1", "FIXED", None),
                _panel("X1", "MOVING", 0, "RIGHT"),
                _panel("X2", "MOVING", 1, "LEFT"),
                _panel("O2", "FIXED", None),
            ],
        },
    },
    {
        "id": "sliding-2l-inferred",
        "name": "Corredera 2 hojas sin travel (dirección inferida)",
        "box": {"x": 0, "y": 0, "w": 1600, "h": 1200},
        "input": {
            "kind": "sliding",
            "unit": "WINDOW",
            "tracks": 2,
            "panels": [
                _panel("S1", "MOVING", 0),
                _panel("S2", "MOVING", 1),
            ],
        },
    },
    {
        "id": "door-single-left",
        "name": "Puerta simple izquierda",
        "box": {"x": 0, "y": 0, "w": 800, "h": 1400},
        "input": {
            "kind": "leaves",
            "unit": "DOOR",
            "leaves": [_leaf("TURN", "LEFT", "INWARD", handle_mm=1050)],
        },
    },
    {
        "id": "door-double",
        "name": "Puerta doble",
        "box": {"x": 0, "y": 0, "w": 1600, "h": 1400},
        "input": {
            "kind": "leaves",
            "unit": "DOOR",
            "leaves": [
                _leaf("TURN", "LEFT", "INWARD", "ACTIVE", handle_mm=1050),
                _leaf("TURN", "RIGHT", "INWARD", "PASSIVE"),
            ],
        },
    },
]


def _build_opening(leaf: dict[str, Any]) -> Opening:
    return Opening(
        movement=OpeningMovement(leaf["movement"]),
        hinge_side=HingeSide(leaf["hinge_side"]),
        direction=(
            OpeningDirection(leaf["direction"]) if leaf["direction"] else None
        ),
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
                travel=(
                    SlidingTravel(panel["travel"]) if panel["travel"] else None
                ),
            )
            for panel in inp["panels"]
        ],
    )


def _paths_json(prims: list[Any], x: float, y: float, w: float, h: float,
                leaf_bottom: float) -> list[dict[str, Any]]:
    return [
        {"d": d, "dash": dash}
        for d, dash in glyph_paths(
            prims,
            Decimal(str(x)),
            Decimal(str(y)),
            Decimal(str(w)),
            Decimal(str(h)),
            leaf_bottom=Decimal(str(leaf_bottom)),
        )
    ]


def _prims_json(prims: list[Any]) -> list[dict[str, Any]]:
    return [
        json.loads(prim.model_dump_json()) for prim in prims
    ]


def generate() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for case in CASES:
        box = case["box"]
        inp = case["input"]
        unit = UnitKind(inp["unit"])
        fixture: dict[str, Any] = {
            "id": case["id"],
            "name": case["name"],
            "box": box,
            "input": inp,
            "views": {},
        }
        for view in ("interior", "exterior"):
            if inp["kind"] == "leaves":
                leaves = inp["leaves"]
                n = len(leaves)
                per_leaf: list[dict[str, Any]] = []
                leaf_w = box["w"] / n
                for index, leaf in enumerate(leaves):
                    opening = _build_opening(leaf)
                    prims = leaf_primitives(
                        opening,
                        view,  # type: ignore[arg-type]
                        unit=unit,
                        handle_mm=Decimal(str(leaf["handle_mm"])) if leaf.get("handle_mm") is not None else None,
                    )
                    lx = box["x"] + leaf_w * index
                    per_leaf.append(
                        {
                            "prims": _prims_json(prims),
                            "paths": _paths_json(
                                prims, lx, box["y"], leaf_w, box["h"],
                                leaf_bottom=box["y"] + box["h"],
                            ),
                        }
                    )
                fixture["views"][view] = {
                    "stiles": max(0, n - 1),
                    "leaves": per_leaf,
                }
            else:
                layout = _build_layout(inp)
                all_prims = sliding_primitives(
                    layout, view  # type: ignore[arg-type]
                )
                n = len(all_prims)
                leaf_w = box["w"] / n
                fixture["views"][view] = {
                    "stiles": 0,
                    "leaves": [
                        {
                            "prims": _prims_json(prims),
                            "paths": _paths_json(
                                prims,
                                box["x"] + leaf_w * index,
                                box["y"],
                                leaf_w,
                                box["h"],
                                leaf_bottom=box["y"] + box["h"],
                            ),
                        }
                        for index, prims in enumerate(all_prims)
                    ],
                }
        path = OUT_DIR / f"{case['id']}.json"
        path.write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        count += 1
        print(f"  {path.relative_to(ROOT)}")
    return count


if __name__ == "__main__":
    print(f"Generating {len(CASES)} symbol fixtures → {OUT_DIR}")
    generate()
