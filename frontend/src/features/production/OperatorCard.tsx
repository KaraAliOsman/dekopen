/** §12 operator card — what the station makes, from which stock, in which
 * order. Scoped to one routing step: material pull list (reservations and
 * remnants of that step's stock kinds), the machining sequence for CUT
 * (saw boundaries + member ops reconstructed from the sealed plan), and the
 * piece list with dimensions/angles/origins. Every value is sealed evidence
 * from the trace read — nothing is recomputed here. */

import { useState } from "react";

import { fmtMm, fmtQty, formatDateTime } from "../../format";
import { t, tOptional } from "../../i18n/es-CL";
import {
  STEP_STOCK_KINDS,
  cutRoleLabel,
  opBasisLabel,
  opBoundaryLabel,
  opFaceLabel,
  opLabel,
  opReferenceLabel,
  stationCodeLabel,
  stockKindLabel,
} from "./labels";
import type { ProductionOrderTrace, ProductionStep } from "../../api/generated/models";
import { formatDate } from "../../format";

type Reservation = {
  kind?: string;
  sku?: string;
  name?: string;
  variant_key?: string;
  unit?: string;
  needed?: string;
  on_hand?: string;
  reserved?: string;
  short?: string;
  consumed_at?: string;
};

type Remnant = {
  id?: string;
  kind?: string;
  status?: string;
  rack_location?: string;
  length_mm?: string;
  width_mm?: string;
  height_mm?: string;
  sheet_workshop_sku?: string;
  consumed_order_id?: string;
};

type Op = {
  operation_id?: string;
  kind?: string;
  host_kind?: string;
  host?: string;
  x_mm?: string;
  y_mm?: string;
  u_mm?: string;
  reference?: string;
  face?: string;
  tool_id?: string;
  sequence_no?: number;
  station?: string;
  angle_left_deg?: string;
  angle_right_deg?: string;
  depth_mm?: string;
  basis?: string;
  detail?: Record<string, unknown>;
};

type UnclaimedOps = {
  station?: string;
  operation_count?: number;
  kinds?: string[];
};

type MemberMeta = {
  cut_length_mm?: string;
  workshop_sku?: string;
  role?: string;
  axis?: string;
  bay_id?: string;
  leaf_id?: string;
};

/** One member strip per physical piece: the op marks sit at their member
 * coordinate (u = mm from the member start, the datum the printed pack
 * calls Ext. A) so the operator verifies position on the part, not in an
 * abstract coordinate table. */
