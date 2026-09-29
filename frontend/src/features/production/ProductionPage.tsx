import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  productionOrderCancel,
  productionOrderCncExport,
  productionOrderMaterialRecheck,
  productionOrderOpsExport,
  productionOrderDelivery,
  productionOrderDeliveryConfirm,
  productionOrderDeliveryConfirmation,
  productionOrderDeliverySchedule,
  productionOrderDeliveryTransition,
  productionOrderDetail,
  productionOrderDispatch,
  productionOrderDispatchNote,
  productionOrderDispatchNoteDte,
  productionOrderDispatchNoteDteEmit,
  productionOrderDispatchNoteVoid,
  productionOrderDispatchNoteDteEnvio,
  productionOrderDispatchNoteDteEnvioSend,
  productionOrderDxfExport,
  productionOrderInstall,
  productionOrderLabels,
  productionOrderOptimize,
  productionOrderOptimizeCompare,
  productionOrderPacking,
  productionOrderRemake,
  productionOrders,
  productionPieceTrace,
  productionOrderTrace,
  productionPrep,
  productionStationQueue,
  productionRelease,
  productionStepTransition,
} from "../../api/generated/dekopen";
import type {
  Delivery,
  DeliveryScheduleRequestRequest,
  DeliveryTransitionRequestStatusEnum,
  ProductionOrderTrace,
  ProductionPieceTrace,
  MethodEnum,
  PackingLabel,
  PaymentKindEnum,
  ProductionOrder,
  ProductionOrderDetail,
  ProductionPrepItem,
  ProductionStep,
  WorkOrderOptimizeCompare,
} from "../../api/generated/models";
import { ApiError, apiFetchBlob } from "../../api/apiMutator";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { formatDateTime } from "../../format";
import { DeniedState, PageHeader, usePrompt } from "../../ui";
import { fmtMm, fmtPct } from "../../format";
import { formatDate } from "../money";
import { t, tDynamic, tOptional } from "../../i18n/es-CL";
import { useAssistantSurface } from "../assistant/assistantContext";
import { PLAN_REQUIRED_CODES, STEP_STOCK_KINDS, cutRoleLabel, stationCodeLabel } from "./labels";

/** Narrow view over `production_station_queue` entries — the sidebar renders
 * the server's open dict shape (same pattern as the trace payload). */
type StationQueueGroup = {
  code?: string;
  pending?: number;
  in_progress?: number;
  blocked?: number;
  entries?: Array<{
    step_id?: string;
    order_id?: string;
    order_code?: string;
    label?: string;
    status?: string;
    is_next?: boolean;
  }>;
};
import { CutPlanView, type WorkOrderOptimization } from "./CutPlanView";
import { CncPanel } from "./CncPanel";
import { CncWorkspace } from "./CncWorkspace";
import {
  GlassSummary,
  glassSummaryCsv,
  type GlassPiece,
  type PolishingEntry,
} from "./GlassSummary";
import SignaturePad, { type SignaturePadHandle } from "./SignaturePad";
import { OperatorStepCard, type QcCheckInput } from "./OperatorCard";
import { TracePieceMatches, TracePlan, TraceStock } from "./TraceView";
import type { PieceMatch } from "./TraceView";
import "./production.css";

type WorkOrderMaterials = {
  profile_cuts?: unknown[];
  glasses?: unknown[];
  panels?: unknown[];
  hardware_items?: unknown[];
};

type StepAction = "START" | "COMPLETE" | "BLOCK" | "UNBLOCK" | "NOTE" | "QC_FAIL";

type CncExport = {
  exported_at?: string;
  files?: Record<string, string>;
};
type DxfExport = CncExport;
type OpsExport = CncExport & {
  operation_count?: number;
  counts_by_kind?: Record<string, number>;
};

type PackingUnit = {
  unit_index: number;
  label_code: string;
  profiles?: number;
  reinforcements?: number;
  glasses?: number;
  panels?: number;
  hardware?: number;
};
type WorkOrderPacking = {
  generated_at?: string;
  units?: PackingUnit[];
};

const stepStatusKey: Record<string, Parameters<typeof t>[0]> = {
  PENDING: "production.stepPending",
  READY: "production.stepReady",
  IN_PROGRESS: "production.stepInProgress",
  DONE: "production.stepDone",
  BLOCKED: "production.stepBlocked",
};
const orderStatusKey: Record<string, Parameters<typeof t>[0]> = {
  RELEASED: "production.orderReleased",
  IN_PROGRESS: "production.orderInProgress",
  HOLD: "production.orderHold",
  COMPLETED: "production.orderCompleted",
  DISPATCHED: "production.orderDispatched",
  INSTALLED: "production.orderInstalled",
  CANCELLED: "production.orderCancelled",
};

/** Orders that no longer accept floor actions — every action gate below
 * excludes them, and shortage/version noise stops applying to them. */
const TERMINAL_ORDER_STATUSES: ReadonlySet<string> = new Set([
  "COMPLETED",
  "DISPATCHED",
  "INSTALLED",
  "CANCELLED",
]);
const eventKey: Record<string, Parameters<typeof t>[0]> = {
  WO_RELEASED: "production.eventReleased",
  STEP_STARTED: "production.eventStepStarted",
  STEP_COMPLETED: "production.eventStepCompleted",
  STEP_BLOCKED: "production.eventStepBlocked",
  STEP_UNBLOCKED: "production.eventStepUnblocked",
  NOTE: "production.eventNote",
  WO_COMPLETED: "production.eventCompleted",
  WO_HOLD: "production.eventHold",
  WO_OPTIMIZED: "production.eventOptimized",
  QC_FAILED: "production.eventQcFailed",
  QC_CHECK: "production.eventQcCheck",
  WO_REMADE: "production.eventRemade",
  WO_CNC_EXPORTED: "production.eventCncExported",
  WO_DXF_EXPORTED: "production.eventDxfExported",
  WO_PACKED: "production.eventPacked",
  WO_DISPATCHED: "production.eventDispatched",
  WO_DISPATCH_VOIDED: "production.eventDispatchVoided",
  WO_INSTALLED: "production.eventInstalled",
  WO_DELIVERY_SCHEDULED: "production.eventDeliveryScheduled",
  WO_DELIVERY_ON_ROUTE: "production.eventDeliveryOnRoute",
  WO_DELIVERY_DELIVERED: "production.eventDeliveryDelivered",
  WO_DELIVERY_CONFIRMED: "production.eventDeliveryConfirmed",
  WO_DELIVERY_FAILED: "production.eventDeliveryFailed",
  WO_REMNANTS_SETTLED: "production.eventRemnantsSettled",
  WO_OPS_EXPORTED: "production.eventOpsExported",
  WO_CNC_PROGRAM: "production.eventCncProgram",
  WO_STOCK_CONSUMED: "production.eventStockConsumed",
  WO_CANCELLED: "production.eventCancelled",
  WO_MATERIAL_RECHECK: "production.eventMaterialRecheck",
};

const deliveryStatusKey: Record<string, Parameters<typeof t>[0]> = {
  SCHEDULED: "production.deliveryStatusScheduled",
  ON_ROUTE: "production.deliveryStatusOnRoute",
  DELIVERED: "production.deliveryStatusDelivered",
  FAILED: "production.deliveryStatusFailed",
};

/** Contract errors carry a human-readable detail — surface it so a refused
 * step (shortage, gate, invalid transition) tells the operator why instead
 * of collapsing into a generic toast. */
function actionErrorDetail(error: unknown): string {
  if (error instanceof ApiError) {
    const payload = error.payload as {
      error?: {
        code?: unknown;
        detail?: unknown;
        short_skus?: unknown;
        unmapped_stock_skus?: unknown;
        missing_operations?: unknown;
      };
    } | null;
    // The order's persistent blockers list already enumerates every missing
    // SKU — the toast stays one line instead of repeating the whole wall
    // (review: four stacked messages on a blocked Completar).
    if (payload?.error?.code === "work_order_material_shortage")
      return t("production.materialShortageToast");
    const detail = payload?.error?.detail;
    if (typeof detail === "string" && detail.trim()) {
      const shortList = payload?.error?.short_skus;
      const unmappedList = payload?.error?.unmapped_stock_skus;
      const missingOps = payload?.error?.missing_operations;
      const skus = [
        ...(Array.isArray(shortList) ? shortList : []),
        ...(Array.isArray(unmappedList) ? unmappedList : []),
        ...(Array.isArray(missingOps) ? missingOps : []),
      ].filter((sku): sku is string => typeof sku === "string" && sku.length > 0);
      return skus.length ? `${detail} · ${skus.join(", ")}` : detail;
    }
  }
  return t("production.actionError");
}

/** Same contract for non-throwing response paths (DTE emit / envío send):
 * a 4xx body carries {error:{detail}} — surface it instead of the generic
 * failure toast. */
function responseErrorDetail(data: unknown, fallback: string): string {
  const detail = (data as { error?: { detail?: unknown } } | null)?.error?.detail;
  return typeof detail === "string" && detail.trim() ? detail : fallback;
}

function stepActions(step: ProductionStep): StepAction[] {
  switch (step.status) {
    case "READY":
    case "PENDING":
      return ["START", "BLOCK", "NOTE"];
    case "IN_PROGRESS":
      return step.code === "QC"
        ? ["COMPLETE", "QC_FAIL", "BLOCK", "NOTE"]
        : ["COMPLETE", "BLOCK", "NOTE"];
    case "BLOCKED":
      return ["UNBLOCK", "NOTE"];
    case "DONE":
      return ["NOTE"];
    default:
      return ["NOTE"];
  }
}

/** Mirrors the backend START gate: a station that consumes stock OR works
 * the sealed plan (MACHINING/PROFILE_CUT/REINFORCEMENT_CUT) cannot begin
 * before the order carries a usable (non-invalidated) plan — otherwise the
 * operator walks into the start-first, optimize-later trap. */
function stepNeedsPlan(step: ProductionStep, detail: ProductionOrderDetail): boolean {
  if (!STEP_STOCK_KINDS[step.code]?.length && !PLAN_REQUIRED_CODES.has(step.code)) {
    return false;
  }
  const optimization = (detail.payload?.optimization ?? null) as {
    invalidated?: unknown;
  } | null;
  return !optimization || Boolean(optimization.invalidated);
}

const actionLabel: Record<StepAction, Parameters<typeof t>[0]> = {
  START: "production.actionStart",
  COMPLETE: "production.actionComplete",
  BLOCK: "production.actionBlock",
  UNBLOCK: "production.actionUnblock",
  NOTE: "production.actionNote",
  QC_FAIL: "production.actionQcFail",
};

