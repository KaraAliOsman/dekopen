import { describe, expect, it } from "vitest";

import {
  scanConsoleEntries,
  scanHttpEntries,
  scanLayout,
  scanVisibleText,
} from "../../scripts/ux-capture/detectors";

describe("scanVisibleText", () => {
  it("flags UUIDs rendered in the UI", () => {
    const findings = scanVisibleText("Proyecto 6e2492b1-a057-4287-a4f0-5808a52f48d1");
    expect(findings.some((f) => f.kind === "uuid")).toBe(true);
  });

  it("flags 10+ lowercase hex runs (hash leaks)", () => {
    const findings = scanVisibleText(
      "bom 921db532db86833a38b74b90be823154b5ecf8622e010712aa99c4dc9d714ebf",
    );
    expect(findings.some((f) => f.kind === "long-hex")).toBe(true);
  });

  it("does NOT flag customer-facing revision codes", () => {
    // Contract case: COT-P-000001-REV-A and OT codes are real copy.
    const findings = scanVisibleText("COT-P-000001-REV-A · OT-P-000017-REV-A-05 · Guía GD-000012");
    expect(findings).toHaveLength(0);
  });

  it("flags [object Object] and undefined/NaN/null leaks", () => {
    expect(scanVisibleText("Total: [object Object]").some((f) => f.kind === "object-object")).toBe(
      true,
    );
    expect(scanVisibleText("cliente undefined").some((f) => f.kind === "undefined-word")).toBe(
      true,
    );
    expect(scanVisibleText("valor NaN").some((f) => f.kind === "undefined-word")).toBe(true);
    expect(scanVisibleText("dirección null").some((f) => f.kind === "undefined-word")).toBe(true);
  });

  it("flags enum-looking tokens but not allowlisted business codes", () => {
    const findings = scanVisibleText("estado INTERNAL_ERROR_CODE ok RUT QC OT");
    expect(findings.some((f) => f.kind === "enum-token")).toBe(true);
    expect(findings.filter((f) => f.detail === "RUT")).toHaveLength(0);
    expect(findings.filter((f) => f.detail === "QC")).toHaveLength(0);
  });

  it("flags MOCK and English-only words, not Spanish homographs", () => {
    const mock = scanVisibleText("datos MOCK precargados");
    expect(mock.some((f) => f.kind === "mock-word")).toBe(true);
    const eng = scanVisibleText("This field is required");
    expect(eng.some((f) => f.kind === "english-word")).toBe(true);
    // "error" is a Spanish word too — never a finding on its own.
    const esp = scanVisibleText("Error al guardar la posición");
    expect(esp.some((f) => f.kind === "english-word")).toBe(false);
  });

  it("flags ≥4-decimal numbers and >2-decimal percents", () => {
    expect(scanVisibleText("largo 1400.0000 mm").some((f) => f.kind === "decimal-4plus")).toBe(
      true,
    );
    expect(scanVisibleText("largo 1400.00 mm")).toHaveLength(0);
    expect(scanVisibleText("merma 8.333 %").some((f) => f.kind === "percent-3plus")).toBe(true);
    expect(scanVisibleText("IVA 19%")).toHaveLength(0);
  });

  it("dedupes repeated findings", () => {
    const findings = scanVisibleText("NaN NaN NaN");
    expect(findings.filter((f) => f.kind === "undefined-word")).toHaveLength(1);
  });
});

describe("scanLayout", () => {
  const wide: Parameters<typeof scanLayout>[2] = [
    { label: "span", fontPx: 9.5, widthPx: 40, heightPx: 10, interactive: false },
    { label: "button#save", fontPx: 12, widthPx: 30, heightPx: 30, interactive: true },
    { label: "button#ok", fontPx: 14, widthPx: 90, heightPx: 44, interactive: true },
  ];

  it("flags horizontal overflow", () => {
    const findings = scanLayout(1500, 1440, [], { touchAudit: false });
    expect(findings.some((f) => f.kind === "overflow-x")).toBe(true);
  });

  it("flags <11px fonts and <44px touch targets only under touch audit", () => {
    const noTouch = scanLayout(1024, 1024, wide, { touchAudit: false });
    expect(noTouch.some((f) => f.kind === "font-too-small")).toBe(true);
    expect(noTouch.some((f) => f.kind === "touch-too-small")).toBe(false);
    const touch = scanLayout(1024, 1024, wide, { touchAudit: true });
    expect(touch.filter((f) => f.kind === "touch-too-small")).toHaveLength(1);
  });
});

describe("console/http scans", () => {
  it("flags console errors and HTTP ≥400", () => {
    const c = scanConsoleEntries([
      { level: "error", text: "Uncaught TypeError" },
      { level: "warning", text: "deprecation" },
    ]);
    expect(c).toHaveLength(1);
    const h = scanHttpEntries([
      { url: "/api/v1/projects/", status: 200 },
      { url: "/api/v1/x", status: 422 },
    ]);
    expect(h).toHaveLength(1);
  });
});
