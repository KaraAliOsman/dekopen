import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { aiAsk } from "../../api/generated/dekopen";
import type { AiAskResponse } from "../../api/generated/models/aiAskResponse";
import { t } from "../../i18n/es-CL";
import { AgentBody, SURFACE_LABELS } from "./AgentBody";
import { Orb, orbStateFor } from "./Orb";
import { useAssistantContext } from "./assistantContext";
import "./assistant.css";

type Thread = { question: string; answer: AiAskResponse }[];

/** Contextual "Preguntar a DEKOPEN": a docked panel that answers questions
 * inside a typed server-side projection of the current surface. The provider
 * can suggest navigation; it can never execute a mutation. */
export function AskDekopen({
  organizationId,
  openRequested = 0,
  hideTrigger = false,
}: {
  organizationId: string | null;
  /** Incremental open signal — the shell's persistent AI entry opens the dock
   * without the floating trigger. */
  openRequested?: number;
  hideTrigger?: boolean;
}): JSX.Element | null {
  const { surface, refs } = useAssistantContext();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"ask" | "agent">("ask");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<Thread>([]);
  /** Agent mode: the bound job's lifecycle drives the header orb so a running
   * job reads alive even while the ask thread sits idle. */
  const [agentJobState, setAgentJobState] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  /** One operation key per question — a retried submit replays the committed
   * call instead of debiting twice. */
  const operationKey = useRef<{ key: string; question: string } | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    if (openRequested > 0) setOpen(true);
  }, [openRequested]);

  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // A surface switch invalidates in-flight requests — the answer belonged to
  // the previous context and must never surface under a different one. The
  // effect keys on the serialized refs (the object identity is unstable).
  const refsKey = JSON.stringify(refs);
  useEffect(() => {
    requestSeq.current += 1;
    setBusy(false);
    setMessage("");
    setThread([]);
    setMode("ask");
    operationKey.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refsKey is the
    // stable serialization of refs.
  }, [surface, refsKey]);

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
        { headers: { "X-Organization-ID": orgId } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (seq !== requestSeq.current) return;
      setThread((prev) => [...prev, { question: trimmed, answer: response.data }]);
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
    <div className={`ask-dock${open ? " ask-dock--open" : ""}`}>
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
                  ? orbStateFor(agentJobState ?? undefined)
                  : busy
                    ? "thinking"
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
              key={`${surface}:${refsKey}`}
              organizationId={orgId}
              surface={surface}
              refs={refs}
              onJobState={setAgentJobState}
            />
          ) : (
            <>
              <div className="ask-dock__thread" aria-live="polite" role="log">
                {thread.length === 0 ? (
                  <p className="ask-dock__hint">{t("ask.hint")}</p>
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
