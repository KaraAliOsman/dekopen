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
  aiJobOutcomeCreate,
  aiJobRetrieve,
  aiJobRetry,
  projectsList,
} from "../../api/generated/dekopen";
import type { AiAgentStep } from "../../api/generated/models/aiAgentStep";
import type { AiJob } from "../../api/generated/models/aiJob";
import type { AiJobDetail } from "../../api/generated/models/aiJobDetail";
import type { AiJobDetailCost } from "../../api/generated/models/aiJobDetailCost";
import type { AiJobLive } from "../../api/generated/models/aiJobLive";
import type { DesignOp } from "../commands/types";
import { describeDesignOp, designAssistProduct, productFingerprint } from "../canvas/designOps";
import type { ProductJson } from "../canvas/productEditing";
import { useAssistantContext, useDesignOpsBridge } from "./assistantContext";
import { useAssistantPresence } from "./useAssistantPresence";
import { AiMetricsCard } from "./AiMetricsCard";
import { ArtifactDetail, type Artifact } from "./ArtifactDetail";
import { BatchOpsStep } from "./BatchOpsStep";
import { BotFigure } from "./BotFigure";
import { FailureCollapse } from "./FailureCollapse";
import { Orb, orbStateFor } from "./Orb";
import { STATE_LABELS } from "./states";
import { SURFACE_LABELS } from "./surfaces";
import { jobErrorKey } from "../jobs/jobError";
import { formatMoney, shortTechnicalId } from "../../format";
import { t, type TranslationKey } from "../../i18n/es-CL";

/* ------------------------------------------------------------------ */
/* §07-H — AI workspace: durable jobs with real state, a transcript     */
/* that shows the work (plan, queries, claims, steps), and inspectable  */
/* artifacts that never disappear inside the chat scroll.               */
/* ------------------------------------------------------------------ */

const LIVE_STATES = new Set(["QUEUED", "PLANNING", "RUNNING"]);
const WAITING_STATES = new Set(["WAITING_FOR_USER", "WAITING_FOR_APPROVAL"]);

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

interface TranscriptStep {
  kind?: string;
  tool?: string;
  label?: string;
  path?: string;
  action?: string;
  ops?: { op?: string }[];
  items?: { position_id?: string }[];
}

interface TranscriptTurn {
  role?: string;
  text?: string;
  reply?: string;
  /** Set on replayed turns — the retry endpoint re-runs the original goal,
   * so the turn is marked rather than rendered as a message retyped. */
  replay?: boolean;
  plan?: { label?: string }[];
  queries?: { surface?: string; tool?: string; status?: string }[];
  claims?: { text?: string; evidence?: string[] }[];
  references?: string[];
  /** UUID → human label the backend resolved from context/observations —
   * the transcript stores ids, the UI renders the entity behind each one. */
  evidence_labels?: Record<string, string>;
  questions?: string[];
  artifacts?: Artifact[];
  steps?: TranscriptStep[];
  warnings?: string[];
  /** Ops the validator refused — shown so a silent drop never reads as
   * the model declining to act. */
  rejected?: { op?: string; reason?: string }[];
  /** Present on error turns — the durable failure code. */
  code?: string;
}

function stateLabel(state: string): string {
  const key = STATE_LABELS[state];
  return key ? t(key as never) : state;
}

/** A timestamp the rail can show without locale clutter — minutes under an
 * hour, hours under a day, then the calendar day. */
function relativeTime(iso: string | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.floor((Date.now() - then) / 60000);
  if (minutes < 1) return t("aiws.justNow");
  if (minutes < 60) return t("aiws.minutesAgo").replace("{n}", String(minutes));
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("aiws.hoursAgo").replace("{n}", String(hours));
  const days = Math.floor(hours / 24);
  if (days < 7) return t("aiws.daysAgo").replace("{n}", String(days));
  return new Date(then).toLocaleDateString("es-CL", { day: "numeric", month: "short" });
}

/** §IA3 — the worker names its own intermediate state on job_runs
 * (context/model/proposal); the band prefers that honest label over the
 * percent heuristic, which stays as the fallback for jobs that predate the
 * phase channel. */
const LIVE_PHASE_KEYS: Record<string, TranslationKey> = {
  context: "aiws.live.context",
  model: "aiws.live.model",
  proposal: "aiws.live.proposal",
};

