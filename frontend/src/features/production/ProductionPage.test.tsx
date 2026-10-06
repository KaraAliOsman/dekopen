import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiMutator } from "../../api/apiMutator";
import { t } from "../../i18n/es-CL";
import { ProductionPage } from "./ProductionPage";
import { ConfirmProvider } from "../../ui";
import { ThemeProvider } from "../../theme/ThemeProvider";

const identity = vi.hoisted(() => ({ id: "tenant-a", role: "WORKSHOP_MANAGER" }));
vi.mock("../../auth/AuthSessionProvider", () => ({
  useAuthSession: () => ({ me: { active_organization: identity } }),
}));
vi.mock("../../api/apiMutator", () => ({ apiMutator: vi.fn(), ApiError: class extends Error {} }));

const mutator = apiMutator as ReturnType<typeof vi.fn>;

const order = {
  id: "order-1",
  order_code: "OT-REV-A-01",
  order_type: "WORKSHOP_OT",
  status: "RELEASED",
  position_id: "pos-1",
  quantity: 2,
  steps_done: 0,
  steps_total: 2,
  created_at: "2026-09-23T00:00:00Z",
};
const detail = {
  ...order,
  // Consuming steps show START only when a live cut plan exists.
  payload: { optimization: { plan: { bars: [] } } },
  steps: [
    {
      id: "step-1",
      sequence: 1,
      code: "CUT",
      label: "Corte",
      status: "READY",
      work_center_id: "wc-1",
      work_center_code: "CUT_SAW",
      started_at: null,
      finished_at: null,
      actor_id: null,
      note: null,
    },
    {
      id: "step-2",
      sequence: 2,
      code: "ASSEMBLE",
      label: "Armado",
      status: "READY",
      work_center_id: "wc-2",
      work_center_code: "ASSEMBLY_BENCH",
      started_at: null,
      finished_at: null,
      actor_id: null,
      note: null,
    },
  ],
  events: [
    {
      id: "ev-1",
      step_id: null,
      event: "WO_RELEASED",
      actor_id: "u-1",
      payload: {},
      created_at: "2026-09-23T00:00:00Z",
    },
  ],
};

const stationQueue = {
  stations: [
    {
      code: "CUT",
      label: "Corte",
      pending: 1,
      in_progress: 0,
      blocked: 0,
      entries: [
        {
          step_id: "step-1",
          order_id: "order-1",
          order_code: "OT-REV-A-01",
          sequence: 1,
          label: "Corte",
          status: "READY",
          is_next: true,
        },
      ],
    },
  ],
};

function respond(url: string): { data: unknown; status: number } {
  if (url === "/api/v1/production/prep/") return { data: { versions: [] }, status: 200 };
  if (url === "/api/v1/production/orders/") return { data: { orders: [order] }, status: 200 };
  if (url === "/api/v1/production/station-queue/") return { data: stationQueue, status: 200 };
  if (url === `/api/v1/production/orders/${order.id}/`) return { data: detail, status: 200 };
  return { data: detail, status: 200 };
}

