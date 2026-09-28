import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/apiMutator";
import { jobsList, jobsRetry } from "../api/generated/dekopen";
import type { JobRun } from "../api/generated/models";
import { useAuthSession } from "../auth/AuthSessionProvider";
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

function typeLabel(type: string): string {
  return tDynamic("jobs.type", type);
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
  const [params, setParams] = useSearchParams();
  const [notice, setNotice] = useState("");
  const client = useQueryClient();
  const stateFilter = params.get("state") ?? "";
  const [pages, setPages] = useState(1);

  const query = useQuery<JobRun[]>({
    queryKey: ["jobs", "list", org?.id, stateFilter, pages],
    enabled: org !== undefined,
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
      {query.isPending ? (
        <p role="status">{t("dashboard.attentionLoading")}</p>
      ) : query.isError ? (
        <p role="alert">{t("jobs.error")}</p>
      ) : items.length === 0 ? (
        <EmptyState title={t("jobs.empty")} />
      ) : (
        <ul className="jobs-list">
          {items.map((job) => {
            const failure = jobFailure(job.error);
            const failureKey = failure ? jobErrorKey(failure.detail) : null;
            return (
              <li key={job.id} className="job-row" data-state={job.state.toLowerCase()}>
                <div className="job-row-main">
                  <strong>{typeLabel(job.type)}</strong>
                  <span className="status-chip" data-status={job.state.toLowerCase()}>
                    {t(STATE_KEYS[job.state] ?? "jobs.state.QUEUED")}
                  </span>
                  {job.ai_job_id ? (
                    <Link
                      className="ui-button ui-button--small ui-button--ghost"
                      to={`/assistant?job=${job.ai_job_id}`}
                    >
                      {t("jobs.openAssistant")}
                    </Link>
                  ) : null}
                </div>
                <div className="job-row-meta">
                  <span>
                    {t("jobs.attempt")
                      .replace("{attempt}", String(job.attempt))
                      .replace("{max}", String(job.max_attempts))}
                  </span>
                  <span>{t("jobs.progress").replace("{percent}", job.progress)}</span>
                  <time dateTime={job.created_at}>{formatDateTime(job.created_at)}</time>
                </div>
                {job.state === "FAILED" && failure !== null && failureKey !== null && (
                  <p className="job-row-error">
                    {t(failureKey)}
                    {/* A snake_case domain code is a useful diagnostic tail;
                        exception text (IntegrityError:, tracebacks) is not —
                        it never reaches the user. */}
                    {/^[a-z0-9_]+$/.test(failure.detail) && failure.detail !== failureKey && (
                      <>
                        {" "}
                        <code className="job-row-code">{failure.detail}</code>
                      </>
                    )}
                  </p>
                )}
                {TERMINAL_RETRYABLE.has(job.state) && (
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
                )}
              </li>
            );
          })}
        </ul>
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
    </section>
  );
}
