import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "../api/apiMutator";
import { analyticsOperationalSummary, projectsList } from "../api/generated/dekopen";
import type { OperationalSummary, ProjectResponse } from "../api/generated/models";
import { useAuthSession } from "../auth/AuthSessionProvider";
import { formatDateTime } from "../format";
import { t, type TranslationKey } from "../i18n/es-CL";
import { attentionEntries, attentionLabel } from "./attention";

const WO_STATUSES = [
  "RELEASED",
  "IN_PROGRESS",
  "COMPLETED",
  "HOLD",
  "DISPATCHED",
  "INSTALLED",
] as const;

const woStatusKey: Record<string, TranslationKey> = {
  RELEASED: "production.orderReleased",
  IN_PROGRESS: "production.orderInProgress",
  COMPLETED: "production.orderCompleted",
  HOLD: "production.orderHold",
  DISPATCHED: "production.orderDispatched",
  INSTALLED: "production.orderInstalled",
};

const eventLabel: Record<string, TranslationKey> = {
  STEP_STARTED: "production.eventStepStarted",
  STEP_COMPLETED: "production.eventStepCompleted",
  STEP_BLOCKED: "production.eventStepBlocked",
  STEP_UNBLOCKED: "production.eventStepUnblocked",
  NOTE: "production.eventNote",
  WO_HOLD: "production.eventHold",
  WO_REMADE: "production.eventRemade",
  WO_RELEASED: "production.eventReleased",
  WO_COMPLETED: "production.eventCompleted",
  WO_OPTIMIZED: "production.eventOptimized",
  QC_FAILED: "production.eventQcFailed",
  WO_CNC_EXPORTED: "production.eventCncExported",
  WO_PACKED: "production.eventPacked",
  WO_DISPATCHED: "production.eventDispatched",
  WO_INSTALLED: "production.eventInstalled",
};

type RecentEvent = { event: string; order_code: string; at: string };

const statuses: Record<ProjectResponse["status"], TranslationKey> = {
  DRAFT: "projects.draft",
  QUOTED: "projects.quoted",
  APPROVED: "projects.approved",
  IN_PRODUCTION: "projects.production",
  COMPLETED: "projects.completed",
  CANCELLED: "projects.cancelled",
};

