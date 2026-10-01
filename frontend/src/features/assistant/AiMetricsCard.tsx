import { useQuery } from "@tanstack/react-query";

import { ApiError } from "../../api/apiMutator";
import { aiMetrics } from "../../api/generated/dekopen";
import type { AiMetrics } from "../../api/generated/models/aiMetrics";
import { t } from "../../i18n/es-CL";

function pct(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) return null;
  return `${Math.round(numeric * 100)}%`;
}

function minutes(seconds: number): string {
  if (seconds < 90) return `${seconds}s`;
  const value = Math.round(seconds / 60);
  if (value < 90) return `${value}min`;
  return `${Math.round(value / 60)}h`;
}

/** §08 measurement — what the AI layer actually did in the trailing window:
 * jobs, completion, proposed-vs-applied commands, credits spent, and a
 * clearly-labeled time-saved estimate. Renders honest zeroes, never fake
 * precision. */
export function AiMetricsCard({
  organizationId,
  days = 30,
}: {
  organizationId: string;
  days?: number;
}): JSX.Element | null {
  const query = useQuery({
    queryKey: ["ai", "metrics", organizationId, days],
    enabled: Boolean(organizationId),
    staleTime: 60_000,
    queryFn: async () => {
      const response = await aiMetrics(
        { days },
        { headers: { "X-Organization-ID": organizationId } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data as AiMetrics;
    },
  });
  const data = query.data;
  if (!data) return null;
  const jobs = data.jobs as {
    total?: number;
    completion_rate?: string | null;
    avg_seconds?: string | null;
    by_state?: Record<string, number>;
    by_surface?: Record<string, number>;
    failure_reasons?: { code: string; count: number }[];
  };
  const approvals = data.approvals as { requested?: number; decided?: number };
  const artifactsProduced = data.artifacts_produced as number | undefined;
  const commands = data.commands as {
    proposed?: number;
    applied?: number;
    declined?: number;
    apply_rate?: string | null;
  };
  const cost = data.cost as { points_debited?: number; calls?: number };
  const timeSaved = data.time_saved as { seconds?: number };
  const topFailure = jobs.failure_reasons?.[0];
  const avgSeconds = Number.parseFloat(jobs.avg_seconds ?? "");
  const topSurfaces = Object.entries(jobs.by_surface ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([surface, count]) => `${surface} ${count}`)
    .join(" · ");
  return (
    <section className="aiws-metrics" aria-label={t("aiws.metrics.title")}>
      <h2>
        {t("aiws.metrics.title")}
        <small>{t("aiws.metrics.window").replace("{days}", String(days))}</small>
      </h2>
      <dl>
        <div>
          <dt>{t("aiws.metrics.jobs")}</dt>
          <dd>{jobs.total ?? 0}</dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.completion")}</dt>
          <dd>{pct(jobs.completion_rate) ?? "—"}</dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.proposed")}</dt>
          <dd>{commands.proposed ?? 0}</dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.applied")}</dt>
          <dd>
            {commands.applied ?? 0}
            {pct(commands.apply_rate) ? ` · ${pct(commands.apply_rate)}` : ""}
          </dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.declined")}</dt>
          <dd>{commands.declined ?? 0}</dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.artifacts")}</dt>
          <dd>{artifactsProduced ?? 0}</dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.approvals")}</dt>
          <dd>
            {approvals.decided ?? 0}/{approvals.requested ?? 0}
          </dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.avgDuration")}</dt>
          <dd>{Number.isFinite(avgSeconds) ? minutes(avgSeconds) : "—"}</dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.credits")}</dt>
          <dd>{cost.points_debited ?? 0}</dd>
        </div>
        <div>
          <dt>{t("aiws.metrics.timeSaved")}</dt>
          <dd>
            {minutes(timeSaved.seconds ?? 0)}{" "}
            <small className="aiws-metrics__estimate">{t("aiws.metrics.estimateMark")}</small>
          </dd>
        </div>
      </dl>
      {topSurfaces ? (
        <p className="aiws-metrics__failure">
          {t("aiws.metrics.bySurface").replace("{surfaces}", topSurfaces)}
        </p>
      ) : null}
      {topFailure ? (
        <p className="aiws-metrics__failure">
          {t("aiws.metrics.topFailure").replace("{code}", topFailure.code)} ({topFailure.count})
        </p>
      ) : null}
    </section>
  );
}
