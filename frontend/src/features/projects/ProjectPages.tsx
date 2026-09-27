import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { UnsavedChangesGuard } from "../../app/UnsavedChangesGuard";
import {
  clientsList,
  documentsCompareVersions,
  projectPaymentsList,
  projectQuoteLinkCreate,
  projectQuoteLinksList,
  projectsList,
  projectsCreate,
  projectsUpdate,
  projectsClone,
  positionsDestroy,
  positionsUpdate,
} from "../../api/generated/dekopen";
import type {
  ApprovalRecord,
  ClientResponse,
  PaymentsSummary,
  PositionDesign,
  PositionDesignRequest,
  PositionResponse,
  ProjectResponse,
  ProjectWriteRequest,
  RevisionCompareResponse,
} from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { formatDate, formatMoney } from "../money";
import { fmtMm, formatDateTime, formatRevision } from "../../format";
import { projectNameWrite } from "./projectNames";
import { useProjectView } from "./useProject";
import "./projects.css";
import { PositionThumb } from "./PositionThumb";
import { ProjectBom } from "./ProjectPositionEditor";
import { ProjectQuotationPanel } from "./ProjectQuotationPanel";
import { ProjectImportsPanel } from "./ProjectImportsPanel";
import { ProjectPaymentsPanel } from "./ProjectPaymentsPanel";
import { DeniedState, EmptyState, useConfirm } from "../../ui";

const fields = [
  ["name", "projects.name", "text", 255],
  ["client_name", "projects.client", "text", 255],
  ["client_rut", "projects.rut", "text", 50],
  ["client_email", "projects.email", "email", undefined],
  ["client_phone", "projects.phone", "tel", 50],
  ["client_giro", "projects.clientGiro", "text", 80],
  ["client_comuna", "projects.clientComuna", "text", 20],
  ["client_address", "projects.clientAddress", "text", 70],
  ["delivery_address", "projects.address", "textarea", undefined],
  ["notes_commercial", "projects.commercialNotes", "textarea", undefined],
  ["notes_internal", "projects.internalNotes", "textarea", undefined],
] as const;

const statuses: Record<ProjectResponse["status"], TranslationKey> = {
  DRAFT: "projects.draft",
  QUOTED: "projects.quoted",
  APPROVED: "projects.approved",
  IN_PRODUCTION: "projects.production",
  COMPLETED: "projects.completed",
  CANCELLED: "projects.cancelled",
};

/** Derived per-position progression — the estimator reads "where in the
 * job" each vano is: drafted → engine-evaluated → priced → sealed into a
 * revision → released to production. It is derived, never stored: the
 * project's own state machine is the authority. */
const typologyKeys: Record<string, TranslationKey> = {
  FIXED: "typology.fixed",
  TURN: "typology.turn",
  TILT_TURN: "typology.tiltTurn",
  SLIDING_2L: "typology.sliding2l",
  SLIDING_3L: "typology.sliding3l",
  SLIDING_4L: "typology.sliding4l",
  AWNING: "typology.awning",
  DOOR_ENTRY: "typology.doorEntry",
  COMPOSITE: "typology.composite",
};

function positionStatusKey(
  project: ProjectResponse,
  position: PositionResponse,
): { key: TranslationKey; tone: string } {
  if (project.status === "IN_PRODUCTION" || project.status === "COMPLETED")
    return { key: "position.status.production", tone: "production" };
  // A draft always carries a revision code; frozen only once the revision
  // is actually sealed — otherwise evaluated/priced would never show.
  const revisionSealed = (project.versions ?? []).some(
    (version) => version.revision_code === project.current_revision,
  );
  if (project.status !== "DRAFT" || revisionSealed)
    return { key: "position.status.frozen", tone: "frozen" };
  if (project.pricing_current) return { key: "position.status.priced", tone: "priced" };
  if (position.bom) return { key: "position.status.evaluated", tone: "evaluated" };
  return { key: "position.status.draft", tone: "draft" };
}

/** Inline quantity edit in the positions grid — commits on Enter/blur via
 * the same optimistic-lock PUT the editor uses; a conflict surfaces the
 * shared reload path instead of silently losing the edit. */
