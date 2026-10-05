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

/** D02 serializable layer stack — the exact dict shape the engine's
 * `composition_to_dict` emits and `composition_from_dict` accepts.
 * Laminae order is exterior → interior; a laminate carries 2+ panes
 * plus its interlayer. */
export type GlassLaminaSpec = {
  type: "lamina";
  panes: string[];
  interlayer?: string | null;
  tint?: string | null;
  treatment?: string | null;
  coating?: string | null;
  coating_face?: number | null;
  supplier_sku?: string | null;
};

export type GlassChamberSpec = {
  type: "chamber";
  width_mm: string;
  gas?: string | null;
  spacer?: string | null;
  sealant?: string | null;
};

export type GlassCompositionSpec = {
  layers: (GlassLaminaSpec | GlassChamberSpec)[];
};

export type GlassSurchargeSelectionSpec = {
  kind: "EDGE_POLISH" | "DRILL" | "PALILLAJE" | string;
  edges?: string[] | null;
  count?: number | null;
  columns?: number | null;
  rows?: number | null;
};

export type GlassOptionsSpec = {
  surcharges?: GlassSurchargeSelectionSpec[];
};

/* ---------- D03 spec-form openings ----------
 * Mirror of the engine's `Opening`/`BayLeaf`/`OpeningSpec` model: a bay may
 * declare its opening as a full spec (`opening` for one leaf, `leaves` for
 * a pair) plus the unit kind it belongs to (`unit_kind` on the unit root —
 * the node directly under ROOT). `opening_type`/`door_handedness` keep
 * working for one version; the engine reconciles both forms.
 */
export type OpeningMovement =
  | "FIXED"
  | "TURN"
  | "TILT"
  | "TILT_TURN"
  | "TOP_HUNG"
  | "BOTTOM_HUNG"
  | "SLIDE"
  | "LIFT_SLIDE"
  | "PARALLEL_SLIDE"
  | "FOLD"
  | "PIVOT_V"
  | "PIVOT_H"
  | "VERTICAL_SLIDE";
export type OpeningHingeSide = "LEFT" | "RIGHT" | "TOP" | "BOTTOM" | "NONE";
export type OpeningDirection = "INWARD" | "OUTWARD";
export type LeafRole = "SINGLE" | "ACTIVE" | "PASSIVE";
export type UnitKind = "WINDOW" | "DOOR";

export type OpeningSpecPayload = {
  movement: OpeningMovement;
  hinge_side?: OpeningHingeSide | null;
  direction?: OpeningDirection | null;
  leaf_role?: LeafRole | null;
  fixed_in_sash?: boolean | null;
};

export type LeafSpecPayload = { slot: string; opening: OpeningSpecPayload };

/** The spec an opening-grid option writes onto the node. */
export interface OptionSpecPatch {
  unit_kind?: UnitKind;
  opening?: OpeningSpecPayload;
  leaves?: LeafSpecPayload[];
}

const TURN_L_IN: OpeningSpecPayload = { movement: "TURN", hinge_side: "LEFT", direction: "INWARD" };
const TURN_R_IN: OpeningSpecPayload = {
  movement: "TURN",
  hinge_side: "RIGHT",
  direction: "INWARD",
};
const TURN_L_OUT: OpeningSpecPayload = {
  movement: "TURN",
  hinge_side: "LEFT",
  direction: "OUTWARD",
};
const TURN_R_OUT: OpeningSpecPayload = {
  movement: "TURN",
  hinge_side: "RIGHT",
  direction: "OUTWARD",
};

/** Options that write a spec instead of a legacy enum value — the ids are
 * editor-side; the API key each maps to lives in OPTION_SPEC_KEY. */
