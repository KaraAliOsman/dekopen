import { useMemo, useState } from "react";

import type { OptimizeStrategyStats } from "../../api/generated/models";
import { cutRoleLabel } from "./labels";
import { fmtMm, fmtPct } from "../../format";
import { t, tOptional } from "../../i18n/es-CL";

// Full engine payload contract (backend/production/service.py →
// dekopen_engine.cutting + nesting, model_dump(mode="json") — every
// mm/area/pct value arrives as a decimal string).
export type CutPlacement = {
  piece_id: string;
  source_kind?: "PROFILE" | "REINFORCEMENT";
  workshop_sku?: string;
  material?: string;
  color?: string;
  length_mm: string;
  source_position_id?: string | null;
  bay_id?: string | null;
  leaf_id?: string | null;
  role?: string;
  unit_index?: number;
  angle_left?: string | null;
  angle_right?: string | null;
  sequence?: number;
};
export type CutBar = {
  bar_index: number;
  commercial_sku: string;
  material?: string;
  color?: string;
  stock_length_mm: string;
  head_trim_mm?: string;
  tail_trim_mm?: string;
  kerf_mm?: string;
  cuts: CutPlacement[];
  remainder_mm: string;
  remainder_reusable?: boolean;
  waste_mm?: string;
  yield_pct: string;
  waste_pct?: string;
  stock_authority_id?: string;
  source?: "NEW" | "REMNANT";
  remnant_id?: string | null;
};
export type PurchaseLine = {
  commercial_sku: string;
  qty_bars: number;
  stock_length_mm: string;
};
export type SheetPurchase = { purchasing_sku: string; qty_sheets: number };
export type NestPlacement = {
  piece_id: string;
  workshop_sku?: string;
  x_mm: string;
  y_mm: string;
  width_mm: string;
  height_mm: string;
  rotated: boolean;
  source_position_id?: string | null;
  bay_id?: string | null;
  leaf_id?: string | null;
  unit_index?: number;
  sequence?: number;
};
export type SheetLayout = {
  sheet_index: number;
  purchasing_sku: string;
  sheet_width_mm: string;
  sheet_height_mm: string;
  yield_pct: string;
  placements: NestPlacement[];
  workshop_sku?: string;
  source?: "NEW" | "REMNANT";
  remnant_id?: string | null;
  produced_remnants?: { x_mm: string; y_mm: string; width_mm: string; height_mm: string }[];
};
export type UnnestedPiece = {
  kind: string;
  group: string;
  width_mm: string;
  height_mm: string;
  quantity: number;
  bay_id?: string | null;
  leaf_id?: string | null;
  reason?: string;
};
export type OptimizationMetrics = {
  bars?: number;
  purchased_bars?: number;
  remnant_bars?: number;
  cuts?: number;
  productive_length_mm?: string;
  process_waste_mm?: string;
  reusable_remnant_mm?: string;
  unplaced?: number;
};
export type StrategyComparison = {
  fast?: OptimizationMetrics;
  deep?: OptimizationMetrics;
  chosen?: string;
};
export type StockReservation = {
  kind?: string;
  sku?: string;
  name?: string;
  unit?: string;
  needed?: string;
  on_hand?: string;
  reserved?: string;
  short?: string;
  consumed_at?: string | null;
};

export type RemnantLedger = {
  consumed?: { id: string; kind: string; rack_location?: string | null }[];
  produced_bars?: { stock_authority_id: string; remainder_mm: string }[];
  produced_sheets?: { workshop_sku: string; width_mm: string; height_mm: string }[];
};
export type WorkOrderOptimization = {
  schema?: string;
  color?: string;
  units?: number;
  optimized_at?: string;
  actor_id?: string;
  strategy?: string;
  /** The strategy that physically produced this plan (auto → its `chosen`). */
  applied_strategy?: string;
  bars?: {
    workshop_cut_plan?: CutBar[];
    purchase_list?: PurchaseLine[];
    metrics?: OptimizationMetrics;
    strategy_comparison?: StrategyComparison;
    plan_seed?: string;
    unplaced?: { piece?: { piece_id?: string }; reason?: string }[];
  };
  sheets?: SheetLayout[];
  sheet_purchases?: SheetPurchase[];
  unnested?: UnnestedPiece[];
  remnants?: RemnantLedger;
  stock_reservations?: StockReservation[];
  unmapped_stock_skus?: string[];
  invalidated?: boolean;
  invalidated_by?: string;
  stats?: OptimizeStrategyStats;
};

