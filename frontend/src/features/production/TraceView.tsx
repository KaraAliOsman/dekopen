/** §11 traceability rendering — the sealed chain a work order assembled:
 * project → version → position → bars/sheets with per-piece origins,
 * stock ledger movements and remnants, and the backward piece lookup.
 * Narrow views over the trace payload's open dicts — every value shown is
 * evidence stored at seal time, never recomputed client-side. */

import { fmtMm } from "../../format";
import { t, tOptional } from "../../i18n/es-CL";
import { domainLabel } from "../../i18n/domainLabels";
import {
  opFaceLabel,
  opKindLabel,
  opReferenceLabel,
  remnantStatusLabel,
  stockKindLabel,
  traceNoteLabel,
} from "./labels";
import type {
  ProductionOrderTracePlan,
  ProductionOrderTraceStock,
  ProductionPieceTrace,
} from "../../api/generated/models";

type TraceBar = {
  bar_index?: number;
  commercial_sku?: string;
  material?: string;
  color?: string;
  source?: string;
  cuts?: Array<Record<string, unknown>>;
};

/** Origen de barra/lámina sellado en la traza — NEW/REMNANT llegan como
 * códigos del motor y se etiquetan aquí, nunca en crudo. */
function traceSourceLabel(source: string | undefined): string {
  if (source === "REMNANT") return t("production.traceSourceRemnant");
  if (!source || source === "NEW") return t("production.traceSourceNew");
  return source;
}

/** Acabado declarado en el sistema — códigos conocidos se etiquetan; un
 * código propio del taller se muestra tal cual (es dato, no inglés). */
function finishLabel(code: string): string {
  return tOptional(`projects.color.${code}`) ?? code;
}

type TraceSheet = {
  sheet_index?: number;
  workshop_sku?: string;
  source?: string;
  pieces?: Array<Record<string, unknown>>;
};

type TraceMovement = {
  id?: string;
  movement_type?: string;
  quantity?: string;
  note?: string;
  created_at?: string;
  sku?: string;
  variant_key?: string;
};

type TraceRemnant = {
  id?: string;
  remnant_code?: string;
  kind?: string;
  status?: string;
  length_mm?: string;
  width_mm?: string;
  height_mm?: string;
  sheet_workshop_sku?: string;
  origin?: string;
  rack_location?: string;
};

export type PieceMatch = {
  work_order?: { id?: string; order_code?: string; status?: string };
  location?: {
    kind?: string;
    bar_index?: number;
    sheet_index?: number;
    position_code?: string;
    location_code?: string;
    piece?: {
      role?: string;
      length_mm?: string;
      bay_id?: string;
      leaf_id?: string;
      code?: string;
      unit_index?: number;
      sequence?: number;
      x_mm?: number | string;
    };
  };
  steps?: Array<{ sequence?: number; code?: string; label?: string; status?: string }>;
  operations?: Array<{
    operation_id?: string;
    kind?: string;
    member_label?: string;
    u_mm?: string;
    reference?: string;
    face?: string;
    depth_mm?: string;
    tool_id?: string;
    sequence_no?: number;
    station?: string;
  }>;
};

function _bars(plan: ProductionOrderTracePlan): TraceBar[] {
  return (plan.bars as TraceBar[] | undefined) ?? [];
}

function _sheets(plan: ProductionOrderTracePlan): TraceSheet[] {
  return (plan.sheets as TraceSheet[] | undefined) ?? [];
}

