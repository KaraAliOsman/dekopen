import type { IntentNode, Opening, SlidingLayout, SplitType } from "./intentEditing";
import { SLIDING_PRESETS } from "./intentEditing";
import {
  findNode,
  intentBays,
  moveDivision,
  parentSplitOf,
  removeDivision,
  splitBay,
  updateBay,
  walkIntent,
} from "./intentEditing";
import type { MemberGeometry } from "./members";
import type { CouplingKind, GraphEdge } from "./assemblyGraph";
import {
  alreadyJoined,
  chainEnd,
  incidentCouplings,
  linkModules,
  resolveCouplings,
  usedEdges,
} from "./assemblyGraph";

/** Compositional product model (product-v2) — modules joined by couplings.
 *
 * Mirrors dekopen_engine.product: a ProductJson is the JSON form of the
 * engine's ProductModel. Every mutator returns a NEW object so edits can be
 * recorded as undo history entries and validated by the engine afterwards.
 */

export type CouplingJson = {
  id: string;
  angle_deg: string;
  coupler_profile_sku: string | null;
  /** Structural class of the joint — absent means the inline chain default. */
  kind?: "INLINE" | "STACKED" | "TEE" | "CORNER";
  /** Explicit endpoints: modules[i]'s edges[i] side meets modules[j]'s
   * edges[j] side. Absent = legacy positional binding (i right, i+1 left). */
  modules?: [string, string];
  edges?: ["left" | "right" | "top" | "bottom", "left" | "right" | "top" | "bottom"];
};

/** Closed elevation outline of a module — mirrors dekopen_engine.contour.
 * vertices[i] → vertices[i+1] is edge i; bulges[i] is its signed sagitta
 * (positive bulges right of the directed edge = outward on a CCW loop).
 * Module-local mm, y-up, CCW; the canvas flips y when drawing. */
export type ContourJson = {
  vertices: { x_mm: string; y_mm: string }[];
  bulges: (string | null)[];
};

/** Edge of a module's elevation for frameless supports / exposed edges —
 * mirrors dekopen_engine EdgeSide (lowercase). */
export type FramelessEdge = "left" | "right" | "top" | "bottom";

/** One supported edge run of a glass-only pane — mirrors FramelessSupport:
 * CHANNEL runs a continuous seat along the edge, CLAMPS counts point clamps. */
export type FramelessSupportJson = {
  kind: "CHANNEL" | "CLAMPS";
  edge: FramelessEdge;
  article_sku: string;
  qty: number;
};

/** A counted fitting on a glass-only pane — mirrors FramelessFitting. */
export type FramelessFittingJson = {
  kind: "PATCH_FITTING" | "CLAMP" | "HINGE" | "LOCK" | "CONNECTOR" | "SEAL" | "SUPPORT";
  sku: string;
  qty: number;
};

/** Glass-only module spec (mandate §14): the pane IS the module — real
 * support/fitting concepts, never fake FRAME/SASH profiles. Omitted
 * exposed_edges means the whole pane is exposed (all four edges). */
export type FramelessSpecJson = {
  supports: FramelessSupportJson[];
  fittings: FramelessFittingJson[];
  exposed_edges?: FramelessEdge[];
};

export type ProductModuleJson = {
  id: string;
  width_mm: string;
  height_mm: string;
  tree: IntentNode;
  /** Present only on non-rectangular modules; width/height stay the bbox. */
  contour?: ContourJson;
  /** Present only on glass-only modules — no frame members exist. */
  frameless?: FramelessSpecJson;
};

export type ProductJson = {
  version: "product-v2";
  assembly: {
    modules: ProductModuleJson[];
    couplings: CouplingJson[];
  };
};

export function isProductModel(value: unknown): value is ProductJson {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { version?: unknown }).version === "product-v2" &&
    typeof (value as { assembly?: { modules?: unknown } }).assembly === "object" &&
    Array.isArray((value as { assembly: { modules?: unknown } }).assembly.modules)
  );
}

export function makeTrapezoidModule(
  id: string,
  widthMm: string,
  heightMm: string,
  offsetLeftMm: number,
  offsetRightMm: number,
  tree: IntentNode,
): ProductModuleJson {
  const w = Number(widthMm);
  const h = Number(heightMm);
  return {
    id,
    width_mm: widthMm,
    height_mm: heightMm,
    contour: {
      vertices: [
        { x_mm: "0", y_mm: "0" },
        { x_mm: w.toFixed(2), y_mm: "0" },
        { x_mm: (w - offsetRightMm).toFixed(2), y_mm: h.toFixed(2) },
        { x_mm: offsetLeftMm.toFixed(2), y_mm: h.toFixed(2) },
      ],
      bulges: [null, null, null, null],
    },
    tree,
  };
}

export function makeArchModule(
  id: string,
  widthMm: string,
  heightMm: string,
  riseMm: number,
  tree: IntentNode,
): ProductModuleJson {
  const w = Number(widthMm);
  const h = Number(heightMm);
  return {
    id,
    width_mm: widthMm,
    height_mm: heightMm,
    contour: {
      vertices: [
        { x_mm: "0", y_mm: "0" },
        { x_mm: w.toFixed(2), y_mm: "0" },
        { x_mm: w.toFixed(2), y_mm: h.toFixed(2) },
        { x_mm: "0", y_mm: h.toFixed(2) },
      ],
      bulges: [null, null, riseMm.toFixed(2), null],
    },
    tree,
  };
}

/** Glass-only module (mandate §14): the pane IS the product — no frame
 * members exist. The standard fixed-panel seat is a bottom channel run;
 * its article resolves against the catalog's coupler articles, so the
 * declared sku may be blank until the user picks one (the engine warns
 * `frameless_article_unknown` rather than guessing). */
export function makeFramelessModule(
  id: string,
  widthMm: string,
  heightMm: string,
  tree: IntentNode,
): ProductModuleJson {
  return {
    id,
    width_mm: widthMm,
    height_mm: heightMm,
    tree,
    frameless: {
      supports: [{ kind: "CHANNEL", edge: "bottom", article_sku: "", qty: 1 }],
      fittings: [],
    },
  };
}

export function makeBayTree(
  id: string,
  opening: Opening,
  glassThicknessMm: string,
  glassSpec: string,
  glassArticleSku: string | null = null,
): IntentNode {
  return {
    id,
    type: "BAY",
    opening_type: opening,
    glass_thickness_mm: glassThicknessMm,
    glass_spec: glassSpec,
    glass_article_sku: glassArticleSku,
  };
}

