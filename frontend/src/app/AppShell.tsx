import { type PropsWithChildren, useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import { t, type TranslationKey } from "../i18n/es-CL";

import { useAuthSession } from "../auth/AuthSessionProvider";
import { MOD_K_HINT } from "../platform";
import { telemetry } from "../telemetry/telemetry";
import { useTheme } from "../theme/ThemeProvider";
import { CommandPalette } from "../features/commands/CommandPalette";
import { AiPresence } from "../features/assistant/AiPresence";
import { AskDekopen } from "../features/assistant/AskDekopen";
import { AssistantSurfaceProvider } from "../features/assistant/assistantContext";
import { AttentionBell } from "./AttentionBell";
import { OrgSwitcher } from "./OrgSwitcher";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { ShellCrumbs, useProjectName } from "./ShellCrumbs";
import { ShellLeafContext } from "./shellLeaf";
import { contextItemActive, roleLabel, type ContextNavItem } from "./shellUtils";

/** Work domains, not database tables: the job surfaces first, operational
 * records next, account/admin last. AI is a persistent topbar entry, not a
 * route. Context (inside a project or production) replaces the global list —
 * the rail serves where you are, not everywhere you could go. */
const domainGroups: {
  id: string;
  title: TranslationKey;
  items: { to: string; label: TranslationKey }[];
}[] = [
  {
    id: "work",
    title: "nav.groupWork",
    items: [
      { to: "/dashboard", label: "nav.dashboard" },
      { to: "/projects", label: "nav.projects" },
      { to: "/clients", label: "nav.clients" },
      { to: "/pricing/commercial", label: "nav.sales" },
    ],
  },
  {
    id: "operations",
    title: "nav.groupOps",
    items: [
      { to: "/catalogs/systems", label: "nav.catalog" },
      { to: "/purchasing", label: "nav.purchasing" },
      { to: "/production", label: "nav.production" },
      { to: "/assistant", label: "nav.assistant" },
      { to: "/jobs", label: "nav.jobs" },
    ],
  },
  {
    id: "account",
    title: "nav.groupAccount",
    items: [{ to: "/settings/general", label: "nav.admin" }],
  },
];

const productionContext: ContextNavItem[] = [
  { to: "/production", label: "nav.context.queue" },
  { to: "/production?shortage=1", label: "nav.context.shortage" },
  { to: "/production?dispatch_ready=1", label: "nav.context.dispatch" },
];

export function AppShell({ children }: PropsWithChildren): JSX.Element {
  const auth = useAuthSession();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [leaf, setLeafState] = useState<string | null>(null);
  const setLeaf = useCallback((label: string | null) => setLeafState(label), []);
  const leafContext = useMemo(() => ({ leaf, setLeaf }), [leaf, setLeaf]);
  const [paletteRequest, setPaletteRequest] = useState(0);
  const [assistantRequest, setAssistantRequest] = useState(0);
  const [railOpen, setRailOpen] = useState(false);

  // Close the drawer nav on route change and on Escape — the drawer only
  // exists below the tablet breakpoint; desktop keeps the rail always.
  useEffect(() => setRailOpen(false), [location.pathname]);
  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") setRailOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    telemetry.capture("shell_route_viewed", { route_name: location.pathname });
  }, [location.pathname]);

  const org = auth.me?.active_organization;
  const role = org?.role;
  const canWrite = role === "OWNER" || role === "ESTIMATOR";

  const parts = location.pathname.split("/").filter(Boolean);
  const projectId = parts[0] === "projects" && parts[1] !== undefined ? parts[1] : null;
  const context: "project" | "production" | null =
    projectId !== null ? "project" : parts[0] === "production" ? "production" : null;
  const projectName = useProjectName(projectId !== null && projectId !== "demo" ? projectId : null);

  function navigationAllowed(to: string): boolean {
    // Mirrors the backend role sets — a nav link must never land on a
    // 403 wall.
    if (to === "/pricing/commercial") return role === "OWNER" || role === "ESTIMATOR";
    if (to === "/assistant") return role !== "INSTALLER";
    if (to === "/jobs") return role !== "INSTALLER";
    if (to === "/catalogs/systems" || to === "/purchasing")
      return role === "OWNER" || role === "WORKSHOP_MANAGER";
    if (to === "/production")
      return role === "OWNER" || role === "WORKSHOP_MANAGER" || role === "INSTALLER";
    if (to === "/dashboard" || to === "/projects" || to === "/clients") return role !== "INSTALLER";
    return true;
  }

  const projectContext: ContextNavItem[] =
    projectId === null || projectId === "demo"
      ? []
      : [
          { to: `/projects/${projectId}`, label: "nav.context.summary" },
          // Pricing ops accept O/E only — WM gets the summary but no dead link.
          ...(canWrite
            ? [
                {
                  to: `/projects/${projectId}/pricing`,
                  label: "nav.context.quote" as const,
                },
              ]
            : []),
          ...(canWrite
            ? [
                {
                  to: `/projects/${projectId}/positions/new`,
                  label: "nav.context.newPosition" as const,
                },
              ]
            : []),
        ];

  const contextItems = context === "project" ? projectContext : productionContext;

  const navItems = domainGroups
    .flatMap((group) => group.items)
    .filter((item) => navigationAllowed(item.to))
    .concat(contextItems);

  return (
    <ShellLeafContext.Provider value={leafContext}>
      <AssistantSurfaceProvider>
        <div className={`app-shell${railOpen ? " rail-open" : ""}`} data-testid="app-shell">
          <a href="#workspace-main" className="skip-link">
            {t("shell.skipToContent")}
          </a>
          <button
            type="button"
            className="rail-scrim"
            aria-hidden={!railOpen}
            tabIndex={railOpen ? 0 : -1}
            onClick={() => setRailOpen(false)}
          />
          <aside className="app-rail">
            <div className="app-rail__brand">
              <span className="brand">{t("app.brand")}</span>
            </div>
            <OrgSwitcher />
            <nav className="app-rail__nav" aria-label={t("shell.navigation")}>
              {context === null ? (
                domainGroups.map((group) => {
                  const items = group.items.filter((item) => navigationAllowed(item.to));
                  if (items.length === 0) return null;
                  return (
                    <div key={group.id} className="rail-group">
                      <p className="rail-group__title">{t(group.title)}</p>
                      {items.map((item) => (
                        <NavLink key={item.to} to={item.to} className="rail-item">
                          {t(item.label)}
                        </NavLink>
                      ))}
                    </div>
                  );
                })
              ) : (
                <div className="rail-context">
                  <Link
                    to={context === "project" ? "/projects" : "/dashboard"}
                    className="rail-context__back"
                  >
                    ‹ {t(context === "project" ? "nav.projects" : "nav.dashboard")}
                  </Link>
                  {context === "project" && (
                    <p className="rail-context__title">
                      {projectId === "demo"
                        ? t("crumb.positionDemo")
                        : (projectName ?? t("crumb.projectFallback"))}
                    </p>
                  )}
                  {contextItems.map((item) => {
                    const active = contextItemActive(
                      item,
                      contextItems,
                      location.pathname,
                      location.search,
                    );
                    return (
                      <Link
                        key={`${item.to}:${item.label}`}
                        to={item.to}
                        className={`rail-item${active ? " active" : ""}`}
                        aria-current={active ? "page" : undefined}
                      >
                        {t(item.label)}
                      </Link>
                    );
                  })}
                </div>
              )}
            </nav>
            <div className="app-rail__user">
              <div className="app-rail__identity">
                <span className="app-rail__email" title={auth.me?.user.email ?? undefined}>
                  {auth.me?.user.email ? auth.me.user.email.split("@")[0] : "—"}
                </span>
                {role && <span className="app-rail__role">{t(roleLabel[role])}</span>}
              </div>
              <div className="app-rail__user-actions">
                <button
                  type="button"
                  className="rail-icon-button"
                  onClick={toggleTheme}
                  aria-label={t("theme.toggle")}
                  title={t(theme === "light" ? "theme.toDark" : "theme.toLight")}
                >
                  {theme === "light" ? "☾" : "☀"}
                </button>
                <button
                  type="button"
                  className="rail-icon-button"
                  onClick={() => void auth.signOut()}
                  aria-label={t("auth.signOut")}
                  title={t("auth.signOut")}
                >
                  ⎋
                </button>
              </div>
            </div>
          </aside>
          <div className="app-body">
            <header className="app-topbar">
              <button
                type="button"
                className="rail-toggle"
                aria-expanded={railOpen}
                aria-label={t("shell.menu")}
                onClick={() => setRailOpen((value) => !value)}
              >
                ☰
              </button>
              <ShellCrumbs leaf={leaf} />
              <div className="app-topbar__actions">
                <ProjectSwitcher />
                <button
                  type="button"
                  className="topbar-search"
                  onClick={() => setPaletteRequest((value) => value + 1)}
                >
                  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden>
                    <circle cx="5.6" cy="5.6" r="4.1" stroke="currentColor" strokeWidth="1.3" />
                    <path
                      d="m8.7 8.7 2.8 2.8"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                    />
                  </svg>
                  <span>{t("shell.searchHint")}</span>
                  <kbd>{MOD_K_HINT}</kbd>
                </button>
                <AttentionBell />
                {/* INSTALLER has no AI surface — every ai endpoint is gated to
                    _AGENT_CALLERS, so the orb would offer a 403 wall. */}
                {role !== "INSTALLER" ? (
                  <button
                    type="button"
                    className="topbar-button topbar-ai"
                    onClick={() => setAssistantRequest((value) => value + 1)}
                  >
                    <AiPresence organizationId={org?.id ?? null} size={22} />
                    {t("shell.aiEntry")}
                  </button>
                ) : null}
              </div>
            </header>
            <main className="workspace" id="workspace-main" tabIndex={-1}>
              {children}
            </main>
          </div>
          <CommandPalette
            openRequested={paletteRequest}
            navItems={navItems.map((item) => ({ to: item.to, label: t(item.label) }))}
            onNavigate={(to) => navigate(to)}
            organizationId={org?.id ?? null}
          />
          {role !== "INSTALLER" ? (
            <AskDekopen
              openRequested={assistantRequest}
              hideTrigger
              organizationId={org?.id ?? null}
            />
          ) : null}
        </div>
      </AssistantSurfaceProvider>
    </ShellLeafContext.Provider>
  );
}
