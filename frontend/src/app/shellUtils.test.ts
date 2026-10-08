import { describe, expect, it } from "vitest";

import type { MembershipRoleEnum } from "../api/generated/models";
import {
  contextItemActive,
  hasUnsavedWork,
  navigationAllowedFor,
  registerDirtySource,
  SHELL_NAV_GROUPS,
  type ContextNavItem,
} from "./shellUtils";

const items: ContextNavItem[] = [
  { to: "/production", label: "nav.context.queue" },
  { to: "/production?shortage=1", label: "nav.context.shortage" },
  { to: "/production?dispatch_ready=1", label: "nav.context.dispatch" },
];

describe("contextItemActive", () => {
  it("activates a query item when its params are a subset of composed live filters", () => {
    expect(contextItemActive(items[1]!, items, "/production", "?shortage=1&status=HOLD")).toBe(
      true,
    );
    expect(contextItemActive(items[0]!, items, "/production", "?shortage=1&status=HOLD")).toBe(
      false,
    );
  });

  it("lights only the first matching query item when two filters claim the URL", () => {
    const search = "?shortage=1&dispatch_ready=1";
    expect(contextItemActive(items[1]!, items, "/production", search)).toBe(true);
    expect(contextItemActive(items[2]!, items, "/production", search)).toBe(false);
    expect(contextItemActive(items[0]!, items, "/production", search)).toBe(false);
  });

  it("keeps the plain item active only when no query sibling matches", () => {
    expect(contextItemActive(items[0]!, items, "/production", "?status=HOLD")).toBe(true);
    expect(contextItemActive(items[0]!, items, "/production", "?shortage=1")).toBe(false);
    expect(contextItemActive(items[1]!, items, "/production", "")).toBe(false);
  });
});

describe("matriz rol → navegación", () => {
  const ALL_ITEMS = SHELL_NAV_GROUPS.flatMap((group) => group.items.map((i) => i.to));

  const EXPECTED: Record<MembershipRoleEnum, string[]> = {
    OWNER: ALL_ITEMS,
    ESTIMATOR: [
      "/dashboard",
      "/clients",
      "/projects",
      "/quotations",
      "/pricing/commercial",
      "/inventory",
      "/production",
      "/field/incidents",
      "/field/service",
      "/assistant",
      "/jobs",
    ],
    WORKSHOP_MANAGER: [
      "/dashboard",
      "/clients",
      "/projects",
      "/catalogs/systems",
      "/purchasing",
      "/inventory",
      "/production",
      "/deliveries",
      "/field/dispatch",
      "/field/agenda",
      "/field/incidents",
      "/field/service",
      "/assistant",
      "/jobs",
      "/analitica",
      "/settings/general",
    ],
    INSTALLER: ["/dashboard", "/production", "/deliveries", "/field/agenda"],
    OPERATOR: ["/dashboard", "/inventory", "/production"],
  };

  it.each(Object.entries(EXPECTED))(
    "rol %s ve exactamente las secciones que su backend permite",
    (role, allowed) => {
      const visible = ALL_ITEMS.filter((to) =>
        navigationAllowedFor(role as MembershipRoleEnum, to),
      );
      expect(visible.sort()).toEqual([...allowed].sort());
    },
  );

  it("no hay entradas de menú huérfanas de grupo ni duplicadas", () => {
    expect(new Set(ALL_ITEMS).size).toBe(ALL_ITEMS.length);
  });

  it("ningún rol se queda sin navegación", () => {
    for (const role of Object.keys(EXPECTED) as MembershipRoleEnum[]) {
      const groups = SHELL_NAV_GROUPS.map((group) => ({
        ...group,
        items: group.items.filter((item) => navigationAllowedFor(role, item.to)),
      })).filter((group) => group.items.length > 0);
      expect(groups.length).toBeGreaterThan(0);
      expect(groups[0]!.id).toBe("home");
    }
  });
});

describe("dirty registry", () => {
  it("tracks unsaved work while a source is registered", () => {
    expect(hasUnsavedWork()).toBe(false);
    const release = registerDirtySource("editor-1");
    expect(hasUnsavedWork()).toBe(true);
    release();
    expect(hasUnsavedWork()).toBe(false);
  });
});
