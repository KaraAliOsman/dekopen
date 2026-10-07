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
  k: "tri" | "arrow" | "lift_arrow" | "varrow" | "axis" | "handle" | "sill" | "none";
  hinge?: "LEFT" | "RIGHT" | "TOP" | "BOTTOM" | null;
  apex_at?: number;
  dash?: boolean;
  dir?: "LEFT" | "RIGHT" | null;
  /** Dirección vertical resuelta de una guillotina. */
  vdir?: "UP" | "DOWN" | null;
  /** Orientación del eje pivotante: "v" (desde el canto izquierdo) o
   * "h" (desde el canto superior), a la distancia `at_mm`. */
  axis_dir?: "v" | "h" | null;
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
  opts: {
    unit?: string;
    handle_mm?: number | null;
    axis_mm?: number | null;
    slot?: string | null;
  } = {},
): GlyphPrimitive[] {
  const movement = opening.movement;
  if (movement === "FIXED") return [{ k: "none" }];
  const dash = opensAway(opening, view);
  const hinge = opening.hinge_side;
  const prims: GlyphPrimitive[] = [];
  if (
    (movement === "TURN" || movement === "TILT_TURN" || movement === "FOLD") &&
    (hinge === "LEFT" || hinge === "RIGHT")
  ) {
    prims.push({ k: "tri", hinge, apex_at: APEX_AT, dash });
  }
  if (
    movement === "TILT_TURN" ||
    movement === "TILT" ||
    movement === "BOTTOM_HUNG" ||
    // Osciloparalela: el basculante (triángulo inferior) + la flecha.
    movement === "PARALLEL_SLIDE"
  ) {
    prims.push({ k: "tri", hinge: "BOTTOM", apex_at: APEX_AT, dash });
  } else if (movement === "TOP_HUNG") {
    prims.push({ k: "tri", hinge: "TOP", apex_at: APEX_AT, dash });
  }
  if (movement === "PIVOT_V" || movement === "PIVOT_H") {
    // Pivotante: el eje declarado es el símbolo, nunca un triángulo.
    prims.push({
      k: "axis",
      axis_dir: movement === "PIVOT_V" ? "v" : "h",
      at_mm: opts.axis_mm ?? null,
      dash,
    });
  }
  if (movement === "LIFT_SLIDE") {
    // HST — flecha de desplazamiento con quiebro de elevación.
    prims.push({ k: "lift_arrow", dir: null, dash, inferred: true });
  } else if (movement === "VERTICAL_SLIDE") {
    // Guillotina — flecha vertical; la hoja BOTTOM sube, la TOP baja.
    const vdir =
      opts.slot === "BOTTOM" ? ("UP" as const) : opts.slot === "TOP" ? ("DOWN" as const) : null;
    prims.push({ k: "varrow", vdir, dash, inferred: vdir === null });
  } else if (movement.endsWith("SLIDE")) {
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
  movement = "SLIDE",
): GlyphPrimitive[][] {
  const count = layout.panels.length;
  return layout.panels.map((panel, index) => {
    if (panel.kind === "FIXED") return [{ k: "none" }];
    const arrowKind = movement === "LIFT_SLIDE" ? ("lift_arrow" as const) : ("arrow" as const);
    const prims: GlyphPrimitive[] = [
      {
        k: arrowKind,
        dir: panelTravel(panel, index, count),
        inferred: travelInferred(panel),
      },
    ];
    if (movement === "PARALLEL_SLIDE") {
      prims.unshift({ k: "tri", hinge: "BOTTOM", apex_at: APEX_AT });
    }
    return prims;
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
    } else if (prim.k === "lift_arrow") {
      // HST — el vástago lleva un quiebro vertical: el gesto de elevar.
      const half = iw * ARROW_LEN;
      const cx = x + w / 2;
      const cy = y + h / 2;
      const head = half * ARROW_HEAD;
      const barb = half * ARROW_BARB;
      const stepY = ih * 0.09;
      const stepX = half * 0.3;
      const shaft = (tail: number, tip: number) =>
        `M ${fmt(tail)} ${fmt(cy)} H ${fmt(cx - stepX)} V ${fmt(cy - stepY)}` +
        ` H ${fmt(cx + stepX)} V ${fmt(cy)} H ${fmt(tip)}`;
      const headPath = (tip: number, towards: number) => {
        const barbX = towards < tip ? tip + head : tip - head;
        return ` M ${fmt(barbX)} ${fmt(cy - barb)} L ${fmt(tip)} ${fmt(cy)} L ${fmt(barbX)} ${fmt(cy + barb)}`;
      };
      let d: string;
      if (prim.dir === "LEFT") {
        d = shaft(cx + half, cx - half) + headPath(cx - half, cx + half);
      } else if (prim.dir === "RIGHT") {
        d = shaft(cx - half, cx + half) + headPath(cx + half, cx - half);
      } else {
        d =
          shaft(cx - half, cx + half) +
          headPath(cx + half, cx - half) +
          headPath(cx - half, cx + half);
      }
      paths.push({ d, dash: prim.dash ? GLYPH_DASH : null, inferred: !!prim.inferred, k: prim.k });
    } else if (prim.k === "varrow") {
      const half = ih * ARROW_LEN;
      const cx = x + w / 2;
      const cy = y + h / 2;
      const head = half * ARROW_HEAD;
      const barb = half * ARROW_BARB;
      let d: string;
      if (prim.vdir === "UP") {
        d =
          `M ${fmt(cx)} ${fmt(cy + half)} V ${fmt(cy - half)}` +
          ` M ${fmt(cx - barb)} ${fmt(cy - half + head)} L ${fmt(cx)} ${fmt(cy - half)} L ${fmt(cx + barb)} ${fmt(cy - half + head)}`;
      } else if (prim.vdir === "DOWN") {
        d =
          `M ${fmt(cx)} ${fmt(cy - half)} V ${fmt(cy + half)}` +
          ` M ${fmt(cx - barb)} ${fmt(cy + half - head)} L ${fmt(cx)} ${fmt(cy + half)} L ${fmt(cx + barb)} ${fmt(cy + half - head)}`;
      } else {
        d =
          `M ${fmt(cx)} ${fmt(cy + half)} V ${fmt(cy - half)}` +
          ` M ${fmt(cx - barb)} ${fmt(cy - half + head)} L ${fmt(cx)} ${fmt(cy - half)} L ${fmt(cx + barb)} ${fmt(cy - half + head)}` +
          ` M ${fmt(cx - barb)} ${fmt(cy + half - head)} L ${fmt(cx)} ${fmt(cy + half)} L ${fmt(cx + barb)} ${fmt(cy + half - head)}`;
      }
      paths.push({ d, dash: prim.dash ? GLYPH_DASH : null, inferred: !!prim.inferred, k: prim.k });
    } else if (prim.k === "axis" && prim.axis_dir) {
      let d: string;
      if (prim.axis_dir === "v") {
        const ax = Math.min(Math.max(x + (prim.at_mm ?? w / 2), x), x + w);
        d = `M ${fmt(ax)} ${fmt(y)} V ${fmt(y + h)}`;
      } else {
        const ay = Math.min(Math.max(y + (prim.at_mm ?? h / 2), y), y + h);
        d = `M ${fmt(x)} ${fmt(ay)} H ${fmt(x + w)}`;
      }
      paths.push({ d, dash: GLYPH_DASH, inferred: false, k: prim.k });
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
