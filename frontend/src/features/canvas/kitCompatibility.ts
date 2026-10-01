/** Studio-side kit compatibility — mirrors the engine axes (opening, size
 * envelope, weight) so the picker shows valid options first and explains
 * the rest. The engine still decides authoritatively at calculate/save;
 * this ranking is presentation over the same declared bounds. */

import type { KitChoice } from "../../api/generated/models";
import type { IntentNode } from "./intentEditing";

export type KitFit = "compatible" | "undecidable" | "incompatible";

export interface KitEvaluation {
  kit: KitChoice;
  fit: KitFit;
  /** Reason codes driving the fit, in the engine's axis order. */
  reasons: ("opening" | "width" | "height" | "weight_unknown" | "overweight")[];
}

/** Mirrors `dekopen_engine.hardware.normalize_opening_type`. */
export function normalizedOpening(opening: string): string {
  if (opening === "TURN_LEFT" || opening === "TURN_RIGHT") return "TURN";
  if (opening === "TILT_TURN_LEFT" || opening === "TILT_TURN_RIGHT") return "TILT_TURN";
  if (opening.startsWith("SLIDING")) return "SLIDING";
  if (opening.startsWith("DOOR")) return "DOOR";
  return opening;
}

const num = (value: string | null | undefined): number | null => {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export function evaluateKitChoice(
  kit: KitChoice,
  ctx: {
    opening: string;
    /** Resolved bay envelope in mm — the leaf's outer bounds proxy. */
    leafWidthMm: number | null;
    leafHeightMm: number | null;
    /** Leaf mass from the engine evaluation; null = unknown (never assumed). */
    leafWeightKg: number | null;
  },
): KitEvaluation {
  const reasons: KitEvaluation["reasons"] = [];
  const kitOpening = normalizedOpening(kit.opening_type);
  if (kitOpening !== normalizedOpening(ctx.opening)) reasons.push("opening");

  const minW = num(kit.min_leaf_width_mm);
  const maxW = num(kit.max_leaf_width_mm);
  if (
    ctx.leafWidthMm !== null &&
    minW !== null &&
    maxW !== null &&
    (ctx.leafWidthMm < minW || ctx.leafWidthMm > maxW)
  ) {
    reasons.push("width");
  }
  const minH = num(kit.min_leaf_height_mm);
  const maxH = num(kit.max_leaf_height_mm);
  if (
    ctx.leafHeightMm !== null &&
    minH !== null &&
    maxH !== null &&
    (ctx.leafHeightMm < minH || ctx.leafHeightMm > maxH)
  ) {
    reasons.push("height");
  }

  const maxWeight = num(kit.max_leaf_weight_kg);
  if (maxWeight !== null && !reasons.includes("opening")) {
    if (ctx.leafWeightKg === null) {
      reasons.push("weight_unknown");
    } else {
      const kitWeight = num(kit.weight_kg ?? null) ?? 0;
      if (ctx.leafWeightKg + kitWeight > maxWeight) reasons.push("overweight");
    }
  }

  const fit: KitFit =
    reasons.length === 0
      ? "compatible"
      : reasons.length === 1 && reasons[0] === "weight_unknown"
        ? "undecidable"
        : "incompatible";
  return { kit, fit, reasons };
}

export function rankKits(
  kits: KitChoice[],
  ctx: Parameters<typeof evaluateKitChoice>[1],
): KitEvaluation[] {
  const order: Record<KitFit, number> = {
    compatible: 0,
    undecidable: 1,
    incompatible: 2,
  };
  return kits
    .map((kit) => evaluateKitChoice(kit, ctx))
    .sort((a, b) => order[a.fit] - order[b.fit] || a.kit.name.localeCompare(b.kit.name));
}

/** Bay envelope in mm: walk the intent tree tracking region extents the way
 * the front layout does — splits divide by declared offset or halve, minus
 * the mullion bar face width. Returns null when dims are not resolvable. */
export function bayEnvelopeMm(
  tree: IntentNode,
  bayId: string,
  moduleWidthMm: number,
  moduleHeightMm: number,
  mullionMm: { vertical: number; horizontal: number },
): { w: number; h: number } | null {
  return walk(tree, bayId, mullionMm, {
    x: 0,
    y: 0,
    w: moduleWidthMm,
    h: moduleHeightMm,
  });
}

function walk(
  node: IntentNode,
  bayId: string,
  mullionMm: { vertical: number; horizontal: number },
  region: { x: number; y: number; w: number; h: number },
): { w: number; h: number } | null {
  // ROOT is transparent; BAY takes the region it's handed.
  if (node.type === "ROOT" && node.children?.length === 1 && node.children[0]) {
    return walk(node.children[0], bayId, mullionMm, region);
  }
  if (node.type === "BAY") return node.id === bayId ? { w: region.w, h: region.h } : null;
  if ((node.type === "SPLIT_V" || node.type === "SPLIT_H") && node.children?.length === 2) {
    // The mullion face width isn't available inside this helper — the caller
    // passes resolved member widths; here we use the proportional extent
    // the same way the layout does (bar consumes part of the region).
    const vertical = node.type === "SPLIT_V";
    const barMm = vertical ? mullionMm.vertical : mullionMm.horizontal;
    const offset = Number(node.split_offset_mm);
    const extent = vertical ? region.w : region.h;
    const axis =
      Number.isFinite(offset) && offset > 0
        ? Math.min(Math.max(offset, barMm / 2), extent - barMm / 2)
        : extent / 2;
    const first = vertical
      ? { ...region, w: Math.max(axis - barMm / 2, 0) }
      : { ...region, h: Math.max(axis - barMm / 2, 0) };
    const second = vertical
      ? { ...region, x: region.x + axis + barMm / 2, w: Math.max(extent - axis - barMm / 2, 0) }
      : { ...region, y: region.y + axis + barMm / 2, h: Math.max(extent - axis - barMm / 2, 0) };
    return (
      walk(node.children[0]!, bayId, mullionMm, first) ??
      walk(node.children[1]!, bayId, mullionMm, second)
    );
  }
  return null;
}
