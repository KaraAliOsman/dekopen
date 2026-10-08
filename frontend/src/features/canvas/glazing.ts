/** D02 structured glazing — the TS mirror of `glass_composition.py`'s
 * serializable shape and canonical notation. The composer edits a
 * `GlassCompositionSpec` whose `layers` order is exterior → interior; the
 * engine stays the calculation authority (weight, cut, findings) — this
 * file only formats and validates the declared stack the picker hands to
 * the intent tree. */

import type {
  GlassCompositionSpec,
  GlassLaminaSpec,
  GlassOptionsSpec,
  GlassSurchargeSelectionSpec,
} from "./intentEditing";

export const LAMINA_THICKNESSES_MM = [3, 4, 5, 6, 8, 10, 12];
export const CHAMBER_WIDTHS_MM = [6, 9, 12, 15, 16, 20, 24];
export const INTERLAYERS = ["PVB_038", "PVB_076", "PVB_152", "PVB_ACOUSTIC"] as const;
export const TINTS = ["CLEAR", "BRONZE", "GREY", "GREEN"] as const;
export const TREATMENTS = ["TEMPERED", "HEAT_STRENGTHENED"] as const;
export const COATINGS = [
  "LOW_E",
  "SOLAR_CONTROL",
  "REFLECTIVE",
  "MIRROR",
  "SATIN",
  "PRINTED",
] as const;
export const CHAMBER_GASES = ["AIR", "ARGON"] as const;
export const SPACERS = ["ALUMINIUM", "WARM_EDGE"] as const;
export const SEALANTS = ["PIB_BUTYL", "POLYSULFIDE", "SILICONE", "POLYURETHANE"] as const;

const INTERLAYER_MM: Record<string, number> = {
  PVB_038: 0.38,
  PVB_076: 0.76,
  PVB_152: 1.52,
  PVB_ACOUSTIC: 0.76,
};

const INTERLAYER_NOTATION: Record<string, string> = {
  PVB_038: "PVB 0,38",
  PVB_076: "PVB 0,76",
  PVB_152: "PVB 1,52",
  PVB_ACOUSTIC: "PVB acústico",
};

const TINT_NOTATION: Record<string, string> = {
  BRONZE: " bronce",
  GREY: " gris",
  GREEN: " verde",
};

const TREATMENT_NOTATION: Record<string, string> = {
  TEMPERED: " templado",
  HEAT_STRENGTHENED: " termoendurecido",
};

const COATING_NOTATION: Record<string, string> = {
  LOW_E: " Low-E",
  SOLAR_CONTROL: " control solar",
  REFLECTIVE: " reflectivo",
  MIRROR: " espejo",
  SATIN: " satinado",
  PRINTED: " impreso",
};

const SEALANT_NOTATION: Record<string, string> = {
  PIB_BUTYL: "butilo",
  POLYSULFIDE: "tiokol",
  SILICONE: "silicona",
  POLYURETHANE: "poliuretano",
};

export function mmNumber(raw: string | null | undefined): number {
  const value = Number(String(raw ?? "").replace(",", "."));
  return Number.isFinite(value) ? value : 0;
}

export function fmtMmSpec(value: number): string {
  return Number.isInteger(value) ? String(value) : String(value).replace(".", ",");
}

function laminaMm(lamina: GlassLaminaSpec): number {
  const panes = lamina.panes.reduce((sum, pane) => sum + mmNumber(pane), 0);
  return panes + (lamina.interlayer ? (INTERLAYER_MM[lamina.interlayer] ?? 0) : 0);
}

/** Total package thickness (panes + interlayers + chambers), mm. */
export function compositionTotalMm(composition: GlassCompositionSpec | null | undefined): number {
  if (!composition) return 0;
  return composition.layers.reduce(
    (sum, layer) => sum + (layer.type === "lamina" ? laminaMm(layer) : mmNumber(layer.width_mm)),
    0,
  );
}

/** Net glass mass thickness — panes + interlayers, chambers excluded. */
export function compositionNetMm(composition: GlassCompositionSpec | null | undefined): number {
  if (!composition) return 0;
  return composition.layers.reduce(
    (sum, layer) => sum + (layer.type === "lamina" ? laminaMm(layer) : 0),
    0,
  );
}

/** Canonical notation — mirrors `format_glass_notation`: "4 / 16 Ar / 4
 * Low-E (c3)", "3+3 PVB 0,38 templado", "6 templado". */
