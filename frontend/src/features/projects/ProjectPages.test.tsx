// frontend/src/features/projects/ProjectPages.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError, apiMutator } from "../../api/apiMutator";
import {
  documentaryListArtifacts,
  positionsDestroy,
  projectPaymentIntegrationStatus,
  projectPaymentLinksList,
  projectPaymentsList,
  projectQuoteLinksList,
  projectsClone,
  projectsCreate,
  projectsList,
  projectsRetrieve,
  projectsUpdate,
} from "../../api/generated/dekopen";
import type {
  PositionResponse,
  ProjectResponse,
  ProjectWriteRequest,
} from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { ConfirmProvider } from "../../ui";
import { ProjectPages } from "./ProjectPages";

vi.mock("../../api/apiMutator", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/apiMutator")>();
  return { ...actual, apiMutator: vi.fn() };
});

vi.mock("../../auth/AuthSessionProvider", () => ({
  useAuthSession: () => ({
    status: "ready",
    session: { user: { id: "user-a" } },
    me: {
      active_organization: {
        id: "org-a",
        name: "Taller A",
        role: "OWNER",
      },
    },
  }),
}));

vi.mock("../../api/generated/dekopen", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/generated/dekopen")>();
  return {
    ...actual,
    projectsList: vi.fn(),
    projectsCreate: vi.fn(),
    projectsRetrieve: vi.fn(),
    projectsUpdate: vi.fn(),
    projectsClone: vi.fn(),
    positionsDestroy: vi.fn(),
    projectPaymentsList: vi.fn(),
    projectPaymentsRecord: vi.fn(),
    projectPaymentVoid: vi.fn(),
    projectPaymentLinksList: vi.fn(),
    projectPaymentIntegrationStatus: vi.fn(),
    projectPaymentLinkCreate: vi.fn(),
    projectPaymentLinkRecover: vi.fn(),
    projectQuoteLinksList: vi.fn(),
    documentaryListArtifacts: vi.fn(),
    documentsCompareVersions: vi.fn(),
  };
});

function response<S extends number, T>(status: S, data: T) {
  return { status, data, headers: new Headers() };
}

function makePosition(): PositionResponse {
  return {
    id: "position-a",
    project_id: "project-a",
    position_index: 1,
    location_tag: "Dormitorio principal",
    quantity: 2,
    price_net: "0",
    discount_pct: "0",
    typology: "FIXED",
    updated_at: "2026-09-18T12:01:02.123456Z",
    design: {
      system_id: "system-a",
      nominal_width_mm: "1234.50",
      nominal_height_mm: "987.60",
      color: "WHITE",
      parametric_tree: {
        id: "bay-a",
        type: "BAY",
        opening_type: "FIXED",
      },
    },
    bom: {
      profile_cuts: [],
      reinforcements: [],
      glasses: [],
      panels: [],
      fittings: [],
      hardware_items: [],
      leaf_weights: [],
      calculation_hash: `sha256:${"a".repeat(64)}`,
    },
  };
}

function makeProject(overrides: Partial<ProjectResponse> = {}): ProjectResponse {
  return {
    id: "project-a",
    code: "P-001",
    name: "Casa original",
    client_name: "Cliente original",
    client_rut: "",
    client_email: "",
    client_phone: "",
    client_giro: "",
    client_comuna: "",
    client_address: "",
    delivery_address: "",
    notes_commercial: "",
    notes_internal: "",
    status: "DRAFT",
    current_revision: "REV-A",
    updated_at: "2026-09-18T12:00:00.654321Z",
    total_price_net: "0.00",
    total_price_tax: "0.00",
    total_price_gross: "0.00",
    pricing_current: false,
    current_pricing_operation_id: null,
    currency: "CLP",
    position_count: 0,
    positions: [],
    versions: [],
    ...overrides,
  };
}

function expectedMetadata(project: ProjectResponse): ProjectWriteRequest {
  return {
    name: project.name,
    client_id: project.client_id ?? null,
    client_name: project.client_name,
    client_rut: project.client_rut ?? "",
    client_email: project.client_email ?? "",
    client_phone: project.client_phone ?? "",
    client_giro: project.client_giro ?? "",
    client_comuna: project.client_comuna ?? "",
    client_address: project.client_address ?? "",
    delivery_address: project.delivery_address ?? "",
    notes_commercial: project.notes_commercial ?? "",
    notes_internal: project.notes_internal ?? "",
  };
}

const mounted: {
  router: ReturnType<typeof createMemoryRouter>;
  client: QueryClient;
}[] = [];

function mount(path = "/projects/project-a") {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [
      { path: "/projects", element: <ProjectPages /> },
      { path: "/projects/:id", element: <ProjectPages /> },
    ],
    { initialEntries: [path] },
  );

  mounted.push({ router, client });
  render(
    <QueryClientProvider client={client}>
      <ConfirmProvider>
        <RouterProvider router={router} />
      </ConfirmProvider>
    </QueryClientProvider>,
  );
  return router;
}

/** Click through the canonical confirmation dialog instead of mocking
 * window.confirm — the test exercises the real surface. */
