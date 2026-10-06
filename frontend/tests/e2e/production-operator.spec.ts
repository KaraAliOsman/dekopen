/// <reference types="node" />
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { environment } from "./support/environment";
import { waitForMagicLink } from "./support/mailpit";

/** P12 — recorrido del operario en tablet (1024×768, oscuro): elige su
 * estación, ve solo su cola, completa un paso, bloquea el siguiente con
 * motivo predefinido; el jefe ve el bloqueo en el tablero y en «Hoy».
 * Corre dentro de `make test-db` (Django + Vite + Supabase + Mailpit vivos).
 *
 * Física del recorrido: al completar el paso de su estación la OT sale de
 * su cola (el siguiente paso es de otra estación), así que el bloqueo cae
 * sobre la SIGUIENTE OT de la misma cola — que es lo que el jefe revisa. */

const REPO = resolve(import.meta.dirname, "../../..");
const FIXTURE = resolve(REPO, "scripts/dev_fixture.py");
const STATE = resolve(REPO, ".fixture-state.json");
// Las capturas del encargo caen en el repo (documentación del producto, no
// artefactos efímeros del runner).
const CAPTURES = resolve(REPO, "docs/redesign/captures/p12-produccion");

const SUPABASE_URL = (environment("SUPABASE_URL") ?? "http://127.0.0.1:25321").replace(/\/$/, "");
const MAILPIT_URL = environment("MAILPIT_URL") ?? "http://127.0.0.1:25324";
const SERVICE_KEY = environment("SUPABASE_SERVICE_ROLE_KEY") ?? "";

type Row = Record<string, unknown>;

async function restRows(path: string): Promise<Row[]> {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`REST ${path}: HTTP ${response.status}`);
  return (await response.json()) as Row[];
}

