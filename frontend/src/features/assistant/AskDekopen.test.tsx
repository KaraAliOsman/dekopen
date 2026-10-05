import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { aiAgent, aiAsk, aiJobOutcomeCreate, aiJobRetrieve } from "../../api/generated/dekopen";
import { AskDekopen } from "./AskDekopen";
import {
  AssistantSurfaceProvider,
  routeContext,
  useRegisterDesignOpsBridge,
} from "./assistantContext";
import type { DesignOp } from "../commands/types";

vi.mock("../../api/generated/dekopen", () => ({
  aiAsk: vi.fn(),
  aiAgent: vi.fn(),
  aiJobRetrieve: vi.fn(),
  aiJobOutcomeCreate: vi.fn(),
}));
const askMock = vi.mocked(aiAsk);
const agentMock = vi.mocked(aiAgent);
const jobMock = vi.mocked(aiJobRetrieve);
vi.mocked(aiJobOutcomeCreate).mockResolvedValue({
  status: 200,
  headers: new Headers(),
  data: {},
} as never);

function successResponse() {
  return {
    status: 200,
    headers: new Headers(),
    data: {
      audit_id: "a1",
      model: "mock-context-1",
      credits_debited: 2,
      answer: "Tienes 3 proyectos activos.",
      actions: [{ kind: "navigate", path: "/projects", label: "Ver proyectos" }],
      warnings: [],
    },
  };
}

