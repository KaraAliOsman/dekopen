import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { apiMutator, ApiError } from "../../api/apiMutator";
import { t } from "../../i18n/es-CL";
import { CommercialPricingPage, PricingPage } from "./PricingPage";
import { formatMoney } from "../../format";

/** Pages under test render router Links (e.g. the demo-design shortcut). */
const page = (ui: JSX.Element): JSX.Element => <MemoryRouter>{ui}</MemoryRouter>;

vi.mock("../../api/generated/dekopen", () => ({
  projectsList: vi.fn().mockResolvedValue({
    status: 200,
    data: {
      items: [
        { id: "project-a", code: "P-001", name: "Casa", client_name: "Cliente" },
        { id: "project-A", code: "P-A", name: "Casa A", client_name: "Cliente A" },
        { id: "project-B", code: "P-B", name: "Casa B", client_name: "Cliente B" },
      ],
    },
  }),
  projectsRetrieve: vi.fn().mockResolvedValue({
    status: 200,
    data: {
      id: "project-a",
      current_revision: "REV-A",
      positions: [
        {
          position_index: 1,
          location_tag: "Living",
          quantity: 2,
          design: {
            parametric_tree: { type: "BAY", opening_type: "FIXED" },
            nominal_width_mm: "1000",
            nominal_height_mm: "1000",
          },
        },
        { position_index: 2, location_tag: "Dormitorio", quantity: 1 },
      ],
    },
  }),
}));

const identity = vi.hoisted(() => ({ id: "tenant-a", role: "OWNER" }));
vi.mock("../../auth/AuthSessionProvider", () => ({
  useAuthSession: () => ({ me: { active_organization: identity } }),
}));
vi.mock("../../api/apiMutator", () => ({ apiMutator: vi.fn(), ApiError: class extends Error {} }));

beforeEach(() => {
  identity.id = "tenant-a";
  identity.role = "OWNER";
  vi.mocked(apiMutator)
    .mockReset()
    .mockResolvedValue({ data: { items: [] } });
});
afterEach(cleanup);

it.each(["ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER"])(
  "denies S09 to %s without fetching costs",
  (role) => {
    identity.role = role;
    render(page(<PricingPage />));
    expect(screen.getByRole("alert")).toHaveTextContent(t("pricing.ownerOnly"));
    expect(apiMutator).not.toHaveBeenCalled();
  },
);

it("keeps the current request alive after StrictMode cleanup and aborts on tenant switch", async () => {
  const view = render(
    page(
      <StrictMode>
        <PricingPage />
      </StrictMode>,
    ),
  );
  await waitFor(() => expect(apiMutator).toHaveBeenCalledTimes(2));
  const previous = vi.mocked(apiMutator).mock.calls.at(-1)?.[1].signal;
  expect(previous?.aborted).toBe(false);
  identity.id = "tenant-b";
  view.rerender(
    page(
      <StrictMode>
        <PricingPage />
      </StrictMode>,
    ),
  );
  expect(previous?.aborted).toBe(true);
  await waitFor(() =>
    expect(apiMutator).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Organization-ID": "tenant-b" }),
      }),
    ),
  );
});

it("lets an estimator calculate without requesting confidential administration", async () => {
  identity.role = "ESTIMATOR";
  render(page(<CommercialPricingPage />));
  expect(screen.getByText(t("pricing.calculate"))).toBeInTheDocument();
  await waitFor(() => expect(apiMutator).toHaveBeenCalledTimes(1));
  expect(apiMutator).toHaveBeenLastCalledWith("/api/v1/pricing/operations/", expect.any(Object));
  expect(screen.queryByText(t("pricing.cost"))).not.toBeInTheDocument();
});

it("does not apply a late preview after its financial input changes", async () => {
  identity.role = "ESTIMATOR";
  let resolve: (value: unknown) => void = () => undefined;
  vi.mocked(apiMutator).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(page(<CommercialPricingPage />));
  const submit = screen.getByRole("button", { name: t("pricing.preview") });
  fireEvent.submit(submit.closest("form")!);
  fireEvent.change(screen.getByLabelText(t("pricing.discount")), { target: { value: "0.05" } });
  await act(async () =>
    resolve({
      data: {
        id: "stale",
        state: "PREVIEW",
        currency: "CLP",
        project_net: "1000",
        lines: [],
        cost_lines: [],
        total_cost: "0",
        reason: "r",
        requested_by: "u",
        approved_by: null,
        approved_at: null,
        created_at: "2026-09-25T00:00:00Z",
      },
    }),
  );
  expect(screen.queryByRole("button", { name: t("pricing.apply") })).not.toBeInTheDocument();
});

