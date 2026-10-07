import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import {
  fieldIncidentResolve,
  fieldIncidentsList,
  fieldPurchaseRequestsList,
  fieldPurchaseRequestTransition,
} from "../../api/generated/dekopen";
import type {
  Incident,
  PurchaseRequest,
  SiteIncidentResolutionEnum,
} from "../../api/generated/models";
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
  Tabs,
} from "../../ui";

import "./field.css";

const BOARD_ROLES = ["OWNER", "WORKSHOP_MANAGER", "ESTIMATOR"];
const WRITE_ROLES = ["OWNER", "WORKSHOP_MANAGER"];
const TABS = ["incidents", "purchases"] as const;
const KIND_TONE: Record<string, string> = {
  DAMAGE: "danger",
  WRONG_MEASURE: "danger",
  MISSING: "warn",
  ADJUSTMENT: "info",
};

/** Mesa de incidencias: cada IN- con su OT, unidad y foto llega aquí; el
 * jefe decide el destino — remake (OT-RM), compra de terreno (SC-),
 * postventa (PV-) o cierre — y el folio queda enlazado. */
export function FieldIncidentsPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const role = org?.role ?? "";
  const allowed = org != null && BOARD_ROLES.includes(role);
  const canResolve = WRITE_ROLES.includes(role);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") ?? "incidents") as (typeof TABS)[number];

  if (!allowed) {
    return <DeniedState reason={t("field.incidentsDenied")} />;
  }

  return (
    <section aria-labelledby="page-title" className="field-root field-root--wide">
      <PageHeader
        context={t("field.incidentsSubtitle")}
        headingId="page-title"
        title={t("field.incidentsTitle")}
      />
      <Tabs
        items={TABS.map((id) => ({
          id,
          label: t(`field.tab.${id}` as TranslationKey),
        }))}
        label={t("field.incidentsTitle")}
        onChange={(id) => {
          const next = new URLSearchParams(params);
          next.set("tab", id);
          setParams(next);
        }}
        value={tab}
      />
      {tab === "incidents" ? (
        <IncidentBoard canResolve={canResolve} orgId={org!.id} />
      ) : (
        <PurchaseBoard canWrite={canResolve} orgId={org!.id} />
      )}
    </section>
  );
}

