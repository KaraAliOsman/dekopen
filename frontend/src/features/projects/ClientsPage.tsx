import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { UnsavedChangesGuard } from "../../app/UnsavedChangesGuard";
import {
  clientsAddNote,
  clientsCreate,
  clientsDeactivate,
  clientsDuplicates,
  clientsList,
  clientsMerge,
  clientsRetrieve,
  clientsUpdate,
} from "../../api/generated/dekopen";
import type {
  ClientAddressRequest,
  ClientsListFiltro,
  ClientContactRequest,
  ClientDetailResponse,
  ClientListItem,
  ClientResponse,
  PatchedClientUpdateRequest,
} from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { t } from "../../i18n/es-CL";
import { Button, DeniedState, Field, PageHeader, useConfirm } from "../../ui";
import { StatusBadge } from "../../ui/StatusBadge";
import { StatusChip } from "../../ui/StatusChip";
import "./projects.css";
import { formatDate, formatDateTime, formatMoney, isValidEmail, isValidRut } from "../../format";

type ContactDraft = ClientContactRequest;
type AddressDraft = ClientAddressRequest;

type Draft = {
  value: PatchedClientUpdateRequest & {
    contacts?: ContactDraft[];
    addresses?: AddressDraft[];
  };
  expectedUpdatedAt?: string;
};

function empty(): Draft {
  return {
    value: {
      name: "",
      rut: "",
      email: "",
      phone: "",
      address: "",
      giro: "",
      comuna: "",
      kind: "COMPANY",
      contacts: [],
      addresses: [],
    },
  };
}

function filled(detail: ClientDetailResponse): Draft {
  const client = detail.client;
  return {
    value: {
      name: client.name,
      rut: client.rut,
      email: client.email,
      phone: client.phone,
      address: client.address,
      giro: client.giro ?? "",
      comuna: client.comuna ?? "",
      kind: client.kind as "PERSON" | "COMPANY",
      contacts: detail.contacts.map((item) => ({
        name: item.name,
        role_label: item.role_label ?? "",
        email: item.email ?? "",
        phone: item.phone ?? "",
        is_primary: item.is_primary,
      })),
      addresses: detail.addresses.map((item) => ({
        label: item.label,
        address: item.address,
        comuna: item.comuna ?? "",
        is_default: item.is_default,
      })),
    },
    expectedUpdatedAt: client.updated_at,
  };
}

const PAYMENT_KIND_ES: Record<string, string> = {
  ANTICIPO: "Anticipo",
  PARCIAL: "Abono",
  SALDO: "Saldo",
};

const PAYMENT_METHOD_ES: Record<string, string> = {
  TRANSFER: "Transferencia",
  CASH: "Efectivo",
  CARD: "Tarjeta",
  CHECK: "Cheque",
  OTHER: "Otro",
};

/** Client registry: master list with search/filters on the left, the full
 * ficha on the right — identidad, contactos, obras, proyectos, cotizaciones,
 * pagos y saldo, documentos, notas con autor, y fusión auditada. */
export function ClientsPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;

  if (!org || !["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"].includes(org.role)) {
    return <DeniedState reason={t("clients.denied")} />;
  }
  return (
    <ClientsWorkspace
      key={org.id}
      orgId={org.id}
      canWrite={org.role === "OWNER" || org.role === "ESTIMATOR"}
    />
  );
}