export function makeBowProduct(options: {
  moduleCount: number;
  widthMm: number;
  heightMm: number;
  angleDeg: number;
  opening?: Opening;
  glassThicknessMm?: string;
  glassSpec?: string;
  glassArticleSku?: string | null;
}): ProductJson {
  const {
    moduleCount,
    widthMm,
    heightMm,
    angleDeg,
    opening = "FIXED",
    glassThicknessMm = "4.00",
    glassSpec = "4",
    glassArticleSku = null,
  } = options;
  const share = Math.floor((widthMm / moduleCount) * 100) / 100;
  const modules: ProductModuleJson[] = [];
  const couplings: CouplingJson[] = [];
  let remaining = widthMm;
  for (let index = 1; index <= moduleCount; index += 1) {
    const width = index === moduleCount ? remaining : share;
    remaining -= width;
    modules.push({
      id: `m${index}`,
      width_mm: width.toFixed(2),
      height_mm: heightMm.toFixed(2),
      tree: makeBayTree(`m${index}`, opening, glassThicknessMm, glassSpec, glassArticleSku),
    });
    if (index > 1) {
      couplings.push({
        id: `c${index - 1}`,
        angle_deg: angleDeg.toFixed(1),
        coupler_profile_sku: null,
      });
    }
  }
  return { version: "product-v2", assembly: { modules, couplings } };
}

export function totalModuleWidth(product: ProductJson): number {
  return product.assembly.modules.reduce((total, module) => total + Number(module.width_mm), 0);
}

/** The nominal front-elevation envelope — mirrors the engine's
 * `elevation_envelope` exactly: stacked members project into their root
 * column, so width sums across columns only and height is the tallest
 * column's stacked sum. Nominal dims are a contract between this request
 * body and the server's validation — keep the resolution rules identical. */
interface ResolvedPair {
  coupling: ProductJson["assembly"]["couplings"][number];
  pair: readonly [string, string];
}

export interface StackResolution {
  /** Every coupling with its resolved module pair (explicit ids, else the
   * positional index→index+1 binding). */
  pairs: ResolvedPair[];
  /** Stacked member id → the partner it hangs over. */
  stackParent: Map<string, string>;
  /** Stacked member id → its root column id. */
  stackRoot: Map<string, string>;
}

/** Resolved stack graph of an assembly — shared by the envelope, the front
 * layout and any consumer that must agree with the engine's rules. */
export function resolveStacks(product: ProductJson): StackResolution {
  const modules = product.assembly.modules;
  const pairs = product.assembly.couplings.flatMap((coupling, index) => {
    const pair =
      coupling.modules ??
      (index < modules.length - 1 && modules[index] && modules[index + 1]
        ? ([modules[index]!.id, modules[index + 1]!.id] as const)
        : undefined);
    return pair !== undefined && pair.length === 2 ? [{ coupling, pair }] : [];
  });
  const stackParent = new Map<string, string>();
  for (const { coupling, pair } of pairs) {
    if (coupling.kind !== "STACKED") continue;
    const edges = coupling.edges ?? ["top", "bottom"];
    if (edges.length !== 2) continue;
    const topIndex = edges[0] === "top" ? 0 : edges[1] === "top" ? 1 : -1;
    if (topIndex === 0 || topIndex === 1) {
      stackParent.set(pair[(1 - topIndex) as 0 | 1]!, pair[topIndex as 0 | 1]!);
    }
  }
  const moduleIds = new Set(modules.map((module) => module.id));
  const stackRoot = new Map<string, string>();
  for (const member of stackParent.keys()) {
    const seen = new Set<string>();
    let current = member;
    while (stackParent.has(current) && !seen.has(current)) {
      seen.add(current);
      current = stackParent.get(current) as string;
    }
    const anchor = stackParent.has(current) ? undefined : current;
    if (anchor !== undefined && moduleIds.has(anchor)) stackRoot.set(member, anchor);
  }
  return { pairs, stackParent, stackRoot };
}

export interface ElevationMemberMm {
  module: ProductJson["assembly"]["modules"][number];
  x: number;
  w: number;
  sill: number;
  h: number;
}

export interface ElevationColumnMm {
  rootId: string;
  x: number;
  w: number;
  top: number;
}

export interface ElevationLayoutMm {
  members: ElevationMemberMm[];
  columns: ElevationColumnMm[];
}

/** Member placement mirroring the engine's `elevation_layout` exactly:
 * non-stacked roots become front columns in declaration order at their
 * declared widths; a stacked member projects into its root column centred,
 * sill = partner's top edge (cycle-safe, degrades to the baseline). */
export function elevationLayoutMm(product: ProductJson): ElevationLayoutMm {
  const modules = product.assembly.modules;
  const { stackParent, stackRoot } = resolveStacks(product);
  const byId = new Map(modules.map((module) => [module.id, module]));
  const sills = new Map<string, number>();
  const memberSill = (id: string, seen: Set<string>): number => {
    const cached = sills.get(id);
    if (cached !== undefined) return cached;
    const parent = stackParent.get(id);
    let sill = 0;
    if (parent !== undefined && byId.has(parent) && !seen.has(parent)) {
      sill = memberSill(parent, new Set([...seen, id])) + Number(byId.get(parent)!.height_mm);
    }
    sills.set(id, sill);
    return sill;
  };
  const members: ElevationMemberMm[] = [];
  const columns: ElevationColumnMm[] = [];
  let cursor = 0;
  for (const root of modules) {
    if (stackRoot.has(root.id)) continue;
    const columnW = Number(root.width_mm);
    let top = 0;
    for (const member of modules) {
      if (member.id !== root.id && stackRoot.get(member.id) !== root.id) continue;
      const w = Number(member.width_mm);
      const h = Number(member.height_mm);
      const sill = memberSill(member.id, new Set([member.id]));
      top = Math.max(top, sill + h);
      members.push({ module: member, x: cursor + (columnW - w) / 2, w, sill, h });
    }
    columns.push({ rootId: root.id, x: cursor, w: columnW, top });
    cursor += columnW;
  }
  return { members, columns };
}

/** The nominal envelope the API validates — member-extent bounds over the
 * placed layout, so a stacked member wider than its column widens the
 * envelope exactly like the engine's `elevation_envelope`. */
export function elevationEnvelopeMm(product: ProductJson): { width: number; height: number } {
  const { members } = elevationLayoutMm(product);
  if (members.length === 0) return { width: 0, height: 0 };
  const left = Math.min(...members.map((member) => member.x));
  const right = Math.max(...members.map((member) => member.x + member.w));
  const top = Math.max(...members.map((member) => member.sill + member.h));
  const bottom = Math.min(...members.map((member) => member.sill));
  return { width: right - left, height: top - bottom };
}

function replaceModule(
  product: ProductJson,
  moduleId: string,
  module: ProductModuleJson,
): ProductJson {
  return {
    ...product,
    assembly: {
      ...product.assembly,
      modules: product.assembly.modules.map((existing) =>
        existing.id === moduleId ? module : existing,
      ),
    },
  };
}

function replaceCoupling(
  product: ProductJson,
  couplingId: string,
  coupling: CouplingJson,
): ProductJson {
  return {
    ...product,
    assembly: {
      ...product.assembly,
      couplings: product.assembly.couplings.map((existing) =>
        existing.id === couplingId ? coupling : existing,
      ),
    },
  };
}

/** Next free module/coupling id — survives removals without collisions. */
export function nextModuleId(product: ProductJson): string {
  const used = new Set(product.assembly.modules.map((module) => module.id));
  let index = product.assembly.modules.length + 1;
  while (used.has(`m${index}`)) index += 1;
  return `m${index}`;
}

