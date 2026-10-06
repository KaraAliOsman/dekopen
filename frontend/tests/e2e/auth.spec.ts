import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";

import { formatMoney } from "../../src/format";
import { t } from "../../src/i18n/es-CL";
import { environment } from "./support/environment";
import { requireMailpitHealthy, waitForMagicLink } from "./support/mailpit";

const supabaseUrl = requiredEnvironment("SUPABASE_URL");
const anonKey = requiredEnvironment("SUPABASE_ANON_KEY");
const serviceRoleKey = requiredEnvironment("SUPABASE_SERVICE_ROLE_KEY");
const mailpitUrl = environment("MAILPIT_URL") ?? "http://127.0.0.1:25324";
const djangoUrl = environment("DJANGO_URL") ?? "http://127.0.0.1:8000";

type FixtureUser = {
  email: string;
  userId: string;
  organizationId: string;
};

const createdFixtures: FixtureUser[] = [];

test.beforeEach(async () => {
  await requireMailpitHealthy(mailpitUrl);
});

test.afterEach(async () => {
  for (const fixture of createdFixtures.splice(0)) {
    const organization = await fetch(
      `${supabaseUrl}/rest/v1/tenancy_organizations?id=eq.${fixture.organizationId}`,
      { method: "DELETE", headers: adminHeaders() },
    );
    expect([200, 204, 400, 403, 409]).toContain(organization.status);
    const user = await fetch(`${supabaseUrl}/auth/v1/admin/users/${fixture.userId}`, {
      method: "DELETE",
      headers: adminHeaders(),
    });
    expect(user.status).toBe(200);
  }
});

function requiredEnvironment(name: string): string {
  const value = environment(name);
  if (!value) throw new Error(`${name} is required for the real Supabase E2E`);
  return value;
}

function adminHeaders(): Record<string, string> {
  return {
    apikey: serviceRoleKey,
    Authorization: `Bearer ${serviceRoleKey}`,
    "Content-Type": "application/json",
  };
}

async function setupUser(
  role: "OWNER" | "ESTIMATOR",
  tier: "TRIAL" | "STARTER" = "TRIAL",
): Promise<FixtureUser> {
  const suffix = crypto.randomUUID();
  const email = `shot04-${role.toLowerCase()}-${suffix}@example.com`;
  const userResponse = await fetch(`${supabaseUrl}/auth/v1/admin/users`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ email, email_confirm: true }),
  });
  expect(userResponse.ok).toBe(true);
  const user = (await userResponse.json()) as { id: string };
  const organizationId = crypto.randomUUID();
  createdFixtures.push({ email, userId: user.id, organizationId });
  const organizationResponse = await fetch(`${supabaseUrl}/rest/v1/tenancy_organizations`, {
    method: "POST",
    headers: { ...adminHeaders(), Prefer: "return=minimal" },
    body: JSON.stringify({
      id: organizationId,
      name: `E2E ${role}`,
      tax_id: `E2E-${suffix}`,
      subscription_tier: tier,
    }),
  });
  expect(organizationResponse.ok).toBe(true);
  const membershipResponse = await fetch(`${supabaseUrl}/rest/v1/tenancy_memberships`, {
    method: "POST",
    headers: { ...adminHeaders(), Prefer: "return=minimal" },
    body: JSON.stringify({
      org_id: organizationId,
      user_id: user.id,
      role,
      is_active: true,
    }),
  });
  expect(membershipResponse.ok).toBe(true);
  return { email, userId: user.id, organizationId };
}

function latestMagicLink(
  email: string,
  previousMessageId: string | null = null,
): Promise<{ id: string; link: string }> {
  return waitForMagicLink({
    baseUrl: mailpitUrl,
    supabaseUrl,
    recipient: email,
    excludedMessageIds: new Set(previousMessageId ? [previousMessageId] : []),
  });
}

