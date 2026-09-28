import { expect, test as base, type Page } from "@playwright/test";

import { environment } from "./environment";
import { requireMailpitHealthy, waitForMagicLink } from "./mailpit";

type Row = Record<string, unknown>;

export type ManualProjectFixture = {
  organizationId: string;
  systemId: string;
  systemName: string;
  readRows(table: string, query: string): Promise<Row[]>;
};

function required(name: string): string {
  const value = environment(name);
  if (!value) throw new Error(`${name} is required for real SHOT-10 E2E`);
  return value;
}

function localUrl(value: string): string {
  const url = new URL(value);
  if (!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
    throw new Error("SHOT-10 fixture seeding requires isolated local Supabase");
  }
  return url.origin;
}

function text(value: unknown): string {
  if (typeof value !== "string") throw new Error("Expected a database string");
  return value;
}

// Preserve NUMERIC values as exact strings through PostgREST.
function projection(columns: string[], decimals: string[]): string {
  return [...columns, ...decimals.map((column) => `${column}::text`)].join(",");
}

async function authenticate(
  page: Page,
  email: string,
  supabaseUrl: string,
  mailpitUrl: string,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Correo", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Enviar enlace de acceso", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Revisa tu correo para continuar");

  const message = await waitForMagicLink({
    baseUrl: mailpitUrl,
    supabaseUrl,
    recipient: email,
  });
  await page.goto(message.link);
  await expect(page.getByTestId("app-shell")).toBeVisible();
}

