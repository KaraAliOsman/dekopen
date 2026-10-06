import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/apiMutator";
import {
  catalogSystemList,
  positionsRetrieve,
  positionsUpdate,
  pricingDesignBatchPreview,
  projectDesignOptions,
} from "../../api/generated/dekopen";
import type { DesignBatchPreviewItemRequestDesign } from "../../api/generated/models/designBatchPreviewItemRequestDesign";
import type { PositionDesignRequest } from "../../api/generated/models/positionDesignRequest";
import type { PositionResponse } from "../../api/generated/models/positionResponse";
import type { DesignOp } from "../commands/types";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { formatMoney } from "../../format";
import { addDecimal, formatDecimal, parseDecimal, subtractDecimal } from "./decimal";
import { applyDesignOps, describeDesignOp, describeScopeOp } from "../canvas/designOps";
import { isProductModel, type ProductJson } from "../canvas/productEditing";
import { designFromProduct } from "../assistant/designPayload";

/** P08 — cambios globales: el mismo cambio aplicado a todas (o un subconjunto)
 * de las posiciones de la revisión en borrador. Usa exactamente el mismo
 * registro de ops del editor/asistente (applyDesignOps + designFromProduct)
 * y el mismo PUT canónico de posiciones; el impacto de precio se previsualiza
 * con pricingDesignBatchPreview antes de tocar nada. Una operación deshacible:
 * el lote anterior queda en memoria hasta que sales del panel. */

type OpKind = "glass" | "finish" | "system" | "handle" | "thickness" | "panel";

const OP_LABELS: Record<OpKind, TranslationKey> = {
  glass: "global.opGlass",
  finish: "global.opFinish",
  system: "global.opSystem",
  handle: "global.opHandle",
  thickness: "global.opThickness",
  panel: "global.opPanel",
};

interface Catalogs {
  glass: { sku: string; label: string }[];
  colors: { code: string; name: string }[];
  panels: { sku: string; label: string }[];
  thicknesses: string[];
  systems: { id: string; label: string }[];
}

interface Row {
  position_id: string;
  index: number;
  location: string;
  detail?: PositionResponse;
  before?: PositionDesignRequest;
  after?: PositionDesignRequest;
  product?: ProductJson;
  ops: DesignOp[];
  status: "loading" | "ready" | "unsupported" | "failed" | "applied" | "apply_failed";
  error?: string;
  unitBefore?: string | null;
  unitAfter?: string | null;
}

interface UndoRow {
  position_id: string;
  location_tag: string;
  quantity: number;
  design: PositionDesignRequest;
}

function apiDetail(error: unknown, fallback: string): string {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload !== null) {
    const detail = (error.payload as { error?: { detail?: unknown } }).error?.detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return error instanceof Error ? error.message : fallback;
}

function productOps(kind: OpKind, value: string, modules: { id: string }[]): DesignOp[] {
  return modules.map((module) => {
    switch (kind) {
      case "glass":
        return { op: "set_glass", module: module.id, sku: value } as DesignOp;
      case "thickness":
        return { op: "set_glass_thickness", module: module.id, mm: value } as DesignOp;
      case "handle":
        return { op: "set_handle_height", module: module.id, mm: value } as DesignOp;
      case "panel":
        return { op: "set_panel", module: module.id, sku: value || null } as DesignOp;
      default:
        return { op: "noop" } as unknown as DesignOp;
    }
  });
}

/** Posición aplicable por el panel — la vista de emisión entrega la fila
 * documental completa; la ficha del proyecto entrega sólo id+ubicación. */
export interface GlobalChangePosition {
  position_id: string;
  location_tag: string | null;
  /** true cuando la fila documental declara que le faltan políticas —
   * el panel avisa que esa posición emitiría «sólo cotización». */
  doc_incomplete?: boolean;
}

