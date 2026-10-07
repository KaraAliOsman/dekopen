/* ------------------------------------------------------------------ */
/* P21 — the project hub: header + lifecycle + tabs. The page stops    */
/* being a pile of accordions and becomes the estimator's workbench:  */
/* Posiciones (default), Servicios, Cotización, Precio, Cobranza,      */
/* Producción, Documentos and Actividad. The panels merged in wave 2   */
/* mount unchanged — this file reorganises, it doesn't re-implement.   */
/* ------------------------------------------------------------------ */

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import {
  documentaryArtifactAccess,
  documentaryListArtifacts,
  documentaryPrepareInputs,
  documentsCompareVersions,
  productionOrders,
  projectPaymentsList,
  projectQuoteLinksList,
} from "../../api/generated/dekopen";
import type {
  ApprovalRecord,
  ArtifactListItem,
  DocumentaryPreparationPosition,
  PaymentsSummary,
  PositionDesign,
  ProductionOrder,
  ProjectResponse,
  RevisionCompareResponse,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import {
  fmtMm,
  fmtQty,
  formatDate,
  formatDateTime,
  formatDims,
  formatMoney,
  formatPercent,
  formatRevision,
} from "../../format";
import { EntityCode } from "../../ui/format";
import { EmptyState, StatusBadge, StatusChip, Tabs, type TabItem } from "../../ui";
import { CommercialOperations, usePricingRequest } from "../pricing/PricingPage";
import { PositionThumb } from "./PositionThumb";
import { PositionsTab } from "./ProjectPositionsTab";
import { ProjectPaymentsPanel } from "./ProjectPaymentsPanel";
import { ProjectQuotationPanel } from "./ProjectQuotationPanel";
import { ProjectServicesPanel } from "./ProjectServicesPanel";
import { ProjectThermalPanel } from "./ProjectThermalPanel";
import { fields } from "./projectShared";

/* ------------------------------------------------------------------ */
/* Lifecycle: stepper + the single next-action CTA.                    */
/* ------------------------------------------------------------------ */

type FactsSection = "quote" | "services" | "payments" | "imports" | "compare";

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
        ? `${formatRevision(latestApproval.revision_code)} · ${formatDate(latestApproval.created_at)}`
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
      // P08 — sin caminos alternativos de envío: la acción siempre abre la
      // pestaña de cotización, donde vive el ciclo de vida del enlace
      // (copiar, regenerar, revocar, cambiar vencimiento).
      return approvals.some(
        (a) =>
          a.revision_code === project.current_revision &&
          (a.status === "PENDING" || a.status === "CHANGES_REQUESTED") &&
          Date.parse(a.expires_at) > now,
      )
        ? { labelKey: "projects.next.awaiting", section: "quote" }
        : { labelKey: "projects.next.share", section: "quote" };
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

/* ------------------------------------------------------------------ */
/* Header: code+name, client link, obra, lifecycle, total with IVA,    */
/* vigencia and ONE next-action CTA.                                   */
/* ------------------------------------------------------------------ */

function ProjectHead({
  project,
  orgId,
  canWrite,
  canRelease,
  editable,
  disabled,
  vigencia,
  onEdit,
  onClone,
  onSection,
}: {
  project: ProjectResponse;
  orgId: string;
  canWrite: boolean;
  canRelease: boolean;
  editable: boolean;
  disabled: boolean;
  /** `quotation_valid_until` from the documentary preparation — shown
   * under the total so the estimator sees the quote's clock at a glance. */
  vigencia?: string | null;
  onEdit(): void;
  onClone(): void;
  onSection(section: FactsSection): void;
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
    // live link (pendiente o con cambios pedidos) exists so the timeline
    // moves without a reload.
    refetchInterval: (query) =>
      query.state.data?.some(
        (a) =>
          (a.status === "PENDING" || a.status === "CHANGES_REQUESTED") &&
          Date.parse(a.expires_at) > Date.now(),
      )
        ? 15000
        : false,
  });
  const approvalsList = approvals.data ?? [];
  // "Now" is state, not a render-time read: the live-PENDING checks above
  // must re-evaluate the moment a link dies, or the timeline would keep
  // showing "waiting for the client" after the link expired. Tick once at
  // the soonest expiry — no continuous polling needed since the refetch
  // interval already dies with the last live link.
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
  const projectStatus = project.status;
  const action = projectNextAction(
    project,
    payments.data,
    canWrite,
    canRelease,
    approvalsList,
    now,
  );

  return (
    <header className="project-head">
      <div className="project-head__row">
        <div className="project-head__identity">
          <div className="project-head__title">
            <h1 className="project-head__name">
              {project.name ? project.name : <EntityCode value={project.code} />}
            </h1>
            {project.name ? <EntityCode value={project.code} /> : null}
          </div>
          <p className="project-head__meta">
            <StatusChip enumName="ProjectResponseStatusEnum" value={projectStatus} />
            {project.client_name ? (
              <>
                {" · "}
                {project.client_id ? (
                  <Link to={`/clients/${project.client_id}`}>{project.client_name}</Link>
                ) : (
                  project.client_name
                )}
              </>
            ) : null}
            {project.delivery_address ? <> · {project.delivery_address}</> : null}
            {project.current_revision ? <> · {formatRevision(project.current_revision)}</> : null}
          </p>
        </div>
        <div className="project-head__aside">
          <p className="project-head__total">
            {project.pricing_current
              ? formatMoney(project.total_price_gross, project.currency)
              : t("projects.unpriced")}
          </p>
          {project.pricing_current ? (
            <p className="project-head__iva">
              {t("projects.ivaLabel")} {formatMoney(project.total_price_tax, project.currency)}
              {vigencia ? (
                <>
                  {" · "}
                  {t("projects.vigencia")}: <time dateTime={vigencia}>{formatDate(vigencia)}</time>
                </>
              ) : null}
            </p>
          ) : null}
          {action ? (
            <div className="project-head__action">
              {action.to ? (
                <Link className="primary-action" to={action.to}>
                  {t(action.labelKey)}
                </Link>
              ) : (
                <button
                  className="primary-action"
                  onClick={() => action.section && onSection(action.section)}
                  type="button"
                >
                  {t(action.labelKey)}
                </button>
              )}
            </div>
          ) : null}
        </div>
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
      <div className="project-head__secondary">
        <Link className="ui-backlink ui-backlink--back" to="/projects">
          {t("projects.back")}
        </Link>
        {editable && (
          <button disabled={disabled} onClick={onEdit} type="button">
            {t("projects.edit")}
          </button>
        )}
        {canWrite && (
          <button disabled={disabled} onClick={onClone} type="button">
            {t("projects.cloneDraft")}
          </button>
        )}
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ */
/* Facts dl — the readout the emission checklist deep-links into       */
/* (project-fact-<field> / project-facts-data anchors, P08).           */
/* ------------------------------------------------------------------ */

function ProjectFacts({
  project,
  editable,
  onEdit,
}: {
  project: ProjectResponse;
  editable: boolean;
  onEdit(): void;
}): JSX.Element {
  return (
    /* `project-facts-data` is the checklist's fallback target when the
     * missing fact isn't rendered (empty fields never render a row) —
     * the jump must land somewhere editable: the dl + «Editar datos». */
    <section className="project-facts-block" id="project-facts-data">
      <div className="project-facts-block__head">
        <h2 className="project-facts-block__title">{t("projects.datosTitle")}</h2>
        {editable && (
          <button className="ghost-button" onClick={onEdit} type="button">
            {t("projects.edit")}
          </button>
        )}
      </div>
      <dl className="project-metadata project-facts__list">
        {fields
          .filter(([name]) => name !== "name" && Boolean(project[name]))
          .map(([name, label]) => (
            <div id={`project-fact-${name}`} key={name}>
              <dt>{t(label)}</dt>
              <dd>{project[name]}</dd>
            </div>
          ))}
        <div>
          <dt>{t("projects.updated")}</dt>
          <dd>
            <time dateTime={project.updated_at}>{formatDateTime(project.updated_at)}</time>
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
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Producción / Documentos tabs — light read surfaces fed by the       */
/* existing endpoints, with links out to the real boards.              */
/* ------------------------------------------------------------------ */

function ProductionTab({
  project,
  orgId,
}: {
  project: ProjectResponse;
  orgId: string;
}): JSX.Element {
  const orders = useQuery({
    queryKey: ["project-hub", "production", orgId, project.id],
    queryFn: async () => {
      // Session-scoped endpoint — no org header (same call the workshop
      // board makes; the response carries every order the role may see).
      const response = await productionOrders();
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.orders;
    },
  });
  // Orders hang off the sealed version — the project link is implicit, so
  // match against this project's own version ids rather than a code string.
  const versionIds = useMemo(
    () => new Set((project.versions ?? []).map((version) => version.id)),
    [project.versions],
  );
  const mine = (orders.data ?? []).filter(
    (order) => order.project_version_id && versionIds.has(order.project_version_id),
  );
  return (
    <section aria-label={t("projects.tab.produccion")} className="project-tab">
      {orders.isPending ? (
        <p role="status">{t("projects.loading")}</p>
      ) : mine.length === 0 ? (
        <EmptyState
          action={
            <Link className="ui-button" to={`/production?project=${project.id}`}>
              {t("projects.productionBoard")}
            </Link>
          }
          body={t("projects.productionHint")}
          illustration="bench"
          title={t("projects.productionEmpty")}
        />
      ) : (
        <ul className="project-orders">
          {mine.map((order: ProductionOrder) => {
            const orderStatus = order.status;
            return (
              <li className="project-order" key={order.id}>
                <Link className="project-order__code" to={`/production?order=${order.id}`}>
                  <EntityCode value={order.order_code} />
                </Link>
                <span className="project-order__progress">
                  {t("projects.orderProgress")
                    .replace("{done}", String(order.steps_done))
                    .replace("{total}", String(order.steps_total))}
                </span>
                {order.next_step ? (
                  <span className="project-order__next">{order.next_step.label}</span>
                ) : null}
                <StatusChip enumName="ProductionOrderStatusEnum" value={orderStatus} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** Human name per (document_type, format) — reuses the purchasing labels
 * so the artifact reads the same here and on the workshop board. */
const DOC_LABELS: Record<string, Record<string, TranslationKey>> = {
  "DOC-01": { PDF: "purchasing.doc01" },
  "DOC-02": { PDF: "purchasing.doc02Pdf", XLSX: "purchasing.doc02" },
  "DOC-03": { PDF: "purchasing.doc03" },
  "DOC-04": { PDF: "purchasing.doc04Pdf", XLSX: "purchasing.doc04Xlsx" },
  "DOC-05": { PDF: "purchasing.doc05" },
  "DOC-06": { PDF: "purchasing.doc06" },
  "DOC-07": { PDF: "purchasing.doc07" },
  "DOC-08": { PDF: "purchasing.doc08Pdf", XLSX: "purchasing.doc08Xlsx" },
};

function DocumentsTab({
  project,
  orgId,
  onError,
}: {
  project: ProjectResponse;
  orgId: string;
  onError(message: string): void;
}): JSX.Element {
  const artifacts = useQuery({
    queryKey: ["project-hub", "artifacts", orgId, project.id],
    queryFn: async () => {
      const response = await documentaryListArtifacts(project.id, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.artifacts;
    },
  });
  const [opening, setOpening] = useState<string | null>(null);

  async function open(artifact: ArtifactListItem): Promise<void> {
    if (opening) return;
    setOpening(artifact.id);
    try {
      const response = await documentaryArtifactAccess(artifact.id, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      // Blob + anchor — signed GETs land with the right filename instead of
      // whatever the object store names the key (same pattern as the quote
      // panel's download).
      const blob = await fetch(response.data.signed_url).then((res) => {
        if (!res.ok) throw new ApiError(res.status, {});
        return res.blob();
      });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `${artifact.document_type}-${project.code}-${artifact.revision_code}.${artifact.format.toLowerCase()}`;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
    } catch {
      onError(t("projects.documentOpenError"));
    } finally {
      setOpening(null);
    }
  }

  const items = artifacts.data ?? [];
  return (
    <section aria-label={t("projects.tab.documentos")} className="project-tab">
      {artifacts.isPending ? (
        <p role="status">{t("projects.loading")}</p>
      ) : items.length === 0 ? (
        <EmptyState
          body={t("projects.documentsHint")}
          illustration="document"
          title={t("projects.documentsEmpty")}
        />
      ) : (
        <ul className="project-artifacts">
          {items.map((artifact) => (
            <li className="project-artifact" key={artifact.id}>
              <span className="project-artifact__name">
                {(() => {
                  const labelKey = DOC_LABELS[artifact.document_type]?.[artifact.format];
                  return labelKey ? t(labelKey) : `${artifact.document_type} · ${artifact.format}`;
                })()}
              </span>
              <span className="project-artifact__meta">
                {formatRevision(artifact.revision_code)} ·{" "}
                <time dateTime={artifact.created_at}>{formatDateTime(artifact.created_at)}</time>
              </span>
              <button
                className="ui-button"
                disabled={opening === artifact.id}
                onClick={() => void open(artifact)}
                type="button"
              >
                {t("projects.documentOpen")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Actividad — the same timeline the accordion used to render, now     */
/* its own tab (the events query keys are unchanged → shared cache).   */
/* ------------------------------------------------------------------ */

type ActivityItem = {
  key: string;
  at: string;
  labelKey: TranslationKey;
  detail?: string;
};

function ProjectActivity({
  project,
  orgId,
}: {
  project: ProjectResponse;
  orgId: string;
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
  });

  const events: ActivityItem[] = [];
  for (const version of project.versions ?? []) {
    events.push({
      key: `rev-${version.id}`,
      at: version.emitted_at,
      labelKey: "projects.activityEmitted",
      detail: formatRevision(version.revision_code),
    });
  }
  for (const link of approvals.data ?? []) {
    events.push({
      key: `link-${link.id}-sent`,
      at: link.created_at,
      labelKey: "projects.activityLinkSent",
      detail: formatRevision(link.revision_code),
    });
    if (link.decided_at) {
      events.push({
        key: `link-${link.id}-decided`,
        at: link.decided_at,
        labelKey:
          link.status === "APPROVED"
            ? "projects.activityApproved"
            : "projects.activityChangesAsked",
        detail: link.decided_note ?? formatRevision(link.revision_code),
      });
    }
    if (link.revoked_at) {
      events.push({
        key: `link-${link.id}-revoked`,
        at: link.revoked_at,
        labelKey: "projects.activityLinkRevoked",
        detail: formatRevision(link.revision_code),
      });
    }
  }
  for (const payment of payments.data?.payments ?? []) {
    events.push({
      key: `payment-${payment.id}`,
      at: payment.voided_at ?? payment.recorded_at,
      labelKey: payment.voided_at ? "projects.activityPaymentVoided" : "projects.activityPayment",
      detail: `${formatMoney(payment.amount, payments.data?.currency ?? project.currency)}${
        payment.recorded_by ? ` · ${payment.recorded_by}` : ""
      }`,
    });
  }
  for (const invoice of payments.data?.invoices ?? []) {
    events.push({
      key: `invoice-${invoice.id}`,
      at: invoice.created_at,
      labelKey: "projects.activityInvoice",
      detail: invoice.invoice_code,
    });
    if (invoice.credit_note) {
      events.push({
        key: `nc-${invoice.id}`,
        at: invoice.credit_note.created_at,
        labelKey: "projects.activityCreditNote",
        detail: invoice.credit_note.credit_code,
      });
    }
  }
  const edited = [...(project.positions ?? [])]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 5);
  for (const position of edited) {
    events.push({
      key: `pos-${position.id}`,
      at: position.updated_at,
      labelKey: "projects.activityPosition",
      detail: `P${position.position_index}${
        position.location_tag ? ` · ${position.location_tag}` : ""
      }`,
    });
  }
  events.sort((a, b) => b.at.localeCompare(a.at));

  return (
    <section aria-label={t("projects.tab.actividad")} className="project-tab">
      <ul className="project-activity">
        {events.length === 0 ? (
          <li className="project-activity__empty">{t("projects.activityEmpty")}</li>
        ) : (
          events.slice(0, 14).map((event) => (
            <li key={event.key}>
              <span className="project-activity__label">{t(event.labelKey)}</span>
              {event.detail && <span className="project-activity__detail">{event.detail}</span>}
              <time dateTime={event.at}>{formatDateTime(event.at)}</time>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Revision compare — moved wholesale from the facts accordion.        */
/* ------------------------------------------------------------------ */

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
// money through formatMoney, dims without decimals, discounts as %,
// technical identifiers through EntityCode (mono + copy).
function formatCompareValue(field: string, value: string, currency: string): string {
  if (value === "" || value == null) return "";
  if (field === "price_net") return formatMoney(value, currency);
  if (field === "width_mm" || field === "height_mm") return fmtMm(value);
  // discount_pct persists as a fraction (0.10 = 10 %) — percent-format it.
  if (field === "discount_pct") {
    return formatPercent(value, "fraction");
  }
  return value;
}

function CompareValue({
  field,
  value,
  currency,
}: {
  field: string;
  value: string;
  currency: string;
}): JSX.Element {
  if (value === "" || value == null) return <>—</>;
  if (field === "system_id") return <EntityCode value={value} />;
  return <>{formatCompareValue(field, value, currency)}</>;
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
          {row ? `${formatDims(row.width_mm, row.height_mm)} mm` : ""}
        </span>
        {entry.change === "ADDED" && row && (
          <span className="compare-row__detail">
            {formatMoney(row.price_net ?? "0", currency)} · ×{fmtQty(row.quantity)}
          </span>
        )}
        {entry.changes.length > 0 && (
          <ul className="compare-row__changes">
            {entry.changes.map((change) => (
              <li key={change.field}>
                {t(COMPARE_FIELD_KEYS[change.field] ?? "projects.compareField.spec")}
                {change.field === "spec" || change.field === "manufacturing" ? (
                  ""
                ) : (
                  <>
                    {": "}
                    <CompareValue field={change.field} value={change.before} currency={currency} />
                    {" → "}
                    <CompareValue field={change.field} value={change.after} currency={currency} />
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </span>
      <StatusBadge
        label={t(
          entry.change === "ADDED"
            ? "projects.compareChangeAdded"
            : entry.change === "REMOVED"
              ? "projects.compareChangeRemoved"
              : "projects.compareChangeChanged",
        )}
        tone={
          entry.change === "ADDED" ? "success" : entry.change === "REMOVED" ? "danger" : "warning"
        }
      />
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
    return <p className="project-tab__hint">{t("projects.compareNoVersions")}</p>;
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

/* ------------------------------------------------------------------ */
/* The hub itself — tab strip wired to the URL (?tab=, ?section= as a  */
/* legacy alias for «Hoy» deep-links) and panels mounted on first visit */
/* so heavy queries never fire for a tab the user never opens.         */
/* ------------------------------------------------------------------ */

type HubTab =
  | "posiciones"
  | "termico"
  | "servicios"
  | "cotizacion"
  | "precio"
  | "cobranza"
  | "produccion"
  | "documentos"
  | "actividad";

const HUB_TABS: readonly HubTab[] = [
  "posiciones",
  "termico",
  "servicios",
  "cotizacion",
  "precio",
  "cobranza",
  "produccion",
  "documentos",
  "actividad",
];

const TAB_LABEL_KEYS: Record<HubTab, TranslationKey> = {
  posiciones: "projects.tab.posiciones",
  termico: "projects.tab.termico",
  servicios: "projects.tab.servicios",
  cotizacion: "projects.tab.cotizacion",
  precio: "projects.tab.precio",
  cobranza: "projects.tab.cobranza",
  produccion: "projects.tab.produccion",
  documentos: "projects.tab.documentos",
  actividad: "projects.tab.actividad",
};

/** Legacy ?section= values the «Hoy» dashboard and the next-action CTA
 * still emit — each lands on the tab that now owns that workflow. */
const SECTION_TO_TAB: Record<FactsSection, HubTab> = {
  quote: "cotizacion",
  services: "servicios",
  payments: "cobranza",
  imports: "posiciones",
  compare: "cotizacion",
};

export function ProjectHub({
  project,
  orgId,
  canWrite,
  canRelease,
  isOwner,
  editable,
  disabled,
  onEdit,
  onClone,
  onChanged,
  onError,
  onNotice,
  onConflict,
  onDirtyChange,
}: {
  project: ProjectResponse;
  orgId: string;
  canWrite: boolean;
  canRelease: boolean;
  isOwner: boolean;
  editable: boolean;
  disabled: boolean;
  onEdit(): void;
  onClone(): void;
  onChanged(): Promise<unknown>;
  onError(message: string): void;
  onNotice(text: string): void;
  onConflict(): void;
  /** Which panel reports unsaved work — the workspace composes the global
   * unsaved-changes guard from these flags. */
  onDirtyChange(kind: "quote" | "payments" | "imports", dirty: boolean): void;
}): JSX.Element {
  const [params, setParams] = useSearchParams();

  const prep = useQuery({
    queryKey: ["project-documentary-inputs", orgId, project.id],
    queryFn: async () => {
      const response = await documentaryPrepareInputs(project.id, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
    // The panel tolerates a missing preparation (drafts without issued
    // revision) — the 404 is handled by the quotation panel itself, but
    // here it only feeds vigencia + position estado, so swallow it.
    retry: false,
    enabled: canWrite,
  });
  const prepByPosition = useMemo(() => {
    const map = new Map<string, DocumentaryPreparationPosition>();
    for (const position of prep.data?.positions ?? []) map.set(position.position_id, position);
    return map;
  }, [prep.data]);

  const rawTab = params.get("tab") ?? "";
  const rawSection = params.get("section") ?? "";
  const tab: HubTab = HUB_TABS.includes(rawTab as HubTab)
    ? (rawTab as HubTab)
    : rawSection && rawSection in SECTION_TO_TAB
      ? SECTION_TO_TAB[rawSection as FactsSection]
      : "posiciones";

  function setTab(next: HubTab): void {
    setParams(
      (current) => {
        const nextParams = new URLSearchParams(current);
        if (next === "posiciones") nextParams.delete("tab");
        else nextParams.set("tab", next);
        // The legacy section alias resolves once — the URL shows the tab
        // id from then on so shares keep working.
        nextParams.delete("section");
        return nextParams;
      },
      { replace: false },
    );
  }

  // Panels mount once per session — state inside the quote/payments flows
  // survives tab switches, and mounting lazily keeps cold tabs free of
  // queries the user never asked for.
  const [visited, setVisited] = useState<Set<HubTab>>(() => new Set([tab]));
  useEffect(() => {
    setVisited((current) => (current.has(tab) ? current : new Set(current).add(tab)));
  }, [tab]);

  const items: TabItem[] = HUB_TABS.map((id) => ({
    id,
    label: t(TAB_LABEL_KEYS[id]),
  }));

  const pricingRequest = usePricingRequest(orgId);

  function panel(id: HubTab, node: JSX.Element): JSX.Element {
    return (
      <div hidden={tab !== id} key={id} role="tabpanel">
        {visited.has(id) ? node : null}
      </div>
    );
  }

  return (
    <div className="project-hub">
      <ProjectHead
        canRelease={canRelease}
        canWrite={canWrite}
        disabled={disabled}
        editable={editable}
        onClone={onClone}
        onEdit={onEdit}
        onSection={(section) => setTab(SECTION_TO_TAB[section])}
        orgId={orgId}
        project={project}
        vigencia={prep.data?.quotation_valid_until}
      />
      <Tabs
        items={items}
        label={t("projects.tabsLabel")}
        onChange={(id) => setTab(id as HubTab)}
        value={tab}
      />

      {panel(
        "posiciones",
        <PositionsTab
          canOpenEditor={canWrite}
          disabled={disabled}
          editable={editable}
          onChanged={onChanged}
          onConflict={onConflict}
          onDirtyImports={(dirty) => onDirtyChange("imports", dirty)}
          onError={onError}
          onNotice={onNotice}
          orgId={orgId}
          prepByPosition={prepByPosition}
          project={project}
        />,
      )}
      {panel(
        "termico",
        <section aria-label={t("projects.tab.termico")} className="project-tab">
          <ProjectThermalPanel
            editable={editable && canWrite}
            onChanged={onChanged}
            onError={onError}
            orgId={orgId}
            project={project}
          />
        </section>,
      )}
      {panel(
        "servicios",
        <section aria-label={t("projects.tab.servicios")} className="project-tab">
          <ProjectServicesPanel canWrite={editable} orgId={orgId} projectId={project.id} />
        </section>,
      )}
      {panel(
        "cotizacion",
        <section aria-label={t("projects.tab.cotizacion")} className="project-tab">
          {canWrite && !editable && (
            <p className="project-locked" role="status">
              {t(project.status === "DRAFT" ? "projects.lockedPriced" : "projects.lockedQuoted")}
            </p>
          )}
          <ProjectQuotationPanel
            canRelease={canRelease}
            canWrite={canWrite}
            onChanged={onChanged}
            onDirtyChange={(dirty) => onDirtyChange("quote", dirty)}
            orgId={orgId}
            project={project}
          />
          <ProjectFacts editable={editable} onEdit={onEdit} project={project} />
          <RevisionComparePanel project={project} />
        </section>,
      )}
      {panel(
        "precio",
        <section aria-label={t("projects.tab.precio")} className="project-tab">
          <CommercialOperations
            boundProjectId={project.id}
            owner={isOwner}
            request={pricingRequest}
          />
        </section>,
      )}
      {panel(
        "cobranza",
        <section aria-label={t("projects.tab.cobranza")} className="project-tab">
          <ProjectPaymentsPanel
            canSendEnvio={canRelease}
            canWrite={canWrite}
            isOwner={isOwner}
            onDirtyChange={(dirty) => onDirtyChange("payments", dirty)}
            orgId={orgId}
            projectId={project.id}
          />
        </section>,
      )}
      {panel("produccion", <ProductionTab orgId={orgId} project={project} />)}
      {panel("documentos", <DocumentsTab onError={onError} orgId={orgId} project={project} />)}
      {panel("actividad", <ProjectActivity orgId={orgId} project={project} />)}
    </div>
  );
}
