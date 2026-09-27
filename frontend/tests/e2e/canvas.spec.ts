import { expect, test, type Page } from "@playwright/test";

import { environment } from "./support/environment";
import { requireMailpitHealthy, waitForMagicLink } from "./support/mailpit";

const supabaseUrl = requiredEnvironment("SUPABASE_URL");
const serviceRoleKey = requiredEnvironment("SUPABASE_SERVICE_ROLE_KEY");
const mailpitUrl = environment("MAILPIT_URL") ?? "http://127.0.0.1:25324";

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
    expect(organization.status).toBe(204);
    const user = await fetch(`${supabaseUrl}/auth/v1/admin/users/${fixture.userId}`, {
      method: "DELETE",
      headers: adminHeaders(),
    });
    expect(user.status).toBe(200);
  }
});

function requiredEnvironment(name: string): string {
  const value = environment(name);
  if (!value) throw new Error(`${name} is required for the real canvas E2E`);
  return value;
}

function adminHeaders(): Record<string, string> {
  return {
    apikey: serviceRoleKey,
    Authorization: `Bearer ${serviceRoleKey}`,
    "Content-Type": "application/json",
  };
}

async function setupEstimator(): Promise<FixtureUser> {
  const suffix = crypto.randomUUID();
  const email = `shot05-estimator-${suffix}@example.com`;
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
      name: "E2E Canvas",
      tax_id: `SHOT05-${suffix}`,
    }),
  });
  expect(organizationResponse.ok).toBe(true);
  const membershipResponse = await fetch(`${supabaseUrl}/rest/v1/tenancy_memberships`, {
    method: "POST",
    headers: { ...adminHeaders(), Prefer: "return=minimal" },
    body: JSON.stringify({
      org_id: organizationId,
      user_id: user.id,
      role: "ESTIMATOR",
      is_active: true,
    }),
  });
  expect(membershipResponse.ok).toBe(true);
  return { email, userId: user.id, organizationId };
}

async function authenticate(page: Page, fixture: FixtureUser): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Correo").fill(fixture.email);
  await page.getByRole("button", { name: "Enviar enlace de acceso" }).click();
  await expect(page.getByRole("status")).toContainText("Revisa tu correo para continuar");
  const message = await waitForMagicLink({
    baseUrl: mailpitUrl,
    supabaseUrl,
    recipient: fixture.email,
    excludedMessageIds: new Set(),
  });
  await page.goto(message.link);
  await expect(page.getByTestId("app-shell")).toBeVisible();
}

async function commitDimension(page: Page, label: string, value: string): Promise<number> {
  const editor = page.getByTestId("canvas-editor");
  const before = Number(await editor.getAttribute("data-last-commit-sequence"));
  const input = page.getByLabel(label);
  await input.fill(value);
  await input.press("Enter");
  await expect(editor).toHaveAttribute("data-last-commit-sequence", String(before + 1));
  const rawDuration = await editor.getAttribute("data-last-commit-ms");
  if (rawDuration === null || rawDuration.length === 0) {
    throw new Error("Canvas commit did not publish its paint measurement");
  }
  return Number(rawDuration);
}

