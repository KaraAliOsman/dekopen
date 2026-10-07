import { expect, type Page, type TestInfo } from "@playwright/test";

import type {
  EngineAssemblyCalculateResponse,
  PositionResponse,
  ProjectResponse,
} from "../../src/api/generated/models";
import { fmtMm } from "../../src/format";
import { test } from "./support/manual-project-fixture";

test.use({ viewport: { width: 1366, height: 768 }, actionTimeout: 15_000 });

async function responseTo<T>(
  page: Page,
  method: string,
  path: string,
  status: number,
  action: () => Promise<unknown>,
): Promise<T> {
  const [response] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.request().method() === method && new URL(candidate.url()).pathname === path,
      { timeout: 20_000 },
    ),
    action(),
  ]);
  expect(response.status(), `${method} ${path}`).toBe(status);
  return (await response.json()) as T;
}

async function screenshot(page: Page, info: TestInfo, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  expect(page.viewportSize()).toEqual({ width: 1366, height: 768 });
  const path = info.outputPath(`${name}-1366x768.png`);
  await page.screenshot({
    path,
    fullPage: false,
    animations: "disabled",
  });
  await info.attach(name, { path, contentType: "image/png" });
}

/** The desk grid is select-then-act: click the vano's row so the side pane
 * offers its actions, then return the action link inside it. */
async function card(page: Page, location: string, action: string) {
  await page.locator(".position-grid [role='option']").filter({ hasText: location }).click();
  return page.locator(".positions-side").getByRole("link", { name: action, exact: true });
}