async function requestMagicLink(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Correo").fill(email);
  await page.getByRole("button", { name: "Enviar enlace de acceso" }).click();
  await expect(page.getByRole("status")).toContainText("Revisa tu correo para continuar");
}

async function accessToken(page: Page): Promise<string> {
  return page.evaluate(() => {
    for (const key of Object.keys(window.localStorage)) {
      if (!key.startsWith("sb-") || !key.endsWith("-auth-token")) continue;
      const raw = window.localStorage.getItem(key);
      if (!raw) continue;
      const parsed = JSON.parse(raw) as { access_token?: string };
      if (parsed.access_token) return parsed.access_token;
    }
    throw new Error("Supabase session was not persisted by the SPA");
  });
}

function tokenClaims(token: string): { sub: string; aal: string } {
  const payload = token.split(".")[1];
  if (!payload) throw new Error("Supabase did not issue a JWT access token");
  return JSON.parse(atob(payload.replaceAll("-", "+").replaceAll("_", "/"))) as {
    sub: string;
    aal: string;
  };
}

async function followRealMagicLink(page: Page, link: string): Promise<void> {
  const callback = page.waitForRequest(
    (request) =>
      request.isNavigationRequest() && new URL(request.url()).pathname === "/auth/callback",
  );
  await page.goto(link);
  await callback;
  // The callback resolves on navigation; the GoTrue session write lands
  // asynchronously after it — wait for the persisted token so callers can
  // read it deterministically.
  await page.waitForFunction(() =>
    Object.keys(window.localStorage).some(
      (key) => key.startsWith("sb-") && key.endsWith("-auth-token"),
    ),
  );
}

async function assertRealIdentity(
  page: Page,
  request: APIRequestContext,
  fixture: FixtureUser,
  aal: "aal1" | "aal2",
): Promise<void> {
  const token = await accessToken(page);
  const claims = tokenClaims(token);
  expect(claims.sub).toBe(fixture.userId);
  expect(claims.aal).toBe(aal);
  const actualUser = await request.get(`${supabaseUrl}/auth/v1/user`, {
    headers: { Authorization: `Bearer ${token}`, apikey: anonKey },
  });
  expect(actualUser.status()).toBe(200);
  expect((await actualUser.json()).id).toBe(fixture.userId);
  const direct = await request.get(`${djangoUrl}/api/v1/auth/me/`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Organization-ID": fixture.organizationId,
    },
  });
  expect(direct.status()).toBe(200);
  const me = await direct.json();
  expect(me.user.id).toBe(fixture.userId);
  expect(me.active_organization.id).toBe(fixture.organizationId);
  expect(me.aal).toBe(aal);
}

async function assertOwnerBlockedAtAal1(
  page: Page,
  request: APIRequestContext,
  fixture: FixtureUser,
): Promise<void> {
  const token = await accessToken(page);
  expect(tokenClaims(token).aal).toBe("aal1");
  const rejected = await request.get(`${djangoUrl}/api/v1/auth/me/`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Organization-ID": fixture.organizationId,
    },
  });
  expect(rejected.status()).toBe(403);
  expect((await rejected.json()).error).toEqual({
    code: "mfa_required",
    detail: "OWNER requires aal2",
    required_aal: "aal2",
  });
}

