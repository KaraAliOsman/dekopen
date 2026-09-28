import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, Route, RouterProvider, Routes } from "react-router-dom";

import { t } from "./i18n/es-CL";

import { AppShell } from "./app/AppShell";
import { RouteErrorBoundary } from "./app/RouteErrorBoundary";
import { DashboardPage } from "./app/DashboardPage";
import { JobsPage } from "./app/JobsPage";
import { SettingsPage } from "./app/SettingsPage";
import { AuthCallbackPage } from "./auth/AuthCallbackPage";
import { ReadyGuard, SessionGuard } from "./auth/AuthGuards";
import { useAuthSession } from "./auth/AuthSessionProvider";
import { LoginPage } from "./auth/LoginPage";
import { MfaPage } from "./auth/MfaPage";
import { SelectOrganizationPage } from "./auth/SelectOrganizationPage";
const WalletPage = lazy(async () => ({
  default: (await import("./features/billing/WalletPage")).WalletPage,
}));
const BillingPage = lazy(async () => ({
  default: (await import("./features/billing/BillingPage")).BillingPage,
}));
const PricingPage = lazy(async () => {
  const module = await import("./features/pricing/PricingPage");
  return { default: module.PricingPage };
});
const CommercialPricingPage = lazy(async () => {
  const module = await import("./features/pricing/PricingPage");
  return { default: module.CommercialPricingPage };
});

const CanvasEditor2DView = lazy(async () => {
  const module = await import("./features/canvas/CanvasEditor2DView");
  return { default: module.CanvasEditor2DView };
});

const ProjectPages = lazy(async () => ({
  default: (await import("./features/projects/ProjectPages")).ProjectPages,
}));
const ClientsPage = lazy(async () => ({
  default: (await import("./features/projects/ClientsPage")).ClientsPage,
}));
const CatalogPage = lazy(async () => ({
  default: (await import("./features/catalogs/CatalogPage")).CatalogPage,
}));
const AssistantWorkspacePage = lazy(async () => ({
  default: (await import("./features/assistant/AssistantWorkspacePage")).AssistantWorkspacePage,
}));
const ProjectPositionEditor = lazy(async () => ({
  default: (await import("./features/projects/ProjectPositionEditor")).ProjectPositionEditor,
}));
const OnboardingPage = lazy(async () => ({
  default: (await import("./features/onboarding/OnboardingPage")).OnboardingPage,
}));

function ProjectSurface({ editor = false }: { editor?: boolean }): JSX.Element {
  return (
    <ReadyGuard>
      <AppShell>
        <Suspense fallback={<p role="status">{t("projects.loading")}</p>}>
          {editor ? <ProjectPositionEditor /> : <ProjectPages />}
        </Suspense>
      </AppShell>
    </ReadyGuard>
  );
}

const PurchasingPage = lazy(async () => {
  const module = await import("./features/purchasing/PurchasingPage");
  return { default: module.PurchasingPage };
});

const ProductionPage = lazy(async () => {
  const module = await import("./features/production/ProductionPage");
  return { default: module.ProductionPage };
});

const PortalQuotePage = lazy(async () => {
  const module = await import("./features/portal/PortalQuotePage");
  return { default: module.PortalQuotePage };
});
const PaymentReturnPage = lazy(async () => {
  const module = await import("./features/portal/PaymentReturnPage");
  return { default: module.PaymentReturnPage };
});
const BenchmarkPage = lazy(async () => {
  const module = await import("./features/benchmark/BenchmarkPage");
  return { default: module.BenchmarkPage };
});

function isFloorRole(role: string | undefined): boolean {
  return ["INSTALLER", "OPERATOR"].includes(role ?? "");
}

function HomeRedirect(): JSX.Element {
  const auth = useAuthSession();
  if (auth.status === "loading" || auth.status === "resolving") {
    return <p role="status">{t("auth.resolving")}</p>;
  }
  if (auth.status === "mfa_required") return <Navigate to="/auth/mfa" replace />;
  if (auth.status === "organization_required") {
    return <Navigate to="/select-organization" replace />;
  }
  if (auth.status === "ready") {
    // Floor roles live on the production floor — the commercial dashboard
    // would deny its queries and greet them with errors.
    const home = isFloorRole(auth.me?.active_organization?.role) ? "/production" : "/dashboard";
    return <Navigate to={home} replace />;
  }
  return <Navigate to="/login" replace />;
}

