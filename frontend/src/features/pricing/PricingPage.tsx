import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { projectsList, projectsRetrieve } from "../../api/generated/dekopen";

import type { PriceResponse, ProjectResponse } from "../../api/generated/models";
import { formatDateTime, formatPercent, shortTechnicalId } from "../../format";
import { formatMoney } from "../../format";
import { apiMutator, ApiError } from "../../api/apiMutator";
import { actionErrorDetail } from "../errors";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { DeniedState, PageHeader, Tabs } from "../../ui";
import { StatusBadge } from "../../ui/StatusBadge";
import { StatusChip } from "../../ui/StatusChip";
import { PositionThumb } from "../projects/PositionThumb";
import { t } from "../../i18n/es-CL";
import { useCanvasStore } from "../canvas/canvasStore";
import "./pricing.css";

const modes = [
  "COST_PLUS_MARGIN",
  "PRICE_PER_M2_BY_TYPOLOGY",
  "FIXED_PRICE_MATRIX_DIMENSIONAL",
  "TARGET_GROSS_MARGIN_PROJECT",
  "COMMERCIAL_LIST_WITH_DISCOUNTS",
];
const optionLabels: Record<string, Parameters<typeof t>[0]> = {
  COST_PLUS_MARGIN: "pricing.mode1",
  PRICE_PER_M2_BY_TYPOLOGY: "pricing.mode2",
  FIXED_PRICE_MATRIX_DIMENSIONAL: "pricing.mode3",
  TARGET_GROSS_MARGIN_PROJECT: "pricing.mode4",
  COMMERCIAL_LIST_WITH_DISCOUNTS: "pricing.mode5",
  PROFILE: "pricing.profile",
  GLASS: "pricing.glass",
  HARDWARE: "pricing.hardware",
  PANEL: "pricing.panel",
  ACCESSORY: "pricing.accessory",
  BAR: "pricing.bar",
  M: "pricing.metre",
  M2: "pricing.squareMetre",
  KIT: "pricing.kit",
  UNIT: "pricing.each",
  EA: "pricing.eachUnit",
  FIXED: "pricing.fixed",
  TURN: "pricing.turn",
  TILT_TURN: "pricing.tiltTurn",
  SLIDING_2L: "pricing.sliding",
  DOOR_ENTRY: "pricing.door",
  AWNING: "pricing.awning",
  COMPOSITE: "pricing.composite",
  RETAIL: "pricing.retail",
  ARCHITECT: "pricing.architect",
  CONSTRUCTION: "pricing.construction",
  REINFORCEMENT: "pricing.coverageKind.reinforcement",
  FITTING: "catalog.componentCategory.FITTING",
};
function optionLabel(value: string): string {
  const key = optionLabels[value];
  return key ? t(key) : value;
}

/** Backend contract codes the estimator can actually act on — the generic
 * "revisa los campos" fallback taught users nothing about what failed. */
const ERROR_KEYS: Record<string, Parameters<typeof t>[0]> = {
  missing_cost: "pricing.errMissingCost",
  ambiguous_cost_list: "pricing.errAmbiguousList",
  stale_pricing_operation: "pricing.errStale",
  mfa_required: "pricing.errMfa",
  invalid_segment_discount: "pricing.errSegment",
  missing_glass_authority: "pricing.errGlass",
  commercial_revision_required: "pricing.errRevision",
  pricing_configuration_not_found: "pricing.errConfig",
  owner_approval_required: "pricing.errOwner",
  owner_confirmation_required: "pricing.errOwnerConfirm",
  operation_not_withdrawable: "pricing.errWithdraw",
  pricing_permission_denied: "pricing.errDenied",
  negative_margin: "pricing.errNegative",
  target_margin_already_defines_final_price: "pricing.errTarget",
};

function pricingError(error: unknown, fallback: Parameters<typeof t>[0]): string {
  if (error instanceof ApiError) {
    const payload = error.payload as { error?: { code?: unknown; detail?: unknown } } | null;
    // The backend detail names the failing position ("P04 · falta precio…")
    // — keep that context; the mapped copy only serves when the payload
    // carries a bare code.
    const detail = payload?.error?.detail;
    if (typeof detail === "string" && detail.trim() !== "") return detail;
    const code = payload?.error?.code;
    if (typeof code === "string" && ERROR_KEYS[code]) return t(ERROR_KEYS[code]);
  }
  return actionErrorDetail(error, t(fallback));
}

/** Contract codes whose fix lives in the pricing admin surface — the
 * blocker links the estimator to the missing data instead of stopping at
 * a red sentence. */
const FIXABLE_CODES = new Set([
  "missing_glass_authority",
  "missing_cost",
  "ambiguous_cost_list",
  "ambiguous_authority",
  "cost_list_not_found",
  "incompatible_cost_unit",
  "missing_fx_authority",
  "pricing_rules_not_found",
  "pricing_configuration_not_found",
]);
function pricingFixCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const payload = error.payload as { error?: { code?: unknown } } | null;
  const code = payload?.error?.code;
  return typeof code === "string" && FIXABLE_CODES.has(code) ? code : null;
}
/** The seeded DEFAULT context is a real value, not a display string — render
 * the operator-facing label everywhere it surfaces (review m2). */
function contextLabel(value: unknown): string {
  return value === "DEFAULT" ? t("pricing.contextDefault") : String(value);
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})/;
/** A <input type=number> only accepts dot decimals — the comma display
 * would render the field blank on edit. */
function pctInput(value: unknown): string {
  const pct = Number(value) * 100;
  if (!Number.isFinite(pct)) return "0";
  return String(Math.round(pct * 10) / 10);
}
/** Stored values are ISO; operators read DD-MM-AAAA everywhere else in the
 * product. Render the business format, keep the raw value for submission. */
function renderFieldValue(
  field: Field,
  value: unknown,
  refs?: { costLists?: Row[]; configurations?: Row[] },
): string {
  if (value === undefined || value === null || value === "") return "—";
  const text = String(value);
  // FK references render the authority's human label, never the raw UUID.
  if (field.name === "cost_list_id") {
    const list = refs?.costLists?.find((row) => String(row.id) === text);
    return list ? `${list.supplier_name} · ${list.currency}` : "—";
  }
  if (field.name === "configuration_id") {
    const config = refs?.configurations?.find((row) => String(row.id) === text);
    return config
      ? `${contextLabel(config.context_code)} · ${optionLabel(String(config.typology))}`
      : "—";
  }
  if (field.type === "date") {
    const match = ISO_DAY.exec(text);
    if (match) return `${match[3]}-${match[2]}-${match[1]}`;
  }
  if (field.type === "percent") return `${formatPercent(text)}`;
  if (field.name === "unit_cost" || field.name === "catalog_price" || field.name === "price")
    return formatMoney(text, "CLP");
  if (field.name === "created_at") return formatDateTime(text);
  if (field.name === "entity") return t(auditEntityLabels[text] ?? "pricing.auditEntity.other");
  if (field.name === "field") return t(auditActionLabels[text] ?? "pricing.auditAction.other");
  if (field.name === "actor_type") return t(auditActorLabels[text] ?? "pricing.auditActor.other");
  return text;
}
type Field = {
  name: string;
  label: Parameters<typeof t>[0];
  type?: string;
  options?: string[];
  initial?: string;
  optional?: boolean;
};
const fields: Record<string, Field[]> = {
  "cost-lists": [
    { name: "supplier_name", label: "pricing.supplier" },
    { name: "description", label: "pricing.description", optional: true },
    { name: "currency", label: "pricing.currency", options: ["CLP", "USD"] },
    { name: "valid_from", label: "pricing.from", type: "date" },
    { name: "valid_to", label: "pricing.until", type: "date", optional: true },
  ],
  "cost-items": [
    { name: "cost_list_id", label: "pricing.listId" },
    { name: "sku", label: "pricing.sku" },
    {
      name: "item_type",
      label: "pricing.itemType",
      options: ["PROFILE", "GLASS", "HARDWARE", "PANEL", "ACCESSORY"],
    },
    { name: "unit", label: "pricing.unit", options: ["BAR", "M", "M2", "KIT", "UNIT", "EA"] },
    { name: "unit_cost", label: "pricing.cost" },
  ],
  rules: [
    { name: "pricing_mode", label: "pricing.mode", options: modes },
    { name: "default_margin_pct", label: "pricing.margin", type: "percent", initial: "35" },
    { name: "margin_min_pct", label: "pricing.marginMin", type: "percent", initial: "25" },
    { name: "margin_max_pct", label: "pricing.marginMax", type: "percent", initial: "60" },
    { name: "tax_rate_pct", label: "pricing.tax", type: "percent", initial: "19" },
    { name: "waste_factor_pct", label: "pricing.waste", type: "percent", initial: "8" },
    { name: "labor_rate_per_m2", label: "pricing.labor", initial: "15000" },
    { name: "installation_rate_per_m2", label: "pricing.installation", initial: "12000" },
  ],
  configurations: [
    { name: "context_code", label: "pricing.context", initial: "DEFAULT" },
    {
      name: "typology",
      label: "pricing.typology",
      options: ["FIXED", "TURN", "TILT_TURN", "SLIDING_2L", "DOOR_ENTRY", "AWNING", "COMPOSITE"],
    },
    { name: "pricing_mode", label: "pricing.mode", options: modes },
    { name: "currency", label: "pricing.currency", options: ["CLP", "USD"] },
    { name: "rate_per_m2", label: "pricing.rate", optional: true },
    { name: "base_glass_sku", label: "pricing.baseGlass", optional: true },
    { name: "catalog_price", label: "pricing.catalogPrice", optional: true },
  ],
  "matrix-cells": [
    { name: "configuration_id", label: "pricing.configurationId" },
    { name: "width_mm", label: "pricing.width", type: "number" },
    { name: "height_mm", label: "pricing.height", type: "number" },
    { name: "price", label: "pricing.price" },
  ],
  fx: [
    { name: "base_currency", label: "pricing.baseCurrency", options: ["USD"] },
    { name: "quote_currency", label: "pricing.quoteCurrency", options: ["CLP"] },
    { name: "observed_rate", label: "pricing.fxRate" },
    { name: "observed_date", label: "pricing.observedDate", type: "date" },
    { name: "effective_date", label: "pricing.effectiveDate", type: "date" },
    { name: "source", label: "pricing.source" },
  ],
  audits: [
    { name: "entity", label: "pricing.auditEntity" },
    { name: "field", label: "pricing.auditAction" },
    { name: "reason", label: "pricing.reason" },
    { name: "actor_type", label: "pricing.auditActor" },
    { name: "created_at", label: "pricing.created" },
  ],
};
// Audit rows carry raw storage names (entity = table, field = SQL verb);
// people read domain nouns and past-tense actions.
const auditEntityLabels: Record<string, Parameters<typeof t>[0]> = {
  cost_lists: "pricing.auditEntity.costLists",
  cost_list_items: "pricing.auditEntity.costListItems",
  pricing_configurations: "pricing.auditEntity.pricingConfigurations",
  pricing_matrix_cells: "pricing.auditEntity.pricingMatrixCells",
  pricing_operations: "pricing.auditEntity.pricingOperations",
  pricing_rules: "pricing.auditEntity.pricingRules",
  project_positions: "pricing.auditEntity.projectPositions",
  projects: "pricing.auditEntity.projects",
  pricing_fx_snapshots: "pricing.auditEntity.fxSnapshots",
};
const auditActionLabels: Record<string, Parameters<typeof t>[0]> = {
  INSERT: "pricing.auditAction.insert",
  UPDATE: "pricing.auditAction.update",
  DELETE: "pricing.auditAction.delete",
};
const auditActorLabels: Record<string, Parameters<typeof t>[0]> = {
  HUMAN: "pricing.auditActor.human",
  SYSTEM: "pricing.auditActor.system",
  AI_AGENT: "pricing.auditActor.ai",
};
const sections = [
  "cost-lists",
  "cost-items",
  "coverage",
  "rules",
  "configurations",
  "matrix-cells",
  "fx",
  "audits",
] as const;
const sectionLabels = [
  "pricing.lists",
  "pricing.items",
  "pricing.coverage",
  "pricing.rules",
  "pricing.configurations",
  "pricing.matrix",
  "pricing.fx",
  "pricing.audits",
] as const;
type Row = Record<string, string | boolean | null>;