test("real Magic Link reaches Mailpit and authenticates Django /auth/me", async ({
  page,
  request,
}) => {
  const fixture = await setupUser("ESTIMATOR");
  await requestMagicLink(page, fixture.email);
  const message = await latestMagicLink(fixture.email);
  const authMeResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/me/") && response.status() === 200,
  );
  await followRealMagicLink(page, message.link);
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await authMeResponse;

  await assertRealIdentity(page, request, fixture, "aal1");

  const navigation = page.getByRole("navigation", { name: "Navegación principal" });
  // The rail mirrors the backend role sets: an ESTIMATOR sees the commercial
  // surfaces but never Catálogo (OWNER/WORKSHOP_MANAGER) nor Administración.
  await expect(navigation.getByRole("link", { name: "Catálogo", exact: true })).toHaveCount(0);
  await expect(navigation.getByRole("link", { name: "Administración", exact: true })).toHaveCount(
    0,
  );
  for (const route of ["Proyectos", "Clientes", "Inicio"]) {
    await navigation.getByRole("link", { name: route, exact: true }).click();
    await expect(page.getByTestId("app-shell")).toBeVisible();
  }
  const initialTheme = await page.locator("html").getAttribute("data-theme");
  await page.getByRole("button", { name: "Cambiar tema" }).click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    initialTheme === "light" ? "dark" : "light",
  );
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    initialTheme === "light" ? "dark" : "light",
  );
  await expect(page.getByTestId("app-shell")).toBeVisible();

  // A consumed email link must not create a second authenticated session.
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page.getByTestId("login-page")).toBeVisible();
  await page.goto(message.link);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByTestId("app-shell")).toHaveCount(0);
  await expect(accessToken(page)).rejects.toThrow("Supabase session was not persisted");
});

