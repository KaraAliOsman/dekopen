/** P12 — modelo del tablero del jefe de producción.
 *
 * Datos reales, cero capacidad inventada: cada tarjeta muestra lo que el
 * listado de OTs trae (código, obra, unidades, compromiso real, avance,
 * faltantes, plan) y en qué columna cae según la cola de estaciones. */

import type { ProductionOrder } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { PLAN_REQUIRED_CODES } from "./labels";
import type { StationQueueGroup } from "./queue";
import { stationByOrder } from "./queue";

/** Etiqueta y tono por estado de OT — la ficha y la tarjeta del tablero
 * comparten el mismo mapa para no duplicar (ni inventar) estados. */
export const ORDER_STATUS_KEY: Record<string, Parameters<typeof t>[0]> = {
  RELEASED: "production.orderReleased",
  IN_PROGRESS: "production.orderInProgress",
  HOLD: "production.orderHold",
  COMPLETED: "production.orderCompleted",
  DISPATCHED: "production.orderDispatched",
  INSTALLED: "production.orderInstalled",
  CANCELLED: "production.orderCancelled",
};

export const ORDER_STATUS_TONE: Record<string, string> = {
  RELEASED: "neutral",
  IN_PROGRESS: "info",
  HOLD: "warn",
  COMPLETED: "ok",
  DISPATCHED: "info",
  INSTALLED: "ok",
  CANCELLED: "neutral",
};

/** Columna de salida: OTs sin paso abierto (terminadas, despachadas,
 * anuladas) — existen, pero no estacionan en la planta. */
export const OUTBOUND_COLUMN = "OUTBOUND";

export type BoardChip =
  "shortage" | "blocked" | "qc" | "unplanned" | "stale_plan" | "remake" | "dispatch";

const TERMINAL = new Set(["COMPLETED", "DISPATCHED", "INSTALLED", "CANCELLED"]);

export function orderChips(order: ProductionOrder): BoardChip[] {
  const chips: BoardChip[] = [];
  if (order.shortage > 0) chips.push("shortage");
  if (order.qc_blocked) chips.push("qc");
  else if ((order.steps_blocked ?? 0) > 0) chips.push("blocked");
  if (order.remake_reason) chips.push("remake");
  if (order.dispatch_ready) chips.push("dispatch");
  if (TERMINAL.has(order.status)) return chips;
  if (order.plan_state === "invalidated") chips.push("stale_plan");
  else if (
    order.plan_state === "none" &&
    order.next_step?.code &&
    PLAN_REQUIRED_CODES.has(order.next_step.code)
  ) {
    chips.push("unplanned");
  }
  return chips;
}

export type CommitmentBucket = "overdue" | "week" | "later" | "none";

function todayISO(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/Santiago" });
}

export function commitmentBucket(committed: string | null | undefined): CommitmentBucket {
  if (!committed) return "none";
  const today = todayISO();
  if (committed < today) return "overdue";
  const week = new Date(`${today}T00:00:00`);
  week.setDate(week.getDate() + 7);
  const weekISO = week.toLocaleDateString("en-CA", { timeZone: "America/Santiago" });
  return committed <= weekISO ? "week" : "later";
}

/** Orden del tablero: compromiso más próximo primero; sin fecha al final. */
export function boardOrderSort(a: ProductionOrder, b: ProductionOrder): number {
  const ca = a.committed_date ?? "9999-12-31";
  const cb = b.committed_date ?? "9999-12-31";
  if (ca !== cb) return ca < cb ? -1 : 1;
  return a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0;
}

/** Columna de la tarjeta: la estación del primer paso abierto según la cola;
 * sin cola, cae por su `next_step`; sin paso abierto, a salida. */
export function orderStation(order: ProductionOrder, queueMap: Map<string, string>): string {
  const queued = queueMap.get(order.id);
  if (queued) return queued;
  if (!TERMINAL.has(order.status) && order.next_step?.code) {
    return String(order.next_step.code);
  }
  return OUTBOUND_COLUMN;
}

export type BoardFilters = {
  /** Texto libre (código de OT, obra, cliente). */
  q: string;
  /** Código de obra exacto, o vacío. */
  project: string;
  commitment: "" | CommitmentBucket;
  issue: "" | BoardChip;
};

export const EMPTY_BOARD_FILTERS: BoardFilters = {
  q: "",
  project: "",
  commitment: "",
  issue: "",
};

function chipIncluded(order: ProductionOrder, issue: BoardChip): boolean {
  // El deep-link «en espera» del dashboard (?blocked=1) cuenta la OT
  // detenida: status HOLD o pasos bloqueados — incluido el rechazo de
  // calidad, que se detiene igual aunque muestre su propio chip.
  if (issue === "blocked") {
    return (
      order.status === "HOLD" ||
      orderChips(order).includes("blocked") ||
      orderChips(order).includes("qc")
    );
  }
  return orderChips(order).includes(issue);
}

export function boardMatches(order: ProductionOrder, filters: BoardFilters): boolean {
  if (filters.project && order.project_code !== filters.project) return false;
  if (filters.commitment && commitmentBucket(order.committed_date) !== filters.commitment) {
    return false;
  }
  if (filters.issue && !chipIncluded(order, filters.issue)) return false;
  if (filters.q) {
    const hay = [order.order_code, order.project_code, order.project_name, order.client_name]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (!hay.includes(filters.q.trim().toLowerCase())) return false;
  }
  return true;
}

/** Columnas del tablero en orden de ruta: solo estaciones que la cola
 * reporta (ruta configurada real), más la columna de salida al final. El
 * puesto de cada estación en el recorrido se infiere de la `sequence` de
 * sus pasos — la cola viene ordenada por OT, no por ruta. */
export function boardColumns(
  queue: StationQueueGroup[],
  orders: ProductionOrder[],
): { code: string; orders: ProductionOrder[] }[] {
  const queueMap = stationByOrder(queue);
  // Posición de ruta por estación: la sequence más temprana en que aparece.
  const routeSlot = new Map<string, number>();
  for (const group of queue) {
    for (const entry of group.entries ?? []) {
      const sequence = Number(entry.sequence) || 0;
      const code = String(group.code);
      const slot = routeSlot.get(code);
      if (slot === undefined || sequence < slot) routeSlot.set(code, sequence);
    }
  }
  const columns = new Map<string, ProductionOrder[]>();
  for (const group of queue) {
    if (group.code) columns.set(String(group.code), []);
  }
  for (const order of orders) {
    const station = orderStation(order, queueMap);
    if (!columns.has(station)) columns.set(station, []);
    columns.get(station)!.push(order);
  }
  const result = [...columns.entries()]
    .map(([code, list]) => ({ code, orders: list.sort(boardOrderSort) }))
    .sort(
      (a, b) =>
        (routeSlot.get(a.code) ?? Number.MAX_SAFE_INTEGER) -
          (routeSlot.get(b.code) ?? Number.MAX_SAFE_INTEGER) || a.code.localeCompare(b.code),
    );
  // Salida siempre al final del recorrido.
  const outboundIndex = result.findIndex((column) => column.code === OUTBOUND_COLUMN);
  if (outboundIndex >= 0) {
    const [outbound] = result.splice(outboundIndex, 1);
    if (outbound) result.push(outbound);
  }
  return result;
}
