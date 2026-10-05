// frontend/src/features/catalogs/CatalogPage.test.tsx
// Component tests only: real CatalogPage, catalogModel and translations.
// Authentication and generated API calls are mocked. These tests do not prove RLS.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/apiMutator";
import * as client from "../../api/generated/dekopen";
import type {
  ArticleResponse,
  ArticleWriteRequest,
  KitResponse,
  KitWriteRequest,
  SystemResponse,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { ConfirmProvider } from "../../ui";
import { CatalogPage } from "./CatalogPage";

const identity = vi.hoisted(() => ({
  id: "00000000-0000-4000-8000-000000000001",
  role: "OWNER",
}));

vi.mock("../../auth/AuthSessionProvider", () => ({
  useAuthSession: () => ({
    status: "ready",
    session: { user: { id: "catalog-test-user" } },
    me: { active_organization: identity },
  }),
}));

vi.mock("../../api/generated/dekopen");

const SYSTEM_ID = "00000000-0000-4000-8000-000000000010";
const KIT_ID = "00000000-0000-4000-8000-000000000020";
const ARTICLE_ID = "00000000-0000-4000-8000-000000000030";
const REVISION = `sha256:${"a".repeat(64)}`;
const PROVENANCE = {
  data_provenance: "MANUAL" as const,
  technical_reviewed_at: null,
  technical_reviewed_by: null,
  review_pending: false,
};
const SAVED_REVISION = `sha256:${"b".repeat(64)}`;

function ok<T>(data: T) {
  return { status: 200 as const, headers: new Headers(), data };
}

function created<T>(data: T) {
  return { status: 201 as const, headers: new Headers(), data };
}

function system(): SystemResponse {
  // Synthetic test data, not manufacturer defaults.
  return {
    id: SYSTEM_ID,
    name: "Serie global de prueba",
    code: "TEST-GLOBAL",
    material: "PVC",
    depth_mm: "60.00",
    system_family: "CASEMENT",
    chamber_count: 3,
    sash_overlap_mm: "8.00",
    glass_clearance_white_mm: "4.00",
    glass_clearance_foil_mm: "5.00",
    pulley_height_mm: "12.00",
    central_overlap_mm: "20.00",
    sliding_lateral_clearance_mm: "3.00",
    sliding_end_add_mm: "2.00",
    corner_bracket_loss_mm: "1.00",
    hook_depth_mm: "6.00",
    door_threshold_mm: "15.00",
    door_bottom_clearance_mm: "7.00",
    rail_type: "dual",
    sliding_glazing_deduction_width_mm: "30.00",
    sliding_glazing_deduction_height_mm: "40.00",
    door_leaf_side_clearance_mm: "4.00",
    chamber_clearance_mm: null,
    version: 1,
    is_active: true,
    is_global: true,
    is_demo: true,
    readiness: { quote_ready: true, scope: "WHITE_FIXED_CATALOG", reasons: [] },
    revision: REVISION,
    ...PROVENANCE,
    read_only: true,
  };
}

function kitWrite(): KitWriteRequest {
  return {
    system_id: SYSTEM_ID,
    sku: "TEST-KIT",
    name: "Kit propio de prueba",
    opening_type: "TURN",
    min_leaf_width_mm: "400.00",
    max_leaf_width_mm: "1200.00",
    min_leaf_height_mm: "500.00",
    max_leaf_height_mm: "2200.00",
    max_leaf_weight_kg: "80.00",
    rail_type: "dual",
    carriages_qty: 0,
    stay_arms_qty: 0,
    weight_kg: null,
    carriage_capacity_kg: null,
    is_active: true,
    contents: [
      { sku: "TEST-HINGE", name: "Bisagra de prueba", qty: "2", unit: "UNIT", category: "HINGE" },
      { sku: "TEST-STOP", name: "Tope de prueba", qty: "1", unit: "UNIT", category: "OTHER" },
    ],
  };
}

function kit(overrides: Partial<KitResponse> = {}): KitResponse {
  return {
    ...kitWrite(),
    id: KIT_ID,
    revision: REVISION,
    read_only: false,
    ...PROVENANCE,
    ...overrides,
  };
}

function articleWrite(): ArticleWriteRequest {
  return {
    system_id: SYSTEM_ID,
    sku: "MARCO-60",
    name: "Marco de prueba",
    material: "PVC",
    role: "FRAME",
    face_width_mm: "60.00",
    commercial_length_mm: "6000.00",
    welding_loss_mm: "3.00",
    reinforcement_sku: null,
    reinforcement_gap_mm: null,
    weight_kg_m: null,
    steel_weight_kg_m: null,
    section: null,
  };
}

function article(overrides: Partial<ArticleResponse> = {}): ArticleResponse {
  return {
    ...articleWrite(),
    id: ARTICLE_ID,
    revision: REVISION,
    read_only: false,
    section_revision: 1,
    section_revised_at: null,
    section_revised_by: null,
    ...PROVENANCE,
    ...overrides,
  };
}

const SECTION_VERTEX = [
  { x: "0", y: "0" },
  { x: "60", y: "0" },
  { x: "0", y: "60" },
];

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

const reads = [
  client.catalogSystemList,
  client.catalogArticleList,
  client.catalogBeadList,
  client.catalogKitList,
];

const writes = [
  client.catalogSystemCreate,
  client.catalogSystemUpdate,
  client.catalogSystemDelete,
  client.catalogArticleCreate,
  client.catalogArticleUpdate,
  client.catalogArticleDelete,
  client.catalogBeadCreate,
  client.catalogBeadUpdate,
  client.catalogBeadDelete,
  client.catalogKitCreate,
  client.catalogKitUpdate,
  client.catalogKitDelete,
];

function expectNoWrites() {
  for (const request of writes) expect(request).not.toHaveBeenCalled();
}

async function mount() {
  render(
    <ConfirmProvider>
      <CatalogPage />
    </ConfirmProvider>,
  );
  await screen.findByRole("heading", { name: t("catalog.title") });
}

function button(key: TranslationKey) {
  return screen.getByRole("button", { name: t(key) });
}

// Section navigation is a real tablist — tabs are role=tab, not button.
function navTab(key: TranslationKey) {
  return screen.getByRole("tab", { name: t(key) });
}

function change(key: TranslationKey, value: string) {
  fireEvent.change(
    screen.getByLabelText(
      (label) => label === t(key) || label === `${t(key)} · ${t("catalog.optional")}`,
    ),
    { target: { value } },
  );
}

function componentField(key: "sku" | "name" | "qty" | "unit", index: number) {
  return screen.getByRole("textbox", {
    name: `${t(`catalog.field.${key}`)} · ${t("catalog.component")} ${index}`,
  });
}

function changeComponent(key: "sku" | "name" | "qty" | "unit", index: number, value: string) {
  fireEvent.change(componentField(key, index), { target: { value } });
}

function editorForm(): HTMLFormElement {
  const form = button("catalog.save").closest("form");
  if (!form) throw new Error("Expected catalog editor form");
  return form;
}

async function openKit(name = kit().name, readOnly = false) {
  fireEvent.click(navTab("catalog.hardware-kits"));
  fireEvent.click(
    await screen.findByRole("button", {
      name: `${t(readOnly ? "catalog.view" : "catalog.edit")} ${name}`,
    }),
  );
}

async function openArticle(name = article().name, readOnly = false) {
  fireEvent.click(navTab("catalog.articles"));
  fireEvent.click(
    await screen.findByRole("button", {
      name: `${t(readOnly ? "catalog.view" : "catalog.edit")} ${name}`,
    }),
  );
}

function sectionField(kind: "x_mm" | "y_mm", index: number) {
  return screen.getByRole("textbox", {
    name: `${t(`catalog.field.${kind}`)} · ${t("catalog.section.vertex")} ${index}`,
  });
}

async function declareSection() {
  fireEvent.click(screen.getByRole("checkbox", { name: t("catalog.section.declare") }));
  for (const [index, vertex] of SECTION_VERTEX.entries()) {
    fireEvent.click(screen.getByRole("button", { name: t("catalog.section.addVertex") }));
    fireEvent.change(sectionField("x_mm", index + 1), { target: { value: vertex.x } });
    fireEvent.change(sectionField("y_mm", index + 1), { target: { value: vertex.y } });
  }
  change("catalog.field.depth_mm", "60");
}

beforeEach(() => {
  vi.resetAllMocks();
  identity.role = "OWNER";

  vi.mocked(client.catalogSystemList).mockResolvedValue(ok({ items: [system()] }));
  vi.mocked(client.catalogArticleList).mockResolvedValue(ok({ items: [] }));
  vi.mocked(client.catalogBeadList).mockResolvedValue(ok({ items: [] }));
  vi.mocked(client.catalogKitList).mockResolvedValue(ok({ items: [kit()] }));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CatalogPage client permissions", () => {
  it.each(["OWNER", "WORKSHOP_MANAGER"])(
    "allows %s to load the catalog using the active organization",
    async (role) => {
      identity.role = role;
      await mount();

      expect(button("catalog.newSystem")).toBeEnabled();
      expect(client.catalogSystemList).toHaveBeenCalledWith({
        headers: { "X-Organization-ID": identity.id },
        signal: expect.any(AbortSignal),
      });
      for (const request of [
        client.catalogArticleList,
        client.catalogBeadList,
        client.catalogKitList,
      ]) {
        expect(request).toHaveBeenCalledWith(undefined, {
          headers: { "X-Organization-ID": identity.id },
          signal: expect.any(AbortSignal),
        });
      }
      expectNoWrites();
    },
  );

  it("admits ESTIMATOR read-only: catalog loads without CRUD affordances", async () => {
    identity.role = "ESTIMATOR";
    await mount();

    // Reads run — the estimator reviews the catalog and the imports panel.
    for (const request of reads) expect(request).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: t("catalog.newSystem") })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: t("catalog.create") })).not.toBeInTheDocument();

    // Own rows open view-only for roles outside catalog CRUD.
    await openKit(kit().name, true);
    expect(componentField("qty", 1)).toBeDisabled();
    expect(button("catalog.addComponent")).toBeDisabled();
    expect(button("catalog.save")).toBeDisabled();
    expect(button("catalog.delete")).toBeDisabled();
    fireEvent.submit(editorForm());
    expectNoWrites();
  });

  it("keeps a global system read-only, including a direct submit event", async () => {
    await mount();
    // The workspace is the system home — the ficha record lives one tab away.
    fireEvent.click(navTab("catalog.systems"));
    fireEvent.click(
      screen.getByRole("button", {
        name: `${t("catalog.view")} ${system().name}`,
      }),
    );

    expect(screen.getByLabelText(t("catalog.field.name"))).toBeDisabled();
    expect(screen.getByLabelText(t("catalog.field.depth_mm"))).toHaveValue("60.00");
    expect(screen.getByLabelText(t("catalog.field.depth_mm"))).toBeDisabled();
    expect(button("catalog.save")).toBeDisabled();
    expect(button("catalog.delete")).toBeDisabled();

    fireEvent.click(button("catalog.save"));
    fireEvent.click(button("catalog.delete"));
    fireEvent.submit(editorForm());

    expectNoWrites();
  });

  it("uses each kit's read_only flag under the same global system", async () => {
    const globalKit = kit({
      id: "00000000-0000-4000-8000-000000000021",
      name: "Kit global de prueba",
      sku: "TEST-GLOBAL-KIT",

      read_only: true,
    });
    vi.mocked(client.catalogKitList).mockResolvedValue(
      ok({
        items: [globalKit, kit()],
      }),
    );

    await mount();
    await openKit(globalKit.name, true);

    expect(componentField("qty", 1)).toBeDisabled();
    expect(button("catalog.addComponent")).toBeDisabled();
    expect(button("catalog.save")).toBeDisabled();
    expect(button("catalog.delete")).toBeDisabled();
    fireEvent.submit(editorForm());
    expectNoWrites();

    fireEvent.click(button("catalog.close"));
    fireEvent.click(
      screen.getByRole("button", {
        name: `${t("catalog.edit")} ${kit().name}`,
      }),
    );

    expect(componentField("qty", 1)).toBeEnabled();
    expect(button("catalog.addComponent")).toBeEnabled();
    expect(button("catalog.delete")).toBeEnabled();

    const parent = screen.getByLabelText(
      (label) => label === `${t("catalog.field.system_id")} · ${t("catalog.optional")}`,
    );
    expect(parent).toHaveValue(SYSTEM_ID);
    expect(parent).toBeDisabled();

    changeComponent("qty", 1, "3");
    expect(button("catalog.save")).toBeEnabled();
    expectNoWrites();
  });
});

