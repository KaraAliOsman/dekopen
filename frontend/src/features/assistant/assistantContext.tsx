import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { matchPath, useLocation } from "react-router-dom";

import type { DesignOp } from "../commands/types";

/** The contextual assistant's (surface, refs) — derived from the route by
 * default; a page can override it (e.g. ProductionPage while a work order is
 * selected). Refs are identifiers only — the server builds the real context. */
export interface AssistantContextValue {
  surface: string;
  refs: Record<string, string>;
}

const AssistantSurface = createContext<{
  value: AssistantContextValue;
  setOverride: (value: AssistantContextValue | null) => void;
} | null>(null);

/** The canvas's live product + commit channel, published while a position
 * editor is mounted — the agent dock sends that product for server-side op
 * validation and applies the returned ops through the same registry commit a
 * human click would use. Kept in its own context so product churn doesn't
 * re-render every surface consumer. */
export interface DesignOpsBridge {
  product: { [key: string]: unknown };
  apply: (ops: DesignOp[]) => void;
}

const DesignOpsBridge = createContext<{
  bridge: DesignOpsBridge | null;
  setBridge: (bridge: DesignOpsBridge | null) => void;
} | null>(null);

const SURFACE_ROUTES: {
  pattern: string;
  surface: string;
  refs: (params: Record<string, string | undefined>) => Record<string, string>;
}[] = [
  {
    pattern: "/projects/:id/positions/:posId/edit",
    surface: "position",
    refs: (p) => ({ project_id: p.id ?? "", position_id: p.posId ?? "" }),
  },
  {
    pattern: "/projects/:id/pricing",
    surface: "quotation",
    refs: (p) => ({ project_id: p.id ?? "" }),
  },
  {
    pattern: "/projects/:id/*",
    surface: "project",
    refs: (p) => ({ project_id: p.id ?? "" }),
  },
  { pattern: "/projects", surface: "projects", refs: () => ({}) },
  { pattern: "/production", surface: "production", refs: () => ({}) },
  { pattern: "/purchasing", surface: "purchasing", refs: () => ({}) },
  { pattern: "/catalogs/*", surface: "catalog", refs: () => ({}) },
  { pattern: "/clients", surface: "clients", refs: () => ({}) },
  { pattern: "/settings/*", surface: "settings", refs: () => ({}) },
  // Org-level commercial config surfaces answer through the organization
  // projection — no dedicated pricing surface exists server-side.
  { pattern: "/pricing/*", surface: "settings", refs: () => ({}) },
  // The assistant workspace is its own surface — jobs started there carry
  // "assistant", not a pretend "dashboard".
  { pattern: "/assistant/*", surface: "assistant", refs: () => ({}) },
  { pattern: "/jobs", surface: "jobs", refs: () => ({}) },
  { pattern: "/onboarding", surface: "onboarding", refs: () => ({}) },
  { pattern: "/dashboard", surface: "dashboard", refs: () => ({}) },
  { pattern: "/", surface: "dashboard", refs: () => ({}) },
];

export function routeContext(pathname: string): AssistantContextValue {
  for (const route of SURFACE_ROUTES) {
    const match = matchPath({ path: route.pattern, end: true }, pathname);
    if (match) {
      return { surface: route.surface, refs: route.refs(match.params) };
    }
  }
  return { surface: "dashboard", refs: {} };
}

export function AssistantSurfaceProvider({ children }: PropsWithChildren): JSX.Element {
  const location = useLocation();
  const [override, setOverride] = useState<AssistantContextValue | null>(null);
  const [bridge, setBridge] = useState<DesignOpsBridge | null>(null);
  const value = useMemo(() => {
    const derived = override ?? routeContext(location.pathname);
    return { value: derived, setOverride };
  }, [location.pathname, override]);
  const bridgeValue = useMemo(() => ({ bridge, setBridge }), [bridge]);
  return (
    <AssistantSurface.Provider value={value}>
      <DesignOpsBridge.Provider value={bridgeValue}>{children}</DesignOpsBridge.Provider>
    </AssistantSurface.Provider>
  );
}

/** The live assistant context for the current route (or a page override). */
export function useAssistantContext(): AssistantContextValue {
  const ctx = useContext(AssistantSurface);
  // useMemo: the fallback literal must keep a stable identity across renders —
  // consumers key effects on the serialized refs.
  return useMemo(() => ctx?.value ?? { surface: "dashboard", refs: {} }, [ctx?.value]);
}

/** A page declares a more specific assistant context while mounted (e.g. the
 * selected work order). Pass null to restore the route-derived value. The
 * effect keys on the serialized refs so an inline object can't loop the
 * override. */
export function useAssistantSurface(surface: string | null, refs?: Record<string, string>): void {
  const ctx = useContext(AssistantSurface);
  const setOverride = ctx?.setOverride;
  const refsKey = refs ? JSON.stringify(refs) : "";
  useEffect(() => {
    if (!setOverride || !surface) return;
    setOverride({ surface, refs: refs ? (JSON.parse(refsKey) as Record<string, string>) : {} });
    return () => setOverride(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refsKey is the
    // stable serialization of refs; the raw object would re-fire per render.
  }, [setOverride, surface, refsKey]);
}

/** The canvas's design-ops bridge, when a position editor is mounted. */
export function useDesignOpsBridge(): DesignOpsBridge | null {
  const ctx = useContext(DesignOpsBridge);
  return ctx?.bridge ?? null;
}

/** A live editor publishes its product + apply channel while mounted (and
 * re-publishes on every product commit so the bridge always closes over the
 * CURRENT product). Pass nulls to unregister. */
export function useRegisterDesignOpsBridge(
  product: { [key: string]: unknown } | null,
  apply: ((ops: DesignOp[]) => void) | null,
): void {
  const ctx = useContext(DesignOpsBridge);
  const setBridge = ctx?.setBridge;
  // Callers pass fresh closures each render — forward the call through a ref
  // so a new identity never re-registers the bridge in a loop.
  const applyRef = useRef(apply);
  applyRef.current = apply;
  const stableApply = useRef<((ops: DesignOp[]) => void) | null>(null);
  if (!stableApply.current && apply) {
    stableApply.current = (ops) => applyRef.current?.(ops);
  }
  useEffect(() => {
    if (!setBridge || !product || !stableApply.current) return;
    setBridge({ product, apply: stableApply.current });
    return () => setBridge(null);
  }, [setBridge, product]);
}
