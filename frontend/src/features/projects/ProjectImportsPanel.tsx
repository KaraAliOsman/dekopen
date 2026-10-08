import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/apiMutator";
import {
  engineSystems,
  projectDesignOptions,
  projectImportConfirm,
  projectImportsCreate,
  projectImportsList,
} from "../../api/generated/dekopen";
import type {
  ConfirmItemRequest,
  DesignOptions,
  ImportOpeningTypeEnum,
  ImportResponse,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { StatusChip } from "../../ui/StatusChip";
import {
  IMPORT_CONFIDENCE_LABEL,
  IMPORT_CONFIDENCE_TONE,
  IMPORT_STATUS_LABEL,
  IMPORT_STATUS_TONE,
} from "../catalogs/importStatus";

type Candidate = {
  key: string;
  label: string | null;
  width_mm: string;
  height_mm: string;
  quantity: number;
  opening_type: string | null;
  confidence: string;
  warnings: string[];
  source_text: string;
};

type EditableRow = Candidate & { include: boolean };

const OPENING_LABEL: Record<string, TranslationKey> = {
  FIXED: "intent.fixed",
  TURN_LEFT: "intent.turnLeft",
  TURN_RIGHT: "intent.turnRight",
  TILT_TURN_LEFT: "intent.tiltLeft",
  TILT_TURN_RIGHT: "intent.tiltRight",
  SLIDING_2L: "intent.sliding",
  AWNING: "intent.awning",
  DOOR_ENTRY: "intent.door",
};
const OPENING_CHOICES = Object.keys(OPENING_LABEL) as ImportOpeningTypeEnum[];
const PENDING_STATUSES = new Set(["UPLOADED", "EXTRACTING"]);

// Import warnings and per-item errors travel as codes — the UI owes the
// estimator workshop language, never raw enum identifiers.
const WARNING_LABEL: Record<string, TranslationKey> = {
  "import.source_parse_failed": "projects.importsWarnParse",
  "import.vision_no_candidates": "projects.importsWarnVisionEmpty",
  "import.no_candidates": "projects.importsWarnNoCandidates",
  "import.candidates_capped": "projects.importsWarnCapped",
};
const ITEM_ERROR_LABEL: Record<string, TranslationKey> = {
  import_item_unknown: "projects.importsErrorItemUnknown",
  import_project_closed: "projects.importsErrorProjectClosed",
  glass_article_unknown: "projects.importsErrorGlassUnknown",
  glass_spec_required: "projects.importsErrorGlassSpec",
  panel_article_required: "projects.importsErrorPanelRequired",
  save_failed: "projects.importsErrorSave",
};

function codeText(code: string): string {
  if (code.startsWith("import.vision_failed")) return t("projects.importsWarnVisionFailed");
  return t(WARNING_LABEL[code] ?? ITEM_ERROR_LABEL[code] ?? "projects.importsErrorUnknown");
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
    label: (raw.label as string | null) ?? null,
    width_mm: String(raw.width_mm ?? ""),
    height_mm: String(raw.height_mm ?? ""),
    quantity: Number(raw.quantity ?? 1),
    opening_type: (raw.opening_type as string | null) ?? null,
    confidence: String(raw.confidence ?? "REVIEW_REQUIRED"),
    warnings: Array.isArray(raw.warnings) ? (raw.warnings as string[]) : [],
    source_text: String(raw.source_text ?? ""),
  };
}