test("SHOT-10 OWNER prices and emits immutable quotation revisions", async ({ page, request }) => {
  test.setTimeout(240_000);
  const fixture = await setupUser("OWNER");
  await requestMagicLink(page, fixture.email);
  await followRealMagicLink(page, (await latestMagicLink(fixture.email)).link);
  await page.getByRole("button", { name: "Configurar autenticador" }).click();
  const secret = (await page.getByTestId("totp-secret").textContent())?.trim() ?? "";
  const generator = new OTPAuth.TOTP({
    algorithm: "SHA1",
    digits: 6,
    period: 30,
    secret: OTPAuth.Secret.fromBase32(secret),
  });
  await page.getByLabel("Código de seis dígitos").fill(generator.generate());
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await page.goto("/pricing/cost-lists");
  await page.getByLabel("Proveedor", { exact: true }).fill("SHOT08 real supplier");
  await page.getByLabel("Vigente desde", { exact: true }).fill("2026-09-01");
  await page
    .locator("form")
    .first()
    .getByLabel("Motivo del cambio")
    .fill("Independent real browser gate");
  await page.getByRole("button", { name: "Guardar cambio auditado", exact: true }).click();
  await expect(
    page.locator("article strong").filter({ hasText: "SHOT08 real supplier" }),
  ).toBeVisible();
  const headers = {
    Authorization: `Bearer ${await accessToken(page)}`,
    "X-Organization-ID": fixture.organizationId,
  };
  async function api(path: string, data: unknown): Promise<Record<string, unknown>> {
    const response = await request.post(`${djangoUrl}/api/v1/pricing/${path}`, { headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json() as Promise<Record<string, unknown>>;
  }
  const lists = await request.get(`${djangoUrl}/api/v1/pricing/admin/cost-lists/`, { headers });
  const listId = (await lists.json()).items[0].id as string;
  for (const [sku, unit] of [
    ["COMPRA-MARCO", "BAR"],
    ["COMPRA-JQ-24", "BAR"],
    // D02: la tarjeta VIDRIO-BASE fija la composición 4·16·4 (24 mm) → junquillo JQ-10.
    ["COMPRA-JQ-10", "BAR"],
    ["COMPRA-POSTE-V", "BAR"],
    ["COMPRA-ACERO-MARCO", "BAR"],
    ["COMPRA-ACERO-POSTE-V", "BAR"],
    ["VIDRIO-BASE", "M2"],
    ["TORNILLO-4X16", "EA"],
  ]) {
    await api("admin/cost-items/", {
      values: { cost_list_id: listId, sku, unit, item_type: "PROFILE", unit_cost: "100" },
      reason: "Explicit test catalog cost",
    });
  }
  await api("admin/rules/", {
    values: {
      pricing_mode: "COST_PLUS_MARGIN",
      default_margin_pct: "0.35",
      tax_rate_pct: "0.19",
      waste_factor_pct: "0.08",
      labor_rate_per_m2: "15",
      installation_rate_per_m2: "12",
    },
    reason: "Test commercial rules",
  });
  await page.goto("/projects");
  await page.getByRole("button", { name: "Crear proyecto", exact: true }).click();
  await page.getByLabel("Nombre del proyecto", { exact: true }).fill("Commercial browser gate");
  await page.getByLabel("Cliente", { exact: true }).fill("Synthetic fixture");
  const creation = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/projects/",
  );
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  const createdResponse = await creation;
  expect(createdResponse.status()).toBe(201);
  const draft = (await createdResponse.json()) as { id: string };
  await page.getByRole("link", { name: "Añadir vano", exact: true }).click();
  await page.getByLabel("Ubicación del vano", { exact: true }).fill("Fijo comercial");
  await page.getByLabel("Cantidad", { exact: true }).fill("2");
  // The series field lives in the strip's Serie chip popover (P04).
  await page.getByRole("button", { name: "Serie de perfiles", exact: true }).click();
  await page.getByRole("combobox", { name: "Serie de perfiles", exact: true }).selectOption({
    label: "Sistema Demo 60mm PVC — referencia sintética · Catálogo de demostración",
  });
  // Canvas-first editor: the single module is already selected on the drawing;
  // glazing choices live in its contextual inspector, not a separate form.
  await page.getByRole("combobox", { name: "Espesor de vidrio", exact: true }).selectOption("4.00");
  // D02: el catálogo de vidrios ahora se elige por tarjeta (su nombre comercial
  // es el aria-label), no por un combobox de SKUs.
  await page.getByRole("button", { name: "Termopanel incoloro 4·16·4", exact: true }).click();
  await expect(page.getByRole("button", { name: "Guardar", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  await expect(page.getByText("Guardado", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Volver al proyecto/ }).click();
  // React Query may serve the pre-save project from its fresh cache — the page
  // would still show "Añadir vano" instead of the quote next-action. Reload to
  // force the backend read that reflects the position just saved.
  await page.reload();
  await page.getByRole("link", { name: "Cotizar proyecto", exact: true }).click();
  await expect(page.getByLabel("Proyecto", { exact: true })).toHaveCount(0);
  await page.getByLabel("Fecha efectiva", { exact: true }).fill("2026-09-10");
  await page.getByLabel("Motivo del cambio", { exact: true }).fill("Apply browser quote");
  const previewResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/pricing/preview/"),
  );
  await page.getByRole("button", { name: "Calcular y revisar", exact: true }).click();
  const priced = await previewResponse;
  expect(priced.status(), await priced.text()).toBe(200);
  const quote = (await priced.json()) as {
    project_net: string;
    project_gross: string;
    project_tax: string;
  };
  await expect(
    page.getByRole("button", { name: "Aprobar y aplicar precios", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Aprobar y aplicar precios", exact: true }).click();
  await expect(
    page
      .locator(".operation-decision")
      .getByText("Precios aplicados al proyecto.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Recargar", exact: true }).click();
  await expect(
    page
      .locator(".operation-history__item")
      .getByText("Precios aplicados al proyecto.", { exact: true }),
  ).toBeVisible();
  await page.goto(`/projects/${draft.id}`);
  await expect(
    page
      .locator("dd")
      .filter({ hasText: formatMoney(quote.project_gross, "CLP") })
      .first(),
  ).toBeVisible();
  const persisted = await request.get(`${djangoUrl}/api/v1/projects/${draft.id}/`, { headers });
  expect(persisted.status()).toBe(200);
  const project = await persisted.json();
  expect(project.pricing_current).toBe(true);
  // Storage uses NUMERIC(14,2); compare Decimal text after removing only zero scale.
  expect(String(project.total_price_gross).replace(/\.0+$/, "")).toBe(
    quote.project_gross.replace(/\.0+$/, ""),
  );
  const audits = await request.get(`${djangoUrl}/api/v1/pricing/admin/audits/`, { headers });
  expect(audits.status()).toBe(200);
  expect(
    (await audits.json()).items.some(
      (item: { actor_user_id: string }) => item.actor_user_id === fixture.userId,
    ),
  ).toBe(true);

  const prepA = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes(`/api/v1/documents/projects/${draft.id}/inputs/`),
  );
  // The quotation panel lives inside the facts rail's collapsed "Cotización"
  // section — expand it once; it stays open for the whole emission flow.
  await page
    .locator("details.project-facts__section")
    .filter({ hasText: "Cotización" })
    .locator("summary")
    .click();
  await page.getByRole("button", { name: "Preparar emisión", exact: true }).click();
  await prepA;
  await page.getByLabel("Condiciones de pago", { exact: true }).fill("50% anticipo, 50% entrega");
  await page.getByLabel("Cotización válida hasta", { exact: true }).fill("2026-10-19");
  await expect(page.getByLabel("Criterio de fabricación", { exact: true })).not.toHaveValue("");
  // DEMO_60 ships two handle authorities since D03 (V3 adds TILT,
  // BOTTOM_HUNG and the double-door leaves): the freeze requires an
  // explicit pick when several versions compete, so select the current one.
  await page
    .getByLabel("Criterio de manillas", { exact: true })
    .selectOption({ label: "DEMO_60_HANDLES_V3 · v3" });
  // DEMO_60 ships two reinforcement authorities since D01 (V2 adds the
  // DOOR_SASH role): the freeze requires an explicit pick when several
  // versions compete, so select the current one.
  await page
    .getByLabel("Criterio de refuerzos", { exact: true })
    .selectOption({ label: "DEMO_60_REINFORCEMENT_CUT_V2 · v2" });
  await page.getByLabel(/Confirmo la emisión: esta revisión/).check();
  const freezeA = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === `/api/v1/documents/projects/${draft.id}/freeze/`,
  );
  await page.getByRole("button", { name: "Emitir cotización", exact: true }).click();
  const frozenA = await freezeA;
  expect(frozenA.status(), await frozenA.text()).toBe(201);
  await expect(page.getByText("Cotizado", { exact: true })).toBeVisible();
  await expect(
    page.locator(".quotation-history strong").filter({ hasText: "Revisión A" }),
  ).toBeVisible();

  const successor = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === `/api/v1/projects/${draft.id}/successor/`,
  );
  await page.getByRole("button", { name: "Crear nueva revisión", exact: true }).click();
  // §F: in-app ConfirmDialog replaced window.confirm — the successor POST
  // only fires after the product-surface confirmation.
  const successorDialog = page.getByRole("dialog");
  await expect(successorDialog).toContainText(t("quotation.successorConfirm"));
  await successorDialog.getByRole("button", { name: t("ui.confirm"), exact: true }).click();
  expect((await successor).status()).toBe(201);
  await expect(page.getByText("Borrador", { exact: true })).toBeVisible();
  await expect(page.getByText("Revisión B", { exact: true })).toBeVisible();
  // The desk grid is select-then-act: pick the vano row so the side pane
  // offers Abrir diseño.
  await page
    .locator(".position-grid [role='option']")
    .filter({ hasText: "Fijo comercial" })
    .click();
  await page.getByRole("link", { name: "Abrir diseño", exact: true }).click();
  await page.getByLabel("Cantidad", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  await expect(page.getByText("Guardado", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Volver al proyecto/ }).click();
  // React Query may serve the pre-save project from its fresh cache — the page
  // would still show "Añadir vano" instead of the quote next-action. Reload to
  // force the backend read that reflects the position just saved.
  await page.reload();
  await page.getByRole("link", { name: "Cotizar proyecto", exact: true }).click();
  await page.getByLabel("Fecha efectiva", { exact: true }).fill("2026-09-19");
  await page.getByLabel("Motivo del cambio", { exact: true }).fill("Apply browser REV-B quote");
  await page.getByRole("button", { name: "Calcular y revisar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Aprobar y aplicar precios", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Aprobar y aplicar precios", exact: true }).click();
  await expect(
    page
      .locator(".operation-decision")
      .getByText("Precios aplicados al proyecto.", { exact: true }),
  ).toBeVisible();
  await page.goto(`/projects/${draft.id}`);
  const prepB = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes(`/api/v1/documents/projects/${draft.id}/inputs/`),
  );
  await page
    .locator("details.project-facts__section")
    .filter({ hasText: "Cotización" })
    .locator("summary")
    .click();
  await page.getByRole("button", { name: "Preparar emisión", exact: true }).click();
  await prepB;
  await expect(page.getByLabel("Condiciones de pago", { exact: true })).toHaveValue(
    "50% anticipo, 50% entrega",
  );
  await page.getByLabel(/Confirmo la emisión: esta revisión/).check();
  const freezeB = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === `/api/v1/documents/projects/${draft.id}/freeze/`,
  );
  await page.getByRole("button", { name: "Emitir cotización", exact: true }).click();
  const frozenB = await freezeB;
  expect(frozenB.status(), await frozenB.text()).toBe(201);
  await expect(page.getByText("Cotizado", { exact: true })).toBeVisible();
  const history = page.locator(".quotation-history");
  await expect(history.getByText("Revisión A", { exact: true })).toBeVisible();
  await expect(history.getByText("Revisión B", { exact: true })).toBeVisible();

  const revA = history.locator("li").filter({ has: page.getByText("Revisión A", { exact: true }) });
  // Emitted evidence is generated by the durable job system, not a direct
  // artifact POST: enqueue → poll → access → blob download.
  const artifact = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/jobs/",
  );
  const access = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/access/"),
  );
  await revA.getByRole("button", { name: "Abrir cotización emitida", exact: true }).click();
  expect((await artifact).status()).toBeLessThan(300);
  expect((await access).status()).toBe(200);

  const finalProject = await request.get(`${djangoUrl}/api/v1/projects/${draft.id}/`, { headers });
  expect(finalProject.status()).toBe(200);
  const finalState = await finalProject.json();
  expect(finalState).toMatchObject({ status: "QUOTED", current_revision: "REV-B" });
  expect(
    finalState.versions.map((version: { revision_code: string }) => version.revision_code),
  ).toEqual(["REV-A", "REV-B"]);

  await page.goto("/projects");
  await page.getByRole("button", { name: "Crear proyecto", exact: true }).click();
  await page.getByLabel("Nombre del proyecto", { exact: true }).fill("Composite browser gate");
  await page.getByLabel("Cliente", { exact: true }).fill("Synthetic composite fixture");
  const compositeCreation = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/projects/",
  );
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  const compositeProject = (await (await compositeCreation).json()) as { id: string };
  await page.getByRole("link", { name: "Añadir vano", exact: true }).click();
  await page.getByLabel("Ubicación del vano", { exact: true }).fill("Fachada compuesta");
  await page.getByRole("button", { name: "Serie de perfiles", exact: true }).click();
  await page.getByRole("combobox", { name: "Serie de perfiles", exact: true }).selectOption({
    label: "Sistema Demo 60mm PVC — referencia sintética · Catálogo de demostración",
  });
  await page.getByRole("combobox", { name: "Espesor de vidrio", exact: true }).selectOption("4.00");
  // D02: el catálogo de vidrios ahora se elige por tarjeta (su nombre comercial
  // es el aria-label), no por un combobox de SKUs.
  await page.getByRole("button", { name: "Termopanel incoloro 4·16·4", exact: true }).click();
  const dividedCalculation = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/engine/assembly/calculate/",
  );
  await page.getByRole("button", { name: "Dividir en vertical", exact: true }).click();
  expect((await dividedCalculation).status()).toBe(200);
  const compositeSave = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === `/api/v1/projects/${compositeProject.id}/positions/`,
  );
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  const compositePosition = await (await compositeSave).json();
  expect(compositePosition.typology).toBe("COMPOSITE");
  await page.getByRole("link", { name: /Volver al proyecto/ }).click();
  await page.getByRole("link", { name: /Volver al proyecto/ }).click();
  await page.reload();
  await page.getByRole("link", { name: "Composite browser gate", exact: true }).click();
  await page
    .locator(".position-grid [role='option']")
    .filter({ hasText: "Fachada compuesta" })
    .click();
  await page.getByRole("link", { name: "Abrir diseño", exact: true }).click();
  // Scoped to the main canvas sheet — inspector previews and alternative
  // thumbnails render their own members on the same page. The bay division
  // draws a real mullion member between the two glass bays.
  await expect(page.locator(".canvas-sheet .member-mullion")).toHaveCount(1);
  await expect(page.locator(".canvas-sheet .module-glass")).toHaveCount(2);
  await page.getByRole("link", { name: /Volver al proyecto/ }).click();
  // React Query may serve the pre-save project from its fresh cache — the page
  // would still show "Añadir vano" instead of the quote next-action. Reload to
  // force the backend read that reflects the position just saved.
  await page.reload();
  await page.getByRole("link", { name: "Cotizar proyecto", exact: true }).click();
  await page.getByLabel("Fecha efectiva", { exact: true }).fill("2026-09-19");
  await page.getByLabel("Motivo del cambio", { exact: true }).fill("Composite browser price");
  const compositePreview = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/pricing/preview/",
  );
  await page.getByRole("button", { name: "Calcular y revisar", exact: true }).click();
  expect((await compositePreview).status()).toBe(200);
  await page.getByRole("button", { name: "Aprobar y aplicar precios", exact: true }).click();
  await expect(
    page
      .locator(".operation-decision")
      .getByText("Precios aplicados al proyecto.", { exact: true }),
  ).toBeVisible();
});

