import { fmtMm } from "../../format";
import { Fragment, useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { ApiError } from "../../api/apiMutator";
import {
  catalogImportConfirm,
  catalogImportsCreate,
  catalogImportsList,
} from "../../api/generated/dekopen";
import type { CatalogImportResponse, CatalogItemRequest } from "../../api/generated/models";
import { CatalogProfileRoleEnum } from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";

const ct = (key: string) => t(`catalog.${key}` as TranslationKey);

type ExistingRef = {
  system_code: string;
  name: string;
  role: string;
  face_width_mm: string | null;
};

type Candidate = {
  key: string;
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
  source_text: string;
  source_ref: string;
  conflict: boolean;
  existing: ExistingRef[];
};

type EditableRow = Candidate & { include: boolean };

const ROLE_CHOICES = Object.values(CatalogProfileRoleEnum);
const PENDING_STATUSES = new Set(["UPLOADED", "EXTRACTING"]);

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
  return ct(WARNING_LABEL[code] ?? ITEM_ERROR_LABEL[code] ?? "importsErrorUnknown");
}

const CONFIDENCE_LABEL: Record<string, string> = {
  VERIFIED_STRUCTURED: "importsConfidenceVerified",
  HIGH_CANDIDATE: "importsConfidenceCandidate",
  REVIEW_REQUIRED: "importsConfidenceReview",
  LOW: "importsConfidenceLow",
};

/** 'Seguro' = structured or unambiguous evidence and no disagreement with the
 * live catalog. Pre-selection only — every suggestion still waits for the
 * human confirm; REVIEW_REQUIRED/LOW rows are never pre-selected. */
function isSafe(candidate: Candidate): boolean {
  return (
    (candidate.confidence === "VERIFIED_STRUCTURED" || candidate.confidence === "HIGH_CANDIDATE") &&
    !candidate.conflict
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
    setRows(
      entry.candidates.map((raw) => {
        const candidate = asCandidate(raw);
        return { ...candidate, include: isSafe(candidate) };
      }),
    );
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
  }

  function closeReview(): void {
    setReviewId(null);
    setReviewDirty(false);
  }

  async function confirm(entry: CatalogImportResponse): Promise<void> {
    const items: CatalogItemRequest[] = rows
      .filter((row) => row.include)
      .map((row) => ({
        key: row.key,
        sku: row.sku,
        name: row.name,
        role: row.role as CatalogItemRequest["role"],
        face_width_mm: row.face_width_mm,
        commercial_length_mm: row.commercial_length_mm || undefined,
        welding_loss_mm: row.welding_loss_mm || undefined,
        reinforcement_sku: row.reinforcement_sku || undefined,
        weight_kg_m: row.weight_kg_m || undefined,
        steel_weight_kg_m: row.steel_weight_kg_m || undefined,
      }));
    const invalid = items.some(
      (item) => !item.sku.trim() || !item.face_width_mm.trim() || !item.role,
    );
    if (!items.length || !systemId || invalid) {
      setMessage(ct("importsConfirmMissing"));
      return;
    }
    setBusy(true);
    setMessage("");
    setItemErrors([]);
    try {
      const response = await catalogImportConfirm(
        entry.id,
        { system_id: systemId, items },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (mounted.current) {
        const errors = response.data.errors as { key: string; code: string }[];
        setItemErrors(errors);
        if (errors.length) {
          // Partial outcome — the import stays retryable; keep the review
          // open so the manager can fix the failed rows and resubmit.
          setMessage(ct("importsConfirmError"));
          await load();
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
      current.map((row) => (isSafe(row) ? { ...row, include: true } : { ...row, include: false })),
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
                  return (
                    <Fragment key={row.key}>
                      <tr className={itemError ? "imports-row-error" : undefined}>
                        <td>
                          <input
                            type="checkbox"
                            checked={row.include}
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
