import type { CouplingJson, ProductJson, ProductModuleJson } from "./productEditing";

/** Canonical structural-edit layer for product-v2 assemblies (mandate §3).
 *
 * Every connection is a coupling between two module endpoints expressed in
 * stable ids — `modules[i]`'s `edges[i]` side joins `modules[j]`'s `edges[j]`
 * side, mirroring dekopen_engine CouplingDef. Positional couplings (no
 * `modules` field) resolve through the legacy i→i+1 declaration binding and
 * are upgraded to explicit pairs whenever a mutation touches them. Structural
 * ops NEVER infer graph semantics from array index once the pair resolves —
 * UI, keyboard, command palette and AI all mutate through these functions.
 */

export type GraphEdge = "left" | "right" | "top" | "bottom";
export type CouplingKind = NonNullable<CouplingJson["kind"]>;

export interface ResolvedCoupling {
  coupling: CouplingJson;
  /** Index into product.assembly.couplings. */
  index: number;
  /** [moduleA, moduleB] — explicit pair or the positional binding. */
  pair: readonly [string, string];
  /** edge[i] is the joining side of pair[i]. */
  edges: readonly [GraphEdge, GraphEdge];
  kind: CouplingKind;
}

const POSITIONAL_EDGES: readonly [GraphEdge, GraphEdge] = ["right", "left"];

export function resolveCouplings(product: ProductJson): ResolvedCoupling[] {
  const modules = product.assembly.modules;
  return product.assembly.couplings.flatMap((coupling, index) => {
    const pair =
      coupling.modules ??
      (modules[index] && modules[index + 1]
        ? ([modules[index]!.id, modules[index + 1]!.id] as const)
        : null);
    if (pair === null || pair.length !== 2) return [];
    return [
      {
        coupling,
        index,
        pair,
        edges:
          coupling.edges ??
          (coupling.kind === "INLINE" || coupling.kind === undefined
            ? POSITIONAL_EDGES
            : (["top", "bottom"] as const)),
        kind: coupling.kind ?? "INLINE",
      },
    ];
  });
}

/** Every coupling incident on `moduleId` (any kind, any side). */
export function incidentCouplings(product: ProductJson, moduleId: string): ResolvedCoupling[] {
  return resolveCouplings(product).filter(
    ({ pair }) => pair[0] === moduleId || pair[1] === moduleId,
  );
}

/** The side of `moduleId` the resolved coupling attaches to. */
export function incidentEdge(resolved: ResolvedCoupling, moduleId: string): GraphEdge | null {
  if (resolved.pair[0] === moduleId) return resolved.edges[0];
  if (resolved.pair[1] === moduleId) return resolved.edges[1];
  return null;
}

/** Sides of `moduleId` already claimed by a coupling. */
export function usedEdges(product: ProductJson, moduleId: string): Set<GraphEdge> {
  const used = new Set<GraphEdge>();
  for (const resolved of incidentCouplings(product, moduleId)) {
    const edge = incidentEdge(resolved, moduleId);
    if (edge) used.add(edge);
  }
  return used;
}

/** Connected components of the coupling graph (declaration-ordered ids).
 * Mirrors the engine's `assembly_disconnected` detection: a module with no
 * incident coupling is its own component. */
export function connectedComponents(product: ProductJson): string[][] {
  const modules = product.assembly.modules;
  const parent = new Map<string, string>();
  const find = (id: string): string => {
    let root = parent.get(id) ?? id;
    if (root !== id) {
      root = find(root);
      parent.set(id, root);
    }
    return root;
  };
  for (const { pair } of resolveCouplings(product)) {
    const [a, b] = pair;
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  }
  const byRoot = new Map<string, string[]>();
  for (const module of modules) {
    const root = find(module.id);
    byRoot.set(root, [...(byRoot.get(root) ?? []), module.id]);
  }
  return [...byRoot.values()];
}

/** True when `a` and `b` already belong to the same component — linking them
 * would close a ring, which a single elevation assembly must never form
 * (the engine only degrades gracefully; the editor refuses). */
export function wouldCloseCycle(product: ProductJson, a: string, b: string): boolean {
  return connectedComponents(product).some(
    (component) => component.includes(a) && component.includes(b),
  );
}

/** True when a resolved coupling already joins these two modules (any order). */
export function alreadyJoined(product: ProductJson, a: string, b: string): boolean {
  return resolveCouplings(product).some(
    ({ pair }) => (pair[0] === a && pair[1] === b) || (pair[0] === b && pair[1] === a),
  );
}

/** Edges a coupling kind may legally join — mirrors the engine's validation:
 * INLINE joints are coplanar front seams (left/right); STACKED and TEE are
 * vertical/stacking joints (top/bottom); CORNER is the L-junction family and
 * may turn the front chain (right/left at an angle) or hang a wing off a
 * member's top, so any two free end faces qualify. */
export function kindEdges(kind: CouplingKind): ReadonlySet<GraphEdge> {
  if (kind === "INLINE") return new Set<GraphEdge>(["left", "right"]);
  if (kind === "CORNER") return new Set<GraphEdge>(["left", "right", "top", "bottom"]);
  return new Set<GraphEdge>(["top", "bottom"]);
}

