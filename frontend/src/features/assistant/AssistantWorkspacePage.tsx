import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useAuthSession } from "../../auth/AuthSessionProvider";
import { ApiError } from "../../api/apiMutator";
import {
  aiAgent,
  aiJobCancel,
  aiJobList,
  aiJobMessageCreate,
  aiJobRetrieve,
  projectsList,
} from "../../api/generated/dekopen";
import type { AiJob } from "../../api/generated/models/aiJob";
import type { AiJobDetail } from "../../api/generated/models/aiJobDetail";
import { designAssistProduct } from "../canvas/designOps";
import type { ProductJson } from "../canvas/productEditing";
import { useDesignOpsBridge } from "./assistantContext";
import { AiMetricsCard } from "./AiMetricsCard";
import { ArtifactDetail, type Artifact } from "./ArtifactDetail";
import { Orb, type OrbState } from "./Orb";
import { jobErrorKey } from "../jobs/jobError";
import { t } from "../../i18n/es-CL";

/* ------------------------------------------------------------------ */
/* §07-H — AI workspace: durable jobs with real state, a transcript     */
/* that shows the work (plan, queries, claims, steps), and inspectable  */
/* artifacts that never disappear inside the chat scroll.               */
/* ------------------------------------------------------------------ */

const LIVE_STATES = new Set(["QUEUED", "PLANNING", "RUNNING"]);
const WAITING_STATES = new Set(["WAITING_FOR_USER", "WAITING_FOR_APPROVAL"]);

const STATE_LABELS: Record<string, string> = {
  QUEUED: "aiws.state.queued",
  PLANNING: "aiws.state.planning",
  RUNNING: "aiws.state.running",
  WAITING_FOR_USER: "aiws.state.waitingUser",
  WAITING_FOR_APPROVAL: "aiws.state.waitingApproval",
  FAILED_RETRYABLE: "aiws.state.failedRetryable",
  FAILED: "aiws.state.failed",
  SUCCEEDED: "aiws.state.succeeded",
  CANCELED: "aiws.state.canceled",
};

const SURFACE_LABELS: Record<string, string> = {
  morning_brief: "brief del día",
  purchase_plan: "plan de compras",
  production_plan: "plan de producción",
  quotation_complete: "completar cotización",
  project_from_documents: "proyecto desde documentos",
  catalog_compiler: "compilador de catálogo",
  customer_comms: "comunicación al cliente",
  dashboard: "panel",
  projects: "proyectos",
  project: "proyecto",
  position: "vano",
  quotation: "cotización",
  catalog: "catálogo",
  production: "producción",
  work_order: "orden",
  clients: "clientes",
  purchasing: "compras",
  settings: "configuración",
};

const NEW_JOB_SURFACES = [
  "morning_brief",
  "purchase_plan",
  "production_plan",
  "quotation_complete",
  "project_from_documents",
  "catalog_compiler",
  "customer_comms",
  "dashboard",
  "projects",
  "clients",
  "catalog",
  "production",
  "purchasing",
];

const GOAL_PRESETS: Record<string, string> = {
  morning_brief: "Genera el brief del día: qué necesita atención hoy y sobre qué entidades.",
  purchase_plan:
    "Prepara el plan de compras: líneas sin cubrir, proveedores elegibles y órdenes abiertas.",
  production_plan:
    "Propone el plan de producción: prioridad por entrega, material listo y estación que bloquea.",
  quotation_complete:
    "Diagnostica la cotización del proyecto: qué está listo, qué falta (diseño, precio, emisión, aprobación) y el siguiente paso.",
  project_from_documents:
    "Convierte los candidatos extraídos de los documentos del proyecto en un borrador de posiciones con su tipología.",
  catalog_compiler:
    "Compila la última importación de catálogo: qué candidatos confirman solos, qué colisiones o ambigüedades reviso yo, y qué queda bloqueado.",
  customer_comms: "Redacta el correo para enviar la cotización del proyecto al cliente.",
};

// Surfaces whose job is bound to a project — the form asks which one. The
// backend REQUIRED_REFS list is the authority; only project-bound workflows
// are launchable from the workspace (position/work_order bind via the dock).
const REF_BOUND_PROJECT_SURFACES = new Set([
  "quotation_complete",
  "project_from_documents",
  "customer_comms",
]);

