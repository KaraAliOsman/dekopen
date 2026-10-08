/** P12 — trazabilidad humana de la OT: una línea por hecho, en lenguaje de
 * taller — «14:32 · Juan Pérez · Corte de perfiles completada (24 piezas)».
 * El log técnico (payloads, ids) vive detrás de «Detalles técnicos». */

import { useMemo, useState } from "react";

import type { ProductionStep, ProductionStepEvent } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { formatDateTime } from "../../format";
import { TechDetails } from "../../ui";
import { stationCodeLabel } from "./labels";

/** Evento → tono. Naranja es «requiere persona»: bloqueos, rechazos y
 * esperas que alguien debe resolver. */
const ATTENTION_EVENTS = new Set(["STEP_BLOCKED", "WO_HOLD", "QC_FAILED", "WO_DELIVERY_FAILED"]);

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

type TraceGroup = "steps" | "material" | "quality" | "delivery" | "system";

const GROUP_OF: Record<string, TraceGroup> = {
  WO_RELEASED: "steps",
  STEP_STARTED: "steps",
  STEP_COMPLETED: "steps",
  STEP_BLOCKED: "steps",
  STEP_UNBLOCKED: "steps",
  NOTE: "steps",
  WO_COMPLETED: "steps",
  WO_HOLD: "steps",
  WO_CANCELLED: "steps",
  QC_FAILED: "quality",
  QC_CHECK: "quality",
  WO_REMADE: "quality",
  WO_MATERIAL_RECHECK: "material",
  WO_STOCK_CONSUMED: "material",
  WO_REMNANTS_SETTLED: "material",
  WO_PACKED: "delivery",
  WO_DISPATCHED: "delivery",
  WO_DISPATCH_VOIDED: "delivery",
  WO_INSTALLED: "delivery",
  WO_DELIVERY_SCHEDULED: "delivery",
  WO_DELIVERY_ON_ROUTE: "delivery",
  WO_DELIVERY_DELIVERED: "delivery",
  WO_DELIVERY_CONFIRMED: "delivery",
  WO_DELIVERY_FAILED: "delivery",
  WO_OPTIMIZED: "system",
  WO_CNC_EXPORTED: "system",
  WO_DXF_EXPORTED: "system",
  WO_OPS_EXPORTED: "system",
  WO_CNC_PROGRAM: "system",
};

export function eventGroup(event: string): TraceGroup {
  return GROUP_OF[event] ?? "system";
}

function hhmm(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString("es-CL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Santiago",
  });
}

function dayKey(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", { timeZone: "America/Santiago" });
}

function humanText(event: ProductionStepEvent): string {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const station = event.step_code ? stationCodeLabel(String(event.step_code)) : "";
  const label = t(eventKey[event.event] ?? "production.eventFallback");
  const base = station ? `${station} — ${label}` : label;
  const count = Array.isArray(payload.ops_executed) ? payload.ops_executed.length : null;
  const suffix = count != null && count > 0 ? ` (${count} ${t("production.piecesUnit")})` : "";
  const note =
    typeof payload.note === "string" && payload.note.trim() ? ` — ${payload.note.trim()}` : "";
  const item =
    typeof payload.qc_item === "string" && payload.qc_item.trim()
      ? ` [${payload.qc_item.trim()}]`
      : "";
  return `${base}${item}${suffix}${note}`;
}

export function HumanTrace({
  events,
  steps,
}: {
  events: ProductionStepEvent[];
  steps: ProductionStep[];
}): JSX.Element {
  const [stationFilter, setStationFilter] = useState("");
  const [groupFilter, setGroupFilter] = useState("" as "" | TraceGroup);
  const [peopleOnly, setPeopleOnly] = useState(false);

  const stations = useMemo(
    () => [...new Set(steps.map((step) => String(step.code ?? "")).filter(Boolean))],
    [steps],
  );

  const filtered = useMemo(
    () =>
      events.filter((event) => {
        if (stationFilter && String(event.step_code ?? "") !== stationFilter) return false;
        if (groupFilter && eventGroup(event.event) !== groupFilter) return false;
        if (peopleOnly && !event.actor_label) return false;
        return true;
      }),
    [events, stationFilter, groupFilter, peopleOnly],
  );

  // Más reciente primero, agrupado por día calendario de la planta.
  const byDay = useMemo(() => {
    const map = new Map<string, ProductionStepEvent[]>();
    for (const event of [...filtered].reverse()) {
      const key = dayKey(event.created_at);
      let list = map.get(key);
      if (!list) {
        list = [];
        map.set(key, list);
      }
      list.push(event);
    }
    return [...map.entries()];
  }, [filtered]);

  return (
    <section aria-label={t("production.traceHumanTitle")} className="human-trace">
      <div className="human-trace__filters">
        <select
          aria-label={t("production.traceFilterStation")}
          onChange={(event) => setStationFilter(event.target.value)}
          value={stationFilter}
        >
          <option value="">{t("production.traceAllStations")}</option>
          {stations.map((code) => (
            <option key={code} value={code}>
              {stationCodeLabel(code)}
            </option>
          ))}
        </select>
        <select
          aria-label={t("production.traceFilterKind")}
          onChange={(event) => setGroupFilter(event.target.value as "" | TraceGroup)}
          value={groupFilter}
        >
          <option value="">{t("production.traceAllKinds")}</option>
          <option value="steps">{t("production.traceGroupSteps")}</option>
          <option value="quality">{t("production.traceGroupQuality")}</option>
          <option value="material">{t("production.traceGroupMaterial")}</option>
          <option value="delivery">{t("production.traceGroupDelivery")}</option>
          <option value="system">{t("production.traceGroupSystem")}</option>
        </select>
        <label className="human-trace__people">
          <input
            checked={peopleOnly}
            onChange={(event) => setPeopleOnly(event.target.checked)}
            type="checkbox"
          />
          {t("production.tracePeopleOnly")}
        </label>
      </div>
      {byDay.length ? (
        byDay.map(([day, list]) => (
          <div className="human-trace__day" key={day}>
            <h4 className="human-trace__date">{day}</h4>
            <ol className="human-trace__list">
              {list.map((event) => (
                <li
                  className={`human-trace__row${ATTENTION_EVENTS.has(event.event) ? " is-attention" : ""}`}
                  key={event.id}
                >
                  <time dateTime={event.created_at}>{hhmm(event.created_at)}</time>
                  <span className="human-trace__actor">
                    {event.actor_label ?? t("production.traceSystem")}
                  </span>
                  <span className="human-trace__text">{humanText(event)}</span>
                </li>
              ))}
            </ol>
          </div>
        ))
      ) : (
        <p className="production-trace-empty">{t("production.traceEmpty")}</p>
      )}
      <TechDetails summary={t("production.traceTechDetails")}>
        <table className="production-plan">
          <thead>
            <tr>
              <th>{t("production.traceTechTime")}</th>
              <th>{t("production.traceTechEvent")}</th>
              <th>{t("production.traceTechActor")}</th>
              <th>{t("production.traceTechPayload")}</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={`raw-${event.id}`}>
                <td>{formatDateTime(event.created_at)}</td>
                <td className="mono">{event.event}</td>
                <td className="mono">{event.actor_id ?? "—"}</td>
                <td className="mono">{JSON.stringify(event.payload ?? {})}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TechDetails>
    </section>
  );
}