const OPTION_SPECS_TABLE = {
  FIXED_SASH: { opening: { movement: "FIXED", fixed_in_sash: true } },
  TURN_LEFT_OUT: { opening: TURN_L_OUT },
  TURN_RIGHT_OUT: { opening: TURN_R_OUT },
  TILT: { opening: { movement: "TILT", hinge_side: "BOTTOM", direction: "INWARD" } },
  BOTTOM_HUNG: { opening: { movement: "BOTTOM_HUNG", hinge_side: "BOTTOM", direction: "INWARD" } },
  BOTTOM_HUNG_OUT: {
    opening: { movement: "BOTTOM_HUNG", hinge_side: "BOTTOM", direction: "OUTWARD" },
  },
  FRENCH_L: {
    leaves: [
      { slot: "L1", opening: { ...TURN_L_IN, leaf_role: "ACTIVE" } },
      { slot: "L2", opening: { ...TURN_R_IN, leaf_role: "PASSIVE" } },
    ],
  },
  FRENCH_R: {
    leaves: [
      { slot: "L1", opening: { ...TURN_L_IN, leaf_role: "PASSIVE" } },
      { slot: "L2", opening: { ...TURN_R_IN, leaf_role: "ACTIVE" } },
    ],
  },
  FRENCH_OUT_L: {
    leaves: [
      { slot: "L1", opening: { ...TURN_L_OUT, leaf_role: "ACTIVE" } },
      { slot: "L2", opening: { ...TURN_R_OUT, leaf_role: "PASSIVE" } },
    ],
  },
  FRENCH_OUT_R: {
    leaves: [
      { slot: "L1", opening: { ...TURN_L_OUT, leaf_role: "PASSIVE" } },
      { slot: "L2", opening: { ...TURN_R_OUT, leaf_role: "ACTIVE" } },
    ],
  },
  DOOR_LEFT_OUT: { unit_kind: "DOOR", opening: TURN_L_OUT },
  DOOR_RIGHT_OUT: { unit_kind: "DOOR", opening: TURN_R_OUT },
  DOOR_DOUBLE: {
    unit_kind: "DOOR",
    leaves: [
      { slot: "L1", opening: { ...TURN_L_IN, leaf_role: "PASSIVE" } },
      { slot: "L2", opening: { ...TURN_R_IN, leaf_role: "ACTIVE" } },
    ],
  },
  DOOR_DOUBLE_L: {
    unit_kind: "DOOR",
    leaves: [
      { slot: "L1", opening: { ...TURN_L_IN, leaf_role: "ACTIVE" } },
      { slot: "L2", opening: { ...TURN_R_IN, leaf_role: "PASSIVE" } },
    ],
  },
  // Not on the grid — the legacy DOOR_ENTRY option + hinge-side select
  // covers it; it exists so the AI's emitted key resolves to a spec.
  DOOR_RIGHT_IN: { unit_kind: "DOOR", opening: TURN_R_IN },
} as const satisfies Record<string, OptionSpecPatch>;

export type SpecOptionId = keyof typeof OPTION_SPECS_TABLE;
export const OPTION_SPECS: Record<SpecOptionId, OptionSpecPatch> = OPTION_SPECS_TABLE;
export type OpeningChoice = Opening | SpecOptionId;

/** The option key `spec_options_from_capabilities` emits for each grid
 * option — capability filtering compares declared keys, not editor ids.
 * Sliding presets resolve to the bare movement (any SLIDE capability
 * admits them; the layout itself is editor intent). */