function Providers({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

function renderDock(initialPath = "/dashboard") {
  return render(
    <Providers>
      <MemoryRouter initialEntries={[initialPath]}>
        <AssistantSurfaceProvider>
          <Routes>
            <Route path="*" element={<AskDekopen organizationId="org-1" />} />
          </Routes>
        </AssistantSurfaceProvider>
      </MemoryRouter>
    </Providers>,
  );
}

describe("routeContext", () => {
  it("maps entity routes to their required refs", () => {
    expect(routeContext("/projects")).toEqual({ surface: "projects", refs: {} });
    expect(routeContext("/projects/abc-1")).toEqual({
      surface: "project",
      refs: { project_id: "abc-1" },
    });
    expect(routeContext("/projects/p1/positions/pos-9/edit")).toEqual({
      surface: "position",
      refs: { project_id: "p1", position_id: "pos-9" },
    });
    expect(routeContext("/settings/billing")).toEqual({ surface: "settings", refs: {} });
    expect(routeContext("/production")).toEqual({ surface: "production", refs: {} });
  });
});

describe("AskDekopen", () => {
  beforeEach(() => askMock.mockReset());

  it("answers inside the route's typed surface and navigates on actions", async () => {
    askMock.mockResolvedValue(successResponse() as never);
    renderDock("/projects/abc-1");
    fireEvent.click(screen.getByRole("button", { name: /Abrir el asistente/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "¿Qué ves aquí?" } });
    fireEvent.click(screen.getByRole("button", { name: /Enviar/i }));
    await waitFor(() => expect(askMock).toHaveBeenCalledTimes(1));
    const [body, options] = askMock.mock.calls[0] ?? [];
    expect(body).toMatchObject({
      surface: "project",
      refs: { project_id: "abc-1" },
      question: "¿Qué ves aquí?",
    });
    expect(new Headers(options?.headers).get("X-Organization-ID")).toBe("org-1");
    expect(await screen.findByText("Tienes 3 proyectos activos.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ver proyectos" })).toBeTruthy();
  });

  it("drops the in-flight answer when the surface changes", async () => {
    let resolve!: (value: ReturnType<typeof successResponse>) => void;
    askMock.mockReturnValue(new Promise((r) => (resolve = r)) as never);
    const view = render(
      <Providers>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <AssistantSurfaceProvider>
            <Routes>
              <Route path="*" element={<AskDekopen organizationId="org-1" />} />
            </Routes>
          </AssistantSurfaceProvider>
        </MemoryRouter>
      </Providers>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Abrir el asistente/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hola" } });
    fireEvent.click(screen.getByRole("button", { name: /Enviar/i }));
    expect(askMock).toHaveBeenCalledTimes(1);
    // Simulate a route change by unmounting/remounting on a different surface.
    view.unmount();
    resolve(successResponse());
    await waitFor(() => expect(screen.queryByText("Tienes 3 proyectos activos.")).toBeNull());
  });

  it("shows the API error detail when the ask fails", async () => {
    askMock.mockResolvedValue({
      status: 400,
      headers: new Headers(),
      data: { error: { detail: "contexto inválido" } },
    } as never);
    renderDock();
    fireEvent.click(screen.getByRole("button", { name: /Abrir el asistente/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "algo" } });
    fireEvent.submit(screen.getByRole("button", { name: /Enviar/i }).closest("form")!);
    expect(await screen.findByText("contexto inválido")).toBeTruthy();
  });
});

/** The agent now answers 202 + a queued job; the dock polls the job detail
 * until the worker settles the round and renders the stored `result`. */
function agentJob(over: Record<string, unknown> = {}) {
  return {
    status: 202,
    headers: new Headers(),
    data: { job_id: "job-1", state: "QUEUED" },
    ...over,
  };
}

function finishedJob(result: Record<string, unknown>) {
  return {
    status: 200,
    headers: new Headers(),
    data: {
      id: "job-1",
      surface: "project",
      refs: {},
      goal: "g",
      state: "SUCCEEDED",
      plan: [],
      artifacts: [],
      warnings: [],
      transcript: [],
      created_at: "2026-09-26T00:00:00Z",
      updated_at: "2026-09-26T00:00:01Z",
      result: {
        model: "mimo-v2.6-pro",
        credits_debited: 8,
        reply: "El proyecto OB-1 tiene 2 vanos.",
        plan: [],
        claims: [],
        references: [],
        questions: [],
        artifacts: [],
        steps: [{ kind: "navigate", path: "/projects/abc-1", label: "Abrir proyecto" }],
        queries: [{ surface: "project", status: "ok" }],
        warnings: [],
        rejected: [],
        ...result,
      },
    },
  };
}

function agentResponse(over: Record<string, unknown> = {}) {
  jobMock.mockResolvedValue(finishedJob(over) as never);
  return agentJob();
}

describe("AskDekopen — Agente mode", () => {
  beforeEach(() => {
    agentMock.mockReset();
    jobMock.mockReset();
  });

  it("runs a goal through the agent endpoint and renders steps + provenance", async () => {
    agentMock.mockResolvedValue(agentResponse() as never);
    renderDock("/projects/abc-1");
    fireEvent.click(screen.getByRole("button", { name: /Abrir el asistente/i }));
    fireEvent.click(screen.getByRole("button", { name: "Agente" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Qué necesitas lograr/i }), {
      target: { value: "Revisa el estado del proyecto" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Ejecutar/i }));
    await waitFor(() => expect(agentMock).toHaveBeenCalledTimes(1));
    const [body, options] = agentMock.mock.calls[0] ?? [];
    expect(body).toMatchObject({
      surface: "project",
      refs: { project_id: "abc-1" },
      goal: "Revisa el estado del proyecto",
    });
    expect(new Headers(options?.headers).get("X-Organization-ID")).toBe("org-1");
    expect(await screen.findByText("El proyecto OB-1 tiene 2 vanos.")).toBeTruthy();
    expect(screen.getByText("Consultó proyecto")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Abrir proyecto" })).toBeTruthy();
  });

  it("applies an ops step through the canvas's registered commit bridge", async () => {
    const product = {
      version: "product-v2",
      assembly: {
        modules: [{ id: "m1", width_mm: "1200", height_mm: "1500" }],
        couplings: [],
      },
    };
    const applied: DesignOp[][] = [];
    function Bridge() {
      useRegisterDesignOpsBridge(product, (ops) => applied.push(ops));
      return null;
    }
    agentMock.mockResolvedValue(
      agentResponse({
        steps: [
          {
            kind: "ops",
            label: "Ajustar",
            ops: [{ op: "set_module_width", module: "m1", width_mm: 1400 }],
          },
        ],
      }) as never,
    );
    render(
      <Providers>
        <MemoryRouter initialEntries={["/projects/p1/positions/pos-9/edit"]}>
          <AssistantSurfaceProvider>
            <Bridge />
            <Routes>
              <Route path="*" element={<AskDekopen organizationId="org-1" />} />
            </Routes>
          </AssistantSurfaceProvider>
        </MemoryRouter>
      </Providers>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Abrir el asistente/i }));
    fireEvent.click(screen.getByRole("button", { name: "Agente" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Qué necesitas lograr/i }), {
      target: { value: "Cambia el ancho a 1400" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Ejecutar/i }));
    await waitFor(() => expect(agentMock).toHaveBeenCalledTimes(1));
    // The wire carries the stable-id projection the ops contract validates
    // against — the same shape AssistantPanel sends.
    expect(agentMock.mock.calls[0]?.[0]).toMatchObject({
      product: {
        modules: [{ id: "m1", width_mm: "1200", height_mm: "1500" }],
        couplings: [],
      },
    });
    const applyButton = await screen.findByRole("button", { name: /Aplicar 1 operaciones/i });
    fireEvent.click(applyButton);
    expect(applied).toEqual([[{ op: "set_module_width", module: "m1", width_mm: 1400 }]]);
    expect(await screen.findByRole("button", { name: "Aplicado" })).toBeTruthy();
  });

  it("refuses to apply ops once the product changed (stale plan)", async () => {
    const productA = {
      version: "product-v2",
      assembly: { modules: [{ id: "m1", width_mm: "1200", height_mm: "1500" }], couplings: [] },
    };
    const productB = {
      version: "product-v2",
      assembly: { modules: [{ id: "m2", width_mm: "1200", height_mm: "1500" }], couplings: [] },
    };
    let current: { [key: string]: unknown } = productA;
    function Bridge() {
      useRegisterDesignOpsBridge(current, () => undefined);
      return null;
    }
    agentMock.mockResolvedValue(
      agentResponse({
        steps: [{ kind: "ops", ops: [{ op: "set_height", height_mm: 1500 }] }],
      }) as never,
    );
    const view = render(
      <Providers>
        <MemoryRouter initialEntries={["/projects/p1/positions/pos-9/edit"]}>
          <AssistantSurfaceProvider>
            <Bridge />
            <Routes>
              <Route path="*" element={<AskDekopen organizationId="org-1" />} />
            </Routes>
          </AssistantSurfaceProvider>
        </MemoryRouter>
      </Providers>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Abrir el asistente/i }));
    fireEvent.click(screen.getByRole("button", { name: "Agente" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Qué necesitas lograr/i }), {
      target: { value: "Cambia el alto" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Ejecutar/i }));
    const applyButton = await screen.findByRole("button", { name: /Aplicar 1 operaciones/i });
    // A commit swapped the live product — the button must refuse.
    current = productB;
    view.rerender(
      <Providers>
        <MemoryRouter initialEntries={["/projects/p1/positions/pos-9/edit"]}>
          <AssistantSurfaceProvider>
            <Bridge />
            <Routes>
              <Route path="*" element={<AskDekopen organizationId="org-1" />} />
            </Routes>
          </AssistantSurfaceProvider>
        </MemoryRouter>
      </Providers>,
    );
    await waitFor(() => expect(applyButton).toHaveProperty("disabled", true));
  });
});