export function TracePlan({ plan }: { plan: ProductionOrderTracePlan }) {
  const bars = _bars(plan);
  const sheets = _sheets(plan);
  if (!bars.length && !sheets.length) return null;
  return (
    <div className="production-trace-plan">
      {bars.length ? (
        <table>
          <thead>
            <tr>
              <th>{t("production.traceBar")}</th>
              <th>{t("production.optimizeSku")}</th>
              <th>{t("production.traceSource")}</th>
              <th>{t("production.traceCuts")}</th>
            </tr>
          </thead>
          <tbody>
            {bars.map((bar, index) => (
              <tr key={bar.bar_index ?? index}>
                <td>{bar.bar_index ?? index + 1}</td>
                <td>
                  {bar.commercial_sku ?? "—"}
                  {bar.material ? ` · ${domainLabel("CutMaterialEnum", bar.material).label}` : ""}
                  {bar.color ? ` · ${finishLabel(bar.color)}` : ""}
                </td>
                <td>{traceSourceLabel(bar.source)}</td>
                <td>{bar.cuts?.length ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {sheets.length ? (
        <table>
          <thead>
            <tr>
              <th>{t("production.traceSheet")}</th>
              <th>{t("production.optimizeSku")}</th>
              <th>{t("production.traceSource")}</th>
              <th>{t("production.traceCuts")}</th>
            </tr>
          </thead>
          <tbody>
            {sheets.map((sheet, index) => (
              <tr key={sheet.sheet_index ?? index}>
                <td>{sheet.sheet_index ?? index + 1}</td>
                <td>{sheet.workshop_sku ?? "—"}</td>
                <td>{traceSourceLabel(sheet.source)}</td>
                <td>{sheet.pieces?.length ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

export function TraceStock({ stock }: { stock: ProductionOrderTraceStock }) {
  const movements = (stock.movements as TraceMovement[] | undefined) ?? [];
  const remnants = (stock.remnants as TraceRemnant[] | undefined) ?? [];
  if (!movements.length && !remnants.length) {
    return <p className="production-trace-empty">{t("production.traceStockEmpty")}</p>;
  }
  return (
    <div className="production-trace-stock">
      {movements.length ? (
        <table>
          <thead>
            <tr>
              <th>{t("production.traceMovement")}</th>
              <th>{t("production.optimizeSku")}</th>
              <th>{t("production.traceQty")}</th>
              <th>{t("production.traceNote")}</th>
            </tr>
          </thead>
          <tbody>
            {movements.map((movement) => (
              <tr key={movement.id}>
                <td>
                  {movement.movement_type
                    ? domainLabel("InventoryMovementMovementTypeEnum", movement.movement_type).label
                    : "—"}
                </td>
                <td>{movement.sku}</td>
                <td>{movement.quantity}</td>
                <td title={movement.note ?? undefined}>{traceNoteLabel(movement.note)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {remnants.length ? (
        <ul className="production-trace-remnants">
          {remnants.map((remnant) => (
            <li key={remnant.id}>
              {remnant.remnant_code ? <strong>{remnant.remnant_code} · </strong> : null}
              {remnant.rack_location ? <strong>{remnant.rack_location} · </strong> : null}
              {stockKindLabel(remnant.kind)} · {remnantStatusLabel(remnant.status)}
              {remnant.length_mm ? ` · ${fmtMm(remnant.length_mm)} mm` : ""}
              {remnant.width_mm ? ` × ${fmtMm(remnant.width_mm)}` : ""}
              {remnant.height_mm ? ` × ${fmtMm(remnant.height_mm)}` : ""}
              {remnant.sheet_workshop_sku ? ` · ${remnant.sheet_workshop_sku}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function TracePieceMatches({
  report,
  onSelectOrder,
}: {
  report: ProductionPieceTrace;
  onSelectOrder?: (orderId: string, stepCode?: string) => void;
}) {
  const matches = (report.matches as PieceMatch[] | undefined) ?? [];
  if (!matches.length) {
    return <p className="production-trace-empty">{t("production.tracePieceNone")}</p>;
  }
  return (
    <ul className="production-trace-matches">
      {matches.map((match, index) => {
        const body = (
          <>
            <strong>{match.work_order?.order_code ?? "—"}</strong>
            {" · "}
            {stockKindLabel(match.location?.kind)}
            {match.location?.kind === "BAR"
              ? ` · ${t("production.traceBar")} ${match.location.bar_index ?? "—"}`
              : ` · ${t("production.traceSheet")} ${match.location?.sheet_index ?? "—"}`}
            {match.location?.kind === "BAR" && match.location?.piece?.sequence != null
              ? ` · #${match.location.piece.sequence}`
              : ""}
            {match.location?.kind === "BAR" && match.location?.piece?.x_mm != null
              ? ` · x ${fmtMm(match.location.piece.x_mm)}`
              : ""}
            {match.location?.piece?.code ? ` · ${match.location.piece.code}` : ""}
            {match.location?.piece?.unit_index != null
              ? ` · u${match.location.piece.unit_index}`
              : ""}
            {match.location?.position_code ? ` · ${match.location.position_code}` : ""}
            {match.location?.location_code ? ` · ${match.location.location_code}` : ""}
            {match.location?.piece?.role
              ? ` · ${domainLabel("CatalogItemRoleEnum", match.location.piece.role).label}`
              : ""}
            {match.location?.piece?.length_mm
              ? ` · ${fmtMm(match.location.piece.length_mm)} mm`
              : ""}
            {match.steps?.length
              ? ` · ${match.steps.filter((s) => s.status === "DONE").length}/${match.steps.length} ${t("production.stepsShort")}`
              : ""}
            {match.operations?.length ? (
              <ul className="production-trace-ops">
                {match.operations.map((op) => (
                  <li key={op.operation_id}>
                    {op.member_label ? `${op.member_label} · ` : ""}
                    {op.sequence_no ? `${op.sequence_no}. ` : ""}
                    {opKindLabel(op.kind)}
                    {op.u_mm ? ` · u ${op.u_mm} mm` : ""}
                    {op.reference ? ` · ${opReferenceLabel(op.reference)}` : ""}
                    {op.face ? ` · ${opFaceLabel(op.face)}` : ""}
                    {op.depth_mm ? ` · ${op.depth_mm} mm` : ""}
                    {op.tool_id ? ` · ${op.tool_id}` : ""}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        );
        const orderId = match.work_order?.id;
        // The op's station names the step the scanned piece belongs to —
        // deep-link opens that card, not just the order.
        const station = match.operations?.find((op) => op.station)?.station;
        return (
          <li key={`${orderId ?? "wo"}-${index}`}>
            {orderId && onSelectOrder ? (
              <button
                type="button"
                className="production-trace-match"
                onClick={() => onSelectOrder(orderId, station)}
              >
                {body}
              </button>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ul>
  );
}
