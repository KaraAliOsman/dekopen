// Progressive first-run flow: org identity → system context → demo-vs-real
// data choice → first client → first project → first position → first quote.
// Steps that produce records create them inline (client, project); steps that
// belong in another surface deep-link into it (editor, pricing).

import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/apiMutator";
import {
  catalogSystemList,
  clientsCreate,
  clientsList,
  projectsCreate,
  projectsList,
  type catalogSystemListResponse,
} from "../../api/generated/dekopen";
import type { SystemResponse } from "../../api/generated/models/systemResponse";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { roleLabel } from "../../app/shellUtils";
import { t } from "../../i18n/es-CL";
import { EmptyState, StatusBadge } from "../../ui";

type Step = 0 | 1 | 2 | 3 | 4 | 5 | 6;

type OnboardingState = {
  step?: Step;
  systemId?: string | null;
  dataChoice?: "demo" | "real" | null;
  clientId?: string | null;
  clientName?: string;
  clientExtra?: { rut: string; email: string; phone: string };
  projectId?: string | null;
  projectName?: string;
};

/** The tour hands off to other surfaces (position editor, pricing) — progress
 * and created IDs survive the detour per organization. */
function storageKey(orgId: string): string {
  return `onboarding:${orgId}`;
}

function readState(orgId: string): OnboardingState {
  if (!orgId) return {};
  try {
    const raw = sessionStorage.getItem(storageKey(orgId));
    return raw ? (JSON.parse(raw) as OnboardingState) : {};
  } catch {
    return {};
  }
}

const STEP_LABELS = [
  "onboarding.stepIdentity",
  "onboarding.stepSystem",
  "onboarding.stepData",
  "onboarding.stepClient",
  "onboarding.stepProject",
  "onboarding.stepPosition",
  "onboarding.stepQuote",
] as const;

function stepIsDone(
  step: Step,
  done: {
    system: boolean;
    data: boolean;
    clientId: string | null;
    projectId: string | null;
  },
): boolean {
  switch (step) {
    case 0:
      return true;
    case 1:
      return done.system;
    case 2:
      return done.data;
    case 3:
      return done.clientId !== null;
    case 4:
      return done.projectId !== null;
    default:
      return false;
  }
}