async function decide(approve: boolean): Promise<void> {
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(
    within(dialog).getByRole("button", { name: approve ? t("ui.confirm") : t("ui.cancel") }),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
}

function change(label: Parameters<typeof t>[0], value: string): void {
  fireEvent.change(screen.getByLabelText(t(label)), {
    target: { value },
  });
}

async function editMetadata(): Promise<void> {
  fireEvent.click(await screen.findByRole("button", { name: t("projects.edit") }));
}

function submit(): void {
  fireEvent.click(screen.getByRole("button", { name: t("projects.save") }));
}

function expectTenant(options: RequestInit | undefined): void {
  expect(new Headers(options?.headers).get("X-Organization-ID")).toBe("org-a");
  expect(options?.signal).toBeInstanceOf(AbortSignal);
}

beforeEach(() => {
  vi.resetAllMocks();
  // Browser dialog only; router, guard, query client and BOM remain real.
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(projectsList).mockResolvedValue(response(200, { items: [] }));
  vi.mocked(projectsRetrieve).mockResolvedValue(response(200, makeProject()));
  vi.mocked(projectPaymentsList).mockResolvedValue(
    response(200, {
      payments: [],
      invoices: [],
      collected: "0",
      quote_total_gross: null,
      balance: null,
      currency: "CLP",
      status: "NO_DEAL",
      sealed_revision: null,
    }),
  );
  vi.mocked(projectPaymentLinksList).mockResolvedValue(response(200, { links: [] }));
  vi.mocked(projectPaymentIntegrationStatus).mockResolvedValue(
    response(200, { configured: false, enabled: false }),
  );
  vi.mocked(projectQuoteLinksList).mockResolvedValue(response(200, []));
  vi.mocked(documentaryListArtifacts).mockResolvedValue(response(200, { artifacts: [] }));
});

afterEach(() => {
  cleanup();
  for (const { router, client } of mounted.splice(0)) {
    router.dispose();
    client.clear();
  }
  vi.restoreAllMocks();
});

it("creates a project, navigates to the server ID and renders persisted metadata", async () => {
  const created = makeProject({
    id: "server-created-id",
    code: "P-1042",
    name: "Nombre confirmado por servidor",
    client_name: "Cliente persistido",
    client_email: "persistido@example.test",
    notes_internal: "Nota recuperada desde detalle",
  });
  vi.mocked(projectsCreate).mockResolvedValue(response(201, created));
  vi.mocked(projectsRetrieve).mockResolvedValue(response(200, created));

  const router = mount("/projects");
  fireEvent.click(await screen.findByRole("button", { name: t("projects.create") }));
  change("projects.name", "Nombre ingresado");
  change("projects.client", "Cliente ingresado");
  change("projects.email", "ingresado@example.test");
  change("projects.internalNotes", "Nota ingresada");
  submit();

  await screen.findByRole("heading", {
    level: 1,
    name: "Nombre confirmado por servidor",
  });
  // The project code stays visible as secondary metadata, not as the title.
  expect(screen.getByText("P-1042")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/projects/server-created-id");
  expect(screen.getByText("Cliente persistido")).toBeInTheDocument();
  expect(screen.getByText("persistido@example.test")).toBeInTheDocument();
  expect(screen.getByText("Nota recuperada desde detalle")).toBeInTheDocument();
  expect(screen.queryByDisplayValue("Nombre ingresado")).not.toBeInTheDocument();

  expect(projectsCreate).toHaveBeenCalledTimes(1);
  const [body, options] = vi.mocked(projectsCreate).mock.calls[0]!;
  expect(body).toEqual({
    name: "Nombre ingresado",
    client_id: null,
    client_name: "Cliente ingresado",
    client_rut: "",
    client_email: "ingresado@example.test",
    client_phone: "",
    client_giro: "",
    client_comuna: "",
    client_address: "",
    delivery_address: "",
    notes_commercial: "",
    notes_internal: "Nota ingresada",
  });
  expectTenant(options);
  expect(projectsRetrieve).toHaveBeenCalledWith(
    created.id,
    expect.objectContaining({
      headers: { "X-Organization-ID": "org-a" },
    }),
  );
  // Successful creation must clear the real unsaved-change blocker.
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("PATCHes the exact original timestamp and reloads persisted metadata", async () => {
  const original = makeProject();
  const saved = makeProject({
    name: "Casa actualizada",
    client_phone: "+56 9 1234 5678",
    updated_at: "2026-09-18T13:00:00.111222Z",
  });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, original))
    .mockResolvedValue(response(200, saved));
  vi.mocked(projectsUpdate).mockResolvedValue(response(200, saved));

  mount();
  await editMetadata();
  change("projects.name", saved.name);
  change("projects.phone", saved.client_phone!);
  submit();

  await screen.findByRole("heading", {
    level: 1,
    name: "Casa actualizada",
  });
  expect(screen.getByText(saved.client_phone!)).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(t("projects.saved"));
  expect(screen.queryByLabelText(t("projects.name"))).not.toBeInTheDocument();

  expect(projectsUpdate).toHaveBeenCalledTimes(1);
  const [id, body, options] = vi.mocked(projectsUpdate).mock.calls[0]!;
  expect(id).toBe(original.id);
  expect(body).toEqual({
    ...expectedMetadata(saved),
    expected_updated_at: original.updated_at,
  });
  expectTenant(options);
  expect(projectsRetrieve).toHaveBeenCalledTimes(2);
});

it.each([
  [400, "projects.invalid", false],
  [409, "projects.conflict", true],
] as const)("retains entered metadata after API status %s", async (status, message, disabled) => {
  vi.mocked(projectsUpdate).mockRejectedValue(
    new ApiError(status, { error: { code: "private_backend_detail" } }),
  );

  mount();
  await editMetadata();
  change("projects.name", "Trabajo todavía sin guardar");
  change("projects.internalNotes", "Conservar esta nota");
  submit();

  expect(await screen.findByRole("alert")).toHaveTextContent(t(message));
  expect(screen.getByLabelText(t("projects.name"))).toHaveValue("Trabajo todavía sin guardar");
  expect(screen.getByLabelText(t("projects.internalNotes"))).toHaveValue("Conservar esta nota");
  expect(screen.queryByText("private_backend_detail")).not.toBeInTheDocument();

  const save = screen.getByRole("button", { name: t("projects.save") });
  if (disabled) {
    expect(save).toBeDisabled();
    expect(screen.getByRole("button", { name: t("projects.reload") })).toBeEnabled();
  } else {
    expect(save).toBeEnabled();
  }
  expect(projectsRetrieve).toHaveBeenCalledTimes(1);
});

it("clones a draft to the returned ID without mutating the source", async () => {
  const source = makeProject();
  const originalSnapshot = structuredClone(source);
  const copy = makeProject({
    id: "copy-server-id",
    code: "P-002",
    name: "Copia de Casa original",
    updated_at: "2026-09-18T14:00:00.000001Z",
  });

  vi.mocked(projectsRetrieve).mockImplementation(async (id) => {
    if (id === source.id) return response(200, source);
    if (id === copy.id) return response(200, copy);
    throw new Error(`Unexpected project ID: ${id}`);
  });
  vi.mocked(projectsClone).mockResolvedValue(response(201, copy));

  const router = mount();
  fireEvent.click(await screen.findByRole("button", { name: t("projects.cloneDraft") }));
  await screen.findByRole("heading", {
    level: 1,
    name: "Copia de Casa original",
  });

  expect(router.state.location.pathname).toBe("/projects/copy-server-id");
  expect(projectsClone).toHaveBeenCalledTimes(1);
  const [id, body, options] = vi.mocked(projectsClone).mock.calls[0]!;
  expect(id).toBe(source.id);
  expect(body).toEqual({ expected_updated_at: source.updated_at });
  expectTenant(options);
  expect(source).toEqual(originalSnapshot);
  expect(projectsUpdate).not.toHaveBeenCalled();
  expect(projectsCreate).not.toHaveBeenCalled();
  expect(positionsDestroy).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: t("projects.edit") }));
  change("projects.name", "Cambio local de la copia");
  expect(source).toEqual(originalSnapshot);
});

