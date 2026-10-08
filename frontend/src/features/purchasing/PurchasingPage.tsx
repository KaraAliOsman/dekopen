import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiMutator, ApiError } from "../../api/apiMutator";
import { PageHeader, useConfirm } from "../../ui";

import { documentaryArtifactAccess } from "../../api/generated/dekopen";
import type { OrderIndexItem } from "../../api/generated/models";
import { runJob } from "../jobs/runJob";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { DeniedState } from "../../ui";
import { fmtMm, fmtQty, formatMoney, shortTechnicalId } from "../../format";
import { t } from "../../i18n/es-CL";
import { domainLabel } from "../../i18n/domainLabels";
import { StatusChip } from "../../ui/StatusChip";
import { formatDateTime, formatRevision } from "../../format";
import { formatDate } from "../../format";
import "./purchasing.css";
import { EntityCode } from "../../ui/format";

type OrderType =
  "SUPPLIER_PROFILE_PO" | "SUPPLIER_GLASS_PO" | "SUPPLIER_HARDWARE_PO" | "SUPPLIER_PANEL_PO";
function categoryLabel(category: string): string {
  const key = `purchasing.categoryValue.${category}` as Parameters<typeof t>[0];
  const known: ReadonlySet<string> = new Set([
    "PROFILE",
    "REINFORCEMENT",
    "GLASS",
    "HARDWARE_KIT",
    "PANEL",
    "ACCESSORY",
    "FITTING",
  ]);
  return known.has(category) ? t(key) : category;
}

const unitPlural = new Intl.PluralRules("es-CL");
const UNIT_ALIAS: Record<string, string> = {
  UNIT: "EA",
  SET: "KIT",
  PIECE: "EA",
  PCS: "EA",
};

function purchaseUnitLabel(unit: string | null | undefined, qty?: number): string {
  if (!unit) return "";
  const normalized = UNIT_ALIAS[unit.toUpperCase()] ?? unit.toUpperCase();
  const known: ReadonlySet<string> = new Set(["EA", "BAR", "KIT", "SHEET", "M", "M2", "KG"]);
  if (!known.has(normalized)) return "";
  const plural = qty === undefined || unitPlural.select(qty) !== "one";
  return t(
    `purchasing.unitValue.${normalized}${plural ? ".other" : ".one"}` as Parameters<typeof t>[0],
  );
}