function usePricingRequest(orgId: string): RequestFn {
  // Each request gets its own controller, registered in a live set aborted on
  // unmount. A single shared controller cannot work: a child effect (e.g. the
  // mount history load) may fire before this component's own effect assigns
  // it, and StrictMode's remount must not cancel requests issued afterwards.
  const live = useRef<Set<AbortController>>(new Set());
  useEffect(() => {
    const controllers = live.current;
    return () => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, []);
  return useCallback(
    async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
      const form = body instanceof FormData;
      const controller = new AbortController();
      live.current.add(controller);
      try {
        const response = await apiMutator<{ data: T }>(`/api/v1/pricing/${path}`, {
          method,
          signal: controller.signal,
          headers: {
            "X-Organization-ID": orgId,
            ...(form ? {} : { "Content-Type": "application/json" }),
          },
          ...(body === undefined ? {} : { body: form ? body : JSON.stringify(body) }),
        });
        return response.data;
      } finally {
        live.current.delete(controller);
      }
    },
    [orgId],
  );
}

export function CommercialPricingPage(): JSX.Element {
  const { id: projectId } = useParams();
  const org = useAuthSession().me?.active_organization;
  if (!org || !["OWNER", "ESTIMATOR"].includes(org.role))
    return <DeniedState reason={t("pricing.commercialDenied")} />;
  return (
    <CommercialWorkspace
      key={`${org.id}:${projectId ?? ""}`}
      orgId={org.id}
      owner={org.role === "OWNER"}
      projectId={projectId}
    />
  );
}

function CommercialWorkspace({
  orgId,
  owner,
  projectId,
}: {
  orgId: string;
  owner: boolean;
  projectId?: string;
}): JSX.Element {
  const request = usePricingRequest(orgId);
  return (
    <section className="pricing-page">
      {projectId && (
        <Link className="ui-backlink ui-backlink--back" to={`/projects/${projectId}`}>
          {t("projects.back")}
        </Link>
      )}
      <PageHeader title={t("crumb.pricingCommercial")} />
      <CommercialOperations request={request} owner={owner} boundProjectId={projectId} />
    </section>
  );
}

export function PricingPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  if (!org || org.role !== "OWNER") return <DeniedState reason={t("pricing.ownerOnly")} />;
  return <PricingWorkspace key={org.id} orgId={org.id} />;
}

