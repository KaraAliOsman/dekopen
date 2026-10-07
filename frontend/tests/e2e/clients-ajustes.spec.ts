/// <reference types="node" />
import { expect, type Page } from "@playwright/test";

import { test } from "./support/manual-project-fixture";

/** P22 e2e — runs inside `make test-db`'s live-stack window (Django + Vite +
 * Supabase + Mailpit up; SUPABASE_* envs set by the gate). The fixture logs an
 * ESTIMATOR in through the real magic-link flow. */

test.use({ viewport: { width: 1366, height: 768 }, actionTimeout: 15_000 });

async function api(
  page: Page,
  method: string,
  path: string,
  orgId: string,
  body?: unknown,
): Promise<{ status: number; data: any }> {
  const token = await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) {
      if (key.includes("auth-token")) {
        try {
          const raw = JSON.parse(localStorage.getItem(key) ?? "{}");
          return (raw.access_token as string) ?? "";
        } catch {
          return "";
        }
      }
    }
    return "";
  });
  expect(token, "session token should be readable").not.toBe("");
  const options = {
    data: body,
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Organization-ID": orgId,
      "Content-Type": "application/json",
    },
  };
  const response =
    method === "GET"
      ? await page.request.get(`http://localhost:8000${path}`, options)
      : await page.request.post(`http://localhost:8000${path}`, options);
  const text = await response.text();
  return { status: response.status(), data: text ? JSON.parse(text) : null };
}

test("cliente empresa con dos obras → proyecto elige una → cotización la usa", async ({
  page,
  manual,
}) => {
  test.setTimeout(180_000);
  const org = manual.organizationId;

  await page.goto("/clients");
  await page.getByRole("button", { name: "Nuevo cliente", exact: true }).first().click();

  const name = `E2E Constructora ${crypto.randomUUID().slice(0, 8)}`;
  await page.getByLabel("Tipo de cliente").selectOption("COMPANY");
  await page.getByRole("textbox", { name: "Nombre", exact: true }).fill(name);
  await page.getByRole("textbox", { name: "RUT", exact: true }).fill("77.777.777-7");
  await page.getByRole("textbox", { name: "Giro", exact: true }).fill("Construcción");
  await page.getByRole("button", { name: "Agregar contacto", exact: true }).click();
  await page.getByLabel("Nombre del contacto").fill("María Obras");
  await page.getByLabel("Rol (ej. comprador, jefe de obra)").fill("Comprador");
  await page.getByRole("button", { name: "Agregar dirección de obra", exact: true }).click();
  await page.getByLabel("Etiqueta (ej. Obra Av. Kennedy)").fill("Casa Matriz");
  await page.getByLabel("Dirección de la obra").fill("Av. Kennedy 9000");
  await page.getByLabel("Comuna", { exact: true }).nth(1).fill("Vitacura");
  await page.getByRole("button", { name: "Agregar dirección de obra", exact: true }).click();
  await page.getByLabel("Etiqueta (ej. Obra Av. Kennedy)").nth(1).fill("Obra Ñuñoa");
  await page.getByLabel("Dirección de la obra").nth(1).fill("Irarrázaval 1234");
  await page.getByLabel("Comuna", { exact: true }).nth(2).fill("Ñuñoa");
  await page.getByRole("button", { name: "Guardar", exact: true }).click();

  // Ficha: contactos, obras y notas con autor.
  await expect(page.getByText("María Obras")).toBeVisible();
  await expect(page.getByText("Av. Kennedy 9000")).toBeVisible();
  await expect(page.getByText("Irarrázaval 1234")).toBeVisible();
  await expect(page.locator("h2").getByText("Empresa", { exact: true })).toBeVisible();
  await page.getByPlaceholder(/Escribe una nota/).fill("Llamar antes de facturar");
  await page.getByRole("button", { name: "Agregar nota", exact: true }).click();
  await expect(page.getByText("Llamar antes de facturar")).toBeVisible();

  // Proyecto: elegir el cliente y la segunda obra registrada.
  await page.goto("/projects");
  await page.getByRole("button", { name: "Crear proyecto", exact: true }).click();
  await page.locator("summary", { hasText: "Datos adicionales" }).click();
  await page.getByLabel("Nombre del proyecto", { exact: true }).fill("E2E proyecto obra");
  await page.getByLabel("Cliente registrado").selectOption({ label: `${name} · 77.777.777-7` });
  await page
    .getByLabel("Dirección de obra registrada")
    .selectOption({ label: "Obra Ñuñoa — Irarrázaval 1234, Ñuñoa" });
  const delivery = page.getByRole("textbox", { name: "Dirección de entrega" });
  await expect(delivery).toHaveValue("Obra Ñuñoa: Irarrázaval 1234, Ñuñoa");
  await page.getByRole("button", { name: "Guardar", exact: true }).click();

  // La cotización (documentos) lee la dirección elegida en el proyecto.
  const found = await api(page, "GET", "/api/v1/projects/?q=E2E%20proyecto%20obra", org);
  expect(found.status).toBe(200);
  const project = (found.data.items ?? []).find(
    (item: { name: string }) => item.name === "E2E proyecto obra",
  );
  expect(project).toBeTruthy();
  expect(project.delivery_address).toBe("Obra Ñuñoa: Irarrázaval 1234, Ñuñoa");
});

