/** D02 glass selector — Básico offers the catalog's declared products as
 * cards (name, stack, thickness, weight, declared relative price, safety
 * marks); Avanzado composes the layer stack exterior → interior with the
 * to-scale section the termopanel actually is. Validation is local to the
 * declared data (alternation, dimensions, bead range); real weight, cut
 * and safety findings stay engine-computed and land on the BOM. */

import { useMemo, useState } from "react";

import type { GlassProductChoice, GlassSafetyFinding } from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { quantize } from "../../format";
import { Icon } from "../../ui/icons";
import { SegmentedControl } from "../../ui/Controls";
import type {
  GlassChamberSpec,
  GlassCompositionSpec,
  GlassLaminaSpec,
  GlassSurchargeSelectionSpec,
  IntentNode,
} from "./intentEditing";
import {
  CHAMBER_WIDTHS_MM,
  COATINGS,
  compositionErrors,
  compositionNetMm,
  compositionNotation,
  compositionTotalMm,
  defaultComposition,
  emptySelection,
  INTERLAYERS,
  LAMINA_THICKNESSES_MM,
  mmNumber,
  productSatisfiesSafety,
  retargetSurcharges,
} from "./glazing";

export type GlazingPatch = Partial<
  Pick<
    IntentNode,
    | "glass_article_sku"
    | "glass_spec"
    | "glass_thickness_mm"
    | "glass_composition"
    | "glass_options"
  >
>;

/** What the picker writes through — the bay's declared glazing fields. */
export type GlazingValue = Pick<
  IntentNode,
  "glass_article_sku" | "glass_spec" | "glass_thickness_mm" | "glass_composition" | "glass_options"
>;

const PRICE_TIER_MARKS = ["", "·", "··", "···", "····", "·····"];

function layerKey(index: number): string {
  return `layer-${index}`;
}

function patchForProduct(product: GlassProductChoice, current: GlazingValue): GlazingPatch {
  const composition = (product.composition as GlassCompositionSpec | null) ?? null;
  const total = product.total_thickness_mm
    ? Number(product.total_thickness_mm)
    : composition
      ? compositionTotalMm(composition)
      : null;
  return {
    glass_article_sku: product.sku,
    glass_spec:
      product.notation ??
      (composition ? compositionNotation(composition) : (current.glass_spec ?? null)),
    glass_thickness_mm: total != null ? String(total) : (current.glass_thickness_mm ?? null),
    glass_composition: composition,
    glass_options: retargetSurcharges(current.glass_options, product),
  };
}

/* ---------- product card ---------- */

function ProductCard({
  product,
  active,
  incompatible,
  busy,
  isFavorite,
  onPick,
  onToggleFavorite,
}: {
  product: GlassProductChoice;
  active: boolean;
  incompatible: boolean;
  busy: boolean;
  isFavorite: boolean;
  onPick(): void;
  onToggleFavorite(sku: string): void;
}): JSX.Element {
  const tier = product.price_tier ?? null;
  const unknown = product.composition == null || product.review_pending;
  return (
    <li
      className={`glass-card${active ? " is-active" : ""}${incompatible ? " is-incompatible" : ""}`}
    >
      <button
        type="button"
        className="glass-card__body"
        disabled={busy}
        aria-pressed={active}
        aria-label={product.name}
        onClick={onPick}
      >
        <span className="glass-card__name">
          {product.name}
          <span className="glass-card__sku">{product.sku}</span>
        </span>
        {product.notation ? (
          <span className="glass-card__notation">{product.notation}</span>
        ) : (
          <span className="glass-card__notation is-unknown">
            {t("assembly.glassNoComposition")}
          </span>
        )}
        <span className="glass-card__stats">
          <span>{product.total_thickness_mm ? `${product.total_thickness_mm} mm` : "—"}</span>
          <span>{product.weight_kg_m2 ? `${product.weight_kg_m2} kg/m²` : t("ui.noData")}</span>
          {tier != null && (
            <span
              className="glass-card__tier"
              title={t("assembly.glassPriceTier")}
              aria-label={`${t("assembly.glassPriceTier")}: ${tier}/5`}
            >
              {t("assembly.glassPriceMark")}
              {PRICE_TIER_MARKS[tier] ?? tier}
            </span>
          )}
        </span>
        <span className="glass-card__flags">
          {product.safety_class && (
            <span className="glass-card__flag">
              {t("assembly.glassSafetyClass").replace("{cls}", product.safety_class)}
            </span>
          )}
          {product.ug_w_m2k && <span className="glass-card__flag">U {product.ug_w_m2k}</span>}
          {product.g_value && <span className="glass-card__flag">g {product.g_value}</span>}
          {unknown && (
            <span className="glass-card__flag is-warn">
              <Icon name="warn" size={11} /> {t("assembly.glassPendingReview")}
            </span>
          )}
          {incompatible && (
            <span className="glass-card__flag is-warn">
              <Icon name="warn" size={11} /> {t("assembly.glassNoBead")}
            </span>
          )}
        </span>
      </button>
      <button
        type="button"
        className={`star-toggle glass-card__star${isFavorite ? " is-active" : ""}`}
        aria-label={t("assembly.favoriteGlass")}
        aria-pressed={isFavorite}
        disabled={busy}
        onClick={() => onToggleFavorite(product.sku)}
      >
        <Icon name="star" size={13} />
      </button>
    </li>
  );
}

