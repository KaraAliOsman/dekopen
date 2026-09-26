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
