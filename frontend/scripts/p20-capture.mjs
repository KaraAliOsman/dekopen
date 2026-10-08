// P20 capture — session-injected screenshots per role/route for acceptance evidence.
import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const REPO = "/home/ubuntu/repos/dekopen";
const BASE = process.env.BASE || "http://127.0.0.1:5173";
const SUPA = "http://127.0.0.1:25321";
const ANON = readFileSync("/tmp/supa.env", "utf8")
  .split("\n")
  .find((l) => l.startsWith("ANON_KEY"))
  .split('"')[1];
const OUT = process.env.OUT || join(REPO, "docs/redesign/captures/p20-aceptacion");
const STATE = JSON.parse(readFileSync(join(REPO, ".fixture-state.json"), "utf8"));
const PW = "Demo-Fixture-2026!";
const EMAILS = {
  owner: "demo-owner@fixture.dekopen.local",
  estimator: "demo-estimator@fixture.dekopen.local",
  manager: "demo-manager@fixture.dekopen.local",
  operator: "demo-operator@fixture.dekopen.local",
  installer: "demo-installer@fixture.dekopen.local",
  multi: "demo-multi@fixture.dekopen.local",
};

async function grant(email) {
  const r = await fetch(`${SUPA}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: ANON, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PW }),
  });
  const d = await r.json();
  if (!d.access_token) throw new Error(`grant failed ${email}: ${JSON.stringify(d)}`);
  return d;
}

// supabase-js v2 default storageKey: sb-<first-hostname-segment>-auth-token
function storageKey() {
  const host = new URL(SUPA).hostname.split(".")[0];
  return `sb-${host}-auth-token`;
}

function storageState(session) {
  const sess = {
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    token_type: "bearer",
    expires_in: session.expires_in || 3600,
    expires_at: Math.floor(Date.now() / 1000) + (session.expires_in || 3600),
    user: session.user,
  };
  return {
    cookies: [],
    origins: [
      {
        origin: BASE,
        localStorage: [{ name: storageKey(), value: JSON.stringify(sess) }],
      },
    ],
  };
}

const interp = (s) =>
  s.replace(/\{\{([^}]+)\}\}/g, (_, p) => {
    const parts = p.split(".");
    let v = STATE;
    for (const k of parts) v = v?.[k];
    return typeof v === "string" ? v : (v?.id ?? v ?? "");
  });

async function main() {
  const specPath = process.argv[2];
  const spec = JSON.parse(readFileSync(specPath, "utf8"));
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const results = [];
  for (const role of spec.roles) {
    let session = await grant(EMAILS[role]);
    // Owner is aal2-gated: prefer the TOTP-verified session minted out-of-band.
    if (role === "owner" && existsSync(join(REPO, ".run/p20/owner_aal2.json"))) {
      const aal2 = JSON.parse(readFileSync(join(REPO, ".run/p20/owner_aal2.json"), "utf8"));
      session = {
        access_token: aal2.aal2,
        refresh_token: aal2.refresh,
        expires_in: 3600,
        user: aal2.user,
      };
    }
    const ss = storageState(session);
    const ctx = await browser.newContext({
      storageState: ss,
      viewport: spec.viewport || { width: 1440, height: 900 },
      colorScheme: spec.colorScheme || "light",
      locale: "es-CL",
    });
    const page = await ctx.newPage();
    for (const r of spec.routes) {
      const url = BASE + interp(r.path);
      const slug = `${role}__${(r.name || r.path).replace(/[^a-z0-9]+/gi, "_").slice(0, 60)}`;
      const shots = [];
      for (const vp of r.viewports || [spec.viewport || { width: 1440, height: 900 }]) {
        try {
          await page.setViewportSize(vp);
          await page.goto(url, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
          await page.waitForTimeout(r.wait || 1200);
          const file = join(OUT, "shots", `${slug}__${vp.width}x${vp.height}.png`);
          await page.screenshot({ path: file, fullPage: false });
          shots.push(file);
          results.push({ role, route: r.path, status: "ok", file });
        } catch (e) {
          results.push({ role, route: r.path, status: "error", err: String(e).slice(0, 200) });
        }
      }
      if (r.actions) {
        try {
          for (const a of r.actions) {
            if (a.click) await page.locator(a.click).first().click({ timeout: 4000 });
            if (a.fill) await page.locator(a.fill.sel).fill(a.fill.value);
            await page.waitForTimeout(a.wait || 800);
          }
          const file = join(OUT, "shots", `${slug}__after.png`);
          await page.screenshot({ path: file });
          shots.push(file);
        } catch (e) {
          results.push({
            role,
            route: r.path + "#actions",
            status: "error",
            err: String(e).slice(0, 200),
          });
        }
      }
      console.log(slug, shots.length ? "ok" : "ERR");
    }
    await ctx.close();
  }
  writeFileSync(join(OUT, "capture-results.json"), JSON.stringify(results, null, 1));
  await browser.close();
  console.log("done", results.length);
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