/* ---------- composer ---------- */

function LayerEditor({
  layer,
  index,
  busy,
  onChange,
  onRemove,
}: {
  layer: GlassLaminaSpec | GlassChamberSpec;
  index: number;
  busy: boolean;
  onChange(layer: GlassLaminaSpec | GlassChamberSpec): void;
  onRemove?(): void;
}): JSX.Element {
  if (layer.type === "chamber") {
    return (
      <li className="glass-layer glass-layer--chamber" key={layerKey(index)}>
        <span className="glass-layer__role">
          {index === 1 ? t("assembly.glassChamber") : `${t("assembly.glassChamber")} ${index}`}
        </span>
        <select
          aria-label={t("assembly.glassChamberWidth")}
          disabled={busy}
          value={layer.width_mm}
          onChange={(event) => onChange({ ...layer, width_mm: event.target.value })}
        >
          {CHAMBER_WIDTHS_MM.map((mm) => (
            <option key={mm} value={String(mm)}>
              {mm} mm
            </option>
          ))}
        </select>
        <select
          aria-label={t("assembly.glassGas")}
          disabled={busy}
          value={layer.gas ?? "AIR"}
          onChange={(event) => onChange({ ...layer, gas: event.target.value })}
        >
          <option value="AIR">{t("assembly.gasAir")}</option>
          <option value="ARGON">{t("assembly.gasArgon")}</option>
        </select>
        <select
          aria-label={t("assembly.glassSpacer")}
          disabled={busy}
          value={layer.spacer ?? "ALUMINIUM"}
          onChange={(event) => onChange({ ...layer, spacer: event.target.value })}
        >
          <option value="ALUMINIUM">{t("assembly.spacerAluminium")}</option>
          <option value="WARM_EDGE">{t("assembly.spacerWarmEdge")}</option>
        </select>
        {onRemove && (
          <button
            type="button"
            className="ghost-button"
            aria-label={t("assembly.glassRemoveChamber")}
            title={t("assembly.glassRemoveChamber")}
            disabled={busy}
            onClick={onRemove}
          >
            <Icon name="minus" size={12} />
          </button>
        )}
      </li>
    );
  }
  const lamina = layer;
  const laminated = lamina.panes.length > 1;
  return (
    <li className="glass-layer" key={layerKey(index)}>
      <span className="glass-layer__role">
        {index === 0 ? t("assembly.glassOuter") : t("assembly.glassInner")}
      </span>
      <span className="glass-layer__panes">
        {lamina.panes.map((pane, paneIndex) => (
          <span className="glass-layer__pane" key={paneIndex}>
            <select
              aria-label={
                paneIndex === 0
                  ? `${t("assembly.glassThickness")} ${t("assembly.glassOuter")}`
                  : `${t("assembly.glassThickness")} ${paneIndex + 1}`
              }
              disabled={busy}
              value={pane}
              onChange={(event) => {
                const panes = [...lamina.panes];
                panes[paneIndex] = event.target.value;
                onChange({ ...lamina, panes });
              }}
            >
              {LAMINA_THICKNESSES_MM.map((mm) => (
                <option key={mm} value={String(mm)}>
                  {mm}
                </option>
              ))}
            </select>
            {paneIndex > 0 && (
              <button
                type="button"
                className="ghost-button"
                aria-label={t("assembly.glassRemovePane")}
                title={t("assembly.glassRemovePane")}
                disabled={busy}
                onClick={() =>
                  onChange({
                    ...lamina,
                    panes: lamina.panes.filter((_, at) => at !== paneIndex),
                    interlayer: lamina.panes.length <= 2 ? null : (lamina.interlayer ?? null),
                  })
                }
              >
                ×
              </button>
            )}
          </span>
        ))}
        <button
          type="button"
          className="ghost-button"
          title={t("assembly.glassLaminate")}
          aria-label={t("assembly.glassLaminate")}
          aria-pressed={laminated}
          disabled={busy}
          onClick={() =>
            onChange(
              laminated
                ? { ...lamina, panes: [lamina.panes[0] ?? "4"], interlayer: null }
                : {
                    ...lamina,
                    panes: [...lamina.panes, lamina.panes[0] ?? "4"],
                    interlayer: lamina.interlayer ?? "PVB_038",
                  },
            )
          }
        >
          {t("assembly.glassLaminate")}
        </button>
      </span>
      {laminated && (
        <select
          aria-label={t("assembly.glassInterlayer")}
          disabled={busy}
          value={lamina.interlayer ?? "PVB_038"}
          onChange={(event) => onChange({ ...lamina, interlayer: event.target.value })}
        >
          {INTERLAYERS.map((kind) => (
            <option key={kind} value={kind}>
              {kind === "PVB_ACOUSTIC" ? "PVB acústico" : kind.replace("_", " 0,")}
            </option>
          ))}
        </select>
      )}
      <select
        aria-label={t("assembly.glassTint")}
        disabled={busy}
        value={lamina.tint ?? "CLEAR"}
        onChange={(event) => onChange({ ...lamina, tint: event.target.value })}
      >
        <option value="CLEAR">{t("assembly.tintClear")}</option>
        <option value="BRONZE">{t("assembly.tintBronze")}</option>
        <option value="GREY">{t("assembly.tintGrey")}</option>
        <option value="GREEN">{t("assembly.tintGreen")}</option>
      </select>
      <select
        aria-label={t("assembly.glassTreatment")}
        disabled={busy}
        value={lamina.treatment ?? ""}
        onChange={(event) => onChange({ ...lamina, treatment: event.target.value || null })}
      >
        <option value="">{t("assembly.treatmentRaw")}</option>
        <option value="TEMPERED">{t("assembly.treatmentTempered")}</option>
        <option value="HEAT_STRENGTHENED">{t("assembly.treatmentHeatStrengthened")}</option>
      </select>
      <select
        aria-label={t("assembly.glassCoating")}
        disabled={busy}
        value={lamina.coating ?? ""}
        onChange={(event) =>
          onChange({
            ...lamina,
            coating: event.target.value || null,
            coating_face:
              event.target.value && event.target.value !== ""
                ? (lamina.coating_face ?? (index === 0 ? 2 : 3))
                : null,
          })
        }
      >
        <option value="">{t("assembly.coatingNone")}</option>
        {COATINGS.map((coating) => (
          <option key={coating} value={coating}>
            {t(`assembly.coating.${coating}` as TranslationKey)}
          </option>
        ))}
      </select>
    </li>
  );
}