export const OPTION_SPEC_KEY: Record<OpeningChoice, string> = {
  FIXED: "PRIMARY:FIXED",
  FIXED_SASH: "PRIMARY:FIXED_SASH",
  TURN_LEFT: "PRIMARY:TURN:LEFT:INWARD",
  TURN_RIGHT: "PRIMARY:TURN:RIGHT:INWARD",
  TURN_LEFT_OUT: "PRIMARY:TURN:LEFT:OUTWARD",
  TURN_RIGHT_OUT: "PRIMARY:TURN:RIGHT:OUTWARD",
  TILT_TURN_LEFT: "PRIMARY:TILT_TURN:LEFT:INWARD",
  TILT_TURN_RIGHT: "PRIMARY:TILT_TURN:RIGHT:INWARD",
  TILT: "PRIMARY:TILT:BOTTOM:INWARD",
  AWNING: "PRIMARY:TOP_HUNG:TOP:OUTWARD",
  BOTTOM_HUNG: "PRIMARY:BOTTOM_HUNG:BOTTOM:INWARD",
  BOTTOM_HUNG_OUT: "PRIMARY:BOTTOM_HUNG:BOTTOM:OUTWARD",
  FRENCH_L: "L1:TURN:LEFT:INWARD:ACTIVE|L2:TURN:RIGHT:INWARD:PASSIVE",
  FRENCH_R: "L1:TURN:LEFT:INWARD:PASSIVE|L2:TURN:RIGHT:INWARD:ACTIVE",
  FRENCH_OUT_L: "L1:TURN:LEFT:OUTWARD:ACTIVE|L2:TURN:RIGHT:OUTWARD:PASSIVE",
  FRENCH_OUT_R: "L1:TURN:LEFT:OUTWARD:PASSIVE|L2:TURN:RIGHT:OUTWARD:ACTIVE",
  SLIDING_2L: "SLIDE",
  SLIDING_3L: "SLIDE",
  SLIDING_4L: "SLIDE",
  SLIDING: "SLIDE",
  DOOR_ENTRY: "DOOR:PRIMARY:TURN:LEFT:INWARD",
  DOOR_LEFT_OUT: "DOOR:PRIMARY:TURN:LEFT:OUTWARD",
  DOOR_RIGHT_OUT: "DOOR:PRIMARY:TURN:RIGHT:OUTWARD",
  DOOR_DOUBLE: "DOOR:L1:TURN:LEFT:INWARD:PASSIVE|L2:TURN:RIGHT:INWARD:ACTIVE",
  DOOR_DOUBLE_L: "DOOR:L1:TURN:LEFT:INWARD:ACTIVE|L2:TURN:RIGHT:INWARD:PASSIVE",
  DOOR_RIGHT_IN: "DOOR:PRIMARY:TURN:RIGHT:INWARD",
};

/** Emitted option key → grid option id — the AI's set_opening echoes back
 * the key the API offered; legacy enum values resolve to themselves. */
export const SPEC_KEY_TO_OPTION: Record<string, OpeningChoice> = (() => {
  const map: Record<string, OpeningChoice> = {};
  for (const [option, key] of Object.entries(OPTION_SPEC_KEY)) {
    if (key !== "SLIDE") map[key] = option as OpeningChoice;
  }
  map["PRIMARY:SLIDE"] = "SLIDING";
  return map;
})();

