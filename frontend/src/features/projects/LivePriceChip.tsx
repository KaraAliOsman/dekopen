import { useEffect, useRef, useState } from "react";

import { pricingDesignBatchPreview } from "../../api/generated/dekopen";
import type { ModuleNetSplit } from "../../api/generated/models";
import { formatMoney } from "../../format";
import { t } from "../../i18n/es-CL";

export interface LivePrice {
  unitNet: string;
  lineNet: string;
  /** P06 — per-module net split for assembly designs (engine-cost
   * attribution inside the pricing boundary); null for single designs. */
  modules: ModuleNetSplit[] | null;
  /** Cost was priced but the org's pricing mode can't quote a single
   * design's net (catalog modes need project authorities) — the chip
   * shows "—", not a wrong number. */
  netless: boolean;
}

/** Live net price for the on-canvas design — same `design_batch_preview`
 * engine gate as the save flow, debounced so a module drag doesn't pile
 * up requests. `enabled` gates the whole effect (unsaveable designs are
 * never quoted). `quote` is the imperative twin the ghost-proposal bar
 * uses for its Δ. */
export function useLivePrice({
  projectId,
  positionId,
  quantity,
  designPayload,
  enabled,
}: {
  projectId: string;
  positionId: string | null;
  quantity: string;
  /** Fresh closure — the payload save() would send, or null when the
   * design isn't quotable. Read at request time so stale drafts never
   * price. */
  designPayload(): { [key: string]: unknown } | null;
  enabled: boolean;
}): {
  price: LivePrice | null;
  /** A quote is in flight — the chip announces "calculando" instead of
   * showing the previous number as if it were current. */
  pending: boolean;
  quote(design: { [key: string]: unknown } | null, qty: number): Promise<LivePrice | null>;
} {
  const [price, setPrice] = useState<LivePrice | null>(null);
  const [pending, setPending] = useState(false);
  const generation = useRef(0);
  const payloadRef = useRef(designPayload);
  payloadRef.current = designPayload;

  async function quote(
    design: { [key: string]: unknown } | null,
    qty: number,
  ): Promise<LivePrice | null> {
    if (design === null) return null;
    try {
      const response = await pricingDesignBatchPreview({
        project_id: projectId,
        effective_date: new Date().toISOString().slice(0, 10),
        items: [{ position_id: positionId, quantity: qty, design }],
      });
      if (response.status !== 200) return null;
      const item = response.data.items[0];
      if (!item?.ok) return null;
      if (item.unit_net_after == null || item.line_net_after == null) {
        // Priced cost but no sell formula for a standalone design —
        // honest "—", never an invented margin.
        return item.unit_cost_after != null
          ? { unitNet: "", lineNet: "", modules: null, netless: true }
          : null;
      }
      return {
        unitNet: item.unit_net_after,
        lineNet: item.line_net_after,
        modules: item.module_net_after ?? null,
        netless: false,
      };
    } catch {
      return null;
    }
  }

  const qty = Math.max(1, Number.parseInt(quantity, 10) || 1);
  // Serializing only as the effect's trigger — the payload itself is read
  // fresh inside the timeout so a settled request never prices a draft
  // the canvas has already moved past.
  const design = designPayload();
  const fingerprint =
    enabled && design !== null ? `${positionId ?? "new"}:${qty}:${JSON.stringify(design)}` : null;
  useEffect(() => {
    if (fingerprint === null) return;
    const epoch = ++generation.current;
    const timer = setTimeout(() => {
      setPending(true);
      void quote(payloadRef.current(), qty).then((next) => {
        if (epoch !== generation.current) return;
        setPending(false);
        // A failed quote keeps the last good number, flagged by the
        // pending flag on its replacement request — never a hidden stale.
        if (next !== null) setPrice(next);
      });
    }, 450);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fingerprint]);

  return { price, pending, quote };
}

/** Strip chip: net unit + line total from the live quote; assemblies
 * additionally break the unit net down per module. "calculando" while a
 * quote is in flight — a stale number is never shown as current. */
export function LivePriceChip({
  price,
  pending,
  currency,
  moduleIds = [],
}: {
  price: LivePrice | null;
  pending: boolean;
  currency: string;
  /** Order of assembly module ids — labels the per-module breakdown
   * M1..Mn in the same left-to-right order the elevation draws them. */
  moduleIds?: string[];
}): JSX.Element {
  const moduleSplit =
    price?.modules && price.modules.length > 1
      ? [...price.modules]
          // Order follows the elevation's declared module order, never the
          // payload's — an out-of-order payload must not scramble M1..Mn.
          .sort(
            (a, b) =>
              (moduleIds.indexOf(a.module_id) + 1 || Number.MAX_SAFE_INTEGER) -
              (moduleIds.indexOf(b.module_id) + 1 || Number.MAX_SAFE_INTEGER),
          )
          .map((item) => {
            const index = moduleIds.indexOf(item.module_id);
            const label = index >= 0 ? `M${index + 1}` : item.module_id;
            return `${label} ${formatMoney(item.unit_net, currency)}`;
          })
          .join(" · ")
      : null;
  return (
    <span
      className={`live-price${pending ? " is-pending" : ""}`}
      data-testid="live-price"
      role="status"
      aria-live="polite"
    >
      {pending ? (
        <span className="live-price__state">{t("assembly.calculating")}</span>
      ) : price === null || price.netless ? (
        <span className="live-price__state" title={t("projects.netlessHint")}>
          —
        </span>
      ) : (
        <>
          <span className="live-price__unit">
            {t("projects.netUnit")} {formatMoney(price.unitNet, currency)}
          </span>
          {moduleSplit !== null && (
            <span
              className="live-price__modules"
              title={t("assembly.pricePerModule")}
              data-testid="live-price-modules"
            >
              {moduleSplit}
            </span>
          )}
          <span className="live-price__line">{formatMoney(price.lineNet, currency)}</span>
        </>
      )}
    </span>
  );
}
