import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/apiMutator";
import { aiActivity } from "../../api/generated/dekopen";
import type { AiActivityStatus } from "../../api/generated/models/aiActivityStatus";
import type { AiInvocation } from "../../api/generated/models/aiInvocation";
import { formatDateTime, formatMoney } from "../../format";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { EmptyState } from "../../ui";

const STATUS_KEYS: Record<string, TranslationKey> = {
  ok: "jobs.activity.ok",
  error: "jobs.activity.error",
  blocked: "jobs.activity.blocked",
};

const KIND_KEYS: Record<string, TranslationKey> = {
  probe: "jobs.activity.probe",
};

const CAPABILITIES = [
  "agent",
  "design_assist",
  "design_alternatives",
  "context_assist",
  "catalog_compile",
  "nlp_command",
  "discount_suggest",
  "vision_ocr",
  "fabricability",
] as const;

const CAPABILITY_KEYS: Record<string, TranslationKey> = {
  agent: "settings.aiCapability.agent",
  design_assist: "settings.aiCapability.designAssist",
  design_alternatives: "settings.aiCapability.designAlternatives",
  context_assist: "settings.aiCapability.contextAssist",
  catalog_compile: "settings.aiCapability.catalogCompile",
  nlp_command: "settings.aiCapability.nlpCommand",
  discount_suggest: "settings.aiCapability.discountSuggest",
  vision_ocr: "settings.aiCapability.visionOcr",
  fabricability: "settings.aiCapability.fabricability",
};

function capabilityLabel(capability: string | null | undefined): string {
  if (!capability) return "—";
  const key = CAPABILITY_KEYS[capability];
  return key !== undefined ? t(key) : capability;
}

const PAGE_SIZE = 30;

/** §IA3 — the org's provider-call ledger: every AI call with its capability,
 * model, tokens, credits, estimated cost and result. Filterable by
 * capability and result so an operator can answer "what did the agent cost
 * today" without reading logs. OWNER reads it — the panel renders nothing
 * for other roles (the endpoint refuses them). */
export function AiActivityPanel({
  orgId,
  isOwner,
}: {
  orgId: string;
  isOwner: boolean;
}): JSX.Element | null {
  const [capability, setCapability] = useState("");
  const [status, setStatus] = useState("");
  const [before, setBefore] = useState<string | null>(null);
  const [trail, setTrail] = useState<AiInvocation[]>([]);

  const query = useQuery<AiInvocation[]>({
    queryKey: ["ai", "activity", orgId, capability, status, before],
    enabled: isOwner,
    staleTime: 10_000,
    queryFn: async ({ signal }) => {
      const response = await aiActivity(
        {
          capability: capability === "" ? undefined : capability,
          status: status === "" ? undefined : (status as AiActivityStatus),
          before: before ?? undefined,
          limit: PAGE_SIZE,
        },
        { signal, headers: { "X-Organization-ID": orgId } },
      );
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data.items ?? [];
    },
  });

  if (!isOwner) return null;
  const items = query.data ?? [];
  const hasMore = items.length === PAGE_SIZE;
  return (
    <section className="ai-activity" aria-labelledby="ai-activity-title">
      <div className="ai-activity-head">
        <div>
          <h2 id="ai-activity-title">{t("jobs.aiActivity")}</h2>
          <p className="settings-hint">{t("jobs.aiActivityHint")}</p>
        </div>
        <div className="ai-activity-filters">
          <label className="ui-field jobs-filter">
            <span className="ui-field__label">{t("jobs.filter.capability")}</span>
            <select
              className="ui-field__input"
              value={capability}
              onChange={(event) => {
                setCapability(event.target.value);
                setBefore(null);
                setTrail([]);
              }}
            >
              <option value="">{t("jobs.filter.all")}</option>
              {CAPABILITIES.map((name) => (
                <option key={name} value={name}>
                  {capabilityLabel(name)}
                </option>
              ))}
            </select>
          </label>
          <label className="ui-field jobs-filter">
            <span className="ui-field__label">{t("jobs.filter.aiStatus")}</span>
            <select
              className="ui-field__input"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setBefore(null);
                setTrail([]);
              }}
            >
              <option value="">{t("jobs.filter.all")}</option>
              {Object.keys(STATUS_KEYS).map((name) => (
                <option key={name} value={name}>
                  {t(STATUS_KEYS[name] ?? "jobs.activity.ok")}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {query.isPending ? (
        <p role="status">{t("dashboard.attentionLoading")}</p>
      ) : query.isError ? (
        <p role="alert">{t("jobs.error")}</p>
      ) : items.length === 0 && trail.length === 0 ? (
        <EmptyState title={t("jobs.activity.empty")} />
      ) : (
        <>
          <table className="ai-activity-table">
            <thead>
              <tr>
                <th>{t("jobs.activity.when")}</th>
                <th>{t("jobs.filter.capability")}</th>
                <th>{t("jobs.activity.tool")}</th>
                <th>{t("jobs.activity.model")}</th>
                <th>{t("jobs.activity.tokens")}</th>
                <th>{t("jobs.activity.credits")}</th>
                <th>{t("jobs.activity.cost")}</th>
                <th>{t("jobs.filter.aiStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {[...trail, ...items].map((row) => (
                <tr key={row.id} data-tone={row.status === "ok" ? "ok" : "alert"}>
                  <td>
                    <time dateTime={row.created_at}>{formatDateTime(row.created_at)}</time>
                  </td>
                  <td>
                    {row.kind === "probe"
                      ? t(KIND_KEYS.probe ?? "jobs.activity.probe")
                      : capabilityLabel(row.capability)}
                    {row.mode === "test" && (
                      <span className="ai-test-mode-badge ai-test-mode-badge--inline">
                        {t("ai.testMode")}
                      </span>
                    )}
                  </td>
                  <td className="settings-mono">{row.tool_name ?? "—"}</td>
                  <td className="settings-mono">{row.public_model ?? "—"}</td>
                  <td>{row.tokens_prompt + row.tokens_completion}</td>
                  <td>{row.credits}</td>
                  <td>
                    {row.est_cost_usd === null || row.est_cost_usd === undefined
                      ? "—"
                      : `≈ ${formatMoney(row.est_cost_usd, "USD")}`}
                  </td>
                  <td>
                    <span
                      className="status-chip"
                      data-status={row.status === "ok" ? "completed" : "cancelled"}
                    >
                      {t(STATUS_KEYS[row.status] ?? "jobs.activity.ok")}
                    </span>
                    {row.error_code && <code className="job-row-code">{row.error_code}</code>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {hasMore && (
            <button
              type="button"
              className="ui-button"
              disabled={query.isFetching}
              onClick={() => {
                const last = items[items.length - 1];
                setBefore(last?.created_at ?? null);
                setTrail((seen) => [...seen, ...items]);
              }}
            >
              {query.isFetching ? t("dashboard.attentionLoading") : t("jobs.loadMore")}
            </button>
          )}
        </>
      )}
    </section>
  );
}