function qtyNumber(value: string | number | null | undefined): number | undefined {
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

const ORDER_TYPES: OrderType[] = [
  "SUPPLIER_PROFILE_PO",
  "SUPPLIER_GLASS_PO",
  "SUPPLIER_HARDWARE_PO",
  "SUPPLIER_PANEL_PO",
];

type Requirement = {
  id: string;
  requirement_key: string;
  order_type: OrderType;
  category: string;
  technical_skus: string[];
  purchasing_sku: string | null;
  physical_stock_identity: string | null;
  physical_stock_sku?: string | null;
  physical_stock_name?: string | null;
  unit: string;
  quantity: string;
  specification: Record<string, unknown>;
  source_trace: Array<string | Record<string, unknown>>;
  source_trace_labels?: Array<string | null>;
  // True while order lines cover the full required quantity; a cancelled
  // order releases its unreceived remainder, which comes back as open_qty.
  claimed?: boolean;
  open_qty?: number;
  // True once an allocation batch exists for this order_type — supplier and
  // price stay as sealed evidence (guard_confirmed_allocation blocks writes).
  sealed?: boolean;
};
type Eligibility = {
  id: string;
  order_type: OrderType;
  supplier_identity: string;
  supplier_name: string;
  eligible_requirement_keys: string[];
  version: number;
  expired?: boolean;
};
type Supplier = {
  id: string;
  tax_id: string;
  name: string;
  details?: Record<string, string>;
  updated_at?: string;
};
type Allocation = {
  id: string;
  requirement_line_id: string;
  supplier_eligibility_id: string;
  order_type: OrderType;
  unit_price?: string | null;
};
type OrderStatus = "DRAFT" | "SENT" | "PARTIALLY_RECEIVED" | "FULFILLED" | "CANCELLED";
type OrderLinePreview = {
  sku: string | null;
  qty: string;
  unit: string | null;
  unit_price?: string | null;
};
type Order = {
  id: string;
  order_code: string;
  order_type: OrderType;
  status: OrderStatus;
  supplier_name: string;
  order_snapshot_hash: string;
  expected_at?: string | null;
  sent_to?: string | null;
  sent_at?: string | null;
  cancelled_at?: string | null;
  supplier_details?: Record<string, unknown> | null;
  line_count?: string | null;
  total_qty?: string | null;
  released_qty?: string | null;
  damaged_qty?: string | null;
  receipt_count?: string | null;
  total_amount?: string | null;
  unpriced_lines?: number;
  lines_preview?: OrderLinePreview[];
};
const ORDER_STATUSES: OrderStatus[] = [
  "DRAFT",
  "SENT",
  "PARTIALLY_RECEIVED",
  "FULFILLED",
  "CANCELLED",
];
type ReceivingLine = {
  id: string;
  purchasing_sku: string | null;
  category: string;
  unit: string;
  ordered_qty: string;
  received_qty: string;
  damaged_qty: string;
  outstanding_qty: string;
};
type Quantities = Record<
  string,
  { received: string; damaged: string; lot_code: string; rack_location: string }
>;
type ReceivingState = {
  order: { id: string; status: OrderStatus };
  lines: ReceivingLine[];
  receipts: Array<{
    id: string;
    receipt_code: string;
    created_at: string;
    note: string | null;
    supplier_delivery_ref?: string | null;
    supplier_delivery_date?: string | null;
  }>;
};
type VersionItem = {
  id: string;
  project_id: string;
  project_code: string;
  revision_code: string;
  bom_hash: string;
  emitted_at: string;
};
type Version = VersionItem & { project_code: string; production_allowed: boolean };
type Blocker = { order_type: OrderType; code: string; requirement_keys?: string[] };
type CoverageLine = {
  requirement_line_id: string;
  order_type: string;
  category: string;
  purchasing_sku: string;
  unit: string;
  required: string;
  on_hand: string;
  reserved: string;
  available: string;
  ordered: string;
  received: string;
  open_ordered: string;
  remnant_pool?: { kind: string; count: number; total_mm?: string; key?: string } | null;
  shortage: string;
  recommended_purchase: string;
};
type Coverage = {
  version_id?: string;
  lines?: CoverageLine[];
  shortages?: number;
};
type PurchasingState = {
  versions?: VersionItem[];
  version?: Version;
  requirements?: Requirement[];
  eligibilities?: Eligibility[];
  allocations?: Allocation[];
  orders?: Order[];
  blockers?: Blocker[];
  coverage?: Coverage;
};

type RequestFn = <T>(path: string, method?: string, body?: unknown) => Promise<T>;

// Codes mirror backend/purchasing/service.py purchasing_state blockers exactly.
const blockerLabels: Record<string, Parameters<typeof t>[0]> = {
  SUPPLIER_ELIGIBILITY_REQUIRED: "purchasing.blockerEligibilityRequired",
  ALLOCATION_REQUIRED: "purchasing.blockerAllocationRequired",
};

function usePurchasingRequest(orgId: string): {
  request: RequestFn;
  lifetime: { current: AbortController };
} {
  const lifetime = useRef(new AbortController());
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);
  const request = useCallback(
    async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
      const response = await apiMutator<{ data: T }>(`/api/v1/${path}`, {
        method,
        signal: lifetime.current.signal,
        headers: {
          "X-Organization-ID": orgId,
          "Content-Type": "application/json",
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      return response.data;
    },
    [orgId],
  );
  return { request, lifetime };
}

export function PurchasingPage(): JSX.Element {
  const org = useAuthSession().me?.active_organization;
  const [query] = useSearchParams();
  if (!org || !["OWNER", "WORKSHOP_MANAGER", "ESTIMATOR"].includes(org.role))
    return <DeniedState reason={t("purchasing.denied")} />;
  const initialVersionId = query.get("version") ?? "";
  return (
    <PurchasingWorkspace
      key={`${org.id}:${initialVersionId}`}
      orgId={org.id}
      role={org.role}
      initialVersionId={initialVersionId}
    />
  );
}

function traceLine(entry: Record<string, unknown>): string {
  return Object.entries(entry)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(" · ");
}

// Mirrors backend/documents/artifacts.py _DOCUMENT_ROLES exactly: a visible
// action must never deterministically fail with document_access_denied.
const DOCUMENT_ROLES: Record<string, string[]> = {
  "DOC-01": ["OWNER", "ESTIMATOR"],
  "DOC-02": ["OWNER", "WORKSHOP_MANAGER"],
  "DOC-03": ["OWNER", "WORKSHOP_MANAGER"],
  "DOC-04": ["OWNER", "WORKSHOP_MANAGER"],
  "DOC-05": ["OWNER", "WORKSHOP_MANAGER"],
  "DOC-06": ["OWNER", "WORKSHOP_MANAGER"],
  "DOC-07": ["OWNER"],
  "DOC-08": ["OWNER", "WORKSHOP_MANAGER"],
};

type DocumentAction = { type: string; format: string; label: Parameters<typeof t>[0] };

function orderDocuments(order: Order, role: string): DocumentAction[] {
  let docs: DocumentAction[] = [];
  if (order.order_type === "SUPPLIER_GLASS_PO")
    docs = [
      { type: "DOC-02", format: "PDF", label: "purchasing.doc02Pdf" },
      { type: "DOC-02", format: "XLSX", label: "purchasing.doc02" },
    ];
  else if (order.order_type === "SUPPLIER_PROFILE_PO")
    docs = [
      { type: "DOC-04", format: "PDF", label: "purchasing.doc04Pdf" },
      { type: "DOC-04", format: "XLSX", label: "purchasing.doc04Xlsx" },
    ];
  else if (order.order_type === "SUPPLIER_HARDWARE_PO" || order.order_type === "SUPPLIER_PANEL_PO")
    docs = [
      { type: "DOC-08", format: "PDF", label: "purchasing.doc08Pdf" },
      { type: "DOC-08", format: "XLSX", label: "purchasing.doc08Xlsx" },
    ];
  return docs.filter((doc) => DOCUMENT_ROLES[doc.type]?.includes(role) === true);
}

function revisionDocuments(role: string): DocumentAction[] {
  return (
    [
      { type: "DOC-01", format: "PDF", label: "purchasing.doc01" },
      { type: "DOC-03", format: "PDF", label: "purchasing.doc03" },
      { type: "DOC-05", format: "PDF", label: "purchasing.doc05" },
      { type: "DOC-06", format: "PDF", label: "purchasing.doc06" },
      { type: "DOC-07", format: "PDF", label: "purchasing.doc07" },
    ] as DocumentAction[]
  ).filter((doc) => DOCUMENT_ROLES[doc.type]?.includes(role) === true);
}

function PurchasingWorkspace({
  orgId,
  role,
  initialVersionId,
}: {
  orgId: string;
  role: string;
  initialVersionId: string;
}): JSX.Element {
  const { request } = usePurchasingRequest(orgId);
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [ordersIndex, setOrdersIndex] = useState<OrderIndexItem[]>([]);
  const [indexStatus, setIndexStatus] = useState<string>("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [versionId, setVersionId] = useState(initialVersionId);
  const [state, setState] = useState<PurchasingState | null>(null);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const canWrite = role === "WORKSHOP_MANAGER" || role === "OWNER";
  // Independent side-loads fail per-section, not into a fake empty state.
  const [failedSections, setFailedSections] = useState<ReadonlySet<string>>(new Set());
  function markSection(section: string, failed: boolean): void {
    setFailedSections((previous) => {
      const next = new Set(previous);
      if (failed) next.add(section);
      else next.delete(section);
      return next;
    });
  }
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let current = true;
    setBusy(true);
    setMessage("");
    void request<{ versions?: VersionItem[] }>("purchasing/versions/")
      .then((data) => {
        void request<{ orders?: OrderIndexItem[] }>("purchasing/orders/")
          .then((indexData) => {
            if (current) {
              setOrdersIndex(indexData.orders ?? []);
              markSection("orders", false);
            }
          })
          .catch(() => {
            if (current) {
              setOrdersIndex([]);
              markSection("orders", true);
            }
          });
        void request<{ suppliers?: Supplier[] }>("purchasing/suppliers/")
          .then((supplierData) => {
            if (current) {
              setSuppliers(supplierData.suppliers ?? []);
              markSection("suppliers", false);
            }
          })
          .catch(() => {
            if (current) {
              setSuppliers([]);
              markSection("suppliers", true);
            }
          });

        if (!current) return;
        const list = data.versions ?? [];
        setVersions(list);
        setVersionId((previous) =>
          list.some((item) => item.id === previous) ? previous : (list[0]?.id ?? ""),
        );
        if (list.length === 0) setBusy(false);
      })
      .catch(() => {
        if (current) {
          setMessage(t("purchasing.loadError"));
          setBusy(false);
        }
      });
    return () => {
      current = false;
    };
  }, [request, revision]);

  useEffect(() => {
    if (!versionId) return;
    let current = true;
    setBusy(true);
    setMessage("");
    void request<PurchasingState>(`purchasing/versions/${versionId}/`)
      .then((data) => {
        if (current) setState(data);
      })
      .catch(() => {
        if (current) {
          setState(null);
          setMessage(t("purchasing.loadError"));
        }
      })
      .finally(() => {
        if (current) setBusy(false);
      });
    return () => {
      current = false;
    };
  }, [request, versionId, revision]);

  async function action(task: Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setMessage("");
    try {
      await task;
      return true;
    } catch (error) {
      if (mounted.current) {
        const detail =
          error instanceof ApiError && typeof error.payload === "object" && error.payload !== null
            ? (error.payload as { error?: { detail?: unknown; code?: unknown } }).error
            : undefined;
        setMessage(
          typeof detail?.detail === "string" && detail.detail
            ? detail.detail
            : t("purchasing.actionError"),
        );
      }
      return false;
    } finally {
      if (mounted.current) {
        setBusy(false);
        setRevision((value) => value + 1);
      }
    }
  }

  async function openDocument(
    documentType: string,
    format: string,
    orderId?: string,
  ): Promise<void> {
    if (!state?.version) return;
    // The artifact resolves after an async job — opening the tab inside the
    // click gesture keeps it out of the popup blocker; a synchronous
    // window.open(url) at resolve time would be silently swallowed.
    const tab = window.open("", "_blank");
    setMessage("");
    try {
      setMessage(t("purchasing.documentGenerating"));
      const job = await runJob(
        {
          type: "document.artifact.generate",
          payload: {
            document_type: documentType,
            format,
            project_version_id: state.version.id,
            order_id: orderId ?? null,
          },
          idempotency_key: `${documentType.toLowerCase()}:${format.toLowerCase()}:${state.version.id}:${orderId ?? ""}`,
        },
        { headers: { "X-Organization-ID": orgId } },
      );
      const artifact = (job.result as { artifact: { id: string } }).artifact;
      const access = await documentaryArtifactAccess(artifact.id, {
        headers: { "X-Organization-ID": orgId },
      });
      if (access.status !== 200) throw new ApiError(access.status, access.data);
      if (tab) tab.location.href = access.data.signed_url;
      else window.open(access.data.signed_url, "_blank", "noopener,noreferrer");
      setMessage("");
    } catch {
      tab?.close();
      if (mounted.current) setMessage(t("purchasing.documentError"));
    }
  }

  const requirements = state?.requirements ?? [];
  const eligibilities = state?.eligibilities ?? [];
  const allocations = state?.allocations ?? [];
  const orders = state?.orders ?? [];
  const blockers = state?.blockers ?? [];
  const coverage = state?.coverage;
  const coverageLines = coverage?.lines ?? [];
  const confirmedTypes = new Set(
    requirements.length > 0
      ? ORDER_TYPES.filter(
          (orderType) =>
            requirements.some((item) => item.order_type === orderType) &&
            requirements
              .filter((item) => item.order_type === orderType)
              .every((item) => item.claimed === true),
        )
      : orders.filter((order) => order.status !== "CANCELLED").map((order) => order.order_type),
  );

  return (
    <section className="purchasing-page">
      <PageHeader
        crumbs={[{ label: t("nav.projects"), to: "/projects" }, { label: t("purchasing.title") }]}
        context={t("purchasing.subtitle")}
        title={t("purchasing.title")}
      />
      {message && <p role="alert">{message}</p>}
      {busy && <p role="status">{t("purchasing.loading")}</p>}
      {!busy && versions.length === 0 && <p>{t("purchasing.empty")}</p>}
      <OrdersIndex
        orders={ordersIndex}
        loadFailed={failedSections.has("orders")}
        status={indexStatus}
        onStatus={setIndexStatus}
        onOpen={(order) => {
          if (order.project_version_id) setVersionId(order.project_version_id);
        }}
      />
      <SupplierDirectory suppliers={suppliers} orders={ordersIndex} />
      {versions.length > 0 && (
        <label>
          {t("purchasing.chooseVersion")}
          <select
            value={versionId}
            disabled={busy}
            onChange={(event) => setVersionId(event.target.value)}
          >
            {versions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.project_code} · {formatRevision(item.revision_code)} ·{" "}
                {formatDateTime(item.emitted_at)}
              </option>
            ))}
          </select>
        </label>
      )}
      {state?.version && (
        <p className="purchasing-version">
          {t("purchasing.project")}: <strong>{state.version.project_code}</strong> ·{" "}
          {formatRevision(state.version.revision_code)} · {t("purchasing.immutable")}
        </p>
      )}
      {coverageLines.length > 0 &&
        (() => {
          // §1 at-a-glance: shortages and next incoming answer "what's missing
          // and when does it land" before the operator reads a single row.
          // "Sin stock" is the raw fact (required − on hand); "Por comprar" is
          // the actionable number (net of stock AND open orders) — the red
          // state belongs on the number a buyer can still act on, so a fully
          // ordered line stops flagging red.
          const shortLines = coverageLines.filter((line) => line.shortage !== "0");
          const recommended = coverageLines.filter((line) => line.recommended_purchase !== "0");
          const openOrders = orders.filter(
            (order) => order.status !== "FULFILLED" && order.status !== "CANCELLED",
          );
          const nextExpected = openOrders
            .map((order) => order.expected_at)
            .filter((value): value is string => Boolean(value))
            .sort()[0];
          return (
            <section className="purchasing-glance" aria-label={t("purchasing.glanceTitle")}>
              <div className="purchasing-glance-cell">
                <strong>{shortLines.length}</strong>
                <span>{t("purchasing.glanceShort")}</span>
              </div>
              <div
                className={
                  recommended.length ? "purchasing-glance-cell is-short" : "purchasing-glance-cell"
                }
              >
                <strong>{recommended.length}</strong>
                <span>{t("purchasing.glanceBuying")}</span>
              </div>
              <div className="purchasing-glance-cell">
                <strong>{openOrders.length}</strong>
                <span>{t("purchasing.glanceIncoming")}</span>
              </div>
              <div className="purchasing-glance-cell">
                <strong>{nextExpected ? formatDate(nextExpected) : "—"}</strong>
                <span>{t("purchasing.glanceNext")}</span>
              </div>
            </section>
          );
        })()}
      {blockers.length > 0 && (
        <section
          className="purchasing-blockers"
          aria-label={t("purchasing.blockers")}
          role="status"
        >
          <h2>{t("purchasing.blockers")}</h2>
          <ul>
            {blockers.map((blocker, index) => (
              <li key={index} role="alert">
                <button
                  type="button"
                  className="purchasing-blocker-link"
                  onClick={() => {
                    // SUPPLIER_ELIGIBILITY_REQUIRED resolves in the eligibility
                    // form for that order type; ALLOCATION_REQUIRED resolves in
                    // the requirement table. Open/scroll to the right surface.
                    const details =
                      blocker.code === "SUPPLIER_ELIGIBILITY_REQUIRED"
                        ? document.getElementById(`purchasing-eligibility-${blocker.order_type}`)
                        : null;
                    if (details instanceof HTMLDetailsElement) {
                      details.open = true;
                    }
                    (
                      details ?? document.getElementById(`purchasing-type-${blocker.order_type}`)
                    )?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                >
                  {domainLabel("OrderTypeEnum", blocker.order_type).label} ·{" "}
                  {t(blockerLabels[blocker.code] ?? "purchasing.blockers")}
                  {blocker.requirement_keys?.length
                    ? ` · ${blocker.requirement_keys.length} ${t("purchasing.requirements")}`
                    : ""}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {coverageLines.length > 0 && (
        <section
          className="purchasing-coverage"
          aria-label={t("purchasing.coverageTitle")}
          role="status"
        >
          <h2>{t("purchasing.coverageTitle")}</h2>
          {(coverage?.shortages ?? 0) > 0 && (
            <p className="purchasing-coverage-alert" role="alert">
              {t("purchasing.coverageShortages")}: {coverage?.shortages}
            </p>
          )}
          <table>
            <thead>
              <tr>
                <th>{t("purchasing.category")}</th>
                <th>{t("purchasing.purchaseSku")}</th>
                <th>{t("purchasing.coverageRequired")}</th>
                <th>{t("purchasing.coverageOnHand")}</th>
                <th>{t("purchasing.coverageReserved")}</th>
                <th>{t("purchasing.coverageOrdered")}</th>
                <th>{t("purchasing.coverageReceived")}</th>
                <th>{t("purchasing.coverageRemnant")}</th>
                <th>{t("purchasing.coverageShortage")}</th>
                <th>{t("purchasing.coverageRecommended")}</th>
              </tr>
            </thead>
            <tbody>
              {coverageLines.map((line) => (
                <tr key={line.requirement_line_id}>
                  <td>{categoryLabel(line.category)}</td>
                  <td>
                    <EntityCode value={line.purchasing_sku} />
                    <span className="purchasing-coverage-unit">
                      {" "}
                      {purchaseUnitLabel(line.unit, 2)}
                    </span>
                  </td>
                  <td>{fmtQty(line.required)}</td>
                  <td>{fmtQty(line.on_hand)}</td>
                  <td>{fmtQty(line.reserved)}</td>
                  <td>{fmtQty(line.open_ordered)}</td>
                  <td>
                    {line.received !== "0" ? (
                      <strong className="purchasing-coverage-received">
                        {fmtQty(line.received)} · {t("purchasing.receivedMark")}
                      </strong>
                    ) : (
                      fmtQty(line.received)
                    )}
                  </td>
                  <td>
                    {line.remnant_pool
                      ? `${line.remnant_pool.count}${
                          line.remnant_pool.total_mm
                            ? ` · ${fmtMm(line.remnant_pool.total_mm)} mm`
                            : ""
                        }`
                      : "—"}
                  </td>
                  <td>
                    {line.shortage !== "0" ? (
                      <strong className="purchasing-coverage-short">{fmtQty(line.shortage)}</strong>
                    ) : (
                      "0"
                    )}
                  </td>
                  <td>{fmtQty(line.recommended_purchase)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {canWrite &&
            coverageLines.some(
              (line) => (qtyNumber(line.shortage) ?? 0) > 0 && line.remnant_pool?.key,
            ) && (
              <section className="purchasing-remnant-offers">
                <h3>{t("purchasing.remnantOffer")}</h3>
                <p className="purchasing-hint">{t("purchasing.remnantOfferHint")}</p>
                {coverageLines
                  .filter((line) => (qtyNumber(line.shortage) ?? 0) > 0 && line.remnant_pool?.key)
                  .map((line) => (
                    <RemnantOffer
                      key={line.requirement_line_id}
                      line={line}
                      busy={busy}
                      request={request}
                      action={action}
                    />
                  ))}
              </section>
            )}
        </section>
      )}
      {state?.version &&
        ORDER_TYPES.map((orderType) => (
          <RequirementSection
            key={orderType}
            orderType={orderType}
            requirements={requirements.filter((item) => item.order_type === orderType)}
            eligibilities={eligibilities.filter((item) => item.order_type === orderType)}
            allocations={allocations}
            confirmed={confirmedTypes.has(orderType)}
            canWrite={canWrite}
            busy={busy}
            versionId={state.version!.id}
            request={request}
            action={action}
            suppliers={suppliers}
            suppliersFailed={failedSections.has("suppliers")}
          />
        ))}
      {state?.version && (
        <section className="purchasing-orders">
          <h2>{t("purchasing.orders")}</h2>
          {orders.length === 0 && <p>{t("purchasing.noOrders")}</p>}
          {orders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              role={role}
              canWrite={canWrite}
              busy={busy}
              request={request}
              action={action}
              onDocument={(type, format) => void openDocument(type, format, order.id)}
            />
          ))}
        </section>
      )}
      {/* El material físico vive en /inventory — Compras decide qué falta,
        a quién pedírselo y cuándo llega; el qué hay se mira allá. */}
      <p className="purchasing-inventory-link">
        {t("purchasing.inventoryLink")}{" "}
        <Link to="/inventory">{t("purchasing.inventoryLinkCta")}</Link>.
      </p>
      {state?.version && (
        <section className="purchasing-documents">
          <h2>{t("purchasing.documents")}</h2>
          <ul>
            {revisionDocuments(role).map((doc) => (
              <li key={`${doc.type}-${doc.format}`}>
                <span>{t(doc.label)}</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void openDocument(doc.type, doc.format)}
                >
                  {t("purchasing.openDocument")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}

function RequirementSection({
  orderType,
  requirements,
  eligibilities,
  allocations,
  confirmed,
  canWrite,
  busy,
  versionId,
  request,
  action,
  suppliers,
  suppliersFailed,
}: {
  orderType: OrderType;
  requirements: Requirement[];
  eligibilities: Eligibility[];
  allocations: Allocation[];
  confirmed: boolean;
  canWrite: boolean;
  busy: boolean;
  versionId: string;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
  suppliers: Supplier[];
  suppliersFailed?: boolean;
}): JSX.Element {
  const [attested, setAttested] = useState(false);
  const allocatedIds = new Set(allocations.map((item) => item.requirement_line_id));
  // Only lines released from a cancelled order need allocating again — claimed
  // lines already sit on a live order.
  const pending = requirements.filter((item) => item.claimed !== true);
  const allAllocated = pending.length > 0 && pending.every((item) => allocatedIds.has(item.id));
  return (
    <section className="purchasing-type" id={`purchasing-type-${orderType}`}>
      <h2>
        {domainLabel("OrderTypeEnum", orderType).label}
        {confirmed && <span className="purchasing-badge">{t("purchasing.confirmedBadge")}</span>}
      </h2>
      {requirements.length === 0 && <p>{t("purchasing.noRequirements")}</p>}
      {requirements.length > 0 &&
        new Set(requirements.map((item) => item.purchasing_sku)).size < requirements.length && (
          <p className="purchasing-order-expected">{t("purchasing.consolidateHint")}</p>
        )}
      {requirements.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("purchasing.category")}</th>
              <th>{t("purchasing.technicalSku")}</th>
              <th>{t("purchasing.purchaseSku")}</th>
              <th>{t("purchasing.quantity")}</th>
              <th>{t("purchasing.allocatedTo")}</th>
              <th>{t("purchasing.trace")}</th>
            </tr>
          </thead>
          <tbody>
            {requirements.map((requirement) => (
              <RequirementRow
                key={requirement.id}
                requirement={requirement}
                eligibilities={eligibilities.filter((item) =>
                  item.eligible_requirement_keys.includes(requirement.requirement_key),
                )}
                allocation={allocations.find((item) => item.requirement_line_id === requirement.id)}
                canWrite={canWrite}
                busy={busy}
                request={request}
                action={action}
              />
            ))}
          </tbody>
        </table>
      )}
      {!confirmed && canWrite && (
        <>
          <EligibilityForm
            orderType={orderType}
            requirements={requirements}
            eligibilities={eligibilities}
            busy={busy}
            versionId={versionId}
            request={request}
            action={action}
            suppliers={suppliers}
            suppliersFailed={suppliersFailed}
          />
          {pending.length > 0 && (
            <form
              noValidate
              className="purchasing-confirm"
              onSubmit={(event) => {
                event.preventDefault();
                void action(
                  request(`purchasing/versions/${versionId}/confirm/`, "POST", {
                    order_type: orderType,
                    confirmed: true,
                  }),
                );
              }}
            >
              <h3>{t("purchasing.confirmBatch")}</h3>
              <p>{t("purchasing.confirmBatchHint")}</p>
              <label>
                <input
                  type="checkbox"
                  checked={attested}
                  disabled={busy || !allAllocated}
                  onChange={(event) => setAttested(event.target.checked)}
                />
                {t("purchasing.confirmCheckbox")}
              </label>
              <button type="submit" disabled={busy || !attested || !allAllocated}>
                {t("purchasing.confirm")}
              </button>
            </form>
          )}
        </>
      )}
    </section>
  );
}

function RequirementRow({
  requirement,
  eligibilities,
  allocation,
  canWrite,
  busy,
  request,
  action,
}: {
  requirement: Requirement;
  eligibilities: Eligibility[];
  allocation: Allocation | undefined;
  canWrite: boolean;
  busy: boolean;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
}): JSX.Element {
  const allocated = eligibilities.find((item) => item.id === allocation?.supplier_eligibility_id);
  // Precio acordado por línea: se edita en la propuesta y el confirmar lo
  // sella dentro de la OC — la OC nunca se deriva de precios posteriores.
  const [price, setPrice] = useState(allocation?.unit_price ?? "");
  useEffect(() => {
    setPrice(allocation?.unit_price ?? "");
  }, [allocation?.unit_price]);

  function savePrice(): void {
    if (!allocation || !canWrite || requirement.claimed || requirement.sealed) return;
    const value = price.trim();
    if (value === (allocation.unit_price ?? "")) return;
    void action(
      request(`purchasing/requirements/${requirement.id}/allocation/`, "PUT", {
        supplier_eligibility_id: allocation.supplier_eligibility_id,
        unit_price: value === "" ? null : value,
      }),
    );
  }
  return (
    <tr>
      <td>{categoryLabel(requirement.category)}</td>
      <td>{requirement.technical_skus.join(", ") || "—"}</td>
      <td>
        {requirement.purchasing_sku ?? "—"}
        {requirement.physical_stock_identity && (
          <small>
            {t("purchasing.stock")}:{" "}
            {requirement.physical_stock_sku || requirement.physical_stock_name
              ? [requirement.physical_stock_sku, requirement.physical_stock_name]
                  .filter(Boolean)
                  .join(" · ")
              : t("purchasing.stockUnassigned")}
          </small>
        )}
      </td>
      <td>
        {requirement.open_qty !== undefined &&
        requirement.open_qty > 0 &&
        requirement.open_qty < (qtyNumber(requirement.quantity) ?? requirement.open_qty) ? (
          <>
            {fmtQty(requirement.open_qty)}{" "}
            {purchaseUnitLabel(requirement.unit, requirement.open_qty)}
            <br />
            <small>
              {t("purchasing.pendingOf")} {fmtQty(requirement.quantity)}
            </small>
          </>
        ) : (
          <>
            {fmtQty(requirement.quantity)}{" "}
            {purchaseUnitLabel(requirement.unit, qtyNumber(requirement.quantity))}
          </>
        )}
      </td>
      <td>
        {requirement.claimed === true || requirement.sealed === true || !canWrite ? (
          <>
            {allocated?.supplier_name ?? "—"}
            {requirement.sealed === true && requirement.claimed !== true ? (
              <small className="purchasing-hint">
                <br />
                {t("purchasing.allocationSealed")}
              </small>
            ) : null}
          </>
        ) : (
          <select
            aria-label={t("purchasing.chooseSupplier")}
            disabled={busy || eligibilities.length === 0}
            value={allocation?.supplier_eligibility_id ?? ""}
            onChange={(event) => {
              if (!event.target.value) return;
              void action(
                request(`purchasing/requirements/${requirement.id}/allocation/`, "PUT", {
                  supplier_eligibility_id: event.target.value,
                  unit_price: price.trim() === "" ? null : price.trim(),
                }),
              );
            }}
          >
            <option value="">
              {eligibilities.length === 0
                ? t("purchasing.noEligibility")
                : t("purchasing.chooseSupplier")}
            </option>
            {eligibilities
              // A supplier re-declared at a newer version supersedes the
              // older rows — offering both would allocate against stale data.
              // Expired evidence is unallocatable by the backend too.
              .filter(
                (item) =>
                  !item.expired &&
                  item.version ===
                    Math.max(
                      0,
                      ...eligibilities
                        .filter((o) => o.supplier_identity === item.supplier_identity)
                        .map((o) => o.version),
                    ),
              )
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.supplier_name} · v{item.version}
                </option>
              ))}
          </select>
        )}
        {allocation ? (
          <div className="purchasing-price">
            {requirement.claimed === true || requirement.sealed === true || !canWrite ? (
              allocation.unit_price ? (
                <small>
                  {t("purchasing.unitPrice")}: {formatMoney(allocation.unit_price, "CLP")}
                </small>
              ) : (
                <small className="purchasing-hint">—</small>
              )
            ) : (
              <input
                type="number"
                min="0"
                step="any"
                aria-label={`${t("purchasing.unitPrice")} · ${requirement.purchasing_sku ?? requirement.category}`}
                title={t("purchasing.unitPriceHint")}
                placeholder={t("purchasing.unitPriceMissing")}
                disabled={busy}
                value={price}
                onChange={(event) => setPrice(event.target.value)}
                onBlur={savePrice}
                onKeyDown={(event) => {
                  if (event.key === "Enter") (event.target as HTMLInputElement).blur();
                }}
              />
            )}
          </div>
        ) : null}
      </td>
      <td>
        <details>
          <summary>{t("purchasing.trace")}</summary>
          {requirement.source_trace.length === 0 && <p>{t("purchasing.noTrace")}</p>}
          <ul>
            {requirement.source_trace.map((entry, index) => {
              const raw = typeof entry === "string" ? entry : traceLine(entry);
              const label = requirement.source_trace_labels?.[index];
              const shown = label ?? shortTechnicalId(raw);
              return (
                <li key={index} title={shown === raw ? undefined : raw}>
                  {shown}
                </li>
              );
            })}
          </ul>
        </details>
      </td>
    </tr>
  );
}

function EligibilityForm({
  orderType,
  requirements,
  eligibilities,
  busy,
  versionId,
  request,
  action,
  suppliers,
  suppliersFailed,
}: {
  orderType: OrderType;
  requirements: Requirement[];
  eligibilities: Eligibility[];
  busy: boolean;
  versionId: string;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
  suppliers: Supplier[];
  suppliersFailed?: boolean;
}): JSX.Element {
  const nextVersion = Math.max(0, ...eligibilities.map((item) => item.version)) + 1;
  return (
    <details className="purchasing-eligibility" id={`purchasing-eligibility-${orderType}`}>
      <summary>{t("purchasing.eligibilities")}</summary>
      {eligibilities.map((item) => (
        <p key={item.id}>
          {item.supplier_name} · v{item.version} · {item.eligible_requirement_keys.length}{" "}
          {t("purchasing.requirements")}
          {item.expired && (
            <span className="purchasing-badge purchasing-badge--expired">
              {" "}
              {t("purchasing.supplierExpired")}
            </span>
          )}
        </p>
      ))}
      {requirements.length > 0 && (
        <form
          noValidate
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const keys = requirements
              .filter((item) => data.get(`key_${item.id}`) === "on")
              .map((item) => item.requirement_key)
              .sort();
            void action(
              request(`purchasing/versions/${versionId}/eligibilities/`, "POST", {
                order_type: orderType,
                supplier_identity: data.get("supplier_identity"),
                supplier_name: data.get("supplier_name"),
                supplier_details: {
                  tax_id: data.get("tax_id") || undefined,
                  email: data.get("email") || undefined,
                  phone: data.get("phone") || undefined,
                  address: data.get("address") || undefined,
                },
                eligible_requirement_keys: keys,
                evidence: {
                  basis: data.get("basis"),
                  reference: data.get("reference") || undefined,
                  valid_until: data.get("valid_until") || null,
                },
                version: nextVersion,
                confirmed: true,
              }),
            );
          }}
        >
          <h3>{t("purchasing.newEligibility")}</h3>
          {suppliersFailed ? <p role="alert">{t("purchasing.suppliersLoadError")}</p> : null}
          <label>
            {t("purchasing.supplierIdentity")}
            <input
              name="supplier_identity"
              required
              maxLength={200}
              disabled={busy}
              list="purchasing-suppliers"
              onChange={(event) => {
                const entry = suppliers.find((item) => item.tax_id === event.target.value);
                if (!entry) return;
                const form = event.target.form;
                if (!form) return;
                const fill = (key: string, value: string) => {
                  const input = form.elements.namedItem(key) as HTMLInputElement | null;
                  if (input) input.value = value;
                };
                fill("supplier_name", entry.name);
                fill("tax_id", entry.details?.tax_id ?? "");
                fill("email", entry.details?.email ?? "");
                fill("phone", entry.details?.phone ?? "");
                fill("address", entry.details?.address ?? "");
              }}
            />
            <datalist id="purchasing-suppliers">
              {suppliers.map((item) => (
                <option key={item.id} value={item.tax_id}>
                  {item.name}
                </option>
              ))}
            </datalist>
          </label>
          <label>
            {t("purchasing.supplierName")}
            <input name="supplier_name" required maxLength={300} disabled={busy} />
          </label>
          <label>
            {t("purchasing.taxId")}
            <input name="tax_id" maxLength={100} disabled={busy} />
          </label>
          <label>
            {t("purchasing.email")}
            <input name="email" type="email" disabled={busy} />
          </label>
          <label>
            {t("purchasing.phone")}
            <input name="phone" maxLength={100} disabled={busy} />
          </label>
          <label>
            {t("purchasing.address")}
            <input name="address" maxLength={1000} disabled={busy} />
          </label>
          <label>
            {t("purchasing.basis")}
            <input name="basis" required maxLength={2000} disabled={busy} />
          </label>
          <label>
            {t("purchasing.reference")}
            <input name="reference" maxLength={500} disabled={busy} />
          </label>
          <label>
            {t("purchasing.validUntil")}
            <input name="valid_until" type="date" disabled={busy} />
          </label>
          <fieldset disabled={busy}>
            <legend>{t("purchasing.requirements")}</legend>
            {requirements.map((item) => (
              <label key={item.id}>
                <input type="checkbox" name={`key_${item.id}`} defaultChecked />
                {categoryLabel(item.category)} ·{" "}
                {item.purchasing_sku ??
                  (item.technical_skus.join(", ") || shortTechnicalId(item.requirement_key))}
              </label>
            ))}
          </fieldset>
          <button type="submit" disabled={busy}>
            {t("purchasing.createEligibility")}
          </button>
        </form>
      )}
    </details>
  );
}

function OrderCard({
  order,
  role,
  canWrite,
  busy,
  request,
  action,
  onDocument,
}: {
  order: Order;
  role: string;
  canWrite: boolean;
  busy: boolean;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
  onDocument: (type: string, format: string) => void;
}): JSX.Element {
  const [attested, setAttested] = useState(false);
  const [expectedAt, setExpectedAt] = useState("");
  const [mailNote, setMailNote] = useState<string | null>(null);
  const supplierEmail =
    typeof order.supplier_details?.email === "string" ? order.supplier_details.email : "";
  const [sentTo, setSentTo] = useState(supplierEmail);
  // Alias antes del JSX: `{x.status}` en llaves lo caza el guard ui-raw-status.
  const orderStatus = order.status;
  return (
    <article className={`purchasing-order purchasing-order-${orderStatus.toLowerCase()}`}>
      <header>
        <strong>{order.order_code}</strong>
        <span>
          {domainLabel("OrderTypeEnum", order.order_type).label} · {order.supplier_name} ·{" "}
          <StatusChip enumName="OrderStatusEnum" value={orderStatus} />
        </span>
      </header>
      {order.lines_preview && order.lines_preview.length > 0 && (
        <ul className="purchasing-order-lines">
          {order.lines_preview.map((line, index) => (
            <li key={index}>
              <EntityCode value={line.sku} /> × {fmtQty(line.qty)}{" "}
              {purchaseUnitLabel(line.unit, qtyNumber(line.qty))}
              {line.unit_price ? ` · ${formatMoney(line.unit_price, "CLP")}` : ""}
            </li>
          ))}
        </ul>
      )}
      {(order.total_amount || (order.unpriced_lines ?? 0) > 0) && (
        <p className="purchasing-order-total">
          {order.total_amount ? (
            <>
              {t("purchasing.orderTotal")}:{" "}
              <strong>{formatMoney(order.total_amount, "CLP")}</strong>
            </>
          ) : null}
          {(order.unpriced_lines ?? 0) > 0 ? (
            <small className="purchasing-hint">
              {" "}
              · {order.unpriced_lines} {t("purchasing.orderUnpriced")}
            </small>
          ) : null}
        </p>
      )}
      {(order.expected_at || order.sent_to) && (
        <p className="purchasing-order-expected">
          {order.expected_at
            ? `${t("purchasing.expectedAt")}: ${formatDate(order.expected_at)}`
            : ""}
          {order.expected_at && order.sent_to ? " · " : ""}
          {order.sent_to ? `${t("purchasing.sentTo")}: ${order.sent_to}` : ""}
        </p>
      )}
      {order.status === "CANCELLED" && order.cancelled_at && (
        <p className="purchasing-order-expected">
          {t("purchasing.cancelledAt")}: {formatDateTime(order.cancelled_at)}
          {order.released_qty && order.released_qty !== "0" && (
            <>
              {" · "}
              {t("purchasing.cancelledReleased")}: {fmtQty(order.released_qty)}
            </>
          )}
        </p>
      )}
      {order.status === "CANCELLED" && (
        <p className="purchasing-order-expected">
          <button
            type="button"
            className="purchasing-blocker-link"
            onClick={() =>
              document
                .getElementById(`purchasing-type-${order.order_type}`)
                ?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
          >
            {t("purchasing.reorderCta")}
          </button>{" "}
          {t("purchasing.reorderHint")}
        </p>
      )}
      {Number(order.damaged_qty ?? "0") > 0 && (
        <p className="purchasing-order-damaged" role="alert">
          {t("purchasing.damagedIncidence")}: {fmtQty(order.damaged_qty)}
        </p>
      )}
      {order.status === "DRAFT" && canWrite && (
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            // El correo al proveedor va por el outbox en la misma llamada —
            // su estado vuelve en la respuesta (sandbox por defecto; SMTP
            // real se activa en docs/operations/ACTIVACION.md).
            void action(
              request<{ mail?: { status: string } | null }>(
                `purchasing/orders/${order.id}/send/`,
                "POST",
                {
                  confirmed: true,
                  expected_at: expectedAt || null,
                  sent_to: sentTo.trim() || null,
                },
              ).then((output) => {
                const mail = output?.mail;
                setMailNote(
                  mail == null
                    ? null
                    : mail.status === "SKIPPED"
                      ? t("purchasing.mailSkipped")
                      : t("purchasing.mailSent"),
                );
                return output;
              }),
            );
          }}
        >
          <label>
            {t("purchasing.expectedAt")}
            <input
              type="date"
              value={expectedAt}
              disabled={busy}
              onChange={(event) => setExpectedAt(event.target.value)}
            />
          </label>
          <label>
            {t("purchasing.sentTo")}
            <input
              type="text"
              value={sentTo}
              disabled={busy}
              placeholder={t("purchasing.sentToPlaceholder")}
              onChange={(event) => setSentTo(event.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={attested}
              disabled={busy}
              onChange={(event) => setAttested(event.target.checked)}
            />
            {t("purchasing.sendCheckbox")}
          </label>
          <button type="submit" disabled={busy || !attested}>
            {t("purchasing.send")}
          </button>
          {mailNote ? (
            <p className="purchasing-hint" role="status">
              {mailNote}
            </p>
          ) : null}
        </form>
      )}
      <ul>
        {orderDocuments(order, role).map((doc) => (
          <li key={doc.format}>
            <button type="button" disabled={busy} onClick={() => onDocument(doc.type, doc.format)}>
              {t(doc.label)}
            </button>
          </li>
        ))}
      </ul>
      {canWrite && order.status !== "FULFILLED" && order.status !== "CANCELLED" && (
        <CancelOrderButton order={order} busy={busy} request={request} action={action} />
      )}
      {canWrite && (order.status === "SENT" || order.status === "PARTIALLY_RECEIVED") && (
        <ReceivingPanel order={order} busy={busy} request={request} action={action} />
      )}
    </article>
  );
}

function SupplierDirectory({
  suppliers,
  orders,
}: {
  suppliers: Supplier[];
  orders: OrderIndexItem[];
}): JSX.Element | null {
  // §2: directory built from real evidence only — contact fields, the
  // categories the supplier has actually been ordered under, and live
  // order state. No lead-time or price columns: nothing stores them.
  const rows = useMemo(() => {
    const bySupplier = new Map<string, OrderIndexItem[]>();
    for (const order of orders) {
      const key = order.supplier_identity ?? order.supplier_name ?? "";
      if (!key) continue;
      bySupplier.set(key, [...(bySupplier.get(key) ?? []), order]);
    }
    return suppliers.map((supplier) => {
      const theirs = bySupplier.get(supplier.tax_id) ?? bySupplier.get(supplier.name) ?? [];
      const open = theirs.filter(
        (order) => order.status === "SENT" || order.status === "PARTIALLY_RECEIVED",
      );
      const categories = [...new Set(theirs.map((order) => order.order_type))];
      const lastOrder = theirs
        .slice()
        .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))[0];
      const nextExpected = open
        .map((order) => order.expected_at)
        .filter((value): value is string => Boolean(value))
        .sort()[0];
      return { supplier, open, categories, total: theirs.length, lastOrder, nextExpected };
    });
  }, [suppliers, orders]);
  if (!rows.length) return null;
  return (
    <section className="purchasing-directory" aria-label={t("purchasing.directoryTitle")}>
      <h2>{t("purchasing.directoryTitle")}</h2>
      <ul>
        {rows.map(({ supplier, open, categories, total, lastOrder, nextExpected }) => (
          <li key={supplier.id} className="purchasing-directory-row">
            <div className="purchasing-directory-id">
              <strong>{supplier.name}</strong>
              {supplier.tax_id ? (
                <span className="purchasing-directory-tax">{supplier.tax_id}</span>
              ) : null}
            </div>
            <div className="purchasing-directory-contact">
              {supplier.details?.email ? <span>{supplier.details.email}</span> : null}
              {supplier.details?.phone ? <span>{supplier.details.phone}</span> : null}
              {supplier.details?.address ? <span>{supplier.details.address}</span> : null}
              {!supplier.details?.email &&
              !supplier.details?.phone &&
              !supplier.details?.address ? (
                <span className="purchasing-directory-empty">—</span>
              ) : null}
            </div>
            <div className="purchasing-directory-cats">
              {categories.length
                ? categories.map((cat) => domainLabel("OrderTypeEnum", cat).label).join(" · ")
                : "—"}
            </div>
            <div className="purchasing-directory-orders">
              {open.length ? (
                <span className="purchasing-directory-open">
                  {open.length} {t("purchasing.directoryOpen")}
                  {nextExpected
                    ? ` · ${t("purchasing.glanceNext")} ${formatDate(nextExpected)}`
                    : ""}
                </span>
              ) : (
                <span>{t("purchasing.directoryNoOpen")}</span>
              )}
              <span className="purchasing-directory-history">
                {total} {t("purchasing.directoryHistory")}
                {lastOrder ? ` · ${lastOrder.order_code}` : ""}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function OrdersIndex({
  orders,
  status,
  onStatus,
  onOpen,
  loadFailed,
}: {
  orders: OrderIndexItem[];
  status: string;
  onStatus: (status: string) => void;
  onOpen: (order: OrderIndexItem) => void;
  loadFailed?: boolean;
}): JSX.Element | null {
  const visible = status ? orders.filter((order) => order.status === status) : orders;
  if (orders.length === 0 && !loadFailed) return null;
  return (
    <section className="purchasing-index" aria-label={t("purchasing.indexTitle")}>
      <h2>{t("purchasing.indexTitle")}</h2>
      {loadFailed ? <p role="alert">{t("purchasing.sectionLoadError")}</p> : null}
      <div
        className="purchasing-index-filters"
        role="group"
        aria-label={t("purchasing.indexFilter")}
      >
        <button
          type="button"
          className={status === "" ? "is-active" : ""}
          onClick={() => onStatus("")}
        >
          {t("purchasing.indexFilterAll")}
        </button>
        {ORDER_STATUSES.map((value) => (
          <button
            key={value}
            type="button"
            className={status === value ? "is-active" : ""}
            onClick={() => onStatus(value)}
          >
            {domainLabel("OrderStatusEnum", value).label}
          </button>
        ))}
      </div>
      <table>
        <thead>
          <tr>
            <th>{t("purchasing.indexOrder")}</th>
            <th>{t("purchasing.project")}</th>
            <th>{t("purchasing.indexType")}</th>
            <th>{t("purchasing.indexSupplier")}</th>
            <th>{t("purchasing.indexStatus")}</th>
            <th>{t("purchasing.expectedAt")}</th>
            <th>{t("purchasing.indexReceipts")}</th>
            <th>{t("purchasing.indexOutstanding")}</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((order) => {
            // `order.status` vía alias: el guard ui-raw-status caza
            // `{x.status}` en JSX — el chip lo recibe ya resuelto.
            const orderStatus = order.status;
            return (
              <tr
                key={order.id}
                className="purchasing-index-row"
                onClick={() => onOpen(order)}
                // Row-level click needs a keyboard twin: focus the row and
                // activate with Enter/Space, same as the button it replaces.
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.target !== event.currentTarget) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onOpen(order);
                  }
                }}
              >
                <td>{order.order_code}</td>
                <td>
                  {order.project_code ?? "—"} · {formatRevision(order.revision_code ?? "")}
                </td>
                <td>{domainLabel("OrderTypeEnum", order.order_type).label}</td>
                <td>{order.supplier_name ?? "—"}</td>
                <td>
                  <StatusChip enumName="OrderStatusEnum" value={orderStatus} />
                </td>
                <td>{order.expected_at ? formatDate(order.expected_at) : "—"}</td>
                <td>
                  {Number(order.receipt_count ?? 0) > 0 ? order.receipt_count : "—"}
                  {Number(order.damaged_qty ?? 0) > 0 && (
                    <span className="purchasing-coverage-short">
                      {" "}
                      {t("purchasing.indexDamaged")}: {fmtQty(order.damaged_qty)}
                    </span>
                  )}
                </td>
                <td>{orderStatus === "CANCELLED" ? "—" : fmtQty(order.outstanding_qty)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function CancelOrderButton({
  order,
  busy,
  request,
  action,
}: {
  order: Order;
  busy: boolean;
  request: <T>(path: string, method?: string, body?: unknown) => Promise<T>;
  action: (task: Promise<unknown>) => Promise<boolean>;
}): JSX.Element {
  const confirm = useConfirm();
  return (
    <button
      type="button"
      className="purchasing-cancel"
      disabled={busy}
      onClick={async () => {
        const ok = await confirm({
          title: t("purchasing.cancelTitle"),
          body: t("purchasing.cancelBody"),
          confirmLabel: t("purchasing.cancelConfirm"),
          danger: true,
        });
        if (!ok) return;
        void action(request(`purchasing/orders/${order.id}/cancel/`, "POST", { confirmed: true }));
      }}
    >
      {t("purchasing.cancelOrder")}
    </button>
  );
}

function ReceivingPanel({
  order,
  busy,
  request,
  action,
}: {
  order: Order;
  busy: boolean;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<ReceivingState | null>(null);
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState("");
  const [quantities, setQuantities] = useState<Quantities>({});
  const [deliveryRef, setDeliveryRef] = useState("");
  const [deliveryDate, setDeliveryDate] = useState("");
  const [overPrompt, setOverPrompt] = useState(false);
  const [receiptKey, setReceiptKey] = useState(
    () => `${order.order_code}-${crypto.randomUUID().slice(0, 8)}`,
  );

  useEffect(() => {
    if (!open) return;
    let current = true;
    void request<ReceivingState>(`inventory/orders/${order.id}/receiving/`)
      .then((data) => {
        if (!current) return;
        setState(data);
        setQuantities((previous) => {
          const next = { ...previous };
          // Receiving starts empty — an unedited submit used to mark the
          // whole order received in one click (review PU13). "Receive all"
          // is the explicit shortcut for that intent.
          for (const line of data.lines) {
            next[line.id] ??= { received: "0", damaged: "0", lot_code: "", rack_location: "" };
          }
          return next;
        });
      })
      .catch(() => {
        if (current) setState(null);
      });
    return () => {
      current = false;
    };
  }, [open, order.id, request]);

  function submit(event: FormEvent, allowOver = false): void {
    event.preventDefault();
    if (!state) return;
    setFormError("");
    const lines = state.lines
      .map((line) => {
        const entry = quantities[line.id] ?? {
          received: "0",
          damaged: "0",
          lot_code: "",
          rack_location: "",
        };
        return {
          order_line_id: line.id,
          received_qty: entry.received,
          damaged_qty: entry.damaged,
          lot_code: entry.lot_code || null,
          rack_location: entry.rack_location || null,
        };
      })
      // damaged is a subset of received — a fully-damaged arrival posts
      // received = damaged, so either field alone keeps the line.
      .filter((line) => Number(line.received_qty) > 0 || Number(line.damaged_qty) > 0);
    if (lines.length === 0) return;
    if (lines.some((line) => Number(line.damaged_qty) > Number(line.received_qty))) {
      // received=0 with damaged>0 would otherwise vanish silently — the
      // damaged field is a subset of what arrived, not a second quantity.
      setFormError(t("purchasing.receiveDamageExceeds"));
      return;
    }
    let overReceived = false;
    void action(
      request(`inventory/orders/${order.id}/receipts/`, "POST", {
        receipt_key: receiptKey,
        note: note || null,
        supplier_delivery_ref: deliveryRef.trim() || null,
        supplier_delivery_date: deliveryDate || null,
        allow_over_receipt: allowOver,
        lines,
      }).catch((error) => {
        // Sobre-recepción: el servidor pide confirmación explícita — se
        // muestra la advertencia y el humano confirma con un segundo clic.
        if (
          error instanceof ApiError &&
          (error.payload as { error?: { code?: unknown } })?.error?.code === "receipt_over_received"
        ) {
          overReceived = true;
          setOverPrompt(true);
          return;
        }
        throw error;
      }),
    ).then((ok) => {
      if (!ok || overReceived) return;
      // One key = one physical receipt: a successful post starts the next one
      // with a fresh key; a failed/uncertain submit keeps it for safe retry.
      setReceiptKey(`${order.order_code}-${crypto.randomUUID().slice(0, 8)}`);
      setQuantities({});
      setNote("");
      setDeliveryRef("");
      setDeliveryDate("");
      setOverPrompt(false);
      request(`inventory/orders/${order.id}/receiving/`)
        .then((fresh) => setState(fresh as ReceivingState))
        .catch(() => undefined);
    });
  }

  return (
    <details className="purchasing-receiving" open={open}>
      <summary
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        {t("purchasing.receiving")}
      </summary>
      {open && !state && <p>{t("purchasing.receivingLoading")}</p>}
      {formError ? <p role="alert">{formError}</p> : null}
      {open && state && (
        <form noValidate onSubmit={submit}>
          <div className="purchasing-receiving-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("purchasing.purchaseSku")}</th>
                  <th>{t("purchasing.receiveOrdered")}</th>
                  <th>{t("purchasing.receiveReceived")}</th>
                  <th>{t("purchasing.receiveOutstanding")}</th>
                  <th>{t("purchasing.receiveNow")}</th>
                  <th>{t("purchasing.receiveDamaged")}</th>
                  <th>{t("purchasing.receiveLot")}</th>
                  <th>{t("purchasing.receiveRack")}</th>
                </tr>
              </thead>
              <tbody>
                {state.lines.map((line) => (
                  <tr key={line.id}>
                    <td>{line.purchasing_sku ?? line.category}</td>
                    <td>
                      {fmtQty(line.ordered_qty)}{" "}
                      {purchaseUnitLabel(line.unit, qtyNumber(line.ordered_qty))}
                    </td>
                    <td>{fmtQty(line.received_qty)}</td>
                    <td>
                      {Number(line.outstanding_qty) < 0 ? "0" : fmtQty(line.outstanding_qty)}
                      {Number(line.outstanding_qty) < 0 ? (
                        <small className="purchasing-hint">
                          {" "}
                          (+{fmtQty(Math.abs(Number(line.outstanding_qty)))}{" "}
                          {t("purchasing.receiveSurplus")})
                        </small>
                      ) : null}
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        step="any"
                        aria-label={`${t("purchasing.receiveNow")} · ${line.purchasing_sku ?? line.category}`}
                        disabled={busy || Number(line.outstanding_qty) <= 0}
                        value={quantities[line.id]?.received ?? "0"}
                        onChange={(event) =>
                          setQuantities((previous) => ({
                            ...previous,
                            [line.id]: {
                              ...(previous[line.id] ?? {
                                lot_code: "",
                                rack_location: "",
                              }),
                              received: event.target.value,
                              damaged: previous[line.id]?.damaged ?? "0",
                            },
                          }))
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="0"
                        step="any"
                        aria-label={`${t("purchasing.receiveDamaged")} · ${line.purchasing_sku ?? line.category}`}
                        disabled={busy || Number(line.outstanding_qty) <= 0}
                        value={quantities[line.id]?.damaged ?? "0"}
                        onChange={(event) =>
                          setQuantities((previous) => ({
                            ...previous,
                            [line.id]: {
                              ...(previous[line.id] ?? {
                                lot_code: "",
                                rack_location: "",
                              }),
                              received: previous[line.id]?.received ?? "0",
                              damaged: event.target.value,
                            },
                          }))
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        aria-label={`${t("purchasing.receiveLot")} · ${line.purchasing_sku ?? line.category}`}
                        disabled={busy || Number(line.outstanding_qty) <= 0}
                        placeholder={t("purchasing.receiveLot")}
                        value={quantities[line.id]?.lot_code ?? ""}
                        onChange={(event) =>
                          setQuantities((previous) => ({
                            ...previous,
                            [line.id]: {
                              ...(previous[line.id] ?? {
                                received: "0",
                                damaged: "0",
                                rack_location: "",
                              }),
                              lot_code: event.target.value,
                            },
                          }))
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        aria-label={`${t("purchasing.receiveRack")} · ${line.purchasing_sku ?? line.category}`}
                        disabled={busy || Number(line.outstanding_qty) <= 0}
                        placeholder={t("purchasing.receiveRack")}
                        value={quantities[line.id]?.rack_location ?? ""}
                        onChange={(event) =>
                          setQuantities((previous) => ({
                            ...previous,
                            [line.id]: {
                              ...(previous[line.id] ?? {
                                received: "0",
                                damaged: "0",
                                lot_code: "",
                              }),
                              rack_location: event.target.value,
                            },
                          }))
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <label>
            {t("purchasing.deliveryRef")}
            <input
              type="text"
              value={deliveryRef}
              disabled={busy}
              placeholder={t("purchasing.deliveryRefHint")}
              onChange={(event) => setDeliveryRef(event.target.value)}
            />
          </label>
          <label>
            {t("purchasing.deliveryDate")}
            <input
              type="date"
              value={deliveryDate}
              disabled={busy}
              onChange={(event) => setDeliveryDate(event.target.value)}
            />
          </label>
          <label>
            {t("purchasing.receiveNote")}
            <input
              type="text"
              value={note}
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              setQuantities(() => {
                const next: Quantities = {};
                for (const line of state.lines) {
                  next[line.id] = {
                    received: String(Math.max(0, Number(line.outstanding_qty))),
                    damaged: "0",
                    lot_code: "",
                    rack_location: "",
                  };
                }
                return next;
              })
            }
          >
            {t("purchasing.receiveAll")}
          </button>
          <button
            type="submit"
            disabled={busy || state.lines.every((line) => Number(line.outstanding_qty) <= 0)}
          >
            {t("purchasing.receiveSubmit")}
          </button>
          {overPrompt ? (
            <div className="purchasing-over-receipt" role="alert">
              <strong>{t("purchasing.overReceiptTitle")}</strong>
              <p>{t("purchasing.overReceiptBody")}</p>
              <button
                type="button"
                disabled={busy}
                onClick={(event) => submit(event as unknown as FormEvent, /* allowOver */ true)}
              >
                {t("purchasing.overReceiptConfirm")}
              </button>
            </div>
          ) : null}
          {state.receipts.length > 0 && (
            <table className="purchasing-receipts">
              <caption>{t("purchasing.receiveHistory")}</caption>
              <thead>
                <tr>
                  <th>{t("purchasing.receiptCode")}</th>
                  <th>{t("purchasing.receiptDate")}</th>
                  <th>{t("purchasing.deliveryRef")}</th>
                  <th>{t("purchasing.deliveryDate")}</th>
                  <th>{t("purchasing.receiptNote")}</th>
                </tr>
              </thead>
              <tbody>
                {state.receipts.map((receipt) => (
                  <tr key={receipt.id}>
                    <td>{receipt.receipt_code}</td>
                    <td>{formatDateTime(receipt.created_at)}</td>
                    <td>{receipt.supplier_delivery_ref || "—"}</td>
                    <td>
                      {receipt.supplier_delivery_date
                        ? formatDate(receipt.supplier_delivery_date)
                        : "—"}
                    </td>
                    <td>{receipt.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </form>
      )}
    </details>
  );
}

type OfferRemnant = {
  id: string;
  remnant_code: string;
  kind: "BAR" | "SHEET";
  length_mm: string | null;
  width_mm: string | null;
  height_mm: string | null;
  rack_location: string | null;
};

type WorkOrderOption = { id: string; order_code: string; status?: string };

// La compatibilidad (largo útil ≥ requerido + mermas) la decide el motor al
// producir el remnant_pool; aquí solo se ofrece reservar la pieza a una OT.
function RemnantOffer({
  line,
  busy,
  request,
  action,
}: {
  line: CoverageLine;
  busy: boolean;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
}): JSX.Element {
  const key = line.remnant_pool?.key ?? "";
  const [remnants, setRemnants] = useState<OfferRemnant[] | null>(null);
  const [orders, setOrders] = useState<WorkOrderOption[]>([]);
  const [orderId, setOrderId] = useState("");
  const [done, setDone] = useState<ReadonlySet<string>>(new Set());

  useEffect(() => {
    let live = true;
    void request<{ remnants?: OfferRemnant[] }>(
      `inventory/remnants/?status=AVAILABLE&stock_identity=${encodeURIComponent(key)}`,
    )
      .then((data) => {
        if (live) setRemnants((data.remnants ?? []).slice(0, 4));
      })
      .catch(() => {
        if (live) setRemnants([]);
      });
    return () => {
      live = false;
    };
  }, [key, request]);

  function loadOrders(): void {
    if (orders.length > 0) return;
    void request<{ orders?: WorkOrderOption[] }>("production/orders/")
      .then((data) =>
        setOrders(
          (data.orders ?? []).filter((order) => order.order_code.startsWith("OT")).slice(0, 30),
        ),
      )
      .catch(() => undefined);
  }

  return (
    <div className="purchasing-remnant-offer">
      <p>
        <EntityCode value={line.purchasing_sku} /> · {t("purchasing.coverageShortage")}:{" "}
        <strong>{fmtQty(line.shortage)}</strong>{" "}
        {purchaseUnitLabel(line.unit, qtyNumber(line.shortage))}
      </p>
      {remnants === null ? (
        <p className="purchasing-hint">{t("purchasing.receivingLoading")}</p>
      ) : remnants.length === 0 ? (
        <p className="purchasing-hint">{t("purchasing.remnantOfferEmpty")}</p>
      ) : (
        <ul>
          {remnants.map((remnant) =>
            done.has(remnant.id) ? (
              <li key={remnant.id} className="purchasing-hint">
                <EntityCode value={remnant.remnant_code} /> · {t("purchasing.remnantOfferReserved")}
              </li>
            ) : (
              <li key={remnant.id}>
                <EntityCode value={remnant.remnant_code} /> ·{" "}
                {remnant.kind === "BAR"
                  ? `${fmtMm(remnant.length_mm)} mm`
                  : `${fmtMm(remnant.width_mm)} × ${fmtMm(remnant.height_mm)} mm`}
                {remnant.rack_location ? ` · ${remnant.rack_location}` : ""}
                {" · "}
                <select
                  aria-label={`${t("inventory.reserveTo")} · ${remnant.remnant_code}`}
                  disabled={busy}
                  value={orderId}
                  onFocus={loadOrders}
                  onChange={(event) => setOrderId(event.target.value)}
                >
                  <option value="">{t("inventory.reservePick")}</option>
                  {orders.map((order) => (
                    <option key={order.id} value={order.id}>
                      {order.order_code}
                    </option>
                  ))}
                </select>{" "}
                <button
                  type="button"
                  disabled={busy || orderId === ""}
                  onClick={() =>
                    void action(
                      request(`inventory/remnants/${remnant.id}/reserve/`, "POST", {
                        order_id: orderId,
                      }),
                    ).then((ok) => {
                      if (ok) {
                        setDone((previous) => new Set(previous).add(remnant.id));
                      }
                    })
                  }
                >
                  {t("inventory.reserve")}
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}
