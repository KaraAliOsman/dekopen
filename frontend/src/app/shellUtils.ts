import { useEffect, useRef } from "react";

import type { Role3ceEnum } from "../api/generated/models";
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

export const roleLabel: Record<Role3ceEnum, TranslationKey> = {
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
