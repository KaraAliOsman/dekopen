import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { fieldAgenda } from "../../api/generated/dekopen";
import type { FieldAgenda } from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";

import { t, tDynamic } from "../../i18n/es-CL";
import { DeniedState, EmptyState, ErrorState, LoadingState, StatusChip } from "../../ui";

import "./field.css";
import { outboxFlush, outboxList } from "./outbox";

const FIELD_ROLES = ["OWNER", "WORKSHOP_MANAGER", "INSTALLER"];

/** Agenda del día en obra: paradas asignadas (o todas, para el jefe),
 * progreso del checklist por posición e incidencias abiertas — cada
 * gesto del celular abre la posición, no un formulario. */
export function FieldAgendaPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const allowed = org != null && FIELD_ROLES.includes(org.role);
  const [params, setParams] = useSearchParams();
  const day = params.get("day") ?? "";
  const [pending, setPending] = useState(0);
  const [online, setOnline] = useState(navigator.onLine);

  useEffect(() => {
    if (!org) return;
    const refresh = () => setPending(outboxList(org.id).length);
    const flush = async () => {
      const result = await outboxFlush(org.id);
      setOnline(result.online);
      setPending(result.remaining);
    };
    refresh();
    const onOnline = () => void flush();
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    void flush();
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [org]);

  const query = useQuery<FieldAgenda>({
    queryKey: ["field-agenda", org?.id, day || "today"],
    enabled: allowed,
    queryFn: async ({ signal }) => {
      const response = await fieldAgenda(day ? { day } : undefined, {
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
  });

  if (!allowed) {
    return <DeniedState reason={t("field.denied")} />;
  }

  const agenda = query.data;
  const stops = agenda?.items ?? [];
  const visits = (agenda?.service_visits ?? []) as {
    ticket_id: string;
    code: string;
    scheduled_visit_at: string;
    project_code: string;
    client_name: string | null;
    address: string | null;
    crew_name: string | null;
  }[];

  return (
    <div className="field-root" data-density="workshop" data-theme-scope="dark">
      <header className="field-header">
        <h1>{t("field.agendaTitle")}</h1>
        <label className="field-day">
          <span>{t("field.day")}</span>
          <input
            onChange={(event) => {
              const next = new URLSearchParams(params);
              if (event.target.value) {
                next.set("day", event.target.value);
              } else {
                next.delete("day");
              }
              setParams(next);
            }}
            type="date"
            value={day || agenda?.date || ""}
          />
        </label>
      </header>

      {pending > 0 || !online ? (
        <div className={`field-outbox${!online ? " field-outbox--offline" : ""}`} role="status">
          <span>
            {!online
              ? t("field.offline")
              : t("field.outboxPending").replace("{count}", String(pending))}
          </span>
        </div>
      ) : null}

      {query.isPending ? (
        <LoadingState shape="lines" />
      ) : query.isError ? (
        <ErrorState title={t("field.loadError")} onRetry={() => void query.refetch()} />
      ) : stops.length === 0 && visits.length === 0 ? (
        <EmptyState title={t("field.agendaEmpty")} illustration="order" />
      ) : (
        <>
          {stops.map((stop) => (
            <div className="field-stop-wrap" key={stop.delivery_id}>
              <Link
                className={`field-stop${stop.confirmed ? " field-stop--done" : ""}`}
                to={`/field/orders/${stop.order_id}?delivery=${stop.delivery_id}`}
              >
                <span className="field-stop__top">
                  <span className="field-stop__order">{stop.order_code}</span>
                  <StatusChip
                    label={tDynamic("deliveries.window", stop.time_window)}
                    tone="info"
                    value={stop.time_window}
                  />
                </span>
                <span className="field-stop__project">
                  {stop.project_code} · {stop.client_name}
                  {stop.location_tag ? ` · ${stop.location_tag}` : ""}
                </span>
                <span className="field-stop__meta">
                  <span className="field-stop__progress">
                    {t("field.checklistProgress")
                      .replace("{done}", String(stop.checklists_done))
                      .replace("{total}", String(stop.checks_total))}
                  </span>
                  {stop.open_incidents > 0 ? (
                    <StatusChip
                      label={t("field.incidentsOpen").replace(
                        "{count}",
                        String(stop.open_incidents),
                      )}
                      tone="danger"
                      value="incidents"
                    />
                  ) : null}
                  {stop.confirmed ? (
                    <StatusChip label={t("field.received")} tone="ok" value="done" />
                  ) : null}
                </span>
              </Link>
              <div className="field-stop__foot">
                <span className="field-stop__address">{stop.address ?? "—"}</span>
                {stop.address ? (
                  <a
                    className="field-stop__maps"
                    href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(stop.address)}`}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {t("field.howToGet")}
                  </a>
                ) : null}
              </div>
            </div>
          ))}
          {visits.length > 0 ? (
            <section className="field-card field-section-gap">
              <h2>{t("field.serviceVisits")}</h2>
              {visits.map((visit) => (
                <div className="field-visit-row" key={visit.ticket_id}>
                  <p className="field-visit">
                    <code>{visit.code}</code> · {visit.project_code} · {visit.client_name ?? "—"} ·{" "}
                    {visit.address ?? "—"}
                  </p>
                  {visit.address ? (
                    <a
                      className="field-stop__maps"
                      href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(visit.address)}`}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {t("field.howToGet")}
                    </a>
                  ) : null}
                </div>
              ))}
            </section>
          ) : null}
        </>
      )}
      {agenda?.mine_only ? (
        <p className="field-visit" aria-live="polite">
          {t("field.mineOnly")}
        </p>
      ) : null}
    </div>
  );
}
