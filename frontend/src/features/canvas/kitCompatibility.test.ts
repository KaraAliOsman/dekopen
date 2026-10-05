import { describe, expect, it } from "vitest";

import type { KitChoice } from "../../api/generated/models";
import type { IntentNode } from "./intentEditing";
import { bayEnvelopeMm, evaluateKitChoice, rankKits, resolveComponent } from "./kitCompatibility";

function kit(partial: Partial<KitChoice> & { sku: string }): KitChoice {
  return {
    name: partial.sku,
    opening_type: "TURN", // eslint-disable-line
    min_leaf_width_mm: "400",
    max_leaf_width_mm: "1600",
    min_leaf_height_mm: "400",
    max_leaf_height_mm: "2400",
    max_leaf_weight_kg: "120",
    weight_kg: null,
    class_label: null,
    max_aspect_ratio: null,
    min_stay_height_mm: null,
    contents: [],
    ...partial,
  };
}

const TURN = { opening: "TURN_LEFT", leafWidthMm: 800, leafHeightMm: 1400, leafWeightKg: 30 };

describe("evaluateKitChoice", () => {
  it("marks a fitting kit compatible", () => {
    expect(evaluateKitChoice(kit({ sku: "K1" }), TURN).fit).toBe("compatible");
  });

  it("rejects opening mismatch — TILT_TURN kit does not fit TURN bay", () => {
    const result = evaluateKitChoice(kit({ sku: "K2", opening_type: "TILT_TURN" }), TURN);
    expect(result.fit).toBe("incompatible");
    expect(result.reasons).toContain("opening");
  });

  it("normalizes family openings — TILT_TURN_L matches TILT_TURN kit", () => {
    const result = evaluateKitChoice(kit({ sku: "K3", opening_type: "TILT_TURN" }), {
      ...TURN,
      opening: "TILT_TURN_LEFT",
    });
    expect(result.fit).toBe("compatible");
  });

  it("rejects on envelope axes independently", () => {
    const narrow = evaluateKitChoice(kit({ sku: "K4" }), { ...TURN, leafWidthMm: 200 });
    expect(narrow.reasons).toEqual(["width"]);
    const tall = evaluateKitChoice(kit({ sku: "K5" }), { ...TURN, leafHeightMm: 3000 });
    expect(tall.reasons).toEqual(["height"]);
  });

  it("weight unknown → undecidable when it is the sole blocker", () => {
    const result = evaluateKitChoice(kit({ sku: "K6" }), { ...TURN, leafWeightKg: null });
    expect(result.fit).toBe("undecidable");
    expect(result.reasons).toEqual(["weight_unknown"]);
  });

  it("overweight leaf → incompatible", () => {
    const result = evaluateKitChoice(kit({ sku: "K7", weight_kg: "1.5" }), {
      ...TURN,
      leafWeightKg: 200,
    });
    expect(result.fit).toBe("incompatible");
    expect(result.reasons).toContain("overweight");
  });

  it("rankKits orders compatible → undecidable → incompatible", () => {
    const kits = [
      kit({ sku: "BAD", opening_type: "SLIDING" }),
      kit({ sku: "MAYBE", max_leaf_weight_kg: "10" }),
      kit({ sku: "GOOD" }),
    ];
    const ranked = rankKits(kits, { ...TURN, leafWeightKg: null });
    expect(ranked.map((r) => r.kit.sku)).toEqual(["GOOD", "MAYBE", "BAD"]);
  });
});

describe("bayEnvelopeMm", () => {
  const tree: IntentNode = {
    id: "r",
    type: "ROOT",
    children: [
      {
        id: "s",
        type: "SPLIT_V",
        split_offset_mm: "900",
        children: [
          { id: "b1", type: "BAY", opening_type: "TURN_LEFT" },
          { id: "b2", type: "BAY", opening_type: "FIXED" },
        ],
      },
    ],
  };

  it("returns the bay's share of a split, less the mullion", () => {
    const env = bayEnvelopeMm(tree, "b1", 1800, 1500, { vertical: 60, horizontal: 40 });
    expect(env).toEqual({ w: 870, h: 1500 });
  });

  it("halves evenly when no offset is declared", () => {
    const noOffset: IntentNode = {
      id: "r",
      type: "ROOT",
      children: [
        {
          id: "s",
          type: "SPLIT_H",
          children: [
            { id: "top", type: "BAY" },
            { id: "bot", type: "BAY" },
          ],
        },
      ],
    };
    const env = bayEnvelopeMm(noOffset, "bot", 1200, 1400, { vertical: 60, horizontal: 40 });
    expect(env).toEqual({ w: 1200, h: 680 });
  });

  it("returns null for a missing bay", () => {
    expect(bayEnvelopeMm(tree, "nope", 1800, 1500, { vertical: 60, horizontal: 40 })).toBeNull();
  });
});

describe("resolveComponent", () => {
  const ctx = { leafWidthMm: 1400, leafHeightMm: 1500 };

  it("resolves cut length from API-serialized string minus_mm", () => {
    const component = {
      sku: "DEMO-TT-CREM-70",
      name: "Transmisión cremona demo 70",
      qty: "1",
      unit: "unit",
      category: "LOCK",
      cut_rule: { axis: "HEIGHT", minus_mm: "60" },
    } as KitChoice["contents"][number];
    const resolved = resolveComponent(component, ctx);
    expect(resolved.lengthMm).toBe(1440);
    expect(resolved.qty).toBe(1);
  });

  it("resolves per-height qty rules from string fields", () => {
    const component = {
      sku: "DEMO-TT-CIERRE-70",
      name: "Punto de cierre demo 70",
      qty: null,
      unit: "unit",
      category: "LOCK",
      qty_rule: { axis: "HEIGHT", per_mm: "500", min_qty: "2", max_qty: "6" },
    } as KitChoice["contents"][number];
    const resolved = resolveComponent(component, ctx);
    expect(resolved.qty).toBe(3); // ceil(1500 / 500)
    expect(resolved.lengthMm).toBeNull();
  });
});
