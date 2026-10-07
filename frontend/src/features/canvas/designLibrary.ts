import type { TranslationKey } from "../../i18n/es-CL";
import type { IntentNode, LeafSpecPayload, Opening, OpeningSpecPayload } from "./intentEditing";
import { fmtWire } from "../../format";
import {
  makeArchModule,
  makeBowProduct,
  makeFramelessModule,
  makeTrapezoidModule,
  totalModuleWidth,
  wrapTreeAsProduct,
  type ProductJson,
} from "./productEditing";

function starterTree(opening: Opening): IntentNode {
  return { id: crypto.randomUUID(), type: "BAY", opening_type: opening };
}

/** Spec-form bay for the advanced typologies (D08): the legacy enum can't
 * express LIFT_SLIDE / FOLD / PIVOT / VERTICAL_SLIDE, so the recipe declares
 * the leaf spec the catalog capability row emits. */
function specTree(opening: OpeningSpecPayload, extra?: Partial<IntentNode>): IntentNode {
  return { id: crypto.randomUUID(), type: "BAY", opening, ...extra };
}

function leavesTree(leaves: LeafSpecPayload[], extra?: Partial<IntentNode>): IntentNode {
  return { id: crypto.randomUUID(), type: "BAY", leaves, ...extra };
}

export interface StarterDefinition {
  key: string;
  titleKey: TranslationKey;
  hintKey: TranslationKey;
  build(widthMm: number, heightMm: number): ProductJson;
}

/** Coupled pair of two independent bays joined by a coupler. */
function coupledModules(
  first: IntentNode,
  second: IntentNode,
  firstShare: number,
  widthMm: number,
  heightMm: number,
): ProductJson {
  return {
    version: "product-v2",
    assembly: {
      modules: [
        {
          id: crypto.randomUUID(),
          width_mm: fmtWire(widthMm * firstShare),
          height_mm: fmtWire(heightMm),
          tree: first,
        },
        {
          id: crypto.randomUUID(),
          width_mm: fmtWire(widthMm * (1 - firstShare)),
          height_mm: fmtWire(heightMm),
          tree: second,
        },
      ],
      couplings: [{ id: crypto.randomUUID(), angle_deg: "0.0", coupler_profile_sku: null }],
    },
  };
}

function splitBay(
  direction: "SPLIT_V" | "SPLIT_H",
  children: IntentNode[],
  widthMm: number,
  heightMm: number,
): ProductJson {
  return wrapTreeAsProduct(
    {
      id: crypto.randomUUID(),
      type: direction,
      split_offset_mm: direction === "SPLIT_V" ? fmtWire(widthMm / 2) : fmtWire(heightMm / 2),
      mullion_profile_sku: null,
      children,
    },
    fmtWire(widthMm),
    fmtWire(heightMm),
  );
}

/** Design library: creation recipes that produce a compositional product.
 * They are not product types — everything they build is editable on canvas. */
