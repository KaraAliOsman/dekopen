/** Per-role login machinery for ux:capture: real Mailpit magic-link logins,
 * org selection, and TOTP enroll/challenge/verify for the aal2-gated OWNER.
 * Sessions are captured once per role and reused via storageState.
 */
import * as OTPAuth from "otpauth";
import type { Page } from "@playwright/test";

const SUPABASE_URL = process.env.SUPABASE_URL ?? "http://127.0.0.1:25321";
const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://127.0.0.1:25324";
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";

const seenMessages = new Set<string>();

async function waitForMagicLink(recipient: string, notBeforeMs: number, timeoutMs = 45_000) {
  const deadline = Date.now() + timeoutMs;
  const expectedOrigin = new URL(SUPABASE_URL).origin;
  while (Date.now() < deadline) {
    const list = await fetch(`${MAILPIT_URL}/api/v1/messages`);
    const payload = (await list.json()) as {
      messages: { ID: string; Created: string; To: { Address: string }[] }[];
    };
    for (const message of payload.messages) {
      if (seenMessages.has(message.ID)) continue;
      if (message.Created && Date.parse(message.Created) < notBeforeMs) continue;
      const to = (message.To ?? []).map((t) => t.Address?.toLowerCase());
      if (!to.includes(recipient.toLowerCase())) continue;
      const detail = await fetch(`${MAILPIT_URL}/api/v1/message/${message.ID}`);
      const body = (await detail.json()) as { HTML?: string; Text?: string };
      const content = `${body.HTML ?? ""}\n${body.Text ?? ""}`;
      const match = content.match(/href="([^"]+)"|(?:https?:\/\/\S+)/);
      if (!match) continue;
      const link = (match[1] ?? match[0]).replace(/&amp;/g, "&");
      if (
        link.startsWith(expectedOrigin) ||
        link.includes("access_token") ||
        link.includes("token_hash")
      ) {
        seenMessages.add(message.ID);
        return link;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`magic link for ${recipient} never arrived in Mailpit`);
}

async function adminUser(email: string): Promise<{ id: string } | undefined> {
  const users = await fetch(`${SUPABASE_URL}/auth/v1/admin/users?page=1&per_page=50`, {
    headers: {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
    },
  });
  const payload = (await users.json()) as {
    users: { id: string; email: string }[];
  };
  return (payload.users ?? []).find((u) => u.email.toLowerCase() === email.toLowerCase());
}

/** When a stale factor exists but its secret is lost, remove it so the
 * enroll path produces a fresh, storable secret. */
async function resetFactors(email: string) {
  const user = await adminUser(email);
  if (!user) return;
  const factors = await fetch(`${SUPABASE_URL}/auth/v1/admin/users/${user.id}/factors`, {
    headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` },
  });
  const body = (await factors.json()) as { factors?: { id: string }[] };
  for (const factor of body.factors ?? []) {
    await fetch(`${SUPABASE_URL}/auth/v1/admin/users/${user.id}/factors/${factor.id}`, {
      method: "DELETE",
      headers: {
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
      },
    });
  }
}

export type TotpVault = Record<string, string>;

/** Enroll (first factor) or challenge-verify (existing factor) on mfa-page. */
async function passMfa(page: Page, email: string, totp: TotpVault) {
  const enrollButton = page.getByRole("button", {
    name: "Configurar autenticador",
  });
  let secret = totp[email];
  if (await enrollButton.isVisible().catch(() => false)) {
    await enrollButton.click();
    const secretEl = page.getByTestId("totp-secret");
    await secretEl.waitFor({ timeout: 10_000 });
    secret = ((await secretEl.textContent()) ?? "").trim();
    totp[email] = secret;
  } else if (!secret) {
    throw new Error(`mfa challenge shown but no factor secret stored for ${email}`);
  }
  const generator = new OTPAuth.TOTP({
    issuer: "Dekopen",
    label: email,
    algorithm: "SHA1",
    digits: 6,
    period: 30,
    secret: OTPAuth.Secret.fromBase32(secret),
  });
  await page.getByLabel("Código de seis dígitos").fill(generator.generate());
  await page.getByRole("button", { name: "Verificar" }).click();
}

async function pickOrganization(page: Page, orgName?: string) {
  // memberships render asynchronously after the selector mounts; bail early
  // when the app moves on to the mfa gate before options are clickable.
  const option = orgName
    ? page.locator(".org-option", { hasText: orgName }).first()
    : page.locator(".org-option").first();
  const deadline = Date.now() + 25_000;
  while (Date.now() < deadline) {
    if (
      await page
        .getByTestId("mfa-page")
        .isVisible()
        .catch(() => false)
    )
      return;
    if (
      await page
        .getByTestId("app-shell")
        .isVisible()
        .catch(() => false)
    )
      return;
    if (await option.isVisible().catch(() => false)) {
      await option.click({ timeout: 5_000 });
      return;
    }
    await page.waitForTimeout(200);
  }
}

/** A magic-link failure lands on /auth/callback#error or back on /login with
 * no session — treat those as hard errors so no empty state gets saved. */
async function assertLoggedIn(page: Page, email: string) {
  const url = page.url();
  if (/error=|error_code=/.test(url) || /\/login/.test(url)) {
    throw new Error(`login failed for ${email}: ${url.slice(0, 160)}`);
  }
  const hasSession = await page.evaluate(() =>
    Object.keys(localStorage).some((k) => k.includes("auth-token")),
  );
  if (!hasSession) throw new Error(`no supabase session stored for ${email}`);
}

/** Full UI login: /login → magic link → org selector and/or TOTP in the order
 * the app presents them (me 409 → select → me 403 mfa_required → verify). */
export async function loginAs(
  page: Page,
  email: string,
  opts: { totp: TotpVault; orgName?: string },
  retried = false,
): Promise<void> {
  const sendLink = async () => {
    await page.goto("/login");
    await page.locator("#email").fill(email);
    const sentAt = Date.now();
    await page.getByRole("button", { name: /Enviar|magic/i }).click();
    const link = await waitForMagicLink(email, sentAt - 1_500);
    await page.goto(link);
  };
  await sendLink();

  const selector = page.getByTestId("organization-selector");
  const mfa = page.getByTestId("mfa-page");
  const shell = page.getByTestId("app-shell");
  const deadline = Date.now() + 60_000;
  let mfaPasses = 0;
  let orgPicks = 0;
  let lastState = "";
  while (Date.now() < deadline) {
    const state = `${await selector.isVisible().catch(() => false)}|${await mfa.isVisible().catch(() => false)}|${await shell.isVisible().catch(() => false)}|${page.url()}`;
    if (state !== lastState) {
      lastState = state;
      console.log(`  [login ${email}] sel|mfa|shell|url = ${state}`);
    }
    if (await shell.isVisible().catch(() => false)) {
      await assertLoggedIn(page, email);
      return;
    }
    if (await selector.isVisible().catch(() => false)) {
      if (++orgPicks > 2) break;
      await pickOrganization(page, opts.orgName);
      await page.waitForTimeout(400);
      continue;
    }
    if (await mfa.isVisible().catch(() => false)) {
      if (++mfaPasses > 2) break;
      try {
        await passMfa(page, email, opts.totp);
      } catch (error) {
        if (retried) throw error;
        // Stored secret belongs to a replaced factor — re-enroll fresh.
        delete opts.totp[email];
        await resetFactors(email);
        await loginAs(page, email, opts, true);
        return;
      }
      await page.waitForTimeout(400);
      continue;
    }
    await page.waitForTimeout(250);
  }
  const text = await page.evaluate(() => document.body.innerText.slice(0, 200));
  throw new Error(`login for ${email} stalled at ${page.url()} · page: ${JSON.stringify(text)}`);
}
