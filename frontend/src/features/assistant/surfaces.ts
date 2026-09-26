/** One surface dictionary — dock, workspace, and the route map all read from
 * here so a new surface name never drifts into three spellings. The values
 * are the Spanish domain words the UI shows next to state chips and headers. */
export const SURFACE_LABELS: Record<string, string> = {
  // Job/workflow surfaces
  morning_brief: "brief del día",
  purchase_plan: "plan de compras",
  production_plan: "plan de producción",
  quotation_complete: "completar cotización",
  project_from_documents: "proyecto desde documentos",
  catalog_compiler: "compilador de catálogo",
  customer_comms: "comunicación al cliente",
  // Route surfaces
  dashboard: "panel",
  projects: "proyectos",
  project: "proyecto",
  position: "vano",
  quotation: "cotización",
  catalog: "catálogo",
  production: "producción",
  work_order: "orden de trabajo",
  clients: "clientes",
  purchasing: "compras",
  settings: "configuración",
  assistant: "asistente",
  jobs: "trabajos",
  onboarding: "inicio guiado",
};