export function nextCouplingId(product: ProductJson): string {
  const used = new Set(product.assembly.couplings.map((coupling) => coupling.id));
  let index = product.assembly.couplings.length + 1;
  while (used.has(`c${index}`)) index += 1;
  return `c${index}`;
}

function cloneTree(node: IntentNode): IntentNode {
  return { ...node, children: node.children?.map(cloneTree) };
}

/** Direct-composition grow: attach a compatible unit on the left/right edge.
 *
 * Inherits the edge module's height and bay structure (same opening, glass,
 * panel), a reasonable default width, and a coupling whose angle/coupler
 * inherit the outermost existing joint — or straight (0°) for the first one.
 */
/** Legacy couplings that omit explicit endpoints resolve positionally —
 * coupling i joins modules i↔i+1 — so any mutation that reorders modules
 * would silently re-aim their joints. Mutators that add, remove or reorder
 * modules first pin every resolvable coupling to the pair it joins in the
 * CURRENT product; couplings already explicit, or so broken no pair
 * resolves, pass through untouched. */
function materializeCouplings(product: ProductJson): CouplingJson[] {
  const resolved = resolveCouplings(product);
  const pairs = new Map(resolved.map((entry) => [entry.index, entry]));
  return product.assembly.couplings.map((coupling, index) => {
    const entry = pairs.get(index);
    if (entry === undefined || (coupling.modules && coupling.edges)) return coupling;
    return {
      ...coupling,
      modules: [entry.pair[0], entry.pair[1]],
      edges: [entry.edges[0], entry.edges[1]],
    };
  });
}

export function addAdjacentUnit(
  product: ProductJson,
  side: "left" | "right",
  defaults: { widthMm?: string } = {},
): ProductJson {
  const { modules } = product.assembly;
  // The chain end is a graph fact — the declaration-extreme module whose
  // side edge carries no coupling — never "the last array element".
  const edge = chainEnd(product, side);
  if (!edge) return product;
  // The outermost joint is the edge module's existing connection — its
  // angle and coupler are what the new unit continues.
  const outerCoupling = incidentCouplings(product, edge.id).at(-1)?.coupling;
  const widthMm = defaults.widthMm ?? edge.width_mm;
  const module: ProductModuleJson = {
    id: nextModuleId(product),
    width_mm: widthMm,
    height_mm: edge.height_mm,
    tree: cloneTree(edge.tree),
    ...(edge.contour ? { contour: scaledContour(edge.contour, widthMm, edge.height_mm) } : {}),
    ...(edge.frameless
      ? {
          frameless: {
            supports: edge.frameless.supports.map((support) => ({ ...support })),
            fittings: edge.frameless.fittings.map((fitting) => ({ ...fitting })),
            ...(edge.frameless.exposed_edges
              ? { exposed_edges: [...edge.frameless.exposed_edges] }
              : {}),
          },
        }
      : {}),
  };
  // An explicit intended relationship: the endpoints are named, not inferred.
  const coupling: CouplingJson = {
    id: nextCouplingId(product),
    angle_deg: outerCoupling?.angle_deg ?? "0.0",
    coupler_profile_sku: outerCoupling?.coupler_profile_sku ?? null,
    kind: "INLINE",
    modules: side === "right" ? [edge.id, module.id] : [module.id, edge.id],
    edges: ["right", "left"],
  };
  const materialized = materializeCouplings(product);
  return {
    ...product,
    assembly:
      side === "right"
        ? { modules: [...modules, module], couplings: [...materialized, coupling] }
        : { modules: [module, ...modules], couplings: [coupling, ...materialized] },
  };
}

/** Remove a module and every incident connection — no coupling may reference
 * a module that no longer exists. Unrelated connections are preserved byte
 * for byte; members the removal disconnects stay modules and surface as
 * `assembly_disconnected` rather than being silently re-attached.
 *
 * One honest repair exists: when the removed module bridged exactly two
 * INLINE joints between two distinct rectangular survivors, they re-join
 * with a merged deflection (c_left + c_right) so downstream modules keep
 * their absolute orientation. Every other topology (stacked roots, TEE
 * nodes, contour/frameless members) only removes — inventing replacement
 * joints would fabricate structure the user never declared. */
export function removeUnit(product: ProductJson, moduleId: string): ProductJson {
  const { modules } = product.assembly;
  if (!modules.some((module) => module.id === moduleId) || modules.length === 1) {
    return product;
  }
  const resolved = resolveCouplings(product);
  const incident = resolved.filter(({ pair }) => pair[0] === moduleId || pair[1] === moduleId);
  const dropped = new Set(incident.map(({ index }) => index));
  const nextModules = modules.filter((module) => module.id !== moduleId);
  const nextCouplings = materializeCouplings(product).filter((_, index) => !dropped.has(index));

  if (incident.length === 2 && incident.every(({ kind }) => kind === "INLINE")) {
    const survivors = incident.map((resolvedCoupling) => {
      const side = resolvedCoupling.pair[0] === moduleId ? 1 : 0;
      return {
        moduleId: resolvedCoupling.pair[side] as string,
        edge: resolvedCoupling.edges[side],
      };
    });
    const first = survivors[0]!;
    const second = survivors[1]!;
    const byId = new Map(nextModules.map((module) => [module.id, module]));
    const remaining = resolved.filter(({ index }) => !dropped.has(index));
    const edgeFree = (moduleId_: string, edge: GraphEdge) =>
      !remaining.some(
        ({ pair, edges }) =>
          (pair[0] === moduleId_ && edges[0] === edge) ||
          (pair[1] === moduleId_ && edges[1] === edge),
      );
    const joinable =
      first.moduleId !== second.moduleId &&
      byId.has(first.moduleId) &&
      byId.has(second.moduleId) &&
      !byId.get(first.moduleId)!.contour &&
      !byId.get(first.moduleId)!.frameless &&
      !byId.get(second.moduleId)!.contour &&
      !byId.get(second.moduleId)!.frameless &&
      edgeFree(first.moduleId, first.edge) &&
      edgeFree(second.moduleId, second.edge) &&
      !alreadyJoined(product, first.moduleId, second.moduleId);
    if (joinable) {
      const order = new Map(nextModules.map((module, index) => [module.id, index]));
      const [left, right] =
        (order.get(first.moduleId) ?? -1) <= (order.get(second.moduleId) ?? -1)
          ? ([first, second] as const)
          : ([second, first] as const);
      const earlier = incident[0]!.index <= incident[1]!.index ? incident[0]! : incident[1]!;
      nextCouplings.splice(earlier.index, 0, {
        id: earlier.coupling.id,
        angle_deg: (
          Number(incident[0]!.coupling.angle_deg) + Number(incident[1]!.coupling.angle_deg)
        ).toFixed(1),
        coupler_profile_sku:
          incident[0]!.coupling.coupler_profile_sku ?? incident[1]!.coupling.coupler_profile_sku,
        kind: "INLINE",
        modules: [left.moduleId, right.moduleId],
        edges: [left.edge, right.edge],
      });
    }
  }
  return {
    ...product,
    assembly: { modules: nextModules, couplings: nextCouplings },
  };
}

