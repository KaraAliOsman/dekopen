import { describe, expect, it } from "vitest";

import type { ProductJson } from "./productEditing";
import { elevationEnvelopeMm, makeBowProduct, wrapTreeAsProduct } from "./productEditing";
import { frontLayout } from "./ProductFrontSvg";

function doorWithTransom(transomWidthMm = 900): ProductJson {
  const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 2100, angleDeg: 0 });
  const door = base.assembly.modules[0]!;
  const transom = wrapTreeAsProduct(
    makeBowProduct({ moduleCount: 1, widthMm: transomWidthMm, heightMm: 400, angleDeg: 0 }).assembly
      .modules[0]!.tree,
    transomWidthMm.toFixed(2),
    "400.00",
  ).assembly.modules[0]!;
  return {
    ...base,
    assembly: {
      modules: [door, { ...transom, id: "t1" }],
      couplings: [
        {
          id: "c1",
          modules: [door.id, "t1"],
          edges: ["top", "bottom"],
          kind: "STACKED",
          coupler_profile_sku: null,
          angle_deg: "0.00",
        },
      ],
    },
  } as ProductJson;
}

describe("frontLayout", () => {
  it("lays flat modules left-to-right like before", () => {
    const layout = frontLayout(
      makeBowProduct({ moduleCount: 3, widthMm: 2100, heightMm: 1400, angleDeg: 15 }),
    );
    expect(layout.rects.map((r) => r.x)).toEqual([0, 700, 1400]);
    expect(layout.rects.map((r) => r.sill)).toEqual([0, 0, 0]);
    expect(layout.columns).toHaveLength(3);
    expect(layout.totalW).toBeCloseTo(2100, 5);
    expect(layout.height).toBeCloseTo(1400, 5);
    // two column seams, no stack joints
    expect(layout.joints.filter((j) => j.kind === "column")).toHaveLength(2);
    expect(layout.joints.filter((j) => j.kind === "stack")).toHaveLength(0);
  });

  it("stacks a member over its parent in the same column", () => {
    const layout = frontLayout(doorWithTransom());
    expect(layout.columns).toHaveLength(1);
    expect(layout.totalW).toBeCloseTo(900, 5);
    expect(layout.height).toBeCloseTo(2500, 5);
    const transom = layout.rects.find((r) => r.module.id === "t1")!;
    expect(transom.x).toBeCloseTo(0, 5);
    expect(transom.sill).toBeCloseTo(2100, 5);
    expect(transom.h).toBeCloseTo(400, 5);
    // a horizontal stack joint sits on the member's sill line
    const stack = layout.joints.find((j) => j.kind === "stack")!;
    expect(stack.x).toBeCloseTo(0, 5);
    expect(stack.y).toBeCloseTo(2100, 5);
    expect(stack.w).toBeCloseTo(900, 5);
    expect(layout.joints.filter((j) => j.kind === "column")).toHaveLength(0);
  });

  it("centres a narrower stacked member inside its column", () => {
    const layout = frontLayout(doorWithTransom(600));
    const transom = layout.rects.find((r) => r.module.id === "t1")!;
    expect(transom.x).toBeCloseTo(150, 5);
    const stack = layout.joints.find((j) => j.kind === "stack")!;
    expect(stack.x).toBeCloseTo(150, 5);
    expect(stack.w).toBeCloseTo(600, 5);
  });

  it("keeps a stack inside its own column when neighbours exist", () => {
    const base = makeBowProduct({ moduleCount: 2, widthMm: 1400, heightMm: 1400, angleDeg: 0 });
    const [a, b] = base.assembly.modules;
    const transom = {
      ...wrapTreeAsProduct(
        makeBowProduct({ moduleCount: 1, widthMm: 700, heightMm: 300, angleDeg: 0 }).assembly
          .modules[0]!.tree,
        "700.00",
        "300.00",
      ).assembly.modules[0]!,
      id: "t2",
    };
    const product = {
      ...base,
      assembly: {
        modules: [a!, b!, transom],
        couplings: [
          base.assembly.couplings[0]!,
          {
            id: "cs",
            modules: [b!.id, "t2"],
            edges: ["top", "bottom"],
            kind: "STACKED",
            coupler_profile_sku: null,
            angle_deg: "0.00",
          },
        ],
      },
    } as ProductJson;
    const layout = frontLayout(product);
    expect(layout.columns).toHaveLength(2);
    const member = layout.rects.find((r) => r.module.id === "t2")!;
    expect(member.x).toBeCloseTo(700, 5);
    expect(member.sill).toBeCloseTo(1400, 5);
    expect(layout.height).toBeCloseTo(1700, 5);
    const seam = layout.joints.find((j) => j.kind === "column")!;
    expect(seam.x).toBeCloseTo(700, 5);
    // column top is the taller column's own top — the seam stops at the
    // shorter column's top, not the elevation top.
    expect(seam.top).toBeCloseTo(1400, 5);
  });

  it("widens layout and envelope for a stacked member wider than its column", () => {
    // Mirror of the engine's elevation_envelope: a 1200 transom on a 900 door
    // centres and protrudes, so bounds span member extent — 1200, not 900.
    const product = doorWithTransom(1200);
    const layout = frontLayout(product);
    expect(layout.totalW).toBeCloseTo(1200, 5);
    const transom = layout.rects.find((r) => r.module.id === "t1")!;
    expect(transom.x).toBeCloseTo(0, 5);
    const door = layout.rects.find((r) => r.module.id !== "t1")!;
    expect(door.x).toBeCloseTo(150, 5);
    const envelope = elevationEnvelopeMm(product);
    expect(envelope.width).toBeCloseTo(1200, 5);
    expect(envelope.height).toBeCloseTo(2500, 5);
  });
});