it("allows an owner to review and reject a saved pending request", async () => {
  const pending = {
    id: "operation-a",
    project_id: "project-a",
    revision_code: "REV-A",
    discount_pct: "0.15",
    state: "PENDING",
    currency: "CLP",
    lines: [],
    cost_lines: [],
    total_cost: "700",
    project_net: "850",
    project_tax: "162",
    project_gross: "1012",
    reason: "Cotización",
    requested_by: "estimator-1",
    approved_by: null,
    approved_at: null,
    created_at: "2026-09-25T00:00:00Z",
  };
  vi.mocked(apiMutator)
    .mockResolvedValueOnce({ data: [pending] })
    .mockResolvedValueOnce({ data: { ...pending, state: "REJECTED" } });
  render(page(<CommercialPricingPage />));
  fireEvent.click(screen.getByRole("button", { name: t("pricing.reload") }));
  fireEvent.click(await screen.findByRole("button", { name: t("pricing.review") }));
  fireEvent.change(screen.getByLabelText(t("pricing.reason")), {
    target: { value: "Descuento no autorizado" },
  });
  fireEvent.click(screen.getByRole("button", { name: t("pricing.reject") }));
  await waitFor(() =>
    expect(apiMutator).toHaveBeenCalledWith(
      "/api/v1/pricing/operations/operation-a/apply/",
      expect.objectContaining({
        body: JSON.stringify({ reason: "Descuento no autorizado", confirmed: false, reject: true }),
      }),
    ),
  );
});

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<unknown>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function result(id: string, state = "PREVIEW") {
  return {
    id,
    project_id: `project-${id}`,
    revision_code: "REV-A",
    discount_pct: "0.05",
    state,
    currency: "CLP",
    lines: [],
    cost_lines: [],
    total_cost: "80",
    project_net: id === "B" ? "200" : "100",
    project_tax: "19",
    project_gross: id === "B" ? "238" : "119",
    reason: "Cotización",
    requested_by: "estimator-1",
    approved_by: null,
    approved_at: null,
    created_at: "2026-09-25T00:00:00Z",
  };
}
function previewButton() {
  return screen.getByRole("button", { name: t("pricing.preview") });
}
function submitPreview() {
  fireEvent.submit(previewButton().closest("form")!);
}
function changeFinancialInput() {
  fireEvent.change(screen.getByLabelText(t("pricing.discount")), { target: { value: "0.07" } });
}
async function settle(task: ReturnType<typeof deferred>, value: unknown, failure = false) {
  await act(async () => {
    if (failure) task.reject(new Error("controlled failure"));
    else task.resolve({ data: value });
  });
}

it.each([false, true])(
  "invalidated preview success/failure cannot publish or finish a newer request (failure=%s)",
  async (failure) => {
    const a = deferred(),
      b = deferred();
    vi.mocked(apiMutator)
      .mockResolvedValueOnce({ data: [] })
      .mockImplementationOnce(() => a.promise)
      .mockImplementationOnce(() => b.promise);
    render(page(<CommercialPricingPage />));
    submitPreview();
    changeFinancialInput();
    expect(previewButton()).toBeEnabled();
    submitPreview();
    await settle(a, result("A"), failure);
    expect(previewButton()).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Proyecto: P-A · Cliente A · Casa A")).not.toBeInTheDocument();
    await settle(b, result("B"));
    expect(screen.getByText("Proyecto: P-B · Cliente B · Casa B")).toBeInTheDocument();
    expect(previewButton()).toBeEnabled();
  },
);

it("preview B alone wins when B completes before A", async () => {
  const a = deferred(),
    b = deferred();
  vi.mocked(apiMutator)
    .mockResolvedValueOnce({ data: [] })
    .mockImplementationOnce(() => a.promise)
    .mockImplementationOnce(() => b.promise);
  render(page(<CommercialPricingPage />));
  submitPreview();
  changeFinancialInput();
  submitPreview();
  await settle(b, result("B"));
  await settle(a, result("A"));
  expect(screen.getByText("Proyecto: P-B · Cliente B · Casa B")).toBeInTheDocument();
  expect(screen.queryByText("Proyecto: P-A · Cliente A · Casa A")).not.toBeInTheDocument();
  expect(previewButton()).toBeEnabled();
});

it("current preview failure remains visible and releases its busy authority", async () => {
  const task = deferred();
  vi.mocked(apiMutator).mockImplementationOnce(() => task.promise);
  render(page(<CommercialPricingPage />));
  submitPreview();
  expect(previewButton()).toBeDisabled();
  await settle(task, null, true);
  expect(screen.getByRole("alert")).toHaveTextContent(t("pricing.calculateError"));
  expect(previewButton()).toBeEnabled();
});

