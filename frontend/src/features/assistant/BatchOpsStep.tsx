import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/apiMutator";
import {
  pricingDesignBatchPreview,
  positionsRetrieve,
  positionsUpdate,
} from "../../api/generated/dekopen";
import type { AiAgentStep } from "../../api/generated/models/aiAgentStep";
import type { PositionDesignRequest } from "../../api/generated/models/positionDesignRequest";
import type { DesignBatchPreviewItemRequestDesign } from "../../api/generated/models/designBatchPreviewItemRequestDesign";
import type { PositionResponse } from "../../api/generated/models/positionResponse";
import { t } from "../../i18n/es-CL";
import { formatMoney } from "../money";
import { addDecimal, formatDecimal, parseDecimal, subtractDecimal } from "../projects/decimal";
import type { DesignOp } from "../commands/types";
import { applyDesignOps, describeDesignOp } from "../canvas/designOps";
import {
  elevationEnvelopeMm,
  isProductModel,
  isSingleUnit,
  type ProductJson,
} from "../canvas/productEditing";

type BatchItem = {
  position_id: string;
  index?: number;
  location?: string | null;
  typology?: string;
  ops?: unknown[];
};

type Row = {
  item: BatchItem;
  ops: DesignOp[];
  detail?: PositionResponse;
  design?: PositionDesignRequest;
  product?: ProductJson;
  status: "loading" | "ready" | "unsupported" | "failed" | "applied" | "apply_failed";
  error?: string;
  unitBefore?: string | null;
  unitAfter?: string | null;
};

/** The same save-payload shape the editor builds: a lone unit persists in
 * the classic documentary shape, real assemblies as product-v2 — the engine
 * envelope check inside calculate_design/positions_update requires exactly
 * this projection. */
function designFromProduct(
  product: ProductJson,
  systemId: string,
  color: PositionDesignRequest["color"],
): PositionDesignRequest {
  const single = isSingleUnit(product) ? product.assembly.modules[0] : undefined;
  const envelope = elevationEnvelopeMm(product);
  return single !== undefined
    ? {
        system_id: systemId,
        nominal_width_mm: single.width_mm,
        nominal_height_mm: single.height_mm,
        color,
        parametric_tree: single.tree,
      }
    : {
        system_id: systemId,
        nominal_width_mm: envelope.width.toFixed(2),
        nominal_height_mm: envelope.height.toFixed(2),
        color,
        parametric_tree: product,
      };
}

function asOps(item: BatchItem): DesignOp[] {
  return (item.ops ?? []).filter((op): op is DesignOp => typeof (op as DesignOp).op === "string");
}

function apiDetail(error: unknown, fallback: string): string {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload !== null) {
    const detail = (error.payload as { error?: { detail?: unknown } }).error?.detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return fallback;
}

/** §08-WC — the batch-edit diff the human confirms: every row resolved
 * against its own stored product, ops applied through the same canonical
 * registry the editor uses, the engine gate and real unit costs computed
 * server-side. Applying saves each position through the canonical PUT —
 * nothing mutates until the click. */