export const STARTER_DEFINITIONS: StarterDefinition[] = [
  {
    key: "fixed",
    titleKey: "assembly.starter.fixed",
    hintKey: "assembly.starter.fixedHint",
    build: (w, h) => wrapTreeAsProduct(starterTree("FIXED"), fmtWire(w), fmtWire(h)),
  },
  {
    key: "sash",
    titleKey: "assembly.starter.sash",
    hintKey: "assembly.starter.sashHint",
    build: (w, h) => wrapTreeAsProduct(starterTree("TILT_TURN_LEFT"), fmtWire(w), fmtWire(h)),
  },
  {
    key: "twoSash",
    titleKey: "assembly.starter.twoSash",
    hintKey: "assembly.starter.twoSashHint",
    build: (w, h) =>
      splitBay("SPLIT_V", [starterTree("TILT_TURN_LEFT"), starterTree("TILT_TURN_RIGHT")], w, h),
  },
  {
    key: "sliding2",
    titleKey: "assembly.starter.sliding2",
    hintKey: "assembly.starter.sliding2Hint",
    build: (w, h) => wrapTreeAsProduct(starterTree("SLIDING_2L"), fmtWire(w), fmtWire(h)),
  },
  {
    key: "sliding3",
    titleKey: "assembly.starter.sliding3",
    hintKey: "assembly.starter.sliding3Hint",
    build: (w, h) => wrapTreeAsProduct(starterTree("SLIDING_3L"), fmtWire(w), fmtWire(h)),
  },
  {
    key: "awning",
    titleKey: "assembly.starter.awning",
    hintKey: "assembly.starter.awningHint",
    build: (w, h) => wrapTreeAsProduct(starterTree("AWNING"), fmtWire(w), fmtWire(h)),
  },
  {
    key: "awningBand",
    titleKey: "assembly.starter.awningBand",
    hintKey: "assembly.starter.awningBandHint",
    build: (w, h) => splitBay("SPLIT_H", [starterTree("FIXED"), starterTree("AWNING")], w, h),
  },
  {
    key: "coupled",
    titleKey: "assembly.starter.coupled",
    hintKey: "assembly.starter.coupledHint",
    build: (w, h) => coupledModules(starterTree("TILT_TURN_LEFT"), starterTree("FIXED"), 0.5, w, h),
  },
  {
    key: "doorSide",
    titleKey: "assembly.starter.doorSide",
    hintKey: "assembly.starter.doorSideHint",
    build: (w, h) => coupledModules(starterTree("DOOR_ENTRY"), starterTree("FIXED"), 0.4, w, h),
  },
  {
    key: "slidingFixed",
    titleKey: "assembly.starter.slidingFixed",
    hintKey: "assembly.starter.slidingFixedHint",
    build: (w, h) => coupledModules(starterTree("SLIDING_2L"), starterTree("FIXED"), 0.55, w, h),
  },
  {
    key: "bow3",
    titleKey: "assembly.starter.bow3",
    hintKey: "assembly.starter.bow3Hint",
    // P06 — canonical bow: fixed center, tilt-turn laterals, 2 × 22,5°. The
    // e2e bar builds this design in ≤10 interactions from the library pick.
    build: (w, h) =>
      makeBowProduct({
        moduleCount: 3,
        widthMm: w,
        heightMm: h,
        angleDeg: 22.5,
        moduleOpenings: ["TILT_TURN_LEFT", "FIXED", "TILT_TURN_RIGHT"],
      }),
  },
  {
    key: "bay45",
    titleKey: "assembly.starter.bay45",
    hintKey: "assembly.starter.bay45Hint",
    build: (w, h) => makeBowProduct({ moduleCount: 3, widthMm: w, heightMm: h, angleDeg: 45 }),
  },
  {
    key: "corner90",
    titleKey: "assembly.starter.corner90",
    hintKey: "assembly.starter.corner90Hint",
    build: (w, h) => makeBowProduct({ moduleCount: 2, widthMm: w, heightMm: h, angleDeg: 90 }),
  },
  {
    key: "windowTransom",
    titleKey: "assembly.starter.windowTransom",
    hintKey: "assembly.starter.windowTransomHint",
    // Sobreluz: la división horizontal deja la ventana abajo (children[0])
    // y el fijo arriba (children[1]) — el motor compone un solo módulo.
    build: (w, h) =>
      splitBay("SPLIT_H", [starterTree("TILT_TURN_LEFT"), starterTree("FIXED")], w, h),
  },
  {
    key: "bow5",
    titleKey: "assembly.starter.bow5",
    hintKey: "assembly.starter.bow5Hint",
    build: (w, h) => makeBowProduct({ moduleCount: 5, widthMm: w, heightMm: h, angleDeg: 15 }),
  },
  {
    key: "trapezoid",
    titleKey: "assembly.starter.trapezoid",
    hintKey: "assembly.starter.trapezoidHint",
    build: (w, h) => ({
      version: "product-v2" as const,
      assembly: {
        modules: [
          makeTrapezoidModule(
            "m1",
            fmtWire(w),
            fmtWire(h),
            Math.round(w * 0.15),
            Math.round(w * 0.15),
            starterTree("FIXED"),
          ),
        ],
        couplings: [],
      },
    }),
  },
  {
    key: "arch",
    titleKey: "assembly.starter.arch",
    hintKey: "assembly.starter.archHint",
    build: (w, h) => ({
      version: "product-v2" as const,
      assembly: {
        modules: [
          makeArchModule("m1", fmtWire(w), fmtWire(h), Math.round(w * 0.2), starterTree("FIXED")),
        ],
        couplings: [],
      },
    }),
  },
  {
    key: "frameless",
    titleKey: "assembly.starter.frameless",
    hintKey: "assembly.starter.framelessHint",
    build: (w, h) => ({
      version: "product-v2" as const,
      assembly: {
        modules: [makeFramelessModule("m1", fmtWire(w), fmtWire(h), starterTree("FIXED"))],
        couplings: [],
      },
    }),
  },
  // -------------------------------------------------------------------
  // Tipologías avanzadas (D08) — spec bays; solo las ofrece la biblioteca
  // cuando la serie seleccionada declara la composición en opening_options.
  // -------------------------------------------------------------------
  {
    key: "hst",
    titleKey: "assembly.starter.hst",
    hintKey: "assembly.starter.hstHint",
    build: (w, h) =>
      wrapTreeAsProduct(specTree({ movement: "LIFT_SLIDE" }), fmtWire(w), fmtWire(h)),
  },
  {
    key: "psk",
    titleKey: "assembly.starter.psk",
    hintKey: "assembly.starter.pskHint",
    build: (w, h) =>
      wrapTreeAsProduct(specTree({ movement: "PARALLEL_SLIDE" }), fmtWire(w), fmtWire(h)),
  },
  {
    key: "foldable",
    titleKey: "assembly.starter.foldable",
    hintKey: "assembly.starter.foldableHint",
    // Plegable 3+0 hacia adentro con hoja de paso en la jamba izquierda —
    // la composición que el catálogo emite para una capacidad FOLD.
    build: (w, h) =>
      wrapTreeAsProduct(
        leavesTree([
          {
            slot: "L1",
            opening: {
              movement: "FOLD",
              hinge_side: "LEFT",
              direction: "INWARD",
              leaf_role: "ACTIVE",
            },
          },
          {
            slot: "L2",
            opening: {
              movement: "FOLD",
              hinge_side: "LEFT",
              direction: "INWARD",
              leaf_role: "PASSIVE",
            },
          },
          {
            slot: "L3",
            opening: {
              movement: "FOLD",
              hinge_side: "LEFT",
              direction: "INWARD",
              leaf_role: "PASSIVE",
            },
          },
        ]),
        fmtWire(w),
        fmtWire(h),
      ),
  },
  {
    key: "pivot",
    titleKey: "assembly.starter.pivot",
    hintKey: "assembly.starter.pivotHint",
    // Puerta pivotante de eje vertical — el eje desplazado se declara ahora
    // (la fabricación rechaza una hoja pivotante sin axis_offset_mm).
    build: (w, h) =>
      wrapTreeAsProduct(
        leavesTree(
          [
            {
              slot: "PRIMARY",
              opening: { movement: "PIVOT_V" },
              axis_offset_mm: Math.min(500, Math.round(w / 3)),
            },
          ],
          { unit_kind: "DOOR" },
        ),
        fmtWire(w),
        fmtWire(h),
      ),
  },
  {
    key: "guillotina",
    titleKey: "assembly.starter.guillotina",
    hintKey: "assembly.starter.guillotinaHint",
    // Guillotina simple: paño fijo arriba (TOP) y corredera vertical abajo.
    build: (w, h) =>
      wrapTreeAsProduct(
        leavesTree([
          { slot: "TOP", opening: { movement: "FIXED" } },
          { slot: "BOTTOM", opening: { movement: "VERTICAL_SLIDE" } },
        ]),
        fmtWire(w),
        fmtWire(h),
      ),
  },
  {
    key: "slidingDoor",
    titleKey: "assembly.starter.slidingDoor",
    hintKey: "assembly.starter.slidingDoorHint",
    // Puerta corredera: hoja SLIDE en unidad DOOR — umbral y cerradura de
    // patio los aporta el kit DOOR_SLIDING de la serie.
    build: (w, h) =>
      wrapTreeAsProduct(
        specTree({ movement: "SLIDE" }, { unit_kind: "DOOR" }),
        fmtWire(w),
        fmtWire(h),
      ),
  },
];