/** Insert a module inside an existing INLINE joint: the seam opens, the new
 * member inherits its left neighbor's structure, and the original deflection
 * splits across the two replacement joints so the far side keeps its
 * absolute heading. Only INLINE joints open this way — a stacked or corner
 * junction has no coplanar seam to split. */
export function insertModuleBetween(
  product: ProductJson,
  couplingId: string,
  defaults: { widthMm?: string } = {},
): ProductJson {
  const { modules } = product.assembly;
  const resolved = resolveCouplings(product).find((entry) => entry.coupling.id === couplingId);
  if (!resolved || resolved.kind !== "INLINE") return product;
  const byId = new Map(modules.map((module) => [module.id, module]));
  const left = byId.get(resolved.pair[0] as string);
  const right = byId.get(resolved.pair[1] as string);
  // Shaped or glass-only members have no straight seam to inherit through.
  if (!left || !right || left.contour || right.contour || left.frameless || right.frameless) {
    return product;
  }
  const widthMm = defaults.widthMm ?? left.width_mm;
  const inserted: ProductModuleJson = {
    id: nextModuleId(product),
    width_mm: widthMm,
    height_mm: left.height_mm,
    tree: cloneTree(left.tree),
  };
  const totalAngle = Number(resolved.coupling.angle_deg);
  const halfAngle = totalAngle / 2;
  const OPPOSITE: Record<GraphEdge, GraphEdge> = {
    left: "right",
    right: "left",
    top: "bottom",
    bottom: "top",
  };
  const first: CouplingJson = {
    id: resolved.coupling.id,
    angle_deg: halfAngle.toFixed(1),
    coupler_profile_sku: resolved.coupling.coupler_profile_sku,
    kind: "INLINE",
    modules: [left.id, inserted.id],
    edges: [resolved.edges[0], OPPOSITE[resolved.edges[0]]],
  };
  const second: CouplingJson = {
    id: nextCouplingId(product),
    angle_deg: (totalAngle - halfAngle).toFixed(1),
    coupler_profile_sku: resolved.coupling.coupler_profile_sku,
    kind: "INLINE",
    modules: [inserted.id, right.id],
    edges: [OPPOSITE[resolved.edges[1]], resolved.edges[1]],
  };
  const nextCouplings = materializeCouplings(product);
  nextCouplings.splice(resolved.index, 1, first, second);
  const insertAt = modules.findIndex((module) => module.id === right.id);
  const nextModules = [...modules];
  nextModules.splice(insertAt === -1 ? modules.length : insertAt, 0, inserted);
  return {
    ...product,
    assembly: { modules: nextModules, couplings: nextCouplings },
  };
}

/** Clone a module onto a free side edge — the copy inherits the whole unit
 * (tree, contour scaled identically, frameless spec) and joins its source
 * coplanar (0° INLINE, no coupler). Refuses when both side edges are taken:
 * duplicating into an occupied seam would silently replace the declared
 * joint. */
export function duplicateModule(product: ProductJson, moduleId: string): ProductJson {
  const { modules } = product.assembly;
  const source = modules.find((module) => module.id === moduleId);
  if (!source) return product;
  const used = usedEdges(product, moduleId);
  const side = !used.has("right") ? "right" : !used.has("left") ? "left" : null;
  if (side === null) return product;
  const copy: ProductModuleJson = {
    ...source,
    id: nextModuleId(product),
    tree: cloneTree(source.tree),
    ...(source.contour
      ? { contour: scaledContour(source.contour, source.width_mm, source.height_mm) }
      : {}),
    ...(source.frameless
      ? {
          frameless: {
            supports: source.frameless.supports.map((support) => ({ ...support })),
            fittings: source.frameless.fittings.map((fitting) => ({ ...fitting })),
            ...(source.frameless.exposed_edges
              ? { exposed_edges: [...source.frameless.exposed_edges] }
              : {}),
          },
        }
      : {}),
  };
  const coupling: CouplingJson = {
    id: nextCouplingId(product),
    angle_deg: "0.0",
    coupler_profile_sku: null,
    kind: "INLINE",
    modules: side === "right" ? [source.id, copy.id] : [copy.id, source.id],
    edges: ["right", "left"],
  };
  const at = modules.findIndex((module) => module.id === moduleId);
  const nextModules = [...modules];
  nextModules.splice(side === "right" ? at + 1 : at, 0, copy);
  return {
    ...product,
    assembly: {
      modules: nextModules,
      couplings: [...materializeCouplings(product), coupling],
    },
  };
}

/** Horizontal neighbours of a module through INLINE couplings — left/right
 * follow each member's slot in the declared module order (the same order
 * `elevationLayoutMm` draws), not the coupling declaration order. */
export function moduleNeighbors(
  product: ProductJson,
  moduleId: string,
): { left: string | null; right: string | null } {
  const modules = product.assembly.modules;
  const index = modules.findIndex((module) => module.id === moduleId);
  if (index === -1) return { left: null, right: null };
  const result: { left: string | null; right: string | null } = { left: null, right: null };
  for (const { pair, kind } of resolveCouplings(product)) {
    if (kind !== "INLINE") continue;
    const [a, b] = pair;
    const other = a === moduleId ? b : b === moduleId ? a : null;
    if (other === null) continue;
    const otherIndex = modules.findIndex((module) => module.id === other);
    if (otherIndex === -1) continue;
    if (otherIndex < index) result.left = other;
    else if (otherIndex > index) result.right = other;
  }
  return result;
}

/** Move a module into another member's slot: exchange both ids across every
 * coupling endpoint AND the declared module order — together they are what
 * "reorder" means: joints keep kind/angle/coupler, connectivity and the
 * drawn column order stay consistent. `edges[]` needs no swap — each entry
 * names a spatial side of modules[i], so [A,B]/[right,left] rewritten as
 * [B,A]/[right,left] describes the same physical seam after the move. */
export function swapModules(product: ProductJson, moduleA: string, moduleB: string): ProductJson {
  if (moduleA === moduleB) return product;
  const modules = product.assembly.modules;
  const indexA = modules.findIndex((module) => module.id === moduleA);
  const indexB = modules.findIndex((module) => module.id === moduleB);
  if (indexA === -1 || indexB === -1) return product;
  const nextModules = [...modules];
  nextModules[indexA] = modules[indexB]!;
  nextModules[indexB] = modules[indexA]!;
  const couplings = materializeCouplings(product).map((coupling) => {
    const pair = coupling.modules;
    if (!pair || pair.length !== 2 || (!pair.includes(moduleA) && !pair.includes(moduleB))) {
      return coupling;
    }
    return {
      ...coupling,
      modules: pair.map((id) => (id === moduleA ? moduleB : id === moduleB ? moduleA : id)) as [
        string,
        string,
      ],
    };
  });
  return { ...product, assembly: { modules: nextModules, couplings } };
}

/** Wrap a classic parametric tree as a degenerate one-module product so the
 * compositional editor can edit legacy positions without a mode switch. */
