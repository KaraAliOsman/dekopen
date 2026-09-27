import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/apiMutator";
import { positionsDesignAssist } from "../../api/generated/dekopen";
import type { DesignAssistResponse } from "../../api/generated/models/designAssistResponse";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { describeDesignOp, designAssistProduct, type DesignOp } from "./designOps";
import type { ProductJson } from "./productEditing";

type Preview = {
  ops: DesignOp[];
  rejected: { op: string | null; reason: string }[];
  notes: string | null;
  model: string;
  credits: number;
  /** The product instance the ops were validated against — any later commit
   * produces a new identity and makes the index-based ops stale. */
  snapshot: ProductJson;
  /** The catalog the ops were validated against — a system switch without a
   * product commit keeps the same snapshot, so identity alone can't catch it. */
  systemId: string | null;
};

/** NL design assistant: prompt → gateway-validated op preview → one commit.
 * Every apply is a single undoable product mutation; rejected ops are listed
 * so a bad proposal can never silently pass for a real edit. */
export function AssistantPanel({
  organizationId,
  positionId,
  systemId,
  product,
  disabled,
  draft,
  onDraftHandled,
  onApply,
}: {
  organizationId: string;
  positionId: string | null;
  systemId: string | null;
  product: ProductJson;
  disabled: boolean;
  /** A queued prompt from an external affordance ("Fix with DEKOPEN",
   * context menus): "" focuses the field, text replaces the draft.
   * `submit` sends it straight to the provider — the human still confirms
   * the returned ops, so no product mutation ever applies on its own. */
  draft: { text: string; submit?: boolean } | null;
  onDraftHandled(): void;
  onApply(ops: DesignOp[]): void;
}): JSX.Element {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const [detailsOpen, setDetailsOpen] = useState(true);
  /** Request generation token — a handled draft (or product change) must
   * invalidate any in-flight generate so its response can't restore ops
   * under a different prompt. */
  const requestSeq = useRef(0);

  useEffect(() => {
    if (draft === null) return;
    requestSeq.current += 1;
    setBusy(false);
    if (draft.text) setPrompt(draft.text);
    setMessage("");
    setPreview(null);
    setDetailsOpen(true);
    // Focus after the (possibly closed) details re-renders open.
    requestAnimationFrame(() => promptRef.current?.focus());
    if (draft.submit && draft.text.trim()) void generate(draft.text);
    onDraftHandled();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- generate is defined below; draft is the trigger
  }, [draft, onDraftHandled]);

  /** A product commit or system switch invalidates anything in flight —
   * responses are only valid under the exact (product, system) pair they
   * were validated against. */
  useEffect(() => {
    requestSeq.current += 1;
    setPreview(null);
  }, [product, systemId]);
  /** One operation key per (prompt, product, system) — a retry after a lost
   * response replays the committed call instead of debiting twice. */
  const operationKey = useRef<{
    key: string;
    prompt: string;
    product: ProductJson;
    systemId: string | null;
  } | null>(null);

  async function generate(rawPrompt?: string): Promise<void> {
    const trimmed = (rawPrompt ?? prompt).trim();
    if (!positionId || !systemId || !trimmed) return;
    setBusy(true);
    setMessage("");
    setPreview(null);
    if (
      !operationKey.current ||
      operationKey.current.prompt !== trimmed ||
      operationKey.current.product !== product ||
      operationKey.current.systemId !== systemId
    ) {
      operationKey.current = {
        key: crypto.randomUUID(),
        prompt: trimmed,
        product,
        systemId,
      };
    }
    const seq = ++requestSeq.current;
    try {
      const response = await positionsDesignAssist(
        positionId,
        {
          prompt: trimmed,
          operation_key: operationKey.current.key,
          system_id: systemId,
          // The wire carries stable domain ids — the same ones commands and
          // selection already use — so ops address modules/couplings by ref,
          // never by position; endpoints expose the assembly graph itself.
          product: designAssistProduct(product),
        },
        { headers: { "X-Organization-ID": organizationId } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      // A newer draft (or request) superseded this call — its ops must never
      // surface under a different prompt.
      if (seq !== requestSeq.current) return;
      const data = response.data as DesignAssistResponse;
      setPreview({
        snapshot: product,
        systemId,
        ops: data.ops as DesignOp[],
        rejected: data.rejected.map((item) => ({
          op: typeof item.op === "string" ? item.op : null,
          reason: typeof item.reason === "string" ? item.reason : "formato_invalido",
        })),
        notes: data.notes,
        model: data.model,
        credits: data.credits_debited,
      });
      if (data.ops.length === 0 && data.rejected.length === 0) {
        setMessage(t("assistant.empty"));
      }
    } catch (error) {
      if (seq !== requestSeq.current) return;
      setMessage(
        error instanceof ApiError && typeof error.payload === "object" && error.payload !== null
          ? String(
              (error.payload as { error?: { detail?: unknown } }).error?.detail ??
                t("assistant.error"),
            )
          : t("assistant.error"),
      );
    } finally {
      // Only the newest request clears busy — a superseded response must not
      // unlock the panel while a newer generate is still in flight.
      if (seq === requestSeq.current) setBusy(false);
    }
  }

  return (
    <details
      className="inspector-section assistant-panel"
      open={detailsOpen}
      onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
    >
      <summary>{t("assistant.title")}</summary>
      {!positionId ? (
        <p className="assembly-hint">{t("assistant.saveFirst")}</p>
      ) : (
        <>
          <textarea
            ref={promptRef}
            className="assistant-panel__prompt"
            rows={2}
            placeholder={t("assistant.prompt")}
            value={prompt}
            disabled={busy || disabled}
            onChange={(event) => setPrompt(event.target.value)}
          />
          <div className="inspector-actions">
            <button
              type="button"
              className="primary-button"
              disabled={busy || disabled || !systemId || !prompt.trim()}
              onClick={() => void generate()}
            >
              {busy ? t("assistant.generating") : t("assistant.generate")}
            </button>
          </div>
          {message && <p className="assembly-hint">{message}</p>}
          {preview && (
            <div className="assistant-panel__preview">
              {preview.notes && <p className="assistant-panel__notes">{preview.notes}</p>}
              {preview.ops.length > 0 && (
                <ul className="assistant-panel__ops">
                  {preview.ops.map((op, index) => (
                    <li key={`op-${index}`}>
                      {describeDesignOp(op, preview.snapshot, preview.ops.slice(0, index))}
                    </li>
                  ))}
                </ul>
              )}
              {preview.rejected.length > 0 && (
                <ul className="assistant-panel__rejected">
                  {preview.rejected.map((item, index) => (
                    <li key={`rejected-${index}`}>
                      {item.op ?? "?"}: {t(`assistant.reason_${item.reason}` as TranslationKey)}
                    </li>
                  ))}
                </ul>
              )}
              {preview.snapshot !== product || preview.systemId !== systemId ? (
                <p className="assembly-hint">{t("assistant.stale")}</p>
              ) : (
                <div className="inspector-actions">
                  <button
                    type="button"
                    className="primary-button"
                    disabled={preview.ops.length === 0 || disabled}
                    onClick={() => {
                      onApply(preview.ops);
                      setPreview(null);
                      setPrompt("");
                    }}
                  >
                    {t("assistant.apply").replace("{count}", String(preview.ops.length))}
                  </button>
                </div>
              )}
              <p className="assistant-panel__meta">
                {preview.model} · {preview.credits} {t("assistant.credits")}
              </p>
            </div>
          )}
        </>
      )}
    </details>
  );
}
