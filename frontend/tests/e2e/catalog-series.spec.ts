// frontend/tests/e2e/catalog-series.spec.ts
import { expect, type Page } from "@playwright/test";

import type { ArticleResponse, BeadResponse, SystemResponse } from "../../src/api/generated/models";
import { t } from "../../src/i18n/es-CL";
import { fmtMm } from "../../src/format";
import { test } from "./support/manual-project-fixture";

type Resource = "systems" | "articles" | "glazing";
type Versioned = { id: string; revision: string };

test.use({
  fixtureRole: "WORKSHOP_MANAGER",
  viewport: { width: 1366, height: 768 },
});

const sectionKeys = {
  systems: "catalog.systems",
  articles: "catalog.articles",
  glazing: "catalog.glazing",
} as const;

const systemFields = [
  "name",
  "code",
  "material",
  "depth_mm",
  "chamber_count",
  "version",
  "is_active",
  "sash_overlap_mm",
  "glass_clearance_white_mm",
  "glass_clearance_foil_mm",
  "chamber_clearance_mm",
  "rail_type",
  "pulley_height_mm",
  "central_overlap_mm",
  "sliding_lateral_clearance_mm",
  "sliding_end_add_mm",
  "corner_bracket_loss_mm",
  "hook_depth_mm",
  "sliding_glazing_deduction_width_mm",
  "sliding_glazing_deduction_height_mm",
  "door_threshold_mm",
  "door_bottom_clearance_mm",
  "door_leaf_side_clearance_mm",
] as const;

const articleFields = [
  "system_id",
  "sku",
  "name",
  "material",
  "role",
  "face_width_mm",
  "commercial_length_mm",
  "welding_loss_mm",
  "reinforcement_sku",
  "reinforcement_gap_mm",
  "weight_kg_m",
  "steel_weight_kg_m",
] as const;

const beadFields = [
  "system_id",
  "bead_article_id",
  "glass_thickness_mm",
  "bead_width_mm",
  "gasket_interior_mm",
  "gasket_exterior_mm",
  "cut_add_mm",
  "is_active",
] as const;

function endpoint(resource: Resource, id?: string): string {
  return `/api/v1/catalogs/${resource}/${id ? `${id}/` : ""}`;
}

async function exchange(
  page: Page,
  method: string,
  path: string,
  expectedStatus: number,
  action: () => Promise<unknown>,
) {
  const [response] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.request().method() === method && new URL(candidate.url()).pathname === path,
    ),
    action(),
  ]);
  expect(response.status(), `${method} ${path}`).toBe(expectedStatus);
  return response;
}

async function loadCatalog(page: Page) {
  const resources: Resource[] = ["systems", "articles", "glazing"];
  const pending = resources.map((resource) =>
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === endpoint(resource),
    ),
  );
  await page.goto("/catalogs/systems");
  const responses = await Promise.all(pending);
  for (const response of responses) expect(response.status()).toBe(200);
  await expect(
    page.getByRole("heading", {
      name: t("catalog.title"),
      exact: true,
    }),
  ).toBeVisible();

  return {
    systems: ((await responses[0]!.json()) as { items: SystemResponse[] }).items,
    articles: ((await responses[1]!.json()) as { items: ArticleResponse[] }).items,
    glazing: ((await responses[2]!.json()) as { items: BeadResponse[] }).items,
  };
}

function form(page: Page) {
  return page.locator("form.catalog-editor");
}

async function section(page: Page, resource: Resource): Promise<void> {
  await page
    .getByRole("navigation", {
      name: t("catalog.sections"),
      exact: true,
    })
    .getByRole("button", {
      name: t(sectionKeys[resource]),
      exact: true,
    })
    .click();
}

async function selectSystem(page: Page, name: string): Promise<void> {
  const button = page.locator("button.catalog-system").filter({
    has: page.getByText(name, { exact: true }),
  });
  await expect(button).toHaveCount(1);
  await button.click();
  await expect(page.locator(".catalog-detail > header h2")).toHaveText(name);
}

async function openEditor(page: Page, resource: Resource, name: string): Promise<void> {
  await section(page, resource);
  await page
    .getByRole("button", {
      name: `${t("catalog.edit")} ${name}`,
      exact: true,
    })
    .click();
  await expect(form(page)).toBeVisible();
}