export function wrapTreeAsProduct(
  tree: IntentNode,
  widthMm: string,
  heightMm: string,
): ProductJson {
  return {
    version: "product-v2",
    assembly: {
      modules: [{ id: "m1", width_mm: widthMm, height_mm: heightMm, tree }],
      couplings: [],
    },
  };
}

/** True when the product is a single uncoupled unit — i.e. it can persist in
 * the classic design shape (which keeps the documentary/quotation path).
 * Contoured and frameless modules stay on the product-v2 path: the classic
 * shape has nowhere to carry their outline or glass-only specification. */
export function isSingleUnit(product: ProductJson): boolean {
  const module = product.assembly.modules[0];
  return (
    product.assembly.modules.length === 1 &&
    product.assembly.couplings.length === 0 &&
    !module?.contour &&
    !module?.frameless
  );
}

/** Set the same deflection on every joint — "Distribuir arco" with an exact value. */
export function setAllCouplingAngles(product: ProductJson, angleDeg: string): ProductJson {
  return {
    ...product,
    assembly: {
      ...product.assembly,
      couplings: product.assembly.couplings.map((coupling) => ({
        ...coupling,
        angle_deg: angleDeg,
      })),
    },
  };
}

export function setModuleCount(product: ProductJson, moduleCount: number): ProductJson {
  const { modules } = product.assembly;
  const current = modules.length;
  if (moduleCount < 1 || moduleCount === current) return product;
  let next = product;
  if (moduleCount < current) {
    // Trim the declaration tail through the same graph-correct removal —
    // explicit couplings and stack members heal or detach exactly like a
    // hand-picked delete; a positional slice would orphan pair references.
    while (next.assembly.modules.length > moduleCount) {
      const tail = next.assembly.modules.at(-1)!;
      next = removeUnit(next, tail.id);
    }
    return next;
  }
  // Grow the resolved right end — each append names its endpoints.
  while (next.assembly.modules.length < moduleCount) {
    next = addAdjacentUnit(next, "right");
  }
  return next;
}

/** Rescale a contour to a new bounding box — x and y scale independently.
 * An arc cannot stay circular under unequal scaling, so each edge's sagitta
 * rescales by the perpendicular component of the scale to its chord: the
 * rebuilt arc keeps the intended rise relative to the new outline (an arch
 * keeps its flecha; a bowed side wall keeps its lateral bow). */
export function scaledContour(
  contour: ContourJson,
  widthMm: string,
  heightMm: string,
): ContourJson {
  const xs = contour.vertices.map((v) => Number(v.x_mm));
  const ys = contour.vertices.map((v) => Number(v.y_mm));
  const bw = Math.max(...xs) - Math.min(...xs);
  const bh = Math.max(...ys) - Math.min(...ys);
  const sx = Number(widthMm) / (bw || 1);
  const sy = Number(heightMm) / (bh || 1);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const n = contour.vertices.length;
  return {
    vertices: contour.vertices.map((v) => ({
      x_mm: ((Number(v.x_mm) - minX) * sx).toFixed(2),
      y_mm: ((Number(v.y_mm) - minY) * sy).toFixed(2),
    })),
    bulges: contour.bulges.map((b, i) => {
      if (b === null || b === undefined) return null;
      const a = contour.vertices[i]!;
      const c = contour.vertices[(i + 1) % n]!;
      const dx = Number(c.x_mm) - Number(a.x_mm);
      const dy = Number(c.y_mm) - Number(a.y_mm);
      const len = Math.hypot(dx, dy) || 1;
      // unit normal of the chord, scaled: |(-dy,dx)/len ⊙ (sx,sy)|
      const factor = Math.hypot((-dy / len) * sx, (dx / len) * sy);
      return (Number(b) * factor).toFixed(2);
    }),
  };
}

export function setModuleWidth(
  product: ProductJson,
  moduleId: string,
  widthMm: string,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  return replaceModule(product, moduleId, {
    ...module,
    width_mm: widthMm,
    ...(module.contour
      ? { contour: scaledContour(module.contour, widthMm, module.height_mm) }
      : {}),
  });
}

/** Minimum width a module may be dragged to — below this the geometry is
 * meaningless for any catalog (engine minimums sit higher, ~400mm). */
export const MIN_MODULE_WIDTH_MM = 150;

/** Drag a column seam: the left column's root grows by `deltaMm`, the right
 * column's root shrinks by the same amount, so the overall width is
 * preserved — stacked members keep their own declared widths. Both sides
 * are clamped to MIN_MODULE_WIDTH_MM; returns the unchanged product when the
 * seam doesn't exist or would cross a minimum. */
export function resizeModuleSeam(
  product: ProductJson,
  seamIndex: number,
  deltaMm: number,
): ProductJson {
  const modules = product.assembly.modules;
  const { stackRoot } = resolveStacks(product);
  const columns = modules.filter((module) => !stackRoot.has(module.id));
  const left = columns[seamIndex];
  const right = columns[seamIndex + 1];
  if (!left || !right || !Number.isFinite(deltaMm)) return product;
  const leftMm = Number(left.width_mm) + deltaMm;
  const rightMm = Number(right.width_mm) - deltaMm;
  if (leftMm < MIN_MODULE_WIDTH_MM || rightMm < MIN_MODULE_WIDTH_MM) return product;
  const nextModules = modules.map((module) =>
    module.id === left.id
      ? {
          ...module,
          width_mm: leftMm.toFixed(2),
          ...(module.contour
            ? { contour: scaledContour(module.contour, leftMm.toFixed(2), module.height_mm) }
            : {}),
        }
      : module.id === right.id
        ? {
            ...module,
            width_mm: rightMm.toFixed(2),
            ...(module.contour
              ? { contour: scaledContour(module.contour, rightMm.toFixed(2), module.height_mm) }
              : {}),
          }
        : module,
  );
  return { ...product, assembly: { ...product.assembly, modules: nextModules } };
}

/** Drag an interior divider (mullion/travesaño) to a new offset. */
export function moveModuleDivision(
  product: ProductJson,
  moduleId: string,
  divisionId: string,
  offsetMm: string,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  try {
    const tree = moveDivision(
      module.tree.type === "ROOT" ? (module.tree.children?.[0] ?? module.tree) : module.tree,
      divisionId,
      offsetMm,
    );
    return replaceModule(product, moduleId, {
      ...module,
      tree: module.tree.type === "ROOT" ? { ...module.tree, children: [tree] } : tree,
    });
  } catch {
    return product;
  }
}

/** Indices of the two top corners (y ≈ maxY, ordered left→right) of a
 * contour whose upper bound is a straight or arched chord — trapezoid and
 * arch starters both qualify. Null for degenerate or free-form outlines. */
export function contourTopCorners(
  contour: ContourJson,
): { leftIndex: number; rightIndex: number } | null {
  const ys = contour.vertices.map((v) => Number(v.y_mm));
  const maxY = Math.max(...ys);
  const top = ys.flatMap((y, index) => (Math.abs(y - maxY) < 0.51 ? [index] : []));
  if (top.length !== 2) return null;
  const [first, second] = top as [number, number];
  return Number(contour.vertices[first]!.x_mm) <= Number(contour.vertices[second]!.x_mm)
    ? { leftIndex: first, rightIndex: second }
    : { leftIndex: second, rightIndex: first };
}

