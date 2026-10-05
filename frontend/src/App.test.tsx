import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { AppRoutes, DEV_ONLY_ROUTE_PATHS, visibleDevOnlyRoutePaths } from "./App";
import { AuthSessionContext, type AuthSessionContextValue } from "./auth/AuthSessionProvider";
import { ThemeProvider } from "./theme/ThemeProvider";
import { ConfirmProvider } from "./ui";
vi.mock("./api/generated/dekopen", () => ({
  projectsList: vi.fn().mockResolvedValue({ status: 200, data: { items: [] } }),
}));

function authValue(status: AuthSessionContextValue["status"]): AuthSessionContextValue {
  return {
    status,
    session:
      status === "anonymous"
        ? null
        : ({ user: { id: "route-test-user" } } as AuthSessionContextValue["session"]),
    me:
      status === "ready"
        ? {
            user: { id: "10000000-0000-0000-0000-000000000001", email: "" },
            aal: "aal1",
            active_organization: {
              id: "20000000-0000-0000-0000-000000000001",
              name: "Taller A",
              role: "ESTIMATOR",
            },
            memberships: [],
          }
        : null,
    memberships:
      status === "organization_required"
        ? [
            {
              organization_id: "20000000-0000-0000-0000-000000000001",
              organization_name: "Taller A",
              role: "ESTIMATOR",
            },
          ]
        : [],
    error: null,
    requestMagicLink: vi.fn().mockResolvedValue(undefined),
    selectOrganization: vi.fn().mockResolvedValue(undefined),
    refreshContext: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined),
  };
}

function renderRoute(path: string, auth: AuthSessionContextValue) {
  return render(
    <AuthSessionContext.Provider value={auth}>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ThemeProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <AppRoutes />
            </MemoryRouter>
          </ConfirmProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </AuthSessionContext.Provider>,
  );
}

describe("SHOT-04 application routes", () => {
  it("shows anonymous visitors the public landing with an entry to login", async () => {
    renderRoute("/", authValue("anonymous"));
    expect(await screen.findByRole("heading", { name: /ventana que diseñas/ })).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", { name: "Entrar" })) {
      expect(link).toHaveAttribute("href", "/login");
    }
  });

  it("opens the real project list from the authenticated shell", async () => {
    renderRoute("/dashboard", authValue("ready"));
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Proyectos" })).toHaveAttribute("href", "/projects");
    fireEvent.click(screen.getByRole("link", { name: "Proyectos" }));
    expect(await screen.findByRole("heading", { name: "Todos los proyectos" })).toBeInTheDocument();
  });

  it("routes an OWNER requiring aal2 to the MFA flow", async () => {
    renderRoute("/dashboard", authValue("mfa_required"));
    expect(await screen.findByTestId("mfa-page")).toBeInTheDocument();
  });

  it("routes multi-membership sessions to explicit organization selection", async () => {
    const auth = authValue("organization_required");
    renderRoute("/dashboard", auth);
    const selector = await screen.findByTestId("organization-selector");
    fireEvent.click(screen.getByRole("button", { name: /Taller A/ }));
    await waitFor(() => expect(auth.selectOrganization).toHaveBeenCalledOnce());
    expect(selector).toBeInTheDocument();
  });

  it("switches and persists the dual theme", () => {
    window.localStorage.setItem("dekopen.theme", "light");
    renderRoute("/dashboard", authValue("ready"));
    fireEvent.click(screen.getByRole("button", { name: "Cambiar tema" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("dekopen.theme")).toBe("dark");
  });

  it("keeps dev-only routes out of production routing", () => {
    expect(DEV_ONLY_ROUTE_PATHS).toContain("/projects/demo/positions/g1/edit");
    expect(visibleDevOnlyRoutePaths({ DEV: false })).toEqual([]);
    expect(visibleDevOnlyRoutePaths({ DEV: true })).toEqual(DEV_ONLY_ROUTE_PATHS);
  });
});
