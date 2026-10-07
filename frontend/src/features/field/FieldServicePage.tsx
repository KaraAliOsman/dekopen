import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { serviceTicketTransition, serviceTicketsList } from "../../api/generated/dekopen";
import type { ServiceTicket } from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { formatDate } from "../../format";
import { t, tDynamic, type TranslationKey } from "../../i18n/es-CL";
import {
  DeniedState,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusChip,
} from "../../ui";

import "./field.css";

const BOARD_ROLES = ["OWNER", "WORKSHOP_MANAGER", "ESTIMATOR"];
const WRITE_ROLES = ["OWNER", "WORKSHOP_MANAGER", "ESTIMATOR"];
const NEXT_ACTIONS: Record<string, { next: string; label: string }[]> = {
  OPEN: [
    { next: "SCHEDULED", label: "field.ticketSchedule" },
    { next: "IN_PROGRESS", label: "field.ticketStart" },
  ],
  SCHEDULED: [{ next: "IN_PROGRESS", label: "field.ticketStart" }],
  IN_PROGRESS: [{ next: "CLOSED", label: "field.ticketClose" }],
};

/** Postventa: cada PV- lleva la garantía sellada en la revisión, la obra,
 * la posición y la pieza — la visita se agenda, se ejecuta y se cierra
 * con nota. El plazo nunca se inventa: viene del sello documental. */