function livePhase(live: AiJobLive | null | undefined): string {
  const phase = live && typeof live.phase === "string" ? live.phase : null;
  if (phase !== null && phase in LIVE_PHASE_KEYS) {
    return t(LIVE_PHASE_KEYS[phase] ?? "aiws.live.context");
  }
  const progress = live && typeof live.progress === "number" ? (live.progress as number) : 0;
  if (progress < 15) return t("aiws.live.queued");
  if (progress < 40) return t("aiws.live.context");
  if (progress < 70) return t("aiws.live.consulting");
  if (progress < 90) return t("aiws.live.writing");
  return t("aiws.live.finishing");
}

/** Job spend line — the attributed provider cost of this run's rounds. */
function jobCostLine(cost: AiJobDetailCost | undefined): string | null {
  if (cost === null || cost === undefined || typeof cost !== "object") return null;
  const credits = Number((cost as { credits?: unknown }).credits ?? 0);
  const tokens = Number((cost as { tokens?: unknown }).tokens ?? 0);
  const usd = (cost as { est_cost_usd?: unknown }).est_cost_usd;
  if (!Number.isFinite(credits) || credits <= 0) return null;
  return t("aiws.costLine")
    .replace("{credits}", String(credits))
    .replace("{tokens}", String(tokens))
    .replace("{usd}", typeof usd === "string" ? ` · ≈ ${formatMoney(usd, "USD")}` : "");
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
  // relativeTime computes once per render — without a tick a mounted rail
  // shows "hace 1 min" for an hour. Thirty seconds is enough granularity.
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((value) => value + 1), 30_000);
    return () => clearInterval(timer);
  }, []);
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
                <Orb state={orbStateFor(job.state)} size={20} />
                <span className="aiws-job__body">
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
                    {relativeTime(job.updated_at) ? ` · ${relativeTime(job.updated_at)}` : ""}
                    {job.artifacts?.length
                      ? ` · ${t("aiws.artifactsCount").replace("{count}", String(job.artifacts.length))}`
                      : ""}
                  </span>
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

/** A durable outcome keyed by (turn, step) — the workspace reads it so an
 * applied or declined proposal keeps its settled state across reloads
 * instead of re-offering buttons that would 409. */
type StepOutcome = { turn_index?: number; step_index?: number; action?: string };

function outcomeFor(
  outcomes: StepOutcome[],
  turnIndex: number,
  stepIndex: number,
): StepOutcome | null {
  return (
    outcomes.find((item) => item.turn_index === turnIndex && item.step_index === stepIndex) ?? null
  );
}

/** The workspace mirrors the same actionable steps the dock mounts. Ops
 * steps bind to a canvas that lives on the position surface — here they
 * deep-link to the vano, where dock continuity re-offers the apply from
 * the same job's transcript. */