export type IntentNode = {
  id: string;
  type: "ROOT" | SplitType | "BAY";
  width_mm?: string | null;
  height_mm?: string | null;
  split_offset_mm?: string | null;
  mullion_profile_sku?: string | null;
  children?: IntentNode[];
  opening_type?: Opening | null;
  /** Spec-form opening (D03): single leaf, or the leaf list of a pair. */
  opening?: OpeningSpecPayload | null;
  leaves?: LeafSpecPayload[] | null;
  /** Kind of the unit the node tops — WINDOW unless declared DOOR. */
  unit_kind?: UnitKind | null;
  sliding_layout?: SlidingLayout | null;
  glass_thickness_mm?: string | null;
  glass_spec?: string | null;
  glass_article_sku?: string | null;
  /** D02 structured stack the catalog product carries (or the composer
   * built) — serializes 1:1 to the engine's `composition_to_dict` shape.
   * Null = the bay relies on the legacy text spec. */
  glass_composition?: GlassCompositionSpec | null;
  /** D02 declared extras on the pane (polished edges, drills, georgian
   * bars). Rates live on the catalog product — the node only picks. */
  glass_options?: GlassOptionsSpec | null;
  panel_article_sku?: string | null;
  hardware_set_sku?: string | null;
  /** D04 sellable hardware selections on the leaf: declared skus against the
   * system's handle/option catalogue; the engine validates membership. */
  handle_model_sku?: string | null;
  handle_color_sku?: string | null;
  hardware_option_skus?: string[] | null;
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

/** Emitted key of a spec opening — the engine's `Opening.key()` format
 * (`MOVEMENT[:HINGE[:DIR[:ROLE]]]`; FIXED in sash collapses to FIXED_SASH). */
export function openingKey(opening: OpeningSpecPayload): string {
  if (opening.movement === "FIXED") return opening.fixed_in_sash ? "FIXED_SASH" : "FIXED";
  const parts: string[] = [opening.movement];
  if (opening.hinge_side && opening.hinge_side !== "NONE") parts.push(opening.hinge_side);
  if (opening.direction) parts.push(opening.direction);
  if (opening.leaf_role && opening.leaf_role !== "SINGLE") parts.push(opening.leaf_role);
  return parts.join(":");
}

/** Per-leaf trace of a bay — spec leaves emit their keys, a legacy enum
 * bay emits the enum (the engine resolves it into a spec). */
export function bayLeafTraces(
  node: IntentNode,
): { slot: string; key: string; opening: OpeningSpecPayload | null }[] {
  if (node.leaves?.length) {
    return node.leaves.map((leaf) => ({
      slot: leaf.slot,
      key: openingKey(leaf.opening),
      opening: leaf.opening,
    }));
  }
  if (node.opening) {
    return [{ slot: "PRIMARY", key: openingKey(node.opening), opening: node.opening }];
  }
  return [{ slot: "PRIMARY", key: node.opening_type ?? "FIXED", opening: null }];
}

/** The trace of the leaf that leads the bay — the ACTIVE one in a pair,
 * otherwise the only leaf. */
export function primaryOpeningKey(node: IntentNode): string {
  const traces = bayLeafTraces(node);
  return (traces.find((leaf) => leaf.opening?.leaf_role !== "PASSIVE") ?? traces[0]!).key;
}

/** Whether the bay's opening is a non-fixed, operable leaf. */
export function bayOperable(node: IntentNode): boolean {
  return bayLeafTraces(node).some(
    (leaf) => !(leaf.opening ? leaf.opening.movement === "FIXED" : leaf.key === "FIXED"),
  );
}

/** The unit kind the bay belongs to — declared on the node itself or on
 * the unit root (the node directly under ROOT). */
export function bayUnitKind(tree: IntentNode, bay: IntentNode): UnitKind {
  if (bay.unit_kind) return bay.unit_kind;
  const top = topIntent(tree);
  return top.unit_kind ?? "WINDOW";
}

export function bayIsDoor(tree: IntentNode, bay: IntentNode): boolean {
  return bay.opening_type === "DOOR_ENTRY" || bayUnitKind(tree, bay) === "DOOR";
}

/** Hardware-kit group the bay's leading leaf evaluates against (mirrors
 * the engine's `leaf_hardware_group`). */
export function bayKitGroup(tree: IntentNode, node: IntentNode): string {
  const traces = bayLeafTraces(node);
  const lead = traces.find((leaf) => leaf.opening?.leaf_role !== "PASSIVE") ?? traces[0]!;
  const opening = lead.opening;
  if (!opening) {
    // Legacy enum — same normalization the engine applies.
    if (lead.key === "TURN_LEFT" || lead.key === "TURN_RIGHT") return "TURN";
    if (lead.key === "TILT_TURN_LEFT" || lead.key === "TILT_TURN_RIGHT") return "TILT_TURN";
    if (lead.key.startsWith("SLIDING")) return "SLIDING";
    if (lead.key === "DOOR_ENTRY") return "DOOR";
    return lead.key;
  }
  if (opening.movement === "FIXED") return "FIXED";
  if (opening.leaf_role === "PASSIVE") return "FALLEBA";
  if (bayUnitKind(tree, node) === "DOOR") return "DOOR";
  return (
    (
      {
        TURN: "TURN",
        TILT: "TILT",
        TILT_TURN: "TILT_TURN",
        TOP_HUNG: "AWNING",
        BOTTOM_HUNG: "BOTTOM_HUNG",
        SLIDE: "SLIDING",
      } as Record<string, string>
    )[opening.movement] ?? "TURN"
  );
}

/** Which grid option id a bay currently displays as — spec keys compare
 * against OPTION_SPEC_KEY so a spec bay lights up its own option. */
export function nodeOptionId(node: IntentNode): string {
  const traces = bayLeafTraces(node);
  if (traces[0]?.opening) {
    const emitted = traces.map((leaf) => `${leaf.slot}:${leaf.key}`).join("|");
    return emitted;
  }
  return node.opening_type ?? "FIXED";
}

/** The emitted spec key a bay corresponds to (for capability filtering):
 * legacy enums resolve through OPTION_SPEC_KEY. */
export function nodeSpecKey(tree: IntentNode, node: IntentNode): string {
  const traces = bayLeafTraces(node);
  if (traces[0]?.opening) {
    const unit = bayUnitKind(tree, node);
    const body = traces.map((leaf) => `${leaf.slot}:${leaf.key}`).join("|");
    return unit === "DOOR" ? `DOOR:${body}` : body;
  }
  return OPTION_SPEC_KEY[(node.opening_type ?? "FIXED") as OpeningChoice] ?? node.opening_type!;
}

export function changeOpening(tree: IntentNode, bayId: string, opening: OpeningChoice): IntentNode {
  const bay = selectedBay(tree, bayId);
  const spec = OPTION_SPECS[opening as SpecOptionId] ?? null;
  if (!spec && !OPENINGS.includes(opening as Opening)) throw new Error("unsupported_opening");
  if (opening === "DOOR_ENTRY" && topIntent(tree).id !== bayId) {
    throw new Error("door_requires_top_bay");
  }

  // Preserve explicit catalog choices. Engine validates their
  // compatibility. Doors declare handedness; the default mirrors the
  // manufacturing policy's DIN convention (hinges left unless stated).
  // Hardware selections are family-scoped (D04): an opening change
  // clears them rather than smuggling another family's skus.
  const replacement: IntentNode = {
    ...bay,
    opening: null,
    leaves: null,
    handle_model_sku: null,
    handle_color_sku: null,
    hardware_option_skus: null,
  };
  if (spec) {
    // Spec option: the bay carries the declared opening/leaves; the unit
    // kind lands on the unit root (the node directly under ROOT) so a
    // door leaf inside a split composes door + fixed side naturally.
    delete replacement.opening_type;
    delete replacement.door_handedness;
    delete replacement.sliding_layout;
    if (spec.unit_kind !== "DOOR") delete replacement.panel_article_sku;
    if (spec.opening) replacement.opening = { ...spec.opening };
    if (spec.leaves) {
      replacement.leaves = spec.leaves.map((leaf) => ({
        slot: leaf.slot,
        opening: { ...leaf.opening },
      }));
    }
    let next = replaceNode(tree, bayId, replacement);
    const top = topIntent(next);
    if (spec.unit_kind) {
      next = replaceNode(next, top.id, { ...top, unit_kind: spec.unit_kind });
    } else if (top.unit_kind === "DOOR") {
      // Re-typing a leaf inside a door unit to a window opening drops the
      // unit back to WINDOW — the alternative silently keeps door hardware
      // on a leaf the user re-declared.
      next = replaceNode(next, top.id, { ...top, unit_kind: "WINDOW" });
    }
    return requestTree(next);
  }
  replacement.opening_type = opening as Opening;
  replacement.sliding_layout =
    opening === "SLIDING" ? structuredClone(SLIDING_PRESETS.SLIDING_2L!) : null;
  if (opening === "DOOR_ENTRY") {
    replacement.door_handedness = bay.door_handedness ?? "LEFT";
  } else {
    delete replacement.door_handedness;
    delete replacement.panel_article_sku;
  }
  return requestTree(replaceNode(tree, bayId, replacement));
}

const MIRRORED_OPENING: Partial<Record<Opening, Opening>> = {
  TURN_LEFT: "TURN_RIGHT",
  TURN_RIGHT: "TURN_LEFT",
  TILT_TURN_LEFT: "TILT_TURN_RIGHT",
  TILT_TURN_RIGHT: "TILT_TURN_LEFT",
};

const MIRROR_HINGE: Record<string, OpeningHingeSide> = { LEFT: "RIGHT", RIGHT: "LEFT" };

function mirrorOpeningSpec(opening: OpeningSpecPayload): OpeningSpecPayload {
  return {
    ...opening,
    hinge_side:
      opening.hinge_side && MIRROR_HINGE[opening.hinge_side]
        ? MIRROR_HINGE[opening.hinge_side]
        : opening.hinge_side,
  };
}

/** Mirroring a pair swaps its leaves — L1 lands right, hinges flip. */
function mirrorLeaves(leaves: LeafSpecPayload[]): LeafSpecPayload[] {
  const slotOf = (slot: string): string => (slot === "L1" ? "L2" : slot === "L2" ? "L1" : slot);
  return leaves
    .map((leaf) => ({ slot: slotOf(leaf.slot), opening: mirrorOpeningSpec(leaf.opening) }))
    .sort((a, b) => a.slot.localeCompare(b.slot));
}

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
  // A split bay can no longer be the unit root — a declared unit kind
  // (door unit) moves up onto the division node.
  const unitKind = first.unit_kind;
  delete first.unit_kind;
  // A vertical split of a handed leaf yields a mullioned pair: the second
  // leaf mirrors so both handles meet at the poste. Horizontal splits
  // (transoms) keep the same opening type on both bays.
  const second = { ...first, id: ids.secondBay };
  if (division.type === "SPLIT_V") {
    if (second.opening_type) {
      second.opening_type = MIRRORED_OPENING[second.opening_type] ?? second.opening_type;
    }
    if (second.opening) second.opening = mirrorOpeningSpec(second.opening);
    if (second.leaves) second.leaves = mirrorLeaves(second.leaves);
    if (second.door_handedness) {
      second.door_handedness = second.door_handedness === "LEFT" ? "RIGHT" : "LEFT";
    }
  }
  const replacement: IntentNode = {
    id: ids.split,
    type: division.type,
    split_offset_mm: exactMm(division.offsetMm),
    mullion_profile_sku: division.mullionSku,
    unit_kind: unitKind ?? null,
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
  "opening",
  "leaves",
  "sliding_layout",
  "glass_thickness_mm",
  "glass_spec",
  "glass_article_sku",
  "glass_composition",
  "glass_options",
  "panel_article_sku",
  "hardware_set_sku",
  "handle_model_sku",
  "handle_color_sku",
  "hardware_option_skus",
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
  if (target.opening_type || target.opening || target.leaves) {
    // An opening the target already declared is identity, not spec — the
    // paste must not silently flip a mirrored leaf's handedness.
    delete spec.opening_type;
    delete spec.opening;
    delete spec.leaves;
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
export function singleBayTemplate(
  tree: IntentNode,
  bayId: string,
  opening: OpeningChoice,
): IntentNode {
  const spec = OPTION_SPECS[opening as SpecOptionId] ?? null;
  if (!spec && !OPENINGS.includes(opening as Opening)) throw new Error("unsupported_opening");
  const bay = omitDimensions(selectedBay(tree, bayId));
  if (spec) {
    return {
      ...bay,
      opening_type: null,
      opening: spec.opening ? { ...spec.opening } : null,
      leaves:
        spec.leaves?.map((leaf) => ({ slot: leaf.slot, opening: { ...leaf.opening } })) ?? null,
      unit_kind: spec.unit_kind ?? "WINDOW",
    };
  }
  return { ...bay, opening_type: opening as Opening };
}
