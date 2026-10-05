export type UxRole = "OWNER" | "ESTIMATOR" | "WORKSHOP_MANAGER" | "OPERATOR" | "INSTALLER";

export type FixtureRefs = {
  projectId: string;
  positionId: string;
  clientId: string;
  quoteTokens: {
    vigente: string;
    aprobada: string;
    revocada: string;
    expirada: string;
    reemplazada: string;
  };
};

export type RouteDefinition = {
  id: string;
  path: string;
  roles: UxRole[];
  public?: boolean;
  workshop?: boolean;
};

export const VIEWPORTS = [
  { id: "1440x900", width: 1440, height: 900 },
  { id: "1280x800", width: 1280, height: 800 },
  { id: "1024x768", width: 1024, height: 768 },
  { id: "390x844", width: 390, height: 844 },
] as const;

export const THEMES = ["light", "dark"] as const;

export const FIXTURE_USERS: Record<UxRole, { email: string; password: string }> = {
  OWNER: { email: "demo-owner@fixture.dekopen.local", password: "Demo-Fixture-2026!" },
  ESTIMATOR: { email: "demo-estimator@fixture.dekopen.local", password: "Demo-Fixture-2026!" },
  WORKSHOP_MANAGER: {
    email: "demo-manager@fixture.dekopen.local",
    password: "Demo-Fixture-2026!",
  },
  OPERATOR: { email: "demo-operator@fixture.dekopen.local", password: "Demo-Fixture-2026!" },
  INSTALLER: { email: "demo-installer@fixture.dekopen.local", password: "Demo-Fixture-2026!" },
};

export function routesForFixture(refs: FixtureRefs): RouteDefinition[] {
  return [
    { id: "inicio", path: "/", roles: ["ESTIMATOR"] },
    { id: "login", path: "/login", roles: ["ESTIMATOR"], public: true },
    { id: "panel", path: "/dashboard", roles: ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"] },
    { id: "proyectos", path: "/projects", roles: ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"] },
    {
      id: "proyecto-detalle",
      path: `/projects/${refs.projectId}`,
      roles: ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"],
    },
    {
      id: "posicion-nueva",
      path: `/projects/${refs.projectId}/positions/new`,
      roles: ["ESTIMATOR"],
    },
    {
      id: "posicion-edicion",
      path: `/projects/${refs.projectId}/positions/${refs.positionId}/edit`,
      roles: ["ESTIMATOR"],
    },
    {
      id: "precios-proyecto",
      path: `/projects/${refs.projectId}/pricing`,
      roles: ["OWNER", "ESTIMATOR"],
    },
    { id: "precios-comercial", path: "/pricing/commercial", roles: ["OWNER", "ESTIMATOR"] },
    { id: "costos", path: "/pricing/cost-lists", roles: ["OWNER"] },
    { id: "clientes", path: "/clients", roles: ["OWNER", "ESTIMATOR"] },
    { id: "cliente-detalle", path: `/clients/${refs.clientId}`, roles: ["OWNER", "ESTIMATOR"] },
    { id: "catalogo", path: "/catalogs/systems", roles: ["OWNER", "WORKSHOP_MANAGER"] },
    { id: "asistente", path: "/assistant", roles: ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"] },
    { id: "trabajos", path: "/jobs", roles: ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"] },
    { id: "ajustes", path: "/settings/general", roles: ["OWNER"] },
    { id: "billetera", path: "/settings/wallet", roles: ["OWNER"] },
    { id: "facturacion", path: "/settings/billing", roles: ["OWNER"] },
    { id: "compras", path: "/purchasing", roles: ["OWNER", "WORKSHOP_MANAGER"] },
    {
      id: "produccion",
      path: "/production",
      roles: ["WORKSHOP_MANAGER", "OPERATOR", "INSTALLER"],
      workshop: true,
    },
    {
      id: "portal-vigente",
      path: `/cotizacion/${refs.quoteTokens.vigente}`,
      roles: ["ESTIMATOR"],
      public: true,
    },
    {
      id: "portal-aprobada",
      path: `/cotizacion/${refs.quoteTokens.aprobada}`,
      roles: ["ESTIMATOR"],
      public: true,
    },
    {
      id: "portal-revocada",
      path: `/cotizacion/${refs.quoteTokens.revocada}`,
      roles: ["ESTIMATOR"],
      public: true,
    },
    {
      id: "portal-expirada",
      path: `/cotizacion/${refs.quoteTokens.expirada}`,
      roles: ["ESTIMATOR"],
      public: true,
    },
    {
      id: "portal-reemplazada",
      path: `/cotizacion/${refs.quoteTokens.reemplazada}`,
      roles: ["ESTIMATOR"],
      public: true,
    },
    { id: "pago-retorno", path: "/pago/retorno", roles: ["ESTIMATOR"], public: true },
  ];
}