test("SHOT-10 real project core path and visual evidence", async ({ page, manual }, info) => {
  test.setTimeout(180_000);

  const projectName = `E2E sintético ${crypto.randomUUID()}`;
  const save = () => page.getByRole("button", { name: "Guardar", exact: true }).click();
  // Navigation uses the editor's own backlink ("Volver al proyecto"). React
  // Query may serve the project from its fresh cache without a fetch, so the
  // reload makes the backend round-trip (and in-memory reset) explicit.
  const back = () => page.getByRole("link", { name: /Volver al proyecto/ }).click();
  const toProjects = () => page.getByRole("link", { name: /‹ Proyectos/ }).click();
  const freshRead = () => page.reload();

  await page.goto("/projects");
  await expect(page.getByText("No hay proyectos que coincidan.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Crear proyecto", exact: true }).click();
  // Extended identity fields live under the collapsed "Datos adicionales" section.
  await page.locator("summary", { hasText: "Datos adicionales" }).click();

  const metadata = [
    ["Nombre del proyecto", projectName],
    ["Cliente", "Cliente sintético E2E"],
    ["RUT", "1-9"],
    ["Correo", "cliente-e2e@example.test"],
    ["Teléfono", "+56900000000"],
    ["Dirección de entrega", "Dirección sintética; no despachar"],
    ["Notas comerciales", "Prueba automatizada; no emitir"],
    ["Notas internas", "DEMO_60 SYNTHETIC FIXTURE — tests only"],
  ] as const;
  for (const [label, value] of metadata) {
    await page.getByLabel(label, { exact: true }).fill(value);
  }

  const project = await responseTo<ProjectResponse>(page, "POST", "/api/v1/projects/", 201, save);
  expect(project).toMatchObject({
    name: projectName,
    client_name: "Cliente sintético E2E",
    client_email: "cliente-e2e@example.test",
    notes_internal: "DEMO_60 SYNTHETIC FIXTURE — tests only",
    status: "DRAFT",
    pricing_current: false,
  });
  const projectPath = `/projects/${project.id}`;
  const projectApi = `/api/v1/projects/${project.id}/`;
  await expect(page).toHaveURL(new RegExp(`${projectPath}$`));
  await expect(page.getByRole("heading", { level: 1 })).toContainText(projectName);
  const addPosition = () =>
    page.locator(".positions-toolbar").getByRole("link", { name: "Añadir vano" });
  await expect(addPosition()).toBeVisible();
  await screenshot(page, info, "01-project-created");

  await addPosition().click();
  await page.getByLabel("Ubicación del vano", { exact: true }).fill("Cocina original");
  await page.getByLabel("Cantidad", { exact: true }).fill("2");

  // The series field lives in the strip's Serie chip popover (P04).
  await page.getByRole("button", { name: "Serie de perfiles", exact: true }).click();
  await responseTo(page, "GET", `/api/v1/projects/design-options/${manual.systemId}/`, 200, () =>
    page
      .getByRole("combobox", { name: "Serie de perfiles", exact: true })
      .selectOption(manual.systemId),
  );

  // The compositional canvas evaluates live: picking the glazing thickness in
  // the contextual inspector is enough to reach VALID (the spec seeds itself).
  await responseTo<EngineAssemblyCalculateResponse>(
    page,
    "POST",
    "/api/v1/engine/assembly/calculate/",
    200,
    () =>
      page.getByRole("combobox", { name: "Espesor de vidrio", exact: true }).selectOption("20.00"),
  );
  await expect(page.getByRole("button", { name: "Guardar", exact: true })).toBeEnabled();

  const initial = await responseTo<PositionResponse>(
    page,
    "POST",
    `${projectApi}positions/`,
    201,
    save,
  );
  // Single-unit saves fold to the classic contract; the saved BOM is the
  // engine result for the folded design (bay ids are unnamespaced there).
  expect(initial.bom?.glasses?.[0]?.thickness_net_mm).toBe("20.00");
  expect(initial.bom?.profile_cuts?.length).toBeGreaterThan(0);
  expect(initial.quantity).toBe(2);
  const positionApi = `/api/v1/positions/${initial.id}/`;
  const editPath = `${projectPath}/positions/${initial.id}/edit`;
  await expect(page).toHaveURL(new RegExp(`${editPath}$`));
  await expect(page.getByText("Guardado", { exact: true })).toBeVisible();

  // Invalid intent cannot expose a previous result as the current calculation.
  await page.getByRole("textbox", { name: "Ancho mm" }).fill("10.00");
  await responseTo(page, "POST", "/api/v1/engine/assembly/calculate/", 200, () =>
    page.getByRole("textbox", { name: "Ancho mm" }).press("Enter"),
  );
  await expect(page.getByTestId("assembly-status")).toHaveText(/inválida|incompleta/);
  await expect(page.getByRole("textbox", { name: "Ancho mm" })).toHaveValue("10.00");
  await expect(page.getByRole("button", { name: "Guardar", exact: true })).toBeDisabled();
  await expect(page.locator("details.project-bom")).toHaveCount(0);

  // Exercise a real update, not only an unsaved creation preview.
  await page.getByRole("textbox", { name: "Ancho mm" }).fill("1100.25");
  await responseTo(page, "POST", "/api/v1/engine/assembly/calculate/", 200, () =>
    page.getByRole("textbox", { name: "Ancho mm" }).press("Enter"),
  );
  // Drafts are uncommitted until blur/Enter — the live model (and its
  // evaluation) is unchanged until the field commits.
  await page.getByRole("textbox", { name: "Alto mm" }).fill("1050.50");

  await responseTo(page, "POST", "/api/v1/engine/assembly/calculate/", 200, () =>
    page.getByRole("textbox", { name: "Alto mm" }).press("Enter"),
  );
  const editedBom = (
    await responseTo<EngineAssemblyCalculateResponse>(
      page,
      "POST",
      "/api/v1/engine/assembly/calculate/",
      200,
      () =>
        page
          .locator(".opening-grid")
          .getByRole("button", {
            name: "Abatible hacia adentro — bisagras a la derecha",
            exact: true,
          })
          .click(),
    )
  ).bom!;
  expect(editedBom.hardware_items![0]!.kit_sku).toBe("KIT-TURN");

  // Inject a transport failure only; successful writes still use the real backend.
  await page.route(`**${positionApi}`, async (route) => {
    if (route.request().method() === "PUT") await route.abort("failed");
    else await route.continue();
  });
  await save();
  await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Guardar", exact: true })).toBeEnabled();
  await expect(page.getByRole("textbox", { name: "Ancho mm" })).toHaveValue("1100.25");
  const beforeRetry = await manual.readRows(
    "project_positions",
    `id=eq.${initial.id}&select=width_mm::text`,
  );
  expect(beforeRetry[0]?.width_mm).toBe("1000.00");
  await page.unroute(`**${positionApi}`);
  const saved = await responseTo<PositionResponse>(page, "PUT", positionApi, 200, save);
  expect(saved.design).toMatchObject({
    system_id: manual.systemId,
    nominal_width_mm: "1100.25",
    nominal_height_mm: "1050.50",
    parametric_tree: { type: "BAY", opening_type: "TURN_RIGHT" },
  });
  expect(saved.bom?.hardware_items).toHaveLength(1);
  expect(saved.bom?.hardware_items?.[0]?.kit_sku).toBe("KIT-TURN");
  await expect(page.getByText("Guardado", { exact: true })).toBeVisible();

  // The BOM lives in the dock's "Materiales" tab (P04 canvas-first layout).
  await page.getByRole("tab", { name: "Materiales", exact: true }).click();
  const bom = page.locator("details.project-bom");
  await bom.waitFor({ state: "attached" });
  await bom.evaluate((element) => {
    (element as HTMLDetailsElement).open = true;
  });
  const profileRows = bom.locator("table").first().locator("tbody tr");
  await expect(profileRows).toHaveCount(editedBom.profile_cuts.length);
  for (const [index, cut] of editedBom.profile_cuts.entries()) {
    await expect(profileRows.nth(index).locator("td")).toHaveText([
      cut.sku,
      fmtMm(cut.length_mm),
      String(cut.qty),
    ]);
  }
  // Top-of-editor composition at the requested real desktop viewport.
  await page.getByRole("heading", { level: 1 }).scrollIntoViewIfNeeded();
  await screenshot(page, info, "02-saved-configurator");

  const persisted = await manual.readRows(
    "project_positions",
    `id=eq.${saved.id}&org_id=eq.${manual.organizationId}` +
      "&select=id,width_mm::text,height_mm::text,parametric_tree,bom_snapshot",
  );
  expect(persisted).toHaveLength(1);
  expect(persisted[0]).toMatchObject({
    id: saved.id,
    width_mm: "1100.25",
    height_mm: "1050.50",
    parametric_tree: saved.design.parametric_tree,
    bom_snapshot: saved.bom,
  });

  // Leave both editor and project; full reload removes in-memory UI state.
  await back();
  await expect(page).toHaveURL(new RegExp(`${projectPath}$`));
  const projectResponse = await responseTo<ProjectResponse>(
    page,
    "GET",
    projectApi,
    200,
    freshRead,
  );
  expect(projectResponse.status).toBe("DRAFT");
  expect(projectResponse.pricing_current).toBe(false);
  expect(projectResponse.position_count).toBe(1);
  await toProjects();
  await expect(page).toHaveURL(/\/projects$/);
  await page.reload();

  const reopenedProject = await responseTo<ProjectResponse>(page, "GET", projectApi, 200, () =>
    page
      .getByRole("link", {
        name: projectName,
        exact: true,
      })
      .click(),
  );
  expect(reopenedProject.client_email).toBe("cliente-e2e@example.test");
  expect(reopenedProject.position_count).toBe(1);

  const reopened = await responseTo<PositionResponse>(page, "GET", positionApi, 200, () =>
    card(page, "Cocina original", "Abrir diseño").then((link) => link.click()),
  );
  expect(reopened).toEqual(saved);
  await expect(page.getByRole("textbox", { name: "Ancho mm" })).toHaveValue("1100.25");
  await expect(page.getByRole("textbox", { name: "Alto mm" })).toHaveValue("1050.50");
  await expect(
    page.locator(".opening-grid").getByRole("button", {
      name: "Abatible hacia adentro — bisagras a la derecha",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  // The canvas sheet overlays the summary on this layout; open the details
  // declaratively instead of clicking through the overlay. The save remounts
  // the editor (new position id), so the dock tab must be re-opened here.
  await page.getByRole("tab", { name: "Materiales", exact: true }).click();
  await bom.waitFor({ state: "attached" });
  await bom.evaluate((element) => {
    (element as HTMLDetailsElement).open = true;
  });
  await bom.scrollIntoViewIfNeeded();
  await screenshot(page, info, "03-reopened-bom");

  await back();
  await expect(page).toHaveURL(new RegExp(`${projectPath}$`));
  await responseTo(page, "GET", positionApi, 200, () =>
    card(page, "Cocina original", "Duplicar vano").then((link) => link.click()),
  );
  await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();
  await page.getByLabel("Ubicación del vano", { exact: true }).fill("Cocina duplicada");

  const duplicate = await responseTo<PositionResponse>(
    page,
    "POST",
    `${projectApi}positions/`,
    201,
    save,
  );
  expect(duplicate.id).not.toBe(saved.id);
  expect(duplicate.design).toEqual(saved.design);
  expect(duplicate.bom).toEqual(saved.bom);
  await expect(page).toHaveURL(new RegExp(`${projectPath}/positions/${duplicate.id}/edit$`));
  await expect(page.getByText("Guardado", { exact: true })).toBeVisible();

  await back();
  await expect(page).toHaveURL(new RegExp(`${projectPath}$`));
  const source = await responseTo<ProjectResponse>(page, "GET", projectApi, 200, freshRead);
  expect(source.position_count).toBe(2);
  expect(source.positions!.find((item) => item.id === saved.id)).toEqual(saved);

  const clone = await responseTo<ProjectResponse>(page, "POST", `${projectApi}clone/`, 201, () =>
    page
      .getByRole("button", {
        name: "Duplicar proyecto",
        exact: true,
      })
      .click(),
  );
  expect(clone.id).not.toBe(source.id);
  expect(clone).toMatchObject({
    status: "DRAFT",
    pricing_current: false,
    position_count: 2,
  });
  expect(clone.positions).toHaveLength(2);

  for (const copy of clone.positions!) {
    const original = source.positions!.find((item) => item.location_tag === copy.location_tag);
    expect(original).toBeDefined();
    expect(copy.id).not.toBe(original!.id);
    expect(copy.project_id).toBe(clone.id);
    expect(copy.design).toEqual(original!.design);
    expect(copy.bom).toEqual(original!.bom);
  }

  await expect(page).toHaveURL(new RegExp(`/projects/${clone.id}$`));
  const reopenedClone = await responseTo<ProjectResponse>(
    page,
    "GET",
    `/api/v1/projects/${clone.id}/`,
    200,
    () => page.reload(),
  );
  expect(reopenedClone.positions).toEqual(clone.positions);
  await expect(page.locator(".position-grid [role='option']")).toHaveCount(2);
  await page.getByRole("heading", { level: 1 }).scrollIntoViewIfNeeded();
  await screenshot(page, info, "04-reopened-draft-clone");

  const unchangedSource = await responseTo<ProjectResponse>(page, "GET", projectApi, 200, () =>
    page.goto(projectPath),
  );
  expect(unchangedSource).toEqual(source);
  await page.getByRole("button", { name: "Cambiar tema", exact: true }).click();
  await screenshot(page, info, "05-project-dark");
  // Estimators can browse the catalog (and run supplier imports); structural
  // edits stay owner/manager-only.
  await page.goto("/catalogs/systems");
  await expect(page.getByRole("heading", { name: "Catálogo técnico", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Crear serie", exact: true })).toHaveCount(0);
});
