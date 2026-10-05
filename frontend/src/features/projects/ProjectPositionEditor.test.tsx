// Component tests for the compositional position workspace.
// Real router, query client, store and editor. Mocks are limited to
// authentication and the generated API boundary.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  engineAssemblyCalculate,
  engineSystems,
  positionsCreate,
  positionsRetrieve,
  positionsUpdate,
  projectDesignOptions,
} from "../../api/generated/dekopen";
import type {
  EngineAssemblyCalculateResponse,
  EngineCalculateResponse,
  PositionResponse,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { useCanvasStore } from "../canvas/canvasStore";
import type { ProductJson } from "../canvas/productEditing";
import { ProjectPositionEditor } from "./ProjectPositionEditor";
import { ApiError } from "../../api/apiMutator";

const identity = vi.hoisted(() => ({
  id: "org-a",
  role: "OWNER",
  listeners: new Set<() => void>(),
}));

vi.mock("../../auth/AuthSessionProvider", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useAuthSession: () => {
      useSyncExternalStore(
        (listener) => {
          identity.listeners.add(listener);
          return () => identity.listeners.delete(listener);
        },
        () => identity.id + ":" + identity.role,
      );
      return { me: { active_organization: { id: identity.id, role: identity.role } } };
    },
  };
});

vi.mock("../../api/generated/dekopen", () => ({
  engineAssemblyCalculate: vi.fn(),
  engineSystems: vi.fn(),
  positionsCreate: vi.fn(),
  positionsRetrieve: vi.fn(),
  positionsUpdate: vi.fn(),
  projectDesignOptions: vi.fn(),
}));

const evaluate = vi.mocked(engineAssemblyCalculate);
const retrieve = vi.mocked(positionsRetrieve);
const update = vi.mocked(positionsUpdate);
const create = vi.mocked(positionsCreate);

function ok<T>(data: T) {
  return { status: 200 as const, headers: new Headers(), data };
}

function bom(sku: string): EngineCalculateResponse {
  return {
    profile_cuts: [
      {
        sku,
        role: "FRAME",
        material: "PVC",
        length_mm: "1234.25",
        angle_left: "45.0",
        angle_right: "45.0",
        qty: 2,
        bay_id: "bay-1",
        leaf_id: null,
        sagitta_mm: null,
      },
    ],
    reinforcements: [],
    glasses: [],
    panels: [],
    fittings: [],
    hardware_items: [],
    leaf_weights: [],
    calculation_hash: `sha256:${"a".repeat(64)}`,
  };
}

function assemblyEval(
  sku = "CUT-A",
  status: EngineAssemblyCalculateResponse["status"] = "VALID",
): EngineAssemblyCalculateResponse {
  return {
    status,
    issues: [],
    plan: {
      front_chain: [
        { x_mm: "0", y_mm: "0" },
        { x_mm: "1234.25", y_mm: "0" },
      ],
      modules: [
        {
          module_id: "m1",
          corners: [
            { x_mm: "0", y_mm: "0" },
            { x_mm: "1234.25", y_mm: "0" },
            { x_mm: "1234.25", y_mm: "60" },
            { x_mm: "0", y_mm: "60" },
          ],
        },
      ],
      couplings: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "1234.25",
      height_mm: "60",
    },
    modules: [],
    bom: bom(sku),
    calculation_hash: `sha256:${"a".repeat(64)}`,
  };
}

function position(
  id = "position-a",
  projectId = "project-a",
  location = "Cocina",
): PositionResponse {
  return {
    id,
    project_id: projectId,
    position_index: 3,
    location_tag: location,
    quantity: 4,
    typology: "FIXED",
    price_net: "0",
    discount_pct: "0",
    measurement: {
      state: "CLIENT_DECLARED",
      confirmed_at: null,
      confirmed_by: null,
      vano: null,
      mounting_rule: null,
      fabrication_lock: null,
      resolution: null,
    },
    updated_at: "2026-09-18T15:00:00.123456Z",
    design: {
      system_id: "system-a",
      nominal_width_mm: "1234.25",
      nominal_height_mm: "987.50",
      color: "WHITE",
      parametric_tree: {
        id: "bay-1",
        type: "BAY",
        opening_type: "FIXED",
        glass_thickness_mm: "24.00",
        glass_spec: "4-16-4 transparente",
        glass_article_sku: "GLASS-A",
        hardware_set_sku: null,
      },
    },
    bom: bom("CUT-A"),
  };
}

