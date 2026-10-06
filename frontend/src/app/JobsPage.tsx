import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/apiMutator";
import { jobsList, jobsRetry } from "../api/generated/dekopen";
import type { JobRun } from "../api/generated/models";
import { useAuthSession } from "../auth/AuthSessionProvider";
import { AiActivityPanel } from "../features/assistant/AiActivityPanel";
import { FailureCollapse } from "../features/assistant/FailureCollapse";
import { jobErrorKey } from "../features/jobs/jobError";
import { formatDateTime } from "../format";
import { EmptyState, PageHeader } from "../ui";
import { t, tDynamic, type TranslationKey } from "../i18n/es-CL";

const STATE_KEYS: Record<string, TranslationKey> = {
  QUEUED: "jobs.state.QUEUED",
  RUNNING: "jobs.state.RUNNING",
  SUCCEEDED: "jobs.state.SUCCEEDED",
  FAILED: "jobs.state.FAILED",
  CANCELED: "jobs.state.CANCELED",
};

const TERMINAL_RETRYABLE = new Set(["FAILED", "CANCELED"]);

function typeLabel(job: JobRun): string {
  // §P17 — el backend ya sirve la etiqueta en español del registro; el
  // i18n local cubre tipos antiguos y el nombre técnico queda de último
  // recurso (nunca un token crudo cuando hay etiqueta).
  if (job.label) return job.label;
  const label = tDynamic("jobs.type", job.type);
  return label === job.type ? job.type : label;
}

/** §P17 — duración legible: de «Empezó» a «Terminó», o el tiempo en cola. */
function durationLabel(job: JobRun): string {
  const start = job.started_at ? Date.parse(job.started_at) : null;
  const end = job.completed_at ? Date.parse(job.completed_at) : null;
  const from = start ?? Date.parse(job.created_at);
  const to = end ?? Date.now();
  const seconds = Math.max(0, Math.round((to - from) / 1000));
  if (seconds < 90) return t("jobs.duration.seconds").replace("{count}", String(seconds));
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return t("jobs.duration.minutes").replace("{count}", String(minutes));
  const hours = Math.floor(minutes / 60);
  return t("jobs.duration.hours")
    .replace("{count}", String(hours))
    .replace("{rest}", String(minutes % 60));
}

/** §P17 — el resultado del trabajo en una sola línea legible: el código o
 * el paso que produjo, nunca el JSON crudo. */
function resultLabel(result: JobRun["result"]): string {
  if (result === null || result === undefined || typeof result !== "object") {
    return "—";
  }
  const record = result as Record<string, unknown>;
  for (const key of ["revision_code", "order_code", "project_code", "next_step", "status"]) {
    const value = record[key];
    if (typeof value === "string" && value !== "") return value;
    if (typeof value === "number") return String(value);
  }
  return "—";
}

interface JobFailure {
  /** The wrapper code — `job_permanent_error` wraps the domain code. */
  code: string;
  /** The domain failure — `error.detail` for permanent wraps, else the code. */
  detail: string;
}

function jobFailure(error: JobRun["error"]): JobFailure | null {
  if (error === null || error === undefined) return null;
  if (typeof error === "object" && "code" in (error as Record<string, unknown>)) {
    const record = error as Record<string, unknown>;
    const code = String(record.code);
    return { code, detail: String(record.detail ?? code) };
  }
  return { code: "", detail: String(error) };
}

/** Background work made visible: what ran, what's running, what failed —
 * with the recovery action (reintentar) next to the failure it fixes.
 * Retry stays available on every terminal job: the endpoint reauthorizes
 * the current actor, so a failure whose cause was fixed (restored access,
 * repaired storage) recovers through it. */
const PAGE_SIZE = 100;

