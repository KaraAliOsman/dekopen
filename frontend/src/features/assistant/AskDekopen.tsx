import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { aiAsk, aiAskThread } from "../../api/generated/dekopen";
import type { AiAskResponse } from "../../api/generated/models/aiAskResponse";
import { t } from "../../i18n/es-CL";
import { AgentBody, SURFACE_LABELS } from "./AgentBody";
import { BotFigure } from "./BotFigure";
import { Orb, orbStateFor } from "./Orb";
import { stableRefs, useAssistantContext } from "./assistantContext";
import "./assistant.css";

type Thread = { question: string; answer: AiAskResponse }[];

/** Ask threads keyed by `${surface}:${refs}` — module scope because the dock
 * mounts inside the per-route shell and remounts on every navigation; a
 * component-level map would lose the conversation the route switch was
 * itself answering. */
const dockThreads = new Map<string, Thread>();

/** Module-scope store bound — an SPA session that visits many surfaces must
 * not accumulate every thread forever; oldest keys age out first. */
const MAX_DOCK_THREADS = 12;

function syncDockThreads(next: Map<string, Thread>): void {
  while (next.size > MAX_DOCK_THREADS) {
    const oldest = next.keys().next().value;
    if (oldest === undefined) break;
    next.delete(oldest);
  }
  dockThreads.clear();
  for (const [key, value] of next) dockThreads.set(key, value);
}

/** Contextual "Preguntar a DEKOPEN": a docked panel that answers questions
 * inside a typed server-side projection of the current surface. The provider
 * can suggest navigation; it can never execute a mutation. */