test("G1 canvas uses runtime discovery, transactional dimensions, snapping and <300 ms paints", async ({
  page,
}) => {
  const fixture = await setupEstimator();
  await authenticate(page, fixture);
  let calculationRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/engine/calculate/") {
      calculationRequests += 1;
    }
  });

  const systemsResponsePromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/v1/engine/systems/",
  );
  const initialCalculationPromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/engine/calculate/" && response.status() === 200,
  );
  await page.goto("/projects/demo/positions/g1/edit");
  const systemsResponse = await systemsResponsePromise;
  const systemsPayload = (await systemsResponse.json()) as {
    systems: Array<{ id: string; code: string; is_demo: boolean }>;
  };
  const discovered = systemsPayload.systems.filter(
    (system) => system.code === "DEMO_60" && system.is_demo,
  );
  expect(discovered).toHaveLength(1);
  const initialCalculation = await initialCalculationPromise;
  const initialRequest = initialCalculation.request().postDataJSON() as {
    system_id: string;
    nominal_width_mm: string;
    nominal_height_mm: string;
  };
  expect(initialRequest).toEqual(
    expect.objectContaining({
      system_id: discovered[0]?.id,
      nominal_width_mm: "1000.00",
      nominal_height_mm: "1000.00",
    }),
  );

  const editor = page.getByTestId("canvas-editor");
  await expect(editor).toHaveAttribute("data-system-id", discovered[0]?.id ?? "");
  await expect(page).toHaveURL(/\/projects\/demo\/positions\/g1\/edit$/);
  await expect(page.getByLabel("Ancho nominal (mm)")).toHaveValue("1000.00");
  await expect(page.getByLabel("Alto nominal (mm)")).toHaveValue("1000.00");
  await expect(page.getByText("FIXED", { exact: true })).toBeVisible();
  await expect(page.getByTestId("canvas-glass-dimension")).toHaveText("910.00 × 910.00 mm");
  await expect(page.getByTestId("technical-frame")).toHaveText("1006.00 mm");
  await expect(page.getByTestId("technical-reinforcement")).toHaveText("970.00 mm");
  await expect(page.getByTestId("technical-glass")).toHaveText("910.00 × 910.00 mm");
  await expect(page.getByTestId("technical-bead")).toHaveText("919.00 mm");
  expect(calculationRequests).toBe(1);

  const width = page.getByLabel("Ancho nominal (mm)");
  const height = page.getByLabel("Alto nominal (mm)");
  await width.focus();
  await expect(width).toBeFocused();
  // The focus contract is a box-shadow ring (ui.css), not outline.
  await expect(width).not.toHaveCSS("box-shadow", "none");
  await page.keyboard.press("Tab");
  await expect(height).toBeFocused();
  await width.fill("1040");
  await width.press("Escape");
  await expect(width).toHaveValue("1000.00");
  await height.fill("1040");
  await page.getByRole("heading", { name: "Editor paramétrico 2D" }).click();
  await expect(height).toHaveValue("1000.00");
  expect(calculationRequests).toBe(1);

  await commitDimension(page, "Ancho nominal (mm)", "1020.5");
  await expect(width).toHaveValue("1020.50");
  await height.fill("0.01");
  await height.press("Enter");
  await expect(page.getByRole("alert")).toContainText("validation_error");
  await expect(height).toHaveValue("1000.00");
  await expect(editor).toHaveAttribute("data-result-height-mm", "1000.00");

  const svg = page.getByTestId("canvas-svg");
  const widthHandle = page.getByTestId("resize-width");
  const handleBox = await widthHandle.boundingBox();
  if (handleBox === null) throw new Error("Width resize handle has no screen bounds");
  const target = await svg.evaluate((element) => {
    const svgElement = element as unknown as SVGSVGElement;
    const matrix = svgElement.getScreenCTM();
    if (matrix === null) throw new Error("SVG screen transform is missing");
    const point = new DOMPoint(1050, 500).matrixTransform(matrix);
    return { x: point.x, y: point.y };
  });
  await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x, target.y);
  await expect(page.getByTestId("snap-guide")).toBeVisible();
  const snappedRequestPromise = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/api/v1/engine/calculate/" &&
      request.postDataJSON().nominal_width_mm === "1050.00",
  );
  await page.mouse.up();
  await expect(width).toHaveValue("1050.00");
  await expect(page.getByTestId("canvas-glass-dimension")).toHaveText("960.00 × 910.00 mm");
  const snappedRequest = await snappedRequestPromise;
  expect(snappedRequest.postDataJSON().nominal_width_mm).toBe("1050.00");

  const lightStroke = await page
    .getByTestId("fixed-glass")
    .evaluate((element) => getComputedStyle(element).stroke);
  await page.getByRole("button", { name: "Cambiar tema" }).click();
  const darkStroke = await page
    .getByTestId("fixed-glass")
    .evaluate((element) => getComputedStyle(element).stroke);
  expect(darkStroke).not.toBe(lightStroke);

  await commitDimension(page, "Ancho nominal (mm)", "1060");
  const durations: number[] = [];
  for (const candidate of ["1070", "1080", "1090", "1100", "1110"]) {
    durations.push(await commitDimension(page, "Ancho nominal (mm)", candidate));
  }
  console.log(
    `SHOT-05 paint durations ms: ${durations.map((value) => value.toFixed(3)).join(", ")}`,
  );
  expect(durations).toHaveLength(5);
  for (const duration of durations) {
    expect(duration).toBeLessThan(300);
  }
});