export type StarterKey = (typeof STARTER_DEFINITIONS)[number]["key"];

/** Nominal canvas the library cards preview at — templates render their own
 * proportions (bow reads wider, door reads taller). */
export function starterNominalSize(key: string): { widthMm: number; heightMm: number } {
  switch (key) {
    case "bow3":
      return { widthMm: 2400, heightMm: 1400 };
    case "bay45":
      return { widthMm: 2400, heightMm: 1400 };
    case "bow5":
      return { widthMm: 3000, heightMm: 1400 };
    case "corner90":
      return { widthMm: 2000, heightMm: 1500 };
    case "windowTransom":
      return { widthMm: 1200, heightMm: 2000 };
    case "doorSide":
      return { widthMm: 1600, heightMm: 2200 };
    case "trapezoid":
      return { widthMm: 2400, heightMm: 1400 };
    case "arch":
      return { widthMm: 1800, heightMm: 1600 };
    case "sliding2":
    case "slidingFixed":
      return { widthMm: 1800, heightMm: 1400 };
    case "sliding3":
      return { widthMm: 2400, heightMm: 1400 };
    case "awning":
    case "awningBand":
      return { widthMm: 1200, heightMm: 800 };
    case "twoSash":
      return { widthMm: 1400, heightMm: 1400 };
    case "hst":
      return { widthMm: 2000, heightMm: 2200 };
    case "psk":
      return { widthMm: 1400, heightMm: 1400 };
    case "foldable":
      return { widthMm: 2800, heightMm: 2400 };
    case "pivot":
      return { widthMm: 1200, heightMm: 2200 };
    case "guillotina":
      return { widthMm: 1200, heightMm: 1800 };
    case "slidingDoor":
      return { widthMm: 1800, heightMm: 2200 };
    default:
      return { widthMm: 1200, heightMm: 1400 };
  }
}

/** Size a new build inherits from whatever is already on canvas. */
export function starterContextSize(current: ProductJson | null): {
  widthMm: number;
  heightMm: number;
} {
  return {
    widthMm: current ? totalModuleWidth(current) : 1500,
    heightMm: current
      ? Math.max(...current.assembly.modules.map((module) => Number(module.height_mm)))
      : 1200,
  };
}
