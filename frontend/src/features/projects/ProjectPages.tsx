import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { UnsavedChangesGuard } from "../../app/UnsavedChangesGuard";
import {
  clientsList,
  projectsList,
  projectsCreate,
  projectsUpdate,
  projectsClone,
} from "../../api/generated/dekopen";
import type {
  ClientResponse,
  ProjectResponse,
  ProjectWriteRequest,
} from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { t } from "../../i18n/es-CL";
import {
  formatDateTime,
  formatMoney,
  formatRevision,
  isValidEmail,
  isValidRut,
} from "../../format";
import { projectNameWrite } from "./projectNames";
import { useProjectView } from "./useProject";
import "./projects.css";
import { ProjectHub } from "./ProjectHub";
import { fields, listNextKeys, statuses } from "./projectShared";
import { Button, DeniedState, EmptyState, PageHeader, useConfirm } from "../../ui";
import { StatusChip } from "../../ui/StatusChip";

function metadata(project?: ProjectResponse): ProjectWriteRequest {
  return {
    name: project?.name ?? "",
    client_id: project?.client_id ?? null,
    client_name: project?.client_name ?? "",
    client_rut: project?.client_rut ?? "",
    client_email: project?.client_email ?? "",
    client_phone: project?.client_phone ?? "",
    client_giro: project?.client_giro ?? "",
    client_comuna: project?.client_comuna ?? "",
    client_address: project?.client_address ?? "",
    delivery_address: project?.delivery_address ?? "",
    notes_commercial: project?.notes_commercial ?? "",
    notes_internal: project?.notes_internal ?? "",
  };
}

type Draft = {
  value: ProjectWriteRequest;
  expectedUpdatedAt?: string;
};

function ProjectMetadataForm({
  draft,
  clients,
  disabled,
  onChange,
  onSave,
  onCancel,
}: {
  draft: Draft;
  clients: ClientResponse[];
  disabled: boolean;
  onChange(value: Draft): void;
  onSave(): void;
  onCancel(): void;
}): JSX.Element {
  const fieldError = !isValidRut(draft.value.client_rut ?? "")
    ? "projects.rutInvalid"
    : !isValidEmail(draft.value.client_email ?? "")
      ? "projects.emailInvalid"
      : null;
  return (
    <form
      className="project-metadata-form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (!disabled && fieldError === null) onSave();
      }}
    >
      <fieldset disabled={disabled}>
        <legend>{t("projects.metadata")}</legend>
        {clients.length > 0 && (
          <label>
            {t("clients.pick")}
            <select
              name="client_id"
              value={draft.value.client_id ?? ""}
              onChange={(event) => {
                const picked = clients.find((item) => item.id === event.target.value) ?? null;
                onChange({
                  ...draft,
                  value: {
                    ...draft.value,
                    client_id: picked?.id ?? null,
                    ...(picked
                      ? {
                          client_name: picked.name,
                          client_rut: picked.rut,
                          client_email: picked.email,
                          client_phone: picked.phone,
                          client_giro: picked.giro ?? "",
                          client_comuna: picked.comuna ?? "",
                          client_address: picked.address,
                          delivery_address: draft.value.delivery_address || picked.address,
                        }
                      : {}),
                  },
                });
              }}
            >
              <option value="">{t("clients.none")}</option>
              {clients
                .filter((item) => item.is_active || item.id === draft.value.client_id)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                    {item.rut ? ` · ${item.rut}` : ""}
                  </option>
                ))}
            </select>
          </label>
        )}
        {/* Required fields first and marked; the nine optional commercial
         * fields collapse so the create flow reads as a step, not a wall
         * (review m11). Details opens automatically when stored values exist. */}
        {fields.slice(0, 2).map(([name, label, type, maxLength]) => {
          const props = {
            name,
            value: draft.value[name] ?? "",
            required: true,
            maxLength,
            "aria-label": t(label),
            onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
              onChange({
                ...draft,
                value: { ...draft.value, [name]: event.target.value },
              }),
          };
          return (
            <label key={name}>
              <span>
                {t(label)}
                <span className="form-required" aria-hidden="true">
                  {" "}
                  *
                </span>
              </span>
              {type === "textarea" ? <textarea {...props} /> : <input {...props} type={type} />}
            </label>
          );
        })}
        <details
          className="project-metadata__extra"
          open={fields.slice(2).some(([key]) => (draft.value[key] ?? "") !== "")}
        >
          <summary>{t("projects.moreFields")}</summary>
          {fields.slice(2).map(([name, label, type, maxLength]) => {
            const props = {
              name,
              value: draft.value[name] ?? "",
              maxLength,
              onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
                onChange({
                  ...draft,
                  value: { ...draft.value, [name]: event.target.value },
                }),
            };
            return (
              <label key={name}>
                {t(label)}
                {type === "textarea" ? <textarea {...props} /> : <input {...props} type={type} />}
                {name === "client_rut" && props.value !== "" && !isValidRut(props.value) ? (
                  <span className="field-hint" role="alert">
                    {t("projects.rutInvalid")}
                  </span>
                ) : null}
                {name === "client_email" && props.value !== "" && !isValidEmail(props.value) ? (
                  <span className="field-hint" role="alert">
                    {t("projects.emailInvalid")}
                  </span>
                ) : null}
              </label>
            );
          })}
        </details>
        {fieldError && (
          <p className="field-hint" role="alert">
            {t(fieldError)}
          </p>
        )}
        <div className="form-actions">
          <button type="submit" disabled={disabled || fieldError !== null}>
            {t("projects.save")}
          </button>
          <button type="button" disabled={disabled} onClick={onCancel}>
            {t("projects.cancel")}
          </button>
        </div>
      </fieldset>
    </form>
  );
}

