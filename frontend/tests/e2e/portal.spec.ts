/// <reference types="node" />
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { environment } from "./support/environment";

/** Portal público de cotización (P10): estados honestos, decisión con
 * evidencia, marca del emisor y cobro simulado. Corre dentro del stack vivo
 * de `make test-db` (Django :8000 + Vite :5173 + FLOW_WS_MOCK=1). */

const REPO = resolve(import.meta.dirname, "../../..");
const FIXTURE = resolve(REPO, "scripts/dev_fixture.py");
const STATE = resolve(REPO, ".fixture-state.json");

const SUPABASE_URL = (environment("SUPABASE_URL") ?? "http://127.0.0.1:25321").replace(/\/$/, "");
const DJANGO_URL = (environment("DJANGO_URL") ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const ANON_KEY = environment("SUPABASE_ANON_KEY") ?? "";

type FixtureState = {
  org_id: string;
  password: string;
  projects: Record<string, { id: string; name: string }>;
  portal: Record<string, string>;
};

function readState(): FixtureState {
  if (!existsSync(STATE)) {
    // La spec depende de los tokens del fixture — si el gate corre esta
    // spec sola, la fixture se instala aquí una sola vez.
    const venvPython = resolve(REPO, ".venv/bin/python");
    const python = existsSync(venvPython) ? venvPython : "python3";
    execFileSync(python, [FIXTURE], {
      cwd: REPO,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 360_000,
    });
  }
  return JSON.parse(readFileSync(STATE, "utf8")) as FixtureState;
}

function digits(text: string): number {
  // "$1.435.471" → 1435471 (es-CL: punto como separador de miles).
  return Number(text.replace(/[^\d]/g, ""));
}

async function estimatorToken(state: FixtureState): Promise<string> {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "demo-estimator@fixture.dekopen.local",
      password: state.password,
    }),
  });
  expect(response.status, "login del estimador de fixture").toBeLessThan(300);
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