export function ProductionPage(): JSX.Element {
  const auth = useAuthSession();
  const role = auth.me?.active_organization?.role ?? "";
  const [params, setParams] = useSearchParams();
  const [orders, setOrders] = useState<ProductionOrder[]>([]);
  const [detail, setDetail] = useState<ProductionOrderDetail | null>(null);
  const [prepVersions, setPrepVersions] = useState<ProductionPrepItem[]>([]);
  // While a work order is open, Ask DEKOPEN answers inside that order's
  // typed context — steps, status and shortages — not the generic list.
  useAssistantSurface(
    detail ? "work_order" : null,
    detail ? { work_order_id: detail.id } : undefined,
  );
  const prompt = usePrompt();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [note, setNote] = useState("");
  // Op-level execution evidence per step: which machining ops the operator
  // declared done — sent as ops_done on COMPLETE for evidence stations.
  const [opsDone, setOpsDone] = useState<Record<string, string[]>>({});
  const [optColor, setOptColor] = useState("");
  const [optStrategy, setOptStrategy] = useState("auto");
  const [labels, setLabels] = useState<PackingLabel[]>([]);
  const [stationQueue, setStationQueue] = useState<StationQueueGroup[]>([]);
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [pendingUnits, setPendingUnits] = useState<number[]>([]);
  const [dispatchUnitsSel, setDispatchUnitsSel] = useState<number[]>([]);
  const [deliveryForm, setDeliveryForm] = useState<DeliveryScheduleRequestRequest | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmName, setConfirmName] = useState("");
  const [confirmRut, setConfirmRut] = useState("");
  const [collectPayment, setCollectPayment] = useState(false);
  const [collectAmount, setCollectAmount] = useState("");
  const [collectMethod, setCollectMethod] = useState<MethodEnum>("CASH");
  const [collectKind, setCollectKind] = useState<PaymentKindEnum>("SALDO");
  const [sigDrawn, setSigDrawn] = useState(false);
  const [signatureMode, setSignatureMode] = useState<"draw" | "typed">("draw");
  const [trace, setTrace] = useState<ProductionOrderTrace | null>(null);
  const [strategyCompare, setStrategyCompare] = useState<WorkOrderOptimizeCompare | null>(null);
  const [compareBusy, setCompareBusy] = useState(false);
  const [traceBusy, setTraceBusy] = useState(false);
  const [operatorStepId, setOperatorStepId] = useState<string | null>(null);
  // Scan deep-link: the piece's station code is known before the order
  // detail loads — hold it until the step list resolves it to a step id.
  const [pendingStepCode, setPendingStepCode] = useState<string | null>(null);
  const [pieceQuery, setPieceQuery] = useState("");
  const [pieceReport, setPieceReport] = useState<ProductionPieceTrace | null>(null);
  const [pieceBusy, setPieceBusy] = useState(false);
  const [pieceMiss, setPieceMiss] = useState(false);
  const [qcFailItem, setQcFailItem] = useState("");
  const sigRef = useRef<SignaturePadHandle | null>(null);
  const labelsGeneration = useRef(0);
  const selectedIdRef = useRef("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const selectedParam = params.get("order") ?? "";
  // Deep links accept the id or the printed order code («OT-0007») — scan and
  // trace jumps hand the operator the code they see on the label (review).
  const resolvedOrder = orders.find(
    (order) =>
      order.id === selectedParam ||
      order.order_code.toUpperCase() === selectedParam.trim().toUpperCase(),
  );
  const selectedId = resolvedOrder?.id ?? selectedParam;
  selectedIdRef.current = selectedId;
  /** Triage queue — deep-linkable: /production?status=HOLD lands on the held
   * orders (dashboard attention items point here). */
  const statusFilter = params.get("status") ?? "";
  const shortageOnly = params.get("shortage") === "1";
  const dispatchReadyOnly = params.get("dispatch_ready") === "1";
  // A blocked step recomputes the order to HOLD — the only source of HOLD.
  const blockedOnly = params.get("blocked") === "1";
  const filteredOrders = orders.filter(
    (order) =>
      (statusFilter === "" || order.status === statusFilter) &&
      (!blockedOnly || order.status === "HOLD") &&
      // Order-level truth only: version_shortage counts the whole sealed
      // version's aggregate, so a fully-stocked order matched the filter
      // whenever a sibling order was short (review P1-1).
      (!shortageOnly || order.shortage > 0) &&
      (!dispatchReadyOnly || order.dispatch_ready),
  );
  const listFiltered = statusFilter !== "" || shortageOnly || dispatchReadyOnly || blockedOnly;
  // QC rejections bind to a physical unit — the piece labels the order's
  // trace already computed are the picker options (review PM-H2).
  const qcItemOptions = trace
    ? [...new Set(Object.values(trace.labels ?? {}).map(String))].sort()
    : [];

  // A workspace leads with the work — pin the top-priority order into the
  // detail pane instead of leaving it empty waiting for a click.
  useEffect(() => {
    if (selectedId || filteredOrders.length === 0) return;
    const next = new URLSearchParams(params);
    next.set("order", filteredOrders[0]!.id);
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, filteredOrders[0]?.id]);

  const loadOrders = useCallback(async () => {
    // Independent feeds: a 500 on the station queue (or prep) must not blank
    // the order list — each call settles on its own.
    const [response, prepResponse, queueResponse] = await Promise.all([
      productionOrders(),
      productionPrep().catch(() => null),
      productionStationQueue().catch(() => null),
    ]);
    if (prepResponse === null || queueResponse === null) {
      setMessage(t("production.loadError"));
    }
    if (response.status === 200) setOrders(response.data.orders);
    else setMessage(t("production.loadError"));
    // §8: versions approved for production but not yet released surface here
    // — the workshop sees the approved work without waiting for a reminder.
    if (prepResponse?.status === 200) setPrepVersions(prepResponse.data.versions);
    if (queueResponse?.status === 200) {
      setStationQueue(
        ((queueResponse.data.stations ?? []) as StationQueueGroup[]).filter(
          (group) => (group.entries ?? []).length > 0,
        ),
      );
    }
  }, []);

  const detailGeneration = useRef(0);

  const loadDetail = useCallback(async (orderId: string) => {
    const generation = ++detailGeneration.current;
    const [response, deliveryResponse] = await Promise.all([
      productionOrderDetail(orderId),
      productionOrderDelivery(orderId),
    ]);
    if (generation === detailGeneration.current) {
      if (response.status === 200) {
        setDetail(response.data);
        setLabels([]);
        const sealedColor = response.data.payload?.color;
        if (typeof sealedColor === "string" && sealedColor.trim()) {
          setOptColor(sealedColor);
        }
      }
      setDelivery(deliveryResponse.status === 200 ? deliveryResponse.data.delivery : null);
      setDeliveries(
        deliveryResponse.status === 200 ? (deliveryResponse.data.deliveries ?? []) : [],
      );
      setPendingUnits(
        deliveryResponse.status === 200 ? (deliveryResponse.data.pending_units ?? []) : [],
      );
      setDispatchUnitsSel([]);
      setDeliveryForm(null);
      setConfirmOpen(false);
    }
  }, []);

  const traceGeneration = useRef(0);
  const loadTrace = useCallback(
    async (orderId?: string) => {
      const id = orderId ?? selectedId;
      // Only the selected order's trace belongs in state — a mutating action
      // whose order is no longer selected refreshes nothing (and must not
      // cancel the selected order's in-flight request either).
      if (!id || id !== selectedIdRef.current) return;
      const generation = ++traceGeneration.current;
      setTraceBusy(true);
      try {
        const response = await productionOrderTrace(id);
        // A late response is discarded when the selection moved on or a
        // newer request started — the operator card must never render an
        // order it isn't about.
        if (generation !== traceGeneration.current) return;
        if (selectedIdRef.current !== id) return;
        // A non-200 response must behave like a failure — leaving the stale
        // trace up lets the operator act on pre-mutation stock/piece data.
        setTrace(response.status === 200 ? response.data : null);
      } catch {
        // On failure drop the stale data instead of leaving it displayed —
        // the reload control reappears and the card can't mislead the
        // operator with pre-mutation stock.
        if (generation === traceGeneration.current && selectedIdRef.current === id) {
          setTrace(null);
        }
      } finally {
        if (generation === traceGeneration.current) setTraceBusy(false);
      }
    },
    [selectedId],
  );

  useEffect(() => {
    void loadOrders().catch(() => setMessage(t("production.loadError")));
  }, [loadOrders]);

  useEffect(() => {
    labelsGeneration.current += 1;
    traceGeneration.current += 1;
    if (!selectedId) {
      detailGeneration.current += 1;
      setDetail(null);
      setDelivery(null);
      setDeliveries([]);
      setPendingUnits([]);
      setDispatchUnitsSel([]);
      setDeliveryForm(null);
      setConfirmOpen(false);
      return;
    }
    // An unresolved human code («OT-0007») waits for the orders list to map
    // it to the real id — firing now would 404 on the literal code. Once the
    // list has loaded, an unresolved param is bogus: let the fetch fail and
    // surface the honest error.
    if (!resolvedOrder && orders.length === 0 && !/^[0-9a-f-]{32,}$/i.test(selectedParam)) return;
    setTrace(null);
    setOperatorStepId(null);
    // Drop the previous order's detail immediately — leaving it rendered
    // during loadDetail's gap lets actions fire against the stale id.
    setDetail(null);
    setLabels([]);
    setDelivery(null);
    setDeliveries([]);
    setPendingUnits([]);
    setDispatchUnitsSel([]);
    setDeliveryForm(null);
    setConfirmOpen(false);
    setConfirmName("");
    setOptColor("");
    // A live ?piece= deep link owns the trace panel — re-runs caused by the
    // orders list resolving must not wipe its in-flight result.
    const deepPiece = params.get("piece");
    if (!deepPiece) {
      setPieceQuery("");
      setPieceReport(null);
    }
    // Keep pendingStepCode — it survives the async detail load so a scan
    // lands on the piece's station. It resolves once below.
    setStrategyCompare(null);
    void loadDetail(selectedId).catch(() => setMessage(t("production.loadError")));
    void loadTrace();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selectedParam, resolvedOrder, orders.length, loadDetail, loadTrace]);

  // Resolve a scan deep-link: piece → station code → step id on this order.
  useEffect(() => {
    if (!pendingStepCode || !detail) return;
    const match = detail.steps.find((step) => step.code === pendingStepCode);
    if (match) setOperatorStepId(match.id);
    setPendingStepCode(null);
  }, [pendingStepCode, detail]);

  // piece_id → printed workshop code (M-xx/R-xx/I-xx) from the trace's
  // sealed plan — the same codes the emitted packs carry, so screen and
  // paper name the same piece identically.
  const pieceCodes = useMemo(() => {
    const codes: Record<string, string> = {};
    const plan = trace?.plan as
      | {
          bars?: { cuts?: { piece_id?: string; code?: string }[] }[];
          sheets?: { pieces?: { piece_id?: string; code?: string }[] }[];
        }
      | undefined;
    for (const bar of plan?.bars ?? []) {
      for (const cut of bar.cuts ?? []) {
        if (cut.piece_id && cut.code) codes[cut.piece_id] = cut.code;
      }
    }
    for (const sheet of plan?.sheets ?? []) {
      for (const piece of sheet.pieces ?? []) {
        if (piece.piece_id && piece.code) codes[piece.piece_id] = piece.code;
      }
    }
    return codes;
  }, [trace]);

  const lookupPiece = useCallback(
    async (queryOverride?: string) => {
      const query = (queryOverride ?? pieceQuery).trim();
      if (!query) return;
      setPieceBusy(true);
      try {
        const response = await productionPieceTrace(query);
        if (response.status === 200) {
          setPieceReport(response.data);
          setPieceMiss(false);
        }
      } catch (error) {
        // A scan miss (404) is a result, not a crash — show the empty state;
        // anything else surfaces as an error the operator can act on.
        if (error instanceof ApiError && error.status === 404) {
          setPieceReport(null);
          setPieceMiss(true);
        } else if (mounted.current) {
          setMessage(t("production.loadError"));
        }
      } finally {
        setPieceBusy(false);
      }
    },
    [pieceQuery],
  );

  /** Order selection keeps the active filters — a ?blocked=1 / ?status=
   *  deep link must not dissolve the moment the operator clicks a row. */
  const openOrder = useCallback(
    (id: string) => {
      const next = new URLSearchParams(params);
      next.set("order", id);
      setParams(next);
    },
    [params, setParams],
  );

  // ?piece= deep link: a QR scan that arrives before login (or from outside
  // the app) fires the lookup once the screen is up — the operator never
  // retypes a code and never lands on a generic order. Fires once per value;
  // the param stays in the URL so a refresh re-runs the same scan.
  const lastDeepPiece = useRef<string | null>(null);
  useEffect(() => {
    const deep = params.get("piece");
    if (!deep || lastDeepPiece.current === deep) return;
    lastDeepPiece.current = deep;
    setPieceQuery(deep);
    void lookupPiece(deep);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // A scan that resolves to exactly one order lands on it — the piece's
  // station preselects the operator card. Ambiguous hits stay a list.
  useEffect(() => {
    if (!params.get("piece") || !pieceReport) return;
    const matches = (pieceReport.matches as PieceMatch[] | undefined) ?? [];
    const orderIds = [
      ...new Set(
        matches.map((match) => match.work_order?.id).filter((id): id is string => Boolean(id)),
      ),
    ];
    if (orderIds.length !== 1) return;
    const match = matches.find((entry) => entry.work_order?.id === orderIds[0]);
    const station = match?.operations?.find((op) => op.station)?.station;
    setPendingStepCode(station ?? null);
    const next = new URLSearchParams(params);
    next.delete("piece");
    next.set("order", orderIds[0]!);
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pieceReport]);

  async function action(task: Promise<unknown>, orderId: string): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await task;
      setNote("");
      // A mutating action (optimize, ops export, step transition) changes
      // the trace — refetch it so an open operator card never shows stale
      // reservations/ops until a manual reload.
      const reloads = [
        loadDetail(orderId).catch(() => undefined),
        loadOrders().catch(() => undefined),
      ];
      // A trace-read failure must not masquerade as a failed mutation —
      // the step transition or optimization already committed.
      if (trace) reloads.push(loadTrace(orderId).catch(() => undefined));
      const results = await Promise.allSettled(reloads);
      if (results.some((entry) => entry.status === "rejected") && mounted.current) {
        setMessage(t("production.loadError"));
      }
    } catch (error) {
      if (mounted.current) setMessage(actionErrorDetail(error));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function qcCheck(stepId: string, check: QcCheckInput, orderId: string): void {
    void action(productionStepTransition(stepId, { action: "QC_CHECK", qc_check: check }), orderId);
  }

  async function transition(
    stepId: string,
    stepAction: StepAction,
    orderId: string,
  ): Promise<void> {
    // BLOCK and QC_FAIL must carry a reason — the step can't be understood or
    // remediated without it. NOTE is the reason by definition. The shared note
    // field sits below the fold: ask inline instead of refusing silently.
    let noteValue = note;
    if (
      (stepAction === "NOTE" || stepAction === "BLOCK" || stepAction === "QC_FAIL") &&
      !noteValue.trim()
    ) {
      const entered = await prompt({
        title: t(
          stepAction === "QC_FAIL"
            ? "production.qcFailReasonTitle"
            : stepAction === "BLOCK"
              ? "production.blockReasonTitle"
              : "production.noteReasonTitle",
        ),
        input: { label: t("production.reasonLabel") },
      });
      if (entered === null) return;
      if (!entered.trim()) {
        setMessage(t("production.stepNoteRequired"));
        return;
      }
      noteValue = entered;
      setNote(entered);
    }
    const sent =
      stepAction === "NOTE" || stepAction === "BLOCK" || stepAction === "QC_FAIL"
        ? noteValue || undefined
        : undefined;
    const body =
      stepAction === "QC_FAIL"
        ? {
            action: "COMPLETE" as const,
            qc_result: "FAIL" as const,
            note: sent ?? null,
            qc_item: qcFailItem || undefined,
          }
        : stepAction === "COMPLETE" && opsDone[stepId]?.length
          ? { action: stepAction, note: sent ?? null, ops_done: opsDone[stepId] }
          : { action: stepAction, note: sent ?? null };
    await action(productionStepTransition(stepId, body), orderId);
  }

  function release(versionId: string): void {
    setBusy(true);
    setMessage("");
    productionRelease(versionId)
      .then(async (response) => {
        if ((response.status === 200 || response.status === 201) && mounted.current) {
          await loadOrders();
          const first = response.data.orders[0];
          if (first) openOrder(first.id);
        }
      })
      .catch((error) => {
        if (mounted.current) setMessage(actionErrorDetail(error));
      })
      .finally(() => {
        if (mounted.current) setBusy(false);
      });
  }

  function remake(orderId: string): void {
    setBusy(true);
    setMessage("");
    productionOrderRemake(orderId, { note: note || undefined })
      .then(async (response) => {
        if (response.status === 201 && mounted.current) {
          setNote("");
          openOrder(response.data.id);
          await loadOrders();
        }
      })
      .catch((error) => {
        if (mounted.current) setMessage(actionErrorDetail(error));
      })
      .finally(() => {
        if (mounted.current) setBusy(false);
      });
  }

  /** Order cancel is destructive-but-reversible work — a danger dialog with an
   * optional note, then the backend releases every outstanding reservation
   * atomically and freezes the routing steps as-is. */
  async function cancelOrder(orderId: string): Promise<void> {
    const entered = await prompt({
      title: t("production.cancelTitle"),
      body: t("production.cancelBody"),
      input: { label: t("production.cancelNoteLabel") },
      confirmLabel: t("production.cancelConfirm"),
      danger: true,
    });
    if (entered === null) return;
    void action(
      productionOrderCancel(orderId, { confirmed: true, note: entered || undefined }),
      orderId,
    );
  }

  function recheckMaterials(orderId: string): void {
    void action(productionOrderMaterialRecheck(orderId), orderId);
  }

  function optimize(orderId: string): void {
    if (!optColor.trim()) return;
    // A committed plan supersedes any comparison that ran against the prior
    // stock/piece state — stale numbers must not survive next to a new plan.
    setStrategyCompare(null);
    void action(
      productionOrderOptimize(orderId, {
        color: optColor.trim(),
        strategy: optStrategy as "fast" | "deep" | "auto",
      }),
      orderId,
    );
  }

  function compareStrategies(orderId: string): void {
    setCompareBusy(true);
    setMessage("");
    productionOrderOptimizeCompare(orderId, { color: optColor.trim() })
      .then((response) => {
        if (mounted.current && response.status === 200) {
          setStrategyCompare(response.data);
        }
      })
      .catch((error) => {
        if (mounted.current) setMessage(actionErrorDetail(error));
      })
      .finally(() => {
        if (mounted.current) setCompareBusy(false);
      });
  }

  // Exports generate the machine file AND hand it to the operator in one
  // click — a generate-then-click-the-chip flow reads as a dead button
  // (review PM-M2).
  async function exportAndDownload(
    orderId: string,
    orderCode: string,
    task: Promise<{ status: number; data: unknown }>,
  ): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const response = await task;
      if (response.status !== 200 && response.status !== 201)
        throw new ApiError(response.status, response.data);
      const files = (response.data as { files?: Record<string, string> } | undefined)?.files ?? {};
      for (const [filename, content] of Object.entries(files)) {
        downloadCnc(orderCode, filename, content);
      }
      const reloads = [
        loadDetail(orderId).catch(() => undefined),
        loadOrders().catch(() => undefined),
      ];
      if (trace) reloads.push(loadTrace(orderId).catch(() => undefined));
      const results = await Promise.allSettled(reloads);
      if (results.some((entry) => entry.status === "rejected") && mounted.current) {
        setMessage(t("production.loadError"));
      }
    } catch (error) {
      if (mounted.current) setMessage(actionErrorDetail(error));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function exportCnc(orderId: string, orderCode: string): void {
    void exportAndDownload(orderId, orderCode, productionOrderCncExport(orderId));
  }

  function exportDxf(orderId: string, orderCode: string): void {
    void exportAndDownload(orderId, orderCode, productionOrderDxfExport(orderId));
  }

  function exportOperations(orderId: string, orderCode: string): void {
    void exportAndDownload(orderId, orderCode, productionOrderOpsExport(orderId));
  }

  async function showLabels(orderId: string): Promise<void> {
    const generation = ++labelsGeneration.current;
    setLabels([]);
    setBusy(true);
    try {
      const response = await productionOrderLabels(orderId);
      // A selection change bumps the generation, but a response can still
      // land in the gap before the effect runs — check the order too.
      if (generation !== labelsGeneration.current) return;
      if (selectedIdRef.current !== orderId) return;
      if (response.status !== 200) {
        setMessage(t("production.labelsError"));
        return;
      }
      setLabels(response.data.labels);
    } catch {
      if (generation === labelsGeneration.current && selectedIdRef.current === orderId) {
        setMessage(t("production.labelsError"));
      }
    } finally {
      setBusy(false);
    }
  }

  async function saveDelivery(orderId: string): Promise<void> {
    if (!deliveryForm) return;
    setBusy(true);
    try {
      const response = await productionOrderDeliverySchedule(orderId, deliveryForm);
      if (response.status === 200) {
        await loadDetail(orderId);
      } else {
        setMessage(t("production.deliveryError"));
      }
    } catch {
      setMessage(t("production.deliveryError"));
    } finally {
      setBusy(false);
    }
  }

  async function transitionDelivery(
    orderId: string,
    status: DeliveryTransitionRequestStatusEnum,
  ): Promise<void> {
    setBusy(true);
    try {
      const response = await productionOrderDeliveryTransition(orderId, { status });
      if (response.status === 200) {
        await loadDetail(orderId);
      } else {
        setMessage(t("production.deliveryError"));
      }
    } catch {
      setMessage(t("production.deliveryError"));
    } finally {
      setBusy(false);
    }
  }

  function openDeliveryForm(existing: Delivery | null): void {
    // A fresh schedule defaults to tomorrow — dispatch work is booked ahead,
    // and an empty date field makes the operator type the obvious (PM-M3).
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const defaultDate = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;
    setDeliveryForm({
      scheduled_date: existing?.scheduled_date ?? defaultDate,
      time_window: (existing?.time_window as DeliveryScheduleRequestRequest["time_window"]) ?? "AM",
      address: existing?.address ?? detail?.delivery_address ?? "",
      contact_name: existing?.contact_name ?? "",
      contact_phone: existing?.contact_phone ?? "",
      installer_name: existing?.installer_name ?? "",
      notes: existing?.notes ?? "",
      // null = the whole pending balance; an explicit list = a partial trip
      unit_indexes: existing?.unit_indexes ?? null,
    });
  }

  function pack(orderId: string): void {
    void action(productionOrderPacking(orderId), orderId);
  }

  // Packing unit codes (U01…) — the same labels the printed bulto labels carry.
  function unitLabel(list?: number[] | null): string {
    if (!list?.length) return t("production.deliveryUnitsAll");
    const units = (detail?.payload?.packing as WorkOrderPacking | undefined)?.units ?? [];
    return list
      .map(
        (i) =>
          units.find((u) => u.unit_index === i)?.label_code ?? `U${String(i).padStart(2, "0")}`,
      )
      .join(" · ");
  }

  function dispatch(orderId: string): void {
    // Despachar emite la guía legal: without a scheduled delivery the truck
    // has no destination, so route the operator to the delivery form first —
    // a hand-off note (retiro en taller) also satisfies the gate.
    if (!delivery && !note.trim()) {
      setMessage(t("production.dispatchNeedsDelivery"));
      openDeliveryForm(null);
      return;
    }
    void action(
      productionOrderDispatch(orderId, {
        note: note || undefined,
        unit_indexes: dispatchUnitsSel.length ? dispatchUnitsSel : null,
      }),
      orderId,
    );
  }

  async function voidNote(orderId: string): Promise<void> {
    const reason = await prompt({
      title: t("production.voidNoteTitle"),
      body: t("production.voidNoteBody"),
      input: { label: t("production.voidNoteReasonLabel") },
      confirmLabel: t("production.voidNoteConfirm"),
      danger: true,
    });
    if (reason === null) return;
    if (!reason) {
      setMessage(t("production.voidNoteReasonRequired"));
      return;
    }
    void action(productionOrderDispatchNoteVoid(orderId, { reason }), orderId);
  }

  function install(orderId: string): void {
    void action(productionOrderInstall(orderId, { note: note || undefined }), orderId);
  }

  function openConfirmForm(): void {
    setConfirmName(delivery?.contact_name ?? "");
    setConfirmRut("");
    setCollectPayment(false);
    setCollectAmount("");
    setCollectMethod("CASH");
    setCollectKind("SALDO");
    setSigDrawn(false);
    setConfirmOpen(true);
  }

  // Typed-mode signatures render live — typing a name with no visible ink
  // reads as a dead field (review PM-M4).
  useEffect(() => {
    if (!confirmOpen || signatureMode !== "typed") return;
    const name = confirmName.trim();
    if (name) {
      sigRef.current?.renderTyped(name);
    } else {
      sigRef.current?.clear();
    }
  }, [confirmOpen, signatureMode, confirmName]);

  async function submitConfirmation(orderId: string): Promise<void> {
    if (!confirmName.trim()) return;
    if (signatureMode === "typed") {
      sigRef.current?.renderTyped(confirmName.trim());
    }
    const dataUrl = sigRef.current?.dataURL();
    if (!dataUrl) {
      setMessage(t("production.deliverySignatureRequired"));
      return;
    }
    setBusy(true);
    try {
      const response = await productionOrderDeliveryConfirm(orderId, {
        receiver_name: confirmName.trim(),
        receiver_rut: confirmRut.trim() || undefined,
        signature_png: dataUrl.split(",")[1] ?? "",
        payment: collectPayment
          ? {
              amount: collectAmount,
              method: collectMethod,
              kind: collectKind,
            }
          : null,
      });
      if (response.status === 201 || response.status === 200) {
        await loadDetail(orderId);
      } else {
        setMessage(t("production.deliveryConfirmError"));
      }
    } catch {
      setMessage(t("production.deliveryConfirmError"));
    } finally {
      setBusy(false);
    }
  }

  async function openConfirmation(orderId: string, deliveryId?: string): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("production.dispatchNoteError"));
      return;
    }
    try {
      const response = await productionOrderDeliveryConfirmation(
        orderId,
        deliveryId ? { delivery: deliveryId } : undefined,
      );
      if (response.status !== 200) throw new Error("confirmation_error");
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      setMessage(t("production.dispatchNoteError"));
    }
  }

  async function emitDispatchNoteDte(orderId: string): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const response = await productionOrderDispatchNoteDteEmit(orderId, {
        ind_traslado: 1,
      });
      if (response.status === 201) {
        await loadDetail(orderId);
      } else {
        setMessage(responseErrorDetail(response.data, t("production.dteEmitError")));
      }
    } catch {
      setMessage(t("production.dteEmitError"));
    } finally {
      setBusy(false);
    }
  }

  async function openDispatchNoteDte(orderId: string): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("production.dteOpenError"));
      return;
    }
    try {
      const response = await productionOrderDispatchNoteDte(orderId);
      if (response.status !== 200) throw new Error("dte_error");
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      setMessage(t("production.dteOpenError"));
    }
  }

  async function sendDispatchEnvio(orderId: string, resubmit = false): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const response = await productionOrderDispatchNoteDteEnvioSend(orderId, {
        resubmit,
      });
      if (response.status === 201) {
        await loadDetail(orderId);
      } else {
        setMessage(responseErrorDetail(response.data, t("production.envioSendError")));
      }
    } catch {
      setMessage(t("production.envioSendError"));
    } finally {
      setBusy(false);
    }
  }

  async function openDispatchEnvio(orderId: string): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("production.envioOpenError"));
      return;
    }
    try {
      const response = await productionOrderDispatchNoteDteEnvio(orderId);
      if (response.status !== 200) throw new Error("envio_error");
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      setMessage(t("production.envioOpenError"));
    }
  }

  async function openDispatchNote(orderId: string, noteId?: string): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("production.dispatchNoteError"));
      return;
    }
    try {
      const response = await productionOrderDispatchNote(
        orderId,
        noteId ? { note: noteId } : undefined,
      );
      if (response.status !== 200) throw new Error("dispatch_note_error");
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      setMessage(t("production.dispatchNoteError"));
    }
  }

  function downloadCnc(orderCode: string, filename: string, content: string): void {
    const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${orderCode}-${filename}`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function downloadCutPack(orderId: string, orderCode: string): Promise<void> {
    try {
      const { blob, filename } = await apiFetchBlob(
        `/api/v1/production/orders/${orderId}/cut-pack/`,
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? `${orderCode}-pack-corte.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setMessage(t("production.cutPackError"));
    }
  }

  async function downloadProductionPack(orderId: string, orderCode: string): Promise<void> {
    try {
      const { blob, filename } = await apiFetchBlob(
        `/api/v1/production/orders/${orderId}/production-pack/`,
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? `${orderCode}-pack-produccion.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setMessage(t("production.productionPackError"));
    }
  }

  // INSTALLER is a field role — it confirms deliveries and installations,
  // never station steps or work-order transitions (server enforces).
  // ESTIMATOR gets a read-only view — the attention queue deep-links them
  // here to see blockers and shortages; the backend readers include them.
  const canAct =
    role === "OWNER" ||
    role === "WORKSHOP_MANAGER" ||
    role === "INSTALLER" ||
    role === "OPERATOR" ||
    role === "ESTIMATOR";
  const canWrite = role === "OWNER" || role === "WORKSHOP_MANAGER";
  // Station work: _WORKSHOP_STEP_ACTORS (office + saw floor).
  const canStep = canWrite || role === "OPERATOR";
  // Field work: _STEP_ACTORS (office + installer) — route/failed/delivery
  // confirmations and the install act. Never drives station steps.
  const canField = canWrite || role === "INSTALLER";
  if (!canAct) {
    return (
      <section className="production-page">
        <PageHeader title={t("production.title")} />
        <DeniedState reason={t("production.denied")} />
      </section>
    );
  }

  return (
    <section className="production-page">
      <PageHeader context={t("production.subtitle")} title={t("production.title")} />
      {message ? (
        <p className="production-action-error" role="alert">
          {message}
        </p>
      ) : null}
      <div className="production-layout">
        <aside className="production-orders" aria-label={t("production.orders")}>
          <h2>{t("production.orders")}</h2>
          {/* Piece in hand → find its order without opening one first
              (PM-M6). Top of the sidebar: scanning a stick is the most
              frequent floor gesture, above filters and boards. */}
          <form
            className="production-trace-lookup"
            onSubmit={(event) => {
              event.preventDefault();
              void lookupPiece();
            }}
          >
            <label>
              {t("production.tracePieceLabel")}
              <input
                type="text"
                value={pieceQuery}
                onChange={(event) => setPieceQuery(event.target.value)}
                placeholder={t("production.tracePiecePlaceholder")}
                autoFocus
              />
            </label>
            <button type="submit" disabled={pieceBusy || !pieceQuery.trim()}>
              {t("production.tracePieceLookup")}
            </button>
          </form>
          {pieceReport ? (
            <TracePieceMatches
              report={pieceReport}
              onSelectOrder={(id, stepCode) => {
                setPendingStepCode(stepCode ?? null);
                openOrder(id);
              }}
            />
          ) : pieceMiss ? (
            <p className="production-trace-empty">{t("production.tracePieceNone")}</p>
          ) : null}
          {/* Station board first for the floor: the operator's authorized
              queue — "qué está esperando en mi puesto" — leads the sidebar
              before release/admin noise. Managers keep the release panel
              on top; installers never see the station board at all. */}
          {role === "OPERATOR" ? (
            <>
              {stationQueue.length ? (
                <section className="production-station-queue">
                  <h3>{t("production.stationQueue")}</h3>
                  <ul>
                    {stationQueue.map((group) => (
                      <li key={group.code}>
                        <strong>{stationCodeLabel(group.code)}</strong>
                        <span className="production-station-counts">
                          {t("production.stationQueueCounts")
                            .replace("{ready}", String(group.pending ?? 0))
                            .replace("{active}", String(group.in_progress ?? 0))
                            .replace("{blocked}", String(group.blocked ?? 0))}
                        </span>
                        <ul>
                          {(group.entries ?? []).map((entry) => (
                            <li key={entry.step_id}>
                              <button
                                type="button"
                                className="production-order"
                                onClick={() => entry.order_id && openOrder(entry.order_id)}
                              >
                                <span className="production-order-code">
                                  {entry.order_code ?? "—"}
                                </span>
                                <span className="production-order-line">
                                  {entry.label ?? stationCodeLabel(group.code)}
                                  {entry.is_next ? ` · ${t("production.stationQueueNext")}` : ""}
                                </span>
                                <span
                                  className={`production-order-status step-${String(
                                    entry.status ?? "",
                                  ).toLowerCase()}`}
                                >
                                  {t(
                                    entry.status === "READY" && !entry.is_next
                                      ? "production.stepPending"
                                      : (stepStatusKey[entry.status ?? ""] ??
                                          "production.stepPending"),
                                  )}
                                </span>
                              </button>
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : orders.some((order) => !TERMINAL_ORDER_STATUSES.has(order.status)) ? (
                <p className="production-station-empty">
                  {t("production.stationQueueEmpty")}{" "}
                  <button type="button" onClick={() => void loadOrders()}>
                    {t("production.reload")}
                  </button>
                </p>
              ) : null}
            </>
          ) : null}
          {role !== "OPERATOR" && role !== "INSTALLER" && prepVersions.length > 0 ? (
            <section className="production-prep" aria-label={t("production.prepTitle")}>
              <h3>{t("production.prepTitle")}</h3>
              <ul>
                {prepVersions.map((version) => (
                  <li key={version.version_id}>
                    <span>
                      {version.project_code} · {version.revision_code} · {version.positions}{" "}
                      {t("production.prepPositions")}
                    </span>
                    {/* Non-writers get the same action disabled with a reason —
                        an invisible gate hides work they should be able to request. */}
                    <button
                      type="button"
                      className="production-prep-release"
                      disabled={busy || !canWrite}
                      title={canWrite ? undefined : t("production.writeHint")}
                      onClick={() => release(version.version_id)}
                    >
                      {t("production.prepRelease")}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          <div
            className="production-filters"
            role="group"
            aria-label={t("production.statusFilter")}
          >
            {[
              "",
              "RELEASED",
              "IN_PROGRESS",
              "HOLD",
              "COMPLETED",
              "DISPATCHED",
              "INSTALLED",
              "CANCELLED",
            ].map((status) => (
              <button
                key={status || "all"}
                type="button"
                className={`production-filter${statusFilter === status ? " is-active" : ""}`}
                aria-pressed={statusFilter === status}
                onClick={() => {
                  const next = new URLSearchParams(params);
                  if (status) next.set("status", status);
                  else next.delete("status");
                  setParams(next);
                }}
              >
                {status === ""
                  ? t("production.statusAll")
                  : t(orderStatusKey[status] ?? "production.orderReleased")}
              </button>
            ))}
            <button
              type="button"
              className={`production-filter${shortageOnly ? " is-active" : ""}`}
              aria-pressed={shortageOnly}
              onClick={() => {
                const next = new URLSearchParams(params);
                if (shortageOnly) next.delete("shortage");
                else next.set("shortage", "1");
                setParams(next);
              }}
            >
              {t("production.filterShortage")}
            </button>
            <button
              type="button"
              className={`production-filter${dispatchReadyOnly ? " is-active" : ""}`}
              aria-pressed={dispatchReadyOnly}
              onClick={() => {
                const next = new URLSearchParams(params);
                if (dispatchReadyOnly) next.delete("dispatch_ready");
                else next.set("dispatch_ready", "1");
                setParams(next);
              }}
            >
              {t("production.filterDispatchReady")}
            </button>
            {listFiltered ? (
              <button
                type="button"
                className="production-filter production-filter-clear"
                onClick={() => {
                  const next = new URLSearchParams(params);
                  next.delete("status");
                  next.delete("shortage");
                  next.delete("dispatch_ready");
                  setParams(next);
                }}
              >
                {t("production.clearFilters")}
              </button>
            ) : null}
          </div>
          {/* Station board for oversight roles — the operator already got
              it at the top; installers work deliveries, not stations. */}
          {role !== "OPERATOR" && role !== "INSTALLER" && stationQueue.length ? (
            <section className="production-station-queue">
              <h3>{t("production.stationQueue")}</h3>
              <ul>
                {stationQueue.map((group) => (
                  <li key={group.code}>
                    <strong>{stationCodeLabel(group.code)}</strong>
                    <span className="production-station-counts">
                      {t("production.stationQueueCounts")
                        .replace("{ready}", String(group.pending ?? 0))
                        .replace("{active}", String(group.in_progress ?? 0))
                        .replace("{blocked}", String(group.blocked ?? 0))}
                    </span>
                    <ul>
                      {(group.entries ?? []).map((entry) => (
                        <li key={entry.step_id}>
                          <button
                            type="button"
                            className="production-order"
                            onClick={() => entry.order_id && openOrder(entry.order_id)}
                          >
                            <span className="production-order-code">{entry.order_code ?? "—"}</span>
                            <span className="production-order-line">
                              {entry.label ?? stationCodeLabel(group.code)}
                              {entry.is_next ? ` · ${t("production.stationQueueNext")}` : ""}
                            </span>
                            <span
                              className={`production-order-status step-${String(
                                entry.status ?? "",
                              ).toLowerCase()}`}
                            >
                              {t(
                                entry.status === "READY" && !entry.is_next
                                  ? "production.stepPending"
                                  : (stepStatusKey[entry.status ?? ""] ?? "production.stepPending"),
                              )}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {orders.length === 0 ? <p>{t("production.empty")}</p> : null}
          {listFiltered && orders.length > 0 && filteredOrders.length === 0 ? (
            <p>{t("production.emptyFilter")}</p>
          ) : null}
          <ul>
            {filteredOrders.map((order) => (
              <li key={order.id}>
                <button
                  type="button"
                  className={
                    order.id === selectedId ? "production-order active" : "production-order"
                  }
                  onClick={() => openOrder(order.id)}
                >
                  <span className="production-order-code">{order.order_code}</span>
                  <span className={`production-chip status-${order.status.toLowerCase()}`}>
                    {t(orderStatusKey[order.status] ?? "production.orderReleased")}
                  </span>
                  <span className="production-order-progress">
                    {order.steps_done}/{order.steps_total} {t("production.stepsShort")}
                  </span>
                  {order.next_step ? (
                    <span className="production-order-next">
                      {t("production.nextStep") + " · " + order.next_step.label}
                    </span>
                  ) : null}
                  {order.shortage > 0 ? (
                    <span className="production-chip is-warn">
                      {t("production.shortageChip").replace("{count}", String(order.shortage))}
                    </span>
                  ) : null}
                  {order.version_shortage > order.shortage &&
                  !TERMINAL_ORDER_STATUSES.has(order.status) ? (
                    <span
                      className="production-chip is-warn"
                      title={t("production.versionShortageTitle")}
                    >
                      {t("production.versionShortageChip").replace(
                        "{count}",
                        String(order.version_shortage - order.shortage),
                      )}
                    </span>
                  ) : null}
                  {order.dispatch_ready ? (
                    <span className="production-chip is-ready">
                      {t("production.dispatchReadyChip")}
                    </span>
                  ) : null}
                  {(() => {
                    const reason = order.remake_reason;
                    if (!reason) return null;
                    const why = [reason.qc_item, reason.note]
                      .filter((part): part is string => Boolean(part))
                      .join(" · ");
                    return (
                      <span className="production-chip is-warn" title={why || undefined}>
                        {t("production.remakeOf")}
                        {why ? `: ${why}` : ""}
                      </span>
                    );
                  })()}
                </button>
              </li>
            ))}
          </ul>
          {/* CNC is a workshop surface — installers never program machines. */}
          {role !== "INSTALLER" ? <CncWorkspace /> : null}
        </aside>
        <article className="production-detail">
          {detail ? (
            <>
              <header className="production-detail-head">
                <h2>{detail.order_code}</h2>
                <span className={`production-chip status-${detail.status.toLowerCase()}`}>
                  {t(orderStatusKey[detail.status] ?? "production.orderReleased")}
                </span>
                {detail.quantity ? (
                  <span className="production-order-progress">
                    {detail.quantity}{" "}
                    {t(detail.quantity === 1 ? "production.unitsOne" : "production.units")}
                  </span>
                ) : null}
                {detail.shortage > 0 ? (
                  <span className="production-chip is-warn">
                    {t("production.shortageChip").replace("{count}", String(detail.shortage))}
                  </span>
                ) : null}
                {detail.version_shortage > detail.shortage &&
                !TERMINAL_ORDER_STATUSES.has(detail.status) ? (
                  <button
                    type="button"
                    className="production-chip is-warn"
                    title={t("production.versionShortageTitle")}
                    onClick={() => {
                      const next = new URLSearchParams(params);
                      next.set("shortage", "1");
                      setParams(next);
                    }}
                  >
                    {t("production.versionShortageChip").replace(
                      "{count}",
                      String(detail.version_shortage - detail.shortage),
                    )}
                  </button>
                ) : null}
                {detail.dispatch_ready ? (
                  <span className="production-chip is-ready">
                    {t("production.dispatchReadyChip")}
                  </span>
                ) : null}
                {canWrite && detail.dispatch_ready ? (
                  <button
                    type="button"
                    className="production-dispatch"
                    disabled={busy}
                    onClick={() => dispatch(detail.id)}
                  >
                    {t("production.dispatchButton")}
                  </button>
                ) : null}
                {canField &&
                detail.status === "DISPATCHED" &&
                (!delivery || delivery.status === "DELIVERED") ? (
                  <button
                    type="button"
                    className="production-dispatch production-install"
                    disabled={busy}
                    onClick={() => install(detail.id)}
                  >
                    {t("production.installButton")}
                  </button>
                ) : null}
                {(detail.dispatch_notes?.length
                  ? detail.dispatch_notes
                  : detail.dispatch_note_code
                    ? [
                        {
                          note_code: detail.dispatch_note_code,
                          voided: detail.dispatch_note_voided,
                        },
                      ]
                    : []
                ).map((entry) => {
                  const code = String(entry.note_code ?? "");
                  const voided = entry.voided === true;
                  const noteId = typeof entry.id === "string" ? entry.id : undefined;
                  const units = Array.isArray(entry.unit_indexes)
                    ? (entry.unit_indexes as number[])
                    : null;
                  return (
                    <button
                      key={noteId ?? code}
                      type="button"
                      className={`production-dispatch production-note${voided ? " is-voided" : ""}`}
                      title={voided ? t("production.dispatchNoteVoided") : undefined}
                      onClick={() => void openDispatchNote(detail.id, noteId)}
                    >
                      {code}
                      {units ? ` · ${unitLabel(units)}` : ""}
                      {voided ? ` · ${t("production.dispatchNoteVoided")}` : ""}
                    </button>
                  );
                })}
                {canWrite &&
                detail.status === "DISPATCHED" &&
                !detail.dispatch_note_dte &&
                detail.dispatch_note_code &&
                !detail.dispatch_note_voided ? (
                  <button
                    type="button"
                    className="production-dispatch production-void"
                    disabled={busy}
                    onClick={() => void voidNote(detail.id)}
                  >
                    {t("production.voidNoteButton")}
                  </button>
                ) : null}
                {detail.dispatch_note_dte ? (
                  <button
                    type="button"
                    className="production-dispatch production-note-dte"
                    title={`${t("production.dteStatus")} · folio ${detail.dispatch_note_dte.folio}`}
                    onClick={() => void openDispatchNoteDte(detail.id)}
                  >
                    {`${t("production.dteStatus")} · ${detail.dispatch_note_dte.folio}`}
                  </button>
                ) : canWrite && detail.dispatch_note_code ? (
                  <button
                    type="button"
                    className="production-dispatch"
                    disabled={busy}
                    onClick={() => void emitDispatchNoteDte(detail.id)}
                  >
                    {t("production.dteEmit")}
                  </button>
                ) : null}
                {(() => {
                  const envio = detail.dispatch_note_dte?.envio as
                    | { status?: string; track_id?: string | null; attempted?: boolean }
                    | null
                    | undefined;
                  if (!detail.dispatch_note_dte) return null;
                  const resubmit = envio?.attempted === true && !envio?.track_id;
                  return (
                    <>
                      {envio?.status ? (
                        <button
                          type="button"
                          className="production-dispatch production-note-envio"
                          title={`${t("production.envioStatus")} · ${envio.track_id ?? ""}`}
                          onClick={() => void openDispatchEnvio(detail.id)}
                        >
                          {`${t("production.envioStatus")} · ${envio.status}`}
                        </button>
                      ) : canWrite ? (
                        <button
                          type="button"
                          className="production-dispatch"
                          disabled={busy}
                          onClick={() => void sendDispatchEnvio(detail.id)}
                        >
                          {t("production.envioSend")}
                        </button>
                      ) : null}
                      {canWrite && envio?.status === "PENDING" ? (
                        <button
                          type="button"
                          className="production-dispatch"
                          disabled={busy}
                          onClick={() => void sendDispatchEnvio(detail.id, resubmit)}
                        >
                          {resubmit ? t("production.envioResend") : t("production.envioRefresh")}
                        </button>
                      ) : null}
                    </>
                  );
                })()}
                {canWrite && detail.status === "HOLD" ? (
                  <button
                    type="button"
                    className="production-remake"
                    disabled={busy}
                    onClick={() => remake(detail.id)}
                  >
                    {t("production.remakeButton")}
                  </button>
                ) : null}
                {/* Stock arrived after release → top up open reservations
                    instead of forcing a re-optimize (review P0-3). */}
                {canWrite && detail.shortage > 0 && !TERMINAL_ORDER_STATUSES.has(detail.status) ? (
                  <button
                    type="button"
                    className="production-remake"
                    disabled={busy}
                    onClick={() => recheckMaterials(detail.id)}
                  >
                    {t("production.materialRecheck")}
                  </button>
                ) : null}
                {/* A cancelled order releases its reservations and freezes
                    where it stands — terminal for every floor gate. */}
                {canWrite && !TERMINAL_ORDER_STATUSES.has(detail.status) ? (
                  <button
                    type="button"
                    className="production-remake production-cancel"
                    disabled={busy}
                    onClick={() => void cancelOrder(detail.id)}
                  >
                    {t("production.cancelButton")}
                  </button>
                ) : null}
              </header>
              {(() => {
                // §10: the operator's first answer — what physical product
                // this order is, from the sealed revision (never CRM text).
                const making = detail.making;
                if (!making) return null;
                const typology = making.typology
                  ? tDynamic(
                      "typology",
                      making.typology
                        .toLowerCase()
                        .replace(/_([a-z])/g, (_, c: string) => c.toUpperCase()),
                    )
                  : null;
                const colors = [
                  making.color_interior,
                  making.color_exterior && making.color_exterior !== making.color_interior
                    ? making.color_exterior
                    : null,
                ]
                  .filter(Boolean)
                  .join(" / ");
                const dims =
                  making.width_mm && making.height_mm
                    ? `${fmtMm(making.width_mm)} × ${fmtMm(making.height_mm)} mm`
                    : null;
                return (
                  <p className="production-making" aria-label={t("production.makingTitle")}>
                    <strong>{making.code ?? `P-${making.position_index ?? "?"}`}</strong>
                    {typology ? <span>{typology}</span> : null}
                    {dims ? <span>{dims}</span> : null}
                    {colors ? <span>{colors}</span> : null}
                    {making.quantity && making.quantity > 1 ? (
                      <span>×{making.quantity}</span>
                    ) : null}
                    {making.location_tag ? (
                      <span className="production-making-location">{making.location_tag}</span>
                    ) : null}
                  </p>
                );
              })()}
              {(() => {
                // Remake provenance, both directions: the remake names the
                // order it replaces; the replaced order names its remakes.
                const remakeOf = detail.payload?.remake_of;
                const source = remakeOf
                  ? orders.find((order) => order.id === String(remakeOf))
                  : undefined;
                const remakes = orders.filter(
                  (order) => String(order.payload?.remake_of ?? "") === detail.id,
                );
                if (!source && !remakes.length) return null;
                const remakeReason = (detail.payload?.remake_reason ?? null) as {
                  qc_item?: unknown;
                  note?: unknown;
                } | null;
                const reasonBits = [
                  remakeReason?.qc_item ? String(remakeReason.qc_item) : "",
                  remakeReason?.note ? String(remakeReason.note) : "",
                ].filter(Boolean);
                return (
                  <p className="production-remake-provenance">
                    {source ? (
                      <>
                        {t("production.remakeOf")} <strong>{source.order_code}</strong>
                        {reasonBits.length ? ` — ${reasonBits.join(" · ")}` : ""}
                        {remakes.length ? " · " : ""}
                      </>
                    ) : null}
                    {remakes.length ? (
                      <>
                        {t("production.remadeBy")}{" "}
                        <strong>{remakes.map((order) => order.order_code).join(", ")}</strong>
                      </>
                    ) : null}
                  </p>
                );
              })()}
              {(() => {
                const blockers = detail.payload?.blockers;
                if (!Array.isArray(blockers) || !blockers.length) return null;
                return (
                  <ul className="production-blockers" role="alert">
                    {blockers.map((blocker) => (
                      <li key={String(blocker)}>
                        {String(blocker).startsWith("work_center_inactive:")
                          ? t("production.blockerWorkCenterInactive").replace(
                              "{kind}",
                              String(blocker).split(":").at(-1) ?? "",
                            )
                          : String(blocker)}
                      </li>
                    ))}
                  </ul>
                );
              })()}
              {(() => {
                const materials = detail.payload?.materials as WorkOrderMaterials | undefined;
                if (!materials) return null;
                return (
                  <dl className="production-materials">
                    <div>
                      <dt>{t("production.materialCuts")}</dt>
                      <dd>{materials.profile_cuts?.length ?? 0}</dd>
                    </div>
                    <div>
                      <dt>{t("production.materialGlass")}</dt>
                      <dd>{materials.glasses?.length ?? 0}</dd>
                    </div>
                    <div>
                      <dt>{t("production.materialHardware")}</dt>
                      <dd>{materials.hardware_items?.length ?? 0}</dd>
                    </div>
                  </dl>
                );
              })()}
              {(() => {
                const materials = detail.payload?.materials as WorkOrderMaterials | undefined;
                const glasses = (materials?.glasses ?? []) as GlassPiece[];
                if (!glasses.length) return null;
                const polishing = (detail.payload?.glass_polishing ?? []) as PolishingEntry[];
                const quantity = Math.max(1, Number(detail.quantity) || 1);
                return (
                  <GlassSummary
                    glasses={glasses}
                    polishing={polishing}
                    quantity={quantity}
                    onExport={(groups) =>
                      downloadCnc(detail.order_code, `glass.csv`, glassSummaryCsv(groups, quantity))
                    }
                  />
                );
              })()}
              {(() => {
                const optimization = detail.payload?.optimization as
                  WorkOrderOptimization | undefined;
                const canOptimize = role === "OWNER" || role === "WORKSHOP_MANAGER";
                const cutPlan = optimization?.bars?.workshop_cut_plan ?? [];
                const purchases = optimization?.bars?.purchase_list ?? [];
                const layouts = optimization?.sheets ?? [];
                const unnested = optimization?.unnested ?? [];
                const sheetPurchases = optimization?.sheet_purchases ?? [];
                // remnant_id → rack tag from the plan's consumed ledger, so a
                // bar row can name the physical drop it was cut from.
                const consumedLocations = new Map<string, string>(
                  (optimization?.remnants?.consumed ?? [])
                    .filter((entry) => entry.rack_location)
                    .map((entry) => [String(entry.id), String(entry.rack_location)]),
                );
                return (
                  <section
                    className="production-optimize"
                    aria-label={t("production.optimizeTitle")}
                  >
                    <header className="production-optimize-head">
                      <h3>{t("production.optimizeTitle")}</h3>
                      {optimization?.applied_strategy || optimization?.strategy ? (
                        <span className="production-remnant-tag">
                          {t("production.optimizeStrategy")}:{" "}
                          {t(
                            `production.optimizeVariant.${String(
                              optimization.applied_strategy ?? optimization.strategy,
                            )}` as Parameters<typeof t>[0],
                          ) || String(optimization.applied_strategy ?? optimization.strategy)}
                        </span>
                      ) : null}
                      {optimization?.optimized_at ? (
                        <time dateTime={optimization.optimized_at}>
                          {t("production.optimizeRunAt")}:
                          {formatDateTime(optimization.optimized_at)}
                        </time>
                      ) : null}
                    </header>
                    {canOptimize && !TERMINAL_ORDER_STATUSES.has(detail.status) ? (
                      <p className="production-optimize-inputs">
                        {t("production.optimizeInputsHint")}
                      </p>
                    ) : null}
                    {canOptimize && !TERMINAL_ORDER_STATUSES.has(detail.status) ? (
                      <div className="production-optimize-controls">
                        {(() => {
                          const sealedColor =
                            typeof detail.payload?.color === "string"
                              ? detail.payload.color.trim()
                              : "";
                          return (
                            <input
                              type="text"
                              value={optColor}
                              onChange={(event) => setOptColor(event.target.value)}
                              placeholder={t("production.optimizeColorPlaceholder")}
                              aria-label={t("production.optimizeColor")}
                              readOnly={Boolean(sealedColor)}
                              title={sealedColor ? t("production.optimizeColorSealed") : undefined}
                            />
                          );
                        })()}
                        <select
                          value={optStrategy}
                          onChange={(event) => setOptStrategy(event.target.value)}
                          aria-label={t("production.optimizeStrategy")}
                          title={
                            tOptional(`production.optimizeStrategyHint.${optStrategy}`) ?? undefined
                          }
                        >
                          <option value="auto" title={t("production.optimizeStrategyHint.auto")}>
                            {t("production.optimizeStrategyAuto")}
                          </option>
                          <option value="fast" title={t("production.optimizeStrategyHint.fast")}>
                            {t("production.optimizeStrategyFast")}
                          </option>
                          <option value="deep" title={t("production.optimizeStrategyHint.deep")}>
                            {t("production.optimizeStrategyDeep")}
                          </option>
                        </select>
                        <button
                          type="button"
                          disabled={busy || !optColor.trim()}
                          onClick={() => optimize(detail.id)}
                        >
                          {t("production.optimizeButton")}
                        </button>
                        <button
                          type="button"
                          className="production-compare"
                          disabled={busy || compareBusy}
                          onClick={() => compareStrategies(detail.id)}
                        >
                          {compareBusy
                            ? t("production.optimizeComparing")
                            : t("production.optimizeCompare")}
                        </button>
                      </div>
                    ) : null}
                    {(() => {
                      const stats = optimization?.stats;
                      if (!stats || optimization?.invalidated) return null;
                      return (
                        <p className="production-optimize-stats">
                          {t("production.optimizeStatsBars")}:{" "}
                          <strong>
                            {stats.bars_total}
                            {stats.bars_remnant
                              ? ` (+${stats.bars_remnant} ${t("production.optimizeStatsRemnant")})`
                              : ""}
                          </strong>
                          {" · "}
                          {t("production.optimizeStatsCuts")}: <strong>{stats.cuts_total}</strong>
                          {" · "}
                          {t("production.optimizeStatsUseful")}:{" "}
                          <strong>{fmtMm(stats.productive_length_mm)} mm</strong>
                          {" · "}
                          {t("production.optimizeStatsWaste")}:{" "}
                          <strong>{fmtMm(stats.process_waste_mm ?? stats.waste_mm)} mm</strong>
                          {stats.reusable_remnant_mm && stats.reusable_remnant_mm !== "0"
                            ? ` · ${t("production.optimizeStatsRemnantReusable")}: ${fmtMm(stats.reusable_remnant_mm)} mm`
                            : ""}
                          {stats.sheets_total
                            ? ` · ${t("production.optimizeStatsSheets")}: ${stats.sheets_total}`
                            : ""}
                          {stats.unnested_count
                            ? ` · ${t("production.optimizeStatsUnnested")}: ${stats.unnested_count}`
                            : ""}
                          {stats.purchase_bars || stats.purchase_sheets
                            ? ` · ${t("production.optimizeStatsPurchases")}: ${
                                stats.purchase_bars + stats.purchase_sheets
                              }`
                            : ""}
                          {canOptimize ? ` · ${stats.runtime_ms} ms` : ""}
                        </p>
                      );
                    })()}
                    {strategyCompare
                      ? (() => {
                          const bestWaste = Math.min(
                            ...strategyCompare.strategies.map((row) =>
                              Number(row.process_waste_mm ?? row.waste_mm),
                            ),
                          );
                          return (
                            <>
                              <table className="production-plan production-compare-table">
                                <thead>
                                  <tr>
                                    <th>{t("production.optimizeStrategy")}</th>
                                    <th>{t("production.optimizeStatsBars")}</th>
                                    <th>{t("production.optimizeStatsCuts")}</th>
                                    <th>{t("production.optimizeStatsWaste")}</th>
                                    <th>{t("production.optimizeStatsPurchases")}</th>
                                    <th>{t("production.optimizeStatsRemnants")}</th>
                                    <th>{t("production.optimizeStatsRuntime")}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {strategyCompare.strategies.map((row) => (
                                    <tr
                                      key={row.strategy}
                                      className={
                                        Number(row.process_waste_mm ?? row.waste_mm) === bestWaste
                                          ? "production-compare-best"
                                          : ""
                                      }
                                    >
                                      <td>
                                        {row.strategy === "fast"
                                          ? t("production.optimizeStrategyFast")
                                          : row.strategy === "deep"
                                            ? t("production.optimizeStrategyDeep")
                                            : row.strategy}
                                      </td>
                                      <td>
                                        {row.bars_total}
                                        {row.bars_remnant
                                          ? ` (+${row.bars_remnant} ${t("production.optimizeStatsRemnant")})`
                                          : ""}
                                      </td>
                                      <td>{row.cuts_total}</td>
                                      <td>{fmtMm(row.process_waste_mm ?? row.waste_mm)} mm</td>
                                      <td>{row.purchase_bars + row.purchase_sheets}</td>
                                      <td>
                                        {row.remnants_consumed}↓ {row.remnants_produced}↑
                                      </td>
                                      <td>{row.runtime_ms} ms</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              <p className="production-compare-note">
                                {t("production.optimizeCompareNote")}
                              </p>
                            </>
                          );
                        })()
                      : null}
                    {(() => {
                      const cncExport = detail.payload?.cnc_export as CncExport | undefined;
                      const dxfExport = detail.payload?.dxf_export as DxfExport | undefined;
                      const opsExport = detail.payload?.operations_export as OpsExport | undefined;
                      const files = Object.entries(cncExport?.files ?? {});
                      const dxfFiles = Object.entries(dxfExport?.files ?? {});
                      const opsFiles = Object.entries(opsExport?.files ?? {});
                      if (!optimization) return null;
                      return (
                        <div className="production-cnc">
                          <button
                            type="button"
                            className="production-cutpack"
                            disabled={busy || Boolean(optimization.invalidated)}
                            title={
                              optimization.invalidated
                                ? t("production.cutPackInvalidated")
                                : undefined
                            }
                            onClick={() => downloadCutPack(detail.id, detail.order_code)}
                          >
                            {t("production.cutPackButton")}
                          </button>
                          <button
                            type="button"
                            className="production-cutpack"
                            disabled={busy || Boolean(optimization.invalidated)}
                            title={
                              optimization.invalidated
                                ? t("production.cutPackInvalidated")
                                : undefined
                            }
                            onClick={() => downloadProductionPack(detail.id, detail.order_code)}
                          >
                            {t("production.productionPackButton")}
                          </button>
                          {canOptimize && !TERMINAL_ORDER_STATUSES.has(detail.status) ? (
                            <>
                              <button
                                type="button"
                                disabled={busy || Boolean(optimization.invalidated)}
                                title={
                                  optimization.invalidated
                                    ? t("production.cutPackInvalidated")
                                    : undefined
                                }
                                onClick={() => exportCnc(detail.id, detail.order_code)}
                              >
                                {t("production.cncExportButton")}
                              </button>
                              <button
                                type="button"
                                disabled={busy || Boolean(optimization.invalidated)}
                                title={
                                  optimization.invalidated
                                    ? t("production.cutPackInvalidated")
                                    : undefined
                                }
                                onClick={() => exportDxf(detail.id, detail.order_code)}
                              >
                                {t("production.dxfExportButton")}
                              </button>
                              <button
                                type="button"
                                disabled={busy || Boolean(optimization.invalidated)}
                                title={
                                  optimization.invalidated
                                    ? t("production.cutPackInvalidated")
                                    : undefined
                                }
                                onClick={() => exportOperations(detail.id, detail.order_code)}
                              >
                                {t("production.opsExportButton")}
                              </button>
                            </>
                          ) : null}
                          {files.map(([filename, content]) => (
                            <button
                              key={filename}
                              type="button"
                              className="production-cnc-file"
                              disabled={Boolean(optimization.invalidated)}
                              title={
                                optimization.invalidated ? t("production.fileStale") : undefined
                              }
                              onClick={() => downloadCnc(detail.order_code, filename, content)}
                            >
                              {filename}
                            </button>
                          ))}
                          {dxfFiles.map(([filename, content]) => (
                            <button
                              key={filename}
                              type="button"
                              className="production-cnc-file"
                              disabled={Boolean(optimization.invalidated)}
                              title={
                                optimization.invalidated ? t("production.fileStale") : undefined
                              }
                              onClick={() => downloadCnc(detail.order_code, filename, content)}
                            >
                              {filename}
                            </button>
                          ))}
                          {opsExport?.operation_count ? (
                            <span className="production-ops-count">
                              {opsExport.operation_count} {t("production.opsOperationsCount")}
                            </span>
                          ) : null}
                          {opsFiles.map(([filename, content]) => (
                            <button
                              key={filename}
                              type="button"
                              className="production-cnc-file"
                              disabled={Boolean(optimization.invalidated)}
                              title={
                                optimization.invalidated ? t("production.fileStale") : undefined
                              }
                              onClick={() => downloadCnc(detail.order_code, filename, content)}
                            >
                              {filename}
                            </button>
                          ))}
                        </div>
                      );
                    })()}
                    {optimization && !optimization.invalidated ? (
                      <CncPanel orderId={detail.id} canWrite={canOptimize} />
                    ) : null}
                    {!optimization ? (
                      <p className="production-optimize-empty">{t("production.optimizeEmpty")}</p>
                    ) : (
                      <>
                        {optimization.invalidated ? (
                          <p className="production-invalidated" role="alert">
                            {t("production.planInvalidated")}
                            {optimization.invalidated_by ? (
                              <code>{String(optimization.invalidated_by).slice(0, 8)}</code>
                            ) : null}
                          </p>
                        ) : null}
                        {!optimization.invalidated && (cutPlan.length || layouts.length) ? (
                          <CutPlanView
                            key={optimization.optimized_at ?? "optimization"}
                            optimization={optimization}
                            labels={(trace?.labels as Record<string, string> | undefined) ?? {}}
                            pieceCodes={pieceCodes}
                          />
                        ) : null}
                        {!optimization.invalidated && cutPlan.length ? (
                          <table className="production-plan">
                            <thead>
                              <tr>
                                <th>{t("production.optimizeBar")}</th>
                                <th>{t("production.optimizeSku")}</th>
                                <th>{t("production.optimizeStock")}</th>
                                <th>{t("production.optimizeCuts")}</th>
                                <th>{t("production.optimizeRemainder")}</th>
                                <th>{t("production.optimizeYield")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {cutPlan.map((bar) => (
                                <tr key={bar.bar_index}>
                                  <td>#{bar.bar_index}</td>
                                  <td>
                                    {bar.commercial_sku}
                                    {bar.source === "REMNANT" ? (
                                      <span className="production-remnant-tag">
                                        {" "}
                                        {t("production.optimizeRemnantBar")}
                                        {bar.remnant_id
                                          ? ` · REM-${String(bar.remnant_id).slice(0, 8)}`
                                          : ""}
                                        {consumedLocations.get(String(bar.remnant_id ?? ""))
                                          ? ` · ${consumedLocations.get(String(bar.remnant_id ?? ""))}`
                                          : ""}
                                      </span>
                                    ) : null}
                                  </td>
                                  <td>{fmtMm(bar.stock_length_mm)} mm</td>
                                  <td>
                                    {bar.cuts
                                      .map(
                                        (cut) =>
                                          `${cutRoleLabel(cut.role)} ${fmtMm(cut.length_mm)}mm u${cut.unit_index ?? 1}`,
                                      )
                                      .join(" · ")}
                                  </td>
                                  <td>
                                    {fmtMm(bar.remainder_mm)} mm
                                    {bar.remainder_reusable ? (
                                      <span className="production-remnant-tag">
                                        {" "}
                                        {t("production.optimizeRemnantReusable")}
                                      </span>
                                    ) : null}
                                  </td>
                                  <td>{fmtPct(bar.yield_pct)}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : null}
                        {purchases.length || sheetPurchases.length ? (
                          <p className="production-optimize-purchases">
                            {t("production.optimizeStockNew")}:{" "}
                            {purchases
                              .map(
                                (line) =>
                                  `${line.qty_bars} ${t("production.optimizePurchaseUnit")} ${line.commercial_sku}`,
                              )
                              .concat(
                                sheetPurchases.map(
                                  (line) =>
                                    `${line.qty_sheets} ${t("production.optimizePurchaseSheet")} ${line.purchasing_sku}`,
                                ),
                              )
                              .join(" · ")}
                          </p>
                        ) : null}
                        {(() => {
                          // Real "what to buy": only the skus whose stock
                          // reservation came back short, or with no stock
                          // authority at all — the plan's NEW-bar list is
                          // consumption, not shortage.
                          const shortRows = (optimization?.stock_reservations ?? []).filter(
                            (row) =>
                              row.short !== undefined &&
                              row.short !== null &&
                              row.short !== "0" &&
                              row.short !== "0.00",
                          );
                          const unmapped = optimization?.unmapped_stock_skus ?? [];
                          if (!shortRows.length && !unmapped.length) return null;
                          return (
                            <p className="production-optimize-purchases production-stock-short">
                              {t("production.optimizeBuy")}:{" "}
                              {shortRows
                                .map((row) =>
                                  `${row.sku ?? row.name ?? "?"} × ${row.short} ${row.unit ?? ""}`.trim(),
                                )
                                .concat(
                                  unmapped.map(
                                    (sku) => `${sku} (${t("production.optimizeUnmapped")})`,
                                  ),
                                )
                                .join(" · ")}
                            </p>
                          );
                        })()}
                        {(() => {
                          const reservations = optimization?.stock_reservations ?? [];
                          const unmappedSkus = optimization?.unmapped_stock_skus ?? [];
                          if (!reservations.length && !unmappedSkus.length) return null;
                          return (
                            <section
                              className="production-stock-reserve"
                              aria-label={t("production.stockReserveTitle")}
                            >
                              <h4>{t("production.stockReserveTitle")}</h4>
                              {reservations.length ? (
                                <table className="production-plan">
                                  <thead>
                                    <tr>
                                      <th>{t("production.stockKind")}</th>
                                      <th>{t("production.stockSku")}</th>
                                      <th>{t("production.stockOnHand")}</th>
                                      <th>{t("production.stockNeeded")}</th>
                                      <th>{t("production.stockReserved")}</th>
                                      <th>{t("production.stockShort")}</th>
                                      <th>{t("production.stockConsumedAt")}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {reservations.map((row, index) => (
                                      <tr key={`${row.kind ?? ""}-${row.sku ?? ""}-${index}`}>
                                        <td>{row.name ?? row.sku ?? "—"}</td>
                                        <td>
                                          {row.sku ?? "—"} · {row.unit ?? ""}
                                        </td>
                                        <td>{row.on_hand ?? "0"}</td>
                                        <td>{row.needed ?? "0"}</td>
                                        <td>{row.reserved ?? "0"}</td>
                                        <td>
                                          {row.short && row.short !== "0" ? (
                                            <strong className="production-stock-short">
                                              {row.short}
                                            </strong>
                                          ) : (
                                            "0"
                                          )}
                                        </td>
                                        <td>
                                          {row.consumed_at ? formatDate(row.consumed_at) : "—"}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : null}
                              {unmappedSkus.length ? (
                                <p className="production-stock-unmapped">
                                  {t("production.stockUnmapped")}: {unmappedSkus.join(" · ")}
                                </p>
                              ) : null}
                            </section>
                          );
                        })()}
                        {(() => {
                          const remnantLedger = optimization?.remnants;
                          const consumed = remnantLedger?.consumed ?? [];
                          const producedCount =
                            (remnantLedger?.produced_bars?.length ?? 0) +
                            (remnantLedger?.produced_sheets?.length ?? 0);
                          const metrics = optimization?.bars?.metrics;
                          const comparison = optimization?.bars?.strategy_comparison;
                          const comparisonEntries = comparison
                            ? (["fast", "deep"] as const)
                                .filter((key) => comparison[key])
                                .map((key) => ({ key, metrics: comparison[key] }))
                            : [];
                          const unplaced = optimization?.bars?.unplaced ?? [];
                          return (
                            <>
                              {consumed.length || producedCount ? (
                                <p className="production-optimize-remnants">
                                  {consumed.length ? (
                                    <span>
                                      {t("production.optimizeRemnantsUsed")}: {consumed.length}
                                    </span>
                                  ) : null}
                                  {producedCount ? (
                                    <span>
                                      {t("production.optimizeRemnantsProduced")}: {producedCount}
                                    </span>
                                  ) : null}
                                </p>
                              ) : null}
                              {metrics ? (
                                <p className="production-optimize-metrics">
                                  {t("production.optimizeMetrics")}:{" "}
                                  {[
                                    `${metrics.bars ?? 0} barras`,
                                    `${metrics.purchased_bars ?? 0} compra`,
                                    `${metrics.remnant_bars ?? 0} barras retazo`,
                                    `${metrics.process_waste_mm ?? "0"} mm merma de proceso`,
                                    `${metrics.reusable_remnant_mm ?? "0"} mm retazo reutilizable`,
                                    `${metrics.cuts ?? 0} cortes`,
                                  ].join(" · ")}
                                </p>
                              ) : null}
                              {comparisonEntries.length > 1 ? (
                                <p className="production-optimize-metrics">
                                  {t("production.optimizeComparison")}:{" "}
                                  {comparisonEntries
                                    .map(
                                      ({ key, metrics: m }) =>
                                        `${
                                          t(
                                            `production.optimizeVariant.${key}` as Parameters<
                                              typeof t
                                            >[0],
                                          ) || key
                                        }${comparison?.chosen === key ? " ← " + t("production.optimizeChosen") : ""}: ${m?.purchased_bars ?? 0} barras · ${m?.process_waste_mm ?? "0"} mm`,
                                    )
                                    .join("  ·  ")}
                                </p>
                              ) : null}
                              {unplaced.length ? (
                                <p className="production-optimize-unnested" role="alert">
                                  {t("production.optimizeUnplaced")}:{" "}
                                  {unplaced
                                    .map(
                                      (entry) =>
                                        `${entry.piece?.piece_id ?? "?"} (${entry.reason ?? ""})`,
                                    )
                                    .join(" · ")}
                                </p>
                              ) : null}
                            </>
                          );
                        })()}
                        {layouts.length ? (
                          <table className="production-plan">
                            <thead>
                              <tr>
                                <th>{t("production.optimizeSheet")}</th>
                                <th>{t("production.optimizeSku")}</th>
                                <th>{t("production.optimizeSize")}</th>
                                <th>{t("production.optimizePieces")}</th>
                                <th>{t("production.optimizeYield")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {layouts.map((layout) => (
                                <tr key={`${layout.purchasing_sku}-${layout.sheet_index}`}>
                                  <td>#{layout.sheet_index}</td>
                                  <td>{layout.purchasing_sku}</td>
                                  <td>
                                    {fmtMm(layout.sheet_width_mm)}×{fmtMm(layout.sheet_height_mm)}{" "}
                                    mm
                                  </td>
                                  <td>
                                    {layout.source === "REMNANT" ? (
                                      <span className="production-remnant-tag">
                                        {t("production.optimizeRemnantBar")}
                                        {layout.remnant_id
                                          ? ` · REM-${String(layout.remnant_id).slice(0, 8)}`
                                          : ""}
                                        {consumedLocations.get(String(layout.remnant_id ?? ""))
                                          ? ` · ${consumedLocations.get(String(layout.remnant_id ?? ""))}`
                                          : ""}{" "}
                                      </span>
                                    ) : null}
                                    {layout.placements
                                      .map(
                                        (piece) =>
                                          `${piece.piece_id}${piece.rotated ? ` (${t("production.optimizeRotated")})` : ""}`,
                                      )
                                      .join(" · ")}
                                  </td>
                                  <td>{fmtPct(layout.yield_pct)}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : null}
                        {unnested.length ? (
                          <p className="production-optimize-unnested" role="alert">
                            {t("production.optimizeUnnested")}:{" "}
                            {unnested
                              .map(
                                (piece) =>
                                  `${tOptional(`production.pieceKind.${piece.kind}`) ?? piece.kind} ${fmtMm(piece.width_mm)}×${fmtMm(piece.height_mm)} mm ×${piece.quantity} (${piece.group})` +
                                  (piece.reason
                                    ? ` — ${tOptional(`production.unnestedReason.${piece.reason}`) ?? piece.reason}`
                                    : ""),
                              )
                              .join(" · ")}
                          </p>
                        ) : null}
                      </>
                    )}
                  </section>
                );
              })()}
              {(() => {
                const packing = detail.payload?.packing as WorkOrderPacking | undefined;
                const units = packing?.units ?? [];
                return (
                  <section className="production-packing" aria-label={t("production.packingTitle")}>
                    <header className="production-optimize-head">
                      <h3>{t("production.packingTitle")}</h3>
                      {packing?.generated_at ? (
                        <time dateTime={packing.generated_at}>
                          {formatDateTime(packing.generated_at)}
                        </time>
                      ) : null}
                      {canWrite &&
                      detail.status !== "DISPATCHED" &&
                      detail.status !== "INSTALLED" &&
                      detail.status !== "CANCELLED" ? (
                        <button type="button" disabled={busy} onClick={() => pack(detail.id)}>
                          {packing
                            ? t("production.packingRegenerate")
                            : t("production.packingGenerate")}
                        </button>
                      ) : null}
                      {units.length ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void showLabels(detail.id)}
                        >
                          {t("production.labelsShow")}
                        </button>
                      ) : null}
                      {labels.length ? (
                        <button type="button" onClick={() => window.print()}>
                          {t("production.labelsPrint")}
                        </button>
                      ) : null}
                    </header>
                    {labels.length ? (
                      <ul className="production-labels">
                        {labels.map((label) => (
                          <li key={label.label_code} className="production-label">
                            <span className="production-label-code">{label.label_code}</span>
                            <span
                              className="production-label-qr"
                              // Generated server-side by segno from the sealed manifest.
                              dangerouslySetInnerHTML={{ __html: label.qr_svg }}
                            />
                            <span className="production-label-pieces">
                              {t("production.labelsPieces")}: {label.pieces}
                            </span>
                            <span className="production-label-parts">
                              {
                                // Non-colliding glyphs — M-xx/V-xx/H-xx mean
                                // member/bay/leaf everywhere else, so the
                                // count letters can't reuse them.
                                (
                                  [
                                    ["PER", label.profiles],
                                    ["REF", label.reinforcements],
                                    ["VID", label.glasses],
                                    ["PAN", label.panels],
                                    ["HER", label.hardware],
                                  ] as Array<[string, number]>
                                )
                                  .filter(([, count]) => count > 0)
                                  .map(([kind, count]) => `${kind}×${count}`)
                                  .join(" · ")
                              }
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {units.length ? (
                      <table className="production-plan">
                        <thead>
                          <tr>
                            <th>{t("production.packingLabel")}</th>
                            <th>{t("production.packingProfiles")}</th>
                            <th>{t("production.packingReinforcements")}</th>
                            <th>{t("production.packingGlasses")}</th>
                            <th>{t("production.packingPanels")}</th>
                            <th>{t("production.packingHardware")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {units.map((unit) => (
                            <tr key={unit.unit_index}>
                              <td className="production-label-code">{unit.label_code}</td>
                              <td>{unit.profiles ?? 0}</td>
                              <td>{unit.reinforcements ?? 0}</td>
                              <td>{unit.glasses ?? 0}</td>
                              <td>{unit.panels ?? 0}</td>
                              <td>{unit.hardware ?? 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <p className="production-optimize-empty">{t("production.packingEmpty")}</p>
                    )}
                    {(() => {
                      // §14: packing honesty — surface unresolved material
                      // shortage and unnested pieces instead of letting a
                      // complete-looking manifest hide them.
                      const unnestedRaw = (
                        detail.payload?.optimization as { unnested?: unknown[] } | undefined
                      )?.unnested;
                      const unnested = Array.isArray(unnestedRaw) ? unnestedRaw.length : 0;
                      const missing = (detail.shortage ?? 0) + unnested;
                      if (!missing) return null;
                      return (
                        <p className="production-packing-missing" role="alert">
                          {t("production.packingMissing")
                            .replace("{short}", String(detail.shortage ?? 0))
                            .replace("{unnested}", String(unnested))}
                        </p>
                      );
                    })()}
                  </section>
                );
              })()}
              {(() => {
                const canSchedule =
                  canWrite && (detail.status === "COMPLETED" || detail.status === "DISPATCHED");
                return (
                  <section
                    className="production-delivery"
                    aria-label={t("production.deliveryTitle")}
                  >
                    <header className="production-optimize-head">
                      <h3>{t("production.deliveryTitle")}</h3>
                      {delivery ? (
                        <span
                          className={`production-chip delivery-${delivery.status.toLowerCase()}`}
                        >
                          {t(
                            deliveryStatusKey[delivery.status] ??
                              "production.deliveryStatusScheduled",
                          )}
                        </span>
                      ) : null}
                      {canSchedule &&
                      deliveryForm === null &&
                      (!delivery ||
                        delivery.status === "DELIVERED" ||
                        delivery.status === "FAILED") &&
                      (deliveries.length === 0 || pendingUnits.length > 0) ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => openDeliveryForm(null)}
                        >
                          {deliveries.length
                            ? t("production.deliveryScheduleNext")
                            : t("production.deliverySchedule")}
                        </button>
                      ) : null}
                      {canWrite && delivery && delivery.status !== "DELIVERED" ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => openDeliveryForm(delivery)}
                        >
                          {t("production.deliveryReschedule")}
                        </button>
                      ) : null}
                      {canField &&
                      delivery?.status === "SCHEDULED" &&
                      detail.status === "DISPATCHED" ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void transitionDelivery(detail.id, "ON_ROUTE")}
                        >
                          {t("production.deliveryOnRoute")}
                        </button>
                      ) : null}
                      {canField && delivery?.status === "ON_ROUTE" && !delivery.confirmation ? (
                        <button
                          type="button"
                          className="production-chip-danger"
                          disabled={busy}
                          onClick={() => void transitionDelivery(detail.id, "FAILED")}
                        >
                          {t("production.deliveryFailed")}
                        </button>
                      ) : null}
                      {canField &&
                      delivery &&
                      (delivery.status === "ON_ROUTE" || delivery.status === "DELIVERED") &&
                      !delivery.confirmation &&
                      !confirmOpen ? (
                        <button type="button" disabled={busy} onClick={openConfirmForm}>
                          {t("production.deliveryConfirm")}
                        </button>
                      ) : null}
                      {delivery?.confirmation ? (
                        <button
                          type="button"
                          className="production-chip delivery-delivered"
                          onClick={() => void openConfirmation(detail.id, delivery.id)}
                        >
                          {delivery.confirmation.confirmation_code}
                        </button>
                      ) : null}
                    </header>
                    {delivery ? (
                      <dl className="production-delivery-facts">
                        <div>
                          <dt>{t("production.deliveryDate")}</dt>
                          <dd>
                            {delivery.scheduled_date} ·{" "}
                            {t(
                              delivery.time_window === "JORNADA"
                                ? "production.windowAllDay"
                                : delivery.time_window === "PM"
                                  ? "production.windowPm"
                                  : "production.windowAm",
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>{t("production.deliveryAddress")}</dt>
                          <dd>{delivery.address}</dd>
                        </div>
                        {delivery.contact_name || delivery.contact_phone ? (
                          <div>
                            <dt>{t("production.deliveryContact")}</dt>
                            <dd>
                              {[delivery.contact_name, delivery.contact_phone]
                                .filter(Boolean)
                                .join(" · ")}
                            </dd>
                          </div>
                        ) : null}
                        {delivery.installer_name ? (
                          <div>
                            <dt>{t("production.deliveryInstaller")}</dt>
                            <dd>{delivery.installer_name}</dd>
                          </div>
                        ) : null}
                        {delivery.notes ? (
                          <div>
                            <dt>{t("production.deliveryNotes")}</dt>
                            <dd>{delivery.notes}</dd>
                          </div>
                        ) : null}
                      </dl>
                    ) : null}
                    {deliveries.length > 1 ? (
                      <ul className="production-delivery-trips">
                        {deliveries.map((trip) => (
                          <li key={trip.id} className="production-delivery-trip">
                            <span
                              className={`production-chip delivery-${trip.status.toLowerCase()}`}
                            >
                              {t(
                                deliveryStatusKey[trip.status] ??
                                  "production.deliveryStatusScheduled",
                              )}
                            </span>
                            <span className="production-delivery-trip-date">
                              {trip.scheduled_date}
                            </span>
                            <span className="production-delivery-trip-units">
                              {unitLabel(trip.unit_indexes)}
                            </span>
                            {trip.confirmation ? (
                              <button
                                type="button"
                                className="production-chip delivery-delivered"
                                onClick={() => void openConfirmation(detail.id, trip.id)}
                              >
                                {trip.confirmation.confirmation_code}
                              </button>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {deliveries.length > 0 && pendingUnits.length > 0 ? (
                      <p className="production-delivery-pending">
                        {t("production.deliveryUnitsPending")}: {unitLabel(pendingUnits)}
                      </p>
                    ) : null}
                    {canWrite && detail.dispatch_ready && pendingUnits.length > 1 ? (
                      <fieldset className="production-delivery-units">
                        <legend>{t("production.dispatchUnits")}</legend>
                        <div className="production-delivery-unit-chips">
                          {pendingUnits.map((idx) => {
                            const current = dispatchUnitsSel.length
                              ? dispatchUnitsSel
                              : pendingUnits;
                            const active = current.includes(idx);
                            return (
                              <button
                                type="button"
                                key={idx}
                                className={`chip${active ? " is-active" : ""}`}
                                aria-pressed={active}
                                onClick={() => {
                                  const next = active
                                    ? current.filter((i) => i !== idx)
                                    : [...current, idx].sort((a, b) => a - b);
                                  setDispatchUnitsSel(
                                    next.length === pendingUnits.length ? [] : next,
                                  );
                                }}
                              >
                                {unitLabel([idx])}
                              </button>
                            );
                          })}
                        </div>
                        <p className="production-delivery-units-hint">
                          {t("production.dispatchUnitsHint")}
                        </p>
                      </fieldset>
                    ) : null}
                    {confirmOpen && canField && delivery ? (
                      <form
                        className="production-delivery-form production-confirm-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void submitConfirmation(detail.id);
                        }}
                      >
                        <label>
                          {t("production.deliveryReceiver")}
                          <input
                            type="text"
                            required
                            maxLength={200}
                            value={confirmName}
                            onChange={(event) => setConfirmName(event.target.value)}
                          />
                        </label>
                        <label>
                          {t("production.deliveryReceiverRut")}
                          <input
                            type="text"
                            maxLength={30}
                            value={confirmRut}
                            onChange={(event) => setConfirmRut(event.target.value)}
                          />
                        </label>
                        <div className="production-delivery-wide">
                          {t("production.deliverySignature")}
                          <div
                            className="production-signature-mode"
                            role="group"
                            aria-label={t("production.deliverySignature")}
                          >
                            <button
                              type="button"
                              className={signatureMode === "draw" ? "chip is-active" : "chip"}
                              aria-pressed={signatureMode === "draw"}
                              onClick={() => setSignatureMode("draw")}
                            >
                              {t("production.signatureModeDraw")}
                            </button>
                            <button
                              type="button"
                              className={signatureMode === "typed" ? "chip is-active" : "chip"}
                              aria-pressed={signatureMode === "typed"}
                              onClick={() => setSignatureMode("typed")}
                            >
                              {t("production.signatureModeType")}
                            </button>
                          </div>
                          <div hidden={signatureMode !== "draw"}>
                            <SignaturePad ref={sigRef} onDraw={setSigDrawn} />
                          </div>
                          {signatureMode === "typed" ? (
                            <p className="production-signature-typed">
                              {t("production.signatureTypedHint")}
                            </p>
                          ) : null}
                        </div>
                        <label className="production-confirm-collect">
                          <input
                            type="checkbox"
                            checked={collectPayment}
                            onChange={(event) => setCollectPayment(event.target.checked)}
                          />
                          {t("production.deliveryCollect")}
                        </label>
                        {collectPayment ? (
                          <>
                            <label>
                              {t("production.deliveryCollectAmount")}
                              <input
                                type="number"
                                min="1"
                                step="1"
                                required
                                value={collectAmount}
                                onChange={(event) => setCollectAmount(event.target.value)}
                              />
                            </label>
                            <label>
                              {t("projects.paymentMethod")}
                              <select
                                value={collectMethod}
                                onChange={(event) =>
                                  setCollectMethod(event.target.value as MethodEnum)
                                }
                              >
                                <option value="CASH">{t("projects.paymentMethodCash")}</option>
                                <option value="TRANSFER">
                                  {t("projects.paymentMethodTransfer")}
                                </option>
                                <option value="CARD">{t("projects.paymentMethodCard")}</option>
                                <option value="CHECK">{t("projects.paymentMethodCheck")}</option>
                                <option value="OTHER">{t("projects.paymentMethodOther")}</option>
                              </select>
                            </label>
                            <label>
                              {t("projects.paymentKind")}
                              <select
                                value={collectKind}
                                onChange={(event) =>
                                  setCollectKind(event.target.value as PaymentKindEnum)
                                }
                              >
                                <option value="ANTICIPO">
                                  {t("projects.paymentKindAnticipo")}
                                </option>
                                <option value="PARCIAL">{t("projects.paymentKindParcial")}</option>
                                <option value="SALDO">{t("projects.paymentKindSaldo")}</option>
                              </select>
                            </label>
                          </>
                        ) : null}
                        <div className="production-delivery-actions">
                          <button
                            type="submit"
                            disabled={
                              busy || !confirmName.trim() || (signatureMode === "draw" && !sigDrawn)
                            }
                          >
                            {t("production.deliveryConfirmSubmit")}
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => sigRef.current?.clear()}
                          >
                            {t("production.deliverySignatureClear")}
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setConfirmOpen(false)}
                          >
                            {t("production.deliveryCancel")}
                          </button>
                        </div>
                      </form>
                    ) : null}
                    {!delivery && deliveryForm === null ? (
                      <p className="production-optimize-empty">{t("production.deliveryEmpty")}</p>
                    ) : null}
                    {deliveryForm !== null && canWrite ? (
                      <form
                        className="production-delivery-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void saveDelivery(detail.id);
                        }}
                      >
                        <label>
                          {t("production.deliveryDate")}
                          <input
                            type="date"
                            required
                            value={deliveryForm.scheduled_date}
                            onChange={(event) =>
                              setDeliveryForm({
                                ...deliveryForm,
                                scheduled_date: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          {t("production.deliveryWindow")}
                          <select
                            value={deliveryForm.time_window ?? "AM"}
                            onChange={(event) =>
                              setDeliveryForm({
                                ...deliveryForm,
                                time_window: event.target
                                  .value as DeliveryScheduleRequestRequest["time_window"],
                              })
                            }
                          >
                            <option value="AM">{t("production.windowAm")}</option>
                            <option value="PM">{t("production.windowPm")}</option>
                            <option value="JORNADA">{t("production.windowAllDay")}</option>
                          </select>
                        </label>
                        <label className="production-delivery-wide">
                          {t("production.deliveryAddress")}
                          <input
                            required
                            value={deliveryForm.address}
                            onChange={(event) =>
                              setDeliveryForm({
                                ...deliveryForm,
                                address: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          {t("production.deliveryContact")}
                          <input
                            value={deliveryForm.contact_name ?? ""}
                            onChange={(event) =>
                              setDeliveryForm({
                                ...deliveryForm,
                                contact_name: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          {t("production.deliveryPhone")}
                          <input
                            value={deliveryForm.contact_phone ?? ""}
                            onChange={(event) =>
                              setDeliveryForm({
                                ...deliveryForm,
                                contact_phone: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          {t("production.deliveryInstaller")}
                          <input
                            value={deliveryForm.installer_name ?? ""}
                            onChange={(event) =>
                              setDeliveryForm({
                                ...deliveryForm,
                                installer_name: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label className="production-delivery-wide">
                          {t("production.deliveryNotes")}
                          <input
                            value={deliveryForm.notes ?? ""}
                            onChange={(event) =>
                              setDeliveryForm({
                                ...deliveryForm,
                                notes: event.target.value,
                              })
                            }
                          />
                        </label>
                        {(() => {
                          // Partial trips: the pickable set is the pending
                          // balance plus whatever this trip already carries
                          // (delivered units are sealed and never offered).
                          const allowed = [
                            ...new Set([...pendingUnits, ...(deliveryForm.unit_indexes ?? [])]),
                          ].sort((a, b) => a - b);
                          if (allowed.length < 2) return null;
                          const checked = deliveryForm.unit_indexes ?? allowed;
                          return (
                            <fieldset className="production-delivery-units production-delivery-wide">
                              <legend>{t("production.deliveryUnitsTrip")}</legend>
                              <div className="production-delivery-unit-chips">
                                {allowed.map((idx) => {
                                  const active = checked.includes(idx);
                                  return (
                                    <button
                                      type="button"
                                      key={idx}
                                      className={`chip${active ? " is-active" : ""}`}
                                      aria-pressed={active}
                                      disabled={checked.length === 1 && active}
                                      onClick={() => {
                                        const next = active
                                          ? checked.filter((i) => i !== idx)
                                          : [...checked, idx].sort((a, b) => a - b);
                                        setDeliveryForm({
                                          ...deliveryForm,
                                          unit_indexes:
                                            next.length === allowed.length ? null : next,
                                        });
                                      }}
                                    >
                                      {unitLabel([idx])}
                                    </button>
                                  );
                                })}
                              </div>
                              <p className="production-delivery-units-hint">
                                {t("production.deliveryUnitsAllHint")}
                              </p>
                            </fieldset>
                          );
                        })()}
                        <div className="production-delivery-actions">
                          <button type="submit" disabled={busy}>
                            {t("production.deliverySave")}
                          </button>
                          <button type="button" onClick={() => setDeliveryForm(null)}>
                            {t("production.deliveryCancel")}
                          </button>
                        </div>
                      </form>
                    ) : null}
                  </section>
                );
              })()}
              {(() => {
                const nextStep = detail.steps.find(
                  (step) => step.status !== "DONE" && stepActions(step).length > 0,
                );
                if (!nextStep || TERMINAL_ORDER_STATUSES.has(detail.status)) return null;
                return (
                  <div
                    className="production-next"
                    role="group"
                    aria-label={t("production.nextStep")}
                  >
                    <span className="production-next-label">
                      {t("production.nextStep")}: <strong>{nextStep.label}</strong>
                      {(nextStep.work_center_name ?? nextStep.work_center_code)
                        ? ` · ${nextStep.work_center_name ?? nextStep.work_center_code}`
                        : ""}
                    </span>
                    {canStep ? (
                      <span className="production-step-actions">
                        {nextStep.code === "QC" && stepActions(nextStep).includes("QC_FAIL") ? (
                          <select
                            className="production-qc-item"
                            aria-label={t("production.qcItem")}
                            value={qcFailItem}
                            onChange={(event) => setQcFailItem(event.target.value)}
                          >
                            <option value="">{t("production.qcItemAny")}</option>
                            {qcItemOptions.map((code) => (
                              <option key={code} value={code}>
                                {code}
                              </option>
                            ))}
                          </select>
                        ) : null}
                        {stepActions(nextStep)
                          // Same supervisor gate as the step list — a blocked
                          // next step must not offer Desbloquear to operators.
                          .filter((stepAction) => stepAction !== "UNBLOCK" || canWrite)
                          .map((stepAction) =>
                            stepAction === "START" && stepNeedsPlan(nextStep, detail) ? (
                              <span className="production-step-hint" key={stepAction}>
                                {t(
                                  canWrite
                                    ? "production.stepNeedsPlan"
                                    : "production.stepNeedsPlanWait",
                                )}
                              </span>
                            ) : (
                              <button
                                key={stepAction}
                                type="button"
                                disabled={busy}
                                onClick={() => void transition(nextStep.id, stepAction, detail.id)}
                              >
                                {t(actionLabel[stepAction])}
                              </button>
                            ),
                          )}
                      </span>
                    ) : null}
                  </div>
                );
              })()}
              {(() => {
                const nextStep = detail.steps.find(
                  (step) => step.status !== "DONE" && stepActions(step).length > 0,
                );
                const operatorStep =
                  detail.steps.find((step) => step.id === operatorStepId) ??
                  nextStep ??
                  detail.steps[detail.steps.length - 1] ??
                  null;
                // Only the first open station is actually workable — every
                // later READY step reads "Pendiente", never "Lista".
                const firstOpenStepId =
                  detail.steps.find((step) => step.status !== "DONE")?.id ?? null;
                // One builder feeds both the step row and the operator
                // card's sticky footer — the primary action (iniciar,
                // registrar, completar) stays on screen while the card's
                // materials and ops scroll beneath it.
                const renderStepActionBar = (step: (typeof detail.steps)[number]) => {
                  if (!canStep || TERMINAL_ORDER_STATUSES.has(detail.status)) return null;
                  return (
                    <div className="production-step-actions">
                      {step.code === "QC" && stepActions(step).includes("QC_FAIL") ? (
                        <select
                          className="production-qc-item"
                          aria-label={t("production.qcItem")}
                          value={qcFailItem}
                          onChange={(event) => setQcFailItem(event.target.value)}
                        >
                          <option value="">{t("production.qcItemAny")}</option>
                          {qcItemOptions.map((code) => (
                            <option key={code} value={code}>
                              {code}
                            </option>
                          ))}
                        </select>
                      ) : null}
                      {stepActions(step)
                        // START only exists on the earliest open step —
                        // the backend sequence gate rejects every other
                        // one with a guaranteed 422.
                        .filter((stepAction) => stepAction !== "START" || step.id === nextStep?.id)
                        // UNBLOCK is a supervisor action — the backend
                        // refuses it for operators
                        // (unblock_requires_supervisor), so the button
                        // would be a guaranteed error toast.
                        .filter((stepAction) => stepAction !== "UNBLOCK" || canWrite)
                        .map((stepAction) =>
                          stepAction === "START" && stepNeedsPlan(step, detail) ? (
                            <span className="production-step-hint" key={stepAction}>
                              {t(
                                canWrite
                                  ? "production.stepNeedsPlan"
                                  : "production.stepNeedsPlanWait",
                              )}
                            </span>
                          ) : (
                            <button
                              key={stepAction}
                              type="button"
                              disabled={busy}
                              onClick={() => void transition(step.id, stepAction, detail.id)}
                            >
                              {t(actionLabel[stepAction])}
                            </button>
                          ),
                        )}
                    </div>
                  );
                };
                return (
                  <>
                    <ol className="production-steps">
                      {detail.steps.map((step) => (
                        <li
                          key={step.id}
                          className={`production-step step-${step.status.toLowerCase()}${
                            operatorStep?.id === step.id ? " step-operator" : ""
                          }`}
                        >
                          <div className="production-step-head">
                            <span className="production-step-seq">{step.sequence}</span>
                            <button
                              type="button"
                              className="production-step-operator"
                              onClick={() =>
                                setOperatorStepId((current) =>
                                  current === step.id ? null : step.id,
                                )
                              }
                            >
                              {step.label}
                            </button>
                            {(step.work_center_name ?? step.work_center_code) ? (
                              <span className="production-step-center">
                                {step.work_center_name ?? step.work_center_code}
                              </span>
                            ) : null}
                            <span className={`production-chip status-${step.status.toLowerCase()}`}>
                              {t(
                                step.status === "READY" && step.id !== firstOpenStepId
                                  ? "production.stepPending"
                                  : (stepStatusKey[step.status] ?? "production.stepReady"),
                              )}
                            </span>
                          </div>
                          {step.note ? <p className="production-step-note">{step.note}</p> : null}
                          {renderStepActionBar(step)}
                        </li>
                      ))}
                    </ol>
                    {operatorStep ? (
                      <OperatorStepCard
                        step={operatorStep}
                        trace={trace}
                        traceBusy={traceBusy}
                        actionBar={renderStepActionBar(operatorStep)}
                        onQcCheck={
                          canStep ? (stepId, check) => qcCheck(stepId, check, detail.id) : undefined
                        }
                        opsCheckable={
                          canStep &&
                          operatorStep.status === "IN_PROGRESS" &&
                          PLAN_REQUIRED_CODES.has(operatorStep.code)
                        }
                        opsDone={opsDone[operatorStep.id] ?? []}
                        onOpsDoneChange={(ids) =>
                          setOpsDone((current) => ({
                            ...current,
                            [operatorStep.id]: ids,
                          }))
                        }
                      />
                    ) : null}
                  </>
                );
              })()}
              {canStep ? (
                <label className="production-note">
                  {t("production.noteLabel")}
                  <input
                    type="text"
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder={t("production.notePlaceholder")}
                  />
                </label>
              ) : null}
              <section className="production-trace" aria-label={t("production.traceTitle")}>
                <header className="production-optimize-head">
                  <h3>{t("production.traceTitle")}</h3>
                  {!trace ? (
                    <button type="button" disabled={traceBusy} onClick={() => void loadTrace()}>
                      {traceBusy ? t("production.traceLoading") : t("production.traceLoad")}
                    </button>
                  ) : null}
                </header>
                {trace ? (
                  <div className="production-trace-body">
                    <p className="production-trace-chain">
                      {trace.project?.code ? String(trace.project.code) : "—"}
                      {" → "}
                      {trace.version?.revision_code ? String(trace.version.revision_code) : "—"}
                      {" → "}
                      {String(trace.work_order?.order_code ?? "—")}
                    </p>
                    {trace.plan ? <TracePlan plan={trace.plan} /> : null}
                    {trace.stock ? <TraceStock stock={trace.stock} /> : null}
                  </div>
                ) : null}
              </section>
              <section className="production-events" aria-label={t("production.events")}>
                <h3>{t("production.events")}</h3>
                <ol>
                  {detail.events.map((event) => {
                    const eventNote = (event.payload as { note?: unknown } | undefined)?.note;
                    const eventItem = (event.payload as { qc_item?: unknown } | undefined)?.qc_item;
                    const eventStep = detail.steps.find((step) => step.id === event.step_id);
                    const stepName =
                      eventStep?.label ??
                      (event.step_code ? stationCodeLabel(event.step_code) : undefined);
                    return (
                      <li key={event.id}>
                        <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                        {stepName ? <strong>{stepName} · </strong> : null}
                        <span>{t(eventKey[event.event] ?? "production.eventNote")}</span>
                        {typeof eventItem === "string" && eventItem.trim() ? (
                          <strong className="production-event-item"> · {eventItem}</strong>
                        ) : null}
                        {event.actor_label ? <span> · {event.actor_label}</span> : null}
                        {typeof eventNote === "string" && eventNote.trim() ? (
                          <em className="production-event-note">{eventNote}</em>
                        ) : null}
                      </li>
                    );
                  })}
                </ol>
              </section>
            </>
          ) : (
            <p className="production-pick">{t("production.pickOrder")}</p>
          )}
        </article>
      </div>
    </section>
  );
}
