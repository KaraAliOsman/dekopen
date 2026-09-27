import { fmtMm } from "../../format";
import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import "./canvas.css";

import type {
  DesignOptions,
  EngineAssemblyCalculateResponse,
  GlassSpecChoice,
  ProductIssue,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import {
  formatShortcut,
  resolveCommands,
  useCommandShortcuts,
  useRegisterCommands,
} from "../commands/registry";
import type { CommandContext, EditorTool } from "../commands/types";
import { useCanvasStore } from "./canvasStore";
import { assemblyCommands } from "./assemblyCommands";
import { AlternativesPanel } from "./AlternativesPanel";
import { AssistantPanel } from "./AssistantPanel";
import { applyDesignOps } from "./designOps";
import { useRegisterDesignOpsBridge } from "../assistant/assistantContext";
import type { DesignOp } from "../commands/types";
import { BowPlanContent, planBounds } from "./BowPlanSvg";
import { CanvasViewport } from "./CanvasViewport";
import { ObjectTree } from "./ObjectTree";
import { buildObjectTree } from "./objectTree";
import { resolveMembers, type MemberGeometry } from "./members";
import { SectionView } from "./SectionView";
import { SectionPreviewSvg } from "./SectionPreviewSvg";
import {
  frontBounds,
  frontLayout,
  frontModuleBox,
  OpeningGlyph,
  ProductFrontContent,
} from "./ProductFrontSvg";

import { useAssemblyCalculation } from "./useAssemblyCalculation";
import type { IntentNode, Opening, SlidingLayout, SplitType } from "./intentEditing";
import {
  findNode,
  intentBays,
  isSlidingOpening,
  resolvedSlidingLayout,
  topIntent,
  updateBay,
  SLIDING_PRESETS,
} from "./intentEditing";
import {
  addAdjacentUnit,
  canRemoveModuleDivision,
  equalizeCouplingAngles,
  equalizeModuleWidths,
  moduleGlassSku,
  moduleGlassThicknessMm,
  moduleOpening,
  modulePanelSku,
  modulePrimaryBay,
  moveModuleDivision,
  removeModuleDivision,
  removeUnit,
  resizeModuleSeam,
  scaleModuleWidths,
  contourTopCorners,
  setAllModuleHeights,
  setContourBulge,
  setContourVertex,
  setModuleGlass,
  setModuleGlassThickness,
  setModulePanel,
  setCouplerSku,
  setCouplingAngle,
  setModuleOpening,
  setModuleSlidingLayout,
  setModuleTree,
  setModuleWidth,
  setModuleFrameless,
  splitModuleBay,
  type CouplingJson,
  type FramelessEdge,
  type FramelessFittingJson,
  type FramelessSpecJson,
  type FramelessSupportJson,
  type ProductJson,
  type ProductModuleJson,
} from "./productEditing";
import { OPENING_OPTIONS } from "./openings";

/** §16 3D view: three.js + the scene builder stay out of the editing path —
 * the bundle only loads when the user opens the panel (lazy chunk), and
 * frameloop="demand" keeps it idle between interactions. */
const Model3DView = lazy(() => import("./Model3DView"));

const ISSUE_KEYS: Record<string, TranslationKey> = {
  couplings_count_mismatch: "assembly.issue.couplingsCountMismatch",
  assembly_folds_back: "assembly.issue.assemblyFoldsBack",
  plan_self_intersection: "assembly.issue.planSelfIntersection",
  module_geometry_failed: "assembly.issue.moduleGeometryFailed",
  coupler_profile_missing: "assembly.issue.couplerProfileMissing",
  coupler_profile_unknown: "assembly.issue.couplerProfileUnknown",
  coupler_height_mismatch: "assembly.issue.couplerHeightMismatch",
  coupler_reinforcement_nonpositive: "assembly.issue.couplerReinforcementNonpositive",
  contour_invalid: "assembly.issue.contourInvalid",
  contour_splits_unsupported: "assembly.issue.contourSplits",
  contour_opening_unsupported: "assembly.issue.contourOpening",
  contour_panel_unsupported: "assembly.issue.contourPanel",
  contour_coupling_unsupported: "assembly.issue.contourCoupling",
  member_bending_required: "assembly.issue.memberBending",
  coupler_width_mismatch: "assembly.issue.couplerWidthMismatch",
  coupler_module_unknown: "assembly.issue.couplerModuleUnknown",
  coupler_edge_invalid: "assembly.issue.couplerEdgeInvalid",
  coupler_edge_conflict: "assembly.issue.couplerEdgeConflict",
  connection_type_unsupported: "assembly.issue.connectionTypeUnsupported",
  assembly_disconnected: "assembly.issue.assemblyDisconnected",
  stacked_cycle: "assembly.issue.stackedCycle",
  inline_not_adjacent: "assembly.issue.inlineNotAdjacent",
  sliding_layout_invalid: "assembly.issue.slidingLayoutInvalid",
  sliding_tracks_unsupported: "assembly.issue.slidingTracksUnsupported",
  frameless_contour_unsupported: "assembly.issue.framelessContour",
  frameless_splits_unsupported: "assembly.issue.framelessSplits",
  frameless_opening_unsupported: "assembly.issue.framelessOpening",
  frameless_panel_unsupported: "assembly.issue.framelessPanel",
  frameless_article_unknown: "assembly.issue.framelessArticleUnknown",
};

/** Engine failure reasons arrive as `str(error)` — member ids and field
 * names never reach the user; each known cause maps to a readable phrase
 * and anything unrecognized degrades to a generic sentence. */
export const REASON_KEYS: [RegExp, TranslationKey][] = [
  [/requires glass_thickness_mm and glass_spec/i, "assembly.reason.glassRequired"],
  [/requires opening_type/i, "assembly.reason.openingRequired"],
  [/requires panel_article_sku/i, "assembly.reason.panelRequired"],
  [/requires split offset and mullion sku/i, "assembly.reason.splitMullionRequired"],
  [/requires at least two modules/i, "assembly.reason.bowTwoModules"],
  [/requires at least one module/i, "assembly.reason.oneModule"],
  [/requires a top-level bay/i, "assembly.reason.doorNeedsBay"],
  [/requires an opening type/i, "assembly.reason.openingRequired"],
  [/zero-length segment/i, "assembly.reason.contourDegenerate"],
  [/sagitta exceeds/i, "assembly.reason.contourSagitta"],
  [/self-intersect/i, "assembly.reason.contourSelfIntersect"],
  [/requires a sliding_layout/i, "assembly.reason.slidingLayoutRequired"],
  [/not a sliding opening/i, "assembly.reason.slidingLayoutRequired"],
  [/duplicate panel slot/i, "assembly.reason.slidingDuplicateSlot"],
  [/undeclared track/i, "assembly.reason.slidingBadTrack"],
  [/cannot occupy a track/i, "assembly.reason.slidingFixedTrack"],
  [/adjacent fixed panels/i, "assembly.reason.slidingFixedAdjacent"],
  [/cannot share a track/i, "assembly.reason.slidingSameTrack"],
  [/at least one moving panel/i, "assembly.reason.slidingNoMoving"],
];

export function issueText(
  issue: ProductIssue,
  modules: ProductModuleJson[],
  couplings: CouplingJson[],
): string {
  const key = ISSUE_KEYS[issue.code];
  // Unmapped engine codes still read as sentences — a chip that shows
  // "R02_LEAF_PROPORTION" asks the user to decode our own identifier.
  let text = key ? t(key) : issue.code.toLowerCase().replace(/_/g, " ");
  for (const [name, value] of Object.entries(issue.params)) {
    if (name === "reason") continue;
    text = text.replace(`{${name}}`, value);
  }
  const [kind, id] = issue.target.split(":", 2);
  const ordinal =
    kind === "module"
      ? modules.findIndex((item) => item.id === id)
      : kind === "coupling"
        ? couplings.findIndex((item) => item.id === id)
        : -1;
  const noun =
    kind === "coupling"
      ? `la ${t("assembly.coupling").toLowerCase()}`
      : `el ${t("assembly.module").toLowerCase()}`;
  const target =
    ordinal >= 0
      ? `${noun} ${ordinal + 1}`
      : kind === "assembly"
        ? t("assembly.wholeAssembly")
        : noun;
  text = text.replace("{target}", target);
  const reason = issue.params["reason"];
  if (reason && !text.includes(reason)) {
    const matched = REASON_KEYS.find(([pattern]) => pattern.test(reason));
    text += ` — ${matched ? t(matched[1]) : t("assembly.reason.generic")}`;
  }
  return text;
}

function normalizeMm(candidate: string): string | null {
  const value = Number(candidate.replace(",", "."));
  if (!Number.isFinite(value) || value <= 0) return null;
  return value.toFixed(2);
}

function normalizeAngle(candidate: string): string | null {
  const value = Number(candidate.replace(",", "."));
  if (!Number.isFinite(value) || Math.abs(value) >= 90) return null;
  return value.toFixed(1);
}

/** Contour coordinates are signed: zero/negative carry meaning (a vertical
 * side, an inward arc). Bounds keep the corner ordering the engine requires. */
function normalizeRange(candidate: string, min: number, max: number): string | null {
  const value = Number(candidate.replace(",", "."));
  if (!Number.isFinite(value) || value < min || value >= max) return null;
  return value.toFixed(2);
}

type DraftFieldProps = {
  label?: string;
  value: string;
  unit: string;
  disabled: boolean;
  onCommit(value: string): void;
  normalize(candidate: string): string | null;
};

function DraftField({
  label,
  value,
  unit,
  disabled,
  onCommit,
  normalize,
}: DraftFieldProps): JSX.Element {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <label className="assembly-field">
      {label ? <span>{label}</span> : null}
      <input
        value={draft}
        disabled={disabled}
        inputMode="decimal"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const normalized = normalize(draft);
          if (normalized === null) setDraft(value);
          else if (normalized !== value) onCommit(normalized);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") setDraft(value);
        }}
      />
      <span className="assembly-unit">{unit}</span>
    </label>
  );
}

function statusKey(status: string | undefined): TranslationKey {
  if (status === "VALID") return "assembly.statusValid";
  if (status === "MANUFACTURING_INCOMPLETE") return "assembly.statusIncomplete";
  return "assembly.statusInvalid";
}

/** Editable semantic fields of a contour outline: the two top-corner
 * offsets for a straight chord, plus one rise per bulged edge. Free-form
 * outlines expose a vertex count until the polygon editor lands. */
