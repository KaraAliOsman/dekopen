import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

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
import { designAssistProduct, productFingerprint } from "../canvas/designOps";
import { applyPositionOps, applyProjectOps, splitOps } from "./positionOps";
import type { ProductJson } from "../canvas/productEditing";
import { stableRefs, useDesignOpsBridge } from "./assistantContext";
import { BatchOpsStep } from "./BatchOpsStep";
import { BotFigure } from "./BotFigure";
import { OpsProposalCard } from "./OpsProposalCard";
import { FailureCollapse } from "./FailureCollapse";
import { SURFACE_LABELS } from "./surfaces";

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
const POLL_BACKOFF_MAX_MS = 15_000;
const POLL_FAIL_BANNER_AT = 3;

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
   * send-time; turns resumed from storage lose it and carry the durable
   * product_sig fingerprint instead (server-persisted on the user turn). */
  product: { [key: string]: unknown } | null;
  /** Fingerprint of the product this round's ops were validated against —
   * survives reload via the transcript so a restored apply still refuses
   * onto a changed design. */
  productSig: string | null;
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
  product_sig?: string;
  reply?: string;
  queries?: { surface?: string; tool?: string; status?: string }[];
  claims?: { text?: string; evidence?: string[] }[];
  questions?: string[];
  steps?: AiAgentStep[];
  warnings?: string[];
  rejected?: { op?: string; reason?: string }[];
  artifacts?: unknown[];
  code?: string;
  /** IA2 §3 — aclaración tipada: una pregunta con opciones reales que la
   * UI muestra como chips; la respuesta continúa el MISMO job. */
  clarify?: { question?: string; options?: { value?: string; label?: string }[] } | null;
}

/** Transcript → thread: user entries pair with the agent/error entry that
 * answers them; a trailing user entry is a round still in flight. */
