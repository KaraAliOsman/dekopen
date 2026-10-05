#!/usr/bin/env node
/** ux:capture — screenshot + leak/noise audit across every declared route.
 *
 *   npm run ux:capture -- --out docs/redesign/captures/baseline-2026-10-05 \
 *       [--routes <glob>] [--roles owner,estimator,...] [--base http://127.0.0.1:5173]
 *
 * Requires: Vite dev server, Django API, Supabase stack + Mailpit, and a
 * seeded .fixture-state.json (scripts/dev_fixture.py).
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

import { loginAs, type TotpVault } from "./auth.ts";
import { runCaptures } from "./capture.ts";
import { writeReport } from "./report.ts";
import { ROUTES, type RouteRole } from "./routes.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../..");
const STATE_PATH = process.env.FIXTURE_STATE ?? join(REPO, ".fixture-state.json");
const DEFAULT_OUT = join(
  REPO,
  "docs/redesign/captures",
  `baseline-${new Date().toISOString().slice(0, 10)}`,
);

type Args = {
  out: string;
  routes?: string;
  roles?: string[];
  base: string;
};

function parseArgs(): Args {
  const args = process.argv.slice(2);
  const out: Args = {
    out: DEFAULT_OUT,
    base: process.env.UX_BASE_URL ?? "http://127.0.0.1:5173",
  };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    const next = () => args[++i];
    if (arg === "--out") out.out = resolve(next());
    else if (arg === "--routes") out.routes = next();
    else if (arg === "--roles")
      out.roles = next()
        .split(",")
        .map((r) => r.trim());
    else if (arg === "--base") out.base = next();
    else {
      console.error(`unknown arg: ${arg}`);
      process.exit(2);
    }
  }
  return out;
}

/** {{a.b.c}} interpolation into .fixture-state.json values. */
function resolvePath(template: string, state: Record<string, unknown>): string {
  return template.replace(/\{\{([^}]+)\}\}/g, (_, keyPath: string) => {
    const parts = keyPath.trim().split(".");
    let node: unknown = state;
    for (const part of parts) {
      node = (node as Record<string, unknown>)?.[part];
    }
    if (typeof node !== "string" || !node) {
      throw new Error(`fixture state has no value for {{${keyPath}}}`);
    }
    return node;
  });
}

function globToRegExp(glob: string): RegExp {
  const escaped = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`^${escaped}$`);
}

async function main() {
  const args = parseArgs();
  if (!existsSync(STATE_PATH)) {
    console.error(`fixture state not found at ${STATE_PATH} — run scripts/dev_fixture.py first`);
    process.exit(1);
  }
  const state = JSON.parse(readFileSync(STATE_PATH, "utf8")) as Record<string, unknown>;
  const accounts = state.accounts as Record<string, { email: string; role: string }>;
  const totp = (state.totp ?? {}) as TotpVault;
  state.totp = totp;

  const routeFilter = args.routes ? globToRegExp(args.routes) : null;
  const roleFilter = args.roles ? new Set(args.roles) : null;
  const jobs = ROUTES.filter(
    (r) =>
      (!routeFilter || routeFilter.test(r.name) || routeFilter.test(r.path)) &&
      (!roleFilter || roleFilter.has(r.role)),
  ).map((r) => ({
    route: r.name,
    url: resolvePath(r.path, state),
    role: r.role,
    waitFor: r.waitFor,
    extraMobile: r.extraMobile,
    touchAudit: r.touchAudit,
  }));
  if (jobs.length === 0) {
    console.error("no routes matched the filters");
    process.exit(2);
  }

  mkdirSync(join(args.out, "shots"), { recursive: true });
  // Sessions carry live tokens — keep them inside the gitignored harness dir,
  // never under --out (which may be committed).
  const authDir = join(HERE, ".auth");
  mkdirSync(authDir, { recursive: true });

  // One real login per role — session persists as a playwright storageState.
  const needed = [...new Set(jobs.map((j) => j.role))].filter(
    (r): r is RouteRole => r !== "public",
  );
  const storageStates: Record<string, string> = {};
  const browser = await chromium.launch();
  for (const role of needed) {
    const email = accounts[role]?.email;
    if (!email) {
      console.error(`fixture state has no account for role ${role}`);
      continue;
    }
    const statePath = join(authDir, `${role}.json`);
    const context = await browser.newContext({ baseURL: args.base });
    const page = await context.newPage();
    try {
      await loginAs(page, email, {
        totp,

        orgName: (state.org_name as string | undefined) ?? undefined,
      });
      await context.storageState({ path: statePath });
      storageStates[role] = statePath;
      console.log(`login ${role}: ${email} ok`);
    } catch (error) {
      console.error(`login ${role} FAILED: ${String(error).slice(0, 300)}`);
    } finally {
      await context.close();
    }
  }
  await browser.close();
  writeFileSync(STATE_PATH, JSON.stringify(state, null, 2) + "\n");

  console.log(`capturing ${jobs.length} routes…`);
  const results = await runCaptures({
    baseUrl: args.base,
    jobs,
    storageStates,
    outDir: args.out,
  });
  writeReport(args.out, results);

  const findings = results.reduce((n, r) => n + r.findings.length, 0);
  console.log(`done: ${results.length} captures, ${findings} findings → ${args.out}`);
  if (findings > 0) {
    const top = results
      .filter((r) => r.findings.length)
      .slice(0, 10)
      .map((r) => `  ${r.route}: ${r.findings.length} (${r.role})`);
    console.log(`top findings:\n${top.join("\n")}`);
  }
}

await main();