it.each(["apply", "reject"] as const)(
  "stale %s cannot replace a newer preview; reload reflects the persisted mutation",
  async (action) => {
    const mutation = deferred(),
      next = deferred();
    const original = result("A", action === "reject" ? "PENDING" : "PREVIEW");
    const persisted = result("A", action === "reject" ? "REJECTED" : "APPLIED");
    vi.mocked(apiMutator)
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: original })
      .mockImplementationOnce(() => mutation.promise)
      .mockImplementationOnce(() => next.promise)
      .mockResolvedValueOnce({ data: [persisted] });
    render(page(<CommercialPricingPage />));
    submitPreview();
    await screen.findByText("Proyecto: P-A · Cliente A · Casa A");
    fireEvent.change(screen.getByLabelText(t("pricing.reason")), { target: { value: "Reviewed" } });
    fireEvent.click(
      screen.getByRole("button", {
        name: t(action === "reject" ? "pricing.reject" : "pricing.apply"),
      }),
    );
    changeFinancialInput();
    submitPreview();
    await settle(mutation, persisted);
    expect(previewButton()).toBeDisabled();
    // The shown operation stays visible after the inputs moved — flagged
    // stale and non-applicable until the newer preview lands and replaces it.
    expect(screen.getByText("Proyecto: P-A · Cliente A · Casa A")).toBeInTheDocument();
    expect(screen.getByText(t("pricing.staleHint"))).toBeInTheDocument();
    await settle(next, result("B"));
    expect(screen.queryByText("Proyecto: P-A · Cliente A · Casa A")).not.toBeInTheDocument();
    expect(screen.getByText("Proyecto: P-B · Cliente B · Casa B")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: t("pricing.reload") }));
    await screen.findByRole("button", { name: t("pricing.review") });
    // The state filter option shares the chip's label — scope to the chip.
    const chip = document.querySelector(".operation-history__item .status-chip");
    expect(chip).toHaveTextContent(t(action === "reject" ? "pricing.rejected" : "pricing.applied"));
    expect(screen.getByText("Proyecto: P-B · Cliente B · Casa B")).toBeInTheDocument();
  },
);

it.each(["apply", "reject"] as const)(
  "stale %s failure cannot publish error or release newer busy",
  async (action) => {
    const mutation = deferred(),
      next = deferred();
    vi.mocked(apiMutator)
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: result("A", action === "reject" ? "PENDING" : "PREVIEW") })
      .mockImplementationOnce(() => mutation.promise)
      .mockImplementationOnce(() => next.promise);
    render(page(<CommercialPricingPage />));
    submitPreview();
    await screen.findByText("Proyecto: P-A · Cliente A · Casa A");
    fireEvent.change(screen.getByLabelText(t("pricing.reason")), { target: { value: "Reviewed" } });
    fireEvent.click(
      screen.getByRole("button", {
        name: t(action === "reject" ? "pricing.reject" : "pricing.apply"),
      }),
    );
    changeFinancialInput();
    submitPreview();
    await settle(mutation, null, true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(previewButton()).toBeDisabled();
    await settle(next, result("B"));
  },
);

it.each([false, true])(
  "reload A cannot publish or finish reload B (failure=%s)",
  async (failure) => {
    const a = deferred(),
      b = deferred();
    vi.mocked(apiMutator)
      .mockImplementationOnce(() => a.promise)
      .mockImplementationOnce(() => b.promise);
    render(page(<CommercialPricingPage />));
    fireEvent.click(screen.getByRole("button", { name: t("pricing.reload") }));
    changeFinancialInput();
    fireEvent.click(screen.getByRole("button", { name: t("pricing.reload") }));
    await settle(a, [result("A")], failure);
    expect(previewButton()).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(formatMoney("119", "CLP"))).not.toBeInTheDocument();
    await settle(b, [result("B")]);
    expect(screen.getByText(formatMoney("238", "CLP"))).toBeInTheDocument();
    expect(previewButton()).toBeEnabled();
  },
);

it("reload B remains authoritative after late reload A", async () => {
  const a = deferred(),
    b = deferred();
  vi.mocked(apiMutator)
    .mockImplementationOnce(() => a.promise)
    .mockImplementationOnce(() => b.promise);
  render(page(<CommercialPricingPage />));
  fireEvent.click(screen.getByRole("button", { name: t("pricing.reload") }));
  changeFinancialInput();
  fireEvent.click(screen.getByRole("button", { name: t("pricing.reload") }));
  await settle(b, [result("B")]);
  await settle(a, [result("A")]);
  expect(screen.getByText(formatMoney("238", "CLP"))).toBeInTheDocument();
  expect(screen.queryByText(formatMoney("119", "CLP"))).not.toBeInTheDocument();
});

