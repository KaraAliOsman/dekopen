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
  | "emoji"
  | "exclamation"
  | "decimal-4plus"
  | "percent-3plus"
  | "overflow-x"
  | "font-too-small"
  | "touch-too-small"
  | "primary-multi"
  | "radius-too-big"
  | "shadow-offscale"
  | "gradient"
  | "blur"
  | "contrast-aa"
  | "bare-interactive"
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
const EMOJI_RE = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{1F1E6}-\u{1F1FF}]/u;
// ¡ o ! en un nodo de texto visible — la voz §4 los prohíbe.
const EXCLAMATION_RE = /[¡!]/;

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
    if (EMOJI_RE.test(token)) pushOnce(out, "emoji", token);
  }
  if (EXCLAMATION_RE.test(text)) pushOnce(out, "exclamation", text.trim().slice(0, 60));
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
  /** §10 extended probes — all optional so old captures still parse. */
  /** max computed corner radius in px */
  radiusPx?: number;
  /** computed box-shadow ("none" or the value) */
  shadow?: string;
  /** computed background-image contains a gradient */
  gradient?: boolean;
  /** backdrop-filter or filter:blur computed */
  blur?: boolean;
  /** computed text color */
  color?: string;
  /** effective background color walking ancestors */
  bgColor?: string;
  /** font-weight numeric */
  weight?: number;
  /** element text (trimmed, for contrast/English checks) */
  text?: string;
  /** cursor: pointer on a non-semantic element */
  cursorPointer?: boolean;
  /** is a primary action */
  primary?: boolean;
  /** data-region name the element belongs to */
  region?: string;
  /** inside a data-density="workshop" surface */
  workshop?: boolean;
  /** :disabled o aria-disabled — WCAG exime el contraste de controles
   * inactivos, así que el detector contrast-aa los omite. */
  disabled?: boolean;
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

/* ---------- §10: computed-style slop detectors ---------- */

/** Computed radius > 4 px. A pill (radius ≈ half the short side) is legal —
 * sólo para puntos de estado — así que el chequeo es "radio grande pero no
 * pastilla": 4px < r < min(w,h)/2. */
export function isRadiusOffScale(box: BoxProbe): boolean {
  const r = box.radiusPx ?? 0;
  if (r <= 4) return false;
  const short = Math.min(box.widthPx, box.heightPx);
  return r * 2 < short - 0.5;
}

/** box-shadow fuera de la escala --e1/e2/e3/--sheet: cualquier sombra
 * computada que no sea "none". El navegador ya resolvió el var(), así que
 * comparamos contra los valores conocidos de la escala. */
export const KNOWN_SHADOWS = new Set([
  "none",
  // --shadow-e2 claro / oscuro
  "rgb(22, 28, 31, 0.05) 0px 1px 2px 0px, rgb(22, 28, 31, 0.08) 0px 4px 12px 0px",
  "rgba(22, 28, 31, 0.05) 0px 1px 2px 0px, rgba(22, 28, 31, 0.08) 0px 4px 12px 0px",
  "rgb(0, 0, 0, 0.45) 0px 1px 2px 0px, rgb(0, 0, 0, 0.5) 0px 4px 12px 0px",
  "rgba(0, 0, 0, 0.45) 0px 1px 2px 0px, rgba(0, 0, 0, 0.5) 0px 4px 12px 0px",
  // --shadow-e3
  "rgb(22, 28, 31, 0.06) 0px 2px 6px 0px, rgb(22, 28, 31, 0.14) 0px 12px 32px 0px",
  "rgba(22, 28, 31, 0.06) 0px 2px 6px 0px, rgba(22, 28, 31, 0.14) 0px 12px 32px 0px",
  "rgb(0, 0, 0, 0.5) 0px 2px 6px 0px, rgb(0, 0, 0, 0.6) 0px 12px 32px 0px",
  "rgba(0, 0, 0, 0.5) 0px 2px 6px 0px, rgba(0, 0, 0, 0.6) 0px 12px 32px 0px",
  // --shadow-sheet
  "rgb(22, 28, 31, 0.07) 0px 1px 3px 0px",
  "rgba(22, 28, 31, 0.07) 0px 1px 3px 0px",
  "rgb(0, 0, 0, 0.5) 0px 1px 3px 0px",
  "rgba(0, 0, 0, 0.5) 0px 1px 3px 0px",
]);

