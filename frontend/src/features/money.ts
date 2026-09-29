/** Shared es-CL presentation helpers — UI mirrors the document formatter
 * (thousands "." + integer CLP) so a quote reads the same on screen and PDF. */

/** Round a decimal string to `digits` places, half-up, without binary float —
 * sealed Decimal strings like "100.005" must render the cents the document
 * carries, not the neighbor float. BigInt carry handles values past 2^53. */
function quantize(value: string, digits: number): string {
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

export function formatMoney(value: string | null | undefined, currency: string): string {
  if (value === null || value === undefined || value === "") return "—";
  const digits = currency === "CLP" ? 0 : 2;
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency,
    maximumFractionDigits: digits,
  }).format(Number(quantize(value, digits)));
}

/** Business date — DD-MM-AAAA pinned to the business timezone so a sealed-at
 * timestamp never renders a different day than the document carries. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (day) return `${day[3]}-${day[2]}-${day[1]}`;
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return value;
  return stamp.toLocaleDateString("es-CL", { timeZone: "America/Santiago" });
}
