import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import {
  fieldCrewsSave,
  fieldDispatchPlan,
  fieldDispatchSchedule,
} from "../../api/generated/dekopen";
import type { DispatchPlan, DispatchScheduleRequest, FieldCrew } from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { formatDate } from "../../format";
import { t, tDynamic } from "../../i18n/es-CL";
import {
  DeniedState,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusChip,
  Tabs,
} from "../../ui";
import type { TabItem } from "../../ui";

import "./field.css";

const BOARD_ROLES = ["OWNER", "WORKSHOP_MANAGER"];
const STOP_TONE: Record<string, string> = {
  SCHEDULED: "info",
  ON_ROUTE: "info",
  DELIVERED: "ok",
  FAILED: "danger",
};

type CrewSlot = { crew_id: string | null; stops: DispatchPlanStop[] };
type DispatchPlanStop = {
  delivery_id: string;
  order_id: string;
  order_code: string;
  project_code: string;
  client_name: string;
  address: string;
  time_window: string;
  status: string;
  route_order: number | null;
  load_checked: boolean;
  note_issued: boolean;
};

/** Tablero de despacho: columnas por día, carriles por cuadrilla/vehículo,
 * y la OT lista para despachar (producción COMPLETED con packing). El
 * jefe asigna fecha, jornada, cuadrilla, orden de ruta y vuelve a abrir
 * la guía cuando haga falta. */
