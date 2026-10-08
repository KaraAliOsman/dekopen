import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
const SUPA = "http://127.0.0.1:25321",
  BASE = "http://127.0.0.1:5173";
const ANON = readFileSync("/tmp/supa.env", "utf8")
  .split("\n")
  .find((l) => l.startsWith("ANON_KEY"))
  .split('"')[1];
const r = await fetch(`${SUPA}/auth/v1/token?grant_type=password`, {
  method: "POST",
  headers: { apikey: ANON, "Content-Type": "application/json" },
  body: JSON.stringify({
    email: "demo-estimator@fixture.dekopen.local",
    password: "Demo-Fixture-2026!",
  }),
});
const d = await r.json();
const sess = {
  access_token: d.access_token,
  refresh_token: d.refresh_token,
  token_type: "bearer",
  expires_in: d.expires_in,
  expires_at: Math.floor(Date.now() / 1000) + d.expires_in,
  user: d.user,
};
const keys = [
  "sb-127-auth-token",
  "sb-127-0-0-1-auth-token",
  "sb-127-0-0-1-25321-auth-token",
  "supabase.auth.token",
];
const browser = await chromium.launch();
for (const k of keys) {
  const ctx = await browser.newContext({
    storageState: {
      cookies: [],
      origins: [{ origin: BASE, localStorage: [{ name: k, value: JSON.stringify(sess) }] }],
    },
  });
  const p = await ctx.newPage();
  await p.goto(BASE + "/dashboard", { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(3500);
  console.log(k, "=>", p.url());
  await ctx.close();
}
await browser.close();
