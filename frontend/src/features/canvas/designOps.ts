import { applyDesignOpOn } from "../commands/registry";
import type { CommandSpec, DesignOp, DesignOpState } from "../commands/types";
import { ASSEMBLY_COMMANDS } from "./assemblyCommands";
import type { ProductJson } from "./productEditing";

export type { DesignOp };

/** Content fingerprint (FNV-1a over the normalized wire payload) the backend
 * persists on each turn — a restored ops step refuses to apply when the live
 * product no longer matches the product its ops were validated against. */
export function productFingerprint(product: unknown): string {
  const text = JSON.stringify(product) ?? "";
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

/** The product wire shape the design-ops contract validates against — stable
 * domain ids (modules/couplings refs), not the full ProductJson. AssistantPanel
 * and the agent share this projection so both apply against the same graph. */
export function designAssistProduct(product: ProductJson): {
  modules: {
    id: string;
    width_mm: string;
    height_mm: string;
    contour?: unknown;
    frameless?: unknown;
  }[];
  couplings: {
    id: string;
    angle_deg: string;
    kind?: "INLINE" | "STACKED" | "TEE" | "CORNER";
    modules?: [string, string];
    edges?: ["left" | "right" | "top" | "bottom", "left" | "right" | "top" | "bottom"];
  }[];
} {
  return {
    modules: product.assembly.modules.map((module) => ({
      id: module.id,
      width_mm: module.width_mm,
      height_mm: module.height_mm,
      ...(module.contour ? { contour: module.contour } : {}),
      ...(module.frameless ? { frameless: module.frameless } : {}),
    })),
    couplings: product.assembly.couplings.map((coupling) => ({
      id: coupling.id,
      angle_deg: coupling.angle_deg,
      ...(coupling.kind ? { kind: coupling.kind } : {}),
      ...(coupling.modules ? { modules: coupling.modules } : {}),
      ...(coupling.edges ? { edges: coupling.edges } : {}),
    })),
  };
}

/** Wire op → product: dispatched through the shared command registry — the
 * same `apply` a palette row or context-menu action commits. The backend has
 * already bounds-checked the op; unknown or undecodable ops are refused. */
export function applyDesignOp(
  product: ProductJson,
  op: DesignOp,
  specs: CommandSpec[] = ASSEMBLY_COMMANDS,
  state?: DesignOpState,
): ProductJson {
  return applyDesignOpOn(specs, product, op, state);
}

/** Ids minted by one apply — the modules/couplings in `next` absent from
 * `before` — join the sequence's synthetic-ref state in creation order. */
function harvestAdded(state: DesignOpState, before: ProductJson, next: ProductJson): void {
  const moduleIds = new Set(before.assembly.modules.map((module) => module.id));
  const couplingIds = new Set(before.assembly.couplings.map((coupling) => coupling.id));
  state.addedModules.push(
    ...next.assembly.modules
      .filter((module) => !moduleIds.has(module.id))
      .map((module) => module.id),
  );
  state.addedCouplings.push(
    ...next.assembly.couplings
      .filter((coupling) => !couplingIds.has(coupling.id))
      .map((coupling) => coupling.id),
  );
}

export function applyDesignOps(
  product: ProductJson,
  ops: DesignOp[],
  specs: CommandSpec[] = ASSEMBLY_COMMANDS,
): ProductJson {
  // Synthetic refs resolve in apply order: after each structural op, the ids
  // it minted join the state so `added_m1`/`added_c2` in a later op points at
  // the real entity the sequence produced, never a guess.
  const state: DesignOpState = { addedModules: [], addedCouplings: [], origin: product };
  return ops.reduce((current, op) => {
    const next = applyDesignOp(current, op, specs, state);
    harvestAdded(state, current, next);
    return next;
  }, product);
}

/** Human one-line description of a wire op — the registry spec's `describe`
 * fed with the decoded args (so `módulo 2`, not a raw id). `priorOps` replays
 * the sequence's earlier ops so refs minted mid-sequence ('módulo nueva 1')
 * resolve to the entity they'd produce. */
export function describeDesignOp(
  op: DesignOp,
  product: ProductJson,
  priorOps: DesignOp[] = [],
  specs: CommandSpec[] = ASSEMBLY_COMMANDS,
): string {
  const state: DesignOpState = { addedModules: [], addedCouplings: [], origin: product };
  const evolved = priorOps.reduce((current, prior) => {
    const next = applyDesignOp(current, prior, specs, state);
    harvestAdded(state, current, next);
    return next;
  }, product);
  for (const spec of specs) {
    if (spec.ai?.op !== op.op || !spec.describe) continue;
    const args = spec.ai.decode(op, evolved, state);
    if (args === null) continue;
    return spec.describe(args);
  }
  return String(op.op);
}