/** True when `moduleId` hangs under a partner — it occupies the `bottom`
 * side of a STACKED coupling. Such members are not front-chain roots:
 * appending beside their column must join the root, not the transom. */
export function isStackedMember(product: ProductJson, moduleId: string): boolean {
  return incidentCouplings(product, moduleId).some(
    (resolved) => resolved.kind === "STACKED" && incidentEdge(resolved, moduleId) === "bottom",
  );
}

/** A module whose `side` edge carries no coupling — a chain end. Candidates
 * are declaration-ordered; the caller picks the end it wants (extreme by
 * default). Stacked members are chain ends in the front chain sense — their
 * top/bottom coupling does not claim a side edge. */
export function chainEndCandidates(product: ProductJson, side: "left" | "right") {
  return product.assembly.modules.filter((module) => !usedEdges(product, module.id).has(side));
}

/** The module at the `side` end of the front chain — the declaration-extreme
 * free-edge module, preferring chain roots over stacked members (a unit
 * appended beside a stacked column joins the column's root, not its top
 * member). */
export function chainEnd(product: ProductJson, side: "left" | "right"): ProductModuleJson | null {
  const candidates = chainEndCandidates(product, side);
  const roots = candidates.filter((module) => !isStackedMember(product, module.id));
  const preferred = roots.length > 0 ? roots : candidates;
  return side === "right" ? (preferred.at(-1) ?? null) : (preferred[0] ?? null);
}

function modulesOrdered(product: ProductJson, a: string, b: string): [string, string] {
  const order = new Map(product.assembly.modules.map((module, index) => [module.id, index]));
  return (order.get(a) ?? -1) <= (order.get(b) ?? -1) ? [a, b] : [b, a];
}

/** Structural invariants for a coupling between existing endpoints —
 * everything the layer refuses before it can produce a dangling or
 * semantically wrong graph edge. Mirrors engine validation so editor state
 * can never encode a joint the engine would reject. */
export function canLink(
  product: ProductJson,
  a: string,
  aEdge: GraphEdge,
  b: string,
  bEdge: GraphEdge,
  kind: CouplingKind,
): boolean {
  if (a === b) return false;
  const byId = new Map(product.assembly.modules.map((module) => [module.id, module]));
  const modA = byId.get(a);
  const modB = byId.get(b);
  if (!modA || !modB) return false;
  if (!kindEdges(kind).has(aEdge) || !kindEdges(kind).has(bEdge)) return false;
  // Shaped outlines and glass panes have no straight seam the coupler could
  // follow — joining them fabricates an edge the geometry does not have.
  if (modA.contour || modB.contour || modA.frameless || modB.frameless) return false;
  if (usedEdges(product, a).has(aEdge) || usedEdges(product, b).has(bEdge)) return false;
  if (alreadyJoined(product, a, b)) return false;
  if (wouldCloseCycle(product, a, b)) return false;
  return true;
}

/** Join two existing endpoints with an explicit coupling — the only way the
 * layer ever creates a relationship between declared modules. Returns the
 * unchanged product when `canLink` refuses. */
export function linkModules(
  product: ProductJson,
  a: string,
  aEdge: GraphEdge,
  b: string,
  bEdge: GraphEdge,
  kind: CouplingKind,
  options: { id?: string; angleDeg?: string; couplerSku?: string | null } = {},
): ProductJson {
  if (!canLink(product, a, aEdge, b, bEdge, kind)) return product;
  const [first, second] = modulesOrdered(product, a, b);
  const used = new Set(product.assembly.couplings.map((coupling) => coupling.id));
  let index = product.assembly.couplings.length + 1;
  while (used.has(`c${index}`)) index += 1;
  const coupling: CouplingJson = {
    id: options.id ?? `c${index}`,
    angle_deg: options.angleDeg ?? "0.0",
    coupler_profile_sku: options.couplerSku ?? null,
    kind,
    modules: [first, second],
    edges: [first === a ? aEdge : bEdge, first === a ? bEdge : aEdge],
  };
  return {
    ...product,
    assembly: {
      ...product.assembly,
      couplings: [...product.assembly.couplings, coupling],
    },
  };
}

/** Reorder declaration position — a presentational op: the resolved graph
 * (every explicit pair) is unchanged, and only legacy positional couplings
 * re-bind since their endpoints ARE the declaration order. */
export function moveModule(product: ProductJson, moduleId: string, toIndex: number): ProductJson {
  const modules = product.assembly.modules;
  const from = modules.findIndex((module) => module.id === moduleId);
  const to = Math.trunc(toIndex);
  if (from === -1 || to === from || to < 0 || to >= modules.length) return product;
  const next = [...modules];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved!);
  return { ...product, assembly: { ...product.assembly, modules: next } };
}

/** Delete a coupling — the only way the layer ever severs a relationship.
 * Members it joined stay modules; if they lose their last connection they
 * become free columns the engine reports via `assembly_disconnected`. */
export function unlinkCoupling(product: ProductJson, couplingId: string): ProductJson {
  const couplings = product.assembly.couplings;
  if (!couplings.some((coupling) => coupling.id === couplingId)) return product;
  return {
    ...product,
    assembly: {
      ...product.assembly,
      couplings: couplings.filter((coupling) => coupling.id !== couplingId),
    },
  };
}