/** /dashboard is a commercial surface: its queries are role-gated, so a floor
 * role deep-linking here met a wall of 403s. Redirect them to the floor home
 * instead (review: OPERATOR on /dashboard). */
function DashboardRoute(): JSX.Element {
  const auth = useAuthSession();
  if (isFloorRole(auth.me?.active_organization?.role)) {
    return <Navigate to="/production" replace />;
  }
  return (
    <AppShell>
      <DashboardPage />
    </AppShell>
  );
}

export function AppRoutes(): JSX.Element {
  return (
    <RouteErrorBoundary>
      <Routes>
        <Route
          path="/settings/billing"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("wallet.loading")}</p>}>
                  <BillingPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/settings/wallet"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("wallet.loading")}</p>}>
                  <WalletPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route path="/projects/:id" element={<ProjectSurface />} />
        <Route path="/projects/:id/positions/new" element={<ProjectSurface editor />} />
        <Route
          path="/projects/:id/pricing"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("projects.loading")}</p>}>
                  <CommercialPricingPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/projects/demo/positions/g1/edit"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("canvas.loading")}</p>}>
                  <CanvasEditor2DView demoRoute />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/pricing/commercial"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("pricing.loading")}</p>}>
                  <CommercialPricingPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/pricing/cost-lists"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("pricing.loading")}</p>}>
                  <PricingPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route path="/" element={<HomeRedirect />} />
        <Route
          path="/cotizacion/:token"
          element={
            <Suspense fallback={<p role="status">{t("portal.loading")}</p>}>
              <PortalQuotePage />
            </Suspense>
          }
        />
        <Route
          path="/pago/retorno"
          element={
            <Suspense fallback={<p role="status" />}>
              <PaymentReturnPage />
            </Suspense>
          }
        />
        {import.meta.env.DEV && (
          <Route
            path="/benchmark"
            element={
              <Suspense fallback={<p role="status" />}>
                <BenchmarkPage />
              </Suspense>
            }
          />
        )}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route
          path="/auth/mfa"
          element={
            <SessionGuard>
              <MfaPage />
            </SessionGuard>
          }
        />
        <Route
          path="/select-organization"
          element={
            <SessionGuard>
              <SelectOrganizationPage />
            </SessionGuard>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ReadyGuard>
              <DashboardRoute />
            </ReadyGuard>
          }
        />
        <Route
          path="/clients/:id?"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("clients.loading")}</p>}>
                  <ClientsPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/jobs"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("jobs.title")}</p>}>
                  <JobsPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/purchasing"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("purchasing.loading")}</p>}>
                  <PurchasingPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/production"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("production.loading")}</p>}>
                  <ProductionPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/projects/:id/positions/:posId/edit"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("projects.loading")}</p>}>
                  <ProjectPositionEditor />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route path="/projects" element={<ProjectSurface />} />
        <Route path="/catalogs" element={<Navigate to="/catalogs/systems" replace />} />
        <Route
          path="/assistant"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("projects.loading")}</p>}>
                  <AssistantWorkspacePage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/catalogs/systems"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("projects.loading")}</p>}>
                  <CatalogPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/onboarding"
          element={
            <ReadyGuard>
              <AppShell>
                <Suspense fallback={<p role="status">{t("onboarding.loading")}</p>}>
                  <OnboardingPage />
                </Suspense>
              </AppShell>
            </ReadyGuard>
          }
        />
        <Route
          path="/settings/general"
          element={
            <ReadyGuard>
              <AppShell>
                <SettingsPage />
              </AppShell>
            </ReadyGuard>
          }
        />
        {/* Bare guesses land on their real surface instead of silently
         * bouncing home — /inventory lives inside Purchasing, /settings
         * inside General. */}
        <Route path="/settings" element={<Navigate to="/settings/general" replace />} />
        <Route path="/inventory" element={<Navigate to="/purchasing" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </RouteErrorBoundary>
  );
}

const router = createBrowserRouter([{ path: "*", element: <AppRoutes /> }]);

export function App(): JSX.Element {
  return <RouterProvider router={router} />;
}
