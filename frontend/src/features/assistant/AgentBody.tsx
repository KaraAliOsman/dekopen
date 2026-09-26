import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { aiAgent, aiJobOutcomeCreate, aiJobRetrieve } from "../../api/generated/dekopen";
import type { AiAgentResult } from "../../api/generated/models/aiAgentResult";
import type { AiAgentStep } from "../../api/generated/models/aiAgentStep";
import type { AiAgentHistoryRequest } from "../../api/generated/models/aiAgentHistoryRequest";
import type { AiJobDetail } from "../../api/generated/models/aiJobDetail";
import { t } from "../../i18n/es-CL";
import type { DesignOp } from "../commands/types";
import { describeDesignOp, designAssistProduct } from "../canvas/designOps";
import type { ProductJson } from "../canvas/productEditing";
import { useDesignOpsBridge } from "./assistantContext";
import { BatchOpsStep } from "./BatchOpsStep";

/** The durable worker can leave the job running far longer than a request
 * timeout — the dock polls the job record and renders the stored result
 * once the round settles. */
const LIVE_STATES = new Set(["QUEUED", "PLANNING", "RUNNING"]);
const STATE_LABEL: Record<string, string> = {
  QUEUED: "agent.state.queued",
  PLANNING: "agent.state.planning",
  RUNNING: "agent.state.running",
  WAITING_FOR_USER: "agent.state.waiting_for_user",
  WAITING_FOR_APPROVAL: "agent.state.waiting_for_approval",
} as const;
const POLL_MS = 1500;
const POLL_LIMIT = 160;

/** What a turn renders — the stored agent result plus the job's identity,
 * which lives on the job row (the envelope fields are not duplicated into
 * `result`). */
type AgentAnswer = AiAgentResult & { job_id: string; state: string };

function jobAnswer(job: AiJobDetail): AgentAnswer {
  return { ...(job.result as AiAgentResult), job_id: job.id, state: job.state };
}