function bowPosition(): PositionResponse {
  const tree: ProductJson = {
    version: "product-v2",
    assembly: {
      modules: [
        {
          id: "m1",
          width_mm: "700.00",
          height_mm: "1400.00",
          tree: { id: "b1", type: "BAY", opening_type: "TILT_TURN_LEFT" },
        },
        {
          id: "m2",
          width_mm: "700.00",
          height_mm: "1400.00",
          tree: { id: "b2", type: "BAY", opening_type: "TILT_TURN_LEFT" },
        },
        {
          id: "m3",
          width_mm: "700.00",
          height_mm: "1400.00",
          tree: { id: "b3", type: "BAY", opening_type: "TILT_TURN_LEFT" },
        },
      ],
      couplings: [
        { id: "c1", angle_deg: "15.0", coupler_profile_sku: "ACOPLE-60" },
        { id: "c2", angle_deg: "15.0", coupler_profile_sku: "ACOPLE-60" },
      ],
    },
  };
  return {
    ...position("position-bow", "project-a", "Bow sala"),
    design: {
      system_id: "system-a",
      nominal_width_mm: "2100.00",
      nominal_height_mm: "1400.00",
      color: "WHITE",
      parametric_tree: tree,
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const clients: QueryClient[] = [];

function mount(path = "/projects/project-a/positions/position-a/edit") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
    },
  });
  clients.push(queryClient);
  const router = createMemoryRouter(
    [
      {
        path: "/projects/:id/positions/:posId/edit",
        element: <ProjectPositionEditor />,
      },
      {
        path: "/projects/:id/positions/new",
        element: <ProjectPositionEditor />,
      },
    ],
    { initialEntries: [path] },
  );

  const tree = () => (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
  const view = render(tree());
  return {
    ...view,
    router,
    refresh: () => act(() => identity.listeners.forEach((listener) => listener())),
  };
}

function change(key: TranslationKey, value: string) {
  fireEvent.change(screen.getByLabelText(t(key)), {
    target: { value },
  });
}

function save() {
  fireEvent.click(screen.getByRole("button", { name: t("projects.save") }));
}