export function DashboardPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const query = useQuery<ProjectResponse[]>({
    queryKey: ["dashboard", "projects", org?.id],
    enabled: org !== undefined,
    queryFn: async ({ signal }) => {
      const response = await projectsList({
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data.items;
    },
  });

  // Floor roles land on /production — the operational summary is a
  // commercial/management feed and its readers exclude them; don't fire a
  // query that's guaranteed to 403.
  const opsVisible = ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"].includes(org?.role ?? "");
  const opsQuery = useQuery<OperationalSummary>({
    queryKey: ["dashboard", "ops", org?.id],
    enabled: org !== undefined && opsVisible,
    queryFn: async ({ signal }) => {
      const response = await analyticsOperationalSummary({
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
  });

  const items = query.data ?? [];
  const byActivity = [...items].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const recent = byActivity.slice(0, 8);
  const next = byActivity.find((item) => item.status === "DRAFT") ?? null;
  const canWrite = org?.role === "OWNER" || org?.role === "ESTIMATOR";

  // One canonical attention feed — the topbar bell renders the same queue,
  // so the surfaces can never disagree about what needs a human.
  const attention = attentionEntries(opsQuery.data);

  return (
    <section className="dashboard" aria-labelledby="page-title">
      <header className="dashboard-head">
        <div>
          <h1 id="page-title">{t("page.dashboard")}</h1>
          <p className="dashboard-sub">{org?.name ?? t("org.none")}</p>
        </div>
        {canWrite && (
          <Link className="primary-action" to="/projects">
            {t("projects.create")}
          </Link>
        )}
      </header>

      {query.isError && <p role="alert">{t("projects.uncertain")}</p>}

      <section className="dashboard-attention" aria-label={t("dashboard.attention")}>
        <h2 className="eyebrow">{t("dashboard.attention")}</h2>
        {query.isPending || (opsVisible && opsQuery.isPending) ? (
          <p className="dashboard-attention-clear">{t("dashboard.attentionLoading")}</p>
        ) : query.isError || opsQuery.isError ? (
          <p className="dashboard-attention-clear" role="alert">
            {t("dashboard.attentionError")}
          </p>
        ) : attention.length === 0 ? (
          <p className="dashboard-attention-clear">{t("dashboard.allClear")}</p>
        ) : (
          <ul>
            {attention.map((entry) => (
              <li
                key={entry.key}
                className={entry.warn ? "attention-item is-warn" : "attention-item"}
              >
                <Link to={entry.to}>
                  <strong>{entry.count}</strong>
                  <span className="attention-label">{attentionLabel(entry)}</span>
                  <span className="attention-cta">{t(entry.action)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {next && (
        <Link to={`/projects/${next.id}`} className="dashboard-continue">
          <span className="eyebrow">{t("dashboard.continue")}</span>
          <span className="dashboard-continue-name">{next.name || next.code}</span>
          <span className="dashboard-continue-meta">
            {next.name ? `${next.code} · ` : ""}
            {next.client_name} ·{" "}
            <time dateTime={next.updated_at}>{formatDateTime(next.updated_at)}</time>
          </span>
          <span className="dashboard-continue-cta">{t("dashboard.resume")}</span>
        </Link>
      )}

      {opsQuery.data ? (
        <section className="dashboard-ops" aria-label={t("dashboard.opsTitle")}>
          <h2 className="eyebrow">{t("dashboard.opsTitle")}</h2>
          <div className="dashboard-funnel">
            {WO_STATUSES.every(
              (status) =>
                Number((opsQuery.data.work_orders as Record<string, number>)[status] ?? 0) === 0,
            ) && <p className="dashboard-funnel-empty">{t("dashboard.noWorkOrders")}</p>}
            {WO_STATUSES.filter(
              (status) =>
                Number((opsQuery.data.work_orders as Record<string, number>)[status] ?? 0) > 0,
            ).map((status) => {
              const count = Number(
                (opsQuery.data.work_orders as Record<string, number>)[status] ?? 0,
              );
              return (
                <span key={status} className="status-chip" data-status={status.toLowerCase()}>
                  {t(woStatusKey[status] ?? "production.orderReleased")} · {count}
                </span>
              );
            })}
          </div>
          <div className="dashboard-cards">
            <div className="metric-card">
              <span className="eyebrow">{t("dashboard.dispatched30")}</span>
              <strong>
                {Number(
                  (opsQuery.data.throughput_30d as Record<string, number>).dispatched_30d ?? 0,
                )}
              </strong>
            </div>
            <div className="metric-card">
              <span className="eyebrow">{t("dashboard.installed30")}</span>
              <strong>
                {Number(
                  (opsQuery.data.throughput_30d as Record<string, number>).installed_30d ?? 0,
                )}
              </strong>
            </div>
            <div className="metric-card">
              <span className="eyebrow">{t("dashboard.leadHours")}</span>
              <strong>
                {opsQuery.data.avg_release_to_dispatch_hours !== null
                  ? `${opsQuery.data.avg_release_to_dispatch_hours} h`
                  : "—"}
              </strong>
            </div>
          </div>
          {((opsQuery.data.recent_events as RecentEvent[]) ?? []).length > 0 ? (
            <ul className="dashboard-activity">
              {(opsQuery.data.recent_events as RecentEvent[]).map((item, i) => (
                <li key={`${item.order_code}-${item.event}-${i}`}>
                  <span className="dashboard-activity-event">
                    {t(eventLabel[item.event] ?? "production.eventStepCompleted")}
                  </span>
                  <span className="dashboard-activity-code">{item.order_code}</span>
                  <time dateTime={item.at}>{formatDateTime(item.at)}</time>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {query.isPending ? (
        <p role="status">{t("projects.loading")}</p>
      ) : items.length === 0 ? (
        <div className="dashboard-empty">
          <p>{t("dashboard.empty")}</p>
          {canWrite && (
            <div className="dashboard-empty__actions">
              <Link className="primary-action" to="/projects">
                {t("dashboard.emptyCta")}
              </Link>
              <Link className="ui-button" to="/onboarding">
                {t("dashboard.onboardingCta")}
              </Link>
            </div>
          )}
        </div>
      ) : (
        <div className="dashboard-list">
          <div className="dashboard-list-head">
            <h2 className="eyebrow">{t("dashboard.recent")}</h2>
            <Link className="ui-backlink" to="/projects">
              {t("dashboard.viewAll")}
            </Link>
          </div>
          <ul>
            {recent.map((item) => (
              <li key={item.id}>
                <Link to={`/projects/${item.id}`} className="dashboard-row">
                  <span className="dashboard-row-name">{item.name}</span>
                  <span className="dashboard-row-code">{item.code}</span>
                  <span className="dashboard-row-client">{item.client_name}</span>
                  <span className="status-chip" data-status={item.status.toLowerCase()}>
                    {t(statuses[item.status])}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