it("deletes using the exact position timestamp and renders the refreshed project", async () => {
  const position = makePosition();
  const original = makeProject({
    position_count: 1,
    positions: [position],
  });
  const emptied = makeProject({
    updated_at: "2026-09-18T15:00:00.000001Z",
  });

  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, original))
    .mockResolvedValue(response(200, emptied));
  vi.mocked(positionsDestroy).mockResolvedValue(response(204, undefined));

  mount();
  // The delete action lives in the side pane — select the vano first.
  fireEvent.click(await screen.findByText("1. Dormitorio principal"));
  fireEvent.click(screen.getByRole("button", { name: t("projects.deletePosition") }));

  await decide(true);
  expect(await screen.findByText(t("projects.noPositions"))).toBeInTheDocument();
  expect(screen.queryByText("1. Dormitorio principal")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(t("projects.deleted"));

  expect(positionsDestroy).toHaveBeenCalledTimes(1);
  const [id, params, options] = vi.mocked(positionsDestroy).mock.calls[0]!;
  expect(id).toBe(position.id);
  expect(params).toEqual({ expected_updated_at: position.updated_at });
  expectTenant(options);
  expect(projectsRetrieve).toHaveBeenCalledTimes(2);
});

it.each([
  [409, "projects.conflict"],
  [503, "projects.saveError"],
] as const)(
  "keeps the position row when deletion fails with status %s",
  async (status, message) => {
    const position = makePosition();
    vi.mocked(projectsRetrieve).mockResolvedValue(
      response(
        200,
        makeProject({
          position_count: 1,
          positions: [position],
        }),
      ),
    );
    vi.mocked(positionsDestroy).mockRejectedValue(
      new ApiError(status, { error: { code: "delete_rejected" } }),
    );

    mount();
    fireEvent.click(await screen.findByText("1. Dormitorio principal"));
    fireEvent.click(screen.getByRole("button", { name: t("projects.deletePosition") }));
    await decide(true);

    expect(await screen.findByRole("alert")).toHaveTextContent(t(message));
    expect(screen.getByText("1. Dormitorio principal")).toBeInTheDocument();
    expect(screen.queryByText(t("projects.noPositions"))).not.toBeInTheDocument();
    expect(screen.queryByText(t("projects.deleted"))).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: t("projects.deletePosition") })).toBeEnabled();
    });

    expect(positionsDestroy).toHaveBeenCalledWith(
      position.id,
      { expected_updated_at: position.updated_at },
      expect.objectContaining({
        headers: { "X-Organization-ID": "org-a" },
      }),
    );
    expect(projectsRetrieve).toHaveBeenCalledTimes(1);
  },
);

it("prepares and explicitly emits the current priced revision", async () => {
  const position = makePosition();
  const priced = makeProject({
    pricing_current: true,
    currency: "CLP",
    current_pricing_operation_id: "operation-a",
    total_price_gross: "1190.00",
    position_count: 1,
    positions: [position],
  });
  const quoted = makeProject({
    ...priced,
    status: "QUOTED",
    versions: [
      {
        id: "version-a",
        revision_code: "REV-A",
        authority_version: "SHOT10_V1",
        bom_hash: "a".repeat(64),
        snapshot_sha256: "b".repeat(64),
        production_allowed: true,
        documentary_complete: false,
        emitted_at: "2026-09-19T12:00:00Z",
      },
    ],
  });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, priced))
    .mockResolvedValue(response(200, quoted));
  vi.mocked(apiMutator).mockImplementation(async (url, options) => {
    if (url.endsWith("/inputs/") && options.method === "GET")
      return response(200, {
        project_id: priced.id,
        revision_code: "REV-A",
        payment_terms: "",
        quotation_valid_until: null,
        positions: [
          {
            position_id: position.id,
            calculation_hash: "sha256:" + "a".repeat(64),
            location_tag: position.location_tag,
            system_name: "Demo 60",
            manufacturing_placement_policy_id: "placement-a",
            handle_requirement_policy_id: "handle-a",
            reinforcement_cut_policy_id: "reinforcement-a",
            placement_options: [{ id: "placement-a", label: "Fabricación v1", version: 1 }],
            handle_options: [{ id: "handle-a", label: "Manillas v1", version: 1 }],
            reinforcement_options: [{ id: "reinforcement-a", label: "Refuerzos v1", version: 1 }],
            workshop_annotations: [],
            structural_inputs: [],
            glass_polishing: [],
            handle_intents: [],
            handle_requirements: [],
            accessory_schedule: { schema_version: 1, coverage: "NONE_REQUIRED", items: [] },
            legacy_handle_migration_confirmed: false,
          },
        ],
      }) as never;
    if (url.endsWith("/inputs/") && options.method === "PUT")
      return response(200, { project_id: priced.id, positions_saved: 1 }) as never;
    if (url.endsWith("/freeze/") && options.method === "POST")
      return response(201, { revision_code: "REV-A" }) as never;
    throw new Error(`Unexpected lifecycle request ${options.method} ${url}`);
  });

  mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.prepare") }));
  await screen.findByLabelText(t("quotation.paymentTerms"));
  change("quotation.paymentTerms", "50% anticipo");
  change("quotation.validUntil", "2026-10-19");
  fireEvent.click(screen.getByLabelText(t("quotation.confirm")));
  fireEvent.click(screen.getByRole("button", { name: t("quotation.emit") }));

  await screen.findAllByText(t("projects.quoted"));
  expect(screen.getAllByText("Revisión A")).toHaveLength(2);
  expect(apiMutator).toHaveBeenCalledTimes(3);
  const saveRequest = vi.mocked(apiMutator).mock.calls[1]!;
  expect(JSON.parse(String((saveRequest[1] as RequestInit).body))).toMatchObject({
    payment_terms: "50% anticipo",
    quotation_valid_until: "2026-10-19",
    positions: [{ location_tag: "Dormitorio principal" }],
  });
});

