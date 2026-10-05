/** Convenciones de formato — la captura de bordes que fija el contrato:
 * 0, negativos, nulos, 1e9, CLP vs USD, "2400" / "2 400" / "2.400" /
 * "1249,5", redondeo half-up documentado. Lo que aquí no se decide,
 * aparecerá en la pantalla como ruido. */
import { describe, expect, it } from "vitest";

import {
  formatAreaM2,
  formatDate,
  formatDateTime,
  formatDims,
  formatLengthMm,
  formatMoney,
  formatPercent,
  formatQty,
  formatRelativeTime,
  formatUvalue,
  formatWeightKg,
  groupThin,
  isValidEmail,
  isValidRut,
  moneyDigits,
  parseMoneyInput,
  quantize,
} from "./format";

const TS = "\u2009"; // espacio fino U+2009

describe("groupThin", () => {
  it("agrupa miles con espacio fino", () => {
    expect(groupThin("2400")).toBe(`2${TS}400`);
    expect(groupThin("1000000000")).toBe(`1${TS}000${TS}000${TS}000`);
    expect(groupThin("-4800")).toBe(`-4${TS}800`);
    expect(groupThin("123")).toBe("123");
    expect(groupThin("abc")).toBe("abc");
  });
});

describe("formatLengthMm / formatDims", () => {
  it("enteros con espacio fino, sin decimales", () => {
    expect(formatLengthMm("2400")).toBe(`2${TS}400`);
    expect(formatLengthMm("0")).toBe("0");
    expect(formatLengthMm("-300")).toBe(`-300`);
    expect(formatLengthMm("1234.6")).toBe(`1${TS}235`);
    expect(formatLengthMm(null)).toBe("—");
    expect(formatLengthMm("")).toBe("—");
  });
  it("dims ancho×alto", () => {
    expect(formatDims(2400, 1800)).toBe(`2${TS}400 × 1${TS}800`);
    expect(formatDims(null, 800)).toBe("—");
  });
});

describe("formatMoney", () => {
  it("CLP sin decimales con punto de miles del documento", () => {
    expect(formatMoney("1435471", "CLP")).toBe("$1.435.471");
    expect(formatMoney(0, "CLP")).toBe("$0");
    expect(formatMoney("-1500", "CLP")).toBe("-$1.500");
    expect(formatMoney("-1500.5", "USD")).toBe("-US$1.500,50");
    expect(formatMoney("1e9", "CLP")).toBe("$1.000.000.000");
  });
  it("USD con 2 decimales y coma", () => {
    expect(formatMoney("1435.471", "USD")).toBe("US$1.435,47");
    expect(formatMoney("99.995", "USD")).toBe("US$100,00");
  });
  it("UF con 4 decimales", () => {
    expect(formatMoney("12.3456", "UF")).toBe("UF 12,3456");
  });
  it("nulo y vacío → guion, basura → texto crudo", () => {
    expect(formatMoney(null, "CLP")).toBe("—");
    expect(formatMoney("", "CLP")).toBe("—");
    expect(formatMoney("xpto", "CLP")).toBe("xpto");
  });
});

describe("moneyDigits", () => {
  it("CLP=0, USD=2, UF=4, otras=2", () => {
    expect(moneyDigits("CLP")).toBe(0);
    expect(moneyDigits("USD")).toBe(2);
    expect(moneyDigits("UF")).toBe(4);
    expect(moneyDigits("EUR")).toBe(2);
  });
});

describe("quantize — redondeo half-up", () => {
  it("documenta el medio hacia arriba", () => {
    expect(quantize("100.005", 2)).toBe("100.01");
    expect(quantize("1.005", 0)).toBe("1");
    expect(quantize("1.999", 0)).toBe("2");
    expect(quantize("999.5", 0)).toBe("1000");
    expect(quantize("-99.5", 0)).toBe("-100");
    expect(quantize("0", 2)).toBe("0.00");
  });
});

describe("parseMoneyInput — entrada es-CL", () => {
  it.each([
    ["2400", "2400"],
    ["2 400", "2400"],
    ["2.400", "2400"],
    ["1249,5", "1249.5"],
    ["1.500.000", "1500000"],
    ["100,50", "100.50"],
    ["1.500.000,25", "1500000.25"],
  ])("%s → %s", (input, expected) => {
    expect(parseMoneyInput(input)).toBe(expected);
  });
  it.each(["", "abc", "12,345", "1.0.0", "-", ".."])("rechaza %s", (input) => {
    expect(parseMoneyInput(input)).toBeNull();
  });
});

describe("números del dominio", () => {
  it("área, peso, U, cantidad", () => {
    expect(formatAreaM2("4.32")).toBe("4,32");
    expect(formatAreaM2(null)).toBe("—");
    expect(formatWeightKg("12.34")).toBe("12,3");
    expect(formatUvalue("1.4")).toBe("1,40");
    expect(formatQty("1000")).toBe(`1${TS}000`);
    expect(formatQty(null)).toBe("—");
  });
  it("porcentaje fraction vs points", () => {
    expect(formatPercent(0.935, "fraction")).toBe("93,5 %");
    expect(formatPercent("93.5", "points")).toBe("93,5 %");
    expect(formatPercent(0, "fraction")).toBe("0,0 %");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("fechas", () => {
  it("formatDate fija America/Santiago y DD-MM-AAAA", () => {
    expect(formatDate("2026-10-05")).toBe("05-10-2026");
    expect(formatDate(null)).toBe("—");
    expect(formatDate("no-fecha")).toBe("no-fecha");
  });
  it("formatDateTime con minutos", () => {
    const out = formatDateTime("2026-10-05T12:30:00Z");
    expect(out).toMatch(/05-10-2026 \d{2}:\d{2}/);
    expect(formatDateTime(null)).toBe("—");
  });
  it("formatRelativeTime: ahora, minutos, horas, días, absoluto ≥7d", () => {
    const now = new Date("2026-10-05T12:00:00Z");
    expect(formatRelativeTime("2026-10-05T12:00:00Z", now)).toBe("ahora");
    expect(formatRelativeTime("2026-10-05T11:55:00Z", now)).toMatch(/hace/);
    expect(formatRelativeTime("2026-10-05T09:00:00Z", now)).toMatch(/hace 3/);
    // numeric:"auto" nombra días cercanos: ayer / anteayer son mejores
    // que «hace 1 día» en el vocabulario de taller.
    expect(formatRelativeTime("2026-10-03T12:00:00Z", now)).toBe("anteayer");
    expect(formatRelativeTime("2026-09-20T12:00:00Z", now)).toBe("20-09-2026");
  });
});

describe("isValidRut — módulo-11", () => {
  it.each([
    "12.345.678-5",
    "12345678-5",
    "123456785",
    "11111111-1",
    "10000013-K", // dígito K verificado módulo-11
    "",
    "  ",
  ])("válido %s", (rut) => {
    expect(isValidRut(rut)).toBe(true);
  });
  it.each(["12345678-9", "123456789", "15589486-0", "abc", "12345678-K2"])("inválido %s", (rut) => {
    expect(isValidRut(rut)).toBe(false);
  });
});

describe("isValidEmail", () => {
  it("rechaza basura, acepta vacío", () => {
    expect(isValidEmail("a@b.cl")).toBe(true);
    expect(isValidEmail("")).toBe(true);
    expect(isValidEmail("sin-arroba")).toBe(false);
    expect(isValidEmail("a@b")).toBe(false);
  });
});