type PieceRef = {
  kind: "cut" | "nest";
  key: string;
  code: string;
  /** Printed workshop code (M-xx/R-xx/I-xx) when the sealed labels resolve. */
  shopCode?: string;
  piece: CutPlacement | NestPlacement;
};

function num(value: string | number | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Interchangeable piece spec — the same join the printed packs use to list
 * shared piece codes: location (position/bay/leaf) + role + sku + measure +
 * angles. Two different frame members of one bay only group when they are
 * literally the same cut spec. */
function memberKey(piece: CutPlacement | NestPlacement): string {
  const cut = piece as CutPlacement;
  const nest = piece as NestPlacement;
  const measure =
    cut.length_mm != null
      ? `L${cut.length_mm}|${cut.angle_left ?? ""}|${cut.angle_right ?? ""}`
      : `N${nest.width_mm ?? ""}x${nest.height_mm ?? ""}`;
  return [
    piece.source_position_id ?? "-",
    piece.bay_id ?? "-",
    piece.leaf_id ?? "-",
    cut.role ?? "",
    cut.source_kind ?? "",
    piece.workshop_sku ?? "",
    measure,
  ].join("|");
}

function materialClass(material: string | undefined, kind?: string): string {
  if (kind === "REINFORCEMENT") return "cutplan-piece-steel";
  switch (material) {
    case "ALUMINIUM":
      return "cutplan-piece-alu";
    case "PVC":
    default:
      return "cutplan-piece-pvc";
  }
}

function CutPlanBarSvg({
  bar,
  selectedMember,
  selectedKey,
  pieceCodes,
  onSelect,
}: {
  bar: CutBar;
  selectedMember: string | null;
  selectedKey: string | null;
  pieceCodes: Record<string, string>;
  onSelect: (ref: PieceRef) => void;
}) {
  const stock = num(bar.stock_length_mm) || 1;
  const head = num(bar.head_trim_mm);
  const tail = num(bar.tail_trim_mm);
  const kerf = num(bar.kerf_mm);
  const scaled = (mm: number) => (mm / stock) * 1000;
  // The strip is the thing a saw operator reads — it has to stay legible at
  // arm's length, so the band itself carries most of the height and the
  // labels stay large inside it (narrow pieces keep their identity in the
  // legend below, mirroring the printed pack's leader list).
  const barH = 96;
  let cursor = head;
  const pieces = bar.cuts.map((cut, index) => {
    const x = cursor;
    const w = num(cut.length_mm);
    cursor += w + kerf;
    const key = `b${bar.bar_index}-c${index}`;
    const code = `B${bar.bar_index}-${cut.sequence ?? index + 1}`;
    const shopCode = pieceCodes[cut.piece_id];
    const keyOfPiece = memberKey(cut);
    const selected = selectedKey === key;
    const memberHit = selectedMember !== null && keyOfPiece === selectedMember;
    const xSc = scaled(x);
    const wSc = scaled(w);
    const mid = xSc + wSc / 2;
    const angleL = cut.angle_left != null && num(cut.angle_left) !== 90;
    const angleR = cut.angle_right != null && num(cut.angle_right) !== 90;
    return (
      <g
        key={key}
        className={`cutplan-cut ${materialClass(cut.material, cut.source_kind)}${
          memberHit ? " is-member" : ""
        }${selected ? " is-selected" : ""}`}
        onClick={() => onSelect({ kind: "cut", key, code, shopCode, piece: cut })}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect({ kind: "cut", key, code, shopCode, piece: cut });
          }
        }}
      >
        <rect x={xSc} y={10} width={Math.max(wSc, 1)} height={barH - 20} rx={2} />
        {wSc > 60 ? (
          <text x={mid} y={42} textAnchor="middle" className="cutplan-cut-id">
            {shopCode ?? pieceLabel(cut, code)}
          </text>
        ) : null}
        {wSc > 44 ? (
          <text x={mid} y={68} textAnchor="middle" className="cutplan-cut-len">
            {fmtMm(cut.length_mm)}
          </text>
        ) : null}
        {angleL ? (
          <polygon
            className="cutplan-miter-notch"
            points={`${xSc + 2},10 ${xSc + 16},10 ${xSc + 2},30`}
            aria-hidden
          />
        ) : null}
        {angleR ? (
          <polygon
            className="cutplan-miter-notch"
            points={`${xSc + wSc - 2},10 ${xSc + wSc - 16},10 ${xSc + wSc - 2},30`}
            aria-hidden
          />
        ) : null}
      </g>
    );
  });
  // The engine charges kerf after every cut (process_consumed_mm) — the
  // trailing kerf is part of the consumed span, so the drawn remainder
  // matches the sealed remainder_mm.
  const usedEnd = cursor;
  const remainder = Math.max(stock - tail - usedEnd, 0);
  return (
    <div className="cutplan-barwrap">
      <svg
        className="cutplan-bar"
        viewBox={`0 0 1000 ${barH}`}
        role="group"
        aria-label={`${t("production.optimizeBar")} #${bar.bar_index}`}
      >
        <rect
          className="cutplan-frame"
          x={0}
          y={10}
          width={1000}
          height={barH - 20}
          rx={2}
          pointerEvents="none"
        />
        {head > 0 ? (
          <rect
            className="cutplan-trim"
            x={0}
            y={10}
            width={Math.max(scaled(head), 1.5)}
            height={barH - 20}
          />
        ) : null}
        {pieces}
        {remainder > 0 ? (
          <rect
            className="cutplan-remainder"
            x={scaled(usedEnd)}
            y={10}
            width={Math.max(scaled(remainder), 1)}
            height={barH - 20}
          />
        ) : null}
        {tail > 0 ? (
          <rect
            className="cutplan-trim"
            x={scaled(stock - tail)}
            y={10}
            width={Math.max(scaled(tail), 1.5)}
            height={barH - 20}
          />
        ) : null}
      </svg>
      {/* Every piece keeps an identity even when it's too narrow to label in
        the bar — the legend mirrors the printed pack's leader list and
        shares the same selection. */}
      <ol className="cutplan-piece-legend">
        {bar.cuts.map((cut, index) => {
          const key = `b${bar.bar_index}-c${index}`;
          const code = `B${bar.bar_index}-${cut.sequence ?? index + 1}`;
          const shopCode = pieceCodes[cut.piece_id];
          const angleL =
            cut.angle_left != null && num(cut.angle_left) !== 90 ? num(cut.angle_left) : null;
          const angleR =
            cut.angle_right != null && num(cut.angle_right) !== 90 ? num(cut.angle_right) : null;
          return (
            <li key={key}>
              <button
                type="button"
                className={selectedKey === key ? "is-selected" : ""}
                onClick={() => onSelect({ kind: "cut", key, code, shopCode, piece: cut })}
              >
                {cut.sequence ?? index + 1} · {shopCode ?? pieceLabel(cut, code)} ·{" "}
                {fmtMm(cut.length_mm)}mm
                {angleL !== null || angleR !== null ? ` · ${angleL ?? 90}°/${angleR ?? 90}°` : ""}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function CutPlanSheetSvg({
  layout,
  selectedMember,
  selectedKey,
  pieceCodes,
  onSelect,
}: {
  layout: SheetLayout;
  selectedMember: string | null;
  selectedKey: string | null;
  pieceCodes: Record<string, string>;
  onSelect: (ref: PieceRef) => void;
}) {
  const w = num(layout.sheet_width_mm) || 1;
  const h = num(layout.sheet_height_mm) || 1;
  const vw = 320;
  const vh = Math.max(Math.round((h / w) * vw), 60);
  return (
    <div className="cutplan-sheetwrap">
      <svg
        className="cutplan-sheet"
        viewBox={`0 0 ${vw} ${vh}`}
        role="group"
        aria-label={`${t("production.optimizeSheet")} #${layout.sheet_index}`}
      >
        <rect className="cutplan-sheet-frame" x={0} y={0} width={vw} height={vh} rx={2} />
        {layout.placements.map((piece, index) => {
          const key = `s${layout.sheet_index}-p${index}`;
          const code = `S${layout.sheet_index}-${piece.sequence ?? index + 1}`;
          const shopCode = pieceCodes[piece.piece_id];
          const memberHit = selectedMember !== null && memberKey(piece) === selectedMember;
          const selected = selectedKey === key;
          const px = (num(piece.x_mm) / w) * vw;
          const py = (num(piece.y_mm) / h) * vh;
          const pw = Math.max((num(piece.width_mm) / w) * vw, 1);
          const ph = Math.max((num(piece.height_mm) / h) * vh, 1);
          return (
            <g
              key={key}
              className={`cutplan-nest${memberHit ? " is-member" : ""}${
                selected ? " is-selected" : ""
              }`}
              onClick={() => onSelect({ kind: "nest", key, code, shopCode, piece })}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect({ kind: "nest", key, code, shopCode, piece });
                }
              }}
            >
              <rect x={px} y={py} width={pw} height={ph} rx={1} />
              {pw > 30 && ph > 12 ? (
                <text x={px + pw / 2} y={py + ph / 2} textAnchor="middle" dominantBaseline="middle">
                  {shopCode ?? pieceLabel(piece, code)}
                  {piece.rotated ? " ⟳" : ""}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <ol className="cutplan-piece-legend">
        {layout.placements.map((piece, index) => {
          const key = `s${layout.sheet_index}-p${index}`;
          const code = `S${layout.sheet_index}-${piece.sequence ?? index + 1}`;
          const shopCode = pieceCodes[piece.piece_id];
          return (
            <li key={key}>
              <button
                type="button"
                className={selectedKey === key ? "is-selected" : ""}
                onClick={() => onSelect({ kind: "nest", key, code, shopCode, piece })}
              >
                {piece.sequence ?? index + 1} · {shopCode ?? pieceLabel(piece, code)} ·{" "}
                {fmtMm(piece.width_mm)}×{fmtMm(piece.height_mm)}
                {piece.rotated ? ` ${t("production.optimizeRotated")}` : ""}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function shortId(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : "—";
}

/** Human piece identity for the workshop: the workshop SKU the printed
 * manifest carries plus the cut code (bar/sheet + sequence — unique in the
 * plan; sku + unit_index alone collide across piece groups). */
function pieceLabel(piece: CutPlacement | NestPlacement, code: string): string {
  return piece.workshop_sku ? `${piece.workshop_sku} · ${code}` : code;
}

export function CutPlanView({
  optimization,
  labels = {},
  pieceCodes = {},
}: {
  optimization: WorkOrderOptimization;
  /** Shop codes matching the printed packs (V-xx/H-xx/P-xx) keyed by id. */
  labels?: Record<string, string>;
  /** Printed piece codes (M-xx/R-xx/I-xx) keyed by piece_id. */
  pieceCodes?: Record<string, string>;
}) {
  const [selected, setSelected] = useState<PieceRef | null>(null);
  const bars = optimization.bars?.workshop_cut_plan ?? [];
  const sheets = optimization.sheets ?? [];
  const unnested = optimization.unnested ?? [];
  const selectedMember = selected ? memberKey(selected.piece) : null;

  const detail = useMemo(() => {
    if (!selected) return null;
    const piece = selected.piece;
    const isCut = selected.kind === "cut";
    const cut = piece as CutPlacement;
    const nest = piece as NestPlacement;
    const angles =
      isCut && (cut.angle_left != null || cut.angle_right != null)
        ? `${cut.angle_left ?? "90"}° / ${cut.angle_right ?? "90"}°`
        : null;
    return {
      id: selected.shopCode ?? pieceLabel(piece, selected.code),
      planRef: selected.code,
      kind: selected.kind,
      sku: piece.workshop_sku ?? "—",
      material: cut.material ?? "—",
      color: cut.color ?? "—",
      role: cutRoleLabel(cut.role),
      position:
        (piece.source_position_id && labels[piece.source_position_id]) ??
        shortId(piece.source_position_id),
      bay: (piece.bay_id && labels[piece.bay_id]) ?? shortId(piece.bay_id),
      leaf: (piece.leaf_id && labels[piece.leaf_id]) ?? shortId(piece.leaf_id),
      unit: piece.unit_index ?? 1,
      measure: isCut
        ? `${fmtMm(cut.length_mm)} mm`
        : `${fmtMm(nest.width_mm)}×${fmtMm(nest.height_mm)} mm${nest.rotated ? ` (${t("production.optimizeRotated")})` : ""}`,
      angles,
      memberCount: 0,
    };
  }, [selected, labels]);

  if (detail && selected) {
    // Count every placement sharing this member across bars + sheets.
    let count = 0;
    for (const bar of bars) {
      for (const cut of bar.cuts) {
        if (memberKey(cut) === selectedMember) count += 1;
      }
    }
    for (const sheet of sheets) {
      for (const piece of sheet.placements) {
        if (memberKey(piece) === selectedMember) count += 1;
      }
    }
    detail.memberCount = count;
  }

  return (
    <div className="cutplan">
      <div className="cutplan-canvas">
        {bars.map((bar) => (
          <figure key={bar.bar_index} className="cutplan-bar-row">
            <figcaption>
              <strong>
                {t("production.optimizeBar")} #{bar.bar_index}
              </strong>{" "}
              {bar.commercial_sku} · {fmtMm(bar.stock_length_mm)} mm ·{" "}
              {t("production.cutplanYield")} {fmtPct(bar.yield_pct)}% ·{" "}
              {t("production.cutplanRemainder")} {fmtMm(bar.remainder_mm)} mm
            </figcaption>
            <CutPlanBarSvg
              bar={bar}
              selectedMember={selectedMember}
              selectedKey={selected?.key ?? null}
              pieceCodes={pieceCodes}
              onSelect={setSelected}
            />
          </figure>
        ))}
        {sheets.length ? (
          <div className="cutplan-sheets">
            {sheets.map((layout) => (
              <figure key={layout.sheet_index} className="cutplan-sheet-card">
                <figcaption>
                  <strong>
                    {t("production.optimizeSheet")} #{layout.sheet_index}
                  </strong>{" "}
                  {layout.purchasing_sku} · {fmtMm(layout.sheet_width_mm)}×
                  {fmtMm(layout.sheet_height_mm)} mm · {t("production.cutplanYield")}{" "}
                  {fmtPct(layout.yield_pct)}%
                </figcaption>
                <CutPlanSheetSvg
                  layout={layout}
                  selectedMember={selectedMember}
                  selectedKey={selected?.key ?? null}
                  pieceCodes={pieceCodes}
                  onSelect={setSelected}
                />
              </figure>
            ))}
          </div>
        ) : null}
        {unnested.length ? (
          <div className="cutplan-unnested">
            <h4>{t("production.operatorUnnested")}</h4>
            <table className="production-plan">
              <thead>
                <tr>
                  <th>{t("production.cutplanPiece")}</th>
                  <th>{t("production.optimizeSize")}</th>
                  <th>{t("production.operatorUnnestedReason")}</th>
                </tr>
              </thead>
              <tbody>
                {unnested.map((pane, index) => (
                  <tr key={index}>
                    <td>
                      {pane.group ?? "—"}
                      {pane.quantity > 1 ? ` ×${pane.quantity}` : ""}
                    </td>
                    <td>
                      {fmtMm(pane.width_mm)}×{fmtMm(pane.height_mm)} mm
                    </td>
                    <td>{tOptional(`production.unnestedReason.${pane.reason}`) ?? pane.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
      <aside className="cutplan-detail" aria-label={t("production.cutplanDetail")}>
        {detail ? (
          <dl>
            <div>
              <dt>{t("production.cutplanPiece")}</dt>
              <dd>
                {detail.id}
                {selected?.shopCode ? (
                  <span className="cutplan-planref"> · {detail.planRef}</span>
                ) : null}
              </dd>
            </div>
            <div>
              <dt>{t("production.cutplanRole")}</dt>
              <dd>{detail.role}</dd>
            </div>
            <div>
              <dt>{t("production.cutplanMeasure")}</dt>
              <dd>{detail.measure}</dd>
            </div>
            {detail.angles ? (
              <div>
                <dt>{t("production.cutplanAngles")}</dt>
                <dd>{detail.angles}</dd>
              </div>
            ) : null}
            <div>
              <dt>{t("production.cutplanMaterial")}</dt>
              <dd>
                {detail.material}
                {detail.color !== "—" ? ` · ${detail.color}` : ""}
              </dd>
            </div>
            <div>
              <dt>{t("production.optimizeSku")}</dt>
              <dd>{detail.sku}</dd>
            </div>
            <div>
              <dt>{t("production.cutplanOrigin")}</dt>
              <dd>
                {t("production.cutplanPosition")} {detail.position} · {t("production.cutplanBay")}{" "}
                {detail.bay} · {t("production.cutplanLeaf")} {detail.leaf} · u{detail.unit}
              </dd>
            </div>
            <div>
              <dt>{t("production.cutplanMemberCuts")}</dt>
              <dd>{detail.memberCount}</dd>
            </div>
          </dl>
        ) : (
          <p className="cutplan-detail-empty">{t("production.cutplanDetailHint")}</p>
        )}
      </aside>
    </div>
  );
}