describe("frontLayout proyectada (P06)", () => {
  it("escorza las alas con w·cos(rumbo) acumulado", () => {
    const product = makeBowProduct({
      moduleCount: 3,
      widthMm: 2400,
      heightMm: 1400,
      angleDeg: 22.5,
    });
    const flat = frontLayout(product);
    const projected = frontLayout(product, { projected: true });
    // rumbo_i = Σ ángulos previos: 0°, 22,5°, 45°
    const cos = (deg: number) => Math.cos((deg * Math.PI) / 180);
    expect(flat.rects.map((r) => r.w)).toEqual([800, 800, 800]);
    expect(projected.rects[0]!.w).toBeCloseTo(800 * cos(0), 4);
    expect(projected.rects[1]!.w).toBeCloseTo(800 * cos(22.5), 4);
    expect(projected.rects[2]!.w).toBeCloseTo(800 * cos(45), 4);
    expect(projected.totalW).toBeCloseTo(800 * (cos(0) + cos(22.5) + cos(45)), 4);
    // la proyección nunca ensancha el frente
    expect(projected.totalW).toBeLessThan(flat.totalW);
  });

  it("un acoplado plano no cambia al proyectar", () => {
    const product = makeBowProduct({
      moduleCount: 2,
      widthMm: 1600,
      heightMm: 1400,
      angleDeg: 0,
    });
    const projected = frontLayout(product, { projected: true });
    expect(projected.totalW).toBeCloseTo(1600, 5);
  });

  it("un rumbo > 90° (módulo plegado) proyecta ancho aparente, nunca negativo", () => {
    // c1 = 90° filo: el ala se pone de canto y casi desaparece de frente;
    // c2 = 90°: el tercer módulo queda a 180°, replegado — su ancho aparente
    // vuelve a ser pleno (la planta es la vista autoritativa del sentido).
    const product = makeBowProduct({
      moduleCount: 3,
      widthMm: 2400,
      heightMm: 1400,
      angleDeg: 90,
    });
    const projected = frontLayout(product, { projected: true });
    for (const rect of projected.rects) {
      expect(rect.w).toBeGreaterThanOrEqual(0);
      expect(Number.isFinite(rect.w)).toBe(true);
    }
    expect(projected.rects[1]!.w).toBeLessThan(0.01);
    expect(projected.rects[2]!.w).toBeCloseTo(800, 5);
    expect(Number.isFinite(projected.totalW)).toBe(true);
    expect(projected.totalW).toBeGreaterThan(0);
  });
});
