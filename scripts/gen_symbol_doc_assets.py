#!/usr/bin/env python3
"""Generate the contract's per-case illustrations for
`docs/PRD/opening-symbols.md` — one SVG per fixture × view, drawn by the
engine itself so the documentation can never drift from the renderer.

Run:  PYTHONPATH=engine/src .venv/bin/python scripts/gen_symbol_doc_assets.py
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from dekopen_engine.models import (
    HingeSide,
    BayLeaf,
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
from dekopen_engine.opening_symbols import (
    glyph_paths,
    leaf_primitives,
    sliding_primitives,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "engine/tests/fixtures/symbols"
OUT = ROOT / "docs/PRD/assets/opening-symbols"


def _opening(raw: dict) -> Opening:
    return Opening(
        movement=OpeningMovement(raw["movement"]),
        hinge_side=HingeSide(raw.get("hinge_side") or "NONE"),
        direction=(
            OpeningDirection(raw["direction"]) if raw.get("direction") else None
        ),
        leaf_role=LeafRole(raw.get("leaf_role", "SINGLE")),
        fixed_in_sash=bool(raw.get("fixed_in_sash")),
    )


def _draw_case(fixture: dict, view: str) -> str:
    box = fixture["box"]
    bw, bh = Decimal(str(box["w"])), Decimal(str(box["h"]))
    unit = UnitKind(fixture["input"]["unit"])
    stroke = min(bw, bh) / Decimal("140")
    parts = [
        f'<rect x="0" y="0" width="{bw}" height="{bh}" fill="none" '
        f'stroke="#465158" stroke-width="{stroke * 2}"/>'
    ]
    if fixture["input"]["kind"] == "leaves":
        leaves = [
            BayLeaf(slot=str(i), opening=_opening(raw))
            for i, raw in enumerate(fixture["input"]["leaves"])
        ]
        lw = bw / len(leaves)
        for index, raw in enumerate(fixture["input"]["leaves"]):
            prims = leaf_primitives(
                leaves[index].opening, view, unit=unit,
                handle_mm=(Decimal(str(raw["handle_mm"])) if raw.get("handle_mm") else None),
            )
            for path_d, dash in glyph_paths(
                prims, lw * index, Decimal("0"), lw, bh
            ):
                attrs = f' stroke-dasharray="{dash}"' if dash else ""
                parts.append(
                    f'<path d="{path_d}" fill="none" stroke="#075F5A" '
                    f'stroke-width="{stroke}"{attrs}/>'
                )
    else:
        layout = SlidingLayout(
            tracks=fixture["input"]["tracks"],
            panels=[
                SlidingPanel(
                    slot=raw["slot"],
                    kind=SlidingPanelKind(raw["kind"]),
                    track=raw.get("track"),
                    travel=(
                        SlidingTravel(raw["travel"]) if raw.get("travel") else None
                    ),
                )
                for raw in fixture["input"]["panels"]
            ],
        )
        pw = bw / len(layout.panels)
        for index, prims in enumerate(sliding_primitives(layout, view)):
            for path_d, dash in glyph_paths(
                prims, pw * index, Decimal("0"), pw, bh
            ):
                attrs = f' stroke-dasharray="{dash}"' if dash else ""
                parts.append(
                    f'<path d="{path_d}" fill="none" stroke="#075F5A" '
                    f'stroke-width="{stroke}"{attrs}/>'
                )
    label = "Vista interior" if view == "interior" else "Vista exterior"
    parts.append(
        f'<text x="{bw}" y="-4" font-size="18" text-anchor="end" '
        f'font-family="monospace" fill="#465158">{label}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 -24 {bw} {bh + 28}">' + "".join(parts) + "</svg>"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted(FIXTURES.glob("*.json")):
        fixture = json.loads(path.read_text())
        for view in ("interior", "exterior"):
            (OUT / f"{fixture['id']}-{view}.svg").write_text(
                _draw_case(fixture, view)
            )
    print(f"wrote {len(list(OUT.glob('*.svg')))} svg assets to {OUT}")


if __name__ == "__main__":
    main()