export const test = base.extend<{
  manual: ManualProjectFixture;
  fixtureRole: "ESTIMATOR" | "WORKSHOP_MANAGER";
}>({
  fixtureRole: ["ESTIMATOR", { option: true }],
  manual: async ({ page, fixtureRole }, use) => {
    const supabaseUrl = localUrl(required("SUPABASE_URL"));
    const mailpitUrl = localUrl(required("MAILPIT_URL"));
    const serviceKey = required("SUPABASE_SERVICE_ROLE_KEY");

    // Fixture setup/cleanup only. Never expose this key to the browser or Vite.
    const headers = {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json",
    };

    async function admin(path: string, method = "GET", body?: unknown): Promise<Response> {
      const response = await fetch(`${supabaseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 400);
        throw new Error(
          `Fixture ${method} ${path.split("?")[0]}: HTTP ${response.status} — ${detail}`,
        );
      }
      return response;
    }

    async function readRows(table: string, query: string): Promise<Row[]> {
      const response = await admin(`/rest/v1/${table}?${query}`);
      const result: unknown = await response.json();
      if (
        !Array.isArray(result) ||
        result.some((row: unknown) => typeof row !== "object" || row === null || Array.isArray(row))
      ) {
        throw new Error(`Fixture ${table} did not return database rows`);
      }
      return result as Row[];
    }

    async function insert(table: string, rows: Row | Row[]): Promise<void> {
      await admin(`/rest/v1/${table}`, "POST", rows);
    }

    const suffix = crypto.randomUUID();
    const organizationId = crypto.randomUUID();
    const systemId = crypto.randomUUID();
    const systemName = `SHOT-10 E2E SYNTHETIC DEMO ${suffix}`;
    const email = `shot10-${suffix}@example.com`;
    let userId: string | undefined;
    let organizationCreationAttempted = false;

    try {
      await requireMailpitHealthy(mailpitUrl);

      const created = await admin("/auth/v1/admin/users", "POST", {
        email,
        email_confirm: true,
      });
      userId = text(((await created.json()) as Row).id);

      organizationCreationAttempted = true;
      await insert("tenancy_organizations", {
        id: organizationId,
        name: `SHOT-10 E2E SYNTHETIC ${suffix}`,
        tax_id: `E2E-${suffix}`,
      });
      await insert("tenancy_memberships", {
        org_id: organizationId,
        user_id: userId,
        role: fixtureRole,
        is_active: true,
      });

      const systemSelect = projection(
        ["id", "name", "code", "material", "chamber_count", "rail_type", "version"],
        [
          "depth_mm",
          "sash_overlap_mm",
          "glass_clearance_white_mm",
          "glass_clearance_foil_mm",
          "pulley_height_mm",
          "central_overlap_mm",
          "sliding_lateral_clearance_mm",
          "sliding_end_add_mm",
          "corner_bracket_loss_mm",
          "hook_depth_mm",
          "door_threshold_mm",
          "door_bottom_clearance_mm",
          "sliding_glazing_deduction_width_mm",
          "sliding_glazing_deduction_height_mm",
          "door_leaf_side_clearance_mm",
          "chamber_clearance_mm",
        ],
      );
      const sources = await readRows(
        "profile_systems",
        "code=eq.DEMO_60&org_id=is.null&is_global=eq.true&is_demo=eq.true" +
          `&is_active=eq.true&select=${systemSelect}`,
      );
      expect(sources).toHaveLength(1);
      const source = sources[0]!;
      const sourceId = text(source.id);

      if (fixtureRole === "ESTIMATOR") {
        // Project editing uses the complete canonical synthetic catalog, including
        // its immutable inspection, manufacturing and purchasing authorities.
        // Catalog CRUD below retains a separate, unreferenced tenant copy.
        await authenticate(page, email, supabaseUrl, mailpitUrl);
        await use({
          organizationId,
          systemId: sourceId,
          systemName: text(source.name),
          readRows,
        });
        return;
      }

      // Test-only copy of existing synthetic authorities. No invented dimensions
      // and no modifications to the shared global DEMO catalog.
      await insert("profile_systems", {
        ...source,
        id: systemId,
        org_id: organizationId,
        name: systemName,
        code: `E2E_${suffix}`,
        is_global: false,
        is_demo: true,
        is_active: true,
      });

      const articleSelect = projection(
        ["id", "sku", "name", "role", "material", "reinforcement_sku"],
        [
          "face_width_mm",
          "commercial_length_mm",
          "welding_loss_mm",
          "reinforcement_gap_mm",
          "weight_kg_m",
          "steel_weight_kg_m",
        ],
      );
      const articles = await readRows(
        "profile_articles",
        `system_id=eq.${sourceId}&org_id=is.null&select=${articleSelect}`,
      );
      expect(articles.some((article) => article.role === "FRAME")).toBe(true);
      expect(articles.some((article) => article.role === "SASH")).toBe(true);

      const articleIds = new Map<string, string>();
      await insert(
        "profile_articles",
        articles.map((article) => {
          const id = crypto.randomUUID();
          articleIds.set(text(article.id), id);
          return {
            ...article,
            id,
            org_id: organizationId,
            system_id: systemId,
          };
        }),
      );

      const beadSelect = projection(
        ["bead_article_id", "is_active"],
        [
          "glass_thickness_mm",
          "bead_width_mm",
          "gasket_interior_mm",
          "gasket_exterior_mm",
          "cut_add_mm",
        ],
      );
      const beads = await readRows(
        "glazing_bead_matrix",
        `system_id=eq.${sourceId}&org_id=is.null&is_active=eq.true` +
          `&glass_thickness_mm=eq.20&select=${beadSelect}`,
      );
      expect(beads).toHaveLength(1);
      const bead = beads[0]!;
      const beadArticleId = articleIds.get(text(bead.bead_article_id));
      if (!beadArticleId) throw new Error("DEMO bead article was not copied");
      await insert("glazing_bead_matrix", {
        ...bead,
        org_id: organizationId,
        system_id: systemId,
        bead_article_id: beadArticleId,
      });

      const kitSelect = projection(
        [
          "sku",
          "name",
          "opening_type",
          "rail_type",
          "carriages_qty",
          "stay_arms_qty",
          "contents::text",
          "is_active",
        ],
        [
          "min_leaf_width_mm",
          "max_leaf_width_mm",
          "min_leaf_height_mm",
          "max_leaf_height_mm",
          "max_leaf_weight_kg",
          "weight_kg",
          "carriage_capacity_kg",
        ],
      );
      const kits = await readRows(
        "hardware_kits",
        `system_id=eq.${sourceId}&org_id=is.null&is_active=eq.true` +
          `&sku=eq.KIT-TURN&select=${kitSelect}`,
      );
      expect(kits).toHaveLength(1);
      const kit = kits[0]!;

      // KIT-TURN carries categorized contents (hinge/lever/lock). Assert the
      // component SKU set — not the exact decimal serialization, which
      // JavaScript binary floating point cannot round-trip.
      const contentsText = text(kit.contents);
      for (const sku of ["DEMO-BIS-60", "DEMO-MAN-PRACT", "DEMO-CREM-60"]) {
        expect(contentsText).toContain(sku);
      }
      expect(kit.opening_type).toBe("TURN");
      await insert("hardware_kits", {
        ...kit,
        org_id: organizationId,
        system_id: systemId,
        contents: [],
      });

      // All project creation/editing/persistence happens through the actual UI,
      // real Auth session, Django API and authenticated RLS.
      await authenticate(page, email, supabaseUrl, mailpitUrl);
      await use({
        organizationId,
        systemId,
        systemName,
        readRows,
      });
    } finally {
      try {
        if (organizationCreationAttempted) {
          await admin(`/rest/v1/tenancy_organizations?id=eq.${organizationId}`, "DELETE");
        }
      } finally {
        if (userId) {
          await admin(`/auth/v1/admin/users/${userId}`, "DELETE");
        }
      }
    }
  },
});
