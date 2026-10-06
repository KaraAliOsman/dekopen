import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/apiMutator";
import { aiProviderCheck, aiSettings, aiSettingsUpdate } from "../../api/generated/dekopen";
import type { AiProviderCheck } from "../../api/generated/models/aiProviderCheck";
import type { AiSettings } from "../../api/generated/models/aiSettings";
import { formatMoney, parseLocaleNumber } from "../../format";
import { domainLabel } from "../../i18n/domainLabels";
import { t, type TranslationKey } from "../../i18n/es-CL";

const MODE_KEYS: Record<string, TranslationKey> = {
  live: "settings.aiMode.live",
  test: "settings.aiMode.test",
  partial: "settings.aiMode.partial",
  unconfigured: "settings.aiMode.unconfigured",
};

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

function capabilityLabel(capability: string): string {
  const key = CAPABILITY_KEYS[capability];
  return key !== undefined ? t(key) : capability;
}

/** §IA3 — Settings › Inteligencia artificial (OWNER). The owner verifies the
 * real provider is serving, sees which model backs each capability, probes
 * the connection with one click, and caps monthly spend — all without ever
 * touching the key (it never leaves the server). */
export function AiSettingsCard({ orgId }: { orgId: string }): JSX.Element {
  const client = useQueryClient();
  const [budget, setBudget] = useState("");
  const [budgetTouched, setBudgetTouched] = useState(false);
  const [check, setCheck] = useState<AiProviderCheck | null>(null);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const options = { headers: { "X-Organization-ID": orgId } };

  const query = useQuery<AiSettings>({
    queryKey: ["ai", "settings", orgId],
    enabled: true,
    staleTime: 15_000,
    queryFn: async ({ signal }) => {
      const response = await aiSettings({ signal, ...options });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
  });

  const settingsData = query.data;
  const budgetValue = settingsData?.budget.monthly_credit_budget;
  const budgetInput = budgetTouched
    ? budget
    : budgetValue === null || budgetValue === undefined
      ? ""
      : String(budgetValue);

  const probe = useMutation({
    mutationFn: async () => {
      const response = await aiProviderCheck(options);
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
    onSuccess: (data) => {
      setCheck(data);
      void client.invalidateQueries({ queryKey: ["ai", "activity"] });
    },
    onError: () => setCheck({ ok: false, error_code: "request_failed", latency_ms: 0 }),
  });

  const saveBudget = useMutation({
    mutationFn: async (value: number | null) => {
      const response = await aiSettingsUpdate({ monthly_credit_budget: value }, options);
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
    onSuccess: (data) => {
      setNotice({ text: t("settings.aiBudgetSaved"), error: false });
      setBudgetTouched(false);
      client.setQueryData(["ai", "settings", orgId], data);
    },
    onError: () => setNotice({ text: t("settings.aiBudgetError"), error: true }),
  });

  const submitBudget = (event: FormEvent) => {
    event.preventDefault();
    const parsed = budgetInput.trim() === "" ? null : parseLocaleNumber(budgetInput);
    if (budgetInput.trim() !== "" && (parsed === null || parsed < 0)) {
      setNotice({ text: t("settings.aiBudgetInvalid"), error: true });
      return;
    }
    saveBudget.mutate(parsed === null ? null : Math.round(parsed));
  };

  if (query.isPending) {
    return (
      <div className="settings-card">
        <h3 className="eyebrow">{t("settings.aiTitle")}</h3>
        <p className="settings-hint">{t("dashboard.attentionLoading")}</p>
      </div>
    );
  }
  if (query.isError || settingsData === undefined) {
    return (
      <div className="settings-card">
        <h3 className="eyebrow">{t("settings.aiTitle")}</h3>
        <p className="settings-hint" role="alert">
          {t("settings.aiError")}
        </p>
      </div>
    );
  }

  const usage = settingsData.usage as {
    calls?: number;
    tokens_prompt?: number;
    tokens_completion?: number;
    credits?: number;
    est_cost_usd?: string | null;
    errors?: number;
    by_user?: {
      user_id: string | null;
      member_role?: string | null;
      calls: number;
      credits: number;
      tokens: number;
    }[];
    by_capability?: { capability: string; calls: number; credits: number }[];
  };
  const estUsd = usage.est_cost_usd;
  return (
    <div className="settings-card" data-testid="ai-settings-card">
      <h3 className="eyebrow">{t("settings.aiTitle")}</h3>
      <p className="settings-hint">{t("settings.aiHint")}</p>

      <dl className="settings-list">
        <div className="settings-row">
          <dt>{t("settings.aiStatus")}</dt>
          <dd>
            <span className="status-chip ai-mode-chip" data-status={settingsData.mode}>
              {t(MODE_KEYS[settingsData.mode] ?? "settings.aiMode.unconfigured")}
            </span>
          </dd>
        </div>
      </dl>
      {settingsData.mode === "unconfigured" && (
        <p className="settings-hint" role="status">
          {t("settings.aiUnconfiguredHint")}
        </p>
      )}

      {settingsData.capabilities.length > 0 && (
        <table className="ai-capabilities">
          <thead>
            <tr>
              <th>{t("settings.aiCapabilityCol")}</th>
              <th>{t("settings.aiModel")}</th>
              <th>{t("settings.aiCredits")}</th>
            </tr>
          </thead>
          <tbody>
            {settingsData.capabilities
              .filter((capability) => capability.enabled)
              .map((capability) => (
                <tr key={capability.capability} data-mode={capability.mode}>
                  <td>{capabilityLabel(capability.capability)}</td>
                  <td className="settings-mono">{capability.model}</td>
                  <td>{capability.credits_cost}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}

      <div className="payments-form-actions ai-check-row">
        <button
          type="button"
          className="secondary-action"
          disabled={probe.isPending}
          onClick={() => {
            setCheck(null);
            probe.mutate();
          }}
        >
          {probe.isPending ? t("settings.aiChecking") : t("settings.aiCheck")}
        </button>
        {check !== null && (
          <span className="ai-check-result" data-ok={check.ok} role="status">
            {check.ok
              ? t("settings.aiCheckOk").replace("{ms}", String(check.latency_ms))
              : t("settings.aiCheckFailed").replace("{code}", check.error_code ?? "error")}
          </span>
        )}
      </div>

      <form noValidate className="payments-form" onSubmit={submitBudget}>
        <label>
          {t("settings.aiBudget")}
          <input
            inputMode="numeric"
            maxLength={9}
            placeholder={t("settings.aiBudgetPlaceholder")}
            value={budgetInput}
            onChange={(event) => {
              setBudget(event.target.value);
              setBudgetTouched(true);
            }}
          />
        </label>
        <p className="settings-hint">{t("settings.aiBudgetHint")}</p>
        <div className="payments-form-actions">
          <button type="submit" className="secondary-action" disabled={saveBudget.isPending}>
            {t("settings.aiBudgetSave")}
          </button>
        </div>
      </form>
      {notice !== null && (
        <p className="settings-hint" role={notice.error ? "alert" : "status"}>
          {notice.text}
        </p>
      )}
      {settingsData.budget.exceeded && (
        <p className="settings-hint ai-budget-exceeded" role="alert">
          {t("settings.aiBudgetExceeded")}
        </p>
      )}

      <dl className="settings-list ai-usage">
        <div className="settings-row">
          <dt>{t("settings.aiSpent")}</dt>
          <dd>
            {t("settings.aiSpentValue")
              .replace("{credits}", String(settingsData.budget.spent_this_month))
              .replace(
                "{budget}",
                settingsData.budget.monthly_credit_budget === null ||
                  settingsData.budget.monthly_credit_budget === undefined
                  ? t("settings.aiNoLimit")
                  : String(settingsData.budget.monthly_credit_budget),
              )}
          </dd>
        </div>
        <div className="settings-row">
          <dt>{t("settings.aiCalls")}</dt>
          <dd>{usage.calls ?? 0}</dd>
        </div>
        <div className="settings-row">
          <dt>{t("settings.aiTokens")}</dt>
          <dd>{(usage.tokens_prompt ?? 0) + (usage.tokens_completion ?? 0)}</dd>
        </div>
        <div className="settings-row">
          <dt>{t("settings.aiErrors")}</dt>
          <dd>{usage.errors ?? 0}</dd>
        </div>
        <div className="settings-row">
          <dt>{t("settings.aiEstCost")}</dt>
          <dd>
            {estUsd === null || estUsd === undefined
              ? t("settings.aiNoRate")
              : `≈ ${formatMoney(estUsd, "USD")}`}
          </dd>
        </div>
      </dl>

      {(usage.by_capability?.length ?? 0) > 0 && (
        <>
          <h4 className="settings-subtitle">{t("settings.aiPerCapability")}</h4>
          <table className="ai-capabilities">
            <tbody>
              {(usage.by_capability ?? []).map((row) => (
                <tr key={row.capability}>
                  <td>{capabilityLabel(row.capability)}</td>
                  <td>{row.calls}</td>
                  <td>{row.credits}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {(usage.by_user?.length ?? 0) > 0 && (
        <>
          <h4 className="settings-subtitle">{t("settings.aiPerUser")}</h4>
          <table className="ai-capabilities">
            <tbody>
              {(usage.by_user ?? []).map((row) => (
                <tr key={row.user_id ?? "none"}>
                  <td className="settings-mono" title={row.user_id ?? ""}>
                    {row.user_id === null
                      ? t("settings.aiSystemUser")
                      : row.member_role
                        ? `${domainLabel("MembershipRoleEnum", row.member_role).label} · ${row.user_id.slice(0, 8)}`
                        : row.user_id.slice(0, 8)}
                  </td>
                  <td>{row.calls}</td>
                  <td>{row.credits}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