export function ProjectPages(): JSX.Element {
  const auth = useAuthSession();
  const { id } = useParams();
  const org = auth.me?.active_organization;
  const userId = auth.session?.user.id;

  if (!org || !userId || !["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER"].includes(org.role)) {
    return <DeniedState reason={t("projects.denied")} />;
  }

  const identity = `${userId}:${org.id}:${org.role}`;
  return (
    <ProjectWorkspace
      key={`${identity}:${id ?? "list"}`}
      identity={identity}
      orgId={org.id}
      id={id}
      canWrite={org.role === "OWNER" || org.role === "ESTIMATOR"}
      canSendEnvio={org.role === "OWNER" || org.role === "WORKSHOP_MANAGER"}
      isOwner={org.role === "OWNER"}
    />
  );
}

type View = {
  items: ProjectResponse[];
  project: ProjectResponse | null;
};

function ProjectWorkspace({
  identity,
  orgId,
  id,
  canWrite,
  canSendEnvio,
  isOwner,
}: {
  identity: string;
  orgId: string;
  id?: string;
  canWrite: boolean;
  canSendEnvio: boolean;
  isOwner: boolean;
}): JSX.Element {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [quotationDirty, setQuotationDirty] = useState(false);
  const [paymentsDirty, setPaymentsDirty] = useState(false);
  const [importsDirty, setImportsDirty] = useState(false);
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [mustReload, setMustReload] = useState(false);
  const lifetime = useRef<AbortController | null>(null);
  const locked = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);

  // Detail rides the shared project query (same cache entry the shell lock
  // check and the crumb use) — one fetch per project, not one per observer.
  const detailQuery = useProjectView(id ?? null);
  const listQuery = useQuery<View>({
    queryKey: ["project-pages", identity, "list"],
    enabled: !id,
    queryFn: async ({ signal }) => {
      const response = await projectsList({
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return { project: null, items: response.data.items };
    },
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const query = id ? detailQuery : listQuery;

  // The picker only materializes when the metadata form opens — fetch then,
  // so the list page never pays for it.
  const clientsQuery = useQuery<ClientResponse[]>({
    queryKey: ["clients", identity],
    enabled: draft !== null,
    queryFn: async ({ signal }) => {
      const response = await clientsList({
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  async function save(): Promise<void> {
    const controller = lifetime.current;
    if (!draft || !controller || controller.signal.aborted || locked.current || mustReload) return;

    locked.current = true;
    setBusy(true);
    setError("");
    const submitted = draft;
    const options = {
      signal: controller.signal,
      headers: { "X-Organization-ID": orgId },
    };

    try {
      if (id) {
        if (!submitted.expectedUpdatedAt) throw new Error("Missing concurrency token");
        const response = await projectsUpdate(
          id,
          {
            ...submitted.value,
            expected_updated_at: submitted.expectedUpdatedAt,
          },
          options,
        );
        if (response.status !== 200) {
          throw new ApiError(response.status, response.data);
        }
        if (controller.signal.aborted) return;
        projectNameWrite(orgId, id, submitted.value.name);
        setDraft(null);
        setNotice(t("projects.saved"));
        void query.refetch();
        void queryClient.invalidateQueries({ queryKey: ["project-switcher"] });
      } else {
        const response = await projectsCreate(submitted.value, options);
        if (response.status !== 201) {
          throw new ApiError(response.status, response.data);
        }
        if (controller.signal.aborted) return;
        flushSync(() => setDraft(null));
        void queryClient.invalidateQueries({ queryKey: ["project-switcher"] });
        navigate(`/projects/${encodeURIComponent(response.data.id)}`);
      }
    } catch (caught) {
      if (controller.signal.aborted) return;
      const status = caught instanceof ApiError ? caught.status : null;
      setError(
        t(
          status === 409 || status === 412
            ? "projects.conflict"
            : status === 403
              ? "projects.denied"
              : status === 400 || status === 422
                ? "projects.invalid"
                : "projects.uncertain",
        ),
      );
      setMustReload(status !== 400 && status !== 422);
    } finally {
      if (!controller.signal.aborted) {
        locked.current = false;
        setBusy(false);
      }
    }
  }

  async function reload(): Promise<void> {
    if (draft && !(await confirm({ title: t("projects.discard") }))) return;
    setDraft(null);
    const result = await query.refetch();
    if (lifetime.current?.signal.aborted) return;
    if (!result.isError) {
      setMustReload(false);
      setError("");
    }
  }

  async function clone(project: ProjectResponse): Promise<void> {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted || locked.current || mustReload) return;
    if (
      (draft !== null || quotationDirty || paymentsDirty || importsDirty) &&
      !(await confirm({ title: t("projects.leaveUnsaved") }))
    )
      return;
    locked.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await projectsClone(
        project.id,
        { expected_updated_at: project.updated_at },
        { headers: { "X-Organization-ID": orgId }, signal: controller.signal },
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (controller.signal.aborted) return;
      flushSync(() => {
        setQuotationDirty(false);
        setPaymentsDirty(false);
        setImportsDirty(false);
      });
      void queryClient.invalidateQueries({ queryKey: ["project-switcher"] });
      navigate(`/projects/${response.data.id}`);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const status = caught instanceof ApiError ? caught.status : null;
      setError(t(status === 409 ? "projects.conflict" : "projects.uncertain"));
      setMustReload(true);
    } finally {
      if (!controller.signal.aborted) {
        locked.current = false;
        setBusy(false);
      }
    }
  }

  // Scroll restoration: the list remounts on every return, so the scroll
  // offset rides sessionStorage keyed by the org — restored once the rows
  // exist, never on first paint of a shorter list. Lives above the early
  // returns so the hook order stays constant.
  useEffect(() => {
    if (id || !query.data?.items?.length) return;
    const saved = window.sessionStorage.getItem(`projects-scroll:${orgId}`);
    if (saved) window.scrollTo(0, Number.parseInt(saved, 10) || 0);
    const onScroll = () =>
      window.sessionStorage.setItem(`projects-scroll:${orgId}`, String(window.scrollY));
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [id, orgId, query.data]);

  if (query.isPending) return <p role="status">{t("projects.loading")}</p>;
  if (query.isError) {
    return (
      <section className="projects-page">
        <p role="alert">{t("projects.loadError")}</p>
        <div className="projects-error-actions">
          <button onClick={() => void reload()}>{t("projects.reload")}</button>
          {/* A stale deep link is a dead end without an escape back to the
           * list — don't strand the user on an error page. */}
          <Link className="ui-backlink" to="/projects">
            {t("crumb.projects")}
          </Link>
        </div>
      </section>
    );
  }

  const { project, items } = query.data;
  const disabled = busy || query.isFetching || mustReload;
  const editable = canWrite && project?.status === "DRAFT" && !project.pricing_current;
  // List state lives in the URL — search, status filter and sort survive a
  // back-navigation from a project detail without a bespoke store.
  const search = params.get("q") ?? "";
  const setSearch = (value: string) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set("q", value);
        else next.delete("q");
        return next;
      },
      { replace: true },
    );
  };
  const sortKey = params.get("sort") ?? "updated";
  const needle = search.toLocaleLowerCase("es-CL");

  // Deep-linkable triage filter — the dashboard attention queue lands on
  // /projects?status=QUOTED so the promised list is already filtered.
  const statusFilter = params.get("status") ?? "";
  const visible = items
    .filter(
      (item) =>
        (statusFilter === "" || item.status === statusFilter) &&
        `${item.code} ${item.name} ${item.client_name}`.toLocaleLowerCase("es-CL").includes(needle),
    )
    .sort((a, b) => {
      if (sortKey === "name") return (a.name || a.code).localeCompare(b.name || b.code, "es-CL");
      if (sortKey === "code") return a.code.localeCompare(b.code, "es-CL");
      return b.updated_at.localeCompare(a.updated_at);
    });

  return (
    <section className="projects-page" aria-busy={busy || query.isFetching}>
      <UnsavedChangesGuard
        dirty={draft !== null || quotationDirty || paymentsDirty || importsDirty}
        message={t("projects.leaveUnsaved")}
      />
      {!project && (
        <PageHeader
          actions={
            canWrite ? (
              <Button
                disabled={disabled || draft !== null}
                onClick={() => setDraft({ value: metadata() })}
                variant="primary"
              >
                {t("projects.create")}
              </Button>
            ) : undefined
          }
          title={t("projects.title")}
        />
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {mustReload && (
        <button disabled={busy} onClick={() => void reload()}>
          {t("projects.reload")}
        </button>
      )}

      {draft ? (
        <ProjectMetadataForm
          draft={draft}
          clients={clientsQuery.data ?? []}
          disabled={disabled}
          onChange={setDraft}
          onSave={() => void save()}
          onCancel={() => {
            void confirm({ title: t("projects.discard") }).then((ok) => {
              if (ok) {
                setDraft(null);
                setError("");
              }
            });
          }}
        />
      ) : project ? (
        /* The hub owns the detail view: header + lifecycle + tabs, with the
         * merged wave-2 panels (P07 precio, P08 cotización, P11 cobranza,
         * D06 servicios) mounted inside their own tabs — reorganised, not
         * re-implemented. */
        <ProjectHub
          canRelease={canSendEnvio}
          canWrite={canWrite}
          disabled={disabled}
          editable={Boolean(editable)}
          isOwner={isOwner}
          onChanged={() => query.refetch()}
          onClone={() => void clone(project)}
          onConflict={() => setMustReload(true)}
          onDirtyChange={(kind, dirty) => {
            if (kind === "quote") setQuotationDirty(dirty);
            else if (kind === "payments") setPaymentsDirty(dirty);
            else setImportsDirty(dirty);
          }}
          onEdit={() =>
            setDraft({ value: metadata(project), expectedUpdatedAt: project.updated_at })
          }
          onError={setError}
          onNotice={setNotice}
          orgId={orgId}
          project={project}
        />
      ) : (
        <>
          <div className="projects-list-bar">
            <div className="ui-field projects-search">
              <label className="ui-field__label" htmlFor="projects-search">
                {t("projects.search")}
              </label>
              <input
                className="ui-field__input"
                id="projects-search"
                onChange={(event) => setSearch(event.target.value)}
                value={search}
              />
            </div>
            <div className="ui-field">
              <label className="ui-field__label" htmlFor="projects-status">
                {t("projects.status")}
              </label>
              <select
                className="ui-field__input"
                id="projects-status"
                onChange={(event) =>
                  setParams(
                    (current) => {
                      const next = new URLSearchParams(current);
                      if (event.target.value) next.set("status", event.target.value);
                      else next.delete("status");
                      return next;
                    },
                    { replace: true },
                  )
                }
                value={statusFilter}
              >
                <option value="">{t("projects.filterAll")}</option>
                {(Object.keys(statuses) as ProjectResponse["status"][]).map((status) => (
                  <option key={status} value={status}>
                    {t(statuses[status])}
                  </option>
                ))}
              </select>
            </div>
            <div className="ui-field">
              <label className="ui-field__label" htmlFor="projects-sort">
                {t("projects.sortLabel")}
              </label>
              <select
                className="ui-field__input"
                id="projects-sort"
                onChange={(event) =>
                  setParams(
                    (current) => {
                      const next = new URLSearchParams(current);
                      if (event.target.value === "updated") next.delete("sort");
                      else next.set("sort", event.target.value);
                      return next;
                    },
                    { replace: true },
                  )
                }
                value={sortKey}
              >
                <option value="updated">{t("projects.sortUpdated")}</option>
                <option value="name">{t("projects.sortName")}</option>
                <option value="code">{t("projects.sortCode")}</option>
              </select>
            </div>
          </div>
          <div className="ui-table-wrap projects-table">
            <table className="ui-table">
              <caption>{t("projects.title")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("projects.name")}</th>
                  <th scope="col">{t("projects.client")}</th>
                  <th scope="col">{t("projects.status")}</th>
                  <th scope="col">{t("projects.revision")}</th>
                  <th scope="col">{t("projects.positions")}</th>
                  <th scope="col">{t("projects.updated")}</th>
                  <th scope="col">{t("projects.total")}</th>
                  <th scope="col">{t("projects.nextStep")}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => {
                  const itemStatus = item.status;
                  return (
                    <tr key={item.id}>
                      <td>
                        {draft ? (
                          `${item.name || item.code}`
                        ) : (
                          <Link to={`/projects/${encodeURIComponent(item.id)}`}>
                            {item.name || item.code}
                          </Link>
                        )}
                        {item.name ? <span className="projects-row__code">{item.code}</span> : null}
                      </td>
                      <td>{item.client_name}</td>
                      <td>
                        <StatusChip enumName="ProjectResponseStatusEnum" value={itemStatus} />
                      </td>
                      <td>
                        {item.current_revision ? (
                          <span className="projects-row__rev">
                            {formatRevision(item.current_revision)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="ui-table__num">{item.position_count}</td>
                      <td>
                        <time dateTime={item.updated_at}>{formatDateTime(item.updated_at)}</time>
                      </td>
                      <td className="ui-table__num">
                        {item.pricing_current
                          ? formatMoney(item.total_price_gross, item.currency)
                          : t("projects.unpriced")}
                      </td>
                      <td className="projects-row__next">{t(listNextKeys[item.status])}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {visible.length === 0 && <EmptyState illustration="bench" title={t("projects.empty")} />}
        </>
      )}
    </section>
  );
}
