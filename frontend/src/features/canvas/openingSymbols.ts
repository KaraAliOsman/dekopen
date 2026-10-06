/**
 * P05 — opening symbology contract, TypeScript twin of the engine module
 * `dekopen_engine.opening_symbols`. Both implement the identical mapping
 * — the fixtures under `engine/tests/fixtures/symbols/` pin primitives
 * AND canonical path data for a reference leaf box in both views, so the
 * canvas and the PDF cannot drift apart (parity test below).
 *
 * The DIN/EN-12519 grammar (docs/PRD/opening-symbols.md):
 * - hinged leaf → triangle lines, base on the hinge edge, apex on the
 *   opposite edge at 40 % (board-04 icon grammar — not the centered 50 %);
 * - tilt-turn → side-hinge triangle + bottom-hinge (tilt) triangle;
 * - sliding leaf → horizontal arrow in its declared `travel` direction;
 * - fixed leaf → nothing (fixed means silence);
 * - door leaf → the same triangles in elevation + sill accent (the swing
 *   arc belongs to the plan view);
 * - operable leaf → handle mark on its free edge at `handle_height_mm`.
 *
 * View convention: primitives are emitted in DATA space (hinge sides and
 * travel as declared). "Vista exterior" renders the whole elevation
 * mirrored horizontally; the only per-primitive change is the stroke —
 * solid/dashed inverts because opening direction is measured against
 * the viewer. Mirroring is a property of the sheet, not the primitive.
 */

import type { LeafSpecPayload, OpeningSpecPayload, SlidingLayout } from "./intentEditing";
import { panelTravel, travelInferred } from "./intentEditing";

/** Fraction along the free edge where the triangle apex lands. */
export const APEX_AT = 0.4;

export type ElevationView = "interior" | "exterior";

export type GlyphPrimitive = {
  k: "tri" | "arrow" | "handle" | "sill" | "none";
  hinge?: "LEFT" | "RIGHT" | "TOP" | "BOTTOM" | null;
  apex_at?: number;
  dash?: boolean;
  dir?: "LEFT" | "RIGHT" | null;
  /** true cuando la dirección es la convención de presentación, no una
   * declaración del producto — las superficies la marcan
   * "dirección inferida". */
  inferred?: boolean;
  side?: "left" | "right" | "top" | "bottom" | null;
  at_mm?: number | null;
};

const HANDLE_INSET_MM = 26;
const HANDLE_ARM_MM = 9;
const ARROW_LEN = 0.24; // of the glyph box width
const ARROW_HEAD = 0.45; // of the arrow half-length
const ARROW_BARB = 0.32; // of the arrow half-length
const GLYPH_PAD_X = 0.2;
const GLYPH_PAD_Y = 0.12;
export const GLYPH_DASH = "6 3";

function opensAway(opening: OpeningSpecPayload, view: ElevationView): boolean {
  if (!opening.direction) return false;
  if (view === "exterior") return opening.direction === "INWARD";
  return opening.direction === "OUTWARD";
}

function handleSide(opening: OpeningSpecPayload): GlyphPrimitive["side"] {
  if (opening.hinge_side === "LEFT") return "right";
  if (opening.hinge_side === "RIGHT") return "left";
  if (opening.hinge_side === "TOP") return "bottom";
  return "top";
}

function isOperable(opening: OpeningSpecPayload): boolean {
  return opening.movement !== "FIXED" && opening.leaf_role !== "PASSIVE";
}

/** Primitives for one leaf spec — per leaf, in slot order. Mirrors
 * `opening_symbols.leaf_primitives`. */
export function leafPrimitives(
  opening: OpeningSpecPayload,
  view: ElevationView = "interior",
  opts: { unit?: string; handle_mm?: number | null } = {},
): GlyphPrimitive[] {
  const movement = opening.movement;
  if (movement === "FIXED") return [{ k: "none" }];
  const dash = opensAway(opening, view);
  const hinge = opening.hinge_side;
  const prims: GlyphPrimitive[] = [];
  if (
    (movement === "TURN" ||
      movement === "TILT_TURN" ||
      movement === "FOLD" ||
      movement === "PIVOT_V") &&
    (hinge === "LEFT" || hinge === "RIGHT")
  ) {
    prims.push({ k: "tri", hinge, apex_at: APEX_AT, dash });
  }
  if (movement === "TILT_TURN" || movement === "TILT" || movement === "BOTTOM_HUNG") {
    prims.push({ k: "tri", hinge: "BOTTOM", apex_at: APEX_AT, dash });
  } else if (movement === "TOP_HUNG") {
    prims.push({ k: "tri", hinge: "TOP", apex_at: APEX_AT, dash });
  }
  if (movement.endsWith("SLIDE")) {
    // A spec-level sliding leaf carries no travel — the layout does; the
    // double-headed arrow only declares "this leaf slides".
    prims.push({ k: "arrow", dir: null, dash, inferred: true });
  }
  if (opts.unit === "DOOR") {
    // Threshold accent under every door leaf (active and passive sit on
    // the sill); fixed lites keep their frame.
    prims.unshift({ k: "sill" });
  }
  if (isOperable(opening) && opts.handle_mm != null) {
    prims.push({ k: "handle", side: handleSide(opening), at_mm: opts.handle_mm });
  }
  return prims;
}

