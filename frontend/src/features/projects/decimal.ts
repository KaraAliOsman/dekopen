/** Exact decimal arithmetic for millimetre values arriving as decimal strings.
 * Mirrors the Rational approach in `features/canvas/snapping.ts` — values keep
 * full precision; never pass through binary floats for bounds the engine will
 * re-check exactly. */

export type DecimalValue = {
  numerator: bigint;
  denominator: bigint;
};

export function parseDecimal(value: string): DecimalValue | null {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?$/.exec(value.trim());
  if (match === null) return null;
  const sign = match[1] === "-" ? -1n : 1n;
  const whole = match[2];
  const fraction = match[3] ?? "";
  if (whole === undefined) return null;
  const denominator = 10n ** BigInt(fraction.length);
  return {
    numerator: sign * (BigInt(whole) * denominator + BigInt(fraction || "0")),
    denominator,
  };
}

export function addDecimal(a: DecimalValue, b: DecimalValue): DecimalValue {
  return {
    numerator: a.numerator * b.denominator + b.numerator * a.denominator,
    denominator: a.denominator * b.denominator,
  };
}

export function subtractDecimal(a: DecimalValue, b: DecimalValue): DecimalValue {
  return {
    numerator: a.numerator * b.denominator - b.numerator * a.denominator,
    denominator: a.denominator * b.denominator,
  };
}

export function multiplyDecimal(a: DecimalValue, b: DecimalValue): DecimalValue {
  return { numerator: a.numerator * b.numerator, denominator: a.denominator * b.denominator };
}

export function divideDecimal(a: DecimalValue, b: DecimalValue): DecimalValue {
  return { numerator: a.numerator * b.denominator, denominator: a.denominator * b.numerator };
}

export function divideByInt(a: DecimalValue, n: number): DecimalValue {
  return { numerator: a.numerator, denominator: a.denominator * BigInt(n) };
}

/** Half-up round to the nearest integer, exact on rationals — money display
 * needs the cents the document carries, never a float neighbor. */
export function roundDecimalToInt(value: DecimalValue): string {
  const negative = value.numerator < 0n;
  const magnitude = negative ? -value.numerator : value.numerator;
  const quotient = magnitude / value.denominator;
  const remainder = magnitude % value.denominator;
  const rounded = remainder * 2n >= value.denominator ? quotient + 1n : quotient;
  return `${negative && rounded !== 0n ? "-" : ""}${rounded}`;
}

export function midpointDecimal(a: DecimalValue, b: DecimalValue): DecimalValue {
  const sum = addDecimal(a, b);
  return { numerator: sum.numerator, denominator: sum.denominator * 2n };
}

export function compareDecimal(a: DecimalValue, b: DecimalValue): number {
  const left = a.numerator * b.denominator;
  const right = b.numerator * a.denominator;
  return left < right ? -1 : left > right ? 1 : 0;
}

/** Exact decimal presentation — long division keeps non-power-of-10
 * denominators (midpoints carry ×2) honest: 70/200 formats as .35, never
 * a mis-scaled .7. Trailing zeros trimmed; non-terminating expansions cap
 * at 40 digits (bounds inputs are always terminating). */
export function formatDecimal(value: DecimalValue): string {
  const negative = value.numerator < 0n;
  const magnitude = negative ? -value.numerator : value.numerator;
  const whole = magnitude / value.denominator;
  let remainder = magnitude % value.denominator;
  if (remainder === 0n) return `${negative ? "-" : ""}${whole}`;
  let digits = "";
  while (remainder !== 0n && digits.length < 40) {
    remainder *= 10n;
    digits += (remainder / value.denominator).toString();
    remainder %= value.denominator;
  }
  return `${negative ? "-" : ""}${whole}.${digits.replace(/0+$/, "")}`;
}
