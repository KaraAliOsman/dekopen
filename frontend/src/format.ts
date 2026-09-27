/** Revision codes are storage identifiers ("REV-A"); the UI reads them as
 * document language («Revisión A»). Anything outside the pattern renders
 * unchanged — never invent a friendlier name for an unknown code. */
export function formatRevision(code: string | null | undefined): string {
  if (!code) return "—";
  const match = /^REV-([A-Z]+)$/.exec(code);
  return match ? `Revisión ${match[1]}` : code;
}

/** Parse a user-entered number accepting both es-CL and software
 * conventions: "1500", "1500.5", "1500,5" and "1.500,5" all work, and the
 * thousands-dot trap ("1.500" meaning fifteen hundred) reads as 1500 —
 * never 1.5. Returns null for anything that is not a plain number. */
export function parseLocaleNumber(candidate: string): number | null {
  const text = candidate.trim();
  if (text === "") return null;
  // Groups of exactly three digits after dots are thousands separators —
  // an optional comma tail is then the decimal part ("1.500.000,25").
  const thousands = /^[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?$/.test(text);
  const commaThousands = /^[+-]?\d{1,3}(?:,\d{3})+$/.test(text);
  const normalized = thousands
    ? text.replaceAll(".", "").replace(",", ".")
    : commaThousands
      ? text.replaceAll(",", "")
      : text.replace(",", ".");
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(normalized)) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

/** Display a decimal millimetre string at business precision: "1200.0000" →
 * "1200", "235.50" → "235.5". Non-decimal text passes through untouched. */
/** Yield/utilization percentages display at one decimal (93.5, not 93.4667). */
export function fmtPct(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toFixed(1);
}

export function fmtMm(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  if (!/^[+-]?\d+(\.\d+)?$/.test(text)) return text;
  return text.includes(".") ? text.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "") : text;
}

/** Chilean RUT — módulo-11 check digit. Accepts "12.345.678-5", "12345678-5",
 * "123456785" and "K" digits; empty/blank is valid (the field is optional). */
export function isValidRut(candidate: string): boolean {
  const cleaned = candidate.replace(/[.\-\s]/g, "").toUpperCase();
  if (cleaned === "") return true;
  if (!/^\d{1,8}[\dK]$/.test(cleaned)) return false;
  const body = cleaned.slice(0, -1);
  const digit = cleaned.slice(-1);
  let sum = 0;
  let factor = 2;
  for (let index = body.length - 1; index >= 0; index -= 1) {
    sum += Number(body[index]) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const remainder = 11 - (sum % 11);
  const expected = remainder === 11 ? "0" : remainder === 10 ? "K" : String(remainder);
  return digit === expected;
}

const BUSINESS_TZ = "America/Santiago";

/** Operator-facing timestamp: business timezone and minute precision — the
 * browser's locale + raw seconds never leak into the product (review m3).
 * Unparseable input renders unchanged rather than as "Invalid Date". */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return value;
  return stamp.toLocaleString("es-CL", {
    timeZone: BUSINESS_TZ,
    dateStyle: "short",
    timeStyle: "short",
  });
}