export function compositionNotation(composition: GlassCompositionSpec): string {
  return composition.layers
    .map((layer) => {
      if (layer.type === "chamber") {
        const gas = layer.gas === "ARGON" ? "Ar" : "aire";
        const spacer = layer.spacer === "WARM_EDGE" ? " BC" : "";
        const sealant = layer.sealant ? ` sellante ${SEALANT_NOTATION[layer.sealant]}` : "";
        return `${fmtMmSpec(mmNumber(layer.width_mm))} ${gas}${spacer}${sealant}`;
      }
      let text = layer.panes.map((pane) => fmtMmSpec(mmNumber(pane))).join("+");
      if (layer.panes.length > 1 && layer.interlayer) {
        text += ` ${INTERLAYER_NOTATION[layer.interlayer] ?? layer.interlayer}`;
      }
      if (layer.tint && layer.tint !== "CLEAR") text += TINT_NOTATION[layer.tint] ?? "";
      if (layer.treatment) text += TREATMENT_NOTATION[layer.treatment] ?? "";
      if (layer.coating) {
        text += COATING_NOTATION[layer.coating] ?? "";
        if (layer.coating_face != null) text += ` (c${layer.coating_face})`;
      }
      return text;
    })
    .join(" / ");
}

/** Structure validation for the composer: lamina/chamber alternation,
 * chambers between laminae, positive dims. Returns i18n keys — the caller
 * renders them; this module stays free of UI copy. */
export function compositionErrors(composition: GlassCompositionSpec | null | undefined): string[] {
  const errors: string[] = [];
  const layers = composition?.layers ?? [];
  if (layers.length === 0) return ["assembly.glassErrEmpty"];
  if (layers[0]?.type !== "lamina" || layers[layers.length - 1]?.type !== "lamina") {
    errors.push("assembly.glassErrEnds");
  }
  layers.forEach((layer, index) => {
    if (layer.type === "lamina") {
      const panes = layer.panes ?? [];
      if (panes.length === 0 || panes.some((pane) => mmNumber(pane) <= 0)) {
        errors.push("assembly.glassErrPane");
      }
      if (panes.length > 1 && !layer.interlayer) {
        errors.push("assembly.glassErrInterlayer");
      }
      if (index > 0 && layers[index - 1]?.type !== "chamber") {
        errors.push("assembly.glassErrChamber");
      }
    } else if (mmNumber(layer.width_mm) <= 0) {
      errors.push("assembly.glassErrCavity");
    }
  });
  return errors;
}

/** A working DVH starter — 4·16·4 incoloro, the most common termopanel. */
export function defaultComposition(): GlassCompositionSpec {
  return {
    layers: [
      { type: "lamina", panes: ["4"], tint: "CLEAR" },
      { type: "chamber", width_mm: "16", gas: "AIR", spacer: "ALUMINIUM" },
      { type: "lamina", panes: ["4"], tint: "CLEAR" },
    ],
  };
}

/** Whether a declared product satisfies a safety rule's requirement —
 * reads the structured stack + declared class, never the name text. */
export function productSatisfiesSafety(
  product: {
    composition?: { layers?: unknown } | null;
    safety_class?: string | null;
  },
  required: string | null | undefined,
): boolean {
  if (!required) return true;
  const layers = Array.isArray(product.composition?.layers)
    ? (product.composition.layers as { type?: string; treatment?: string | null }[])
    : [];
  const tempered = layers.some(
    (layer) => layer.type === "lamina" && layer.treatment === "TEMPERED",
  );
  const laminated = layers.some(
    (layer) =>
      layer.type === "lamina" &&
      Array.isArray((layer as GlassLaminaSpec).panes) &&
      (layer as GlassLaminaSpec).panes.length > 1,
  );
  const safetyClass = product.safety_class ?? null;
  switch (required) {
    case "TEMPERED":
      return tempered;
    case "LAMINATED":
      return laminated;
    case "SAFETY_GLASS":
      return tempered || laminated || safetyClass !== null;
    case "SAFETY_CLASS_A":
      return safetyClass === "A";
    case "SAFETY_CLASS_B":
      return safetyClass === "A" || safetyClass === "B";
    case "SAFETY_CLASS_C":
      return safetyClass === "A" || safetyClass === "B" || safetyClass === "C";
    default:
      return false;
  }
}

/** Existing selections pruned to the kinds the newly-picked product
 * actually prices — a polish on a product that never declared a polish
 * rate is silently billable otherwise. */
export function retargetSurcharges(
  options: GlassOptionsSpec | null | undefined,
  product: { surcharges?: { kind: string }[] } | null | undefined,
): GlassOptionsSpec | null {
  const selections = options?.surcharges ?? [];
  if (selections.length === 0) return options ?? null;
  const supported = new Set((product?.surcharges ?? []).map((rate) => rate.kind));
  const kept = selections.filter((selection) => supported.has(selection.kind));
  return kept.length === 0 ? null : { ...options, surcharges: kept };
}

export function emptySelection(kind: string): GlassSurchargeSelectionSpec {
  if (kind === "EDGE_POLISH") return { kind, edges: [] };
  if (kind === "DRILL") return { kind, count: 1 };
  if (kind === "PALILLAJE") return { kind, columns: 2, rows: 2 };
  return { kind };
}