/** The termopanel section, drawn to scale: lamina bands proportional to
 * their declared mm, chambers tinted. Exterior left, interior right. */
function CompositionSection({ composition }: { composition: GlassCompositionSpec }): JSX.Element {
  const total = compositionTotalMm(composition);
  const pxPerMm = total > 0 ? Math.min(9, 190 / total) : 9;
  const height = 120;
  let cursor = 10;
  return (
    <svg
      className="glass-section"
      viewBox={`0 0 ${20 + total * pxPerMm} ${height}`}
      role="img"
      aria-label={t("assembly.glassSectionView")}
    >
      <text x={4} y={height / 2} className="glass-section__side">
        {t("assembly.glassOutside")}
      </text>
      <text
        x={16 + total * pxPerMm}
        y={height / 2}
        className="glass-section__side"
        textAnchor="end"
      >
        {t("assembly.glassInside")}
      </text>
      {composition.layers.map((layer, index) => {
        const w =
          (layer.type === "lamina"
            ? layer.panes.reduce((sum, pane) => sum + mmNumber(pane), 0) +
              (layer.interlayer ? 0.38 : 0)
            : mmNumber(layer.width_mm)) * pxPerMm;
        const node =
          layer.type === "lamina" ? (
            <g key={layerKey(index)}>
              {(() => {
                const paneW = w / layer.panes.length;
                return layer.panes.map((_pane, paneIndex) => {
                  const tintClass =
                    layer.tint && layer.tint !== "CLEAR"
                      ? ` glass-layer-svg--${layer.tint.toLowerCase()}`
                      : "";
                  return (
                    <rect
                      key={paneIndex}
                      className={`glass-layer-svg__pane${tintClass}`}
                      x={cursor + paneIndex * paneW}
                      y={12}
                      width={paneW}
                      height={height - 24}
                    />
                  );
                });
              })()}
              <text
                x={cursor + w / 2}
                y={height - 2}
                className="glass-section__label"
                textAnchor="middle"
              >
                {layer.panes.join("+")}
              </text>
            </g>
          ) : (
            <g key={layerKey(index)}>
              <rect
                className="glass-layer-svg__chamber"
                x={cursor}
                y={12}
                width={w}
                height={height - 24}
              />
              <rect
                className="glass-layer-svg__spacer"
                x={cursor}
                y={height - 20}
                width={w}
                height={8}
              />
              <text
                x={cursor + w / 2}
                y={height - 2}
                className="glass-section__label"
                textAnchor="middle"
              >
                {fmtSectionMm(layer.width_mm)}
              </text>
            </g>
          );
        cursor += w;
        return node;
      })}
    </svg>
  );
}

