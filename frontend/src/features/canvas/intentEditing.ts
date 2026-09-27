import { normalizeDimensionCandidate } from "./snapping";

export const OPENINGS = [
  "FIXED",
  "TURN_LEFT",
  "TURN_RIGHT",
  "TILT_TURN_LEFT",
  "TILT_TURN_RIGHT",
  "SLIDING_2L",
  "SLIDING_3L",
  "SLIDING_4L",
  "SLIDING",
  "AWNING",
  "DOOR_ENTRY",
] as const;

/** Ordered sliding topology of a bay (mandate §12): rail count plus one
 * panel per slot, left to right. MOVING panels ride `track` (0-based);
 * FIXED panels carry `track: null`.
 */
export type SlidingPanel = {
  slot: string;
  kind: "MOVING" | "FIXED";
  track: number | null;
};

export type SlidingLayout = {
  tracks: number;
  panels: SlidingPanel[];
};

/** Presets mirrored from the engine (`geometry._SLIDING_PRESETS`) — every
 * arrangement alternates tracks so adjacent leaves never collide. */
export const SLIDING_PRESETS: Record<string, SlidingLayout> = {
  SLIDING_2L: {
    tracks: 2,
    panels: [
      { slot: "S1", kind: "MOVING", track: 0 },
      { slot: "S2", kind: "MOVING", track: 1 },
    ],
  },
  SLIDING_3L: {
    tracks: 2,
    panels: [
      { slot: "S1", kind: "MOVING", track: 0 },
      { slot: "S2", kind: "MOVING", track: 1 },
      { slot: "S3", kind: "MOVING", track: 0 },
    ],
  },
  SLIDING_4L: {
    tracks: 2,
    panels: [
      { slot: "S1", kind: "MOVING", track: 0 },
      { slot: "S2", kind: "MOVING", track: 1 },
      { slot: "S3", kind: "MOVING", track: 0 },
      { slot: "S4", kind: "MOVING", track: 1 },
    ],
  },
};

const SLIDING_OPENINGS = new Set<Opening>(["SLIDING_2L", "SLIDING_3L", "SLIDING_4L", "SLIDING"]);

export function isSlidingOpening(opening: Opening | null | undefined): boolean {
  return opening != null && SLIDING_OPENINGS.has(opening);
}

/** The topology a bay evaluates to: the declared layout wins, otherwise
 * the preset table supplies it (engine `resolved_sliding_layout`). */
export function resolvedSlidingLayout(node: IntentNode): SlidingLayout | null {
  if (node.sliding_layout) return node.sliding_layout;
  if (!node.opening_type) return null;
  return SLIDING_PRESETS[node.opening_type] ?? null;
}

export type Opening = (typeof OPENINGS)[number];
export type SplitType = "SPLIT_V" | "SPLIT_H";

export type IntentNode = {
  id: string;
  type: "ROOT" | SplitType | "BAY";
  width_mm?: string | null;
  height_mm?: string | null;
  split_offset_mm?: string | null;
  mullion_profile_sku?: string | null;
  children?: IntentNode[];
  opening_type?: Opening | null;
  sliding_layout?: SlidingLayout | null;
  glass_thickness_mm?: string | null;
  glass_spec?: string | null;
  glass_article_sku?: string | null;
  panel_article_sku?: string | null;
  hardware_set_sku?: string | null;
  handle_height_mm?: string | null;
  /** Declared hinge side of a DOOR_ENTRY leaf (DIN: LEFT = hinges left).
   * Doors carry no side in their opening_type, so handedness is declared
   * intent — manufacturing refuses an undeclared door rather than assume. */
  door_handedness?: "LEFT" | "RIGHT" | null;
};

export function walkIntent(tree: IntentNode): IntentNode[] {
  const nodes: IntentNode[] = [];
  const ids = new Set<string>();

  function visit(node: IntentNode): void {
    if (!node.id || ids.has(node.id)) throw new Error("invalid_node_identity");
    ids.add(node.id);
    nodes.push(node);
    for (const child of node.children ?? []) visit(child);
  }

  visit(tree);
  return nodes;
}

export function intentBays(tree: IntentNode): IntentNode[] {
  return walkIntent(tree).filter((node) => node.type === "BAY");
}

export function topIntent(tree: IntentNode): IntentNode {
  if (tree.type !== "ROOT") return tree;
  if (tree.children?.length !== 1 || !tree.children[0]) {
    throw new Error("invalid_root");
  }
  return tree.children[0];
}