async function ready(location = "Cocina", sku = "CUT-A") {
  await screen.findByRole("heading", { name: location });
  await waitFor(() => expect(evaluate).toHaveBeenCalled());
  await screen.findByText(sku);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: t("projects.save") })).toBeEnabled(),
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  identity.id = "org-a";
  identity.role = "OWNER";
  useCanvasStore.getState().reset();

  vi.mocked(engineSystems).mockResolvedValue(
    ok({
      systems: [
        {
          id: "system-a",
          code: "A",
          name: "Sistema A",
          is_demo: false,
          system_family: "CASEMENT",
          allowed_openings: [
            "FIXED",
            "TURN_LEFT",
            "TURN_RIGHT",
            "TILT_TURN_LEFT",
            "TILT_TURN_RIGHT",
            "AWNING",
            "DOOR_ENTRY",
            "DOOR_DOUBLE",
          ],
          quote_ready: true,
          readiness_reasons: [],
        },
        {
          id: "system-b",
          code: "B",
          name: "Sistema B",
          is_demo: false,
          system_family: "CASEMENT",
          allowed_openings: [
            "FIXED",
            "TURN_LEFT",
            "TURN_RIGHT",
            "TILT_TURN_LEFT",
            "TILT_TURN_RIGHT",
            "AWNING",
            "DOOR_ENTRY",
            "DOOR_DOUBLE",
          ],
          quote_ready: true,
          readiness_reasons: [],
        },
      ],
    }),
  );
  vi.mocked(projectDesignOptions).mockResolvedValue(
    ok({
      profiles: [
        {
          sku: "MULL-60",
          role: "MULLION_V",
          name: "Mullión 60",
          material: "PVC",
          face_width_mm: "70.00",
        },
        {
          sku: "MULL-H-60",
          role: "MULLION_H",
          name: "Travesaño 60",
          material: "PVC",
          face_width_mm: "70.00",
        },
      ],
      glazing_thicknesses: ["24.00", "28.00"],
      glass_skus: ["GLASS-A", "GLASS-B"],
      glass_products: [],
      glass_specs: [
        { sku: "GLASS-A", spec: "4-16-4" },
        { sku: "GLASS-B", spec: null },
      ],
      handle_policy: null,
      hardware_families: [],
      hardware_options: [],
      hardware_kits: [
        {
          sku: "KIT-B",
          name: "Kit B",
          opening_type: "TURN",
          min_leaf_width_mm: "400",
          max_leaf_width_mm: "1600",
          min_leaf_height_mm: "400",
          max_leaf_height_mm: "2400",
          max_leaf_weight_kg: "120",
          weight_kg: null,
          class_label: null,
          max_aspect_ratio: null,
          min_stay_height_mm: null,
          contents: [],
        },
      ],
      coupler_skus: ["ACOPLE-60"],
      coupler_profiles: [
        { sku: "ACOPLE-60", name: "Coplana 60", material: "PVC", face_width_mm: "90.00" },
      ],
      glazing_beads: [{ glass_thickness_mm: "24.00", bead_width_mm: "18.00", sku: "BEAD-24" }],
      panel_skus: [],
      panel_choices: [],
      colors: ["WHITE"],
      rebate_depth_mm: "20.00",
      sash_overlap_mm: "8.00",
      depth_mm: "60.00",
    }),
  );
  evaluate.mockResolvedValue(ok(assemblyEval()));
  retrieve.mockResolvedValue(ok(position()));
  update.mockResolvedValue(
    ok({
      ...position(),
      updated_at: "2026-09-18T15:01:00.123456Z",
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  clients.splice(0).forEach((client) => client.clear());
  useCanvasStore.getState().reset();
});

it("opens a new position directly on the canvas editor", async () => {
  mount("/projects/project-a/positions/new");
  await screen.findByRole("list", { name: t("assembly.starterLibrary") });
  // A blank window is already on the canvas — no product-type decision exists.
  expect(useCanvasStore.getState().inputs.product).not.toBeNull();
  expect(screen.getByRole("button", { name: t("projects.save") })).toBeDisabled();
});

it("loads a classic position as a compositional product and saves it back unchanged", async () => {
  mount();
  await ready();

  const product = useCanvasStore.getState().inputs.product;
  expect(product).not.toBeNull();
  expect(product!.assembly.modules).toHaveLength(1);
  expect(product!.assembly.modules[0]!.tree).toEqual(position().design.parametric_tree);

  change("projects.location", "Dormitorio");
  change("pricing.quantity", "7");
  save();

  await screen.findByText(t("projects.saved"));
  expect(update).toHaveBeenCalledExactlyOnceWith(
    position().id,
    {
      location_tag: "Dormitorio",
      quantity: 7,
      // Single-unit products fold back to the classic documentary shape.
      design: position().design,
      expected_updated_at: position().updated_at,
    },
    { headers: { "X-Organization-ID": "org-a" } },
  );
});

it("round-trips a saved assembly as product-v2", async () => {
  retrieve.mockResolvedValue(ok(bowPosition()));
  mount("/projects/project-a/positions/position-bow/edit");
  await ready("Bow sala");

  const product = useCanvasStore.getState().inputs.product;
  expect(product?.assembly.modules.map((m) => m.id)).toEqual(["m1", "m2", "m3"]);

  change("pricing.quantity", "2");
  save();
  await screen.findByText(t("projects.saved"));
  expect(update.mock.calls[0]?.[1].design).toEqual(bowPosition().design);
});

it("evaluates live through the assembly endpoint when the system changes", async () => {
  mount();
  await ready();

  change("projects.system", "system-b");

  await waitFor(() =>
    expect(evaluate).toHaveBeenCalledWith(expect.objectContaining({ system_id: "system-b" })),
  );
  expect(screen.getByText(t("projects.unsaved"))).toBeInTheDocument();
});

it("keeps save disabled only while the product is invalid", async () => {
  evaluate.mockResolvedValue(ok(assemblyEval("CUT-A", "INVALID")));
  mount();
  await screen.findByRole("heading", { name: "Cocina" });
  await screen.findByText("CUT-A");
  await waitFor(() => expect(evaluate).toHaveBeenCalled());
  expect(screen.getByRole("button", { name: t("projects.save") })).toBeDisabled();
  expect(update).not.toHaveBeenCalled();
});

it("saves a manufacturing-incomplete assembly as a draft", async () => {
  // Warnings carry a complete BOM — the draft persists; sealing/production
  // stay gated downstream.
  evaluate.mockResolvedValue(ok(assemblyEval("CUT-A", "MANUFACTURING_INCOMPLETE")));
  mount();
  await screen.findByRole("heading", { name: "Cocina" });
  await screen.findByText("CUT-A");
  await waitFor(() => expect(evaluate).toHaveBeenCalled());
  const button = screen.getByRole("button", { name: t("projects.save") });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await screen.findByText(t("projects.saved"));
  expect(update).toHaveBeenCalled();
});

it("builds a five-unit bow from the design library and edits a joint angle on plan", async () => {
  mount("/projects/project-a/positions/new");
  await screen.findByRole("list", { name: t("assembly.starterLibrary") });

  fireEvent.click(screen.getByRole("button", { name: /Bow ×5/ }));

  const product = useCanvasStore.getState().inputs.product;
  expect(product?.assembly.modules).toHaveLength(5);
  expect(product?.assembly.couplings).toHaveLength(4);
});

it("auto-resolves the catalog coupler when only one exists", async () => {
  mount("/projects/project-a/positions/new");
  await screen.findByRole("list", { name: t("assembly.starterLibrary") });

  fireEvent.click(screen.getByRole("button", { name: /Bow ×3/ }));

  // Starters ship null couplers; the catalog's single coupler fills them in.
  change("projects.system", "system-a");
  await waitFor(() => {
    const product = useCanvasStore.getState().inputs.product;
    expect(product?.assembly.couplings.every((c) => c.coupler_profile_sku === "ACOPLE-60")).toBe(
      true,
    );
  });
});

it("fills glass defaults when the catalog has a single glazing thickness", async () => {
  vi.mocked(projectDesignOptions).mockResolvedValue(
    ok({
      profiles: [],
      glazing_thicknesses: ["4.00"],
      handle_policy: null,
      hardware_families: [],
      hardware_options: [],
      hardware_kits: [],
      glass_skus: ["GLASS-A"],
      glass_products: [],
      glass_specs: [{ sku: "GLASS-A", spec: "4" }],
      coupler_skus: [],
      coupler_profiles: [],
      glazing_beads: [],
      panel_skus: [],
      panel_choices: [],
      colors: ["WHITE"],
      rebate_depth_mm: "20.00",
      sash_overlap_mm: "8.00",
      depth_mm: "60.00",
    }),
  );
  mount("/projects/project-a/positions/new");
  await screen.findByRole("list", { name: t("assembly.starterLibrary") });
  // The system <select> only commits once its options exist.
  await screen.findByRole("option", { name: /Sistema A/ });

  change("projects.system", "system-a");

  await waitFor(() =>
    expect(evaluate).toHaveBeenLastCalledWith(
      expect.objectContaining({
        product: expect.objectContaining({
          assembly: expect.objectContaining({
            modules: [
              expect.objectContaining({
                tree: expect.objectContaining({
                  glass_thickness_mm: "4.00",
                  glass_spec: "4.00",
                }),
              }),
            ],
          }),
        }),
      }),
    ),
  );
});

it("removes a selected module with Delete and undoes it", async () => {
  mount("/projects/project-a/positions/new");
  await screen.findByRole("list", { name: t("assembly.starterLibrary") });
  fireEvent.click(screen.getByRole("button", { name: /Bow ×3/ }));

  useCanvasStore.getState().select("m2");
  fireEvent.keyDown(window, { key: "Delete" });

  expect(useCanvasStore.getState().inputs.product?.assembly.modules).toHaveLength(2);

  fireEvent.click(screen.getByRole("button", { name: t("projects.undo") }));
  expect(useCanvasStore.getState().inputs.product?.assembly.modules).toHaveLength(3);
});

it("keeps a new design after an uncertain network response and prevents duplicate creation", async () => {
  create.mockRejectedValueOnce(new Error("connection lost after request"));
  mount("/projects/project-a/positions/new?copy=position-a");
  await ready();
  change("projects.location", "Copia pendiente");
  save();
  await screen.findByText(t("projects.uncertainPosition"));
  expect(screen.getByLabelText(t("projects.location"))).toHaveValue("Copia pendiente");
  expect(screen.getByRole("button", { name: t("projects.save") })).toBeDisabled();
  save();
  expect(create).toHaveBeenCalledOnce();
  expect(update).not.toHaveBeenCalled();
});

it("copies a position through create, preserving its exact design", async () => {
  const source = position();
  const sourceBefore = JSON.stringify(source);
  retrieve.mockResolvedValueOnce(ok(source));

  const pending = deferred<Awaited<ReturnType<typeof positionsCreate>>>();
  create.mockReturnValueOnce(pending.promise);
  const view = mount("/projects/project-a/positions/new?copy=position-a");
  await ready();

  expect(retrieve).toHaveBeenCalledExactlyOnceWith(source.id, {
    headers: { "X-Organization-ID": "org-a" },
  });
  expect(screen.getByText(t("projects.unsaved"))).toBeInTheDocument();
  expect(screen.getByLabelText(t("pricing.quantity"))).toHaveValue("4");

  change("projects.location", "Copia cocina");
  save();

  expect(create).toHaveBeenCalledExactlyOnceWith(
    source.project_id,
    {
      location_tag: "Copia cocina",
      quantity: source.quantity,
      design: source.design,
    },
    { headers: { "X-Organization-ID": "org-a" } },
  );
  expect(create.mock.calls[0]?.[1]).not.toHaveProperty("expected_updated_at");

  const copied: PositionResponse = {
    ...position("position-copy", "project-a", "Copia cocina"),
    position_index: 4,
    updated_at: "2026-09-18T16:00:00.123456Z",
  };
  retrieve.mockResolvedValueOnce(ok(copied));
  await act(async () => {
    pending.resolve({ ...ok(copied), status: 201 });
  });

  await waitFor(() => {
    expect(view.router.state.location.pathname).toBe(
      "/projects/project-a/positions/position-copy/edit",
    );
    expect(retrieve).toHaveBeenLastCalledWith(copied.id, {
      headers: { "X-Organization-ID": "org-a" },
    });
  });
  await ready("Copia cocina");
  expect(JSON.stringify(source)).toBe(sourceBefore);
});

it.each(["create", "update"] as const)(
  "sends only one %s for same-tick save clicks and unlocks after rejection",
  async (operation) => {
    const pendingCreate = deferred<Awaited<ReturnType<typeof positionsCreate>>>();
    const pendingUpdate = deferred<Awaited<ReturnType<typeof positionsUpdate>>>();
    const copied = position("position-copy");

    create.mockResolvedValue({ ...ok(copied), status: 201 });
    if (operation === "create") create.mockReturnValueOnce(pendingCreate.promise);
    else update.mockReturnValueOnce(pendingUpdate.promise);

    const view = mount(
      operation === "create"
        ? "/projects/project-a/positions/new?copy=position-a"
        : "/projects/project-a/positions/position-a/edit",
    );
    await ready();

    const button = screen.getByRole("button", { name: t("projects.save") });
    expect(button).toBeEnabled();

    act(() => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    const write = operation === "create" ? create : update;
    const otherWrite = operation === "create" ? update : create;
    expect(write).toHaveBeenCalledOnce();
    expect(otherWrite).not.toHaveBeenCalled();
    expect(button).toBeDisabled();

    await act(async () => {
      if (operation === "create")
        pendingCreate.reject(new ApiError(400, { error: { code: "validation_error" } }));
      else pendingUpdate.reject(new Error("write rejected"));
    });
    await screen.findByText(t("projects.saveError"));
    expect(screen.getByRole("button", { name: t("projects.save") })).toBeEnabled();

    if (operation === "create") retrieve.mockResolvedValueOnce(ok(copied));
    save();

    await waitFor(() => expect(write).toHaveBeenCalledTimes(2));
    expect(otherWrite).not.toHaveBeenCalled();
    if (operation === "create") {
      await waitFor(() =>
        expect(view.router.state.location.pathname).toBe(
          "/projects/project-a/positions/position-copy/edit",
        ),
      );
      await ready();
    } else {
      await screen.findByText(t("projects.saved"));
    }
    expect(write).toHaveBeenCalledTimes(2);
  },
);

it.each(["", "0", "-1", "1.5", "1e2", "abc", "2147483648"])(
  "does not submit invalid quantity %j",
  async (quantity) => {
    mount();
    await ready();
    change("pricing.quantity", quantity);
    save();

    expect(update).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByLabelText(t("pricing.quantity"))).toHaveValue(quantity);
  },
);

it.each(["1", "12", "2147483647"])(
  "submits quantity %s as an integer without recalculating",
  async (quantity) => {
    mount();
    await ready();
    const callsBefore = evaluate.mock.calls.length;
    change("pricing.quantity", quantity);
    save();

    await waitFor(() => expect(update).toHaveBeenCalledOnce());
    expect(update.mock.calls[0]?.[1].quantity).toBe(Number(quantity));
    expect(update.mock.calls[0]?.[1].design).toEqual(position().design);
    expect(evaluate.mock.calls.length).toBe(callsBefore);
  },
);

it.each(["http", "network"] as const)(
  "preserves edited fields and concurrency token after %s save rejection",
  async (failure) => {
    if (failure === "network") {
      update.mockRejectedValueOnce(new Error("private backend trace"));
    } else {
      update.mockResolvedValueOnce({
        status: 409,
        headers: new Headers(),
        data: { error: { code: "stale_position", detail: "Rejected" } },
      });
    }
    mount();
    await ready();
    change("projects.location", "Entrada editada");
    change("pricing.quantity", "9");
    const designBefore = useCanvasStore.getState().inputs;

    save();
    await screen.findByText(t("projects.saveError"));

    expect(screen.getByLabelText(t("projects.location"))).toHaveValue("Entrada editada");
    expect(screen.getByLabelText(t("pricing.quantity"))).toHaveValue("9");
    expect(useCanvasStore.getState().inputs).toEqual(designBefore);
    expect(screen.getByText(t("projects.unsaved"))).toBeInTheDocument();
    expect(screen.queryByText("private backend trace")).not.toBeInTheDocument();

    save();
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    expect(update.mock.calls[1]?.[1]).toEqual(update.mock.calls[0]?.[1]);
  },
);

it.each([
  ["organization", "retrieve"],
  ["navigation", "retrieve"],
  ["organization", "save"],
  ["navigation", "save"],
] as const)(
  "ignores late %s-bound %s completion after the workspace changes",
  async (boundary, operation) => {
    const oldLoad = deferred<Awaited<ReturnType<typeof positionsRetrieve>>>();
    const oldSave = deferred<Awaited<ReturnType<typeof positionsUpdate>>>();

    if (operation === "retrieve") retrieve.mockReturnValueOnce(oldLoad.promise);
    if (operation === "save") update.mockReturnValueOnce(oldSave.promise);

    const view = mount();
    if (operation === "retrieve") {
      await waitFor(() => expect(retrieve).toHaveBeenCalledOnce());
    } else {
      await ready();
      change("projects.location", "Old pending save");
      save();
      await waitFor(() => expect(update).toHaveBeenCalledOnce());
    }

    const next =
      boundary === "organization"
        ? position("position-a", "project-a", "Tenant B")
        : position("position-b", "project-b", "Position B");
    // Different dims → different product → the eval cache can't leak the old result.
    next.design = { ...next.design, nominal_width_mm: "1555.75" };
    next.bom = bom("CUT-B");
    evaluate.mockResolvedValue(ok(assemblyEval("CUT-B")));
    retrieve.mockResolvedValueOnce(ok(next));

    if (boundary === "organization") {
      identity.id = "org-b";
      view.refresh();
    } else {
      await act(async () => {
        await view.router.navigate("/projects/project-b/positions/position-b/edit");
      });
      // The pending save leaves the workspace dirty — the leave dialog gates
      // the route change and must be confirmed before the new position loads.
      if (operation === "save") {
        fireEvent.click(await screen.findByRole("button", { name: t("ui.confirm") }));
      }
    }
    await ready(next.location_tag!, "CUT-B");
    const currentInputs = useCanvasStore.getState().inputs;
    const currentPath = view.router.state.location.pathname;

    await act(async () => {
      if (operation === "retrieve") oldLoad.resolve(ok(position()));
      if (operation === "save") oldSave.resolve(ok(position()));
    });

    expect(useCanvasStore.getState().inputs).toEqual(currentInputs);
    expect(screen.getByLabelText(t("projects.location"))).toHaveValue(next.location_tag);
    expect(screen.getByText("CUT-B")).toBeInTheDocument();
    expect(screen.queryByText("CUT-A")).not.toBeInTheDocument();
    expect(screen.queryByText(t("projects.saved"))).not.toBeInTheDocument();
    expect(view.router.state.location.pathname).toBe(currentPath);
    expect(retrieve).toHaveBeenLastCalledWith(next.id, {
      headers: {
        "X-Organization-ID": boundary === "organization" ? "org-b" : "org-a",
      },
    });
  },
);

it("refuses generic FOILED canvas state at the persisted project boundary", async () => {
  mount();
  await ready();
  act(() => {
    const inputs = useCanvasStore.getState().inputs;
    useCanvasStore.getState().loadDesign({ ...inputs, color: "FOILED" });
  });
  save();
  expect(update).not.toHaveBeenCalled();
  expect(create).not.toHaveBeenCalled();
});

it("does not offer FOILED or a catalog the backend marks incomplete", async () => {
  vi.mocked(engineSystems).mockResolvedValue(
    ok({
      systems: [
        {
          id: "system-a",
          code: "A",
          name: "Sistema A",
          is_demo: false,
          system_family: "CASEMENT",
          allowed_openings: [
            "FIXED",
            "TURN_LEFT",
            "TURN_RIGHT",
            "TILT_TURN_LEFT",
            "TILT_TURN_RIGHT",
            "AWNING",
            "DOOR_ENTRY",
            "DOOR_DOUBLE",
          ],
          quote_ready: true,
          readiness_reasons: [],
        },
        {
          id: "system-b",
          code: "B",
          name: "Incomplete system",
          is_demo: false,
          system_family: "CASEMENT",
          allowed_openings: [
            "FIXED",
            "TURN_LEFT",
            "TURN_RIGHT",
            "TILT_TURN_LEFT",
            "TILT_TURN_RIGHT",
            "AWNING",
            "DOOR_ENTRY",
            "DOOR_DOUBLE",
          ],
          quote_ready: false,
          readiness_reasons: ["manufacturing"],
        },
      ],
    }),
  );
  mount();
  await ready();
  expect(screen.queryByRole("option", { name: /FOILED|Foliado/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Incomplete system" })).not.toBeInTheDocument();
});

it("renders the design library with rendered starter cards", async () => {
  mount("/projects/project-a/positions/new");
  const list = await screen.findByRole("list", {
    name: t("assembly.starterLibrary"),
  });
  expect(within(list).getAllByRole("listitem")).toHaveLength(15);
  // Every card previews through the same front-elevation renderer.
  expect(within(list).getAllByTestId("product-front").length).toBeGreaterThan(0);
});

it("picking a sliding starter card builds a sliding product", async () => {
  mount("/projects/project-a/positions/new");
  await screen.findByRole("list", { name: t("assembly.starterLibrary") });
  fireEvent.click(screen.getByRole("button", { name: /Corredera 2 hojas/ }));
  const product = useCanvasStore.getState().inputs.product;
  expect(product?.assembly.modules[0]?.tree.opening_type).toBe("SLIDING_2L");
});