function fmtSectionMm(raw: string): string {
  return `${String(raw).replace(".", ",")} mm`;
}

/* ---------- surcharges ---------- */

function SurchargeRow({
  kind,
  rate,
  selection,
  busy,
  onChange,
}: {
  kind: string;
  rate: { kind: string; unit: string; amount: string; label: string | null };
  selection: GlassSurchargeSelectionSpec | undefined;
  busy: boolean;
  onChange(selection: GlassSurchargeSelectionSpec | null): void;
}): JSX.Element {
  const selected = selection != null;
  const set = (patch: Partial<GlassSurchargeSelectionSpec>) =>
    onChange({ ...(selection ?? emptySelection(kind)), ...patch });
  return (
    <div className="glass-surcharge">
      <label className="assembly-field--inline">
        <input
          type="checkbox"
          checked={selected}
          disabled={busy}
          onChange={(event) => onChange(event.target.checked ? emptySelection(kind) : null)}
          aria-label={rate.label ?? kind}
        />
        <span>
          {rate.label ?? t(`assembly.surcharge.${kind}` as TranslationKey)}
          <small>
            {" "}
            · {rate.amount}/{rate.unit === "CROSS" ? t("assembly.surchargeCross") : rate.unit}
          </small>
        </span>
      </label>
      {selected && kind === "EDGE_POLISH" && (
        <span
          className="glass-surcharge__edges"
          role="group"
          aria-label={t("assembly.surchargeEdges")}
        >
          {(["top", "right", "bottom", "left"] as const).map((edge) => {
            const edges = selection?.edges ?? [];
            const active = edges.includes(edge);
            return (
              <button
                key={edge}
                type="button"
                className={`recents__chip${active ? " is-active" : ""}`}
                aria-pressed={active}
                disabled={busy}
                onClick={() =>
                  set({
                    edges: active ? edges.filter((item) => item !== edge) : [...edges, edge],
                  })
                }
              >
                {t(`assembly.edge.${edge}` as TranslationKey)}
              </button>
            );
          })}
        </span>
      )}
      {selected && kind === "DRILL" && (
        <span className="glass-surcharge__count">
          <input
            type="number"
            min={1}
            max={20}
            aria-label={t("assembly.surchargeDrillCount")}
            disabled={busy}
            value={selection?.count ?? 1}
            onChange={(event) => set({ count: Math.max(1, Number(event.target.value) || 1) })}
          />
        </span>
      )}
      {selected && kind === "PALILLAJE" && (
        <span className="glass-surcharge__grid">
          <input
            type="number"
            min={1}
            max={12}
            aria-label={t("assembly.surchargeColumns")}
            disabled={busy}
            value={selection?.columns ?? 2}
            onChange={(event) => set({ columns: Math.max(1, Number(event.target.value) || 1) })}
          />
          ×
          <input
            type="number"
            min={1}
            max={12}
            aria-label={t("assembly.surchargeRows")}
            disabled={busy}
            value={selection?.rows ?? 2}
            onChange={(event) => set({ rows: Math.max(1, Number(event.target.value) || 1) })}
          />
        </span>
      )}
    </div>
  );
}