it("guards unsaved quotation preparation edits against navigation and cancel", async () => {
  const position = makePosition();
  const priced = makeProject({
    pricing_current: true,
    current_pricing_operation_id: "operation-a",
    total_price_gross: "1190.00",
    position_count: 1,
    positions: [position],
  });
  vi.mocked(projectsRetrieve).mockResolvedValue(response(200, priced));
  vi.mocked(apiMutator).mockImplementation(async (url, options) => {
    if (url.endsWith("/inputs/") && options.method === "GET")
      return response(200, {
        project_id: priced.id,
        revision_code: "REV-A",
        payment_terms: "",
        quotation_valid_until: null,
        positions: [
          {
            position_id: position.id,
            calculation_hash: "sha256:" + "a".repeat(64),
            location_tag: position.location_tag,
            system_name: "Demo 60",
            manufacturing_placement_policy_id: "placement-a",
            handle_requirement_policy_id: "handle-a",
            reinforcement_cut_policy_id: "reinforcement-a",
            placement_options: [{ id: "placement-a", label: "Fabricación v1", version: 1 }],
            handle_options: [{ id: "handle-a", label: "Manillas v1", version: 1 }],
            reinforcement_options: [{ id: "reinforcement-a", label: "Refuerzos v1", version: 1 }],
            workshop_annotations: [],
            structural_inputs: [],
            glass_polishing: [],
            handle_intents: [],
            handle_requirements: [],
            accessory_schedule: { schema_version: 1, coverage: "NONE_REQUIRED", items: [] },
            legacy_handle_migration_confirmed: false,
          },
        ],
      }) as never;
    throw new Error(`Unexpected lifecycle request ${options.method} ${url}`);
  });

  const router = mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.prepare") }));
  await screen.findByLabelText(t("quotation.paymentTerms"));
  change("quotation.paymentTerms", "50% anticipo");

  fireEvent.click(screen.getByRole("link", { name: t("projects.back") }));
  const leaveDialog = await screen.findByRole("dialog");
  expect(leaveDialog).toHaveTextContent(t("projects.leaveUnsaved"));
  await decide(false);
  expect(router.state.location.pathname).toBe("/projects/project-a");
  expect(screen.getByLabelText(t("quotation.paymentTerms"))).toHaveValue("50% anticipo");

  fireEvent.click(screen.getByRole("button", { name: t("projects.cancel") }));
  const discardDialog = await screen.findByRole("dialog");
  expect(discardDialog).toHaveTextContent(t("projects.discard"));
  await decide(false);
  expect(screen.getByLabelText(t("quotation.paymentTerms"))).toHaveValue("50% anticipo");

  fireEvent.click(screen.getByRole("button", { name: t("projects.cancel") }));
  await decide(true);
  await waitFor(() =>
    expect(screen.queryByLabelText(t("quotation.paymentTerms"))).not.toBeInTheDocument(),
  );

  fireEvent.click(screen.getByRole("button", { name: t("quotation.prepare") }));
  await screen.findByLabelText(t("quotation.paymentTerms"));
  change("quotation.validUntil", "2026-10-19");
  fireEvent.click(screen.getByRole("link", { name: t("projects.back") }));
  const leaveDialog2 = await screen.findByRole("dialog");
  expect(leaveDialog2).toHaveTextContent(t("projects.leaveUnsaved"));
  await decide(false);
  expect(router.state.location.pathname).toBe("/projects/project-a");

  fireEvent.click(screen.getByRole("link", { name: t("projects.back") }));
  await decide(true);
  await waitFor(() => expect(router.state.location.pathname).toBe("/projects"));
});

