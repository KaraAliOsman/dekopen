import { describe, expect, it } from "vitest";

import type { GlassCompositionSpec, GlassLaminaSpec, GlassOptionsSpec } from "./intentEditing";
import {
  compositionErrors,
  compositionNetMm,
  compositionNotation,
  compositionTotalMm,
  defaultComposition,
  productSatisfiesSafety,
  retargetSurcharges,
} from "./glazing";
import type { GlassProductChoice } from "../../api/generated/models";

const lamina = (panes: number[], extra: Partial<GlassLaminaSpec> = {}): GlassLaminaSpec => ({
  type: "lamina",
  panes: panes.map(String),
  ...extra,
});

describe("composition totals", () => {
  it("sums lamina panes + interlayers + chambers for the total, panes for net", () => {
    const comp: GlassCompositionSpec = {
      layers: [lamina([4]), { type: "chamber", width_mm: "16", gas: "AIR" }, lamina([4])],
    };
    expect(compositionTotalMm(comp)).toBe(24);
    expect(compositionNetMm(comp)).toBe(8);
  });

  it("counts PVB thickness in net and total", () => {
    const comp: GlassCompositionSpec = {
      layers: [lamina([3, 3], { interlayer: "PVB_038" })],
    };
    expect(compositionTotalMm(comp)).toBeCloseTo(6.38);
    expect(compositionNetMm(comp)).toBeCloseTo(6.38);
  });

  it("treats a missing interlayer as zero", () => {
    const comp: GlassCompositionSpec = { layers: [lamina([3, 3])] };
    expect(compositionTotalMm(comp)).toBe(6);
  });
});

describe("compositionNotation", () => {
  it("formats a double-glazed stack like the engine", () => {
    const comp: GlassCompositionSpec = {
      layers: [
        lamina([5]),
        { type: "chamber", width_mm: "12", gas: "ARGON" },
        lamina([4], { coating: "LOW_E", coating_face: 3 }),
      ],
    };
    expect(compositionNotation(comp)).toBe("5 / 12 Ar / 4 Low-E (c3)");
  });

  it("formats laminated panes with the interlayer", () => {
    const comp: GlassCompositionSpec = { layers: [lamina([3, 3], { interlayer: "PVB_038" })] };
    expect(compositionNotation(comp)).toBe("3+3 PVB 0,38");
  });

  it("keeps warm-edge and sealant words on chambers", () => {
    const comp: GlassCompositionSpec = {
      layers: [
        lamina([4]),
        { type: "chamber", width_mm: "16", gas: "AIR", spacer: "WARM_EDGE", sealant: "PIB_BUTYL" },
        lamina([4]),
      ],
    };
    expect(compositionNotation(comp)).toBe("4 / 16 aire BC sellante butilo / 4");
  });
});

describe("compositionErrors", () => {
  it("rejects an empty composition", () => {
    expect(compositionErrors({ layers: [] })).toContain("assembly.glassErrEmpty");
  });

  it("rejects a chamber at the edge", () => {
    const comp: GlassCompositionSpec = {
      layers: [{ type: "chamber", width_mm: "12", gas: "AIR" }, lamina([4])],
    };
    expect(compositionErrors(comp)).toContain("assembly.glassErrEnds");
  });

  it("rejects two adjacent laminae", () => {
    const comp: GlassCompositionSpec = { layers: [lamina([4]), lamina([4])] };
    expect(compositionErrors(comp)).toContain("assembly.glassErrChamber");
  });

  it("rejects a laminate without interlayer", () => {
    const comp: GlassCompositionSpec = { layers: [lamina([3, 3])] };
    expect(compositionErrors(comp)).toContain("assembly.glassErrInterlayer");
  });

  it("accepts the default DVH", () => {
    expect(compositionErrors(defaultComposition())).toHaveLength(0);
  });
});

describe("defaultComposition", () => {
  it("produces pane / chamber / pane", () => {
    const comp = defaultComposition();
    expect(comp.layers.map((layer) => layer.type)).toEqual(["lamina", "chamber", "lamina"]);
    expect(compositionTotalMm(comp)).toBe(24);
  });
});

describe("productSatisfiesSafety", () => {
  const product = (composition: GlassCompositionSpec | null, safety_class: string | null = "B") =>
    ({
      composition,
      safety_class,
      sku: "X",
      name: "X",
      notation: null,
      total_thickness_mm: null,
      ug_w_m2k: null,
      g_value: null,
      light_transmission_pct: null,
      weight_kg_m2: null,
      min_billable_area_m2: null,
      price_tier: null,
      surcharges: [],
      review_pending: false,
    }) as GlassProductChoice;

  it("matches treatment and laminate requirements", () => {
    const tempered = product({
      layers: [lamina([5], { treatment: "TEMPERED" })],
    });
    expect(productSatisfiesSafety(tempered, "TEMPERED")).toBe(true);
    expect(productSatisfiesSafety(tempered, "SAFETY_GLASS")).toBe(true);
    expect(productSatisfiesSafety(tempered, "LAMINATED")).toBe(false);
    const laminated = product({
      layers: [lamina([3, 3], { interlayer: "PVB_038" })],
    });
    expect(productSatisfiesSafety(laminated, "LAMINATED")).toBe(true);
    expect(productSatisfiesSafety(laminated, "SAFETY_GLASS")).toBe(true);
  });

  it("falls back to declared safety class when composition is missing", () => {
    expect(productSatisfiesSafety(product(null, "A"), "SAFETY_CLASS_A")).toBe(true);
    expect(productSatisfiesSafety(product(null, "B"), "SAFETY_CLASS_A")).toBe(false);
    expect(productSatisfiesSafety(product(null, "C"), "SAFETY_CLASS_B")).toBe(false);
    expect(productSatisfiesSafety(product(null, "B"), "SAFETY_CLASS_B")).toBe(true);
    expect(productSatisfiesSafety(product(null, "A"), "SAFETY_GLASS")).toBe(true);
    expect(productSatisfiesSafety(product(null, null), "SAFETY_GLASS")).toBe(false);
  });
});

describe("retargetSurcharges", () => {
  const options = (kinds: string[]): GlassOptionsSpec => ({
    surcharges: kinds.map((kind) => {
      if (kind === "EDGE_POLISH") {
        return { kind, edges: ["top" as const] };
      }
      if (kind === "PALILLAJE") {
        return { kind, columns: 2, rows: 1 };
      }
      return { kind };
    }),
  });

  const product = (kinds: string[]) =>
    ({
      surcharges: kinds.map((kind) => ({
        kind,
        unit: "UNIT",
        amount: "1",
        currency: "CLP",
        label: null,
      })),
      sku: "X",
      name: "X",
      notation: null,
      composition: null,
      total_thickness_mm: null,
      ug_w_m2k: null,
      g_value: null,
      light_transmission_pct: null,
      weight_kg_m2: null,
      min_billable_area_m2: null,
      price_tier: null,
      review_pending: false,
    }) as GlassProductChoice;

  it("drops selections the new product does not price", () => {
    const next = retargetSurcharges(options(["EDGE_POLISH", "DRILL"]), product(["DRILL"]));
    expect(next?.surcharges?.map((sel) => sel.kind)).toEqual(["DRILL"]);
  });

  it("keeps only kinds the new product prices", () => {
    const kept = retargetSurcharges(options(["TEMPERED"]), product(["TEMPERED"]));
    expect(kept?.surcharges?.map((sel) => sel.kind)).toEqual(["TEMPERED"]);
    const dropped = retargetSurcharges(options(["PALILLAJE"]), product(["EDGE_POLISH"]));
    expect(dropped).toBeNull();
  });
});
