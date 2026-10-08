import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const HERE = dirname(fileURLToPath(import.meta.url));
const SUPA = "http://127.0.0.1:25321";
const BASE = "http://127.0.0.1:5173";
const ANON = readFileSync("/tmp/supa.env", "utf8")
  .split("\n")
  .find((l) => l.startsWith("ANON_KEY"))
  .split('"')[1];
const PW = "Demo-Fixture-2026!";
const EMAILS = {
  owner: "demo-owner@fixture.dekopen.local",
  estimator: "demo-estimator@fixture.dekopen.local",
  manager: "demo-manager@fixture.dekopen.local",
  operator: "demo-operator@fixture.dekopen.local",
  installer: "demo-installer@fixture.dekopen.local",
};
mkdirSync(join(HERE, "ux-capture", ".auth"), { recursive: true });
for (const [role, email] of Object.entries(EMAILS)) {
  const r = await fetch(`${SUPA}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: ANON, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PW }),
  });
  const d = await r.json();
  if (!d.access_token) throw new Error(`grant ${role}: ${JSON.stringify(d)}`);
  const sess = {
    access_token: d.access_token,
    refresh_token: d.refresh_token,
    token_type: "bearer",
    expires_in: d.expires_in,
    expires_at: Math.floor(Date.now() / 1000) + d.expires_in,
    user: d.user,
  };
  const state = {
    cookies: [],
    origins: [
      { origin: BASE, localStorage: [{ name: "sb-127-auth-token", value: JSON.stringify(sess) }] },
    ],
  };
  writeFileSync(join(HERE, "ux-capture", ".auth", `${role}.json`), JSON.stringify(state));
  console.log("wrote", role);
}