export function setContourVertex(
  product: ProductJson,
  moduleId: string,
  vertexIndex: number,
  xMm: string,
  yMm: string,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module?.contour) return product;
  const vertices = module.contour.vertices.map((vertex, index) =>
    index === vertexIndex ? { x_mm: xMm, y_mm: yMm } : vertex,
  );
  return replaceModule(product, moduleId, {
    ...module,
    contour: { ...module.contour, vertices },
  });
}

export function setContourBulge(
  product: ProductJson,
  moduleId: string,
  edgeIndex: number,
  sagittaMm: string | null,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module?.contour) return product;
  const bulges = module.contour.bulges.map((bulge, index) =>
    index === edgeIndex ? sagittaMm : bulge,
  );
  return replaceModule(product, moduleId, {
    ...module,
    contour: { ...module.contour, bulges },
  });
}

export function setAllModuleHeights(product: ProductJson, heightMm: string): ProductJson {
  return {
    ...product,
    assembly: {
      ...product.assembly,
      modules: product.assembly.modules.map((module) => ({
        ...module,
        height_mm: heightMm,
        ...(module.contour
          ? { contour: scaledContour(module.contour, module.width_mm, heightMm) }
          : {}),
      })),
    },
  };
}

export function equalizeModuleWidths(product: ProductJson): ProductJson {
  const modules = product.assembly.modules;
  const total = totalModuleWidth(product);
  const share = Math.round((total / modules.length) * 100) / 100;
  const nextModules = modules.map((module, index) => {
    const widthMm =
      index === modules.length - 1
        ? (total - share * (modules.length - 1)).toFixed(2)
        : share.toFixed(2);
    return {
      ...module,
      width_mm: widthMm,
      ...(module.contour
        ? { contour: scaledContour(module.contour, widthMm, module.height_mm) }
        : {}),
    };
  });
  return { ...product, assembly: { ...product.assembly, modules: nextModules } };
}

export function scaleModuleWidths(product: ProductJson, totalMm: string): ProductJson {
  const modules = product.assembly.modules;
  const totalCents = Math.round(Number(totalMm) * 100);
  // The control edits the elevation envelope, so the factor must come from
  // `elevationLayoutMm` member extents — a stacked member shares its root's
  // column and must not count twice against the requested total.
  const layout = elevationLayoutMm(product);
  if (layout.members.length === 0) return product;
  const envelopeCents = (candidate: ElevationLayoutMm) =>
    Math.round(
      (Math.max(...candidate.members.map((member) => member.x + member.w)) -
        Math.min(...candidate.members.map((member) => member.x))) *
        100,
    );
  const currentCents = envelopeCents(layout);
  if (!Number.isFinite(totalCents) || totalCents < modules.length || currentCents <= 0)
    return product;
  // Uniform factor scaling: every member width follows the same factor, so
  // columns, centred stacks and protrusions all track the envelope exactly.
  const factor = totalCents / currentCents;
  const widths = new Map(
    modules.map((module) => [
      module.id,
      Math.max(1, Math.round(Number(module.width_mm) * 100 * factor)),
    ]),
  );
  const build = (map: Map<string, number>): ProductJson => ({
    ...product,
    assembly: {
      ...product.assembly,
      modules: modules.map((module) => {
        const widthMm = ((map.get(module.id) ?? 1) / 100).toFixed(2);
        return {
          ...module,
          width_mm: widthMm,
          ...(module.contour
            ? { contour: scaledContour(module.contour, widthMm, module.height_mm) }
            : {}),
        };
      }),
    },
  });
  // Per-member cent rounding drifts the envelope by a few cents — hand the
  // residual to the module owning the right edge (a centred stack moves
  // that edge only half a cent per cent, so double the delta there) until
  // the elevation lands on the requested width.
  let next = build(widths);
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const diff = totalCents - envelopeCents(elevationLayoutMm(next));
    if (diff === 0) return next;
    const right = Math.max(...elevationLayoutMm(next).members.map((member) => member.x + member.w));
    const edgeOwner = elevationLayoutMm(next).members.find(
      (member) => member.x + member.w === right,
    );
    if (edgeOwner === undefined) break;
    const id = edgeOwner.module.id;
    const centred = !elevationLayoutMm(next).columns.some((column) => column.rootId === id);
    const delta = centred ? diff * 2 : diff;
    const adjusted = (widths.get(id) ?? 1) + delta;
    if (adjusted < 1) break;
    widths.set(id, adjusted);
    next = build(widths);
  }
  return next;
}

export function setCouplingAngle(
  product: ProductJson,
  couplingId: string,
  angleDeg: string,
): ProductJson {
  const coupling = product.assembly.couplings.find((item) => item.id === couplingId);
  if (!coupling) return product;
  return replaceCoupling(product, couplingId, {
    ...coupling,
    angle_deg: angleDeg,
  });
}

export function equalizeCouplingAngles(product: ProductJson): ProductJson {
  const couplings = product.assembly.couplings;
  const angle = couplings.at(0)?.angle_deg;
  if (angle === undefined) return product;
  return {
    ...product,
    assembly: {
      ...product.assembly,
      couplings: couplings.map((coupling) => ({
        ...coupling,
        angle_deg: angle,
      })),
    },
  };
}

export function setCouplerSku(
  product: ProductJson,
  couplingId: string,
  sku: string | null,
): ProductJson {
  const coupling = product.assembly.couplings.find((item) => item.id === couplingId);
  if (!coupling) return product;
  return replaceCoupling(product, couplingId, {
    ...coupling,
    coupler_profile_sku: sku,
  });
}

export function setCouplerSkuAll(product: ProductJson, sku: string | null): ProductJson {
  return {
    ...product,
    assembly: {
      ...product.assembly,
      couplings: product.assembly.couplings.map((coupling) => ({
        ...coupling,
        coupler_profile_sku: sku,
      })),
    },
  };
}

/** Kinds a coupling may take given the module edges it actually joins —
 * INLINE is coplanar (left/right), every stacking kind is top/bottom. */
export function allowedCouplingKinds(product: ProductJson, couplingId: string): CouplingKind[] {
  const resolved = resolveCouplings(product).find((item) => item.coupling.id === couplingId);
  if (!resolved) return [];
  const horizontal = resolved.edges.every((edge) => edge === "left" || edge === "right");
  return horizontal ? ["INLINE"] : ["STACKED", "TEE", "CORNER"];
}

/** Change a coupling's kind, only across compatible edges — the joint's
 * geometry never moves, so an INLINE seam can never become a stack. */
export function setCouplingKind(
  product: ProductJson,
  couplingId: string,
  kind: CouplingKind,
): ProductJson {
  const coupling = product.assembly.couplings.find((item) => item.id === couplingId);
  if (!coupling || !allowedCouplingKinds(product, couplingId).includes(kind)) return product;
  return replaceCoupling(product, couplingId, { ...coupling, kind });
}

/** Replace one module's parametric tree — bay-level edits land through
 * updateBay upstream, this only swaps the validated result. */
