// frontend/src/features/projects/ProjectPositionsTab.tsx
/** P21 — pestaña Posiciones del hub de proyecto: posiciones de verdad.
 *
 * Una sola superficie con dos vistas del mismo listbox: la grilla (el
 * dibujo real del vano, grande) y la lista densa de columnas. Agrupación
 * por ubicación/tipología/sistema, multiselección con acciones por lote
 * (duplicar, eliminar, cambios globales, ubicación, cantidad, reordenar),
 * cotas editables en la fila — el mismo `set_total_width`/`set_height` del
 * editor — y alta rápida desde la biblioteca de tipologías. La vista
 * «Importar» monta el flujo IA de documentos (P14) en la misma pestaña. */

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import {
  catalogSystemList,
  positionsCreate,
  positionsDestroy,
  positionsMove,
  positionsUpdate,
  projectDesignOptions,
} from "../../api/generated/dekopen";
import type {
  DocumentaryPreparationPosition,
  PositionDesignRequest,
  PositionResponse,
  ProjectResponse,
} from "../../api/generated/models";
import { colorLabel, t, typologyLabel, type TranslationKey } from "../../i18n/es-CL";
import { fmtQty, formatDims, formatMoney, formatPercent } from "../../format";
import { Checkbox, Dialog, EmptyState, StatusBadge, useConfirm, type StatusTone } from "../../ui";
import { designFromProduct } from "../assistant/designPayload";
import { starterNominalSize, type StarterDefinition } from "../canvas/designLibrary";
import { applyDesignOps } from "../canvas/designOps";
import { resolveMembers } from "../canvas/members";
import { isProductModel, wrapTreeAsProduct, type ProductJson } from "../canvas/productEditing";
import { TypologyFlyout } from "../canvas/TypologyFlyout";
import type { IntentNode } from "../canvas/intentEditing";
import type { DesignOp } from "../commands/types";
import { GlobalChangesPanel } from "./GlobalChangesPanel";
import { PositionThumb } from "./PositionThumb";
import { ProjectImportsPanel } from "./ProjectImportsPanel";
import { ProjectBom } from "./ProjectPositionEditor";

/** Derived per-position progression — the estimator reads "where in the
 * job" each vano is: drafted → engine-evaluated → priced → sealed into a
 * revision → released to production. It is derived, never stored: the
 * project's own state machine is the authority. */
export function positionStatusKey(
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

/** §4: la cifra lleva su nombre en singular cuando es 1 (precedente ED2). */
function positionsCountLabel(count: number): string {
  return t(count === 1 ? "projects.positionsOne" : "projects.positionsMany").replace(
    "{count}",
    String(count),
  );
}

const STATUS_TONES: Record<string, StatusTone> = {
  draft: "neutral",
  evaluated: "info",
  priced: "success",
  frozen: "unknown",
  production: "success",
};

/** Inline quantity edit — commits on Enter/blur via the same
 * optimistic-lock PUT the editor uses; a conflict surfaces the shared
 * reload path instead of silently losing the edit. */
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

function parseMm(text: string): number | null {
  const value = Number(text.trim().replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(value) && value >= 250 && value <= 100_000 ? Math.round(value) : null;
}

/** F4 — la cota es editable en la fila: mismo `set_total_width` +
 * `set_height` del editor aplicados sobre el producto, PUT canónico con
 * lock. Si la tipología no acepta la op (el producto no cambia), el campo
 * revierte y avisa en vez de fingir la edición. */
function PositionDims({
  position,
  orgId,
  editable,
  disabled,
  onSaved,
  onConflict,
  onError,
}: {
  position: PositionResponse;
  orgId: string;
  editable: boolean;
  disabled: boolean;
  onSaved(): Promise<unknown>;
  onConflict(): void;
  onError(message: string): void;
}): JSX.Element {
  const design = position.design as PositionDesignRequest;
  const width = Math.round(Number(design.nominal_width_mm));
  const height = Math.round(Number(design.nominal_height_mm));
  const [w, setW] = useState(String(width));
  const [h, setH] = useState(String(height));
  const [saving, setSaving] = useState(false);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setW(String(width));
    setH(String(height));
    setInvalid(false);
  }, [width, height, position.updated_at]);

  if (!editable) {
    return <span className="position-dims">{formatDims(width, height)}</span>;
  }

  async function commit(): Promise<void> {
    const nextW = parseMm(w);
    const nextH = parseMm(h);
    if (nextW === null || nextH === null) {
      setW(String(width));
      setH(String(height));
      setInvalid(true);
      return;
    }
    if ((nextW === width && nextH === height) || saving) return;
    setSaving(true);
    try {
      const tree = position.design.parametric_tree;
      const product = isProductModel(tree)
        ? (tree as ProductJson)
        : wrapTreeAsProduct(tree as IntentNode, String(width), String(height));
      const ops: DesignOp[] = [];
      if (nextW !== width) ops.push({ op: "set_total_width", width_mm: String(nextW) } as DesignOp);
      if (nextH !== height) ops.push({ op: "set_height", height_mm: String(nextH) } as DesignOp);
      const after = applyDesignOps(product, ops);
      const nextDesign = designFromProduct(after, design.system_id, design.color);
      // The op silently no-ops on an undecodable tree — refuse to write a
      // design whose envelope doesn't match what the user typed.
      const gotW = Math.round(Number(nextDesign.nominal_width_mm));
      const gotH = Math.round(Number(nextDesign.nominal_height_mm));
      if (gotW !== nextW || gotH !== nextH) {
        setW(String(width));
        setH(String(height));
        onError(t("projects.dimsUnsupported"));
        return;
      }
      const response = await positionsUpdate(
        position.id,
        {
          location_tag: position.location_tag ?? "",
          quantity: position.quantity,
          design: nextDesign,
          expected_updated_at: position.updated_at,
        },
        { headers: { "X-Organization-ID": orgId } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      await onSaved();
    } catch (caught) {
      setW(String(width));
      setH(String(height));
      if (caught instanceof ApiError && caught.status === 409) onConflict();
      else onError(t("projects.dimsUnsupported"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <span className={`position-dims position-dims--edit${invalid ? " is-invalid" : ""}`}>
      <input
        aria-label={t("projects.dimsEditW")}
        aria-invalid={invalid || undefined}
        className="position-dims__input"
        disabled={disabled || saving}
        inputMode="numeric"
        onBlur={() => void commit()}
        onChange={(event) => {
          setW(event.target.value);
          setInvalid(false);
        }}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setW(String(width));
            setInvalid(false);
          }
        }}
        title={invalid ? t("projects.dimsInvalid") : t("projects.dimsEditTitle")}
        type="text"
        value={w}
      />
      <span aria-hidden>×</span>
      <input
        aria-label={t("projects.dimsEditH")}
        aria-invalid={invalid || undefined}
        className="position-dims__input"
        disabled={disabled || saving}
        inputMode="numeric"
        onBlur={() => void commit()}
        onChange={(event) => {
          setH(event.target.value);
          setInvalid(false);
        }}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setH(String(height));
            setInvalid(false);
          }
        }}
        title={invalid ? t("projects.dimsInvalid") : t("projects.dimsEditTitle")}
        type="text"
        value={h}
      />
      <span className="position-dims__unit">mm</span>
    </span>
  );
}

