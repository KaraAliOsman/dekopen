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
  reasons: (
    "opening" | "width" | "height" | "weight_unknown" | "overweight" | "ratio" | "stay_height"
  )[];
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

  // D04 declared restrictions beyond the envelope — slenderness and the
  // stay's minimum leaf height (compás), same axes the engine checks.
  const maxRatio = num(kit.max_aspect_ratio);
  if (
    maxRatio !== null &&
    ctx.leafWidthMm !== null &&
    ctx.leafHeightMm !== null &&
    ctx.leafWidthMm > 0 &&
    ctx.leafHeightMm / ctx.leafWidthMm > maxRatio
  ) {
    reasons.push("ratio");
  }
  const stayMin = num(kit.min_stay_height_mm);
  if (stayMin !== null && ctx.leafHeightMm !== null && ctx.leafHeightMm < stayMin) {
    reasons.push("stay_height");
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

/** Mirrors the engine's class tightness (`_class_tightness`):
 * (max_weight, max_width, max_height) ascending — the most restrictive
 * compatible class wins auto-resolution. */
export function autoPickKit(evaluations: KitEvaluation[]): KitEvaluation | null {
  const compatible = evaluations.filter((item) => item.fit === "compatible");
  if (compatible.length === 0) return null;
  const key = (kit: KitChoice): [number, number, number] => [
    num(kit.max_leaf_weight_kg) ?? Number.POSITIVE_INFINITY,
    num(kit.max_leaf_width_mm) ?? Number.POSITIVE_INFINITY,
    num(kit.max_leaf_height_mm) ?? Number.POSITIVE_INFINITY,
  ];
  return compatible.sort(
    (a, b) =>
      key(a.kit)[0] - key(b.kit)[0] ||
      key(a.kit)[1] - key(b.kit)[1] ||
      key(a.kit)[2] - key(b.kit)[2],
  )[0]!;
}

/** Declared kit cost = sum of component `cost_clp`; null when any
 * component leaves it undeclared (never assumed — §04 honesty). */
export function kitCostClp(kit: KitChoice): number | null {
  let total = 0;
  let declared = false;
  for (const component of kit.contents) {
    const cost = num(component.cost_clp);
    if (cost === null) return null;
    total += cost * (num(component.qty) ?? 1);
    declared = true;
  }
  return declared ? total : null;
}

/** The next compatible class a rejected pick could suggest — mirrors the
 * engine's overweight `suggestion` (same opening family, looser class). */
export function suggestUpgrade(
  evaluations: KitEvaluation[],
  rejected: KitEvaluation,
): { kit: KitChoice; deltaClp: number | null } | null {
  const rejectedCost = kitCostClp(rejected.kit);
  const candidates = evaluations.filter(
    (item) =>
      item.fit === "compatible" &&
      normalizedOpening(item.kit.opening_type) === normalizedOpening(rejected.kit.opening_type) &&
      item.kit.sku !== rejected.kit.sku &&
      (num(item.kit.max_leaf_weight_kg) ?? -1) > (num(rejected.kit.max_leaf_weight_kg) ?? -1),
  );
  if (candidates.length === 0) return null;
  const pick = autoPickKit(candidates);
  if (!pick) return null;
  const pickCost = kitCostClp(pick.kit);
  return {
    kit: pick.kit,
    deltaClp: rejectedCost !== null && pickCost !== null ? pickCost - rejectedCost : null,
  };
}

/** Resolved component line for the inspector's Avanzado view — mirrors
 * `dekopen_engine.hardware.expand_components` on declared data only. */
export interface ResolvedComponent {
  sku: string;
  name: string;
  qty: number | null;
  unit: string;
  category: string;
  /** Cut length when the component declares a cut rule; null otherwise. */
  lengthMm: number | null;
  machiningCount: number;
}

export function resolveComponent(
  component: KitChoice["contents"][number],
  ctx: { leafWidthMm: number | null; leafHeightMm: number | null },
): ResolvedComponent {
  let qty = num(component.qty);
  const rule = component.qty_rule as {
    axis?: string;
    per_mm?: number;
    min_qty?: number;
    max_qty?: number;
  } | null;
  if (rule) {
    const span = rule.axis === "WIDTH" ? ctx.leafWidthMm : ctx.leafHeightMm;
    if (span !== null && rule.per_mm && rule.per_mm > 0) {
      qty = Math.max(
        rule.min_qty ?? 1,
        Math.min(Math.ceil(span / rule.per_mm), rule.max_qty ?? Number.POSITIVE_INFINITY),
      );
    }
  }
  let lengthMm: number | null = null;
  const cut = component.cut_rule as {
    axis?: string;
    minus_mm?: number;
  } | null;
  if (cut) {
    const span = cut.axis === "WIDTH" ? ctx.leafWidthMm : ctx.leafHeightMm;
    if (span !== null && typeof cut.minus_mm === "number") {
      lengthMm = Math.round((span - cut.minus_mm) * 10) / 10;
    }
  }
  return {
    sku: component.sku,
    name: component.name,
    qty,
    unit: component.unit,
    category: component.category,
    lengthMm,
    machiningCount: component.machining?.length ?? 0,
  };
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