export function setModuleTree(
  product: ProductJson,
  moduleId: string,
  tree: IntentNode,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  return replaceModule(product, moduleId, { ...module, tree });
}

export function setModuleOpening(
  product: ProductJson,
  moduleId: string,
  opening: Opening,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  function withOpening(node: IntentNode): IntentNode {
    if (node.type === "BAY") {
      // Panels are only an engine input for DOOR_ENTRY; a stale panel sku on a
      // non-door bay would linger invisibly after switching back. Doors carry
      // declared handedness (DIN: hinges LEFT unless stated) — a stale value
      // on a non-door bay is likewise cleared.
      const cleared =
        opening === "DOOR_ENTRY"
          ? { ...node, opening_type: opening, door_handedness: node.door_handedness ?? "LEFT" }
          : { ...node, opening_type: opening, panel_article_sku: null, door_handedness: null };
      // The opening picker selects presets — a stale declared layout would
      // keep winning over the new preset. "SLIDING" alone needs a layout to
      // evaluate, so it seeds the 2-leaf topology the user then edits.
      return {
        ...cleared,
        sliding_layout: opening === "SLIDING" ? structuredClone(SLIDING_PRESETS.SLIDING_2L!) : null,
      };
    }
    return { ...node, children: node.children?.map(withOpening) };
  }
  const singleChild = module.tree.children?.at(0);
  const tree =
    module.tree.type === "ROOT" && singleChild && module.tree.children?.length === 1
      ? { ...module.tree, children: [withOpening(singleChild)] }
      : withOpening(module.tree);
  return replaceModule(product, moduleId, { ...module, tree });
}

/** Author one bay's sliding topology (mandate §12). Only the addressed bay
 * changes — a manual layout edit makes that bay layout-driven
 * (`opening_type: "SLIDING"` — presets resolve without a declared layout),
 * and sibling bays keep their own opening and BOM. */
export function setModuleSlidingLayout(
  product: ProductJson,
  moduleId: string,
  layout: SlidingLayout,
  bayId: string,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  function withLayout(node: IntentNode): IntentNode {
    if (node.type === "BAY") {
      return node.id === bayId
        ? { ...node, opening_type: "SLIDING", sliding_layout: layout }
        : node;
    }
    return { ...node, children: node.children?.map(withLayout) };
  }
  const singleChild = module.tree.children?.at(0);
  const tree =
    module.tree.type === "ROOT" && singleChild && module.tree.children?.length === 1
      ? { ...module.tree, children: [withLayout(singleChild)] }
      : withLayout(module.tree);
  return replaceModule(product, moduleId, { ...module, tree });
}

/** First bay of a module tree — anchor for material edits. */
export function modulePrimaryBay(module: ProductModuleJson): IntentNode | null {
  const child = module.tree.children?.at(0);
  const bays = intentBays(module.tree.type === "ROOT" && child ? child : module.tree);
  return bays[0] ?? null;
}

export function moduleOpening(module: ProductModuleJson): Opening {
  const bay = modulePrimaryBay(module);
  return bay?.opening_type ?? "FIXED";
}

/** Commercial glass SKU on every bay of a module — pricing authority. */
export function setModuleGlass(
  product: ProductJson,
  moduleId: string,
  glassArticleSku: string | null,
  glassSpec?: string | null,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  function withGlass(node: IntentNode): IntentNode {
    if (node.type === "BAY") {
      return {
        ...node,
        glass_article_sku: glassArticleSku,
        // The article is the composition authority: pick one and its spec is
        // sealed (null spec stays null — honest MISSING, never a thickness).
        glass_spec: glassArticleSku == null ? node.glass_spec : (glassSpec ?? null),
      };
    }
    return { ...node, children: node.children?.map(withGlass) };
  }
  return replaceModule(product, moduleId, { ...module, tree: withGlass(module.tree) });
}

export function moduleGlassSku(module: ProductModuleJson): string | null {
  return modulePrimaryBay(module)?.glass_article_sku ?? null;
}

/** Glazing thickness on every bay of a module (the physical bead slot).
 * The composition spec is a separate authority — setModuleGlass writes it. */
export function setModuleGlassThickness(
  product: ProductJson,
  moduleId: string,
  glassThicknessMm: string | null,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  function withThickness(node: IntentNode): IntentNode {
    if (node.type === "BAY") {
      return {
        ...node,
        glass_thickness_mm: glassThicknessMm,
        glass_spec: node.glass_spec ?? glassThicknessMm,
      };
    }
    return { ...node, children: node.children?.map(withThickness) };
  }
  return replaceModule(product, moduleId, { ...module, tree: withThickness(module.tree) });
}

export function moduleGlassThicknessMm(module: ProductModuleJson): string | null {
  return modulePrimaryBay(module)?.glass_thickness_mm ?? null;
}

/** Catalog panel article for door modules (DOOR_ENTRY infill authority). */
export function setModulePanel(
  product: ProductJson,
  moduleId: string,
  panelArticleSku: string | null,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  function withPanel(node: IntentNode): IntentNode {
    if (node.type === "BAY") return { ...node, panel_article_sku: panelArticleSku };
    return { ...node, children: node.children?.map(withPanel) };
  }
  return replaceModule(product, moduleId, { ...module, tree: withPanel(module.tree) });
}

export function modulePanelSku(module: ProductModuleJson): string | null {
  return modulePrimaryBay(module)?.panel_article_sku ?? null;
}

/** Set or clear a module's glass-only spec. `null` returns the module to
 * the framed path; a spec replaces it wholesale (the inspector edits rows
 * by rebuilding the arrays). */
export function setModuleFrameless(
  product: ProductJson,
  moduleId: string,
  spec: FramelessSpecJson | null,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  const { frameless: _omitted, ...rest } = module;
  return replaceModule(product, moduleId, spec === null ? rest : { ...rest, frameless: spec });
}

/** A bay's region extent along an axis — the span its local split_offset_mm
 * must stay inside, derived exactly like the engine walks the tree: the top
 * node fills the frame-clear rectangle (module span minus both frame faces)
 * and every same-axis ancestor consumes half its mullion face on each side
 * of the split centerline. The top node's own split_offset_mm is measured
 * from the module edge (local origin 0); deeper nodes measure from their
 * own region origin, so only the root step folds in raw module mm.
 * `isTopBay` tells callers the bay IS the tree top — a new split there
 * becomes the root and needs a module-relative offset. */
