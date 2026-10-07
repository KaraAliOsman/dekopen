// frontend/src/features/projects/ProjectPaymentLinksPanel.test.tsx
// Regresión de «No pudimos cargar los links de pago» (histórico F-09): la
// consulta del estado de la integración es owner-scoped y vivía dentro del
// mismo Promise.all que la lista — un 403 en la primera ocultaba la segunda.
// Estos tests fijan que la lista siempre se pinta, con o sin integración.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../api/apiMutator";
import {
  projectPaymentIntegrationStatus,
  projectPaymentLinksList,
} from "../../api/generated/dekopen";
import type { PaymentLink } from "../../api/generated/models";
import { ProjectPaymentLinksPanel } from "./ProjectPaymentLinksPanel";

vi.mock("../../api/generated/dekopen", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/generated/dekopen")>();
  return {
    ...actual,
    projectPaymentLinksList: vi.fn(),
    projectPaymentIntegrationStatus: vi.fn(),
    projectPaymentLinkCreate: vi.fn(),
    projectPaymentLinkRecover: vi.fn(),
  };
});

function response<S extends number, T>(status: S, data: T) {
  return { status, data, headers: new Headers() };
}

const LINK: PaymentLink = {
  id: "11111111-2222-3333-4444-555555555555",
  operation_key: "op-abc",
  kind: "SALDO",
  amount: "291760",
  payer_email: "cliente@correo.cl",
  subject: "Saldo P-0001",
  status: "PENDING",
  environment: "sandbox",
  url: "http://localhost:8000/api/v1/billing/flow-sim/sim-abc/",
  project_payment_id: null,
  expires_at: null,
  created_at: "2026-10-01T12:00:00Z",
  updated_at: "2026-10-01T12:00:00Z",
};

function mount({ isOwner }: { isOwner: boolean }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProjectPaymentLinksPanel
        projectId="project-1"
        orgId="org-a"
        canWrite
        isOwner={isOwner}
        onChanged={() => undefined}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(projectPaymentLinksList).mockResolvedValue(response(200, { links: [LINK] }));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("renders the links for a non-owner without ever asking for the integration status", async () => {
  vi.mocked(projectPaymentIntegrationStatus).mockRejectedValue(
    new ApiError(403, { detail: "Solo el dueño" }),
  );
  mount({ isOwner: false });
  await waitFor(() => expect(screen.getByText("cliente@correo.cl")).toBeTruthy());
  expect(screen.getByText("$291.760")).toBeTruthy();
  expect(projectPaymentIntegrationStatus).not.toHaveBeenCalled();
  expect(screen.queryByText(/No pudimos cargar/i)).toBeNull();
});

it("keeps the links visible when the owner-scoped integration status 403s", async () => {
  vi.mocked(projectPaymentIntegrationStatus).mockRejectedValue(
    new ApiError(403, { detail: "forbidden" }),
  );
  mount({ isOwner: true });
  await waitFor(() => expect(screen.getByText("cliente@correo.cl")).toBeTruthy());
  expect(screen.getByText("$291.760")).toBeTruthy();
  expect(screen.queryByText(/No pudimos cargar/i)).toBeNull();
});

it("marks the simulated provider and enables creating links without credentials", async () => {
  vi.mocked(projectPaymentIntegrationStatus).mockResolvedValue(
    response(200, { configured: false, provider_mode: "mock", enabled: false }),
  );
  mount({ isOwner: true });
  await waitFor(() => expect(screen.getByText(/Proveedor simulado/i)).toBeTruthy());
  expect(screen.getByText("Crear link de pago")).toBeTruthy();
});