export function AskDekopen({
  organizationId,
  userId = null,
  openRequested = 0,
  hideTrigger = false,
}: {
  organizationId: string | null;
  /** Module-scope threads are keyed org+user — without it an org switch
   * would render another tenant's conversation. */
  userId?: string | null;
  /** Incremental open signal — the shell's persistent AI entry opens the dock
   * without the floating trigger. */
  openRequested?: number;
  hideTrigger?: boolean;
}): JSX.Element | null {
  const { surface, refs } = useAssistantContext();
  const navigate = useNavigate();
  /* The dock remembers its expanded state across navigation and refresh —
   * closing it for one screen must not re-open on the next, and a running
   * thread shouldn't collapse mid-journey. sessionStorage scopes it to the
   * tab: a fresh session starts docked, a mid-work one keeps the panel. */
  const [open, setOpen] = useState(() => sessionStorage.getItem("dk:askdock") === "1");
  const [mode, setMode] = useState<"ask" | "agent">("ask");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  /** Threads live per surface — following the answer's own navigate action
   * to another surface must not delete the conversation that produced it.
   * The store is module-level: the dock mounts inside the per-route shell,
   * so component state dies on every navigation while this map survives. */
  const [threads, setThreads] = useState<Map<string, Thread>>(() => new Map(dockThreads));
  /** Agent mode: the bound job's lifecycle drives the header orb so a running
   * job reads alive even while the ask thread sits idle. */
  const [agentJobState, setAgentJobState] = useState<string | null>(null);
  const [agentComposing, setAgentComposing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  /** One operation key per question — a retried submit replays the committed
   * call instead of debiting twice. */
  const operationKey = useRef<{ key: string; question: string } | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    sessionStorage.setItem("dk:askdock", open ? "1" : "0");
  }, [open]);

  useEffect(() => {
    if (openRequested > 0) setOpen(true);
  }, [openRequested]);

  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // A surface switch invalidates in-flight requests — the answer belonged to
  // the previous context and must never surface under a different one. The
  // stored thread survives: returning to the surface restores it. Volatile
  // refs (a live canvas selection) reach the provider but never the thread
  // key — clicking another bay must not reset the conversation.
  const stableRefsKey = JSON.stringify(stableRefs(refs));
  // The module map is shared across the whole SPA session — key it by the
  // org AND user or an org switch would render another tenant's thread.
  const threadKey = `${organizationId ?? ""}:${userId ?? ""}:${surface}:${stableRefsKey}`;
  const thread = threads.get(threadKey) ?? [];
  useEffect(() => {
    requestSeq.current += 1;
    setBusy(false);
    setMessage("");
    operationKey.current = null;
    // Durable conversation (§3): the module map survives SPA navigation, but
    // a reload or a later session restores from the server-side turns — the
    // thread for this (surface, refs) comes back exactly where it was left.
    const key = `${organizationId ?? ""}:${userId ?? ""}:${surface}:${stableRefsKey}`;
    const seq = requestSeq.current;
    let cancelled = false;
    if (!organizationId) return;
    void (async () => {
      try {
        const list = await aiAskThread(
          { surface, refs: stableRefsKey },
          { headers: { "X-Organization-ID": organizationId } },
        );
        if (cancelled || seq !== requestSeq.current || list.status !== 200) return;
        const restored = (list.data ?? [])
          .map((turn) => ({
            question: String(turn.question ?? ""),
            answer: turn.answer as AiAskResponse,
          }))
          .filter((turn) => turn.question && turn.answer);
        if (!restored.length) return;
        setThreads((prev) => {
          // Newer in-session turns win — a turn asked while the restore was
          // in flight must never be replaced by the older snapshot.
          const existing = prev.get(key) ?? [];
          if (existing.length >= restored.length) return prev;
          const next = new Map(prev);
          next.set(key, restored);
          syncDockThreads(next);
          return next;
        });
      } catch {
        // A restore failure must never surface as an error — the dock simply
        // opens on an empty thread.
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stableRefsKey is
    // the stable serialization of the identity refs; volatile refs (canvas
    // selection) must not cancel the in-flight ask or reset the thread.
  }, [surface, stableRefsKey, organizationId, userId]);

  if (!organizationId) return null;
  const orgId: string = organizationId;

  async function ask(): Promise<void> {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setMessage("");
    if (!operationKey.current || operationKey.current.question !== trimmed) {
      operationKey.current = { key: crypto.randomUUID(), question: trimmed };
    }
    const seq = ++requestSeq.current;
    try {
      const response = await aiAsk(
        {
          surface,
          refs,
          question: trimmed,
          operation_key: operationKey.current.key,
        },
        {
          headers: { "X-Organization-ID": orgId },
          // The provider is bounded server-side — the client must not spin
          // forever on a wedged request.
          signal: AbortSignal.timeout(120_000),
        },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (seq !== requestSeq.current) return;
      setThreads((prev) => {
        const next = new Map(prev);
        next.set(threadKey, [
          ...(next.get(threadKey) ?? []),
          { question: trimmed, answer: response.data },
        ]);
        syncDockThreads(next);
        return next;
      });
      setQuestion("");
      operationKey.current = null;
    } catch (error) {
      if (seq !== requestSeq.current) return;
      setMessage(
        error instanceof ApiError && typeof error.payload === "object" && error.payload !== null
          ? String(
              (error.payload as { error?: { detail?: unknown } }).error?.detail ?? t("ask.error"),
            )
          : t("ask.error"),
      );
    } finally {
      if (seq === requestSeq.current) setBusy(false);
    }
  }

  return (
    <div
      className={`ask-dock${open ? " ask-dock--open" : ""}${
        surface === "position" ? " ask-dock--canvas" : ""
      }`}
    >
      {open ? (
        <section
          className="ask-dock__panel"
          aria-label={t("ask.title")}
          onKeyDown={(event) => {
            if (event.key === "Escape") setOpen(false);
          }}
        >
          <header className="ask-dock__header">
            <Orb
              state={
                mode === "agent"
                  ? agentJobState &&
                    [
                      "QUEUED",
                      "PLANNING",
                      "RUNNING",
                      "WAITING_FOR_USER",
                      "WAITING_FOR_APPROVAL",
                      "FAILED_RETRYABLE",
                    ].includes(agentJobState)
                    ? orbStateFor(agentJobState)
                    : agentComposing
                      ? "input"
                      : orbStateFor(agentJobState ?? undefined)
                  : busy
                    ? "thinking"
                    : question.trim()
                      ? "input"
                      : "idle"
              }
              size={26}
            />
            <span className="ask-dock__title">{t("assistant.dockTitle")}</span>
            <span className="ask-dock__modes">
              <button
                type="button"
                aria-pressed={mode === "ask"}
                className={`ask-dock__mode${mode === "ask" ? " ask-dock__mode--active" : ""}`}
                onClick={() => setMode("ask")}
              >
                {t("assistant.askMode")}
              </button>
              <button
                type="button"
                aria-pressed={mode === "agent"}
                className={`ask-dock__mode${mode === "agent" ? " ask-dock__mode--active" : ""}`}
                onClick={() => setMode("agent")}
              >
                {t("assistant.agentMode")}
              </button>
            </span>
            <span className="ask-dock__surface" title={t("ask.surfaceHint")}>
              {SURFACE_LABELS[surface] ?? surface}
            </span>
            <button
              type="button"
              className="ask-dock__close"
              onClick={() => setOpen(false)}
              aria-label={t("ask.close")}
            >
              ×
            </button>
          </header>
          {mode === "agent" ? (
            <AgentBody
              key={`${surface}:${stableRefsKey}`}
              organizationId={orgId}
              surface={surface}
              refs={refs}
              onJobState={setAgentJobState}
              onComposing={setAgentComposing}
            />
          ) : (
            <>
              <div className="ask-dock__thread" aria-live="polite" role="log">
                {thread.length === 0 ? (
                  <div className="ask-dock__welcome">
                    <BotFigure size={110} />
                    <p className="ask-dock__hint">{t("ask.hint")}</p>
                  </div>
                ) : (
                  thread.map((turn, index) => (
                    <div key={index} className="ask-dock__turn">
                      <p className="ask-dock__question">{turn.question}</p>
                      <p className="ask-dock__answer">{turn.answer.answer}</p>
                      {turn.answer.warnings?.length ? (
                        <ul className="ask-dock__warnings">
                          {turn.answer.warnings.map((warning, i) => (
                            <li key={i}>{warning}</li>
                          ))}
                        </ul>
                      ) : null}
                      {turn.answer.actions?.length ? (
                        <div className="ask-dock__actions">
                          {turn.answer.actions.map((action, i) => (
                            <button
                              key={i}
                              type="button"
                              className="ask-dock__action"
                              onClick={() => navigate(action.path)}
                            >
                              {action.label}
                            </button>
                          ))}
                        </div>
                      ) : null}
                      <p className="ask-dock__meta">
                        {turn.answer.model} · {turn.answer.credits_debited} {t("assistant.credits")}
                      </p>
                    </div>
                  ))
                )}
                {busy ? (
                  <p className="ask-dock__busy">
                    <Orb state="thinking" size={20} />
                    {t("ask.thinking")}
                  </p>
                ) : null}
              </div>
              {message ? <p className="ask-dock__error">{message}</p> : null}
              <form
                noValidate
                className="ask-dock__form"
                onSubmit={(event) => {
                  event.preventDefault();
                  ask().catch(() => undefined);
                }}
              >
                <input
                  ref={inputRef}
                  type="text"
                  value={question}
                  maxLength={2000}
                  placeholder={t("ask.placeholder")}
                  aria-label={t("ask.placeholder")}
                  onChange={(event) => setQuestion(event.target.value)}
                  disabled={busy}
                />
                <button type="submit" disabled={busy || !question.trim()}>
                  {t("ask.send")}
                </button>
              </form>
            </>
          )}
        </section>
      ) : hideTrigger ? null : (
        <button
          type="button"
          className="ask-dock__trigger"
          onClick={() => setOpen(true)}
          aria-label={t("ask.open")}
          title={t("ask.open")}
        >
          <Orb state={busy ? "working" : "idle"} size={38} />
        </button>
      )}
    </div>
  );
}