it("saves handle placement intents for operable leaves before emitting", async () => {
  const position = makePosition();
  const priced = makeProject({
    pricing_current: true,
    current_pricing_operation_id: "operation-a",
    total_price_gross: "1190.00",
    position_count: 1,
    positions: [position],
  });
  const quoted = makeProject({
    ...priced,
    status: "QUOTED",
    versions: [
      {
        id: "version-a",
        revision_code: "REV-A",
        authority_version: "SHOT10_V1",
        bom_hash: "a".repeat(64),
        snapshot_sha256: "b".repeat(64),
        production_allowed: true,
        documentary_complete: true,
        emitted_at: "2026-09-19T12:00:00Z",
      },
    ],
  });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, priced))
    .mockResolvedValue(response(200, quoted));
  vi.mocked(apiMutator).mockImplementation(async (url, options) => {
    if (url.endsWith("/inputs/") && options.method === "GET")
      return response(200, {
        project_id: priced.id,
        revision_code: "REV-A",
        payment_terms: "",
        quotation_valid_until: null,
        positions: [
          {
            position_id: position.id,
            calculation_hash: "sha256:" + "a".repeat(64),
            location_tag: position.location_tag,
            system_name: "Demo 60",
            manufacturing_placement_policy_id: "placement-a",
            handle_requirement_policy_id: "handle-a",
            reinforcement_cut_policy_id: "reinforcement-a",
            placement_options: [{ id: "placement-a", label: "Fabricación v1", version: 1 }],
            handle_options: [{ id: "handle-a", label: "Manillas v1", version: 1 }],
            reinforcement_options: [{ id: "reinforcement-a", label: "Refuerzos v1", version: 1 }],
            workshop_annotations: [],
            structural_inputs: [],
            glass_polishing: [],
            handle_intents: [],
            handle_requirements: [
              {
                policy_id: "handle-a",
                requirements: [
                  {
                    bay_id: "B1",
                    leaf_id: null,
                    leaf_label: "Hoja 1",
                    opening_type: "TURN_LEFT",
                    handle_domain_slot: "PRIMARY",
                    host_member_side: "LEFT",
                    outer_height_mm: "1400.10",
                    mounting_min_from_leaf_top_mm: "900.30",
                    mounting_max_from_leaf_top_mm: "1100.40",
                    permitted_vertical_references: ["LEAF_TOP", "OUTER_BOTTOM"],
                    leaf_rects: [
                      {
                        placement_policy_id: "placement-a",
                        leaf_top_from_outer_top_mm: "100.20",
                        leaf_height_mm: "1150.00",
                      },
                    ],
                  },
                ],
              },
            ],
            accessory_schedule: { schema_version: 1, coverage: "NONE_REQUIRED", items: [] },
            legacy_handle_migration_confirmed: false,
          },
        ],
      }) as never;
    if (url.endsWith("/inputs/") && options.method === "PUT")
      return response(200, { project_id: priced.id, positions_saved: 1 }) as never;
    if (url.endsWith("/freeze/") && options.method === "POST")
      return response(201, { revision_code: "REV-A" }) as never;
    throw new Error(`Unexpected lifecycle request ${options.method} ${url}`);
  });

  mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.prepare") }));
  const heightInput = await screen.findByLabelText(t("quotation.handleHeight"));
  // Missing intents are seeded with the displayed midpoint — the visible
  // value is exactly what Guardar/Emitir persists (no pending trap).
  expect(heightInput).toHaveValue("1000.35");
  expect(screen.queryByText(t("quotation.handlePending"))).toBeNull();
  expect(heightInput.getAttribute("placeholder")).toBe("900.3–1100.4");
  const referenceSelect = screen.getByLabelText(t("quotation.handleReference"));
  fireEvent.change(referenceSelect, { target: { value: "OUTER_BOTTOM" } });
  // OUTER_BOTTOM: outer 1400.10 − leafTop 100.20 − leaf-top bounds. Float math
  // would emit 399.599… and reject the exact boundary value the engine accepts.
  expect(heightInput.getAttribute("placeholder")).toBe("199.5–399.6");
  fireEvent.change(heightInput, { target: { value: "1050" } });
  expect(screen.getByText(t("quotation.handleOutOfBounds"))).toBeTruthy();
  fireEvent.change(heightInput, { target: { value: "399.6" } });
  expect(screen.queryByText(t("quotation.handleOutOfBounds"))).toBeNull();
  fireEvent.change(heightInput, { target: { value: "399.61" } });
  expect(screen.getByText(t("quotation.handleOutOfBounds"))).toBeTruthy();
  fireEvent.change(heightInput, { target: { value: "300" } });
  expect(screen.queryByText(t("quotation.handleOutOfBounds"))).toBeNull();
  change("quotation.paymentTerms", "50% anticipo");
  change("quotation.validUntil", "2026-10-19");
  fireEvent.click(screen.getByLabelText(t("quotation.confirm")));
  fireEvent.click(screen.getByRole("button", { name: t("quotation.emit") }));

  await screen.findAllByText(t("projects.quoted"));
  const saveRequest = vi.mocked(apiMutator).mock.calls[1]!;
  const body = JSON.parse(String((saveRequest[1] as RequestInit).body));
  expect(body.positions[0].handle_intents).toEqual([
    {
      bay_id: "B1",
      leaf_id: null,
      handle_domain_slot: "PRIMARY",
      requested_height_mm: "300",
      vertical_reference: "OUTER_BOTTOM",
    },
  ]);
});

it("reconciles handle intents when the handle policy changes", async () => {
  const position = makePosition();
  const priced = makeProject({
    pricing_current: true,
    current_pricing_operation_id: "operation-a",
    total_price_gross: "1190.00",
    position_count: 1,
    positions: [position],
  });
  const quoted = makeProject({
    ...priced,
    status: "QUOTED",
    versions: [
      {
        id: "version-a",
        revision_code: "REV-A",
        authority_version: "SHOT10_V1",
        bom_hash: "a".repeat(64),
        snapshot_sha256: "b".repeat(64),
        production_allowed: true,
        documentary_complete: true,
        emitted_at: "2026-09-19T12:00:00Z",
      },
    ],
  });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, priced))
    .mockResolvedValue(response(200, quoted));
  vi.mocked(apiMutator).mockImplementation(async (url, options) => {
    if (url.endsWith("/inputs/") && options.method === "GET")
      return response(200, {
        project_id: priced.id,
        revision_code: "REV-A",
        payment_terms: "",
        quotation_valid_until: null,
        positions: [
          {
            position_id: position.id,
            calculation_hash: "sha256:" + "a".repeat(64),
            location_tag: position.location_tag,
            system_name: "Demo 60",
            manufacturing_placement_policy_id: "placement-a",
            handle_requirement_policy_id: "handle-a",
            reinforcement_cut_policy_id: "reinforcement-a",
            placement_options: [{ id: "placement-a", label: "Fabricación v1", version: 1 }],
            handle_options: [
              { id: "handle-a", label: "Manillas v1", version: 1 },
              { id: "handle-b", label: "Manillas v2", version: 2 },
            ],
            reinforcement_options: [{ id: "reinforcement-a", label: "Refuerzos v1", version: 1 }],
            workshop_annotations: [],
            structural_inputs: [],
            glass_polishing: [],
            handle_intents: [
              {
                bay_id: "B1",
                leaf_id: null,
                handle_domain_slot: "PRIMARY",
                requested_height_mm: "1050",
                vertical_reference: "LEAF_TOP",
              },
              {
                bay_id: "B2",
                leaf_id: null,
                handle_domain_slot: "SECONDARY",
                requested_height_mm: "1050",
                vertical_reference: "LEAF_TOP",
              },
            ],
            handle_requirements: [
              {
                policy_id: "handle-a",
                requirements: [
                  {
                    bay_id: "B1",
                    leaf_id: null,
                    leaf_label: "Hoja 1",
                    opening_type: "TURN_LEFT",
                    handle_domain_slot: "PRIMARY",
                    host_member_side: "LEFT",
                    outer_height_mm: "1400.00",
                    mounting_min_from_leaf_top_mm: "900.00",
                    mounting_max_from_leaf_top_mm: "1100.00",
                    permitted_vertical_references: ["LEAF_TOP"],
                    leaf_rects: [
                      {
                        placement_policy_id: "placement-a",
                        leaf_top_from_outer_top_mm: "100.00",
                        leaf_height_mm: "1150.00",
                      },
                    ],
                  },
                  {
                    bay_id: "B2",
                    leaf_id: null,
                    leaf_label: "Hoja 2",
                    opening_type: "TURN_RIGHT",
                    handle_domain_slot: "SECONDARY",
                    host_member_side: "RIGHT",
                    outer_height_mm: "1400.00",
                    mounting_min_from_leaf_top_mm: "900.00",
                    mounting_max_from_leaf_top_mm: "1100.00",
                    permitted_vertical_references: ["LEAF_TOP"],
                    leaf_rects: [],
                  },
                ],
              },
              {
                policy_id: "handle-b",
                requirements: [
                  {
                    bay_id: "B1",
                    leaf_id: null,
                    leaf_label: "Hoja 1",
                    opening_type: "TURN_LEFT",
                    handle_domain_slot: "PRIMARY",
                    host_member_side: "LEFT",
                    outer_height_mm: "1400.00",
                    mounting_min_from_leaf_top_mm: "900.00",
                    mounting_max_from_leaf_top_mm: "1100.00",
                    permitted_vertical_references: ["OUTER_BOTTOM"],
                    leaf_rects: [],
                  },
                ],
              },
            ],
            accessory_schedule: { schema_version: 1, coverage: "NONE_REQUIRED", items: [] },
            legacy_handle_migration_confirmed: false,
          },
        ],
      }) as never;
    if (url.endsWith("/inputs/") && options.method === "PUT")
      return response(200, { project_id: priced.id, positions_saved: 1 }) as never;
    if (url.endsWith("/freeze/") && options.method === "POST")
      return response(201, { revision_code: "REV-A" }) as never;
    throw new Error(`Unexpected lifecycle request ${options.method} ${url}`);
  });

  mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.prepare") }));
  const policySelect = await screen.findByLabelText(t("quotation.handlePolicy"));
  fireEvent.change(policySelect, { target: { value: "handle-b" } });
  change("quotation.paymentTerms", "50% anticipo");
  change("quotation.validUntil", "2026-10-19");
  fireEvent.click(screen.getByLabelText(t("quotation.confirm")));
  fireEvent.click(screen.getByRole("button", { name: t("quotation.emit") }));

  await screen.findAllByText(t("projects.quoted"));
  const saveRequest = vi.mocked(apiMutator).mock.calls[1]!;
  const body = JSON.parse(String((saveRequest[1] as RequestInit).body));
  // B2's SECONDARY slot does not exist under handle-b: dropped. B1 survives
  // but LEAF_TOP is not permitted there: reset to the only permitted value.
  expect(body.positions[0].handle_intents).toEqual([
    {
      bay_id: "B1",
      leaf_id: null,
      handle_domain_slot: "PRIMARY",
      requested_height_mm: "1050",
      vertical_reference: "OUTER_BOTTOM",
    },
  ]);
});