export function selectedBay(tree: IntentNode, id: string): IntentNode {
  const node = walkIntent(tree).find((candidate) => candidate.id === id);
  if (!node || node.type !== "BAY") throw new Error("bay_unavailable");
  return node;
}

/** Any node by id — mullions and other divisions are objects too, not only
 * leaf bays. Returns null instead of throwing so callers can probe. */
export function findNode(tree: IntentNode, id: string): IntentNode | null {
  return walkIntent(tree).find((candidate) => candidate.id === id) ?? null;
}

/** Formatting only: no rounding, unit conversion, or geometry calculation. */
export function exactMm(value: string): string {
  const normalized = normalizeDimensionCandidate(value.trim().replace(",", "."));
  if (normalized === null) throw new Error("invalid_dimension");
  return normalized;
}

function omitDimensions(node: IntentNode): IntentNode {
  const result = { ...node };
  delete result.width_mm;
  delete result.height_mm;
  return result;
}

/** The API envelope owns nominal dimensions. Derived child dimensions are untouched. */
export function requestTree(tree: IntentNode): IntentNode {
  walkIntent(tree);
  const root = omitDimensions(tree);
  if (root.type !== "ROOT") return root;
  return { ...root, children: [omitDimensions(topIntent(tree))] };
}

function replaceNode(tree: IntentNode, id: string, replacement: IntentNode): IntentNode {
  if (tree.id === id) return replacement;
  if (!tree.children?.length) return tree;
  const children = tree.children.map((child) => replaceNode(child, id, replacement));
  return children.every((child, index) => child === tree.children?.[index])
    ? tree
    : { ...tree, children };
}

export function changeOpening(tree: IntentNode, bayId: string, opening: Opening): IntentNode {
  const bay = selectedBay(tree, bayId);
  if (!OPENINGS.includes(opening)) throw new Error("unsupported_opening");
  if (opening === "DOOR_ENTRY" && topIntent(tree).id !== bayId) {
    throw new Error("door_requires_top_bay");
  }

  // Preserve explicit catalog choices. Engine validates their
  // compatibility. Doors declare handedness; the default mirrors the
  // manufacturing policy's DIN convention (hinges left unless stated).
  const replacement: IntentNode = { ...bay, opening_type: opening };
  if (opening === "DOOR_ENTRY") {
    replacement.door_handedness = bay.door_handedness ?? "LEFT";
  } else {
    delete replacement.door_handedness;
  }
  return requestTree(replaceNode(tree, bayId, replacement));
}

const MIRRORED_OPENING: Partial<Record<Opening, Opening>> = {
  TURN_LEFT: "TURN_RIGHT",
  TURN_RIGHT: "TURN_LEFT",
  TILT_TURN_LEFT: "TILT_TURN_RIGHT",
  TILT_TURN_RIGHT: "TILT_TURN_LEFT",
};

export function splitBay(
  tree: IntentNode,
  bayId: string,
  division: {
    type: SplitType;
    offsetMm: string;
    mullionSku: string;
  },
  ids: { split: string; secondBay: string },
): IntentNode {
  const bay = selectedBay(tree, bayId);
  if (bay.opening_type === "DOOR_ENTRY") {
    throw new Error("door_requires_top_bay");
  }
  if (!["SPLIT_V", "SPLIT_H"].includes(division.type) || !division.mullionSku.trim()) {
    throw new Error("invalid_division");
  }

  const existing = new Set(walkIntent(tree).map((node) => node.id));
  if (
    !ids.split ||
    !ids.secondBay ||
    ids.split === ids.secondBay ||
    existing.has(ids.split) ||
    existing.has(ids.secondBay)
  ) {
    throw new Error("invalid_node_identity");
  }

  const first = omitDimensions(bay);
  // A declared layout is whole-unit topology: splitting derives each half's
  // own unit, so the stale layout drops and a layout-driven bay defaults
  // back to the two-leaf preset on each side.
  if (first.sliding_layout) {
    delete first.sliding_layout;
    if (first.opening_type === "SLIDING") first.opening_type = "SLIDING_2L";
  }
  // A vertical split of a handed leaf yields a mullioned pair: the second
  // leaf mirrors so both handles meet at the poste. Horizontal splits
  // (transoms) keep the same opening type on both bays.
  const second = { ...first, id: ids.secondBay };
  if (division.type === "SPLIT_V" && second.opening_type) {
    second.opening_type = MIRRORED_OPENING[second.opening_type] ?? second.opening_type;
  }
  const replacement: IntentNode = {
    id: ids.split,
    type: division.type,
    split_offset_mm: exactMm(division.offsetMm),
    mullion_profile_sku: division.mullionSku,
    children: [first, second],
  };

  return requestTree(replaceNode(tree, bayId, replacement));
}

