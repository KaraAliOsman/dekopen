/** Declarative route table for ux:capture.
 *
 * `path` templates interpolate `{{projects.<slug>.id}}`, `{{orders.<k>}}`,
 * `{{portal.<state>}}`, `{{vitrina_position_ids.<tag>}}` and
 * `{{system_id}}` against `.fixture-state.json`.
 *
 * roles: which fixture account drives the session ("public" = no login).
 * extraMobile: route also captures the 390×844 operator/portal viewport.
 * touchAudit: the <44px target detector runs (floor and field roles).
 */

export type RouteRole =
  "public" | "owner" | "estimator" | "manager" | "operator" | "installer" | "multi";

export type CaptureRoute = {
  name: string;
  path: string;
  role: RouteRole;
  extraMobile?: boolean;
  touchAudit?: boolean;
  /** settle hint: css selector to wait for before snapshotting */
  waitFor?: string;
  /** la página ES el muestrario de anti-patrones: los hallazgos son su
   * contenido, no defectos — se captura igual pero no cuenta hallazgos. */
  expectViolations?: boolean;
  /** Estados HTTP que la ruta espera por diseño (p. ej. un enlace de portal
   * revocado responde 410 Gone y la UI muestra el estado correcto). */
  toleratedHttpStatuses?: number[];
};

