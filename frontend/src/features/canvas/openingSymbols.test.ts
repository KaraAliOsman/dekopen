/**
 * P05 — parity contract for opening symbology, TypeScript half.
 *
 * The JSON fixtures under `engine/tests/fixtures/symbols/` pin the
 * primitives AND the canonical path data the elevation renderers must
 * produce for a reference leaf box, in interior and exterior view. The
 * Python twin (`engine/tests/test_opening_symbols_p05.py`) exercises the
 * same files — a divergence on either side fails the suite. Regenerate
 * fixtures ONLY via `scripts/gen_symbol_fixtures.py` and review the diff.
 */
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  glyphPaths,
  leafPrimitives,
  slidingPrimitives,
  type GlyphPrimitive,
} from "./openingSymbols";
import type { OpeningSpecPayload, SlidingLayout } from "./intentEditing";

const FIXTURE_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../engine/tests/fixtures/symbols",
);
const FIXTURES = readdirSync(FIXTURE_DIR)
  .filter((name) => name.endsWith(".json"))
  .sort();

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

/** The engine serializes Decimal as a JSON string ("0.4", "1050") — the
 * comparison normalizes numeric strings to numbers like the Python twin. */
function canon(value: Json): Json {
  if (typeof value === "string") {
    return /^-?\d+(\.\d+)?$/.test(value) ? Number(value) : value;
  }
  if (Array.isArray(value)) return value.map(canon);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, canon(v)]));
  }
  return value;
}

const DEFAULT_PRIM: Required<Omit<GlyphPrimitive, never>> = {
  k: "none",
  hinge: null,
  apex_at: 0.4,
  dash: false,
  dir: null,
  inferred: false,
  side: null,
  at_mm: null,
};

function dumpPrim(prim: GlyphPrimitive): Json {
  const full = { ...DEFAULT_PRIM, ...prim };
  return canon({
    k: full.k,
    hinge: full.hinge,
    apex_at: full.apex_at,
    dash: full.dash,
    dir: full.dir,
    inferred: full.inferred,
    side: full.side,
    at_mm: full.at_mm,
  }) as Json;
}

interface LeafInput {
  movement: string;
  hinge_side?: string | null;
  direction?: string | null;
  leaf_role?: string;
  handle_mm?: number | null;
}

interface FixtureJson {
  id: string;
  name: string;
  box: { x: number; y: number; w: number; h: number };
  input: {
    kind: "leaves" | "sliding";
    unit: string;
    leaves?: LeafInput[];
    tracks?: number;
    panels?: { slot: string; kind: string; track: number | null; travel?: string | null }[];
  };
  views: Record<string, { stiles: number; leaves: { prims: Json; paths: Json }[] }>;
}

function actual(fixture: FixtureJson, view: "interior" | "exterior"): Json {
  const { input, box } = fixture;
  if (input.kind === "leaves") {
    const leaves = input.leaves ?? [];
    const leafW = box.w / leaves.length;
    return {
      stiles: Math.max(0, leaves.length - 1),
      leaves: leaves.map((leaf, index) => {
        const prims = leafPrimitives(leaf as unknown as OpeningSpecPayload, view, {
          unit: input.unit,
          handle_mm: leaf.handle_mm ?? null,
        });
        return {
          prims: prims.map(dumpPrim),
          paths: glyphPaths(prims, box.x + leafW * index, box.y, leafW, box.h, box.y + box.h).map(
            ({ d, dash }) => ({ d, dash }),
          ),
        };
      }),
    };
  }
  const layout: SlidingLayout = {
    tracks: input.tracks ?? 1,
    panels: (input.panels ?? []).map((panel) => ({
      slot: panel.slot,
      kind: panel.kind as "MOVING" | "FIXED",
      track: panel.track,
      travel: (panel.travel ?? null) as "LEFT" | "RIGHT" | null,
    })),
  };
  const allPrims = slidingPrimitives(layout, view);
  const leafW = box.w / allPrims.length;
  return {
    stiles: 0,
    leaves: allPrims.map((prims, index) => ({
      prims: prims.map(dumpPrim),
      paths: glyphPaths(prims, box.x + leafW * index, box.y, leafW, box.h, box.y + box.h).map(
        ({ d, dash }) => ({ d, dash }),
      ),
    })),
  };
}

describe("opening symbol parity (P05)", () => {
  it("covers the 13 base cases", () => {
    expect(FIXTURES.length).toBeGreaterThanOrEqual(13);
  });

  for (const file of FIXTURES) {
    const fixture = JSON.parse(readFileSync(join(FIXTURE_DIR, file), "utf-8")) as FixtureJson;
    for (const view of ["interior", "exterior"] as const) {
      it(`${fixture.id} — vista ${view}`, () => {
        expect(actual(fixture, view)).toEqual(canon(fixture.views[view] as unknown as Json));
      });
    }
  }
});
