import { useEffect, useRef } from "react";

import type { MembershipRoleEnum } from "../api/generated/models";
import type { TranslationKey } from "../i18n/es-CL";

/** Editors register while they hold unsaved work so non-router transitions
 * (org switch remounts the session context, not the router) can gate on the
 * same dirty boundary as the route blocker. */
const dirtySources = new Set<string>();
export function registerDirtySource(id: string): () => void {
  dirtySources.add(id);
  return () => {
    dirtySources.delete(id);
  };
}
export function hasUnsavedWork(): boolean {
  return dirtySources.size > 0;
}

/** One-shot bypass for the next guarded navigation: a surface that already
 * confirmed the discard (e.g. the org switcher's own dialog) must not make
 * the route blocker ask a second time. Consumed by the first navigation it
 * affects — it cannot leak into a later, unrelated transition. */
let navigationBypassArmed = false;
export function allowNextGuardedNavigation(): void {
  navigationBypassArmed = true;
}
export function consumeNavigationBypass(): boolean {
  const armed = navigationBypassArmed;
  navigationBypassArmed = false;
  return armed;
}

export const roleLabel: Record<MembershipRoleEnum, TranslationKey> = {
  OWNER: "shell.role.owner",
  ESTIMATOR: "shell.role.estimator",
  WORKSHOP_MANAGER: "shell.role.workshopManager",
  INSTALLER: "shell.role.installer",
  OPERATOR: "shell.role.operator",
};

/** Dismiss a floating menu on outside click or Escape — shared by the org
 * switcher, project switcher and attention bell so they behave identically. */
export function useDismiss<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent): void {
      if (ref.current !== null && !ref.current.contains(event.target as Node)) onClose();
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);
  return ref;
}
export type ContextNavItem = { to: string; label: TranslationKey };

export type ShellNavItem = { to: string; label: TranslationKey };
export type ShellNavGroup = {
  id: string;
  title: TranslationKey;
  items: ShellNavItem[];
};

/** El menú sigue el flujo real de la fábrica — vender → diseñar → producir
 * → entregar — no las tablas de la base de datos. Cada entrada existe solo
 * si el backend tiene datos para ella (nada de secciones vacías). */
export const SHELL_NAV_GROUPS: ShellNavGroup[] = [
  {
    id: "home",
    title: "nav.groupHome",
    items: [{ to: "/dashboard", label: "nav.home" }],
  },
  {
    id: "sales",
    title: "nav.groupSales",
    items: [
      { to: "/clients", label: "nav.clients" },
      { to: "/projects", label: "nav.projects" },
      { to: "/quotations", label: "nav.quotations" },
      { to: "/pricing/commercial", label: "nav.pricing" },
    ],
  },
  {
    id: "engineering",
    title: "nav.groupEngineering",
    items: [{ to: "/catalogs/systems", label: "nav.technicalCatalog" }],
  },
  {
    id: "operation",
    title: "nav.groupOperation",
    items: [
      { to: "/purchasing", label: "nav.purchasing" },
      { to: "/inventory", label: "nav.inventory" },
      { to: "/production", label: "nav.production" },
      { to: "/deliveries", label: "nav.deliveries" },
      { to: "/field/dispatch", label: "nav.dispatchBoard" },
      { to: "/field/agenda", label: "nav.fieldAgenda" },
      { to: "/field/incidents", label: "nav.incidents" },
      { to: "/field/service", label: "nav.service" },
    ],
  },
  {
    id: "assistant",
    title: "nav.groupAssistant",
    items: [
      { to: "/assistant", label: "nav.assistant" },
      { to: "/jobs", label: "nav.jobs" },
    ],
  },
  {
    id: "analytics",
    title: "nav.groupAnalytics",
    items: [{ to: "/analitica", label: "nav.analytics" }],
  },
  {
    id: "settings",
    title: "nav.groupSettings",
    items: [{ to: "/settings/general", label: "nav.settings" }],
  },
];

