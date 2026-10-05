import { fmtMm } from "../../format";
import { Fragment, useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { ApiError } from "../../api/apiMutator";
import {
  catalogImportConfirm,
  catalogImportsCreate,
  catalogImportsList,
  getCatalogImportTemplateUrl,
} from "../../api/generated/dekopen";
import { apiFetchBlob } from "../../api/apiMutator";
import type {
  CatalogImportResponse,
  CatalogItemRequest,
  NewSystemRequest,
} from "../../api/generated/models";
import { CatalogItemRoleEnum } from "../../api/generated/models";
import { domainLabel } from "../../i18n/domainLabels";
import { t, tOptional, type TranslationKey } from "../../i18n/es-CL";

const ct = (key: string) => t(`catalog.${key}` as TranslationKey);

type ExistingRef = {
  system_code: string;
  name: string;
  role: string;
  face_width_mm: string | null;
};

type Candidate = {
  key: string;
  entity: string;
  fields: Record<string, unknown>;
  sku: string;
  name: string;
  role: string;
  face_width_mm: string;
  commercial_length_mm: string;
  welding_loss_mm: string;
  reinforcement_sku: string;
  weight_kg_m: string;
  steel_weight_kg_m: string;
  confidence: string;
  warnings: string[];
  row_errors: string[];
  source_text: string;
  source_ref: string;
  conflict: boolean;
  existing: ExistingRef[];
};

type EditableRow = Candidate & { include: boolean; published?: boolean };

// El confirm acepta los 17 roles (CatalogItemRoleEnum); el enum "profile"
// heredado solo tiene 9 y dejaba fuera SLIDING_SASH/INTERLOCK/RAIL…
const ROLE_CHOICES = Object.values(CatalogItemRoleEnum);
const PENDING_STATUSES = new Set(["UPLOADED", "EXTRACTING"]);

/** Campos cuyo valor es un enum de dominio — se etiquetan, no se vuelcan
 * en crudo ("CASEMENT", "TURN_LEFT", …) en la tabla de revisión. */
const FIELD_VALUE_ENUM: Record<string, string> = {
  material: "MaterialEnum",
  system_family: "SystemFamilyEnum",
  opening_type: "ImportOpeningTypeEnum",
  rail_type: "RailTypeEnum",
  role: "CatalogItemRoleEnum",
};

function fieldNameLabel(name: string): string {
  return tOptional(`catalog.field.${name}`) ?? name;
}

function fieldValueLabel(name: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return t(value ? "inspector.yes" : "inspector.no");
  const enumName = FIELD_VALUE_ENUM[name];
  if (enumName && typeof value === "string") {
    return domainLabel(enumName, value).label;
  }
  if (name === "unit" && typeof value === "string") {
    return tOptional(`purchasing.unitValue.${value.toUpperCase()}.other`) ?? value;
  }
  if (name === "item_type" && typeof value === "string") {
    return tOptional(`catalog.entity.${value}`) ?? value;
  }
  if (name === "finish_class" && typeof value === "string") {
    return (
      tOptional(`catalog.option.finishClass.${value}`) ??
      tOptional(`projects.color.${value}`) ??
      value
    );
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === "object") {
          const entry = item as Record<string, unknown>;
          // Contenido de kit {sku, qty} → "SKU ×2"; nunca "[object Object]".
          if ("sku" in entry) {
            const qty = entry.qty !== undefined ? ` ×${String(entry.qty)}` : "";
            return `${String(entry.sku)}${qty}`;
          }
          return Object.entries(entry)
            .map(([k, v]) => `${fieldNameLabel(k)} ${String(v)}`)
            .join(" ");
        }
        if (name === "finishes") {
          return tOptional(`projects.color.${String(item)}`) ?? String(item);
        }
        return String(item);
      })
      .join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Resumen legible de los campos de un candidato no-PROFILE — nombres de
 * campo traducidos y valores de enum etiquetados, jamás "clave: valor". */