export function JobsPage(): JSX.Element {
  const org = useAuthSession().me?.active_organization;
  // Espejo de _JOB_READERS — para roles de piso la página declara el aviso
  // de permiso en vez de disparar una consulta que el contrato rechaza.
  const canReadJobs =
    org?.role === "OWNER" || org?.role === "ESTIMATOR" || org?.role === "WORKSHOP_MANAGER";
  const [params, setParams] = useSearchParams();
  const [notice, setNotice] = useState("");
  const client = useQueryClient();
  const stateFilter = params.get("state") ?? "";
  const [pages, setPages] = useState(1);

  const query = useQuery<JobRun[]>({
    queryKey: ["jobs", "list", org?.id, stateFilter, pages],
    enabled: canReadJobs,
    // Un 403 es decisión del contrato (rol sin lectura): reintentar solo
    // alarga el "Cargando…" antes del aviso de permiso. Errores transitorios
    // sí reintentan una vez.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 403) && failureCount < 1,
    // A running job is a living row — poll fast while anything can still
    // move; idle keeps a slow beat so jobs started elsewhere still appear.
    refetchInterval: (result) =>
      (result.state.data ?? []).some((job) => job.state === "QUEUED" || job.state === "RUNNING")
        ? 4_000
        : 60_000,
    queryFn: async ({ signal }) => {
      // Older failures stay reachable: all loaded pages refresh in parallel —
      // a 4s poll must not run N serial round-trips.
      const responses = await Promise.all(
        Array.from({ length: pages }, (_, page) =>
          jobsList(
            {
              limit: PAGE_SIZE,
              offset: page * PAGE_SIZE,
              state: stateFilter === "" ? undefined : (stateFilter as never),
            },
            { signal, headers: { "X-Organization-ID": org!.id } },
          ),
        ),
      );
      const all: JobRun[] = [];
      for (const response of responses) {
        if (response.status !== 200) {
          throw new ApiError(response.status, response.data);
        }
        all.push(...response.data);
      }
      return all;
    },
  });

  const retry = useMutation({
    mutationFn: async (jobId: string) => {
      const response = await jobsRetry(jobId, {
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
    onSuccess: () => {
      setNotice(t("jobs.retryQueued"));
      void client.invalidateQueries({ queryKey: ["jobs", "list"] });
      // The shell badge counts failed jobs — refetch after requeueing.
      void client.invalidateQueries({ queryKey: ["shell", "attention"] });
    },
    onError: () => setNotice(t("jobs.retryFailed")),
  });

  const items = query.data ?? [];
  const hasMore = items.length === pages * PAGE_SIZE;
  return (
    <section className="dashboard jobs-page" aria-labelledby="page-title">
      <PageHeader
        actions={
          <label className="ui-field jobs-filter">
            <span className="ui-field__label">{t("jobs.filter.state")}</span>
            <select
              className="ui-field__input"
              value={stateFilter}
              onChange={(event) => {
                const next = new URLSearchParams(params);
                if (event.target.value === "") next.delete("state");
                else next.set("state", event.target.value);
                setParams(next, { replace: true });
              }}
            >
              <option value="">{t("jobs.filter.all")}</option>
              {Object.keys(STATE_KEYS).map((state) => (
                <option key={state} value={state}>
                  {t(STATE_KEYS[state] ?? "jobs.state.QUEUED")}
                </option>
              ))}
            </select>
          </label>
        }
        context={t("jobs.subtitle")}
        headingId="page-title"
        title={t("jobs.title")}
      />

      {notice !== "" && <p role="status">{notice}</p>}
      {org !== undefined && !canReadJobs ? (
        <p role="alert">{t("jobs.denied")}</p>
      ) : query.isPending ? (
        <p role="status">{t("dashboard.attentionLoading")}</p>
      ) : query.isError ? (
        <p role="alert">
          {query.error instanceof ApiError && query.error.status === 403
            ? t("jobs.denied")
            : t("jobs.error")}
        </p>
      ) : items.length === 0 ? (
        <EmptyState title={t("jobs.empty")} />
      ) : (
        <div className="jobs-table-wrap">
          <table className="jobs-table">
            <thead>
              <tr>
                <th scope="col">{t("jobs.col.type")}</th>
                <th scope="col">{t("jobs.col.object")}</th>
                <th scope="col">{t("jobs.col.state")}</th>
                <th scope="col">{t("jobs.col.duration")}</th>
                <th scope="col">{t("jobs.col.actor")}</th>
                <th scope="col">{t("jobs.col.result")}</th>
                <th scope="col" aria-label={t("jobs.col.actions")} />
              </tr>
            </thead>
            <tbody>
              {items.map((job) => {
                const failure = jobFailure(job.error);
                const failureKey = failure ? jobErrorKey(failure.detail) : null;
                // El código técnico solo se pliega cuando es un token
                // snake_case útil — nunca trazas ni excepciones.
                const detailCode =
                  failure && /^[a-z0-9_]+$/.test(failure.detail) ? failure.detail : null;
                return (
                  <tr key={job.id} data-state={job.state.toLowerCase()}>
                    <td>
                      <strong>{typeLabel(job)}</strong>
                    </td>
                    <td>
                      {job.object_label ?? "—"}
                      <time className="jobs-table__time" dateTime={job.created_at}>
                        {formatDateTime(job.created_at)}
                      </time>
                    </td>
                    <td>
                      <span className="status-chip" data-status={job.state.toLowerCase()}>
                        {t(STATE_KEYS[job.state] ?? "jobs.state.QUEUED")}
                      </span>
                    </td>
                    <td className="jobs-table__num">{durationLabel(job)}</td>
                    <td>{job.actor ?? t("jobs.actor.system")}</td>
                    <td>
                      {job.state === "FAILED" && failure !== null ? (
                        <FailureCollapse
                          message={failureKey ? t(failureKey) : t("jobs.fail.generic")}
                          code={detailCode}
                          attempts={job.attempt}
                          onRetry={
                            TERMINAL_RETRYABLE.has(job.state)
                              ? () => {
                                  setNotice("");
                                  retry.mutate(job.id);
                                }
                              : undefined
                          }
                          retryBusy={retry.isPending}
                        />
                      ) : job.state === "SUCCEEDED" ? (
                        resultLabel(job.result)
                      ) : job.state === "RUNNING" || job.state === "QUEUED" ? (
                        t("jobs.progress").replace("{percent}", job.progress)
                      ) : TERMINAL_RETRYABLE.has(job.state) ? (
                        <button
                          type="button"
                          className="ui-button ui-button--small"
                          disabled={retry.isPending}
                          onClick={() => {
                            setNotice("");
                            retry.mutate(job.id);
                          }}
                        >
                          {retry.isPending ? t("jobs.retrying") : t("jobs.retry")}
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="jobs-table__actions">
                      {job.ai_job_id ? (
                        <Link
                          className="ui-button ui-button--small ui-button--ghost"
                          to={`/assistant?job=${job.ai_job_id}`}
                        >
                          {t("jobs.openAssistant")}
                        </Link>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {!query.isPending && !query.isError && hasMore && (
        <button
          type="button"
          className="ui-button"
          disabled={query.isFetching}
          onClick={() => setPages((value) => value + 1)}
        >
          {query.isFetching ? t("dashboard.attentionLoading") : t("jobs.loadMore")}
        </button>
      )}
      {org != null && <AiActivityPanel orgId={org.id} isOwner={org.role === "OWNER"} />}
    </section>
  );
}
