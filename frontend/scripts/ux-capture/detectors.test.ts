import { describe, expect, it } from "vitest";

import {
  contrastOf,
  isRadiusOffScale,
  isShadowOffScale,
  scanStyles,
  scanText,
  type BoxProbe,
} from "./detectors.ts";

const box = (over: Partial<BoxProbe>): BoxProbe => ({
  label: "div · prueba",
  fontPx: 12,
  widthPx: 100,
  heightPx: 32,
  interactive: false,
  ...over,
});

describe("scanText — emoji y exclamaciones", () => {
  it("flaggea emoji en texto visible", () => {
    expect(scanText("Guardado 🎉").map((f) => f.kind)).toContain("emoji");
  });
  it("no flaggea texto plano", () => {
    expect(scanText("Guardado correctamente").map((f) => f.kind)).not.toContain("emoji");
  });
  it("flaggea ¡…! en texto visible", () => {
    const kinds = scanText("¡Guardado!").map((f) => f.kind);
    expect(kinds).toContain("exclamation");
  });
  it("no flaggea voz imperativa plana", () => {
    expect(scanText("Revisa los datos.").map((f) => f.kind)).not.toContain("exclamation");
  });
});

describe("isRadiusOffScale", () => {
  it("flaggea 12px en un panel", () => {
    expect(isRadiusOffScale(box({ radiusPx: 12, widthPx: 200, heightPx: 100 }))).toBe(true);
  });
  it("permite ≤4px", () => {
    expect(isRadiusOffScale(box({ radiusPx: 4 }))).toBe(false);
  });
  it("permite pastilla real (radio = mitad de la altura)", () => {
    expect(isRadiusOffScale(box({ radiusPx: 10, widthPx: 60, heightPx: 20 }))).toBe(false);
  });
});

describe("isShadowOffScale", () => {
  it("flaggea sombra improvisada", () => {
    expect(isShadowOffScale(box({ shadow: "rgba(0, 0, 0, 0.3) 0px 8px 24px 0px" }))).toBe(true);
  });
  it("permite none", () => {
    expect(isShadowOffScale(box({ shadow: "none" }))).toBe(false);
  });
  it("permite --shadow-e2 resuelto", () => {
    expect(
      isShadowOffScale(
        box({
          shadow: "rgba(22, 28, 31, 0.05) 0px 1px 2px 0px, rgba(22, 28, 31, 0.08) 0px 4px 12px 0px",
        }),
      ),
    ).toBe(false);
  });
  it("permite anillo de foco (spread sin offset)", () => {
    expect(
      isShadowOffScale(
        box({
          shadow: "rgb(27, 87, 79) 0px 0px 0px 2px, rgba(27, 87, 79, 0.5) 0px 0px 0px 4px",
        }),
      ),
    ).toBe(false);
  });
});

describe("contrastOf", () => {
  it("negro sobre blanco es 21", () => {
    const ratio = contrastOf("rgb(0, 0, 0)", "rgb(255, 255, 255)");
    expect(ratio).not.toBeNull();
    expect(ratio!).toBeGreaterThan(20.9);
  });
  it("rechaza colores ilegibles", () => {
    expect(contrastOf("rgb(200, 200, 200)", "rgb(255, 255, 255)")).toBeLessThan(2);
  });
  it("devuelve null ante formato desconocido", () => {
    expect(contrastOf("red", "rgb(0,0,0)")).toBeNull();
  });
});

describe("scanStyles", () => {
  it("flaggea >1 primaria por región", () => {
    const findings = scanStyles([
      box({ region: "header", primary: true, label: "a" }),
      box({ region: "header", primary: true, label: "b" }),
    ]);
    expect(findings.map((f) => f.kind)).toContain("primary-multi");
  });
  it("una primaria por región pasa", () => {
    const findings = scanStyles([box({ region: "header", primary: true })]);
    expect(findings).toHaveLength(0);
  });
  it("flaggea degradado y blur", () => {
    const kinds = scanStyles([box({ gradient: true }), box({ blur: true })]).map((f) => f.kind);
    expect(kinds).toContain("gradient");
    expect(kinds).toContain("blur");
  });
  it("flaggea objetivo pequeño en taller", () => {
    const findings = scanStyles([
      box({ workshop: true, interactive: true, widthPx: 30, heightPx: 30 }),
    ]);
    expect(findings.map((f) => f.kind)).toContain("touch-too-small");
  });
  it("no flaggea objetivo pequeño fuera de taller", () => {
    const findings = scanStyles([
      box({ workshop: false, interactive: true, widthPx: 30, heightPx: 30 }),
    ]);
    expect(findings).toHaveLength(0);
  });
  it("flaggea cursor pointer sin semántica interactiva", () => {
    const findings = scanStyles([box({ cursorPointer: true, interactive: false })]);
    expect(findings.map((f) => f.kind)).toContain("bare-interactive");
  });
  it("un button con pointer no dispara bare-interactive", () => {
    const findings = scanStyles([box({ cursorPointer: true, interactive: true })]);
    expect(findings).toHaveLength(0);
  });
  it("flaggea contraste < 4.5 en texto", () => {
    const findings = scanStyles([
      box({
        text: "hola",
        color: "rgb(210, 210, 210)",
        bgColor: "rgb(255, 255, 255)",
        fontPx: 12,
        weight: 400,
      }),
    ]);
    expect(findings.map((f) => f.kind)).toContain("contrast-aa");
  });
  it("texto con buen contraste pasa", () => {
    const findings = scanStyles([
      box({
        text: "hola",
        color: "rgb(22, 28, 31)",
        bgColor: "rgb(255, 255, 255)",
        fontPx: 12,
        weight: 400,
      }),
    ]);
    expect(findings).toHaveLength(0);
  });
  it("un control deshabilitado está exento de AA", () => {
    const findings = scanStyles([
      box({
        text: "Emitiendo…",
        color: "rgb(107, 122, 118)",
        bgColor: "rgb(34, 42, 45)",
        fontPx: 12,
        weight: 400,
        disabled: true,
      }),
    ]);
    expect(findings).toHaveLength(0);
  });
});
