import { type PropsWithChildren, useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import { t } from "../i18n/es-CL";

import { useAuthSession } from "../auth/AuthSessionProvider";
import { BrandMark } from "../brand/BrandMark";
import { Wordmark } from "../brand";
import { MOD_K_HINT } from "../platform";
import { useProject } from "../features/projects/useProject";
import { telemetry } from "../telemetry/telemetry";
import { useTheme } from "../theme/ThemeProvider";
import { CommandPalette } from "../features/commands/CommandPalette";
import type { AiJob } from "../api/generated/models/aiJob";
import { AiPresence } from "../features/assistant/AiPresence";
import { AiTestModeBadge } from "../features/assistant/AiTestModeBadge";
import { AskDekopen } from "../features/assistant/AskDekopen";
import { STATE_LABELS } from "../features/assistant/states";
import { AssistantSurfaceProvider } from "../features/assistant/assistantContext";
import { AttentionBell } from "./AttentionBell";
import { OrgSwitcher } from "./OrgSwitcher";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { RailIcon } from "./railIcons";
import { Icon as UiIcon } from "../ui/icons";
import { ShellCrumbs, crumbsFor, useProjectName } from "./ShellCrumbs";
import { ShellLeafContext } from "./shellLeaf";
import {
  contextItemActive,
  navigationAllowedFor,
  roleLabel,
  SHELL_NAV_GROUPS,
  useDismiss,
  type ContextNavItem,
} from "./shellUtils";

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
  const [presenceJob, setPresenceJob] = useState<AiJob | null>(null);
  const onActiveJob = useCallback(
    (job: AiJob | null) =>
      setPresenceJob((previous) =>
        previous?.id === job?.id && previous?.state === job?.state ? previous : job,
      ),
    [],
  );
  const [railOpen, setRailOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const closeHelp = useCallback(() => setHelpOpen(false), []);
  const helpRef = useDismiss<HTMLDivElement>(helpOpen, closeHelp);
  // El riel colapsa a iconos con tooltip — la preferencia persiste entre
  // sesiones porque es costumbre de trabajo, no estado de la página.
  const [railCollapsed, setRailCollapsed] = useState(
    () => localStorage.getItem("dekopen.rail.collapsed") === "1",
  );
  const toggleRail = useCallback(() => {
    setRailCollapsed((value) => {
      const next = !value;
      localStorage.setItem("dekopen.rail.collapsed", next ? "1" : "0");
      return next;
    });
  }, []);

  // Close the drawer nav on route change and on Escape — the drawer only
  // exists below the tablet breakpoint; desktop keeps the rail always.
  useEffect(() => setRailOpen(false), [location.pathname]);
  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setRailOpen(false);
        setHelpOpen(false);
      } else if (event.key === "?") {
        const target = event.target as HTMLElement | null;
        const inField =
          target instanceof HTMLElement &&
          (target.tagName === "INPUT" ||
            target.tagName === "TEXTAREA" ||
            target.tagName === "SELECT" ||
            target.isContentEditable);
        if (!inField) {
          event.preventDefault();
          setHelpOpen((value) => !value);
        }
      }
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
  // Same queryKey as the position editor's lock check — when the user is
  // already on the project this is a cache hit; a locked project must not
  // keep advertising «Nuevo vano» in the rail.
  const projectLock = useProject(
    canWrite && projectId !== null && projectId !== "demo" ? projectId : null,
  );
  const lockedProject = projectLock.data;
  const projectUnlocked =
    !lockedProject ||
    (lockedProject.status === "DRAFT" &&
      !lockedProject.versions?.some(
        (version) => version.revision_code === lockedProject.current_revision,
      ) &&
      !lockedProject.current_pricing_operation_id);
  // Studio (position editor): the project-context rail yields to a compact
  // 64px global icon strip — the canvas owns the room and the topbar keeps
  // the where-you-are breadcrumbs (mandate 01: Studio rail may be ~64px).
  const isStudio = parts[0] === "projects" && parts[2] === "positions" && parts.length >= 4;
  const context: "project" | "production" | null = isStudio
    ? null
    : projectId !== null
      ? "project"
      : parts[0] === "production"
        ? "production"
        : null;
  const projectName = useProjectName(projectId !== null && projectId !== "demo" ? projectId : null);

  // Browser tab title tracks the same crumbs the shell renders — tabs and
  // history entries stop all saying "DEKOPEN".
  useEffect(() => {
    const crumbs = crumbsFor(location.pathname, projectName, leaf);
    const head = crumbs
      .slice(-2)
      .map((crumb) => crumb.label)
      .join(" · ");
    document.title = head ? `${head} · DEKOPEN` : "DEKOPEN";
  }, [location.pathname, projectName, leaf]);

  function navigationAllowed(to: string): boolean {
    // Mirrors the backend role sets — a nav link must never land on a
    // 403 wall. Pure + exported for the role→nav matrix test.
    return navigationAllowedFor(role, to);
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
          ...(canWrite && projectUnlocked
            ? [
                {
                  to: `/projects/${projectId}/positions/new`,
                  label: "nav.context.newPosition" as const,
                },
              ]
            : []),
        ];

  const contextItems = context === "project" ? projectContext : productionContext;

  const navItems = SHELL_NAV_GROUPS.flatMap((group) => group.items)
    .filter((item) => navigationAllowed(item.to))
    .concat(contextItems);

  return (
    <ShellLeafContext.Provider value={leafContext}>
      <AssistantSurfaceProvider>
        <div
          className={`app-shell${railOpen ? " rail-open" : ""}${railCollapsed ? " rail-collapsed" : ""}`}
          data-studio={isStudio || undefined}
          data-testid="app-shell"
        >
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
              {railCollapsed && !isStudio ? <BrandMark size={14} /> : <Wordmark size={14} />}
            </div>
            <OrgSwitcher />
            <nav className="app-rail__nav" aria-label={t("shell.navigation")}>
              {context === null ? (
                SHELL_NAV_GROUPS.map((group) => {
                  const items = group.items.filter((item) => navigationAllowed(item.to));
                  if (items.length === 0) return null;
                  const iconsOnly = isStudio || railCollapsed;
                  return (
                    <div key={group.id} className="rail-group">
                      <p className="rail-group__title" aria-hidden={iconsOnly || undefined}>
                        {t(group.title)}
                      </p>
                      {items.map((item) => (
                        <NavLink
                          aria-label={iconsOnly ? t(item.label) : undefined}
                          className="rail-item"
                          key={item.to}
                          title={iconsOnly ? t(item.label) : undefined}
                          to={item.to}
                        >
                          <RailIcon to={item.to} />
                          <span aria-hidden={iconsOnly || undefined}>{t(item.label)}</span>
                        </NavLink>
                      ))}
                    </div>
                  );
                })
              ) : (
                <div className="rail-context">
                  {context === "project" ? (
                    <Link to="/projects" className="rail-context__back">
                      ‹ {t("nav.projects")}
                    </Link>
                  ) : (
                    // «Hoy» le sirve a los cinco roles — el regreso nunca es
                    // una pared 403, ni para el piso.
                    <Link to="/dashboard" className="rail-context__back">
                      ‹ {t("nav.home")}
                    </Link>
                  )}
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
                {/* Collapsar a iconos — tooltip en cada ítem compensa la
                    etiqueta escondida; nunca se pierde el destino. */}
                <button
                  type="button"
                  className="rail-icon-button rail-collapse-toggle"
                  onClick={toggleRail}
                  aria-expanded={!railCollapsed}
                  aria-label={t(railCollapsed ? "nav.expand" : "nav.collapse")}
                  title={t(railCollapsed ? "nav.expand" : "nav.collapse")}
                >
                  <UiIcon name={railCollapsed ? "arrow-right" : "arrow-left"} />
                </button>
                <button
                  type="button"
                  className="rail-icon-button"
                  onClick={toggleTheme}
                  aria-label={t("theme.toggle")}
                  title={t(theme === "light" ? "theme.toDark" : "theme.toLight")}
                >
                  <UiIcon name={theme === "light" ? "moon" : "sun"} />
                </button>
                <button
                  type="button"
                  className="rail-icon-button"
                  onClick={() => void auth.signOut()}
                  aria-label={t("auth.signOut")}
                  title={t("auth.signOut")}
                >
                  <UiIcon name="logout" />
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
                <UiIcon name="menu" />
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
                  <kbd>/</kbd>
                </button>
                <AttentionBell />
                <button
                  type="button"
                  className="rail-icon-button topbar-help"
                  aria-expanded={helpOpen}
                  aria-label={t("shell.help.title")}
                  title={`${t("shell.help.title")} (?)`}
                  onClick={() => setHelpOpen((value) => !value)}
                >
                  <UiIcon name="info" />
                </button>
                {/* INSTALLER has no AI surface — every ai endpoint is gated to
                    _AGENT_CALLERS, so the orb would offer a 403 wall. */}
                {role !== "INSTALLER" ? (
                  <>
                    {/* The orb always opens the dock — a pressing job gets its
                        own chip so an unlucky FAILED_RETRYABLE can never make
                        the dock unreachable (AI review P1-1). */}
                    <button
                      type="button"
                      className="topbar-button topbar-ai"
                      onClick={() => setAssistantRequest((value) => value + 1)}
                    >
                      <AiPresence
                        organizationId={org?.id ?? null}
                        size={22}
                        onActiveJob={onActiveJob}
                      />
                      {t("shell.aiEntry")}
                    </button>
                    {/* §IA3 — MOCK serving means every member must see the
                        test-mode badge; the orb alone can't carry honesty. */}
                    <AiTestModeBadge organizationId={org?.id ?? null} />
                    {presenceJob ? (
                      <button
                        type="button"
                        className="topbar-button topbar-ai-job"
                        title={t("aiws.presenceOpen")}
                        onClick={() => navigate(`/assistant?job=${presenceJob.id}`)}
                      >
                        {t(STATE_LABELS[presenceJob.state] ?? "aiws.jobs")}
                      </button>
                    ) : null}
                  </>
                ) : null}
              </div>
            </header>
            <main className="workspace" id="workspace-main" tabIndex={-1}>
              {children}
            </main>
            {helpOpen ? (
              <div
                className="shell-help"
                ref={helpRef}
                role="dialog"
                aria-label={t("shell.help.title")}
              >
                <p className="shell-help__title">{t("shell.help.title")}</p>
                <dl>
                  <div>
                    <dt>
                      <kbd>{MOD_K_HINT}</kbd> <kbd>/</kbd>
                    </dt>
                    <dd>{t("shell.help.search")}</dd>
                  </div>
                  <div>
                    <dt>
                      <kbd>?</kbd>
                    </dt>
                    <dd>{t("shell.help.shortcuts")}</dd>
                  </div>
                  <div>
                    <dt>
                      <kbd>Esc</kbd>
                    </dt>
                    <dd>{t("shell.help.close")}</dd>
                  </div>
                </dl>
              </div>
            ) : null}
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
              userId={auth.me?.user.id ?? null}
            />
          ) : null}
        </div>
      </AssistantSurfaceProvider>
    </ShellLeafContext.Provider>
  );
}