export function FieldDispatchPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const allowed = org != null && BOARD_ROLES.includes(org.role);
  const queryClient = useQueryClient();
  const [days, setDays] = useState(5);
  const [scheduling, setScheduling] = useState<{
    order_id: string;
    order_code: string;
    address: string;
  } | null>(null);
  const [crewForm, setCrewForm] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const plan = useQuery<DispatchPlan>({
    queryKey: ["dispatch-plan", org?.id, days],
    enabled: allowed,
    queryFn: async ({ signal }) => {
      const response = await fieldDispatchPlan(
        { days },
        { signal, headers: { "X-Organization-ID": org!.id } },
      );
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
  });

  if (!allowed) {
    return <DeniedState reason={t("field.dispatchDenied")} />;
  }

  const data = plan.data;
  const crews = data?.crews ?? [];
  const ready = data?.ready ?? [];
  const dayColumns = data?.days ?? [];

  const tabs: TabItem[] = [
    { id: "5", label: t("field.days5") },
    { id: "7", label: t("field.days7") },
    { id: "14", label: t("field.days14") },
  ];

  return (
    <section aria-labelledby="page-title" className="field-root field-root--wide">
      <PageHeader
        context={t("field.dispatchSubtitle")}
        headingId="page-title"
        title={t("field.dispatchTitle")}
      />
      <Tabs
        items={tabs}
        label={t("field.horizon")}
        onChange={(id) => setDays(Number(id))}
        value={String(days)}
      />

      {message ? <p className="field-message field-message--ok">{message}</p> : null}

      {plan.isPending ? (
        <LoadingState shape="table" />
      ) : plan.isError ? (
        <ErrorState title={t("field.loadError")} onRetry={() => void plan.refetch()} />
      ) : (
        <>
          <section className="field-card">
            <div className="field-stop__top">
              <h2>{t("field.readyTitle")}</h2>
              <button
                className="field-button field-button--ghost"
                onClick={() => setCrewForm(true)}
                type="button"
              >
                {t("field.crewNew")}
              </button>
            </div>
            {crewForm ? (
              <CrewForm
                onDone={() => {
                  setCrewForm(false);
                  void queryClient.invalidateQueries({ queryKey: ["dispatch-plan"] });
                }}
                orgId={org!.id}
              />
            ) : null}
            {ready.length === 0 ? (
              <EmptyState title={t("field.readyEmpty")} illustration="bench" />
            ) : (
              ready.map((order) => (
                <div className="dispatch-ready__item" key={order.order_id}>
                  <span>
                    <span className="dispatch-stop__order">{order.order_code}</span> ·{" "}
                    {order.client_name} · {order.delivery_address ?? "—"} ·{" "}
                    {t("field.readyUnits").replace("{count}", String(order.units))}
                  </span>
                  <button
                    className="field-button"
                    onClick={() =>
                      setScheduling({
                        order_id: order.order_id,
                        order_code: order.order_code,
                        address: order.delivery_address ?? "",
                      })
                    }
                    type="button"
                  >
                    {t("field.schedule")}
                  </button>
                </div>
              ))
            )}
          </section>

          <div className="dispatch-grid">
            {dayColumns.map((column) => (
              <div
                className={`dispatch-day${column.today ? " dispatch-day--today" : ""}`}
                key={column.date}
              >
                <p className="dispatch-day__head">
                  {column.weekday} {formatDate(column.date)}
                </p>
                {crews.length === 0 && (column.crews as CrewSlot[]).length === 0 ? (
                  <p className="field-visit">{t("field.noCrews")}</p>
                ) : null}
                {crews.map((crew) => {
                  const slot = (column.crews as CrewSlot[]).find(
                    (entry) => entry.crew_id === crew.id,
                  );
                  return (
                    <div className="dispatch-lane" key={crew.id}>
                      <p className="dispatch-lane__crew">{crew.name}</p>
                      {(slot?.stops ?? []).map((stop) => {
                        const status = stop.status;
                        return (
                          <Link
                            className="dispatch-stop"
                            key={stop.delivery_id}
                            to={`/field/orders/${stop.order_id}`}
                          >
                            <span className="dispatch-stop__order">
                              {stop.route_order ? `${stop.route_order} · ` : ""}
                              {stop.order_code}
                            </span>{" "}
                            <StatusChip
                              label={tDynamic("deliveries.status", status)}
                              tone={STOP_TONE[status] ?? "neutral"}
                              value={status}
                            />
                            <br />
                            <span className="dispatch-stop__address">{stop.address}</span>
                            {stop.load_checked ? (
                              <StatusChip label={t("field.loadChecked")} tone="ok" value="load" />
                            ) : null}
                          </Link>
                        );
                      })}
                    </div>
                  );
                })}
                {(column.crews as CrewSlot[])
                  .filter((entry) => entry.crew_id === null)
                  .map((entry) => (
                    <div className="dispatch-lane" key="unassigned">
                      <p className="dispatch-lane__crew">{t("field.unassigned")}</p>
                      {entry.stops.map((stop) => (
                        <Link
                          className="dispatch-stop"
                          key={stop.delivery_id}
                          to={`/field/orders/${stop.order_id}`}
                        >
                          <span className="dispatch-stop__order">{stop.order_code}</span>
                          <br />
                          <span className="dispatch-stop__address">{stop.address}</span>
                        </Link>
                      ))}
                    </div>
                  ))}
              </div>
            ))}
          </div>
        </>
      )}

      {scheduling ? (
        <SchedulePanel
          crews={crews}
          onClose={(saved) => {
            setScheduling(null);
            if (saved) {
              setMessage(t("field.scheduled"));
              void queryClient.invalidateQueries({ queryKey: ["dispatch-plan"] });
            }
          }}
          orgId={org!.id}
          order={scheduling}
        />
      ) : null}
    </section>
  );
}