test("OWNER must complete real TOTP enrollment and challenge after each Magic Link", async ({
  page,
  request,
}) => {
  const fixture = await setupUser("OWNER");
  await requestMagicLink(page, fixture.email);
  const firstMessage = await latestMagicLink(fixture.email);
  await followRealMagicLink(page, firstMessage.link);
  await expect(page.getByTestId("mfa-page")).toBeVisible();
  await assertOwnerBlockedAtAal1(page, request, fixture);

  await page.getByRole("button", { name: "Configurar autenticador" }).click();
  await expect(page.getByTestId("totp-secret")).toBeVisible();
  const secret = (await page.getByTestId("totp-secret").textContent())?.trim() ?? "";
  const generator = new OTPAuth.TOTP({
    issuer: "Dekopen",
    label: fixture.email,
    algorithm: "SHA1",
    digits: 6,
    period: 30,
    secret: OTPAuth.Secret.fromBase32(secret),
  });
  const firstCode = generator.generate();
  await page.getByLabel("Código de seis dígitos").fill(firstCode);
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await assertRealIdentity(page, request, fixture, "aal2");

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page.getByTestId("login-page")).toBeVisible();
  await requestMagicLink(page, fixture.email);
  const secondMessage = await latestMagicLink(fixture.email, firstMessage.id);
  expect(secondMessage.id).not.toBe(firstMessage.id);
  expect(secondMessage.link === firstMessage.link).toBe(false);
  await followRealMagicLink(page, secondMessage.link);
  await expect(page.getByTestId("mfa-page")).toBeVisible();
  await expect(page.getByLabel("Código de seis dígitos")).toBeVisible();
  await expect(page.getByTestId("totp-secret")).toHaveCount(0);
  await assertOwnerBlockedAtAal1(page, request, fixture);

  await expect
    .poll(() => generator.generate(), { timeout: 35_000, intervals: [500] })
    .not.toBe(firstCode);
  const secondCode = generator.generate();
  await page.getByLabel("Código de seis dígitos").fill(secondCode);
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await assertRealIdentity(page, request, fixture, "aal2");
});

