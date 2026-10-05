/// <reference types="node" />
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

/** Idempotency proof for scripts/dev_fixture.py (P00): running the fixture a
 * second time must not duplicate entities — the deterministic ids it reuses
 * keep every count stable. Runs inside `make test-db`'s live-stack window
 * (Django + Supabase + Mailpit are up; SUPABASE_* envs are set by the gate). */

const REPO = resolve(import.meta.dirname, "../../..");
const FIXTURE = resolve(REPO, "scripts/dev_fixture.py");
const STATE = resolve(REPO, ".fixture-state.json");

const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
const SUPABASE_URL = (process.env.SUPABASE_URL ?? "http://127.0.0.1:25321").replace(/\/$/, "");

async function fetchCount(orgId: string, table: string): Promise<number> {
  // Kong's docker proxy drops idle keep-alive sockets — fresh connection +
  // retry covers the "other side closed" flake seen on CI runners.
  let lastError: unknown;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const response = await fetch(
        `${SUPABASE_URL}/rest/v1/${table}?org_id=eq.${orgId}&select=id`,
        {
          headers: {
            apikey: SERVICE_KEY,
            Authorization: `Bearer ${SERVICE_KEY}`,
            Prefer: "count=exact",
            Range: "0-0",
            Connection: "close",
          },
        },
      );
      const range = response.headers.get("content-range") ?? "";
      return Number(range.split("/")[1] ?? "0");
    } catch (error) {
      lastError = error;
      await new Promise((done) => setTimeout(done, 500 * (attempt + 1)));
    }
  }
  throw lastError;
}

async function orgCounts(orgId: string): Promise<Record<string, number>> {
  const tables = [
    "clients",
    "projects",
    "project_positions",
    "orders",
    "customer_approvals",
    "suppliers",
    "tenancy_memberships",
  ];
  const counts: Record<string, number> = {};
  for (const table of tables) {
    counts[table] = await fetchCount(orgId, table);
  }
  return counts;
}

test.describe.configure({ mode: "serial" });

test("dev_fixture is idempotent — a second run duplicates nothing", async () => {
  test.setTimeout(420_000);
  expect(SERVICE_KEY, "SUPABASE_SERVICE_ROLE_KEY must be set by the gate").not.toBe("");

  // Local checkouts keep deps in .venv; CI installs them into system python.
  const venvPython = resolve(REPO, ".venv/bin/python");
  const python = existsSync(venvPython) ? venvPython : "python3";
  const run = () =>
    execFileSync(python, [FIXTURE], {
      cwd: REPO,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 360_000,
    });

  run();
  expect(existsSync(STATE), ".fixture-state.json must be written").toBe(true);
  const first = JSON.parse(readFileSync(STATE, "utf8")) as {
    org_id: string;
    projects: Record<string, { id: string }>;
    orders: Record<string, string>;
  };
  const countsBefore = await orgCounts(first.org_id);

  run();
  const second = JSON.parse(readFileSync(STATE, "utf8")) as typeof first;
  const countsAfter = await orgCounts(first.org_id);

  // Same ids — the fixture reuses entities instead of re-creating them.
  expect(second.org_id).toBe(first.org_id);
  for (const [slug, info] of Object.entries(first.projects)) {
    expect(second.projects[slug]?.id, `project ${slug} id changed`).toBe(info.id);
  }
  // Same counts — nothing duplicated on the second pass.
  expect(countsAfter).toEqual(countsBefore);
});