for (const theme of ["light", "dark"] as const) {
  test(`SHOT-07 ${theme}: real modal, BFD, preview, rollback and recomputed semaphore`, async ({
    page,
  }) => {
    await authenticate(page, await setupEstimator());
    await page.goto("/projects/demo/positions/g1/edit");
    await expect(page.getByTestId("technical-frame")).toHaveText("1006.00 mm");
    if (theme === "dark") await page.getByRole("button", { name: "Cambiar tema" }).click();
    const optimization = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/engine/optimize-cut/") && response.status() === 200,
    );
    await page.getByRole("button", { name: "Inspector y corte 1D" }).click();
    const modal = page.getByRole("dialog", { name: "Revisión técnica de taller" });
    await expect(modal).toBeVisible();
    await expect(page).toHaveURL(/\/projects\/demo\/positions\/g1\/edit$/);
    const cutResponse = await optimization;
    const cuts = (await cutResponse.json()) as {
      source_calculation_hash: string;
      purchase_list: Array<{ commercial_sku: string }>;
      workshop_cut_plan: Array<{ cuts: Array<{ workshop_sku: string; length_mm: string }> }>;
    };
    expect(cuts.purchase_list.map((line) => line.commercial_sku)).toContain("DEMO-BAR-MARCO");
    expect(
      cuts.workshop_cut_plan
        .flatMap((bar) => bar.cuts)
        .some((cut) => cut.workshop_sku === "MARCO" && cut.length_mm === "1006.00"),
    ).toBe(true);
    expect(cutResponse.request().postDataJSON()).not.toHaveProperty("cuts");
    await expect(modal.locator(".inspector-semaphore")).toHaveAttribute("data-status", "RED");
    const approve = modal.getByRole("button", { name: "Aprobar para Taller" });
    await expect(approve).toBeDisabled();
    const drains = modal.getByLabel("Posiciones de desagües inferiores (mm, separadas por coma)");
    await drains.fill("100, 900");
    await modal.getByLabel("Ancho continuo declarado (mm)").fill("1000");
    await modal.getByLabel("¿Existe acople de dilatación?").selectOption("no");
    await modal.getByRole("button", { name: "Verificar observaciones" }).click();
    await expect(modal.locator(".inspector-semaphore")).toHaveAttribute("data-status", "YELLOW");
    await modal.getByRole("button", { name: "Ver corrección propuesta" }).click();
    await expect(drains).toHaveValue("100, 900");
    await expect(modal.getByLabel("Ver corrección propuesta")).toContainText("500");
    // Inject one network failure; the calculations and successful retry use the real server.
    await page.route("**/api/v1/engine/inspect/", (route) => route.abort("failed"), { times: 1 });
    await modal.getByRole("button", { name: "Aplicar corrección" }).click();
    await expect(modal.getByRole("alert")).toContainText("El diseño anterior se conserva");
    await expect(drains).toHaveValue("100, 900");
    await expect(modal.locator(".inspector-semaphore")).toHaveAttribute("data-status", "YELLOW");
    const inspection = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/engine/inspect/") && response.status() === 200,
    );
    await modal.getByRole("button", { name: "Aplicar corrección" }).click();
    const inspected = (await (await inspection).json()) as {
      source_calculation_hash: string;
      status: string;
    };
    expect(inspected.source_calculation_hash).toBe(cuts.source_calculation_hash);
    expect(inspected.status).toBe("GREEN");
    await expect(modal.locator(".inspector-semaphore")).toHaveAttribute("data-status", "GREEN");
    await expect(drains).toHaveValue("100.0000, 500.00, 900.0000");
    await expect(modal.getByRole("button", { name: "Aplicar corrección" })).toHaveCount(0);
    await expect(approve).toBeEnabled();
    const transition = await modal
      .locator(".inspector-semaphore")
      .evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(transition.split(", ")).toContain("0.15s");
    await expect(modal.locator(".is-corrected")).toHaveCSS("animation-duration", "0.3s");
    await modal.getByRole("button", { name: "Corte 1D", exact: true }).click();
    await expect(modal.getByRole("heading", { name: "Pedido", exact: true })).toBeVisible();
    await expect(modal.getByText("DEMO-BAR-MARCO", { exact: true })).toBeVisible();
    await expect(modal.getByRole("heading", { name: "Plan de corte de taller" })).toBeVisible();
    await expect(modal.getByText("MARCO", { exact: true }).first()).toBeVisible();
    await modal.screenshot({ path: `test-results/shot07-${theme}.png` });
    await modal.getByRole("button", { name: "Cerrar revisión" }).click();
    await expect(modal).not.toBeVisible();
    await expect(page.getByTestId("canvas-glass-dimension")).toHaveText("910.00 × 910.00 mm");
  });
}