function ContourShapeSection({
  module,
  product,
  busy,
  commit,
}: {
  module: ProductModuleJson;
  product: ProductJson;
  busy: boolean;
  commit(next: ProductJson): void;
}): JSX.Element {
  const contour = module.contour!;
  const corners = contourTopCorners(contour);
  const hasBulges = contour.bulges.some((bulge) => bulge !== null && bulge !== undefined);
  const widthMm = Number(module.width_mm);
  const leftBound = corners ? Number(contour.vertices[corners.rightIndex]!.x_mm) : 0;
  const rightBound = corners ? widthMm - Number(contour.vertices[corners.leftIndex]!.x_mm) : 0;
  // Sagitta is signed and bounded by half the chord (minor arcs only);
  // zero straightens the edge back to a line.
  const edgeChordMm = (edgeIndex: number): number => {
    const n = contour.vertices.length;
    const a = contour.vertices[edgeIndex % n]!;
    const b = contour.vertices[(edgeIndex + 1) % n]!;
    return Math.hypot(Number(b.x_mm) - Number(a.x_mm), Number(b.y_mm) - Number(a.y_mm));
  };
  return (
    <details className="inspector-section" open>
      <summary>{t("assembly.shape")}</summary>
      {corners && !hasBulges && (
        <>
          <DraftField
            label={t("assembly.shapeOffsetLeft")}
            value={Number(contour.vertices[corners.leftIndex]!.x_mm).toFixed(2)}
            unit="mm"
            disabled={busy}
            normalize={(candidate) => normalizeRange(candidate, 0, leftBound)}
            onCommit={(value) =>
              commit(
                setContourVertex(
                  product,
                  module.id,
                  corners.leftIndex,
                  value,
                  contour.vertices[corners.leftIndex]!.y_mm,
                ),
              )
            }
          />
          <DraftField
            label={t("assembly.shapeOffsetRight")}
            value={(widthMm - Number(contour.vertices[corners.rightIndex]!.x_mm)).toFixed(2)}
            unit="mm"
            disabled={busy}
            normalize={(candidate) => normalizeRange(candidate, 0, rightBound)}
            onCommit={(value) =>
              commit(
                setContourVertex(
                  product,
                  module.id,
                  corners.rightIndex,
                  (widthMm - Number(value)).toFixed(2),
                  contour.vertices[corners.rightIndex]!.y_mm,
                ),
              )
            }
          />
        </>
      )}
      {contour.bulges.map(
        (bulge, edgeIndex) =>
          bulge !== null &&
          bulge !== undefined && (
            <DraftField
              key={edgeIndex}
              label={t("assembly.shapeRise")}
              value={bulge}
              unit="mm"
              disabled={busy}
              normalize={(candidate) =>
                normalizeRange(
                  candidate,
                  -edgeChordMm(edgeIndex) / 2,
                  edgeChordMm(edgeIndex) / 2 + 0.01,
                )
              }
              onCommit={(value) => commit(setContourBulge(product, module.id, edgeIndex, value))}
            />
          ),
      )}
      {!corners && !hasBulges && (
        <p className="inspector-note">
          {t("assembly.shapeVertices").replace("{count}", String(contour.vertices.length))}
        </p>
      )}
    </details>
  );
}

const FRAMELESS_EDGES: [FramelessEdge, TranslationKey][] = [
  ["bottom", "assembly.framelessEdgeBottom"],
  ["top", "assembly.framelessEdgeTop"],
  ["left", "assembly.framelessEdgeLeft"],
  ["right", "assembly.framelessEdgeRight"],
];
const FRAMELESS_FITTING_KINDS: FramelessFittingJson["kind"][] = [
  "PATCH_FITTING",
  "CLAMP",
  "HINGE",
  "LOCK",
  "CONNECTOR",
  "SEAL",
  "SUPPORT",
];

