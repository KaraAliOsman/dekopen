import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/apiMutator";
import { engineCalculate, engineSystems } from "../../api/generated/dekopen";
import type {
  EngineCalculateRequestRequest,
  EngineCalculateResponse,
} from "../../api/generated/models";
import { AuthSessionContext, type AuthSessionContextValue } from "../../auth/AuthSessionProvider";
import { CanvasEditor2DView } from "./CanvasEditor2DView";
import { useCanvasStore } from "./canvasStore";

vi.mock("../../api/generated/dekopen", () => ({
  engineCalculate: vi.fn(),
  engineSystems: vi.fn(),
}));

const calculateMock = vi.mocked(engineCalculate);
const systemsMock = vi.mocked(engineSystems);

function responseFor(request: EngineCalculateRequestRequest): EngineCalculateResponse {
  const changed = request.nominal_width_mm !== "1000.00" || request.nominal_height_mm !== "1000.00";
  return {
    profile_cuts: [
      {
        sku: "FRAME",
        role: "FRAME",
        material: "PVC",
        length_mm: changed ? "1206.25" : "1006.00",
        angle_left: "45.0",
        angle_right: "45.0",
        qty: 4,
        bay_id: "g1",
        leaf_id: null,
        sagitta_mm: null,
      },
      {
        sku: "BEAD",
        role: "GLAZING_BEAD",
        material: "PVC",
        length_mm: changed ? "1119.25" : "919.00",
        angle_left: "45.0",
        angle_right: "45.0",
        qty: 4,
        bay_id: "g1",
        leaf_id: null,
        sagitta_mm: null,
      },
    ],
    reinforcements: [
      {
        parent_profile_sku: "FRAME",
        reinforcement_sku: "STEEL",
        role: "FRAME",
        length_mm: changed ? "1170.25" : "970.00",
        qty: 4,
        bay_id: "g1",
        leaf_id: null,
        sagitta_mm: null,
      },
    ],
    glasses: [
      {
        bay_id: "g1",
        leaf_id: null,
        width_mm: request.nominal_width_mm === "1000.00" ? "910.00" : "1010.25",
        height_mm: request.nominal_height_mm === "1000.00" ? "910.00" : "1060.50",
        shape: null,
        area_m2: "1.1775",
        weight_kg: "11.78",
        thickness_net_mm: "4.00",
        glass_spec: null,
        article_sku: null,
        exposed_edges: null,
      },
    ],
    hardware_items: [],
    panels: [],
    fittings: [],
    leaf_weights: [],
    calculation_hash: `sha256:${"0".repeat(64)}`,
  };
}

function authValue(): AuthSessionContextValue {
  return {
    status: "ready",
    session: {} as AuthSessionContextValue["session"],
    me: {
      user: { id: "user-id", email: "test@example.com" },
      aal: "aal1",
      active_organization: { id: "org-id", name: "Taller", role: "ESTIMATOR" },
      memberships: [],
    },
    memberships: [],
    error: null,
    requestMagicLink: vi.fn().mockResolvedValue(undefined),
    selectOrganization: vi.fn().mockResolvedValue(undefined),
    refreshContext: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined),
  };
}

function renderEditor(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthSessionContext.Provider value={authValue()}>
        <MemoryRouter initialEntries={["/projects/demo/positions/g1/edit"]}>
          <Routes>
            <Route
              path="/projects/demo/positions/g1/edit"
              element={<CanvasEditor2DView demoRoute />}
            />
          </Routes>
        </MemoryRouter>
      </AuthSessionContext.Provider>
    </QueryClientProvider>,
  );
}