const ARTIFACT_KIND_LABELS: Record<string, string> = {
  product_draft: "aiws.artifact.product",
  project_draft: "aiws.artifact.project",
  quote_draft: "aiws.artifact.quote",
  catalog_candidates: "aiws.artifact.catalog",
  catalog_review: "aiws.artifact.catalogReview",
  purchase_plan: "aiws.artifact.purchase",
  production_plan: "aiws.artifact.production",
  message: "aiws.artifact.message",
  comparison: "aiws.artifact.comparison",
  document_preview: "aiws.artifact.document",
};

interface TranscriptTurn {
  role?: string;
  text?: string;
  reply?: string;
  plan?: { label?: string }[];
  queries?: { surface?: string; tool?: string; status?: string }[];
  claims?: { text?: string; evidence?: string[] }[];
  references?: string[];
  questions?: string[];
  artifacts?: Artifact[];
  steps?: { kind?: string; tool?: string; label?: string; path?: string }[];
  warnings?: string[];
}

function stateLabel(state: string): string {
  const key = STATE_LABELS[state];
  return key ? t(key as never) : state;
}

/** The orb mirrors the durable job state so the assistant's presence
 * communicates what it is doing without reading a label. */
function orbState(state: string | undefined): OrbState {
  switch (state) {
    case "QUEUED":
    case "PLANNING":
      return "thinking";
    case "RUNNING":
      return "working";
    case "WAITING_FOR_USER":
    case "WAITING_FOR_APPROVAL":
      return "waiting";
    case "SUCCEEDED":
      return "ok";
    case "FAILED":
    case "FAILED_RETRYABLE":
    case "CANCELED":
      return "error";
    default:
      return "idle";
  }
}

const JOBS_PAGE_SIZE = 30;

function artifactKindLabel(kind: string | undefined): string {
  const key = kind ? ARTIFACT_KIND_LABELS[kind] : undefined;
  return key ? t(key as never) : (kind ?? "artefacto");
}

