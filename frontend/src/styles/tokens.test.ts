/**
 * Tests de tokens — la constitución hecha contrato:
 *
 * 1. Ningún `var(--x)` en frontend/src puede referirse a una variable que no
 *    exista (ni en :root, ni en bloques de tema/densidad). Una variable
 *    fantasma es un estilo roto silencioso — hoy había 36.
 * 2. Las variables definidas en tokens.css que nadie usa deben estar en la
 *    línea base tokens.unused.txt; añadir tokens nuevos sin uso exige
 *    actualizarla a conciencia.
 * 3. Los pares texto/fondo declarados por rol mantienen contraste WCAG AA
 *    (≥ 4.5 texto normal, ≥ 3 texto grande/controles) en ambos temas.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = join(HERE, "..");
const TOKENS_FILE = join(HERE, "tokens.css");
const UNUSED_BASELINE = join(HERE, "tokens.unused.txt");

const VAR_DEF_RE = /(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g;
const VAR_USE_RE = /var\(\s*(--[a-zA-Z0-9-]+)/g;
/** Referencia completa `var(--x)` para resolver cadenas en valores. */
const VAR_REF_RE = /var\(\s*(--[a-zA-Z0-9-]+)\s*\)/g;

type ThemeName = "light" | "dark";

function collectSources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) out.push(...collectSources(full));
    else if (/\.(css|tsx?|html)$/.test(entry)) out.push(full);
  }
  return out;
}

function definedInBlock(css: string, scopePattern: RegExp): Map<string, string> {
  const map = new Map<string, string>();
  for (const match of css.matchAll(scopePattern)) {
    const body = match[1] ?? "";
    for (const d of body.matchAll(VAR_DEF_RE)) map.set(d[1] ?? "", (d[2] ?? "").trim());
  }
  return map;
}