it("keeps a manually edited height when the handle policy changes", async () => {
  const position = makePosition();
  const priced = makeProject({
    pricing_current: true,
    current_pricing_operation_id: "operation-a",
    total_price_gross: "1190.00",
    position_count: 1,
    positions: [position],
  });
  const quoted = makeProject({
    ...priced,
    status: "QUOTED",
    versions: [
      {
        id: "version-a",
        revision_code: "REV-A",
        authority_version: "SHOT10_V1",
        bom_hash: "a".repeat(64),
        snapshot_sha256: "b".repeat(64),
        production_allowed: true,
        documentary_complete: true,
        emitted_at: "2026-09-19T12:00:00Z",
      },
    ],
  });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, priced))
    .mockResolvedValue(response(200, quoted));
  const requirement = (policyId: string, minMm: string, maxMm: string) => ({
    policy_id: policyId,
    requirements: [
      {
        bay_id: "B1",
        leaf_id: null,
        leaf_label: "Hoja 1",
        opening_type: "TURN_LEFT",
        handle_domain_slot: "PRIMARY",
        host_member_side: "LEFT",
        outer_height_mm: "1400.00",
        mounting_min_from_leaf_top_mm: minMm,
        mounting_max_from_leaf_top_mm: maxMm,
        permitted_vertical_references: ["LEAF_TOP"],
        leaf_rects: [
          {
            placement_policy_id: "placement-a",
            leaf_top_from_outer_top_mm: "100.00",
            leaf_height_mm: "1150.00",
          },
        ],
      },
    ],
  });
  vi.mocked(apiMutator).mockImplementation(async (url, options) => {
    if (url.endsWith("/inputs/") && options.method === "GET")
      return response(200, {
        project_id: priced.id,
        revision_code: "REV-A",
        payment_terms: "",
        quotation_valid_until: null,
        positions: [
          {
            position_id: position.id,
            calculation_hash: "sha256:" + "a".repeat(64),
            location_tag: position.location_tag,
            system_name: "Demo 60",
            manufacturing_placement_policy_id: "placement-a",
            handle_requirement_policy_id: "handle-a",
            reinforcement_cut_policy_id: "reinforcement-a",
            placement_options: [{ id: "placement-a", label: "Fabricación v1", version: 1 }],
            handle_options: [
              { id: "handle-a", label: "Manillas v1", version: 1 },
              { id: "handle-b", label: "Manillas v2", version: 2 },
            ],
            reinforcement_options: [{ id: "reinforcement-a", label: "Refuerzos v1", version: 1 }],
            workshop_annotations: [],
            structural_inputs: [],
            glass_polishing: [],
            // No stored intent: the app seeds the displayed midpoint and
            // tracks the seed — the estimator's edit must detach it.
            handle_intents: [],
            handle_requirements: [
              requirement("handle-a", "900.00", "1100.00"),
              // The same slot exists under v2 with different bounds — a
              // reseed would recompute the height it seeded under v1.
              requirement("handle-b", "700.00", "900.00"),
            ],
            accessory_schedule: { schema_version: 1, coverage: "NONE_REQUIRED", items: [] },
            legacy_handle_migration_confirmed: false,
          },
        ],
      }) as never;
    if (url.endsWith("/inputs/") && options.method === "PUT")
      return response(200, { project_id: priced.id, positions_saved: 1 }) as never;
    if (url.endsWith("/freeze/") && options.method === "POST")
      return response(201, { revision_code: "REV-A" }) as never;
    throw new Error(`Unexpected lifecycle request ${options.method} ${url}`);
  });

  mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.prepare") }));
  const heightInput = await screen.findByLabelText(t("quotation.handleHeight"));
  expect(heightInput).toHaveValue("1000");
  fireEvent.change(heightInput, { target: { value: "750" } });
  const policySelect = screen.getByLabelText(t("quotation.handlePolicy"));
  fireEvent.change(policySelect, { target: { value: "handle-b" } });
  change("quotation.paymentTerms", "50% anticipo");
  change("quotation.validUntil", "2026-10-19");
  fireEvent.click(screen.getByLabelText(t("quotation.confirm")));
  fireEvent.click(screen.getByRole("button", { name: t("quotation.emit") }));

  await screen.findAllByText(t("projects.quoted"));
  const saveRequest = vi.mocked(apiMutator).mock.calls[1]!;
  const body = JSON.parse(String((saveRequest[1] as RequestInit).body));
  // The estimator typed 750 — the v2 reseed (bounds 700–900 → midpoint 800)
  // must not overwrite it with its own recomputed value.
  expect(body.positions[0].handle_intents).toEqual([
    {
      bay_id: "B1",
      leaf_id: null,
      handle_domain_slot: "PRIMARY",
      requested_height_mm: "750",
      vertical_reference: "LEAF_TOP",
    },
  ]);
});