/** Qué le falta a la posición — la columna Estado lo muestra como tooltip
 * y el panel lateral lo lista; nunca un texto inventado. */
function positionIssues(
  position: PositionResponse,
  prep: DocumentaryPreparationPosition | undefined,
): string[] {
  const issues: string[] = [];
  if (!position.bom) issues.push(t("projects.issue.noBom"));
  if (prep?.inspector_blocked) issues.push(t("projects.issue.inspector"));
  if (prep && !prep.documentary_ready) issues.push(t("projects.issue.doc"));
  if (!position.location_tag?.trim()) issues.push(t("projects.issue.noLocation"));
  const resolution = position.measurement?.resolution;
  if (resolution && resolution.coherent === false) issues.push(t("projects.issue.measure"));
  if (resolution) {
    for (const warning of resolution.warnings ?? []) {
      const text = typeof warning === "string" ? warning : String(warning ?? "");
      if (text) issues.push(text);
    }
  }
  return issues;
}

type PositionEstado = { key: TranslationKey; tone: StatusTone; reasons: string[] };

function positionEstado(
  project: ProjectResponse,
  position: PositionResponse,
  prep: DocumentaryPreparationPosition | undefined,
): PositionEstado {
  // Sellada o en obra: la progresión manda; los faltantes documentales ya
  // fueron absorbidos por la emisión o el precio.
  if (project.status !== "DRAFT" || project.pricing_current) {
    const status = positionStatusKey(project, position);
    return { key: status.key, tone: STATUS_TONES[status.tone] ?? "neutral", reasons: [] };
  }
  const reasons = positionIssues(position, prep);
  if (!position.bom || prep?.inspector_blocked)
    return { key: "projects.estado.bloqueada", tone: "blocked", reasons };
  if (reasons.length > 0) return { key: "projects.estado.avisos", tone: "warning", reasons };
  return { key: "projects.estado.valida", tone: "success", reasons };
}

function EstadoChip({ estado }: { estado: PositionEstado }): JSX.Element {
  return (
    <StatusBadge label={t(estado.key)} tone={estado.tone} title={estado.reasons.join(" · ")} />
  );
}

/** Vidrio declarado por el árbol — dedup por spec; varios specs distintos
 * se leen como tal, nunca un promedio inventado. */
function glassSummary(design: PositionDesignRequest | undefined): string {
  const specs = new Set<string>();
  const walk = (node: unknown): void => {
    if (!node || typeof node !== "object") return;
    const record = node as Record<string, unknown>;
    if (typeof record.glass_spec === "string" && record.glass_spec) specs.add(record.glass_spec);
    if (Array.isArray(record.children)) record.children.forEach(walk);
    if (Array.isArray(record.leaves)) record.leaves.forEach(walk);
    const assembly = record.assembly as { modules?: { tree?: unknown }[] } | undefined;
    assembly?.modules?.forEach((module) => walk(module.tree));
  };
  walk(design?.parametric_tree);
  const list = [...specs];
  if (list.length === 0) return "—";
  if (list.length === 1) return list[0]!;
  return t("projects.glassMixed").replace("{count}", String(list.length));
}

function positionColorSummary(position: PositionResponse): string {
  const design = position.design as PositionDesignRequest;
  if (!design.color) return "—";
  const exterior =
    design.color_exterior && design.color_exterior !== design.color ? design.color_exterior : null;
  if (!exterior) return colorLabel(design.color);
  return t("projects.colorSummary")
    .replace("{exterior}", colorLabel(exterior))
    .replace("{interior}", colorLabel(design.color));
}

type GroupBy = "none" | "location" | "typology" | "system";

interface PositionGroup {
  key: string;
  label: string;
  items: PositionResponse[];
}

function groupPositions(
  positions: PositionResponse[],
  groupBy: GroupBy,
  systemName: (position: PositionResponse) => string,
): PositionGroup[] {
  if (groupBy === "none") return [{ key: "all", label: "", items: positions }];
  const keyOf = (position: PositionResponse): string => {
    if (groupBy === "location") {
      const tag = (position.location_tag ?? "").trim();
      return tag ? tag.split(/[·\-—,]/)[0]!.trim() : "";
    }
    if (groupBy === "typology") return typologyLabel(position.typology);
    return systemName(position);
  };
  const groups = new Map<string, PositionResponse[]>();
  for (const position of positions) {
    const key = keyOf(position) || t("projects.groupEmpty");
    const list = groups.get(key);
    if (list) list.push(position);
    else groups.set(key, [position]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b, "es-CL"))
    .map(([key, items]) => ({ key, label: key, items }));
}