it.each([false, true])(
  "StrictMode tenant replacement rejects late preview publication (failure=%s)",
  async (failure) => {
    const a = deferred(),
      b = deferred();
    vi.mocked(apiMutator)
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: [] })
      .mockImplementationOnce(() => a.promise)
      .mockImplementationOnce(() => b.promise);
    const view = render(
      page(
        <StrictMode>
          <CommercialPricingPage />
        </StrictMode>,
      ),
    );
    submitPreview();
    const signal = vi.mocked(apiMutator).mock.calls[0]?.[1].signal;
    identity.id = "tenant-b";
    view.rerender(
      page(
        <StrictMode>
          <CommercialPricingPage />
        </StrictMode>,
      ),
    );
    expect(signal?.aborted).toBe(true);
    submitPreview();
    await settle(a, result("A"), failure);
    expect(previewButton()).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await settle(b, result("B"));
    expect(screen.getByText("Proyecto: P-B · Cliente B · Casa B")).toBeInTheDocument();
    expect(previewButton()).toBeEnabled();
    view.unmount();
  },
);

it("unmount settles a rejected request without unhandled publication", async () => {
  const task = deferred();
  vi.mocked(apiMutator).mockImplementationOnce(() => task.promise);
  const view = render(page(<CommercialPricingPage />));
  submitPreview();
  view.unmount();
  await settle(task, null, true);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it.each(["reload", "apply", "reject"] as const)(
  "current %s failure is shown and releases busy",
  async (action) => {
    const task = deferred();
    vi.mocked(apiMutator).mockResolvedValueOnce({ data: [] });
    if (action !== "reload")
      vi.mocked(apiMutator).mockResolvedValueOnce({
        data: result("A", action === "reject" ? "PENDING" : "PREVIEW"),
      });
    vi.mocked(apiMutator).mockImplementationOnce(() => task.promise);
    render(page(<CommercialPricingPage />));
    if (action !== "reload") {
      submitPreview();
      await screen.findByText("Proyecto: P-A · Cliente A · Casa A");
      fireEvent.change(screen.getByLabelText(t("pricing.reason")), {
        target: { value: "Reviewed" },
      });
    } else {
      // The mount history load must finish first — the reload button is
      // disabled while a request is in flight.
      await waitFor(() => expect(previewButton()).toBeEnabled());
    }
    fireEvent.click(
      screen.getByRole("button", {
        name: t(
          action === "reload"
            ? "pricing.reload"
            : action === "reject"
              ? "pricing.reject"
              : "pricing.apply",
        ),
      }),
    );
    expect(previewButton()).toBeDisabled();
    await settle(task, null, true);
    expect(screen.getByRole("alert")).toHaveTextContent(
      t(action === "reload" ? "pricing.loadError" : "pricing.applyError"),
    );
    expect(previewButton()).toBeEnabled();
  },
);

function confirmCheckbox(): HTMLElement {
  return screen.getByLabelText(t("pricing.confirmDiscount"));
}
function previewBodies() {
  return vi
    .mocked(apiMutator)
    .mock.calls.filter((call) => String(call[0]).endsWith("preview/"))
    .map((call) => JSON.parse(String(call[1]?.body)) as Record<string, unknown>);
}
function operationApplyBodies() {
  return vi
    .mocked(apiMutator)
    .mock.calls.filter((call) => /operations\/.+\/apply\//.test(String(call[0])))
    .map((call) => JSON.parse(String(call[1]?.body)) as Record<string, unknown>);
}

it("a material request change voids the owner's discount attestation", async () => {
  const first = deferred(),
    second = deferred();
  vi.mocked(apiMutator)
    .mockImplementationOnce(() => first.promise)
    .mockImplementationOnce(() => second.promise);
  render(page(<CommercialPricingPage />));
  fireEvent.change(screen.getByLabelText(t("pricing.discount")), {
    target: { value: "0.25" },
  });
  fireEvent.click(confirmCheckbox());
  expect(confirmCheckbox()).toBeChecked();
  submitPreview();
  await settle(first, { ...result("A"), discount_pct: "0.25" });
  expect(previewBodies()[0]?.confirmed).toBe(true);
  fireEvent.change(screen.getByLabelText(t("pricing.currency")), {
    target: { value: "USD" },
  });
  expect(confirmCheckbox()).not.toBeChecked();
  submitPreview();
  expect(previewBodies()[1]?.confirmed).toBe(false);
  await settle(second, null, true);
  expect(screen.getByRole("alert")).toHaveTextContent(t("pricing.calculateError"));
});

it("changing the project voids the owner's discount attestation", () => {
  render(page(<CommercialPricingPage />));
  fireEvent.click(confirmCheckbox());
  expect(confirmCheckbox()).toBeChecked();
  fireEvent.change(screen.getByLabelText(t("pricing.projectId")), {
    target: { value: "another-project" },
  });
  expect(confirmCheckbox()).not.toBeChecked();
});

it("selecting a different persisted operation from history voids the attestation", async () => {
  const applyTask = deferred();
  vi.mocked(apiMutator)
    .mockResolvedValueOnce({
      data: [{ ...result("A"), discount_pct: "0.25" }],
    })
    .mockImplementationOnce(() => applyTask.promise);
  render(page(<CommercialPricingPage />));
  fireEvent.click(confirmCheckbox());
  expect(confirmCheckbox()).toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: t("pricing.reload") }));
  fireEvent.click(await screen.findByRole("button", { name: t("pricing.review") }));
  expect(confirmCheckbox()).not.toBeChecked();
  fireEvent.change(screen.getByLabelText(t("pricing.reason")), {
    target: { value: "Revisado sin nueva confirmación" },
  });
  fireEvent.click(screen.getByRole("button", { name: t("pricing.apply") }));
  await waitFor(() => expect(operationApplyBodies()).toHaveLength(1));
  expect(operationApplyBodies()[0]?.confirmed).toBe(false);
});

