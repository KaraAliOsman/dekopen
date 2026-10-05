export type TextFindingKind =
  | "uuid"
  | "hex"
  | "object-object"
  | "empty-js-value"
  | "raw-enum"
  | "native-validation-english"
  | "mock"
  | "decimal-precision"
  | "percent-precision";

export type TextFinding = {
  kind: TextFindingKind;
  match: string;
  sample: string;
};

type Detector = {
  kind: TextFindingKind;
  pattern: RegExp;
  include?(match: string, fullText: string): boolean;
};

const LEGITIMATE_CODES = /^(?:COT|OT)-P-\d{6}-REV-[A-Z](?:-\d{2})?$|^P-\d{6}$|^REV-[A-Z]$/;

const DETECTORS: Detector[] = [
  {
    kind: "uuid",
    pattern: /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi,
  },
  {
    kind: "hex",
    pattern: /\b[0-9a-f]{10,}\b/gi,
    include: (match) => /[a-f]/i.test(match) && !/^\d+$/.test(match),
  },
  { kind: "object-object", pattern: /\[object Object\]/g },
  { kind: "empty-js-value", pattern: /\b(?:undefined|NaN|null)\b/g },
  {
    kind: "raw-enum",
    pattern: /\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/g,
    include: (match) => !LEGITIMATE_CODES.test(match),
  },
  { kind: "native-validation-english", pattern: /\b(?:Please|Fill out)\b/g },
  { kind: "mock", pattern: /\bMOCK\b/g },
  { kind: "decimal-precision", pattern: /(?:^|[^\d])[-+]?\d+[.,]\d{4,}\b/g },
  { kind: "percent-precision", pattern: /\b\d+[.,]\d{3,}\s*%/g },
];

function sampleAround(text: string, index: number, length: number): string {
  const start = Math.max(0, index - 60);
  const end = Math.min(text.length, index + length + 60);
  return text.slice(start, end).replace(/\s+/g, " ").trim();
}

export function detectTextFindings(text: string): TextFinding[] {
  const findings: TextFinding[] = [];
  for (const detector of DETECTORS) {
    for (const match of text.matchAll(detector.pattern)) {
      const value = match[0].trim();
      if (!value) continue;
      if (detector.include && !detector.include(value, text)) continue;
      findings.push({
        kind: detector.kind,
        match: value,
        sample: sampleAround(text, match.index ?? 0, value.length),
      });
    }
  }
  return findings;
}

export function summarizeFindings(
  captures: readonly { routeId: string; findings: readonly { kind: string; sample?: string }[] }[],
): { key: string; count: number; routes: string[]; sample: string }[] {
  const grouped = new Map<string, { count: number; routes: Set<string>; sample: string }>();
  for (const capture of captures) {
    for (const finding of capture.findings) {
      const key = finding.kind;
      const current = grouped.get(key) ?? { count: 0, routes: new Set<string>(), sample: "" };
      current.count += 1;
      current.routes.add(capture.routeId);
      if (!current.sample && finding.sample) current.sample = finding.sample;
      grouped.set(key, current);
    }
  }
  return [...grouped.entries()]
    .map(([key, value]) => ({
      key,
      count: value.count,
      routes: [...value.routes].sort(),
      sample: value.sample,
    }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}