describe("ProductionPage", () => {
  beforeEach(() => {
    mutator.mockReset();
    mutator.mockImplementation(async (url: string) => respond(url));
    identity.role = "WORKSHOP_MANAGER";
  });
  afterEach(cleanup);

  it("lists work orders and opens the detail with steps", async () => {
    render(
      <MemoryRouter initialEntries={["/production"]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    const orderButton = await screen.findByRole("button", { name: /OT-REV-A-01/ });
    fireEvent.click(orderButton);
    await waitFor(() => expect(screen.getAllByText("Corte").length).toBeGreaterThan(0));
    expect(screen.getByText("Armado")).toBeTruthy();
    // La barra «Siguiente» del resumen ofrece START solo en el paso abierto;
    // abrir el paso en el drawer lo duplica en el panel de acciones.
    expect(screen.getAllByRole("button", { name: t("production.actionStart") })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /Corte/ }));
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: t("production.actionStart") }).length,
      ).toBeGreaterThanOrEqual(2),
    );
  });

  it("starts a step through the transition endpoint", async () => {
    render(
      <MemoryRouter initialEntries={[`/production?order=${order.id}`]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    const start = (await screen.findAllByRole("button", { name: t("production.actionStart") }))[0];
    if (!start) throw new Error("missing start button");
    fireEvent.click(start);
    await waitFor(() =>
      expect(mutator).toHaveBeenCalledWith(
        "/api/v1/production/steps/step-1/transition/",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("gives estimators a read-only view", async () => {
    identity.role = "ESTIMATOR";
    render(
      <MemoryRouter initialEntries={[`/production?order=${order.id}`]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("OT-REV-A-01")).toBeTruthy());
    // The estimator sees blockers and shortages, never step controls.
    expect(screen.queryByText(t("production.denied"))).toBeNull();
    expect(screen.queryByRole("button", { name: t("production.actionStart") })).toBeNull();
  });

  it("cancels a work order after a danger prompt", async () => {
    render(
      <MemoryRouter initialEntries={[`/production?order=${order.id}`]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: t("production.cancelButton") }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox"), {
      target: { value: "cliente canceló" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: t("production.cancelConfirm") }));
    await waitFor(() =>
      expect(mutator).toHaveBeenCalledWith(
        `/api/v1/production/orders/${order.id}/cancel/`,
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ confirmed: true, note: "cliente canceló" }),
        }),
      ),
    );
  });

  it("offers a material recheck on a shortage order", async () => {
    mutator.mockImplementation(async (url: string) => {
      if (url === "/api/v1/production/prep/") return { data: { versions: [] }, status: 200 };
      if (url === "/api/v1/production/orders/") return { data: { orders: [order] }, status: 200 };
      return { data: { ...detail, shortage: 2 }, status: 200 };
    });
    render(
      <MemoryRouter initialEntries={[`/production?order=${order.id}`]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: t("production.materialRecheck") }));
    await waitFor(() =>
      expect(mutator).toHaveBeenCalledWith(
        `/api/v1/production/orders/${order.id}/material-recheck/`,
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("hides write affordances on a cancelled order", async () => {
    mutator.mockImplementation(async (url: string) => {
      if (url === "/api/v1/production/prep/") return { data: { versions: [] }, status: 200 };
      if (url === "/api/v1/production/orders/") return { data: { orders: [order] }, status: 200 };
      return { data: { ...detail, status: "CANCELLED" }, status: 200 };
    });
    render(
      <MemoryRouter initialEntries={[`/production?order=${order.id}`]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("OT-REV-A-01")).toBeTruthy());
    expect(screen.queryByRole("button", { name: t("production.cancelButton") })).toBeNull();
    expect(screen.queryByRole("button", { name: t("production.actionStart") })).toBeNull();
    expect(screen.getAllByText(t("production.orderCancelled")).length).toBeGreaterThan(0);
  });

  it("hides UNBLOCK from operators but shows it to managers", async () => {
    mutator.mockImplementation(async (url: string) => {
      if (url === "/api/v1/production/prep/") return { data: { versions: [] }, status: 200 };
      if (url === "/api/v1/production/orders/") return { data: { orders: [order] }, status: 200 };
      if (url === "/api/v1/production/station-queue/") return { data: stationQueue, status: 200 };
      return {
        data: {
          ...detail,
          status: "HOLD",
          steps: [{ ...detail.steps[0], status: "BLOCKED" }, detail.steps[1]],
        },
        status: 200,
      };
    });
    identity.role = "OPERATOR";
    // El operario aterriza en su superficie: estación fijada → solo la cola
    // de esa estación; Desbloquear es acción de supervisor y no existe ahí.
    localStorage.setItem("dekopen.operatorStation.", "CUT");
    const { unmount } = render(
      <MemoryRouter initialEntries={[`/production?order=${order.id}`]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getAllByText("OT-REV-A-01").length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: t("production.actionUnblock") })).toBeNull();
    unmount();
    localStorage.removeItem("dekopen.operatorStation.");
    identity.role = "WORKSHOP_MANAGER";
    render(
      <MemoryRouter initialEntries={[`/production?order=${order.id}`]}>
        <ConfirmProvider>
          <ThemeProvider>
            <ProductionPage />
          </ThemeProvider>
        </ConfirmProvider>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: t("production.actionUnblock") }).length,
      ).toBeGreaterThan(0),
    );
  });
});