export function FieldServicePage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const role = org?.role ?? "";
  const allowed = org != null && BOARD_ROLES.includes(role);
  const canWrite = WRITE_ROLES.includes(role);
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [closing, setClosing] = useState<ServiceTicket | null>(null);
  const [scheduling, setScheduling] = useState<ServiceTicket | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const query = useQuery<ServiceTicket[]>({
    queryKey: ["field-tickets", org?.id, status],
    enabled: allowed,
    queryFn: async ({ signal }) => {
      const response = await serviceTicketsList(status ? { status } : undefined, {
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data.tickets;
    },
  });

  if (!allowed) {
    return <DeniedState reason={t("field.serviceDenied")} />;
  }

  const transition = (ticket: ServiceTicket, next: string) => {
    void serviceTicketTransition(ticket.id, { status: next } as never, {
      headers: { "X-Organization-ID": org!.id },
    })
      .then((response) => {
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        setMessage(t("field.ticketUpdated").replace("{code}", ticket.code));
        void queryClient.invalidateQueries({ queryKey: ["field-tickets"] });
      })
      .catch(() => setMessage(t("field.saveFailed")));
  };

  const tickets = query.data ?? [];

  return (
    <section aria-labelledby="page-title" className="field-root field-root--wide">
      <PageHeader
        context={t("field.serviceSubtitle")}
        headingId="page-title"
        title={t("field.serviceTitle")}
      />
      <div className="field-chip-row">
        {["", "OPEN", "SCHEDULED", "IN_PROGRESS", "CLOSED"].map((option) => (
          <button
            aria-pressed={status === option}
            className="field-button field-button--ghost"
            key={option || "all"}
            onClick={() => setStatus(option)}
            type="button"
          >
            {option ? tDynamic("field.ticketStatus", option) : t("field.all")}
          </button>
        ))}
      </div>
      {message ? <p className="field-message field-message--ok">{message}</p> : null}

      {query.isPending ? (
        <LoadingState shape="table" />
      ) : query.isError ? (
        <ErrorState title={t("field.loadError")} onRetry={() => void query.refetch()} />
      ) : tickets.length === 0 ? (
        <EmptyState title={t("field.serviceEmpty")} illustration="document" />
      ) : (
        <table className="field-table">
          <thead>
            <tr>
              <th scope="col">{t("field.colCode")}</th>
              <th scope="col">{t("field.colKind")}</th>
              <th scope="col">{t("field.colProject")}</th>
              <th scope="col">{t("field.colClient")}</th>
              <th scope="col">{t("field.colOrder")}</th>
              <th scope="col">{t("field.colDescription")}</th>
              <th scope="col">{t("field.colWarranty")}</th>
              <th scope="col">{t("field.colVisit")}</th>
              <th scope="col">{t("field.colStatus")}</th>
              {canWrite ? <th scope="col">{t("field.colAction")}</th> : null}
            </tr>
          </thead>
          <tbody>
            {tickets.map((ticket) => {
              const status = ticket.status;
              return (
                <tr key={ticket.id}>
                  <td>
                    <code>{ticket.code}</code>
                  </td>
                  <td>
                    <StatusChip
                      label={tDynamic("field.ticketKind", ticket.kind)}
                      tone={ticket.kind === "WARRANTY" ? "info" : "neutral"}
                      value={ticket.kind}
                    />
                  </td>
                  <td>
                    <code>{ticket.project_code}</code>
                    <br />
                    <span className="dispatch-stop__address">{ticket.site_address ?? ""}</span>
                  </td>
                  <td>{ticket.client_name ?? "—"}</td>
                  <td>
                    {ticket.order_id ? (
                      <Link className="deliveries-order" to={`/field/orders/${ticket.order_id}`}>
                        {ticket.order_code}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{ticket.description}</td>
                  <td>
                    {ticket.warranty_until ? (
                      <>
                        {formatDate(ticket.warranty_until)}
                        <StatusChip
                          label={
                            ticket.in_warranty ? t("field.inWarranty") : t("field.outWarranty")
                          }
                          tone={ticket.in_warranty ? "ok" : "neutral"}
                          value="warranty"
                        />
                      </>
                    ) : ticket.kind === "WARRANTY" ? (
                      t("field.noData")
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {ticket.scheduled_visit_at ? formatDate(ticket.scheduled_visit_at) : "—"}
                    {ticket.crew_name ? ` · ${ticket.crew_name}` : ""}
                  </td>
                  <td>
                    <StatusChip
                      label={tDynamic("field.ticketStatus", status)}
                      tone={status === "CLOSED" ? "ok" : "info"}
                      value={status}
                    />
                  </td>
                  {canWrite ? (
                    <td>
                      <div className="field-chip-row">
                        {(NEXT_ACTIONS[status] ?? []).map((action) => (
                          <button
                            className="field-button field-button--ghost"
                            key={action.next}
                            onClick={() => {
                              if (action.next === "CLOSED") {
                                setClosing(ticket);
                              } else if (action.next === "SCHEDULED") {
                                setScheduling(ticket);
                              } else {
                                transition(ticket, action.next);
                              }
                            }}
                            type="button"
                          >
                            {t(action.label as TranslationKey)}
                          </button>
                        ))}
                        {status !== "CLOSED" && status !== "CANCELLED" ? (
                          <button
                            className="field-button field-button--ghost"
                            onClick={() => transition(ticket, "CANCELLED")}
                            type="button"
                          >
                            {t("field.ticketCancel")}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {closing ? (
        <ClosePanel
          onClose={(saved) => {
            setClosing(null);
            if (saved) {
              setMessage(t("field.ticketClosed").replace("{code}", closing.code));
              void queryClient.invalidateQueries({ queryKey: ["field-tickets"] });
            }
          }}
          orgId={org!.id}
          ticket={closing}
        />
      ) : null}
      {scheduling ? (
        <SchedulePanel
          onClose={(saved) => {
            setScheduling(null);
            if (saved) {
              setMessage(t("field.ticketScheduled").replace("{code}", scheduling.code));
              void queryClient.invalidateQueries({ queryKey: ["field-tickets"] });
            }
          }}
          orgId={org!.id}
          ticket={scheduling}
        />
      ) : null}
    </section>
  );
}

function ClosePanel({
  ticket,
  orgId,
  onClose,
}: {
  ticket: ServiceTicket;
  orgId: string;
  onClose: (saved: boolean) => void;
}): JSX.Element {
  const [note, setNote] = useState("");
  const [diagnosis, setDiagnosis] = useState(ticket.diagnosis ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const submit = () => {
    if (!note.trim()) return;
    setBusy(true);
    void serviceTicketTransition(
      ticket.id,
      {
        status: "CLOSED",
        close_note: note.trim(),
        diagnosis: diagnosis.trim() || undefined,
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
    <div className="field-card field-section-gap" role="dialog">
      <h2>
        {t("field.closeTitle")} {ticket.code}
      </h2>
      <label className="field-field">
        <span>{t("field.diagnosis")}</span>
        <textarea onChange={(event) => setDiagnosis(event.target.value)} value={diagnosis} />
      </label>
      <label className="field-field field-section-gap">
        <span>{t("field.closeNote")}</span>
        <textarea onChange={(event) => setNote(event.target.value)} value={note} />
      </label>
      {error ? <p className="field-message field-message--error">{t("field.saveFailed")}</p> : null}
      <div className="field-actions">
        <button
          className="field-button"
          disabled={busy || !note.trim()}
          onClick={submit}
          type="button"
        >
          {busy ? t("field.saving") : t("field.ticketClose")}
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

function SchedulePanel({
  ticket,
  orgId,
  onClose,
}: {
  ticket: ServiceTicket;
  orgId: string;
  onClose: (saved: boolean) => void;
}): JSX.Element {
  const [when, setWhen] = useState("");
  const [visitNote, setVisitNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const submit = () => {
    if (!when) return;
    setBusy(true);
    void serviceTicketTransition(
      ticket.id,
      {
        status: "SCHEDULED",
        scheduled_visit_at: new Date(when).toISOString(),
        visit_note: visitNote.trim() || undefined,
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
    <div className="field-card field-section-gap" role="dialog">
      <h2>
        {t("field.scheduleVisitTitle")} {ticket.code}
      </h2>
      <label className="field-field">
        <span>{t("field.visitAt")}</span>
        <input
          onChange={(event) => setWhen(event.target.value)}
          type="datetime-local"
          value={when}
        />
      </label>
      <label className="field-field field-section-gap">
        <span>{t("field.visitNote")}</span>
        <textarea onChange={(event) => setVisitNote(event.target.value)} value={visitNote} />
      </label>
      {error ? <p className="field-message field-message--error">{t("field.saveFailed")}</p> : null}
      <div className="field-actions">
        <button className="field-button" disabled={busy || !when} onClick={submit} type="button">
          {busy ? t("field.saving") : t("field.ticketSchedule")}
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
