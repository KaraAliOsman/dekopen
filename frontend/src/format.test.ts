import { describe, expect, it } from "vitest";

import { parseLocaleNumber } from "./format";

describe("parseLocaleNumber", () => {
  it("reads plain integers and dot decimals", () => {
    expect(parseLocaleNumber("1500")).toBe(1500);
    expect(parseLocaleNumber("1500.5")).toBe(1500.5);
    expect(parseLocaleNumber("0.01")).toBe(0.01);
    expect(parseLocaleNumber("-45")).toBe(-45);
  });

  it("reads comma decimals", () => {
    expect(parseLocaleNumber("1500,5")).toBe(1500.5);
    expect(parseLocaleNumber("15,5")).toBe(15.5);
    expect(parseLocaleNumber("-12,25")).toBe(-12.25);
  });

  it("reads thousands separators without shrinking the value", () => {
    // The es-CL thousands-dot: "1.500" is fifteen hundred, never 1.5.
    expect(parseLocaleNumber("1.500")).toBe(1500);
    expect(parseLocaleNumber("1.500.000")).toBe(1500000);
    expect(parseLocaleNumber("1.500,25")).toBe(1500.25);
    expect(parseLocaleNumber("15,500")).toBe(15500);
  });

  it("rejects non-numbers and mixed junk", () => {
    expect(parseLocaleNumber("")).toBeNull();
    expect(parseLocaleNumber("abc")).toBeNull();
    expect(parseLocaleNumber("1.2.3.4")).toBeNull();
    // Trailing zeros after a decimal dot are still a decimal (1.5000 = 1.5).
    expect(parseLocaleNumber("1.5000")).toBe(1.5);
    expect(parseLocaleNumber("1,5,5")).toBeNull();
    expect(parseLocaleNumber("1.5e3")).toBeNull();
  });
});
