"""P05 — opening symbology contract: one primitive grammar for every
surface that draws an elevation (editor canvas, technical PDF, portal).

The DIN/EN-12519 grammar DEKOPEN follows — the contract lives in
docs/PRD/opening-symbols.md:

- a hinged leaf draws triangle lines whose BASE is the hinge edge and
  whose APEX sits on the opposite edge at 40 % from the edge's start
  (40 %, not 50 % — the asymmetric apex reads as a draughting mark,
  never as a play button);
- a tilt-turn leaf draws its two modes: the side-hinge triangle plus the
  bottom-hinge (tilt) triangle;
- a sliding leaf draws a horizontal arrow parallel to the rail in its
  declared ``travel`` direction — never a hinged triangle;
- a fixed leaf draws nothing: fixed means silence;
- door leaves draw the same triangle grammar in elevation — the swing
  arc belongs to the plan view, not the elevation — plus the sill
  accent under operable leaves;
- an operable leaf carries a handle mark on its free edge at the
  declared ``handle_height_mm`` datum.

View convention: primitives are emitted in DATA space (hinge sides and
travel directions as declared in the model). "Vista exterior" renders
the whole elevation mirrored horizontally; the only per-primitive
change is the stroke — solid/dashed inverts because opening direction
is measured against the viewer (INWARD opens toward the interior
viewer, away from the exterior one). Mirroring is a property of the
sheet, not of the primitive, so renderers wrap the drawing in a
horizontal mirror and keep these primitives unchanged.

The TypeScript twin ``frontend/src/features/canvas/openingSymbols.ts``
implements the identical mapping; the JSON fixtures under
``engine/tests/fixtures/symbols/`` pin both implementations to the same
output — primitives and canonical path data — so a divergence fails the
parity tests on both sides.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from dekopen_engine.models import (
    EngineModel,
    HingeSide,
    LeafRole,
    Opening,
    OpeningDirection,
    OpeningMovement,
    SlidingLayout,
    SlidingPanelKind,
    SlidingTravel,
    UnitKind,
)

# Fraction along the free edge where the triangle apex lands — measured
# from the edge's start (top for vertical edges, left for horizontal
# ones). board-04 icon grammar: 40 %, not the centered 50 %.
APEX_AT = Decimal("0.4")

ElevationView = Literal["interior", "exterior"]

_HANDLE_INSET_MM = Decimal("26")
_HANDLE_ARM_MM = Decimal("9")
_ARROW_LEN = Decimal("0.24")  # of the glyph box width
_ARROW_HEAD = Decimal("0.45")  # of the arrow half-length
_ARROW_BARB = Decimal("0.32")  # of the arrow half-length
_GLYPH_PAD_X = Decimal("0.20")  # of the glyph box width
_GLYPH_PAD_Y = Decimal("0.12")  # of the glyph box height
_DASH = "6 3"  # canonical stroke-dasharray for "opens away"


class GlyphPrimitive(EngineModel):
    """One drawable mark inside a leaf's glyph box — renderer-agnostic.

    ``k`` values:
    - ``tri``: DIN triangle; `hinge` names the edge carrying the base,
      ``apex_at`` the fraction along the opposite edge, ``dash`` the
      stroke (dashed = opens away from the viewer).
    - ``arrow``: sliding leaf travel; ``dir`` is the resolved direction
      (None when no travel exists anywhere to resolve) and ``inferred``
      marks the presentation convention — surfaces badge it
      "dirección inferida".
    - ``lift_arrow``: HST leaf — the same displacement arrow with a
      vertical kink in the shaft that reads as the lift gesture.
    - ``varrow``: guillotina — vertical arrow; ``vdir`` is the resolved
      direction (None → double-headed) and ``inferred`` marks the
      presentation convention like ``arrow``.
    - ``axis``: pivot leaf — dashed centre line at the declared pivot
      axis; ``axis_dir`` is "v" (offset from the left edge) or "h"
      (offset from the top edge) and ``at_mm`` the offset.
    - ``handle``: handle mark; ``side`` is the edge it sits on (left/
      right free stile, or the bottom/top rail of a hopper/tilt leaf)
      and ``at_mm`` the datum from the leaf bottom.
    - ``sill``: threshold accent under a door leaf.
    - ``none``: a leaf that draws no mark (FIXED) — explicit so a missing
      symbol is a decision, not an omission.
    """

    k: Literal["tri", "arrow", "lift_arrow", "varrow", "axis", "handle", "sill", "none"]
    hinge: HingeSide | None = None
    apex_at: Decimal = APEX_AT
    dash: bool = False
    dir: SlidingTravel | None = None
    vdir: Literal["UP", "DOWN"] | None = None
    axis_dir: Literal["v", "h"] | None = None
    inferred: bool = False
    side: Literal["left", "right", "top", "bottom"] | None = None
    at_mm: Decimal | None = None


def _opens_away(opening: Opening, view: ElevationView) -> bool:
    """Whether the leaf opens away from the viewer of ``view`` — the dash
    rule. Direction is declared from the interior: INWARD opens toward
    the interior viewer and away from the exterior one."""
    if opening.direction is None:
        return False
    if view == "exterior":
        return opening.direction is OpeningDirection.INWARD
    return opening.direction is OpeningDirection.OUTWARD


def _handle_side(opening: Opening) -> Literal["left", "right", "top", "bottom"]:
    """Edge an operable leaf's handle sits on: the stile opposite the
    side hinge, the bottom rail of a top-hung leaf, the top rail of a
    bottom-hung one."""
    hinge = opening.hinge_side
    if hinge is HingeSide.LEFT:
        return "right"
    if hinge is HingeSide.RIGHT:
        return "left"
    if hinge is HingeSide.TOP:
        return "bottom"
    return "top"


def _is_operable(opening: Opening) -> bool:
    """Operable = takes a handle: every non-FIXED leaf that is not a
    PASSIVE inversor leaf (those ride falleba bolts instead)."""
    return (
        opening.movement is not OpeningMovement.FIXED
        and opening.leaf_role is not LeafRole.PASSIVE
    )


def leaf_primitives(
    opening: Opening,
    view: ElevationView = "interior",
    *,
    unit: UnitKind = UnitKind.WINDOW,
    handle_mm: Decimal | None = None,
    axis_mm: Decimal | None = None,
    slot: str | None = None,
) -> list[GlyphPrimitive]:
    """Primitives for one leaf spec — per leaf, in slot order. The caller
    owns the leaf's glyph box; positions stay symbolic (``hinge`` /
    ``apex_at`` / ``dir`` / ``vdir`` / ``side``), never pixel
    coordinates. ``axis_mm`` is the declared pivot offset of a pivot
    leaf; ``slot`` (TOP/BOTTOM) resolves the guillotina arrow direction
    — without it the primitive declares "slides vertically" only."""
    movement = opening.movement
    if movement is OpeningMovement.FIXED:
        return [GlyphPrimitive(k="none")]
    dash = _opens_away(opening, view)
    hinge = opening.hinge_side
    prims: list[GlyphPrimitive] = []
    if movement in (
        OpeningMovement.TURN,
        OpeningMovement.TILT_TURN,
        OpeningMovement.FOLD,
    ) and hinge in (HingeSide.LEFT, HingeSide.RIGHT):
        prims.append(GlyphPrimitive(k="tri", hinge=hinge, dash=dash))
    if (
        movement is OpeningMovement.TILT_TURN
        or movement is OpeningMovement.TILT
        or movement is OpeningMovement.BOTTOM_HUNG
        # La hoja osciloparalela dibuja su basculante: el triángulo de
        # bisagra inferior más la flecha de desplazamiento.
        or movement is OpeningMovement.PARALLEL_SLIDE
    ):
        prims.append(GlyphPrimitive(k="tri", hinge=HingeSide.BOTTOM, dash=dash))
    elif movement is OpeningMovement.TOP_HUNG:
        prims.append(GlyphPrimitive(k="tri", hinge=HingeSide.TOP, dash=dash))
    if movement in (OpeningMovement.PIVOT_V, OpeningMovement.PIVOT_H):
        # Hoja pivotante: el eje marcado es el símbolo — línea de eje a
        # la distancia declarada, nunca un triángulo de bisagra.
        prims.append(
            GlyphPrimitive(
                k="axis",
                axis_dir="v" if movement is OpeningMovement.PIVOT_V else "h",
                at_mm=axis_mm,
                dash=dash,
            )
        )
    if movement is OpeningMovement.LIFT_SLIDE:
        # Corredera elevable — flecha de desplazamiento con quiebro de
        # elevación; la dirección la resuelve el layout, igual que la
        # corredera (sin dirección → doble punta con quiebro).
        prims.append(
            GlyphPrimitive(k="lift_arrow", dir=None, dash=dash, inferred=True)
        )
    elif movement is OpeningMovement.VERTICAL_SLIDE:
        # Guillotina — flecha vertical; la hoja de abajo sube (UP) y la
        # de arriba baja (DOWN) cuando el slot lo declara.
        vdir = (
            "UP" if slot == "BOTTOM" else "DOWN" if slot == "TOP" else None
        )
        prims.append(
            GlyphPrimitive(
                k="varrow",
                vdir=vdir,  # type: ignore[arg-type]
                dash=dash,
                inferred=vdir is None,
            )
        )
    elif movement.endswith("SLIDE"):
        # A spec-level sliding leaf carries no travel — the layout does.
        # The renderer supplies the direction from `sliding_primitives`;
        # here the arrow only declares "this leaf slides" (unspecified
        # direction → the renderer draws a double-headed arrow).
        prims.append(GlyphPrimitive(k="arrow", dir=None, dash=dash, inferred=True))
    if unit is UnitKind.DOOR:
        # The threshold accent runs under every door LEAF (active and
        # passive leaves alike sit on the sill); fixed lites in the unit
        # keep their frame — they returned "none" above.
        prims.insert(0, GlyphPrimitive(k="sill"))
    if _is_operable(opening) and handle_mm is not None:
        prims.append(
            GlyphPrimitive(
                k="handle",
                side=_handle_side(opening),
                at_mm=handle_mm,
            )
        )
    return prims


def sliding_primitives(
    layout: SlidingLayout,
    view: ElevationView = "interior",
    *,
    movement: OpeningMovement = OpeningMovement.SLIDE,
) -> list[list[GlyphPrimitive]]:
    """Per-panel primitives of a sliding layout, in slot order. The arrow
    direction is the declared travel; when the layout pre-dates ``travel``
    the documented convention resolves it and the primitive is flagged
    ``inferred`` so the surfaces can badge "dirección inferida".
    ``movement`` selects the family glyph: LIFT_SLIDE panels draw the
    kinked lift arrow, PARALLEL_SLIDE panels the tilt triangle plus the
    arrow."""
    from dekopen_engine.geometry import panel_travel, travel_inferred

    count = len(layout.panels)
    out: list[list[GlyphPrimitive]] = []
    for index, panel in enumerate(layout.panels):
        if panel.kind is SlidingPanelKind.FIXED:
            out.append([GlyphPrimitive(k="none")])
            continue
        direction = panel_travel(panel, index, count)
        arrow_kind = (
            "lift_arrow" if movement is OpeningMovement.LIFT_SLIDE else "arrow"
        )
        prims = [
            GlyphPrimitive(
                k=arrow_kind,  # type: ignore[arg-type]
                dir=direction,
                inferred=travel_inferred(panel),
            )
        ]
        if movement is OpeningMovement.PARALLEL_SLIDE:
            prims.insert(
                0, GlyphPrimitive(k="tri", hinge=HingeSide.BOTTOM)
            )
        out.append(prims)
    return out


# ---------------------------------------------------------------------------
# Canonical geometry — the mm mapping every renderer shares. `glyph_paths`
# turns primitives into SVG path data for a leaf's glyph box; renderers
# only pick stroke/fill attributes. The fixtures pin these exact strings
# for a reference box, so the canvas and the PDF cannot drift apart.
# ---------------------------------------------------------------------------


def _fmt(value: Decimal) -> str:
    """Canonical number formatting for path data — integers stay
    integers, decimals keep at most 2 places (0.01 mm tolerance)."""
    quantized = value.quantize(Decimal("0.01"))
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def glyph_paths(
    prims: list[GlyphPrimitive],
    x: Decimal,
    y: Decimal,
    w: Decimal,
    h: Decimal,
    *,
    leaf_bottom: Decimal | None = None,
) -> list[tuple[str, str | None]]:
    """SVG path data for the primitives inside leaf box (x, y, w, h).

    Returns (d, dash) pairs — dash is the ``stroke-dasharray`` value to
    apply ("6 3" convention) or None for a solid stroke. ``leaf_bottom``
    is the mm y of the sill line the handle datum measures from (defaults
    to the box bottom).
    """
    pad_x = w * _GLYPH_PAD_X
    pad_y = h * _GLYPH_PAD_Y
    ix, iy = x + pad_x, y + pad_y
    iw, ih = w - 2 * pad_x, h - 2 * pad_y
    bottom = leaf_bottom if leaf_bottom is not None else y + h
    paths: list[tuple[str, str | None]] = []
    for prim in prims:
        if prim.k == "tri" and prim.hinge is not None:
            a = prim.apex_at
            if prim.hinge is HingeSide.LEFT:
                apex_x, apex_y = ix + iw, iy + ih * a
                d = (
                    f"M {_fmt(ix)} {_fmt(iy)} L {_fmt(apex_x)} {_fmt(apex_y)}"
                    f" L {_fmt(ix)} {_fmt(iy + ih)}"
                )
            elif prim.hinge is HingeSide.RIGHT:
                apex_x, apex_y = ix, iy + ih * a
                d = (
                    f"M {_fmt(ix + iw)} {_fmt(iy)} L {_fmt(apex_x)} {_fmt(apex_y)}"
                    f" L {_fmt(ix + iw)} {_fmt(iy + ih)}"
                )
            elif prim.hinge is HingeSide.TOP:
                apex_x, apex_y = ix + iw * a, iy + ih
                d = (
                    f"M {_fmt(ix)} {_fmt(iy)} L {_fmt(apex_x)} {_fmt(apex_y)}"
                    f" L {_fmt(ix + iw)} {_fmt(iy)}"
                )
            else:  # BOTTOM — the tilt triangle of an oscilobatiente
                apex_x, apex_y = ix + iw * a, iy
                d = (
                    f"M {_fmt(ix)} {_fmt(iy + ih)} L {_fmt(apex_x)} {_fmt(apex_y)}"
                    f" L {_fmt(ix + iw)} {_fmt(iy + ih)}"
                )
            paths.append((d, _DASH if prim.dash else None))
        elif prim.k == "arrow":
            half = iw * _ARROW_LEN
            cx, cy = x + w / 2, y + h / 2
            head, barb = half * _ARROW_HEAD, half * _ARROW_BARB
            if prim.dir is SlidingTravel.LEFT:
                tip, tail = cx - half, cx + half
                d = (
                    f"M {_fmt(tail)} {_fmt(cy)} H {_fmt(tip)}"
                    f" M {_fmt(tip + head)} {_fmt(cy - barb)} L {_fmt(tip)} {_fmt(cy)}"
                    f" L {_fmt(tip + head)} {_fmt(cy + barb)}"
                )
            elif prim.dir is SlidingTravel.RIGHT:
                tip, tail = cx + half, cx - half
                d = (
                    f"M {_fmt(tail)} {_fmt(cy)} H {_fmt(tip)}"
                    f" M {_fmt(tip - head)} {_fmt(cy - barb)} L {_fmt(tip)} {_fmt(cy)}"
                    f" L {_fmt(tip - head)} {_fmt(cy + barb)}"
                )
            else:
                # Direction nowhere declared or resolvable — a double
                # arrow says "slides" without inventing a handedness.
                tip_r, tip_l = cx + half, cx - half
                d = (
                    f"M {_fmt(tip_l)} {_fmt(cy)} H {_fmt(tip_r)}"
                    f" M {_fmt(tip_r - head)} {_fmt(cy - barb)} L {_fmt(tip_r)} {_fmt(cy)}"
                    f" L {_fmt(tip_r - head)} {_fmt(cy + barb)}"
                    f" M {_fmt(tip_l + head)} {_fmt(cy - barb)} L {_fmt(tip_l)} {_fmt(cy)}"
                    f" L {_fmt(tip_l + head)} {_fmt(cy + barb)}"
                )
            paths.append((d, _DASH if prim.dash else None))
        elif prim.k == "lift_arrow":
            # Corredera elevable — el desplazamiento lleva un quiebro
            # vertical en el vástago: el gesto de elevar la hoja.
            half = iw * _ARROW_LEN
            cx, cy = x + w / 2, y + h / 2
            head, barb = half * _ARROW_HEAD, half * _ARROW_BARB
            step_y = ih * Decimal("0.09")
            step_x = half * Decimal("0.30")

            def _lift_head(tip: Decimal, towards: Decimal) -> str:
                barb_x = tip + head if towards < tip else tip - head
                return (
                    f" M {_fmt(barb_x)} {_fmt(cy - barb)} L {_fmt(tip)} {_fmt(cy)}"
                    f" L {_fmt(barb_x)} {_fmt(cy + barb)}"
                )

            def _lift_shaft(tail: Decimal, tip: Decimal) -> str:
                return (
                    f"M {_fmt(tail)} {_fmt(cy)}"
                    f" H {_fmt(cx - step_x)} V {_fmt(cy - step_y)}"
                    f" H {_fmt(cx + step_x)} V {_fmt(cy)} H {_fmt(tip)}"
                )

            if prim.dir is SlidingTravel.LEFT:
                tip, tail = cx - half, cx + half
                d = _lift_shaft(tail, tip) + _lift_head(tip, tail)
            elif prim.dir is SlidingTravel.RIGHT:
                tip, tail = cx + half, cx - half
                d = _lift_shaft(tail, tip) + _lift_head(tip, tail)
            else:
                tip_r, tip_l = cx + half, cx - half
                d = (
                    _lift_shaft(tip_l, tip_r)
                    + _lift_head(tip_r, tip_l)
                    + _lift_head(tip_l, tip_r)
                )
            paths.append((d, _DASH if prim.dash else None))
        elif prim.k == "varrow":
            # Guillotina — flecha vertical centrada; doble punta cuando la
            # dirección no está resuelta.
            half = ih * _ARROW_LEN
            cx, cy = x + w / 2, y + h / 2
            head, barb = half * _ARROW_HEAD, half * _ARROW_BARB
            if prim.vdir == "UP":
                tip, tail = cy - half, cy + half
                d = (
                    f"M {_fmt(cx)} {_fmt(tail)} V {_fmt(tip)}"
                    f" M {_fmt(cx - barb)} {_fmt(tip + head)} L {_fmt(cx)} {_fmt(tip)}"
                    f" L {_fmt(cx + barb)} {_fmt(tip + head)}"
                )
            elif prim.vdir == "DOWN":
                tip, tail = cy + half, cy - half
                d = (
                    f"M {_fmt(cx)} {_fmt(tail)} V {_fmt(tip)}"
                    f" M {_fmt(cx - barb)} {_fmt(tip - head)} L {_fmt(cx)} {_fmt(tip)}"
                    f" L {_fmt(cx + barb)} {_fmt(tip - head)}"
                )
            else:
                tip_t, tip_b = cy - half, cy + half
                d = (
                    f"M {_fmt(cx)} {_fmt(tip_b)} V {_fmt(tip_t)}"
                    f" M {_fmt(cx - barb)} {_fmt(tip_t + head)} L {_fmt(cx)} {_fmt(tip_t)}"
                    f" L {_fmt(cx + barb)} {_fmt(tip_t + head)}"
                    f" M {_fmt(cx - barb)} {_fmt(tip_b - head)} L {_fmt(cx)} {_fmt(tip_b)}"
                    f" L {_fmt(cx + barb)} {_fmt(tip_b - head)}"
                )
            paths.append((d, _DASH if prim.dash else None))
        elif prim.k == "axis" and prim.axis_dir is not None:
            # Hoja pivotante — el eje declarado, siempre a trazos.
            offset = prim.at_mm
            if prim.axis_dir == "v":
                ax = x + (offset if offset is not None else w / 2)
                ax = min(max(ax, x), x + w)
                d = f"M {_fmt(ax)} {_fmt(y)} V {_fmt(y + h)}"
            else:
                ay = y + (offset if offset is not None else h / 2)
                ay = min(max(ay, y), y + h)
                d = f"M {_fmt(x)} {_fmt(ay)} H {_fmt(x + w)}"
            paths.append((d, _DASH))
        elif prim.k == "handle" and prim.side is not None:
            arm = _HANDLE_ARM_MM
            datum = prim.at_mm or Decimal("0")
            if prim.side == "left":
                hx, hy = x + _HANDLE_INSET_MM, bottom - datum
            elif prim.side == "right":
                hx, hy = x + w - _HANDLE_INSET_MM, bottom - datum
            elif prim.side == "top":
                hx, hy = x + w / 2, y + _HANDLE_INSET_MM
            else:
                hx, hy = x + w / 2, bottom - _HANDLE_INSET_MM
            d = (
                f"M {_fmt(hx - arm)} {_fmt(hy)} H {_fmt(hx + arm)}"
                f" M {_fmt(hx)} {_fmt(hy - arm)} V {_fmt(hy + arm)}"
            )
            paths.append((d, _DASH if prim.dash else None))
        elif prim.k == "sill":
            paths.append((f"M {_fmt(x)} {_fmt(y + h)} H {_fmt(x + w)}", None))
    return paths
