import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import {
  aiAgent,
  aiJobCancel,
  aiJobList,
  aiJobMessageCreate,
  aiJobOutcomeCreate,
  aiJobRetrieve,
  aiJobRetry,
} from "../../api/generated/dekopen";
import type { AiAgentStep } from "../../api/generated/models/aiAgentStep";
import type { AiJobDetail } from "../../api/generated/models/aiJobDetail";
import { t } from "../../i18n/es-CL";
import { jobErrorKey } from "../jobs/jobError";
import type { DesignOp } from "../commands/types";
import { describeDesignOp, designAssistProduct } from "../canvas/designOps";
import type { ProductJson } from "../canvas/productEditing";
import { useDesignOpsBridge } from "./assistantContext";
import { BatchOpsStep } from "./BatchOpsStep";

/** The durable worker can leave the job running far longer than a request
 * timeout — the dock polls the job record and renders the stored result
 * once the round settles. */
const LIVE_STATES = new Set(["QUEUED", "PLANNING", "RUNNING"]);
const TERMINAL_STATES = new Set(["FAILED", "CANCELED"]);
const STATE_LABEL: Record<string, string> = {
  QUEUED: "agent.state.queued",
  PLANNING: "agent.state.planning",
  RUNNING: "agent.state.running",
  WAITING_FOR_USER: "agent.state.waiting_for_user",
  WAITING_FOR_APPROVAL: "agent.state.waiting_for_approval",
} as const;
const POLL_MS = 1500;

/** One turn in the dock thread — rebuilt from the job's durable transcript
 * so a reopened dock (or a job started elsewhere) shows the same work. */
type Turn = {
  goal: string;
  /** The server marks replayed goals — a retry is not a retyped message. */
  replay: boolean;
  /** The transcript's agent entry; null while the round is pending or on a
   * failed round (errorCode then carries the classified code). */
  result: TranscriptAgentTurn | null;
  errorCode: string | null;
  /** The product the ops steps were validated against — captured at
   * send-time; turns resumed from storage lose it (the bridge re-validates
   * at apply anyway). */
  product: { [key: string]: unknown } | null;
  /** Position of this turn's agent/error entry inside the job transcript —
   * outcomes are keyed on that index, not the thread's. */
  transcriptIndex: number;
  appliedOps: Set<number>;
  declinedOps: Set<number>;
};

interface TranscriptAgentTurn {
  role?: string;
  text?: string;
  replay?: boolean;
  reply?: string;
  queries?: { surface?: string; tool?: string; status?: string }[];
  claims?: { text?: string; evidence?: string[] }[];
  questions?: string[];
  steps?: AiAgentStep[];
  warnings?: string[];
  rejected?: { op?: string; reason?: string }[];
  artifacts?: unknown[];
  code?: string;
}

/** Transcript → thread: user entries pair with the agent/error entry that
 * answers them; a trailing user entry is a round still in flight. */
function threadFromJob(job: AiJobDetail): Turn[] {
  const turns: Turn[] = [];
  let pending: { text: string; replay: boolean } | null = null;
  const entries = (job.transcript ?? []) as TranscriptAgentTurn[];
  for (const [index, entry] of entries.entries()) {
    if (!entry || typeof entry !== "object") continue;
    if (entry.role === "user") {
      pending = { text: String(entry.text ?? ""), replay: Boolean(entry.replay) };
    } else if (entry.role === "agent") {
      turns.push({
        goal: pending?.text ?? "",
        replay: pending?.replay ?? false,
        result: entry,
        errorCode: null,
        product: null,
        transcriptIndex: index,
        appliedOps: new Set(),
        declinedOps: new Set(),
      });
      pending = null;
    } else if (entry.role === "error") {
      turns.push({
        goal: pending?.text ?? "",
        replay: pending?.replay ?? false,
        result: null,
        errorCode: typeof entry.code === "string" ? entry.code : null,
        product: null,
        transcriptIndex: index,
        appliedOps: new Set(),
        declinedOps: new Set(),
      });
      pending = null;
    }
  }
  if (pending) {
    turns.push({
      goal: pending.text,
      replay: pending.replay,
      result: null,
      errorCode: null,
      product: null,
      transcriptIndex: entries.length - 1,
      appliedOps: new Set(),
      declinedOps: new Set(),
    });
  }
  // Jobs settled before transcript turns carried the result shape still
  // hold the aggregate in `result` — surface it as the last turn rather
  // than rendering an empty conversation.
  if (!turns.some((turn) => turn.result !== null) && job.result) {
    turns.push({
      goal: job.goal ?? "",
      replay: false,
      result: job.result as TranscriptAgentTurn,
      errorCode: null,
      product: null,
      transcriptIndex: entries.length - 1,
      appliedOps: new Set(),
      declinedOps: new Set(),
    });
  }
  return turns;
}