function PositionQtyInput({
  position,
  orgId,
  disabled,
  onSaved,
  onConflict,
  onError,
}: {
  position: PositionResponse;
  orgId: string;
  disabled: boolean;
  onSaved(): Promise<unknown>;
  onConflict(): void;
  /** Non-conflict failures surface to the page — the edit reverting must
   * never look like it saved. */
  onError(): void;
}): JSX.Element {
  const [value, setValue] = useState(String(position.quantity));
  const [saving, setSaving] = useState(false);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setValue(String(position.quantity));
    setInvalid(false);
  }, [position.quantity]);

  async function commit(): Promise<void> {
    const next = Number(value);
    // Rejects flag the field instead of silently reverting — a quantity that
    // "snaps back" with no hint reads as the input being ignored.
    if (!Number.isInteger(next) || next < 1) {
      setValue(String(position.quantity));
      setInvalid(true);
      return;
    }
    if (next === position.quantity || saving) return;
    setSaving(true);
    try {
      const response = await positionsUpdate(
        position.id,
        {
          location_tag: position.location_tag ?? "",
          quantity: next,
          design: position.design as PositionDesignRequest,
          expected_updated_at: position.updated_at,
        },
        { headers: { "X-Organization-ID": orgId } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      await onSaved();
    } catch (caught) {
      setValue(String(position.quantity));
      if (caught instanceof ApiError && caught.status === 409) onConflict();
      else onError();
    } finally {
      setSaving(false);
    }
  }

  return (
    <input
      aria-label={t("pricing.quantity")}
      aria-invalid={invalid || undefined}
      className={`position-row__qty-input${invalid ? " is-invalid" : ""}`}
      disabled={disabled || saving}
      inputMode="numeric"
      min={1}
      title={invalid ? t("projects.qtyInvalid") : undefined}
      onBlur={() => void commit()}
      onChange={(event) => {
        setValue(event.target.value);
        setInvalid(false);
      }}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      }}
      type="number"
      value={value}
    />
  );
}

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
  return (
    <form
      className="project-metadata-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!disabled) onSave();
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
              </label>
            );
          })}
        </details>
        <div className="form-actions">
          <button type="submit">{t("projects.save")}</button>
          <button type="button" disabled={disabled} onClick={onCancel}>
            {t("projects.cancel")}
          </button>
        </div>
      </fieldset>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* §03-C/E/F — project workspace header: lifecycle stepper with        */
/* blockers, commercial state track and revision comparison.           */
/* ------------------------------------------------------------------ */

type FactsSection = "quote" | "payments" | "imports" | "compare";

interface SnapshotPosition {
  position_index: number;
  location_tag?: string;
  quantity: string;
  typology: string;
  system_id: string;
  width_mm: string;
  height_mm: string;
  color_interior?: string;
  price_net?: string;
  parametric_tree?: unknown;
}

interface CompareFieldChange {
  field: string;
  before: string;
  after: string;
}

interface ComparePositionEntry {
  position_index: number;
  change: "ADDED" | "REMOVED" | "CHANGED";
  location_tag?: string;
  before: SnapshotPosition | null;
  after: SnapshotPosition | null;
  changes: CompareFieldChange[];
}

const COMPARE_FIELD_KEYS: Record<string, TranslationKey> = {
  position_index: "projects.compareField.position_index",
  location_tag: "projects.compareField.location_tag",
  quantity: "projects.compareField.quantity",
  typology: "projects.compareField.typology",
  system_id: "projects.compareField.system_id",
  width_mm: "projects.compareField.width_mm",
  height_mm: "projects.compareField.height_mm",
  color_interior: "projects.compareField.color_interior",
  color_exterior: "projects.compareField.color_exterior",
  price_net: "projects.compareField.price_net",
  discount_pct: "projects.compareField.discount_pct",
  manufacturing: "projects.compareField.manufacturing",
  spec: "projects.compareField.spec",
};

// Compare values arrive as raw strings — render them as the reader expects:
// money through formatMoney, dims without decimals, discounts as %.
function formatCompareValue(field: string, value: string, currency: string): string {
  if (value === "" || value == null) return "";
  if (field === "price_net") return formatMoney(value, currency);
  if (field === "width_mm" || field === "height_mm") return fmtMm(value);
  // discount_pct persists as a fraction (0.10 = 10 %) — percent-format it.
  if (field === "discount_pct") {
    const fraction = Number(value);
    if (!Number.isFinite(fraction)) return `${value}%`;
    const pct = fraction <= 1 ? fraction * 100 : fraction;
    return `${pct.toFixed(2).replace(/\.?0+$/, "")}%`;
  }
  return value;
}

const PROJECT_ORDER = ["DRAFT", "QUOTED", "APPROVED", "IN_PRODUCTION", "COMPLETED"];

function projectRank(status: string): number {
  return PROJECT_ORDER.indexOf(status);
}

type CommercialState = "done" | "current" | "pending" | "blocked";

interface CommercialStep {
  key: string;
  labelKey: TranslationKey;
  state: CommercialState;
  detail?: string;
}