function baySpanOnAxis(
  root: IntentNode,
  bayId: string,
  vertical: boolean,
  moduleSpanMm: number,
  members: MemberGeometry,
): { spanMm: number; isTopBay: boolean } | null {
  const pathTo = (node: IntentNode): { node: IntentNode; index: number }[] | null => {
    if (node.id === bayId) return [];
    for (const [index, child] of (node.children ?? []).entries()) {
      const rest = pathTo(child);
      if (rest !== null) return [{ node, index }, ...rest];
    }
    return null;
  };
  const path = pathTo(root);
  if (!path) return null;
  const frameFace = members.frame.faceWidthMm;
  // A same-axis ancestor split can only bound the bay when the mullion's
  // face width is declared — a guessed width would persist a fallback
  // number as if it were authority.
  const axisMullion = vertical ? members.mullionV : members.mullionH;
  const mullionHalf = axisMullion === null ? null : axisMullion.faceWidthMm / 2;
  let lo = frameFace;
  let hi = Math.max(moduleSpanMm - frameFace, frameFace);
  for (const { node, index } of path) {
    if (node.type !== "SPLIT_V" && node.type !== "SPLIT_H") continue;
    if ((node.type === "SPLIT_V") !== vertical) continue;
    const offset = Number(node.split_offset_mm);
    if (!Number.isFinite(offset) || offset <= 0) continue;
    if (mullionHalf === null) return null;
    const centerline = node === root ? offset : lo + offset;
    if (index === 0) hi = Math.min(hi, centerline - mullionHalf);
    else lo = Math.max(lo, centerline + mullionHalf);
  }
  return { spanMm: Math.max(hi - lo, 0), isTopBay: path.length === 0 };
}

/** "Dividir" — split a module's bay region with a catalog mullion.
 *
 * The default split centers inside the TARGET bay's own span (bay-local
 * offsets measure from the bay's region origin, not the module edge), so a
 * click anywhere — front view, object tree, plan — produces a valid nested
 * split. Returns the unchanged product when the module or split is invalid
 * (door bays can't split).
 */
export function splitModuleBay(
  product: ProductJson,
  moduleId: string,
  division: { type: SplitType; mullionSku: string; offsetMm?: string; bayId?: string },
  members: MemberGeometry,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module || !division.mullionSku.trim()) return product;
  const root =
    module.tree.type === "ROOT" ? (module.tree.children?.[0] ?? module.tree) : module.tree;
  const bay = division.bayId
    ? (intentBays(root).find((item) => item.id === division.bayId) ?? null)
    : modulePrimaryBay(module);
  if (!bay || moduleOpening(module) === "DOOR_ENTRY") return product;
  const size = division.type === "SPLIT_V" ? Number(module.width_mm) : Number(module.height_mm);
  if (!Number.isFinite(size) || size <= 0) return product;
  const region = baySpanOnAxis(root, bay.id, division.type === "SPLIT_V", size, members);
  if (region === null || region.spanMm <= 0) return product;
  // The top bay's split becomes the new root — its default centers the
  // module span, a pure product coordinate with no member geometry in it.
  // Deeper bays store bay-local offsets, so centering halves the bay's own
  // span — which only real (declared) member geometry may bound.
  const offset = division.offsetMm ?? (region.isTopBay ? size / 2 : region.spanMm / 2).toFixed(2);
  const used = new Set(walkIntent(module.tree).map((node) => node.id));
  const freeId = (base: string): string => {
    let index = 1;
    while (used.has(`${base}${index}`)) index += 1;
    return `${base}${index}`;
  };
  try {
    const tree = splitBay(
      module.tree.type === "ROOT" ? (module.tree.children?.[0] ?? module.tree) : module.tree,
      bay.id,
      { type: division.type, offsetMm: offset, mullionSku: division.mullionSku },
      {
        split: freeId(`${module.id}-s${division.type === "SPLIT_V" ? "v" : "h"}`),
        secondBay: freeId(`${bay.id}-b`),
      },
    );
    return replaceModule(product, moduleId, { ...module, tree });
  } catch {
    return product;
  }
}

/** Remove a mullion/transom division: its two leaf bays merge into the first
 * child's spec. Refuses (returns product unchanged) on nested structure —
 * inside splits must be collapsed first so nothing is silently dropped. */
export function removeModuleDivision(
  product: ProductJson,
  moduleId: string,
  divisionId: string,
  keepChildId?: string,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  try {
    const tree = removeDivision(module.tree, divisionId, keepChildId);
    return replaceModule(product, moduleId, { ...module, tree });
  } catch {
    return product;
  }
}

/** Remove a leaf bay by collapsing its parent split into the sibling — the
 * tree-level form of "remove bay" (no-op when the bay's parent is nested or
 * the tree is a single bay: a module always has at least one opening). */
export function removeModuleBay(
  product: ProductJson,
  moduleId: string,
  bayId: string,
): ProductJson {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return product;
  const parent = parentSplitOf(module.tree, bayId);
  if (!parent) return product;
  const sibling = (parent.children ?? []).find((child) => child.id !== bayId)?.id;
  return removeModuleDivision(product, moduleId, parent.id, sibling);
}

/** Whether a division can merge — same predicate removeDivision enforces,
 * so the command layer can hide the action instead of failing silently. */
export function canRemoveModuleDivision(
  product: ProductJson,
  moduleId: string,
  divisionId: string,
): boolean {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  const node = module ? findNode(module.tree, divisionId) : null;
  return (
    !!node &&
    (node.type === "SPLIT_V" || node.type === "SPLIT_H") &&
    (node.children ?? []).length === 2 &&
    (node.children ?? []).every((child) => child.type === "BAY")
  );
}

/** Copy one leaf bay's spec onto another — the target may live in a
 * different module (clipboard carry is spec-level, not tree-level). */
export function copyBaySpec(
  product: ProductJson,
  targetModuleId: string,
  targetBayId: string,
  spec: Partial<IntentNode>,
): ProductJson {
  const target = product.assembly.modules.find((item) => item.id === targetModuleId);
  if (!target) return product;
  const targetNode = findNode(target.tree, targetBayId);
  // Opening identity (which way the leaf opens, hinge side, sliding layout)
  // never travels with a spec paste once the target declares one — copying
  // Osc-izq onto an Osc-der leaf would silently break the mirrored pair.
  // A bay with no declared opening adopts the source's.
  const payload = { ...spec };
  if (targetNode?.opening_type) {
    delete payload.opening_type;
    delete payload.door_handedness;
    delete payload.sliding_layout;
  }
  try {
    const tree = updateBay(target.tree, targetBayId, payload);
    return replaceModule(product, targetModuleId, { ...target, tree });
  } catch {
    return product;
  }
}

/** Stack a new unit on top of an existing module — the transom-over-door /
 * fanlight move. The member clones the base's spec and spans its width;
 * `heightMm` is a display default the user then edits (never engine data).
 * Refuses when the base's top edge is claimed or the base is shaped/bare. */
export function addStackedUnit(
  product: ProductJson,
  baseId: string,
  defaults: { heightMm?: string } = {},
): ProductJson {
  const base = product.assembly.modules.find((module) => module.id === baseId);
  if (!base || base.contour || base.frameless) return product;
  if (usedEdges(product, baseId).has("top")) return product;
  const member: ProductModuleJson = {
    id: nextModuleId(product),
    width_mm: base.width_mm,
    height_mm: defaults.heightMm ?? "600.00",
    tree: cloneTree(base.tree),
  };
  const withMember: ProductJson = {
    ...product,
    assembly: {
      ...product.assembly,
      modules: [...product.assembly.modules, member],
    },
  };
  return linkModules(withMember, baseId, "top", member.id, "bottom", "STACKED");
}