function candidateFieldSummary(fields: Record<string, unknown>): string {
  return Object.entries(fields)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([name, value]) => {
      const rendered = fieldValueLabel(name, value);
      return rendered ? `${fieldNameLabel(name)}: ${rendered}` : "";
    })
    .filter(Boolean)
    .join(" · ");
}

const STATUS_LABEL: Record<string, TranslationKey> = {
  UPLOADED: "projects.importsStatusUploaded",
  EXTRACTING: "projects.importsStatusExtracting",
  REVIEW_READY: "projects.importsStatusReviewReady",
  CONFIRMED: "projects.importsStatusConfirmed",
  FAILED: "projects.importsStatusFailed",
};

// Import warnings and per-item errors travel as codes — the UI owes the
// catalog manager workshop language, never raw enum identifiers.
const WARNING_LABEL: Record<string, string> = {
  "catalog.source_parse_failed": "importsWarnParse",
  "catalog.compile_no_candidates": "importsWarnCompileEmpty",
  "catalog.no_candidates": "importsWarnNoCandidates",
  "catalog.candidates_capped": "importsWarnCapped",
  catalog_name_missing: "importsWarnNameMissing",
  catalog_role_unknown: "importsWarnRoleUnknown",
  catalog_face_width_missing: "importsWarnFaceMissing",
  catalog_face_width_ambiguous: "importsWarnFaceAmbiguous",
  catalog_conflicts_existing: "importsWarnConflict",
};
const ITEM_ERROR_LABEL: Record<string, string> = {
  catalog_item_unknown: "importsErrorItemUnknown",
  catalog_role_invalid: "importsErrorRoleInvalid",
  catalog_sku_conflict: "importsErrorSkuConflict",
  catalog_singleton_role_conflict: "importsErrorSingletonRole",
  catalog_insert_failed: "importsErrorInsertFailed",
  catalog_bead_unknown: "importsErrorBeadUnknown",
  catalog_price_list_required: "importsErrorPriceListRequired",
  catalog_opening_type_unknown: "importsErrorOpeningType",
  catalog_system_changed: "importsErrorSystemChanged",
  catalog_entity_unknown: "importsErrorEntityUnknown",
  catalog_row_invalid: "importsErrorRowInvalid",
  catalog_field_required: "importsErrorFieldRequired",
};

function codeText(code: string): string {
  if (code.startsWith("catalog.compile_failed")) return ct("importsWarnCompileFailed");
  if (code.startsWith("catalog.series_incomplete"))
    return ct("importsWarnSeriesIncomplete").replace(
      "{roles}",
      (code.split(":", 2)[1] || "")
        .split(",")
        .map((role) => ct(`option.${role.trim()}`))
        .join(", "),
    );
  const label = WARNING_LABEL[code] ?? ITEM_ERROR_LABEL[code];
  if (label) return ct(label as TranslationKey);
  // Las advertencias del parser pueden llegar ya como frase en español
  // ("La hoja «Sistemas» no tiene las columnas…") — se muestran tal cual;
  // solo los códigos compactos sin mapeo caen al mensaje genérico.
  return code.includes(" ") ? code : ct("importsErrorUnknown");
}

const CONFIDENCE_LABEL: Record<string, string> = {
  VERIFIED_STRUCTURED: "importsConfidenceVerified",
  HIGH_CANDIDATE: "importsConfidenceCandidate",
  REVIEW_REQUIRED: "importsConfidenceReview",
  LOW: "importsConfidenceLow",
  ERROR: "importsConfidenceError",
};

/** 'Seguro' = structured or unambiguous evidence and no disagreement with the
 * live catalog. Pre-selection only — every suggestion still waits for the
 * human confirm; REVIEW_REQUIRED/LOW rows are never pre-selected. */