function threadFromJob(job: AiJobDetail): Turn[] {
  const turns: Turn[] = [];
  let pending: { text: string; replay: boolean; sig: string | null } | null = null;
  const entries = (job.transcript ?? []) as TranscriptAgentTurn[];
  for (const [index, entry] of entries.entries()) {
    if (!entry || typeof entry !== "object") continue;
    if (entry.role === "user") {
      pending = {
        text: String(entry.text ?? ""),
        replay: Boolean(entry.replay),
        sig: typeof entry.product_sig === "string" ? entry.product_sig : null,
      };
    } else if (entry.role === "agent") {
      turns.push({
        goal: pending?.text ?? "",
        replay: pending?.replay ?? false,
        result: entry,
        errorCode: null,
        product: null,
        productSig: pending?.sig ?? null,
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
        productSig: pending?.sig ?? null,
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
      productSig: pending.sig,
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
      productSig: null,
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

/** El producto contra el que se propuso el turno: la copia enviada en la
 * sesión, o el producto vivo cuando su huella coincide con la persistida.
 * Sin match no hay referencia válida — las ops de producto son obsoletas
 * (stale) y se dibujan con su nombre de registro, no con descripción. */
function proposalProduct(turn: Turn, live: unknown): ProductJson | null {
  if (turn.product) return turn.product as ProductJson;
  if (!live || !turn.productSig) return null;
  try {
    return productFingerprint(designAssistProduct(live as ProductJson)) === turn.productSig
      ? (live as ProductJson)
      : null;
  } catch {
    return null;
  }
}

export { SURFACE_LABELS };

/** §08-WG — communication workflows are goals on the project/quotation
 * surface: the dock already binds the project refs, so a preset turns the
 * generic grounded agent into the five customer communications without a
 * separate surface. They only prefill the goal — the human edits before
 * sending, and the answer stays evidence-bound either way. */
const GOAL_CHIPS: Record<string, string[]> = {
  // §P17 — el dock contextual ofrece sugerencias de la pantalla real: en el
  // editor son propuestas de diseño sobre el modelo; en precios, lecturas
  // del motor; cada frase cae dentro de lo que el agente sabe ejecutar.
  position: [
    "Divide la hoja en dos oscilobatientes",
    "Proponer división 1/3–2/3",
    "Revisar compatibilidad de herrajes",
    "¿Cuánto pesa la hoja derecha?",
  ],
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
    "Explica por qué subió el total",
    "¿Qué falta para emitir la revisión?",
    "Redacta el correo para enviar la cotización al cliente.",
    "Resume los cambios de la última revisión para el cliente.",
    "Redacta un recordatorio de pago pendiente.",
  ],
  production: [
    "¿Qué órdenes están bloqueadas o atrasadas?",
    "¿Qué falta para liberar la próxima OT?",
  ],
  work_order: [
    "¿Qué pasos quedan pendientes en esta OT?",
    "¿Hay material faltante para esta orden?",
  ],
  purchasing: [
    "Arma el plan de compras con las líneas sin cobertura.",
    "¿Qué pedidos siguen abiertos?",
  ],
  dashboard: ["¿Qué requiere mi atención hoy?", "¿Qué órdenes de producción están atrasadas?"],
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
  onComposing,
}: {
  organizationId: string;
  surface: string;
  refs: Record<string, string>;
  /** Lifts the bound job's lifecycle up to the dock header orb. */
  onJobState?: (state: string | null) => void;
  /** Lifts composition state — while a goal is typed the orb reads INPUT. */
  onComposing?: (composing: boolean) => void;
}): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const bridge = useDesignOpsBridge();
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  /** The job this dock is bound to — found by continuity on mount, created
   * by the next send when none applies. */
  const [job, setJob] = useState<AiJobDetail | null>(null);
  useEffect(() => {
    onJobState?.(job?.state ?? null);
  }, [job?.state, onJobState]);
  useEffect(() => {
    onComposing?.(!!goal.trim());
  }, [goal, onComposing]);
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<Turn[]>([]);
  /** Instructions typed while a run is live — the backend can't interleave
   * a second run, so they queue client-side and post once the job settles. */
  const [pending, setPending] = useState<string[]>([]);
  const pendingRef = useRef<string[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** One operation key per goal — a retried submit replays the audited loop
   * (each round is suffixed server-side) instead of debiting twice. */
  const operationKey = useRef<{ key: string; goal: string } | null>(null);
  const requestSeq = useRef(0);
  const pollTimer = useRef<number | null>(null);
  const pollFailures = useRef(0);
  /** Persistent poll loss — the live run is probably still working, the dock
   * just can't see it right now. */
  const [offline, setOffline] = useState(false);
  const headers = { headers: { "X-Organization-ID": organizationId } };

  // Continuity keys on the stable identity refs — a canvas selection change
  // must not re-run the bind (it would churn the dock on every click), while
  // the full refs still travel with each request for context.
  const refsKey = JSON.stringify(stableRefs(refs));

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
        pollFailures.current = 0;
        setOffline(false);
        const built = threadFromJob(next);
        if (product) {
          for (const turn of built) {
            // Restored turns (productSig set) keep their durable fingerprint —
            // backfilling the live product onto them would let stale ops
            // apply onto a changed design.
            if (
              turn.product === null &&
              turn.productSig === null &&
              turn.result?.steps?.some((step) => step.kind === "ops")
            ) {
              turn.product = product;
            }
          }
        }
        setThread(built);
        if (LIVE_STATES.has(next.state)) {
          pollTimer.current = window.setTimeout(() => void tick(), POLL_MS);
        } else {
          setBusy(false);
          // Queued instructions flush in the job-state effect — it runs
          // after this render commits, even if one queued mid-settle.
        }
      } catch {
        // A transient poll failure is not a job failure — back off
        // exponentially (2× to a 15s cap) and surface the offline state
        // once it is clearly persistent, not a single blip.
        pollFailures.current += 1;
        if (pollFailures.current >= POLL_FAIL_BANNER_AT) setOffline(true);
        const delay = Math.min(POLL_BACKOFF_MAX_MS, POLL_MS * 2 ** pollFailures.current);
        pollTimer.current = window.setTimeout(() => void tick(), delay);
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
    pendingRef.current = [];
    setPending([]);
    operationKey.current = null;
    let cancelled = false;
    void (async () => {
      try {
        const list = await aiJobList({}, headers);
        if (cancelled || seq !== requestSeq.current) return;
        if (list.status !== 200) return;
        const items = (list.data ?? []) as AiJobDetail[];
        // Volatile refs (a live canvas selection) never key the durable job —
        // match on the stable identity refs only.
        const identity = stableRefs(refs);
        // Symmetric match: a job stored with extra refs (e.g. the editor's
        // project_id pair) must not bind to a bare-surface dock — subset
        // matching re-keys a position job onto every position route.
        const match = items.find(
          (item) =>
            item.surface === surface &&
            Object.keys(identity).length === Object.keys(item.refs ?? {}).length &&
            Object.entries(identity).every(
              ([key, value]) => String(item.refs?.[key] ?? "") === value,
            ),
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
    if (!trimmed) return;
    // A terminal job can't take follow-ups — start a fresh one instead of
    // bouncing the message off a 409.
    const followTarget = job && !TERMINAL_STATES.has(job.state) ? job : null;
    if (followTarget && LIVE_STATES.has(followTarget.state)) {
      // Mid-run instructions are accepted and delivered once the run
      // settles — the claim chain can't interleave a second run anyway.
      pendingRef.current = [...pendingRef.current, trimmed];
      setPending(pendingRef.current);
      setGoal("");
      return;
    }
    if (busy) return;
    await send(trimmed);
  }

  async function send(trimmed: string): Promise<void> {
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
    // The sig persists on the user turn — a restored ops step applies only
    // while the live product still matches what the ops validated against.
    const productSig = product
      ? productFingerprint(designAssistProduct(product as ProductJson))
      : null;
    try {
      let jobId: string;
      if (followTarget) {
        // Follow-ups continue the same durable job — transcript, plan and
        // artifacts accumulate on one record instead of fragmenting.
        const response = await aiJobMessageCreate(
          followTarget.id,
          {
            message: trimmed,
            // Live refs refresh volatile pointers (the canvas selection) so
            // a follow-up's "this" resolves to what's selected now.
            refs,
            ...(product ? { product: designAssistProduct(product as ProductJson) } : {}),
            ...(productSig ? { product_sig: productSig } : {}),
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
            ...(productSig ? { product_sig: productSig } : {}),
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
          productSig,
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
    // Instructions queued against the old job belong to its conversation —
    // leaving them queued would post them onto the NEXT job the dock binds.
    pendingRef.current = [];
    setPending([]);
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
    if (!turn) return;
    // IA2 — el arreglo puede mezclar tres ejecuciones reales: ops de
    // producto (canvas), de campos de la posición viva (PUT) y de lista de
    // posiciones del proyecto (create/duplicate/remove/update). Cada grupo
    // reporta su resultado por separado — un fallo en uno no bloquea los
    // otros ni infla el conteo de aplicadas.
    const groups = splitOps(ops);
    // Misma regla que dibuja el plan como obsoleto: sin producto de
    // referencia (snapshot o huella coincidente) el plan no aplica.
    const staleProduct =
      groups.product.length > 0 &&
      (!bridge || proposalProduct(turn, bridge.product) !== bridge.product);
    if (groups.product.length > 0 && staleProduct) return;

    const failures: DesignOp[] = [];
    const applied: DesignOp[] = [];
    const after = (): void => {
      if (applied.length) {
        reportOutcome(turn.transcriptIndex, stepIndex, "applied", applied);
      }
      if (failures.length) {
        reportOutcome(turn.transcriptIndex, stepIndex, "apply_failed", failures);
      }
      setThread((prev) =>
        prev.map((item, i) =>
          // IA2 — "Aplicado" sólo cuando todo el paso aplicó: un éxito
          // parcial o un fallo deja el mensaje de error visible y el paso
          // no se marca, para que la insignia nunca mienta.
          i === turnIndex
            ? {
                ...item,
                appliedOps: failures.length
                  ? item.appliedOps
                  : new Set(item.appliedOps).add(stepIndex),
              }
            : item,
        ),
      );
      void queryClient.invalidateQueries({ queryKey: ["project-pages"] });
      void queryClient.invalidateQueries({ queryKey: ["project", organizationId] });
    };

    if (groups.product.length > 0 && bridge) {
      try {
        bridge.apply(groups.product);
        applied.push(...groups.product);
      } catch {
        failures.push(...groups.product);
      }
    }

    const positionId = refs.position_id;
    const projectId = refs.project_id;
    const asyncOps: Promise<void>[] = [];
    if (groups.position.length > 0 && positionId) {
      asyncOps.push(
        applyPositionOps(groups.position, positionId, headers).then((outcome) => {
          applied.push(...outcome.applied);
          failures.push(...outcome.failed.map((item) => item.op));
          if (outcome.failed.length) {
            setMessage(t("agent.opFailed").replace("{detail}", outcome.failed[0]?.error ?? ""));
          }
        }),
      );
    } else if (groups.position.length > 0) {
      failures.push(...groups.position);
    }
    if (groups.project.length > 0 && projectId) {
      asyncOps.push(
        applyProjectOps(
          groups.project,
          { projectId, fallbackPositionId: positionId ?? null },
          headers,
        ).then((outcome) => {
          applied.push(...outcome.applied);
          failures.push(...outcome.failed.map((item) => item.op));
          if (outcome.failed.length) {
            setMessage(t("agent.opFailed").replace("{detail}", outcome.failed[0]?.error ?? ""));
          }
        }),
      );
    } else if (groups.project.length > 0) {
      failures.push(...groups.project);
    }
    if (!asyncOps.length) {
      after();
      return;
    }
    void Promise.all(asyncOps).then(after);
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

  const removePending = (index: number): void => {
    pendingRef.current = pendingRef.current.filter((_, item) => item !== index);
    setPending(pendingRef.current);
  };

  // Flush queued instructions once the run leaves live states — one at a
  // time, so each pending becomes its own follow-up round on the same job.
  useEffect(() => {
    if (!job || LIVE_STATES.has(job.state)) return;
    const queued = pendingRef.current;
    if (!queued.length) return;
    if (TERMINAL_STATES.has(job.state)) {
      // The job died while instructions waited — say so rather than post
      // them into a terminal-state 409.
      pendingRef.current = [];
      setPending([]);
      setMessage(t("agent.pendingDropped"));
      return;
    }
    const [first, ...rest] = queued;
    if (!first) return;
    pendingRef.current = rest;
    setPending(rest);
    void send(first);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- send is stable
    // enough here: it posts against whatever job the dock is bound to.
  }, [job]);

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
          <div className="ask-dock__welcome">
            <BotFigure size={110} welcome />
            <p className="ask-dock__hint">{t("agent.hint")}</p>
          </div>
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
                  <FailureCollapse
                    message={t(jobErrorKey(turn.errorCode))}
                    code={turn.errorCode}
                    /* Los intentos fallidos son los turnos de error que el
                     * transcript acumula hasta este punto. */
                    attempts={
                      thread.slice(0, turnIndex + 1).filter((item) => item.errorCode !== null)
                        .length
                    }
                    onRetry={retryable ? () => void retryJob() : undefined}
                  />
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
                  {turn.result.clarify?.question ? (
                    <div className="ask-dock__questions ask-dock__clarify">
                      <p>{turn.result.clarify.question}</p>
                      {turn.result.clarify.options?.length ? (
                        <div className="ask-dock__chips" role="list">
                          {turn.result.clarify.options.map((option, i) => (
                            <button
                              key={i}
                              type="button"
                              className="ask-dock__chip"
                              disabled={busy || live}
                              // La respuesta continúa el mismo pedido: el chip
                              // viaja con el goal original, como en el panel.
                              onClick={() =>
                                void send(`${turn.goal} — ${option.label ?? option.value ?? ""}`)
                              }
                            >
                              {option.label ?? option.value}
                            </button>
                          ))}
                        </div>
                      ) : null}
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
                          const groups = splitOps(ops);
                          // IA2 — el bloqueo de "stale" sólo corre para ops de
                          // producto; las de posición/proyecto van por API y no
                          // dependen del producto vivo ni del bridge.
                          // El plan propuesto sigue vivo sólo si el producto
                          // de referencia (snapshot o huella persistida) es
                          // el producto vivo — un turno restaurado sin copia
                          // se compara por huella, no desaparece del chequeo.
                          const proposal = proposalProduct(turn, bridge?.product);
                          const stale =
                            groups.product.length > 0 && (!bridge || proposal !== bridge.product);
                          const unroutable =
                            (groups.position.length > 0 && !refs.position_id) ||
                            (groups.project.length > 0 && !refs.project_id) ||
                            (groups.product.length > 0 && !bridge);
                          // IA2 §4 — la simulación se agrega al contrato del
                          // step (openapi.yaml regen en el mismo PR); el cast
                          // cubre el periodo entre ambos.
                          const simulation = (step as AiAgentStep & { simulation?: unknown })
                            .simulation as
                            | {
                                modules?: {
                                  ref?: string;
                                  bays?: { ref?: string; opening?: string }[];
                                  splits?: { type?: string; offset_mm?: string }[];
                                }[];
                              }
                            | undefined;
                          return (
                            <OpsProposalCard
                              key={stepIndex}
                              ops={ops}
                              proposal={proposal as ProductJson | null}
                              organizationId={organizationId}
                              positionId={refs.position_id ?? null}
                              stale={stale}
                              unroutable={unroutable}
                              applied={applied}
                              declined={declined}
                              simulation={simulation}
                              onApply={() => applyOps(turnIndex, stepIndex, ops)}
                              onDecline={() => declineOps(turnIndex, stepIndex, ops)}
                              onAudit={() =>
                                job ? navigate(`/assistant?job=${job.id}`) : undefined
                              }
                            />
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
                        // Deep-link by transcript coordinates (turn:item) — the
                        // flat shelf truncates to the newest entries, so a
                        // shelf index would drift to the wrong artifact.
                        const artRef = `${turn.transcriptIndex}:${i}`;
                        return (
                          <button
                            key={i}
                            type="button"
                            className="ask-dock__artifact"
                            title={t("aiws.openWorkspace")}
                            onClick={() =>
                              job ? navigate(`/assistant?job=${job.id}&art=${artRef}`) : undefined
                            }
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
      {offline ? (
        <p className="ask-dock__offline" role="status">
          {t("agent.offline")}
        </p>
      ) : null}
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
      {pending.length > 0 ? (
        <ul className="ask-dock__pending" aria-label={t("agent.pending")}>
          {pending.map((item, index) => (
            <li key={`${index}-${item.slice(0, 16)}`}>
              <span>
                {t("agent.pending")} {item}
              </span>
              <button
                type="button"
                aria-label={t("agent.pendingRemove")}
                onClick={() => removePending(index)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {!terminal ? (
        <form
          noValidate
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
            disabled={busy && !live}
          />
          <button type="submit" disabled={(busy && !live) || !goal.trim()}>
            {t("agent.send")}
          </button>
        </form>
      ) : null}
    </>
  );
}
