import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  productionOrderCncExport,
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
  productionOrderPacking,
  productionOrderRemake,
  productionOrders,
  productionPieceTrace,
  productionOrderTrace,
  productionPrep,
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
} from "../../api/generated/models";
import { ApiError, apiFetchBlob } from "../../api/apiMutator";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { formatDateTime } from "../../format";
import { DeniedState, usePrompt } from "../../ui";
import { fmtMm } from "../../format";
import { formatDate } from "../money";
import { t } from "../../i18n/es-CL";
import { useAssistantSurface } from "../assistant/assistantContext";
import { cutRoleLabel } from "./labels";
import { CutPlanView, type WorkOrderOptimization } from "./CutPlanView";
import {
  GlassSummary,
  glassSummaryCsv,
  type GlassPiece,
  type PolishingEntry,
} from "./GlassSummary";
import SignaturePad, { type SignaturePadHandle } from "./SignaturePad";
import { OperatorStepCard } from "./OperatorCard";
import { TracePieceMatches, TracePlan, TraceStock } from "./TraceView";
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
};
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
        detail?: unknown;
        short_skus?: unknown;
        unmapped_stock_skus?: unknown;
      };
    } | null;
    const detail = payload?.error?.detail;
    if (typeof detail === "string" && detail.trim()) {
      const shortList = payload?.error?.short_skus;
      const unmappedList = payload?.error?.unmapped_stock_skus;
      const skus = [
        ...(Array.isArray(shortList) ? shortList : []),
        ...(Array.isArray(unmappedList) ? unmappedList : []),
      ].filter((sku): sku is string => typeof sku === "string" && sku.length > 0);
      return skus.length ? `${detail} · ${skus.join(", ")}` : detail;
    }
  }
  return t("production.actionError");
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
  const [optColor, setOptColor] = useState("");
  const [optStrategy, setOptStrategy] = useState("auto");
  const [labels, setLabels] = useState<PackingLabel[]>([]);
  const [delivery, setDelivery] = useState<Delivery | null>(null);
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
  const [traceBusy, setTraceBusy] = useState(false);
  const [operatorStepId, setOperatorStepId] = useState<string | null>(null);
  const [pieceQuery, setPieceQuery] = useState("");
  const [pieceReport, setPieceReport] = useState<ProductionPieceTrace | null>(null);
  const [pieceBusy, setPieceBusy] = useState(false);
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

  const selectedId = params.get("order") ?? "";
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
      (!shortageOnly || order.shortage > 0) &&
      (!dispatchReadyOnly || order.dispatch_ready),
  );
  const listFiltered = statusFilter !== "" || shortageOnly || dispatchReadyOnly || blockedOnly;

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
    const [response, prepResponse] = await Promise.all([productionOrders(), productionPrep()]);
    if (response.status === 200) setOrders(response.data.orders);
    // §8: versions approved for production but not yet released surface here
    // — the workshop sees the approved work without waiting for a reminder.
    if (prepResponse.status === 200) setPrepVersions(prepResponse.data.versions);
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
        if (response.status === 200) setTrace(response.data);
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
      setDeliveryForm(null);
      setConfirmOpen(false);
      return;
    }
    setTrace(null);
    setOperatorStepId(null);
    setPieceQuery("");
    setPieceReport(null);
    void loadDetail(selectedId).catch(() => setMessage(t("production.loadError")));
    void loadTrace();
  }, [selectedId, loadDetail, loadTrace]);

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

  const lookupPiece = useCallback(async () => {
    const query = pieceQuery.trim();
    if (!query) return;
    setPieceBusy(true);
    try {
      const response = await productionPieceTrace(query);
      if (response.status === 200) setPieceReport(response.data);
    } finally {
      setPieceBusy(false);
    }
  }, [pieceQuery]);

  async function action(task: Promise<unknown>, orderId: string): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await task;
      setNote("");
      // A mutating action (optimize, ops export, step transition) changes
      // the trace — refetch it so an open operator card never shows stale
      // reservations/ops until a manual reload.
      const reloads = [loadDetail(orderId), loadOrders()];
      // A trace-read failure must not masquerade as a failed mutation —
      // the step transition or optimization already committed.
      if (trace) reloads.push(loadTrace(orderId).catch(() => undefined));
      await Promise.all(reloads);
    } catch (error) {
      if (mounted.current) setMessage(actionErrorDetail(error));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function transition(stepId: string, stepAction: StepAction, orderId: string): void {
    // BLOCK and QC_FAIL must carry a reason — the step can't be understood or
    // remediated without it. NOTE is the reason by definition.
    if (
      (stepAction === "NOTE" || stepAction === "BLOCK" || stepAction === "QC_FAIL") &&
      !note.trim()
    ) {
      setMessage(t("production.stepNoteRequired"));
      return;
    }
    const noteValue =
      stepAction === "NOTE" || stepAction === "BLOCK" || stepAction === "QC_FAIL"
        ? note || undefined
        : undefined;
    const body =
      stepAction === "QC_FAIL"
        ? { action: "COMPLETE" as const, qc_result: "FAIL" as const, note: noteValue ?? null }
        : { action: stepAction, note: noteValue ?? null };
    void action(productionStepTransition(stepId, body), orderId);
  }

  function release(versionId: string): void {
    setBusy(true);
    setMessage("");
    productionRelease(versionId)
      .then(async (response) => {
        if ((response.status === 200 || response.status === 201) && mounted.current) {
          await loadOrders();
          const first = response.data.orders[0];
          if (first) setParams({ order: first.id });
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
          setParams({ order: response.data.id });
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

  function optimize(orderId: string): void {
    if (!optColor.trim()) return;
    void action(
      productionOrderOptimize(orderId, {
        color: optColor.trim(),
        strategy: optStrategy as "fast" | "deep" | "auto",
      }),
      orderId,
    );
  }

  function exportCnc(orderId: string): void {
    void action(productionOrderCncExport(orderId), orderId);
  }

  function exportDxf(orderId: string): void {
    void action(productionOrderDxfExport(orderId), orderId);
  }

  function exportOperations(orderId: string): void {
    void action(productionOrderOpsExport(orderId), orderId);
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
    setDeliveryForm({
      scheduled_date: existing?.scheduled_date ?? "",
      time_window: (existing?.time_window as DeliveryScheduleRequestRequest["time_window"]) ?? "AM",
      address: existing?.address ?? "",
      contact_name: existing?.contact_name ?? "",
      contact_phone: existing?.contact_phone ?? "",
      installer_name: existing?.installer_name ?? "",
      notes: existing?.notes ?? "",
    });
  }

  function pack(orderId: string): void {
    void action(productionOrderPacking(orderId), orderId);
  }

  function dispatch(orderId: string): void {
    void action(productionOrderDispatch(orderId, { note: note || undefined }), orderId);
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

  async function submitConfirmation(orderId: string): Promise<void> {
    if (!confirmName.trim()) return;
    if (signatureMode === "typed") {
      sigRef.current?.renderTyped(confirmName.trim());
    }
    const dataUrl = sigRef.current?.dataURL();
    if (!dataUrl) return;
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

  async function openConfirmation(orderId: string): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("production.dispatchNoteError"));
      return;
    }
    try {
      const response = await productionOrderDeliveryConfirmation(orderId);
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
        setMessage(t("production.dteEmitError"));
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
        setMessage(t("production.envioSendError"));
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

  async function openDispatchNote(orderId: string): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("production.dispatchNoteError"));
      return;
    }
    try {
      const response = await productionOrderDispatchNote(orderId);
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

  const canAct = role === "OWNER" || role === "WORKSHOP_MANAGER" || role === "INSTALLER";
  const canWrite = role === "OWNER" || role === "WORKSHOP_MANAGER";
  const canStep = canWrite || role === "INSTALLER";
  if (!canAct) {
    return (
      <section className="production-page">
        <h1>{t("production.title")}</h1>
        <DeniedState reason={t("production.denied")} />
      </section>
    );
  }

  return (
    <section className="production-page">
      <header>
        <h1>{t("production.title")}</h1>
        <p>{t("production.subtitle")}</p>
      </header>
      {message ? <p role="alert">{message}</p> : null}
      <div className="production-layout">
        <aside className="production-orders" aria-label={t("production.orders")}>
          <h2>{t("production.orders")}</h2>
          {prepVersions.length > 0 ? (
            <section className="production-prep" aria-label={t("production.prepTitle")}>
              <h3>{t("production.prepTitle")}</h3>
              <ul>
                {prepVersions.map((version) => (
                  <li key={version.version_id}>
                    <span>
                      {version.project_code} · {version.revision_code} · {version.positions}{" "}
                      {t("production.prepPositions")}
                    </span>
                    {canWrite ? (
                      <button
                        type="button"
                        className="production-prep-release"
                        disabled={busy}
                        onClick={() => release(version.version_id)}
                      >
                        {t("production.prepRelease")}
                      </button>
                    ) : null}
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
            {["", "RELEASED", "IN_PROGRESS", "HOLD", "COMPLETED", "DISPATCHED", "INSTALLED"].map(
              (status) => (
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
              ),
            )}
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
                  onClick={() => setParams({ order: order.id })}
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
                  {order.version_shortage > order.shortage ? (
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
                </button>
              </li>
            ))}
          </ul>
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
                {detail.version_shortage > detail.shortage ? (
                  <span
                    className="production-chip is-warn"
                    title={t("production.versionShortageTitle")}
                  >
                    {t("production.versionShortageChip").replace(
                      "{count}",
                      String(detail.version_shortage - detail.shortage),
                    )}
                  </span>
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
                {canStep &&
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
                {detail.dispatch_note_code ? (
                  <button
                    type="button"
                    className={`production-dispatch production-note${
                      detail.dispatch_note_voided ? " is-voided" : ""
                    }`}
                    title={
                      detail.dispatch_note_voided ? t("production.dispatchNoteVoided") : undefined
                    }
                    onClick={() => void openDispatchNote(detail.id)}
                  >
                    {detail.dispatch_note_code}
                    {detail.dispatch_note_voided ? ` · ${t("production.dispatchNoteVoided")}` : ""}
                  </button>
                ) : null}
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
              </header>
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
                return (
                  <p className="production-remake-provenance">
                    {source ? (
                      <>
                        {t("production.remakeOf")} <strong>{source.order_code}</strong>
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
                      {optimization?.optimized_at ? (
                        <time dateTime={optimization.optimized_at}>
                          {t("production.optimizeRunAt")}:
                          {formatDateTime(optimization.optimized_at)}
                        </time>
                      ) : null}
                    </header>
                    {canOptimize &&
                    detail.status !== "COMPLETED" &&
                    detail.status !== "DISPATCHED" &&
                    detail.status !== "INSTALLED" ? (
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
                        >
                          <option value="auto">{t("production.optimizeStrategyAuto")}</option>
                          <option value="fast">{t("production.optimizeStrategyFast")}</option>
                          <option value="deep">{t("production.optimizeStrategyDeep")}</option>
                        </select>
                        <button
                          type="button"
                          disabled={busy || !optColor.trim()}
                          onClick={() => optimize(detail.id)}
                        >
                          {t("production.optimizeButton")}
                        </button>
                      </div>
                    ) : null}
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
                          {canOptimize &&
                          detail.status !== "COMPLETED" &&
                          detail.status !== "DISPATCHED" &&
                          detail.status !== "INSTALLED" ? (
                            <>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => exportCnc(detail.id)}
                              >
                                {t("production.cncExportButton")}
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => exportDxf(detail.id)}
                              >
                                {t("production.dxfExportButton")}
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => exportOperations(detail.id)}
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
                              onClick={() => downloadCnc(detail.order_code, filename, content)}
                            >
                              {filename}
                            </button>
                          ))}
                        </div>
                      );
                    })()}
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
                                  <td>{bar.yield_pct}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : null}
                        {purchases.length || sheetPurchases.length ? (
                          <p className="production-optimize-purchases">
                            {t("production.optimizePurchases")}:{" "}
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
                                      <th>{t("production.stockConsumed")}</th>
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
                                    `${metrics.remnant_bars ?? 0} remanentes`,
                                    `${metrics.process_waste_mm ?? "0"} mm desperdicio`,
                                    `${metrics.reusable_remnant_mm ?? "0"} mm reutilizable`,
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
                                  <td>{layout.yield_pct}%</td>
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
                                  `${piece.kind} ${fmtMm(piece.width_mm)}×${fmtMm(piece.height_mm)} mm ×${piece.quantity} (${piece.group})`,
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
                      detail.status !== "INSTALLED" ? (
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
                      {!delivery && canSchedule && deliveryForm === null ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => openDeliveryForm(null)}
                        >
                          {t("production.deliverySchedule")}
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
                      {canStep &&
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
                      {canStep && delivery?.status === "ON_ROUTE" && !delivery.confirmation ? (
                        <button
                          type="button"
                          className="production-chip-danger"
                          disabled={busy}
                          onClick={() => void transitionDelivery(detail.id, "FAILED")}
                        >
                          {t("production.deliveryFailed")}
                        </button>
                      ) : null}
                      {canStep &&
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
                          onClick={() => void openConfirmation(detail.id)}
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
                            {delivery.scheduled_date} · {delivery.time_window}
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
                    {confirmOpen && canStep && delivery ? (
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
                            <option value="AM">AM</option>
                            <option value="PM">PM</option>
                            <option value="JORNADA">JORNADA</option>
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
                if (
                  !nextStep ||
                  detail.status === "COMPLETED" ||
                  detail.status === "DISPATCHED" ||
                  detail.status === "INSTALLED"
                )
                  return null;
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
                    <span className="production-step-actions">
                      {stepActions(nextStep).map((stepAction) => (
                        <button
                          key={stepAction}
                          type="button"
                          disabled={busy}
                          onClick={() => transition(nextStep.id, stepAction, detail.id)}
                        >
                          {t(actionLabel[stepAction])}
                        </button>
                      ))}
                    </span>
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
                              {t(stepStatusKey[step.status] ?? "production.stepReady")}
                            </span>
                          </div>
                          {step.note ? <p className="production-step-note">{step.note}</p> : null}
                          {detail.status !== "COMPLETED" &&
                          detail.status !== "DISPATCHED" &&
                          detail.status !== "INSTALLED" ? (
                            <div className="production-step-actions">
                              {stepActions(step)
                                // START only exists on the earliest open step —
                                // the backend sequence gate rejects every other
                                // one with a guaranteed 422.
                                .filter(
                                  (stepAction) =>
                                    stepAction !== "START" || step.id === nextStep?.id,
                                )
                                .map((stepAction) => (
                                  <button
                                    key={stepAction}
                                    type="button"
                                    disabled={busy}
                                    onClick={() => transition(step.id, stepAction, detail.id)}
                                  >
                                    {t(actionLabel[stepAction])}
                                  </button>
                                ))}
                            </div>
                          ) : null}
                        </li>
                      ))}
                    </ol>
                    {operatorStep ? (
                      <OperatorStepCard step={operatorStep} trace={trace} traceBusy={traceBusy} />
                    ) : null}
                  </>
                );
              })()}
              <label className="production-note">
                {t("production.noteLabel")}
                <input
                  type="text"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder={t("production.notePlaceholder")}
                />
              </label>
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
                <div className="production-trace-lookup">
                  <label>
                    {t("production.tracePieceLabel")}
                    <input
                      type="text"
                      value={pieceQuery}
                      onChange={(event) => setPieceQuery(event.target.value)}
                      placeholder={t("production.tracePiecePlaceholder")}
                    />
                  </label>
                  <button
                    type="button"
                    disabled={pieceBusy || !pieceQuery.trim()}
                    onClick={() => void lookupPiece()}
                  >
                    {t("production.tracePieceLookup")}
                  </button>
                </div>
                {pieceReport ? <TracePieceMatches report={pieceReport} /> : null}
              </section>
              <section className="production-events" aria-label={t("production.events")}>
                <h3>{t("production.events")}</h3>
                <ol>
                  {detail.events.map((event) => {
                    const eventNote = (event.payload as { note?: unknown } | undefined)?.note;
                    return (
                      <li key={event.id}>
                        <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                        <span>{t(eventKey[event.event] ?? "production.eventNote")}</span>
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
