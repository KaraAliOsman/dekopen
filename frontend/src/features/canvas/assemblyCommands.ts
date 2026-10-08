import { parseLocaleNumber, fmtWire } from "../../format";
import { t } from "../../i18n/es-CL";
import type {
  CommandArgs,
  CommandContext,
  CommandSpec,
  DesignOp,
  DesignOpState,
} from "../commands/types";
import type { IntentNode, OpeningChoice } from "./intentEditing";
import { baySpec, findNode, parentSplitOf, SPEC_KEY_TO_OPTION, walkIntent } from "./intentEditing";
import { OPENING_OPTIONS } from "./openings";
import { couplerFitsAngle } from "./members";
import { runCommand } from "../commands/registry";
import { unlinkCoupling, usedEdges } from "./assemblyGraph";
import {
  addAdjacentUnit,
  addStackedUnit,
  allowedCouplingKinds,
  canRemoveModuleDivision,
  copyBaySpec,
  duplicateModule,
  equalizeCouplingAngles,
  equalizeModuleBays,
  equalizeModuleWidths,
  flipModuleBay,
  insertModuleBetween,
  moduleGlassThicknessMm,
  moduleNeighbors,
  modulePanelSku,
  moveModuleDivision,
  removeModuleBay,
  removeModuleDivision,
  removeUnit,
  resizeModuleBay,
  scaleModuleWidths,
  setAllCouplingAngles,
  setAllModuleHeights,
  setBayOpening,
  setBaySlidingPreset,
  setBayTravel,
  setCouplerSku,
  setCouplingAngle,
  setCouplingKind,
  setModuleCount,
  setModuleGlass,
  setModuleGlassThickness,
  setModuleOpening,
  setModulePanel,
  setModuleTree,
  setModuleWidth,
  splitModuleBay,
  swapModules,
  updateModuleBay,
  type ProductJson,
  type ProductModuleJson,
} from "./productEditing";

/** Same presentation rules as the canvas DraftFields: positive dimensions
 * commit at 0.01mm, joint angles stay strictly inside ±90° at 0.1°, module
 * counts are positive integers bounded by the product contract. */
const MAX_MM = 30000;

function normalizeMm(raw: string): string | null {
  const value = parseLocaleNumber(raw);
  if (value === null || value <= 0 || value > MAX_MM) return null;
  return fmtWire(value);
}

function normalizeAngle(raw: string): string | null {
  const value = parseLocaleNumber(raw);
  if (value === null || Math.abs(value) >= 90) return null;
  return fmtWire(value, 1);
}

function normalizeCount(raw: string): string | null {
  const value = parseLocaleNumber(raw);
  if (value === null || !Number.isInteger(value) || value < 1 || value > 12) return null;
  return String(value);
}

function selectedModule(ctx: CommandContext): ProductModuleJson | null {
  return ctx.product.assembly.modules.find((module) => module.id === ctx.selection) ?? null;
}

/** Module the selection lives in — the module row itself, or the module
 * owning a selected bay/split/handle. Module-level commands (duplicate,
 * reorder, width) act on it so a selected paño doesn't orphan them. */
function selectedModuleScope(ctx: CommandContext): ProductModuleJson | null {
  return selectedModule(ctx) ?? selectedTreeNode(ctx)?.module ?? null;
}

function selectedCoupling(ctx: CommandContext) {
  return ctx.product.assembly.couplings.find((coupling) => coupling.id === ctx.selection) ?? null;
}

/** Composite selection "moduleId/nodeId" → owning module + tree node.
 * Mullions, transoms and bays all live behind this address form. */
function selectedTreeNode(
  ctx: CommandContext,
): { module: ProductModuleJson; node: IntentNode } | null {
  const separator = ctx.selection?.indexOf("/") ?? -1;
  if (!ctx.selection || separator === -1) return null;
  const moduleId = ctx.selection.slice(0, separator);
  const nodeId = ctx.selection.slice(separator + 1);
  const module = ctx.product.assembly.modules.find((item) => item.id === moduleId) ?? null;
  const node = module ? findNode(module.tree, nodeId) : null;
  return module && node ? { module, node } : null;
}

function selectedSplit(ctx: CommandContext) {
  const target = selectedTreeNode(ctx);
  return target && (target.node.type === "SPLIT_V" || target.node.type === "SPLIT_H")
    ? target
    : null;
}

function selectedBayTarget(ctx: CommandContext) {
  const target = selectedTreeNode(ctx);
  return target && target.node.type === "BAY" ? target : null;
}

/** Target resolution: explicit args (palette params, AI wire args) win over
 * the live selection — same stable id space either way. */
function moduleTarget(ctx: CommandContext, args: CommandArgs): ProductModuleJson | null {
  const id = args.module ?? selectedModuleScope(ctx)?.id ?? null;
  return id ? (ctx.product.assembly.modules.find((module) => module.id === id) ?? null) : null;
}

function couplingTarget(ctx: CommandContext, args: CommandArgs) {
  const id = args.coupling ?? selectedCoupling(ctx)?.id ?? null;
  return id ? (ctx.product.assembly.couplings.find((item) => item.id === id) ?? null) : null;
}

function bayTarget(ctx: CommandContext, args: CommandArgs) {
  if (args.module && args.bay) {
    const module = ctx.product.assembly.modules.find((item) => item.id === args.module) ?? null;
    const node = module ? findNode(module.tree, args.bay) : null;
    return module && node?.type === "BAY" ? { module, node } : null;
  }
  return selectedBayTarget(ctx);
}

function splitTarget(ctx: CommandContext, args: CommandArgs) {
  if (args.module && args.division) {
    const module = ctx.product.assembly.modules.find((item) => item.id === args.module) ?? null;
    const node = module ? findNode(module.tree, args.division) : null;
    return module && node && (node.type === "SPLIT_V" || node.type === "SPLIT_H")
      ? { module, node }
      : null;
  }
  return selectedSplit(ctx);
}

/** The module a new member's id was minted from — post-commit selection
 * helper for structural run commands (duplicate, stack, insert). */
function createdModule(before: ProductJson, after: ProductJson): string | null {
  return (
    after.assembly.modules.find(
      (module) => !before.assembly.modules.some((item) => item.id === module.id),
    )?.id ?? null
  );
}

/** Wire `module`/`coupling` address → entity id. A string is a stable domain
 * ref — the module's own id, a synthetic `added_m{n}`/`added_c{n}` minted by
 * an earlier structural op in the same sequence, or the `m{n}`/`c{n}`
 * positional fallback — a number stays a legacy index. */
/** Positional addresses (a bare number or `m{n}`/`c{n}`) name the sequence
 * author's ORIGINAL ordering — the backend validator resolves them against
 * the immutable summary list, so the client resolves them against the
 * sequence-start product in state.origin. A member removed mid-sequence is
 * no longer addressable by position on either side. */
function moduleAt(product: ProductJson, address: unknown, state?: DesignOpState): string | null {
  const positional = state?.origin ?? product;
  const live = (id: string | undefined): string | null =>
    id && product.assembly.modules.some((module) => module.id === id) ? id : null;
  if (typeof address === "number") {
    return live(positional.assembly.modules[address]?.id);
  }
  if (typeof address !== "string") return null;
  const direct = product.assembly.modules.find((module) => module.id === address);
  if (direct) return direct.id;
  const added = /^added_m(\d+)$/.exec(address);
  if (added) return state?.addedModules[Number(added[1]) - 1] ?? null;
  const index = /^m(\d+)$/.exec(address);
  if (index) return live(positional.assembly.modules[Number(index[1]) - 1]?.id);
  return null;
}