/** Per-panel primitives of a sliding layout, in slot order — mirrors
 * `opening_symbols.sliding_primitives`. */
export function slidingPrimitives(
  layout: SlidingLayout,
  _view: ElevationView = "interior",
): GlyphPrimitive[][] {
  const count = layout.panels.length;
  return layout.panels.map((panel, index) => {
    if (panel.kind === "FIXED") return [{ k: "none" }];
    return [
      {
        k: "arrow",
        dir: panelTravel(panel, index, count),
        inferred: travelInferred(panel),
      },
    ];
  });
}

/** Leaves for a bay expressed in the contract's vocabulary — either the
 * D03 `leaves`/`opening` spec or the legacy `opening_type` enum mapped
 * to its equivalent spec. Returns null when the bay is not a leaf bay. */
export function leafSpecsForBay(node: {
  opening_type?: string | null;
  opening?: OpeningSpecPayload | null;
  leaves?: LeafSpecPayload[] | null;
  unit_kind?: string | null;
  door_handedness?: string | null;
}): { leaves: OpeningSpecPayload[]; unit: string } | null {
  const unit = node.unit_kind ?? "WINDOW";
  if (Array.isArray(node.leaves) && node.leaves.length) {
    return { leaves: node.leaves.map((leaf) => leaf.opening), unit };
  }
  if (node.opening && node.opening.movement) {
    return { leaves: [node.opening], unit };
  }
  const legacy: Record<string, OpeningSpecPayload[]> = {
    TURN_LEFT: [{ movement: "TURN", hinge_side: "LEFT", direction: "INWARD" }],
    TURN_RIGHT: [{ movement: "TURN", hinge_side: "RIGHT", direction: "INWARD" }],
    TILT_TURN_LEFT: [{ movement: "TILT_TURN", hinge_side: "LEFT", direction: "INWARD" }],
    TILT_TURN_RIGHT: [{ movement: "TILT_TURN", hinge_side: "RIGHT", direction: "INWARD" }],
    AWNING: [{ movement: "TOP_HUNG", hinge_side: "TOP", direction: "OUTWARD" }],
    FIXED: [{ movement: "FIXED" }],
    DOOR_ENTRY: [
      {
        movement: "TURN",
        hinge_side: node.door_handedness === "RIGHT" ? "RIGHT" : "LEFT",
        direction: "INWARD",
      },
    ],
    DOOR_DOUBLE: [
      { movement: "TURN", hinge_side: "LEFT", direction: "INWARD", leaf_role: "ACTIVE" },
      { movement: "TURN", hinge_side: "RIGHT", direction: "INWARD", leaf_role: "PASSIVE" },
    ],
  };
  const spec = node.opening_type ? legacy[node.opening_type] : undefined;
  if (!spec) return null;
  return { leaves: spec, unit };
}

/** Canonical mm mapping shared with `opening_symbols.glyph_paths` —
 * turns primitives into SVG path data inside a leaf's glyph box.
 * Returns {d, dash} pairs; `leafBottom` is the mm y of the sill line the
 * handle datum measures from (defaults to the box bottom). */
