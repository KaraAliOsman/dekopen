import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiMutator, ApiError } from "../../api/apiMutator";
import { documentaryArtifactAccess } from "../../api/generated/dekopen";
import { InventorySection } from "./InventorySection";
import { runJob } from "../jobs/runJob";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { DeniedState } from "../../ui";
import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";
import { formatDateTime, formatRevision } from "../../format";
import "./purchasing.css";

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
function purchaseUnitLabel(unit: string | null | undefined, qty?: number): string {
  if (!unit) return "";
  const known: ReadonlySet<string> = new Set(["EA", "BAR", "KIT", "SHEET", "M", "M2", "KG"]);
  if (!known.has(unit)) return unit;
  const plural = qty === undefined || unitPlural.select(qty) !== "one";
  return t(`purchasing.unitValue.${unit}${plural ? ".other" : ".one"}` as Parameters<typeof t>[0]);
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
const orderTypeLabels: Record<OrderType, Parameters<typeof t>[0]> = {
  SUPPLIER_PROFILE_PO: "purchasing.orderTypeProfile",
  SUPPLIER_GLASS_PO: "purchasing.orderTypeGlass",
  SUPPLIER_HARDWARE_PO: "purchasing.orderTypeHardware",
  SUPPLIER_PANEL_PO: "purchasing.orderTypePanel",
};

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
};
type Eligibility = {
  id: string;
  order_type: OrderType;
  supplier_identity: string;
  supplier_name: string;
  eligible_requirement_keys: string[];
  version: number;
};
type Allocation = {
  id: string;
  requirement_line_id: string;
  supplier_eligibility_id: string;
  order_type: OrderType;
};
type OrderStatus = "DRAFT" | "SENT" | "PARTIALLY_RECEIVED" | "FULFILLED" | "CANCELLED";
type OrderLinePreview = { sku: string | null; qty: string; unit: string | null };
type Order = {
  id: string;
  order_code: string;
  order_type: OrderType;
  status: OrderStatus;
  supplier_name: string;
  order_snapshot_hash: string;
  expected_at?: string | null;
  line_count?: string | null;
  total_qty?: string | null;
  lines_preview?: OrderLinePreview[];
};
const orderStatusLabels: Record<OrderStatus, Parameters<typeof t>[0]> = {
  DRAFT: "purchasing.draft",
  SENT: "purchasing.sent",
  PARTIALLY_RECEIVED: "purchasing.partiallyReceived",
  FULFILLED: "purchasing.fulfilled",
  CANCELLED: "purchasing.cancelled",
};
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
    receipt_key: string;
    created_at: string;
    note: string | null;
  }>;
};
type StockItem = {
  item_id: string;
  sku: string;
  name: string;
  category: string;
  unit: string;
  on_hand_qty: string;
  reserved_qty: string;
  available_qty: string;
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
  remnant_pool?: { kind: string; count: number; total_mm?: string } | null;
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
  if (!org || !["OWNER", "WORKSHOP_MANAGER"].includes(org.role))
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
};

type DocumentAction = { type: string; format: string; label: Parameters<typeof t>[0] };

