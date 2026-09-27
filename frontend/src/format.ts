/** Revision codes are storage identifiers ("REV-A"); the UI reads them as
 * document language («Revisión A»). Anything outside the pattern renders
 * unchanged — never invent a friendlier name for an unknown code. */
export function formatRevision(code: string | null | undefined): string {
  if (!code) return "—";
  const match = /^REV-([A-Z]+)$/.exec(code);
  return match ? `Revisión ${match[1]}` : code;
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