it("editing only the audit reason preserves the owner's attestation", () => {
  render(page(<CommercialPricingPage />));
  fireEvent.click(confirmCheckbox());
  fireEvent.change(screen.getByLabelText(t("pricing.reason")), {
    target: { value: "Motivo aclarado" },
  });
  expect(confirmCheckbox()).toBeChecked();
});

it.each(["apply", "reject"] as const)(
  "late %s success cannot replace preview B that already completed",
  async (action) => {
    const task = deferred();
    vi.mocked(apiMutator)
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: result("A", action === "reject" ? "PENDING" : "PREVIEW") })
      .mockImplementationOnce(() => task.promise)
      .mockResolvedValueOnce({ data: result("B") });
    render(page(<CommercialPricingPage />));
    submitPreview();
    await screen.findByText("Proyecto: P-A · Cliente A · Casa A");
    fireEvent.change(screen.getByLabelText(t("pricing.reason")), { target: { value: "Reviewed" } });
    fireEvent.click(
      screen.getByRole("button", {
        name: t(action === "reject" ? "pricing.reject" : "pricing.apply"),
      }),
    );
    changeFinancialInput();
    submitPreview();
    await screen.findByText("Proyecto: P-B · Cliente B · Casa B");
    await settle(task, result("A", action === "reject" ? "REJECTED" : "APPLIED"));
    expect(screen.getByText("Proyecto: P-B · Cliente B · Casa B")).toBeInTheDocument();
    expect(screen.queryByText("Proyecto: P-A · Cliente A · Casa A")).not.toBeInTheDocument();
    expect(previewButton()).toBeEnabled();
  },
);

const costListRow = {
  id: "9f4e5a00-0000-4000-8000-000000000001",
  supplier_name: "Proveedor Fixture",
  description: "",
  currency: "CLP",
  valid_from: "2026-09-01",
  valid_to: null,
  is_active: true,
};

function importRow(sku: string) {
  return { sku, unit: "M", unit_cost: "12.5" };
}

function importSection(): HTMLElement {
  return screen.getByRole("heading", { name: t("pricing.import") }).closest("section")!;
}
function importPreviewButton(): HTMLElement {
  return within(importSection()).getByRole("button", { name: t("pricing.previewImport") });
}
function importCalls() {
  return vi.mocked(apiMutator).mock.calls.filter((call) => String(call[0]).endsWith("import/"));
}
function adminCalls() {
  return vi.mocked(apiMutator).mock.calls.filter((call) => String(call[0]).includes("admin/"));
}
function applyCalls() {
  return importCalls().filter((call) => (call[1]?.body as FormData).get("apply") === "true");
}
function tenantCalls(organization: string) {
  return vi
    .mocked(apiMutator)
    .mock.calls.filter(
      (call) => (call[1]?.headers as Record<string, string>)["X-Organization-ID"] === organization,
    );
}
function mockImportRequests(tasks: Array<ReturnType<typeof deferred>>) {
  let index = 0;
  vi.mocked(apiMutator).mockImplementation((url) => {
    if (String(url).endsWith("import/")) {
      const task = tasks[index];
      index += 1;
      return task ? task.promise : Promise.reject(new Error("unexpected import request"));
    }
    return Promise.resolve({ data: { items: [costListRow] } });
  });
}
async function fillImportForm() {
  const section = importSection();
  await within(section).findByRole("option", { name: /Proveedor Fixture/ });
  fireEvent.change(within(section).getByLabelText(t("pricing.listId")), {
    target: { value: costListRow.id },
  });
  fireEvent.change(within(section).getByLabelText(t("pricing.file")), {
    target: { files: [new File(["SKU,Precio"], "lista.xlsx")] },
  });
  fireEvent.change(within(section).getByLabelText(t("pricing.reason")), {
    target: { value: "Carga inicial auditada" },
  });
}
function submitImport() {
  fireEvent.submit(importPreviewButton().closest("form")!);
}
function changeImportInput() {
  fireEvent.change(within(importSection()).getByLabelText(t("pricing.reason")), {
    target: { value: "Otro motivo auditado" },
  });
}
function confirmImportButton() {
  return within(importSection()).queryByRole("button", { name: t("pricing.confirmImport") });
}

