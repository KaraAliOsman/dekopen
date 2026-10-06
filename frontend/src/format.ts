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
/** Porcentaje a un decimal con coma — 85.9 → "85,9". El glifo % lo pone
 * el llamador (`{fmtPct(x)} %`) o `formatPercent`, que lo incluye. */
export function fmtPct(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toFixed(1).replace(".", ",");
}

/** Identificador técnico cuando falta la etiqueta humana — un UUID/hash
 * nunca imprime su hex: queda como "#8f3a", inequívoco de folio. */
export function shortTechnicalId(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const clean = value.replaceAll("-", "");
  if (clean.length > 8 && /^[0-9a-fA-F]+$/.test(clean)) {
    return `#${clean.slice(-4).toLowerCase()}`;
  }
  return value;
}

/** Decimal canónico para INPUTS — sin agrupar ni coma: un valor editable o
 * persistido jamás lleva glifos §3.3 ("1000.35" se edita, "1 000,35" se lee). */
export function fmtMmCanonical(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  if (!/^[+-]?\d+(\.\d+)?$/.test(text)) return text;
  return text.includes(".") ? text.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "") : text;
}

/** Milímetros §3.3 — agrupa con espacio fino y decimal con coma:
 * "2400" → "2 400", "1249.50" → "1 249,5". */