async function fillFields(
  page: Page,
  resource: Resource,
  source: object,
  fields: readonly string[],
): Promise<void> {
  const values = source as Record<string, unknown>;
  for (const field of fields) {
    const control = form(page).locator(`#catalog-${resource}-${field}`);
    const value = values[field] == null ? "" : String(values[field]);
    if (await control.evaluate((element) => element.tagName === "SELECT")) {
      await control.selectOption(value);
    } else {
      await control.fill(value);
    }
  }
}

async function assertFields(
  page: Page,
  resource: Resource,
  source: object,
  fields: readonly string[],
): Promise<void> {
  const values = source as Record<string, unknown>;
  for (const field of fields) {
    await expect(form(page).locator(`#catalog-${resource}-${field}`)).toHaveValue(
      values[field] == null ? "" : String(values[field]),
    );
  }
}

async function closeEditor(page: Page): Promise<void> {
  await form(page)
    .getByRole("button", {
      name: t("catalog.close"),
      exact: true,
    })
    .click();
  await expect(form(page)).toHaveCount(0);
}

async function save<T extends Versioned>(
  page: Page,
  resource: Resource,
  existing?: Versioned,
): Promise<T> {
  const response = await exchange(
    page,
    existing ? "PATCH" : "POST",
    endpoint(resource, existing?.id),
    existing ? 200 : 201,
    () =>
      form(page)
        .getByRole("button", {
          name: t("catalog.save"),
          exact: true,
        })
        .click(),
  );
  if (existing) {
    expect(response.request().headers()["if-match"]).toBe(`"${existing.revision}"`);
  }
  const row = (await response.json()) as T;
  await expect(form(page)).toHaveCount(0);
  return row;
}