function ClientsWorkspace({ orgId, canWrite }: { orgId: string; canWrite: boolean }): JSX.Element {
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { id: routeClientId } = useParams();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(routeClientId ?? null);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [merging, setMerging] = useState<{ id: string; name: string; rut: string } | null>(null);
  const [survivorId, setSurvivorId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const lifetime = useRef<AbortController | null>(null);

  const selectClient = (clientId: string | null) => {
    setSelected(clientId);
    navigate(clientId ? `/clients/${clientId}` : "/clients");
  };

  useEffect(() => {
    setSelected(routeClientId ?? null);
  }, [routeClientId]);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);

  const query = useQuery<ClientListItem[]>({
    queryKey: ["clients", orgId, search, filter],
    queryFn: async ({ signal }) => {
      const response = await clientsList(
        {
          q: search || undefined,
          filtro: (filter || undefined) as ClientsListFiltro | undefined,
        },
        {
          signal,
          headers: { "X-Organization-ID": orgId },
        },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });

  const detailQuery = useQuery<ClientDetailResponse>({
    queryKey: ["clients", orgId, "detail", selected],
    queryFn: async ({ signal }) => {
      const response = await clientsRetrieve(selected!, {
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
    enabled: selected !== null && !creating,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });

  const duplicatesQuery = useQuery({
    queryKey: ["clients", orgId, "duplicates"],
    queryFn: async ({ signal }) => {
      const response = await clientsDuplicates({
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (routeClientId || creating || !query.data || query.data.length === 0) return;
    navigate(`/clients/${query.data[0]!.id}`, { replace: true });
  }, [routeClientId, creating, query.data, navigate]);

  async function save(): Promise<void> {
    const controller = lifetime.current;
    if (!draft || !controller || controller.signal.aborted) return;
    if (!isValidRut(draft.value.rut ?? "")) {
      setError(t("clients.rutInvalid"));
      return;
    }
    if (!isValidEmail(draft.value.email ?? "")) {
      setError(t("clients.emailInvalid"));
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    const options = {
      signal: controller.signal,
      headers: { "X-Organization-ID": orgId },
    };
    try {
      if (editing) {
        const response = await clientsUpdate(
          editing,
          { ...draft.value, expected_updated_at: draft.expectedUpdatedAt },
          options,
        );
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        setNotice(t("clients.saved"));
      } else {
        const response = await clientsCreate(
          {
            name: draft.value.name ?? "",
            rut: draft.value.rut ?? "",
            email: draft.value.email ?? "",
            phone: draft.value.phone ?? "",
            address: draft.value.address ?? "",
            giro: draft.value.giro ?? "",
            comuna: draft.value.comuna ?? "",
            kind: draft.value.kind ?? "COMPANY",
            contacts: draft.value.contacts ?? [],
            addresses: draft.value.addresses ?? [],
          },
          options,
        );
        if (response.status !== 201) throw new ApiError(response.status, response.data);
        setNotice(t("clients.saved"));
      }
      if (controller.signal.aborted) return;
      setDraft(null);
      setEditing(null);
      setCreating(false);
      void query.refetch();
      void detailQuery.refetch();
    } catch (caught) {
      if (controller.signal.aborted) return;
      const status = caught instanceof ApiError ? caught.status : null;
      setError(
        t(
          status === 409
            ? "projects.conflict"
            : status === 400 || status === 422
              ? "projects.invalid"
              : "projects.uncertain",
        ),
      );
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function deactivate(client: ClientResponse): Promise<void> {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted) return;
    if (!(await confirm({ title: t("clients.deactivateConfirm"), danger: true }))) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await clientsDeactivate(client.id, {
        signal: controller.signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 204) throw new ApiError(response.status, response.data);
      if (controller.signal.aborted) return;
      setNotice(t("clients.deactivated"));
      void query.refetch();
      void detailQuery.refetch();
    } catch {
      if (!controller.signal.aborted) setError(t("projects.uncertain"));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function addNote(): Promise<void> {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted || !selected) return;
    if (!noteDraft.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await clientsAddNote(
        selected,
        { body: noteDraft },
        {
          signal: controller.signal,
          headers: { "X-Organization-ID": orgId },
        },
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (controller.signal.aborted) return;
      setNoteDraft("");
      setNotice(t("clients.noteSaved"));
      void detailQuery.refetch();
    } catch {
      if (!controller.signal.aborted) setError(t("projects.uncertain"));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function mergeNow(): Promise<void> {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted || !merging || !survivorId) return;
    if (
      !(await confirm({
        title: t("clients.mergeConfirm"),
        danger: true,
      }))
    )
      return;
    setBusy(true);
    setError("");
    try {
      const response = await clientsMerge(
        merging.id,
        { survivor_id: survivorId },
        { signal: controller.signal, headers: { "X-Organization-ID": orgId } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (controller.signal.aborted) return;
      setNotice(t("clients.merged"));
      setMerging(null);
      setSurvivorId("");
      selectClient(survivorId);
      void query.refetch();
      void duplicatesQuery.refetch();
    } catch {
      if (!controller.signal.aborted) setError(t("projects.uncertain"));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  if (query.isPending) return <p role="status">{t("projects.loading")}</p>;
  if (query.isError) {
    return (
      <section className="projects-page">
        <p role="alert">{t("projects.loadError")}</p>
        <button onClick={() => void query.refetch()}>{t("projects.reload")}</button>
      </section>
    );
  }

  const detail = detailQuery.data ?? null;
  const duplicateGroups = duplicatesQuery.data ?? [];

  return (
    <section className="projects-page" aria-busy={busy || query.isFetching}>
      <UnsavedChangesGuard dirty={draft !== null} message={t("projects.leaveUnsaved")} />
      <PageHeader
        actions={
          canWrite && !creating ? (
            <Button
              disabled={busy}
              onClick={() => {
                setCreating(true);
                setEditing(null);
                selectClient(null);
                setDraft(empty());
              }}
              variant="primary"
            >
              {t("clients.new")}
            </Button>
          ) : undefined
        }
        title={t("clients.title")}
      />
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}

      {duplicateGroups.length > 0 && (
        <div className="clients-duplicates" role="status">
          <strong>{t("clients.duplicatesTitle")}</strong>
          {duplicateGroups.map((group) => (
            <p key={group.rut}>
              {t("clients.duplicatesRow").replace("{rut}", group.rut)}
              {canWrite && (
                <button
                  type="button"
                  className="clients-empty__cta"
                  disabled={busy}
                  onClick={() => {
                    setMerging(group.clients[0]!);
                    setSurvivorId(group.clients[1]?.id ?? "");
                  }}
                >
                  {t("clients.mergeCta")}
                </button>
              )}
            </p>
          ))}
        </div>
      )}

      {merging && (
        <form
          className="project-metadata-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) void mergeNow();
          }}
        >
          <fieldset disabled={busy}>
            <legend>{t("clients.mergeTitle")}</legend>
            <p>
              {t("clients.mergeHint")
                .replace("{merged}", merging.name)
                .replace("{rut}", merging.rut || "—")}
            </p>
            <Field label={t("clients.mergeSurvivor")}>
              <select
                className="ui-field__input"
                value={survivorId}
                onChange={(event) => setSurvivorId(event.target.value)}
                required
              >
                <option value="" disabled>
                  {t("clients.mergePick")}
                </option>
                {query.data
                  .filter((item) => item.id !== merging.id && item.is_active)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · {item.rut || "—"}
                    </option>
                  ))}
              </select>
            </Field>
            <div className="form-actions">
              <button type="submit" disabled={!survivorId}>
                {t("clients.mergeDo")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMerging(null);
                  setSurvivorId("");
                }}
              >
                {t("projects.cancel")}
              </button>
            </div>
          </fieldset>
        </form>
      )}

      {draft ? (
        <ClientForm
          draft={draft}
          setDraft={setDraft}
          editing={editing}
          busy={busy}
          onCancel={() => {
            void confirm({ title: t("projects.discard") }).then((ok) => {
              if (ok) {
                setDraft(null);
                setEditing(null);
                setCreating(false);
                setError("");
              }
            });
          }}
          onSave={() => {
            if (!busy) void save();
          }}
        />
      ) : (
        <div className="clients-desk">
          <div className="clients-list">
            <Field label={t("clients.search")}>
              <input
                className="ui-field__input"
                onChange={(event) => setSearch(event.target.value)}
                value={search}
              />
            </Field>
            <Field label={t("clients.filter")}>
              <select
                className="ui-field__input"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
              >
                <option value="">{t("clients.filterAll")}</option>
                <option value="activos">{t("clients.filterActive")}</option>
                <option value="saldo">{t("clients.filterBalance")}</option>
              </select>
            </Field>
            <ul>
              {query.data.map((item) => {
                const active = selected === item.id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`clients-row${active ? " is-active" : ""}`}
                      aria-current={active ? "true" : undefined}
                      onClick={() => selectClient(item.id)}
                    >
                      <span className="clients-row-name">
                        {item.name}
                        {item.kind === "COMPANY" ? (
                          <StatusBadge label={t("clients.kindCompany")} tone="neutral" />
                        ) : (
                          <StatusBadge label={t("clients.kindPerson")} tone="neutral" />
                        )}
                      </span>
                      <span className="clients-row-meta">{item.rut || item.email || "—"}</span>
                      <span className="clients-row-meta">
                        {t("clients.projectsCount")
                          .replace("{count}", String(item.projects_count))
                          .replace("{active}", String(item.active_projects))}
                        {item.balance !== "0" && item.balance !== "0.00" && (
                          <>
                            {" · "}
                            {t("clients.balanceHint")} {formatMoney(item.balance, "CLP")}
                          </>
                        )}
                      </span>
                      {!item.is_active && (
                        <StatusBadge label={t("clients.inactive")} tone="neutral" />
                      )}
                    </button>
                  </li>
                );
              })}
              {query.data.length === 0 && (
                <li className="clients-empty">
                  {t("clients.empty")}
                  {canWrite && (
                    <button
                      type="button"
                      className="clients-empty__cta"
                      onClick={() => {
                        setCreating(true);
                        setEditing(null);
                        selectClient(null);
                        setDraft(empty());
                      }}
                    >
                      {t("clients.new")}
                    </button>
                  )}
                </li>
              )}
            </ul>
          </div>

          <div className="clients-detail">
            {selected === null || detail === null ? (
              <p className="clients-empty">
                {detailQuery.isFetching ? t("projects.loading") : t("clients.selectHint")}
              </p>
            ) : (
              <ClientFicha
                detail={detail}
                canWrite={canWrite}
                busy={busy}
                noteDraft={noteDraft}
                setNoteDraft={setNoteDraft}
                onEdit={() => {
                  setEditing(detail.client.id);
                  setDraft(filled(detail));
                }}
                onDeactivate={() => void deactivate(detail.client)}
                onMerge={() => {
                  setMerging(detail.client);
                  setSurvivorId("");
                }}
                onAddNote={() => void addNote()}
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function ClientFicha({
  detail,
  canWrite,
  busy,
  noteDraft,
  setNoteDraft,
  onEdit,
  onDeactivate,
  onMerge,
  onAddNote,
}: {
  detail: ClientDetailResponse;
  canWrite: boolean;
  busy: boolean;
  noteDraft: string;
  setNoteDraft: (value: string) => void;
  onEdit: () => void;
  onDeactivate: () => void;
  onMerge: () => void;
  onAddNote: () => void;
}): JSX.Element {
  const client = detail.client;
  return (
    <>
      <header className="clients-detail-head">
        <div>
          <h2>
            {client.name}
            <StatusBadge
              label={t(client.kind === "COMPANY" ? "clients.kindCompany" : "clients.kindPerson")}
              tone="neutral"
            />
          </h2>
          <p className="clients-detail-meta">
            {client.rut || "—"}
            {client.giro ? ` · ${client.giro}` : ""}
            {client.comuna ? ` · ${client.comuna}` : ""}
            {!client.is_active ? ` · ${t("clients.inactive")}` : ""}
          </p>
          <p className="clients-detail-meta">
            {t("clients.totals")
              .replace("{billed}", formatMoney(detail.totals.billed, detail.totals.currency))
              .replace("{collected}", formatMoney(detail.totals.collected, detail.totals.currency))
              .replace("{balance}", formatMoney(detail.totals.balance, detail.totals.currency))}
          </p>
        </div>
        {canWrite && (
          <div className="clients-detail-actions">
            <button type="button" className="ui-button" disabled={busy} onClick={onEdit}>
              {t("projects.edit")}
            </button>
            <button type="button" className="ui-button" disabled={busy} onClick={onMerge}>
              {t("clients.mergeCta")}
            </button>
            {client.is_active && (
              <button
                type="button"
                className="ui-button ui-button--danger"
                disabled={busy}
                onClick={onDeactivate}
              >
                {t("clients.deactivate")}
              </button>
            )}
          </div>
        )}
      </header>

      <dl className="clients-facts">
        {client.email && (
          <div>
            <dt>{t("clients.email")}</dt>
            <dd>{client.email}</dd>
          </div>
        )}
        {client.phone && (
          <div>
            <dt>{t("clients.phone")}</dt>
            <dd>{client.phone}</dd>
          </div>
        )}
        {client.address && (
          <div>
            <dt>{t("clients.address")}</dt>
            <dd>{client.address}</dd>
          </div>
        )}
      </dl>

      <section aria-label={t("clients.contactsTitle")}>
        <h3 className="eyebrow">{t("clients.contactsTitle")}</h3>
        {detail.contacts.length === 0 ? (
          <p className="clients-empty">{t("clients.noContacts")}</p>
        ) : (
          <ul className="clients-projects">
            {detail.contacts.map((item) => (
              <li key={item.id}>
                <span className="clients-project-row">
                  <span className="dashboard-row-name">
                    {item.name}
                    {item.is_primary ? ` · ${t("clients.contactPrimary")}` : ""}
                  </span>
                  <span className="clients-row-meta">
                    {[item.role_label, item.email, item.phone].filter(Boolean).join(" · ") || "—"}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label={t("clients.addressesTitle")}>
        <h3 className="eyebrow">{t("clients.addressesTitle")}</h3>
        {detail.addresses.length === 0 ? (
          <p className="clients-empty">{t("clients.noAddresses")}</p>
        ) : (
          <ul className="clients-projects">
            {detail.addresses.map((item) => (
              <li key={item.id}>
                <span className="clients-project-row">
                  <span className="dashboard-row-name">
                    {item.label}
                    {item.is_default ? ` · ${t("clients.addressDefault")}` : ""}
                  </span>
                  <span className="clients-row-meta">
                    {item.address}
                    {item.comuna ? ` · ${item.comuna}` : ""}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label={t("clients.projectsTitle")}>
        <h3 className="eyebrow">{t("clients.projectsTitle")}</h3>
        {detail.projects.length === 0 ? (
          <p className="clients-empty">{t("clients.noProjects")}</p>
        ) : (
          <ul className="clients-projects">
            {detail.projects.map((project) => {
              const projectStatus = project.status;
              return (
                <li key={project.id}>
                  <Link to={`/projects/${project.id}`} className="clients-project-row">
                    <span className="dashboard-row-code">{project.code}</span>
                    <span className="dashboard-row-name">{project.name}</span>
                    <StatusChip enumName="ProjectResponseStatusEnum" value={projectStatus} />
                    <span className="clients-row-meta">
                      {formatMoney(project.billed, "CLP")}
                      {" · "}
                      {t("clients.balanceHint")} {formatMoney(project.balance, "CLP")}
                    </span>
                    <time dateTime={project.created_at}>{formatDate(project.created_at)}</time>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-label={t("clients.quotationsTitle")}>
        <h3 className="eyebrow">{t("clients.quotationsTitle")}</h3>
        {detail.quotations.length === 0 ? (
          <p className="clients-empty">{t("clients.noQuotations")}</p>
        ) : (
          <ul className="clients-projects">
            {detail.quotations.map((item) => (
              <li key={`${item.project_id}-${item.revision_code}`}>
                <Link to={`/projects/${item.project_id}`} className="clients-project-row">
                  <span className="dashboard-row-code">{item.revision_code}</span>
                  <span className="clients-row-meta">
                    {item.total_price_gross
                      ? formatMoney(item.total_price_gross, item.currency)
                      : "—"}
                  </span>
                  <time dateTime={item.emitted_at}>{formatDate(item.emitted_at)}</time>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label={t("clients.paymentsTitle")}>
        <h3 className="eyebrow">{t("clients.paymentsTitle")}</h3>
        {detail.payments.length === 0 ? (
          <p className="clients-empty">{t("clients.noPayments")}</p>
        ) : (
          <ul className="clients-projects">
            {detail.payments.map((item) => (
              <li key={item.id}>
                <Link to={`/projects/${item.project_id}`} className="clients-project-row">
                  <span className="dashboard-row-code">
                    {item.receipt_code || item.project_code}
                  </span>
                  <span className="dashboard-row-name">
                    {formatMoney(item.amount, "CLP")}
                    {item.voided ? ` · ${t("clients.paymentVoided")}` : ""}
                  </span>
                  <span className="clients-row-meta">
                    {PAYMENT_KIND_ES[item.kind] ?? item.kind}
                    {" · "}
                    {PAYMENT_METHOD_ES[item.method] ?? item.method}
                  </span>
                  <time dateTime={item.recorded_at}>{formatDate(item.recorded_at)}</time>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label={t("clients.documentsTitle")}>
        <h3 className="eyebrow">{t("clients.documentsTitle")}</h3>
        {detail.documents.length === 0 ? (
          <p className="clients-empty">{t("clients.noDocuments")}</p>
        ) : (
          <ul className="clients-projects">
            {detail.documents.map((item) => (
              <li key={item.id}>
                <Link to={`/projects/${item.project_id}`} className="clients-project-row">
                  <span className="dashboard-row-code">{item.document_type}</span>
                  <span className="dashboard-row-name">{item.project_code}</span>
                  <span className="clients-row-meta">{item.format}</span>
                  <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label={t("clients.notesTitle")}>
        <h3 className="eyebrow">{t("clients.notesTitle")}</h3>
        {detail.notes.length === 0 ? (
          <p className="clients-empty">{t("clients.noNotes")}</p>
        ) : (
          <ul className="clients-projects">
            {detail.notes.map((item) => (
              <li key={item.id}>
                <span className="clients-project-row">
                  <span className="dashboard-row-name">{item.body}</span>
                  <span className="clients-row-meta">{item.author_label}</span>
                  <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                </span>
              </li>
            ))}
          </ul>
        )}
        {canWrite && (
          <form
            className="clients-note-form"
            onSubmit={(event) => {
              event.preventDefault();
              onAddNote();
            }}
          >
            <input
              className="ui-field__input"
              aria-label={t("clients.notePlaceholder")}
              placeholder={t("clients.notePlaceholder")}
              value={noteDraft}
              onChange={(event) => setNoteDraft(event.target.value)}
            />
            <button type="submit" className="ui-button" disabled={busy || !noteDraft.trim()}>
              {t("clients.noteAdd")}
            </button>
          </form>
        )}
      </section>

      {detail.merges.length > 0 && (
        <section aria-label={t("clients.mergesTitle")}>
          <h3 className="eyebrow">{t("clients.mergesTitle")}</h3>
          <ul className="clients-projects">
            {detail.merges.map((item) => (
              <li key={item.id}>
                <span className="clients-project-row">
                  <span className="clients-row-meta">
                    {item.actor_label}
                    {" · "}
                    {t("clients.mergeDetail")
                      .replace("{projects}", String(item.detail.projects ?? 0))
                      .replace("{contacts}", String(item.detail.client_contacts ?? 0))
                      .replace("{addresses}", String(item.detail.client_addresses ?? 0))
                      .replace("{notes}", String(item.detail.client_notes ?? 0))}
                  </span>
                  <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function ClientForm({
  draft,
  setDraft,
  editing,
  busy,
  onCancel,
  onSave,
}: {
  draft: Draft;
  setDraft: (value: Draft) => void;
  editing: string | null;
  busy: boolean;
  onCancel: () => void;
  onSave: () => void;
}): JSX.Element {
  const contacts = draft.value.contacts ?? [];
  const addresses = draft.value.addresses ?? [];
  const setField = (name: string, value: string) =>
    setDraft({ ...draft, value: { ...draft.value, [name]: value } });

  return (
    <form
      className="project-metadata-form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <fieldset disabled={busy}>
        <legend>{t(editing ? "clients.edit" : "clients.new")}</legend>
        <label>
          <span>{t("clients.kind")}</span>
          <select
            className="ui-field__input"
            value={draft.value.kind ?? "COMPANY"}
            onChange={(event) => setField("kind", event.target.value)}
          >
            <option value="COMPANY">{t("clients.kindCompany")}</option>
            <option value="PERSON">{t("clients.kindPerson")}</option>
          </select>
        </label>
        <label>
          <span>
            {t("clients.name")}
            <span className="form-required" aria-hidden="true">
              {" "}
              *
            </span>
          </span>
          <input
            name="name"
            required
            value={draft.value.name ?? ""}
            onChange={(event) => setField("name", event.target.value)}
          />
        </label>
        <label>
          <span>{t("clients.rut")}</span>
          <input
            name="rut"
            value={draft.value.rut ?? ""}
            maxLength={50}
            onChange={(event) => setField("rut", event.target.value)}
          />
          {(draft.value.rut ?? "") !== "" && !isValidRut(draft.value.rut ?? "") ? (
            <span className="field-hint" role="alert">
              {t("clients.rutInvalid")}
            </span>
          ) : null}
        </label>
        <label>
          <span>{t("clients.email")}</span>
          <input
            name="email"
            type="email"
            value={draft.value.email ?? ""}
            onChange={(event) => setField("email", event.target.value)}
          />
          {(draft.value.email ?? "") !== "" && !isValidEmail(draft.value.email ?? "") ? (
            <span className="field-hint" role="alert">
              {t("clients.emailInvalid")}
            </span>
          ) : null}
        </label>
        <label>
          <span>{t("clients.phone")}</span>
          <input
            name="phone"
            type="tel"
            value={draft.value.phone ?? ""}
            maxLength={50}
            onChange={(event) => setField("phone", event.target.value)}
          />
        </label>
        <label>
          <span>{t("clients.address")}</span>
          <textarea
            name="address"
            value={draft.value.address ?? ""}
            onChange={(event) => setField("address", event.target.value)}
          />
        </label>
        <label>
          <span>{t("clients.giro")}</span>
          <input
            name="giro"
            value={draft.value.giro ?? ""}
            maxLength={80}
            onChange={(event) => setField("giro", event.target.value)}
          />
        </label>
        <label>
          <span>{t("clients.comuna")}</span>
          <input
            name="comuna"
            value={draft.value.comuna ?? ""}
            maxLength={20}
            onChange={(event) => setField("comuna", event.target.value)}
          />
        </label>

        <h3 className="eyebrow">{t("clients.contactsTitle")}</h3>
        {contacts.map((contact, index) => (
          <div className="clients-subrow" key={index}>
            <input
              aria-label={t("clients.contactName")}
              placeholder={t("clients.contactName")}
              value={contact.name ?? ""}
              onChange={(event) => {
                const next = contacts.slice();
                next[index] = { ...contact, name: event.target.value };
                setDraft({ ...draft, value: { ...draft.value, contacts: next } });
              }}
            />
            <input
              aria-label={t("clients.contactRole")}
              placeholder={t("clients.contactRole")}
              value={contact.role_label ?? ""}
              onChange={(event) => {
                const next = contacts.slice();
                next[index] = { ...contact, role_label: event.target.value };
                setDraft({ ...draft, value: { ...draft.value, contacts: next } });
              }}
            />
            <input
              aria-label={t("clients.email")}
              placeholder={t("clients.email")}
              value={contact.email ?? ""}
              onChange={(event) => {
                const next = contacts.slice();
                next[index] = { ...contact, email: event.target.value };
                setDraft({ ...draft, value: { ...draft.value, contacts: next } });
              }}
            />
            <input
              aria-label={t("clients.phone")}
              placeholder={t("clients.phone")}
              value={contact.phone ?? ""}
              onChange={(event) => {
                const next = contacts.slice();
                next[index] = { ...contact, phone: event.target.value };
                setDraft({ ...draft, value: { ...draft.value, contacts: next } });
              }}
            />
            <label className="clients-inline-check">
              <input
                type="checkbox"
                checked={contact.is_primary ?? false}
                onChange={(event) => {
                  const next = contacts.slice();
                  next[index] = { ...contact, is_primary: event.target.checked };
                  setDraft({ ...draft, value: { ...draft.value, contacts: next } });
                }}
              />
              {t("clients.contactPrimary")}
            </label>
            <button
              type="button"
              className="ui-button"
              onClick={() => {
                setDraft({
                  ...draft,
                  value: {
                    ...draft.value,
                    contacts: contacts.filter((_, at) => at !== index),
                  },
                });
              }}
            >
              {t("clients.removeRow")}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="ui-button"
          onClick={() =>
            setDraft({
              ...draft,
              value: {
                ...draft.value,
                contacts: [
                  ...contacts,
                  {
                    name: "",
                    role_label: "",
                    email: "",
                    phone: "",
                    is_primary: contacts.length === 0,
                  },
                ],
              },
            })
          }
        >
          {t("clients.addContact")}
        </button>

        <h3 className="eyebrow">{t("clients.addressesTitle")}</h3>
        {addresses.map((item, index) => (
          <div className="clients-subrow" key={index}>
            <input
              aria-label={t("clients.addressLabel")}
              placeholder={t("clients.addressLabel")}
              value={item.label ?? ""}
              onChange={(event) => {
                const next = addresses.slice();
                next[index] = { ...item, label: event.target.value };
                setDraft({ ...draft, value: { ...draft.value, addresses: next } });
              }}
            />
            <input
              aria-label={t("clients.addressStreet")}
              placeholder={t("clients.addressStreet")}
              value={item.address ?? ""}
              onChange={(event) => {
                const next = addresses.slice();
                next[index] = { ...item, address: event.target.value };
                setDraft({ ...draft, value: { ...draft.value, addresses: next } });
              }}
            />
            <input
              aria-label={t("clients.comuna")}
              placeholder={t("clients.comuna")}
              value={item.comuna ?? ""}
              onChange={(event) => {
                const next = addresses.slice();
                next[index] = { ...item, comuna: event.target.value };
                setDraft({ ...draft, value: { ...draft.value, addresses: next } });
              }}
            />
            <label className="clients-inline-check">
              <input
                type="checkbox"
                checked={item.is_default ?? false}
                onChange={(event) => {
                  const next = addresses.slice();
                  next[index] = { ...item, is_default: event.target.checked };
                  setDraft({ ...draft, value: { ...draft.value, addresses: next } });
                }}
              />
              {t("clients.addressDefault")}
            </label>
            <button
              type="button"
              className="ui-button"
              onClick={() => {
                setDraft({
                  ...draft,
                  value: {
                    ...draft.value,
                    addresses: addresses.filter((_, at) => at !== index),
                  },
                });
              }}
            >
              {t("clients.removeRow")}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="ui-button"
          onClick={() =>
            setDraft({
              ...draft,
              value: {
                ...draft.value,
                addresses: [
                  ...addresses,
                  { label: "Obra", address: "", comuna: "", is_default: addresses.length === 0 },
                ],
              },
            })
          }
        >
          {t("clients.addAddress")}
        </button>

        <div className="form-actions">
          <button type="submit">{t("projects.save")}</button>
          <button type="button" disabled={busy} onClick={onCancel}>
            {t("projects.cancel")}
          </button>
        </div>
      </fieldset>
    </form>
  );
}