export function GlobalChangesPanel({
  projectId,
  orgId,
  positions,
  disabled,
  pricingLocked = false,
  onApplied,
}: {
  projectId: string;
  orgId: string;
  positions: GlobalChangePosition[];
  disabled: boolean;
  /** Precios aplicados: el PUT de posiciones 409 commercial_revision_required
   * — el panel se muestra bloqueado con la causa, no deja intentar. */
  pricingLocked?: boolean;
  onApplied(): Promise<unknown>;
}): JSX.Element {
  const queryClient = useQueryClient();
  const headers = useMemo(() => ({ headers: { "X-Organization-ID": orgId } }), [orgId]);
  const [op, setOp] = useState<OpKind>("glass");
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<Set<string> | null>(null); // null = todas
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "applying" | "done">("idle");
  const [currency, setCurrency] = useState("CLP");
  const [undo, setUndo] = useState<UndoRow[] | null>(null);
  const [notice, setNotice] = useState("");

  const targets = positions.filter((position) => scope === null || scope.has(position.position_id));

  // Catálogos por sistema involucrado — el picker sólo ofrece valores que
  // algún sistema del alcance declara (el motor vuelve a validar).
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const systemIds = new Set<string>();
        for (const position of targets) {
          try {
            const detail = await positionsRetrieve(position.position_id, headers);
            if (detail.status === 200) {
              const design = (detail.data as PositionResponse).design as PositionDesignRequest;
              if (design.system_id) systemIds.add(design.system_id);
            }
          } catch {
            /* una posición ilegible se resuelve al previsualizar */
          }
        }
        const glass = new Map<string, string>();
        const colors = new Map<string, string>();
        const panels = new Map<string, string>();
        const thicknesses = new Set<string>();
        await Promise.all(
          [...systemIds].map(async (systemId) => {
            const options = await projectDesignOptions(systemId, headers);
            if (options.status !== 200) return;
            const data = options.data as {
              glass_products?: { sku?: string; name?: string; notation?: string | null }[];
              color_options?: { code?: string; name?: string }[];
              colors?: string[];
              panel_choices?: { sku?: string; name?: string }[];
              glazing_thicknesses?: string[];
            };
            for (const item of data.glass_products ?? []) {
              if (item.sku) {
                glass.set(
                  item.sku,
                  [item.name, item.notation].filter(Boolean).join(" · ") || item.sku,
                );
              }
            }
            for (const item of data.color_options ?? []) {
              if (item.code) colors.set(item.code, item.name || item.code);
            }
            for (const code of data.colors ?? []) {
              if (!colors.has(code)) colors.set(code, code);
            }
            for (const item of data.panel_choices ?? []) {
              if (item.sku) panels.set(item.sku, item.name || item.sku);
            }
            for (const mm of data.glazing_thicknesses ?? []) thicknesses.add(mm);
          }),
        );
        const systemsResponse = await catalogSystemList(headers);
        const systems =
          systemsResponse.status === 200
            ? systemsResponse.data.items
                .filter((item) => !item.read_only)
                .map((item) => ({
                  id: item.id,
                  label: `${item.name}${item.code ? ` (${item.code})` : ""}`,
                }))
            : [];
        if (active) {
          setCatalogs({
            glass: [...glass].map(([sku, label]) => ({ sku, label })),
            colors: [...colors].map(([code, name]) => ({ code, name })),
            panels: [...panels].map(([sku, label]) => ({ sku, label })),
            thicknesses: [...thicknesses].sort((a, b) => Number(a) - Number(b)),
            systems,
          });
        }
      } catch {
        /* catálogo parcial — el picker puede quedar vacío sin romper */
      }
    })();
    return () => {
      active = false;
    };
  }, [targets.length, headers]);

  async function preview(): Promise<void> {
    setPhase("loading");
    setNotice("");
    const resolved: Row[] = await Promise.all(
      targets.map(async (position, index): Promise<Row> => {
        const row: Row = {
          position_id: position.position_id,
          index: index + 1,
          location: position.location_tag || `V-${index + 1}`,
          ops: [],
          status: "loading",
        };
        try {
          const detail = await positionsRetrieve(position.position_id, headers);
          if (detail.status !== 200) throw new ApiError(detail.status, detail.data);
          row.detail = detail.data as PositionResponse;
          row.before = row.detail.design as PositionDesignRequest;
          if (op === "finish" || op === "system") {
            row.after = {
              ...row.before,
              ...(op === "finish" ? { color: value } : { system_id: value }),
            };
            row.ops = [
              op === "finish"
                ? ({ op: "set_finish", color: value } as DesignOp)
                : ({ op: "set_system", system_id: value } as DesignOp),
            ];
            row.status = "ready";
            return row;
          }
          const tree = row.before.parametric_tree;
          if (!isProductModel(tree)) {
            row.status = "unsupported";
            return row;
          }
          row.product = tree;
          row.ops = productOps(op, value, tree.assembly.modules);
          row.after = designFromProduct(
            applyDesignOps(tree, row.ops),
            row.before.system_id,
            row.before.color,
          );
          row.status = "ready";
        } catch (error) {
          row.status = "failed";
          row.error = apiDetail(error, t("global.refused"));
        }
        return row;
      }),
    );
    const candidates = resolved.filter((row) => row.status === "ready" && row.after);
    if (candidates.length > 0) {
      try {
        const response = await pricingDesignBatchPreview(
          {
            project_id: projectId,
            effective_date: new Date().toISOString().slice(0, 10),
            items: candidates.map((row) => ({
              position_id: row.position_id,
              design: row.after as unknown as DesignBatchPreviewItemRequestDesign,
            })),
          },
          headers,
        );
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        setCurrency(response.data.currency ?? "CLP");
        const costs = new Map(response.data.items.map((item) => [item.position_id, item]));
        for (const row of resolved) {
          const entry = costs.get(row.position_id);
          if (entry === undefined) continue;
          if (!entry.ok) {
            row.status = "failed";
            row.error = entry.error ?? entry.error_code ?? t("global.refused");
            continue;
          }
          row.unitBefore = entry.unit_cost_before;
          row.unitAfter = entry.unit_cost_after;
        }
      } catch (error) {
        // La estimación de costo es auxiliar — el PUT canónico valida con
        // el motor igual; pero el fallo NO se traga: se declara en el aviso
        // y la fila muestra "sin costo".
        setNotice(apiDetail(error, t("global.previewNoCost")));
        for (const row of resolved) {
          if (row.status === "ready") {
            row.unitBefore = null;
            row.unitAfter = null;
          }
        }
      }
    }
    setRows(resolved);
    setPhase("ready");
  }

  async function apply(): Promise<void> {
    if (phase !== "ready") return;
    setPhase("applying");
    const undoRows: UndoRow[] = [];
    const next = [...rows];
    for (const [index, row] of next.entries()) {
      if (row.status !== "ready" || row.after === undefined || row.detail === undefined) continue;
      undoRows.push({
        position_id: row.position_id,
        location_tag: row.detail.location_tag ?? "",
        quantity: row.detail.quantity,
        design: row.before!,
      });
      try {
        const response = await positionsUpdate(
          row.position_id,
          {
            location_tag: row.detail.location_tag ?? "",
            quantity: row.detail.quantity,
            design: row.after,
            expected_updated_at: row.detail.updated_at,
          },
          headers,
        );
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        next[index] = { ...row, status: "applied" };
      } catch (error) {
        next[index] = {
          ...row,
          status: "apply_failed",
          error: apiDetail(error, t("global.refused")),
        };
      }
      setRows([...next]);
    }
    setUndo(undoRows);
    setPhase("done");
    void queryClient.invalidateQueries({ queryKey: ["project-pages"] });
    const appliedCount = next.filter((row) => row.status === "applied").length;
    const firstError = next.find((row) => row.status === "apply_failed")?.error;
    setNotice(
      appliedCount === 0
        ? `${t("global.noneApplied")} ${firstError ?? ""}`.trim()
        : t("global.done"),
    );
    await onApplied();
  }

  async function undoApply(): Promise<void> {
    if (!undo?.length) return;
    setPhase("applying");
    try {
      for (const snapshot of undo) {
        const detail = await positionsRetrieve(snapshot.position_id, headers);
        if (detail.status !== 200) continue;
        const current = detail.data as PositionResponse;
        const response = await positionsUpdate(
          snapshot.position_id,
          {
            location_tag: snapshot.location_tag,
            quantity: snapshot.quantity,
            design: snapshot.design,
            expected_updated_at: current.updated_at,
          },
          headers,
        );
        if (response.status !== 200) throw new ApiError(response.status, response.data);
      }
      setUndo(null);
      setRows([]);
      setPhase("idle");
      setNotice(t("global.undone"));
      void queryClient.invalidateQueries({ queryKey: ["project-pages"] });
      await onApplied();
    } catch (error) {
      setNotice(apiDetail(error, t("projects.saveError")));
      setPhase("done");
    }
  }

  const ready = rows.filter((row) => row.status === "ready");
  const applied = rows.filter((row) => row.status === "applied");
  const totalDelta = ready.reduce(
    (sum, row) => {
      const before = parseDecimal(row.unitBefore ?? "");
      const after = parseDecimal(row.unitAfter ?? "");
      if (before === null || after === null) return sum;
      const quantity = parseDecimal(String(row.detail?.quantity ?? 1));
      const delta = subtractDecimal(after, before);
      return addDecimal(
        sum,
        quantity === null
          ? delta
          : {
              numerator: delta.numerator * quantity.numerator,
              denominator: delta.denominator * quantity.denominator,
            },
      );
    },
    parseDecimal("0") ?? { numerator: 0n, denominator: 1n },
  );

  const valueOptions: { value: string; label: string }[] =
    op === "glass"
      ? (catalogs?.glass ?? []).map((item) => ({ value: item.sku, label: item.label }))
      : op === "finish"
        ? (catalogs?.colors ?? []).map((item) => ({ value: item.code, label: item.name }))
        : op === "system"
          ? (catalogs?.systems ?? []).map((item) => ({ value: item.id, label: item.label }))
          : op === "thickness"
            ? (catalogs?.thicknesses ?? []).map((mm) => ({ value: mm, label: `${mm} mm` }))
            : op === "panel"
              ? [
                  { value: "", label: t("global.noPanel") },
                  ...(catalogs?.panels ?? []).map((item) => ({
                    value: item.sku,
                    label: item.label,
                  })),
                ]
              : [];

  const locked = disabled || pricingLocked;
  const canPreview = targets.length > 0 && (op === "panel" ? true : value.trim() !== "") && !locked;
  const invalidTargets = targets.filter((position) => position.doc_incomplete);

  return (
    <section className="global-changes" aria-label={t("global.title")}>
      <h3>{t("global.title")}</h3>
      <p className="global-changes__hint">{t("global.hint")}</p>
      {pricingLocked && (
        <p className="global-changes__warn" role="note">
          {t("global.pricingLocked")}
        </p>
      )}
      <div className="global-changes__form">
        <label htmlFor="global-op">{t("global.op")}</label>
        <select
          id="global-op"
          disabled={locked || phase === "applying"}
          value={op}
          onChange={(event) => {
            setOp(event.target.value as OpKind);
            setValue("");
            setPhase("idle");
            setRows([]);
          }}
        >
          {(Object.keys(OP_LABELS) as OpKind[]).map((kind) => (
            <option key={kind} value={kind}>
              {t(OP_LABELS[kind])}
            </option>
          ))}
        </select>
        <label htmlFor="global-value">{t("global.value")}</label>
        {op === "handle" ? (
          <input
            id="global-value"
            inputMode="decimal"
            disabled={locked || phase === "applying"}
            placeholder="1050"
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setPhase("idle");
            }}
          />
        ) : (
          <select
            id="global-value"
            disabled={locked || phase === "applying" || valueOptions.length === 0}
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setPhase("idle");
            }}
          >
            <option value="">{op === "panel" ? t("global.noPanel") : "—"}</option>
            {valueOptions.map((item) => (
              <option key={item.value || "__none"} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        )}
        <fieldset className="global-changes__scope">
          <legend>{t("global.positions")}</legend>
          <label className="global-changes__scope-all">
            <input
              type="checkbox"
              checked={scope === null}
              disabled={locked || phase === "applying"}
              onChange={(event) => {
                setScope(event.target.checked ? null : new Set());
                setPhase("idle");
              }}
            />
            {t("global.allPositions").replace("{count}", String(positions.length))}
          </label>
          {scope !== null && (
            <ul>
              {positions.map((position, index) => (
                <li key={position.position_id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={scope.has(position.position_id)}
                      disabled={locked || phase === "applying"}
                      onChange={(event) => {
                        const next = new Set(scope);
                        if (event.target.checked) next.add(position.position_id);
                        else next.delete(position.position_id);
                        setScope(next);
                        setPhase("idle");
                      }}
                    />
                    V-{index + 1}
                    {position.location_tag ? ` · ${position.location_tag}` : ""}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
        <div className="projects-actions">
          <button type="button" disabled={!canPreview || locked} onClick={() => void preview()}>
            {phase === "loading" ? t("global.previewing") : t("global.preview")}
          </button>
          <button
            type="button"
            className="primary-action"
            disabled={phase !== "ready" || ready.length === 0 || locked}
            onClick={() => void apply()}
          >
            {t("global.apply").replace("{count}", String(ready.length))}
          </button>
        </div>
      </div>
      {notice && <p role="status">{notice}</p>}
      {(phase === "ready" || phase === "done") && rows.length > 0 && (
        <>
          {invalidTargets.length > 0 && (
            <p className="global-changes__warn" role="note">
              {t("quotation.emitOutcomeQuoteOnly")}{" "}
              {invalidTargets.map((position) => `V-${targets.indexOf(position) + 1}`).join(" · ")}
            </p>
          )}
          <ul className="global-changes__rows">
            {rows.map((row) => (
              <li className="global-changes__row" key={row.position_id}>
                <span className="global-changes__where">
                  V-{row.index}
                  {row.location ? ` · ${row.location}` : ""}
                </span>
                <span className="global-changes__ops">
                  {row.product && row.ops.length
                    ? `${describeDesignOp(row.ops[0]!, row.product)}${
                        row.ops.length > 1 ? ` +${row.ops.length - 1}` : ""
                      }`
                    : row.ops.length
                      ? (describeScopeOp(row.ops[0]!) ?? String(row.ops[0]!.op))
                      : "—"}
                </span>
                <span className="global-changes__cost">
                  {row.status === "applied"
                    ? t("global.appliedCount").replace("{done}", "1").replace("{count}", "1")
                    : row.status === "failed" || row.status === "apply_failed"
                      ? (row.error ?? t("global.refused"))
                      : row.status === "unsupported"
                        ? t("global.refused")
                        : row.unitBefore === undefined
                          ? "…"
                          : row.unitBefore === null || row.unitAfter === null
                            ? t("global.noCost")
                            : `${formatMoney(row.unitBefore, currency)} → ${formatMoney(row.unitAfter, currency)}`}
                </span>
              </li>
            ))}
          </ul>
          {phase === "ready" && (
            <p className="global-changes__delta">
              {ready.length > 0
                ? t("global.delta").replace(
                    "{delta}",
                    formatMoney(formatDecimal(totalDelta), currency),
                  )
                : t("global.noneReady")}
            </p>
          )}
        </>
      )}
      {phase === "done" && (
        <p role="status">
          {t("global.appliedCount")
            .replace("{done}", String(applied.length))
            .replace("{count}", String(rows.length))}
        </p>
      )}
      {undo !== null && undo.length > 0 && phase === "done" && (
        <div className="global-changes__undo">
          <p>{t("global.undoHint")}</p>
          <button type="button" disabled={disabled} onClick={() => void undoApply()}>
            {t("global.undo")}
          </button>
        </div>
      )}
      {phase === "idle" && !notice && (
        <p className="global-changes__hint">{t("global.pickFirst")}</p>
      )}
    </section>
  );
}