export function OnboardingPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const orgId = org?.id ?? "";
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<Step>(0);
  const [systemId, setSystemId] = useState<string | null>(null);
  const [dataChoice, setDataChoice] = useState<"demo" | "real" | null>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [clientName, setClientName] = useState("");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  // Org-scoped draft: `restoredOrgRef` marks the org whose draft was already
  // loaded so switching orgs restores that org's own saved state instead of
  // carrying the previous org's records. `restoredFor` gates persistence — the
  // write effect skips until the new org's draft is actually in state, so a
  // switch can never overwrite B's entry with A's values.
  const restoredOrgRef = useRef("");
  const [restoredFor, setRestoredFor] = useState("");
  const [moreClient, setMoreClient] = useState(false);
  const [clientExtra, setClientExtra] = useState({ rut: "", email: "", phone: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId || restoredOrgRef.current === orgId) return;
    restoredOrgRef.current = orgId;
    const saved = readState(orgId);
    setStep(saved.step ?? 0);
    setSystemId(saved.systemId ?? null);
    setDataChoice(saved.dataChoice ?? null);
    setClientId(saved.clientId ?? null);
    setClientName(saved.clientName ?? "");
    setClientExtra(saved.clientExtra ?? { rut: "", email: "", phone: "" });
    setProjectId(saved.projectId ?? null);
    setProjectName(saved.projectName ?? "");
    setMoreClient(false);
    setError(null);
    setRestoredFor(orgId);
  }, [orgId]);

  useEffect(() => {
    if (!orgId || restoredFor !== orgId) return;
    sessionStorage.setItem(
      storageKey(orgId),
      JSON.stringify({
        step,
        systemId,
        dataChoice,
        clientId,
        clientName,
        clientExtra,
        projectId,
        projectName,
      }),
    );
  }, [
    orgId,
    restoredFor,
    step,
    systemId,
    dataChoice,
    clientId,
    clientName,
    clientExtra,
    projectId,
    projectName,
  ]);

  function finish(destination: string): void {
    if (orgId) sessionStorage.removeItem(storageKey(orgId));
    navigate(destination);
  }

  const systems = useQuery<SystemResponse[]>({
    queryKey: ["onboarding", "systems", orgId],
    enabled: orgId !== "",
    queryFn: async ({ signal }) => {
      const response: catalogSystemListResponse = await catalogSystemList({
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
  });

  const done = { system: systemId !== null, data: dataChoice !== null, clientId, projectId };
  const currentDone = stepIsDone(step, done);
  const lastStep = (STEP_LABELS.length - 1) as Step;
  const canWrite = org?.role === "OWNER" || org?.role === "ESTIMATOR";
  const options = useMemo(() => ({ headers: { "X-Organization-ID": orgId } }), [orgId]);

  // Creates carry no idempotency key: when the response is lost after a
  // server-side commit, reconcile before letting the user submit again. A
  // record may only be adopted when it is indistinguishable from this
  // attempt — same name AND every submitted field, fresh within the attempt
  // window, and the unique match. Anything ambiguous stays an error instead
  // of linking an unrelated record.
  async function adoptIfCreated(
    kind: "client" | "project",
    name: string,
    attemptStart: number,
    clientName?: string,
    fields?: { rut: string; email: string; phone: string },
  ): Promise<string | null> {
    const wanted = name.trim().toLowerCase();
    const fresh = (updated: string): boolean =>
      Math.abs(Date.parse(updated) - attemptStart) <= 60_000;
    const norm = (value: string | undefined): string => (value ?? "").trim().toLowerCase();
    try {
      if (kind === "client") {
        const response = await clientsList(options);
        if (response.status !== 200) return null;
        const matches = response.data.items.filter(
          (entry) =>
            entry.name.trim().toLowerCase() === wanted &&
            fresh(entry.updated_at) &&
            norm(entry.rut) === norm(fields?.rut) &&
            norm(entry.email) === norm(fields?.email) &&
            norm(entry.phone) === norm(fields?.phone),
        );
        return matches.length === 1 ? (matches[0]!.id as string) : null;
      }
      const wantedClient = clientName?.trim().toLowerCase() ?? null;
      const response = await projectsList(options);
      if (response.status !== 200) return null;
      const matches = response.data.items.filter(
        (entry) =>
          entry.name.trim().toLowerCase() === wanted &&
          fresh(entry.updated_at) &&
          (wantedClient === null || entry.client_name.trim().toLowerCase() === wantedClient),
      );
      return matches.length === 1 ? (matches[0]!.id as string) : null;
    } catch {
      return null;
    }
  }

  async function createClient(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (busy || clientName.trim() === "") return;
    setError(null);
    setBusy(true);
    const attemptStart = Date.now();
    try {
      const response = await clientsCreate(
        {
          name: clientName.trim(),
          rut: clientExtra.rut,
          email: clientExtra.email,
          phone: clientExtra.phone,
        },
        options,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      setClientId(response.data.id);
      setStep(4);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status < 500) {
        setError(t(caught.status === 422 ? "projects.invalid" : "onboarding.saveError"));
      } else {
        const adopted = await adoptIfCreated("client", clientName, attemptStart, undefined, {
          rut: clientExtra.rut,
          email: clientExtra.email,
          phone: clientExtra.phone,
        });
        if (adopted) {
          setClientId(adopted);
          setStep(4);
        } else {
          setError(t("onboarding.saveError"));
        }
      }
    } finally {
      setBusy(false);
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (busy || projectName.trim() === "") return;
    setError(null);
    setBusy(true);
    const attemptStart = Date.now();
    try {
      const response = await projectsCreate(
        {
          name: projectName.trim(),
          client_name: clientName.trim(),
          ...(clientId ? { client_id: clientId } : {}),
        },
        options,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      setProjectId(response.data.id);
      void queryClient.invalidateQueries({ queryKey: ["project-switcher"] });
      setStep(5);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status < 500) {
        setError(
          t(
            caught.status === 409 || caught.status === 412
              ? "projects.conflict"
              : "projects.invalid",
          ),
        );
      } else {
        const adopted = await adoptIfCreated("project", projectName, attemptStart, clientName);
        if (adopted) {
          setProjectId(adopted);
          void queryClient.invalidateQueries({ queryKey: ["project-switcher"] });
          setStep(5);
        } else {
          setError(t("onboarding.saveError"));
        }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="onboarding" aria-labelledby="onboarding-title">
      <header className="onboarding-head">
        <p className="eyebrow">{t("onboarding.eyebrow")}</p>
        <h1 id="onboarding-title">{t("onboarding.title")}</h1>
        <p className="onboarding-sub">{t("onboarding.subtitle")}</p>
      </header>

      <ol className="onboarding-steps" aria-label={t("onboarding.title")}>
        {STEP_LABELS.map((label, index) => {
          const n = index as Step;
          const state = stepIsDone(n, done) ? "done" : n === step ? "current" : "pending";
          return (
            <li key={label} className={`onboarding-step is-${state}`}>
              <button
                type="button"
                onClick={() => setStep(n)}
                aria-current={n === step ? "step" : undefined}
              >
                <span className="onboarding-step__index">{index + 1}</span>
                {t(label)}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="onboarding-panel">
        {step === 0 && org && (
          <div className="onboarding-card">
            <h2>{t("onboarding.identityTitle")}</h2>
            <p className="auth-hint">{t("onboarding.identityDescription")}</p>
            <div className="onboarding-org">
              <span className="org-option__glyph" aria-hidden>
                {org.name.trim().slice(0, 1).toUpperCase()}
              </span>
              <span className="org-option__meta">
                <strong>{org.name}</strong>
                <span className="org-option__sub">{t("onboarding.identityWorkspace")}</span>
              </span>
              <StatusBadge
                tone={org.role === "OWNER" ? "info" : "neutral"}
                label={t(roleLabel[org.role])}
              />
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="onboarding-card">
            <h2>{t("onboarding.systemTitle")}</h2>
            <p className="auth-hint">{t("onboarding.systemDescription")}</p>
            {systems.isPending ? (
              <p role="status">{t("onboarding.loadingSystems")}</p>
            ) : systems.isError ? (
              <EmptyState
                title={t("onboarding.systemsError")}
                body={t("onboarding.systemsErrorHint")}
              />
            ) : systems.data.length === 0 ? (
              <EmptyState
                title={t("onboarding.systemsEmpty")}
                body={t("onboarding.systemsEmptyHint")}
              />
            ) : (
              <div className="onboarding-systems" role="list">
                {systems.data.map((system) => (
                  <button
                    key={system.id}
                    type="button"
                    role="listitem"
                    aria-pressed={systemId === system.id}
                    className={`onboarding-system${systemId === system.id ? " is-picked" : ""}`}
                    // A non-quotable system cannot produce the first quote —
                    // offer it for context only; the catalog flow fixes its
                    // readiness before the editor handoff can use it.
                    disabled={!system.readiness.quote_ready}
                    title={system.readiness.quote_ready ? undefined : system.readiness.reasons[0]}
                    onClick={() => setSystemId(system.id)}
                  >
                    <span className="onboarding-system__meta">
                      <strong>{system.name}</strong>
                      <span className="org-option__sub">{system.code}</span>
                      {!system.readiness.quote_ready && system.readiness.reasons[0] ? (
                        <span className="org-option__sub">{system.readiness.reasons[0]}</span>
                      ) : null}
                    </span>
                    {system.is_demo ? (
                      <StatusBadge
                        tone="neutral"
                        label={t("catalog.demo")}
                        title={t("catalog.demoHelp")}
                      />
                    ) : (
                      <StatusBadge
                        tone={system.readiness.quote_ready ? "success" : "warning"}
                        label={
                          system.readiness.quote_ready
                            ? t("onboarding.systemReady")
                            : t("onboarding.systemBlocked")
                        }
                      />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="onboarding-card">
            <h2>{t("onboarding.dataTitle")}</h2>
            <p className="auth-hint">{t("onboarding.dataDescription")}</p>
            <div className="onboarding-choice">
              <button
                type="button"
                aria-pressed={dataChoice === "demo"}
                className={`onboarding-choice__card${dataChoice === "demo" ? " is-picked" : ""}`}
                onClick={() => setDataChoice("demo")}
              >
                <StatusBadge tone="info" label={t("onboarding.demoBadge")} />
                <strong>{t("onboarding.demoTitle")}</strong>
                <span>{t("onboarding.demoDescription")}</span>
              </button>
              <button
                type="button"
                aria-pressed={dataChoice === "real"}
                className={`onboarding-choice__card${dataChoice === "real" ? " is-picked" : ""}`}
                onClick={() => setDataChoice("real")}
              >
                <StatusBadge tone="success" label={t("onboarding.realBadge")} />
                <strong>{t("onboarding.realTitle")}</strong>
                <span>{t("onboarding.realDescription")}</span>
              </button>
            </div>
            {dataChoice === "real" && (
              <p className="onboarding-note">
                {t("onboarding.realHint")}{" "}
                <Link to="/catalogs/systems">{t("onboarding.realLink")}</Link>
              </p>
            )}
            {dataChoice === "demo" && (
              <p className="onboarding-note">
                {t("onboarding.demoHint")}{" "}
                <Link to="/catalogs/systems">{t("onboarding.removeDemoLink")}</Link>
              </p>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="onboarding-card">
            <h2>{t("onboarding.clientTitle")}</h2>
            <p className="auth-hint">{t("onboarding.clientDescription")}</p>
            {clientId ? (
              <p className="onboarding-note">
                <StatusBadge tone="success" label={t("onboarding.clientSaved")} /> {clientName}
              </p>
            ) : canWrite ? (
              <form className="auth-form" onSubmit={(event) => void createClient(event)}>
                <label htmlFor="onb-client-name">{t("clients.name")}</label>
                <input
                  id="onb-client-name"
                  required
                  autoFocus
                  value={clientName}
                  onChange={(event) => setClientName(event.target.value)}
                />
                <button
                  type="button"
                  className="ui-button ui-button--ghost"
                  aria-expanded={moreClient}
                  onClick={() => setMoreClient((value) => !value)}
                >
                  {t("onboarding.moreClient")}
                </button>
                {moreClient && (
                  <>
                    <label htmlFor="onb-client-rut">{t("clients.rut")}</label>
                    <input
                      id="onb-client-rut"
                      value={clientExtra.rut}
                      onChange={(event) =>
                        setClientExtra((value) => ({ ...value, rut: event.target.value }))
                      }
                    />
                    <label htmlFor="onb-client-email">{t("clients.email")}</label>
                    <input
                      id="onb-client-email"
                      type="email"
                      value={clientExtra.email}
                      onChange={(event) =>
                        setClientExtra((value) => ({ ...value, email: event.target.value }))
                      }
                    />
                    <label htmlFor="onb-client-phone">{t("clients.phone")}</label>
                    <input
                      id="onb-client-phone"
                      value={clientExtra.phone}
                      onChange={(event) =>
                        setClientExtra((value) => ({ ...value, phone: event.target.value }))
                      }
                    />
                  </>
                )}
                <button
                  type="submit"
                  className="ui-button ui-button--primary"
                  disabled={busy || clientName.trim() === ""}
                >
                  {busy ? t("onboarding.saving") : t("onboarding.clientCreate")}
                </button>
              </form>
            ) : (
              <EmptyState
                title={t("onboarding.clientReadonly")}
                body={t("onboarding.readonlyHint")}
              />
            )}
          </div>
        )}

        {step === 4 && (
          <div className="onboarding-card">
            <h2>{t("onboarding.projectTitle")}</h2>
            <p className="auth-hint">{t("onboarding.projectDescription")}</p>
            {projectId ? (
              <p className="onboarding-note">
                <StatusBadge tone="success" label={t("onboarding.projectSaved")} /> {projectName}
              </p>
            ) : canWrite ? (
              <form className="auth-form" onSubmit={(event) => void createProject(event)}>
                <label htmlFor="onb-project-name">{t("projects.name")}</label>
                <input
                  id="onb-project-name"
                  required
                  autoFocus
                  value={projectName}
                  onChange={(event) => setProjectName(event.target.value)}
                />
                {clientId === null && (
                  <>
                    <label htmlFor="onb-project-client">{t("projects.client")}</label>
                    <input
                      id="onb-project-client"
                      required
                      value={clientName}
                      onChange={(event) => setClientName(event.target.value)}
                    />
                  </>
                )}
                <button
                  type="submit"
                  className="ui-button ui-button--primary"
                  disabled={
                    busy ||
                    projectName.trim() === "" ||
                    (clientId === null && clientName.trim() === "")
                  }
                >
                  {busy ? t("onboarding.saving") : t("onboarding.projectCreate")}
                </button>
              </form>
            ) : (
              <EmptyState
                title={t("onboarding.projectReadonly")}
                body={t("onboarding.readonlyHint")}
              />
            )}
          </div>
        )}

        {step === 5 && (
          <div className="onboarding-card">
            <h2>{t("onboarding.positionTitle")}</h2>
            <p className="auth-hint">{t("onboarding.positionDescription")}</p>
            {projectId ? (
              <Link
                className="ui-button ui-button--primary onboarding-link"
                to={`/projects/${projectId}/positions/new${systemId ? `?system=${systemId}` : ""}`}
              >
                {t("onboarding.positionOpen")}
              </Link>
            ) : (
              <EmptyState
                title={t("onboarding.positionNeedProject")}
                body={t("onboarding.readonlyHint")}
              />
            )}
          </div>
        )}

        {step === 6 && (
          <div className="onboarding-card">
            <h2>{t("onboarding.quoteTitle")}</h2>
            <p className="auth-hint">{t("onboarding.quoteDescription")}</p>
            {projectId ? (
              <Link
                className="ui-button ui-button--primary onboarding-link"
                to={`/projects/${projectId}/pricing`}
              >
                {t("onboarding.quoteOpen")}
              </Link>
            ) : (
              <EmptyState
                title={t("onboarding.quoteNeedProject")}
                body={t("onboarding.readonlyHint")}
              />
            )}
          </div>
        )}

        {error ? (
          <p role="alert" className="auth-notice auth-notice--error">
            {error}
          </p>
        ) : null}

        <footer className="onboarding-actions">
          <button
            type="button"
            className="ui-button ui-button--ghost"
            disabled={step === 0}
            onClick={() => setStep((value) => Math.max(0, value - 1) as Step)}
          >
            {t("onboarding.back")}
          </button>
          <button type="button" className="ui-button" onClick={() => navigate("/dashboard")}>
            {t("onboarding.later")}
          </button>
          {step < lastStep ? (
            <button
              type="button"
              className="ui-button ui-button--primary"
              onClick={() => setStep((value) => Math.min(lastStep, value + 1) as Step)}
            >
              {currentDone ? t("onboarding.next") : t("onboarding.skip")}
            </button>
          ) : (
            <button
              type="button"
              className="ui-button ui-button--primary"
              onClick={() => finish("/dashboard")}
            >
              {t("onboarding.finish")}
            </button>
          )}
        </footer>
      </div>
    </section>
  );
}