/** Declaraciones de :root "plano" (fuera de selectores de tema/densidad). */
function rootBlock(css: string): Map<string, string> {
  const map = new Map<string, string>();
  // ":root {" o ":root,\n[otro-selector] {" — no ":root[atributo] {".
  const re = /:root(?:\s*,[^{}]*)?\s*\{/g;
  for (const m of css.matchAll(re)) {
    const start = m.index + m[0].length;
    let depth = 1;
    let i = start;
    while (i < css.length && depth > 0) {
      if (css[i] === "{") depth += 1;
      if (css[i] === "}") depth -= 1;
      i += 1;
    }
    for (const d of css.slice(start, i - 1).matchAll(VAR_DEF_RE)) {
      map.set(d[1] ?? "", (d[2] ?? "").trim());
    }
  }
  return map;
}

function themedBlock(css: string, theme: ThemeName): Map<string, string> {
  // Bloques como ":root[data-theme="dark"], [data-theme-scope="dark"] { ... }"
  const re = new RegExp(`\\[data-theme(?:-scope)?="${theme}"\\][^{]*\\{([^}]*)\\}`, "g");
  return definedInBlock(css, re);
}

function resolveVar(
  name: string,
  scope: Map<string, string>,
  seen = new Set<string>(),
): string | undefined {
  const raw = scope.get(name);
  if (raw === undefined) return raw;
  if (seen.has(name)) return raw;
  seen.add(name);
  return raw.replace(VAR_REF_RE, (_all, dep: string) => {
    const resolved = resolveVar(dep, scope, seen);
    return resolved === undefined ? `var(${dep})` : resolved;
  });
}

function hexToRgb(hex: string): [number, number, number] | null {
  const m = hex.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i);
  if (!m || !m[1]) return null;
  let h = m[1];
  if (h.length === 8) h = h.slice(0, 6);
  if (h.length === 3)
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function luminance([r, g, b]: [number, number, number]): number {
  const f = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

export function contrastRatio(fg: string, bg: string): number | null {
  const a = hexToRgb(fg);
  const b = hexToRgb(bg);
  if (!a || !b) return null;
  const l1 = luminance(a);
  const l2 = luminance(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

const css = readFileSync(TOKENS_FILE, "utf8");

describe("tokens.css", () => {
  it("todo var(--x) usado en src está definido", () => {
    const root = rootBlock(css);
    const dark = themedBlock(css, "dark");
    const light = themedBlock(css, "light");
    const defined = new Set([...root.keys(), ...dark.keys(), ...light.keys()]);
    const missing = new Map<string, string[]>();
    for (const file of collectSources(SRC_ROOT)) {
      if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) continue;
      const text = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
      for (const m of text.matchAll(VAR_USE_RE)) {
        const name = m[1] ?? "";
        if (!defined.has(name)) {
          const rel = relative(join(SRC_ROOT, ".."), file);
          missing.set(rel, [...(missing.get(rel) ?? []), name]);
        }
      }
    }
    const details = [...missing.entries()]
      .map(([f, vars]) => `${f}: ${[...new Set(vars)].join(", ")}`)
      .join("\n");
    expect(details, `variables usadas pero nunca definidas:\n${details}`).toBe("");
  });

  it("sin variables muertas nuevas (ratchet con línea base)", () => {
    const root = rootBlock(css);
    const defined = new Set([...root.keys(), ...themedBlock(css, "dark").keys()]);
    const used = new Set<string>();
    for (const file of collectSources(SRC_ROOT)) {
      for (const m of readFileSync(file, "utf8").matchAll(VAR_USE_RE)) used.add(m[1] ?? "");
    }
    // var() dentro de tokens.css también cuenta como uso (roles → rampas).
    for (const m of css.matchAll(VAR_USE_RE)) used.add(m[1] ?? "");
    const baseline = new Set(
      readFileSync(UNUSED_BASELINE, "utf8")
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("#")),
    );
    const newUnused = [...defined].filter((v) => !used.has(v) && !baseline.has(v));
    expect(
      newUnused,
      `tokens definidos sin uso y fuera de la línea base:\n${newUnused.join("\n")}`,
    ).toEqual([]);
  });

  it.each(["light", "dark"] as const)("los roles texto/fondo mantienen AA en tema %s", (theme) => {
    const scope = new Map([...rootBlock(css), ...themedBlock(css, theme)]);
    const get = (name: string) => resolveVar(name, scope) ?? "";
    // [texto, fondo, mínimo] — mínimo 4.5 normal, 3 para
    // texto grande/controles y gráficos del lienzo.
    const pairs: Array<[string, string, number]> = [
      ["--text-primary", "--bg-app", 4.5],
      ["--text-primary", "--surface-panel", 4.5],
      ["--text-primary", "--surface-card", 4.5],
      ["--text-primary", "--surface-sheet", 4.5],
      ["--text-secondary", "--bg-app", 4.5],
      ["--text-secondary", "--surface-panel", 4.5],
      ["--text-secondary", "--surface-card", 4.5],
      ["--text-secondary", "--surface-sheet", 4.5],
      ["--text-muted", "--bg-app", 4.5],
      ["--text-muted", "--surface-panel", 4.5],
      ["--interactive", "--bg-app", 4.5],
      ["--interactive", "--surface-panel", 4.5],
      ["--interactive", "--surface-sheet", 4.5],
      ["--on-interactive-fill", "--interactive-fill", 4.5],
      ["--on-mark", "--mark", 3],
      ["--ok-ink", "--ok-soft", 4.5],
      ["--warn-ink", "--warn-soft", 4.5],
      ["--danger-ink", "--danger-soft", 4.5],
      ["--info-ink", "--info-soft", 4.5],
      ["--person-ink", "--person-soft", 4.5],
      ["--canvas-dim", "--canvas-paper", 4.5],
      ["--canvas-profile", "--canvas-paper", 3],
      ["--canvas-symbol", "--canvas-paper", 3],
      ["--canvas-selection", "--canvas-paper", 3],
      ["--canvas-handle", "--canvas-handle-edge", 3],
    ];
    const failures: string[] = [];
    for (const [fg, bg, min] of pairs) {
      const ratio = contrastRatio(get(fg), get(bg));
      if (ratio === null) {
        failures.push(`${fg} sobre ${bg}: no se pudo resolver a hex`);
      } else if (ratio < min) {
        failures.push(`${fg} (${get(fg)}) sobre ${bg} (${get(bg)}): ${ratio.toFixed(2)} < ${min}`);
      }
    }
    expect(failures).toEqual([]);
  });
});