function StepView({
  step,
  turnIndex,
  stepIndex,
  organizationId,
  job,
  outcomes,
  product,
  onOutcome,
}: {
  step: TranscriptStep;
  turnIndex: number;
  stepIndex: number;
  organizationId: string;
  job: AiJobDetail;
  outcomes: StepOutcome[];
  product: { [key: string]: unknown } | null;
  onOutcome: (entry: {
    turn_index: number;
    step_index: number;
    action: "applied" | "declined" | "apply_failed";
    ops: string[];
  }) => void;
}): JSX.Element | null {
  const navigate = useNavigate();
  const decided = outcomeFor(outcomes, turnIndex, stepIndex);

  if (step.kind === "ops") {
    const ops = (step.ops ?? []).filter((item): item is DesignOp => typeof item.op === "string");
    if (!ops.length) return null;
    const positionId = typeof job.refs?.position_id === "string" ? job.refs.position_id : null;
    const projectId = typeof job.refs?.project_id === "string" ? job.refs.project_id : null;
    const settledAction =
      decided?.action === "applied"
        ? t("agent.applied")
        : decided?.action === "declined"
          ? t("agent.declined")
          : null;
    return (
      <div className="aiws-step" key={`ops-${stepIndex}`}>
        <ul className="aiws-step__ops">
          {ops.map((op, i) => (
            <li key={i}>
              {product ? describeDesignOp(op, product as ProductJson, ops.slice(0, i)) : op.op}
            </li>
          ))}
        </ul>
        {settledAction ? (
          <span className="aiws-step__settled">{settledAction}</span>
        ) : positionId && projectId ? (
          <button
            type="button"
            className="aiws-action"
            title={t("aiws.opsReviewHint")}
            onClick={() => navigate(`/projects/${projectId}/positions/${positionId}/edit`)}
          >
            {t("aiws.opsReview").replace("{count}", String(ops.length))}
          </button>
        ) : null}
      </div>
    );
  }

  if (step.kind === "batch_ops") {
    const projectId = typeof job.refs?.project_id === "string" ? job.refs.project_id : null;
    if (!projectId) return null;
    return (
      <BatchOpsStep
        key={`batch-${stepIndex}`}
        // The transcript step narrows to batch_ops above — AiAgentStep wants
        // `kind` non-optional, which narrowing alone doesn't tighten.
        step={step as AiAgentStep}
        organizationId={organizationId}
        projectId={projectId}
        settled={Boolean(decided)}
        onSettled={(action, ops) =>
          onOutcome({
            turn_index: turnIndex,
            step_index: stepIndex,
            action,
            ops: ops.map((op) => op.op ?? "unknown"),
          })
        }
      />
    );
  }

  if (step.path) {
    return (
      <button
        key={`nav-${stepIndex}`}
        type="button"
        className="aiws-action"
        title={step.kind === "prepare" ? t("agent.prepareHint") : undefined}
        onClick={() => navigate(step.path as string)}
      >
        {step.kind === "prepare" ? `${t("agent.prepare")} ` : ""}
        {step.label}
        {step.tool ? <code className="aiws-tool">{step.tool}</code> : null}
      </button>
    );
  }

  return (
    <span key={`static-${stepIndex}`} className="aiws-action aiws-action--static">
      {step.label}
      {step.tool ? <code className="aiws-tool">{step.tool}</code> : null}
    </span>
  );
}

/** One agent turn: plan, reply, questions, warnings, the collapsible work
 * log (queries/claims/navigation), the actionable steps rendered
 * first-class (ops deep-link, batch ops mount, prepare deep-link), the
 * rejected ops, and the artifact cards. */
function AgentTurnView({
  turn,
  turnIndex,
  isLatest,
  organizationId,
  job,
  outcomes,
  onArtifact,
  onOutcome,
}: {
  turn: TranscriptTurn;
  turnIndex: number;
  isLatest: boolean;
  organizationId: string;
  job: AiJobDetail;
  outcomes: StepOutcome[];
  onArtifact: (a: Artifact) => void;
  onOutcome: (entry: {
    turn_index: number;
    step_index: number;
    action: "applied" | "declined" | "apply_failed";
    ops: string[];
  }) => void;
}): JSX.Element {
  const [showWork, setShowWork] = useState(false);
  // Ops were validated against the position's product at request time; the
  // job record doesn't persist it, so descriptions fall back to op labels
  // and the deep-link carries the apply to where the product lives.
  const product: { [key: string]: unknown } | null = null;
  const actionable = (turn.steps ?? []).filter((step) =>
    ["ops", "batch_ops", "prepare", "navigate"].includes(step.kind ?? ""),
  );
  const workCount = (turn.queries?.length ?? 0) + (turn.claims?.length ?? 0);
  return (
    <div className="aiws-turn aiws-turn--agent">
      <Orb state={isLatest && LIVE_STATES.has(job.state) ? "working" : "success"} size={28} />
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
        {turn.rejected?.length ? (
          <ul className="aiws-warnings aiws-warnings--rejected">
            {turn.rejected.map((item, i) => (
              <li key={i}>
                {item.op ?? "—"}: {item.reason}
              </li>
            ))}
          </ul>
        ) : null}
        {actionable.length ? (
          <div className="aiws-steps aiws-steps--live">
            {actionable.map((step) => (
              <StepView
                key={turn.steps!.indexOf(step)}
                step={step}
                turnIndex={turnIndex}
                stepIndex={turn.steps!.indexOf(step)}
                organizationId={organizationId}
                job={job}
                outcomes={outcomes}
                product={product}
                onOutcome={onOutcome}
              />
            ))}
          </div>
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
                            · {t("aiws.evidence")}:{" "}
                            {claim.evidence
                              .map((ref) => turn.evidence_labels?.[ref] ?? shortTechnicalId(ref))
                              .join(", ")}
                          </small>
                        ) : null}
                      </li>
                    ))}
                  </ul>
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
                <Orb state="idle" size={18} />
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

