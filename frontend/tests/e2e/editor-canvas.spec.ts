import { expect, type Page } from "@playwright/test";

import type { DesignOptions, ProjectResponse } from "../../src/api/generated/models";
import { OPENING_OPTIONS, openingOptionAdmitted } from "../../src/features/canvas/openings";
import { OPTION_SPEC_KEY, type OpeningChoice } from "../../src/features/canvas/intentEditing";
import { test } from "./support/manual-project-fixture";

test.use({ viewport: { width: 1440, height: 900 }, actionTimeout: 15_000 });

const CANVAS = ".assembly-canvas";
const LIBRARY = /Biblioteca de diseños/;

/** The SPA authenticates with a Bearer token + org header (not cookies) —
 * reuse the session's own token for fixture-side API calls. */
async function authHeaders(page: Page, organizationId: string) {
  const token = await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) {
      try {
        const data: unknown = JSON.parse(localStorage.getItem(key) ?? "null");
        if (data && typeof data === "object" && "access_token" in data) {
          const value = (data as { access_token?: unknown }).access_token;
          if (typeof value === "string") return value;
        }
      } catch {
        // not JSON — next key
      }
    }
    return null;
  });
  if (!token) throw new Error("sin access_token en localStorage");
  return { Authorization: `Bearer ${token}`, "X-Organization-ID": organizationId };
}

async function newProject(page: Page, organizationId: string): Promise<ProjectResponse> {
  const response = await page.request.post("/api/v1/projects/", {
    headers: await authHeaders(page, organizationId),
    data: { name: `Canvas E2E ${crypto.randomUUID()}`, client_name: "E2E" },
  });
  expect(response.status()).toBe(201);
  return (await response.json()) as ProjectResponse;
}

async function openNewPosition(page: Page, project: ProjectResponse, systemId?: string) {
  const query = systemId ? `?system=${systemId}` : "";
  await page.goto(`/projects/${project.id}/positions/new${query}`);
  await expect(page.getByTestId("editor-strip")).toBeVisible();
  // The app needs a navigation inside the SPA for localStorage/session to be
  // live in this page — the fixture already authenticated on another page.
  await page.waitForLoadState("networkidle");
}

async function pickStarter(page: Page, title: RegExp) {
  await page.getByRole("button", { name: LIBRARY }).click();
  await page.getByRole("button", { name: title }).click();
}