it("seals suggested heights only after the estimator confirms them", async () => {
  const position = makePosition();
  const priced = makeProject({
    pricing_current: true,
    current_pricing_operation_id: "operation-a",
    total_price_gross: "1190.00",
    position_count: 1,
    positions: [position],
  });
  const quoted = makeProject({
    ...priced,
    status: "QUOTED",
    versions: [
      {
        id: "version-a",
        revision_code: "REV-A",
        authority_version: "SHOT10_V1",
        bom_hash: "a".repeat(64),
        snapshot_sha256: "b".repeat(64),
        production_allowed: true,
        documentary_complete: true,
        emitted_at: "2026-09-19T12:00:00Z",
      },
    ],
  });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, priced))
    .mockResolvedValue(response(200, quoted));
  vi.mocked(apiMutator).mockImplementation(async (url, options) => {
    if (url.endsWith("/inputs/") && options.method === "GET")
      return response(200, {
        project_id: priced.id,
        revision_code: "REV-A",
        payment_terms: "",
        quotation_valid_until: null,
        positions: [
          {
            position_id: position.id,
            calculation_hash: "sha256:" + "a".repeat(64),
            location_tag: position.location_tag,
            system_name: "Demo 60",
            manufacturing_placement_policy_id: "placement-a",
            handle_requirement_policy_id: "handle-a",
            reinforcement_cut_policy_id: "reinforcement-a",
            placement_options: [{ id: "placement-a", label: "Fabricación v1", version: 1 }],
            handle_options: [
              { id: "handle-a", label: "Manillas v1", version: 1 },
              { id: "handle-b", label: "Manillas v2", version: 2 },
            ],
            reinforcement_options: [{ id: "reinforcement-a", label: "Refuerzos v1", version: 1 }],
            workshop_annotations: [],
            structural_inputs: [],
            glass_polishing: [],
            handle_intents: [],
            handle_requirements: [
              {
                policy_id: "handle-a",
                requirements: [
                  {
                    bay_id: "B1",
                    leaf_id: null,
                    leaf_label: "Hoja 1",
                    opening_type: "TURN_LEFT",
                    handle_domain_slot: "PRIMARY",
                    host_member_side: "LEFT",
                    outer_height_mm: "1400.00",
                    mounting_min_from_leaf_top_mm: "900.00",
                    mounting_max_from_leaf_top_mm: "1100.00",
                    permitted_vertical_references: ["LEAF_TOP"],
                    leaf_rects: [
                      {
                        placement_policy_id: "placement-a",
                        leaf_top_from_outer_top_mm: "100.00",
                        leaf_height_mm: "1150.00",
                      },
                    ],
                  },
                ],
              },
              // Same slot, different bounds under v2 — the carried seed must
              // recompute to the new policy's midpoint.
              {
                policy_id: "handle-b",
                requirements: [
                  {
                    bay_id: "B1",
                    leaf_id: null,
                    leaf_label: "Hoja 1",
                    opening_type: "TURN_LEFT",
                    handle_domain_slot: "PRIMARY",
                    host_member_side: "LEFT",
                    outer_height_mm: "1400.00",
                    mounting_min_from_leaf_top_mm: "700.00",
                    mounting_max_from_leaf_top_mm: "900.00",
                    permitted_vertical_references: ["LEAF_TOP"],
                    leaf_rects: [
                      {
                        placement_policy_id: "placement-a",
                        leaf_top_from_outer_top_mm: "100.00",
                        leaf_height_mm: "1150.00",
                      },
                    ],
                  },
                ],
              },
            ],
            accessory_schedule: { schema_version: 1, coverage: "NONE_REQUIRED", items: [] },
            legacy_handle_migration_confirmed: false,
          },
        ],
      }) as never;
    if (url.endsWith("/inputs/") && options.method === "PUT")
      return response(200, { project_id: priced.id, positions_saved: 1 }) as never;
    if (url.endsWith("/freeze/") && options.method === "POST")
      return response(201, { revision_code: "REV-A" }) as never;
    throw new Error(`Unexpected lifecycle request ${options.method} ${url}`);
  });

  mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.prepare") }));
  const heightInput = await screen.findByLabelText(t("quotation.handleHeight"));
  // The generated midpoint is visible but flagged as a suggestion — not yet
  // the estimator's choice.
  expect(heightInput).toHaveValue("1000");
  expect(screen.getByText(t("quotation.handleSuggested"))).toBeTruthy();
  change("quotation.paymentTerms", "50% anticipo");
  change("quotation.validUntil", "2026-10-19");
  fireEvent.click(screen.getByLabelText(t("quotation.confirm")));
  fireEvent.click(screen.getByRole("button", { name: t("quotation.emit") }));

  // Unconfirmed suggestions block the seal — nothing is persisted.
  await screen.findByText(t("quotation.seedsUnconfirmed"));
  expect(
    vi
      .mocked(apiMutator)
      .mock.calls.filter(
        ([url, options]) => url.endsWith("/inputs/") && (options as RequestInit).method === "PUT",
      ),
  ).toHaveLength(0);

  // Switching policy recomputes the carried seed to the new bounds (700–900 →
  // 800), so a stale generated midpoint cannot ride along.
  const policySelect = screen.getByLabelText(t("quotation.handlePolicy"));
  fireEvent.change(policySelect, { target: { value: "handle-b" } });
  expect(heightInput).toHaveValue("800");

  fireEvent.click(screen.getByRole("button", { name: t("quotation.confirmSuggested") }));
  expect(screen.queryByText(t("quotation.handleSuggested"))).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: t("quotation.emit") }));

  await screen.findByText(t("projects.quoted"));
  const saveRequest = vi
    .mocked(apiMutator)
    .mock.calls.find(
      ([url, options]) => url.endsWith("/inputs/") && (options as RequestInit).method === "PUT",
    )!;
  const body = JSON.parse(String((saveRequest[1] as RequestInit).body));
  expect(body.positions[0].handle_intents).toEqual([
    {
      bay_id: "B1",
      leaf_id: null,
      handle_domain_slot: "PRIMARY",
      requested_height_mm: "800",
      vertical_reference: "LEAF_TOP",
    },
  ]);
});