function isSafe(candidate: Candidate): boolean {
  return (
    (candidate.confidence === "VERIFIED_STRUCTURED" || candidate.confidence === "HIGH_CANDIDATE") &&
    !candidate.conflict &&
    candidate.row_errors.length === 0
  );
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("es-CL", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function asCandidate(raw: Record<string, unknown>): Candidate {
  return {
    key: String(raw.key ?? ""),
    entity: String(raw.entity ?? "PROFILE"),
    fields:
      raw.fields && typeof raw.fields === "object" && !Array.isArray(raw.fields)
        ? (raw.fields as Record<string, unknown>)
        : {},
    sku: String(raw.sku ?? ""),
    name: String(raw.name ?? ""),
    role: String(raw.role ?? "ADDITIONAL"),
    face_width_mm: String(raw.face_width_mm ?? ""),
    commercial_length_mm: String(raw.commercial_length_mm ?? ""),
    welding_loss_mm: String(raw.welding_loss_mm ?? ""),
    reinforcement_sku: String(raw.reinforcement_sku ?? ""),
    weight_kg_m: String(raw.weight_kg_m ?? ""),
    steel_weight_kg_m: String(raw.steel_weight_kg_m ?? ""),
    confidence: String(raw.confidence ?? "REVIEW_REQUIRED"),
    warnings: Array.isArray(raw.warnings) ? (raw.warnings as string[]) : [],
    row_errors: Array.isArray(raw.row_errors) ? (raw.row_errors as string[]) : [],
    source_text: String(raw.source_text ?? ""),
    source_ref: String(raw.source_ref ?? ""),
    conflict: raw.conflict === true,
    existing: Array.isArray(raw.existing) ? (raw.existing as ExistingRef[]) : [],
  };
}

export function CatalogImportsPanel({
  orgId,
  canWrite,
  systems,
  onConfirmed,
}: {
  orgId: string;
  canWrite: boolean;
  systems: Array<{ id: string; name: string; code: string }>;
  onConfirmed?: () => void;
}): JSX.Element {
  const [imports, setImports] = useState<CatalogImportResponse[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [systemId, setSystemId] = useState("");
  const [reviewDirty, setReviewDirty] = useState(false);
  const [itemErrors, setItemErrors] = useState<{ key: string; code: string }[]>([]);
  const mounted = useRef(true);
  const listGeneration = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    const current = ++listGeneration.current;
    try {
      const response = await catalogImportsList(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (mounted.current && listGeneration.current === current) setImports(response.data.imports);
    } catch {
      if (mounted.current && listGeneration.current === current) setMessage(ct("importsLoadError"));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (expanded) void load();
  }, [expanded, load]);

  // Extraction runs in the job worker — poll while anything is in flight.
  useEffect(() => {
    if (!imports.some((entry) => PENDING_STATUSES.has(entry.status))) return;
    const timer = window.setTimeout(() => void load(), 2500);
    return () => window.clearTimeout(timer);
  }, [imports, load]);

  function startReview(entry: CatalogImportResponse): void {
    setReviewId(entry.id);
    setItemErrors([]);
    setMessage("");
    setReviewDirty(false);
    setSystemId(entry.system_id ?? systems[0]?.id ?? "");
    // Claves ya publicadas por un confirm parcial anterior — quedan
    // marcadas Publicado y fuera de la selección; re-enviarlas (sobre todo
    // la fila Sistema como new_system) provoca el 409 catalog_system_changed.
    const done = new Set((entry.result ?? []).map((result) => String(result.key ?? "")));
    setRows(
      entry.candidates.map((raw) => {
        const candidate = asCandidate(raw);
        const published = done.has(candidate.key);
        return { ...candidate, include: isSafe(candidate) && !published, published };
      }),
    );
  }

  async function downloadTemplate(): Promise<void> {
    setBusy(true);
    try {
      const { blob, filename } = await apiFetchBlob(getCatalogImportTemplateUrl());
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? "plantilla-catalogo-dekopen.xlsx";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      if (mounted.current) setMessage(ct("importsTemplateError"));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await catalogImportsCreate({ file }, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      await load();
    } catch {
      if (mounted.current) setMessage(ct("importsUploadError"));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function patchRow(key: string, patch: Partial<EditableRow>): void {
    setReviewDirty(true);
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
    // Editar la fila invalida el resultado anterior: el error por-ítem de la
    // fila y el mensaje global de confirmación dejan de aplicar en cuanto el
    // gestor corrige algo — nunca quedan obsoletos en pantalla.
    setItemErrors((current) => current.filter((entry) => entry.key !== key));
    setMessage("");
  }

  function closeReview(): void {
    setReviewId(null);
    setReviewDirty(false);
    setItemErrors([]);
  }

  async function confirm(entry: CatalogImportResponse): Promise<void> {
    const included = rows.filter((row) => row.include);
    // A Sistemas row declares the target itself — the backend creates the
    // org-owned system in the same confirm transaction. A row already
    // published by a previous partial confirm must NOT be re-sent as
    // new_system (that re-declare is the catalog_system_changed 409).
    const newSystemRow = included.find((row) => row.entity === "SYSTEM" && !row.published);
    const items: CatalogItemRequest[] = included.map((row) => ({
      key: row.key,
      entity: row.entity as CatalogItemRequest["entity"],
      fields: row.fields as CatalogItemRequest["fields"],
      sku: row.sku,
      name: row.name,
      role: row.role as CatalogItemRequest["role"],
      face_width_mm: row.face_width_mm || undefined,
      commercial_length_mm: row.commercial_length_mm || undefined,
      welding_loss_mm: row.welding_loss_mm || undefined,
      reinforcement_sku: row.reinforcement_sku || undefined,
      weight_kg_m: row.weight_kg_m || undefined,
      steel_weight_kg_m: row.steel_weight_kg_m || undefined,
    }));
    const invalid = items.some(
      (item) =>
        item.entity === "PROFILE" && (!item.sku?.trim() || !item.face_width_mm || !item.role),
    );
    const newSystem = newSystemRow
      ? {
          code: String(newSystemRow.fields.code ?? ""),
          name: String(newSystemRow.fields.name ?? ""),
          depth_mm: String(newSystemRow.fields.depth_mm ?? ""),
          material: String(newSystemRow.fields.material ?? "PVC"),
          system_family: String(newSystemRow.fields.system_family ?? "CASEMENT"),
          sliding_glazing_deduction_width_mm: String(
            newSystemRow.fields.sliding_glazing_deduction_width_mm ?? "0",
          ),
          sliding_glazing_deduction_height_mm: String(
            newSystemRow.fields.sliding_glazing_deduction_height_mm ?? "0",
          ),
          door_leaf_side_clearance_mm: String(
            newSystemRow.fields.door_leaf_side_clearance_mm ?? "0",
          ),
          finishes: Array.isArray(newSystemRow.fields.finishes)
            ? (newSystemRow.fields.finishes as string[])
            : ["WHITE"],
        }
      : undefined;
    if (!items.length || (!systemId && !newSystem) || invalid) {
      setMessage(ct("importsConfirmMissing"));
      return;
    }
    setBusy(true);
    setMessage("");
    setItemErrors([]);
    try {
      const response = await catalogImportConfirm(
        entry.id,
        {
          system_id: newSystem ? undefined : systemId,
          new_system: newSystem as NewSystemRequest | undefined,
          items,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (mounted.current) {
        const created = (response.data.created ?? []) as {
          key: string;
          entity?: string;
          id?: string;
        }[];
        const createdSystem = created.find((c) => c.entity === "SYSTEM" && c.id);
        if (createdSystem?.id) {
          // The org system now exists even if sibling rows failed: retarget
          // the select to it (it was created this session, the parent list
          // refresh below makes it visible) and pin the row as published so
          // the next retry confirms items against system_id, not new_system.
          const newId = String(createdSystem.id);
          setSystemId(newId);
          setRows((current) =>
            current.map((row) =>
              row.key === createdSystem.key ? { ...row, published: true, include: false } : row,
            ),
          );
        }
        const errors = response.data.errors as { key: string; code: string }[];
        setItemErrors(errors);
        if (errors.length) {
          // Partial outcome — the import stays retryable; keep the review
          // open so the manager can fix the failed rows and resubmit.
          setMessage(ct("importsConfirmError"));
          await load();
          // Rows WERE published — the parent systems list must reflect the
          // new system in the destination select without a page reload.
          onConfirmed?.();
        } else {
          closeReview();
          setMessage(
            ct("importsConfirmed").replace("{count}", String(response.data.created.length)),
          );
          await load();
          onConfirmed?.();
        }
      }
    } catch {
      if (mounted.current) setMessage(ct("importsConfirmError"));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function includeOnlySafe(): void {
    setReviewDirty(true);
    setRows((current) =>
      current.map((row) =>
        row.published ? row : isSafe(row) ? { ...row, include: true } : { ...row, include: false },
      ),
    );
  }

  const [evidenceKey, setEvidenceKey] = useState<string | null>(null);
  const reviewImport = imports.find((entry) => entry.id === reviewId) ?? null;

  if (!expanded) {
    return (
      <section className="projects-payments" aria-label={ct("importsTitle")}>
        <div className="projects-actions">
          <button
            type="button"
            className="imports-toggle"
            aria-expanded="false"
            onClick={() => setExpanded(true)}
          >
            {ct("importsTitle")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="projects-payments" aria-label={ct("importsTitle")}>
      <div className="projects-actions">
        <h3>{ct("importsTitle")}</h3>
        {canWrite && (
          <>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.xlsx,.xlsm,.csv,.png,.jpg,.jpeg,.webp"
              className="imports-file-input"
              onChange={(event) => void upload(event)}
            />
            <button type="button" disabled={busy} onClick={() => void downloadTemplate()}>
              {ct("importsTemplate")}
            </button>
            <button type="button" disabled={busy} onClick={() => fileInput.current?.click()}>
              {busy ? ct("importsUploading") : ct("importsUpload")}
            </button>
          </>
        )}
      </div>
      <p className="imports-hint">{ct("importsHelp")}</p>
      {message && <p className="form-error">{message}</p>}
      {imports.length === 0 && (
        <p className="imports-empty">
          {canWrite ? ct("importsEmpty") : `${ct("importsEmpty")} ${ct("importsReadOnly")}`}
        </p>
      )}
      {imports.length > 0 && (
        <div className="catalog-table-scroll">
          <table className="payments-table">
            <thead>
              <tr>
                <th>{t("projects.importsFile")}</th>
                <th>{t("projects.importsStatus")}</th>
                <th>{ct("importsCandidates")}</th>
                <th>{t("projects.importsCreated")}</th>
                <th aria-label={t("projects.importsActions")} />
              </tr>
            </thead>
            <tbody>
              {imports.map((entry) => (
                <tr key={entry.id}>
                  <td title={entry.file_name}>{entry.file_name}</td>
                  <td>
                    <span
                      className={`production-chip imports-status-${entry.status.toLowerCase()}`}
                    >
                      {t(STATUS_LABEL[entry.status] ?? "projects.importsStatusUploaded")}
                    </span>
                    {entry.status === "FAILED" && entry.error_code && (
                      <span className="imports-warning">{codeText(entry.error_code)}</span>
                    )}
                  </td>
                  <td>{entry.candidates.length}</td>
                  <td>{formatDate(entry.created_at)}</td>
                  <td>
                    {(entry.status === "REVIEW_READY" || entry.status === "FAILED") && canWrite && (
                      <button
                        type="button"
                        // A dirty review's edits live only in this component —
                        // opening another import would silently discard them.
                        disabled={reviewDirty && entry.id !== reviewId}
                        title={
                          reviewDirty && entry.id !== reviewId
                            ? t("projects.importsReviewLocked")
                            : undefined
                        }
                        onClick={() => startReview(entry)}
                      >
                        {t("projects.importsReview")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {reviewImport && (
        <div className="imports-review">
          <p className="imports-hint">{ct("importsReviewHint")}</p>
          {reviewImport.warnings.length > 0 && (
            <ul className="imports-warning">
              {reviewImport.warnings.map((warning) => (
                <li key={warning}>{codeText(warning)}</li>
              ))}
            </ul>
          )}
          <div className="imports-review-fields">
            <button type="button" onClick={includeOnlySafe}>
              {ct("importsOnlySafe")}
            </button>
            <label>
              {ct("importsSystem")}
              <select value={systemId} onChange={(event) => setSystemId(event.target.value)}>
                <option value="">{ct("importsSystemChoose")}</option>
                {systems.map((system) => (
                  <option key={system.id} value={system.id}>
                    {system.name} · {system.code}
                  </option>
                ))}
              </select>
              <small>{ct("importsSystemHint")}</small>
            </label>
          </div>
          <div className="catalog-table-scroll">
            <table className="payments-table">
              <thead>
                <tr>
                  <th>{t("projects.importsInclude")}</th>
                  <th>{ct("importsFieldSku")}</th>
                  <th>{ct("importsFieldName")}</th>
                  <th>{ct("importsFieldRole")}</th>
                  <th>{ct("importsFieldFace")}</th>
                  <th>{ct("importsFieldLength")}</th>
                  <th>{ct("importsFieldWeld")}</th>
                  <th>{ct("importsFieldReinforcement")}</th>
                  <th>{ct("importsFieldWeight")}</th>
                  <th>{ct("importsFieldSteelWeight")}</th>
                  <th>{ct("importsConfidence")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const itemError = itemErrors.find((entry) => entry.key === row.key);
                  if (row.entity !== "PROFILE") {
                    const summary = candidateFieldSummary(row.fields);
                    return (
                      <Fragment key={row.key}>
                        <tr
                          className={
                            itemError || row.row_errors.length ? "imports-row-error" : undefined
                          }
                        >
                          <td>
                            <input
                              type="checkbox"
                              checked={row.include}
                              disabled={row.row_errors.length > 0 || row.published}
                              onChange={(event) =>
                                patchRow(row.key, { include: event.target.checked })
                              }
                            />
                          </td>
                          <td colSpan={3}>
                            <span className="production-chip">{ct(`entity.${row.entity}`)}</span>{" "}
                            {row.published && (
                              <span className="production-chip">{ct("importsPublished")}</span>
                            )}{" "}
                            {summary || ct("importsNoFields")}
                          </td>
                          <td colSpan={6}>
                            <button
                              type="button"
                              className="imports-evidence-toggle"
                              aria-expanded={evidenceKey === row.key}
                              onClick={() =>
                                setEvidenceKey(evidenceKey === row.key ? null : row.key)
                              }
                            >
                              {ct("importsEvidence")}
                            </button>
                            <span
                              className={`production-chip imports-confidence-${row.confidence.toLowerCase()}`}
                            >
                              {ct(CONFIDENCE_LABEL[row.confidence] ?? "importsConfidenceReview")}
                            </span>
                            {row.row_errors.map((error) => (
                              <span key={error} className="imports-warning">
                                {error}
                              </span>
                            ))}
                            {row.warnings.length > 0 && (
                              <span className="imports-warning">
                                {row.warnings.map(codeText).join(" · ")}
                              </span>
                            )}
                            {itemError && (
                              <span className="imports-warning">{codeText(itemError.code)}</span>
                            )}
                          </td>
                        </tr>
                        {evidenceKey === row.key && (
                          <tr className="imports-evidence-row">
                            <td colSpan={10}>
                              {row.source_ref && (
                                <span className="imports-evidence-ref">{row.source_ref}</span>
                              )}
                              <code className="imports-evidence-text">
                                {row.source_text || candidateFieldSummary(row.fields)}
                              </code>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  }
                  return (
                    <Fragment key={row.key}>
                      <tr
                        className={
                          itemError || row.row_errors.length ? "imports-row-error" : undefined
                        }
                      >
                        <td>
                          <input
                            type="checkbox"
                            checked={row.include}
                            disabled={row.row_errors.length > 0 || row.published}
                            onChange={(event) =>
                              patchRow(row.key, { include: event.target.checked })
                            }
                          />
                        </td>
                        <td>
                          <input
                            value={row.sku}
                            maxLength={100}
                            size={12}
                            onChange={(event) => patchRow(row.key, { sku: event.target.value })}
                          />
                        </td>
                        <td>
                          <input
                            value={row.name}
                            maxLength={255}
                            size={20}
                            onChange={(event) => patchRow(row.key, { name: event.target.value })}
                          />
                        </td>
                        <td>
                          <select
                            value={row.role}
                            onChange={(event) => patchRow(row.key, { role: event.target.value })}
                          >
                            {ROLE_CHOICES.map((role) => (
                              <option key={role} value={role}>
                                {ct(`option.${role}`)}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            value={row.face_width_mm}
                            inputMode="decimal"
                            size={6}
                            onChange={(event) =>
                              patchRow(row.key, { face_width_mm: event.target.value })
                            }
                          />
                        </td>
                        <td>
                          <input
                            value={row.commercial_length_mm}
                            inputMode="decimal"
                            size={7}
                            onChange={(event) =>
                              patchRow(row.key, { commercial_length_mm: event.target.value })
                            }
                          />
                        </td>
                        <td>
                          <input
                            value={row.welding_loss_mm}
                            inputMode="decimal"
                            size={6}
                            onChange={(event) =>
                              patchRow(row.key, { welding_loss_mm: event.target.value })
                            }
                          />
                        </td>
                        <td>
                          <input
                            value={row.reinforcement_sku}
                            maxLength={100}
                            size={10}
                            onChange={(event) =>
                              patchRow(row.key, { reinforcement_sku: event.target.value })
                            }
                          />
                        </td>
                        <td>
                          <input
                            value={row.weight_kg_m}
                            inputMode="decimal"
                            size={7}
                            onChange={(event) =>
                              patchRow(row.key, { weight_kg_m: event.target.value })
                            }
                          />
                        </td>
                        <td>
                          <input
                            value={row.steel_weight_kg_m}
                            inputMode="decimal"
                            size={7}
                            onChange={(event) =>
                              patchRow(row.key, { steel_weight_kg_m: event.target.value })
                            }
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="imports-evidence-toggle"
                            aria-expanded={evidenceKey === row.key}
                            onClick={() => setEvidenceKey(evidenceKey === row.key ? null : row.key)}
                          >
                            {ct("importsEvidence")}
                          </button>
                          <span
                            className={`production-chip imports-confidence-${row.confidence.toLowerCase()}`}
                          >
                            {ct(CONFIDENCE_LABEL[row.confidence] ?? "importsConfidenceReview")}
                          </span>
                          {row.warnings.length > 0 && (
                            <span className="imports-warning">
                              {row.warnings.map(codeText).join(" · ")}
                            </span>
                          )}
                          {row.row_errors.map((error) => (
                            <span key={error} className="imports-warning">
                              {error}
                            </span>
                          ))}
                          {itemError && (
                            <span className="imports-warning">{codeText(itemError.code)}</span>
                          )}
                        </td>
                      </tr>
                      {evidenceKey === row.key && (
                        <tr className="imports-evidence-row">
                          <td colSpan={11}>
                            {row.source_ref && (
                              <span className="imports-evidence-ref">{row.source_ref}</span>
                            )}
                            <code className="imports-evidence-text">{row.source_text}</code>
                            {row.existing.map((match) => (
                              <span key={match.system_code} className="imports-existing">
                                {ct("importsExisting").replace("{system}", match.system_code)}:{" "}
                                {match.name} · {ct(`option.${match.role}`)}
                                {match.face_width_mm ? ` · ${fmtMm(match.face_width_mm)} mm` : ""}
                              </span>
                            ))}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          {/* El error de confirmación se repite junto al botón: la tabla de
              revisión puede ser larga y el mensaje superior queda fuera de
              vista justo donde se decide. */}
          {message && <p className="form-error">{message}</p>}
          <div className="projects-actions">
            <button type="button" disabled={busy} onClick={() => void confirm(reviewImport)}>
              {ct("importsConfirm")}
            </button>
            <button type="button" disabled={busy} onClick={closeReview}>
              {t("projects.importsCancel")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