function MemberOpsStrip({
  memberCode,
  locationCode,
  lengthMm,
  ops,
}: {
  memberCode: string;
  locationCode?: string;
  lengthMm: number;
  ops: Op[];
}) {
  const W = 560;
  const H = 56;
  const pad = 24;
  const barY = 30;
  const barH = 12;
  const scale = Math.max(lengthMm, 1);
  const ux = (u: number) => pad + (u / scale) * (W - pad * 2);
  const opX = (op: Op): number | null => {
    const u = op.u_mm != null ? Number(op.u_mm) : null;
    if (u != null) {
      return op.reference === "member_end" ? ux(scale - u) : ux(u);
    }
    if (op.face === "START_EDGE") return pad;
    if (op.face === "END_EDGE") return W - pad;
    return null;
  };
  const unplaced = ops.filter((op) => opX(op) === null);
  return (
    <figure className="operator-member-strip">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={memberCode}>
        <text x={pad} y={12} className="operator-member-datum">
          {t("production.operatorDatumStart")}
        </text>
        <text x={W - pad} y={12} textAnchor="end" className="operator-member-datum">
          {t("production.operatorDatumEnd")} · {fmtMm(String(lengthMm))} mm
        </text>
        <line x1={pad} y1={16} x2={pad} y2={barY - 2} className="operator-member-datum-line" />
        <line
          x1={W - pad}
          y1={16}
          x2={W - pad}
          y2={barY - 2}
          className="operator-member-datum-line"
        />
        <rect
          x={pad}
          y={barY}
          width={W - pad * 2}
          height={barH}
          rx={2}
          className="operator-member-bar"
        />
        {ops.map((op, index) => {
          const x = opX(op);
          if (x === null) return null;
          return (
            <g key={op.operation_id ?? index}>
              <title>
                {`${index + 1} · ${opLabel(op)} · u=${fmtMm(op.u_mm)} · ${opFaceLabel(op.face)}`}
              </title>
              <line
                x1={x}
                y1={barY - 4}
                x2={x}
                y2={barY + barH + 4}
                className="operator-member-op"
              />
              <text x={x} y={barY + barH + 12} textAnchor="middle" className="operator-member-seq">
                {index + 1}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption>
        {memberCode}
        {locationCode ? ` · ${locationCode}` : ""}
        {unplaced.length > 0
          ? ` · ${t("production.operatorNoPosition")}: ${unplaced
              .map((op) => opLabel(op))
              .join(", ")}`
          : ""}
      </figcaption>
    </figure>
  );
}

type CutPiece = {
  sequence?: number;
  workshop_sku?: string;
  role?: string;
  length_mm?: string;
  angle_left?: string;
  angle_right?: string;
  unit_index?: number;
  bay_id?: string;
  leaf_id?: string;
  sagitta_mm?: string;
  piece_id?: string;
  code?: string;
};

type SheetPiece = {
  piece_id?: string;
  role?: string;
  width_mm?: string;
  height_mm?: string;
  bay_id?: string;
  leaf_id?: string;
  unit_index?: number;
  workshop_sku?: string;
  code?: string;
};

function _reservations(trace: ProductionOrderTrace): Reservation[] {
  return (trace.stock?.reservations as Reservation[] | undefined) ?? [];
}

function _remnants(trace: ProductionOrderTrace): Remnant[] {
  return (trace.stock?.remnants as Remnant[] | undefined) ?? [];
}

function _ops(trace: ProductionOrderTrace): Op[] {
  const ops = trace.operations?.items;
  return Array.isArray(ops) ? (ops as Op[]) : [];
}

function _bars(trace: ProductionOrderTrace): Array<Record<string, unknown>> {
  return (trace.plan?.bars as Array<Record<string, unknown>> | undefined) ?? [];
}

function _sheets(trace: ProductionOrderTrace): Array<Record<string, unknown>> {
  return (trace.plan?.sheets as Array<Record<string, unknown>> | undefined) ?? [];
}

/** Shop location codes (V-xx bays / H-xx leaves / P-xx positions) matching the
 * printed packs — the backend emits the same map it uses for the PDFs. */
function _labels(trace: ProductionOrderTrace): Record<string, string> {
  return (trace.labels as Record<string, string> | undefined) ?? {};
}

function _loc(
  labels: Record<string, string>,
  piece: { unit_index?: number; bay_id?: string; leaf_id?: string },
): string {
  const parts: string[] = [];
  if (piece.bay_id) {
    parts.push(labels[piece.bay_id] ?? `b·${piece.bay_id.slice(0, 4)}`);
  }
  if (piece.leaf_id) {
    parts.push(labels[piece.leaf_id] ?? `h·${piece.leaf_id.slice(0, 4)}`);
  }
  const prefix = piece.unit_index ? `u${piece.unit_index}` : "";
  return [prefix, ...parts].filter(Boolean).join(" · ");
}

function _isShort(value: string | undefined): boolean {
  return !!value && Number(value) > 0;
}

export type QcCheckInput = {
  check: string;
  expected: string;
  actual: string;
  item_code: string;
  result: "PASS" | "FAIL";
};

export function OperatorStepCard({
  step,
  trace,
  traceBusy,
  actionBar,
  onQcCheck,
  opsCheckable = false,
  opsDone = [],
  onOpsDoneChange,
}: {
  step: ProductionStep;
  trace: ProductionOrderTrace | null;
  traceBusy: boolean;
  // The step's live transitions rendered as a sticky footer — the operator's
  // primary action stays reachable while materials and ops scroll by.
  actionBar?: React.ReactNode;
  onQcCheck?: (stepId: string, check: QcCheckInput) => void;
  // Plan-evidence stations (MACHINING, PROFILE_CUT, REINFORCEMENT_CUT):
  // COMPLETE must declare every routed member op — the card shows one
  // checkbox per operation and reports the picked ids upward.
  opsCheckable?: boolean;
  opsDone?: string[];
  onOpsDoneChange?: (ids: string[]) => void;
}) {
  const kinds = STEP_STOCK_KINDS[step.code] ?? [];
  const reservations = trace ? _reservations(trace) : [];
  const material = reservations.filter((row) => kinds.includes(row.kind ?? ""));
  const remnants = trace ? _remnants(trace).filter((row) => kinds.includes(row.kind ?? "")) : [];
  const unmapped = trace ? ((trace.stock?.unmapped_stock_skus as string[] | undefined) ?? []) : [];
  const blockers = material.filter((row) => _isShort(row.short));
  const ops = trace ? _ops(trace) : [];
  const bars = trace ? _bars(trace) : [];
  const sheets = trace ? _sheets(trace) : [];
  const labels = trace ? _labels(trace) : {};

  // Ops land on the station the frozen process authority declares for their
  // kind (END_MACHINING→MACHINING, HANDLE_PREP→HARDWARE on frameless, ...).
  // A kind absent from the map is never silently sent to the saw — it
  // surfaces as an unassigned blocker. Orders frozen before the authority
  // model keep the legacy saw/member split.
  const stationMap = trace?.operations?.station_map as Record<string, string> | undefined;
  const stepOps = stationMap
    ? ops.filter((op) => stationMap[String(op.kind ?? "")] === step.code)
    : ops.filter((op) => (op.kind === "SAW_CUT" ? step.code === "CUT" : step.code === "MACHINING"));
  const unassignedOps = stationMap
    ? ops.filter((op) => !(String(op.kind ?? "") in stationMap))
    : [];
  const unclaimedStations =
    ((trace?.operations as { unclaimed?: UnclaimedOps[] } | undefined)?.unclaimed as
      UnclaimedOps[] | undefined) ?? [];
  const memberMeta =
    ((trace?.operations as { members?: Record<string, MemberMeta> } | undefined)?.members as
      Record<string, MemberMeta> | undefined) ?? {};
  const planInvalidated = Boolean(
    (trace?.operations as { plan_invalidated?: boolean } | undefined)?.plan_invalidated,
  );
  const sawOps = stepOps.filter((op) => op.kind === "SAW_CUT");
  const memberOps = stepOps
    .filter((op) => op.kind !== "SAW_CUT")
    .sort((a, b) => (a.sequence_no ?? 0) - (b.sequence_no ?? 0));
  const toggleOp = (operationId: string): void => {
    onOpsDoneChange?.(
      opsDone.includes(operationId)
        ? opsDone.filter((id) => id !== operationId)
        : [...opsDone, operationId],
    );
  };
  // Stations that consume no stock (WELD, CLEAN, SASH_ASSEMBLE, CRIMP,
  // QC, PACK) still own the physical pieces — the sealed cut/sheet lists
  // are their work checklist, not a CUT-only artifact.
  const consumesStock = kinds.length > 0;
  // Whether the order carries a live plan at all — without it, an empty
  // material table means "not computed yet", never "nothing needed".
  const hasPlan = Boolean((trace?.plan as Record<string, unknown> | undefined)?.optimized_at);
  const showPieces = step.code === "CUT" || step.code === "GLAZE" || !consumesStock;
  const cutPieces: Array<{ barIndex: number; source?: string } & CutPiece> = [];
  if (step.code === "CUT" || !consumesStock) {
    for (const bar of bars) {
      const cuts = (bar.cuts as CutPiece[] | undefined) ?? [];
      for (const cut of cuts) {
        cutPieces.push({
          barIndex: Number(bar.bar_index ?? 0),
          source: String(bar.source ?? "NEW"),
          ...cut,
        });
      }
    }
    cutPieces.sort((a, b) => a.barIndex - b.barIndex || (a.sequence ?? 0) - (b.sequence ?? 0));
  }
  const sheetPieces: SheetPiece[] = [];
  if (showPieces) {
    for (const sheet of sheets) {
      for (const piece of (sheet.pieces as SheetPiece[] | undefined) ?? []) {
        sheetPieces.push(piece);
      }
    }
  }
  // Glass/panels that no declared sheet could host (shaped outlines,
  // oversized pieces) never appear inside a sheet layout — at GLAZE they'd
  // be invisible without this list, so the operator would cut only part of
  // the order's glass.
  const unnestedPanes: Array<Record<string, unknown>> = showPieces
    ? (((trace?.plan as Record<string, unknown> | undefined)?.unnested as
        Array<Record<string, unknown>> | undefined) ?? [])
    : [];
  const totalPieces =
    bars.reduce((count, bar) => count + ((bar.cuts as unknown[] | undefined) ?? []).length, 0) +
    sheetPieces.length;

  return (
    <section className="operator-card" aria-label={t("production.operatorTitle")}>
      <header className="operator-card-head">
        <h3>
          {t("production.operatorTitle")}: {step.label}
        </h3>
        {(step.work_center_name ?? step.work_center_code) ? (
          <span className="production-step-center">
            {step.work_center_name ?? step.work_center_code}
          </span>
        ) : null}
      </header>
      {!trace ? (
        <p className="production-trace-empty">
          {traceBusy ? t("production.traceLoading") : t("production.operatorNoOps")}
        </p>
      ) : (
        <div className="operator-card-body">
          {blockers.length ||
          (step.code === "CUT" && unmapped.length) ||
          unassignedOps.length ||
          unclaimedStations.length ||
          planInvalidated ? (
            <p className="operator-blockers" role="alert">
              {blockers.length ? t("production.operatorBlockers") : ""}
              {unassignedOps.length
                ? ` · ${t("production.operatorUnassignedOps")}: ${[
                    ...new Set(unassignedOps.map((op) => opLabel(op))),
                  ].join(", ")}`
                : ""}
              {unclaimedStations.length
                ? ` · ${t("production.operatorUnclaimedOps")}: ${unclaimedStations
                    .map(
                      (group) =>
                        `${stationCodeLabel(group.station)} (${group.operation_count ?? 0})`,
                    )
                    .join(", ")}`
                : ""}
              {planInvalidated ? ` · ${t("production.operatorPlanStale")}` : ""}
              {unmapped.length && step.code === "CUT"
                ? ` · ${t("production.operatorUnmapped")}: ${unmapped.join(", ")}`
                : ""}
            </p>
          ) : null}

          {kinds.length ? (
            <div className="operator-section">
              <h4>{t("production.operatorMaterial")}</h4>
              {material.length ? (
                <table className="production-plan">
                  <thead>
                    <tr>
                      <th>{t("production.stockSku")}</th>
                      <th>{t("production.stockNeeded")}</th>
                      <th>{t("production.stockReserved")}</th>
                      <th>{t("production.stockShort")}</th>
                      <th>{t("production.stockConsumedAt")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {material.map((row, index) => (
                      <tr
                        key={`${row.kind}-${row.sku}-${index}`}
                        className={_isShort(row.short) ? "operator-row-short" : ""}
                      >
                        <td>
                          {row.name ?? row.sku ?? "—"}
                          {row.sku && row.sku !== row.name ? ` · ${row.sku}` : ""}
                          {row.unit ? ` · ${row.unit}` : ""}
                        </td>
                        <td>{row.needed ?? "0"}</td>
                        <td>{row.reserved ?? "0"}</td>
                        <td>
                          {_isShort(row.short) ? (
                            <strong className="production-stock-short">{row.short}</strong>
                          ) : (
                            "0"
                          )}
                        </td>
                        <td>{row.consumed_at ? formatDate(row.consumed_at) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="production-trace-empty">
                  {hasPlan
                    ? unnestedPanes.length
                      ? t("production.operatorNoStockButPanes")
                      : t("production.operatorNoStock")
                    : t("production.operatorNoPlan")}
                </p>
              )}
              {remnants.length ? (
                <ul className="operator-remnants">
                  {remnants.map((remnant) => (
                    <li key={remnant.id}>
                      {stockKindLabel(remnant.kind)}
                      {remnant.length_mm ? ` · ${fmtMm(remnant.length_mm)} mm` : ""}
                      {remnant.width_mm ? ` × ${fmtMm(remnant.width_mm)}` : ""}
                      {remnant.height_mm ? ` × ${fmtMm(remnant.height_mm)}` : ""}
                      {remnant.sheet_workshop_sku ? ` · ${remnant.sheet_workshop_sku}` : ""}
                      {remnant.rack_location
                        ? ` · ${t("production.operatorRack")}: ${remnant.rack_location}`
                        : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {step.code === "CUT" ||
          step.code === "MACHINING" ||
          stepOps.length ||
          (!consumesStock && (cutPieces.length || sheetPieces.length)) ? (
            <div className="operator-section">
              <h4>
                {step.code === "CUT" || step.code === "MACHINING" || stepOps.length
                  ? t("production.operatorSequence")
                  : t("production.operatorPieces")}
              </h4>
              {stepOps.length ? (
                <>
                  {sawOps.length ? (
                    <table className="production-plan operator-ops">
                      <thead>
                        <tr>
                          <th>{t("production.traceBar")}</th>
                          <th>x (mm)</th>
                          <th>{t("production.operatorAngles")}</th>
                          <th>{t("production.operatorCut")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sawOps.map((op) => (
                          <tr key={op.operation_id}>
                            <td>{String(op.host ?? "").replace("bar:", "")}</td>
                            <td>{fmtMm(op.x_mm)}</td>
                            <td>
                              {op.angle_left_deg ? `${fmtQty(op.angle_left_deg)}°` : "—"}
                              {" / "}
                              {op.angle_right_deg ? `${fmtQty(op.angle_right_deg)}°` : "—"}
                            </td>
                            <td>
                              {op.detail?.boundary
                                ? opBoundaryLabel(String(op.detail.boundary))
                                : op.detail?.sequence
                                  ? `#${String(op.detail.sequence)}`
                                  : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : null}
                  {memberOps.length ? (
                    <>
                      {opsCheckable && memberOps.length > 1 ? (
                        <button
                          type="button"
                          className="operator-ops-all"
                          onClick={() =>
                            onOpsDoneChange?.(
                              memberOps
                                .map((op) => op.operation_id)
                                .filter((id): id is string => Boolean(id)),
                            )
                          }
                        >
                          {t("production.opsDoneAll")}
                        </button>
                      ) : null}
                      <div className="operator-member-strips">
                        {Object.entries(
                          memberOps.reduce<Record<string, Op[]>>((acc, op) => {
                            const host = String(op.host ?? "");
                            (acc[host] = acc[host] ?? []).push(op);
                            return acc;
                          }, {}),
                        ).map(([host, hostOps]) => {
                          const meta = memberMeta[host] ?? {};
                          const code =
                            labels[host] ?? (meta.role ? cutRoleLabel(meta.role) : String(host));
                          const locationCode = _loc(labels, meta);
                          const length =
                            Number(meta.cut_length_mm ?? 0) ||
                            Math.max(...hostOps.map((op) => Number(op.u_mm ?? 0)), 1);
                          return (
                            <MemberOpsStrip
                              key={host}
                              memberCode={code}
                              locationCode={locationCode || undefined}
                              lengthMm={length}
                              ops={hostOps}
                            />
                          );
                        })}
                      </div>
                      <table className="production-plan operator-ops">
                        <thead>
                          <tr>
                            {opsCheckable ? (
                              <th aria-label={t("production.opsDoneColumn")} />
                            ) : null}
                            <th>{t("production.operatorOperation")}</th>
                            <th>{t("production.operatorHost")}</th>
                            <th>u (mm)</th>
                            <th>{t("production.operatorReference")}</th>
                            <th>{t("production.operatorFace")}</th>
                            <th>{t("production.operatorDepth")}</th>
                            <th>{t("production.operatorTool")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {memberOps.map((op) => {
                            const memberCode =
                              (op.host && labels[op.host]) ??
                              String(op.detail?.role ?? op.host ?? "—");
                            const shareCount = memberCode.split("·").length;
                            const opId = op.operation_id ?? "";
                            return (
                              <tr
                                key={op.operation_id}
                                className={
                                  opsCheckable && opsDone.includes(opId) ? "operator-op-done" : ""
                                }
                              >
                                {opsCheckable ? (
                                  <td>
                                    <input
                                      type="checkbox"
                                      aria-label={`${memberCode} · ${opLabel(op)}`}
                                      checked={opsDone.includes(opId)}
                                      onChange={() => toggleOp(opId)}
                                    />
                                  </td>
                                ) : null}
                                <td>
                                  {op.sequence_no ? `${op.sequence_no}. ` : ""}
                                  {opLabel(op)}
                                </td>
                                <td title={op.host ?? ""}>
                                  {memberCode}
                                  {shareCount > 1 ? ` · ×${shareCount}` : ""}
                                </td>
                                <td>{op.u_mm ?? "—"}</td>
                                <td>{opReferenceLabel(op.reference)}</td>
                                <td>{opFaceLabel(op.face)}</td>
                                <td>{op.depth_mm ?? "—"}</td>
                                <td title={opBasisLabel(op.basis)}>{op.tool_id ?? "—"}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </>
                  ) : null}
                </>
              ) : (
                <p className="production-trace-empty">
                  {hasPlan ? t("production.operatorStepNoOps") : t("production.operatorNoOps")}
                </p>
              )}
              {cutPieces.length ? (
                <table className="production-plan operator-pieces">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t("production.optimizeSku")}</th>
                      <th>{t("production.operatorRole")}</th>
                      <th>{t("production.traceLength")}</th>
                      <th>{t("production.operatorAngles")}</th>
                      <th>{t("production.operatorOrigin")}</th>
                      <th>{t("production.traceBar")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cutPieces.map((piece, index) => (
                      <tr
                        key={`${piece.piece_id ?? "x"}-${piece.unit_index ?? 0}-${piece.barIndex}-${piece.sequence}-${index}`}
                      >
                        <td>
                          {piece.code ? <strong>{piece.code} · </strong> : null}
                          {piece.sequence ?? "—"}
                        </td>
                        <td>{piece.workshop_sku ?? "—"}</td>
                        <td>{cutRoleLabel(piece.role)}</td>
                        <td>
                          {fmtMm(piece.length_mm)}
                          {piece.sagitta_mm ? ` · f ${fmtMm(piece.sagitta_mm)}` : ""}
                        </td>
                        <td>
                          {piece.angle_left ? `${fmtQty(piece.angle_left)}°` : "—"}
                          {" / "}
                          {piece.angle_right ? `${fmtQty(piece.angle_right)}°` : "—"}
                        </td>
                        <td>{_loc(labels, piece)}</td>
                        <td>
                          {piece.barIndex}
                          {piece.source === "REMNANT"
                            ? ` · ${t("production.traceSourceRemnant")}`
                            : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
            </div>
          ) : null}

          {(step.code === "GLAZE" || !consumesStock) && sheetPieces.length ? (
            <div className="operator-section">
              <h4>{t("production.operatorPieces")}</h4>
              <table className="production-plan operator-pieces">
                <thead>
                  <tr>
                    <th>{t("production.cutplanPiece")}</th>
                    <th>{t("production.operatorRole")}</th>
                    <th>{t("production.optimizeSize")}</th>
                    <th>{t("production.operatorOrigin")}</th>
                  </tr>
                </thead>
                <tbody>
                  {sheetPieces.map((piece, index) => (
                    <tr key={`${piece.piece_id ?? "x"}-${index}`}>
                      <td>
                        {piece.code ?? "—"}
                        {piece.workshop_sku ? ` · ${piece.workshop_sku}` : ""}
                      </td>
                      <td>{cutRoleLabel(piece.role)}</td>
                      <td>
                        {piece.width_mm ?? "—"} × {piece.height_mm ?? "—"}
                      </td>
                      <td>{_loc(labels, piece)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {unnestedPanes.length ? (
            <div className="operator-section">
              <h4>{t("production.operatorUnnested")}</h4>
              <table className="production-plan operator-pieces">
                <thead>
                  <tr>
                    <th>{t("production.operatorRole")}</th>
                    <th>{t("production.optimizeSize")}</th>
                    <th>{t("production.operatorOrigin")}</th>
                    <th>{t("production.operatorUnnestedReason")}</th>
                  </tr>
                </thead>
                <tbody>
                  {unnestedPanes.map((pane, index) => (
                    <tr key={index}>
                      <td>
                        {String(pane.group ?? "—")}
                        {pane.quantity ? ` ×${pane.quantity}` : ""}
                      </td>
                      <td>
                        {pane.width_mm ? fmtMm(String(pane.width_mm)) : "—"} ×{" "}
                        {pane.height_mm ? fmtMm(String(pane.height_mm)) : "—"}
                      </td>
                      <td>{_loc(labels, pane as { bay_id?: string; leaf_id?: string }) || "—"}</td>
                      <td>
                        {pane.reason
                          ? (tOptional(`production.unnestedReason.${pane.reason}`) ??
                            String(pane.reason))
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {step.code === "QC" ? (
            <QcCheckSection step={step} trace={trace} onQcCheck={onQcCheck} />
          ) : null}

          {!consumesStock && !cutPieces.length && !sheetPieces.length && !unnestedPanes.length ? (
            <p className="operator-summary">
              {hasPlan
                ? `${t("production.operatorNoStock")} · ${totalPieces} ${t("production.operatorPiecesTotal")}`
                : t("production.operatorNoPlan")}
            </p>
          ) : null}
        </div>
      )}
      {actionBar ? <footer className="operator-card-actions">{actionBar}</footer> : null}
    </section>
  );
}

type _QcCheckEntry = {
  id: string;
  check: string;
  expected: string;
  actual: string;
  item_code: string;
  result: string;
  created_at: string;
};

function _qcEntries(trace: ProductionOrderTrace | null, stepId: string): _QcCheckEntry[] {
  if (!trace) return [];
  const entries: _QcCheckEntry[] = [];
  for (const event of (trace.events as Array<Record<string, unknown>> | undefined) ?? []) {
    if (event?.event !== "QC_CHECK" || String(event.step_id ?? "") !== stepId) continue;
    const payload = (event.payload ?? {}) as { qc_check?: Record<string, unknown> };
    const check = payload.qc_check;
    if (!check || typeof check !== "object") continue;
    entries.push({
      id: String(event.id ?? `${check.check}-${entries.length}`),
      check: String(check.check ?? ""),
      expected: String(check.expected ?? ""),
      actual: String(check.actual ?? ""),
      item_code: String(check.item_code ?? ""),
      result: String(check.result ?? ""),
      created_at: String(event.created_at ?? ""),
    });
  }
  return entries;
}

function QcCheckSection({
  step,
  trace,
  onQcCheck,
}: {
  step: ProductionStep;
  trace: ProductionOrderTrace | null;
  onQcCheck?: (stepId: string, check: QcCheckInput) => void;
}) {
  const [itemCode, setItemCode] = useState("");
  const [checkName, setCheckName] = useState("");
  const [expected, setExpected] = useState("");
  const [actual, setActual] = useState("");
  const entries = _qcEntries(trace, step.id);
  const itemOptions = trace
    ? [...new Set(Object.values(trace.labels ?? {}).map(String))].sort()
    : [];
  const writable = !!onQcCheck && ["READY", "IN_PROGRESS", "BLOCKED"].includes(step.status);

  function submit(result: "PASS" | "FAIL"): void {
    if (!onQcCheck || !checkName.trim()) return;
    onQcCheck(step.id, {
      check: checkName.trim(),
      expected: expected.trim(),
      actual: actual.trim(),
      item_code: itemCode,
      result,
    });
    setCheckName("");
    setExpected("");
    setActual("");
  }

  return (
    <div className="operator-section operator-qc">
      <h4>{t("production.qcChecksTitle")}</h4>
      {entries.length ? (
        <table className="production-plan operator-qc-ledger">
          <thead>
            <tr>
              <th>{t("production.qcCheck")}</th>
              <th>{t("production.qcExpected")}</th>
              <th>{t("production.qcActual")}</th>
              <th>{t("production.qcItem")}</th>
              <th>{t("production.qcResult")}</th>
              <th>{t("production.qcTime")}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.check}</td>
                <td>{entry.expected || "—"}</td>
                <td>{entry.actual || "—"}</td>
                <td>{entry.item_code ? <strong>{entry.item_code}</strong> : "—"}</td>
                <td>
                  <strong className={entry.result === "FAIL" ? "qc-result-fail" : "qc-result-pass"}>
                    {entry.result === "FAIL" ? t("production.qcFail") : t("production.qcPass")}
                  </strong>
                </td>
                <td>{formatDateTime(entry.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="production-trace-empty">{t("production.qcChecksEmpty")}</p>
      )}
      {writable ? (
        <div className="operator-qc-form">
          <select
            aria-label={t("production.qcItem")}
            value={itemCode}
            onChange={(event) => setItemCode(event.target.value)}
          >
            <option value="">{t("production.qcItemAny")}</option>
            {itemOptions.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
          <input
            aria-label={t("production.qcCheck")}
            placeholder={t("production.qcCheckPlaceholder")}
            value={checkName}
            onChange={(event) => setCheckName(event.target.value)}
          />
          <input
            aria-label={t("production.qcExpected")}
            placeholder={t("production.qcExpected")}
            value={expected}
            onChange={(event) => setExpected(event.target.value)}
          />
          <input
            aria-label={t("production.qcActual")}
            placeholder={t("production.qcActual")}
            value={actual}
            onChange={(event) => setActual(event.target.value)}
          />
          <button
            type="button"
            className="qc-submit-pass"
            disabled={!checkName.trim()}
            onClick={() => submit("PASS")}
          >
            {t("production.qcPass")}
          </button>
          <button
            type="button"
            className="qc-submit-fail"
            disabled={!checkName.trim()}
            onClick={() => submit("FAIL")}
          >
            {t("production.qcFail")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
