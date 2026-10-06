import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { apiMutator } from "../../api/apiMutator";
import { t } from "../../i18n/es-CL";
import { ConfirmProvider } from "../../ui";
import { PurchasingPage } from "./PurchasingPage";

const identity = vi.hoisted(() => ({ id: "tenant-a", role: "WORKSHOP_MANAGER" }));
vi.mock("../../auth/AuthSessionProvider", () => ({
  useAuthSession: () => ({ me: { active_organization: identity } }),
}));
vi.mock("../../api/apiMutator", () => ({ apiMutator: vi.fn(), ApiError: class extends Error {} }));

const versionItem = {
  id: "version-a",
  project_id: "project-a",
  revision_code: "REV-A",
  bom_hash: "a".repeat(64),
  snapshot_sha256: "b".repeat(64),
  emitted_at: "2026-09-14T00:00:00Z",
};
const glassRequirement = {
  id: "req-glass",
  requirement_key: "c".repeat(64),
  order_type: "SUPPLIER_GLASS_PO",
  category: "GLASS_UNIT",
  technical_skus: ["DVE-4-12-4"],
  purchasing_sku: "DVE-4-12-4",
  physical_stock_identity: null,
  unit: "EA",
  quantity: "4",
  specification: {},
  source_trace: ["5".repeat(64), "6".repeat(64)],
  source_trace_labels: ["I-01", null],
};
const profileRequirement = {
  id: "req-profile",
  requirement_key: "d".repeat(64),
  order_type: "SUPPLIER_PROFILE_PO",
  category: "PROFILE_BAR",
  technical_skus: ["ALU-60"],
  purchasing_sku: "ALU-60",
  physical_stock_identity: "ALU-60/WHITE/6000",
  unit: "BAR",
  quantity: "7",
  specification: {},
  source_trace: ["7".repeat(64)],
};
const eligibility = {
  id: "elig-glass",
  order_type: "SUPPLIER_GLASS_PO",
  supplier_identity: "supplier-glass",
  supplier_name: "Vidrios SPA",
  eligible_requirement_keys: [glassRequirement.requirement_key],
  version: 1,
};
const foreignEligibility = {
  id: "elig-profile",
  order_type: "SUPPLIER_PROFILE_PO",
  supplier_identity: "supplier-profile",
  supplier_name: "Perfiles LTDA",
  eligible_requirement_keys: [profileRequirement.requirement_key],
  version: 1,
};

function state(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      versions: [versionItem],
      version: { ...versionItem, project_code: "P-001", production_allowed: true },
      requirements: [glassRequirement, profileRequirement],
      eligibilities: [eligibility, foreignEligibility],
      allocations: [],
      orders: [],
      blockers: [],
      ...overrides,
    },
  };
}