/* ---------- main component ---------- */

export function GlazingPicker({
  value,
  products,
  glazingThicknesses,
  findings,
  busy,
  favoriteGlass,
  recentGlass,
  onPick,
  onToggleFavorite,
}: {
  value: GlazingValue;
  products: GlassProductChoice[];
  glazingThicknesses: string[];
  /** Engine findings already resolved for this bay — shown verbatim with
   * their source reference; a compatible product row carries the
   * one-click fix. */
  findings: GlassSafetyFinding[];
  busy: boolean;
  favoriteGlass: string[];
  recentGlass: string[];
  onPick(patch: GlazingPatch): void;
  onToggleFavorite(sku: string): void;
}): JSX.Element {
  const [mode, setMode] = useState<"basic" | "advanced">("basic");
  const supportedThicknesses = useMemo(
    () => new Set(glazingThicknesses.map((thickness) => Number(thickness))),
    [glazingThicknesses],
  );
  const selectedProduct = products.find((product) => product.sku === value.glass_article_sku);
  const composition = value.glass_composition ?? null;
  const errors = compositionErrors(composition);
  const requiredSafety =
    findings.find((finding) => finding.severity === "MANDATORY")?.required_safety ??
    findings.find((finding) => finding.required_safety != null)?.required_safety ??
    null;
  const compatibleAlternatives = useMemo(
    () =>
      requiredSafety
        ? products.filter(
            (product) =>
              product.sku !== value.glass_article_sku &&
              productSatisfiesSafety(product, requiredSafety),
          )
        : [],
    [products, requiredSafety, value.glass_article_sku],
  );

  function applyComposition(next: GlassCompositionSpec): void {
    const total = compositionTotalMm(next);
    // A hand-composed stack that matches a catalog product's sealed
    // composition adopts that product (and its surcharge scope); anything
    // else stays a custom stack with no article attached.
    const matchedProduct =
      products.find(
        (product) => product.composition && compositionsEqual(next, product.composition),
      ) ?? null;
    onPick({
      glass_composition: next,
      glass_spec: errors.length === 0 ? compositionNotation(next) : (value.glass_spec ?? null),
      glass_thickness_mm: quantize(String(Math.round(total * 100) / 100), 2),
      glass_article_sku: matchedProduct?.sku ?? null,
      glass_options: retargetSurcharges(value.glass_options, matchedProduct),
    });
  }

  function setSurcharge(kind: string, selection: GlassSurchargeSelectionSpec | null): void {
    const selections = (value.glass_options?.surcharges ?? []).filter((item) => item.kind !== kind);
    if (selection) {
      selections.push(selection);
    }
    onPick({
      glass_options: selections.length === 0 ? null : { surcharges: selections },
    });
  }

  return (
    <div className="glazing-picker">
      <SegmentedControl
        options={[
          { value: "basic", label: t("assembly.glassModeBasic") },
          { value: "advanced", label: t("assembly.glassModeAdvanced") },
        ]}
        value={mode}
        onValueChange={setMode}
      />
      {findings.length > 0 && (
        <ul className="glass-findings" role="list">
          {findings.map((finding, index) => (
            <li
              key={`${finding.rule_code}-${index}`}
              className={`glass-finding glass-finding--${finding.severity === "MANDATORY" ? "mandatory" : "warning"}`}
            >
              <Icon name="warn" size={13} />
              <span>
                {finding.message}
                {finding.source_ref && (
                  <small className="glass-finding__source"> — {finding.source_ref}</small>
                )}
              </span>
            </li>
          ))}
          {requiredSafety && compatibleAlternatives.length > 0 && (
            <li className="glass-finding glass-finding--fix">
              <span>{t("assembly.glassSafetyFix")}</span>
              {compatibleAlternatives.slice(0, 3).map((product) => (
                <button
                  key={product.sku}
                  type="button"
                  className="recents__chip"
                  disabled={busy}
                  onClick={() => onPick(patchForProduct(product, value))}
                >
                  {product.name}
                </button>
              ))}
            </li>
          )}
        </ul>
      )}
      {mode === "basic" ? (
        <ul className="glass-cards" role="list">
          <li className={`glass-card${value.glass_article_sku == null ? " is-active" : ""}`}>
            <button
              type="button"
              className="glass-card__body"
              disabled={busy}
              aria-pressed={value.glass_article_sku == null}
              onClick={() => onPick({ glass_article_sku: null })}
            >
              <span className="glass-card__name">{t("assembly.noGlassProduct")}</span>
              <span className="glass-card__notation is-unknown">
                {value.glass_spec ?? t("assembly.glassFreeSpec")}
              </span>
            </button>
          </li>
          {products.map((product) => {
            const total = product.total_thickness_mm
              ? Number(product.total_thickness_mm)
              : product.composition
                ? compositionTotalMm(product.composition as GlassCompositionSpec)
                : null;
            const incompatible =
              supportedThicknesses.size > 0 && total != null && !supportedThicknesses.has(total);
            return (
              <ProductCard
                key={product.sku}
                product={product}
                active={product.sku === value.glass_article_sku}
                incompatible={incompatible}
                busy={busy}
                isFavorite={favoriteGlass.includes(product.sku)}
                onPick={() => onPick(patchForProduct(product, value))}
                onToggleFavorite={onToggleFavorite}
              />
            );
          })}
        </ul>
      ) : (
        <div className="glass-composer">
          <CompositionSection composition={composition ?? defaultComposition()} />
          <ul className="glass-composer__layers" role="list">
            {(composition ?? defaultComposition()).layers.map((layer, index) => (
              <LayerEditor
                key={layerKey(index)}
                layer={layer}
                index={index}
                busy={busy}
                onChange={(next) => {
                  const layers = [...(composition ?? defaultComposition()).layers];
                  layers[index] = next;
                  applyComposition({ layers });
                }}
                onRemove={
                  layer.type === "chamber"
                    ? () => {
                        () => {
                          const layers = (composition ?? defaultComposition()).layers;
                          // Removing a chamber also removes the lamina that
                          // follows it — the stack keeps exterior→interior
                          // alternation (outer lamina always stays).
                          applyComposition({
                            layers: layers.filter((_, at) => at !== index && at !== index + 1),
                          });
                        };
                      }
                    : undefined
                }
              />
            ))}
          </ul>
          <div className="inspector-actions">
            <button
              type="button"
              className="ghost-button"
              disabled={busy || (composition?.layers.length ?? 0) >= 5}
              onClick={() => {
                const layers = [...(composition ?? defaultComposition()).layers];
                // New cavity + ply before the last (innermost) lamina —
                // the stack always starts and ends on a lamina.
                layers.splice(
                  layers.length - 1,
                  0,
                  { type: "chamber", width_mm: "12", gas: "AIR", spacer: "ALUMINIUM" },
                  { type: "lamina", panes: ["4"], tint: "CLEAR" },
                );
                applyComposition({ layers });
              }}
            >
              {t("assembly.glassAddChamber")}
            </button>
          </div>
          <p className="assembly-hint glass-composer__summary">
            {t("assembly.glassNotation")}: {composition ? compositionNotation(composition) : "—"} ·{" "}
            {t("assembly.glassTotal")}:{" "}
            {composition ? `${compositionTotalMm(composition)} mm` : "—"} · {t("assembly.glassNet")}
            : {composition ? `${compositionNetMm(composition)} mm` : "—"}
          </p>
          {errors.length > 0 && (
            <ul className="glass-findings" role="list">
              {errors.map((error) => (
                <li key={error} className="glass-finding glass-finding--mandatory">
                  <Icon name="warn" size={13} /> {t(error as TranslationKey)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {recentGlass.some((sku) => products.some((product) => product.sku === sku)) && (
        <div className="recents" aria-label={t("assembly.recentGlass")}>
          <span className="recents__label">{t("assembly.recentGlass")}</span>
          {recentGlass
            .filter((sku) => sku !== value.glass_article_sku)
            .map((sku) => {
              const product = products.find((item) => item.sku === sku);
              return product ? (
                <button
                  key={sku}
                  type="button"
                  className="recents__chip"
                  disabled={busy}
                  title={product.name}
                  onClick={() => onPick(patchForProduct(product, value))}
                >
                  {product.notation ?? sku}
                </button>
              ) : null;
            })}
        </div>
      )}
      {favoriteGlass.some((sku) => products.some((product) => product.sku === sku)) && (
        <div className="recents" aria-label={t("assembly.favoriteGlass")}>
          <span className="recents__label">{t("assembly.favoriteGlass")}</span>
          {favoriteGlass
            .filter((sku) => sku !== value.glass_article_sku)
            .map((sku) => {
              const product = products.find((item) => item.sku === sku);
              return product ? (
                <button
                  key={sku}
                  type="button"
                  className="recents__chip recents__chip--favorite"
                  disabled={busy}
                  title={product.name}
                  onClick={() => onPick(patchForProduct(product, value))}
                >
                  {product.notation ?? sku}
                </button>
              ) : null;
            })}
        </div>
      )}
      {selectedProduct && selectedProduct.surcharges.length > 0 && (
        <div className="glass-surcharges">
          <span className="assembly-field__label">{t("assembly.glassSurcharges")}</span>
          {selectedProduct.surcharges.map((rate) => (
            <SurchargeRow
              key={rate.kind}
              kind={rate.kind}
              rate={rate}
              busy={busy}
              selection={(value.glass_options?.surcharges ?? []).find(
                (item) => item.kind === rate.kind,
              )}
              onChange={(selection) => setSurcharge(rate.kind, selection)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Structural equality between a composed stack and a product's declared
 * composition — shallow per layer, enough for "still the same product". */
function compositionsEqual(a: GlassCompositionSpec, b: unknown): boolean {
  const bLayers = (b as GlassCompositionSpec | null)?.layers;
  if (!Array.isArray(bLayers) || bLayers.length !== a.layers.length) return false;
  return a.layers.every((layer, index) => {
    const other = bLayers[index] as GlassLaminaSpec | GlassChamberSpec;
    if (layer.type !== other?.type) return false;
    if (layer.type === "lamina") {
      const lamina = other as GlassLaminaSpec;
      return (
        layer.panes.join("|") === lamina.panes.join("|") &&
        (layer.interlayer ?? null) === (lamina.interlayer ?? null) &&
        (layer.treatment ?? null) === (lamina.treatment ?? null) &&
        (layer.coating ?? null) === (lamina.coating ?? null) &&
        (layer.tint ?? "CLEAR") === (lamina.tint ?? "CLEAR")
      );
    }
    const chamber = other as GlassChamberSpec;
    return (
      mmNumber(layer.width_mm) === mmNumber(chamber.width_mm) &&
      (layer.gas ?? "AIR") === (chamber.gas ?? "AIR") &&
      (layer.spacer ?? "ALUMINIUM") === (chamber.spacer ?? "ALUMINIUM")
    );
  });
}
