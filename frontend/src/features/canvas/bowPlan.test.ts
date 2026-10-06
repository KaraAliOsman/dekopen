import { describe, expect, it } from "vitest";

import type { PlanGeometry } from "../../api/generated/models";
import { planMeasures, snapAngleDeg } from "./BowPlanSvg";

/** Bow simétrico 600/1200/600 @22,5° por junta: la cadena del frente parte
 * en (0,0) rumbo 0° y gira 22,5° en cada bisagra (convención del engine:
 * heading_i = Σ angle_deg de los coples anteriores). */
function symmetricBowPlan(): PlanGeometry {
  const side = 600;
  const center = 1200;
  const angle = (22.5 * Math.PI) / 180;
  const chain = [{ x: 0, y: 0 }];
  let x = 0;
  let y = 0;
  let heading = 0;
  for (const length of [side, center, side]) {
    x += length * Math.cos(heading);
    y += length * Math.sin(heading);
    chain.push({ x, y });
    heading += angle;
  }
  return {
    front_chain: chain.map((point) => ({ x_mm: String(point.x), y_mm: String(point.y) })),
    modules: [],
    couplings: [],
    min_x_mm: "0",
    min_y_mm: "0",
    width_mm: "0",
    height_mm: "0",
  };
}

describe("planMeasures", () => {
  it("desarrollado = suma de segmentos de la cadena", () => {
    const measures = planMeasures(symmetricBowPlan());
    expect(measures.developedMm).toBeCloseTo(2400, 5);
  });

  it("cuerda = distancia recta entre extremos de la cadena", () => {
    const measures = planMeasures(symmetricBowPlan());
    // bow simétrico: cuerda = centro + 2·lateral·cos(22,5°)
    expect(measures.chordMm).toBeCloseTo(1200 + 2 * 600 * Math.cos((22.5 * Math.PI) / 180), 4);
  });

  it("proyección = salida máxima de la cadena respecto a la cuerda", () => {
    const measures = planMeasures(symmetricBowPlan());
    // el tramo central queda paralelo a la cuerda a s·sin(22,5°) de ella
    expect(measures.projectionMm).toBeCloseTo(600 * Math.sin((22.5 * Math.PI) / 180), 4);
  });

  it("cadena plana: cuerda = desarrollado, proyección 0", () => {
    const measures = planMeasures({
      front_chain: [
        { x_mm: "0", y_mm: "0" },
        { x_mm: "500", y_mm: "0" },
        { x_mm: "1500", y_mm: "0" },
      ],
      modules: [],
      couplings: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "0",
      height_mm: "0",
    });
    expect(measures.developedMm).toBeCloseTo(1500, 5);
    expect(measures.chordMm).toBeCloseTo(1500, 5);
    expect(measures.projectionMm).toBeCloseTo(0, 5);
  });
});

describe("snapAngleDeg", () => {
  it("atrae a los imanes dentro de la tolerancia", () => {
    expect(snapAngleDeg(22.0)).toBe(22.5);
    expect(snapAngleDeg(-24.9)).toBe(-22.5);
    expect(snapAngleDeg(43.0)).toBe(45);
  });

  it("deja el valor libre fuera de la banda", () => {
    expect(snapAngleDeg(38)).toBe(38);
    expect(snapAngleDeg(-5)).toBe(-5);
    expect(snapAngleDeg(-7)).toBe(-10); // a 3° del imán −10 sí atrae
  });

  it("recorta al límite editorial ±90°", () => {
    expect(snapAngleDeg(120)).toBe(90);
    expect(snapAngleDeg(-120)).toBe(-90);
  });
});