function orderDocuments(order: Order, role: string): DocumentAction[] {
  let docs: DocumentAction[] = [];
  if (order.order_type === "SUPPLIER_GLASS_PO")
    docs = [{ type: "DOC-02", format: "XLSX", label: "purchasing.doc02" }];
  else if (order.order_type === "SUPPLIER_PROFILE_PO")
    docs = [
      { type: "DOC-04", format: "PDF", label: "purchasing.doc04Pdf" },
      { type: "DOC-04", format: "XLSX", label: "purchasing.doc04Xlsx" },
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
  const [versionId, setVersionId] = useState(initialVersionId);
  const [state, setState] = useState<PurchasingState | null>(null);
  const [stock, setStock] = useState<StockItem[]>([]);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
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
        void request<{ items?: StockItem[] }>("inventory/stock/")
          .then((stockData) => {
            if (current) setStock(stockData.items ?? []);
          })
          .catch(() => {
            if (current) setStock([]);
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
      window.open(access.data.signed_url, "_blank", "noopener,noreferrer");
      setMessage("");
    } catch {
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
  const confirmedTypes = new Set(orders.map((order) => order.order_type));

  return (
    <section className="purchasing-page">
      <header>
        <h1>{t("purchasing.title")}</h1>
        <p>{t("purchasing.subtitle")}</p>
        <Link className="ui-backlink ui-backlink--back" to="/projects">
          {t("purchasing.workshop")}
        </Link>
      </header>
      {message && <p role="alert">{message}</p>}
      {busy && <p role="status">{t("purchasing.loading")}</p>}
      {!busy && versions.length === 0 && <p>{t("purchasing.empty")}</p>}
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
                {t(orderTypeLabels[blocker.order_type])} ·{" "}
                {t(blockerLabels[blocker.code] ?? "purchasing.blockers")}
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
                    {line.purchasing_sku}
                    <span className="purchasing-coverage-unit">
                      {" "}
                      {purchaseUnitLabel(line.unit, 2)}
                    </span>
                  </td>
                  <td>{line.required}</td>
                  <td>{line.on_hand}</td>
                  <td>{line.reserved}</td>
                  <td>{line.open_ordered}</td>
                  <td>
                    {line.received !== "0" ? (
                      <strong className="purchasing-coverage-received">
                        {line.received} · {t("purchasing.receivedMark")}
                      </strong>
                    ) : (
                      line.received
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
                      <strong className="purchasing-coverage-short">{line.shortage}</strong>
                    ) : (
                      "0"
                    )}
                  </td>
                  <td>{line.recommended_purchase}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
            busy={busy}
            versionId={state.version!.id}
            request={request}
            action={action}
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
              busy={busy}
              request={request}
              action={action}
              onDocument={(type, format) => void openDocument(type, format, order.id)}
            />
          ))}
        </section>
      )}
      {stock.length > 0 && (
        <section className="purchasing-stock">
          <h2>{t("purchasing.stockTitle")}</h2>
          <table>
            <thead>
              <tr>
                <th>{t("purchasing.purchaseSku")}</th>
                <th>{t("purchasing.stockName")}</th>
                <th>{t("purchasing.stockOnHand")}</th>
                <th>{t("purchasing.stockReserved")}</th>
                <th>{t("purchasing.stockAvailable")}</th>
              </tr>
            </thead>
            <tbody>
              {stock.map((item) => (
                <tr key={item.item_id}>
                  <td>{item.sku}</td>
                  <td>
                    {item.name} · {purchaseUnitLabel(item.unit, 2)}
                  </td>
                  <td>{item.on_hand_qty}</td>
                  <td>{item.reserved_qty}</td>
                  <td>{item.available_qty}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <InventorySection
        request={request}
        canWrite={role === "WORKSHOP_MANAGER" || role === "OWNER"}
        stockItems={stock.map((item) => ({
          item_id: item.item_id,
          sku: item.sku,
          name: item.name,
        }))}
      />
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
  busy,
  versionId,
  request,
  action,
}: {
  orderType: OrderType;
  requirements: Requirement[];
  eligibilities: Eligibility[];
  allocations: Allocation[];
  confirmed: boolean;
  busy: boolean;
  versionId: string;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
}): JSX.Element {
  const [attested, setAttested] = useState(false);
  const allocatedIds = new Set(allocations.map((item) => item.requirement_line_id));
  const allAllocated =
    requirements.length > 0 && requirements.every((item) => allocatedIds.has(item.id));
  return (
    <section className="purchasing-type">
      <h2>
        {t(orderTypeLabels[orderType])}
        {confirmed && <span className="purchasing-badge">{t("purchasing.confirmedBadge")}</span>}
      </h2>
      {requirements.length === 0 && <p>{t("purchasing.noRequirements")}</p>}
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
                confirmed={confirmed}
                busy={busy}
                request={request}
                action={action}
              />
            ))}
          </tbody>
        </table>
      )}
      {!confirmed && (
        <>
          <EligibilityForm
            orderType={orderType}
            requirements={requirements}
            eligibilities={eligibilities}
            busy={busy}
            versionId={versionId}
            request={request}
            action={action}
          />
          {requirements.length > 0 && (
            <form
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
  confirmed,
  busy,
  request,
  action,
}: {
  requirement: Requirement;
  eligibilities: Eligibility[];
  allocation: Allocation | undefined;
  confirmed: boolean;
  busy: boolean;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
}): JSX.Element {
  const allocated = eligibilities.find((item) => item.id === allocation?.supplier_eligibility_id);
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
        {requirement.quantity}{" "}
        {purchaseUnitLabel(requirement.unit, qtyNumber(requirement.quantity))}
      </td>
      <td>
        {confirmed ? (
          (allocated?.supplier_name ?? "—")
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
              .filter(
                (item) =>
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
      </td>
      <td>
        <details>
          <summary>{t("purchasing.trace")}</summary>
          {requirement.source_trace.length === 0 && <p>{t("purchasing.noTrace")}</p>}
          <ul>
            {requirement.source_trace.map((entry, index) => (
              <li key={index}>{typeof entry === "string" ? entry : traceLine(entry)}</li>
            ))}
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
}: {
  orderType: OrderType;
  requirements: Requirement[];
  eligibilities: Eligibility[];
  busy: boolean;
  versionId: string;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
}): JSX.Element {
  const nextVersion = Math.max(0, ...eligibilities.map((item) => item.version)) + 1;
  return (
    <details className="purchasing-eligibility">
      <summary>{t("purchasing.eligibilities")}</summary>
      {eligibilities.map((item) => (
        <p key={item.id}>
          {item.supplier_name} · v{item.version} · {item.eligible_requirement_keys.length}{" "}
          {t("purchasing.requirements")}
        </p>
      ))}
      {requirements.length > 0 && (
        <form
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
          <label>
            {t("purchasing.supplierIdentity")}
            <input name="supplier_identity" required maxLength={200} disabled={busy} />
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
                {item.purchasing_sku ?? item.requirement_key.slice(0, 12)}
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
  busy,
  request,
  action,
  onDocument,
}: {
  order: Order;
  role: string;
  busy: boolean;
  request: RequestFn;
  action: (task: Promise<unknown>) => Promise<boolean>;
  onDocument: (type: string, format: string) => void;
}): JSX.Element {
  const [attested, setAttested] = useState(false);
  const [expectedAt, setExpectedAt] = useState("");
  return (
    <article className={`purchasing-order purchasing-order-${order.status.toLowerCase()}`}>
      <header>
        <strong>{order.order_code}</strong>
        <span>
          {t(orderTypeLabels[order.order_type])} · {order.supplier_name} ·{" "}
          {t(orderStatusLabels[order.status])}
        </span>
      </header>
      {order.lines_preview && order.lines_preview.length > 0 && (
        <ul className="purchasing-order-lines">
          {order.lines_preview.slice(0, 4).map((line, index) => (
            <li key={index}>
              {line.sku} × {line.qty} {line.unit}
            </li>
          ))}
          {Number(order.line_count) > 4 && (
            <li>
              +{Number(order.line_count) - 4} {t("purchasing.moreLines")}
            </li>
          )}
        </ul>
      )}
      {order.expected_at && (
        <p className="purchasing-order-expected">
          {t("purchasing.expectedAt")}: {order.expected_at}
        </p>
      )}
      {order.status === "DRAFT" && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void action(
              request(`purchasing/orders/${order.id}/send/`, "POST", {
                confirmed: true,
                expected_at: expectedAt || null,
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
      {(order.status === "SENT" || order.status === "PARTIALLY_RECEIVED") && (
        <ReceivingPanel order={order} busy={busy} request={request} action={action} />
      )}
    </article>
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
  const [quantities, setQuantities] = useState<Quantities>({});
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

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!state) return;
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
      .filter((line) => Number(line.received_qty) > 0);
    if (lines.length === 0) return;
    void action(
      request(`inventory/orders/${order.id}/receipts/`, "POST", {
        receipt_key: receiptKey,
        note: note || null,
        lines,
      }),
    ).then((ok) => {
      if (!ok) return;
      // One key = one physical receipt: a successful post starts the next one
      // with a fresh key; a failed/uncertain submit keeps it for safe retry.
      setReceiptKey(`${order.order_code}-${crypto.randomUUID().slice(0, 8)}`);
      setQuantities({});
      setNote("");
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
      {open && state && (
        <form onSubmit={submit}>
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
                    {line.ordered_qty} {purchaseUnitLabel(line.unit, qtyNumber(line.ordered_qty))}
                  </td>
                  <td>{line.received_qty}</td>
                  <td>{line.outstanding_qty}</td>
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
                    received: line.outstanding_qty,
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
          {state.receipts.length > 0 && (
            <table className="purchasing-receipts">
              <caption>{t("purchasing.receiveHistory")}</caption>
              <thead>
                <tr>
                  <th>{t("purchasing.receiptKey")}</th>
                  <th>{t("purchasing.receiptDate")}</th>
                  <th>{t("purchasing.receiptNote")}</th>
                </tr>
              </thead>
              <tbody>
                {state.receipts.map((receipt) => (
                  <tr key={receipt.id}>
                    <td>{receipt.receipt_key}</td>
                    <td>{formatDateTime(receipt.created_at)}</td>
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
