import { useSyncExternalStore } from "react";
import { Link, useLocation } from "react-router-dom";

import { useAuthSession } from "../auth/AuthSessionProvider";
import { t } from "../i18n/es-CL";
import { useProject } from "../features/projects/useProject";
import { projectNameCached, projectNameSubscribe } from "../features/projects/projectNames";

export type Crumb = { label: string; to?: string };

/** The project name rides on the shared project query — the page, the rail
 * lock check and this crumb observe one fetch. `projectNames` remains as a
 * rename override: a rename writes through to already-mounted crumbs while
 * the cached server copy is still stale. */
export function useProjectName(id: string | null): string | null {
  const orgId = useAuthSession().me?.active_organization?.id;
  const override = useSyncExternalStore(projectNameSubscribe, () =>
    id && orgId ? projectNameCached(orgId, id) : null,
  );
  // Always fetch — the code travels with the name even when a rename
  // override bypasses the cached row.
  const project = useProject(id);
  const name = override ?? project.data?.name ?? null;
  const code = project.data?.code ?? null;
  // Human code + name: «P-000012 Edificio Prat», never a bare UUID/name.
  if (code !== null && name !== null) return `${code} ${name}`;
  return name ?? code;
}

/** Rail → entity → leaf. The first crumb is the rail destination the user
 * came from; the last is whatever the page itself published (or the page's
 * own name). Intermediate crumbs link back — the last never does. */
export function crumbsFor(
  pathname: string,
  projectName: string | null,
  leaf: string | null,
): Crumb[] {
  const parts = pathname.split("/").filter(Boolean);
  const [section, second, third, fourth] = parts;

  if (section === "dashboard") return [{ label: t("crumb.dashboard") }];
  if (section === "production") return [{ label: t("crumb.production") }];
  if (section === "purchasing") return [{ label: t("crumb.purchasing") }];
  if (section === "quotations") return [{ label: t("crumb.quotations") }];
  if (section === "deliveries") return [{ label: t("crumb.deliveries") }];
  if (section === "inventory") return [{ label: t("crumb.inventory") }];
  if (section === "clients") {
    const head: Crumb = { label: t("crumb.clients") };
    if (second !== undefined)
      return [{ ...head, to: "/clients" }, { label: t("crumb.clientDetail") }];
    return [head];
  }
  if (section === "jobs") return [{ label: t("crumb.jobs") }];
  if (section === "assistant") return [{ label: t("crumb.assistant") }];
  if (section === "catalogs") {
    const head: Crumb = { label: t("crumb.catalogs") };
    if (second === "systems") return [head, { label: t("crumb.systems") }];
    return [head];
  }
  if (section === "pricing") {
    const head: Crumb = { label: t("crumb.pricingRoot") };
    if (second === "commercial") return [head, { label: t("crumb.pricingCommercial") }];
    if (second === "cost-lists") return [head, { label: t("crumb.costLists") }];
    return [head];
  }
  if (section === "settings") {
    const head: Crumb = { label: t("crumb.settings") };
    const leafKey =
      second === "billing"
        ? "crumb.settingsBilling"
        : second === "wallet"
          ? "crumb.settingsWallet"
          : "crumb.settingsGeneral";
    return [head, { label: t(leafKey) }];
  }
  if (section === "projects") {
    const head: Crumb = { label: t("crumb.projects"), to: "/projects" };
    if (second === undefined) return [{ label: t("crumb.projects") }];
    // The demo canvas is not a real project row — it gets an honest label
    // instead of a fetch that would 404.
    const entity =
      second === "demo" ? t("crumb.positionDemo") : (projectName ?? t("crumb.projectFallback"));
    if (third === undefined) return [head, { label: entity }];
    if (third === "positions" && fourth === "new")
      return [
        head,
        { label: entity, to: `/projects/${second}` },
        { label: t("crumb.positionNew") },
      ];
    if (third === "positions" && fourth !== undefined)
      return [
        head,
        { label: entity, to: `/projects/${second}` },
        { label: leaf ?? t("crumb.positionFallback") },
      ];
    if (third === "pricing")
      return [head, { label: entity, to: `/projects/${second}` }, { label: t("crumb.pricing") }];
    return [head, { label: entity, to: `/projects/${second}` }, { label: leaf ?? third }];
  }
  return [{ label: t("crumb.home"), to: "/dashboard" }];
}

export function ShellCrumbs({ leaf }: { leaf: string | null }): JSX.Element {
  const location = useLocation();
  const parts = location.pathname.split("/").filter(Boolean);
  const projectId =
    parts[0] === "projects" && parts[1] !== undefined && parts[1] !== "demo" ? parts[1] : null;
  const projectName = useProjectName(projectId);
  const crumbs = crumbsFor(location.pathname, projectName, leaf);
  return (
    <nav className="crumbs" aria-label={t("crumb.label")}>
      <ol className="crumbs__list">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <li key={`${crumb.label}-${index}`} className="crumbs__item">
              {index > 0 && (
                <span className="crumbs__sep" aria-hidden>
                  /
                </span>
              )}
              {crumb.to !== undefined && !last ? (
                <Link className="crumbs__link" to={crumb.to}>
                  {crumb.label}
                </Link>
              ) : (
                <span className="crumbs__current" aria-current={last ? "page" : undefined}>
                  {crumb.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