describe("CatalogPage typed kit editor", () => {
  it("saves typed contents and exact decimals once, then displays the saved values", async () => {
    const expected: KitWriteRequest = {
      ...kitWrite(),
      name: "Kit corredera actualizado",
      opening_type: "SLIDING",
      max_leaf_width_mm: "1250.75",
      carriages_qty: 2,
      contents: [
        {
          sku: "TEST-HINGE",
          name: "Bisagra de prueba",
          qty: "2.5000",
          unit: "UNIT",
          category: "HINGE",
        },
        {
          sku: "TEST-GASKET",
          name: "Junta de prueba",
          qty: "0.1000000000000000001",
          unit: "M",
          category: "OTHER",
        },
      ],
    };
    const saved: KitResponse = {
      ...expected,
      id: KIT_ID,
      revision: SAVED_REVISION,
      read_only: false,
      ...PROVENANCE,
    };
    const pending = deferred<ReturnType<typeof ok<KitResponse>>>();
    vi.mocked(client.catalogKitUpdate).mockReturnValueOnce(pending.promise);

    await mount();
    await openKit();

    const opening = screen.getByRole("combobox", {
      name: t("catalog.field.opening_type"),
    });
    expect(
      within(opening)
        .getAllByRole("option")
        .map((option) => option.getAttribute("value")),
    ).toEqual(["", "TURN", "TILT_TURN", "SLIDING", "DOOR", "AWNING"]);

    change("catalog.field.name", expected.name);
    change("catalog.field.opening_type", "SLIDING");
    change("catalog.field.max_leaf_width_mm", "1250,75");
    change("catalog.field.carriages_qty", "2");
    changeComponent("qty", 1, "2,5000");

    fireEvent.click(
      screen.getByRole("button", {
        name: `${t("catalog.removeComponent")} 2`,
      }),
    );
    fireEvent.click(button("catalog.addComponent"));
    changeComponent("sku", 2, "TEST-GASKET");
    changeComponent("name", 2, "Junta de prueba");
    changeComponent("qty", 2, "0,1000000000000000001");
    changeComponent("unit", 2, "M");

    const form = editorForm();
    expect(form.checkValidity()).toBe(true);
    fireEvent.click(button("catalog.save"));

    await waitFor(() => expect(client.catalogKitUpdate).toHaveBeenCalledTimes(1));
    expect(client.catalogKitUpdate).toHaveBeenCalledWith(KIT_ID, expected, {
      headers: { "X-Organization-ID": identity.id, "If-Match": `"${REVISION}"` },
    });
    expect(button("catalog.working")).toBeDisabled();
    expect(componentField("qty", 1)).toBeDisabled();

    // The submit handler also guards against duplicate programmatic submissions.
    fireEvent.submit(form);
    expect(client.catalogKitUpdate).toHaveBeenCalledTimes(1);
    expect(client.catalogKitCreate).not.toHaveBeenCalled();

    await act(async () => {
      pending.resolve(ok(saved));
    });

    expect(await screen.findByRole("status")).toHaveTextContent(t("catalog.saved"));
    expect(screen.queryByRole("button", { name: t("catalog.save") })).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: `${t("catalog.edit")} ${expected.name}`,
      }),
    );
    expect(screen.getByLabelText(t("catalog.field.max_leaf_width_mm"))).toHaveValue("1250.75");
    expect(componentField("qty", 1)).toHaveValue("2.5000");
    expect(componentField("qty", 2)).toHaveValue("0.1000000000000000001");
    expect(button("catalog.save")).toBeDisabled();
  });

  it.each([
    [400, "catalog.errorValidation"],
    [409, "catalog.errorConflict"],
    [503, "catalog.errorNetwork"],
  ] as const)(
    "preserves edited fields and contents after API error %s",
    async (status, message) => {
      const rawDetail = "SQLSTATE test-only internal detail";
      vi.mocked(client.catalogKitUpdate).mockRejectedValueOnce(
        new ApiError(status, {
          error: { code: "catalog_test_error", detail: rawDetail },
        }),
      );

      await mount();
      await openKit();

      change("catalog.field.name", "Kit pendiente de guardar");
      change("catalog.field.max_leaf_width_mm", "1300,25");
      changeComponent("qty", 1, "3,1250");
      fireEvent.click(button("catalog.addComponent"));
      changeComponent("sku", 3, "TEST-ADDED");
      changeComponent("name", 3, "Componente pendiente");
      changeComponent("qty", 3, "0,5000");
      changeComponent("unit", 3, "M");

      expect(editorForm().checkValidity()).toBe(true);
      fireEvent.click(button("catalog.save"));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(t(message));
      expect(alert).toHaveFocus();
      expect(screen.queryByText(rawDetail)).not.toBeInTheDocument();

      expect(screen.getByLabelText(t("catalog.field.name"))).toHaveValue(
        "Kit pendiente de guardar",
      );
      expect(screen.getByLabelText(t("catalog.field.max_leaf_width_mm"))).toHaveValue("1300,25");
      expect(componentField("qty", 1)).toHaveValue("3,1250");
      expect(componentField("name", 3)).toHaveValue("Componente pendiente");
      expect(componentField("qty", 3)).toHaveValue("0,5000");
      expect(button("catalog.save")).toBeEnabled();
      expect(screen.queryByText(t("catalog.saved"))).not.toBeInTheDocument();

      const expected: KitWriteRequest = {
        ...kitWrite(),
        name: "Kit pendiente de guardar",
        max_leaf_width_mm: "1300.25",
        contents: [
          {
            sku: "TEST-HINGE",
            name: "Bisagra de prueba",
            qty: "3.1250",
            unit: "UNIT",
            category: "HINGE",
          },
          { sku: "TEST-STOP", name: "Tope de prueba", qty: "1", unit: "UNIT", category: "OTHER" },
          {
            sku: "TEST-ADDED",
            name: "Componente pendiente",
            qty: "0.5000",
            unit: "M",
            category: "OTHER",
          },
        ],
      };
      vi.mocked(client.catalogKitUpdate).mockResolvedValueOnce(
        ok({
          ...expected,
          id: KIT_ID,
          revision: SAVED_REVISION,
          read_only: false,
          ...PROVENANCE,
        }),
      );

      fireEvent.click(button("catalog.save"));

      await waitFor(() => {
        expect(screen.getByRole("status")).toHaveTextContent(t("catalog.saved"));
      });
      expect(client.catalogKitUpdate).toHaveBeenCalledTimes(2);
      expect(client.catalogKitUpdate).toHaveBeenNthCalledWith(1, KIT_ID, expected, {
        headers: { "X-Organization-ID": identity.id, "If-Match": `"${REVISION}"` },
      });
      expect(client.catalogKitUpdate).toHaveBeenNthCalledWith(2, KIT_ID, expected, {
        headers: { "X-Organization-ID": identity.id, "If-Match": `"${REVISION}"` },
      });
      expect(client.catalogKitCreate).not.toHaveBeenCalled();
    },
  );
});

