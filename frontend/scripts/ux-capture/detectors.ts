/** Pure leak/noise detectors for the ux:capture harness.
 *
 * Every detector is a pure function over strings or layout numbers so the
 * same rules run in the browser probe and in vitest without a DOM.
 */

export type FindingKind =
  | "uuid"
  | "long-hex"
  | "object-object"
  | "undefined-word"
  | "enum-token"
  | "english-word"
  | "mock-word"
  | "decimal-4plus"
  | "percent-3plus"
  | "overflow-x"
  | "font-too-small"
  | "touch-too-small"
  | "console-error"
  | "http-error";

export type Finding = {
  kind: FindingKind;
  /** Exact offending token/snippet, kept short for the report. */
  detail: string;
};

const UUID_RE = /\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b/;
const LONG_HEX_RE = /\b[0-9a-f]{10,}\b/;
const OBJECT_OBJECT = "[object Object]";
const UNDEFINED_WORD_RE = /\b(undefined|NaN|null)\b/;
const ENUM_TOKEN_RE = /\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/;
const DECIMAL_4PLUS_RE = /\d+\.\d{4,}\b/;
const PERCENT_3PLUS_RE = /\d+\.\d{3,}\s*%/;

/** English words that would betray untranslated validation/copy. */
const ENGLISH_WORDS = new Set([
  // "error" is intentionally absent — it is also Spanish.
  "required",
  "invalid",
  "password",
  "submit",
  "cancel",
  "loading",
  "success",
  "warning",
  "delete",
  "edit",
  "save",
  "search",
]);

/** Tokens the enum detector must never flag — real customer-facing codes. */
const ENUM_ALLOWLIST = new Set(["RUT", "OT", "QC", "IVA", "CLP", "PDF", "CNC", "DXF"]);

/** A revision/work-order code like COT-P-000001-REV-A or OT-P-000017-REV-A-05
 * contains underscores-free segments — REV_A inside it must not fire. */
const CODE_LIKE_RE = /\b[A-Z]{2,4}-[A-Z]?-?\d{4,}(-[A-Z0-9-]+)*\b/;

function pushOnce(findings: Finding[], kind: FindingKind, detail: string) {
  findings.push({ kind, detail: detail.slice(0, 120) });
}

/** Scan one text node's content for leaked technical strings. */
export function scanText(text: string, out: Finding[] = []): Finding[] {
  // Multi-token patterns need the whole fragment, not per-word tokens.
  if (text.includes(OBJECT_OBJECT)) pushOnce(out, "object-object", OBJECT_OBJECT);
  {
    const percent = text.match(PERCENT_3PLUS_RE);
    if (percent) pushOnce(out, "percent-3plus", percent[0]);
  }
  for (const raw of text.split(/\s+/)) {
    const token = raw.trim();
    if (!token) continue;
    if (CODE_LIKE_RE.test(token)) continue;
    if (UUID_RE.test(token)) pushOnce(out, "uuid", token);
    else if (LONG_HEX_RE.test(token)) pushOnce(out, "long-hex", token);
    if (UNDEFINED_WORD_RE.test(token)) pushOnce(out, "undefined-word", token);
    if (
      ENUM_TOKEN_RE.test(token) &&
      !ENUM_ALLOWLIST.has(token) &&
      !/^(REV|REV-[A-Z]+)$/.test(token)
    ) {
      pushOnce(out, "enum-token", token);
    }
    if (/^mock$/i.test(token) || /\bmock\b/i.test(token)) {
      pushOnce(out, "mock-word", token);
    }
    if (DECIMAL_4PLUS_RE.test(token)) pushOnce(out, "decimal-4plus", token);
  }
  const lower = ` ${text.toLowerCase()} `;
  for (const word of ENGLISH_WORDS) {
    if (new RegExp(`\\b${word}\\b`).test(lower)) {
      pushOnce(out, "english-word", word);
      break; // one english finding per text node is enough signal
    }
  }
  return out;
}

/** Whole-document visible text scan — deduped findings. */
export function scanVisibleText(text: string): Finding[] {
  const raw = scanText(text);
  const seen = new Set<string>();
  return raw.filter((f) => {
    const key = `${f.kind}:${f.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export type BoxProbe = {
  /** short human label for the report (tag + text snippet) */
  label: string;
  fontPx: number;
  widthPx: number;
  heightPx: number;
  /** interactive element (button/a/input/[role]) */
  interactive: boolean;
};

export function scanLayout(
  scrollWidth: number,
  clientWidth: number,
  boxes: BoxProbe[],
  { touchAudit }: { touchAudit: boolean },
): Finding[] {
  const findings: Finding[] = [];
  if (scrollWidth > clientWidth + 1) {
    findings.push({
      kind: "overflow-x",
      detail: `scrollWidth ${scrollWidth} > clientWidth ${clientWidth}`,
    });
  }
  const seen = new Set<string>();
  for (const box of boxes) {
    if (box.fontPx > 0 && box.fontPx < 11) {
      const key = `font:${box.label}`;
      if (!seen.has(key)) {
        seen.add(key);
        findings.push({
          kind: "font-too-small",
          detail: `${box.label} · ${box.fontPx.toFixed(1)}px`,
        });
      }
    }
    if (touchAudit && box.interactive && (box.widthPx < 44 || box.heightPx < 44)) {
      const key = `touch:${box.label}`;
      if (!seen.has(key)) {
        seen.add(key);
        findings.push({
          kind: "touch-too-small",
          detail: `${box.label} · ${box.widthPx.toFixed(0)}×${box.heightPx.toFixed(0)}px`,
        });
      }
    }
  }
  return findings;
}

export function scanConsoleEntries(entries: { level: string; text: string }[]): Finding[] {
  return entries
    .filter((e) => e.level === "error" || /uncaught|failed to load|net::err/i.test(e.text))
    .map((e) => ({ kind: "console-error", detail: e.text.slice(0, 160) }));
}

export function scanHttpEntries(entries: { url: string; status: number }[]): Finding[] {
  return entries
    .filter((e) => e.status >= 400)
    .map((e) => ({
      kind: "http-error",
      detail: `${e.status} ${e.url.slice(0, 140)}`,
    }));
}