for (const tier of ["TRIAL", "STARTER"] as const) {
  test(`SHOT-11 real OWNER ${tier} wallet, billing and manual calculation`, async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(90_000);
    const fixture = await setupUser("OWNER", tier);
    await requestMagicLink(page, fixture.email);
    await followRealMagicLink(page, (await latestMagicLink(fixture.email)).link);
    const weakToken = await accessToken(page);
    for (const path of ["billing/", "billing/wallet/"]) {
      const blocked = await request.get(`${djangoUrl}/api/v1/${path}`, {
        headers: {
          Authorization: `Bearer ${weakToken}`,
          "X-Organization-ID": fixture.organizationId,
        },
      });
      expect(blocked.status()).toBe(403);
    }
    await page.getByRole("button", { name: "Configurar autenticador" }).click();
    const secret = (await page.getByTestId("totp-secret").textContent())?.trim() ?? "";
    const generator = new OTPAuth.TOTP({
      algorithm: "SHA1",
      digits: 6,
      period: 30,
      secret: OTPAuth.Secret.fromBase32(secret),
    });
    await page.getByLabel("Código de seis dígitos").fill(generator.generate());
    await page.getByRole("button", { name: "Verificar" }).click();
    await expect(page.getByTestId("app-shell")).toBeVisible();
    const headers = {
      Authorization: `Bearer ${await accessToken(page)}`,
      "X-Organization-ID": fixture.organizationId,
    };
    await page.goto("/settings/wallet");
    await expect(page.getByRole("heading", { name: "Billetera de créditos IA" })).toBeVisible();
    await expect(page.getByText("Créditos disponibles", { exact: true })).toBeVisible();
    const walletResponse = await request.get(`${djangoUrl}/api/v1/billing/wallet/`, { headers });
    expect(walletResponse.status()).toBe(200);
    const wallet = await walletResponse.json();
    expect(wallet.balance).toBe(tier === "TRIAL" ? 500 : 0);
    expect(wallet.ledger.length).toBe(tier === "TRIAL" ? 1 : 0);
    if (tier === "STARTER")
      await expect(page.getByText(/Las funciones manuales siguen disponibles/)).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`wallet-${tier}.png`), fullPage: true });
    await page.goto("/settings/billing");
    await expect(page.getByRole("heading", { name: "Suscripción y facturación" })).toBeVisible();
    await expect(page.getByText("No tienes una suscripción de pago registrada.")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`billing-${tier}.png`), fullPage: true });
    const systems = await request.get(
      `${supabaseUrl}/rest/v1/profile_systems?code=eq.DEMO_60&select=id`,
      { headers: adminHeaders() },
    );
    const systemId = (await systems.json())[0].id as string;
    const calculation = await request.post(`${djangoUrl}/api/v1/engine/calculate/`, {
      headers,
      data: {
        system_id: systemId,
        nominal_width_mm: "1000.00",
        nominal_height_mm: "1000.00",
        color: "WHITE",
        parametric_tree: {
          id: "g1",
          type: "BAY",
          opening_type: "FIXED",
          glass_thickness_mm: "4.00",
          glass_spec: "4",
        },
      },
    });
    expect(calculation.status(), await calculation.text()).toBe(200);
    expect((await calculation.json()).calculation_hash).toMatch(/^sha256:/);
    const project = await request.post(`${djangoUrl}/api/v1/projects/`, {
      headers,
      data: { name: "SHOT-11 manual product", client_name: "Synthetic customer" },
    });
    expect(project.status(), await project.text()).toBe(201);
    await page.goto(`/projects/${(await project.json()).id}`);
    await expect(
      page.getByRole("heading", { name: "SHOT-11 manual product", exact: true, level: 1 }),
    ).toBeVisible();
  });
}