/** The durable error turn — a failure the job recorded in its transcript,
 * with the classified code and a retry action when the job is still
 * retryable. */
function ErrorTurnView({
  turn,
  job,
  onRetry,
  retryBusy,
}: {
  turn: TranscriptTurn;
  job: AiJobDetail;
  onRetry: () => void;
  retryBusy: boolean;
}): JSX.Element {
  return (
    <div className="aiws-turn aiws-turn--error">
      <Orb state="error" size={28} />
      <div className="aiws-turn__body">
        <FailureCollapse
          message={turn.code ? t(jobErrorKey(turn.code)) : t("jobs.fail.generic")}
          code={turn.code}
          onRetry={job.state === "FAILED_RETRYABLE" ? onRetry : undefined}
          retryBusy={retryBusy}
        />
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
  const { surface: presenceSurface, refs: presenceRefs } = useAssistantContext();
  const presence = useAssistantPresence({
    organizationId: orgId ?? null,
    surface: presenceSurface,
    refs: presenceRefs,
  });
  const selectedId = searchParams.get("job");
  const artParam = searchParams.get("art");
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

  // UUID → entity name across every turn — claims and artifact references
  // cite ids; the workspace renders the entity behind each one.
  const evidenceLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    for (const turn of transcript) {
      Object.assign(labels, turn.evidence_labels ?? {});
    }
    return labels;
  }, [transcript]);

  // Elapsed clock while a run is live — honest signal, not a percentage the
  // worker can't guarantee. Ticks only while a live job is on screen.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live]);
  const liveSince =
    (job?.live && typeof job.live.updated_at === "string"
      ? (job.live.updated_at as string)
      : undefined) ?? job?.updated_at;
  const elapsedSec = liveSince
    ? Math.max(0, Math.floor((now - new Date(liveSince).getTime()) / 1000))
    : null;

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "end" });
  }, [job?.id, transcript.length]);

  // A finished job's newest artifact surfaces in the inspector without a
  // click — the pane only stays empty when the user picked nothing yet. A
  // ?art=<index> deep link opens that shelf item instead of the newest one.
  useEffect(() => {
    if (artifact !== null) return;
    if (artParam !== null) {
      // Turn-scoped coordinates (transcriptIndex:artifactIndex) resolve on the
      // transcript — immune to the shelf's truncation; a bare number is the
      // legacy flat-shelf index.
      const coord = artParam.split(":");
      const target =
        coord.length === 2
          ? (transcript[Number(coord[0])]?.artifacts?.[Number(coord[1])] as Artifact | undefined)
          : ((job?.artifacts as Artifact[] | undefined) ?? [])[Number(artParam)];
      if (target) {
        setArtifact(target);
        return;
      }
    }
    const latest = [...transcript].reverse().find((turn) => turn.artifacts?.length);
    const first = latest?.artifacts?.[0];
    if (first) setArtifact(first);
  }, [transcript, artifact, artParam, job?.artifacts]);

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
        // Persisted on the turn — restored ops refuse onto a changed design.
        const productSig = product ? productFingerprint(product) : null;
        const response = await aiJobMessageCreate(
          job.id,
          {
            message,
            // Live refs refresh volatile pointers (the canvas selection) so a
            // follow-up's "this" resolves to what's selected now.
            refs: job.refs ?? {},
            ...(product ? { product } : {}),
            ...(productSig ? { product_sig: productSig } : {}),
          },
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

  /** §08 measurement — the workspace's apply/decline decisions feed the
   * same outcomes telemetry the dock reports; best-effort, never blocking. */
  function reportOutcome(entry: {
    turn_index: number;
    step_index: number;
    action: "applied" | "declined" | "apply_failed";
    ops: string[];
  }): void {
    if (!job || !orgId) return;
    void aiJobOutcomeCreate(job.id, entry, headers)
      .then((response) => {
        if (response.status === 200) {
          // The detail query lives at ["ai","jobs",orgId,jobId] — the prefix
          // invalidates both the list and this job's detail.
          void queryClient.invalidateQueries({ queryKey: ["ai", "jobs", orgId] });
        }
      })
      .catch(() => undefined);
  }

  async function retry(): Promise<void> {
    if (!job || !orgId || job.state !== "FAILED_RETRYABLE" || busy) return;
    setBusy(true);
    setError("");
    try {
      // The retry endpoint replays the job's own goal — it marks the
      // transcript turn as a replay instead of faking a user retype.
      const response = await aiJobRetry(job.id, headers);
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
            <Orb state={orbStateFor(job.state)} size={40} />
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
                {(job.state === "FAILED" || job.state === "FAILED_RETRYABLE") && job.error_code
                  ? ` · ${t(jobErrorKey(job.error_code))}`
                  : ""}
                {jobCostLine(job.cost) !== null ? ` · ${jobCostLine(job.cost)}` : ""}
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
        {job && live ? (
          <p className="aiws-progress" role="status">
            <span className="aiws-progress__label">
              {livePhase(job.live)}
              {elapsedSec !== null
                ? ` · ${t("aiws.live.elapsed").replace("{s}", String(elapsedSec))}`
                : ""}
            </span>
          </p>
        ) : null}
        {job && WAITING_STATES.has(job.state) ? (
          <p className="aiws-waiting" role="status">
            <Orb state={job.state === "WAITING_FOR_APPROVAL" ? "approval" : "waiting"} size={20} />
            {job.state === "WAITING_FOR_APPROVAL"
              ? t("aiws.waitingApprovalBanner")
              : t("aiws.waitingUserBanner")}
          </p>
        ) : null}
        {job && (job.artifacts?.length ?? 0) > 0 ? (
          <div className="aiws-shelf" aria-label={t("aiws.shelf")}>
            <span className="aiws-shelf__label">{t("aiws.shelf")}</span>
            {(job.artifacts as Artifact[]).map((item, i) => (
              <button
                key={i}
                type="button"
                className="aiws-shelf__item"
                onClick={() => setArtifact(item)}
              >
                {/* §P17 — la tarjeta de artefacto comunica el estado real
                 * del trabajo que la produjo. */}
                <Orb state={orbStateFor(job.state)} size={16} />
                {item.title ?? artifactKindLabel(item.kind)}
              </button>
            ))}
          </div>
        ) : null}
        <div className="aiws-transcript">
          {transcript.length === 0 && !job ? (
            <>
              <div className="aiws-hero">
                {/* §P17 — el estado vacío también deriva su figura del
                 * trabajo más reciente del contexto. */}
                <BotFigure size={160} state={presence.orbState} welcome />
                <div>
                  <h1 className="aiws-hero__title">{t("aiws.title")}</h1>
                  <AiMetricsCard organizationId={orgId ?? ""} />
                </div>
              </div>
              <p className="aiws-empty">{t("aiws.hint")}</p>
            </>
          ) : (
            transcript.map((turn, index) =>
              turn.role === "user" ? (
                <p key={index} className="aiws-turn aiws-turn--user">
                  {turn.text}
                  {turn.replay ? <span className="aiws-replay">{t("aiws.replayed")}</span> : null}
                </p>
              ) : turn.role === "error" ? (
                <ErrorTurnView
                  key={index}
                  turn={turn}
                  job={job!}
                  onRetry={() => void retry()}
                  retryBusy={busy}
                />
              ) : (
                <AgentTurnView
                  key={index}
                  turn={turn}
                  turnIndex={index}
                  isLatest={index === transcript.length - 1}
                  organizationId={orgId ?? ""}
                  job={job!}
                  outcomes={(job?.outcomes ?? []) as StepOutcome[]}
                  onArtifact={setArtifact}
                  onOutcome={reportOutcome}
                />
              ),
            )
          )}
          {live ? (
            <p className="aiws-live">
              <Orb state={orbStateFor(job?.state)} size={22} />
              {job ? livePhase(job.live) : t("agent.thinking")}
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
          noValidate
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
          <Orb state={live ? orbStateFor(job?.state) : draft.trim() ? "input" : "idle"} size={20} />
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
                {t("aiws.evidence")}:{" "}
                {artifact.references
                  .map((ref) => evidenceLabels[ref] ?? shortTechnicalId(ref))
                  .join(", ")}
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