describe("Catalog creation recovery", () => {
  it("preserves an uncertain creation without allowing duplicate submission", async () => {
    vi.mocked(client.catalogKitCreate).mockRejectedValueOnce(
      new TypeError("Network response lost"),
    );
    await mount();
    fireEvent.click(navTab("catalog.hardware-kits"));
    fireEvent.click(button("catalog.create"));
    for (const [key, value] of Object.entries(kitWrite())) {
      if (value !== null && key !== "contents") {
        change(`catalog.field.${key}` as TranslationKey, String(value));
      }
    }
    change("catalog.field.name", "Kit pendiente");
    fireEvent.submit(editorForm());
    expect(await screen.findByRole("alert")).toHaveTextContent(t("catalog.uncertainCreate"));
    expect(screen.getByLabelText(t("catalog.field.name"))).toHaveValue("Kit pendiente");
    expect(button("catalog.save")).toBeDisabled();
    fireEvent.submit(editorForm());
    expect(client.catalogKitCreate).toHaveBeenCalledTimes(1);
  });
});

describe("CatalogPage article section editor", () => {
  it("authors a declared section on create — polygon, depth and axes reach the request", async () => {
    vi.mocked(client.catalogArticleCreate).mockResolvedValue(created(article()));
    await mount();
    fireEvent.click(navTab("catalog.articles"));
    fireEvent.click(button("catalog.create"));
    for (const [key, value] of Object.entries(articleWrite())) {
      if (value !== null && key !== "section" && key !== "system_id") {
        change(`catalog.field.${key}` as TranslationKey, String(value));
      }
    }
    await declareSection();

    fireEvent.submit(editorForm());

    await waitFor(() => expect(client.catalogArticleCreate).toHaveBeenCalled());
    const body = vi.mocked(client.catalogArticleCreate).mock.calls.at(0)![0];
    expect(body.section).toEqual({
      source: "POLYGON",
      polygon: SECTION_VERTEX.map(({ x, y }) => ({ x_mm: x, y_mm: y })),
      depth_mm: "60",
      orientation: "EXTERIOR_DOWN",
      local_origin: "TOP_LEFT",
      axes: [],
      drawing_ref: null,
    });
  });

  it("clears a stored section to null when the user undeclares it", async () => {
    const declared = article({
      section: {
        source: "POLYGON",
        polygon: SECTION_VERTEX.map(({ x, y }) => ({ x_mm: x, y_mm: y })),
        depth_mm: "60",
        orientation: "EXTERIOR_DOWN",
        local_origin: "TOP_LEFT",
        axes: [],
        drawing_ref: null,
      },
    });
    vi.mocked(client.catalogArticleList).mockResolvedValue(ok({ items: [declared] }));
    vi.mocked(client.catalogArticleUpdate).mockResolvedValue(ok(declared));
    await mount();
    await openArticle();

    fireEvent.click(screen.getByRole("checkbox", { name: t("catalog.section.declare") }));
    fireEvent.submit(editorForm());

    await waitFor(() => expect(client.catalogArticleUpdate).toHaveBeenCalled());
    const body = vi.mocked(client.catalogArticleUpdate).mock.calls.at(0)![1];
    expect(body?.section).toBeNull();
  });

  it("refuses an incomplete declared section instead of writing it", async () => {
    vi.mocked(client.catalogArticleCreate).mockResolvedValue(created(article()));
    await mount();
    fireEvent.click(navTab("catalog.articles"));
    fireEvent.click(button("catalog.create"));
    for (const [key, value] of Object.entries(articleWrite())) {
      if (value !== null && key !== "section" && key !== "system_id") {
        change(`catalog.field.${key}` as TranslationKey, String(value));
      }
    }
    // Declared but no vertices and no depth — the submit must fail locally.
    fireEvent.click(screen.getByRole("checkbox", { name: t("catalog.section.declare") }));

    fireEvent.submit(editorForm());

    expect(await screen.findByRole("alert")).toHaveTextContent(t("catalog.errorValidation"));
    expectNoWrites();
  });

  it("keeps section fields off the other catalog resources", async () => {
    await mount();
    await openKit();
    expect(
      screen.queryByRole("checkbox", { name: t("catalog.section.declare") }),
    ).not.toBeInTheDocument();
  });
});