function IncidentBoard({ orgId, canResolve }: { orgId: string; canResolve: boolean }): JSX.Element {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [resolving, setResolving] = useState<Incident | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const query = useQuery<Incident[]>({
    queryKey: ["field-incidents", orgId, status],
    queryFn: async ({ signal }) => {
      const response = await fieldIncidentsList(status ? { status } : undefined, {
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data.incidents;
    },
  });

  if (query.isPending) return <LoadingState shape="table" />;
  if (query.isError) {
    return <ErrorState title={t("field.loadError")} onRetry={() => void query.refetch()} />;
  }
  const incidents = query.data ?? [];

  return (
    <>
      <div className="field-chip-row field-section-gap">
        {["", "OPEN", "IN_PROGRESS", "RESOLVED"].map((option) => (
          <button
            aria-pressed={status === option}
            className="field-button field-button--ghost"
            key={option || "all"}
            onClick={() => setStatus(option)}
            type="button"
          >
            {option ? tDynamic("field.incidentStatus", option) : t("field.all")}
          </button>
        ))}
      </div>
      {message ? <p className="field-message field-message--ok">{message}</p> : null}
      {incidents.length === 0 ? (
        <EmptyState title={t("field.incidentsEmpty")} illustration="document" />
      ) : (
        <div className="dispatch-table__wrap">
          <table className="field-table">
            <thead>
              <tr>
                <th scope="col">{t("field.colCode")}</th>
                <th scope="col">{t("field.colOrder")}</th>
                <th scope="col">{t("field.colKind")}</th>
                <th scope="col">{t("field.colUnit")}</th>
                <th scope="col">{t("field.colNote")}</th>
                <th scope="col">{t("field.colReported")}</th>
                <th scope="col">{t("field.colStatus")}</th>
                <th scope="col">{t("field.colResolution")}</th>
                {canResolve ? <th scope="col">{t("field.colAction")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {incidents.map((incident) => {
                const status = incident.status;
                return (
                  <tr key={incident.id}>
                    <td>
                      <code>{incident.code}</code>
                    </td>
                    <td>
                      <Link className="deliveries-order" to={`/field/orders/${incident.order_id}`}>
                        {incident.order_code}
                      </Link>
                      <br />
                      <span className="dispatch-stop__address">{incident.project_code}</span>
                    </td>
                    <td>
                      <StatusChip
                        label={tDynamic("field.incidentKind", incident.kind)}
                        tone={KIND_TONE[incident.kind] ?? "neutral"}
                        value={incident.kind}
                      />
                    </td>
                    <td>{incident.unit_index != null ? `U${incident.unit_index}` : "—"}</td>
                    <td>{incident.note ?? "—"}</td>
                    <td>{formatDate(incident.reported_at)}</td>
                    <td>
                      <StatusChip
                        label={tDynamic("field.incidentStatus", status)}
                        tone={status === "RESOLVED" ? "ok" : "danger"}
                        value={status}
                      />
                    </td>
                    <td>
                      {incident.resolution_ref_code ??
                        (incident.resolution_kind
                          ? tDynamic("field.resolution", incident.resolution_kind)
                          : "—")}
                    </td>
                    {canResolve ? (
                      <td>
                        {status !== "RESOLVED" ? (
                          <button
                            className="field-button field-button--ghost"
                            onClick={() => setResolving(incident)}
                            type="button"
                          >
                            {t("field.resolve")}
                          </button>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {resolving ? (
        <ResolvePanel
          incident={resolving}
          onClose={(ref) => {
            setResolving(null);
            if (ref) {
              setMessage(t("field.resolved").replace("{ref}", ref));
              void queryClient.invalidateQueries({ queryKey: ["field-incidents"] });
              void queryClient.invalidateQueries({ queryKey: ["field-purchases"] });
            }
          }}
          orgId={orgId}
        />
      ) : null}
    </>
  );
}

function ResolvePanel({
  incident,
  orgId,
  onClose,
}: {
  incident: Incident;
  orgId: string;
  onClose: (ref: string | null) => void;
}): JSX.Element {
  const [resolution, setResolution] = useState<SiteIncidentResolutionEnum>("REMAKE");
  const [note, setNote] = useState("");
  const [item, setItem] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState("");
  const [supplier, setSupplier] = useState("");
  const [neededAt, setNeededAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    if (resolution === "PURCHASE" && !item.trim()) {
      setError(t("field.purchaseItemRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    void fieldIncidentResolve(
      incident.id,
      {
        resolution_kind: resolution,
        note: note.trim() || undefined,
        purchase_item: item.trim() || undefined,
        purchase_quantity: quantity.trim() || undefined,
        purchase_unit: unit.trim() || undefined,
        purchase_supplier_hint: supplier.trim() || undefined,
        purchase_needed_at: neededAt || undefined,
      },
      { headers: { "X-Organization-ID": orgId } },
    )
      .then((response) => {
        if (response.status !== 200) {
          throw new ApiError(response.status, response.data);
        }
        const ref =
          response.data.remake_order_code ??
          response.data.purchase_request_code ??
          response.data.ticket_code ??
          incident.code;
        onClose(ref);
      })
      .catch((caught: unknown) => {
        setError(
          caught instanceof ApiError && caught.payload
            ? t("field.saveFailed")
            : t("field.saveFailed"),
        );
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="field-card field-section-gap" role="dialog">
      <h2>
        {t("field.resolveTitle")} {incident.code}
      </h2>
      <div className="field-chip-row" role="radiogroup">
        {(["REMAKE", "PURCHASE", "SERVICE", "NONE"] as const).map((option) => (
          <button
            aria-pressed={resolution === option}
            className="field-button field-button--ghost"
            key={option}
            onClick={() => setResolution(option)}
            type="button"
          >
            {tDynamic("field.resolution", option)}
          </button>
        ))}
      </div>
      {resolution === "PURCHASE" ? (
        <>
          <label className="field-field field-section-gap">
            <span>{t("field.purchaseItem")}</span>
            <input onChange={(event) => setItem(event.target.value)} value={item} />
          </label>
          <div
            className="field-grid field-section-gap"
            style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr" }}
          >
            <label className="field-field">
              <span>{t("field.purchaseQuantity")}</span>
              <input
                inputMode="decimal"
                onChange={(event) => setQuantity(event.target.value)}
                value={quantity}
              />
            </label>
            <label className="field-field">
              <span>{t("field.purchaseUnit")}</span>
              <input onChange={(event) => setUnit(event.target.value)} value={unit} />
            </label>
            <label className="field-field">
              <span>{t("field.purchaseSupplier")}</span>
              <input onChange={(event) => setSupplier(event.target.value)} value={supplier} />
            </label>
            <label className="field-field">
              <span>{t("field.purchaseNeededAt")}</span>
              <input
                onChange={(event) => setNeededAt(event.target.value)}
                type="date"
                value={neededAt}
              />
            </label>
          </div>
        </>
      ) : null}
      <label className="field-field field-section-gap">
        <span>{t("field.notes")}</span>
        <textarea onChange={(event) => setNote(event.target.value)} value={note} />
      </label>
      {error ? <p className="field-message field-message--error">{error}</p> : null}
      <div className="field-actions">
        <button className="field-button" disabled={busy} onClick={submit} type="button">
          {busy ? t("field.saving") : t("field.resolveSave")}
        </button>
        <button
          className="field-button field-button--ghost"
          onClick={() => onClose(null)}
          type="button"
        >
          {t("field.cancel")}
        </button>
      </div>
    </div>
  );
}

function PurchaseBoard({ orgId, canWrite }: { orgId: string; canWrite: boolean }): JSX.Element {
  const queryClient = useQueryClient();
  const query = useQuery<PurchaseRequest[]>({
    queryKey: ["field-purchases", orgId],
    queryFn: async ({ signal }) => {
      const response = await fieldPurchaseRequestsList(undefined, {
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data.items;
    },
  });

  const mark = (requestId: string, status: "ORDERED" | "RECEIVED" | "CANCELLED") => {
    void fieldPurchaseRequestTransition(
      requestId,
      { status },
      { headers: { "X-Organization-ID": orgId } },
    )
      .then((response) => {
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        void queryClient.invalidateQueries({ queryKey: ["field-purchases"] });
      })
      .catch(() => undefined);
  };

  if (query.isPending) return <LoadingState shape="table" />;
  if (query.isError) {
    return <ErrorState title={t("field.loadError")} onRetry={() => void query.refetch()} />;
  }
  const requests = query.data ?? [];
  if (requests.length === 0) {
    return <EmptyState title={t("field.purchasesEmpty")} illustration="order" />;
  }

  return (
    <table className="field-table">
      <thead>
        <tr>
          <th scope="col">{t("field.colCode")}</th>
          <th scope="col">{t("field.colIncident")}</th>
          <th scope="col">{t("field.colItem")}</th>
          <th scope="col">{t("field.colQuantity")}</th>
          <th scope="col">{t("field.colSupplier")}</th>
          <th scope="col">{t("field.colNeededAt")}</th>
          <th scope="col">{t("field.colStatus")}</th>
          {canWrite ? <th scope="col">{t("field.colAction")}</th> : null}
        </tr>
      </thead>
      <tbody>
        {requests.map((request) => {
          const status = request.status;
          return (
            <tr key={request.id}>
              <td>
                <code>{request.code}</code>
              </td>
              <td>
                <code>{request.incident_code}</code>
              </td>
              <td>{request.item}</td>
              <td>
                {request.quantity ?? "—"} {request.unit ?? ""}
              </td>
              <td>{request.supplier_hint ?? "—"}</td>
              <td>{request.needed_at ? formatDate(request.needed_at) : "—"}</td>
              <td>
                <StatusChip
                  label={tDynamic("field.purchaseStatus", status)}
                  tone={status === "RECEIVED" ? "ok" : "info"}
                  value={status}
                />
              </td>
              {canWrite ? (
                <td>
                  <div className="field-chip-row">
                    {status === "PENDING" ? (
                      <button
                        className="field-button field-button--ghost"
                        onClick={() => mark(request.id, "ORDERED")}
                        type="button"
                      >
                        {t("field.markOrdered")}
                      </button>
                    ) : null}
                    {status === "PENDING" || status === "ORDERED" ? (
                      <button
                        className="field-button field-button--ghost"
                        onClick={() => mark(request.id, "RECEIVED")}
                        type="button"
                      >
                        {t("field.markReceived")}
                      </button>
                    ) : null}
                    {status === "PENDING" || status === "ORDERED" ? (
                      <button
                        className="field-button field-button--ghost"
                        onClick={() => mark(request.id, "CANCELLED")}
                        type="button"
                      >
                        {t("field.markCancelled")}
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
  );
}
