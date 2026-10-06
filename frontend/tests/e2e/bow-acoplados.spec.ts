/// <reference types="node" />
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, type Page } from "@playwright/test";

import type { PositionResponse, ProjectResponse } from "../../src/api/generated/models";
import { test } from "./support/manual-project-fixture";

test.use({ viewport: { width: 1440, height: 900 }, actionTimeout: 15_000 });

const CANVAS = ".assembly-canvas";
const PLAN = ".plan-strip";
const LIBRARY = /Biblioteca de diseños/;
const CAPTURES = resolve(import.meta.dirname, "../../../docs/redesign/captures/p06-bow-acoplados");

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
    data: { name: `Bow E2E ${crypto.randomUUID()}`, client_name: "E2E" },
  });
  expect(response.status()).toBe(201);
  return (await response.json()) as ProjectResponse;
}

async function openNewPosition(page: Page, project: ProjectResponse, systemId?: string) {
  const query = systemId ? `?system=${systemId}` : "";
  await page.goto(`/projects/${project.id}/positions/new${query}`);
  await expect(page.getByTestId("editor-strip")).toBeVisible();
  await page.waitForLoadState("networkidle");
}

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

test.describe("Bow/acoplados en el editor principal (P06)", () => {
  test("bow 3 módulos (centro fijo 1200, laterales 600 oscilobatiente, 2×22,5°) en ≤10 interacciones, guardado/reabierto idéntico", async ({
    page,
    manual,
  }) => {
    test.setTimeout(120_000);
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await expect(page.getByTestId("assembly-sheet")).toBeVisible();

    // Una "interacción" = un gesto con un solo intento (abrir el riel,
    // elegir la plantilla, teclear una cota+Enter). La plantilla Bow ×3 ya
    // trae el diseño canónico: centro fijo, laterales oscilobatientes y
    // 2×22,5° — sólo los anchos 600/1200/600 faltan sobre el reparto 3×500.
    let actions = 0;
    const act = async (gesture: () => Promise<unknown>): Promise<void> => {
      actions += 1;
      await gesture();
    };

    await act(() => page.getByRole("button", { name: LIBRARY }).click());
    await act(() => page.getByRole("button", { name: /Bow ×3/, exact: true }).click());

    // La planta acoplada aparece como franja inferior del lienzo.
    await expect(page.locator(PLAN)).toBeVisible();
    await expect(page.getByTestId("plan-module-m1")).toBeVisible();

    // El cuerpo del panel del árbol flota sobre el borde inferior del lienzo
    // (por diseño de P04): plegarlo es el gesto con que una persona alcanza
    // las cotas del pie del alzado.
    await act(() => page.getByRole("button", { name: "Plegar el panel" }).click());

    for (const [moduleId, mm] of [
      ["m1", "600"],
      ["m2", "1200"],
      ["m3", "600"],
    ] as const) {
      const label = `Módulo ${moduleId} Ancho`;
      await act(async () => {
        await page.getByLabel(label, { exact: true }).click();
        const field = page.getByRole("textbox", { name: label, exact: true });
        await field.fill(mm);
        await field.press("Enter");
      });
    }

    // Lo que el diseño ya tiene por plantilla se verifica, no se edita:
    // aperturas laterales oscilobatiente (simbolo en frente) y 2×22,5°.
    await expect(page.getByTestId("plan-angle-c1")).toContainText("22.5");
    await expect(page.getByTestId("plan-angle-c2")).toContainText("22.5");
    expect(actions, "crear el bow superó 10 interacciones").toBeLessThanOrEqual(10);

    // Cotas del conjunto etiquetadas en el encabezado de la franja.
    const measures = page.locator(".plan-strip__measures");
    await expect(measures).toContainText("Ancho desarrollado");
    await expect(measures).toContainText("Frente/cuerda");
    await expect(measures).toContainText("Proyección");

    // Guardar → la posición persiste el conjunto completo.
    const save = () => page.getByRole("button", { name: "Guardar", exact: true }).click();
    await expect(page.getByRole("button", { name: "Guardar", exact: true })).toBeEnabled({
      timeout: 20_000,
    });
    const saved = await responseTo<PositionResponse>(
      page,
      "POST",
      `/api/v1/projects/${project.id}/positions/`,
      201,
      save,
    );
    expect(saved.design.parametric_tree).toMatchObject({
      version: "product-v2",
      assembly: {
        couplings: [
          { id: "c1", angle_deg: "22.5" },
          { id: "c2", angle_deg: "22.5" },
        ],
      },
    });
    const tree = saved.design.parametric_tree as {
      assembly: { modules: { id: string; width_mm: string }[] };
    };
    expect(tree.assembly.modules.map((m) => [m.id, Number(m.width_mm)])).toEqual([
      ["m1", 600],
      ["m2", 1200],
      ["m3", 600],
    ]);

    // Reabrir: el editor vuelve con el mismo modelo (igualdad profunda).
    await page.goto(`/projects/${project.id}/positions/${saved.id}/edit`);
    const reopened = await responseTo<PositionResponse>(
      page,
      "GET",
      `/api/v1/positions/${saved.id}/`,
      200,
      () => page.reload(),
    );
    expect(reopened).toEqual(saved);
    await expect(page.locator(PLAN)).toBeVisible();
    await expect(page.getByTestId("plan-angle-c1")).toContainText("22.5");
  });

  test("selección plan↔frente sincronizada en ambos sentidos", async ({ page, manual }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await page.getByRole("button", { name: LIBRARY }).click();
    await page.getByRole("button", { name: /Bow ×3/, exact: true }).click();
    await expect(page.getByTestId("plan-module-m2")).toBeVisible();

    // Planta → frente: elegir m2 en la planta selecciona el módulo del frente.
    await page.getByTestId("plan-module-m2").click();
    const selectedModule = page.locator(`${CANVAS} .front-module.is-selected`);
    await expect(selectedModule).toHaveCount(1);
    const moduleInspector = page.locator('section.assembly-inspector[aria-label="Módulo"]');
    await expect(moduleInspector).toBeVisible();
    await expect(moduleInspector).toContainText("Módulo 2");

    // Frente → planta: elegir un vano del módulo m3 en el frente marca su
    // módulo en la planta.
    await page
      .getByRole("button", { name: /Paño ·/ })
      .nth(2)
      .click();
    await expect(page.getByTestId("plan-module-m3")).toHaveClass(/is-selected/);
  });

  test("elevación Desarrollada/Proyectada alterna el ancho del frente", async ({
    page,
    manual,
  }) => {
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await page.getByRole("button", { name: LIBRARY }).click();
    await page.getByRole("button", { name: /Bow ×3/, exact: true }).click();
    await expect(page.getByTestId("plan-module-m1")).toBeVisible();

    const seg = page.locator(".plan-strip__elevation");
    await expect(seg.getByRole("button", { name: "Desarrollada" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // La lámina reencuadra el contenido al ajustar la vista, así que el
    // ancho real se lee en la cota «Ancho total» del frente (mm en el svg).
    const totalDim = page.getByTestId("product-front").getByLabel("Ancho total", { exact: true });
    const readTotalMm = async (): Promise<number> =>
      Number.parseFloat(
        ((await totalDim.textContent()) ?? "").replace(/[^\d,.-]/g, "").replace(",", "."),
      );
    const developed = await readTotalMm();
    expect(developed).toBeGreaterThan(0);
    await seg.getByRole("button", { name: "Proyectada" }).click();
    await expect(seg.getByRole("button", { name: "Proyectada" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const projected = await readTotalMm();
    expect(projected, "la proyección acorta el frente").toBeLessThan(developed);
    expect(projected).toBeGreaterThan(0);
    // La cota proyectada se lee con formato de taller (≤2 decimales), nunca
    // un float del motor — y en vista proyectada las cotas son solo-lectura:
    // el ancho declarado se edita en desarrollada.
    const totalText = (await totalDim.textContent()) ?? "";
    // Sin separadores finos: dígitos enteros + como máximo ",NN".
    expect(totalText.replace(/\s/g, "")).toMatch(/^\d+(,\d{1,2})?$/);
    await expect(
      page.getByTestId("product-front").getByLabel("Ancho total", { exact: true }),
    ).toHaveAttribute("tabindex", "-1");
    await expect(page.getByLabel(/Módulo m1 Ancho/)).toHaveAttribute("tabindex", "-1");
  });

  // Capturas del encargo — caen en docs/redesign/captures/p06-bow-acoplados/
  // (documentación del antes/después, como hace el spec de P12).
  test("capturas: bow desarrollada/proyectada, selección de unión y 1024", async ({
    page,
    manual,
  }) => {
    mkdirSync(CAPTURES, { recursive: true });
    const project = await newProject(page, manual.organizationId);
    await openNewPosition(page, project, manual.systemId);
    await page.getByRole("button", { name: LIBRARY }).click();
    await page.getByRole("button", { name: /Bow ×3/, exact: true }).click();
    await expect(page.getByTestId("plan-module-m1")).toBeVisible();
    await expect(page.getByTestId("plan-angle-c2")).toContainText("22.5");

    await page.screenshot({
      path: resolve(CAPTURES, "editor-bow-desarrollada-1440x900-light.png"),
      fullPage: false,
    });

    await page
      .locator(".plan-strip__elevation")
      .getByRole("button", { name: "Proyectada" })
      .click();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: resolve(CAPTURES, "editor-bow-proyectada-1440x900-light.png"),
      fullPage: false,
    });
    await page
      .locator(".plan-strip__elevation")
      .getByRole("button", { name: "Desarrollada" })
      .click();

    // Unión c1 seleccionada → inspector del acoplado con el cople filtrado.
    // La etiqueta del ángulo se pinta sobre el vértice: un clic en la zona
    // baja de la manija de la bisagra selecciona la unión (sin arrastrar).
    const joint = page.getByTestId("plan-joint-c1");
    const jointBox = await joint.boundingBox();
    expect(jointBox).not.toBeNull();
    await joint.click({
      position: { x: jointBox!.width / 2, y: jointBox!.height * 0.8 },
    });
    await expect(page.locator('section.assembly-inspector[aria-label="Unión"]')).toContainText(
      "Unión 1",
    );
    await page.screenshot({
      path: resolve(CAPTURES, "editor-bow-union-inspector-1440x900-light.png"),
      fullPage: false,
    });

    await page.emulateMedia({ colorScheme: "dark" });
    await page.screenshot({
      path: resolve(CAPTURES, "editor-bow-desarrollada-1440x900-dark.png"),
      fullPage: false,
    });
    await page.emulateMedia({ colorScheme: "light" });

    await page.setViewportSize({ width: 1024, height: 768 });
    await expect(page.getByTestId("plan-module-m1")).toBeVisible();
    await page.screenshot({
      path: resolve(CAPTURES, "editor-bow-1024x768-light.png"),
      fullPage: false,
    });
  });
});