function mockState(overrides: Record<string, unknown> = {}) {
  vi.mocked(apiMutator).mockImplementation((url) => {
    if (String(url).endsWith("purchasing/versions/"))
      return Promise.resolve({ data: { versions: [versionItem] } });
    if (String(url).endsWith("purchasing/orders/"))
      return Promise.resolve({
        data: {
          orders: [
            {
              id: "order-idx-1",
              order_code: "OC-HW-7",
              order_type: "SUPPLIER_HARDWARE_PO",
              status: "SENT",
              supplier_identity: "76.1-2",
              supplier_name: "Vorne SPA",
              expected_at: "2026-10-01",
              sent_at: null,
              created_at: "2026-09-01T00:00:00Z",
              project_id: "project-a",
              project_code: "P-002",
              project_version_id: versionItem.id,
              revision_code: "REV-A",
              line_count: "3",
              total_qty: "10",
              good_qty: "2",
              outstanding_qty: "8",
            },
            {
              id: "order-idx-2",
              order_code: "OC-GL-2",
              order_type: "SUPPLIER_GLASS_PO",
              status: "DRAFT",
              supplier_identity: null,
              supplier_name: "Vidrios SPA",
              expected_at: null,
              sent_at: null,
              created_at: "2026-09-02T00:00:00Z",
              project_id: "project-a",
              project_code: "P-002",
              project_version_id: versionItem.id,
              revision_code: "REV-A",
              line_count: "1",
              total_qty: "4",
              good_qty: "0",
              outstanding_qty: "4",
            },
          ],
        },
      });
    if (String(url).includes(`purchasing/versions/${versionItem.id}/`))
      return Promise.resolve(state(overrides));
    return Promise.resolve({ data: {} });
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ConfirmProvider>
        <PurchasingPage />
      </ConfirmProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  identity.id = "tenant-a";
  identity.role = "WORKSHOP_MANAGER";
  vi.mocked(apiMutator).mockReset();
});
afterEach(cleanup);

it.each(["INSTALLER"])("denies S19 to %s without fetching", (role) => {
  identity.role = role;
  renderPage();
  expect(screen.getByRole("alert")).toHaveTextContent(t("purchasing.denied"));
  expect(apiMutator).not.toHaveBeenCalled();
});

it("opens read-only to ESTIMATOR: coverage visible, no write controls", async () => {
  identity.role = "ESTIMATOR";
  mockState();
  renderPage();
  await screen.findByText("4 unidades");
  expect(
    screen.queryByRole("combobox", { name: t("purchasing.chooseSupplier") }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});

it("renders immutable quantities without editable inputs", async () => {
  mockState();
  renderPage();
  const cell = await screen.findByText("4 unidades");
  expect(cell.closest("td")).not.toContainHTML("input");
  expect(screen.getByText("7 barras")).toBeInTheDocument();
});

it("offers only suppliers eligible for the requirement key", async () => {
  mockState();
  renderPage();
  const row = (await screen.findByText("4 unidades")).closest("tr")!;
  const select = within(row).getByLabelText(t("purchasing.chooseSupplier"));
  const options = within(select)
    .getAllByRole("option")
    .map((item) => item.textContent);
  expect(options.join()).toContain("Vidrios SPA");
  expect(options.join()).not.toContain("Perfiles LTDA");
});

it("keeps batch confirmation disabled until the type is fully allocated and attested", async () => {
  mockState();
  renderPage();
  const section = (await screen.findByText("4 unidades")).closest("section")!;
  const confirm = within(section).getByRole("button", { name: t("purchasing.confirm") });
  expect(confirm).toBeDisabled();
  const checkbox = within(section).getByLabelText(t("purchasing.confirmCheckbox"));
  expect(checkbox).toBeDisabled();
});

it("confirms an allocated type only after explicit attestation", async () => {
  mockState({
    allocations: [
      {
        id: "alloc-1",
        requirement_line_id: "req-glass",
        supplier_eligibility_id: "elig-glass",
        order_type: "SUPPLIER_GLASS_PO",
      },
    ],
  });
  renderPage();
  const section = (await screen.findByText("4 unidades")).closest("section")!;
  const confirm = within(section).getByRole("button", { name: t("purchasing.confirm") });
  expect(confirm).toBeDisabled();
  fireEvent.click(within(section).getByLabelText(t("purchasing.confirmCheckbox")));
  expect(confirm).toBeEnabled();
  fireEvent.submit(confirm.closest("form")!);
  await waitFor(() =>
    expect(apiMutator).toHaveBeenCalledWith(
      `/api/v1/purchasing/versions/${versionItem.id}/confirm/`,
      expect.objectContaining({
        body: JSON.stringify({ order_type: "SUPPLIER_GLASS_PO", confirmed: true }),
      }),
    ),
  );
});

it("sends a draft order only after explicit attestation", async () => {
  mockState({
    orders: [
      {
        id: "order-1",
        order_code: "OC-GLASS-1",
        order_type: "SUPPLIER_GLASS_PO",
        status: "DRAFT",
        supplier_name: "Vidrios SPA",
        order_snapshot_hash: "e".repeat(64),
      },
    ],
  });
  renderPage();
  const orderCard = (await screen.findByText("OC-GLASS-1")).closest("article")!;
  const send = within(orderCard).getByRole("button", { name: t("purchasing.send") });
  expect(send).toBeDisabled();
  fireEvent.click(within(orderCard).getByLabelText(t("purchasing.sendCheckbox")));
  expect(send).toBeEnabled();
  fireEvent.submit(send.closest("form")!);
  await waitFor(() =>
    expect(apiMutator).toHaveBeenCalledWith(
      "/api/v1/purchasing/orders/order-1/send/",
      expect.objectContaining({
        body: JSON.stringify({ confirmed: true, expected_at: null, sent_to: null }),
      }),
    ),
  );
});

it("renders trace labels with a short digest fallback for unlabelled ids", async () => {
  mockState();
  renderPage();
  const cell = (await screen.findByText("4 unidades")).closest("tr")!;
  // "5".repeat(64) carries the I-01 label; "6".repeat(64) has none and renders
  // as a technical digest (#últimos4) — never char-by-char enumeration or a
  // hex fragment.
  expect(within(cell).getByText("I-01")).toBeInTheDocument();
  expect(within(cell).getByText("#6666")).toBeInTheDocument();
  expect(within(cell).queryByText(/^0=/)).not.toBeInTheDocument();
});

it("shows workshop managers only document actions the backend authorizes", async () => {
  mockState({
    orders: [
      {
        id: "order-1",
        order_code: "OC-GLASS-1",
        order_type: "SUPPLIER_GLASS_PO",
        status: "SENT",
        supplier_name: "Vidrios SPA",
        order_snapshot_hash: "e".repeat(64),
      },
    ],
  });
  renderPage();
  await screen.findByText("4 unidades");
  for (const key of ["purchasing.doc03", "purchasing.doc05", "purchasing.doc06"] as const)
    expect(screen.getByText(t(key))).toBeInTheDocument();
  expect(screen.getByText(t("purchasing.doc02"))).toBeInTheDocument();
  expect(screen.queryByText(t("purchasing.doc01"))).not.toBeInTheDocument();
  expect(screen.queryByText(t("purchasing.doc07"))).not.toBeInTheDocument();
});

it("shows the owner every document action including DOC-01 and DOC-07", async () => {
  identity.role = "OWNER";
  mockState();
  renderPage();
  await screen.findByText("4 unidades");
  for (const key of [
    "purchasing.doc01",
    "purchasing.doc03",
    "purchasing.doc05",
    "purchasing.doc06",
    "purchasing.doc07",
  ] as const)
    expect(screen.getByText(t(key))).toBeInTheDocument();
});

it("surfaces a load failure without fabricating requirements", async () => {
  vi.mocked(apiMutator).mockRejectedValue(new Error("network"));
  renderPage();
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(t("purchasing.loadError")),
  );
  expect(screen.queryByText("4 unidades")).not.toBeInTheDocument();
});

it("drops the stale revision when the newly selected version fails to load", async () => {
  const other = { ...versionItem, id: "version-b", revision_code: "REV-B" };
  vi.mocked(apiMutator).mockImplementation((url) => {
    const path = String(url);
    if (path.endsWith("purchasing/versions/"))
      return Promise.resolve({ data: { versions: [versionItem, other] } });
    if (path.includes(`purchasing/versions/${versionItem.id}/`)) return Promise.resolve(state());
    if (path.includes(`purchasing/versions/${other.id}/`))
      return Promise.reject(new Error("unavailable"));
    return Promise.resolve({ data: {} });
  });
  renderPage();
  await screen.findByText("P-001");
  fireEvent.change(screen.getByLabelText(t("purchasing.chooseVersion")), {
    target: { value: other.id },
  });
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(t("purchasing.loadError")),
  );
  expect(screen.queryByText("P-001")).not.toBeInTheDocument();
  expect(screen.queryByText("4 unidades")).not.toBeInTheDocument();
  expect(screen.queryByText(t("purchasing.doc03"))).not.toBeInTheDocument();
});

it("submits eligibility keys in canonical order even when visual order differs", async () => {
  const lowKey = "a".repeat(64);
  const laterVisualRequirement = {
    ...glassRequirement,
    id: "req-glass-2",
    requirement_key: lowKey,
    purchasing_sku: "DVE-6-12-6",
    quantity: "9",
  };
  // Visual/table order is [c…, a…] — intentionally NOT lexicographic.
  mockState({
    requirements: [glassRequirement, laterVisualRequirement, profileRequirement],
    eligibilities: [],
  });
  renderPage();
  const section = (await screen.findByText("4 unidades")).closest("section")!;
  const form = section.querySelector("details.purchasing-eligibility form")!;
  expect(form).not.toBeNull();
  fireEvent.change(form.querySelector('input[name="supplier_identity"]')!, {
    target: { value: "supplier-glass-2" },
  });
  fireEvent.change(form.querySelector('input[name="supplier_name"]')!, {
    target: { value: "Vidrios Segunda" },
  });
  fireEvent.change(form.querySelector('input[name="basis"]')!, {
    target: { value: "Selección humana explícita" },
  });
  fireEvent.submit(form);
  await waitFor(() =>
    expect(apiMutator).toHaveBeenCalledWith(
      `/api/v1/purchasing/versions/${versionItem.id}/eligibilities/`,
      expect.objectContaining({ body: expect.any(String) }),
    ),
  );
  const call = vi
    .mocked(apiMutator)
    .mock.calls.find((item) => String(item[0]).includes("eligibilities"))!;
  const body = JSON.parse(String((call[1] as { body: string }).body));
  expect(body.eligible_requirement_keys).toEqual([lowKey, glassRequirement.requirement_key]);
  expect(body.eligible_requirement_keys).toEqual([...body.eligible_requirement_keys].sort());
});

it("maps backend blocker codes to actionable labels", async () => {
  mockState({
    blockers: [
      { order_type: "SUPPLIER_PROFILE_PO", code: "SUPPLIER_ELIGIBILITY_REQUIRED" },
      {
        order_type: "SUPPLIER_GLASS_PO",
        code: "ALLOCATION_REQUIRED",
        requirement_keys: [glassRequirement.requirement_key],
      },
    ],
  });
  renderPage();
  const section = await screen.findByRole("heading", {
    name: t("purchasing.blockers"),
  });
  const list = section.closest("section")!;
  expect(
    within(list).getByText(t("purchasing.blockerEligibilityRequired"), {
      exact: false,
    }),
  ).toBeInTheDocument();
  expect(
    within(list).getByText(t("purchasing.blockerAllocationRequired"), {
      exact: false,
    }),
  ).toBeInTheDocument();
});

it("lists org-wide orders with supplier, expected date and outstanding, filtered by status", async () => {
  mockState();
  renderPage();
  const index = (await screen.findByText(t("purchasing.indexTitle"))).closest("section")!;
  expect(within(index).getByText("OC-HW-7")).toBeInTheDocument();
  expect(within(index).getByText("OC-GL-2")).toBeInTheDocument();
  expect(within(index).getByText("Vorne SPA")).toBeInTheDocument();
  expect(within(index).getByText("2026-10-01")).toBeInTheDocument();
  expect(within(index).getByText("8")).toBeInTheDocument();
  fireEvent.click(within(index).getByRole("button", { name: t("purchasing.sent") }));
  expect(within(index).getByText("OC-HW-7")).toBeInTheDocument();
  expect(within(index).queryByText("OC-GL-2")).not.toBeInTheDocument();
});