type Turn = {
  goal: string;
  answer: AgentAnswer;
  /** The product the ops steps were validated against — a later commit makes
   * them stale, so applying them then is refused. */
  product: { [key: string]: unknown } | null;
  /** Step indexes whose proposal already committed — re-applying a consumed
   * plan would mint duplicate structural ids against a changed product. */
  appliedOps: Set<number>;
  /** Step indexes the human explicitly declined — feeds the rejection-rate
   * metric server-side. */
  declinedOps: Set<number>;
};

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
}: {
  organizationId: string;
  surface: string;
  refs: Record<string, string>;
}): JSX.Element {
  const navigate = useNavigate();
  const bridge = useDesignOpsBridge();
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [jobState, setJobState] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<Turn[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** One operation key per goal — a retried submit replays the audited loop
   * (each round is suffixed server-side) instead of debiting twice. */
  const operationKey = useRef<{ key: string; goal: string } | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function run(): Promise<void> {
    const trimmed = goal.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setMessage("");
    setJobState(null);
    if (!operationKey.current || operationKey.current.goal !== trimmed) {
      operationKey.current = { key: crypto.randomUUID(), goal: trimmed };
    }
    const seq = ++requestSeq.current;
    // The live product rides along only on the position surface — elsewhere
    // ops steps can't be validated and are dropped server-side anyway.
    const product = surface === "position" && bridge ? bridge.product : null;
    const history: AiAgentHistoryRequest[] = thread.slice(-3).flatMap((turn) => [
      { role: "user" as const, content: turn.goal.slice(0, 1900) },
      { role: "agent" as const, content: turn.answer.reply.slice(0, 1900) },
    ]);
    try {
      const response = await aiAgent(
        {
          surface,
          refs,
          goal: trimmed,
          // The ops contract validates the stable-id projection, not the raw
          // product — the same wire shape AssistantPanel sends.
          ...(product ? { product: designAssistProduct(product as ProductJson) } : {}),
          history,
          operation_key: operationKey.current.key,
        },
        { headers: { "X-Organization-ID": organizationId } },
      );
      if (response.status !== 202) {
        throw new ApiError(response.status, response.data);
      }
      const jobId = response.data.job_id;
      const headers = { headers: { "X-Organization-ID": organizationId } };
      let job: AiJobDetail | null = null;
      for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
        if (seq !== requestSeq.current) return;
        const detail = await aiJobRetrieve(jobId, headers);
        if (detail.status !== 200) throw new ApiError(detail.status, detail.data);
        job = detail.data;
        if (!LIVE_STATES.has(job.state)) break;
        setJobState(job.state);
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
      if (!job || LIVE_STATES.has(job.state)) {
        setMessage(t("agent.stillRunning"));
        return;
      }
      if (job.state === "CANCELED") {
        setMessage(t("agent.canceled"));
        return;
      }
      if (job.state.startsWith("FAILED")) {
        setMessage(t("agent.error"));
        return;
      }
      setThread((prev) => [
        ...prev,
        {
          goal: trimmed,
          answer: jobAnswer(job),
          product,
          appliedOps: new Set(),
          declinedOps: new Set(),
        },
      ]);
      setGoal("");
      operationKey.current = null;
    } catch (error) {
      if (seq !== requestSeq.current) return;
      setMessage(
        error instanceof ApiError && typeof error.payload === "object" && error.payload !== null
          ? String(
              (error.payload as { error?: { detail?: unknown } }).error?.detail ?? t("agent.error"),
            )
          : t("agent.error"),
      );
    } finally {
      if (seq === requestSeq.current) {
        setBusy(false);
        setJobState(null);
      }
    }
  }

  /** §08 measurement — report the human's decision on a proposed step back
   * to the job. Best-effort: the server dedupes on (turn, step, action), so
   * a retry or double click can never double-count; a reporting failure
   * must never block the UI. */
  function reportOutcome(
    turnIndex: number,
    stepIndex: number,
    action: "applied" | "declined" | "apply_failed",
    ops: { op?: string }[],
  ): void {
    const jobId = thread[turnIndex]?.answer.job_id;
    if (!jobId) return;
    void aiJobOutcomeCreate(
      jobId,
      {
        turn_index: turnIndex,
        step_index: stepIndex,
        action,
        ops: ops.map((op) => op.op ?? "unknown"),
      },
      { headers: { "X-Organization-ID": organizationId } },
    ).catch(() => undefined);
  }

  function applyOps(turnIndex: number, stepIndex: number, ops: DesignOp[]): void {
    const turn = thread[turnIndex];
    // The bridge must still close over the exact product the ops were
    // validated against — a commit in between made them stale.
    if (!bridge || !turn || turn.product !== bridge.product) return;
    try {
      bridge.apply(ops);
    } catch {
      reportOutcome(turnIndex, stepIndex, "apply_failed", ops);
      return;
    }
    reportOutcome(turnIndex, stepIndex, "applied", ops);
    setThread((prev) =>
      prev.map((item, i) =>
        i === turnIndex ? { ...item, appliedOps: new Set(item.appliedOps).add(stepIndex) } : item,
      ),
    );
  }

  function declineOps(turnIndex: number, stepIndex: number, ops: DesignOp[]): void {
    reportOutcome(turnIndex, stepIndex, "declined", ops);
    setThread((prev) =>
      prev.map((item, i) =>
        i === turnIndex ? { ...item, declinedOps: new Set(item.declinedOps).add(stepIndex) } : item,
      ),
    );
  }

  return (
    <>
      <div className="ask-dock__thread">
        {thread.length === 0 ? (
          <p className="ask-dock__hint">{t("agent.hint")}</p>
        ) : (
          thread.map((turn, turnIndex) => (
            <div key={turnIndex} className="ask-dock__turn">
              <p className="ask-dock__question">{turn.goal}</p>
              {turn.answer.queries.length ? (
                <ul className="ask-dock__queries">
                  {turn.answer.queries.map((query, i) => (
                    <li key={i}>
                      {query.status === "ok"
                        ? t("agent.queried").replace(
                            "{surface}",
                            SURFACE_LABELS[query.surface] ?? query.surface,
                          )
                        : t("agent.queryFailed").replace(
                            "{surface}",
                            SURFACE_LABELS[query.surface] ?? query.surface,
                          )}
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="ask-dock__answer">{turn.answer.reply}</p>
              {turn.answer.warnings?.length ? (
                <ul className="ask-dock__warnings">
                  {turn.answer.warnings.map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                </ul>
              ) : null}
              {turn.answer.rejected?.length ? (
                <ul className="ask-dock__warnings">
                  {turn.answer.rejected.map((item, i) => (
                    <li key={i}>
                      {item.op ?? "—"}: {item.reason}
                    </li>
                  ))}
                </ul>
              ) : null}
              {turn.answer.steps.length ? (
                <div className="ask-dock__actions">
                  {turn.answer.steps.map((step, stepIndex) => {
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
                            reportOutcome(turnIndex, stepIndex, action, ops);
                            setThread((prev) =>
                              prev.map((item, i) =>
                                i === turnIndex
                                  ? { ...item, appliedOps: new Set(item.appliedOps).add(stepIndex) }
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
                      const stale = !bridge || turn.product !== bridge.product;
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
              {turn.answer.artifacts?.length ? (
                <div className="ask-dock__artifacts">
                  {turn.answer.artifacts.map((item, i) => {
                    const artifact = item as { kind?: string; title?: string };
                    return (
                      <button
                        key={i}
                        type="button"
                        className="ask-dock__artifact"
                        title={t("aiws.openWorkspace")}
                        onClick={() => navigate(`/assistant?job=${turn.answer.job_id}`)}
                      >
                        {artifact.title ?? artifact.kind ?? t("aiws.inspector")}
                      </button>
                    );
                  })}
                </div>
              ) : null}
              <p className="ask-dock__meta">
                {turn.answer.model} · {turn.answer.credits_debited} {t("assistant.credits")}
                {turn.answer.job_id ? (
                  <>
                    {" · "}
                    <button
                      type="button"
                      className="ask-dock__meta-link"
                      onClick={() => navigate(`/assistant?job=${turn.answer.job_id}`)}
                    >
                      {t("aiws.openWorkspace")}
                    </button>
                  </>
                ) : null}
              </p>
            </div>
          ))
        )}
        {busy ? (
          <p className="ask-dock__busy">
            {jobState && STATE_LABEL[jobState]
              ? t(STATE_LABEL[jobState] as Parameters<typeof t>[0])
              : t("agent.thinking")}
          </p>
        ) : null}
      </div>
      {message ? <p className="ask-dock__error">{message}</p> : null}
      {!goal.trim() && (GOAL_CHIPS[surface] ?? []).length ? (
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
    </>
  );
}