it("asks before cloning away from dirty quotation preparation edits", async () => {
  const position = makePosition();
  const priced = makeProject({
    pricing_current: true,
    current_pricing_operation_id: "operation-a",
    position_count: 1,
    positions: [position],
  });
  const copy = makeProject({ id: "copy-server-id", code: "P-002" });
  vi.mocked(projectsRetrieve).mockImplementation(async (id) => {
    if (id === priced.id) return response(200, priced);
    if (id === copy.id) return response(200, copy);
    throw new Error(`Unexpected project ID: ${id}`);
  });
  vi.mocked(projectsClone).mockResolvedValue(response(201, copy));
  vi.mocked(apiMutator).mockImplementation(async (url, options) => {
    if (url.endsWith("/inputs/") && options.method === "GET")
      return response(200, {
        project_id: priced.id,
        revision_code: "REV-A",
        payment_terms: "",
        quotation_valid_until: null,
        positions: [
          {
            position_id: position.id,
            calculation_hash: "sha256:" + "a".repeat(64),
            location_tag: position.location_tag,
            system_name: "Demo 60",
            manufacturing_placement_policy_id: "placement-a",
            handle_requirement_policy_id: "handle-a",
            reinforcement_cut_policy_id: "reinforcement-a",
            placement_options: [{ id: "placement-a", label: "Fabricación v1", version: 1 }],
            handle_options: [{ id: "handle-a", label: "Manillas v1", version: 1 }],
            reinforcement_options: [{ id: "reinforcement-a", label: "Refuerzos v1", version: 1 }],
            workshop_annotations: [],
            structural_inputs: [],
            glass_polishing: [],
            handle_intents: [],
            handle_requirements: [],
            accessory_schedule: { schema_version: 1, coverage: "NONE_REQUIRED", items: [] },
            legacy_handle_migration_confirmed: false,
          },
        ],
      }) as never;
    throw new Error(`Unexpected lifecycle request ${options.method} ${url}`);
  });

  const router = mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.prepare") }));
  await screen.findByLabelText(t("quotation.paymentTerms"));
  change("quotation.paymentTerms", "50% anticipo");

  fireEvent.click(screen.getByRole("button", { name: t("projects.cloneDraft") }));
  const leaveDialog = await screen.findByRole("dialog");
  expect(leaveDialog).toHaveTextContent(t("projects.leaveUnsaved"));
  await decide(false);
  expect(projectsClone).not.toHaveBeenCalled();
  expect(router.state.location.pathname).toBe("/projects/project-a");
  expect(screen.getByLabelText(t("quotation.paymentTerms"))).toHaveValue("50% anticipo");

  fireEvent.click(screen.getByRole("button", { name: t("projects.cloneDraft") }));
  await decide(true);
  await screen.findByRole("heading", { level: 1, name: "Casa original" });
  expect(router.state.location.pathname).toBe("/projects/copy-server-id");
  expect(projectsClone).toHaveBeenCalledTimes(1);
});

it("opens one idempotent editable successor from a quoted revision", async () => {
  const quoted = makeProject({ status: "QUOTED", versions: [] });
  const successor = makeProject({ current_revision: "REV-B" });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, quoted))
    .mockResolvedValue(response(200, successor));
  vi.mocked(apiMutator).mockResolvedValue(
    response(201, { ...successor, successor_created: true }) as never,
  );

  mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.editQuoted") }));

  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent(t("quotation.successorConfirm"));
  await decide(true);
  await screen.findByText("Revisión B");
  expect(apiMutator).toHaveBeenCalledTimes(1);
  expect(vi.mocked(apiMutator).mock.calls[0]?.[0]).toBe("/api/v1/projects/project-a/successor/");
});

it("explicitly retires current draft pricing with an audit reason before editing", async () => {
  const priced = makeProject({
    pricing_current: true,
    current_pricing_operation_id: "operation-a",
    position_count: 1,
    positions: [makePosition()],
  });
  vi.mocked(projectsRetrieve)
    .mockResolvedValueOnce(response(200, priced))
    .mockResolvedValue(
      response(200, makeProject({ position_count: 1, positions: [makePosition()] })),
    );
  vi.mocked(apiMutator).mockResolvedValue(response(200, {}) as never);
  mount();
  fireEvent.click(await screen.findByRole("button", { name: t("quotation.resetPricing") }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent(t("quotation.resetReason"));
  fireEvent.change(within(dialog).getByRole("textbox"), {
    target: { value: "Corregir medidas" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: t("ui.confirm") }));
  await waitFor(() =>
    expect(apiMutator).toHaveBeenCalledWith(
      "/api/v1/projects/project-a/reset-pricing/",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_operation_id: "operation-a",
          reason: "Corregir medidas",
          confirmed: true,
        }),
      }),
    ),
  );
  expect(await screen.findByRole("link", { name: t("projects.addPosition") })).toBeInTheDocument();
});