export function glyphPaths(
  prims: GlyphPrimitive[],
  x: number,
  y: number,
  w: number,
  h: number,
  leafBottom?: number,
): { d: string; dash: string | null; inferred: boolean; k: GlyphPrimitive["k"] }[] {
  const padX = w * GLYPH_PAD_X;
  const padY = h * GLYPH_PAD_Y;
  const ix = x + padX;
  const iy = y + padY;
  const iw = w - 2 * padX;
  const ih = h - 2 * padY;
  const bottom = leafBottom ?? y + h;
  const paths: { d: string; dash: string | null; inferred: boolean; k: GlyphPrimitive["k"] }[] = [];
  for (const prim of prims) {
    if (prim.k === "tri" && prim.hinge) {
      const a = prim.apex_at ?? APEX_AT;
      let d: string;
      if (prim.hinge === "LEFT") {
        d = `M ${fmt(ix)} ${fmt(iy)} L ${fmt(ix + iw)} ${fmt(iy + ih * a)} L ${fmt(ix)} ${fmt(iy + ih)}`;
      } else if (prim.hinge === "RIGHT") {
        d = `M ${fmt(ix + iw)} ${fmt(iy)} L ${fmt(ix)} ${fmt(iy + ih * a)} L ${fmt(ix + iw)} ${fmt(iy + ih)}`;
      } else if (prim.hinge === "TOP") {
        d = `M ${fmt(ix)} ${fmt(iy)} L ${fmt(ix + iw * a)} ${fmt(iy + ih)} L ${fmt(ix + iw)} ${fmt(iy)}`;
      } else {
        d = `M ${fmt(ix)} ${fmt(iy + ih)} L ${fmt(ix + iw * a)} ${fmt(iy)} L ${fmt(ix + iw)} ${fmt(iy + ih)}`;
      }
      paths.push({ d, dash: prim.dash ? GLYPH_DASH : null, inferred: !!prim.inferred, k: prim.k });
    } else if (prim.k === "arrow") {
      const half = iw * ARROW_LEN;
      const cx = x + w / 2;
      const cy = y + h / 2;
      const head = half * ARROW_HEAD;
      const barb = half * ARROW_BARB;
      let d: string;
      if (prim.dir === "LEFT") {
        const tip = cx - half;
        const tail = cx + half;
        d = `M ${fmt(tail)} ${fmt(cy)} H ${fmt(tip)} M ${fmt(tip + head)} ${fmt(cy - barb)} L ${fmt(tip)} ${fmt(cy)} L ${fmt(tip + head)} ${fmt(cy + barb)}`;
      } else if (prim.dir === "RIGHT") {
        const tip = cx + half;
        const tail = cx - half;
        d = `M ${fmt(tail)} ${fmt(cy)} H ${fmt(tip)} M ${fmt(tip - head)} ${fmt(cy - barb)} L ${fmt(tip)} ${fmt(cy)} L ${fmt(tip - head)} ${fmt(cy + barb)}`;
      } else {
        const tipR = cx + half;
        const tipL = cx - half;
        d = `M ${fmt(tipL)} ${fmt(cy)} H ${fmt(tipR)} M ${fmt(tipR - head)} ${fmt(cy - barb)} L ${fmt(tipR)} ${fmt(cy)} L ${fmt(tipR - head)} ${fmt(cy + barb)} M ${fmt(tipL + head)} ${fmt(cy - barb)} L ${fmt(tipL)} ${fmt(cy)} L ${fmt(tipL + head)} ${fmt(cy + barb)}`;
      }
      paths.push({ d, dash: prim.dash ? GLYPH_DASH : null, inferred: !!prim.inferred, k: prim.k });
    } else if (prim.k === "handle" && prim.side) {
      const arm = HANDLE_ARM_MM;
      const datum = prim.at_mm ?? 0;
      let hx: number;
      let hy: number;
      if (prim.side === "left") {
        hx = x + HANDLE_INSET_MM;
        hy = bottom - datum;
      } else if (prim.side === "right") {
        hx = x + w - HANDLE_INSET_MM;
        hy = bottom - datum;
      } else if (prim.side === "top") {
        hx = x + w / 2;
        hy = y + HANDLE_INSET_MM;
      } else {
        hx = x + w / 2;
        hy = bottom - HANDLE_INSET_MM;
      }
      paths.push({
        d: `M ${fmt(hx - arm)} ${fmt(hy)} H ${fmt(hx + arm)} M ${fmt(hx)} ${fmt(hy - arm)} V ${fmt(hy + arm)}`,
        dash: prim.dash ? GLYPH_DASH : null,
        inferred: !!prim.inferred,
        k: prim.k,
      });
    } else if (prim.k === "sill") {
      paths.push({
        d: `M ${fmt(x)} ${fmt(y + h)} H ${fmt(x + w)}`,
        dash: null,
        inferred: false,
        k: prim.k,
      });
    }
  }
  return paths;
}

/** `fmt` twin of the engine's — integers stay integers, decimals keep
 * at most 2 places (0.01 mm tolerance). */
export function fmt(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  return Object.is(rounded, -0) ? "0" : String(rounded);
}
