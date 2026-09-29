import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { UnsavedChangesGuard } from "../../app/UnsavedChangesGuard";
import {
  clientsCreate,
  clientsDeactivate,
  clientsList,
  clientsUpdate,
  projectsList,
} from "../../api/generated/dekopen";
import type { ClientResponse, ProjectResponse } from "../../api/generated/models";
import type { PatchedClientUpdateRequest } from "../../api/generated/models/patchedClientUpdateRequest";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { t } from "../../i18n/es-CL";
import { Button, DeniedState, Field, PageHeader, useConfirm } from "../../ui";
import "./projects.css";
import { isValidEmail, isValidRut } from "../../format";
import { formatDate } from "../money";

const clientFields = [
  ["name", "clients.name", "text", 255],
  ["rut", "clients.rut", "text", 50],
  ["email", "clients.email", "email", undefined],
  ["phone", "clients.phone", "tel", 50],
  ["address", "clients.address", "textarea", undefined],
  ["giro", "clients.giro", "text", 80],
  ["comuna", "clients.comuna", "text", 20],
  ["notes", "clients.notes", "textarea", undefined],
] as const;

const projectStatusKey: Record<string, Parameters<typeof t>[0]> = {
  DRAFT: "projects.draft",
  QUOTED: "projects.quoted",
  APPROVED: "projects.approved",
  IN_PRODUCTION: "projects.production",
  COMPLETED: "projects.completed",
  CANCELLED: "projects.cancelled",
};

type Draft = {
  value: PatchedClientUpdateRequest;
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
      notes: "",
    },
  };
}

function filled(client: ClientResponse): Draft {
  return {
    value: {
      name: client.name,
      rut: client.rut,
      email: client.email,
      phone: client.phone,
      address: client.address,
      giro: client.giro ?? "",
      comuna: client.comuna ?? "",
      notes: client.notes,
    },
    expectedUpdatedAt: client.updated_at,
  };
}

function lastActivity(client: ClientResponse, projects: ProjectResponse[]): string {
  return projects.reduce(
    (latest, project) => (project.updated_at > latest ? project.updated_at : latest),
    client.updated_at,
  );
}