export function ProjectImportsPanel({
  projectId,
  orgId,
  canWrite,
  onChanged,
  onDirtyChange,
}: {
  projectId: string;
  orgId: string;
  canWrite: boolean;
  onChanged?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}): JSX.Element {
  const [imports, setImports] = useState<ImportResponse[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [systemId, setSystemId] = useState("");
  const [glassSpec, setGlassSpec] = useState("");
  const [manualSpec, setManualSpec] = useState("");
  const [glassThickness, setGlassThickness] = useState("");
  const [panelSku, setPanelSku] = useState("");
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
      const response = await projectImportsList(projectId, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (mounted.current && listGeneration.current === current) setImports(response.data.imports);
    } catch {
      if (mounted.current && listGeneration.current === current)
        setMessage(t("projects.importsLoadError"));
    }
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (expanded) void load();
  }, [expanded, load]);

  // Extraction runs in the job worker — poll while anything is in flight so
  // the UI shows progress without the estimator refreshing manually.
  useEffect(() => {
    if (!imports.some((entry) => PENDING_STATUSES.has(entry.status))) return;
    const timer = window.setTimeout(() => void load(), 2500);
    return () => window.clearTimeout(timer);
  }, [imports, load]);

  const systems = useQuery({
    queryKey: ["project-systems", orgId],
    queryFn: async () => {
      const response = await engineSystems(requestOptions);
      if (response.status !== 200) throw new Error("load");
      return response.data.systems;
    },
    enabled: expanded && canWrite,
    retry: false,
  });
  const options = useQuery({
    queryKey: ["project-design-options", orgId, systemId],
    queryFn: async () => {
      const response = await projectDesignOptions(systemId, requestOptions);
      if (response.status !== 200) throw new Error("load");
      return response.data as DesignOptions;
    },
    enabled: expanded && !!systemId,
    retry: false,
  });

  useEffect(() => {
    const first = systems.data?.[0];
    if (!systemId && first) setSystemId(first.id);
  }, [systems.data, systemId]);

  // Edited candidate rows belong to the page's unsaved-changes guard —
  // navigating away mid-review must warn instead of silently discarding.
  useEffect(() => {
    onDirtyChange?.(reviewDirty);
  }, [reviewDirty, onDirtyChange]);

  // A system change invalidates the previous catalog's glass, panel and
  // composition selection — clear them so the options effect re-derives values.
  useEffect(() => {
    setGlassSpec("");
    setGlassThickness("");
    setPanelSku("");
    setManualSpec("");
  }, [systemId]);

  useEffect(() => {
    if (!options.data) return;
    const [sku] = options.data.glass_skus;
    const [thickness] = options.data.glazing_thicknesses;
    const [panel] = options.data.panel_skus ?? [];
    if (!glassSpec && sku) setGlassSpec(sku);
    if (!glassThickness && thickness) setGlassThickness(thickness);
    if (!panelSku && panel) setPanelSku(panel);
  }, [options.data, glassSpec, glassThickness, panelSku]);

  // The catalog mapping declares the recipe for known SKUs; when the chosen
  // article carries none, the reviewer supplies the composition it lacks.
  const specNeeded =
    !!options.data &&
    options.data.glass_specs.some((entry) => entry.sku === glassSpec && !entry.spec);

  // Only user-driven catalog edits dirty the review — automatic defaults from
  // the options effect stay clean so an untouched review warns on nothing.
  function chooseSystem(value: string): void {
    setReviewDirty(true);
    setSystemId(value);
  }

  function chooseGlass(value: string): void {
    setReviewDirty(true);
    // The entered recipe belongs to the previous SKU — never reuse it.
    setManualSpec("");
    setGlassSpec(value);
  }

  function chooseThickness(value: string): void {
    setReviewDirty(true);
    setGlassThickness(value);
  }

  function choosePanel(value: string): void {
    setReviewDirty(true);
    setPanelSku(value);
  }

  function editManualSpec(value: string): void {
    setReviewDirty(true);
    setManualSpec(value);
  }

  function startReview(entry: ImportResponse): void {
    setReviewId(entry.id);
    setItemErrors([]);
    setMessage("");
    setReviewDirty(false);
    setRows(
      entry.candidates.map((raw) => {
        const candidate = asCandidate(raw);
        return { ...candidate, include: candidate.confidence === "HIGH" };
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
      const response = await projectImportsCreate(projectId, { file }, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      await load();
      if (mounted.current && response.data.import.status === "REVIEW_READY") {
        startReview(response.data.import);
      }
    } catch {
      if (mounted.current) setMessage(t("projects.importsUploadError"));
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

  async function confirm(entry: ImportResponse): Promise<void> {
    const hasDoors = rows.some((row) => row.include && row.opening_type === "DOOR_ENTRY");
    const items: ConfirmItemRequest[] = rows
      .filter((row) => row.include)
      .map((row) => ({
        key: row.key,
        label: row.label ?? "",
        width_mm: row.width_mm,
        height_mm: row.height_mm,
        quantity: row.quantity,
        opening_type: (row.opening_type ?? "FIXED") as ImportOpeningTypeEnum,
        system_id: systemId,
        color: "WHITE",
        glass_thickness_mm: glassThickness,
        // The SKU is enough — the purchase mapping's recipe resolves the
        // physical spec server-side; only a spec-less mapping asks the
        // reviewer for the composition it lacks.
        glass_article_sku: glassSpec,
        ...(specNeeded ? { glass_spec: manualSpec } : {}),
        ...(row.opening_type === "DOOR_ENTRY" ? { panel_article_sku: panelSku } : {}),
      }));
    const glassValid =
      !!options.data &&
      options.data.glass_skus.includes(glassSpec) &&
      options.data.glazing_thicknesses.includes(glassThickness);
    const panelValid =
      !hasDoors || (!!options.data && (options.data.panel_skus ?? []).includes(panelSku));
    if (
      !items.length ||
      !systemId ||
      !glassSpec ||
      !glassThickness ||
      !glassValid ||
      !panelValid ||
      (specNeeded && !manualSpec.trim())
    ) {
      setMessage(t("projects.importsConfirmMissing"));
      return;
    }
    setBusy(true);
    setMessage("");
    setItemErrors([]);
    try {
      const response = await projectImportConfirm(projectId, entry.id, { items }, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (mounted.current) {
        const errors = response.data.errors as { key: string; code: string }[];
        setItemErrors(errors);
        if (errors.length) {
          // Partial outcome — the import stays retryable; keep the review
          // open so the estimator can fix the failed rows and resubmit.
          setMessage(t("projects.importsConfirmError"));
          await load();
        } else {
          closeReview();
          setMessage(
            t("projects.importsConfirmed").replace("{count}", String(response.data.created.length)),
          );
          await load();
          onChanged?.();
        }
      }
    } catch {
      if (mounted.current) setMessage(t("projects.importsConfirmError"));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  const reviewImport = imports.find((entry) => entry.id === reviewId) ?? null;

  if (!expanded) {
    return (
      <section className="projects-payments" aria-label={t("projects.importsTitle")}>
        <div className="projects-actions">
          <button
            type="button"
            className="imports-toggle"
            aria-expanded="false"
            onClick={() => setExpanded(true)}
          >
            {t("projects.importsTitle")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="projects-payments" aria-label={t("projects.importsTitle")}>
      <div className="projects-actions">
        <h3>{t("projects.importsTitle")}</h3>
        {canWrite && (
          <>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.xlsx,.xlsm,.png,.jpg,.jpeg,.webp"
              className="imports-file-input"
              onChange={(event) => void upload(event)}
            />
            <button
              type="button"

              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              {busy ? t("projects.importsUploading") : t("projects.importsUpload")}
            </button>
          </>
        )}
      </div>
      {message && <p className="form-error">{message}</p>}
      {imports.length === 0 && <p className="imports-empty">{t("projects.importsEmpty")}</p>}
      {imports.length > 0 && (
        <table className="payments-table">
          <thead>
            <tr>
              <th>{t("projects.importsFile")}</th>
              <th>{t("projects.importsStatus")}</th>
              <th>{t("projects.importsCandidates")}</th>
              <th>{t("projects.importsCreated")}</th>
              <th aria-label={t("projects.importsActions")} />
            </tr>
          </thead>
          <tbody>
            {imports.map((entry) => (
              <tr key={entry.id}>
                <td title={entry.file_name}>{entry.file_name}</td>
                <td>
                  <StatusChip
                    label={t(IMPORT_STATUS_LABEL[entry.status] ?? "projects.importsStatusUploaded")}
                    tone={IMPORT_STATUS_TONE[entry.status] ?? "neutral"}
                    value={null}
                  />
                  {entry.status === "FAILED" && entry.error_code && (
                    <span className="imports-warning">{codeText(entry.error_code)}</span>
                  )}
                </td>
                <td>{entry.candidates.length}</td>
                <td>{formatDate(entry.created_at)}</td>
                <td>
                  {entry.status === "REVIEW_READY" && canWrite && (
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
      )}

      {reviewImport && (
        <div className="imports-review">
          <p className="imports-hint">{t("projects.importsReviewHint")}</p>
          {reviewImport.warnings.length > 0 && (
            <ul className="imports-warning">
              {reviewImport.warnings.map((warning) => (
                <li key={warning}>{codeText(warning)}</li>
              ))}
            </ul>
          )}
          <div className="imports-review-fields">
            <label>
              {t("projects.importsSystem")}
              <select value={systemId} onChange={(event) => chooseSystem(event.target.value)}>
                {(systems.data ?? []).map((system) => (
                  <option key={system.id} value={system.id}>
                    {system.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("projects.importsGlass")}
              <select value={glassSpec} onChange={(event) => chooseGlass(event.target.value)}>
                {(options.data?.glass_specs ?? []).map((entry) => (
                  <option key={entry.sku} value={entry.sku}>
                    {entry.spec ? `${entry.sku} — ${entry.spec}` : entry.sku}
                  </option>
                ))}
              </select>
            </label>
            {specNeeded && (
              <label>
                {t("projects.importsGlassSpecManual")}
                <input
                  value={manualSpec}
                  onChange={(event) => editManualSpec(event.target.value)}
                  placeholder="4-16-4"
                />
              </label>
            )}
            <label>
              {t("projects.importsThickness")}
              <select
                value={glassThickness}
                onChange={(event) => chooseThickness(event.target.value)}
              >
                {(options.data?.glazing_thicknesses ?? []).map((thickness) => (
                  <option key={thickness} value={thickness}>
                    {thickness} mm
                  </option>
                ))}
              </select>
            </label>
            {rows.some((row) => row.include && row.opening_type === "DOOR_ENTRY") && (
              <label>
                {t("projects.importsPanel")}
                <select value={panelSku} onChange={(event) => choosePanel(event.target.value)}>
                  {(options.data?.panel_skus ?? []).map((sku) => (
                    <option key={sku} value={sku}>
                      {sku}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <table className="payments-table">
            <thead>
              <tr>
                <th>{t("projects.importsInclude")}</th>
                <th>{t("projects.importsLabel")}</th>
                <th>{t("projects.importsWidth")}</th>
                <th>{t("projects.importsHeight")}</th>
                <th>{t("projects.importsQty")}</th>
                <th>{t("projects.importsOpening")}</th>
                <th>{t("projects.importsConfidence")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const itemError = itemErrors.find((entry) => entry.key === row.key);
                return (
                  <tr key={row.key} className={itemError ? "imports-row-error" : undefined}>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.include}
                        onChange={(event) => patchRow(row.key, { include: event.target.checked })}
                      />
                    </td>
                    <td>
                      <input
                        value={row.label ?? ""}
                        maxLength={100}
                        onChange={(event) => patchRow(row.key, { label: event.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        value={row.width_mm}
                        inputMode="decimal"
                        size={7}
                        onChange={(event) => patchRow(row.key, { width_mm: event.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        value={row.height_mm}
                        inputMode="decimal"
                        size={7}
                        onChange={(event) => patchRow(row.key, { height_mm: event.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        value={row.quantity}
                        inputMode="numeric"
                        size={4}
                        onChange={(event) =>
                          patchRow(row.key, { quantity: Number(event.target.value) || 1 })
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={row.opening_type ?? "FIXED"}
                        onChange={(event) =>
                          patchRow(row.key, {
                            opening_type: event.target.value,
                          })
                        }
                      >
                        {OPENING_CHOICES.map((opening) => {
                          const label = OPENING_LABEL[opening];
                          return (
                            <option key={opening} value={opening}>
                              {label ? t(label) : opening}
                            </option>
                          );
                        })}
                      </select>
                    </td>
                    <td title={row.source_text}>
                      <StatusChip
                        label={
                          IMPORT_CONFIDENCE_LABEL[row.confidence]
                            ? t(IMPORT_CONFIDENCE_LABEL[row.confidence]!)
                            : row.confidence
                        }
                        tone={IMPORT_CONFIDENCE_TONE[row.confidence] ?? "neutral"}
                        value={null}
                      />
                      {itemError && (
                        <span className="imports-warning">{codeText(itemError.code)}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="payments-form-actions">
            <button
              type="button"
              className="primary-action"
              disabled={busy || !rows.some((row) => row.include)}
              onClick={() => void confirm(reviewImport)}
            >
              {t("projects.importsConfirm")}
            </button>
            <button
              type="button"

              onClick={closeReview}
            >
              {t("projects.importsCancel")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