function CrewForm({ orgId, onDone }: { orgId: string; onDone: () => void }): JSX.Element {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<FieldCrew["kind"]>("VEHICLE");
  const [plate, setPlate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const submit = () => {
    if (!name.trim()) return;
    setBusy(true);
    void fieldCrewsSave(
      {
        name: name.trim(),
        kind,
        plate: plate.trim() || undefined,
      },
      { headers: { "X-Organization-ID": orgId } },
    )
      .then((response) => {
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        onDone();
      })
      .catch(() => setError(true))
      .finally(() => setBusy(false));
  };

  return (
    <div className="field-card">
      <div className="field-grid" style={{ gridTemplateColumns: "2fr 1fr 1fr" }}>
        <label className="field-field">
          <span>{t("field.crewName")}</span>
          <input onChange={(event) => setName(event.target.value)} value={name} />
        </label>
        <label className="field-field">
          <span>{t("field.crewKind")}</span>
          <select
            onChange={(event) => setKind(event.target.value as FieldCrew["kind"])}
            value={kind}
          >
            <option value="VEHICLE">{t("field.crewVehicle")}</option>
            <option value="TEAM">{t("field.crewTeam")}</option>
          </select>
        </label>
        <label className="field-field">
          <span>{t("field.crewPlate")}</span>
          <input onChange={(event) => setPlate(event.target.value)} value={plate} />
        </label>
      </div>
      {error ? <p className="field-message field-message--error">{t("field.saveFailed")}</p> : null}
      <div className="field-actions">
        <button className="field-button" disabled={busy} onClick={submit} type="button">
          {t("field.crewSave")}
        </button>
        <button className="field-button field-button--ghost" onClick={onDone} type="button">
          {t("field.cancel")}
        </button>
      </div>
    </div>
  );
}

function SchedulePanel({
  order,
  orgId,
  crews,
  onClose,
}: {
  order: { order_id: string; order_code: string; address: string };
  orgId: string;
  crews: FieldCrew[];
  onClose: (saved: boolean) => void;
}): JSX.Element {
  const [date, setDate] = useState("");
  const [window_, setWindow] = useState<DispatchScheduleRequest["time_window"]>("AM");
  const [address, setAddress] = useState(order.address);
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [crewId, setCrewId] = useState("");
  const [routeOrder, setRouteOrder] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const submit = () => {
    if (!date || !address.trim()) return;
    setBusy(true);
    void fieldDispatchSchedule(
      {
        order_id: order.order_id,
        scheduled_date: date,
        time_window: window_,
        address: address.trim(),
        contact_name: contactName.trim() || undefined,
        contact_phone: contactPhone.trim() || undefined,
        crew_id: crewId || null,
        route_order: routeOrder ? Number(routeOrder) : null,
      },
      { headers: { "X-Organization-ID": orgId } },
    )
      .then((response) => {
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        onClose(true);
      })
      .catch(() => setError(true))
      .finally(() => setBusy(false));
  };

  return (
    <div className="field-card" role="dialog">
      <h2>
        {t("field.scheduleTitle")} {order.order_code}
      </h2>
      <div className="field-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <label className="field-field">
          <span>{t("field.date")}</span>
          <input onChange={(event) => setDate(event.target.value)} type="date" value={date} />
        </label>
        <label className="field-field">
          <span>{t("field.timeWindow")}</span>
          <select
            onChange={(event) =>
              setWindow(event.target.value as DispatchScheduleRequest["time_window"])
            }
            value={window_}
          >
            <option value="AM">AM</option>
            <option value="PM">PM</option>
            <option value="JORNADA">{t("field.fullDay")}</option>
          </select>
        </label>
      </div>
      <label className="field-field field-section-gap">
        <span>{t("field.address")}</span>
        <input onChange={(event) => setAddress(event.target.value)} value={address} />
      </label>
      <div className="field-grid field-section-gap" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <label className="field-field">
          <span>{t("field.contactName")}</span>
          <input onChange={(event) => setContactName(event.target.value)} value={contactName} />
        </label>
        <label className="field-field">
          <span>{t("field.contactPhone")}</span>
          <input onChange={(event) => setContactPhone(event.target.value)} value={contactPhone} />
        </label>
      </div>
      <div className="field-grid field-section-gap" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <label className="field-field">
          <span>{t("field.crew")}</span>
          <select onChange={(event) => setCrewId(event.target.value)} value={crewId}>
            <option value="">{t("field.unassigned")}</option>
            {crews.map((crew) => (
              <option key={crew.id} value={crew.id}>
                {crew.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field-field">
          <span>{t("field.routeOrder")}</span>
          <input
            inputMode="numeric"
            onChange={(event) => setRouteOrder(event.target.value)}
            value={routeOrder}
          />
        </label>
      </div>
      {error ? <p className="field-message field-message--error">{t("field.saveFailed")}</p> : null}
      <div className="field-actions">
        <button
          className="field-button"
          disabled={busy || !date || !address.trim()}
          onClick={submit}
          type="button"
        >
          {busy ? t("field.saving") : t("field.scheduleSave")}
        </button>
        <button
          className="field-button field-button--ghost"
          onClick={() => onClose(false)}
          type="button"
        >
          {t("field.cancel")}
        </button>
      </div>
    </div>
  );
}