it.each([false, true])(
  "stale import preview cannot publish after an input change (failure=%s)",
  async (failure) => {
    const a = deferred();
    mockImportRequests([a]);
    render(page(<PricingPage />));
    await fillImportForm();
    submitImport();
    expect(importPreviewButton()).toBeDisabled();
    changeImportInput();
    await settle(a, { items: [importRow("SKU-A")] }, failure);
    expect(importPreviewButton()).toBeEnabled();
    expect(within(importSection()).queryByRole("alert")).not.toBeInTheDocument();
    expect(within(importSection()).queryByText("SKU-A")).not.toBeInTheDocument();
    expect(confirmImportButton()).not.toBeInTheDocument();
  },
);

it("superseded import preview A cannot publish or release B's busy authority", async () => {
  const a = deferred(),
    b = deferred();
  mockImportRequests([a, b]);
  render(page(<PricingPage />));
  await fillImportForm();
  submitImport();
  submitImport();
  await settle(a, { items: [importRow("SKU-A")] });
  expect(importPreviewButton()).toBeDisabled();
  expect(within(importSection()).queryByText("SKU-A")).not.toBeInTheDocument();
  await settle(b, { items: [importRow("SKU-B")] });
  expect(within(importSection()).getByText("SKU-B")).toBeInTheDocument();
  expect(importPreviewButton()).toBeEnabled();
});

it.each([false, true])(
  "import preview B failure is published and late A cannot replace or clear it (late failure=%s)",
  async (lateFailure) => {
    const a = deferred(),
      b = deferred();
    mockImportRequests([a, b]);
    render(page(<PricingPage />));
    await fillImportForm();
    submitImport();
    submitImport();
    expect(importPreviewButton()).toBeDisabled();
    await settle(b, null, true);
    expect(within(importSection()).getByRole("alert")).toHaveTextContent(t("pricing.importError"));
    expect(importPreviewButton()).toBeEnabled();
    await settle(a, { items: [importRow("SKU-A")] }, lateFailure);
    expect(within(importSection()).getByRole("alert")).toHaveTextContent(t("pricing.importError"));
    expect(within(importSection()).queryByText("SKU-A")).not.toBeInTheDocument();
    expect(confirmImportButton()).not.toBeInTheDocument();
    expect(importPreviewButton()).toBeEnabled();
  },
);

it("import preview B remains authoritative after late A completes", async () => {
  const a = deferred(),
    b = deferred(),
    applied = deferred();
  mockImportRequests([a, b, applied]);
  render(page(<PricingPage />));
  await fillImportForm();
  submitImport();
  submitImport();
  await settle(b, { items: [importRow("SKU-B")] });
  expect(within(importSection()).getByText("SKU-B")).toBeInTheDocument();
  await settle(a, { items: [importRow("SKU-A")] });
  expect(within(importSection()).getByText("SKU-B")).toBeInTheDocument();
  expect(within(importSection()).queryByText("SKU-A")).not.toBeInTheDocument();
  fireEvent.click(confirmImportButton()!);
  expect(applyCalls()).toHaveLength(1);
  expect((applyCalls()[0]?.[1]?.body as FormData).get("apply")).toBe("true");
  await settle(applied, { items: [] });
});