const SHADOW_LAYER_SPLIT = /,(?![^(]*\))/;

/** A spread-only "shadow" is a focus/separator ring (0 offset + 0 blur) —
 * border under another name, not elevation. */
const SPREAD_ONLY_LAYER_RE = /^rgba?\([^)]*\)\s+0px\s+0px\s+0px(\s+-?\d*\.?\d+px)?(\s+inset)?$/;

export function isShadowOffScale(box: BoxProbe): boolean {
  const shadow = (box.shadow ?? "none").trim();
  if (shadow === "none" || shadow === "") return false;
  if (KNOWN_SHADOWS.has(shadow)) return false;
  const layers = shadow.split(SHADOW_LAYER_SPLIT).map((l) => l.trim());
  return !layers.every((l) => SPREAD_ONLY_LAYER_RE.test(l) || l.startsWith("0px 0px 0px"));
}

/** Relación de contraste WCAG entre dos colores rgb()/rgba(). */
export function contrastOf(fg: string, bg: string): number | null {
  const parse = (value: string): readonly [number, number, number] | null => {
    const m = /rgba?\(([^)]+)\)/.exec(value);
    if (!m?.[1]) return null;
    const [r, g, b] = m[1]
      .split(/[\s,/]+/)
      .filter(Boolean)
      .map(Number);
    if (![r, g, b].every((n) => Number.isFinite(n))) return null;
    return [r as number, g as number, b as number] as const;
  };
  const a = parse(fg);
  const b = parse(bg);
  if (!a || !b) return null;
  const lum = ([r, g, bl]: readonly [number, number, number]) => {
    const f = (c: number) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl);
  };
  const l1 = lum(a);
  const l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

/** Detectores de estilo computado — radios, sombras, degradados, blur,
 * contraste real y objetivos de taller. Corre una vez por captura sobre
 * las cajas del probe. */
export function scanStyles(boxes: BoxProbe[]): Finding[] {
  const findings: Finding[] = [];
  const seen = new Set<string>();
  const push = (kind: FindingKind, detail: string) => {
    if (seen.has(`${kind}:${detail}`)) return;
    seen.add(`${kind}:${detail}`);
    findings.push({ kind, detail: detail.slice(0, 140) });
  };
  const regions = new Map<string, string[]>();
  for (const box of boxes) {
    if (box.region && box.primary) {
      const list = regions.get(box.region) ?? [];
      list.push(box.label);
      regions.set(box.region, list);
    }
    if (isRadiusOffScale(box)) {
      push("radius-too-big", `${box.label} · ${box.radiusPx?.toFixed(1)}px`);
    }
    if (isShadowOffScale(box)) {
      push("shadow-offscale", `${box.label} · ${(box.shadow ?? "").slice(0, 80)}`);
    }
    if (box.gradient) push("gradient", box.label);
    if (box.blur) push("blur", box.label);
    if (box.workshop && box.interactive && (box.widthPx < 44 || box.heightPx < 44)) {
      push(
        "touch-too-small",
        `${box.label} · ${box.widthPx.toFixed(0)}×${box.heightPx.toFixed(0)}px (taller)`,
      );
    }
    if (box.cursorPointer && !box.interactive) {
      push("bare-interactive", box.label);
    }
    // Contraste real: solo elementos que llevan texto y están activos
    // (los controles deshabilitados están exentos de AA por WCAG).
    if (box.text && box.color && box.bgColor && box.fontPx > 0 && !box.disabled) {
      const ratio = contrastOf(box.color, box.bgColor);
      const large = box.fontPx >= 18.66 || (box.fontPx >= 14 && (box.weight ?? 400) >= 700);
      const min = large ? 3 : 4.5;
      if (ratio !== null && ratio < min) {
        push(
          "contrast-aa",
          `${box.label} · ${ratio.toFixed(2)} < ${min} (${box.color} sobre ${box.bgColor})`,
        );
      }
    }
  }
  for (const [region, labels] of regions) {
    if (labels.length > 1) {
      push(
        "primary-multi",
        `${region}: ${labels.length} primarias (${labels.slice(0, 3).join(", ")})`,
      );
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