function commercialSteps(
  project: ProjectResponse,
  approvals: ApprovalRecord[],
  payments: PaymentsSummary | undefined,
  now: number,
): CommercialStep[] {
  // The timeline tracks the CURRENT revision — approvals sent against an
  // older revision must not mark "sent" done for a revision never shared.
  const currentApprovals = approvals.filter((a) => a.revision_code === project.current_revision);
  const rank = projectRank(project.status);
  // A fully revoked batch never reached the client's hands — REVOKED links
  // alone must not mark "sent" done.
  const sent = currentApprovals.some((a) => a.status !== "REVOKED");
  const approvedRecord = currentApprovals.some((a) => a.status === "APPROVED");
  // A PENDING link past its expires_at is dead — the portal refuses it — so
  // the project is not "waiting on the client"; it needs a fresh link.
  const livePending = currentApprovals.some(
    (a) => a.status === "PENDING" && Date.parse(a.expires_at) > now,
  );
  const stalePending = currentApprovals.some(
    (a) => a.status === "PENDING" && Date.parse(a.expires_at) <= now,
  );
  // A declined answer is a real answer — the estimator must see "rechazada",
  // not an eternal "waiting on client" (review F15).
  const declined = currentApprovals.some((a) => a.status === "DECLINED");
  // A sealed version only counts as "sent for quote" when it IS the current
  // revision — an old sealed draft must not light this step forever.
  // "Quoted" means the CURRENT revision is sealed — pricing applied to a
  // live draft is preparation, not a finished quote the client can review.
  const quoted =
    project.versions?.some((v) => v.revision_code === project.current_revision) ?? false;
  const approved = rank >= 2 || approvedRecord;
  const collected = Number(payments?.collected ?? "0");
  const paid = payments?.status === "PAID";
  // The deposit step must name the anticipo amount, not the running total —
  // once the saldo lands, `collected` IS the whole quote and the row reads
  // as "the anticipo was the full price" (hostile P1-5).
  const anticipoTotal = (payments?.payments ?? [])
    .filter((payment) => payment.kind === "ANTICIPO" && payment.voided_at == null)
    .reduce((sum, payment) => sum + Number(payment.amount), 0);
  const released = rank >= 3;
  const latestApproval = [...currentApprovals].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )[0];
  return [
    {
      key: "quoted",
      labelKey: "projects.step.quoted",
      state: quoted ? "done" : "current",
      detail:
        quoted && project.total_price_gross
          ? formatMoney(project.total_price_gross, project.currency)
          : undefined,
    },
    {
      key: "sent",
      labelKey: "projects.step.sent",
      state: sent ? "done" : quoted ? "current" : "pending",
      detail: latestApproval
        ? `${latestApproval.revision_code} · ${formatDate(latestApproval.created_at)}`
        : sent
          ? undefined
          : quoted
            ? t("projects.stepBlockedSend")
            : undefined,
    },
    {
      key: "approved",
      labelKey: "projects.step.approved",
      state: approved
        ? "done"
        : livePending
          ? "current"
          : declined || stalePending
            ? "blocked"
            : "pending",
      detail: approvedRecord
        ? formatDate(currentApprovals.find((a) => a.status === "APPROVED")?.decided_at ?? undefined)
        : livePending
          ? t("projects.stepWaitClient")
          : declined
            ? t("projects.stepLinkDeclined")
            : stalePending
              ? t("projects.stepLinkExpired")
              : undefined,
    },
    {
      key: "deposit",
      labelKey: "projects.step.deposit",
      state: collected > 0 ? "done" : approved ? "current" : "pending",
      detail:
        anticipoTotal > 0 && payments
          ? formatMoney(String(anticipoTotal), payments.currency)
          : collected > 0 && payments
            ? formatMoney(payments.collected, payments.currency)
            : approved && collected === 0
              ? t("projects.stepBlockedDeposit")
              : undefined,
    },
    {
      key: "balance",
      labelKey: "projects.step.balance",
      state: paid ? "done" : collected > 0 ? "current" : "pending",
      detail:
        payments?.balance && Number(payments.balance) > 0
          ? formatMoney(payments.balance, payments.currency)
          : undefined,
    },
    {
      key: "released",
      labelKey: "projects.step.released",
      state: released ? "done" : paid ? "current" : "pending",
    },
  ];
}

interface NextAction {
  labelKey: TranslationKey;
  to?: string;
  section?: FactsSection;
  /** "Enviar al cliente" performs the share itself — mint the portal link
   * and copy it — instead of merely revealing the rail where it lives
   * (review WB1). */
  share?: boolean;
}

function projectNextAction(
  project: ProjectResponse,
  payments: PaymentsSummary | undefined,
  canWrite: boolean,
  canRelease: boolean,
  approvals: ApprovalRecord[],
  now: number,
): NextAction | undefined {
  const paid = payments?.status === "PAID";
  const collected = Number(payments?.collected ?? "0");
  switch (project.status) {
    case "DRAFT":
      if (!canWrite) return undefined;
      if (project.position_count === 0)
        return {
          labelKey: "projects.next.addPositions",
          to: `/projects/${project.id}/positions/new`,
        };
      if (!project.pricing_current)
        return { labelKey: "projects.next.quote", to: `/projects/${project.id}/pricing` };
      return { labelKey: "projects.next.emit", section: "quote" };
    case "QUOTED":
      if (!canWrite) return undefined;
      // A live PENDING link on the current revision means the client already
      // has the quote — the next action is reviewing that outstanding link,
      // not minting another one.
      return approvals.some(
        (a) =>
          a.revision_code === project.current_revision &&
          a.status === "PENDING" &&
          Date.parse(a.expires_at) > now,
      )
        ? { labelKey: "projects.next.awaiting", section: "quote" }
        : { labelKey: "projects.next.share", share: true };
    case "APPROVED":
      // Payment recording is estimator/owner work; release is owner/WM.
      // Check each capability separately — a WM (canRelease, !canWrite)
      // must still reach the release shortcut once the deal is settled.
      if (canWrite) {
        if (collected === 0) return { labelKey: "projects.next.deposit", section: "payments" };
        if (!paid) return { labelKey: "projects.next.balance", section: "payments" };
      }
      // Approved and settled — the remaining work is releasing the sealed
      // revision into production. Only roles the release endpoint accepts
      // (owner / workshop manager) get the shortcut; estimators can't act
      // on it, so for them the header stays honest instead of dead-ending.
      if (!paid || !canRelease) return undefined;
      return { labelKey: "projects.next.release", section: "quote" };
    case "IN_PRODUCTION":
      return { labelKey: "projects.next.production", to: "/production" };
    default:
      return undefined;
  }
}

