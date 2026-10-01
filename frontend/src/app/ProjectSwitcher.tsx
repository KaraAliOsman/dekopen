import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useQuery } from "@tanstack/react-query";

import { ApiError } from "../api/apiMutator";
import { projectsList, type projectsListResponse } from "../api/generated/dekopen";
import { useAuthSession } from "../auth/AuthSessionProvider";
import { t } from "../i18n/es-CL";
import { useDismiss } from "./shellUtils";

/** Jump between recent projects without leaving the project context. Only
 * rendered inside /projects/:id — everywhere else the rail already offers
 * the full list. Fetch is lazy on first open and stays fresh: project
 * mutations invalidate the org's query cache. */
export function ProjectSwitcher(): JSX.Element | null {
  const org = useAuthSession().me?.active_organization;
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const rootRef = useDismiss<HTMLDivElement>(open, () => setOpen(false));

  const parts = location.pathname.split("/").filter(Boolean);
  const projectId = parts[0] === "projects" && parts[1] && parts[1] !== "demo" ? parts[1] : null;

  const query = useQuery({
    queryKey: ["project-switcher", org?.id],
    enabled: open && Boolean(org),
    staleTime: 30_000,
    queryFn: async ({ signal }) => {
      const response: projectsListResponse = await projectsList({
        signal,
        headers: { "X-Organization-ID": org?.id ?? "" },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items.slice(0, 8);
    },
  });

  if (!org || !projectId) return null;

  const candidates = (query.data ?? []).filter((item) => item.id !== projectId);
  return (
    <div className="project-switcher" ref={rootRef}>
      <button
        type="button"
        className="topbar-button"
        aria-haspopup="menu"
        aria-expanded={open || undefined}
        onClick={() => setOpen((value) => !value)}
      >
        {t("shell.switchProject")}
        <span aria-hidden className="topbar-button__chevron">
          ▾
        </span>
      </button>
      {open && (
        <div className="shell-menu shell-menu--right" aria-label={t("shell.switchProject")}>
          <p className="shell-menu__title">{t("shell.recentProjects")}</p>
          {query.isPending ? (
            <p className="shell-menu__meta">{t("projects.loading")}</p>
          ) : query.isError ? (
            <button
              type="button"
              className="shell-menu__item"
              role="alert"
              onClick={() => void query.refetch()}
            >
              {t("projects.uncertain")} · {t("ui.retry")}
            </button>
          ) : candidates.length === 0 ? (
            <p className="shell-menu__meta">{t("shell.noOtherProjects")}</p>
          ) : (
            <ul>
              {candidates.map((item) => (
                <li key={item.id}>
                  <Link
                    className="shell-menu__item"
                    to={`/projects/${item.id}`}
                    onClick={() => setOpen(false)}
                  >
                    <span>
                      {item.code} · {item.name}
                    </span>
                    <span className="shell-menu__meta">{item.client_name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