/** Explicit user action replaces the layout while retaining the chosen infill. */
export function moveDivision(tree: IntentNode, divisionId: string, offset: string): IntentNode {
  const node = walkIntent(tree).find((item) => item.id === divisionId);
  if (!node || (node.type !== "SPLIT_H" && node.type !== "SPLIT_V"))
    throw new Error("division_unavailable");
  return requestTree(replaceNode(tree, divisionId, { ...node, split_offset_mm: exactMm(offset) }));
}

/** Remove a division: its two leaf bays merge into one. The merged bay keeps
 * `keepChildId`'s identity and spec (first child by default — the dropped
 * bay's spec is discarded, so the op refuses when either child isn't a leaf
 * BAY: nested structure must be collapsed inside-out, never silently lost). */
export function removeDivision(
  tree: IntentNode,
  divisionId: string,
  keepChildId?: string,
): IntentNode {
  const node = findNode(tree, divisionId);
  if (!node || (node.type !== "SPLIT_H" && node.type !== "SPLIT_V"))
    throw new Error("division_unavailable");
  const children = node.children ?? [];
  if (children.length !== 2 || children.some((child) => child.type !== "BAY"))
    throw new Error("division_nested");
  const merged = children.find((child) => child.id === keepChildId) ?? children[0]!;
  return requestTree(replaceNode(tree, divisionId, merged));
}

/** The division node that owns a bay, when removing `bayId` would collapse
 * the split into a single bay — null when the bay has no split parent or a
 * nested sibling that would also be dropped. */
export function parentSplitOf(tree: IntentNode, bayId: string): IntentNode | null {
  const walk = (node: IntentNode): IntentNode | null => {
    const children = node.children ?? [];
    if (children.some((child) => child.id === bayId)) return node;
    for (const child of children) {
      const found = walk(child);
      if (found) return found;
    }
    return null;
  };
  const parent = walk(tree);
  if (!parent || (parent.type !== "SPLIT_H" && parent.type !== "SPLIT_V")) return null;
  return (parent.children ?? []).every((child) => child.type === "BAY") ? parent : null;
}

/** The spec fields a bay can donate — structure never travels with them. */
const BAY_SPEC_KEYS = [
  "opening_type",
  "sliding_layout",
  "glass_thickness_mm",
  "glass_spec",
  "glass_article_sku",
  "panel_article_sku",
  "hardware_set_sku",
  "handle_height_mm",
  "door_handedness",
] as const;

/** The transferable spec of a leaf bay (opening, infill, hardware). Every
 * transferable key is present — fields the source doesn't declare emit
 * `null`, so pasting clears stale recipient fields instead of inheriting
 * whatever the target happened to carry. */
export function baySpec(node: IntentNode): Partial<IntentNode> {
  const spec: Record<string, unknown> = {};
  for (const key of BAY_SPEC_KEYS) {
    spec[key] = node[key] ?? null;
  }
  return spec;
}

/** Copy one leaf bay's spec onto another — ids and structure untouched. */
export function applyBaySpec(
  tree: IntentNode,
  sourceBayId: string,
  targetBayId: string,
): IntentNode {
  const source = selectedBay(tree, sourceBayId);
  const target = selectedBay(tree, targetBayId);
  const spec = baySpec(source);
  if (target.opening_type) {
    // An opening the target already declared is identity, not spec — the
    // paste must not silently flip a mirrored leaf's handedness.
    delete spec.opening_type;
    delete spec.door_handedness;
    delete spec.sliding_layout;
  }
  return requestTree(
    replaceNode(tree, targetBayId, { ...target, ...spec, id: target.id, type: "BAY" }),
  );
}

/** Explicit per-bay edit: patch fields on one leaf without touching the
 * rest of the tree — bay selection writes through the same request-tree
 * normalization every other edit uses. */
export function updateBay(tree: IntentNode, bayId: string, patch: Partial<IntentNode>): IntentNode {
  const bay = selectedBay(tree, bayId);
  return requestTree(replaceNode(tree, bayId, { ...bay, ...patch, id: bay.id, type: bay.type }));
}

/** Explicit user action replaces the layout while retaining the chosen infill. */
export function singleBayTemplate(tree: IntentNode, bayId: string, opening: Opening): IntentNode {
  if (!OPENINGS.includes(opening)) throw new Error("unsupported_opening");
  const bay = omitDimensions(selectedBay(tree, bayId));
  return { ...bay, opening_type: opening };
}
