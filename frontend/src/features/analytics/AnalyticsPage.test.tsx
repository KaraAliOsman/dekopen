import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiMutator } from "../../api/apiMutator";
import { AnalyticsPage } from "./AnalyticsPage";

const identity = vi.hoisted(() => ({ id: "tenant-a", role: "OWNER" }));
vi.mock("../../auth/AuthSessionProvider", () => ({
  useAuthSession: () => ({ me: { active_organization: identity } }),
}));
vi.mock("../../api/apiMutator", () => ({
  apiMutator: vi.fn(),
  apiFetchBlob: vi.fn(async () => ({ blob: new Blob(["a\n1"]), filename: "x.csv" })),
  ApiError: class extends Error {
    status: number;
    constructor(status: number, _data: unknown) {
      super(String(status));
      this.status = status;
    }
  },
}));

const mutator = apiMutator as ReturnType<typeof vi.fn>;

const DEFS = {
  conversion_pct: {
    label: "Conversión",
    formula: "aprobadas / emitidas",
    source: "sales_quotes",
    period: "emitida en el período",
  },
  real_margin_pct: {
    label: "Margen real",
    formula: "(neto − costo real) / neto",
    source: "orders + cost_movements",
    period: "entregada en el período",
  },
};

const overview = (financial: boolean) => ({
  schema: "dekopen.analytics.overview.v1",
  period: { desde: "2027-09-01", hasta: "2027-09-30" },
  definitions: DEFS,
  sales: {
    financial,
    metrics: {
      emitted: 10,
      approved: 4,
      declined: 1,
      conversion_pct: { value: 40, n: 10, cause: null },
      pipeline_net: { value: 150000, n: 3, cause: null },
    },
    pipeline_by_phase: [{ phase: "PENDIENTE", net: 90000 }],
    by_typology: [{ typology: "VENTANA", emitted: 6, decided: 4, approved: 3, conversion_pct: 50 }],
    rejection_reasons: [],
    rows: [{ code: "COT-1", client: "Cliente A", state: "APPROVED", net: 120000 }],
  },
  margins: {
    financial,
    metrics: {
      obras: 1,
      quoted_avg_margin_pct: { value: 40, n: 1, cause: null },
      real_avg_margin_pct: { value: 18, n: 1, cause: null },
      deviation_pp: { value: -22, n: 1, cause: null },
    },
    by_typology: [{ typology: "VENTANA", obras: 1, avg_dev_pct: -22 }],
    obras: [
      {
        project_id: "p-1",
        code: "PA-1",
        project_name: "Obra Uno",
        state: "EN_PRODUCCION",
        quoted_margin_pct: 40,
        real_margin_pct: 18,
        deviation_pp: -22,
        real_missing: ["horas"],
      },
    ],
  },
  production: {
    financial,
    metrics: {
      ots_total: 3,
      ots_remakes: 1,
      merma_real_mm: { value: 850, n: 3, cause: null },
      aprovechamiento_pct: { value: 92, n: 3, cause: null },
      ot_punctuality: { a_tiempo: 2, atrasadas: 1, sin_plazo: 0 },
    },
    ot_waste: [{ order_id: "ot-1", order_code: "OT-1", merma_real_mm: 850 }],
    station_times: [{ code: "CUT", label: "Corte", avg_hours: 1.5, steps: 3 }],
    remakes: [{ order_id: "ot-2", order_code: "OT-2-R" }],
  },
  field: {
    financial,
    metrics: {
      deliveries: 2,
      deliveries_on_time_pct: { value: 100, n: 2, cause: null },
      installations: 2,
      incidents: 1,
      incidents_open: 0,
      warranties_open: 1,
      warranties_expiring: 0,
    },
    deliveries: [{ delivery_id: "d-1", a_tiempo: true }],
    incidents_by_kind: [{ kind: "DAMAGE", n: 1 }],
    incidents_by_typology: [],
    incidents: [{ id: "i-1", kind: "DAMAGE" }],
    warranties: [{ id: "w-1", expira: "2028-01-01" }],
  },
});

const breakdown = {
  project: { id: "p-1", code: "PA-1", name: "Obra Uno" },
  quoted: {
    net: 100000,
    margin_pct: 40,
    materials: 30000,
    labor: 20000,
    install: 15000,
    discount_pct: 10,
  },
  real: { total: 82000, material: 55000, hours: 3, missing: ["tarifa horaria no configurada"] },
  causes: [
    { key: "material", amount: 25000 },
    { key: "horas", amount: null },
    { key: "remake", amount: 0 },
  ],
  ots: [{ id: "ot-1", code: "OT-1", status: "RELEASED", is_remake: false }],
};

function respond(url: string, financial: boolean) {
  if (url.startsWith("/api/v1/analytics/overview/")) {
    return { data: overview(financial), status: 200 };
  }
  if (url.startsWith("/api/v1/analytics/margin-breakdown/")) {
    return { data: breakdown, status: 200 };
  }
  return { data: {}, status: 200 };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/analitica"]}>
      <QueryClientProvider client={client}>
        <AnalyticsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("AnalyticsPage", () => {
  beforeEach(() => {
    mutator.mockReset();
    mutator.mockImplementation(async (url: string) => respond(url, true));
    identity.role = "OWNER";
  });
  afterEach(cleanup);

  it("muestra tarjetas solo con datos, barras por tipología y la tabla de obras", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText("40,0 %").length).toBeGreaterThan(0));
    expect(screen.getByText("Cotizaciones emitidas")).toBeTruthy();
    expect(screen.getByText("Obra Uno")).toBeTruthy();
    expect(screen.getAllByText("VENTANA").length).toBeGreaterThan(0);
    // Puntualidad con valor solo donde la fuente lo declara.
    expect(screen.getByText("A tiempo")).toBeTruthy();
  });

  it("abre el desglose de margen con causas y enlaces de origen", async () => {
    renderPage();
    const button = await screen.findByRole("button", { name: "Desglose" });
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText("Causas de la diferencia")).toBeTruthy());
    expect(screen.getAllByText("Material vs. cotizado").length).toBeGreaterThan(0);
    expect(screen.getByText(/tarifa horaria no configurada/)).toBeTruthy();
  });

  it("oculta montos cuando el rol no tiene acceso financiero", async () => {
    mutator.mockImplementation(async (url: string) => respond(url, false));
    renderPage();
    await screen.findByText(/no los montos/i);
    expect(screen.getByText("Cotizaciones emitidas")).toBeTruthy();
  });

  it("muestra el estado de acceso denegado para un rol sin lectura", async () => {
    identity.role = "ESTIMATOR";
    renderPage();
    await screen.findByText("Tu rol no abre la analítica de la organización.");
    expect(screen.queryByText("Cotizaciones emitidas")).toBeNull();
  });
});