function asDesignOps(step: AiAgentStep): DesignOp[] {
  return (step.ops ?? []).filter((item): item is DesignOp => typeof item.op === "string");
}

export const SURFACE_LABELS: Record<string, string> = {
  dashboard: "panel",
  projects: "proyectos",
  project: "proyecto",
  position: "vano",
  quotation: "cotización",
  catalog: "catálogo",
  production: "producción",
  work_order: "orden de trabajo",
  clients: "clientes",
  purchasing: "compras",
  settings: "configuración",
};

/** §08-WG — communication workflows are goals on the project/quotation
 * surface: the dock already binds the project refs, so a preset turns the
 * generic grounded agent into the five customer communications without a
 * separate surface. They only prefill the goal — the human edits before
 * sending, and the answer stays evidence-bound either way. */
const GOAL_CHIPS: Record<string, string[]> = {
  project: [
    "Convierte todas las fijas del proyecto en abatibles.",
    "Copia el vidrio del primer vano a todos los demás.",
    "Redacta el correo para enviar la cotización al cliente.",
    "Resume los cambios de la última revisión para el cliente.",
    "Redacta un recordatorio de pago pendiente.",
    "Redacta una actualización del estado de producción para el cliente.",
    "Redacta el aviso de entrega programada.",
  ],
  quotation: [
    "Redacta el correo para enviar la cotización al cliente.",
    "Resume los cambios de la última revisión para el cliente.",
    "Redacta un recordatorio de pago pendiente.",
  ],
};

/** The DEKOPEN agent: a goal turns into a server-side observe → plan loop.
 * The backend executes the queries and validates every step; this panel
 * renders provenance (what it consulted), lets the human apply design ops
 * through the canvas's own commit, and deep-links consequential actions —
 * it never executes them itself. */
