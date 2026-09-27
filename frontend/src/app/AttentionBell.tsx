import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/apiMutator";
import { analyticsOperationalSummary } from "../api/generated/dekopen";
import { useAuthSession } from "../auth/AuthSessionProvider";
import { t } from "../i18n/es-CL";
import { attentionEntries, attentionLabel } from "./attention";
import { useDismiss } from "./shellUtils";

/** Topbar bell: the same action-required feed the dashboard renders, one
 * click away from every surface. The badge counts entries, not noise. */
export function AttentionBell(): JSX.Element | null {
  const org = useAuthSession().me?.active_organization;
  const [open, setOpen] = useState(false);
  const rootRef = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  // "Read" = seen at last open, per org. The badge counts only entries that
  // are new or grew since then; opening the list acknowledges them.
  const seenKey = org ? `attention-seen:${org.id}` : null;
  const [seen, setSeen] = useState<Record<string, number>>({});

  const query = useQuery({
    queryKey: ["shell", "attention", org?.id],
    enabled:
      org !== undefined && ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"].includes(org?.role ?? ""),
    staleTime: 60_000,
    queryFn: async ({ signal }) => {
      const ops = await analyticsOperationalSummary({
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (ops.status !== 200) throw new ApiError(ops.status, ops.data);
      return attentionEntries(ops.data);
    },
  });

  // Hydrate the per-org seen snapshot when the org resolves / switches.
  useEffect(() => {
    if (!seenKey) return;
    try {
      setSeen(JSON.parse(localStorage.getItem(seenKey) ?? "{}"));
    } catch {
      setSeen({});
    }
  }, [seenKey]);

  if (!org) return null;
  const unread = (query.data ?? []).filter((entry) => entry.count > (seen[entry.key] ?? 0)).length;
  return (
    <div className="attention-bell" ref={rootRef}>
      <button
        type="button"
        className="topbar-button topbar-button--icon"
        aria-haspopup="menu"
        aria-expanded={open || undefined}
        aria-label={t("shell.notifications")}
        title={t("shell.notifications")}
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next && query.data && seenKey) {
            const snapshot = Object.fromEntries(
              query.data.map((entry) => [entry.key, entry.count]),
            );
            setSeen(snapshot);
            try {
              localStorage.setItem(seenKey, JSON.stringify(snapshot));
            } catch {
              // Storage quota/denied — badge still works for this session.
            }
          }
        }}
      >
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
          <path
            d="M7.5 1.7a3.9 3.9 0 0 0-3.9 3.9v1.8l-1.2 1.8a.45.45 0 0 0 .38.7h9.44a.45.45 0 0 0 .38-.7l-1.2-1.8V5.6a3.9 3.9 0 0 0-3.9-3.9Z"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
          <path
            d="M5.8 11.9a1.7 1.7 0 0 0 3.4 0"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
          />
        </svg>
        {unread > 0 && <span className="attention-bell__badge">{unread}</span>}
      </button>
      {open && (
        <div className="shell-menu shell-menu--right" aria-label={t("shell.notifications")}>
          <p className="shell-menu__title">{t("shell.notifications")}</p>
          {query.isPending ? (
            <p className="shell-menu__meta">{t("dashboard.attentionLoading")}</p>
          ) : query.isError ? (
            <p className="shell-menu__meta" role="alert">
              {t("dashboard.attentionError")}
            </p>
          ) : (query.data ?? []).length === 0 ? (
            <p className="shell-menu__meta">{t("shell.notificationsEmpty")}</p>
          ) : (
            <ul>
              {(query.data ?? []).map((entry) => (
                <li key={entry.key}>
                  <Link
                    className={`shell-menu__item${entry.warn ? " shell-menu__item--warn" : ""}`}
                    to={entry.to}
                    onClick={() => setOpen(false)}
                  >
                    <span>{attentionLabel(entry)}</span>
                    <strong>{entry.count}</strong>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link className="shell-menu__all" to="/dashboard" onClick={() => setOpen(false)}>
            {t("shell.notificationsAll")}
          </Link>
        </div>
      )}
    </div>
  );
}