test.describe("Editor canvas-first (P04)", () => {
  test("canvas ≥60% ancho y ≥75% alto en 1440×900, sin scroll horizontal 1024–1920", async ({
    page,
    manual,
  }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await expect(page.getByTestId("assembly-sheet")).toBeVisible();
    const canvas = await page.locator(CANVAS).boundingBox();
    if (!canvas) throw new Error("canvas sin bounding box");
    expect(canvas.width).toBeGreaterThanOrEqual(1440 * 0.6);
    expect(canvas.height).toBeGreaterThanOrEqual(900 * 0.75);
    for (const width of [1024, 1280, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `scroll horizontal en ${width}px`).toBeLessThanOrEqual(1);
    }
  });

  test("ventana 2 hojas oscilobatientes 1500×1200 vidrio 4-16-4 en ≤6 interacciones", async ({
    page,
    manual,
  }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await expect(page.getByTestId("assembly-sheet")).toBeVisible();

    // Una "interacción" = un gesto con un solo intento (abrir el riel, elegir
    // la tipología, teclear una cota+Enter, elegir el vidrio). La serie ya
    // llega elegida vía ?system= — igual que la app real al lanzar el editor.
    let actions = 0;
    const act = async (gesture: () => Promise<unknown>): Promise<void> => {
      actions += 1;
      await gesture();
    };

    await act(() => page.getByRole("button", { name: LIBRARY }).click());
    await act(() => page.getByRole("button", { name: /Dos hojas/ }).click());
    await act(async () => {
      const field = page.getByRole("textbox", { name: "Ancho mm", exact: true });
      await field.fill("1500");
      await field.press("Enter");
    });
    await act(async () => {
      const field = page.getByRole("textbox", { name: "Alto mm", exact: true });
      await field.fill("1200");
      await field.press("Enter");
    });
    await act(() => page.getByLabel("Espesor de vidrio", { exact: true }).selectOption("24.00"));

    expect(actions).toBeLessThanOrEqual(6);
    await expect(page.getByTestId("assembly-status")).toHaveClass(/assembly-status--valid/);
  });

  test("pan extremo de 10.000 px: el dibujo sigue visible o se recentra", async ({
    page,
    manual,
  }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await pickStarter(page, /Una hoja/);
    const canvas = page.locator(CANVAS);
    const box = await canvas.boundingBox();
    if (!box) throw new Error("canvas sin bounding box");

    const startX = box.x + box.width / 2;
    const startY = box.y + box.height / 2;
    await page.mouse.move(startX, startY);
    await page.mouse.down({ button: "middle" });
    for (let i = 1; i <= 20; i += 1) {
      await page.mouse.move(startX + i * 500, startY);
    }
    await page.mouse.up();

    const intersects = () =>
      page.evaluate(() => {
        const sheet = document.querySelector<SVGElement>('[data-testid="assembly-sheet"]');
        const surface = document.querySelector(".assembly-canvas");
        if (!sheet || !surface) return false;
        const a = sheet.getBoundingClientRect();
        const b = surface.getBoundingClientRect();
        return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      });
    if (!(await intersects())) {
      await page.getByRole("button", { name: "Ajustar", exact: true }).click();
    }
    await expect.poll(intersects).toBe(true);
  });

  test("todas las herramientas del riel con etiqueta visible y aria-label", async ({
    page,
    manual,
  }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    const items = page.locator(".editor-rail .rail-item");
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(7);
    for (let i = 0; i < count; i += 1) {
      const item = items.nth(i);
      const aria = (await item.getAttribute("aria-label"))?.trim() ?? "";
      expect(aria, `rail-item ${i} sin aria-label`).not.toHaveLength(0);
      await expect(item.locator(".rail-item__label")).not.toBeEmpty();
      const title = (await item.getAttribute("title"))?.trim() ?? "";
      expect(title, `rail-item ${i} sin tooltip`).not.toHaveLength(0);
    }
  });

  test("selector de apertura: nombres en español y solo opciones compatibles", async ({
    page,
    manual,
  }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await pickStarter(page, /Dos hojas/);

    const optionsResponse = await page.request.get(
      `/api/v1/projects/design-options/${manual.systemId}/`,
      { headers: await authHeaders(page, manual.organizationId) },
    );
    expect(optionsResponse.status()).toBe(200);
    const options = (await optionsResponse.json()) as DesignOptions;

    const sheet = page.getByTestId("assembly-sheet");
    const box = await sheet.boundingBox();
    if (!box) throw new Error("sheet sin bounding box");
    await page.mouse.dblclick(box.x + box.width / 4, box.y + box.height / 2);
    const grid = page.getByRole("dialog").locator(".opening-grid");
    await expect(grid).toBeVisible();

    const rendered = await grid
      .locator("[data-opening]")
      .evaluateAll((nodes) =>
        nodes.map((node) => node.getAttribute("data-opening") as OpeningChoice),
      );
    const admitted = OPENING_OPTIONS.map(([value]) => value).filter((value) =>
      openingOptionAdmitted(value, options.opening_options),
    );
    expect([...rendered].sort()).toEqual([...admitted].sort());

    for (const value of rendered) {
      expect(OPTION_SPEC_KEY[value]).toBeTruthy();
    }
    const labels = await grid.locator(".opening-choice__name").allTextContents();
    for (const label of labels) {
      expect(label.trim()).not.toHaveLength(0);
      expect(label).not.toMatch(/^[A-Z_]+$/);
    }
  });

  test("guard de cambios sin guardar cubre todos los enlaces del editor", async ({
    page,
    manual,
  }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await pickStarter(page, /Una hoja/);
    await page.getByLabel("Ubicación del vano", { exact: true }).fill("Muro norte");
    await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();

    const guardDialog = page.getByRole("dialog");
    const guardText = /cambios sin guardar/i;

    // Enlace de las migas — el guard bloquea la navegación.
    await page.getByRole("link", { name: /Volver al proyecto/ }).click();
    await expect(guardDialog.getByText(guardText)).toBeVisible();
    await guardDialog.getByRole("button", { name: "Cancelar", exact: true }).click();

    // "Nuevo vano" en el dock — el hallazgo dirty-link de la auditoría.
    await page.getByRole("tab", { name: "Vanos", exact: true }).click();
    const newVano = page.getByRole("link", { name: "Nuevo vano", exact: true });
    await expect(newVano).toBeVisible();
    await newVano.click();
    await expect(guardDialog.getByText(guardText)).toBeVisible();
    await guardDialog.getByRole("button", { name: "Cancelar", exact: true }).click();
    await expect(page).toHaveURL(/positions\/new/);
  });

  test("menor a 1024 px: vista de lectura con aviso, sin edición", async ({ page, manual }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await pickStarter(page, /Una hoja/);
    await page.setViewportSize({ width: 800, height: 700 });
    await expect(page.getByText(/edición.*desde 1024/i)).toBeVisible();
    await expect(page.locator(".editor-rail")).toBeHidden();
  });
});
