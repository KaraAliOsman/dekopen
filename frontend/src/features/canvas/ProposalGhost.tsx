import type { ProductIssue } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { formatMoney } from "../../format";
import type { MemberGeometry } from "./members";
import { ProductFrontContent, frontBounds } from "./ProductFrontSvg";
import type { ProductJson } from "./productEditing";

const NO_ISSUES: ProductIssue[] = [];
const NOOP = () => {};

/** The typed-command proposal drawn over the live canvas: the proposed
 * product ghosted in accent orange on top of the current drawing, before
 * Enter applies it (the §8 "see the answer before it lands" ceiling). */
export function GhostLayer({
  proposal,
  members,
  k,
}: {
  proposal: ProductJson;
  members: MemberGeometry;
  k: number;
}): JSX.Element {
  const box = frontBounds(proposal);
  const stroke = 1.5 / Math.max(0.01, k);
  return (
    <g className="canvas-ghost" aria-hidden="true" opacity={0.55}>
      <ProductFrontContent
        product={proposal}
        members={members}
        selectedId={null}
        issues={NO_ISSUES}
        disabled
        preview
        onSelectModule={NOOP}
        onAddUnit={NOOP}
        onCommitModuleWidth={NOOP}
        onCommitTotalWidth={NOOP}
        onCommitHeight={NOOP}
      />
      <rect
        className="canvas-ghost__frame"
        x={box.x}
        y={box.y}
        width={box.w}
        height={box.h}
        fill="none"
        strokeWidth={stroke}
        strokeDasharray={`${stroke * 3} ${stroke * 2}`}
      />
    </g>
  );
}

/** Screen-space bar over the canvas while a proposal is staged: the
 * price Δ from the same live-price gate, Enter applies, Esc discards.
 * "Calculando" while the Δ is in flight — never an invented number. */
export function ProposalBar({
  delta,
  pending,
  currency,
  onApply,
  onDiscard,
}: {
  /** signed line-total delta vs the current design — null until quoted. */
  delta: string | null;
  pending: boolean;
  currency: string;
  onApply(): void;
  onDiscard(): void;
}): JSX.Element {
  return (
    <div className="proposal-bar" role="status" data-testid="proposal-bar">
      <span className="proposal-bar__label">{t("assembly.proposalPending")}</span>
      <span className="proposal-bar__delta">
        {pending
          ? t("assembly.calculating")
          : delta === null
            ? "—"
            : `${delta.startsWith("-") ? "" : "+"}${formatMoney(delta, currency)}`}
      </span>
      <button type="button" className="ui-button proposal-bar__apply" onClick={onApply}>
        {t("assembly.proposalApply")} <kbd>Enter</kbd>
      </button>
      <button type="button" className="ui-button" onClick={onDiscard}>
        {t("assembly.proposalDiscard")} <kbd>Esc</kbd>
      </button>
    </div>
  );
}