export const ROUTES: CaptureRoute[] = [
  // ---- public surfaces --------------------------------------------------
  { name: "login", path: "/login", role: "public", waitFor: '[data-testid="login-page"]' },
  {
    name: "portal-vigente",
    path: "/cotizacion/{{portal.vigente}}",
    role: "public",
    extraMobile: true,
  },
  {
    name: "portal-aprobada",
    path: "/cotizacion/{{portal.aprobada}}",
    role: "public",
    extraMobile: true,
  },
  {
    name: "portal-revocada",
    path: "/cotizacion/{{portal.revocada}}",
    role: "public",
    extraMobile: true,
    toleratedHttpStatuses: [410],
  },
  {
    name: "portal-expirada",
    path: "/cotizacion/{{portal.expirada}}",
    role: "public",
    extraMobile: true,
    toleratedHttpStatuses: [410],
  },
  {
    name: "portal-reemplazada",
    path: "/cotizacion/{{portal.reemplazada}}",
    role: "public",
    extraMobile: true,
    toleratedHttpStatuses: [410],
  },
  {
    name: "portal-rechazada",
    path: "/cotizacion/{{portal.rechazada}}",
    role: "public",
    extraMobile: true,
  },
  {
    name: "portal-cambios",
    path: "/cotizacion/{{portal.cambios}}",
    role: "public",
    extraMobile: true,
  },
  {
    name: "portal-parcial",
    path: "/cotizacion/{{portal.parcial}}",
    role: "public",
    extraMobile: true,
  },
  {
    name: "portal-usd",
    path: "/cotizacion/{{portal.usd}}",
    role: "public",
    extraMobile: true,
  },
  {
    name: "portal-vitrina",
    path: "/cotizacion/{{portal.vitrina}}",
    role: "public",
    extraMobile: true,
  },
  { name: "pago-retorno", path: "/pago/retorno", role: "public" },

  // ---- owner (aal2) ------------------------------------------------------
  {
    name: "dashboard-owner",
    path: "/dashboard",
    role: "owner",
    waitFor: '[data-testid="app-shell"]',
    extraMobile: true,
  },
  { name: "settings-general", path: "/settings/general", role: "owner" },
  { name: "settings-billing", path: "/settings/billing", role: "owner" },
  { name: "settings-wallet", path: "/settings/wallet", role: "owner" },

  // ---- estimator ---------------------------------------------------------
  {
    name: "dashboard",
    path: "/dashboard",
    role: "estimator",
    waitFor: '[data-testid="app-shell"]',
    extraMobile: true,
  },
  { name: "projects", path: "/projects", role: "estimator" },
  { name: "project-borrador", path: "/projects/{{projects.borrador.id}}", role: "estimator" },
  { name: "project-cotizado", path: "/projects/{{projects.cotizado.id}}", role: "estimator" },
  { name: "project-vitrina", path: "/projects/{{projects.vitrina.id}}", role: "estimator" },
  { name: "project-conjuntos", path: "/projects/{{projects.conjuntos.id}}", role: "estimator" },
  { name: "project-escala", path: "/projects/{{projects.escala.id}}", role: "estimator" },
  {
    name: "project-position-new",
    path: "/projects/{{projects.borrador.id}}/positions/new",
    role: "estimator",
  },
  {
    name: "project-position-edit",
    path: "/projects/{{projects.vitrina.id}}/positions/{{vitrina_position_ids.V01 Fijo living}}/edit",
    role: "estimator",
  },
  { name: "project-pricing", path: "/projects/{{projects.vitrina.id}}/pricing", role: "estimator" },
  { name: "pricing-commercial", path: "/pricing/commercial", role: "estimator" },
  { name: "pricing-cost-lists", path: "/pricing/cost-lists", role: "estimator" },
  { name: "clients-list", path: "/clients", role: "estimator" },
  { name: "quotations", path: "/quotations", role: "estimator" },
  { name: "deliveries", path: "/deliveries", role: "manager" },
  { name: "catalogs-systems", path: "/catalogs/systems", role: "estimator" },
  { name: "catalogs-alias", path: "/catalogs", role: "estimator" },
  { name: "assistant", path: "/assistant", role: "estimator" },
  { name: "onboarding", path: "/onboarding", role: "estimator" },
  { name: "benchmark", path: "/benchmark", role: "estimator" },

  // ---- workshop manager --------------------------------------------------
  {
    name: "dashboard-manager",
    path: "/dashboard",
    role: "manager",
    waitFor: '[data-testid="app-shell"]',
    extraMobile: true,
  },
  {
    name: "production-manager",
    path: "/production",
    role: "manager",
    extraMobile: true,
    touchAudit: true,
  },
  { name: "purchasing", path: "/purchasing", role: "manager" },
  {
    name: "production-order",
    path: "/production?order={{orders.en_produccion}}",
    role: "manager",
    extraMobile: true,
    touchAudit: true,
  },
  {
    name: "production-order-blocked",
    path: "/production?order={{orders.bloqueada_faltante}}",
    role: "manager",
  },
  {
    name: "inventory-alias",
    path: "/inventory",
    role: "manager",
    extraMobile: true,
    touchAudit: true,
  },
  { name: "jobs-manager", path: "/jobs", role: "manager" },

  // ---- operator ----------------------------------------------------------
  {
    name: "production-operator",
    path: "/production",
    role: "operator",
    extraMobile: true,
    touchAudit: true,
  },
  {
    name: "dashboard-operator",
    path: "/dashboard",
    role: "operator",
    extraMobile: true,
    touchAudit: true,
  },
  { name: "jobs-operator", path: "/jobs", role: "operator", extraMobile: true, touchAudit: true },

  // ---- installer ----------------------------------------------------------
  {
    name: "dashboard-installer",
    path: "/dashboard",
    role: "installer",
    waitFor: '[data-testid="app-shell"]',
    extraMobile: true,
    touchAudit: true,
  },
  { name: "jobs-installer", path: "/jobs", role: "installer", extraMobile: true, touchAudit: true },
  {
    name: "production-installer",
    path: "/production",
    role: "installer",
    extraMobile: true,
    touchAudit: true,
  },

  // ---- multi-org selector -------------------------------------------------
  { name: "select-organization", path: "/select-organization", role: "multi" },
  { name: "dashboard-multi", path: "/dashboard", role: "multi" },

  // ---- muestrario del sistema (DEV-only) ----------------------------------
  { name: "dev-ui", path: "/dev/ui", role: "public", waitFor: ".dev-ui" },
  {
    name: "dev-ui-mal",
    path: "/dev/ui/mal",
    role: "public",
    waitFor: ".mal",
    expectViolations: true,
  },
];
