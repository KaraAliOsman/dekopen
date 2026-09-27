import { create } from "zustand";
import type { AnnotationRequest, InspectorDiff } from "../../api/generated/models";
import type { SpecClipboard } from "../commands/types";
import { intentBays, walkIntent, type IntentNode } from "./intentEditing";
import type { ProductJson } from "./productEditing";

export type DimensionAxis = "width" | "height";

export type FixedParametricTree = {
  id: "g1";
  type: "BAY";
  opening_type: "FIXED";
  glass_thickness_mm: "4.00";
  glass_spec: "4 Float Incoloro";
};

export type CanvasDesignInputs = {
  systemId: string | null;
  nominalWidthMm: string;
  nominalHeightMm: string;
  /** Finish code — the series' declared finishes drive the picker; a stored
   * finish the catalog stopped offering still displays but can't save. */
  color: string;
  parametricTree: IntentNode;
  /** Compositional product (product-v2). null = classic single unit. */
  product: ProductJson | null;
};

const HISTORY_LIMIT = 100;

type DraftDimension = {
  axis: DimensionAxis;
  value: string;
} | null;

type ViewportState = {
  scale: number;
  offsetX: number;
  offsetY: number;
};

type CanvasState = {
  annotations: AnnotationRequest[];
  previewDiff: InspectorDiff | null;
  setAnnotations(annotations: AnnotationRequest[]): void;
  setPreviewDiff(diff: InspectorDiff | null): void;
  inputs: CanvasDesignInputs;
  draftDimension: DraftDimension;
  selection: string;
  selectBay(id: string): void;
  /** Direct-manipulation selection: module, coupling, or null to clear. */
  select(id: string | null): void;
  loadDesign(inputs: CanvasDesignInputs): void;
  acceptIntent(expected: CanvasDesignInputs, next: CanvasDesignInputs, selection: string): boolean;
  /** Typed design commands: record history, then apply. */
  commitInputs(next: CanvasDesignInputs): void;
  /** Deterministic normalization: swap inputs without an undo step. */
  replaceInputs(next: CanvasDesignInputs): void;
  past: CanvasDesignInputs[];
  future: CanvasDesignInputs[];
  undo(): void;
  redo(): void;
  viewport: ViewportState;
  snapEnabled: boolean;
  /** Spec clipboard for copiar/aplicar especificación (§04-G). */
  specClipboard: SpecClipboard | null;
  /** Recently used glass skus (most recent first, max 3) — quick chips in
   * the bay inspector for people designing dozens of windows. */
  recentGlass: string[];
  /** Pinned glass skus — a user preference persisted to localStorage, never
   * part of the product model. */
  favoriteGlass: string[];
  /** Last mutating command run through the registry — powers edit.repeat. */
  lastMutation: { specId: string; args: Record<string, string> } | null;
  setSpecClipboard(clipboard: SpecClipboard | null): void;
  pushRecentGlass(sku: string): void;
  toggleFavoriteGlass(sku: string): void;
  recordMutation(specId: string, args: Record<string, string>): void;
  setSystemId(systemId: string): void;
  setDraftDimension(draft: DraftDimension): void;
  acceptDimension(axis: DimensionAxis, value: string): void;
  setViewport(viewport: ViewportState): void;
  toggleSnap(): void;
  reset(): void;
};

const G1_TREE: FixedParametricTree = Object.freeze({
  id: "g1",
  type: "BAY",
  opening_type: "FIXED",
  glass_thickness_mm: "4.00",
  glass_spec: "4 Float Incoloro",
});

function initialInputs(): CanvasDesignInputs {
  return {
    systemId: null,
    nominalWidthMm: "1000.00",
    nominalHeightMm: "1000.00",
    color: "WHITE",
    parametricTree: G1_TREE,
    product: null,
  };
}

const INITIAL_VIEWPORT: ViewportState = {
  scale: 1,
  offsetX: 0,
  offsetY: 0,
};

const FAVORITE_GLASS_KEY = "dekopen:favorite-glass";

function loadFavoriteGlass(): string[] {
  try {
    const raw = localStorage.getItem(FAVORITE_GLASS_KEY);
    const parsed: unknown = raw === null ? [] : JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string").slice(0, 8)
      : [];
  } catch {
    return [];
  }
}

function persistFavoriteGlass(favorites: string[]): void {
  try {
    localStorage.setItem(FAVORITE_GLASS_KEY, JSON.stringify(favorites));
  } catch {
    // Storage unavailable — favorites stay in memory for this session.
  }
}

function selectionResolves(inputs: CanvasDesignInputs, id: string): boolean {
  const product = inputs.product;
  // Bay selections carry a composite `moduleId/bayId` — the tree only knows
  // the bay id on its own, so resolve the pair against the owning module.
  const separator = id.indexOf("/");
  const moduleId = separator === -1 ? "" : id.slice(0, separator);
  const bayId = separator === -1 ? id : id.slice(separator + 1);
  if (product !== null) {
    if (product.assembly.modules.some((m) => m.id === id)) return true;
    if (product.assembly.couplings.some((c) => c.id === id)) return true;
    // Composite "moduleId/nodeId" selects any tree node — a bay OR a split
    // (mullion/transom are selectable objects, not only leaf bays).
    return product.assembly.modules.some(
      (m) =>
        (moduleId === "" || m.id === moduleId) &&
        walkIntent(m.tree).some((node) => node.id === bayId),
    );
  }
  return moduleId === "" && intentBays(inputs.parametricTree).some((bay) => bay.id === id);
}