function PricingWorkspace({ orgId }: { orgId: string }): JSX.Element {
  const [resource, setResource] = useState<string>("cost-lists");
  const [items, setItems] = useState<Row[]>([]);
  const [costLists, setCostLists] = useState<Row[]>([]);
  const [configurations, setConfigurations] = useState<Row[]>([]);
  const [catalogSkus, setCatalogSkus] = useState<Row[]>([]);
  const [editing, setEditing] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const lifetime = useRef<AbortController>(new AbortController());
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);
  async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    const form = body instanceof FormData;
    const response = await apiMutator<{ data: T }>(`/api/v1/pricing/${path}`, {
      method,
      signal: lifetime.current.signal,
      headers: {
        "X-Organization-ID": orgId,
        ...(form ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: form ? body : JSON.stringify(body) }),
    });
    return response.data;
  }
  useEffect(() => {
    let current = true;
    setItems([]);
    setEditing(null);
    setMessage("");
    setBusy(true);
    void request<{ items: Row[] }>(`admin/${resource}/`)
      .then((response) => {
        if (current) {
          setItems(response.items);
          if (resource === "cost-lists") setCostLists(response.items);
          if (resource === "configurations") setConfigurations(response.items);
        }
      })
      .catch(() => {
        if (current) setMessage(t("pricing.loadError"));
      })
      .finally(() => {
        if (current) setBusy(false);
      });
    if (resource === "matrix-cells") {
      void request<{ items: Row[] }>("admin/configurations/")
        .then((response) => {
          if (current) setConfigurations(response.items);
        })
        .catch(() => {
          if (current) setMessage(t("pricing.loadError"));
        });
    }
    if (resource === "cost-items") {
      void request<{ items: Row[] }>("admin/cost-lists/")
        .then((response) => {
          if (current) setCostLists(response.items);
        })
        .catch(() => {
          if (current) setMessage(t("pricing.loadError"));
        });
      void request<{ items: Row[] }>("admin/coverage/")
        .then((response) => {
          if (current) setCatalogSkus(response.items);
        })
        .catch(() => {
          if (current) setCatalogSkus([]);
        });
    }
    return () => {
      current = false;
    };
    // The workspace remounts for each organization; resource/revision own reloads.
  }, [resource, revision]);

  async function save(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const values: Record<string, unknown> = {};
    for (const field of fields[resource] ?? []) {
      const value = String(data.get(field.name) ?? "");
      if (field.optional && value === "") {
        if (field.name !== "description") values[field.name] = null;
        else values[field.name] = "";
        continue;
      }
      values[field.name] =
        field.type === "percent"
          ? Number(value) / 100
          : field.type === "number"
            ? Number(value)
            : value;
    }
    if (resource === "cost-lists" || resource === "configurations")
      values.is_active = data.get("is_active") === "on";
    setBusy(true);
    setMessage("");
    try {
      await request(`admin/${resource}/`, "POST", {
        ...(editing ? { id: editing.id } : {}),
        values,
        reason: data.get("reason"),
      });
      if (!lifetime.current.signal.aborted) {
        setEditing(null);
        setRevision((value) => value + 1);
      }
    } catch (error) {
      if (!lifetime.current.signal.aborted)
        setMessage(
          t(
            error instanceof ApiError && error.status === 409
              ? "pricing.conflict"
              : "pricing.saveError",
          ),
        );
    } finally {
      if (!lifetime.current.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="pricing-page">
      <PageHeader context={t("pricing.subtitle")} title={t("pricing.title")} />
      <Tabs
        items={sections.map((name, index) => ({
          disabled: busy,
          id: name,
          label: t(sectionLabels[index]!),
        }))}
        label={t("pricing.sections")}
        onChange={setResource}
        value={resource}
      />
      {message && <p role="alert">{message}</p>}
      {busy && <p role="status">{t("pricing.loading")}</p>}
      <div className="pricing-grid">
        <div className="pricing-records">
          <button type="button" disabled={busy} onClick={() => setRevision((value) => value + 1)}>
            {t("pricing.reload")}
          </button>
          {!busy && items.length === 0 && <p>{t("pricing.empty")}</p>}
          {resource === "audits" ? (
            items.map((item) => <AuditCard key={String(item.id)} item={item} />)
          ) : resource === "coverage" ? (
            <CoverageList items={items} />
          ) : (
            items.map((item) => (
              <article key={String(item.id)}>
                <strong>
                  {String(
                    item.supplier_name ??
                      item.sku ??
                      (item.context_code !== undefined && item.context_code !== null
                        ? contextLabel(item.context_code)
                        : (item.source ?? item.entity ?? t("pricing.rules"))),
                  )}
                </strong>
                <dl>
                  {(
                    fields[resource] ?? [
                      { name: "reason", label: "pricing.reason" as const },
                      { name: "created_at", label: "pricing.created" as const },
                    ]
                  ).map((field) => (
                    <div key={field.name}>
                      <dt>{t(field.label)}</dt>
                      <dd>
                        {renderFieldValue(field, item[field.name], { costLists, configurations })}
                      </dd>
                    </div>
                  ))}
                </dl>
                {resource !== "audits" && resource !== "fx" && (
                  <button type="button" disabled={busy} onClick={() => setEditing(item)}>
                    {t("pricing.edit")}
                  </button>
                )}
              </article>
            ))
          )}
        </div>
        {fields[resource] && resource !== "audits" && (
          <form
            noValidate
            key={`${resource}-${editing?.id ?? "new"}-${revision}`}
            onSubmit={(event) => void save(event)}
            className="pricing-form"
          >
            <h2>{t(editing ? "pricing.editRecord" : "pricing.newRecord")}</h2>
            {fields[resource].map((field) => (
              <label key={field.name}>
                {t(field.label)}
                {field.name === "cost_list_id" || field.name === "configuration_id" ? (
                  <select
                    name={field.name}
                    required
                    disabled={busy}
                    defaultValue={String(editing?.[field.name] ?? "")}
                  >
                    <option value="">{t("pricing.chooseAuthority")}</option>
                    {(field.name === "cost_list_id" ? costLists : configurations).map((row) => (
                      <option key={String(row.id)} value={String(row.id)}>
                        {field.name === "cost_list_id"
                          ? `${row.supplier_name} · ${row.currency} · ${row.valid_from}`
                          : `${contextLabel(row.context_code)} · ${optionLabel(String(row.typology))} · ${optionLabel(String(row.pricing_mode))}`}
                      </option>
                    ))}
                  </select>
                ) : field.options ? (
                  <select
                    name={field.name}
                    defaultValue={String(
                      editing?.[field.name] ?? field.initial ?? field.options[0],
                    )}
                    disabled={busy}
                  >
                    {field.options.map((value) => (
                      <option key={value} value={value}>
                        {optionLabel(value)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    name={field.name}
                    type={field.type === "percent" ? "number" : (field.type ?? "text")}
                    step={field.type === "percent" ? "0.1" : undefined}
                    min={field.type === "percent" ? "0" : undefined}
                    max={field.type === "percent" ? "100" : undefined}
                    list={
                      resource === "cost-items" && field.name === "sku"
                        ? "pricing-catalog-skus"
                        : undefined
                    }
                    required={!field.optional}
                    defaultValue={
                      field.type === "percent"
                        ? editing?.[field.name] !== undefined &&
                          editing?.[field.name] !== null &&
                          editing?.[field.name] !== ""
                          ? pctInput(editing[field.name])
                          : (field.initial ?? "0")
                        : String(editing?.[field.name] ?? field.initial ?? "")
                    }
                    disabled={busy}
                  />
                )}
              </label>
            ))}
            {resource === "cost-items" && (
              <datalist id="pricing-catalog-skus">
                {catalogSkus.map((row) => (
                  <option key={String(row.sku)} value={String(row.sku)}>
                    {String(row.name)} ·{" "}
                    {t(coverageKindLabels[String(row.kind)] ?? "pricing.coverageKind.other")}
                  </option>
                ))}
              </datalist>
            )}
            {(resource === "cost-lists" || resource === "configurations") && (
              <label>
                <input
                  type="checkbox"
                  name="is_active"
                  defaultChecked={editing?.is_active !== false}
                  disabled={busy}
                />
                {t("pricing.active")}
              </label>
            )}
            <label>
              {t("pricing.reason")}
              <input name="reason" required maxLength={1000} disabled={busy} />
            </label>
            <button type="submit" disabled={busy}>
              {t("pricing.save")}
            </button>
            {editing && (
              <button type="button" disabled={busy} onClick={() => setEditing(null)}>
                {t("pricing.cancel")}
              </button>
            )}
          </form>
        )}
      </div>
      {(resource === "cost-lists" || resource === "cost-items") && (
        <ImportCosts
          request={request}
          costLists={costLists}
          onSaved={() => setRevision((value) => value + 1)}
        />
      )}
    </section>
  );
}

const coverageKindLabels: Record<string, Parameters<typeof t>[0]> = {
  PROFILE: "pricing.coverageKind.profile",
  GLASS: "pricing.coverageKind.glass",
  HARDWARE: "pricing.coverageKind.hardware",
  REINFORCEMENT: "pricing.coverageKind.reinforcement",
  PANEL: "pricing.coverageKind.panel",
  FITTING: "pricing.coverageKind.fitting",
};

function CoverageList({ items }: { items: Row[] }): JSX.Element {
  const [onlyMissing, setOnlyMissing] = useState(false);
  const missing = items.filter((item) => Number(item.active_cost_items ?? 0) === 0);
  const shown = onlyMissing ? missing : items;
  return (
    <>
      <p className="coverage-summary">
        <strong>{missing.length}</strong> / {items.length} {t("pricing.coverageNoPrice")}{" "}
        {missing.length > 0 && (
          <button
            type="button"
            className="link-button"
            aria-pressed={onlyMissing}
            onClick={() => setOnlyMissing((value) => !value)}
          >
            {t(onlyMissing ? "pricing.coverageShowAll" : "pricing.coverageOnlyMissing")}
          </button>
        )}
      </p>
      {shown.map((item) => {
        const uncovered = Number(item.active_cost_items ?? 0) === 0;
        return (
          <article
            key={`${String(item.kind)}-${String(item.sku)}`}
            className={uncovered ? "coverage-card coverage-card--missing" : "coverage-card"}
          >
            <strong>{String(item.sku)}</strong>
            <span>{String(item.name)}</span>
            <span className="coverage-card__meta">
              {t(coverageKindLabels[String(item.kind)] ?? "pricing.coverageKind.other")} ·{" "}
              {String(item.required_unit)}
            </span>
            <StatusBadge
              label={
                uncovered
                  ? t("pricing.coverageMissing")
                  : `${Number(item.active_cost_items ?? 0)} ${t("pricing.coverageLists")}`
              }
              tone={uncovered ? "danger" : "success"}
            />
          </article>
        );
      })}
    </>
  );
}

const auditInternalKeys = new Set(["id", "org_id", "updated_at", "created_at"]);

function auditRecordLabel(entity: string, record: Record<string, unknown> | null): string {
  if (!record) return "";
  for (const key of [
    "sku",
    "commercial_sku",
    "supplier_name",
    "code",
    "name",
    "context_code",
    "pricing_mode",
    "source",
    "revision_code",
  ]) {
    const value = record[key];
    if (typeof value === "string" && value !== "") return value;
  }
  const id = record["entity_id"] ?? record["id"];
  return typeof id === "string" ? `${entity} ${shortTechnicalId(id)}` : entity;
}

function auditValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

function auditDiffs(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
): [string, string, string][] {
  if (!after) return [];
  const diffs: [string, string, string][] = [];
  for (const [key, value] of Object.entries(after)) {
    if (auditInternalKeys.has(key)) continue;
    const prior = before?.[key];
    if (before === null || JSON.stringify(prior) !== JSON.stringify(value)) {
      diffs.push([key, auditValue(prior), auditValue(value)]);
    }
  }
  return diffs;
}

function AuditCard({ item }: { item: Row }): JSX.Element {
  const entity = String(item.entity ?? "");
  const verb = String(item.field ?? "");
  const after = (item.new_record ?? null) as Record<string, unknown> | null;
  const before = (item.old_record ?? null) as Record<string, unknown> | null;
  const diffs = auditDiffs(before, after);
  const label = auditRecordLabel(entity, after ?? before);
  const project = item.project_code
    ? `${String(item.project_code)}${item.project_name ? ` — ${String(item.project_name)}` : ""}`
    : "";
  return (
    <article className="audit-card">
      <header className="audit-card__header">
        <strong>{t(auditEntityLabels[entity] ?? "pricing.auditEntity.other")}</strong>
        <StatusBadge
          label={t(auditActionLabels[verb] ?? "pricing.auditAction.other")}
          tone={verb === "INSERT" ? "success" : verb === "DELETE" ? "danger" : "warning"}
        />
        {project !== "" && <span className="audit-card__project">{project}</span>}
      </header>
      {label !== "" && <p className="audit-card__title">{label}</p>}
      {diffs.length > 0 ? (
        <ul className="audit-card__diffs">
          {diffs.slice(0, 8).map(([key, oldValue, newValue]) => (
            <li key={key}>
              <code>{key}</code>: <span>{oldValue}</span> → <strong>{newValue}</strong>
            </li>
          ))}
          {diffs.length > 8 && (
            <li>
              +{diffs.length - 8} {t("pricing.auditMore")}
            </li>
          )}
        </ul>
      ) : (
        ((item.old_value !== undefined && item.old_value !== null) ||
          (item.new_value !== undefined && item.new_value !== null)) && (
          <p className="audit-card__diffs">
            {auditValue(item.old_value)} → <strong>{auditValue(item.new_value)}</strong>
          </p>
        )
      )}
      <footer className="audit-card__footer">
        <span>{t(auditActorLabels[String(item.actor_type)] ?? "pricing.auditActor.other")}</span>
        {item.reason ? <span>{String(item.reason)}</span> : null}
        <time dateTime={String(item.created_at)}>{formatDateTime(String(item.created_at))}</time>
      </footer>
    </article>
  );
}

type RequestFn = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
function ImportCosts({
  request,
  costLists,
  onSaved,
}: {
  request: RequestFn;
  costLists: Row[];
  onSaved: () => void;
}): JSX.Element {
  const [preview, setPreview] = useState<Row[]>([]);
  const [pending, setPending] = useState<FormData | null>(null);
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRevision = useRef(0);
  const requestSequence = useRef(0);
  const activeRequest = useRef<{ id: number; apply: boolean } | null>(null);
  const pendingAuthority = useRef<FormData | null>(null);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      inputRevision.current += 1;
      activeRequest.current = null;
      pendingAuthority.current = null;
    };
  }, []);
  async function run(form: FormData, apply: boolean): Promise<void> {
    if (!mounted.current) return;
    if (apply) {
      if (activeRequest.current !== null || pendingAuthority.current !== form) return;
      pendingAuthority.current = null;
    } else if (activeRequest.current?.apply) {
      return;
    }
    const revision = inputRevision.current;
    const body = new FormData();
    form.forEach((value, key) => {
      body.append(key, value);
    });
    body.set("apply", String(apply));
    const id = ++requestSequence.current;
    activeRequest.current = { id, apply };
    pendingAuthority.current = null;
    setPreview([]);
    setPending(null);
    setError("");
    setBusy(true);
    try {
      const response = await request<{ items: Row[] }>("import/", "POST", body);
      const current = mounted.current && activeRequest.current?.id === id;
      const fresh = revision === inputRevision.current;
      if (current && fresh) {
        setPreview(response.items);
        if (!apply) {
          pendingAuthority.current = body;
          setPending(body);
        }
      }
    } catch {
      const current = mounted.current && activeRequest.current?.id === id;
      const fresh = revision === inputRevision.current;
      if (current && fresh) {
        setError(t("pricing.importError"));
        setPending(null);
      }
    } finally {
      if (mounted.current && activeRequest.current?.id === id) {
        activeRequest.current = null;
        setBusy(false);
        if (apply) onSaved();
      }
    }
  }
  return (
    <section className="pricing-import">
      <h2>{t("pricing.import")}</h2>
      <form
        noValidate
        onChange={() => {
          inputRevision.current += 1;
          pendingAuthority.current = null;
          setPending(null);
          setPreview([]);
          setError("");
        }}
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          form.set(
            "mapping",
            JSON.stringify(
              Object.fromEntries(
                ["sku", "description", "unit", "unit_cost"].map((key) => [
                  key,
                  form.get(`column_${key}`),
                ]),
              ),
            ),
          );
          void run(form, false);
        }}
      >
        <label>
          {t("pricing.listId")}
          <select name="cost_list_id" required defaultValue="">
            <option value="">{t("pricing.chooseAuthority")}</option>
            {costLists.map((row) => (
              <option key={String(row.id)} value={String(row.id)}>
                {String(row.supplier_name)} · {String(row.currency)} · {String(row.valid_from)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("pricing.file")}
          <span className="file-field">
            <span className="ui-button ui-button--small">{t("settings.fileChoose")}</span>
            <span className="file-field__name">{fileName || t("settings.fileNone")}</span>
          </span>
          <input
            type="file"
            className="file-input-hidden"
            accept=".xlsx"
            name="file"
            required
            aria-label={t("pricing.file")}
            onChange={(event) => setFileName(event.target.files?.[0]?.name ?? "")}
          />
        </label>
        <div className="form-grid">
          {["sku", "description", "unit", "unit_cost"].map((key, index) => (
            <label key={key}>
              {t("pricing.column")} ·{" "}
              {t(
                ["pricing.sku", "pricing.description", "pricing.unit", "pricing.cost"][
                  index
                ] as Parameters<typeof t>[0],
              )}
              <input
                name={`column_${key}`}
                required
                defaultValue={["SKU", "Descripción", "Unidad", "Precio Unitario"][index]}
              />
            </label>
          ))}
          <label>
            {t("pricing.separator")}
            <select name="decimal_separator">
              <option value=".">.</option>
              <option value=",">,</option>
            </select>
          </label>
          <label>
            {t("pricing.reason")}
            <input name="reason" required />
          </label>
        </div>
        <button disabled={busy}>{t("pricing.previewImport")}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {preview.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t("pricing.sku")}</th>
              <th>{t("pricing.unit")}</th>
              <th>{t("pricing.cost")}</th>
            </tr>
          </thead>
          <tbody>
            {preview.map((row) => (
              <tr key={String(row.sku)}>
                <td>{String(row.sku)}</td>
                <td>{String(row.unit)}</td>
                <td>{formatMoney(String(row.unit_cost), "CLP")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {pending && (
        <button disabled={busy} onClick={() => void run(pending, true)}>
          {t("pricing.confirmImport")}
        </button>
      )}
    </section>
  );
}

type Operation = PriceResponse;

/** One position's technical price formation: what the engine attributed to
 * materials, the waste/labour rates the authority supplied, and how the line
 * net falls out of unit cost × quantity × discount. */
function CostComposition({
  entry,
  currency,
  discount,
  lineNet,
  lineCost,
}: {
  entry: NonNullable<PriceResponse["positions_breakdown"]>[number];
  currency: string;
  discount: number;
  lineNet: string;
  lineCost: string;
}): JSX.Element {
  const area = Number(entry.area_m2);
  const rates = Number(entry.labor_rate_per_m2) + Number(entry.installation_rate_per_m2);
  const labour = Number.isFinite(area) && Number.isFinite(rates) ? area * rates : null;
  // BOM cut rows map 1:1 into components — the estimator reads materials,
  // not cuts, so identical SKUs aggregate into one row.
  const grouped = new Map<
    string,
    { kind: string; sku: string; unit: string; qtyScaled: bigint; cents: bigint }
  >();
  for (const component of entry.composition ?? []) {
    const key = `${component.kind}|${component.sku}|${component.unit}`;
    const existing = grouped.get(key);
    const cents = moneyCents(component.cost ?? "0") ?? 0n;
    // Quantities are Decimals: accumulate on a 6dp integer scale so float
    // addition never leaks artifacts like 5.6240000000000006 into the UI.
    const qtyScaled = BigInt(Math.round(Number(component.quantity ?? 0) * 1e6));
    if (existing) {
      existing.qtyScaled += qtyScaled;
      existing.cents += cents;
    } else {
      grouped.set(key, {
        kind: component.kind ?? "",
        sku: component.sku ?? "",
        unit: component.unit ?? "",
        qtyScaled,
        cents,
      });
    }
  }
  const netCents = moneyCents(lineNet);
  const costCents = moneyCents(lineCost);
  const marginPct =
    netCents !== null && costCents !== null && netCents > 0n
      ? Number(((netCents - costCents) * 10000n) / netCents) / 100
      : null;
  return (
    <div className="cost-composition">
      <table className="cost-composition__table">
        <tbody>
          {[...grouped.values()].map((component, index) => (
            <tr key={index}>
              <td>{optionLabel(component.kind)}</td>
              <td>{component.sku}</td>
              <td>
                {Number(component.qtyScaled) / 1e6} {optionLabel(component.unit)}
              </td>
              <td>
                {formatMoney(
                  `${component.cents / 100n}.${`${component.cents % 100n}`.padStart(2, "0")}`,
                  currency,
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="cost-composition__math">
        {t("pricing.materials")} {formatMoney(entry.materials_cost ?? "0", currency)} +{" "}
        {t("pricing.wasteShort")} {formatPercent(entry.waste_pct)}
        {labour !== null &&
          ` + ${t("pricing.laborShort")} ${formatMoney(String(labour), currency)}`}{" "}
        → {t("pricing.unitCost")} {formatMoney(entry.unit_cost ?? "0", currency)}
        {marginPct !== null &&
          ` · ${t("pricing.marginRealized")} ${formatPercent(marginPct, "points")}`}
        {discount > 0 && ` · ${t("pricing.discount")} ${formatPercent(discount)}`} →{" "}
        {formatMoney(lineNet, currency)}
      </p>
    </div>
  );
}

/** Whole-percent-free margin: (net − cost) / net, both Decimal strings —
 * computed in cents so the display never carries a float artifact. */
function moneyCents(value: string): bigint | null {
  const match = value.trim().match(/^(-?)(\d*)(?:\.(\d*))?$/);
  if (match === null || (match[2] === "" && (match[3] ?? "") === "")) return null;
  const units = match[2] === "" ? "0" : match[2];
  const fraction = `${match[3] ?? ""}00`.slice(0, 2);
  return BigInt(`${match[1]}${units}${fraction}`);
}
function marginText(net: string, cost: string, currency: string): string {
  const netCents = moneyCents(net);
  const costCents = moneyCents(cost);
  if (netCents === null || costCents === null || netCents <= 0n) return "—";
  const diffCents = netCents - costCents;
  const margin = Number((diffCents * 10_000n) / netCents) / 100;
  const whole = diffCents / 100n;
  const cents = diffCents % 100n;
  const signed = diffCents < 0n ? "-" : "";
  const text = `${signed}${whole < 0n ? -whole : whole}.${`${cents < 0n ? -cents : cents}`.padStart(2, "0")}`;
  return `${formatMoney(text, currency)} · ${formatPercent(margin, "points")}`;
}

// ——— P07 workspace payloads — server-derived, rendered verbatim ———

type BandPayload = {
  min?: string;
  objective?: string;
  max?: string;
  state?: string;
};
type CascadeRowPayload = { key?: string; amount?: string; kind?: string };
type CascadePositionPayload = {
  position_index?: number;
  groups?: Record<string, string>;
  materials?: string;
  waste?: string;
  labour?: string;
  rounding?: string;
  cost?: string;
  margin?: string;
  sell?: string;
  list_price?: string;
  discount?: string;
  net?: string;
};
type CascadePayload = {
  rows?: CascadeRowPayload[];
  positions?: CascadePositionPayload[];
  margin_realized?: string | null;
};
type DeltaDriverPayload = {
  driver?: string;
  net_delta?: string;
  cost_delta?: string;
  net_after?: string;
};
type DeltaPayload = {
  baseline_revision?: string;
  baseline_net?: string;
  proposed_net?: string;
  net_delta?: string;
  drivers?: DeltaDriverPayload[];
};

function cascadeRowLabel(key: string): string {
  return t(`pricing.cascadeRow.${key}` as never);
}

/** P07 — the org's declared margin band as a gauge: min→max corridor,
 * the objective tick, and the realized marker. The state the server
 * computed drives the chip — the UI never re-judges it. */
function MarginBand({
  band,
  owner,
  realized,
}: {
  band: BandPayload;
  owner: boolean;
  realized: string | null;
}) {
  const min = Number(band.min);
  const max = Number(band.max);
  const objective = Number(band.objective);
  const value = realized === null || realized === undefined ? null : Number(realized);
  if (![min, max, objective].every(Number.isFinite)) return null;
  const span = max * 1.25 || 1;
  const at = (v: number) => `${Math.min(100, Math.max(0, (v / span) * 100))}%`;
  const state = band.state ?? "";
  return (
    <section className="margin-band" aria-label={t("pricing.marginBand")}>
      <h3>{t("pricing.marginBand")}</h3>
      <div className="margin-band__track">
        <span
          className="margin-band__corridor"
          style={{ left: at(min), right: `${100 - (max / span) * 100}%` }}
        />
        <span className="margin-band__objective" style={{ left: at(objective) }} />
        {value !== null && Number.isFinite(value) && (
          <span className="margin-band__marker" style={{ left: at(value) }} />
        )}
      </div>
      <p className="margin-band__labels">
        <span>
          {t("pricing.marginMin")} {formatPercent(band.min)}
        </span>
        <span>
          {t("pricing.bandObjective")} {formatPercent(band.objective)}
        </span>
        <span>
          {t("pricing.marginMax")} {formatPercent(band.max)}
        </span>
        {value !== null && (
          <strong>
            {t("pricing.bandRealized")} {formatPercent(String(value))}
          </strong>
        )}
        <StatusBadge
          label={t(`pricing.band.${state}` as never)}
          tone={state === "IN_BAND" ? "success" : "warning"}
        />
        {state !== "IN_BAND" && !owner && (
          <span className="operation-warning">{t("pricing.bandPendingHint")}</span>
        )}
      </p>
    </section>
  );
}

/** P07 — the exact waterfall the engine closed: family groups, then the
 * landmark rows (materiales → costo → margen → lista → neto → total). A
 * position panel shows the same chain at line level. */
function PriceCascade({
  authorities,
  cascade,
  currency,
}: {
  authorities?: unknown[];
  cascade: CascadePayload;
  currency: string;
}) {
  const rows = cascade.rows ?? [];
  const positions = cascade.positions ?? [];
  if (!rows.length) return null;
  return (
    <section className="price-cascade">
      <h3>{t("pricing.cascade")}</h3>
      {(authorities ?? []).length > 0 && (
        <details className="operation-authorities">
          <summary>{t("pricing.authorities")}</summary>
          <ul>
            {(authorities ?? []).map((authority, index) => (
              <li key={index}>{flattenAuthority(authority).join(" · ")}</li>
            ))}
          </ul>
        </details>
      )}
      <table className="price-cascade__table">
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              className={`price-cascade__row price-cascade__row--${row.kind ?? "step"}`}
            >
              <td>{cascadeRowLabel(String(row.key))}</td>
              <td className="operation-lines__money">
                {formatMoney(String(row.amount ?? "0"), currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {positions.length > 0 && (
        <details className="price-cascade__positions">
          <summary>{t("pricing.cascadePosition")}</summary>
          {positions.map((position) => (
            <table
              className="price-cascade__table price-cascade__table--position"
              key={position.position_index}
            >
              <caption>#{position.position_index}</caption>
              <tbody>
                {Object.entries(position.groups ?? {})
                  .filter(([, amount]) => Number(amount) !== 0)
                  .map(([group, amount]) => (
                    <tr key={group} className="price-cascade__row price-cascade__row--group">
                      <td>{cascadeRowLabel(group)}</td>
                      <td className="operation-lines__money">{formatMoney(amount, currency)}</td>
                    </tr>
                  ))}
                {(
                  [
                    "materials",
                    "waste",
                    "labour",
                    "rounding",
                    "cost",
                    "margin",
                    "sell",
                    "list_price",
                    "discount",
                    "net",
                  ] as const
                ).map((key) => (
                  <tr
                    key={key}
                    className={`price-cascade__row ${
                      ["cost", "list_price", "net"].includes(key)
                        ? "price-cascade__row--subtotal"
                        : ""
                    }`}
                  >
                    <td>{cascadeRowLabel(key === "cost" ? "cost_total" : key)}</td>
                    <td className="operation-lines__money">
                      {formatMoney(String(position[key] ?? "0"), currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </details>
      )}
    </section>
  );
}

/** P07 — "¿Por qué cambió?": the driver's net contribution in the
 * canonical order — the amounts sum to the total Δ by construction. */
function DeltaBreakdown({ delta, currency }: { delta: DeltaPayload; currency: string }) {
  const drivers = delta.drivers ?? [];
  if (!drivers.length) return null;
  const signed = (value: string | undefined) => {
    const amount = Number(value ?? "0");
    return (
      <span data-negative={amount < 0 || undefined}>
        {amount > 0 ? "+" : ""}
        {formatMoney(String(value ?? "0"), currency)}
      </span>
    );
  };
  return (
    <section className="delta-breakdown">
      <h3>
        {t("pricing.delta")}
        {delta.baseline_revision && (
          <span className="delta-breakdown__baseline">
            {" "}
            · {t("pricing.deltaBaseline")} {delta.baseline_revision}
          </span>
        )}
      </h3>
      <table className="delta-breakdown__table">
        <thead>
          <tr>
            <th scope="col">{t("pricing.deltaLabel")}</th>
            <th scope="col" className="operation-lines__money">
              {t("pricing.deltaNet")}
            </th>
            <th scope="col" className="operation-lines__money">
              {t("pricing.deltaCost")}
            </th>
            <th scope="col" className="operation-lines__money">
              {t("pricing.deltaAfter")}
            </th>
          </tr>
        </thead>
        <tbody>
          {drivers.map((driver) => (
            <tr key={driver.driver}>
              <td>{t(`pricing.deltaDriver.${driver.driver}` as never)}</td>
              <td className="operation-lines__money">{signed(driver.net_delta)}</td>
              <td className="operation-lines__money">{signed(driver.cost_delta)}</td>
              <td className="operation-lines__money">
                {formatMoney(String(driver.net_after ?? "0"), currency)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td>{t("pricing.deltaLabel")}</td>
            <td className="operation-lines__money">{signed(delta.net_delta)}</td>
            <td />
            <td className="operation-lines__money">
              {formatMoney(String(delta.proposed_net ?? "0"), currency)}
            </td>
          </tr>
        </tfoot>
      </table>
    </section>
  );
}

/** §03-D — the pricing decision surface: the estimator and the approver
 * read the SAME frozen numbers — per-position cost vs selling, project
 * margin, the recorded reason and who applied/rejected it. */

/** Nested authority records flatten to `key.sub: value` pairs — String(value)
 * on an object renders '[object Object]', which the audit panel shipped. */
function flattenAuthority(value: unknown, prefix = ""): string[] {
  if (Array.isArray(value)) {
    return [`${prefix}: ${value.length} ítems`];
  }
  if (value !== null && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, sub]) =>
      flattenAuthority(sub, prefix ? `${prefix}.${key}` : key),
    );
  }
  return [`${prefix}: ${String(value)}`];
}

function OperationDecision({
  operation,
  owner,
  busy,
  reasonReady,
  boundProject,
  projectLabel,
  currentUserId,
  onApply,
  stale,
  onReject,
  onWithdraw,
}: {
  operation: Operation;
  owner: boolean;
  busy: boolean;
  reasonReady: boolean;
  boundProject?: ProjectResponse;
  projectLabel?: string;
  currentUserId?: string;
  stale?: boolean;
  onApply: () => void;
  onReject: () => void;
  onWithdraw?: () => void;
}): JSX.Element {
  const costs = new Map(
    (operation.cost_lines ?? []).map((line) => [line.position_index, line.line_cost]),
  );
  // The preview's technical snapshot prices each position line-by-line:
  // kind/SKU/quantity/cost plus the waste and labour rates the authority
  // supplied. Estimators fold it open under each net line.
  const breakdowns = new Map(
    (operation.positions_breakdown ?? []).map((entry) => [entry.position_index, entry]),
  );
  // Position metadata joins only when the operation targets the live
  // revision of the project it actually belongs to — a stale operation's
  // indexes can point at moved/deleted positions, and a project fetched
  // for another operation must never loan its labels, so both stay empty
  // rather than mislead.
  const isBoundProject = boundProject?.id === operation.project_id;
  const positions = new Map(
    (isBoundProject && operation.revision_code === boundProject?.current_revision
      ? (boundProject.positions ?? [])
      : []
    ).map((position) => [position.position_index, position]),
  );
  // Baseline for the delta: the live priced totals, or — after a successor
  // revision zeroed them — the latest sealed version's snapshot totals (what
  // the customer was actually quoted). Without it CURRENT→PROPOSED is
  // invisible exactly when it matters: the reprice decision.
  const sealedBaseline = isBoundProject
    ? [...(boundProject?.versions ?? [])].filter((version) => version.sealed_price_gross).at(-1)
    : undefined;
  const baselineGross =
    boundProject?.pricing_current && boundProject.total_price_gross
      ? boundProject.total_price_gross
      : (sealedBaseline?.sealed_price_gross ?? null);
  const baselineCurrency = boundProject?.pricing_current
    ? boundProject.currency
    : (sealedBaseline?.sealed_currency ?? boundProject?.currency);
  // A delta is only meaningful when both sides share a currency — a
  // historical operation in another currency shows its own totals instead.
  const sameCurrency = baselineCurrency === operation.currency;
  const diff =
    isBoundProject && baselineGross && Number(baselineGross) > 0 && sameCurrency
      ? Number(operation.project_gross) - Number(baselineGross)
      : null;
  const diffPct =
    diff !== null && Number(baselineGross) > 0 ? (diff / Number(baselineGross)) * 100 : null;
  // Per-position delta: the live price_net of the bound revision vs the
  // proposed line_net — same position index, same currency, never a guess.
  // Only a live applied quote (pricing_current) is a real baseline: with no
  // applied quote the live net is modelled, not quoted, and the delta would
  // echo the whole amount like a change. The header already explains the
  // absence with 'sin comparación'.
  const canLineDelta = isBoundProject && sameCurrency && !!boundProject?.pricing_current;
  // Category rollup: every cost component across all positions aggregated by
  // kind — the 'why' behind the total, in exact cents (no float artifacts).
  const kindTotals = new Map<string, bigint>();
  for (const entry of operation.positions_breakdown ?? []) {
    for (const component of entry.composition ?? []) {
      const cents = moneyCents(component.cost ?? "0");
      if (cents === null) continue;
      const kind = component.kind ?? "OTHER";
      kindTotals.set(kind, (kindTotals.get(kind) ?? 0n) + cents);
    }
  }
  const kindRows = [...kindTotals.entries()].sort((a, b) =>
    a[1] > b[1] ? -1 : a[1] < b[1] ? 1 : 0,
  );
  const discount = Number(operation.discount_pct ?? 0);
  // finish_lines applies the discount per line, so net/(1−d) reproduces the
  // pre-discount list price exactly — no second authority needed.
  const listNet =
    discount > 0 && discount < 1 ? Number(operation.project_net) / (1 - discount) : null;
  const netCents = moneyCents(operation.project_net);
  const costCents = moneyCents(operation.total_cost);
  const realizedPct =
    netCents !== null && costCents !== null && netCents > 0n
      ? Number(((netCents - costCents) * 10000n) / netCents) / 100
      : null;
  const objective = Number(operation.rules?.default_margin_pct ?? NaN);
  // Compare at the displayed precision (marginText renders one decimal):
  // a realized 34.9998% shows as "35.0 %" — flagging it "below objective"
  // next to that readout would contradict the number on screen.
  const marginBelow =
    realizedPct !== null &&
    Number.isFinite(objective) &&
    Math.round(realizedPct * 10) / 10 < objective * 100;
  return (
    <article className="operation-decision">
      <header className="operation-decision__head">
        <StatusChip enumName="PriceResponseStateEnum" value={operation.state} />
        {projectLabel && (
          <span className="operation-decision__meta">
            {t("pricing.projectId")}: {projectLabel}
          </span>
        )}
        <span className="operation-decision__meta">
          {operation.revision_code} · {t("pricing.discount")}{" "}
          {formatPercent(operation.discount_pct)}·{" "}
          <time dateTime={operation.created_at}>{formatDateTime(operation.created_at)}</time>
        </span>
        {stale && <p className="operation-decision__stale">{t("pricing.staleHint")}</p>}
      </header>

      {diff !== null && baselineGross ? (
        <div className="operation-compare">
          <div className="operation-compare__cell">
            <span>
              {t("pricing.currentTotal")}
              {sealedBaseline && !boundProject?.pricing_current
                ? ` · ${sealedBaseline.revision_code}`
                : ""}
            </span>
            <strong>{formatMoney(baselineGross, operation.currency)}</strong>
          </div>
          <span className="operation-compare__arrow" aria-hidden>
            →
          </span>
          <div className="operation-compare__cell">
            <span>{t("pricing.proposedTotal")}</span>
            <strong>{formatMoney(operation.project_gross, operation.currency)}</strong>
          </div>
          <div
            className="operation-compare__cell operation-compare__delta"
            data-negative={diff < 0 || undefined}
          >
            <span>{t("pricing.deltaLabel")}</span>
            <strong>
              {diff > 0 ? "+" : ""}
              {formatMoney(String(diff), operation.currency)}
              {diffPct !== null && (
                <small>
                  {" "}
                  ({diffPct > 0 ? "+" : ""}
                  {formatPercent(diffPct, "points")})
                </small>
              )}
            </strong>
          </div>
        </div>
      ) : null}

      <div className="operation-totals">
        <div className="operation-total">
          <dt>{t("pricing.totalCost")}</dt>
          <dd>{formatMoney(operation.total_cost, operation.currency)}</dd>
        </div>
        <div className="operation-total">
          <dt>{t("pricing.marginNet")}</dt>
          <dd>
            {marginText(operation.project_net, operation.total_cost, operation.currency)}
            {marginBelow && (
              <span className="operation-warning">{t("pricing.marginBelowObjective")}</span>
            )}
          </dd>
        </div>
        {listNet !== null && (
          <div className="operation-total">
            <dt>{t("pricing.listPrice")}</dt>
            <dd>{formatMoney(String(listNet), operation.currency)}</dd>
          </div>
        )}
        {(operation.extras ?? []).map((item, index) => (
          <div className="operation-total" key={`${item.label}-${index}`}>
            <dt>{String(item.label ?? t("pricing.extras"))}</dt>
            <dd>{formatMoney(String(item.amount ?? "0"), operation.currency)}</dd>
          </div>
        ))}
        <div className="operation-total">
          <dt>{t("pricing.net")}</dt>
          <dd>{formatMoney(operation.project_net, operation.currency)}</dd>
        </div>
        <div className="operation-total">
          <dt>{t("pricing.taxTotal")}</dt>
          <dd>{formatMoney(operation.project_tax, operation.currency)}</dd>
        </div>
        <div className="operation-total operation-total--gross">
          <dt>{t("pricing.gross")}</dt>
          <dd>{formatMoney(operation.project_gross, operation.currency)}</dd>
        </div>
        {diff !== null && diff !== 0 && (
          <div className="operation-total">
            <dt>{t("pricing.vsCurrent")}</dt>
            <dd data-negative={diff < 0 || undefined}>
              {diff > 0 ? "+" : ""}
              {formatMoney(String(diff), operation.currency)}
            </dd>
          </div>
        )}
      </div>

      {(operation.band as BandPayload | null) && (
        <MarginBand
          band={operation.band as BandPayload}
          owner={owner}
          realized={operation.margin_realized ?? null}
        />
      )}
      {(operation.cascade as CascadePayload | null)?.rows?.length ? (
        <PriceCascade
          authorities={operation.authorities ?? []}
          cascade={operation.cascade as CascadePayload}
          currency={operation.currency}
        />
      ) : (
        <p className="operation-decision__meta">{t("pricing.noCascade")}</p>
      )}
      {(operation.delta as DeltaPayload | null)?.drivers?.length ? (
        <DeltaBreakdown delta={operation.delta as DeltaPayload} currency={operation.currency} />
      ) : (
        <p className="operation-decision__meta">{t("pricing.noDelta")}</p>
      )}

      <div className="operation-lines__wrap">
        <table className="operation-lines">
          <caption>{t("pricing.perPosition")}</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">{t("projects.location")}</th>
              <th scope="col">{t("pricing.quantity")}</th>
              <th scope="col">{t("pricing.unitPrice")}</th>
              <th scope="col">{t("pricing.lineDiscount")}</th>
              <th scope="col">{t("pricing.lineCost")}</th>
              <th scope="col">{t("pricing.net")}</th>
              <th scope="col">{t("pricing.marginNet")}</th>
              {canLineDelta && <th scope="col">{t("pricing.lineDelta")}</th>}
            </tr>
          </thead>
          <tbody>
            {(operation.lines ?? []).map((line) => {
              const position = positions.get(line.position_index);
              const breakdown = breakdowns.get(line.position_index);
              const lineDiscount = line.discount_pct ? Number(line.discount_pct) : null;
              return (
                <Fragment key={line.position_index}>
                  <tr>
                    <td>
                      <span className="operation-lines__vano">
                        {position?.design && <PositionThumb design={position.design} />}
                        {line.position_index}
                      </span>
                    </td>
                    <td>{position?.location_tag || "—"}</td>
                    <td>{line.quantity ?? position?.quantity ?? "—"}</td>
                    <td className="operation-lines__money">
                      {line.unit_price != null
                        ? formatMoney(line.unit_price, operation.currency)
                        : "—"}
                    </td>
                    <td>
                      {lineDiscount !== null && lineDiscount > 0
                        ? `−${formatPercent(lineDiscount)}`
                        : "—"}
                    </td>
                    <td className="operation-lines__money">
                      {formatMoney(costs.get(line.position_index) ?? "0", operation.currency)}
                    </td>
                    <td className="operation-lines__money">
                      {discount > 0 && position?.quantity ? (
                        <>
                          {formatMoney(line.line_net, operation.currency)}
                          <span className="operation-lines__list">
                            {" "}
                            (
                            {formatMoney(
                              String(Number(line.line_net) / (1 - discount)),
                              operation.currency,
                            )}{" "}
                            −{formatPercent(discount)})
                          </span>
                        </>
                      ) : (
                        formatMoney(line.line_net, operation.currency)
                      )}
                    </td>
                    <td className="operation-lines__money">
                      {marginText(
                        line.line_net,
                        costs.get(line.position_index) ?? "0",
                        operation.currency,
                      )}
                    </td>
                    {canLineDelta && (
                      <td className="operation-lines__delta operation-lines__money">
                        {position?.price_net != null
                          ? (() => {
                              const lineDelta = Number(line.line_net) - Number(position.price_net);
                              return lineDelta !== 0 ? (
                                <span data-negative={lineDelta < 0 || undefined}>
                                  {lineDelta > 0 ? "+" : ""}
                                  {formatMoney(String(lineDelta), operation.currency)}
                                </span>
                              ) : (
                                "—"
                              );
                            })()
                          : "—"}
                      </td>
                    )}
                  </tr>
                  {breakdown && (
                    <tr className="operation-lines__detail">
                      <td colSpan={canLineDelta ? 9 : 8}>
                        <details>
                          <summary>{t("pricing.costComposition")}</summary>
                          <CostComposition
                            currency={operation.currency}
                            discount={discount}
                            entry={breakdown}
                            lineNet={line.line_net}
                            lineCost={costs.get(line.position_index) ?? "0"}
                          />
                        </details>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {kindRows.length > 0 && (
        <details className="operation-authorities">
          <summary>{t("pricing.costByKind")}</summary>
          <table className="cost-composition__table">
            <tbody>
              {kindRows.map(([kind, cents]) => (
                <tr key={kind}>
                  <td>{optionLabel(kind)}</td>
                  <td>
                    {formatMoney(
                      `${cents / 100n}.${`${cents % 100n}`.padStart(2, "0")}`,
                      operation.currency,
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      <p className="operation-decision__audit">
        {t("pricing.auditReason")}: {operation.reason || "—"} · {t("pricing.auditBy")}{" "}
        {operation.requested_by
          ? operation.requested_by === currentUserId
            ? t("pricing.auditYou")
            : (operation.requested_by_email ?? t("pricing.auditOtherUser"))
          : "—"}
        {operation.approved_at &&
          ` · ${t("pricing.auditDecided")} ${formatDateTime(operation.approved_at)}`}
      </p>

      {(operation.authorities ?? []).length > 0 &&
        !(operation.cascade as CascadePayload | null)?.rows?.length && (
          <details className="operation-authorities">
            <summary>{t("pricing.authorities")}</summary>
            <ul>
              {(operation.authorities ?? []).map((authority, index) => (
                <li key={index}>{flattenAuthority(authority).join(" · ")}</li>
              ))}
            </ul>
          </details>
        )}

      <div className="operation-decision__actions">
        {["PREVIEW", "PENDING"].includes(operation.state) &&
          (owner || operation.state !== "PENDING") && (
            <button
              className="ui-button"
              disabled={busy || !reasonReady || stale}
              onClick={onApply}
              type="button"
            >
              {t("pricing.apply")}
            </button>
          )}
        {operation.state === "PENDING" &&
          onWithdraw &&
          (owner || operation.requested_by === currentUserId) && (
            <button className="btn" disabled={busy || stale} onClick={onWithdraw} type="button">
              {t("pricing.withdraw")}
            </button>
          )}
        {owner && operation.state === "PENDING" && (
          <button
            className="ui-button ui-button--danger"
            disabled={busy || !reasonReady}
            onClick={onReject}
            type="button"
          >
            {t("pricing.reject")}
          </button>
        )}
      </div>
    </article>
  );
}
function CommercialOperations({
  request,
  owner,
  boundProjectId,
}: {
  request: RequestFn;
  owner: boolean;
  boundProjectId?: string;
}): JSX.Element {
  const [operation, setOperation] = useState<Operation | null>(null);
  const [error, setError] = useState("");
  const [fixCode, setFixCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [projectId, setProjectId] = useState(boundProjectId ?? "");
  const [selectedMode, setSelectedMode] = useState("COST_PLUS_MARGIN");
  // Project-level charges (instalación, traslado) — priced extras that ride
  // the pricing request into the sealed revision. Amounts are net.
  const [extras, setExtras] = useState<{ label: string; kind: string; amount: string }[]>([]);
  const [history, setHistory] = useState<Operation[]>([]);
  const [boundProject, setBoundProject] = useState<ProjectResponse | undefined>();
  // Bumped after a successful apply — the project's live totals changed, so
  // the vsCurrent comparison must rebind rather than diff against the
  // pre-apply snapshot.
  const [boundReload, setBoundReload] = useState(0);
  // Set when the form moves after a preview — the shown operation no longer
  // matches the inputs, so it stays visible but stops being applicable.
  const [stale, setStale] = useState(false);
  const [stateFilter, setStateFilter] = useState("");
  const generation = useRef(0);

  const me = useAuthSession().me;
  const orgId = me?.active_organization?.id;
  const currentUserId = me?.user?.id;

  const [projectOptions, setProjectOptions] = useState<ProjectResponse[]>([]);

  const [projectsError, setProjectsError] = useState(false);

  const [projectReload, setProjectReload] = useState(0);

  // FX snapshots exist as a managed resource — the quote form offers them as
  // a picklist instead of asking for a raw UUID nobody can type. Loaded lazily
  // on first focus: a USD picker is rare, and an unconditional mount fetch
  // would add a network call to every pricing visit.
  const [fxOptions, setFxOptions] = useState<Row[] | null>(null);
  function loadFxOptions(): void {
    if (fxOptions !== null) return;
    void request<{ items: Row[] }>("admin/fx/")
      .then((response) => setFxOptions(Array.isArray(response.items) ? response.items : []))
      .catch(() => setFxOptions([]));
  }

  useEffect(() => {
    let active = true;

    setProjectOptions([]);

    setProjectsError(false);

    if (orgId)
      void projectsList({ headers: { "X-Organization-ID": orgId } })
        .then((response) => {
          if (response.status !== 200) throw new Error("projects unavailable");

          if (active) setProjectOptions(response.data.items);
        })
        .catch(() => {
          if (active) setProjectsError(true);
        });

    return () => {
      active = false;
    };
  }, [orgId, projectReload]);

  const projectLabel = (project: ProjectResponse) =>
    [project.code, project.client_name, project.name].filter(Boolean).join(" · ");

  // The decision surface needs position labels and the currently applied
  // totals — fetch the operation's project once it exists. A new operation
  // must never see the previous project's labels: clear first, rebind only
  // when this operation's project answers, and never join across ids.
  useEffect(() => {
    let active = true;
    setBoundProject(undefined);
    if (!orgId || !operation?.project_id) {
      return;
    }
    void projectsRetrieve(operation.project_id, {
      headers: { "X-Organization-ID": orgId },
    })
      .then((response) => {
        if (active) setBoundProject(response.status === 200 ? response.data : undefined);
      })
      .catch(() => {
        if (active) setBoundProject(undefined);
      });
    return () => {
      active = false;
    };
  }, [orgId, operation?.project_id, boundReload]);

  // The audit requires a reason on every preview; seed the first quote's
  // reason so the estimator isn't blocked before any price exists — still
  // editable, still recorded verbatim in the audit trail.
  useEffect(() => {
    if (projectId && !reason && history.length === 0) {
      setReason(t("pricing.firstQuoteReason"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, history.length]);

  // The applied operation is the page's primary state — load history on
  // mount and whenever the active organization changes. The ref survives
  // StrictMode's simulated remount, so the dedupe is per organization, not
  // per effect run; the mount load's publish is guarded by the generation
  // counter like every other request, never by mount bookkeeping.
  const historyOrg = useRef<string | undefined>();
  const historyInflight = useRef<string | undefined>();
  function loadHistory(): Promise<"published" | "stopped" | "retry"> {
    let aborted = false;
    return runCurrent(
      () =>
        request<Operation[]>("operations/").catch((loadError: unknown) => {
          if (loadError instanceof DOMException && loadError.name === "AbortError") aborted = true;
          throw loadError;
        }),
      setHistory,
      "pricing.loadError",
    ).then((published) => (published ? "published" : aborted ? "retry" : "stopped"));
  }
  useEffect(() => {
    if (!orgId || historyOrg.current === orgId || historyInflight.current === orgId) return;
    historyInflight.current = orgId;
    // StrictMode's simulated unmount aborts the first request while the
    // component stays alive; an abort is retried once. A real failure is
    // surfaced by runCurrent's error state and a superseding request owns
    // the newer generation — neither is retried here.
    const finish = (result: string) => {
      if (historyInflight.current !== orgId) return;
      historyInflight.current = undefined;
      if (result === "published") historyOrg.current = orgId;
    };
    void loadHistory().then((result) => {
      if (result === "retry" && historyInflight.current === orgId) {
        void loadHistory().then(finish);
        return;
      }
      finish(result);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);
  function invalidate(): void {
    generation.current += 1;
    setBusy(false);
    setError("");
    setFixCode(null);
    setConfirmed(false);
  }
  async function runCurrent<T>(
    action: () => Promise<T>,
    publish: (value: T) => void,
    errorKey: Parameters<typeof t>[0],
  ): Promise<boolean> {
    const current = ++generation.current;
    setBusy(true);
    setError("");
    setFixCode(null);
    try {
      const value = await action();
      if (generation.current !== current) return false;
      publish(value);
      return true;
    } catch (error) {
      // An aborted request (unmount, StrictMode remount) is not an error
      // worth showing — the next load owns the surface.
      const aborted = error instanceof DOMException && error.name === "AbortError";
      if (generation.current === current && !aborted) {
        setError(pricingError(error, errorKey));
        setFixCode(pricingFixCode(error));
      }
      return false;
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }
  function reload(): Promise<boolean> {
    return runCurrent(() => request<Operation[]>("operations/"), setHistory, "pricing.loadError");
  }
  function isOperation(value: unknown): value is Operation {
    return (
      typeof value === "object" &&
      value !== null &&
      typeof (value as Operation).id === "string" &&
      typeof (value as Operation).state === "string" &&
      Array.isArray((value as Operation).lines)
    );
  }
  function publishOperation(value: Operation): void {
    if (!isOperation(value)) throw new Error("pricing.malformedOperation");
    setStale(false);
    setOperation(value);
    // The just-created operation belongs in the history immediately —
    // waiting for a manual Recargar made submissions look lost. Upsert
    // locally instead of refetching: a reload here would race the next
    // preview's request generation.
    setHistory((current) => {
      if (!Array.isArray(current)) return current;
      const index = current.findIndex((item) => item.id === value.id);
      if (index === -1) return [value, ...current];
      const next = [...current];
      next[index] = value;
      return next;
    });
    // Fuera de banda para un estimador = pedir aprobación: la causa queda
    // precargada (constitución §8) sin pisar un motivo ya escrito.
    const band = value.band as BandPayload | null | undefined;
    const outOfBand = band?.state === "BELOW_MIN" || band?.state === "ABOVE_MAX";
    setReason((current) =>
      outOfBand &&
      !owner &&
      (current.trim().length === 0 || current === t("pricing.firstQuoteReason"))
        ? t("pricing.bandReason")
        : current,
    );
  }
  function apply(reject = false): Promise<boolean> {
    if (!operation) return Promise.resolve(false);
    return runCurrent(
      () =>
        request<Operation>(`operations/${operation.id}/apply/`, "POST", {
          reason,
          confirmed,
          ...(reject ? { reject: true } : {}),
        }),
      (value) => {
        publishOperation(value);
        setHistory((rows) => rows.map((row) => (row.id === value.id ? value : row)));
        setBoundReload((count) => count + 1);
      },
      "pricing.applyError",
    );
  }
  function withdraw(): Promise<boolean> {
    if (!operation) return Promise.resolve(false);
    return runCurrent(
      () =>
        request<Operation>(`operations/${operation.id}/withdraw/`, "POST", {
          reason: reason || t("pricing.withdrawReason"),
        }),
      (value) => {
        publishOperation(value);
        setHistory((rows) => rows.map((row) => (row.id === value.id ? value : row)));
      },
      "pricing.applyError",
    );
  }
  return (
    <section>
      <h2>{t("pricing.calculate")}</h2>

      {projectsError && (
        <p role="alert">
          {t("projects.loadError")}{" "}
          <button type="button" onClick={() => setProjectReload((value) => value + 1)}>
            {t("pricing.reload")}
          </button>
        </p>
      )}
      {!boundProjectId && (
        <CommercialDraft
          request={request}
          onCreated={(id) => {
            invalidate();
            setOperation(null);
            setProjectId(id);

            setProjectReload((value) => value + 1);
          }}
        />
      )}
      <form
        noValidate
        className="commercial-form"
        onChange={(event) => {
          const target = event.target as HTMLInputElement;
          if (target.name === "reason" || target.name === "confirmed") return;
          invalidate();
          setStale(true);
        }}
        onSubmit={(event) => {
          event.preventDefault();
          const data = Object.fromEntries(new FormData(event.currentTarget));
          if (data.fx_snapshot_id === "") delete data.fx_snapshot_id;
          // Margen vacío → la regla por defecto; vacío no es 0 %.
          if (data.margin_pct === "" || data.margin_pct === undefined) delete data.margin_pct;
          // The UI collects percents; the authority stores fractions.
          for (const key of ["discount_pct", "target_margin", "margin_pct"] as const) {
            if (data[key] !== undefined && data[key] !== "")
              data[key] = String(Number(data[key]) / 100);
          }
          const extraLines = extras
            .filter((item) => item.label.trim() !== "" && item.amount !== "")
            .map((item) => ({
              label: item.label.trim(),
              kind: item.kind,
              amount: item.amount,
            }));
          void runCurrent(
            () =>
              request<Operation>("preview/", "POST", { ...data, extras: extraLines, confirmed }),
            publishOperation,
            "pricing.calculateError",
          );
        }}
      >
        {boundProjectId ? (
          <input type="hidden" name="project_id" value={boundProjectId} />
        ) : (
          <label>
            {t("pricing.projectId")}
            <select
              name="project_id"
              required
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            >
              <option value="">{t("projects.chooseProject")}</option>

              {projectOptions.map((project) => (
                <option key={project.id} value={project.id}>
                  {projectLabel(project)}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          {t("pricing.mode")}
          <select
            name="pricing_mode"
            value={selectedMode}
            onChange={(event) => setSelectedMode(event.target.value)}
          >
            {modes
              .filter((mode) => owner || mode !== "TARGET_GROSS_MARGIN_PROJECT")
              .map((mode) => (
                <option key={mode} value={mode}>
                  {optionLabel(mode)}
                </option>
              ))}
          </select>
        </label>
        {selectedMode === "COST_PLUS_MARGIN" && (
          <p className="field-hint">{t("pricing.mode1Hint")}</p>
        )}
        <label>
          {t("pricing.context")}
          <input
            key={selectedMode}
            name="context_code"
            // El modo costo+margen no usa contexto: el campo queda fuera del
            // submit (disabled) y muestra el nombre legible, no la clave cruda.
            defaultValue={
              selectedMode === "COST_PLUS_MARGIN" ? t("pricing.contextDefault") : "DEFAULT"
            }
            disabled={selectedMode === "COST_PLUS_MARGIN"}
            required={selectedMode !== "COST_PLUS_MARGIN"}
          />
        </label>
        {selectedMode === "COST_PLUS_MARGIN" && (
          <p className="field-hint">{t("pricing.contextUnusedHint")}</p>
        )}
        <label>
          {t("pricing.currency")}
          <select name="currency">
            <option>CLP</option>
            <option>USD</option>
          </select>
        </label>
        <label>
          {t("pricing.effectiveDate")}
          <input
            name="effective_date"
            type="date"
            defaultValue={new Date().toISOString().slice(0, 10)}
            required
          />
        </label>
        <label>
          {t("pricing.fxId")}
          <select name="fx_snapshot_id" defaultValue="" onFocus={loadFxOptions}>
            <option value="">{t("pricing.fxNone")}</option>
            {(fxOptions ?? []).map((row) => (
              <option key={String(row.id)} value={String(row.id)}>
                {[
                  `${row.base_currency ?? ""}→${row.quote_currency ?? ""}`,
                  row.observed_rate,
                  row.observed_date ?? row.effective_date,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </option>
            ))}
          </select>
        </label>
        <p className="field-hint">{t("pricing.fxHint")}</p>
        <label>
          {t("pricing.discount")}
          <input
            name="discount_pct"
            type="number"
            step="0.1"
            min="0"
            max="100"
            defaultValue="0"
            required
          />
        </label>
        {selectedMode === "COST_PLUS_MARGIN" && (
          <label>
            {t("pricing.marginPct")}
            <input name="margin_pct" type="number" step="0.1" min="0" max="99.9" placeholder="—" />
            <span className="field-hint">{t("pricing.marginPctHint")}</span>
          </label>
        )}
        {selectedMode === "TARGET_GROSS_MARGIN_PROJECT" && (
          <label>
            {t("pricing.margin")}
            <input
              name="target_margin"
              type="number"
              step="0.1"
              min="0"
              max="100"
              defaultValue="35"
              required
            />
          </label>
        )}
        <label>
          {t("pricing.segment")}
          <select name="segment">
            {["RETAIL", "ARCHITECT", "CONSTRUCTION"].map((value) => (
              <option key={value} value={value}>
                {optionLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <p className="field-hint">{t("pricing.segmentHint")}</p>
        <fieldset className="pricing-extras">
          <legend>{t("pricing.extras")}</legend>
          <p className="field-hint">{t("pricing.extrasHint")}</p>
          {extras.map((item, index) => (
            <div className="pricing-extras__row" key={index}>
              <select
                aria-label={t("pricing.extras")}
                value={item.kind}
                onChange={(event) =>
                  setExtras(
                    extras.map((entry, i) =>
                      i === index ? { ...entry, kind: event.target.value } : entry,
                    ),
                  )
                }
              >
                <option value="INSTALLATION">{t("pricing.extraKindInstallation")}</option>
                <option value="FREIGHT">{t("pricing.extraKindFreight")}</option>
                <option value="OTHER">{t("pricing.extraKindOther")}</option>
              </select>
              <input
                aria-label={t("pricing.extraLabel")}
                placeholder={t("pricing.extraLabel")}
                maxLength={120}
                value={item.label}
                onChange={(event) =>
                  setExtras(
                    extras.map((entry, i) =>
                      i === index ? { ...entry, label: event.target.value } : entry,
                    ),
                  )
                }
              />
              <input
                aria-label={t("pricing.extraAmount")}
                placeholder={t("pricing.extraAmount")}
                type="number"
                min="0"
                step="1"
                value={item.amount}
                onChange={(event) =>
                  setExtras(
                    extras.map((entry, i) =>
                      i === index ? { ...entry, amount: event.target.value } : entry,
                    ),
                  )
                }
              />
              <button type="button" onClick={() => setExtras(extras.filter((_, i) => i !== index))}>
                {t("pricing.extraRemove")}
              </button>
            </div>
          ))}
          {extras.length < 10 && (
            <button
              type="button"
              onClick={() =>
                setExtras([...extras, { label: "", kind: "INSTALLATION", amount: "" }])
              }
            >
              {t("pricing.extraAdd")}
            </button>
          )}
        </fieldset>
        <label>
          {t("pricing.reason")}
          <input
            name="reason"
            required
            placeholder={t("pricing.reasonPlaceholder")}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            onFocus={(event) => {
              // The seeded first-quote reason is a convenience, not content to
              // append to — select it on focus so typing replaces it instead
              // of concatenating ("Cotización inicial…" + typed text).
              if (reason === t("pricing.firstQuoteReason")) event.target.select();
            }}
          />
        </label>
        <label>
          <input
            type="checkbox"
            name="confirmed"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          {(() => {
            const band = operation?.band as BandPayload | null | undefined;
            return band?.state === "BELOW_MIN" || band?.state === "ABOVE_MAX"
              ? t("pricing.confirmBand")
              : t("pricing.confirmDiscount");
          })()}
        </label>
        <button disabled={busy}>
          {(() => {
            const band = operation?.band as BandPayload | null | undefined;
            const outOfBand = band?.state === "BELOW_MIN" || band?.state === "ABOVE_MAX";
            return outOfBand && !owner ? t("pricing.requestApproval") : t("pricing.preview");
          })()}
        </button>
      </form>
      {error && (
        <p role="alert">
          {error}
          {fixCode &&
            (owner ? (
              <>
                {" "}
                <Link className="pricing-fix" to="/pricing/cost-lists">
                  {t("pricing.fixInCostLists")}
                </Link>
              </>
            ) : (
              <span className="pricing-fix"> {t("pricing.fixAskOwner")}</span>
            ))}
        </p>
      )}
      {operation && (
        <OperationDecision
          boundProject={boundProject}
          currentUserId={currentUserId}
          busy={busy}
          onApply={() => void apply()}
          onReject={() => void apply(true)}
          operation={operation}
          owner={owner}
          projectLabel={
            boundProjectId
              ? undefined
              : projectOptions.find((p) => p.id === operation.project_id)
                ? projectLabel(projectOptions.find((p) => p.id === operation.project_id)!)
                : t("projects.loadError")
          }
          onWithdraw={() => void withdraw()}
          reasonReady={reason.trim().length > 0}
          stale={stale}
        />
      )}
      <h2>{t("pricing.history")}</h2>
      <div className="operation-history__filters">
        <label>
          {t("pricing.filterState")}
          <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
            <option value="">{t("pricing.filterAll")}</option>
            {["PENDING", "APPLIED", "REJECTED", "WITHDRAWN", "PREVIEW"].map((state) => (
              <option key={state} value={state}>
                {t(`pricing.operationState.${state}` as never)}
              </option>
            ))}
          </select>
        </label>
        <button type="button" disabled={busy} onClick={() => void reload()}>
          {t("pricing.reload")}
        </button>
      </div>
      {Array.isArray(history) &&
        history
          .filter((item) => !boundProjectId || item.project_id === boundProjectId)
          .filter((item) => !stateFilter || item.state === stateFilter)
          .map((item) => (
            <article className="operation-history__item" key={item.id}>
              <p>
                <strong>{formatMoney(item.project_gross, item.currency)}</strong>{" "}
                <StatusChip enumName="PriceResponseStateEnum" value={item.state} />
              </p>
              <p className="operation-history__meta">
                {[
                  item.project_code,
                  item.client_name,
                  item.revision_code,
                  item.requested_by_email,
                  item.reason,
                  formatDateTime(item.created_at),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  invalidate();
                  setStale(false);
                  setOperation(item);
                  setReason(item.reason);
                  setConfirmed(false);
                }}
              >
                {t("pricing.review")}
              </button>
            </article>
          ))}
    </section>
  );
}

/** Client-side port of backend/projects/typology.py's derive_typology —
 * walks the same parametric tree so a drafted position doesn't claim every
 * product is FIXED. The backend re-derives authoritatively on save. */
function deriveDraftTypology(tree: unknown): string {
  const OPENING: Record<string, string> = {
    FIXED: "FIXED",
    TURN_LEFT: "TURN",
    TURN_RIGHT: "TURN",
    TILT_TURN_LEFT: "TILT_TURN",
    TILT_TURN_RIGHT: "TILT_TURN",
    SLIDING_2L: "SLIDING_2L",
    SLIDING_3L: "SLIDING_3L",
    SLIDING_4L: "SLIDING_4L",
    SLIDING: "SLIDING",
    AWNING: "AWNING",
    DOOR_ENTRY: "DOOR_ENTRY",
  };
  const node = tree as Record<string, unknown> | undefined;
  if (!node) return "FIXED";
  if (node.version === "product-v2") {
    const modules = (node.assembly as { modules?: unknown[] } | undefined)?.modules;
    if (Array.isArray(modules) && modules.length === 1)
      return deriveDraftTypology((modules[0] as { tree?: unknown }).tree);
    return "COMPOSITE";
  }
  let current: Record<string, unknown> = node;
  if (current.type === "ROOT") {
    const children = current.children;
    if (!Array.isArray(children) || children.length !== 1) return "FIXED";
    current = children[0] as Record<string, unknown>;
  }
  const children = current.children;
  if (Array.isArray(children) && children.length) return "COMPOSITE";
  return OPENING[String(current.opening_type)] ?? "FIXED";
}

function CommercialDraft({
  request,
  onCreated,
}: {
  request: RequestFn;
  onCreated: (id: string) => void;
}): JSX.Element {
  const inputs = useCanvasStore((state) => state.inputs);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!inputs.systemId)
    return (
      <p>
        <Link to="/projects">{t("pricing.prepareDesign")}</Link>
      </p>
    );
  return (
    <details>
      <summary>{t("pricing.createDraft")}</summary>
      <p>
        {inputs.nominalWidthMm} × {inputs.nominalHeightMm} mm
      </p>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          const data = Object.fromEntries(new FormData(event.currentTarget));
          setBusy(true);
          setError("");
          void request<{ id: string }>("drafts/", "POST", {
            code: data.code,
            name: data.name,
            client_name: data.client_name,
            reason: data.reason,
            positions: [
              {
                system_id: inputs.systemId,
                nominal_width_mm: inputs.nominalWidthMm,
                nominal_height_mm: inputs.nominalHeightMm,
                color: inputs.color,
                parametric_tree: { ...inputs.parametricTree, glass_article_sku: data.glass_sku },
                position_index: 1,
                quantity: Number(data.quantity),
                typology: deriveDraftTypology(inputs.parametricTree),
              },
            ],
          })
            .then((value) => onCreated(value.id))
            .catch(() => setError(t("pricing.saveError")))
            .finally(() => setBusy(false));
        }}
      >
        <label>
          {t("pricing.projectCode")}
          <input name="code" required disabled={busy} />
        </label>
        <label>
          {t("pricing.projectName")}
          <input name="name" required disabled={busy} />
        </label>
        <label>
          {t("pricing.client")}
          <input name="client_name" required disabled={busy} />
        </label>
        <label>
          {t("pricing.selectedGlass")}
          <input name="glass_sku" required disabled={busy} />
        </label>
        <label>
          {t("pricing.quantity")}
          <input
            name="quantity"
            type="number"
            min="1"
            step="1"
            defaultValue="1"
            required
            disabled={busy}
          />
        </label>
        <label>
          {t("pricing.reason")}
          <input name="reason" required disabled={busy} />
        </label>
        <button disabled={busy}>{t("pricing.createDraft")}</button>
      </form>
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