describe("SHOT-05 transactional G1 editor", () => {
  beforeEach(() => {
    useCanvasStore.getState().reset();
    calculateMock.mockReset();
    systemsMock.mockReset();
    systemsMock.mockResolvedValue({
      status: 200,
      headers: new Headers(),
      data: {
        systems: [
          {
            id: "runtime-discovered-system",
            code: "DEMO_60",
            name: "Sistema Demo 60mm PVC",
            is_demo: true,
            quote_ready: true,
            readiness_reasons: [],
          },
        ],
      },
    });
    calculateMock.mockImplementation(async (request) => {
      if (request.nominal_width_mm === "999.00") {
        throw new ApiError(400, {
          error: { code: "validation_error", detail: "Request validation failed" },
        });
      }
      return { status: 200, headers: new Headers(), data: responseFor(request) };
    });
  });

  it("discovers DEMO_60 and renders the complete API-derived G1 evidence", async () => {
    renderEditor();

    const editor = await screen.findByTestId("canvas-editor");
    expect(editor).toHaveAttribute("data-system-id", "runtime-discovered-system");
    expect(calculateMock).toHaveBeenCalledWith(
      expect.objectContaining({ system_id: "runtime-discovered-system" }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByLabelText("Ancho nominal (mm)")).toHaveValue("1000.00");
    expect(screen.getByLabelText("Alto nominal (mm)")).toHaveValue("1000.00");
    expect(screen.getByText("FIXED")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-glass-dimension")).toHaveTextContent("910 × 910 mm");
    expect(screen.getByTestId("technical-frame")).toHaveTextContent("1006 mm");
    expect(screen.getByTestId("technical-reinforcement")).toHaveTextContent("970 mm");
    expect(screen.getByTestId("technical-glass")).toHaveTextContent("910 × 910 mm");
    expect(screen.getByTestId("technical-bead")).toHaveTextContent("919 mm");
  });

  it("supports width and height keyboard edits without implicit blur commits", async () => {
    renderEditor();
    const width = await screen.findByLabelText("Ancho nominal (mm)");
    const height = screen.getByLabelText("Alto nominal (mm)");
    await waitFor(() => expect(calculateMock).toHaveBeenCalledTimes(1));

    fireEvent.focus(width);
    fireEvent.change(width, { target: { value: "1200" } });
    fireEvent.keyDown(width, { key: "Escape" });
    expect(width).toHaveValue("1000.00");
    expect(calculateMock).toHaveBeenCalledTimes(1);

    fireEvent.focus(height);
    fireEvent.change(height, { target: { value: "1250" } });
    fireEvent.blur(height);
    expect(height).toHaveValue("1000.00");
    expect(calculateMock).toHaveBeenCalledTimes(1);

    fireEvent.focus(width);
    fireEvent.change(width, { target: { value: "1100.5" } });
    fireEvent.keyDown(width, { key: "Enter" });
    await waitFor(() => expect(width).toHaveValue("1100.50"));

    fireEvent.focus(height);
    fireEvent.change(height, { target: { value: "1150" } });
    fireEvent.keyDown(height, { key: "Enter" });
    await waitFor(() => expect(height).toHaveValue("1150.00"));
    expect(calculateMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        nominal_width_mm: "1100.50",
        nominal_height_mm: "1150.00",
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("keeps the accepted dimensions and response when the backend rejects a candidate", async () => {
    renderEditor();
    const width = await screen.findByLabelText("Ancho nominal (mm)");
    await waitFor(() => expect(calculateMock).toHaveBeenCalledTimes(1));

    fireEvent.focus(width);
    fireEvent.change(width, { target: { value: "999" } });
    fireEvent.keyDown(width, { key: "Enter" });

    expect(await screen.findByRole("alert")).toHaveTextContent("validation_error");
    expect(width).toHaveValue("1000.00");
    expect(screen.getByTestId("canvas-glass-dimension")).toHaveTextContent("910 × 910 mm");
  });

  it.each([
    [[], "demo_system_unavailable"],
    [
      [
        {
          id: "one",
          code: "DEMO_60",
          name: "One",
          is_demo: true,
          quote_ready: true,
          readiness_reasons: [],
        },
        {
          id: "two",
          code: "DEMO_60",
          name: "Two",
          is_demo: true,
          quote_ready: true,
          readiness_reasons: [],
        },
      ],
      "demo_system_ambiguous",
    ],
  ])("fails closed when runtime discovery is not unique", async (systems, code) => {
    systemsMock.mockResolvedValue({ status: 200, headers: new Headers(), data: { systems } });
    renderEditor();
    expect(await screen.findByRole("alert")).toHaveTextContent(code);
    expect(calculateMock).not.toHaveBeenCalled();
  });
});