function couplingAt(product: ProductJson, address: unknown, state?: DesignOpState): string | null {
  const positional = state?.origin ?? product;
  const live = (id: string | undefined): string | null =>
    id && product.assembly.couplings.some((coupling) => coupling.id === id) ? id : null;
  if (typeof address === "number") {
    return live(positional.assembly.couplings[address]?.id);
  }
  if (typeof address !== "string") return null;
  const direct = product.assembly.couplings.find((coupling) => coupling.id === address);
  if (direct) return direct.id;
  const added = /^added_c(\d+)$/.exec(address);
  if (added) return state?.addedCouplings[Number(added[1]) - 1] ?? null;
  const index = /^c(\d+)$/.exec(address);
  if (index) return live(positional.assembly.couplings[Number(index[1]) - 1]?.id);
  return null;
}

function text(value: unknown): string | null {
  if (typeof value === "string" && value.length) return value;
  // El wire manda los mm/ángulos como números — rechazarlos deja las cards
  // con el nombre crudo de la op en vez de la descripción del registro.
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

/** Entero positivo del wire — number o string numérico; null si no calza. */
function intAt(value: unknown): number | null {
  const parsed =
    typeof value === "number" ? value : Number(typeof value === "string" ? value : NaN);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

/** Human position label for a wire address — '2' for the second module,
 * 'nueva 1' for a unit an earlier op in the sequence just created. */
function targetLabel(address: unknown, entities: { id: string }[]): string {
  if (typeof address === "number") return String(address + 1);
  if (typeof address !== "string") return "?";
  const added = /^added_[mc](\d+)$/.exec(address);
  if (added?.[1]) return `nueva ${added[1]}`;
  const index = entities.findIndex((entity) => entity.id === address);
  if (index >= 0) return String(index + 1);
  const positional = /^[mc](\d+)$/.exec(address);
  return positional?.[1] ?? "?";
}

/** Wire `module` address (ref or legacy index) → args `{module: <id>,
 * target: "<n>"}`: the id drives `apply`, the position stays for human
 * descriptions. */
function decodeModule(
  op: DesignOp,
  product: ProductJson,
  state?: DesignOpState,
  extra: CommandArgs = {},
): CommandArgs | null {
  const id = moduleAt(product, op.module, state);
  return id
    ? { module: id, target: targetLabel(op.module, product.assembly.modules), ...extra }
    : null;
}

function decodeCoupling(
  op: DesignOp,
  product: ProductJson,
  state?: DesignOpState,
  extra: CommandArgs = {},
): CommandArgs | null {
  const id = couplingAt(product, op.coupling, state);
  return id
    ? {
        coupling: id,
        target: targetLabel(op.coupling, product.assembly.couplings),
        ...extra,
      }
    : null;
}

/** IA2 — paños/divisiones de un módulo en orden de documento (el índice
 * posicional del wire apunta a ESTA lista, igual que en el backend). */
function moduleNodes(product: ProductJson, moduleId: string, kind: "BAY" | "SPLIT"): IntentNode[] {
  const module = product.assembly.modules.find((item) => item.id === moduleId);
  if (!module) return [];
  return walkIntent(module.tree).filter((node) =>
    kind === "BAY" ? node.type === "BAY" : node.type === "SPLIT_V" || node.type === "SPLIT_H",
  );
}

/** Wire `bay`/`divider` → node id inside the resolved module: real id, the
 * "modId/nodeId" composite the canvas selects by, `added_b{n}`/`added_d{n}`
 * minted earlier in the sequence, or a bare/index positional against the
 * module's nodes in the sequence's ORIGIN product (bays never reorder). */
function nodeAt(
  product: ProductJson,
  moduleId: string,
  address: unknown,
  state: DesignOpState | undefined,
  kind: "BAY" | "SPLIT",
): string | null {
  const live = moduleNodes(product, moduleId, kind);
  const liveId = (id: string | undefined): string | null =>
    id && live.some((node) => node.id === id) ? id : null;
  const added = kind === "BAY" ? state?.addedBays : state?.addedDividers;
  const positional = (): string | null => {
    if (typeof address === "number") {
      const origin = state?.origin;
      const basis =
        origin && origin.assembly.modules.some((m) => m.id === moduleId)
          ? moduleNodes(origin, moduleId, kind)
          : live;
      return liveId(basis[address]?.id);
    }
    return null;
  };
  if (typeof address !== "string") return positional();
  if (liveId(address)) return address;
  const slash = address.indexOf("/");
  if (slash !== -1 && liveId(address.slice(slash + 1))) return address.slice(slash + 1);
  const synthetic =
    kind === "BAY" ? /^added_b(\d+)$/.exec(address) : /^added_d(\d+)$/.exec(address);
  if (synthetic) return liveId(added?.[Number(synthetic[1]) - 1]);
  const index = kind === "BAY" ? /^b(\d+)$/.exec(address) : /^d(\d+)$/.exec(address);
  if (index) {
    const origin = state?.origin;
    const basis =
      origin && origin.assembly.modules.some((m) => m.id === moduleId)
        ? moduleNodes(origin, moduleId, kind)
        : live;
    return liveId(basis[Number(index[1]) - 1]?.id);
  }
  return null;
}

function decodeBay(
  op: DesignOp,
  product: ProductJson,
  state?: DesignOpState,
  extra: CommandArgs = {},
): CommandArgs | null {
  const moduleId = moduleAt(product, op.module, state);
  if (!moduleId) return null;
  const bayId = nodeAt(product, moduleId, op.bay, state, "BAY");
  if (!bayId) return null;
  return {
    module: moduleId,
    bay: bayId,
    target: targetLabel(op.module, product.assembly.modules),
    ...extra,
  };
}

const OPENING_LABELS: Partial<Record<string, string>> = {
  FIXED: "fijo",
  FIXED_SASH: "fijo en hoja",
  TURN_LEFT: "abatible izquierda",
  TURN_RIGHT: "abatible derecha",
  TURN_LEFT_OUT: "abatible afuera izquierda",
  TURN_RIGHT_OUT: "abatible afuera derecha",
  TILT_TURN_LEFT: "oscilobatiente izquierda",
  TILT_TURN_RIGHT: "oscilobatiente derecha",
  TILT: "banderola",
  BOTTOM_HUNG: "abatimiento inferior",
  BOTTOM_HUNG_OUT: "abatimiento inferior afuera",
  FRENCH_L: "francesa activa izquierda",
  FRENCH_R: "francesa activa derecha",
  FRENCH_OUT_L: "francesa afuera activa izquierda",
  FRENCH_OUT_R: "francesa afuera activa derecha",
  SLIDING_2L: "corredera 2 hojas",
  AWNING: "proyectante",
  DOOR_ENTRY: "puerta",
  DOOR_LEFT_OUT: "puerta afuera izquierda",
  DOOR_RIGHT_OUT: "puerta afuera derecha",
  DOOR_DOUBLE: "puerta doble",
  DOOR_DOUBLE_L: "puerta doble izquierda",
};

function moduleLabel(args: CommandArgs): string {
  return `módulo ${args.target ?? "?"}`;
}

/** THE command table — the single typed domain registry every surface shares.
 * Palette rows, shortcuts, context menus and AI ops all resolve to these
 * specs; `apply` is the only mutation path (one undoable commit upstream). */
export const ASSEMBLY_COMMANDS: CommandSpec[] = [
  {
    id: "product.add-right",
    title: "cmd.addUnitRight",
    keywords: ["añadir", "unidad", "vano", "hoja", "derecha", "modulo", "agregar"],
    apply: (ctx) => addAdjacentUnit(ctx.product, "right"),
    describe: () => "agregar unidad a la derecha",
    ai: { op: "add_unit", decode: (op) => (op.side === "left" ? null : { side: "right" }) },
  },
  {
    id: "product.add-left",
    title: "cmd.addUnitLeft",
    keywords: ["añadir", "unidad", "vano", "hoja", "izquierda", "modulo", "agregar"],
    apply: (ctx) => addAdjacentUnit(ctx.product, "left"),
    describe: () => "agregar unidad a la izquierda",
    ai: { op: "add_unit", decode: (op) => (op.side === "left" ? { side: "left" } : null) },
  },
  {
    id: "product.set-module-count",
    title: "cmd.setModuleCount",
    keywords: ["cantidad", "módulos", "modulos", "unidades", "número"],
    params: () => [
      { kind: "number", id: "count", label: t("cmd.moduleCountLabel"), validate: normalizeCount },
    ],
    apply: (ctx, args) => {
      const count = normalizeCount(args.count ?? "");
      return count === null ? ctx.product : setModuleCount(ctx.product, Number(count));
    },
    describe: (args) => `${args.count ?? "?"} módulos`,
    ai: {
      op: "set_module_count",
      decode: (op) =>
        typeof op.count === "number" && Number.isInteger(op.count) && op.count >= 1
          ? { count: String(op.count) }
          : null,
    },
  },
  {
    id: "module.remove",
    title: "cmd.removeUnit",
    keywords: ["eliminar", "quitar", "unidad", "vano", "hoja", "modulo"],
    applicable: (ctx) =>
      selectedModuleScope(ctx) !== null && ctx.product.assembly.modules.length > 1,
    apply: (ctx, args) => {
      const id = args.module ?? selectedModule(ctx)?.id;
      return id && ctx.product.assembly.modules.length > 1
        ? removeUnit(ctx.product, id)
        : ctx.product;
    },
    postCommit: (ctx, before, next, args) => {
      const removedId = args.module ?? ctx.selection;
      const index = before.assembly.modules.findIndex((item) => item.id === removedId);
      ctx.select(
        next.assembly.modules[Math.min(Math.max(index, 0), next.assembly.modules.length - 1)]?.id ??
          null,
      );
    },
    describe: (args) => `quitar ${moduleLabel(args)}`,
    ai: { op: "remove_unit", decode: decodeModule },
  },
  {
    id: "product.set-height",
    title: "cmd.setHeight",
    keywords: ["alto", "altura", "dimensiones"],
    params: (ctx) => [
      {
        kind: "number",
        id: "height",
        label: t("cmd.heightLabel"),
        unit: "mm",
        defaultValue: ctx.product.assembly.modules[0]?.height_mm,
        validate: normalizeMm,
      },
    ],
    apply: (ctx, args) => {
      const height = normalizeMm(args.height ?? "");
      return height === null ? ctx.product : setAllModuleHeights(ctx.product, height);
    },
    describe: (args) => `alto ${args.height ?? "?"} mm`,
    ai: {
      op: "set_height",
      decode: (op) => {
        const height = text(op.height_mm);
        return height ? { height } : null;
      },
    },
  },
  {
    id: "product.set-total-width",
    title: "cmd.setTotalWidth",
    keywords: ["ancho", "total", "dimensiones", "ancho total"],
    params: (ctx) => [
      {
        kind: "number",
        id: "width",
        label: t("cmd.totalWidthLabel"),
        unit: "mm",
        defaultValue: String(
          ctx.product.assembly.modules.reduce((sum, module) => sum + Number(module.width_mm), 0),
        ),
        validate: normalizeMm,
      },
    ],
    apply: (ctx, args) => {
      const width = normalizeMm(args.width ?? "");
      return width === null ? ctx.product : scaleModuleWidths(ctx.product, width);
    },
    describe: (args) => `ancho total ${args.width ?? "?"} mm`,
    ai: {
      op: "set_total_width",
      decode: (op) => {
        const width = text(op.width_mm);
        return width ? { width } : null;
      },
    },
  },
  {
    id: "module.set-width",
    title: "cmd.setWidth",
    keywords: ["ancho", "unidad", "dimensiones"],
    applicable: (ctx) => selectedModule(ctx) !== null,
    params: (ctx) => [
      {
        kind: "number",
        id: "width",
        label: t("cmd.widthLabel"),
        unit: "mm",
        defaultValue: selectedModuleScope(ctx)?.width_mm,
        validate: normalizeMm,
      },
    ],
    apply: (ctx, args) => {
      const id = args.module ?? selectedModule(ctx)?.id;
      const width = normalizeMm(args.width ?? "");
      return id && width !== null ? setModuleWidth(ctx.product, id, width) : ctx.product;
    },
    describe: (args) => `${moduleLabel(args)}: ancho ${args.width ?? "?"} mm`,
    ai: {
      op: "set_module_width",
      decode: (op, product, state) => {
        const width = text(op.width_mm);
        return width ? decodeModule(op, product, state, { width }) : null;
      },
    },
  },
  {
    id: "module.set-opening",
    title: "cmd.setOpening",
    keywords: ["apertura", "hoja", "fijo", "oscilobatiente", "puerta", "corredera"],
    applicable: (ctx) => selectedModule(ctx) !== null,
    params: () => [
      {
        kind: "choice",
        id: "opening",
        label: t("cmd.openingLabel"),
        options: OPENING_OPTIONS.map(([value, key]) => ({ value, label: t(key) })),
      },
    ],
    apply: (ctx, args) => {
      const id = args.module ?? selectedModule(ctx)?.id;
      if (!id || !args.opening) return ctx.product;
      if (args.bay) {
        return setBayOpening(ctx.product, id, args.bay, args.opening);
      }
      if (args.everyBay) {
        // IA2 — paridad con el validador: una op module-wide aplica la
        // misma changeOpening sobre CADA hoja (la regla D03 por hoja).
        return moduleNodes(ctx.product, id, "BAY").reduce(
          (next, bay) => setBayOpening(next, id, bay.id, args.opening!),
          ctx.product,
        );
      }
      return setModuleOpening(ctx.product, id, args.opening as OpeningChoice | string);
    },
    describe: (args) => {
      // Una key D03 se muestra como su opción humana, no como el token wire.
      const resolved = SPEC_KEY_TO_OPTION[args.opening ?? ""] ?? args.opening;
      return `${moduleLabel(args)}: ${OPENING_LABELS[resolved ?? ""] ?? resolved ?? "?"}`;
    },
    ai: {
      op: "set_opening",
      decode: (op, product, state) => {
        const opening = text(op.opening);
        if (!opening) return null;
        // IA2 — "bay" en el wire cambia UNA hoja (setBayOpening); sin él
        // la op toca todas las hojas del módulo (todas: "1").
        if (op.bay !== undefined) {
          return decodeBay(op, product, state, { opening });
        }
        return decodeModule(op, product, state, { opening, everyBay: "1" });
      },
    },
  },
  {
    id: "module.set-glass",
    title: "cmd.setGlass",
    keywords: ["vidrio", "composicion", "composición", "artículo", "articulo", "dvh"],
    applicable: (ctx) => selectedModule(ctx) !== null && ctx.catalog.glassSkus.length > 0,
    params: (ctx) => [
      {
        kind: "choice",
        id: "glass",
        label: t("cmd.glassLabel"),
        options: ctx.catalog.glassSkus.map((value) => ({ value, label: value })),
      },
    ],
    apply: (ctx, args) => {
      const id = args.module ?? selectedModule(ctx)?.id;
      if (!id) return ctx.product;
      // IA2 bay-scoped: una hoja toma el SKU sin tocar el spec de las demás
      // (paridad con el validador: set_glass bay solo escribe el artículo).
      if (args.bay) {
        return updateModuleBay(ctx.product, id, args.bay, {
          glass_article_sku: args.glass ?? null,
        });
      }
      if (args.everyBay) {
        return moduleNodes(ctx.product, id, "BAY").reduce(
          (next, bay) =>
            updateModuleBay(next, id, bay.id, { glass_article_sku: args.glass ?? null }),
          ctx.product,
        );
      }
      return setModuleGlass(ctx.product, id, args.glass ?? null);
    },
    describe: (args) => `${moduleLabel(args)}: vidrio ${args.glass ?? "?"}`,
    ai: {
      op: "set_glass",
      decode: (op, product, state) => {
        const sku = text(op.sku) ?? text(op.recipe);
        if (!sku) return null;
        if (op.bay !== undefined) return decodeBay(op, product, state, { glass: sku });
        return decodeModule(op, product, state, { glass: sku, everyBay: "1" });
      },
    },
  },
  {
    id: "module.set-glass-thickness",
    title: "cmd.setGlassThickness",
    keywords: ["vidrio", "espesor", "dvh"],
    applicable: (ctx) => selectedModule(ctx) !== null && ctx.catalog.glassThicknesses.length > 0,
    params: (ctx) => [
      {
        kind: "choice",
        id: "thickness",
        label: t("cmd.glassThicknessLabel"),
        options: ctx.catalog.glassThicknesses.map((value) => ({
          value,
          label: `${value} mm`,
        })),
      },
    ],
    apply: (ctx, args) => {
      const id = args.module ?? selectedModule(ctx)?.id;
      if (!id) return ctx.product;
      if (args.bay) {
        return updateModuleBay(ctx.product, id, args.bay, {
          glass_thickness_mm: args.thickness ?? null,
        });
      }
      if (args.everyBay) {
        return moduleNodes(ctx.product, id, "BAY").reduce(
          (next, bay) =>
            updateModuleBay(next, id, bay.id, { glass_thickness_mm: args.thickness ?? null }),
          ctx.product,
        );
      }
      return setModuleGlassThickness(ctx.product, id, args.thickness ?? null);
    },
    describe: (args) => `${moduleLabel(args)}: vidrio ${args.thickness ?? "?"} mm`,
    ai: {
      op: "set_glass_thickness",
      decode: (op, product, state) => {
        if (op.bay !== undefined) {
          return decodeBay(op, product, state, { thickness: text(op.mm) ?? "" });
        }
        return decodeModule(op, product, state, {
          thickness: text(op.mm) ?? "",
          everyBay: "1",
        });
      },
    },
  },
  {
    id: "module.set-panel",
    title: "cmd.setPanel",
    keywords: ["panel", "sandwich", "tablero"],
    applicable: (ctx) => selectedModule(ctx) !== null && ctx.catalog.panelSkus.length > 0,
    params: (ctx) => [
      {
        kind: "choice",
        id: "panel",
        label: t("cmd.panelLabel"),
        options: [
          { value: "", label: t("assembly.noPanel") },
          ...ctx.catalog.panelSkus.map((value) => ({ value, label: value })),
        ],
      },
    ],
    apply: (ctx, args) => {
      const id = args.module ?? selectedModule(ctx)?.id;
      if (!id) return ctx.product;
      if (args.bay) {
        return updateModuleBay(ctx.product, id, args.bay, {
          panel_article_sku: args.panel || null,
        });
      }
      if (args.everyBay) {
        return moduleNodes(ctx.product, id, "BAY").reduce(
          (next, bay) =>
            updateModuleBay(next, id, bay.id, { panel_article_sku: args.panel || null }),
          ctx.product,
        );
      }
      return setModulePanel(ctx.product, id, args.panel || null);
    },
    describe: (args) => `${moduleLabel(args)}: panel ${args.panel || "ninguno"}`,
    ai: {
      op: "set_panel",
      decode: (op, product, state) => {
        const sku = op.sku === null ? "" : (text(op.sku) ?? "");
        if (op.bay !== undefined) return decodeBay(op, product, state, { panel: sku });
        return decodeModule(op, product, state, { panel: sku, everyBay: "1" });
      },
    },
  },
  {
    id: "module.clear-panel",
    title: "cmd.clearPanel",
    keywords: ["panel", "quitar", "eliminar"],
    applicable: (ctx) => {
      const module = selectedModule(ctx);
      return module !== null && modulePanelSku(module) !== null;
    },
    apply: (ctx) => {
      const module = selectedModule(ctx);
      return module ? setModulePanel(ctx.product, module.id, null) : ctx.product;
    },
  },
  {
    id: "module.clear-glass-thickness",
    title: "cmd.clearGlassThickness",
    keywords: ["vidrio", "espesor", "quitar"],
    applicable: (ctx) => {
      const module = selectedModule(ctx);
      return module !== null && moduleGlassThicknessMm(module) !== null;
    },
    apply: (ctx) => {
      const module = selectedModule(ctx);
      return module ? setModuleGlassThickness(ctx.product, module.id, null) : ctx.product;
    },
  },
  {
    id: "product.equalize-widths",
    title: "cmd.equalizeWidths",
    keywords: ["igualar", "anchos", "unidades", "repartir"],
    applicable: (ctx) => ctx.product.assembly.modules.length > 1,
    apply: (ctx) => equalizeModuleWidths(ctx.product),
    describe: () => "anchos iguales",
    ai: { op: "equalize_widths", decode: () => ({}) },
  },
  {
    id: "product.equalize-angles",
    title: "cmd.equalizeAngles",
    keywords: ["igualar", "ángulos", "angulos", "acoplamiento", "bow"],
    applicable: (ctx) => ctx.product.assembly.couplings.length > 1,
    apply: (ctx) => equalizeCouplingAngles(ctx.product),
    describe: () => "ángulos iguales",
    ai: { op: "equalize_angles", decode: () => ({}) },
  },
  {
    id: "product.straighten",
    title: "cmd.straighten",
    keywords: ["recto", "enderezar", "cero", "ángulos", "planar"],
    applicable: (ctx) =>
      ctx.product.assembly.couplings.some((coupling) => coupling.angle_deg !== "0"),
    apply: (ctx) => setAllCouplingAngles(ctx.product, "0"),
    describe: () => "conjunto recto",
  },
  {
    id: "coupling.set-angle",
    title: "cmd.setAngle",
    keywords: ["ángulo", "angulo", "acoplamiento", "unión", "union", "plano"],
    applicable: (ctx) => selectedCoupling(ctx) !== null,
    params: (ctx) => [
      {
        kind: "number",
        id: "angle",
        label: t("cmd.angleLabel"),
        unit: "°",
        defaultValue: selectedCoupling(ctx)?.angle_deg,
        validate: normalizeAngle,
      },
    ],
    apply: (ctx, args) => {
      const id = args.coupling ?? selectedCoupling(ctx)?.id;
      const angle = normalizeAngle(args.angle ?? "");
      return id && angle !== null ? setCouplingAngle(ctx.product, id, angle) : ctx.product;
    },
    describe: (args) =>
      Number(args.angle ?? "0") === 0
        ? t("cmd.setAngleStraightDesc")
        : `unión ${args.target ?? "?"}: ${args.angle ?? "?"}°`,
    ai: {
      op: "set_coupling_angle",
      decode: (op, product, state) => {
        const angle = text(op.angle_deg);
        return angle ? decodeCoupling(op, product, state, { angle }) : null;
      },
    },
  },
  {
    id: "coupling.clear-angle",
    title: "cmd.clearAngle",
    keywords: ["ángulo", "angulo", "recto", "cero", "acoplamiento"],
    applicable: (ctx) => {
      const coupling = selectedCoupling(ctx);
      return coupling !== null && coupling.angle_deg !== "0";
    },
    apply: (ctx) => {
      const coupling = selectedCoupling(ctx);
      return coupling ? setCouplingAngle(ctx.product, coupling.id, "0") : ctx.product;
    },
  },
  {
    id: "coupling.set-coupler",
    title: "cmd.setCoupler",
    keywords: ["cople", "acoplador", "perfil", "acoplamiento"],
    applicable: (ctx) => selectedCoupling(ctx) !== null && ctx.catalog.couplerSkus.length > 0,
    params: (ctx) => {
      // P06 — filtro por compatibilidad de ángulo declarada en catálogo;
      // el cople asignado siempre aparece (la selección vigente no se esconde).
      const coupling = selectedCoupling(ctx);
      const angleDeg = Number(coupling?.angle_deg ?? "0");
      const skus = ctx.catalog.couplerSkus.filter(
        (sku) =>
          sku === coupling?.coupler_profile_sku ||
          couplerFitsAngle(ctx.members?.couplerFor(sku) ?? null, angleDeg),
      );
      return [
        {
          kind: "choice" as const,
          id: "coupler",
          label: t("cmd.couplerLabel"),
          options: skus.map((value) => ({
            value,
            label: ctx.members?.couplerFor(value)?.name
              ? `${ctx.members.couplerFor(value)!.name} · ${value}`
              : value,
          })),
        },
      ];
    },
    apply: (ctx, args) => {
      const id = args.coupling ?? selectedCoupling(ctx)?.id;
      return id ? setCouplerSku(ctx.product, id, args.coupler ?? null) : ctx.product;
    },
    describe: (args) => `unión ${args.target ?? "?"}: cople ${args.coupler ?? "?"}`,
  },
  {
    id: "module.duplicate",
    title: "cmd.duplicateModule",
    keywords: ["duplicar", "copiar", "clonar", "unidad", "vano"],
    shortcut: "mod+d",
    applicable: (ctx) => selectedModuleScope(ctx) !== null,
    apply: (ctx, args) => {
      const module = moduleTarget(ctx, args);
      return module ? duplicateModule(ctx.product, module.id) : ctx.product;
    },
    postCommit: (ctx, before, next) => {
      const created = createdModule(before, next);
      if (created) ctx.select(created);
    },
    describe: () => "duplicar unidad",
    ai: { op: "duplicate_module", decode: decodeModule },
  },
  {
    id: "module.move-left",
    title: "cmd.moveModuleLeft",
    keywords: ["mover", "izquierda", "reordenar", "orden", "intercambiar"],
    applicable: (ctx) =>
      selectedModuleScope(ctx) !== null &&
      moduleNeighbors(ctx.product, selectedModuleScope(ctx)!.id).left !== null,
    apply: (ctx) => {
      const module = selectedModuleScope(ctx);
      const left = module ? moduleNeighbors(ctx.product, module.id).left : null;
      return module && left ? swapModules(ctx.product, module.id, left) : ctx.product;
    },
    describe: () => "intercambiar con la unidad de la izquierda",
  },
  {
    id: "module.move-right",
    title: "cmd.moveModuleRight",
    keywords: ["mover", "derecha", "reordenar", "orden", "intercambiar"],
    applicable: (ctx) =>
      selectedModuleScope(ctx) !== null &&
      moduleNeighbors(ctx.product, selectedModuleScope(ctx)!.id).right !== null,
    apply: (ctx) => {
      const module = selectedModuleScope(ctx);
      const right = module ? moduleNeighbors(ctx.product, module.id).right : null;
      return module && right ? swapModules(ctx.product, module.id, right) : ctx.product;
    },
    describe: () => "intercambiar con la unidad de la derecha",
  },
  {
    id: "module.stack-above",
    title: "cmd.stackAbove",
    keywords: ["apilar", "encima", "montante", "transom", "stacked", "superior"],
    applicable: (ctx) => {
      const module = selectedModuleScope(ctx);
      return (
        module !== null &&
        !module.contour &&
        !module.frameless &&
        !usedEdges(ctx.product, module.id).has("top")
      );
    },
    apply: (ctx, args) => {
      const module = moduleTarget(ctx, args);
      return module ? addStackedUnit(ctx.product, module.id) : ctx.product;
    },
    postCommit: (ctx, before, next) => {
      const created = createdModule(before, next);
      if (created) ctx.select(created);
    },
    describe: () => "unidad apilada encima",
    ai: { op: "add_stacked_unit", decode: decodeModule },
  },
  {
    id: "module.copy-spec",
    title: "cmd.copySpec",
    keywords: ["copiar", "especificación", "propiedades", "formato"],
    shortcut: "mod+shift+c",
    applicable: (ctx) => selectedModuleScope(ctx) !== null && ctx.writeSpecClipboard !== undefined,
    run: (ctx) => {
      const module = selectedModuleScope(ctx);
      if (module) ctx.writeSpecClipboard?.({ kind: "module", tree: module.tree });
    },
  },
  {
    id: "module.apply-spec",
    title: "cmd.applySpec",
    keywords: ["aplicar", "pegar", "especificación", "propiedades", "formato"],
    shortcut: "mod+shift+v",
    applicable: (ctx) => selectedModuleScope(ctx) !== null && ctx.specClipboard?.kind === "module",
    apply: (ctx) => {
      const module = selectedModuleScope(ctx);
      const clipboard = ctx.specClipboard;
      return module && clipboard?.kind === "module"
        ? setModuleTree(ctx.product, module.id, structuredClone(clipboard.tree))
        : ctx.product;
    },
    describe: () => "aplicar estructura copiada",
  },
  {
    id: "bay.copy-spec",
    title: "cmd.copyBaySpec",
    keywords: ["copiar", "especificación", "vano", "apertura", "vidrio", "hoja"],
    shortcut: "mod+shift+c",
    applicable: (ctx) => selectedBayTarget(ctx) !== null && ctx.writeSpecClipboard !== undefined,
    run: (ctx) => {
      const target = selectedBayTarget(ctx);
      if (target) ctx.writeSpecClipboard?.({ kind: "bay", spec: baySpec(target.node) });
    },
  },
  {
    id: "bay.apply-spec",
    title: "cmd.applyBaySpec",
    keywords: ["aplicar", "pegar", "especificación", "vano", "apertura", "vidrio"],
    shortcut: "mod+shift+v",
    applicable: (ctx) => selectedBayTarget(ctx) !== null && ctx.specClipboard?.kind === "bay",
    apply: (ctx) => {
      const target = selectedBayTarget(ctx);
      const clipboard = ctx.specClipboard;
      return target && clipboard?.kind === "bay"
        ? copyBaySpec(ctx.product, target.module.id, target.node.id, clipboard.spec)
        : ctx.product;
    },
    describe: () => "aplicar especificación de vano",
  },
  {
    id: "coupling.insert-module",
    title: "cmd.insertModule",
    // No "dividir" keyword: this inserts a whole new unit — under a divide
    // search it impersonates the in-place bay split (designer report P1-7).
    keywords: ["insertar", "unidad", "entre", "agregar"],
    applicable: (ctx) => {
      const coupling = selectedCoupling(ctx);
      return coupling !== null && (coupling.kind ?? "INLINE") === "INLINE";
    },
    apply: (ctx, args) => {
      const coupling = couplingTarget(ctx, args);
      return coupling ? insertModuleBetween(ctx.product, coupling.id) : ctx.product;
    },
    postCommit: (ctx, before, next) => {
      const created = createdModule(before, next);
      if (created) ctx.select(created);
    },
    describe: () => "insertar unidad en la unión",
    ai: { op: "insert_module", decode: decodeCoupling },
  },
  {
    id: "coupling.disconnect",
    title: "cmd.disconnectCoupling",
    keywords: ["desconectar", "quitar unión", "separar", "acoplamiento"],
    applicable: (ctx) => selectedCoupling(ctx) !== null,
    apply: (ctx, args) => {
      const coupling = couplingTarget(ctx, args);
      return coupling ? unlinkCoupling(ctx.product, coupling.id) : ctx.product;
    },
    postCommit: (ctx, _before, next) => {
      if (
        ctx.selection &&
        !next.assembly.couplings.some((coupling) => coupling.id === ctx.selection)
      ) {
        ctx.select(null);
      }
    },
    describe: () => "desconectar unión",
    ai: { op: "remove_coupling", decode: decodeCoupling },
  },
  {
    id: "coupling.set-kind",
    title: "cmd.couplingKind",
    keywords: ["tipo", "unión", "inline", "stacked", "tee", "corner", "esquina", "codo"],
    applicable: (ctx) => {
      const coupling = selectedCoupling(ctx);
      return coupling !== null && allowedCouplingKinds(ctx.product, coupling.id).length > 1;
    },
    params: (ctx) => {
      const coupling = selectedCoupling(ctx);
      const kinds = coupling ? allowedCouplingKinds(ctx.product, coupling.id) : [];
      return [
        {
          kind: "choice",
          id: "kind",
          label: t("cmd.couplingKindLabel"),
          options: kinds.map((value) => ({
            value,
            label: t(
              (
                {
                  INLINE: "assembly.kindInline",
                  STACKED: "assembly.kindStacked",
                  TEE: "assembly.kindTee",
                  CORNER: "assembly.kindCorner",
                } as const
              )[value],
            ),
          })),
        },
      ];
    },
    apply: (ctx, args) => {
      const coupling = couplingTarget(ctx, args);
      const kind = args.kind;
      return coupling && kind
        ? setCouplingKind(ctx.product, coupling.id, kind as "STACKED" | "TEE" | "CORNER" | "INLINE")
        : ctx.product;
    },
    describe: (args) => `unión ${args.target ?? "?"}: ${args.kind ?? "?"}`,
    ai: {
      op: "set_coupling_kind",
      decode: (op, product, state) => {
        const kind = text(op.kind);
        return kind ? decodeCoupling(op, product, state, { kind }) : null;
      },
    },
  },
  {
    id: "bay.remove",
    title: "cmd.removeBay",
    keywords: ["quitar", "eliminar", "vano", "hoja"],
    applicable: (ctx) => {
      const target = selectedBayTarget(ctx);
      return target !== null && parentSplitOf(target.module.tree, target.node.id) !== null;
    },
    apply: (ctx, args) => {
      const target = bayTarget(ctx, args);
      return target ? removeModuleBay(ctx.product, target.module.id, target.node.id) : ctx.product;
    },
    postCommit: (ctx, _before, _next, args) => {
      const target = bayTarget(ctx, args);
      if (!target) return;
      const parent = parentSplitOf(target.module.tree, target.node.id);
      const sibling = (parent?.children ?? []).find((child) => child.id !== target.node.id)?.id;
      ctx.select(sibling ? `${target.module.id}/${sibling}` : target.module.id);
    },
    describe: () => "quitar vano",
    ai: {
      op: "remove_bay",
      decode: (op, product, state) => decodeBay(op, product, state),
    },
  },
  {
    id: "split.remove",
    title: "cmd.removeSplit",
    keywords: ["quitar", "eliminar", "división", "montante", "travesaño", "mullion", "transom"],
    applicable: (ctx) => {
      const target = selectedSplit(ctx);
      return (
        target !== null && canRemoveModuleDivision(ctx.product, target.module.id, target.node.id)
      );
    },
    apply: (ctx, args) => {
      const target = splitTarget(ctx, args);
      return target
        ? removeModuleDivision(ctx.product, target.module.id, target.node.id)
        : ctx.product;
    },
    postCommit: (ctx, _before, _next, args) => {
      const target = splitTarget(ctx, args);
      if (!target) return;
      const kept = target.node.children?.[0]?.id;
      ctx.select(kept ? `${target.module.id}/${kept}` : target.module.id);
    },
    describe: () => "quitar división",
    ai: {
      op: "remove_divider",
      decode: (op, product, state) => {
        const moduleId = moduleAt(product, op.module, state);
        if (!moduleId) return null;
        const division = nodeAt(product, moduleId, op.divider, state, "SPLIT");
        if (!division) return null;
        const keep =
          op.keep_bay !== undefined ? nodeAt(product, moduleId, op.keep_bay, state, "BAY") : null;
        return {
          module: moduleId,
          division,
          ...(keep ? { keep } : {}),
          target: targetLabel(op.module, product.assembly.modules),
        };
      },
    },
  },
  {
    id: "edit.remove",
    title: "cmd.removeSelection",
    keywords: ["eliminar", "quitar", "borrar"],
    shortcut: "del",
    mutates: true,
    applicable: (ctx) =>
      (selectedModule(ctx) !== null && ctx.product.assembly.modules.length > 1) ||
      selectedCoupling(ctx) !== null ||
      selectedSplit(ctx) !== null ||
      (selectedBayTarget(ctx) !== null &&
        parentSplitOf(selectedBayTarget(ctx)!.module.tree, selectedBayTarget(ctx)!.node.id) !==
          null),
    run: (ctx) => {
      const dispatch = (specId: string, args: CommandArgs): void => {
        const spec = ASSEMBLY_COMMANDS.find((item) => item.id === specId);
        if (spec) runCommand(ctx, spec, args);
      };
      const split = selectedSplit(ctx);
      if (split) {
        dispatch("split.remove", { module: split.module.id, division: split.node.id });
        return;
      }
      const coupling = selectedCoupling(ctx);
      if (coupling) {
        dispatch("coupling.disconnect", { coupling: coupling.id });
        return;
      }
      const bay = selectedBayTarget(ctx);
      if (bay && parentSplitOf(bay.module.tree, bay.node.id)) {
        dispatch("bay.remove", { module: bay.module.id, bay: bay.node.id });
        return;
      }
      const module = selectedModule(ctx);
      if (module && ctx.product.assembly.modules.length > 1) {
        dispatch("module.remove", { module: module.id });
      }
    },
    describe: () => "eliminar selección",
  },
  {
    id: "edit.deselect",
    title: "cmd.deselect",
    keywords: ["deseleccionar", "cancelar", "escape"],
    shortcut: "esc",
    applicable: (ctx) => ctx.selection !== null && ctx.selection !== "",
    run: (ctx) => ctx.select(null),
    describe: () => "deseleccionar",
  },
  {
    id: "edit.repeat",
    title: "cmd.repeatLast",
    keywords: ["repetir", "último", "otra vez"],
    shortcut: "mod+shift+d",
    mutates: true,
    applicable: (ctx) =>
      ctx.lastMutation !== null &&
      ctx.lastMutation !== undefined &&
      ASSEMBLY_COMMANDS.some(
        (spec) => spec.id === ctx.lastMutation?.specId && (spec.applicable?.(ctx) ?? true),
      ),
    run: (ctx) => {
      const spec = ASSEMBLY_COMMANDS.find((item) => item.id === ctx.lastMutation?.specId);
      if (spec && ctx.lastMutation) runCommand(ctx, spec, ctx.lastMutation.args);
    },
  },
  {
    id: "bay.split-vertical",
    title: "cmd.splitBayVertical",
    keywords: ["dividir", "montante", "mullion", "paño", "vano", "vertical"],
    mutates: true,
    applicable: (ctx) => ctx.catalog.mullionSkus.SPLIT_V !== undefined,
    apply: (ctx, args) => {
      const target = moduleTarget(ctx, args);
      const sku = args.mullion ?? ctx.catalog.mullionSkus.SPLIT_V;
      if (!target || !sku || !ctx.members) return ctx.product;
      return splitModuleBay(
        ctx.product,
        target.id,
        {
          type: "SPLIT_V",
          mullionSku: sku,
          offsetMm: args.offset || undefined,
          bayId: args.bay || undefined,
          parts: args.parts ? (intAt(args.parts) ?? undefined) : undefined,
        },
        ctx.members,
      );
    },
    describe: (args) =>
      args.parts && (intAt(args.parts) ?? 0) >= 2
        ? `${moduleLabel(args)}: ${args.parts} hojas iguales`
        : `${moduleLabel(args)}: montante${args.bay ? " · " + args.bay : ""}`,
    ai: {
      op: "split_bay",
      decode: (op, product, state) => {
        if (text(op.axis) !== "V") return null;
        const moduleId = moduleAt(product, op.module, state);
        if (!moduleId) return null;
        const bay = op.bay !== undefined ? nodeAt(product, moduleId, op.bay, state, "BAY") : null;
        if (op.bay !== undefined && !bay) return null;
        const parts = intAt(op.parts);
        return {
          module: moduleId,
          ...(bay ? { bay } : {}),
          ...(parts !== null && parts >= 2 ? { parts: String(parts) } : {}),
          ...(text(op.offset_mm) ? { offset: text(op.offset_mm)! } : {}),
          ...(text(op.mullion_sku) ? { mullion: text(op.mullion_sku)! } : {}),
          target: targetLabel(op.module, product.assembly.modules),
        };
      },
    },
  },
  {
    id: "bay.split-horizontal",
    title: "cmd.splitBayHorizontal",
    keywords: ["dividir", "travesaño", "transom", "paño", "vano", "horizontal"],
    mutates: true,
    applicable: (ctx) => ctx.catalog.mullionSkus.SPLIT_H !== undefined,
    apply: (ctx, args) => {
      const target = moduleTarget(ctx, args);
      const sku = args.mullion ?? ctx.catalog.mullionSkus.SPLIT_H;
      if (!target || !sku || !ctx.members) return ctx.product;
      return splitModuleBay(
        ctx.product,
        target.id,
        {
          type: "SPLIT_H",
          mullionSku: sku,
          offsetMm: args.offset || undefined,
          bayId: args.bay || undefined,
          parts: args.parts ? (intAt(args.parts) ?? undefined) : undefined,
        },
        ctx.members,
      );
    },
    describe: (args) =>
      args.parts && (intAt(args.parts) ?? 0) >= 2
        ? `${moduleLabel(args)}: ${args.parts} hojas iguales`
        : `${moduleLabel(args)}: travesaño${args.bay ? " · " + args.bay : ""}`,
    ai: {
      op: "split_bay",
      decode: (op, product, state) => {
        if (text(op.axis) !== "H") return null;
        const moduleId = moduleAt(product, op.module, state);
        if (!moduleId) return null;
        const bay = op.bay !== undefined ? nodeAt(product, moduleId, op.bay, state, "BAY") : null;
        if (op.bay !== undefined && !bay) return null;
        const parts = intAt(op.parts);
        return {
          module: moduleId,
          ...(bay ? { bay } : {}),
          ...(parts !== null && parts >= 2 ? { parts: String(parts) } : {}),
          ...(text(op.offset_mm) ? { offset: text(op.offset_mm)! } : {}),
          ...(text(op.mullion_sku) ? { mullion: text(op.mullion_sku)! } : {}),
          target: targetLabel(op.module, product.assembly.modules),
        };
      },
    },
  },
  {
    id: "divider.move",
    title: "cmd.moveDivider",
    keywords: ["mover", "desplazar", "montante", "travesaño", "división", "division"],
    mutates: true,
    apply: (ctx, args) => {
      const target = splitTarget(ctx, args);
      return target && args.offset
        ? moveModuleDivision(ctx.product, target.module.id, target.node.id, args.offset)
        : ctx.product;
    },
    describe: (args) => `mover división a ${args.offset ?? "?"} mm`,
    ai: {
      op: "move_divider",
      decode: (op, product, state) => {
        const moduleId = moduleAt(product, op.module, state);
        if (!moduleId) return null;
        const division = nodeAt(product, moduleId, op.divider, state, "SPLIT");
        const offset = text(op.offset_mm);
        if (!division || !offset) return null;
        return {
          module: moduleId,
          division,
          offset,
          target: targetLabel(op.module, product.assembly.modules),
        };
      },
    },
  },
  {
    id: "module.equalize-bays",
    title: "cmd.equalizeBays",
    keywords: ["igualar", "equidistante", "repartir", "vanos", "módulo"],
    mutates: true,
    apply: (ctx, args) => {
      const target = moduleTarget(ctx, args);
      return target && ctx.members
        ? equalizeModuleBays(ctx.product, target.id, ctx.members)
        : ctx.product;
    },
    describe: (args) => `${moduleLabel(args)}: igualar vanos`,
    ai: {
      op: "equalize_bays",
      decode: (op, product, state) => decodeModule(op, product, state),
    },
  },
  {
    id: "bay.set-size",
    title: "cmd.setBaySize",
    keywords: ["paño", "vano", "ancho", "alto", "medida", "redimensionar"],
    mutates: true,
    apply: (ctx, args) => {
      const target = bayTarget(ctx, args);
      if (!target || !args.mm || !ctx.members) return ctx.product;
      const mm = parseLocaleNumber(args.mm);
      if (mm === null) return ctx.product;
      const result = resizeModuleBay(
        ctx.product,
        target.module.id,
        target.node.id,
        mm,
        args.axis === "H" ? "H" : "V",
        ctx.members,
      );
      return typeof result === "string" ? ctx.product : result;
    },
    describe: (args) => `${moduleLabel(args)}: paño de ${args.mm ?? "?"} mm`,
    ai: {
      op: "set_bay_size",
      decode: (op, product, state) => {
        const mm = text(op.mm);
        if (!mm) return null;
        const decoded = decodeBay(op, product, state);
        if (!decoded) return null;
        decoded.mm = mm;
        if (text(op.axis) === "H") decoded.axis = "H";
        return decoded;
      },
    },
  },
  {
    id: "bay.flip-handing",
    title: "cmd.flipHanding",
    keywords: ["invertir", "espejo", "mano", "apertura", "derecha", "izquierda", "corredera"],
    mutates: true,
    apply: (ctx, args) => {
      const target = moduleTarget(ctx, args);
      if (!target) return ctx.product;
      if (args.bay) {
        return flipModuleBay(ctx.product, target.id, args.bay);
      }
      // Sin hoja: espejo sobre TODAS las hojas (paridad con el validador).
      return moduleNodes(ctx.product, target.id, "BAY").reduce(
        (next, bay) => flipModuleBay(next, target.id, bay.id),
        ctx.product,
      );
    },
    describe: (args) => `${moduleLabel(args)}: invertir apertura`,
    ai: {
      op: "flip_handing",
      decode: (op, product, state) => {
        if (op.bay !== undefined) return decodeBay(op, product, state);
        return decodeModule(op, product, state);
      },
    },
  },
  {
    id: "bay.set-handle-height",
    title: "cmd.setHandleHeight",
    keywords: ["manilla", "manija", "altura", "cremona"],
    mutates: true,
    apply: (ctx, args) => {
      const target = moduleTarget(ctx, args);
      if (!target || !args.mm) return ctx.product;
      const patch = { handle_height_mm: args.mm };
      if (args.bay) {
        return updateModuleBay(ctx.product, target.id, args.bay, patch);
      }
      return moduleNodes(ctx.product, target.id, "BAY").reduce(
        (next, bay) => updateModuleBay(next, target.id, bay.id, patch),
        ctx.product,
      );
    },
    describe: (args) => `${moduleLabel(args)}: manilla a ${args.mm ?? "?"} mm`,
    ai: {
      op: "set_handle_height",
      decode: (op, product, state) => {
        const mm = text(op.mm);
        if (!mm) return null;
        const decoded =
          op.bay !== undefined ? decodeBay(op, product, state) : decodeModule(op, product, state);
        if (!decoded) return null;
        decoded.mm = mm;
        return decoded;
      },
    },
  },
  {
    id: "module.set-sliding-layout",
    title: "cmd.setSlidingLayout",
    keywords: ["corredera", "hojas", "esquema", "2l", "3l", "4l"],
    mutates: true,
    apply: (ctx, args) => {
      const target = moduleTarget(ctx, args);
      if (!target) return ctx.product;
      const primary =
        args.primaryIndex !== undefined && args.primaryIndex !== ""
          ? Number(args.primaryIndex)
          : undefined;
      const apply = (product: ProductJson, bayId: string) =>
        setBaySlidingPreset(product, target.id, bayId, {
          preset: args.preset || undefined,
          primaryIndex: Number.isInteger(primary) ? primary : undefined,
        });
      if (args.bay) return apply(ctx.product, args.bay);
      return moduleNodes(ctx.product, target.id, "BAY").reduce(
        (next, bay) => apply(next, bay.id),
        ctx.product,
      );
    },
    describe: (args) => `${moduleLabel(args)}: corredera ${args.preset ?? ""}`.trim(),
    ai: {
      op: "set_sliding_layout",
      decode: (op, product, state) => {
        const preset = text(op.preset);
        const primary = op.primary_index;
        const extra: CommandArgs = {};
        if (preset) extra.preset = preset;
        if (primary !== undefined && primary !== null) extra.primaryIndex = String(primary);
        const decoded =
          op.bay !== undefined
            ? decodeBay(op, product, state, extra)
            : decodeModule(op, product, state, extra);
        return decoded;
      },
    },
  },
  {
    id: "bay.set-travel",
    title: "cmd.setTravel",
    keywords: ["corredera", "recorrido", "hoja", "dirección", "direccion", "movimiento"],
    mutates: true,
    apply: (ctx, args) => {
      const target = bayTarget(ctx, args);
      const slot = args.slot !== undefined ? Number(args.slot) : NaN;
      return target && Number.isInteger(slot) && args.kind
        ? setBayTravel(
            ctx.product,
            target.module.id,
            target.node.id,
            slot,
            args.kind === "MOVING" ? "MOVING" : "FIXED",
          )
        : ctx.product;
    },
    describe: (args) => `${moduleLabel(args)}: hoja ${args.slot ?? "?"} → ${args.kind ?? "?"}`,
    ai: {
      op: "set_travel",
      decode: (op, product, state) => {
        const kind = text(op.kind);
        const slot = op.slot;
        if (!kind || slot === undefined || slot === null) return null;
        return decodeBay(op, product, state, { kind, slot: String(slot) });
      },
    },
  },
  {
    id: "edit.undo",
    title: "cmd.undo",
    keywords: ["deshacer", "volver"],
    shortcut: "mod+z",
    mutates: true,
    applicable: (ctx) => ctx.canUndo === true,
    run: (ctx) => ctx.undo?.(),
  },
  {
    id: "edit.redo",
    title: "cmd.redo",
    keywords: ["rehacer", "adelante"],
    shortcut: ["mod+shift+z", "mod+y"],
    mutates: true,
    applicable: (ctx) => ctx.canRedo === true,
    run: (ctx) => ctx.redo?.(),
  },
  {
    id: "tool.select",
    title: "cmd.selectTool",
    keywords: ["seleccionar", "cursor", "herramienta"],
    shortcut: "v",
    run: (ctx) => ctx.setTool?.("select"),
  },
  {
    id: "tool.split-vertical",
    title: "cmd.splitVertical",
    keywords: ["dividir", "partir", "vertical", "montante", "mullion"],
    shortcut: "|",
    applicable: (ctx) => ctx.catalog.mullionSkus.SPLIT_V !== undefined,
    run: (ctx) => ctx.setTool?.("split_v"),
  },
  {
    id: "tool.split-horizontal",
    title: "cmd.splitHorizontal",
    keywords: ["dividir", "partir", "horizontal", "travesaño", "transom"],
    shortcut: "-",
    applicable: (ctx) => ctx.catalog.mullionSkus.SPLIT_H !== undefined,
    run: (ctx) => ctx.setTool?.("split_h"),
  },
  {
    id: "tool.opening",
    title: "cmd.openingTool",
    keywords: ["apertura", "abrir", "opening", "tipo de vano"],
    shortcut: "a",
    applicable: (ctx) => ctx.product !== null,
    run: (ctx) => ctx.setTool?.("opening"),
  },
  {
    id: "tool.glazing",
    title: "cmd.glazingTool",
    keywords: ["vidrio", "glass", "relleno", "composición", "composicion"],
    shortcut: "g",
    run: (ctx) => ctx.setTool?.("glazing"),
  },
  {
    id: "tool.measure",
    title: "cmd.measureTool",
    keywords: ["medir", "measure", "distancia", "cota", "regla"],
    shortcut: "m",
    run: (ctx) => ctx.setTool?.("measure"),
  },
  {
    id: "tool.couple",
    title: "cmd.coupleTool",
    keywords: ["acoplar", "couple", "unir", "módulos", "modulos", "ensamblar"],
    shortcut: "c",
    run: (ctx) => ctx.openCoupleMenu?.(),
  },
  {
    id: "tool.library",
    title: "cmd.library",
    keywords: ["tipologías", "tipologias", "biblioteca", "library", "plantillas", "starter"],
    shortcut: "b",
    run: (ctx) => ctx.toggleLibrary?.(),
  },
  {
    id: "view.fit",
    title: "cmd.fitView",
    keywords: ["ajustar", "fit", "centrar", "encuadrar", "zoom", "pantalla"],
    shortcut: "f",
    run: (ctx) => ctx.fitView?.(),
  },
  {
    id: "help.shortcuts",
    title: "cmd.shortcuts",
    keywords: ["atajos", "shortcuts", "teclado", "ayuda", "help", "keys"],
    shortcut: "?",
    run: (ctx) => ctx.showShortcuts?.(),
  },
  {
    id: "bay.opening-picker",
    title: "cmd.openingPicker",
    keywords: ["apertura", "selector", "vano", "opening", "tipo de vano", "cambiar"],
    applicable: (ctx) => ctx.openOpeningPicker !== undefined,
    run: (ctx) => ctx.openOpeningPicker?.(),
  },
];

/** UI affordance on the same registry: the palette row and context-menu entry
 * that open the design assistant. Non-mutating — `run` only moves focus. */
export const UI_ASK_ASSISTANT: CommandSpec = {
  id: "ui.ask-assistant",
  title: "cmd.askDekopen",
  keywords: ["ia", "ai", "asistente", "preguntar", "dekopen", "ayuda", "help"],
  run: (ctx) => ctx.focusAssistant?.(),
};

/** Commands the surface offers right now (selection/product-sensitive). */
export function assemblyCommands(ctx: CommandContext): CommandSpec[] {
  if (ctx.disabled) return [];
  const domain = ASSEMBLY_COMMANDS.filter((spec) => spec.applicable?.(ctx) ?? true);
  return ctx.focusAssistant ? [...domain, UI_ASK_ASSISTANT] : domain;
}
