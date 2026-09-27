/** §12 operator card — what the station makes, from which stock, in which
 * order. Scoped to one routing step: material pull list (reservations and
 * remnants of that step's stock kinds), the machining sequence for CUT
 * (saw boundaries + member ops reconstructed from the sealed plan), and the
 * piece list with dimensions/angles/origins. Every value is sealed evidence
 * from the trace read — nothing is recomputed here. */

import { useState } from "react";

import { fmtMm, formatDateTime } from "../../format";
import { t } from "../../i18n/es-CL";
import { opKindLabel, stockKindLabel } from "./labels";
import type { ProductionOrderTrace, ProductionStep } from "../../api/generated/models";
import { formatDate } from "../money";

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
  angle_left_deg?: string;
  angle_right_deg?: string;
  depth_mm?: string;
  basis?: string;
  detail?: Record<string, unknown>;
};

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

/** Stock kinds each routing step physically consumes — mirrors the backend's
 * consume mapping (bars/sheets at CUT, kits/fittings at ASSEMBLE/HARDWARE,
 * panels at GLAZE); QC, PACK and the process steps reserve nothing. */
const STEP_STOCK_KINDS: Record<string, string[]> = {
  CUT: ["BAR", "SHEET"],
  ASSEMBLE: ["HARDWARE_KIT", "FITTING"],
  HARDWARE: ["HARDWARE_KIT", "FITTING"],
  GLAZE: ["PANEL"],
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
  onQcCheck,
}: {
  step: ProductionStep;
  trace: ProductionOrderTrace | null;
  traceBusy: boolean;
  onQcCheck?: (stepId: string, check: QcCheckInput) => void;
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
  const sawOps = stepOps.filter((op) => op.kind === "SAW_CUT");
  const memberOps = stepOps.filter((op) => op.kind !== "SAW_CUT");
  const cutPieces: Array<{ barIndex: number; source?: string } & CutPiece> = [];
  if (step.code === "CUT") {
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
  if (step.code === "GLAZE" || step.code === "CUT") {
    for (const sheet of sheets) {
      for (const piece of (sheet.pieces as SheetPiece[] | undefined) ?? []) {
        sheetPieces.push(piece);
      }
    }
  }
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
          {blockers.length || (step.code === "CUT" && unmapped.length) || unassignedOps.length ? (
            <p className="operator-blockers" role="alert">
              {blockers.length ? t("production.operatorBlockers") : ""}
              {unassignedOps.length
                ? ` · ${t("production.operatorUnassignedOps")}: ${[
                    ...new Set(unassignedOps.map((op) => opKindLabel(op.kind))),
                  ].join(", ")}`
                : ""}
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
                      <th>{t("production.stockConsumed")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {material.map((row, index) => (
                      <tr
                        key={`${row.kind}-${row.sku}-${index}`}
                        className={_isShort(row.short) ? "operator-row-short" : ""}
                      >
                        <td>
                          {row.name ?? row.sku ?? "—"} · {row.sku ?? ""} {row.unit ?? ""}
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
                <p className="production-trace-empty">{t("production.operatorNoStock")}</p>
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

          {step.code === "CUT" || step.code === "MACHINING" || stepOps.length ? (
            <div className="operator-section">
              <h4>{t("production.operatorSequence")}</h4>
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
                            <td>{op.x_mm ?? "—"}</td>
                            <td>
                              {op.angle_left_deg ?? "—"}° / {op.angle_right_deg ?? "—"}°
                            </td>
                            <td>
                              {op.detail?.boundary
                                ? String(op.detail.boundary)
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
                    <table className="production-plan operator-ops">
                      <thead>
                        <tr>
                          <th>{t("production.operatorOperation")}</th>
                          <th>{t("production.operatorHost")}</th>
                          <th>x/y (mm)</th>
                          <th>{t("production.operatorDepth")}</th>
                          <th>{t("production.operatorBasis")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {memberOps.map((op) => (
                          <tr key={op.operation_id}>
                            <td>{opKindLabel(op.kind)}</td>
                            <td title={op.host ?? ""}>
                              {(op.host && labels[op.host]) ??
                                String(op.detail?.role ?? op.host ?? "—")}
                            </td>
                            <td>
                              {op.x_mm ?? "—"} / {op.y_mm ?? "—"}
                            </td>
                            <td>{op.depth_mm ?? "—"}</td>
                            <td>{op.basis ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : null}
                </>
              ) : (
                <p className="production-trace-empty">{t("production.operatorNoOps")}</p>
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
                    {cutPieces.map((piece) => (
                      <tr key={piece.piece_id ?? `${piece.barIndex}-${piece.sequence}`}>
                        <td>
                          {piece.code ? <strong>{piece.code} · </strong> : null}
                          {piece.sequence ?? "—"}
                        </td>
                        <td>{piece.workshop_sku ?? "—"}</td>
                        <td>{piece.role ?? "—"}</td>
                        <td>
                          {piece.length_mm ?? "—"}
                          {piece.sagitta_mm ? ` · f ${fmtMm(piece.sagitta_mm)}` : ""}
                        </td>
                        <td>
                          {piece.angle_left ?? "—"}° / {piece.angle_right ?? "—"}°
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

          {step.code === "GLAZE" && sheetPieces.length ? (
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
                    <tr key={piece.piece_id ?? index}>
                      <td>
                        {piece.code ?? "—"}
                        {piece.workshop_sku ? ` · ${piece.workshop_sku}` : ""}
                      </td>
                      <td>{piece.role ?? "—"}</td>
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

          {step.code === "QC" ? (
            <QcCheckSection step={step} trace={trace} onQcCheck={onQcCheck} />
          ) : null}

          {!kinds.length ? (
            <p className="operator-summary">
              {t("production.operatorNoStock")} · {totalPieces}{" "}
              {t("production.operatorPiecesTotal")}
            </p>
          ) : null}
        </div>
      )}
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