/** Selection is outside history but must always resolve against the
 * restored inputs — keep it when it does, else land on the first module
 * or bay so the inspector never points at a gone object. */
function reconciledSelection(inputs: CanvasDesignInputs, current: string): string {
  if (current && selectionResolves(inputs, current)) return current;
  if (inputs.product !== null) return inputs.product.assembly.modules[0]?.id ?? "";
  return intentBays(inputs.parametricTree)[0]?.id ?? "";
}

export const useCanvasStore = create<CanvasState>((set) => ({
  annotations: [],
  previewDiff: null,
  setAnnotations(annotations) {
    set({ annotations, previewDiff: null });
  },
  setPreviewDiff(previewDiff) {
    set({ previewDiff });
  },
  inputs: initialInputs(),
  draftDimension: null,
  selection: "g1",
  selectBay(id) {
    set((state) => {
      if (
        state.inputs.product !== null &&
        state.inputs.product.assembly.modules.some((m) => m.id === id)
      )
        return { selection: id };
      return intentBays(state.inputs.parametricTree).some((bay) => bay.id === id)
        ? { selection: id }
        : state;
    });
  },
  select(id) {
    set((state) => {
      if (id === null) return { selection: "" };
      return selectionResolves(state.inputs, id) ? { selection: id } : state;
    });
  },
  loadDesign(inputs) {
    set({
      inputs,
      selection:
        inputs.product !== null
          ? (inputs.product.assembly.modules[0]?.id ?? "")
          : (intentBays(inputs.parametricTree)[0]?.id ?? ""),
      annotations: [],
      previewDiff: null,
      draftDimension: null,
      viewport: INITIAL_VIEWPORT,
      past: [],
      future: [],
    });
  },
  acceptIntent(expected, next, selection) {
    let accepted = false;
    set((state) => {
      if (
        state.inputs !== expected ||
        !intentBays(next.parametricTree).some((bay) => bay.id === selection)
      )
        return state;
      accepted = true;
      return {
        inputs: next,
        selection,
        draftDimension: null,
        previewDiff: null,
        past: [...state.past.slice(-(HISTORY_LIMIT - 1)), state.inputs],
        future: [],
      };
    });
    return accepted;
  },
  commitInputs(next) {
    set((state) => ({
      inputs: next,
      past: [...state.past.slice(-(HISTORY_LIMIT - 1)), state.inputs],
      future: [],
      draftDimension: null,
      previewDiff: null,
    }));
  },
  replaceInputs(next) {
    set(() => ({
      inputs: next,
      draftDimension: null,
      previewDiff: null,
    }));
  },
  past: [],
  future: [],
  undo() {
    set((state) => {
      const previous = state.past[state.past.length - 1];
      if (previous === undefined) return state;
      return {
        inputs: previous,
        selection: reconciledSelection(previous, state.selection),
        past: state.past.slice(0, -1),
        future: [...state.future, state.inputs],
        draftDimension: null,
      };
    });
  },
  redo() {
    set((state) => {
      const next = state.future[state.future.length - 1];
      if (next === undefined) return state;
      return {
        inputs: next,
        selection: reconciledSelection(next, state.selection),
        past: [...state.past, state.inputs],
        future: state.future.slice(0, -1),
        draftDimension: null,
      };
    });
  },
  viewport: INITIAL_VIEWPORT,
  snapEnabled: true,
  specClipboard: null,
  recentGlass: [],
  favoriteGlass: loadFavoriteGlass(),
  lastMutation: null,
  setSpecClipboard(specClipboard) {
    set({ specClipboard });
  },
  pushRecentGlass(sku) {
    set((state) => ({
      recentGlass: [sku, ...state.recentGlass.filter((item) => item !== sku)].slice(0, 3),
    }));
  },
  toggleFavoriteGlass(sku) {
    set((state) => {
      const favoriteGlass = state.favoriteGlass.includes(sku)
        ? state.favoriteGlass.filter((item) => item !== sku)
        : [...state.favoriteGlass, sku].slice(-8);
      persistFavoriteGlass(favoriteGlass);
      return { favoriteGlass };
    });
  },
  recordMutation(specId, args) {
    set({ lastMutation: { specId, args } });
  },
  setSystemId(systemId) {
    set((state) => ({ inputs: { ...state.inputs, systemId } }));
  },
  setDraftDimension(draftDimension) {
    set({ draftDimension });
  },
  acceptDimension(axis, value) {
    set((state) => ({
      inputs: {
        ...state.inputs,
        ...(axis === "width" ? { nominalWidthMm: value } : { nominalHeightMm: value }),
      },
      past: [...state.past.slice(-(HISTORY_LIMIT - 1)), state.inputs],
      future: [],
      draftDimension: null,
    }));
  },
  setViewport(viewport) {
    set({ viewport });
  },
  toggleSnap() {
    set((state) => ({ snapEnabled: !state.snapEnabled }));
  },
  reset() {
    set({
      annotations: [],
      previewDiff: null,
      inputs: initialInputs(),
      draftDimension: null,
      selection: "g1",
      viewport: INITIAL_VIEWPORT,
      snapEnabled: true,
      specClipboard: null,
      recentGlass: [],
      lastMutation: null,
      past: [],
      future: [],
    });
  },
}));