async function loginAs(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Correo", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Enviar enlace de acceso", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Revisa tu correo para continuar");
  const message = await waitForMagicLink({
    baseUrl: MAILPIT_URL,
    supabaseUrl: SUPABASE_URL,
    recipient: email,
  });
  await page.goto(message.link);
  await expect(page.getByTestId("app-shell")).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("operario: su estación → completa → bloquea → el jefe lo ve", async ({ page, browser }) => {
  // El fixture demo es pesado en un stack limpio (P-ESCALA sella y libera
  // ~100 OTs para la prueba de escala del tablero): el presupuesto es real.
  test.setTimeout(900_000);
  expect(SERVICE_KEY, "SUPABASE_SERVICE_ROLE_KEY must be set by the gate").not.toBe("");

  // El fixture demo es idempotente: garantiza OTs liberadas, pasos por
  // estación y las cuentas de rol.
  const venvPython = resolve(REPO, ".venv/bin/python");
  execFileSync(existsSync(venvPython) ? venvPython : "python3", [FIXTURE], {
    cwd: REPO,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 600_000,
  });
  const state = JSON.parse(readFileSync(STATE, "utf8")) as {
    org_id: string;
    orders: Record<string, string>;
  };
  expect(state.orders.liberada, "el fixture debe liberar una OT").toBeTruthy();
  expect(state.orders.escala, "el fixture debe liberar la OT de escala").toBeTruthy();

  // La OT operable: cualquier OT viva cuyo PRIMER paso abierto no sea QC —
  // el operario no firma calidad (_QC_STEP_ACTORS excluye OPERATOR) y un paso
  // QC en curso bloquea el START del resto (step_sequence_blocked). El
  // fixture acumula DONE entre corridas, así que el objetivo se resuelve
  // vivo en vez de fijarse a la OT liberada.
  const openSteps = await restRows(
    `production_steps?status=not.eq.DONE&order=order_id,sequence&select=order_id,code,sequence&limit=4000`,
  );
  const firstOpen = new Map<string, Row>();
  for (const step of openSteps) {
    const orderId = String(step.order_id);
    if (!firstOpen.has(orderId)) firstOpen.set(orderId, step);
  }
  const liveOrders = await restRows(
    `orders?order_type=eq.WORKSHOP_OT&status=in.(RELEASED,IN_PROGRESS)&select=id,order_code,payload_json&limit=400`,
  );
  const liveById = new Map(liveOrders.map((row) => [String(row.id), row]));
  // Las estaciones de material exigen plan de corte vigente: el objetivo debe
  // tener optimización viva o el backend rechaza el START/COMPLETE.
  const hasLivePlan = (row: Row | undefined): boolean => {
    const optimization = (row?.payload_json as Row | undefined)?.optimization as Row | undefined;
    return Boolean(optimization) && !optimization?.invalidated;
  };
  const viable = [...firstOpen.values()].filter(
    (step) => String(step.code) !== "QC" && liveById.has(String(step.order_id)),
  );
  const target =
    viable.find((step) => hasLivePlan(liveById.get(String(step.order_id)))) ?? viable[0];
  expect(
    target,
    "el fixture debe ofrecer una OT viva con un primer paso abierto no-QC",
  ).toBeTruthy();
  const stationCode = String(target!.code);
  const liberadaCode = String(liveById.get(String(target!.order_id))!.order_code);

  // ---- Operario: tablet 1024×768, tema taller (oscuro) -----------------
  await page.setViewportSize({ width: 1024, height: 768 });
  await loginAs(page, "demo-operator@fixture.dekopen.local");
  await page.goto("/production");

  // La densidad workshop fija el tema oscuro y objetivos de 44 px.
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");
  await expect
    .poll(() => page.evaluate(() => document.documentElement.dataset.density))
    .toBe("workshop");

  // Ve solo su estación: elige la estación del primer paso abierto.
  const stationButton = page.locator(
    `.operator-station-pick__grid button[data-station="${stationCode}"]`,
  );
  await expect(stationButton).toBeVisible({ timeout: 30_000 });
  await stationButton.click();

  // Abre la OT liberada desde la cola (tarjeta «Siguiente» o fila) — la
  // estación puede tener ~100 OTs en cola (fixture P-ESCALA).
  const liberadaEntry = page
    .locator(".operator-next__card", { hasText: liberadaCode })
    .or(page.locator(".operator-queue-row", { hasText: liberadaCode }))
    .first();
  await expect(liberadaEntry).toBeVisible({ timeout: 30_000 });
  await liberadaEntry.click();

  // Detalle de la OT: solo el paso de su estación, sin datos comerciales.
  await expect(page.locator(".operator-order-code")).toBeVisible();
  const completedCode = (await page.locator(".operator-order-code").innerText()).trim();
  expect(completedCode).toBe(liberadaCode);

  // Completa el paso de su estación: Comenzar → evidencia de ops →
  // Completar. Las estaciones de miembros exigen declarar las operaciones
  // hechas — «Marcar todas» es el gesto del operario.
  const startBtn = page.getByRole("button", { name: "Comenzar", exact: true }).first();
  if (await startBtn.isVisible().catch(() => false)) await startBtn.click();
  const markAll = page.getByRole("button", { name: "Marcar todas", exact: true });
  if (await markAll.isVisible().catch(() => false)) {
    await markAll.click();
  } else {
    const singleOp = page.locator('input[type="checkbox"]').first();
    if (await singleOp.isVisible().catch(() => false)) await singleOp.check();
  }
  const completeBtn = page.getByRole("button", { name: "Completar", exact: true }).first();
  await expect(completeBtn).toBeVisible({ timeout: 30_000 });
  await completeBtn.click();
  // Al terminar, su estación ya no tiene paso abierto en esta OT: vuelve a
  // la cola donde lo espera la siguiente OT.
  const back = page.locator(".operator-back");
  await expect(back).toBeVisible({ timeout: 30_000 });
  await back.click();

  // Siguiente OT en la misma cola: la bloquea con un motivo predefinido.
  // La cola se recarga tras la acción — espera a que la OT completada salga
  // de la tarjeta «Siguiente» antes de abrir la que sigue.
  const nextAfter = page.locator(".operator-next__card").first();
  await expect(nextAfter).toBeVisible({ timeout: 30_000 });
  await expect(nextAfter).not.toContainText(completedCode, { timeout: 30_000 });
  await nextAfter.click();
  const blockedCode = (await page.locator(".operator-order-code").innerText()).trim();
  expect(blockedCode).not.toBe("");
  expect(blockedCode).not.toBe(completedCode);

  const blockBtn = page.getByRole("button", { name: "Bloquear", exact: true }).first();
  await expect(blockBtn).toBeEnabled({ timeout: 30_000 });
  await blockBtn.click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Máquina detenida", exact: true })
    .click();
  await expect(page.locator(".operator-blocked-hint")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".operator-blocked-hint")).toContainText("Máquina detenida");

  await page.screenshot({
    path: resolve(CAPTURES, "operario-bloqueo-1024x768.png"),
    fullPage: false,
  });

  // ---- Jefe de producción: tablero + «Hoy» -----------------------------
  const managerContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const manager = await managerContext.newPage();
  try {
    await loginAs(manager, "demo-manager@fixture.dekopen.local");
    await manager.goto("/production");
    const otCard = manager.locator(".board-card", { hasText: blockedCode });
    await expect(otCard).toBeVisible({ timeout: 30_000 });
    await expect(otCard.locator(".board-chip", { hasText: "Bloqueada" })).toBeVisible();
    await manager.screenshot({
      path: resolve(CAPTURES, "tablero-bloqueo-1440x900.png"),
      fullPage: false,
    });

    // Detalle de la OT bloqueada: cabecera + stepper + pestañas visibles sin
    // más de dos pantallas de scroll hasta ellas (criterio del encargo).
    await otCard.click();
    await expect(manager.locator(".ui-tabs").first()).toBeVisible({ timeout: 30_000 });
    await manager.screenshot({
      path: resolve(CAPTURES, "detalle-ot-1440x900.png"),
      fullPage: false,
    });

    // ---- Escala: la OT de 100 posiciones es interactiva en < 2 s ----------
    // La métrica del encargo es abrir la OT desde el tablero ya cargado
    // (la SPA fría en vite-dev suma ~1 s de transformación de módulos que
    // no es código de producto): click en tarjeta → pestañas usables.
    await manager.goto("/production");
    await expect(manager.locator(".board-card").first()).toBeVisible({ timeout: 30_000 });
    const escala = (
      await restRows(`orders?id=eq.${state.orders.escala}&select=order_code&limit=1`)
    )[0]!;
    const escalaCard = manager.locator(".board-card", { hasText: String(escala.order_code) });
    await escalaCard.scrollIntoViewIfNeeded({ timeout: 30_000 });
    const t0 = Date.now();
    await escalaCard.click();
    await expect(manager.locator(".ui-tabs").first()).toBeVisible({ timeout: 30_000 });
    const tabsMs = Date.now() - t0;
    await manager.getByRole("tab", { name: "Piezas", exact: true }).click();
    const t1 = Date.now();
    await expect(manager.locator(".piece-list").first()).toBeVisible({ timeout: 30_000 });
    const piecesMs = Date.now() - t1;
    const totalMs = Date.now() - t0;
    const measure =
      `OT de 100 posiciones (P-ESCALA, ${String(escala.order_code)}): ` +
      `detalle con pestañas en ${tabsMs} ms, pestaña Piezas en ${piecesMs} ms, ` +
      `total ${totalMs} ms (click en tarjeta → interactiva, stack local caliente).`;
    console.log(`[P12 escala] ${measure}`);
    writeFileSync(resolve(CAPTURES, "medida-escala.txt"), `${measure}\n`);
    expect(totalMs, "la OT de 100 posiciones debe abrir interactiva en < 2 s").toBeLessThan(2000);

    await manager.screenshot({
      path: resolve(CAPTURES, "detalle-ot-piezas-1440x900.png"),
      fullPage: false,
    });

    await manager.goto("/dashboard");
    // «Hoy» del jefe (P03): la OT detenida entra como «en espera» y la
    // estación declara sus «bloqueado» — el bloqueo del operario se ve.
    await expect(manager.getByText(/OTs? en espera/).first()).toBeVisible({
      timeout: 20_000,
    });
    await expect(manager.getByText(/bloqueado/).first()).toBeVisible({ timeout: 20_000 });
  } finally {
    await managerContext.close();
  }
});