test("manager creates, updates and reopens a synthetic series and bead compatibility", async ({
  page,
  manual,
}, info) => {
  test.setTimeout(180_000);

  const baseline = await loadCatalog(page);
  const templates = baseline.systems.filter(
    (row) => row.code === "DEMO_60" && row.is_global && row.is_demo && row.is_active,
  );
  expect(templates).toHaveLength(1);
  const templateSystem = templates[0]!;

  const beadTemplates = baseline.glazing.filter(
    (row) =>
      row.system_id === templateSystem.id && row.glass_thickness_mm === "20.00" && row.is_active,
  );
  expect(beadTemplates).toHaveLength(1);
  const templateBead = beadTemplates[0]!;
  const templateArticle = baseline.articles.find((row) => row.id === templateBead.bead_article_id);
  expect(templateArticle).toBeDefined();
  expect(templateArticle!.role).toBe("GLAZING_BEAD");
  expect(templateArticle!.system_id).toBe(templateSystem.id);

  const suffix = crypto.randomUUID();
  const initialSystemName = `E2E SYNTHETIC serie ${suffix}`;
  const systemName = `E2E SYNTHETIC serie revisada ${suffix}`;
  const initialArticleName = `E2E SYNTHETIC junquillo ${suffix}`;
  const articleName = `E2E SYNTHETIC junquillo revisado ${suffix}`;

  // Copy existing synthetic facts through typed UI fields. Only identifiers,
  // descriptive names and activation flags differ. No manufacturer facts change.
  const systemInput = {
    ...templateSystem,
    name: initialSystemName,
    code: `E2E_${suffix}`,
    is_active: false,
  };

  await page
    .getByRole("button", {
      name: t("catalog.newSystem"),
      exact: true,
    })
    .click();
  await fillFields(page, "systems", systemInput, systemFields);
  let system = await save<SystemResponse>(page, "systems");
  expect(system).toMatchObject({
    name: initialSystemName,
    is_global: false,
    is_demo: false,
    is_active: false,
    read_only: false,
  });

  await openEditor(page, "systems", initialSystemName);
  await fillFields(page, "systems", { name: systemName }, ["name"]);
  system = await save<SystemResponse>(page, "systems", system);
  expect(system.name).toBe(systemName);

  const articleInput = {
    ...templateArticle!,
    system_id: system.id,
    sku: `E2E-BEAD-${suffix}`,
    name: initialArticleName,
  };

  await section(page, "articles");
  await page
    .getByRole("button", {
      name: t("catalog.create"),
      exact: true,
    })
    .click();
  await fillFields(page, "articles", articleInput, articleFields);
  let article = await save<ArticleResponse>(page, "articles");
  expect(article).toMatchObject({
    system_id: system.id,
    role: "GLAZING_BEAD",
    read_only: false,
  });

  await openEditor(page, "articles", initialArticleName);
  await fillFields(page, "articles", { name: articleName }, ["name"]);
  article = await save<ArticleResponse>(page, "articles", article);
  expect(article.name).toBe(articleName);

  const beadInput = {
    ...templateBead,
    system_id: system.id,
    bead_article_id: article.id,
    is_active: false,
  };

  await section(page, "glazing");
  await page
    .getByRole("button", {
      name: t("catalog.create"),
      exact: true,
    })
    .click();
  await fillFields(page, "glazing", beadInput, beadFields);
  let bead = await save<BeadResponse>(page, "glazing");
  expect(bead).toMatchObject({
    system_id: system.id,
    bead_article_id: article.id,
    is_active: false,
    read_only: false,
  });

  const beadName = `${articleName} · ${fmtMm(bead.glass_thickness_mm)} ${t("catalog.mm")}`;
  await openEditor(page, "glazing", beadName);
  await fillFields(page, "glazing", { is_active: true }, ["is_active"]);
  bead = await save<BeadResponse>(page, "glazing", bead);
  expect(bead.is_active).toBe(true);
  expect(system.is_active).toBe(false);

  // Compare all copied technical fields against their source authority.
  for (const field of systemFields) {
    if (["name", "code", "is_active"].includes(field)) continue;
    expect(system[field], field).toEqual(templateSystem[field]);
  }
  for (const field of articleFields) {
    if (["system_id", "sku", "name"].includes(field)) continue;
    expect(article[field], field).toEqual(templateArticle![field]);
  }
  for (const field of beadFields) {
    if (["system_id", "bead_article_id", "is_active"].includes(field)) continue;
    expect(bead[field], field).toEqual(templateBead[field]);
  }

  // Full navigation discards the catalog component's in-memory records.
  const reopened = await loadCatalog(page);
  expect(reopened.systems.find((row) => row.id === system.id)).toEqual(system);
  expect(reopened.articles.find((row) => row.id === article.id)).toEqual(article);
  expect(reopened.glazing.find((row) => row.id === bead.id)).toEqual(bead);

  await selectSystem(page, systemName);
  await openEditor(page, "systems", systemName);
  await assertFields(page, "systems", system, systemFields);
  await closeEditor(page);

  await openEditor(page, "articles", articleName);
  await assertFields(page, "articles", article, articleFields);
  await expect(form(page).locator("#catalog-articles-system_id")).toBeDisabled();
  await closeEditor(page);

  await openEditor(page, "glazing", beadName);
  await assertFields(page, "glazing", bead, beadFields);
  await expect(form(page).locator("#catalog-glazing-system_id")).toBeDisabled();

  // Independent database evidence: ownership, relationship and exact decimals.
  expect(
    await manual.readRows(
      "profile_systems",
      `id=eq.${system.id}&org_id=eq.${manual.organizationId}` +
        "&select=id,name,is_global,is_demo,is_active,depth_mm::text",
    ),
  ).toEqual([
    {
      id: system.id,
      name: systemName,
      is_global: false,
      is_demo: false,
      is_active: false,
      depth_mm: templateSystem.depth_mm,
    },
  ]);

  expect(
    await manual.readRows(
      "profile_articles",
      `id=eq.${article.id}&org_id=eq.${manual.organizationId}` +
        "&select=id,system_id,name,role,face_width_mm::text,weight_kg_m::text",
    ),
  ).toEqual([
    {
      id: article.id,
      system_id: system.id,
      name: articleName,
      role: "GLAZING_BEAD",
      face_width_mm: templateArticle!.face_width_mm,
      weight_kg_m: templateArticle!.weight_kg_m,
    },
  ]);

  expect(
    await manual.readRows(
      "glazing_bead_matrix",
      `id=eq.${bead.id}&org_id=eq.${manual.organizationId}` +
        "&select=id,system_id,bead_article_id,is_active," +
        "glass_thickness_mm::text,cut_add_mm::text",
    ),
  ).toEqual([
    {
      id: bead.id,
      system_id: system.id,
      bead_article_id: article.id,
      is_active: true,
      glass_thickness_mm: templateBead.glass_thickness_mm,
      cut_add_mm: templateBead.cut_add_mm,
    },
  ]);

  await form(page).scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  const path = info.outputPath("catalog-series-glazing-reopened-1366x768.png");
  await page.screenshot({ path, fullPage: false, animations: "disabled" });
  await info.attach("catalog-series-glazing-reopened", {
    path,
    contentType: "image/png",
  });
  await closeEditor(page);
});