/** Client registry: master list on the left, the client's whole commercial
 * story on the right — contact data, their projects, last activity. */
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
  // /clients/:id deep-links straight to a client's detail — selection mirrors
  // the route so the address bar and the shell rail stay truthful (review m10).
  const [selected, setSelected] = useState<string | null>(routeClientId ?? null);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lifetime = useRef<AbortController | null>(null);

  const selectClient = (clientId: string | null) => {
    setSelected(clientId);
    navigate(clientId ? `/clients/${clientId}` : "/clients");
  };

  // Browser back/forward or a pasted link changes the route first — selection
  // follows it, so the detail pane never disagrees with the address bar.
  useEffect(() => {
    setSelected(routeClientId ?? null);
  }, [routeClientId]);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);

  const query = useQuery<ClientResponse[]>({
    queryKey: ["clients", orgId],
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
  });

  const projectsQuery = useQuery<ProjectResponse[]>({
    queryKey: ["clients", orgId, "projects"],
    queryFn: async ({ signal }) => {
      const response = await projectsList({
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
    staleTime: 60_000,
  });

  // A workspace leads with the work — land on the first client's ficha
  // instead of an empty hint pane (same pattern as /production).
  useEffect(() => {
    if (routeClientId || creating || !query.data || query.data.length === 0) return;
    navigate(`/clients/${query.data[0]!.id}`, { replace: true });
  }, [routeClientId, creating, query.data, navigate]);

  const allProjects = projectsQuery.data ?? [];
  const projectsByClient = new Map<string, ProjectResponse[]>();
  for (const project of allProjects) {
    if (!project.client_id) continue;
    const list = projectsByClient.get(project.client_id) ?? [];
    list.push(project);
    projectsByClient.set(project.client_id, list);
  }

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
    const options = { signal: controller.signal, headers: { "X-Organization-ID": orgId } };
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
            notes: draft.value.notes ?? "",
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
    } catch (caught) {
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

  const needle = search.toLocaleLowerCase("es-CL");
  const visible = query.data.filter((item) =>
    `${item.name} ${item.rut} ${item.email}`.toLocaleLowerCase("es-CL").includes(needle),
  );
  const selectedClient = query.data.find((item) => item.id === selected) ?? null;
  const selectedProjects = selectedClient
    ? (projectsByClient.get(selectedClient.id) ?? []).sort((a, b) =>
        b.updated_at.localeCompare(a.updated_at),
      )
    : [];

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

      {draft ? (
        <form
          className="project-metadata-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) void save();
          }}
        >
          <fieldset disabled={busy}>
            <legend>{t(editing ? "clients.edit" : "clients.new")}</legend>
            {clientFields.map(([name, label, type, maxLength]) => {
              const props = {
                name,
                value: (draft.value[name] as string | undefined) ?? "",
                required: name === "name",
                "aria-label": t(label),
                maxLength,
                onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
                  setDraft({
                    ...draft,
                    value: { ...draft.value, [name]: event.target.value },
                  }),
              };
              return (
                <label key={name}>
                  <span>
                    {t(label)}
                    {name === "name" ? (
                      <span className="form-required" aria-hidden="true">
                        {" "}
                        *
                      </span>
                    ) : null}
                  </span>
                  {type === "textarea" ? <textarea {...props} /> : <input {...props} type={type} />}
                  {name === "rut" && props.value !== "" && !isValidRut(props.value) ? (
                    <span className="field-hint" role="alert">
                      {t("clients.rutInvalid")}
                    </span>
                  ) : null}
                  {name === "email" && props.value !== "" && !isValidEmail(props.value) ? (
                    <span className="field-hint" role="alert">
                      {t("clients.emailInvalid")}
                    </span>
                  ) : null}
                </label>
              );
            })}
            <div className="form-actions">
              <button type="submit">{t("projects.save")}</button>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  void confirm({ title: t("projects.discard") }).then((ok) => {
                    if (ok) {
                      setDraft(null);
                      setEditing(null);
                      setCreating(false);
                      // The form's validation banner belongs to the form —
                      // it must not linger on the list after cancel.
                      setError("");
                    }
                  });
                }}
              >
                {t("projects.cancel")}
              </button>
            </div>
          </fieldset>
        </form>
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
            <ul>
              {visible.map((item) => {
                const clientProjects = projectsByClient.get(item.id) ?? [];
                const active = selected === item.id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`clients-row${active ? " is-active" : ""}`}
                      aria-current={active ? "true" : undefined}
                      onClick={() => selectClient(item.id)}
                    >
                      <span className="clients-row-name">{item.name}</span>
                      <span className="clients-row-meta">{item.rut || item.email || "—"}</span>
                      <span className="clients-row-meta">
                        {t(
                          clientProjects.length === 1
                            ? "clients.projectsCountOne"
                            : "clients.projectsCount",
                        ).replace("{count}", String(clientProjects.length))}
                        {" · "}
                        <time dateTime={lastActivity(item, clientProjects)}>
                          {formatDate(lastActivity(item, clientProjects))}
                        </time>
                      </span>
                      {!item.is_active && (
                        <span className="status-chip" data-status="cancelled">
                          {t("clients.inactive")}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
              {visible.length === 0 && (
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
            {selectedClient === null ? (
              <p className="clients-empty">{t("clients.selectHint")}</p>
            ) : (
              <>
                <header className="clients-detail-head">
                  <div>
                    <h2>{selectedClient.name}</h2>
                    <p className="clients-detail-meta">
                      {selectedClient.rut || "—"}
                      {selectedClient.giro ? ` · ${selectedClient.giro}` : ""}
                      {selectedClient.comuna ? ` · ${selectedClient.comuna}` : ""}
                    </p>
                  </div>
                  {canWrite && (
                    <div className="clients-detail-actions">
                      <button
                        type="button"
                        className="ui-button"
                        disabled={busy}
                        onClick={() => {
                          setEditing(selectedClient.id);
                          setDraft(filled(selectedClient));
                        }}
                      >
                        {t("projects.edit")}
                      </button>
                      {selectedClient.is_active && (
                        <button
                          type="button"
                          className="ui-button ui-button--danger"
                          disabled={busy}
                          onClick={() => void deactivate(selectedClient)}
                        >
                          {t("clients.deactivate")}
                        </button>
                      )}
                    </div>
                  )}
                </header>

                <dl className="clients-facts">
                  {selectedClient.email && (
                    <div>
                      <dt>{t("clients.email")}</dt>
                      <dd>{selectedClient.email}</dd>
                    </div>
                  )}
                  {selectedClient.phone && (
                    <div>
                      <dt>{t("clients.phone")}</dt>
                      <dd>{selectedClient.phone}</dd>
                    </div>
                  )}
                  {selectedClient.address && (
                    <div>
                      <dt>{t("clients.address")}</dt>
                      <dd>{selectedClient.address}</dd>
                    </div>
                  )}
                  {selectedClient.notes && (
                    <div>
                      <dt>{t("clients.notes")}</dt>
                      <dd>{selectedClient.notes}</dd>
                    </div>
                  )}
                </dl>

                <section aria-label={t("clients.projectsTitle")}>
                  <h3 className="eyebrow">{t("clients.projectsTitle")}</h3>
                  {selectedProjects.length === 0 ? (
                    <p className="clients-empty">{t("clients.noProjects")}</p>
                  ) : (
                    <ul className="clients-projects">
                      {selectedProjects.map((project) => (
                        <li key={project.id}>
                          <Link to={`/projects/${project.id}`} className="clients-project-row">
                            <span className="dashboard-row-code">{project.code}</span>
                            <span className="dashboard-row-name">{project.name}</span>
                            <span
                              className="status-chip"
                              data-status={project.status.toLowerCase()}
                            >
                              {t(projectStatusKey[project.status] ?? "projects.draft")}
                            </span>
                            <time dateTime={project.updated_at}>
                              {formatDate(project.updated_at)}
                            </time>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