it.each([false, true])(
  "stale durable apply releases busy, reloads once and never restores pending (failure=%s)",
  async (failure) => {
    const previewTask = deferred(),
      applyTask = deferred();
    mockImportRequests([previewTask, applyTask]);
    render(page(<PricingPage />));
    await fillImportForm();
    submitImport();
    await settle(previewTask, { items: [importRow("SKU-P")] });
    const confirm = within(importSection()).getByRole("button", {
      name: t("pricing.confirmImport"),
    });
    act(() => {
      confirm.click();
      confirm.click();
    });
    expect(importPreviewButton()).toBeDisabled();
    expect(within(importSection()).queryByText("SKU-P")).not.toBeInTheDocument();
    expect(confirmImportButton()).not.toBeInTheDocument();
    expect(applyCalls()).toHaveLength(1);
    expect((applyCalls()[0]?.[1]?.body as FormData).get("apply")).toBe("true");
    changeImportInput();
    expect(importPreviewButton()).toBeDisabled();
    await settle(applyTask, { items: [importRow("SKU-APPLIED")] }, failure);
    expect(importPreviewButton()).toBeEnabled();
    expect(within(importSection()).queryByText("SKU-APPLIED")).not.toBeInTheDocument();
    expect(within(importSection()).queryByRole("alert")).not.toBeInTheDocument();
    expect(confirmImportButton()).not.toBeInTheDocument();
    expect(importCalls()).toHaveLength(2);
    expect(applyCalls()).toHaveLength(1);
    expect(adminCalls()).toHaveLength(2);
  },
);

it.each([false, true])(
  "unmounted import request settles without publication (failure=%s)",
  async (failure) => {
    const task = deferred();
    mockImportRequests([task]);
    const view = render(page(<PricingPage />));
    await fillImportForm();
    submitImport();
    expect(importCalls()).toHaveLength(1);
    view.unmount();
    await settle(task, { items: [importRow("SKU-X")] }, failure);
    expect(view.container.innerHTML).toBe("");
    expect(importCalls()).toHaveLength(1);
  },
);

it.each([false, true])(
  "tenant replacement aborts an outstanding import apply and suppresses its reload (failure=%s)",
  async (failure) => {
    const previewTask = deferred(),
      applyTask = deferred();
    mockImportRequests([previewTask, applyTask]);
    const view = render(
      page(
        <StrictMode>
          <PricingPage />
        </StrictMode>,
      ),
    );
    await fillImportForm();
    submitImport();
    await settle(previewTask, { items: [importRow("SKU-T")] });
    fireEvent.click(confirmImportButton()!);
    const signal = applyCalls()[0]?.[1]?.signal;
    identity.id = "tenant-b";
    view.rerender(
      page(
        <StrictMode>
          <PricingPage />
        </StrictMode>,
      ),
    );
    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(tenantCalls("tenant-b").length).toBeGreaterThan(0));
    const oldTenantCalls = tenantCalls("tenant-a").length;
    await settle(applyTask, { items: [importRow("SKU-T")] }, failure);
    expect(tenantCalls("tenant-a")).toHaveLength(oldTenantCalls);
    expect(importCalls()).toHaveLength(2);
    expect(within(importSection()).queryByText("SKU-T")).not.toBeInTheDocument();
    expect(within(importSection()).queryByRole("alert")).not.toBeInTheDocument();
    view.unmount();
  },
);