export function fmtMm(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  if (!/^[+-]?\d+(\.\d+)?$/.test(text)) return text;
  const [intPart = "", fracRaw] = text.split(".");
  const frac = (fracRaw ?? "").replace(/0+$/, "");
  const grouped = groupThin(intPart);
  return frac ? `${grouped},${frac}` : grouped;
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

/** Contact email — pragmatic shape check, not full RFC 5322. Empty is valid
 * (the field is optional); the point is rejecting obvious garbage before the
 * browser's English-only type=email bubble does it for us. */
export function isValidEmail(candidate: string): boolean {
  const text = candidate.trim();
  if (text === "") return true;
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(text);
}

const BUSINESS_TZ = "America/Santiago";

/** Operator-facing timestamp: business timezone and minute precision — the
 * browser's locale + raw seconds never leak into the product (review m3).
 * Unparseable input renders unchanged rather than as "Invalid Date". */
export function formatDateTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return String(value);
  // Año de 4 dígitos siempre: «05-10-2026» como en el documento.
  const day = stamp.toLocaleDateString("es-CL", {
    timeZone: BUSINESS_TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  const time = stamp.toLocaleTimeString("es-CL", {
    timeZone: BUSINESS_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${day} ${time}`;
}

/** Business date — DD-MM-AAAA pinned to the business timezone so a sealed-at
 * timestamp never renders a different day than the document carries. */
export function formatDate(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (day) return `${day[3]}-${day[2]}-${day[1]}`;
  const stamp = new Date(text);
  if (Number.isNaN(stamp.getTime())) return text;
  return stamp.toLocaleDateString("es-CL", { timeZone: BUSINESS_TZ });
}

/** Round a decimal string to `digits` places, half-up, without binary float —
 * sealed Decimal strings like "100.005" must render the cents the document
 * carries, not the neighbor float. BigInt carry handles values past 2^53. */
export function quantize(value: string, digits: number): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value;
  const negative = match[1] === "-";
  const intPart = match[2] ?? "0";
  const frac = match[3] ?? "";
  if (frac.length <= digits) {
    return `${negative ? "-" : ""}${intPart}${digits > 0 ? `.${frac.padEnd(digits, "0")}` : ""}`;
  }
  const kept = frac.slice(0, digits);
  if (Number(frac[digits]) < 5) {
    return `${negative ? "-" : ""}${intPart}${digits > 0 ? `.${kept}` : ""}`;
  }
  const carry = (BigInt(intPart + kept) + 1n).toString().padStart(intPart.length + digits, "0");
  return `${negative ? "-" : ""}${carry.slice(0, carry.length - digits)}${
    digits > 0 ? `.${carry.slice(carry.length - digits)}` : ""
  }`;
}

/** Parse a typed amount into the canonical decimal string the API expects.
 * es-CL rules: "," is the only decimal mark, "." only groups thousands —
 * "1.500.000" is 1500000, "100,50" is 100.50. Garbage rejects rather than
 * guessing: a mangled immutable document is worse than a rejected
 * keystroke. */
export function parseMoneyInput(text: string): string | null {
  const cleaned = text.trim().replace(/\s/g, "");
  if (!cleaned || !/^[\d.,]+$/.test(cleaned) || !/\d/.test(cleaned)) return null;
  const lastComma = cleaned.lastIndexOf(",");
  const hasDecimal =
    lastComma !== -1 &&
    cleaned.indexOf(",") === lastComma &&
    /^\d{1,2}$/.test(cleaned.slice(lastComma + 1));
  const intRaw = hasDecimal ? cleaned.slice(0, lastComma) : cleaned;
  const dec = hasDecimal ? cleaned.slice(lastComma + 1) : "";
  // Every "." in the integer part must lead a 3-digit thousands group —
  // "1.0.0" or "12,34" reject instead of silently rescaling.
  if (!/^\d+$/.test(intRaw) && !/^\d{1,3}(\.\d{3})+$/.test(intRaw)) return null;
  const intPart = intRaw.replace(/\./g, "");
  if (!intPart) return null;
  return dec ? `${intPart}.${dec}` : intPart;
}

/** Decimales por moneda — §3.3: CLP entero, USD 2, UF 4. */
const CURRENCY_DIGITS: Record<string, number> = { CLP: 0, USD: 2, UF: 4 };

export function moneyDigits(currency: string): number {
  return CURRENCY_DIGITS[currency] ?? 2;
}

/** Dinero con la convención del documento — "$1.435.471", "US$1.435,47",
 * "UF 12,3456". Mismos decimales que el PDF: lo que se precisa se lee igual
 * en pantalla y en papel. */
export function formatMoney(value: string | number | null | undefined, currency: string): string {
  if (value === null || value === undefined || value === "") return "—";
  const digits = moneyDigits(currency);
  const text = String(value);
  const numeric = /^-?\d+(\.\d+)?$/.test(text) ? text : String(Number(text));
  if (!/^-?\d+(\.\d+)?$/.test(numeric)) return text;
  const rounded = quantize(numeric, digits);
  const negative = rounded.startsWith("-");
  const magnitude = Number(negative ? rounded.slice(1) : rounded);
  let formatted: string;
  try {
    formatted = new Intl.NumberFormat("es-CL", {
      style: "currency",
      currency,
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    }).format(magnitude);
  } catch {
    // Moneda no ISO (UF): código + número con sus decimales.
    formatted = `${currency} ${new Intl.NumberFormat("es-CL", {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    }).format(magnitude)}`;
  }
  // El signo precede al símbolo: «-$1.500», no «$-1.500».
  return negative ? `-${formatted}` : formatted;
}

/* ------------------------------------------------------------------ *
 * §3.3 — números del dominio. Medidas agrupan con espacio fino U+2009  *
 * (convención de plano), no con el punto del dinero.                    *
 * ------------------------------------------------------------------ */

const THIN_SPACE = "\u2009";

/** Agrupación de miles con espacio fino — "2400" → "2 400". */
export function groupThin(value: string): string {
  const match = /^(-?)(\d+)(.*)$/.exec(value.trim());
  if (!match) return value;
  const sign = match[1] ?? "";
  const intPart = match[2] ?? "";
  const rest = match[3] ?? "";
  return sign + intPart.replace(/\B(?=(\d{3})+(?!\d))/g, THIN_SPACE) + rest;
}

/** Milímetros enteros con espacio fino — "2400" → "2 400". El motor
 * entrega milímetros; nunca se convierte a metros. */
export function formatLengthMm(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return groupThin(String(Math.round(num)));
}

/** Par ancho×alto — "2400"×"1800" → "2 400 × 1 800". */
export function formatDims(
  width: string | number | null | undefined,
  height: string | number | null | undefined,
): string {
  const w = formatLengthMm(width);
  const h = formatLengthMm(height);
  if (w === "—" || h === "—") return "—";
  return `${w} × ${h}`;
}

/** Área en m² con 2 decimales y coma — "4.32" → "4,32". */
export function formatAreaM2(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

/** Peso en kg con 1 decimal — "12.34" → "12,3". */
export function formatWeightKg(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(num);
}

/** Transmitancia Uw/Ug con 2 decimales — "1.4" → "1,40". */
export function formatUvalue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

/** Cantidad entera — sin decimales, con espacio fino. */
export function formatQty(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return groupThin(String(Math.round(num)));
}

/** Porcentaje — "fraction" recibe el número 0–1 del motor y muestra
 * "93,5 %"; "points" recibe puntos porcentuales ("93.5" → "93,5 %").
 * Un decimal con coma en ambos casos. */
export function formatPercent(
  value: string | number | null | undefined,
  kind: "fraction" | "points" = "fraction",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  const points = kind === "fraction" ? num * 100 : num;
  const text = new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(points);
  return `${text} %`;
}

/** Reloj relativo en español — "hace 5 min", "hace 2 h", "ayer" cae en
 * "hace 1 d". A partir de 7 días devuelve la fecha absoluta. */
export function formatRelativeTime(
  value: string | number | null | undefined,
  now = new Date(),
): string {
  if (value === null || value === undefined || value === "") return "—";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return String(value);
  const diffMs = now.getTime() - stamp.getTime();
  const rtf = new Intl.RelativeTimeFormat("es-CL", { numeric: "auto" });
  const minutes = Math.round(diffMs / 60000);
  if (Math.abs(minutes) < 1) return "ahora";
  if (Math.abs(minutes) < 60) return rtf.format(-minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(-hours, "hour");
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 7) return rtf.format(-days, "day");
  return formatDate(value);
}