async function mintLink(state: FixtureState, projectSlug: string): Promise<string> {
  const token = await estimatorToken(state);
  const projectId = state.projects[projectSlug]?.id;
  expect(projectId, `fixture sin proyecto ${projectSlug}`).toBeTruthy();
  const response = await fetch(`${DJANGO_URL}/api/v1/projects/${projectId}/quote-link/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Organization-ID": state.org_id,
      "Content-Type": "application/json",
    },
  });
  expect(response.status, "mint de link").toBeLessThan(300);
  const body = (await response.json()) as { token?: string };
  expect(body.token).toBeTruthy();
  return body.token as string;
}

async function openPortal(page: Page, token: string) {
  await page.goto(`/cotizacion/${token}`);
  // La data viene del API público: esperar a que la página muestre contenido
  // real (propuesta, estado dedicado o error) — el loading usa role=status
  // igual que los banners decididos, así que no sirve como señal de espera.
  await expect(
    page
      .locator(
        ".portal-proposal__summary, .portal-state, .portal-decided, .portal-card [role=alert]",
      )
      .first(),
  ).toBeVisible({ timeout: 30_000 });
}

let state: FixtureState;

test.beforeAll(() => {
  state = readState();
  for (const key of [
    "vigente",
    "vitrina",
    "aprobada",
    "reemplazada",
    "parcial",
    "revocada",
    "expirada",
    "cambios",
    "usd",
    "rechazada",
  ]) {
    expect(state.portal[key], `fixture sin token portal.${key}`).toBeTruthy();
  }
});

test.describe.configure({ mode: "serial" });

test("cotización vigente: marca del fabricante, posiciones y suma de líneas = total", async ({
  page,
}) => {
  await openPortal(page, state.portal["vitrina"]!);

  // Marca del emisor — el cliente ve al fabricante, no a DEKOPEN.
  const issuer = page.locator(".portal-proposal__issuer");
  await expect(issuer).toContainText("Ventanas del Sur SpA");
  await expect(issuer.locator(".portal-proposal__logo")).toBeVisible();

  // Hero: obra, cliente y total IVA incluido.
  await expect(page.locator(".portal-proposal__refs")).toContainText("Casa Ríos");
  await expect(page.locator(".portal-proposal__summary")).toContainText("Colegio San Patricio");
  const grossText = await page.locator(".portal-totals__gross dd").innerText();
  const gross = digits(grossText);
  expect(gross, "total del encabezado").toBeGreaterThan(0);

  // 12 posiciones: 11 incluidas + 1 alternativa real (is_option).
  const included = page.locator(".portal-positions .portal-position:not([data-option])");
  await expect(included).toHaveCount(11);
  const options = page.locator('.portal-options .portal-position[data-option="true"]');
  await expect(options).toHaveCount(1);
  await expect(options.first()).toContainText("V12 Alternativa corredera");
  await expect(page.locator(".portal-options")).toContainText("no incluidas en el total");

  // La suma de líneas incluidas (bruto por línea) iguala el total IVA incluido.
  let sum = 0;
  for (const line of await included.locator(".portal-position__price strong").all()) {
    sum += digits(await line.innerText());
  }
  expect(sum, "suma de líneas = total del encabezado").toBe(gross);

  // La alternativa muestra su propio precio pero marcada fuera del total.
  const optionPrice = digits(
    await options.first().locator(".portal-position__price strong").innerText(),
  );
  expect(optionPrice, "la alternativa está precificada").toBeGreaterThan(0);
});

test("cotización vigente: decisión exige nombre + RUT válido + aceptación literal", async ({
  page,
}) => {
  // Link nuevo: decidir consume el token, no se reutiliza el del fixture.
  // conjuntos está QUOTED y sellado — minta sin tocar los tokens del fixture.
  const token = await mintLink(state, "conjuntos");
  await openPortal(page, token);

  const approve = page.getByRole("button", { name: "Aprobar propuesta" });
  await expect(approve).toBeDisabled();

  const acceptance = page.locator(".portal-decision__accept");
  await expect(acceptance).toContainText("Acepto la propuesta COT-");
  await expect(acceptance).toContainText("IVA incluido");

  await page.locator("#portal-name").fill("Juan Carlos Muñoz Vera");
  await page.locator("#portal-rut").fill("12.345.678-9"); // dígito malo
  await acceptance.locator("input[type=checkbox]").check();
  await expect(page.getByRole("alert").filter({ hasText: "dígito verificador" })).toBeVisible();
  await expect(approve).toBeDisabled();

  await page.locator("#portal-rut").fill("11.222.333-9");
  await expect(approve).toBeEnabled();
});

test("aprobar deja evidencia pública sin exponer datos internos", async ({ page }) => {
  const token = await mintLink(state, "conjuntos");
  await openPortal(page, token);

  await page.locator("#portal-name").fill("Juan Carlos Muñoz Vera");
  await page.locator("#portal-rut").fill("11.222.333-9");
  await page.locator(".portal-decision__accept input[type=checkbox]").check();
  await page.getByRole("button", { name: "Aprobar propuesta" }).click();

  const decided = page.locator('.portal-decided[data-state="approved"]');
  await expect(decided).toContainText("Propuesta aprobada", { timeout: 30_000 });
  const evidence = page.locator(".portal-evidence");
  await expect(evidence).toContainText("Acepto la propuesta COT-");
  // El evento público no publica RUT/IP/user-agent — son del estimador.
  await expect(evidence).not.toContainText("11.222.333-9");
});

test("estados honestos: revocada, expirada, rechazada, cambios y parcial", async ({ page }) => {
  await openPortal(page, state.portal["revocada"]!);
  await expect(page.locator(".portal-state")).toContainText("Este enlace fue anulado");
  await expect(page.getByRole("button", { name: "Aprobar propuesta" })).toHaveCount(0);

  await openPortal(page, state.portal["expirada"]!);
  await expect(page.locator(".portal-state")).toContainText("La cotización venció");

  await openPortal(page, state.portal["rechazada"]!);
  await expect(page.locator('.portal-decided[data-state="declined"]')).toContainText(
    "Propuesta rechazada",
  );

  await openPortal(page, state.portal["cambios"]!);
  await expect(page.locator('.portal-decided[data-state="changes"]')).toContainText(
    "Pediste cambios",
  );

  // Aprobada con anticipo pagado: saldo pendiente, CTA de pago sigue activo.
  await openPortal(page, state.portal["parcial"]!);
  await expect(page.locator(".portal-payment")).toContainText("Abonado parcial");
  await expect(page.locator(".portal-paybox")).toBeVisible();
});

test("reemplazada: el seguimiento abre la cotización vigente", async ({ page }) => {
  await openPortal(page, state.portal["reemplazada"]!);
  await expect(page.locator(".portal-state")).toContainText("Esta propuesta fue reemplazada");
  await page.getByRole("button", { name: "Ver la cotización vigente" }).click();
  await expect(page).toHaveURL(/\/cotizacion\//, { timeout: 30_000 });
  await expect(page.locator(".portal-proposal__refs")).toContainText("Casa Molina");
});

test("enlace inexistente muestra página dedicada, no error genérico", async ({ page }) => {
  await page.goto("/cotizacion/token-inexistente-123");
  await expect(page.getByRole("alert")).toContainText("Este enlace de cotización no existe");
});

test("cotización aprobada: CTA de pago simulado completa el ciclo", async ({ page }) => {
  await openPortal(page, state.portal["aprobada"]!);
  const paybox = page.locator(".portal-paybox");
  await expect(paybox).toBeVisible();
  await expect(paybox).toContainText("Modo de prueba");

  await page.locator("#portal-payer").fill("pagador@correo.cl");
  await page.locator(".portal-pay").click();

  // Checkout simulado del proveedor → pagar → retorno al portal con estado.
  await expect(page.getByText("PAGO SIMULADO — SIN CARGO REAL")).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: "Pagar" }).click();
  await expect(page).toHaveURL(/\/cotizacion\/.+flow_token=/, { timeout: 30_000 });
  await expect(page.locator(".portal-payment")).toContainText("Pagado", {
    timeout: 30_000,
  });
});

test("cotización en USD: el CTA de pago no existe (sin fraude)", async ({ page }) => {
  await openPortal(page, state.portal["usd"]!);
  await expect(page.locator(".portal-proposal__refs")).toContainText("Bodega");
  await expect(page.locator(".portal-paybox")).toHaveCount(0);
  await expect(page.locator(".portal-pay")).toHaveCount(0);
});

test("portal móvil 390×844: sin scroll horizontal y decisión usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openPortal(page, state.portal["vitrina"]!);
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth, "sin overflow horizontal a 390px").toBeLessThanOrEqual(390);
  await expect(page.getByRole("button", { name: "Aprobar propuesta" })).toBeVisible();
  await expect(page.locator(".portal-proposal__issuer")).toContainText("Ventanas del Sur SpA");
});

test("axe: portal sin violaciones serious ni critical (1440 y 390)", async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await openPortal(page, state.portal["vigente"]!);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious, `${width}px: ${serious.map((v) => v.id).join(", ")}`).toHaveLength(0);
  }
});