function ProjectHeader({
  project,
  orgId,
  canWrite,
  canRelease,
  onOpenSection,
  onShareQuote,
}: {
  project: ProjectResponse;
  orgId: string;
  canWrite: boolean;
  canRelease: boolean;
  onOpenSection: (section: FactsSection) => void;
  onShareQuote: () => void;
}): JSX.Element {
  const payments = useQuery({
    queryKey: ["projects", "payments-summary", orgId, project.id],
    queryFn: async () => {
      const response = await projectPaymentsList(project.id);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
  });
  const approvals = useQuery({
    queryKey: ["projects", "quote-approvals", orgId, project.id],
    queryFn: async () => {
      const response = await projectQuoteLinksList(project.id);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
    // A client-side approval or expiry lands on no websocket — poll while a
    // live PENDING link exists so the timeline moves without a reload.
    refetchInterval: (query) =>
      query.state.data?.some((a) => a.status === "PENDING" && Date.parse(a.expires_at) > Date.now())
        ? 15000
        : false,
  });
  const approvalsList = approvals.data ?? [];
  // "Now" is state, not a render-time read: the live-PENDING checks above
  // must re-evaluate the moment a link dies, or the timeline would keep
  // showing "waiting for the client" after the link expired. Tick once at
  // the soonest pending expiry — no continuous polling needed since the
  // refetch interval already dies with the last live link.
  const [now, setNow] = useState(() => Date.now());
  const soonestExpiry = approvalsList
    .filter((a) => a.status === "PENDING")
    .map((a) => Date.parse(a.expires_at))
    .filter((ts) => Number.isFinite(ts) && ts > now)
    .sort((a, b) => a - b)[0];
  useEffect(() => {
    if (soonestExpiry === undefined) return;
    const id = window.setTimeout(
      () => setNow(Date.now()),
      Math.max(0, soonestExpiry - Date.now() + 250),
    );
    return () => window.clearTimeout(id);
  }, [soonestExpiry]);
  const steps = commercialSteps(project, approvalsList, payments.data, now);
  const action = projectNextAction(
    project,
    payments.data,
    canWrite,
    canRelease,
    approvalsList,
    now,
  );
  return (
    <div className="project-head">
      <div className="project-head__row">
        <div>
          <h1>{project.name || project.code}</h1>
          <p className="project-head__meta">
            {project.name ? <span className="project-head__code">{project.code}</span> : null}
            <span className="status-chip" data-status={project.status.toLowerCase()}>
              {t(statuses[project.status])}
            </span>
            {project.client_name && (
              <>
                {" · "}
                {project.client_name}
              </>
            )}
            {" · "}
            <time dateTime={project.updated_at}>{formatDate(project.updated_at)}</time>
          </p>
        </div>
        {action && (
          <div className="project-head__action">
            {action.to ? (
              <Link className="primary-action" to={action.to}>
                {t(action.labelKey)}
              </Link>
            ) : (
              <button
                className="primary-action"
                onClick={() =>
                  action.share ? onShareQuote() : action.section && onOpenSection(action.section)
                }
                type="button"
              >
                {t(action.labelKey)}
              </button>
            )}
          </div>
        )}
      </div>
      <ol aria-label={t("projects.lifecycle")} className="commercial-track">
        {steps.map((step) => (
          <li className="commercial-step" data-state={step.state} key={step.key}>
            <span className="commercial-step__marker" aria-hidden="true" />
            <span className="commercial-step__label">{t(step.labelKey)}</span>
            {step.detail && <span className="commercial-step__detail">{step.detail}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function snapshotDesign(row: SnapshotPosition): PositionDesign {
  return {
    system_id: row.system_id,
    nominal_width_mm: row.width_mm,
    nominal_height_mm: row.height_mm,
    color: "WHITE",
    parametric_tree: row.parametric_tree,
  };
}

function ComparePosition({
  currency,
  entry,
}: {
  currency: string;
  entry: ComparePositionEntry;
}): JSX.Element {
  const row = entry.after ?? entry.before;
  return (
    <li className="compare-row" data-change={entry.change.toLowerCase()}>
      <span className="compare-row__index">{entry.position_index}</span>
      <span className="compare-row__thumbs">
        {entry.before && (
          <span className="compare-thumb" title={t("projects.compareBase")}>
            <PositionThumb design={snapshotDesign(entry.before)} />
          </span>
        )}
        {entry.change === "CHANGED" && (
          <span aria-hidden="true" className="compare-arrow">
            →
          </span>
        )}
        {entry.after && (
          <span className="compare-thumb" title={t("projects.compareHead")}>
            <PositionThumb design={snapshotDesign(entry.after)} />
          </span>
        )}
      </span>
      <span className="compare-row__main">
        <span className="compare-row__loc">
          {entry.location_tag || row?.location_tag || t("projects.position")}
        </span>
        <span className="compare-row__dims">
          {row ? `${fmtMm(row.width_mm)} × ${fmtMm(row.height_mm)} mm` : ""}
        </span>
        {entry.change === "ADDED" && row && (
          <span className="compare-row__detail">
            {formatMoney(row.price_net ?? "0", currency)} · ×{row.quantity}
          </span>
        )}
        {entry.changes.length > 0 && (
          <ul className="compare-row__changes">
            {entry.changes.map((change) => (
              <li key={change.field}>
                {t(COMPARE_FIELD_KEYS[change.field] ?? "projects.compareField.spec")}
                {change.field === "spec" || change.field === "manufacturing"
                  ? ""
                  : `: ${formatCompareValue(change.field, change.before, currency) || "—"} → ${
                      formatCompareValue(change.field, change.after, currency) || "—"
                    }`}
              </li>
            ))}
          </ul>
        )}
      </span>
      <span className="status-chip compare-chip" data-status={entry.change.toLowerCase()}>
        {t(
          entry.change === "ADDED"
            ? "projects.compareChangeAdded"
            : entry.change === "REMOVED"
              ? "projects.compareChangeRemoved"
              : "projects.compareChangeChanged",
        )}
      </span>
    </li>
  );
}

function RevisionComparePanel({ project }: { project: ProjectResponse }): JSX.Element | undefined {
  const versions = project.versions ?? [];
  const [baseCode, setBaseCode] = useState("");
  const [headCode, setHeadCode] = useState("");
  const [result, setResult] = useState<RevisionCompareResponse | undefined>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // A selector change invalidates an in-flight comparison — only the response
  // for the currently selected pair may publish.
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
  }, [baseCode, headCode]);

  useEffect(() => {
    if (versions.length >= 2 && !baseCode && !headCode) {
      setBaseCode(versions[versions.length - 2]!.revision_code);
      setHeadCode(versions[versions.length - 1]!.revision_code);
    }
  }, [versions, baseCode, headCode]);

  async function compare(): Promise<void> {
    if (!baseCode || !headCode || baseCode === headCode) return;
    const current = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const response = await documentsCompareVersions(project.id, {
        base: baseCode,
        head: headCode,
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current === current) setResult(response.data);
    } catch (err) {
      if (generation.current !== current) return;
      setResult(undefined);
      setError(
        t(
          err instanceof ApiError && err.status === 404
            ? "projects.compareNotFound"
            : "projects.compareError",
        ),
      );
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  if (versions.length < 2) {
    return <p className="project-desk__hint">{t("projects.compareNoVersions")}</p>;
  }

  type CompareSide = {
    revision_code?: string;
    integrity?: string | null;
    currency?: string;
    total_price_net?: string;
    total_price_tax?: string;
    total_price_gross?: string;
  };
  const baseSide = result?.base as CompareSide | undefined;
  const headSide = result?.head as CompareSide | undefined;
  const baseCurrency = baseSide?.currency || project.currency;
  const headCurrency = headSide?.currency || project.currency;
  // "Identical" means identical positions AND identical commercial totals —
  // a currency or net/tax-only change with unchanged positions is still a
  // commercial difference.
  const totalsSame =
    baseCurrency === headCurrency &&
    (baseSide?.total_price_net ?? "") === (headSide?.total_price_net ?? "") &&
    (baseSide?.total_price_tax ?? "") === (headSide?.total_price_tax ?? "") &&
    (baseSide?.total_price_gross ?? "") === (headSide?.total_price_gross ?? "");
  const summary = result?.summary as
    | {
        added?: number;
        removed?: number;
        changed?: number;
        unchanged?: number;
        price_gross_delta?: string | null;
      }
    | undefined;
  const positions = (result?.positions ?? []) as ComparePositionEntry[];
  const integrity = (side: CompareSide | undefined) =>
    side?.integrity === "VERIFIED"
      ? t("projects.compareIntegrityVerified")
      : side?.integrity === "MISMATCH"
        ? t("projects.compareIntegrityMismatch")
        : "";

  return (
    <div className="compare-panel">
      <div className="compare-controls">
        <label className="ui-field">
          <span className="ui-field__label">{t("projects.compareBase")}</span>
          <select
            value={baseCode}
            onChange={(e) => {
              setBaseCode(e.target.value);
              setResult(undefined);
              setError("");
            }}
          >
            {versions.map((v) => (
              <option key={v.revision_code} value={v.revision_code}>
                {formatRevision(v.revision_code)} · {formatDate(v.emitted_at)}
              </option>
            ))}
          </select>
        </label>
        <label className="ui-field">
          <span className="ui-field__label">{t("projects.compareHead")}</span>
          <select
            value={headCode}
            onChange={(e) => {
              setHeadCode(e.target.value);
              setResult(undefined);
              setError("");
            }}
          >
            {versions.map((v) => (
              <option key={v.revision_code} value={v.revision_code}>
                {formatRevision(v.revision_code)} · {formatDate(v.emitted_at)}
              </option>
            ))}
          </select>
        </label>
        <button
          className="ui-button"
          disabled={busy || !baseCode || !headCode || baseCode === headCode}
          onClick={() => void compare()}
          type="button"
        >
          {busy ? t("projects.compareLoading") : t("projects.compareRun")}
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <p className="compare-summary">
            <span>
              {formatRevision(baseSide?.revision_code)} {integrity(baseSide)}
            </span>
            <span aria-hidden="true">→</span>
            <span>
              {formatRevision(headSide?.revision_code)} {integrity(headSide)}
            </span>
            {" · "}
            <strong>{summary?.added ?? 0}</strong> {t("projects.compareAdded")} ·{" "}
            <strong>{summary?.removed ?? 0}</strong> {t("projects.compareRemoved")} ·{" "}
            <strong>{summary?.changed ?? 0}</strong> {t("projects.compareChanged")} ·{" "}
            {summary?.unchanged ?? 0} {t("projects.compareUnchanged")}
            {summary?.price_gross_delta != null && (
              <>
                {" · "}
                {t("projects.compareDelta")}{" "}
                <strong>{formatMoney(summary.price_gross_delta, headCurrency)}</strong>
              </>
            )}
          </p>
          <ul className="compare-list">
            {positions.map((entry) => (
              <ComparePosition
                currency={entry.after ? headCurrency : baseCurrency}
                entry={entry}
                key={`${entry.change}-${entry.position_index}`}
              />
            ))}
            {positions.length === 0 && (
              <li className="compare-row" data-change="unchanged">
                <span className="compare-row__main">
                  {totalsSame ? t("projects.compareIdentical") : t("projects.compareTotalsOnly")}
                </span>
              </li>
            )}
          </ul>
        </>
      )}
    </div>
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
  const [search, setSearch] = useState("");
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [factsCollapsed, setFactsCollapsed] = useState(false);
  const [openSection, setOpenSection] = useState<FactsSection | null>(null);
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

  // Workspace-first pattern (same as /clients and /production): land on the
  // first vano's detail card rather than an empty hint pane.
  useEffect(() => {
    if (selectedId) return;
    const first = query.data?.project?.positions?.[0]?.id;
    if (first) setSelectedId(first);
  }, [selectedId, query.data]);

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

  async function deletePosition(position: PositionResponse): Promise<void> {
    const controller = lifetime.current;
    if (!controller || controller.signal.aborted || locked.current) return;
    if (!(await confirm({ title: t("projects.deleteConfirm"), danger: true }))) return;
    locked.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await positionsDestroy(
        position.id,
        { expected_updated_at: position.updated_at },
        { headers: { "X-Organization-ID": orgId }, signal: controller.signal },
      );
      if (response.status !== 204) throw new ApiError(response.status, response.data);
      if (controller.signal.aborted) return;
      setNotice(t("projects.deleted"));
      await query.refetch();
    } catch (caught) {
      if (!controller.signal.aborted)
        setError(
          t(
            caught instanceof ApiError && caught.status === 409
              ? "projects.conflict"
              : "projects.saveError",
          ),
        );
    } finally {
      if (!controller.signal.aborted) {
        locked.current = false;
        setBusy(false);
      }
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
  const needle = search.toLocaleLowerCase("es-CL");

  // The header's "Enviar al cliente" CTA performs the share itself — mint
  // the portal link, copy it, refresh the approvals track (review WB1).
  async function shareQuote(): Promise<void> {
    if (!project) return;
    setNotice("");
    setError("");
    try {
      const response = await projectQuoteLinkCreate(project.id, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      void queryClient.invalidateQueries({
        queryKey: ["projects", "quote-approvals", orgId, project.id],
      });
      const url = `${window.location.origin}${response.data.path}`;
      // Reveal the quote section so the share visibly lands somewhere —
      // a bare toast under the header reads as "nothing happened".
      setFactsCollapsed(false);
      setOpenSection("quote");
      try {
        await navigator.clipboard.writeText(url);
        // The notice carries the URL verbatim: some clipboards accept the
        // write without copying, so the link must always be selectable.
        setNotice(`${t("quotation.shareCopied")} — ${url}`);
      } catch {
        setNotice(url);
      }
    } catch {
      setError(t("quotation.error"));
    }
  }
  // Deep-linkable triage filter — the dashboard attention queue lands on
  // /projects?status=QUOTED so the promised list is already filtered.
  const statusFilter = params.get("status") ?? "";
  const visible = items.filter(
    (item) =>
      (statusFilter === "" || item.status === statusFilter) &&
      `${item.code} ${item.name} ${item.client_name}`.toLocaleLowerCase("es-CL").includes(needle),
  );

  return (
    <section className="projects-page" aria-busy={busy || query.isFetching}>
      <UnsavedChangesGuard
        dirty={draft !== null || quotationDirty || paymentsDirty || importsDirty}
        message={t("projects.leaveUnsaved")}
      />
      {project ? (
        <ProjectHeader
          canWrite={canWrite}
          canRelease={canSendEnvio}
          orgId={orgId}
          onOpenSection={(section) => {
            setFactsCollapsed(false);
            setOpenSection(section);
          }}
          onShareQuote={() => void shareQuote()}
          project={project}
        />
      ) : (
        <h1>{t("projects.title")}</h1>
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
              if (ok) setDraft(null);
            });
          }}
        />
      ) : (
        <div className="projects-actions">
          {project && (
            <Link className="ui-backlink ui-backlink--back" to="/projects">
              {t("projects.back")}
            </Link>
          )}
          {editable && (
            <button
              disabled={disabled}
              onClick={() =>
                setDraft({
                  value: metadata(project!),
                  expectedUpdatedAt: project!.updated_at,
                })
              }
            >
              {t("projects.edit")}
            </button>
          )}
          {project && canWrite && (
            <button disabled={disabled} onClick={() => void clone(project)}>
              {t("projects.cloneDraft")}
            </button>
          )}
          {!project && canWrite && (
            <button disabled={disabled} onClick={() => setDraft({ value: metadata() })}>
              {t("projects.create")}
            </button>
          )}
        </div>
      )}

      {project ? (
        /* data-facts-open widens the facts column while a workflow section
         * (quote/payments/imports/compare) is open — the emission form is
         * unusable at the idle rail's ~280px (review WM4). */
        <div className="project-desk" data-facts-open={openSection || undefined}>
          {/* LEFT — project facts rail: the deal's identity plus the
              quotation/cobranza/imports workflows as collapsible sections.
              Collapsed it shrinks to a strip so the grid owns the room. */}
          <aside className="project-facts" data-collapsed={factsCollapsed || undefined}>
            <div className="project-facts__head">
              <button
                aria-expanded={!factsCollapsed}
                className="ghost-button project-facts__toggle"
                onClick={() => setFactsCollapsed((value) => !value)}
                type="button"
              >
                {t(factsCollapsed ? "projects.factsShow" : "projects.factsHide")}
              </button>
            </div>
            <div className="project-facts__body" hidden={factsCollapsed}>
              <>
                {canWrite && !editable && (
                  <p className="project-locked" role="status">
                    {t(
                      project.status === "DRAFT"
                        ? "projects.lockedPriced"
                        : "projects.lockedQuoted",
                    )}
                    {project.status === "DRAFT" && (
                      <button
                        className="link-button"
                        onClick={() => {
                          setFactsCollapsed(false);
                          setOpenSection("quote");
                        }}
                        type="button"
                      >
                        {t("projects.goToQuote")}
                      </button>
                    )}
                  </p>
                )}
                <dl className="project-metadata project-facts__list">
                  {fields
                    .filter(([name]) => name !== "name" && Boolean(project[name]))
                    .map(([name, label]) => (
                      <div key={name}>
                        <dt>{t(label)}</dt>
                        <dd>{project[name]}</dd>
                      </div>
                    ))}
                  <div>
                    <dt>{t("projects.updated")}</dt>
                    <dd>
                      <time dateTime={project.updated_at}>
                        {formatDateTime(project.updated_at)}
                      </time>
                    </dd>
                  </div>
                  <div>
                    <dt>{t("projects.positions")}</dt>
                    <dd>{project.position_count}</dd>
                  </div>
                  {project.pricing_current ? (
                    <>
                      <div>
                        <dt>{t("projects.net")}</dt>
                        <dd>{formatMoney(project.total_price_net, project.currency)}</dd>
                      </div>
                      <div>
                        <dt>{t("projects.tax")}</dt>
                        <dd>{formatMoney(project.total_price_tax, project.currency)}</dd>
                      </div>
                      <div>
                        <dt>{t("projects.total")}</dt>
                        <dd>{formatMoney(project.total_price_gross, project.currency)}</dd>
                      </div>
                    </>
                  ) : (
                    <div>
                      <dt>{t("projects.total")}</dt>
                      <dd>{t("projects.unpriced")}</dd>
                    </div>
                  )}
                </dl>
                <details
                  className="project-facts__section"
                  onToggle={(event) => {
                    if (event.currentTarget.open) {
                      setOpenSection("quote");
                      event.currentTarget.scrollIntoView({ block: "start" });
                    } else if (openSection === "quote") {
                      setOpenSection(null);
                    }
                  }}
                  open={openSection === "quote"}
                >
                  <summary>{t("projects.quoteSection")}</summary>
                  <ProjectQuotationPanel
                    project={project}
                    orgId={orgId}
                    canWrite={canWrite}
                    canRelease={canSendEnvio}
                    onChanged={() => query.refetch()}
                    onDirtyChange={setQuotationDirty}
                  />
                </details>
                <details
                  className="project-facts__section"
                  onToggle={(event) => {
                    if (event.currentTarget.open) setOpenSection("payments");
                    else if (openSection === "payments") setOpenSection(null);
                  }}
                  open={openSection === "payments"}
                >
                  <summary>{t("projects.paymentsTitle")}</summary>
                  <ProjectPaymentsPanel
                    projectId={project.id}
                    orgId={orgId}
                    canWrite={canWrite}
                    canSendEnvio={canSendEnvio}
                    isOwner={isOwner}
                    onDirtyChange={setPaymentsDirty}
                  />
                </details>
                <details
                  className="project-facts__section"
                  onToggle={(event) => {
                    if (event.currentTarget.open) setOpenSection("imports");
                    else if (openSection === "imports") setOpenSection(null);
                  }}
                  open={openSection === "imports"}
                >
                  <summary>{t("projects.importsSection")}</summary>
                  <ProjectImportsPanel
                    projectId={project.id}
                    orgId={orgId}
                    canWrite={canWrite && editable}
                    onChanged={() => query.refetch()}
                    onDirtyChange={setImportsDirty}
                  />
                </details>
                <details
                  className="project-facts__section"
                  onToggle={(event) => {
                    if (event.currentTarget.open) setOpenSection("compare");
                    else if (openSection === "compare") setOpenSection(null);
                  }}
                  open={openSection === "compare"}
                >
                  <summary>{t("projects.compareTitle")}</summary>
                  <RevisionComparePanel project={project} />
                </details>
              </>
            </div>
          </aside>

          {/* CENTER — the positions grid: dense rows, one per vano, with
              inline quantity and a derived status chip. Clicking a row
              selects it for the side pane. */}
          <div className="project-desk__center">
            <div className="projects-actions">
              <h2 title={t("projects.positionsHint")}>{t("projects.positions")}</h2>
              {editable && (
                <Link className="primary-action" to={`/projects/${project.id}/positions/new`}>
                  {t("projects.addPosition")}
                </Link>
              )}
            </div>
            {project.position_count === 0 && <p>{t("projects.noPositions")}</p>}
            <div className="position-grid" role="listbox" aria-label={t("projects.positions")}>
              {project.positions?.map((position) => {
                const status = positionStatusKey(project, position);
                return (
                  <div
                    aria-selected={selectedId === position.id}
                    className="position-row"
                    data-selected={selectedId === position.id || undefined}
                    key={position.id}
                    onClick={() => setSelectedId(position.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedId(position.id);
                      }
                    }}
                    role="option"
                    tabIndex={0}
                  >
                    <span className="position-row__thumb">
                      <PositionThumb design={position.design} variant="studio" />
                    </span>
                    <span
                      className="position-row__loc"
                      title={
                        position.location_tag
                          ? `${position.position_index}. ${position.location_tag}`
                          : undefined
                      }
                    >
                      {position.position_index}. {position.location_tag || t("projects.position")}
                    </span>
                    <span className="position-row__dims">
                      {fmtMm(position.design.nominal_width_mm)} ×{" "}
                      {fmtMm(position.design.nominal_height_mm)}
                    </span>
                    {Number(position.price_net) > 0 && (
                      <span className="position-row__net">
                        {formatMoney(position.price_net ?? "0", project.currency)}
                      </span>
                    )}
                    <span className="position-row__qty">
                      {editable ? (
                        <PositionQtyInput
                          disabled={disabled}
                          onConflict={() => setMustReload(true)}
                          onError={() => setError(t("projects.uncertain"))}
                          onSaved={() => query.refetch()}
                          orgId={orgId}
                          position={position}
                        />
                      ) : (
                        `×${position.quantity}`
                      )}
                    </span>
                    <span className="status-chip" data-status={status.tone}>
                      {t(status.key)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* RIGHT — the selected vano's summary and its actions; no
              selection means an honest hint, never a fabricated detail. */}
          <aside className="project-desk__side">
            {(() => {
              const selected = project.positions?.find((item) => item.id === selectedId);
              if (!selected)
                return <p className="project-desk__hint">{t("projects.positionHint")}</p>;
              return (
                <div className="position-detail">
                  <h3>
                    {t("projects.selectedPosition")} · {selected.position_index}
                  </h3>
                  <div className="position-detail__thumb">
                    <PositionThumb design={selected.design} variant="studio" />
                  </div>
                  <dl className="project-metadata">
                    <div>
                      <dt>{t("projects.location")}</dt>
                      <dd>{selected.location_tag || "—"}</dd>
                    </div>
                    <div>
                      <dt>{t("projects.dims")}</dt>
                      <dd>
                        {fmtMm(selected.design.nominal_width_mm)} ×{" "}
                        {fmtMm(selected.design.nominal_height_mm)} mm
                      </dd>
                    </div>
                    <div>
                      <dt>{t("pricing.quantity")}</dt>
                      <dd>{selected.quantity}</dd>
                    </div>
                    {Number(selected.price_net) > 0 && (
                      <div>
                        <dt>{t("pricing.net")}</dt>
                        <dd>
                          {formatMoney(selected.price_net ?? "0", project.currency)}
                          {Number(selected.discount_pct) > 0 &&
                            ` · ${t("portal.discount")} ${(Number(selected.discount_pct) * 100).toFixed(2).replace(/\.?0+$/, "")}%`}
                        </dd>
                      </div>
                    )}
                    <div>
                      <dt>{t("projects.typology")}</dt>
                      <dd>
                        {typologyKeys[selected.typology]
                          ? t(typologyKeys[selected.typology]!)
                          : selected.typology}
                      </dd>
                    </div>
                  </dl>
                  <div className="projects-actions">
                    {editable && (
                      <Link to={`/projects/${project.id}/positions/${selected.id}/edit`}>
                        {t("projects.openPosition")}
                      </Link>
                    )}
                    {editable && (
                      <Link to={`/projects/${project.id}/positions/new?copy=${selected.id}`}>
                        {t("projects.duplicatePosition")}
                      </Link>
                    )}
                    {editable && (
                      <button disabled={disabled} onClick={() => void deletePosition(selected)}>
                        {t("projects.deletePosition")}
                      </button>
                    )}
                  </div>
                  <ProjectBom result={selected.bom} />
                </div>
              );
            })()}
          </aside>
        </div>
      ) : (
        <>
          <label>
            {t("projects.search")}
            <input value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <div className="projects-table">
            <table>
              <caption>{t("projects.title")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("projects.name")}</th>
                  <th scope="col">{t("projects.client")}</th>
                  <th scope="col">{t("projects.status")}</th>
                  <th scope="col">{t("projects.positions")}</th>
                  <th scope="col">{t("projects.updated")}</th>
                  <th scope="col">{t("projects.total")}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
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
                      <span className="status-chip" data-status={item.status.toLowerCase()}>
                        {t(statuses[item.status])}
                      </span>
                    </td>
                    <td>{item.position_count}</td>
                    <td>
                      <time dateTime={item.updated_at}>{formatDateTime(item.updated_at)}</time>
                    </td>
                    <td>
                      {item.pricing_current
                        ? formatMoney(item.total_price_gross, item.currency)
                        : t("projects.unpriced")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {visible.length === 0 && <EmptyState title={t("projects.empty")} />}
        </>
      )}
    </section>
  );
}