export function BatchOpsStep({
  step,
  organizationId,
  projectId,
  settled = false,
  onSettled,
}: {
  step: AiAgentStep;
  organizationId: string;
  projectId: string;
  /** The turn already decided this proposal (apply or decline) — render the
   * settled state instead of re-offering actions. */
  settled?: boolean;
  /** §08 measurement — report the human's decision to the owning job. The
   * parent records the outcome; dedupe happens server-side. */
  onSettled?: (action: "applied" | "declined" | "apply_failed", ops: { op?: string }[]) => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const items = (step.items ?? []) as BatchItem[];
  const [rows, setRows] = useState<Row[]>([]);
  const [phase, setPhase] = useState<"loading" | "ready" | "applying" | "done">("loading");
  const [currency, setCurrency] = useState("CLP");
  const loadSeq = useRef(0);

  useEffect(() => {
    const seq = ++loadSeq.current;
    const headers = { headers: { "X-Organization-ID": organizationId } };
    void (async () => {
      const resolved = await Promise.all(
        items.map(async (item): Promise<Row> => {
          const row: Row = { item, ops: asOps(item), status: "loading" };
          try {
            const response = await positionsRetrieve(item.position_id, headers);
            if (response.status !== 200) throw new ApiError(response.status, response.data);
            const detail = response.data as PositionResponse;
            row.detail = detail;
            const tree = detail.design.parametric_tree;
            if (!isProductModel(tree)) {
              row.status = "unsupported";
              return row;
            }
            row.product = tree;
            // The canonical apply — identical to the editor's ops path.
            const next = applyDesignOps(tree, row.ops);
            row.design = designFromProduct(next, detail.design.system_id, detail.design.color);
            row.status = "ready";
          } catch (error) {
            row.status = "failed";
            row.error = apiDetail(error, t("agent.batchFailed"));
          }
          return row;
        }),
      );
      if (seq !== loadSeq.current) return;
      const candidates = resolved.filter(
        (row) => row.status === "ready" && row.design !== undefined,
      );
      if (candidates.length > 0) {
        try {
          const preview = await pricingDesignBatchPreview(
            {
              project_id: projectId,
              effective_date: new Date().toISOString().slice(0, 10),
              items: candidates.map((row) => ({
                position_id: row.item.position_id,
                // The wire payload is the same typed design shape; the generated
                // request model is an open dict so it needs the cast.
                design: row.design as unknown as DesignBatchPreviewItemRequestDesign,
              })),
            },
            headers,
          );
          if (preview.status !== 200) throw new ApiError(preview.status, preview.data);
          setCurrency(preview.data.currency ?? "CLP");
          const costs = new Map(preview.data.items.map((entry) => [entry.position_id, entry]));
          for (const row of resolved) {
            const entry = costs.get(row.item.position_id);
            if (entry === undefined) continue;
            if (!entry.ok) {
              // The engine gate already rejected this proposed design — the
              // row can't apply; surface the exact reason.
              row.status = "failed";
              row.error = entry.error ?? entry.error_code ?? t("agent.batchFailed");
              continue;
            }
            row.unitBefore = entry.unit_cost_before;
            row.unitAfter = entry.unit_cost_after;
          }
        } catch {
          // Pricing authority unavailable (no rules configured): rows stay
          // confirmable — the canonical save still re-validates the engine
          // gate — but the diff honestly shows no numbers.
          for (const row of resolved) {
            if (row.status === "ready") {
              row.unitBefore = null;
              row.unitAfter = null;
            }
          }
        }
      }
      if (seq === loadSeq.current) {
        setRows(resolved);
        setPhase("ready");
      }
    })();
    return () => {
      loadSeq.current += 1;
    };
    // The step's items are fixed for the turn's lifetime — resolve once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function apply(): Promise<void> {
    if (phase !== "ready") return;
    setPhase("applying");
    const headers = { headers: { "X-Organization-ID": organizationId } };
    setRows((current) => {
      const next = [...current];
      void (async () => {
        for (const [index, row] of next.entries()) {
          if (row.status !== "ready" || row.design === undefined || row.detail === undefined)
            continue;
          try {
            const response = await positionsUpdate(
              row.item.position_id,
              {
                location_tag: row.detail.location_tag ?? "",
                quantity: row.detail.quantity,
                design: row.design,
                expected_updated_at: row.detail.updated_at,
              },
              headers,
            );
            if (response.status !== 200) throw new ApiError(response.status, response.data);
            next[index] = { ...row, status: "applied" };
          } catch (error) {
            next[index] = {
              ...row,
              status: "apply_failed",
              error: apiDetail(error, t("projects.saveError")),
            };
          }
          setRows([...next]);
        }
        void queryClient.invalidateQueries({ queryKey: ["project-pages"] });
        setPhase("done");
        // Report each group separately so apply failures don't inflate the
        // applied count — dedupe is per (turn, step, action) server-side.
        const appliedOps = next.filter((row) => row.status === "applied").flatMap((row) => row.ops);
        const failedOps = next
          .filter((row) => row.status === "apply_failed")
          .flatMap((row) => row.ops);
        if (appliedOps.length) onSettled?.("applied", appliedOps);
        if (failedOps.length) onSettled?.("apply_failed", failedOps);
        if (!appliedOps.length && !failedOps.length) onSettled?.("apply_failed", []);
      })();
      return next;
    });
  }

  function decline(): void {
    onSettled?.(
      "declined",
      rows.flatMap((row) => row.ops),
    );
    setPhase("done");
  }

  const ready = rows.filter((row) => row.status === "ready");
  const applied = rows.filter((row) => row.status === "applied");
  const totalDelta = ready.reduce(
    (sum, row) => {
      const before = parseDecimal(row.unitBefore ?? "");
      const after = parseDecimal(row.unitAfter ?? "");
      if (before === null || after === null) return sum;
      const quantity = parseDecimal(String(row.detail?.quantity ?? 1));
      return addDecimal(
        sum,
        quantity === null
          ? subtractDecimal(after, before)
          : {
              numerator: subtractDecimal(after, before).numerator * quantity.numerator,
              denominator: subtractDecimal(after, before).denominator * quantity.denominator,
            },
      );
    },
    parseDecimal("0") ?? { numerator: 0n, denominator: 1n },
  );

  if (phase === "loading") {
    return <p className="ask-dock__hint">{t("agent.batchLoading")}</p>;
  }
  if (settled && phase !== "done") {
    return (
      <div className="ask-dock__ops ask-dock__batch">
        <p className="ask-dock__hint">{t("agent.batchSettled")}</p>
      </div>
    );
  }
  return (
    <div className="ask-dock__ops ask-dock__batch">
      <ul>
        {rows.map((row) => (
          <li key={row.item.position_id} className={`ask-dock__batch-row is-${row.status}`}>
            <span className="ask-dock__batch-where">
              V-{row.item.index ?? row.detail?.position_index ?? "?"}
              {row.item.location || row.detail?.location_tag
                ? ` · ${row.item.location ?? row.detail?.location_tag}`
                : ""}
            </span>
            <span className="ask-dock__batch-ops">
              {row.product && row.ops.length
                ? `${describeDesignOp(row.ops[0] as DesignOp, row.product)}${row.ops.length > 1 ? ` +${row.ops.length - 1}` : ""}`
                : t("agent.batchOps").replace("{count}", String(row.ops.length))}
            </span>
            <span className="ask-dock__batch-cost">
              {row.status === "applied"
                ? t("agent.batchApplied")
                : row.status === "failed" || row.status === "apply_failed"
                  ? (row.error ?? t("agent.batchFailed"))
                  : row.status === "unsupported"
                    ? t("agent.batchUnsupported")
                    : row.unitBefore !== undefined && row.unitAfter !== undefined
                      ? row.unitBefore === null
                        ? t("agent.batchNoCost")
                        : `${formatMoney(row.unitBefore, currency)} → ${formatMoney(row.unitAfter, currency)}`
                      : "…"}
            </span>
          </li>
        ))}
      </ul>
      <footer className="ask-dock__batch-footer">
        {phase === "done" ? (
          <span>
            {t("agent.batchAppliedCount")
              .replace("{done}", String(applied.length))
              .replace("{count}", String(rows.length))}
          </span>
        ) : (
          <>
            <span>
              {ready.length > 0
                ? t("agent.batchTotal")
                    .replace("{count}", String(ready.length))
                    .replace("{delta}", formatMoney(formatDecimal(totalDelta), currency))
                : t("agent.batchNone")}
            </span>
            <button
              type="button"
              className="ask-dock__action"
              disabled={ready.length === 0 || phase === "applying"}
              onClick={() => void apply()}
            >
              {t("agent.batchApply").replace("{count}", String(ready.length))}
            </button>
            <button
              type="button"
              className="ask-dock__action ask-dock__action--ghost"
              disabled={phase === "applying"}
              onClick={decline}
            >
              {t("agent.decline")}
            </button>
          </>
        )}
      </footer>
    </div>
  );
}
