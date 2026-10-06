import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { positionsRetrieve, pricingDesignBatchPreview } from "../../api/generated/dekopen";
import type { DesignBatchPreviewItemRequestDesign } from "../../api/generated/models/designBatchPreviewItemRequestDesign";
import type { PositionResponse } from "../../api/generated/models/positionResponse";
import { formatMoney } from "../../format";
import { t } from "../../i18n/es-CL";
import type { DesignOp } from "../commands/types";
import { formatDecimal, parseDecimal, subtractDecimal } from "../projects/decimal";
import { designFromProduct } from "./designPayload";
import { ProductPreviewFigure, isDrawableProduct } from "./ProductPreviewFigure";
import { applyDesignOps, describeDesignOp, describeScopeOp } from "../canvas/designOps";
import type { ProductJson } from "../canvas/productEditing";

/** §P17 — la propuesta del agente como tarjeta revisable: diff del modelo
 * dibujado con el renderer real (antes/después), el impacto en precio y la
 * validez que calcula el motor (design_batch_preview — la misma compuerta
 * que guarda la posición), y las acciones Aplicar / Descartar / Ver
 * auditoría. La IA nunca escribe números: cada cifra sale del motor. */
export function OpsProposalCard({
  ops,
  proposal,
  organizationId,
  positionId,
  stale,
  unroutable,
  applied,
  declined,
  simulation,
  onApply,
  onDecline,
  onAudit,
}: {
  ops: DesignOp[];
  /** El producto de referencia de la propuesta (snapshot o el vivo cuando
   * la huella coincide) — con él se dibuja «antes» y se materializa
   * «después» aplicando las ops por el registro canónico. */
  proposal: ProductJson | null;
  organizationId: string;
  positionId: string | null;
  stale: boolean;
  unroutable: boolean;
  applied: boolean;
  declined: boolean;
  simulation?:
    | {
        modules?: {
          ref?: string;
          bays?: { ref?: string; opening?: string }[];
          splits?: { type?: string; offset_mm?: string }[];
        }[];
      }
    | undefined;
  onApply: () => void;
  onDecline: () => void;
  onAudit: () => void;
}): JSX.Element {
  // El «después» se materializa por el mismo registro canónico que usará
  // Aplicar — una op que no aplica nunca llega al dibujo.
  const after = useMemo(() => {
    if (!proposal || !isDrawableProduct(proposal)) return null;
    try {
      const next = applyDesignOps(proposal, ops);
      return isDrawableProduct(next) ? next : null;
    } catch {
      return null;
    }
  }, [proposal, ops]);

  const headers = useMemo(
    () => ({ headers: { "X-Organization-ID": organizationId } }),
    [organizationId],
  );

  // La posición aporta system_id/color/cantidad — la compuerta del motor
  // evalúa el MISMO payload que un Guardar enviaría.
  const detailQuery = useQuery({
    queryKey: ["assistant", "ops-card", "position", positionId],
    enabled: Boolean(organizationId && positionId && proposal && after !== null),
    staleTime: 30_000,
    queryFn: async () => {
      const response = await positionsRetrieve(positionId ?? "", headers);
      return response.status === 200 ? (response.data as PositionResponse) : null;
    },
  });

  const afterDesign = useMemo(() => {
    const detail = detailQuery.data;
    if (!detail || !after) return null;
    try {
      return designFromProduct(after, detail.design.system_id, detail.design.color);
    } catch {
      return null;
    }
  }, [detailQuery.data, after]);

  const previewQuery = useQuery({
    queryKey: [
      "assistant",
      "ops-card",
      "preview",
      positionId,
      afterDesign ? JSON.stringify(afterDesign) : "",
    ],
    enabled: Boolean(organizationId && positionId && afterDesign),
    staleTime: 60_000,
    queryFn: async () => {
      const detail = detailQuery.data;
      if (!detail || !afterDesign) return null;
      const response = await pricingDesignBatchPreview(
        {
          project_id: detail.project_id,
          effective_date: new Date().toISOString().slice(0, 10),
          items: [
            {
              position_id: positionId,
              quantity: Math.max(1, detail.quantity || 1),
              design: afterDesign as unknown as DesignBatchPreviewItemRequestDesign,
            },
          ],
        },
        headers,
      );
      return response.status === 200 ? response.data : null;
    },
  });
  const previewItem = previewQuery.data?.items?.[0] ?? null;
  // La compuerta puede no estar disponible (422 — taller sin reglas de
  // precio): la tarjeta lo declara honesto en vez de girar «evaluando…»
  // para siempre. La propuesta sigue aplicable: el Guardar revalida el
  // mismo contrato del motor.
  const previewSettled = previewQuery.isFetched || previewQuery.isError;
  const engineUnavailable = previewSettled && previewItem === null;
  const engineOk = previewItem?.ok === true;
  const engineError = previewItem?.error ?? previewItem?.error_code ?? null;
  const delta = (() => {
    const before =
      previewItem?.unit_net_before != null ? parseDecimal(previewItem.unit_net_before) : null;
    const afterNet =
      previewItem?.unit_net_after != null ? parseDecimal(previewItem.unit_net_after) : null;
    return engineOk && before && afterNet ? formatDecimal(subtractDecimal(afterNet, before)) : null;
  })();
  const currency = previewQuery.data?.currency ?? "CLP";

  return (
    <div className="ops-card">
      <ul className="ops-card__ops">
        {ops.map((op, i) => (
          <li key={i}>
            {proposal
              ? describeDesignOp(op, proposal, ops.slice(0, i))
              : (describeScopeOp(op) ?? op.op)}
          </li>
        ))}
      </ul>
      {proposal && after ? (
        <div className="ops-card__diff">
          <ProductPreviewFigure product={proposal} label={t("assistant.cardBefore")} />
          <span className="ops-card__arrow" aria-hidden="true">
            →
          </span>
          <ProductPreviewFigure product={after} label={t("assistant.cardAfter")} />
        </div>
      ) : null}
      {positionId && after ? (
        <p className="ops-card__verdict" data-ok={engineOk}>
          {!previewSettled
            ? t("assistant.cardEvaluating")
            : engineUnavailable
              ? t("assistant.cardEngineUnavailable")
              : engineOk
                ? delta !== null
                  ? `${t("assistant.cardValid")} · Δ ${delta.startsWith("-") ? "" : "+"}${formatMoney(delta, currency)}`
                  : t("assistant.cardValid")
                : `${t("assistant.cardInvalid")}${engineError ? ` — ${engineError}` : ""}`}
        </p>
      ) : null}
      {simulation?.modules?.length ? (
        <p className="ask-dock__ops-sim">
          {simulation.modules
            .map(
              (module) =>
                `${module.ref ?? "?"}: ${(module.bays ?? []).length} paño(s)${(module.splits ?? []).length ? `, ${(module.splits ?? []).length} división(es)` : ""}`,
            )
            .join(" · ")}
        </p>
      ) : null}
      <div className="ops-card__actions">
        <button
          type="button"
          className="ask-dock__action"
          disabled={applied || declined || stale || unroutable || previewItem?.ok === false}
          title={stale ? t("assistant.stale") : undefined}
          onClick={onApply}
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
            onClick={onDecline}
          >
            {declined ? t("agent.declined") : t("agent.decline")}
          </button>
        ) : null}
        <button
          type="button"
          className="ask-dock__action ask-dock__action--ghost"
          onClick={onAudit}
        >
          {t("assistant.cardAudit")}
        </button>
      </div>
    </div>
  );
}