test("duplicado de RUT aparece y la fusión queda auditada", async ({ page, manual }) => {
  test.setTimeout(120_000);
  const org = manual.organizationId;

  // Dos clientes con el mismo RUT normalizado pero distinto texto — el
  // índice único del texto deja pasar ambos y la bandera los detecta.
  const first = await api(page, "POST", "/api/v1/clients/", org, {
    name: "Duplicado Uno E2E",
    rut: "11.111.111-1",
    kind: "PERSON",
  });
  expect(first.status).toBe(201);
  const second = await api(page, "POST", "/api/v1/clients/", org, {
    name: "Duplicado Dos E2E",
    rut: "11111111-1",
    kind: "PERSON",
  });
  expect(second.status).toBe(201);

  const dup = await api(page, "GET", "/api/v1/clients/duplicates/", org);
  expect(dup.status).toBe(200);
  const group = (dup.data.items ?? []).find((item: { rut: string }) => item.rut === "111111111");
  expect(group, "RUT group should be flagged").toBeTruthy();

  await page.goto("/clients");
  await expect(page.getByText("Posibles duplicados por RUT:")).toBeVisible();
  await expect(page.locator(".clients-duplicates p").first()).toContainText("111111111");

  // Fusión vía UI: el absorbido desaparece, el sobreviviente audita.
  await page
    .locator(".clients-duplicates")
    .getByRole("button", { name: "Fusionar" })
    .first()
    .click();
  // La UI fusiona el primer cliente del grupo dentro del segundo.
  await page
    .getByRole("group", { name: "Fusionar clientes" })
    .getByRole("combobox")
    .selectOption({ label: "Duplicado Dos E2E · 11111111-1" });
  await page.getByRole("button", { name: "Fusionar ahora", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(page.getByText(/Clientes fusionados/)).toBeVisible();
  const gone = await api(page, "GET", `/api/v1/clients/${first.data.id}/`, org);
  expect(gone.status).toBe(200);
  expect(gone.data.client.merged_into).toBe(second.data.id);
  const ficha = await api(page, "GET", `/api/v1/clients/${second.data.id}/`, org);
  expect(ficha.status).toBe(200);
  expect(ficha.data.merges.length).toBeGreaterThanOrEqual(1);
});

test("ajustes: secciones, permisos por rol y consumo por cotización", async ({ page, manual }) => {
  test.setTimeout(120_000);
  const org = manual.organizationId;

  // Nav lateral con las secciones del encargo. El GET de la sección puebla el
  // formulario: registrarlo antes de navegar evita que una respuesta tardía
  // pise el valor tipeado más abajo.
  const settingsRead = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/organization/settings/") &&
      response.request().method() === "GET",
  );
  await page.goto("/settings/comercial");
  await settingsRead;
  await expect(page.getByRole("link", { name: "Empresa", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Comercial", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Numeración", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Integraciones", exact: true })).toBeVisible();
  // ESTIMATOR no abre Usuarios y roles ni Plan — deshabilitados con razón.
  const usuarios = page.getByText("Usuarios y roles", { exact: true });
  await expect(usuarios).toBeVisible();
  await expect(page.getByRole("link", { name: "Usuarios y roles" })).toHaveCount(0);
  // El backend también bloquea: la API de miembros exige OWNER.
  const members = await api(page, "GET", "/api/v1/organization/members/", org);
  expect(members.status).toBe(403);

  // Comercial: cambiar la vigencia por defecto la consume la cotización.
  const validity = page.getByLabel("Vigencia por defecto (días)");
  await validity.fill("21");
  const commercialSave = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/organization/settings/commercial/") &&
      response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "Guardar comercial", exact: true }).click();
  await expect(page.getByText("Marca guardada.")).toBeVisible();
  const savedPayload = (await commercialSave).request().postDataJSON() as {
    doc_validity_days?: number;
  };
  expect(savedPayload.doc_validity_days).toBe(21);

  // Un proyecto nuevo consume el valor de la sección en su preparación.
  const holder = await api(page, "POST", "/api/v1/clients/", org, {
    name: `E2E Consumo Spa ${crypto.randomUUID().slice(0, 8)}`,
  });
  expect(holder.status).toBe(201);
  const created = await api(page, "POST", "/api/v1/projects/", org, {
    name: `E2E consumo ${crypto.randomUUID().slice(0, 8)}`,
    client_name: holder.data.name,
    client_id: holder.data.id,
  });
  expect(created.status).toBe(201);
  const prep = await api(page, "GET", `/api/v1/documents/projects/${created.data.id}/inputs/`, org);
  expect(prep.status).toBe(200);
  expect(prep.data.doc_validity_days).toBe(21);

  // Numeración es solo lectura y muestra prefijos reales.
  await page.goto("/settings/numeracion");
  await expect(page.getByText("Solo lectura", { exact: false })).toBeVisible();
  await expect(page.getByRole("cell", { name: "P-", exact: true })).toBeVisible();

  // Integraciones: estado declarado por integración, sin secretos.
  await page.goto("/settings/integraciones");
  await expect(page.getByText("Flow (cobros)", { exact: true })).toBeVisible();
  await expect(page.getByText("SII / DTE", { exact: true })).toBeVisible();
  await expect(page.getByText("Proveedor de IA", { exact: true })).toBeVisible();
});