it("lists human project identities before any pricing operation and submits only the internal ID", async () => {
  render(page(<CommercialPricingPage />));
  const option = await screen.findByRole("option", { name: "P-001 \u00b7 Cliente \u00b7 Casa" });
  expect(option).toHaveValue("project-a");
  expect(screen.queryByRole("option", { name: "project-a" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(t("pricing.projectId")), {
    target: { value: "project-a" },
  });
  submitPreview();
  expect(previewBodies()[0]?.project_id).toBe("project-a");
});

it("keeps FX authority available for a bound foreign-currency project quote", async () => {
  vi.mocked(apiMutator).mockImplementation((url) => {
    if (String(url).endsWith("admin/fx/"))
      return Promise.resolve({
        data: {
          items: [
            {
              id: "fx-snapshot-a",
              base_currency: "USD",
              quote_currency: "CLP",
              observed_rate: "950.00",
              observed_date: "2026-09-20",
            },
          ],
        },
      });
    return Promise.resolve({ data: { items: [] } });
  });
  render(
    <MemoryRouter initialEntries={["/projects/project-a/pricing"]}>
      <Routes>
        <Route path="/projects/:id/pricing" element={<CommercialPricingPage />} />
      </Routes>
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText(t("pricing.currency")), {
    target: { value: "USD" },
  });
  fireEvent.focus(screen.getByLabelText(t("pricing.fxId")));
  await screen.findByRole("option", { name: /USD→CLP/ });
  fireEvent.change(screen.getByLabelText(t("pricing.fxId")), {
    target: { value: "fx-snapshot-a" },
  });
  submitPreview();
  expect(previewBodies()[0]).toMatchObject({
    project_id: "project-a",
    currency: "USD",
    fx_snapshot_id: "fx-snapshot-a",
  });
});

it("shows unit price, per-line discount and the position thumbnail on the decision table", async () => {
  vi.mocked(apiMutator)
    .mockResolvedValueOnce({ data: { items: [] } })
    .mockResolvedValueOnce({
      data: {
        ...result("A"),
        project_id: "project-a",
        lines: [
          {
            position_index: 1,
            line_net: "90000",
            quantity: 3,
            unit_price: "31578.9474",
            discount_pct: "0.05",
          },
        ],
        cost_lines: [{ position_index: 1, line_cost: "70000" }],
      },
    });
  render(
    <MemoryRouter initialEntries={["/projects/project-a/pricing"]}>
      <Routes>
        <Route path="/projects/:id/pricing" element={<CommercialPricingPage />} />
      </Routes>
    </MemoryRouter>,
  );
  submitPreview();
  // line_net is a position TOTAL — unit price and discount sit next to it.
  await screen.findByText(t("pricing.unitPrice"));
  expect(screen.getByText(formatMoney("31578.9474", "CLP"))).toBeInTheDocument();
  expect(screen.getByText("−5,0 %")).toBeInTheDocument();
  expect(screen.getByText(formatMoney("90000", "CLP"))).toBeInTheDocument();
  // A legible drawing of the position, not a generic icon.
  expect(document.querySelector(".operation-lines__vano svg")).not.toBeNull();
});

it("keeps the positioned backend reason and links to the resolver surface", async () => {
  const failure = new ApiError(422, null);
  // The mocked ApiError has no fields — attach the payload explicitly.
  Object.assign(failure, {
    payload: {
      error: {
        code: "missing_glass_authority",
        detail: "P04 · no hay precio registrado para el vidrio seleccionado.",
      },
    },
  });
  vi.mocked(apiMutator)
    .mockResolvedValueOnce({ data: { items: [] } })
    .mockRejectedValueOnce(failure);
  render(page(<CommercialPricingPage />));
  submitPreview();
  await screen.findByRole("alert");
  expect(screen.getByRole("alert")).toHaveTextContent("P04 ·");
  expect(screen.getByRole("link", { name: t("pricing.fixInCostLists") })).toHaveAttribute(
    "href",
    "/pricing/cost-lists",
  );
});

it("P07 — band, cascade and delta render; out-of-band flips to request approval", async () => {
  identity.role = "ESTIMATOR";
  const operation = {
    ...result("A"),
    project_id: "project-a",
    margin_realized: "0.20",
    band: { min: "0.25", objective: "0.35", max: "0.60", state: "BELOW_MIN" },
    cascade: {
      rows: [
        { key: "materials", amount: "60", kind: "subtotal" },
        { key: "cost_total", amount: "80", kind: "subtotal" },
        { key: "net", amount: "100", kind: "subtotal" },
        { key: "gross", amount: "119", kind: "total" },
      ],
      positions: [],
      margin_realized: "0.20",
    },
    delta: {
      baseline_revision: "REV-A",
      baseline_net: "90",
      proposed_net: "100",
      net_delta: "10",
      drivers: [{ driver: "quantity", net_delta: "10", cost_delta: "8", net_after: "100" }],
    },
  };
  vi.mocked(apiMutator)
    .mockResolvedValueOnce({ data: [] })
    .mockResolvedValueOnce({ data: operation });
  render(page(<CommercialPricingPage />));
  submitPreview();
  expect(await screen.findByText(t("pricing.marginBand"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.band.BELOW_MIN"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.bandPendingHint"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.cascade"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.delta"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.deltaDriver.quantity"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.confirmBand"))).toBeInTheDocument();
  expect(screen.getByRole("button", { name: t("pricing.requestApproval") })).toBeInTheDocument();
  expect(screen.getByLabelText(t("pricing.reason"))).toHaveValue(t("pricing.bandReason"));
});

it("P07 — in-band keeps the calculate label and the owner sees no pending hint", async () => {
  const operation = {
    ...result("A"),
    project_id: "project-a",
    margin_realized: "0.20",
    band: { min: "0.10", objective: "0.35", max: "0.60", state: "IN_BAND" },
    cascade: null,
    delta: null,
  };
  vi.mocked(apiMutator)
    .mockResolvedValueOnce({ data: [] })
    .mockResolvedValueOnce({ data: operation });
  render(page(<CommercialPricingPage />));
  submitPreview();
  expect(await screen.findByText(t("pricing.marginBand"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.band.IN_BAND"))).toBeInTheDocument();
  expect(screen.queryByText(t("pricing.bandPendingHint"))).not.toBeInTheDocument();
  expect(previewButton()).toBeInTheDocument();
  expect(screen.getByText(t("pricing.noCascade"))).toBeInTheDocument();
  expect(screen.getByText(t("pricing.noDelta"))).toBeInTheDocument();
});
