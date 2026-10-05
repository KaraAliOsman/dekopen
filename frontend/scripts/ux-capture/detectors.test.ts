import { describe, expect, it } from "vitest";

import { detectTextFindings, summarizeFindings } from "./detectors";

describe("ux-capture text detectors", () => {
  it("detects UUIDs and long hexadecimal hashes", () => {
    const findings = detectTextFindings(
      "id 550e8400-e29b-41d4-a716-446655440000 hash abcdef1234567890",
    );
    expect(findings.map((finding) => finding.kind)).toEqual(["uuid", "hex"]);
  });

  it("ignores legitimate quotation and work-order codes", () => {
    const findings = detectTextFindings("COT-P-000001-REV-A OT-P-000005-REV-A-03 P-000001");
    expect(findings).toEqual([]);
  });

  it("detects raw JS values and object rendering leaks", () => {
    const kinds = detectTextFindings("[object Object] undefined NaN null").map(
      (finding) => finding.kind,
    );
    expect(kinds).toEqual(["object-object", "empty-js-value", "empty-js-value", "empty-js-value"]);
  });

  it("detects raw enums without flagging normal Spanish labels", () => {
    const findings = detectTextFindings("WORKSHOP_MANAGER Orden de trabajo liberada");
    expect(findings).toHaveLength(1);
    expect(findings[0]?.kind).toBe("raw-enum");
  });

  it("detects native browser validation English and mock labels", () => {
    const kinds = detectTextFindings("Please Fill out MOCK").map((finding) => finding.kind);
    expect(kinds).toEqual(["native-validation-english", "native-validation-english", "mock"]);
  });

  it("detects excessive decimals and percentage precision", () => {
    const kinds = detectTextFindings("1561.0000 mm 92.533%").map((finding) => finding.kind);
    expect(kinds).toEqual(["decimal-precision", "percent-precision"]);
  });

  it("summarizes findings by kind and route", () => {
    const summary = summarizeFindings([
      { routeId: "a", findings: [{ kind: "uuid", sample: "uno" }] },
      { routeId: "b", findings: [{ kind: "uuid", sample: "dos" }, { kind: "mock" }] },
    ]);
    expect(summary[0]).toMatchObject({ key: "uuid", count: 2, routes: ["a", "b"] });
  });
});