/* ------------------------------------------------------------------ */
/* Alta rápida — la biblioteca de tipologías del editor, dentro de la    */
/* pestaña. Elige sistema + tipología + medidas y crea la posición con   */
/* los defaults del sistema (primer vidrio/espesor/color declarados).    */
/* ------------------------------------------------------------------ */

function QuickAddDialog({
  project,
  orgId,
  onCreated,
  onClose,
}: {
  project: ProjectResponse;
  orgId: string;
  onCreated(): Promise<unknown>;
  onClose(): void;
}): JSX.Element {
  const headers = useMemo(() => ({ headers: { "X-Organization-ID": orgId } }), [orgId]);
  const [systemId, setSystemId] = useState("");
  const [location, setLocation] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [widthMm, setWidthMm] = useState("1200");
  const [heightMm, setHeightMm] = useState("1200");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const systemsQuery = useQuery({
    queryKey: ["catalog-systems", orgId],
    queryFn: async ({ signal }) => {
      const response = await catalogSystemList({ signal, ...headers });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items.filter((item) => !item.read_only);
    },
    retry: false,
  });

  const optionsQuery = useQuery({
    queryKey: ["project-design-options", orgId, systemId],
    enabled: systemId !== "",
    queryFn: async ({ signal }) => {
      const response = await projectDesignOptions(systemId, { signal, ...headers });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
    retry: false,
  });
  const options = optionsQuery.data;
  const members = useMemo(() => resolveMembers(options), [options]);

  async function create(definition: StarterDefinition): Promise<void> {
    const w = parseMm(widthMm);
    const h = parseMm(heightMm);
    const qty = Number(quantity);
    if (w === null || h === null) {
      setError(t("projects.dimsInvalid"));
      return;
    }
    if (!Number.isInteger(qty) || qty < 1) {
      setError(t("projects.qtyInvalid"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      const nominal = starterNominalSize(definition.key);
      const product = definition.build(w ?? nominal.widthMm, h ?? nominal.heightMm);
      const modules = product.assembly.modules.map((module: { id: string }) => ({
        id: module.id,
      }));
      const ops: DesignOp[] = [];
      const glass = options?.glass_products?.[0]?.sku;
      const thickness = options?.glazing_thicknesses?.[0];
      if (glass)
        for (const module of modules)
          ops.push({ op: "set_glass", module: module.id, sku: glass } as DesignOp);
      if (thickness)
        for (const module of modules)
          ops.push({ op: "set_glass_thickness", module: module.id, mm: thickness } as DesignOp);
      const after = ops.length ? applyDesignOps(product, ops) : product;
      const color = options?.color_options?.[0]?.code ?? options?.colors?.[0] ?? "WHITE";
      const design = designFromProduct(after, systemId, color);
      const response = await positionsCreate(
        project.id,
        { location_tag: location.trim(), quantity: qty, design },
        headers,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      await onCreated();
      onClose();
    } catch (caught) {
      setError(
        t(
          caught instanceof ApiError && caught.status === 409
            ? "projects.conflict"
            : "projects.saveError",
        ),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog onClose={onClose} title={t("projects.quickAddTitle")}>
      <div className="quick-add">
        <p className="quick-add__hint">{t("projects.quickAddHint")}</p>
        <div className="quick-add__form">
          <label>
            {t("projects.colSystem")}
            <select
              autoFocus
              disabled={saving}
              onChange={(event) => setSystemId(event.target.value)}
              value={systemId}
            >
              <option value="">{t("ui.selectPlaceholder")}</option>
              {(systemsQuery.data ?? []).map((system) => (
                <option key={system.id} value={system.id}>
                  {system.name}
                  {system.code ? ` (${system.code})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("projects.location")}
            <input
              disabled={saving}
              maxLength={100}
              onChange={(event) => setLocation(event.target.value)}
              value={location}
            />
          </label>
          <label>
            {t("pricing.quantity")}
            <input
              disabled={saving}
              inputMode="numeric"
              min={1}
              onChange={(event) => setQuantity(event.target.value)}
              type="number"
              value={quantity}
            />
          </label>
          <label>
            {t("projects.colWidth")}
            <input
              disabled={saving}
              inputMode="numeric"
              onChange={(event) => setWidthMm(event.target.value)}
              value={widthMm}
            />
          </label>
          <label>
            {t("projects.colHeight")}
            <input
              disabled={saving}
              inputMode="numeric"
              onChange={(event) => setHeightMm(event.target.value)}
              value={heightMm}
            />
          </label>
        </div>
        {error && (
          <p className="quick-add__error" role="alert">
            {error}
          </p>
        )}
        {systemId === "" ? (
          <EmptyState title={t("projects.quickAddPickSystem")} />
        ) : optionsQuery.isPending ? (
          <p role="status">{t("projects.loading")}</p>
        ) : (
          <TypologyFlyout
            disabled={saving}
            members={members}
            onPick={(definition) => void create(definition)}
            openingOptions={options?.opening_options}
          />
        )}
      </div>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* La pestaña completa.                                                */
/* ------------------------------------------------------------------ */

export function PositionsTab({
  project,
  orgId,
  editable,
  disabled,
  canOpenEditor,
  prepByPosition,
  onChanged,
  onError,
  onNotice,
  onConflict,
  onDirtyImports,
}: {
  project: ProjectResponse;
  orgId: string;
  editable: boolean;
  disabled: boolean;
  /** Rol de escritura — Enter/«Abrir diseño» sólo aparecen donde el
   * editor no cae en el DeniedState (WM lee pero no diseña). */
  canOpenEditor: boolean;
  prepByPosition: Map<string, DocumentaryPreparationPosition>;
  onChanged(): Promise<unknown>;
  onError(message: string): void;
  onNotice(message: string): void;
  onConflict(): void;
  onDirtyImports(dirty: boolean): void;
}): JSX.Element {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const positions = useMemo(() => project.positions ?? [], [project.positions]);

  const systemsQuery = useQuery({
    queryKey: ["catalog-systems", orgId],
    enabled: editable,
    queryFn: async ({ signal }) => {
      const response = await catalogSystemList({
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
    retry: false,
    staleTime: 300_000,
  });
  const systemName = (position: PositionResponse): string => {
    const prep = prepByPosition.get(position.id);
    if (prep?.system_name) return prep.system_name;
    const design = position.design as PositionDesignRequest;
    const found = systemsQuery.data?.find((system) => system.id === design.system_id);
    return found?.name ?? "";
  };

  // La vista vive en la URL — compartible y capturable: ?vista=grilla|lista|importar
  const vista = params.get("vista") ?? "grilla";
  const groupBy = (params.get("grupo") ?? "none") as GroupBy;
  const setParam = (name: string, value: string | null) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value === null || value === "" || value === "none") next.delete(name);
        else next.set(name, value);
        return next;
      },
      { replace: true },
    );

  const [focusId, setFocusId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [quickAdd, setQuickAdd] = useState(false);
  const [batchDialog, setBatchDialog] = useState<"location" | "quantity" | "global" | null>(null);
  const [batchText, setBatchText] = useState("");
  const [batch, setBatch] = useState<{ done: number; total: number } | null>(null);
  const [batchError, setBatchError] = useState("");
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const mounted = useRef(true);
  // Requests mutables llevan el signal del ciclo de vida — un cambio de
  // pestaña desmonta la vista y aborta lo que aún no resolvió el servidor
  // (el contrato del workspace: toda escritura es abortable).
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    lifetime.current = new AbortController();
    return () => {
      mounted.current = false;
      lifetime.current?.abort();
      lifetime.current = null;
    };
  }, []);

  const groups = useMemo(
    () => groupPositions(positions, groupBy, systemName),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [positions, groupBy, prepByPosition, systemsQuery.data],
  );
  const flat = useMemo(() => groups.flatMap((group) => group.items), [groups]);
  const indexById = useMemo(
    () => new Map(flat.map((position, index) => [position.id, index])),
    [flat],
  );
  const focusIndex = Math.max(
    0,
    flat.findIndex((entry) => entry.id === focusId),
  );
  const focused = flat[focusIndex] ?? null;

  // Selección por defecto: el primer vano (workspace-first, como antes).
  useEffect(() => {
    if (focusId === null && flat[0]) setFocusId(flat[0].id);
  }, [flat, focusId]);
  // Una posición eliminada sale de la selección.
  useEffect(() => {
    const ids = new Set(positions.map((position) => position.id));
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => ids.has(id)));
      return next.size === prev.size ? prev : next;
    });
    if (focusId !== null && !ids.has(focusId)) setFocusId(flat[0]?.id ?? null);
  }, [positions]);

  function moveFocus(index: number): void {
    const target = flat[index];
    if (!target) return;
    setFocusId(target.id);
    rowRefs.current.get(target.id)?.focus();
  }

  function toggleSelected(id: string): void {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setFocusId(id);
  }

  function rangeSelect(toIndex: number): void {
    const anchor = focusIndex;
    const [from, to] = anchor <= toIndex ? [anchor, toIndex] : [toIndex, anchor];
    setSelected(new Set(flat.slice(from, to + 1).map((position) => position.id)));
    const target = flat[toIndex];
    if (target) setFocusId(target.id);
  }

  function onRowKeyDown(
    event: React.KeyboardEvent,
    position: PositionResponse,
    index: number,
  ): void {
    const target = event.target as HTMLElement;
    if (target.closest("input,select,textarea,button,a")) return;
    if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      // Alt+flecha reordena el N.º impreso — sólo sin agrupar, donde el
      // orden visible es exactamente el orden de la cotización.
      event.preventDefault();
      void move(position, event.key === "ArrowUp" ? index : index + 2);
    } else if (event.key === "Enter") {
      if (!canOpenEditor) return;
      event.preventDefault();
      navigate(`/projects/${project.id}/positions/${position.id}/edit`);
    } else if (event.key === "Delete" || event.key === "Backspace") {
      if (!editable) return;
      event.preventDefault();
      if (selected.size > 1 && selected.has(position.id)) void batchDelete();
      else void deleteOne(position);
    } else if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      event.preventDefault();
      moveFocus(Math.min(flat.length - 1, index + 1));
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      event.preventDefault();
      moveFocus(Math.max(0, index - 1));
    } else if (event.key === "Home") {
      event.preventDefault();
      moveFocus(0);
    } else if (event.key === "End") {
      event.preventDefault();
      moveFocus(flat.length - 1);
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
      event.preventDefault();
      setSelected(new Set(positions.map((entry) => entry.id)));
    }
  }

  function onRowClick(event: React.MouseEvent, position: PositionResponse, index: number): void {
    if (event.shiftKey) rangeSelect(index);
    else if (event.ctrlKey || event.metaKey) toggleSelected(position.id);
    else setFocusId(position.id);
  }

  /* ------------------------- batch ops ------------------------- */

  const selectedPositions = positions.filter((position) => selected.has(position.id));

  async function runBatch(fn: (position: PositionResponse) => Promise<void>): Promise<void> {
    if (batch) return;
    const targets = selectedPositions;
    if (targets.length === 0) return;
    setBatch({ done: 0, total: targets.length });
    let failed = 0;
    for (const position of targets) {
      try {
        await fn(position);
      } catch (caught) {
        failed += 1;
        if (caught instanceof ApiError && caught.status === 409) onConflict();
      }
      if (!mounted.current) return;
      setBatch((prev) => (prev ? { done: prev.done + 1, total: prev.total } : null));
    }
    if (!mounted.current) return;
    setBatch(null);
    await onChanged();
    if (failed > 0) {
      setSelected(new Set(targets.slice(-failed).map((position) => position.id)));
      onError(
        t("projects.batch.partial")
          .replace("{done}", String(targets.length - failed))
          .replace("{count}", String(targets.length)),
      );
    } else {
      setSelected(new Set());
      onNotice(t("projects.batch.done").replace("{count}", String(targets.length)));
    }
  }

  async function deleteOne(position: PositionResponse): Promise<void> {
    if (!(await confirm({ title: t("projects.deleteConfirm"), danger: true }))) return;
    try {
      const response = await positionsDestroy(
        position.id,
        { expected_updated_at: position.updated_at },
        { headers: { "X-Organization-ID": orgId }, signal: lifetime.current?.signal },
      );
      if (response.status !== 204) throw new ApiError(response.status, response.data);
      onNotice(t("projects.deleted"));
      await onChanged();
    } catch (caught) {
      onError(
        t(
          caught instanceof ApiError && caught.status === 409
            ? "projects.conflict"
            : "projects.saveError",
        ),
      );
    }
  }

  async function batchDelete(): Promise<void> {
    const count = selectedPositions.length;
    if (count === 0) return;
    if (
      !(await confirm({
        title: t("projects.batch.deleteConfirm").replace("{count}", String(count)),
        danger: true,
      }))
    )
      return;
    await runBatch((position) =>
      positionsDestroy(
        position.id,
        { expected_updated_at: position.updated_at },
        { headers: { "X-Organization-ID": orgId }, signal: lifetime.current?.signal },
      ).then((response) => {
        if (response.status !== 204) throw new ApiError(response.status, response.data);
      }),
    );
  }

  async function batchDuplicate(): Promise<void> {
    await runBatch(async (position) => {
      const response = await positionsCreate(
        project.id,
        {
          location_tag: position.location_tag ?? "",
          quantity: position.quantity,
          design: position.design as PositionDesignRequest,
        },
        { headers: { "X-Organization-ID": orgId }, signal: lifetime.current?.signal },
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
    });
  }

  async function batchLocation(): Promise<void> {
    const value = batchText.trim();
    await runBatch(async (position) => {
      const response = await positionsUpdate(
        position.id,
        {
          location_tag: value,
          quantity: position.quantity,
          design: position.design as PositionDesignRequest,
          expected_updated_at: position.updated_at,
        },
        { headers: { "X-Organization-ID": orgId }, signal: lifetime.current?.signal },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
    });
  }

  async function batchQuantity(): Promise<void> {
    const qty = Number(batchText);
    if (!Number.isInteger(qty) || qty < 1) {
      setBatchError(t("projects.qtyInvalid"));
      return;
    }
    await runBatch(async (position) => {
      const response = await positionsUpdate(
        position.id,
        {
          location_tag: position.location_tag ?? "",
          quantity: qty,
          design: position.design as PositionDesignRequest,
          expected_updated_at: position.updated_at,
        },
        { headers: { "X-Organization-ID": orgId }, signal: lifetime.current?.signal },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
    });
  }

  async function move(position: PositionResponse, toIndex: number): Promise<void> {
    if (!editable || disabled || batch !== null || groupBy !== "none") return;
    const clamped = Math.max(1, Math.min(flat.length, toIndex));
    if (clamped === position.position_index) return;
    try {
      const response = await positionsMove(
        position.id,
        { to_index: clamped, expected_updated_at: position.updated_at },
        { headers: { "X-Organization-ID": orgId }, signal: lifetime.current?.signal },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      await onChanged();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) onConflict();
      else onError(t("projects.saveError"));
    }
  }

  /* ------------------------- render ------------------------- */

  const busy = disabled || batch !== null;
  const batchLabel = batch
    ? t("projects.batch.progress")
        .replace("{done}", String(batch.done))
        .replace("{count}", String(batch.total))
    : "";

  if (vista === "importar") {
    return (
      <div className="positions-import">
        <button
          className="ui-backlink ui-backlink--back"
          onClick={() => setParam("vista", null)}
          type="button"
        >
          {t("projects.importBack")}
        </button>
        <ProjectImportsPanel
          canWrite={editable}
          onChanged={() => void onChanged()}
          onDirtyChange={onDirtyImports}
          orgId={orgId}
          projectId={project.id}
        />
      </div>
    );
  }

  const rowProps = (position: PositionResponse, index: number) => ({
    "aria-selected": selected.has(position.id) || focusId === position.id,
    "data-selected": selected.has(position.id) || undefined,
    onClick: (event: React.MouseEvent) => onRowClick(event, position, index),
    onKeyDown: (event: React.KeyboardEvent) => onRowKeyDown(event, position, index),
    ref: (element: HTMLDivElement | null) => {
      if (element) rowRefs.current.set(position.id, element);
      else rowRefs.current.delete(position.id);
    },
    role: "option" as const,
    tabIndex: index === focusIndex ? 0 : -1,
  });

  const check = (position: PositionResponse) => (
    <input
      aria-label={t("projects.selectPosition").replace("{index}", String(position.position_index))}
      checked={selected.has(position.id)}
      className="position-check"
      disabled={busy}
      onChange={() => toggleSelected(position.id)}
      onClick={(event) => event.stopPropagation()}
      type="checkbox"
    />
  );

  const estado = (position: PositionResponse): PositionEstado =>
    positionEstado(project, position, prepByPosition.get(position.id));

  // `price_net` es el neto de LÍNEA (precio × cantidad, lo aplica
  // pricing.service): P.unitario = línea/cantidad, Total = línea.
  const rowCells = (position: PositionResponse) => {
    const lineNet = Number(position.price_net);
    return {
      index: `${position.position_index}.`,
      location: position.location_tag || t("projects.issue.noLocation"),
      typology: typologyLabel(position.typology),
      system: systemName(position),
      color: positionColorSummary(position),
      glass: glassSummary(position.design as PositionDesignRequest),
      unit:
        lineNet > 0 && position.quantity > 0
          ? formatMoney(String(lineNet / position.quantity), project.currency)
          : "—",
      total: lineNet > 0 ? formatMoney(position.price_net, project.currency) : "—",
    };
  };

  return (
    <div className="positions-tab">
      <div className="positions-toolbar" role="toolbar" aria-label={t("projects.positions")}>
        <div aria-label={t("projects.viewToggle")} className="positions-toolbar__view" role="group">
          <button
            aria-pressed={vista !== "lista"}
            className="ui-button ui-button--compact"
            onClick={() => setParam("vista", "grilla")}
            type="button"
          >
            {t("projects.view.grid")}
          </button>
          <button
            aria-pressed={vista === "lista"}
            className="ui-button ui-button--compact"
            onClick={() => setParam("vista", "lista")}
            type="button"
          >
            {t("projects.view.list")}
          </button>
        </div>
        <label className="positions-toolbar__group">
          {t("projects.groupBy")}
          <select
            disabled={busy}
            onChange={(event) => setParam("grupo", event.target.value)}
            value={groupBy}
          >
            <option value="none">{t("projects.group.none")}</option>
            <option value="location">{t("projects.group.location")}</option>
            <option value="typology">{t("projects.group.typology")}</option>
            <option value="system">{t("projects.group.system")}</option>
          </select>
        </label>
        <span className="positions-toolbar__count">{positionsCountLabel(positions.length)}</span>
        <div className="positions-toolbar__actions">
          {editable && (
            <>
              <button
                className="ui-button"
                disabled={busy}
                onClick={() => setQuickAdd(true)}
                type="button"
              >
                {t("projects.quickAdd")}
              </button>
              <button
                className="ui-button"
                disabled={busy}
                onClick={() => setParam("vista", "importar")}
                type="button"
              >
                {t("projects.importView")}
              </button>
              <Link
                className="ui-button ui-button--primary"
                to={`/projects/${project.id}/positions/new`}
              >
                {t("projects.addPosition")}
              </Link>
            </>
          )}
        </div>
      </div>

      {selected.size > 0 && (
        <div className="positions-batch" role="toolbar" aria-label={t("projects.selectedPosition")}>
          <Checkbox
            aria-label={t("projects.selectAll")}
            checked={selected.size === positions.length && positions.length > 0}
            label=""
            onChange={() =>
              setSelected(
                selected.size === positions.length
                  ? new Set()
                  : new Set(positions.map((position) => position.id)),
              )
            }
          />
          <span className="positions-batch__count">
            {t("projects.selectedCount").replace("{count}", String(selected.size))}
          </span>
          {editable && (
            <>
              <button
                className="ui-button ui-button--compact"
                disabled={busy}
                onClick={() => void batchDuplicate()}
                type="button"
              >
                {t("projects.batch.duplicate")}
              </button>
              <button
                className="ui-button ui-button--compact"
                disabled={busy}
                onClick={() => {
                  setBatchText("");
                  setBatchError("");
                  setBatchDialog("location");
                }}
                type="button"
              >
                {t("projects.batch.location")}
              </button>
              <button
                className="ui-button ui-button--compact"
                disabled={busy}
                onClick={() => {
                  setBatchText("");
                  setBatchError("");
                  setBatchDialog("quantity");
                }}
                type="button"
              >
                {t("projects.batch.quantity")}
              </button>
              <button
                className="ui-button ui-button--compact"
                disabled={busy || Boolean(project.pricing_current)}
                onClick={() => setBatchDialog("global")}
                title={project.pricing_current ? t("projects.lockedPriced") : undefined}
                type="button"
              >
                {t("projects.batch.global")}
              </button>
              <button
                className="ui-button ui-button--compact ui-button--danger"
                disabled={busy}
                onClick={() => void batchDelete()}
                type="button"
              >
                {t("projects.batch.delete")}
              </button>
            </>
          )}
          <button
            className="ui-button ui-button--compact"
            onClick={() => setSelected(new Set())}
            type="button"
          >
            {t("projects.clearSelection")}
          </button>
          {batchLabel && (
            <span className="positions-batch__progress" role="status">
              {batchLabel}
            </span>
          )}
        </div>
      )}

      {positions.length === 0 ? (
        <EmptyState
          action={
            editable ? (
              <div className="positions-empty__actions">
                <Link
                  className="ui-button ui-button--primary"
                  to={`/projects/${project.id}/positions/new`}
                >
                  {t("projects.addPosition")}
                </Link>
                <button className="ui-button" onClick={() => setQuickAdd(true)} type="button">
                  {t("projects.quickAdd")}
                </button>
                <button
                  className="ui-button"
                  onClick={() => setParam("vista", "importar")}
                  type="button"
                >
                  {t("projects.importView")}
                </button>
              </div>
            ) : undefined
          }
          body={t("projects.addFirst")}
          illustration="elevation"
          title={t("projects.noPositions")}
        />
      ) : (
        <div className="positions-area">
          <div
            aria-label={t("projects.positions")}
            className={`position-grid${vista === "lista" ? " position-grid--dense" : ""}`}
            role="listbox"
          >
            {vista === "lista" && (
              <div aria-hidden className="position-line position-line--head">
                <span />
                <span className="position-line__thumb" />
                <span className="position-line__loc">
                  {t("projects.colIndex")} · {t("projects.location")}
                </span>
                <span>{t("projects.typology")}</span>
                <span>{t("projects.colVanoFab")}</span>
                <span>{t("projects.colSystem")}</span>
                <span>{t("projects.color")}</span>
                <span>{t("projects.glass")}</span>
                <span className="is-numeric">{t("pricing.quantity")}</span>
                <span className="is-numeric">{t("projects.unitPrice")}</span>
                <span className="is-numeric">{t("projects.lineTotal")}</span>
                <span>{t("projects.colEstado")}</span>
              </div>
            )}
            {groups.map((group) =>
              vista === "lista" ? (
                <div className="position-group" key={group.key}>
                  {groupBy !== "none" && (
                    <h3 className="position-group__title">
                      {group.label}
                      <span className="position-group__count">
                        {positionsCountLabel(group.items.length)}
                      </span>
                    </h3>
                  )}
                  {group.items.map((position) => {
                    const index = indexById.get(position.id) ?? 0;
                    const cells = rowCells(position);
                    return (
                      <div
                        {...rowProps(position, index)}
                        className="position-line"
                        key={position.id}
                      >
                        <span className="position-line__check">{check(position)}</span>
                        <span className="position-line__thumb">
                          <PositionThumb design={position.design} variant="studio" />
                        </span>
                        <span className="position-line__loc" title={cells.location}>
                          <span className="position-line__index">{cells.index}</span>{" "}
                          {cells.location}
                        </span>
                        <span title={cells.typology}>{cells.typology}</span>
                        <span className="position-line__dims">
                          <PositionDims
                            disabled={busy}
                            editable={editable}
                            onConflict={onConflict}
                            onError={onError}
                            onSaved={onChanged}
                            orgId={orgId}
                            position={position}
                          />
                          {position.measurement?.resolution && (
                            <span className="position-line__fab" title={t("projects.colVanoFab")}>
                              →{" "}
                              {formatDims(
                                position.measurement.resolution.fabrication_width_mm,
                                position.measurement.resolution.fabrication_height_mm,
                              )}
                            </span>
                          )}
                        </span>
                        <span title={cells.system}>{cells.system || "—"}</span>
                        <span title={cells.color}>{cells.color}</span>
                        <span title={cells.glass}>{cells.glass}</span>
                        <span className="is-numeric">
                          {editable ? (
                            <PositionQtyInput
                              disabled={busy}
                              onConflict={onConflict}
                              onError={() => onError(t("projects.uncertain"))}
                              onSaved={onChanged}
                              orgId={orgId}
                              position={position}
                            />
                          ) : (
                            `×${fmtQty(position.quantity)}`
                          )}
                        </span>
                        <span className="is-numeric">{cells.unit}</span>
                        <span className="is-numeric">{cells.total}</span>
                        <span>
                          <EstadoChip estado={estado(position)} />
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="position-group" key={group.key}>
                  {groupBy !== "none" && (
                    <h3 className="position-group__title">
                      {group.label}
                      <span className="position-group__count">
                        {positionsCountLabel(group.items.length)}
                      </span>
                    </h3>
                  )}
                  <div className="position-cards">
                    {group.items.map((position) => {
                      const index = indexById.get(position.id) ?? 0;
                      const cells = rowCells(position);
                      return (
                        <div
                          {...rowProps(position, index)}
                          className="position-card"
                          key={position.id}
                        >
                          <div className="position-card__check">{check(position)}</div>
                          <div className="position-card__estado">
                            <EstadoChip estado={estado(position)} />
                          </div>
                          <div className="position-card__thumb">
                            <PositionThumb design={position.design} variant="studio" />
                          </div>
                          <div className="position-card__id">
                            <span className="position-card__index">{cells.index}</span>
                            <span className="position-card__loc" title={cells.location}>
                              {cells.location}
                            </span>
                          </div>
                          <div className="position-card__dims">
                            <PositionDims
                              disabled={busy}
                              editable={editable}
                              onConflict={onConflict}
                              onError={onError}
                              onSaved={onChanged}
                              orgId={orgId}
                              position={position}
                            />
                          </div>
                          <div
                            className="position-card__spec"
                            title={`${cells.typology} · ${cells.system} · ${cells.color} · ${cells.glass}`}
                          >
                            <span>{cells.typology}</span>
                            {cells.system && (
                              <span className="position-card__system">{cells.system}</span>
                            )}
                            <span>{cells.color}</span>
                            <span>{cells.glass}</span>
                          </div>
                          <div className="position-card__row">
                            {editable ? (
                              <PositionQtyInput
                                disabled={busy}
                                onConflict={onConflict}
                                onError={() => onError(t("projects.uncertain"))}
                                onSaved={onChanged}
                                orgId={orgId}
                                position={position}
                              />
                            ) : (
                              <span>×{fmtQty(position.quantity)}</span>
                            )}
                            <span className="position-card__price">
                              {cells.total !== "—" ? cells.total : cells.unit}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ),
            )}
          </div>

          <aside aria-label={t("projects.selectedPosition")} className="positions-side">
            {focused ? (
              <PositionDetail
                busy={busy}
                canOpenEditor={canOpenEditor}
                editable={editable}
                estado={estado(focused)}
                groupBy={groupBy}
                onDelete={() => void deleteOne(focused)}
                onMove={(toIndex) => void move(focused, toIndex)}
                position={focused}
                project={project}
                reasons={estado(focused).reasons}
              />
            ) : (
              <p className="positions-side__hint">{t("projects.positionHint")}</p>
            )}
          </aside>
        </div>
      )}

      {quickAdd && (
        <QuickAddDialog
          onClose={() => setQuickAdd(false)}
          onCreated={async () => {
            await onChanged();
          }}
          orgId={orgId}
          project={project}
        />
      )}

      {batchDialog === "location" && (
        <Dialog
          onClose={() => setBatchDialog(null)}
          title={t("projects.batch.locationTitle").replace("{count}", String(selected.size))}
        >
          <form
            className="batch-form"
            onSubmit={(event) => {
              event.preventDefault();
              setBatchDialog(null);
              void batchLocation();
            }}
          >
            <label>
              {t("projects.batch.locationLabel")}
              <input
                autoFocus
                disabled={Boolean(batch)}
                maxLength={100}
                onChange={(event) => setBatchText(event.target.value)}
                value={batchText}
              />
            </label>
            <div className="form-actions">
              <button
                className="ui-button ui-button--primary"
                disabled={Boolean(batch)}
                type="submit"
              >
                {t("projects.batch.apply")}
              </button>
              <button className="ui-button" onClick={() => setBatchDialog(null)} type="button">
                {t("projects.cancel")}
              </button>
            </div>
          </form>
        </Dialog>
      )}

      {batchDialog === "quantity" && (
        <Dialog
          onClose={() => setBatchDialog(null)}
          title={t("projects.batch.quantityTitle").replace("{count}", String(selected.size))}
        >
          <form
            className="batch-form"
            onSubmit={(event) => {
              event.preventDefault();
              setBatchDialog(null);
              void batchQuantity();
            }}
          >
            <label>
              {t("projects.batch.quantityLabel")}
              <input
                autoFocus
                disabled={Boolean(batch)}
                inputMode="numeric"
                min={1}
                onChange={(event) => {
                  setBatchText(event.target.value);
                  setBatchError("");
                }}
                type="number"
                value={batchText}
              />
            </label>
            {batchError && (
              <p className="field-hint" role="alert">
                {batchError}
              </p>
            )}
            <div className="form-actions">
              <button
                className="ui-button ui-button--primary"
                disabled={Boolean(batch)}
                type="submit"
              >
                {t("projects.batch.apply")}
              </button>
              <button className="ui-button" onClick={() => setBatchDialog(null)} type="button">
                {t("projects.cancel")}
              </button>
            </div>
          </form>
        </Dialog>
      )}

      {batchDialog === "global" && (
        <Dialog onClose={() => setBatchDialog(null)} title={t("projects.batch.globalTitle")}>
          <GlobalChangesPanel
            disabled={busy}
            initialScope={selected}
            onApplied={async () => {
              setSelected(new Set());
              setBatchDialog(null);
              await onChanged();
            }}
            orgId={orgId}
            positions={positions.map((position) => ({
              position_id: position.id,
              location_tag: position.location_tag,
              doc_incomplete: prepByPosition.get(position.id)?.documentary_ready === false,
            }))}
            pricingLocked={Boolean(project.pricing_current)}
            projectId={project.id}
          />
        </Dialog>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Panel lateral — la posición enfocada: ficha completa, qué falta,     */
/* acciones y la composición real del BOM.                              */
/* ------------------------------------------------------------------ */

function PositionDetail({
  position,
  project,
  estado,
  reasons,
  editable,
  canOpenEditor,
  busy,
  groupBy,
  onDelete,
  onMove,
}: {
  position: PositionResponse;
  project: ProjectResponse;
  estado: PositionEstado;
  reasons: string[];
  editable: boolean;
  canOpenEditor: boolean;
  busy: boolean;
  groupBy: GroupBy;
  onDelete(): void;
  onMove(toIndex: number): void;
}): JSX.Element {
  const design = position.design as PositionDesignRequest;
  const net = Number(position.price_net) > 0;
  const discount = Number(position.discount_pct) > 0;
  const total = position.position_index;
  const count = project.positions?.length ?? 0;
  return (
    <div className="positions-side__detail">
      <div className="positions-side__thumb">
        <PositionThumb design={position.design} variant="studio" />
      </div>
      <dl className="positions-side__facts">
        <div>
          <dt>{t("projects.location")}</dt>
          <dd>{position.location_tag || "—"}</dd>
        </div>
        <div>
          <dt>{t("projects.dims")}</dt>
          <dd>{formatDims(design.nominal_width_mm, design.nominal_height_mm)}</dd>
        </div>
        {position.measurement?.resolution && (
          <div>
            <dt>{t("projects.colVanoFab")}</dt>
            <dd>
              {formatDims(
                position.measurement.resolution.fabrication_width_mm,
                position.measurement.resolution.fabrication_height_mm,
              )}
            </dd>
          </div>
        )}
        <div>
          <dt>{t("pricing.quantity")}</dt>
          <dd>{fmtQty(position.quantity)}</dd>
        </div>
        {net && (
          <div>
            <dt>{t("projects.unitPrice")}</dt>
            <dd>
              {formatMoney(
                String(Number(position.price_net) / Math.max(1, position.quantity)),
                project.currency,
              )}
              {discount &&
                ` · ${t("portal.discount")} ${formatPercent(position.discount_pct, "fraction")}`}
            </dd>
          </div>
        )}
        {net && (
          <div>
            <dt>{t("projects.lineTotal")}</dt>
            <dd>{formatMoney(position.price_net, project.currency)}</dd>
          </div>
        )}
        <div>
          <dt>{t("projects.typology")}</dt>
          <dd>{typologyLabel(position.typology)}</dd>
        </div>
        <div>
          <dt>{t("projects.colEstado")}</dt>
          <dd>
            <EstadoChip estado={estado} />
          </dd>
        </div>
      </dl>
      {reasons.length > 0 && (
        <ul className="positions-side__issues">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <div className="positions-side__actions">
        {canOpenEditor && (
          <Link className="ui-button" to={`/projects/${project.id}/positions/${position.id}/edit`}>
            {t("projects.openPosition")}
          </Link>
        )}
        {editable && (
          <>
            <Link
              className="ui-button"
              to={`/projects/${project.id}/positions/new?copy=${position.id}`}
            >
              {t("projects.duplicatePosition")}
            </Link>
            {groupBy === "none" && (
              <div className="positions-side__move" role="group" aria-label={t("projects.reorder")}>
                <button
                  className="ui-button ui-button--compact"
                  disabled={busy || total <= 1}
                  onClick={() => onMove(total - 1)}
                  title={t("projects.movePosition.up")}
                  type="button"
                >
                  {t("projects.batch.moveUp")}
                </button>
                <button
                  className="ui-button ui-button--compact"
                  disabled={busy || total >= count}
                  onClick={() => onMove(total + 1)}
                  title={t("projects.movePosition.down")}
                  type="button"
                >
                  {t("projects.batch.moveDown")}
                </button>
              </div>
            )}
            <button
              className="ui-button ui-button--danger"
              disabled={busy}
              onClick={onDelete}
              type="button"
            >
              {t("projects.deletePosition")}
            </button>
          </>
        )}
      </div>
      <ProjectBom result={position.bom} />
    </div>
  );
}