export function AgentBody({
  organizationId,
  surface,
  refs,
  onJobState,
}: {
  organizationId: string;
  surface: string;
  refs: Record<string, string>;
  /** Lifts the bound job's lifecycle up to the dock header orb. */
  onJobState?: (state: string | null) => void;
}): JSX.Element {
  const navigate = useNavigate();
  const bridge = useDesignOpsBridge();
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  /** The job this dock is bound to — found by continuity on mount, created
   * by the next send when none applies. */
  const [job, setJob] = useState<AiJobDetail | null>(null);
  useEffect(() => {
    onJobState?.(job?.state ?? null);
  }, [job?.state, onJobState]);
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<Turn[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** One operation key per goal — a retried submit replays the audited loop
   * (each round is suffixed server-side) instead of debiting twice. */
  const operationKey = useRef<{ key: string; goal: string } | null>(null);
  const requestSeq = useRef(0);
  const pollTimer = useRef<number | null>(null);
  const headers = { headers: { "X-Organization-ID": organizationId } };

  const refsKey = JSON.stringify(refs);

  function clearPoll(): void {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }

  /** Poll the bound job until it settles — the transcript thread refreshes
   * on every tick so a live round visibly accumulates work. `product` is
   * this session's sent snapshot — ops turns rebind it so the stale-plan
   * guard keeps refusing after a commit swaps the live product. */
  function watch(
    jobId: string,
    seq: number,
    product: { [key: string]: unknown } | null = null,
  ): void {
    clearPoll();
    const tick = async (): Promise<void> => {
      if (seq !== requestSeq.current) return;
      try {
        const detail = await aiJobRetrieve(jobId, headers);
        if (detail.status !== 200) {
          // The job vanished or the role lost access — stop watching rather
          // than spin a dead poll.
          setBusy(false);
          return;
        }
        const next = detail.data;
        setJob(next);
        const built = threadFromJob(next);
        if (product) {
          for (const turn of built) {
            if (turn.product === null && turn.result?.steps?.some((step) => step.kind === "ops")) {
              turn.product = product;
            }
          }
        }
        setThread(built);
        if (LIVE_STATES.has(next.state)) {
          pollTimer.current = window.setTimeout(() => void tick(), POLL_MS);
        } else {
          setBusy(false);
        }
      } catch {
        // A transient poll failure is not a job failure — keep watching.
        pollTimer.current = window.setTimeout(() => void tick(), POLL_MS * 2);
      }
    };
    void tick();
  }

  /** Continuity: the dock re-binds to the newest job for this
   * (surface, refs) pair — a conversation started in the workspace or a
   * previous dock session resumes instead of resetting to a blank thread. */
  useEffect(() => {
    const seq = ++requestSeq.current;
    setThread([]);
    setJob(null);
    setMessage("");
    setBusy(false);
    operationKey.current = null;
    let cancelled = false;
    void (async () => {
      try {
        const list = await aiJobList({}, headers);
        if (cancelled || seq !== requestSeq.current) return;
        if (list.status !== 200) return;
        const items = (list.data ?? []) as AiJobDetail[];
        const match = items.find(
          (item) =>
            item.surface === surface &&
            Object.entries(refs).every(([key, value]) => String(item.refs?.[key] ?? "") === value),
        );
        if (!match) return;
        const detail = await aiJobRetrieve(match.id, headers);
        if (cancelled || seq !== requestSeq.current) return;
        if (detail.status !== 200) return;
        setJob(detail.data);
        setThread(threadFromJob(detail.data));
        if (LIVE_STATES.has(detail.data.state)) {
          setBusy(true);
          watch(detail.data.id, seq);
        }
      } catch {
        // Continuity is best-effort — a failed lookup leaves a fresh dock.
      }
    })();
    return () => {
      cancelled = true;
      clearPoll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refsKey is the
    // stable serialization of refs; surface/refs changes re-run the lookup.
  }, [organizationId, surface, refsKey]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function run(): Promise<void> {
    const trimmed = goal.trim();
    if (!trimmed || busy) return;
    // A terminal job can't take follow-ups — start a fresh one instead of
    // bouncing the message off a 409.
    const followTarget = job && !TERMINAL_STATES.has(job.state) ? job : null;
    setBusy(true);
    setMessage("");
    if (!operationKey.current || operationKey.current.goal !== trimmed) {
      operationKey.current = { key: crypto.randomUUID(), goal: trimmed };
    }
    const seq = requestSeq.current;
    // The live product rides along only on the position surface — elsewhere
    // ops steps can't be validated and are dropped server-side anyway.
    const product = surface === "position" && bridge ? bridge.product : null;
    try {
      let jobId: string;
      if (followTarget) {
        // Follow-ups continue the same durable job — transcript, plan and
        // artifacts accumulate on one record instead of fragmenting.
        const response = await aiJobMessageCreate(
          followTarget.id,
          {
            message: trimmed,
            ...(product ? { product: designAssistProduct(product as ProductJson) } : {}),
          },
          {
            headers: {
              ...headers.headers,
              "X-Operation-Key": operationKey.current.key,
            },
          },
        );
        if (response.status !== 202) {
          throw new ApiError(response.status, response.data);
        }
        jobId = followTarget.id;
      } else {
        const response = await aiAgent(
          {
            surface,
            refs,
            goal: trimmed,
            ...(product ? { product: designAssistProduct(product as ProductJson) } : {}),
            history: [],
            operation_key: operationKey.current.key,
          },
          headers,
        );
        if (response.status !== 202) {
          throw new ApiError(response.status, response.data);
        }
        jobId = String(response.data.job_id);
      }
      // Optimistic user turn — the transcript rebuild replaces it on the
      // first poll, but the goal should be visible immediately.
      setThread((prev) => [
        ...prev,
        {
          goal: trimmed,
          replay: false,
          result: null,
          errorCode: null,
          product,
          transcriptIndex: prev.length ? (prev[prev.length - 1]?.transcriptIndex ?? -1) + 1 : 0,
          appliedOps: new Set(),
          declinedOps: new Set(),
        },
      ]);
      setGoal("");
      operationKey.current = null;
      watch(jobId, seq, product);
      return;
    } catch (error) {
      if (seq !== requestSeq.current) return;
      setBusy(false);
      setMessage(
        error instanceof ApiError && typeof error.payload === "object" && error.payload !== null
          ? String(
              (error.payload as { error?: { detail?: unknown } }).error?.detail ?? t("agent.error"),
            )
          : t("agent.error"),
      );
    }
  }

  async function cancelJob(): Promise<void> {
    if (!job || !LIVE_STATES.has(job.state)) return;
    try {
      const response = await aiJobCancel(job.id, headers);
      if (response.status === 200) {
        setJob(response.data as AiJobDetail);
        setThread(threadFromJob(response.data as AiJobDetail));
        setBusy(false);
      }
    } catch {
      setMessage(t("agent.error"));
    }
  }

  async function retryJob(): Promise<void> {
    if (!job || job.state !== "FAILED_RETRYABLE" || busy) return;
    setBusy(true);
    setMessage("");
    const seq = requestSeq.current;
    try {
      const response = await aiJobRetry(job.id, headers);
      if (response.status !== 202) throw new ApiError(response.status, response.data);
      watch(job.id, seq);
    } catch {
      setBusy(false);
      setMessage(t("agent.error"));
    }
  }

  function startFresh(): void {
    clearPoll();
    setJob(null);
    setThread([]);
    setMessage("");
    setBusy(false);
    operationKey.current = null;
    inputRef.current?.focus();
  }

  /** §08 measurement — report the human's decision on a proposed step back
   * to the job. Best-effort: the server dedupes on (turn, step, action), so
   * a retry or double click can never double-count; a reporting failure
   * must never block the UI. turnIndex indexes the transcript (user turns
   * included), matching the server's own indexing. */
  function reportOutcome(
    transcriptIndex: number,
    stepIndex: number,
    action: "applied" | "declined" | "apply_failed",
    ops: { op?: string }[],
  ): void {
    if (!job) return;
    void aiJobOutcomeCreate(
      job.id,
      {
        turn_index: transcriptIndex,
        step_index: stepIndex,
        action,
        ops: ops.map((op) => op.op ?? "unknown"),
      },
      headers,
    ).catch(() => undefined);
  }

  function applyOps(turnIndex: number, stepIndex: number, ops: DesignOp[]): void {
    const turn = thread[turnIndex];
    // The bridge must still close over the exact product the ops were
    // validated against — a commit in between made them stale. Resumed
    // turns carry no snapshot (product null); the bridge's own validation
    // is the gate there.
    if (!bridge || !turn || (turn.product !== null && turn.product !== bridge.product)) return;
    try {
      bridge.apply(ops);
    } catch {
      reportOutcome(turn.transcriptIndex, stepIndex, "apply_failed", ops);
      return;
    }
    reportOutcome(turn.transcriptIndex, stepIndex, "applied", ops);
    setThread((prev) =>
      prev.map((item, i) =>
        i === turnIndex ? { ...item, appliedOps: new Set(item.appliedOps).add(stepIndex) } : item,
      ),
    );
  }

  function declineOps(turnIndex: number, stepIndex: number, ops: DesignOp[]): void {
    const turn = thread[turnIndex];
    if (!turn) return;
    reportOutcome(turn.transcriptIndex, stepIndex, "declined", ops);
    setThread((prev) =>
      prev.map((item, i) =>
        i === turnIndex ? { ...item, declinedOps: new Set(item.declinedOps).add(stepIndex) } : item,
      ),
    );
  }

  const live = job !== null && LIVE_STATES.has(job.state);
  const retryable = job !== null && job.state === "FAILED_RETRYABLE";
  const terminal = job !== null && TERMINAL_STATES.has(job.state);
  const liveProgress =
    job?.live && typeof job.live.progress === "number"
      ? Math.min(99, Math.max(0, job.live.progress))
      : null;

  return (
    <>
      <div className="ask-dock__thread">
        {thread.length === 0 && !live ? (
          <p className="ask-dock__hint">{t("agent.hint")}</p>
        ) : (
          thread.map((turn, turnIndex) => (
            <div key={turnIndex} className="ask-dock__turn">
              {turn.goal ? (
                <p className="ask-dock__question">
                  {turn.goal}
                  {turn.replay ? (
                    <span className="ask-dock__replay">{t("aiws.replayed")}</span>
                  ) : null}
                </p>
              ) : null}
              {turn.errorCode !== null ? (
                <div className="ask-dock__errorTurn">
                  <p>
                    {t(jobErrorKey(turn.errorCode))}
                    <code>{turn.errorCode}</code>
                  </p>
                  {retryable ? (
                    <button
                      type="button"
                      className="ask-dock__action"
                      title={t("aiws.retryTitle")}
                      onClick={() => void retryJob()}
                    >
                      {t("aiws.retry")}
                    </button>
                  ) : null}
                </div>
              ) : turn.result === null ? null : (
                <>
                  {turn.result.queries?.length ? (
                    <ul className="ask-dock__queries">
                      {turn.result.queries.map((query, i) => (
                        <li key={i}>
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
                  {turn.result.reply ? (
                    <p className="ask-dock__answer">{turn.result.reply}</p>
                  ) : null}
                  {turn.result.questions?.length ? (
                    <div className="ask-dock__questions">
                      {turn.result.questions.map((question, i) => (
                        <p key={i}>{question}</p>
                      ))}
                    </div>
                  ) : null}
                  {turn.result.warnings?.length ? (
                    <ul className="ask-dock__warnings">
                      {turn.result.warnings.map((warning, i) => (
                        <li key={i}>{warning}</li>
                      ))}
                    </ul>
                  ) : null}
                  {turn.result.rejected?.length ? (
                    <ul className="ask-dock__warnings">
                      {turn.result.rejected.map((item, i) => (
                        <li key={i}>
                          {item.op ?? "—"}: {item.reason}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {turn.result.steps?.length ? (
                    <div className="ask-dock__actions">
                      {turn.result.steps.map((step, stepIndex) => {
                        if (step.kind === "navigate" && step.path) {
                          return (
                            <button
                              key={stepIndex}
                              type="button"
                              className="ask-dock__action"
                              onClick={() => navigate(step.path as string)}
                            >
                              {step.label}
                            </button>
                          );
                        }
                        if (step.kind === "prepare" && step.path) {
                          return (
                            <button
                              key={stepIndex}
                              type="button"
                              className="ask-dock__action ask-dock__action--prepare"
                              title={t("agent.prepareHint")}
                              onClick={() => navigate(step.path as string)}
                            >
                              {t("agent.prepare")} {step.label}
                            </button>
                          );
                        }
                        if (step.kind === "batch_ops" && refs.project_id) {
                          const applied = turn.appliedOps.has(stepIndex);
                          return (
                            <BatchOpsStep
                              key={stepIndex}
                              step={step}
                              organizationId={organizationId}
                              projectId={refs.project_id}
                              settled={applied}
                              onSettled={(action, ops) => {
                                reportOutcome(turn.transcriptIndex, stepIndex, action, ops);
                                setThread((prev) =>
                                  prev.map((item, i) =>
                                    i === turnIndex
                                      ? {
                                          ...item,
                                          appliedOps: new Set(item.appliedOps).add(stepIndex),
                                        }
                                      : item,
                                  ),
                                );
                              }}
                            />
                          );
                        }
                        if (step.kind === "ops") {
                          const ops = asDesignOps(step);
                          if (!ops.length) return null;
                          const applied = turn.appliedOps.has(stepIndex);
                          const declined = turn.declinedOps.has(stepIndex);
                          const stale =
                            !bridge || (turn.product !== null && turn.product !== bridge.product);
                          return (
                            <div key={stepIndex} className="ask-dock__ops">
                              <ul>
                                {ops.map((op, i) => (
                                  <li key={i}>
                                    {turn.product
                                      ? describeDesignOp(
                                          op,
                                          turn.product as ProductJson,
                                          ops.slice(0, i),
                                        )
                                      : op.op}
                                  </li>
                                ))}
                              </ul>
                              <div className="ask-dock__ops-actions">
                                <button
                                  type="button"
                                  className="ask-dock__action"
                                  disabled={applied || declined || stale || !bridge}
                                  title={stale && bridge ? t("assistant.stale") : undefined}
                                  onClick={() => applyOps(turnIndex, stepIndex, ops)}
                                >
                                  {applied
                                    ? t("agent.applied")
                                    : t("assistant.apply").replace("{count}", String(ops.length))}
                                </button>
                                {!applied ? (
                                  <button
                                    type="button"
                                    className="ask-dock__action ask-dock__action--ghost"
                                    disabled={declined}
                                    onClick={() => declineOps(turnIndex, stepIndex, ops)}
                                  >
                                    {declined ? t("agent.declined") : t("agent.decline")}
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          );
                        }
                        return null;
                      })}
                    </div>
                  ) : null}
                  {turn.result.artifacts?.length ? (
                    <div className="ask-dock__artifacts">
                      {turn.result.artifacts.map((item, i) => {
                        const artifact = item as { kind?: string; title?: string };
                        return (
                          <button
                            key={i}
                            type="button"
                            className="ask-dock__artifact"
                            title={t("aiws.openWorkspace")}
                            onClick={() => (job ? navigate(`/assistant?job=${job.id}`) : undefined)}
                          >
                            {artifact.title ?? artifact.kind ?? t("aiws.inspector")}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </>
              )}
              {turnIndex === thread.length - 1 && job ? (
                <p className="ask-dock__meta">
                  <button
                    type="button"
                    className="ask-dock__meta-link"
                    onClick={() => navigate(`/assistant?job=${job.id}`)}
                  >
                    {t("aiws.openWorkspace")}
                  </button>
                  {" · "}
                  <button type="button" className="ask-dock__meta-link" onClick={startFresh}>
                    {t("aiws.new")}
                  </button>
                </p>
              ) : null}
            </div>
          ))
        )}
        {live && job ? (
          <p className="ask-dock__busy">
            {liveProgress !== null ? `${liveProgress}% · ` : ""}
            {STATE_LABEL[job.state]
              ? t(STATE_LABEL[job.state] as Parameters<typeof t>[0])
              : t("agent.thinking")}
            {" · "}
            <button type="button" className="ask-dock__meta-link" onClick={() => void cancelJob()}>
              {t("aiws.cancel")}
            </button>
          </p>
        ) : null}
      </div>
      {message ? <p className="ask-dock__error">{message}</p> : null}
      {terminal ? (
        <p className="ask-dock__error">
          {job?.state === "CANCELED" ? t("agent.canceled") : t("agent.error")}
          {" · "}
          <button type="button" className="ask-dock__meta-link" onClick={startFresh}>
            {t("aiws.new")}
          </button>
        </p>
      ) : null}
      {!goal.trim() && !terminal && (GOAL_CHIPS[surface] ?? []).length ? (
        <div className="ask-dock__chips">
          {(GOAL_CHIPS[surface] ?? []).map((preset) => (
            <button
              key={preset}
              type="button"
              className="ask-dock__chip"
              onClick={() => {
                setGoal(preset);
                inputRef.current?.focus();
              }}
            >
              {preset}
            </button>
          ))}
        </div>
      ) : null}
      {!terminal ? (
        <form
          className="ask-dock__form"
          onSubmit={(event) => {
            event.preventDefault();
            run().catch(() => undefined);
          }}
        >
          <textarea
            ref={inputRef}
            value={goal}
            maxLength={2000}
            rows={2}
            placeholder={t("agent.placeholder")}
            aria-label={t("agent.placeholder")}
            onChange={(event) => setGoal(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                run().catch(() => undefined);
              }
            }}
            disabled={busy}
          />
          <button type="submit" disabled={busy || !goal.trim()}>
            {t("agent.send")}
          </button>
        </form>
      ) : null}
    </>
  );
}