/** Espejo de `_AGENT_CALLERS`/`_JOB_READERS` del backend: la superficie
 * Asistente (orb, dock, /assistant, /jobs) sólo sirve a los roles de
 * oficina — OPERATOR e INSTALLER jamás deben pagar una pared 403. */
export const AI_SURFACE_ROLES: ReadonlySet<MembershipRoleEnum> = new Set([
  "OWNER",
  "ESTIMATOR",
  "WORKSHOP_MANAGER",
]);

export function hasAiSurface(role: MembershipRoleEnum | null | undefined): boolean {
  return role !== undefined && role !== null && AI_SURFACE_ROLES.has(role);
}

/** Matriz rol → destino. Refleja los role-sets del backend: una entrada
 * de menú nunca lleva a una pared 403. Exportada para el test de matriz. */
export function navigationAllowedFor(
  role: MembershipRoleEnum | null | undefined,
  to: string,
): boolean {
  const base = to.split("?")[0];
  switch (base) {
    // «Hoy» le sirve a los cinco roles — es su única superficie común.
    case "/dashboard":
    case "/production":
      return role !== undefined;
    case "/clients":
    case "/projects":
      return role === "OWNER" || role === "ESTIMATOR" || role === "WORKSHOP_MANAGER";
    case "/quotations":
    case "/pricing/commercial":
      return role === "OWNER" || role === "ESTIMATOR";
    case "/catalogs/systems":
    case "/purchasing":
      return role === "OWNER" || role === "WORKSHOP_MANAGER";
    case "/inventory":
      return (
        role === "OWNER" ||
        role === "ESTIMATOR" ||
        role === "WORKSHOP_MANAGER" ||
        role === "OPERATOR"
      );
    case "/deliveries":
    case "/field/agenda":
      return role === "OWNER" || role === "WORKSHOP_MANAGER" || role === "INSTALLER";
    case "/field/dispatch":
      return role === "OWNER" || role === "WORKSHOP_MANAGER";
    case "/field/incidents":
    case "/field/service":
      return role === "OWNER" || role === "WORKSHOP_MANAGER" || role === "ESTIMATOR";
    case "/assistant":
    case "/jobs":
      return hasAiSurface(role);
    // P24: espejo de READER_ROLES del backend — montos ya vienen recortados
    // por analytics_financial_roles; la puerta es membership, no dinero.
    case "/analitica":
      return role === "OWNER" || role === "WORKSHOP_MANAGER";
    case "/settings/general":
      return role === "OWNER" || role === "WORKSHOP_MANAGER";
    default:
      return true;
  }
}

/** Context items share a path and differ only by query (Cola vs ?shortage=1):
 * a query target activates when all of its params appear in the live query —
 * production filters compose, so `?shortage=1&status=HOLD` is still Faltantes;
 * the plain target stays active unless a sibling claims the live query. */
export function contextItemActive(
  item: ContextNavItem,
  siblings: ContextNavItem[],
  pathname: string,
  search: string,
): boolean {
  const url = new URL(item.to, "http://shell.local");
  if (url.pathname !== pathname) return false;
  const live = new URLSearchParams(search);
  const claimed = (target: ContextNavItem): boolean => {
    const targetUrl = new URL(target.to, "http://shell.local");
    const params = [...targetUrl.searchParams.entries()];
    return (
      targetUrl.pathname === pathname &&
      params.length > 0 &&
      params.every(([key, value]) => live.get(key) === value)
    );
  };
  if (url.search !== "") {
    // Composed filters (?shortage=1&status=HOLD) still credit the query item
    // whose params are a subset of the live ones; the first matching sibling
    // wins so two applied filters never light two rail items.
    if (!claimed(item)) return false;
    const earlier = siblings.slice(0, siblings.indexOf(item));
    return !earlier.some(claimed);
  }
  return !siblings.some(claimed);
}