function FramelessSection({
  module,
  product,
  couplerSkus,
  busy,
  commit,
}: {
  module: ProductModuleJson;
  product: ProductJson;
  couplerSkus: string[];
  busy: boolean;
  commit(next: ProductJson): void;
}): JSX.Element {
  const spec = module.frameless;
  const update = (next: FramelessSpecJson | null) =>
    commit(setModuleFrameless(product, module.id, next));
  if (!spec) {
    return (
      <details className="inspector-section">
        <summary>{t("assembly.frameless")}</summary>
        <p className="inspector-note">{t("assembly.framelessHint")}</p>
        <div className="inspector-actions">
          <button
            type="button"
            className="ghost-button"
            disabled={busy}
            onClick={() => update({ supports: [], fittings: [] })}
          >
            {t("assembly.makeFrameless")}
          </button>
        </div>
      </details>
    );
  }
  const exposed = spec.exposed_edges ?? ["left", "right", "top", "bottom"];
  const setSupport = (index: number, next: Partial<FramelessSupportJson>) =>
    update({
      ...spec,
      supports: spec.supports.map((item, at) => (at === index ? { ...item, ...next } : item)),
    });
  const setFitting = (index: number, next: Partial<FramelessFittingJson>) =>
    update({
      ...spec,
      fittings: spec.fittings.map((item, at) => (at === index ? { ...item, ...next } : item)),
    });
  return (
    <details className="inspector-section" open>
      <summary>{t("assembly.frameless")}</summary>
      <p className="inspector-note">{t("assembly.framelessHint")}</p>
      <h5 className="inspector-subhead">{t("assembly.framelessSupports")}</h5>
      <ul className="frameless-rows">
        {spec.supports.map((support, index) => (
          <li key={index} className="frameless-row">
            <select
              aria-label={t("assembly.framelessEdge")}
              value={support.edge}
              disabled={busy}
              onChange={(event) => setSupport(index, { edge: event.target.value as FramelessEdge })}
            >
              {FRAMELESS_EDGES.map(([edge, key]) => (
                <option key={edge} value={edge}>
                  {t(key)}
                </option>
              ))}
            </select>
            <select
              aria-label={t("assembly.framelessKind")}
              value={support.kind}
              disabled={busy}
              onChange={(event) =>
                setSupport(index, {
                  kind: event.target.value as FramelessSupportJson["kind"],
                })
              }
            >
              <option value="CHANNEL">{t("assembly.framelessKindChannel")}</option>
              <option value="CLAMPS">{t("assembly.framelessKindClamps")}</option>
            </select>
            {support.kind === "CHANNEL" ? (
              <select
                aria-label={t("assembly.framelessSku")}
                value={support.article_sku}
                disabled={busy}
                onChange={(event) => setSupport(index, { article_sku: event.target.value })}
              >
                <option value="">{t("assembly.framelessSku")}…</option>
                {couplerSkus.map((sku) => (
                  <option key={sku} value={sku}>
                    {sku}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label={t("assembly.framelessSku")}
                type="text"
                value={support.article_sku}
                disabled={busy}
                onChange={(event) => setSupport(index, { article_sku: event.target.value })}
              />
            )}
            <input
              aria-label={t("assembly.framelessQty")}
              type="number"
              min={1}
              value={support.qty}
              disabled={busy}
              onChange={(event) =>
                setSupport(index, { qty: Math.max(1, Number(event.target.value) || 1) })
              }
            />
            <button
              type="button"
              className="ghost-button is-danger"
              aria-label={`${t("assembly.framelessRemoveItem")} ${t("assembly.framelessSupports")} ${index + 1}`}
              disabled={busy}
              onClick={() =>
                update({ ...spec, supports: spec.supports.filter((_, at) => at !== index) })
              }
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <div className="inspector-actions">
        <button
          type="button"
          className="ghost-button"
          disabled={busy}
          onClick={() =>
            update({
              ...spec,
              supports: [
                ...spec.supports,
                { kind: "CHANNEL", edge: "bottom", article_sku: "", qty: 1 },
              ],
            })
          }
        >
          {t("assembly.framelessAddSupport")}
        </button>
      </div>
      <h5 className="inspector-subhead">{t("assembly.framelessFittings")}</h5>
      <ul className="frameless-rows">
        {spec.fittings.map((fitting, index) => (
          <li key={index} className="frameless-row">
            <select
              aria-label={t("assembly.framelessKind")}
              value={fitting.kind}
              disabled={busy}
              onChange={(event) =>
                setFitting(index, {
                  kind: event.target.value as FramelessFittingJson["kind"],
                })
              }
            >
              {FRAMELESS_FITTING_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {t(`assembly.fittingKind.${kind}` as TranslationKey)}
                </option>
              ))}
            </select>
            <input
              aria-label={t("assembly.framelessSku")}
              type="text"
              value={fitting.sku}
              disabled={busy}
              onChange={(event) => setFitting(index, { sku: event.target.value })}
            />
            <input
              aria-label={t("assembly.framelessQty")}
              type="number"
              min={1}
              value={fitting.qty}
              disabled={busy}
              onChange={(event) =>
                setFitting(index, { qty: Math.max(1, Number(event.target.value) || 1) })
              }
            />
            <button
              type="button"
              className="ghost-button is-danger"
              aria-label={`${t("assembly.framelessRemoveItem")} ${t("assembly.framelessFittings")} ${index + 1}`}
              disabled={busy}
              onClick={() =>
                update({ ...spec, fittings: spec.fittings.filter((_, at) => at !== index) })
              }
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <div className="inspector-actions">
        <button
          type="button"
          className="ghost-button"
          disabled={busy}
          onClick={() =>
            update({
              ...spec,
              fittings: [...spec.fittings, { kind: "PATCH_FITTING", sku: "", qty: 1 }],
            })
          }
        >
          {t("assembly.framelessAddFitting")}
        </button>
      </div>
      <h5 className="inspector-subhead">{t("assembly.framelessExposedEdges")}</h5>
      <div
        className="frameless-edges"
        role="group"
        aria-label={t("assembly.framelessExposedEdges")}
      >
        {FRAMELESS_EDGES.map(([edge, key]) => (
          <label key={edge} className="assembly-field assembly-field--inline">
            <input
              type="checkbox"
              checked={exposed.includes(edge)}
              disabled={busy}
              onChange={(event) => {
                const next = event.target.checked
                  ? [...exposed, edge]
                  : exposed.filter((item) => item !== edge);
                update({
                  ...spec,
                  exposed_edges:
                    next.length === 4
                      ? undefined
                      : FRAMELESS_EDGES.map(([candidate]) => candidate).filter((candidate) =>
                          next.includes(candidate),
                        ),
                });
              }}
            />
            <span>{t(key)}</span>
          </label>
        ))}
      </div>
      <div className="inspector-actions">
        <button
          type="button"
          className="ghost-button is-danger"
          disabled={busy}
          onClick={() => update(null)}
        >
          {t("assembly.framelessRemove")}
        </button>
      </div>
    </details>
  );
}

/** Detail levels on the right rail — the same selection shows progressively
 * more: identity & facts (overview), editable design intent (design), or the
 * engine's manufacturing output (technical). */
type DetailLevel = "overview" | "design" | "technical";

const DETAIL_LEVELS: { level: DetailLevel; labelKey: TranslationKey }[] = [
  { level: "overview", labelKey: "assembly.levelOverview" },
  { level: "design", labelKey: "assembly.levelDesign" },
  { level: "technical", labelKey: "assembly.levelTechnical" },
];

/** Sliding panel topology editor — shared by the module inspector (primary
 * bay) and the bay inspector (the leaf the layout actually lives on). */
function SlidingPanelsEditor({
  instanceId,
  layout,
  busy,
  onChange,
}: {
  instanceId: string;
  layout: SlidingLayout;
  busy: boolean;
  onChange(next: SlidingLayout): void;
}): JSX.Element {
  return (
    <details className="inspector-section" open>
      <summary>{t("assembly.slidingLayout")}</summary>
      <div className="inspector-field">
        <label htmlFor={`tracks-${instanceId}`}>{t("assembly.slidingTracks")}</label>
        <select
          id={`tracks-${instanceId}`}
          value={layout.tracks}
          disabled={busy}
          onChange={(event) => {
            const tracks = Number(event.target.value);
            onChange({
              tracks,
              panels: layout.panels.map((panel, index) =>
                panel.kind === "MOVING" ? { ...panel, track: index % tracks } : panel,
              ),
            });
          }}
        >
          {[1, 2, 3, 4]
            .filter(
              (count) =>
                count === layout.tracks ||
                count >=
                  (layout.panels.filter((panel) => panel.kind === "MOVING").length > 1 ? 2 : 1),
            )
            .map((count) => (
              <option key={count} value={count}>
                {count}
              </option>
            ))}
        </select>
      </div>
      <ul className="sliding-panels" aria-label={t("assembly.slidingLayout")}>
        {layout.panels.map((panel, index) => (
          <li key={panel.slot} className="sliding-panel">
            <span className="sliding-panel__slot">
              {t("assembly.slidingPanel").replace("{index}", String(index + 1))}
            </span>
            <select
              aria-label={`${t("assembly.slidingPanel").replace("{index}", String(index + 1))} ${t("intent.opening")}`}
              value={panel.kind}
              disabled={busy}
              onChange={(event) => {
                const kind = event.target.value as "MOVING" | "FIXED";
                const panels = layout.panels.map((item, at) =>
                  at === index
                    ? {
                        ...item,
                        kind,
                        track:
                          kind === "MOVING"
                            ? (item.track ?? index % Math.max(layout.tracks, 1))
                            : null,
                      }
                    : item,
                );
                onChange({ ...layout, panels });
              }}
            >
              <option value="MOVING">{t("assembly.panelMoving")}</option>
              <option value="FIXED">{t("assembly.panelFixed")}</option>
            </select>
            {panel.kind === "MOVING" && (
              <select
                aria-label={`${t("assembly.slidingPanel").replace("{index}", String(index + 1))} ${t("assembly.panelTrack")}`}
                value={panel.track ?? 0}
                disabled={busy}
                onChange={(event) => {
                  const track = Number(event.target.value);
                  const panels = layout.panels.map((item, at) =>
                    at === index ? { ...item, track } : item,
                  );
                  onChange({ ...layout, panels });
                }}
              >
                {Array.from({ length: layout.tracks }, (_, track) => (
                  <option key={track} value={track}>
                    {t("assembly.panelTrack")} {track + 1}
                  </option>
                ))}
              </select>
            )}
          </li>
        ))}
      </ul>
      <div className="inspector-actions">
        <button
          type="button"
          className="ghost-button"
          disabled={busy || layout.panels.length >= 8}
          onClick={() =>
            onChange({
              ...layout,
              panels: [
                ...layout.panels,
                {
                  slot: `S${layout.panels.length + 1}`,
                  kind: "MOVING",
                  track: layout.panels.length % Math.max(layout.tracks, 1),
                },
              ],
            })
          }
        >
          {t("assembly.addPanel")}
        </button>
        <button
          type="button"
          className="ghost-button"
          disabled={busy || layout.panels.length <= 1}
          onClick={() =>
            onChange({
              ...layout,
              panels: layout.panels.slice(0, -1),
            })
          }
        >
          {t("assembly.removePanel")}
        </button>
      </div>
    </details>
  );
}

/** A bay (paño) is the leaf granularity the workshop thinks in — opening,
 * glazing and handle placement edit on this leaf alone, through the same
 * normalized request-tree every other canvas edit uses. */
function BayInspector({
  module,
  bay,
  product,
  glassSkus,
  glassSpecs,
  glazingThicknesses,
  panelSkus,
  busy,
  commit,
  onAskAssistant,
}: {
  module: ProductModuleJson;
  bay: IntentNode;
  product: ProductJson;
  glassSkus: string[];
  glassSpecs: GlassSpecChoice[];
  glazingThicknesses: string[];
  panelSkus: string[];
  busy: boolean;
  commit(next: ProductJson): void;
  onAskAssistant?(): void;
}): JSX.Element {
  const opening = bay.opening_type ?? "FIXED";
  const isDoor = opening === "DOOR_ENTRY";
  const slidingLayout = resolvedSlidingLayout(bay);
  const bays = intentBays(module.tree);
  const bayOrdinal = bays.findIndex((node) => node.id === bay.id) + 1;
  const moduleOrdinal = product.assembly.modules.findIndex((item) => item.id === module.id) + 1;
  const isTopBay = topIntent(module.tree).id === bay.id;
  const recentGlass = useCanvasStore((state) => state.recentGlass);
  const pushRecentGlass = useCanvasStore((state) => state.pushRecentGlass);
  const favoriteGlass = useCanvasStore((state) => state.favoriteGlass);
  const toggleFavoriteGlass = useCanvasStore((state) => state.toggleFavoriteGlass);

  function patchBay(patch: Partial<IntentNode>): void {
    commit(setModuleTree(product, module.id, updateBay(module.tree, bay.id, patch)));
  }

  function pickGlass(sku: string | null): void {
    if (sku) pushRecentGlass(sku);
    patchBay({
      glass_article_sku: sku,
      glass_spec:
        sku == null ? bay.glass_spec : (glassSpecs.find((item) => item.sku === sku)?.spec ?? null),
    });
  }

  function pickOpening(next: Opening): void {
    if (next === "DOOR_ENTRY" && !isTopBay) return;
    // Mirrors setModuleOpening's normalization at leaf scope: a sliding pick
    // seeds the 2-leaf preset, a non-door bay never keeps a panel sku, and a
    // door always carries declared handedness (manufacture refuses to guess).
    patchBay({
      opening_type: next,
      sliding_layout: next === "SLIDING" ? structuredClone(SLIDING_PRESETS.SLIDING_2L!) : null,
      panel_article_sku: next === "DOOR_ENTRY" ? (bay.panel_article_sku ?? null) : null,
      door_handedness: next === "DOOR_ENTRY" ? (bay.door_handedness ?? "LEFT") : null,
    });
  }

  return (
    <section className="assembly-inspector" aria-label={t("assembly.bay")}>
      <header className="assembly-inspector__header">
        <h4>
          {t("assembly.bay")} {bayOrdinal} · {t("assembly.module")} {moduleOrdinal}
        </h4>
      </header>
      <ProvenanceStrip
        items={[
          { label: t("assembly.opening"), state: "DECLARED" },
          {
            label: t("assembly.glass"),
            state: bay.glass_article_sku
              ? "VERIFIED"
              : opening === "FIXED" || isDoor
                ? "UNKNOWN"
                : "BLOCKED",
          },
          {
            label: t("assembly.glassThickness"),
            state: bay.glass_thickness_mm ? "DECLARED" : "UNKNOWN",
          },
          {
            label: t("quotation.handleHeight"),
            state: bay.handle_height_mm ? "DECLARED" : "UNKNOWN",
          },
        ]}
      />
      <details className="inspector-section" open>
        <summary>{t("assembly.opening")}</summary>
        <div className="opening-grid" role="group" aria-label={t("assembly.opening")}>
          {OPENING_OPTIONS.map(([value, labelKey]) => {
            const doorBlocked = value === "DOOR_ENTRY" && !isTopBay;
            return (
              <button
                key={value}
                type="button"
                className={`opening-choice${opening === value ? " is-active" : ""}`}
                title={doorBlocked ? t("assembly.doorTopOnly") : t(labelKey)}
                aria-label={t(labelKey)}
                aria-pressed={opening === value}
                disabled={busy || doorBlocked}
                onClick={() => pickOpening(value)}
              >
                <svg viewBox="0 0 100 100" aria-hidden="true">
                  <rect className="opening-choice__frame" x={4} y={4} width={92} height={92} />
                  <OpeningGlyph opening={value} x={4} y={4} w={92} h={92} />
                </svg>
              </button>
            );
          })}
        </div>
        {isDoor && (
          <label className="assembly-field">
            <span>{t("assembly.hingeSide")}</span>
            <select
              aria-label={t("assembly.hingeSide")}
              disabled={busy}
              value={bay.door_handedness ?? "LEFT"}
              onChange={(event) =>
                patchBay({ door_handedness: event.target.value as "LEFT" | "RIGHT" })
              }
            >
              <option value="LEFT">{t("assembly.hingeLeft")}</option>
              <option value="RIGHT">{t("assembly.hingeRight")}</option>
            </select>
          </label>
        )}
        {isDoor && !isTopBay && <p className="assembly-hint">{t("assembly.doorTopOnly")}</p>}
      </details>
      {slidingLayout && (
        <SlidingPanelsEditor
          instanceId={bay.id}
          layout={slidingLayout}
          busy={busy}
          onChange={(next) => commit(setModuleSlidingLayout(product, module.id, next, bay.id))}
        />
      )}
      <details className="inspector-section" open>
        <summary>{t("inspector.glazing")}</summary>
        <label className="assembly-field">
          <span>{t("assembly.glassThickness")}</span>
          <select
            aria-label={t("assembly.glassThickness")}
            disabled={busy}
            value={bay.glass_thickness_mm ?? ""}
            onChange={(event) => {
              const next = event.target.value || null;
              patchBay({
                glass_thickness_mm: next,
                glass_spec: bay.glass_spec ?? next,
              });
            }}
          >
            <option value="">{t("assembly.chooseThickness")}</option>
            {glazingThicknesses.map((thickness) => (
              <option key={thickness} value={thickness}>
                {thickness} mm
              </option>
            ))}
          </select>
        </label>
        <label className="assembly-field">
          <span>{t("assembly.glass")}</span>
          <span className="assembly-field__row">
            <select
              aria-label={t("assembly.glass")}
              disabled={busy}
              value={bay.glass_article_sku ?? ""}
              onChange={(event) => pickGlass(event.target.value || null)}
            >
              <option value="">{t("assembly.noGlass")}</option>
              {glassSkus.map((sku) => (
                <option key={sku} value={sku}>
                  {sku}
                </option>
              ))}
            </select>
            <button
              type="button"
              className={`star-toggle${
                favoriteGlass.includes(bay.glass_article_sku ?? "") ? " is-active" : ""
              }`}
              aria-label={t("assembly.favoriteGlass")}
              aria-pressed={favoriteGlass.includes(bay.glass_article_sku ?? "")}
              disabled={busy || bay.glass_article_sku == null}
              onClick={() => {
                if (bay.glass_article_sku) toggleFavoriteGlass(bay.glass_article_sku);
              }}
            >
              ★
            </button>
          </span>
        </label>
        {favoriteGlass.some((sku) => glassSkus.includes(sku)) && (
          <div className="recents" aria-label={t("assembly.favoriteGlass")}>
            <span className="recents__label">{t("assembly.favoriteGlass")}</span>
            {favoriteGlass
              .filter((sku) => sku !== bay.glass_article_sku && glassSkus.includes(sku))
              .map((sku) => (
                <button
                  key={sku}
                  type="button"
                  className="recents__chip recents__chip--favorite"
                  disabled={busy}
                  title={sku}
                  onClick={() => pickGlass(sku)}
                >
                  {sku}
                </button>
              ))}
          </div>
        )}
        {recentGlass.some((sku) => glassSkus.includes(sku)) && (
          <div className="recents" aria-label={t("assembly.recentGlass")}>
            <span className="recents__label">{t("assembly.recentGlass")}</span>
            {recentGlass
              .filter((sku) => sku !== bay.glass_article_sku && glassSkus.includes(sku))
              .map((sku) => (
                <button
                  key={sku}
                  type="button"
                  className="recents__chip"
                  disabled={busy}
                  title={sku}
                  onClick={() => pickGlass(sku)}
                >
                  {sku}
                </button>
              ))}
          </div>
        )}
        {isDoor && (
          <label className="assembly-field">
            <span>{t("assembly.panel")}</span>
            <select
              aria-label={t("assembly.panel")}
              disabled={busy}
              value={bay.panel_article_sku ?? ""}
              onChange={(event) => patchBay({ panel_article_sku: event.target.value || null })}
            >
              <option value="">{t("assembly.noPanel")}</option>
              {panelSkus.map((sku) => (
                <option key={sku} value={sku}>
                  {sku}
                </option>
              ))}
            </select>
          </label>
        )}
        <DraftField
          label={t("quotation.handleHeight")}
          value={bay.handle_height_mm ?? ""}
          unit="mm"
          disabled={busy}
          normalize={normalizeMm}
          onCommit={(value) => patchBay({ handle_height_mm: value })}
        />
      </details>
      {onAskAssistant && (
        <div className="inspector-actions">
          <button type="button" className="ghost-button" disabled={busy} onClick={onAskAssistant}>
            {t("assistant.modifyWith")}
          </button>
        </div>
      )}
    </section>
  );
}

/** §04-D technical provenance: which declared values are catalog-backed
 * (VERIFIED), which are user intent (DECLARED), which are missing
 * (UNKNOWN) and which block the design (BLOCKED). Rendered as a compact
 * strip at the top of every inspector so the states are always obvious. */
type FieldState = "VERIFIED" | "DECLARED" | "UNKNOWN" | "BLOCKED";

function ProvenanceStrip({
  items,
}: {
  items: { label: string; state: FieldState }[];
}): JSX.Element {
  return (
    <ul className="prov-strip" aria-label={t("prov.title")}>
      {items.map((item, index) => (
        <li
          key={`${item.label}-${index}`}
          className={`prov-chip prov-chip--${item.state.toLowerCase()}`}
          title={t(`prov.${item.state.toLowerCase()}` as TranslationKey)}
        >
          <span className="prov-chip__state">
            {t(`prov.${item.state.toLowerCase()}` as TranslationKey)}
          </span>
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** Mullion/transom inspector — a division is a real object: its offset is
 * editable, its profile is catalog authority, its bays are one click away,
 * and merging it back is an explicit domain op (never index surgery). */
function DivisionInspector({
  module,
  division,
  product,
  busy,
  commit,
  onSelect,
  onAskAssistant,
}: {
  module: ProductModuleJson;
  division: IntentNode;
  product: ProductJson;
  busy: boolean;
  commit(next: ProductJson): void;
  onSelect(id: string): void;
  onAskAssistant?(): void;
}): JSX.Element {
  const vertical = division.type === "SPLIT_V";
  const children = division.children ?? [];
  const removable = canRemoveModuleDivision(product, module.id, division.id);
  const bays = intentBays(module.tree);
  const childLabel = (child: IntentNode): string =>
    child.type === "BAY"
      ? `${t("assembly.bay")} ${bays.findIndex((node) => node.id === child.id) + 1}`
      : child.type === "SPLIT_V"
        ? t("assembly.mullionV")
        : child.type === "SPLIT_H"
          ? t("assembly.transomH")
          : child.id;
  return (
    <section className="assembly-inspector" aria-label={t("assembly.division")}>
      <header className="assembly-inspector__header">
        <h4>{vertical ? t("assembly.mullionV") : t("assembly.transomH")}</h4>
      </header>
      <ProvenanceStrip
        items={[
          { label: t("inspector.divisionType"), state: "DECLARED" },
          { label: t("assembly.splitOffset"), state: "DECLARED" },
          {
            label: t("assembly.mullionProfile"),
            state: division.mullion_profile_sku ? "VERIFIED" : "UNKNOWN",
          },
        ]}
      />
      <details className="inspector-section" open>
        <summary>{t("inspector.dimensions")}</summary>
        <DraftField
          label={t("assembly.splitOffset")}
          value={division.split_offset_mm ?? ""}
          unit="mm"
          disabled={busy}
          normalize={normalizeMm}
          onCommit={(value) => commit(moveModuleDivision(product, module.id, division.id, value))}
        />
        <div className="inspector-field">
          <span className="inspector-field__label">{t("assembly.mullionProfile")}</span>
          <code className="inspector-field__value">
            {division.mullion_profile_sku ?? t("prov.unknown")}
          </code>
        </div>
      </details>
      <details className="inspector-section" open>
        <summary>{t("assembly.divisionBays")}</summary>
        <ul className="division-children">
          {children.map((child) => (
            <li key={child.id}>
              <button
                type="button"
                className="link-button"
                onClick={() => onSelect(`${module.id}/${child.id}`)}
              >
                {childLabel(child)}
              </button>
            </li>
          ))}
        </ul>
      </details>
      <div className="inspector-actions">
        <button
          type="button"
          className="ghost-button ghost-button--danger"
          disabled={busy || !removable}
          onClick={() => {
            const kept = children[0]?.id;
            commit(removeModuleDivision(product, module.id, division.id));
            onSelect(kept ? `${module.id}/${kept}` : module.id);
          }}
        >
          {t("assembly.removeSplit")}
        </button>
        {!removable && <p className="assembly-hint">{t("assembly.removeSplitNested")}</p>}
        {removable && <p className="assembly-hint">{t("assembly.removeSplitKeeps")}</p>}
        {onAskAssistant && (
          <button type="button" className="ghost-button" disabled={busy} onClick={onAskAssistant}>
            {t("assistant.modifyWith")}
          </button>
        )}
      </div>
    </section>
  );
}

/** Overview level: what this element IS, not how to change it. */
function ElementSummary({ title, rows }: { title: string; rows: [string, string][] }): JSX.Element {
  return (
    <section className="assembly-inspector inspector-summary">
      <h4 className="inspector-summary__title">{title}</h4>
      <dl className="inspector-summary__list">
        {rows.map(([label, value]) => (
          <div key={label} className="inspector-summary__row">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Technical level: the engine's manufacturing output for the selection —
 * the module's cuts/glass/hardware, or just the pieces tagged to one bay. */
function TechnicalPanel({
  evaluation,
  moduleId,
  bayId,
  moduleIndex,
  members,
  bayNode,
  widthMm,
}: {
  evaluation: EngineAssemblyCalculateResponse | null;
  moduleId?: string;
  bayId?: string | null;
  moduleIndex?: (moduleId: string) => number;
  /** The declared member sections + bay the §05 section view cuts through
   * — same product model as the canvas, never a separate drawing. */
  members?: MemberGeometry;
  bayNode?: IntentNode | null;
  widthMm?: number;
}): JSX.Element {
  const entries = (evaluation?.modules ?? []).filter(
    (entry) => !moduleId || entry.module_id === moduleId,
  );
  if (entries.length === 0) {
    return (
      <section className="assembly-inspector">
        <p className="assembly-hint">{t("assembly.techPending")}</p>
      </section>
    );
  }
  return (
    <div className="tech-panel">
      {members && widthMm !== undefined && widthMm > 0 && (
        <details className="inspector-section" open>
          <summary>{t("assembly.sectionView")}</summary>
          <SectionView bay={bayNode ?? null} members={members} widthMm={widthMm} />
        </details>
      )}
      {entries.map((entry) => {
        const result = entry.result;
        const ordinal = moduleIndex ? moduleIndex(entry.module_id) : 0;
        const heading = `${t("assembly.module")} ${ordinal}`;
        if (!result) {
          return (
            <section key={entry.module_id} className="assembly-inspector">
              <h4 className="inspector-summary__title">{heading}</h4>
              <p className="assembly-hint">{t("assembly.techUnavailable")}</p>
            </section>
          );
        }
        const cuts = result.profile_cuts.filter((cut) => !bayId || cut.bay_id === bayId);
        const glasses = result.glasses.filter((glass) => !bayId || glass.bay_id === bayId);
        const panels = result.panels.filter((panel) => !bayId || panel.bay_id === bayId);
        const fittings = result.fittings.filter((fit) => !bayId || fit.bay_id === bayId);
        const empty =
          cuts.length === 0 && glasses.length === 0 && panels.length === 0 && fittings.length === 0;
        return (
          <section key={entry.module_id} className="assembly-inspector">
            <h4 className="inspector-summary__title">{heading}</h4>
            {empty && <p className="assembly-hint">{t("assembly.techEmpty")}</p>}
            {cuts.length > 0 && (
              <details className="inspector-section" open>
                <summary>{t("assembly.techCuts")}</summary>
                <table className="tech-table">
                  <thead>
                    <tr>
                      <th>{t("assembly.techSku")}</th>
                      <th>{t("assembly.techLength")}</th>
                      <th>{t("assembly.techQty")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cuts.map((cut, index) => (
                      <tr key={`${cut.sku}-${index}`}>
                        <td>{cut.sku}</td>
                        <td>{Number(cut.length_mm).toFixed(0)}</td>
                        <td>{cut.qty}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
            {glasses.length > 0 && (
              <details className="inspector-section" open>
                <summary>{t("assembly.techGlasses")}</summary>
                <table className="tech-table">
                  <thead>
                    <tr>
                      <th>{t("assembly.glass")}</th>
                      <th>{t("projects.dims")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {glasses.map((glass, index) => (
                      <tr key={`${glass.bay_id}-${index}`}>
                        <td>{glass.article_sku ?? "—"}</td>
                        <td>
                          {Number(glass.width_mm).toFixed(0)} × {Number(glass.height_mm).toFixed(0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
            {panels.length > 0 && (
              <details className="inspector-section" open>
                <summary>{t("assembly.techPanels")}</summary>
                <table className="tech-table">
                  <thead>
                    <tr>
                      <th>{t("assembly.panel")}</th>
                      <th>{t("projects.dims")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {panels.map((panel, index) => (
                      <tr key={`${panel.bay_id}-${index}`}>
                        <td>{panel.sku}</td>
                        <td>
                          {Number(panel.width_mm).toFixed(0)} × {Number(panel.height_mm).toFixed(0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
            {fittings.length > 0 && (
              <details className="inspector-section" open>
                <summary>{t("assembly.techFittings")}</summary>
                <table className="tech-table">
                  <thead>
                    <tr>
                      <th>{t("assembly.techSku")}</th>
                      <th>{t("assembly.techQty")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fittings.map((fit, index) => (
                      <tr key={`${fit.sku}-${index}`}>
                        <td>{fit.sku}</td>
                        <td>{fit.qty}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </section>
        );
      })}
    </div>
  );
}

function ModuleInspector({
  module,
  product,
  members,
  glassSkus,
  glassSpecs,
  glazingThicknesses,
  panelSkus,
  mullionSkus,
  couplerSkus,
  busy,
  commit,
  onAskAssistant,
}: {
  module: ProductJson["assembly"]["modules"][number];
  product: ProductJson;
  members: MemberGeometry;
  glassSkus: string[];
  glassSpecs: GlassSpecChoice[];
  glazingThicknesses: string[];
  panelSkus: string[];
  mullionSkus: Partial<Record<SplitType, string>>;
  couplerSkus: string[];
  busy: boolean;
  commit(next: ProductJson): void;
  onAskAssistant?(): void;
}): JSX.Element {
  const opening = moduleOpening(module);
  const isDoor = opening === "DOOR_ENTRY";
  const slidingBay = isSlidingOpening(opening) ? modulePrimaryBay(module) : null;
  const slidingLayout = slidingBay ? resolvedSlidingLayout(slidingBay) : null;
  const ordinal = product.assembly.modules.findIndex((item) => item.id === module.id) + 1;
  const commitSlidingLayout = (layout: SlidingLayout) => {
    if (slidingBay) {
      commit(setModuleSlidingLayout(product, module.id, layout, slidingBay.id));
    }
  };
  return (
    <section className="assembly-inspector" aria-label={t("assembly.module")}>
      <header className="assembly-inspector__header">
        <h4>
          {t("assembly.module")} {ordinal}
        </h4>
        <button
          type="button"
          className="ghost-button is-danger"
          disabled={busy || product.assembly.modules.length <= 1}
          title={t("assembly.removeUnit")}
          aria-label={t("assembly.removeUnit")}
          onClick={() => commit(removeUnit(product, module.id))}
        >
          ×
        </button>
      </header>
      <ProvenanceStrip
        items={[
          { label: t("inspector.dimensions"), state: "DECLARED" },
          {
            label: t("assembly.glass"),
            state: moduleGlassSku(module) !== null ? "VERIFIED" : "UNKNOWN",
          },
          {
            label: t("assembly.coupler"),
            state: couplerSkus.length > 0 ? "VERIFIED" : "UNKNOWN",
          },
        ]}
      />
      <details className="inspector-section" open>
        <summary>{t("assembly.opening")}</summary>
        <div className="opening-grid" role="group" aria-label={t("assembly.opening")}>
          {OPENING_OPTIONS.map(([value, labelKey]) => (
            <button
              key={value}
              type="button"
              className={`opening-choice${opening === value ? " is-active" : ""}`}
              title={t(labelKey)}
              aria-label={t(labelKey)}
              aria-pressed={opening === value}
              disabled={busy}
              onClick={() => commit(setModuleOpening(product, module.id, value))}
            >
              <svg viewBox="0 0 100 100" aria-hidden="true">
                <rect className="opening-choice__frame" x={4} y={4} width={92} height={92} />
                <OpeningGlyph opening={value} x={4} y={4} w={92} h={92} />
              </svg>
            </button>
          ))}
        </div>
        <div className="inspector-actions">
          <button
            type="button"
            className="ghost-button"
            disabled={busy || mullionSkus.SPLIT_V === undefined || isDoor}
            onClick={() =>
              commit(
                splitModuleBay(
                  product,
                  module.id,
                  { type: "SPLIT_V", mullionSku: mullionSkus.SPLIT_V ?? "" },
                  members,
                ),
              )
            }
          >
            {t("assembly.splitV")}
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={busy || mullionSkus.SPLIT_H === undefined || isDoor}
            onClick={() =>
              commit(
                splitModuleBay(
                  product,
                  module.id,
                  { type: "SPLIT_H", mullionSku: mullionSkus.SPLIT_H ?? "" },
                  members,
                ),
              )
            }
          >
            {t("assembly.splitH")}
          </button>
        </div>
      </details>
      {slidingLayout && slidingBay && (
        <SlidingPanelsEditor
          instanceId={slidingBay.id}
          layout={slidingLayout}
          busy={busy}
          onChange={commitSlidingLayout}
        />
      )}
      <details className="inspector-section" open>
        <summary>{t("inspector.dimensions")}</summary>
        <DraftField
          label={t("assembly.width")}
          value={module.width_mm}
          unit="mm"
          disabled={busy}
          normalize={normalizeMm}
          onCommit={(value) => commit(setModuleWidth(product, module.id, value))}
        />
        <DraftField
          label={t("assembly.height")}
          value={module.height_mm}
          unit="mm"
          disabled={busy}
          normalize={normalizeMm}
          onCommit={(value) => commit(setAllModuleHeights(product, value))}
        />
      </details>
      {!module.frameless && (
        <details className="inspector-section">
          <summary>{t("assembly.sectionTitle")}</summary>
          <div className="section-preview-list">
            <div>
              <p className="inspector-note">{members.frame.sku ?? t("assembly.frame")}</p>
              <SectionPreviewSvg
                section={members.frame.section}
                faceWidthMm={members.frame.faceWidthMm}
                material={members.frame.material}
              />
            </div>
            <div>
              <p className="inspector-note">{members.sash.sku ?? t("assembly.sash")}</p>
              <SectionPreviewSvg
                section={members.sash.section}
                faceWidthMm={members.sash.faceWidthMm}
                material={members.sash.material}
              />
            </div>
          </div>
        </details>
      )}
      {module.contour && (
        <ContourShapeSection module={module} product={product} busy={busy} commit={commit} />
      )}
      <FramelessSection
        module={module}
        product={product}
        couplerSkus={couplerSkus}
        busy={busy}
        commit={commit}
      />
      <details className="inspector-section" open>
        <summary>{t("inspector.glazing")}</summary>
        <label className="assembly-field">
          <span>{t("assembly.glassThickness")}</span>
          <select
            aria-label={t("assembly.glassThickness")}
            disabled={busy}
            value={moduleGlassThicknessMm(module) ?? ""}
            onChange={(event) =>
              commit(setModuleGlassThickness(product, module.id, event.target.value || null))
            }
          >
            <option value="">{t("assembly.chooseThickness")}</option>
            {glazingThicknesses.map((thickness) => (
              <option key={thickness} value={thickness}>
                {thickness} mm
              </option>
            ))}
          </select>
        </label>
        <label className="assembly-field">
          <span>{t("assembly.glass")}</span>
          <select
            aria-label={t("assembly.glass")}
            disabled={busy}
            value={moduleGlassSku(module) ?? ""}
            onChange={(event) => {
              const sku = event.target.value || null;
              commit(
                setModuleGlass(
                  product,
                  module.id,
                  sku,
                  sku == null
                    ? undefined
                    : (glassSpecs.find((item) => item.sku === sku)?.spec ?? null),
                ),
              );
            }}
          >
            <option value="">{t("assembly.noGlass")}</option>
            {glassSkus.map((sku) => (
              <option key={sku} value={sku}>
                {sku}
              </option>
            ))}
          </select>
        </label>
        {isDoor && (
          <label className="assembly-field">
            <span>{t("assembly.panel")}</span>
            <select
              aria-label={t("assembly.panel")}
              disabled={busy}
              value={modulePanelSku(module) ?? ""}
              onChange={(event) =>
                commit(setModulePanel(product, module.id, event.target.value || null))
              }
            >
              <option value="">{t("assembly.noPanel")}</option>
              {panelSkus.map((sku) => (
                <option key={sku} value={sku}>
                  {sku}
                </option>
              ))}
            </select>
          </label>
        )}
      </details>
      {onAskAssistant && (
        <div className="inspector-actions">
          <button type="button" className="ghost-button" disabled={busy} onClick={onAskAssistant}>
            {t("assistant.modifyWith")}
          </button>
        </div>
      )}
    </section>
  );
}

function CouplingInspector({
  coupling,
  product,
  ordinal,
  couplerSkus,
  busy,
  commit,
  onAskAssistant,
}: {
  coupling: CouplingJson;
  product: ProductJson;
  ordinal: number;
  couplerSkus: string[];
  busy: boolean;
  commit(next: ProductJson): void;
  onAskAssistant?(): void;
}): JSX.Element {
  return (
    <section className="assembly-inspector" aria-label={t("assembly.coupling")}>
      <header className="assembly-inspector__header">
        <h4>
          {t("assembly.coupling")} {ordinal}
        </h4>
      </header>
      <ProvenanceStrip
        items={[
          { label: t("assembly.angle"), state: "DECLARED" },
          { label: t("inspector.couplingType"), state: "DECLARED" },
          {
            label: t("assembly.coupler"),
            state: coupling.coupler_profile_sku ? "VERIFIED" : "UNKNOWN",
          },
        ]}
      />
      <DraftField
        label={t("assembly.angle")}
        value={coupling.angle_deg}
        unit="°"
        disabled={busy}
        normalize={normalizeAngle}
        onCommit={(value) => commit(setCouplingAngle(product, coupling.id, value))}
      />
      <label className="assembly-field">
        <span>{t("assembly.coupler")}</span>
        <select
          aria-label={t("assembly.coupler")}
          disabled={busy}
          value={coupling.coupler_profile_sku ?? ""}
          onChange={(event) =>
            commit(setCouplerSku(product, coupling.id, event.target.value || null))
          }
        >
          <option value="">{t("assembly.noCoupler")}</option>
          {couplerSkus.map((sku) => (
            <option key={sku} value={sku}>
              {sku}
            </option>
          ))}
        </select>
      </label>
      <div className="inspector-actions">
        <button
          type="button"
          className="ghost-button"
          disabled={busy || Number(coupling.angle_deg) === 0}
          title={
            Number(coupling.angle_deg) === 0
              ? t("assembly.straightenDisabled")
              : t("assembly.straightenHint")
          }
          onClick={() => commit(setCouplingAngle(product, coupling.id, "0"))}
        >
          {t("assembly.straighten")}
        </button>
        {onAskAssistant && (
          <button type="button" className="ghost-button" disabled={busy} onClick={onAskAssistant}>
            {t("assistant.modifyWith")}
          </button>
        )}
      </div>
    </section>
  );
}

function ToolIcon({ name }: { name: string }): JSX.Element {
  const strokes: Record<string, JSX.Element> = {
    select: <path d="M4 2l10 5.5-4.2 1.2L12 13l-2 1.4-2.2-4.3-3.8 2.9z" />,
    split_v: <path d="M3 3h10v10H3z M8 3v10" />,
    split_h: <path d="M3 3h10v10H3z M3 8h10" />,
    couple_left: <path d="M6 3h7v10H6z M5.5 8H1 M2.5 5.5L1 8l1.5 2.5" />,
    couple_right: <path d="M3 3h7v10H3z M10.5 8H15 M13.5 5.5L15 8l-1.5 2.5" />,
    equalize: <path d="M3 5h10 M8 2.5L10.5 5 8 7.5 M3 11h10 M8 8.5L10.5 11 8 13.5" />,
    tree: <path d="M4 3h9 M4 8h9 M4 13h9 M1 3h.5 M1 8h.5 M1 13h.5" />,
  };
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="tool-icon">
      {strokes[name]}
    </svg>
  );
}

export function AssemblyEditor({
  organizationId,
  couplerSkus,
  glassSkus,
  panelSkus,
  options,
  disabled,
  onChanged,
  onEvaluationChange,
  positionId,
  positionPanel,
  contentEpoch = 0,
  optionsReady = options !== undefined,
}: {
  organizationId: string;
  couplerSkus: string[];
  glassSkus: string[];
  panelSkus: string[];
  options: DesignOptions | undefined;
  disabled: boolean;
  onChanged(): void;
  onEvaluationChange(evaluation: EngineAssemblyCalculateResponse | null): void;
  positionId: string | null;
  positionPanel?: JSX.Element;
  /** Bumped when the product is replaced wholesale (starter pick) so the
   * canvas viewport re-fits even after the user took manual pan/zoom control. */
  contentEpoch?: number;
  /** The system's design options have hydrated (or errored) — paid AI
   * generation must not start on an empty catalog signature. Defaults to
   * the options value's presence for callers without a loading state. */
  optionsReady?: boolean;
}): JSX.Element | null {
  const inputs = useCanvasStore((state) => state.inputs);
  const commitInputs = useCanvasStore((state) => state.commitInputs);
  const selection = useCanvasStore((state) => state.selection);
  const select = useCanvasStore((state) => state.select);
  const undoHistory = useCanvasStore((state) => state.undo);
  const redoHistory = useCanvasStore((state) => state.redo);
  const canUndo = useCanvasStore((state) => state.past.length > 0);
  const canRedo = useCanvasStore((state) => state.future.length > 0);
  const specClipboard = useCanvasStore((state) => state.specClipboard);
  const lastMutation = useCanvasStore((state) => state.lastMutation);
  const product = inputs.product;
  const { evaluation, isPending, errorCode } = useAssemblyCalculation(organizationId, inputs);
  const issues = evaluation?.issues ?? [];
  const members = useMemo(() => resolveMembers(options), [options]);
  const [tool, setTool] = useState<EditorTool>("select");
  const [treeOpen, setTreeOpen] = useState(true);
  /** Right-rail detail level — overview/design/technical over the same
   * selection; complexity stays hidden until the user asks for it. */
  const [detail, setDetail] = useState<DetailLevel>("design");
  const [planOpen, setPlanOpen] = useState(true);
  const [view3dOpen, setView3dOpen] = useState(false);
  /** Queued prompt for the assistant — "" means focus only. Every "…with
   * DEKOPEN" affordance funnels here; the human always confirms. */
  const [assistantDraft, setAssistantDraft] = useState<string | null>(null);
  const assistantSectionRef = useRef<HTMLDivElement>(null);
  const issuesListRef = useRef<HTMLUListElement>(null);
  /** Canvas context menu — cursor position, closed on action/outside/Escape. */
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const contextMenuRef = useRef<HTMLDivElement | null>(null);
  /** Measured on-screen position — null until the first layout pass, so the
   * menu can flip away from viewport edges instead of overflowing them. */
  const [contextMenuPos, setContextMenuPos] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (!contextMenu) {
      setContextMenuPos(null);
      return;
    }
    const menu = contextMenuRef.current;
    if (!menu) return;
    const rect = menu.getBoundingClientRect();
    setContextMenuPos({
      left: Math.max(0, Math.min(contextMenu.x, window.innerWidth - rect.width)),
      top: Math.max(0, Math.min(contextMenu.y, window.innerHeight - rect.height)),
    });
    menu.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  }, [contextMenu]);

  useEffect(() => {
    onEvaluationChange(evaluation);
  }, [evaluation, onEvaluationChange]);

  /** Every "…with DEKOPEN" affordance: scroll the assistant into view and
   * hand it a prompt draft — "" focuses the field untouched. */
  function askAssistant(prompt: string): void {
    assistantSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setAssistantDraft(prompt);
  }

  useEffect(() => {
    if (!contextMenu) return;
    function dismiss(): void {
      setContextMenu(null);
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") dismiss();
    }
    window.addEventListener("mousedown", dismiss);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", dismiss);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [contextMenu]);

  function commit(next: ProductJson): void {
    if (next === product) return;
    // Any product edit ends modal tool state — an armed divide must not
    // survive an unrelated edit and surprise the next module click.
    setTool("select");
    commitInputs({ ...inputs, product: next });
    onChanged();
  }

  // The agent dock's ops bridge: publishes the live product plus an apply
  // channel that commits through the same registry path as a human click.
  // The hook forwards calls to the latest closure, so capturing `product` and
  // `commit` always lands on the current product — and the published product
  // re-registers on every commit so a stale-product apply is refused.
  useRegisterDesignOpsBridge(
    product && !disabled ? (product as unknown as { [key: string]: unknown }) : null,
    product && !disabled
      ? (ops: DesignOp[]) => {
          if (product) commit(applyDesignOps(product, ops));
        }
      : null,
  );

  if (!product) {
    return (
      <section className="assembly-editor assembly-editor--empty">
        <div className="assembly-canvas canvas-empty">
          <p className="assembly-hint">{t("assembly.pickStarter")}</p>
        </div>
        <aside className="assembly-side">
          {positionPanel ?? <p className="assembly-hint">{t("assembly.elementHint")}</p>}
        </aside>
      </section>
    );
  }
  const productJson = product;
  const modules = product.assembly.modules;
  const couplings = product.assembly.couplings;
  const selectedModule = modules.find((module) => module.id === selection);
  const selectedCoupling = couplings.find((coupling) => coupling.id === selection);
  // Leaf granularity: canvas bay clicks and tree leaf rows select the
  // composite "moduleId/bayId" — resolved back into (module, bay node) here.
  const treeSelection = selection?.includes("/") ? selection.split("/") : null;
  const selectedTreeModule = treeSelection
    ? modules.find((module) => module.id === treeSelection[0])
    : undefined;
  const selectedNode = (() => {
    if (!treeSelection || !selectedTreeModule || treeSelection[1] === undefined) return null;
    return findNode(selectedTreeModule.tree, treeSelection[1]);
  })();
  const selectedBayModule = selectedNode?.type === "BAY" ? selectedTreeModule : undefined;
  const selectedBayNode = selectedNode?.type === "BAY" ? selectedNode : null;
  const selectedDivisionModule =
    selectedNode && (selectedNode.type === "SPLIT_V" || selectedNode.type === "SPLIT_H")
      ? selectedTreeModule
      : undefined;
  const selectedDivisionNode = selectedDivisionModule ? selectedNode : null;
  // isPending also holds while the query is disabled (no system/product yet).
  // Evaluation is non-blocking: an in-flight recalc keeps the canvas live —
  // react-query keys on the product so stale results never land on newer
  // state, and save still requires the fresh engine verdict upstream.
  const evaluating = isPending && inputs.systemId !== null;
  const busy = disabled;
  const mullionSkus: Partial<Record<SplitType, string>> = useMemo(
    () => ({
      SPLIT_V: options?.profiles.find((profile) => profile.role === "MULLION_V")?.sku,
      SPLIT_H: options?.profiles.find((profile) => profile.role === "MULLION_H")?.sku,
    }),
    [options],
  );

  // One layout pass per product commit — bounds/selection boxes derive from
  // the memo instead of recomputing the elevation four times per render.
  const front = useMemo(() => frontLayout(product), [product]);
  const frontBox = useMemo(() => frontBounds(front), [front]);
  const planBox = couplings.length > 0 && evaluation?.plan ? planBounds(evaluation.plan) : null;
  const selectionBox = useMemo(
    () => frontModuleBox(front, selectedModule?.id ?? null),
    [front, selectedModule?.id],
  );

  // The shared command registry: palette, keyboard and AI all dispatch the
  // same typed commands; `commit` inside is the single undoable transaction.
  const commandCtx = useMemo<CommandContext>(
    () => ({
      product,
      selection,
      catalog: {
        glassThicknesses: options?.glazing_thicknesses ?? [],
        glassSkus,
        couplerSkus,
        panelSkus,
        mullionSkus,
      },
      disabled: busy,
      commit,
      select,
      setTool,
      focusAssistant: () => askAssistant(""),
      undo: () => {
        if (useCanvasStore.getState().past.length === 0) return;
        undoHistory();
        onChanged();
      },
      redo: () => {
        if (useCanvasStore.getState().future.length === 0) return;
        redoHistory();
        onChanged();
      },
      canUndo,
      canRedo,
      specClipboard,
      writeSpecClipboard: useCanvasStore.getState().setSpecClipboard,
      lastMutation,
      recordMutation: useCanvasStore.getState().recordMutation,
    }),
    // `commit` is re-declared per render and always sees current inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      product,
      selection,
      options,
      glassSkus,
      couplerSkus,
      panelSkus,
      mullionSkus,
      busy,
      select,
      undoHistory,
      redoHistory,
      canUndo,
      canRedo,
      specClipboard,
      lastMutation,
    ],
  );
  const surface = useMemo(
    () => ({ commands: resolveCommands(commandCtx, assemblyCommands(commandCtx)) }),
    [commandCtx],
  );
  useRegisterCommands(surface);
  useCommandShortcuts(surface);
  const statusText = `${front.totalW.toFixed(0)} × ${front.height.toFixed(0)} mm`;
  // Labels derive from actual product membership — selection ids are
  // arbitrary strings, so a coupling legitimately named "coupling-x" must
  // still resolve (prefix sniffing would hide it).
  const bayOrdinal =
    selectedBayModule && selectedBayNode
      ? intentBays(selectedBayModule.tree).findIndex((node) => node.id === selectedBayNode.id) + 1
      : 0;
  const selectedLabel = selectedModule
    ? `${t("assembly.module")} ${modules.findIndex((item) => item.id === selection) + 1}`
    : selectedBayModule && selectedBayNode
      ? `${t("assembly.bay")} ${bayOrdinal} · ${t("assembly.module")} ${modules.findIndex((item) => item.id === selectedBayModule.id) + 1}`
      : selectedDivisionModule && selectedDivisionNode
        ? `${selectedDivisionNode.type === "SPLIT_V" ? t("assembly.mullionV") : t("assembly.transomH")} · ${t("assembly.module")} ${modules.findIndex((item) => item.id === selectedDivisionModule.id) + 1}`
        : selectedCoupling
          ? `${t("assembly.coupling")} ${couplings.findIndex((item) => item.id === selection) + 1}`
          : null;

  const divideToolType = tool === "split_v" ? "SPLIT_V" : tool === "split_h" ? "SPLIT_H" : null;

  // Divide tool: a canvas click splits the module at the cursor offset
  // (direct manipulation), a tree click splits it at the center.
  function pickModule(id: string): void {
    const sku =
      divideToolType === "SPLIT_V"
        ? mullionSkus.SPLIT_V
        : divideToolType === "SPLIT_H"
          ? mullionSkus.SPLIT_H
          : undefined;
    if (divideToolType !== null && sku !== undefined) {
      commit(splitModuleBay(productJson, id, { type: divideToolType, mullionSku: sku }, members));
      setTool("select");
    }
    select(id);
  }

  function divideModule(id: string, bayId: string | null, offsetMm?: string): void {
    const sku =
      divideToolType === "SPLIT_V"
        ? mullionSkus.SPLIT_V
        : divideToolType === "SPLIT_H"
          ? mullionSkus.SPLIT_H
          : undefined;
    if (divideToolType === null || sku === undefined) {
      select(id);
      return;
    }
    commit(
      splitModuleBay(
        productJson,
        id,
        {
          type: divideToolType,
          mullionSku: sku,
          bayId: bayId ?? undefined,
          offsetMm,
        },
        members,
      ),
    );
    setTool("select");
    select(id);
  }
  const objectTree = useMemo(
    () => buildObjectTree(product, members, issues, t),
    [product, members, issues],
  );

  function coupleUnit(side: "left" | "right"): void {
    const next = addAdjacentUnit(productJson, side);
    commit(next);
    select(
      next.assembly.modules[side === "left" ? 0 : next.assembly.modules.length - 1]?.id ?? null,
    );
  }

  const splitReady = { SPLIT_V: mullionSkus.SPLIT_V, SPLIT_H: mullionSkus.SPLIT_H };
  return (
    <div
      className={`assembly-editor${treeOpen ? "" : " assembly-editor--tree-closed"}`}
      aria-label={t("assembly.frontView")}
    >
      <div className="assembly-tools" role="toolbar" aria-label={t("assembly.tools")}>
        <button
          type="button"
          className={`tool-button${tool === "select" ? " is-active" : ""}`}
          title={t("assembly.toolSelect")}
          aria-label={t("assembly.toolSelect")}
          aria-pressed={tool === "select"}
          onClick={() => setTool("select")}
        >
          <ToolIcon name="select" />
        </button>
        <button
          type="button"
          className={`tool-button${tool === "split_v" ? " is-active" : ""}`}
          title={t("assembly.toolDivideV")}
          aria-label={t("assembly.toolDivideV")}
          aria-pressed={tool === "split_v"}
          disabled={busy || splitReady.SPLIT_V === undefined}
          onClick={() => setTool(tool === "split_v" ? "select" : "split_v")}
        >
          <ToolIcon name="split_v" />
        </button>
        <button
          type="button"
          className={`tool-button${tool === "split_h" ? " is-active" : ""}`}
          title={t("assembly.toolDivideH")}
          aria-label={t("assembly.toolDivideH")}
          aria-pressed={tool === "split_h"}
          disabled={busy || splitReady.SPLIT_H === undefined}
          onClick={() => setTool(tool === "split_h" ? "select" : "split_h")}
        >
          <ToolIcon name="split_h" />
        </button>
        <span className="assembly-tools__divider" aria-hidden="true" />
        <button
          type="button"
          className="tool-button"
          title={t("assembly.addUnitLeft")}
          aria-label={t("assembly.addUnitLeft")}
          disabled={busy}
          onClick={() => coupleUnit("left")}
        >
          <ToolIcon name="couple_left" />
        </button>
        <button
          type="button"
          className="tool-button"
          title={t("assembly.addUnitRight")}
          aria-label={t("assembly.addUnitRight")}
          disabled={busy}
          onClick={() => coupleUnit("right")}
        >
          <ToolIcon name="couple_right" />
        </button>
        <span className="assembly-tools__divider" aria-hidden="true" />
        <button
          type="button"
          className="tool-button"
          title={t("assembly.equalizeModules")}
          aria-label={t("assembly.equalizeModules")}
          disabled={busy || modules.length <= 1}
          onClick={() => commit(equalizeModuleWidths(product))}
        >
          <ToolIcon name="equalize" />
        </button>
        <button
          type="button"
          className="tool-button"
          title={t("assembly.equalizeAngles")}
          aria-label={t("assembly.equalizeAngles")}
          disabled={busy || couplings.length === 0}
          onClick={() => commit(equalizeCouplingAngles(product))}
        >
          <ToolIcon name="equalize" />
        </button>
        <span className="assembly-tools__spacer" aria-hidden="true" />
        <button
          type="button"
          className={`tool-button${treeOpen ? " is-active" : ""}`}
          title={t("assembly.toggleTree")}
          aria-label={t("assembly.toggleTree")}
          aria-pressed={treeOpen}
          onClick={() => setTreeOpen((open) => !open)}
        >
          <ToolIcon name="tree" />
        </button>
      </div>
      {treeOpen && (
        <div className="assembly-tree">
          <ObjectTree
            root={objectTree}
            selection={selection}
            onSelect={(id) => {
              if (id !== null && modules.some((module) => module.id === id)) pickModule(id);
              else select(id);
            }}
            title={t("tree.title")}
          />
        </div>
      )}
      <div
        className="assembly-canvas"
        onContextMenu={(event) => {
          event.preventDefault();
          setContextMenu({ x: event.clientX, y: event.clientY });
        }}
        onKeyDown={(event) => {
          // Keyboard context-menu trigger — Shift+F10 or the dedicated
          // ContextMenu key opens the same menu, centered on the canvas.
          if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
            event.preventDefault();
            const rect = event.currentTarget.getBoundingClientRect();
            setContextMenu({
              x: rect.left + rect.width / 2,
              y: rect.top + rect.height / 2,
            });
          }
        }}
      >
        <CanvasViewport
          contentBox={frontBox}
          selectionBox={selectionBox}
          status={statusText}
          contentEpoch={contentEpoch}
        >
          <ProductFrontContent
            product={product}
            members={members}
            selectedId={selectedModule?.id ?? null}
            issues={issues}
            disabled={busy}
            divideTool={divideToolType}
            dimLevel={detail}
            onSelectModule={pickModule}
            onSelectBay={(moduleId, bayId) => select(`${moduleId}/${bayId}`)}
            onSelectDivision={(moduleId, divisionId) => select(`${moduleId}/${divisionId}`)}
            onSelectCoupling={(couplingId) => select(couplingId)}
            selectedBayId={selectedBayModule && selectedBayNode ? selectedBayNode.id : null}
            selectedDivisionId={
              selectedDivisionModule && selectedDivisionNode ? selectedDivisionNode.id : null
            }
            onContextMenuModule={(moduleId, pos) => {
              select(moduleId);
              setContextMenu(pos);
            }}
            onAddUnit={coupleUnit}
            onCommitModuleWidth={(moduleId, widthMm) =>
              commit(setModuleWidth(product, moduleId, widthMm))
            }
            onCommitTotalWidth={(totalMm) => commit(scaleModuleWidths(product, totalMm))}
            onCommitHeight={(heightMm) => commit(setAllModuleHeights(product, heightMm))}
            onCommitDivide={divideModule}
            onMoveDivision={(moduleId, divisionId, offsetMm) =>
              commit(moveModuleDivision(product, moduleId, divisionId, offsetMm))
            }
            onResizeSeam={(index, deltaMm) => commit(resizeModuleSeam(product, index, deltaMm))}
          />
        </CanvasViewport>
        {couplings.length > 0 && evaluation?.plan && planBox && planOpen && (
          <div className="plan-inset" role="complementary" aria-label={t("assembly.planView")}>
            <div className="plan-inset__header">
              <span>{t("assembly.planView")}</span>
              <button
                type="button"
                aria-label={t("assembly.hidePlan")}
                onClick={() => setPlanOpen(false)}
              >
                ×
              </button>
            </div>
            <svg
              className="plan-inset__svg"
              viewBox={`${planBox.x} ${planBox.y} ${planBox.w} ${planBox.h}`}
              preserveAspectRatio="xMidYMid meet"
              role="img"
              aria-label={t("assembly.planView")}
            >
              <BowPlanContent
                plan={evaluation.plan}
                couplings={couplings}
                members={members}
                selectedModuleId={selectedModule?.id ?? null}
                selectedCouplingId={selectedCoupling?.id ?? null}
                issues={issues}
                disabled={busy}
                onSelectModule={pickModule}
                onSelectCoupling={select}
                onContextMenuElement={(elementId, pos) => {
                  select(elementId);
                  setContextMenu(pos);
                }}
                onCommitAngle={(couplingId, angleDeg) =>
                  commit(setCouplingAngle(product, couplingId, angleDeg))
                }
              />
            </svg>
          </div>
        )}
        {couplings.length > 0 && evaluation?.plan && !planOpen && (
          <button type="button" className="plan-toggle" onClick={() => setPlanOpen(true)}>
            {t("assembly.planView")}
          </button>
        )}
        {view3dOpen ? (
          <div className="model3d-inset" role="complementary" aria-label={t("assembly.view3d")}>
            <div className="plan-inset__header">
              <span>{t("assembly.view3d")}</span>
              <button
                type="button"
                aria-label={t("assembly.hide3d")}
                onClick={() => setView3dOpen(false)}
              >
                ×
              </button>
            </div>
            <Suspense
              fallback={
                <div className="model3d-loading" role="status">
                  <span className="model3d-loading__bar" aria-hidden="true" />
                  {t("assembly.loading3d")}
                </div>
              }
            >
              <Model3DView
                product={product}
                members={members}
                plan={evaluation?.plan ?? null}
                selection={selection}
                onSelectModule={pickModule}
                onSelectBay={(moduleId, bayId) => select(`${moduleId}/${bayId}`)}
                onSelectCoupling={select}
              />
            </Suspense>
          </div>
        ) : (
          <button type="button" className="model3d-toggle" onClick={() => setView3dOpen(true)}>
            {t("assembly.view3d")}
          </button>
        )}
      </div>
      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="context-menu"
          role="menu"
          style={{
            left: contextMenuPos?.left ?? contextMenu.x,
            top: contextMenuPos?.top ?? contextMenu.y,
            visibility: contextMenuPos ? "visible" : "hidden",
          }}
          onMouseDown={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.preventDefault()}
          onKeyDown={(event) => {
            // APG menu contract — arrows cycle, Home/End jump, Esc closes.
            if (
              event.key !== "ArrowDown" &&
              event.key !== "ArrowUp" &&
              event.key !== "Home" &&
              event.key !== "End"
            ) {
              return;
            }
            const items = Array.from(
              event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'),
            );
            if (!items.length) return;
            event.preventDefault();
            const index = items.indexOf(document.activeElement as HTMLElement);
            const next =
              event.key === "Home"
                ? items[0]
                : event.key === "End"
                  ? items[items.length - 1]
                  : items[
                      (index + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length
                    ];
            next?.focus();
          }}
        >
          {surface.commands
            .filter((command) => !command.params?.length)
            .map((command) => (
              <button
                key={command.id}
                type="button"
                role="menuitem"
                className="context-menu__item"
                onClick={() => {
                  command.run({});
                  setContextMenu(null);
                }}
              >
                <span className="context-menu__label">{command.title}</span>
                {command.shortcut && (
                  <kbd className="context-menu__hint">{formatShortcut(command.shortcut)}</kbd>
                )}
              </button>
            ))}
          {selectedLabel && (
            <button
              type="button"
              role="menuitem"
              className="context-menu__item context-menu__item--assistant"
              onClick={() => {
                askAssistant(t("assistant.modifyPrompt").replace("{target}", selectedLabel));
                setContextMenu(null);
              }}
            >
              {t("assistant.modifyWith")}
            </button>
          )}
        </div>
      )}
      <div className="assembly-side">
        <div className="detail-levels" role="group" aria-label={t("assembly.detailLevels")}>
          {DETAIL_LEVELS.map(({ level, labelKey }) => (
            <button
              key={level}
              type="button"
              className={`detail-levels__btn${detail === level ? " is-active" : ""}`}
              aria-pressed={detail === level}
              onClick={() => setDetail(level)}
            >
              {t(labelKey)}
            </button>
          ))}
        </div>
        {issues.length > 0 && (
          <ul className="assembly-issues" aria-label={t("assembly.issues")} ref={issuesListRef}>
            {issues.map((issue, index) => (
              <li key={`${issue.code}-${index}`}>
                <button
                  type="button"
                  className={`issue-chip issue-chip--${issue.severity}`}
                  onClick={() => {
                    const target = issue.target;
                    if (target.startsWith("module:") || target.startsWith("coupling:")) {
                      select(target.slice(target.indexOf(":") + 1));
                    }
                  }}
                >
                  {issueText(issue, modules, couplings)}
                </button>
                <button
                  type="button"
                  className="issue-fix"
                  title={t("assistant.fixWith")}
                  onClick={() =>
                    askAssistant(
                      `${t("assistant.fixPrompt")} ${issueText(issue, modules, couplings)}`,
                    )
                  }
                >
                  {t("assistant.fixWith")}
                </button>
              </li>
            ))}
          </ul>
        )}
        {detail === "technical" ? (
          <TechnicalPanel
            evaluation={evaluation}
            moduleId={selectedBayModule?.id ?? selectedModule?.id}
            bayId={selectedBayNode && selectedBayModule ? selectedBayNode.id : null}
            moduleIndex={(moduleId) => modules.findIndex((module) => module.id === moduleId) + 1}
            members={members}
            bayNode={selectedBayNode}
            widthMm={Number((selectedBayModule ?? selectedModule)?.width_mm) || undefined}
          />
        ) : detail === "overview" ? (
          selectedModule ? (
            <ElementSummary
              title={selectedLabel ?? t("assembly.module")}
              rows={[
                [
                  t("inspector.dimensions"),
                  `${Number(selectedModule.width_mm).toFixed(0)} × ${Number(selectedModule.height_mm).toFixed(0)} mm`,
                ],
                [
                  t("assembly.opening"),
                  t(
                    OPENING_OPTIONS.find(
                      ([value]) => value === moduleOpening(selectedModule),
                    )?.[1] ?? "intent.fixed",
                  ),
                ],
                [t("assembly.bayCount"), String(intentBays(selectedModule.tree).length)],
                [
                  t("assembly.glass"),
                  [moduleGlassThicknessMm(selectedModule), moduleGlassSku(selectedModule)]
                    .filter((value): value is string => value !== null && value !== "")
                    .join(" · ") || "—",
                ],
              ]}
            />
          ) : selectedBayModule && selectedBayNode ? (
            <ElementSummary
              title={selectedLabel ?? t("assembly.bay")}
              rows={[
                [
                  t("assembly.opening"),
                  t(
                    OPENING_OPTIONS.find(
                      ([value]) => value === (selectedBayNode.opening_type ?? "FIXED"),
                    )?.[1] ?? "intent.fixed",
                  ),
                ],
                [
                  t("assembly.glass"),
                  [selectedBayNode.glass_thickness_mm, selectedBayNode.glass_article_sku]
                    .filter((value): value is string => value != null && value !== "")
                    .join(" · ") || "—",
                ],
                [
                  t("quotation.handleHeight"),
                  selectedBayNode.handle_height_mm
                    ? `${fmtMm(selectedBayNode.handle_height_mm)} mm`
                    : "—",
                ],
                ...(selectedBayNode.opening_type === "DOOR_ENTRY"
                  ? [
                      [t("assembly.panel"), selectedBayNode.panel_article_sku ?? "—"] as [
                        string,
                        string,
                      ],
                      [
                        t("assembly.hingeSide"),
                        selectedBayNode.door_handedness === "RIGHT"
                          ? t("assembly.hingeRight")
                          : t("assembly.hingeLeft"),
                      ] as [string, string],
                    ]
                  : []),
              ]}
            />
          ) : selectedCoupling ? (
            <ElementSummary
              title={selectedLabel ?? t("assembly.coupling")}
              rows={[
                [t("assembly.angle"), `${selectedCoupling.angle_deg}°`],
                [t("assembly.coupler"), selectedCoupling.coupler_profile_sku ?? "—"],
              ]}
            />
          ) : (
            (positionPanel ?? (
              <section className="assembly-inspector">
                <p className="assembly-hint">{t("assembly.elementHint")}</p>
              </section>
            ))
          )
        ) : selectedModule ? (
          <ModuleInspector
            module={selectedModule}
            product={product}
            members={members}
            glassSkus={glassSkus}
            glassSpecs={options?.glass_specs ?? []}
            glazingThicknesses={options?.glazing_thicknesses ?? []}
            panelSkus={panelSkus}
            mullionSkus={mullionSkus}
            couplerSkus={couplerSkus}
            busy={busy}
            commit={commit}
            onAskAssistant={
              selectedLabel
                ? () => askAssistant(t("assistant.modifyPrompt").replace("{target}", selectedLabel))
                : undefined
            }
          />
        ) : selectedBayModule && selectedBayNode ? (
          <BayInspector
            module={selectedBayModule}
            bay={selectedBayNode}
            product={product}
            glassSkus={glassSkus}
            glassSpecs={options?.glass_specs ?? []}
            glazingThicknesses={options?.glazing_thicknesses ?? []}
            panelSkus={panelSkus}
            busy={busy}
            commit={commit}
            onAskAssistant={
              selectedLabel
                ? () => askAssistant(t("assistant.modifyPrompt").replace("{target}", selectedLabel))
                : undefined
            }
          />
        ) : selectedDivisionModule && selectedDivisionNode ? (
          <DivisionInspector
            module={selectedDivisionModule}
            division={selectedDivisionNode}
            product={product}
            busy={busy}
            commit={commit}
            onSelect={(id) => select(id)}
            onAskAssistant={
              selectedLabel
                ? () => askAssistant(t("assistant.modifyPrompt").replace("{target}", selectedLabel))
                : undefined
            }
          />
        ) : selectedCoupling ? (
          <CouplingInspector
            coupling={selectedCoupling}
            product={product}
            ordinal={couplings.findIndex((item) => item.id === selectedCoupling.id) + 1}
            couplerSkus={couplerSkus}
            busy={busy}
            commit={commit}
            onAskAssistant={
              selectedLabel
                ? () => askAssistant(t("assistant.modifyPrompt").replace("{target}", selectedLabel))
                : undefined
            }
          />
        ) : (
          <section className="assembly-inspector">
            <p className="assembly-hint">{t("assembly.elementHint")}</p>
          </section>
        )}
        {product && (
          <div ref={assistantSectionRef}>
            <AssistantPanel
              organizationId={organizationId}
              positionId={positionId}
              systemId={inputs.systemId}
              product={product}
              disabled={disabled}
              draft={assistantDraft}
              onDraftHandled={() => setAssistantDraft(null)}
              onApply={(ops) => commit(applyDesignOps(product, ops))}
            />
            <AlternativesPanel
              organizationId={organizationId}
              positionId={positionId}
              systemId={inputs.systemId}
              product={product}
              members={members}
              disabled={disabled}
              onUse={(next) => commit(next)}
              catalogReady={optionsReady}
              catalogKey={[
                ...(options?.glass_skus ?? []),
                ...(options?.panel_skus ?? []),
                ...(options?.coupler_skus ?? []),
                ...(options?.glazing_thicknesses ?? []),
                // Recipes are catalog authority too — a composition edit
                // makes old cards stale and new generations a new request.
                ...(options?.glass_specs ?? []).map((item) => `${item.sku}=${item.spec}`),
              ]
                .sort()
                .join("|")}
            />
          </div>
        )}
      </div>
      <footer className="assembly-statusbar">
        <span
          className={`assembly-status assembly-status--${
            inputs.systemId === null ? "idle" : (evaluation?.status ?? "INVALID").toLowerCase()
          }`}
          data-testid="assembly-status"
        >
          {evaluating
            ? t("assembly.calculating")
            : inputs.systemId === null
              ? t("assembly.chooseSystemHint")
              : errorCode
                ? t("assembly.calculateError")
                : t(statusKey(evaluation?.status))}
        </span>
        <span className="assembly-statusbar__dims">{statusText}</span>
        {selectedLabel && <span className="assembly-statusbar__selection">{selectedLabel}</span>}
        {issues.length > 0 && (
          <button
            type="button"
            className="assembly-statusbar__issues"
            onClick={() => {
              const first = issues[0];
              if (
                first &&
                (first.target.startsWith("module:") || first.target.startsWith("coupling:"))
              ) {
                select(first.target.slice(first.target.indexOf(":") + 1));
              }
              // The list sits at the top of the inspector column — surface
              // it so the click visibly resolves to the issues, not silence.
              issuesListRef.current?.scrollIntoView({
                behavior: "smooth",
                block: "nearest",
              });
            }}
          >
            {t("assembly.issueCount").replace("{count}", String(issues.length))}
          </button>
        )}
      </footer>
    </div>
  );
}
