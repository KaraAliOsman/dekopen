import { fmtWire } from "../../format";

const MAX_DIMENSION_CENTI_MM = 9_999_999_999n;
const FIFTY_MM_CENTI = 5_000n;
const TEN_MM_CENTI = 1_000n;
const ONE_CENTI_MM = 1n;
const SNAP_RADIUS_PX = 12n;

type Rational = {
  numerator: bigint;
  denominator: bigint;
};

export type SnapResult = {
  valueMm: string;
  mode: "50mm" | "10mm" | "0.01mm";
  showGuide: boolean;
};

function powerOfTen(exponent: number): bigint {
  return 10n ** BigInt(exponent);
}

function parseDecimal(value: string): Rational {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?$/.exec(value.trim());
  if (match === null) throw new Error("Decimal presentation value is invalid");
  const sign = match[1] === "-" ? -1n : 1n;
  const whole = match[2];
  const fraction = match[3] ?? "";
  if (whole === undefined) throw new Error("Decimal presentation value is invalid");
  const denominator = powerOfTen(fraction.length);
  return {
    numerator: sign * (BigInt(whole) * denominator + BigInt(fraction || "0")),
    denominator,
  };
}

function absolute(value: bigint): bigint {
  return value < 0n ? -value : value;
}

function roundHalfUpToCentiMultiple(value: Rational, incrementCenti: bigint): bigint {
  const sign = value.numerator < 0n ? -1n : 1n;
  const scaled = absolute(value.numerator) * 100n;
  const divisor = value.denominator * incrementCenti;
  let quotient = scaled / divisor;
  const remainder = scaled % divisor;
  if (remainder * 2n >= divisor) quotient += 1n;
  return sign * quotient * incrementCenti;
}

function formatCentiMm(value: bigint): string {
  const sign = value < 0n ? "-" : "";
  const absoluteValue = absolute(value);
  const whole = absoluteValue / 100n;
  const fraction = (absoluteValue % 100n).toString().padStart(2, "0");
  return `${sign}${whole}.${fraction}`;
}

function withinScreenRadius(
  candidate: Rational,
  targetCenti: bigint,
  pixelsPerMm: Rational,
): boolean {
  if (pixelsPerMm.numerator <= 0n) throw new Error("Viewport scale must be positive");
  const differenceNumerator = absolute(
    candidate.numerator * 100n - targetCenti * candidate.denominator,
  );
  const differenceDenominator = candidate.denominator * 100n;
  const screenNumerator = differenceNumerator * pixelsPerMm.numerator;
  const screenDenominator = differenceDenominator * pixelsPerMm.denominator;
  return screenNumerator <= SNAP_RADIUS_PX * screenDenominator;
}

export function normalizeDimensionCandidate(value: string): string | null {
  const match = /^\+?(\d+)(?:\.(\d{0,2}))?$/.exec(value.trim());
  if (match === null || match[1] === undefined) return null;
  const fraction = (match[2] ?? "").padEnd(2, "0");
  const centiMm = BigInt(match[1]) * 100n + BigInt(fraction || "0");
  if (centiMm < ONE_CENTI_MM || centiMm > MAX_DIMENSION_CENTI_MM) return null;
  return formatCentiMm(centiMm);
}

export function snapOuterDimension(
  candidateMm: string,
  pixelsPerMm: string,
  snapEnabled: boolean,
): SnapResult {
  const candidate = parseDecimal(candidateMm);
  if (!snapEnabled) {
    return {
      valueMm: formatCentiMm(roundHalfUpToCentiMultiple(candidate, ONE_CENTI_MM)),
      mode: "0.01mm",
      showGuide: false,
    };
  }

  const nearestFifty = roundHalfUpToCentiMultiple(candidate, FIFTY_MM_CENTI);
  if (withinScreenRadius(candidate, nearestFifty, parseDecimal(pixelsPerMm))) {
    return {
      valueMm: formatCentiMm(nearestFifty),
      mode: "50mm",
      showGuide: true,
    };
  }
  return {
    valueMm: formatCentiMm(roundHalfUpToCentiMultiple(candidate, TEN_MM_CENTI)),
    mode: "10mm",
    showGuide: false,
  };
}

export function presentationNumberToDecimal(value: number): string {
  if (!Number.isFinite(value)) throw new Error("Pointer coordinate must be finite");
  return fmtWire(value, 6);
}
