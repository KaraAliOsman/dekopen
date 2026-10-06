import { useEffect, useRef, useState } from "react";

import { pricingDesignBatchPreview } from "../../api/generated/dekopen";
import { formatMoney } from "../../format";
import { t } from "../../i18n/es-CL";

export interface LivePrice {
  unitNet: string;
  lineNet: string;
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
        return item.unit_cost_after != null ? { unitNet: "", lineNet: "", netless: true } : null;
      }
      return { unitNet: item.unit_net_after, lineNet: item.line_net_after, netless: false };
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

/** Strip chip: net unit + line total from the live quote. "calculando"
 * while a quote is in flight — a stale number is never shown as current. */
export function LivePriceChip({
  price,
  pending,
  currency,
}: {
  price: LivePrice | null;
  pending: boolean;
  currency: string;
}): JSX.Element {
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
          <span className="live-price__line">{formatMoney(price.lineNet, currency)}</span>
        </>
      )}
    </span>
  );
}