function JobRail({
  jobs,
  selected,
  onSelect,
  onNew,
  hasMore,
  loadingMore,
  onLoadMore,
}: {
  jobs: AiJob[];
  selected: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}): JSX.Element {
  return (
    <aside className="aiws-rail" aria-label={t("aiws.jobs")}>
      <div className="aiws-rail__head">
        <h2>{t("aiws.jobs")}</h2>
        <button type="button" className="ui-button ui-button--small" onClick={onNew}>
          {t("aiws.new")}
        </button>
      </div>
      {jobs.length === 0 ? (
        <p className="aiws-empty">{t("aiws.jobsEmpty")}</p>
      ) : (
        <ul className="aiws-joblist">
          {jobs.map((job) => (
            <li key={job.id}>
              <button
                type="button"
                className={`aiws-job ${job.id === selected ? "aiws-job--active" : ""}`}
                onClick={() => onSelect(job.id)}
              >
                <span className="aiws-job__goal">{job.goal}</span>
                <span className="aiws-job__meta">
                  <span
                    className="aiws-state"
                    data-state={job.state.toLowerCase().replace(/_/g, "-")}
                  >
                    {stateLabel(job.state)}
                  </span>
                  {" · "}
                  {SURFACE_LABELS[job.surface] ?? job.surface}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {hasMore ? (
        <button
          type="button"
          className="ui-button ui-button--small aiws-more"
          disabled={loadingMore}
          onClick={onLoadMore}
        >
          {t("aiws.loadMore")}
        </button>
      ) : null}
    </aside>
  );
}

function AgentTurnView({
  turn,
  onArtifact,
}: {
  turn: TranscriptTurn;
  onArtifact: (a: Artifact) => void;
}): JSX.Element {
  const navigate = useNavigate();
  const [showWork, setShowWork] = useState(false);
  const workCount =
    (turn.queries?.length ?? 0) + (turn.claims?.length ?? 0) + (turn.steps?.length ?? 0);
  return (
    <div className="aiws-turn aiws-turn--agent">
      <Orb state="idle" size={24} />
      <div className="aiws-turn__body">
      {turn.plan?.length ? (
        <ol className="aiws-plan">
          {turn.plan.map((step, i) => (
            <li key={i}>{step.label}</li>
          ))}
        </ol>
      ) : null}
      <p className="aiws-reply">{turn.reply}</p>
      {turn.questions?.length ? (
        <div className="aiws-questions">
          {turn.questions.map((question, i) => (
            <p key={i}>{question}</p>
          ))}
        </div>
      ) : null}
      {turn.warnings?.length ? (
        <ul className="aiws-warnings">
          {turn.warnings.map((warning, i) => (
            <li key={i}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {workCount > 0 ? (
        <>
          <button
            type="button"
            className="aiws-toggle"
            aria-expanded={showWork}
            onClick={() => setShowWork((v) => !v)}
          >
            {t("aiws.work")} ({workCount})
          </button>
          {showWork ? (
            <div className="aiws-work">
              {turn.queries?.length ? (
                <ul>
                  {turn.queries.map((query, i) => (
                    <li key={i}>
                      {query.tool ? <code className="aiws-tool">{query.tool}</code> : null}
                      {query.status === "ok"
                        ? t("agent.queried").replace(
                            "{surface}",
                            SURFACE_LABELS[query.surface ?? ""] ?? query.surface ?? "",
                          )
                        : t("agent.queryFailed").replace(
                            "{surface}",
                            SURFACE_LABELS[query.surface ?? ""] ?? query.surface ?? "",
                          )}
                    </li>
                  ))}
                </ul>
              ) : null}
              {turn.claims?.length ? (
                <ul className="aiws-claims">
                  {turn.claims.map((claim, i) => (
                    <li key={i}>
                      {claim.text}
                      {claim.evidence?.length ? (
                        <small>
                          {" "}
                          · {t("aiws.evidence")}: {claim.evidence.join(", ")}
                        </small>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              {turn.steps?.length ? (
                <div className="aiws-steps">
                  {turn.steps.map((step, i) =>
                    step.path ? (
                      <button
                        key={i}
                        type="button"
                        className="aiws-action"
                        onClick={() => navigate(step.path as string)}
                      >
                        {step.kind === "prepare" ? `${t("agent.prepare")} ` : ""}
                        {step.label}
                        {step.tool ? <code className="aiws-tool">{step.tool}</code> : null}
                      </button>
                    ) : (
                      <span key={i} className="aiws-action aiws-action--static">
                        {step.label}
                        {step.tool ? <code className="aiws-tool">{step.tool}</code> : null}
                      </span>
                    ),
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
      {turn.artifacts?.length ? (
        <div className="aiws-artifacts">
          {turn.artifacts.map((artifact, i) => (
            <button
              key={i}
              type="button"
              className="aiws-artifact"
              onClick={() => onArtifact(artifact)}
            >
              <strong>{artifact.title ?? artifactKindLabel(artifact.kind)}</strong>
              <small>{artifactKindLabel(artifact.kind)}</small>
            </button>
          ))}
        </div>
      ) : null}
      </div>
    </div>
  );
}

export function AssistantWorkspacePage(): JSX.Element {
  const auth = useAuthSession();
  const bridge = useDesignOpsBridge();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const orgId = auth.me?.active_organization?.id ?? null;
  const selectedId = searchParams.get("job");
  const [draft, setDraft] = useState("");
  const [newSurface, setNewSurface] = useState("dashboard");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [olderJobs, setOlderJobs] = useState<AiJob[]>([]);
  const [hasMoreJobs, setHasMoreJobs] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [newProjectId, setNewProjectId] = useState("");
  const transcriptEnd = useRef<HTMLDivElement>(null);
  // One operation key per draft: a retry/double-submit of the same message
  // replays server-side instead of re-debiting the wallet for a fresh round.
  const operationKey = useRef<{ key: string; draft: string } | null>(null);

  const headers = useMemo(() => ({ headers: { "X-Organization-ID": orgId ?? "" } }), [orgId]);

  const jobsQuery = useQuery({
    queryKey: ["ai", "jobs", orgId],
    enabled: Boolean(orgId),
    queryFn: async () => {
      const response = await aiJobList(undefined, headers);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data as unknown as AiJob[];
    },
    refetchInterval: (query) =>
      query.state.data?.some((job) => LIVE_STATES.has(job.state)) ? 4000 : false,
  });

  const jobQuery = useQuery({
    queryKey: ["ai", "jobs", orgId, selectedId],
    enabled: Boolean(orgId && selectedId),
    queryFn: async () => {
      const response = await aiJobRetrieve(selectedId ?? "", headers);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data as unknown as AiJobDetail;
    },
    refetchInterval: (query) =>
      query.state.data && LIVE_STATES.has(query.state.data.state) ? 2000 : false,
  });

  const job = jobQuery.data ?? null;

  const projectPickerQuery = useQuery({
    queryKey: ["ai", "project-picker", orgId],
    enabled: Boolean(orgId && REF_BOUND_PROJECT_SURFACES.has(newSurface) && !job),
    queryFn: async () => {
      const response = await projectsList(headers);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
  });
  const transcript = (job?.transcript ?? []) as TranscriptTurn[];
  const live = job !== null && LIVE_STATES.has(job.state);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "end" });
  }, [job?.id, transcript.length]);

  // A finished job's newest artifact surfaces in the inspector without a
  // click — the pane only stays empty when the user picked nothing yet.
  useEffect(() => {
    if (artifact !== null) return;
    const latest = [...transcript].reverse().find((turn) => turn.artifacts?.length);
    const first = latest?.artifacts?.[0];
    if (first) setArtifact(first);
  }, [transcript, artifact]);

  async function send(): Promise<void> {
    const message = draft.trim();
    if (!message || busy || !orgId) return;
    if (!operationKey.current || operationKey.current.draft !== message) {
      operationKey.current = { key: crypto.randomUUID(), draft: message };
    }
    setBusy(true);
    setError("");
    try {
      if (job) {
        // Follow-ups carry the live product on position jobs — design ops
        // validate against the current design, not a snapshot from creation.
        const product =
          job.surface === "position" && bridge
            ? designAssistProduct(bridge.product as ProductJson)
            : null;
        const response = await aiJobMessageCreate(
          job.id,
          { message, ...(product ? { product } : {}) },
          { headers: { ...headers.headers, "X-Operation-Key": operationKey.current.key } },
        );
        if (response.status !== 202) {
          throw new ApiError(response.status, response.data);
        }
      } else {
        const needsProject = REF_BOUND_PROJECT_SURFACES.has(newSurface);
        if (needsProject && !newProjectId) {
          setError(t("aiws.project_required"));
          setBusy(false);
          return;
        }
        const response = await aiAgent(
          {
            surface: newSurface,
            refs: needsProject ? { project_id: newProjectId } : {},
            goal: message,
            history: [],
            operation_key: operationKey.current.key,
          },
          headers,
        );
        if (response.status !== 202) {
          throw new ApiError(response.status, response.data);
        }
        const jobId = (response.data as { job_id?: string }).job_id;
        if (jobId) setSearchParams({ job: jobId });
      }
      setDraft("");
      operationKey.current = null;
      await queryClient.invalidateQueries({ queryKey: ["ai", "jobs", orgId] });
    } catch (cause) {
      setError(
        cause instanceof ApiError && typeof cause.payload === "object" && cause.payload !== null
          ? String(
              (cause.payload as { error?: { detail?: unknown } }).error?.detail ?? t("agent.error"),
            )
          : t("agent.error"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancel(): Promise<void> {
    if (!job || !orgId) return;
    const response = await aiJobCancel(job.id, headers);
    if (response.status === 200) {
      await queryClient.invalidateQueries({ queryKey: ["ai", "jobs", orgId] });
    }
  }

  async function retry(): Promise<void> {
    if (!job || !orgId || job.state !== "FAILED_RETRYABLE" || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await aiJobMessageCreate(
        job.id,
        { message: t("aiws.retryMessage") },
        { headers: { ...headers.headers, "X-Operation-Key": crypto.randomUUID() } },
      );
      if (response.status !== 202) throw new ApiError(response.status, response.data);
      await queryClient.invalidateQueries({ queryKey: ["ai", "jobs", orgId] });
    } catch {
      setError(t("agent.error"));
    } finally {
      setBusy(false);
    }
  }

  const firstJobs = useMemo(() => jobsQuery.data ?? [], [jobsQuery.data]);
  const jobs = useMemo(() => {
    const seen = new Set(firstJobs.map((j) => j.id));
    return [...firstJobs, ...olderJobs.filter((j) => !seen.has(j.id))];
  }, [firstJobs, olderJobs]);
  const hasMore = olderJobs.length > 0 ? hasMoreJobs : firstJobs.length === JOBS_PAGE_SIZE;

  async function loadOlder(): Promise<void> {
    const last = jobs[jobs.length - 1];
    if (!last) return;
    setLoadingMore(true);
    try {
      const response = await aiJobList({ before: last.created_at, before_id: last.id }, headers);
      if (response.status === 200) {
        const page = response.data as unknown as AiJob[];
        setOlderJobs((prev) => [...prev, ...page]);
        setHasMoreJobs(page.length === JOBS_PAGE_SIZE);
      }
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="aiws" aria-busy={busy}>
      <JobRail
        jobs={jobs}
        selected={selectedId}
        hasMore={hasMore}
        loadingMore={loadingMore}
        onLoadMore={() => void loadOlder()}
        onSelect={(id) => {
          setArtifact(null);
          setSearchParams({ job: id });
        }}
        onNew={() => {
          setArtifact(null);
          setSearchParams({});
        }}
      />
      <div className="aiws-main">
        {job ? (
          <header className="aiws-head">
            <Orb state={orbState(job.state)} size={40} />
            <div>
              <h1>{job.goal}</h1>
              <p className="aiws-head__meta">
                <span
                  className="aiws-state"
                  data-state={job.state.toLowerCase().replace(/_/g, "-")}
                >
                  {stateLabel(job.state)}
                </span>
                {" · "}
                {SURFACE_LABELS[job.surface] ?? job.surface}
                {job.error_code ? ` · ${t(jobErrorKey(job.error_code))}` : ""}
              </p>
            </div>
            <div className="aiws-head__actions">
              {job.state === "FAILED_RETRYABLE" ? (
                <button
                  type="button"
                  className="ui-button ui-button--small"
                  disabled={busy}
                  onClick={() => void retry()}
                >
                  {t("aiws.retry")}
                </button>
              ) : null}
              {live || WAITING_STATES.has(job.state) ? (
                <button
                  type="button"
                  className="ui-button ui-button--small ui-button--danger"
                  onClick={() => void cancel()}
                >
                  {t("aiws.cancel")}
                </button>
              ) : null}
            </div>
          </header>
        ) : null}
        <div className="aiws-transcript">
          {transcript.length === 0 && !job ? (
            <>
              <div className="aiws-hero">
                <Orb state="idle" size={64} />
                <AiMetricsCard organizationId={orgId ?? ""} />
              </div>
              <p className="aiws-empty">{t("aiws.hint")}</p>
            </>
          ) : (
            transcript.map((turn, index) =>
              turn.role === "user" ? (
                <p key={index} className="aiws-turn aiws-turn--user">
                  {turn.text}
                </p>
              ) : (
                <AgentTurnView key={index} turn={turn} onArtifact={setArtifact} />
              ),
            )
          )}
          {live ? (
            <p className="aiws-live">
              <Orb state="working" size={22} />
              {t("agent.thinking")}
            </p>
          ) : null}
          <div ref={transcriptEnd} />
        </div>
        {error ? (
          <p role="alert" className="aiws-error">
            {error}
          </p>
        ) : null}
        <form
          className="aiws-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          {!job ? (
            <select
              value={newSurface}
              onChange={(event) => {
                const surface = event.target.value;
                setNewSurface(surface);
                const preset = GOAL_PRESETS[surface];
                setDraft((current) =>
                  preset && (!current.trim() || Object.values(GOAL_PRESETS).includes(current))
                    ? preset
                    : current,
                );
              }}
              aria-label={t("aiws.surface")}
            >
              {NEW_JOB_SURFACES.map((surface) => (
                <option key={surface} value={surface}>
                  {SURFACE_LABELS[surface] ?? surface}
                </option>
              ))}
            </select>
          ) : null}
          {!job && REF_BOUND_PROJECT_SURFACES.has(newSurface) ? (
            <select
              value={newProjectId}
              onChange={(event) => setNewProjectId(event.target.value)}
              aria-label={t("aiws.project")}
              disabled={projectPickerQuery.isLoading}
            >
              <option value="">{t("aiws.project_pick")}</option>
              {(projectPickerQuery.data ?? []).map((project) => (
                <option key={project.id} value={project.id}>
                  {project.code} — {project.name}
                </option>
              ))}
            </select>
          ) : null}
          <textarea
            value={draft}
            rows={2}
            maxLength={2000}
            placeholder={job ? t("aiws.followup") : t("agent.placeholder")}
            aria-label={job ? t("aiws.followup") : t("agent.placeholder")}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            disabled={busy || live}
          />
          <button
            type="submit"
            disabled={
              busy ||
              live ||
              !draft.trim() ||
              (!job && REF_BOUND_PROJECT_SURFACES.has(newSurface) && !newProjectId)
            }
          >
            {t("agent.send")}
          </button>
        </form>
      </div>
      <aside className="aiws-inspector" aria-label={t("aiws.inspector")}>
        {artifact ? (
          <div className="aiws-artifact-detail">
            <header>
              <h2>{artifact.title ?? artifactKindLabel(artifact.kind)}</h2>
              <p className="aiws-head__meta">{artifactKindLabel(artifact.kind)}</p>
            </header>
            {artifact.references?.length ? (
              <p className="aiws-evidence">
                {t("aiws.evidence")}: {artifact.references.join(", ")}
              </p>
            ) : null}
            <ArtifactDetail artifact={artifact} />
          </div>
        ) : (
          <p className="aiws-empty">{t("aiws.inspectorEmpty")}</p>
        )}
      </aside>
    </section>
  );
}
