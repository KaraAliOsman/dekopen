import {
  fmtMm,
  formatMoney,
  parseLocaleNumber,
  fmtMmCanonical,
  formatDims,
  fmtWire,
} from "../../format";
import {
  lazy,
  Suspense,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import "./canvas.css";

import type {
  DesignOptions,
  EngineAssemblyCalculateResponse,
  GlassProductChoice,
  GlassSafetyFinding,
  GlassSpecChoice,
  HardwareFamily,
  HardwareItem,
  HardwareOption,
  KitChoice,
  OpeningOption,
  PanelChoice,
  ProductIssue,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import {
  formatShortcut,
  resolveCommands,
  useCommandShortcuts,
  useRegisterCommands,
} from "../commands/registry";
import type { CommandContext, CommandProposal, EditorTool } from "../commands/types";
import { Drawer, Menu, Popover } from "../../ui";
import { useMediaQuery } from "../../utils/useMediaQuery";
import { useCanvasStore } from "./canvasStore";
import { assemblyCommands } from "./assemblyCommands";
import { AlternativesPanel } from "./AlternativesPanel";
import { AssistantPanel } from "./AssistantPanel";
import { applyDesignOps } from "./designOps";
import { GhostLayer, ProposalBar } from "./ProposalGhost";
import { MeasureChip, MeasureLayer, type MeasurePoint } from "./MeasureLayer";
import { OpeningGrid } from "./OpeningGrid";
import { ShortcutsDialog } from "./ShortcutsDialog";
import { TypologyFlyout } from "./TypologyFlyout";
import type { StarterDefinition } from "./designLibrary";
import type { ViewTransform } from "./viewport";
import { useRegisterDesignOpsBridge } from "../assistant/assistantContext";
import type { DesignOp } from "../commands/types";
import { BowPlanContent, planBounds, planMeasures } from "./BowPlanSvg";
import { CanvasViewport } from "./CanvasViewport";
import { ObjectTree } from "./ObjectTreeView";
import { buildObjectTree } from "./objectTree";
import { finishForSelection } from "./finishes";
import { couplerFitsAngle, resolveMembers, tintMembers, type MemberGeometry } from "./members";
import {
  autoPickKit,
  bayEnvelopeMm,
  normalizedOpening,
  rankKits,
  resolveComponent,
  suggestUpgrade,
} from "./kitCompatibility";
import { SectionView } from "./SectionView";
import { SectionPreviewSvg } from "./SectionPreviewSvg";
import { GlazingPicker, type GlazingPatch } from "./GlazingPicker";
import {
  frontBounds,
  frontLayout,
  frontModuleBox,
  ProductFrontContent,
  technicalExtraBottom,
  type VanoDim,
} from "./ProductFrontSvg";

import { useAssemblyCalculation } from "./useAssemblyCalculation";
import type {
  IntentNode,
  Opening,
  OpeningChoice,
  SlidingLayout,
  SlidingTravel,
  SplitType,
} from "./intentEditing";
import {
  bayIsDoor,
  bayKitGroup,
  bayOperable,
  changeOpening,
  findNode,
  intentBays,
  isSlidingOpening,
  nodeSpecKey,
  OPTION_SPEC_KEY,
  panelTravel,
  resolvedSlidingLayout,
  topIntent,
  updateBay,
} from "./intentEditing";
import {
  addAdjacentUnit,
  canRemoveModuleDivision,
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
  setModuleGlazing,
  setModuleHeight,
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
  coupler_angle_incompatible: "assembly.issue.couplerAngleIncompatible",
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
  member_exceeds_stock: "assembly.issue.memberExceedsStock",
  hardware_kit_incompatible: "assembly.issue.hardwareKitIncompatible",
  hardware_kit_overweight: "assembly.issue.hardwareKitOverweight",
  hardware_undecidable: "assembly.issue.hardwareUndecidable",
  glass_safety_finding: "assembly.issue.glassSafetyFinding",
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
  [/cannot travel toward a jamb/i, "assembly.reason.slidingJambTravel"],
  [/a FIXED panel declares no travel/i, "assembly.reason.slidingFixedTravel"],
  [/frame inset collapsed the glass pocket/i, "assembly.reason.glassPocketCollapsed"],
  [/handle height requires explicit/i, "assembly.reason.handleHeightMigration"],
  [/polishing authority/i, "assembly.reason.polishingAuthority"],
  [/requires policy placement/i, "assembly.reason.policyPlacement"],
  [/requires all four bead offsets/i, "assembly.reason.beadOffsets"],
  [/no compatible hardware kit/i, "assembly.reason.noHardwareKit"],
  [/hardware compatibility undecidable|leaf mass unknown/i, "assembly.reason.hardwareUndecidable"],
  [/ambiguous hardware kits/i, "assembly.reason.ambiguousHardware"],
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
    // Engine params arrive as str(Decimal) — "345.00" reads as technical
    // noise in a sentence; trim to the human form.
    const human = /^-?\d+\.\d+0*$/.test(value)
      ? value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "")
      : value;
    text = text.replace(`{${name}}`, human);
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

const MAX_MM = 30000;

function normalizeMm(candidate: string): string | null {
  const value = parseLocaleNumber(candidate);
  if (value === null || value <= 0 || value > MAX_MM) return null;
  return fmtWire(value);
}

function normalizeAngle(candidate: string): string | null {
  const value = parseLocaleNumber(candidate);
  // P06 — el rango llega hasta ±90° inclusive (esquina cuadrada); más allá
  // el módulo se repliega hacia atrás y el plano deja de ser legible.
  if (value === null || Math.abs(value) > 90) return null;
  return fmtWire(value, 1);
}

/** Contour coordinates are signed: zero/negative carry meaning (a vertical
 * side, an inward arc). Bounds keep the corner ordering the engine requires. */
function normalizeRange(candidate: string, min: number, max: number): string | null {
  const value = parseLocaleNumber(candidate);
  if (value === null || value < min || value >= max) return null;
  return fmtWire(value);
}

/* Pickers label an option the way an estimator reads the catalog — the
 * composition/panel name first, the SKU as the qualifier. A bare SKU
 * ("GLASS-BASE") forces decoding shorthand mid-design. */
function glassLabel(sku: string, specs: GlassSpecChoice[]): string {
  const spec = specs.find((item) => item.sku === sku)?.spec;
  return spec ? `${spec} · ${sku}` : sku;
}

function panelLabel(sku: string, choices: PanelChoice[]): string {
  const name = choices.find((item) => item.sku === sku)?.name;
  return name ? `${name} · ${sku}` : sku;
}

type DraftFieldProps = {
  label?: string;
  value: string;
  unit: string;
  disabled: boolean;
  onCommit(value: string): void;
  normalize(candidate: string): string | null;
  /** Constraint shown when Enter rejects the value (e.g. the ±90° band on
   * coupling angles) — a silent revert reads as the field ignoring input. */
  rejectHint?: string;
};

function DraftField({
  label,
  value,
  unit,
  disabled,
  onCommit,
  normalize,
  rejectHint,
}: DraftFieldProps): JSX.Element {
  const [draft, setDraft] = useState(value);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setDraft(value);
    setInvalid(false);
  }, [value]);

  return (
    <label className={`assembly-field${invalid ? " is-invalid" : ""}`}>
      {label ? <span>{label}</span> : null}
      <span className="assembly-input-wrap">
        <input
          value={draft}
          disabled={disabled}
          inputMode="decimal"
          aria-invalid={invalid || undefined}
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event) => {
            setDraft(event.target.value);
            setInvalid(false);
          }}
          onBlur={() => {
            const normalized = normalize(draft);
            if (normalized === null) {
              // Revert to the last valid value but keep the field flagged —
              // a silent snap-back reads as the input being ignored.
              setDraft(value);
              setInvalid(true);
            } else {
              if (normalized !== value) onCommit(normalized);
              setInvalid(false);
            }
          }}
          onKeyDown={(event) => {
            // Enter on an unparseable value keeps the field open and flags
            // it — reverting silently reads as the input being ignored.
            if (event.key === "Enter") {
              if (normalize(draft) === null) {
                setInvalid(true);
              } else {
                event.currentTarget.blur();
              }
            }
            if (event.key === "Escape") {
              setInvalid(false);
              setDraft(value);
            }
          }}
        />
        <span className="assembly-unit">{unit}</span>
      </span>
      {invalid ? (
        <span className="assembly-field-error" role="alert">
          {rejectHint ?? t("assembly.fieldRejected")}
        </span>
      ) : null}
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
            value={fmtMmCanonical(Number(contour.vertices[corners.leftIndex]!.x_mm))}
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
            value={fmtMmCanonical(widthMm - Number(contour.vertices[corners.rightIndex]!.x_mm))}
            unit="mm"
            disabled={busy}
            normalize={(candidate) => normalizeRange(candidate, 0, rightBound)}
            onCommit={(value) =>
              commit(
                setContourVertex(
                  product,
                  module.id,
                  corners.rightIndex,
                  fmtWire(widthMm - Number(value)),
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
            {panel.kind === "MOVING" && (
              <select
                // P05 — travel declarado: la flecha del alzado sigue esta
                // dirección en vista interior. Sin declaración la lámina
                // aplica la convención de presentación y la marca
                // "dirección inferida".
                aria-label={`${t("assembly.slidingPanel").replace("{index}", String(index + 1))} ${t("assembly.travelDirection")}`}
                value={panel.travel ?? ""}
                disabled={busy}
                title={panel.travel ? undefined : t("assembly.travelInferredHint")}
                onChange={(event) => {
                  const travel = (event.target.value || null) as SlidingTravel | null;
                  const panels = layout.panels.map((item, at) =>
                    at === index ? { ...item, travel } : item,
                  );
                  onChange({ ...layout, panels });
                }}
              >
                <option value="">
                  {t("assembly.travelInferred")} —{" "}
                  {panelTravel(panel, index, layout.panels.length) === "LEFT"
                    ? t("assembly.travelLeft")
                    : t("assembly.travelRight")}
                </option>
                <option value="LEFT">{t("assembly.travelLeft")}</option>
                <option value="RIGHT">{t("assembly.travelRight")}</option>
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
  glassProducts,
  glassFindings,
  glazingThicknesses,
  panelSkus,
  panelChoices,
  kits,
  hardwareFamilies,
  hardwareOptions,
  resolvedHardware,
  openingOptions,
  members,
  leafWeightKg,
  busy,
  commit,
  onAskAssistant,
}: {
  module: ProductModuleJson;
  bay: IntentNode;
  product: ProductJson;
  glassSkus: string[];
  glassSpecs: GlassSpecChoice[];
  glassProducts: GlassProductChoice[];
  /** Engine safety/type-limit findings the BOM resolved for this bay —
   * shown in the glazing section with the rule's own source_ref. */
  glassFindings: GlassSafetyFinding[];
  glazingThicknesses: string[];
  panelSkus: string[];
  panelChoices: PanelChoice[];
  kits: KitChoice[];
  /** D04 declared sellable catalogue: handle families by opening and the
   * position-level options the system offers. */
  hardwareFamilies: HardwareFamily[];
  hardwareOptions: HardwareOption[];
  /** Engine-emitted item for this bay — the resolved class/selection truth
   * after the last calculation; null before the first one. */
  resolvedHardware: HardwareItem | null;
  /** The system's declared opening repertoire (D03) — the grid only shows
   * what the catalog admits. Undefined (options not loaded) shows all. */
  openingOptions?: readonly OpeningOption[];
  members: MemberGeometry;
  /** Engine-resolved leaf mass; null = undecidable (never assumed). */
  leafWeightKg: number | null;
  busy: boolean;
  commit(next: ProductJson): void;
  onAskAssistant?(): void;
}): JSX.Element {
  const opening = bay.opening_type ?? "FIXED";
  const isDoor = bayIsDoor(module.tree, bay);
  const activeKey = nodeSpecKey(module.tree, bay);
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

  function pickGlazing(patch: GlazingPatch): void {
    if (patch.glass_article_sku) pushRecentGlass(patch.glass_article_sku);
    patchBay(patch);
  }

  function pickOpening(next: OpeningChoice): void {
    // changeOpening owns the normalization (spec payload vs legacy enum,
    // unit-kind lift for door options, stale layout/panel/handedness clear).
    if (next === "DOOR_ENTRY" && !isTopBay) return;
    // changeOpening owns the normalization (spec payload vs legacy enum,
    // unit-kind lift for door options, stale layout/panel/handedness clear,
    // hardware-selection clear — D04 selections are family-scoped).
    commit(setModuleTree(product, module.id, changeOpening(module.tree, bay.id, next)));
  }

  function toggleHardwareOption(sku: string, on: boolean): void {
    const current = bay.hardware_option_skus ?? [];
    const next = on ? [...new Set([...current, sku])] : current.filter((item) => item !== sku);
    patchBay({ hardware_option_skus: next.length > 0 ? next : null });
  }

  // Hardware picker context: bay envelope from the intent tree + the
  // engine's leaf mass. The select ranks valid kits first; incompatible
  // kits stay consultable with their reason but are not selectable as if
  // they were equivalent (mandate 04). The engine re-checks at save.
  const operable = bayOperable(bay) && !(isDoor && bay.panel_article_sku);
  const leafEnvelope = operable
    ? bayEnvelopeMm(module.tree, bay.id, Number(module.width_mm), Number(module.height_mm), {
        vertical: members.mullionV?.faceWidthMm ?? 0,
        horizontal: members.mullionH?.faceWidthMm ?? 0,
      })
    : null;
  const kitEvaluations = operable
    ? rankKits(kits, {
        opening: bayKitGroup(module.tree, bay),
        leafWidthMm: leafEnvelope ? Math.round(leafEnvelope.w * 10) / 10 : null,
        leafHeightMm: leafEnvelope ? Math.round(leafEnvelope.h * 10) / 10 : null,
        leafWeightKg,
      })
    : [];
  const selectableKits = kitEvaluations.filter((item) => item.fit !== "incompatible");
  const incompatibleKits = kitEvaluations.filter((item) => item.fit === "incompatible");
  const selectedKitEval = kitEvaluations.find((item) => item.kit.sku === bay.hardware_set_sku);

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
          // A panelled door leaf is complete without glass — name the panel,
          // not a "Sin definir Vidrio" chip for a leaf that has none.
          isDoor && bay.panel_article_sku
            ? { label: t("assembly.panel"), state: "VERIFIED" as const }
            : {
                label: t("assembly.glass"),
                state: bay.glass_article_sku
                  ? ("VERIFIED" as const)
                  : opening === "FIXED" || isDoor
                    ? ("UNKNOWN" as const)
                    : ("BLOCKED" as const),
              },
          {
            label: t("assembly.glassThickness"),
            state: bay.glass_thickness_mm ? "DECLARED" : "UNKNOWN",
          },
          {
            label: t("assembly.handleHeight"),
            state: bay.handle_height_mm ? "DECLARED" : "UNKNOWN",
          },
        ]}
      />
      <details className="inspector-section" open data-section="opening">
        <summary>{t("assembly.opening")}</summary>
        <OpeningGrid
          openingOptions={openingOptions}
          activeKey={activeKey}
          activeChoice={bay.opening_type ?? ""}
          busy={busy}
          doorBlocked={!isTopBay}
          onPick={pickOpening}
        />
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
      {operable && kits.length > 0 && (
        <details
          className="inspector-section"
          open={bay.hardware_set_sku != null}
          data-section="hardware"
        >
          <summary>{t("assembly.hardware")}</summary>
          {/* Clase resuelta — read-only for the basic user: the engine's
              pick or the declared kit, plus the F6 "why this kit" summary. */}
          {(() => {
            const resolvedEval = selectedKitEval ?? autoPickKit(kitEvaluations);
            if (!resolvedEval) return null;
            const upgrade = suggestUpgrade(kitEvaluations, resolvedEval);
            return (
              <div className="assembly-kit-summary">
                <p className="assembly-kit-class">
                  <span>{t("assembly.kitClass")}</span>:{" "}
                  {resolvedEval.kit.class_label ?? t("assembly.kitClassUnknown")}
                  {bay.hardware_set_sku == null && <small> · {t("assembly.kitClassAuto")}</small>}
                </p>
                <details className="assembly-kit-why">
                  <summary>{t("assembly.kitWhy")}</summary>
                  <p className="assembly-hint">
                    {resolvedEval.fit === "compatible"
                      ? t("assembly.kitWhyFits")
                      : resolvedEval.reasons
                          .map((reason) => t(`assembly.kitReason.${reason}` as TranslationKey))
                          .join(" · ")}
                  </p>
                  {resolvedEval.fit !== "compatible" && upgrade && (
                    <p className="assembly-hint" role="status">
                      {t("assembly.kitUpgrade").replace("{kit}", upgrade.kit.name)}
                      {" · "}
                      {upgrade.deltaClp !== null
                        ? t("assembly.kitUpgradeDelta").replace(
                            "{delta}",
                            formatMoney(String(upgrade.deltaClp), "CLP"),
                          )
                        : t("assembly.kitUpgradeDeltaUnknown")}
                    </p>
                  )}
                </details>
              </div>
            );
          })()}
          <label className="assembly-field">
            <span>{t("assembly.hardwareKit")}</span>
            <select
              aria-label={t("assembly.hardwareKit")}
              disabled={busy}
              value={bay.hardware_set_sku ?? ""}
              onChange={(event) => patchBay({ hardware_set_sku: event.target.value || null })}
            >
              <option value="">{t("assembly.hardwareAuto")}</option>
              {bay.hardware_set_sku != null &&
                !selectableKits.some((item) => item.kit.sku === bay.hardware_set_sku) && (
                  <option value={bay.hardware_set_sku}>{bay.hardware_set_sku}</option>
                )}
              {selectableKits.map((item) => (
                <option key={item.kit.sku} value={item.kit.sku}>
                  {item.kit.name}
                  {item.fit === "undecidable" ? ` · ${t("assembly.kitUndecidable")}` : ""}
                </option>
              ))}
            </select>
          </label>
          {selectedKitEval && selectedKitEval.fit !== "compatible" && (
            <p className="assembly-hint" role="status">
              {selectedKitEval.fit === "undecidable"
                ? t("assembly.kitUndecidableHint")
                : t("assembly.kitIncompatibleHint")}
              {" — "}
              {selectedKitEval.reasons
                .map((reason) => t(`assembly.kitReason.${reason}` as TranslationKey))
                .join(" · ")}
            </p>
          )}
          {incompatibleKits.length > 0 && (
            <ul
              className="assembly-kit-incompatible"
              aria-label={t("assembly.kitIncompatibleList")}
            >
              {incompatibleKits.map((item) => (
                <li key={item.kit.sku}>
                  <span>{item.kit.name}</span>
                  <small>
                    {item.reasons
                      .map((reason) => t(`assembly.kitReason.${reason}` as TranslationKey))
                      .join(" · ")}
                  </small>
                </li>
              ))}
            </ul>
          )}
          {/* D04 sellable selections — only what the family declares. */}
          {(() => {
            const family = hardwareFamilies.find(
              (item) => item.opening_type === normalizedOpening(opening),
            );
            const options = hardwareOptions.filter(
              (item) => item.opening_type === normalizedOpening(opening),
            );
            const declaredHeight = family
              ? {
                  min: Number(family.handle_height_min_mm ?? NaN),
                  max: Number(family.handle_height_max_mm ?? NaN),
                  rule: family.handle_height_rule,
                }
              : null;
            const declaredMm = Number(bay.handle_height_mm ?? NaN);
            const heightOutOfRange =
              Number.isFinite(declaredMm) &&
              declaredHeight != null &&
              Number.isFinite(declaredHeight.min) &&
              Number.isFinite(declaredHeight.max) &&
              (declaredMm < declaredHeight.min || declaredMm > declaredHeight.max);
            if (!family && options.length === 0) return null;
            return (
              <div className="inspector-subsection" data-section="handle">
                {family && family.handle_models.length > 0 && (
                  <label className="assembly-field">
                    <span>{t("assembly.handleModel")}</span>
                    <select
                      aria-label={t("assembly.handleModel")}
                      disabled={busy}
                      value={bay.handle_model_sku ?? ""}
                      onChange={(event) =>
                        patchBay({ handle_model_sku: event.target.value || null })
                      }
                    >
                      <option value="">{t("assembly.handleDefault")}</option>
                      {family.handle_models.map((model) => (
                        <option key={model.sku} value={model.sku}>
                          {model.name}
                          {model.price_delta_clp
                            ? ` · +${formatMoney(model.price_delta_clp, "CLP")}`
                            : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {family && family.handle_colors.length > 0 && (
                  <label className="assembly-field">
                    <span>{t("assembly.handleColor")}</span>
                    <select
                      aria-label={t("assembly.handleColor")}
                      disabled={busy}
                      value={bay.handle_color_sku ?? ""}
                      onChange={(event) =>
                        patchBay({ handle_color_sku: event.target.value || null })
                      }
                    >
                      <option value="">{t("assembly.handleDefault")}</option>
                      {family.handle_colors.map((color) => (
                        <option key={color.sku} value={color.sku}>
                          {color.name}
                          {color.price_delta_clp
                            ? ` · +${formatMoney(color.price_delta_clp, "CLP")}`
                            : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {declaredHeight &&
                  Number.isFinite(declaredHeight.min) &&
                  Number.isFinite(declaredHeight.max) &&
                  declaredHeight.rule === "RANGE" && (
                    <p className="assembly-hint">
                      {t("assembly.handleHeightRange")
                        .replace("{min}", fmtMm(String(declaredHeight.min)))
                        .replace("{max}", fmtMm(String(declaredHeight.max)))}
                      {heightOutOfRange ? ` — ${t("assembly.handleHeightOutOfRange")}` : ""}
                    </p>
                  )}
                {options.length > 0 && (
                  <fieldset className="assembly-field assembly-hardware-options">
                    <legend>{t("assembly.handleOptions")}</legend>
                    {options.map((option) => (
                      <label key={option.sku} className="assembly-check">
                        <input
                          type="checkbox"
                          disabled={busy}
                          checked={(bay.hardware_option_skus ?? []).includes(option.sku)}
                          onChange={(event) =>
                            toggleHardwareOption(option.sku, event.target.checked)
                          }
                        />
                        <span>
                          {option.name}
                          {" · "}
                          {option.price_delta_clp
                            ? `+${formatMoney(option.price_delta_clp, "CLP")}`
                            : t("assembly.optionDeltaUnknown")}
                        </span>
                      </label>
                    ))}
                  </fieldset>
                )}
              </div>
            );
          })()}
          {/* Avanzado: the expanded component list. The engine's emitted
              BOM lines win when the last calculation covers the same kit —
              they carry the leaf's real qty and cut length. Otherwise the
              declared-data mirror applies the same rules on the bay
              envelope (pre-calculation preview). */}
          {(() => {
            const resolvedEval = selectedKitEval ?? autoPickKit(kitEvaluations);
            const span = {
              leafWidthMm: leafEnvelope ? Math.round(leafEnvelope.w * 10) / 10 : null,
              leafHeightMm: leafEnvelope ? Math.round(leafEnvelope.h * 10) / 10 : null,
            };
            const engineOptionSkus = new Set(
              (resolvedHardware?.contents ?? [])
                .map((item) => item.option_sku)
                .filter((sku): sku is string => typeof sku === "string" && sku.length > 0),
            );
            const draftOptionSkus = new Set(bay.hardware_option_skus ?? []);
            const sameOptions =
              engineOptionSkus.size === draftOptionSkus.size &&
              [...draftOptionSkus].every((sku) => engineOptionSkus.has(sku));
            const engineContents =
              resolvedHardware && sameOptions && resolvedHardware.kit_sku === resolvedEval?.kit.sku
                ? resolvedHardware.contents
                : null;
            const optionContents = hardwareOptions
              .filter((item) => (bay.hardware_option_skus ?? []).includes(item.sku))
              .flatMap((item) => item.contents);
            const contents = [...(resolvedEval?.kit.contents ?? []), ...optionContents];
            if (engineContents === null && contents.length === 0) return null;
            return (
              <details className="assembly-kit-advanced">
                <summary>{t("assembly.kitAdvanced")}</summary>
                <table className="assembly-kit-table">
                  <thead>
                    <tr>
                      <th>{t("assembly.kitComponentQty")}</th>
                      <th />
                      <th>{t("assembly.kitComponentLength")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {engineContents !== null
                      ? engineContents.map((component, index) => (
                          <tr key={`${component.sku}-${index}`}>
                            <td>{component.qty}</td>
                            <td>
                              {component.name}
                              {(component.machining?.length ?? 0) > 0 && (
                                <small>
                                  {" "}
                                  · {component.machining!.length}{" "}
                                  {t("assembly.kitComponentMachining")}
                                </small>
                              )}
                            </td>
                            <td>
                              {component.length_mm != null && component.length_mm !== ""
                                ? `${fmtMm(String(component.length_mm))} mm`
                                : "—"}
                            </td>
                          </tr>
                        ))
                      : contents.map((component, index) => {
                          const resolved = resolveComponent(component, span);
                          return (
                            <tr key={`${component.sku}-${index}`}>
                              <td>{resolved.qty ?? "—"}</td>
                              <td>
                                {resolved.name}
                                {resolved.machiningCount > 0 && (
                                  <small>
                                    {" "}
                                    · {resolved.machiningCount}{" "}
                                    {t("assembly.kitComponentMachining")}
                                  </small>
                                )}
                              </td>
                              <td>
                                {resolved.lengthMm !== null
                                  ? `${fmtMm(String(resolved.lengthMm))} mm`
                                  : "—"}
                              </td>
                            </tr>
                          );
                        })}
                  </tbody>
                </table>
              </details>
            );
          })()}
          {/* The engine's resolved leaf truth after the last calculation —
              what manufacture will actually produce (handle, height, options). */}
          {resolvedHardware && (
            <p className="assembly-hint" aria-label={t("assembly.hardware")}>
              {[
                resolvedHardware.handle_model_name
                  ? `${resolvedHardware.handle_model_name}${
                      resolvedHardware.handle_color_name
                        ? ` · ${resolvedHardware.handle_color_name}`
                        : ""
                    }`
                  : null,
                resolvedHardware.handle_height_mm
                  ? `${fmtMm(resolvedHardware.handle_height_mm)} mm`
                  : null,
                ...(resolvedHardware.option_names ?? []),
              ]
                .filter((item): item is string => item !== null && item !== "")
                .join(" · ") || t("assembly.kitClassUnknown")}
            </p>
          )}
        </details>
      )}
      <details className="inspector-section" open data-section="glazing">
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
        {glassProducts.length > 0 ? (
          <GlazingPicker
            value={bay}
            products={glassProducts}
            glazingThicknesses={glazingThicknesses}
            findings={glassFindings}
            busy={busy}
            favoriteGlass={favoriteGlass}
            recentGlass={recentGlass}
            onPick={pickGlazing}
            onToggleFavorite={toggleFavoriteGlass}
          />
        ) : (
          <label className="assembly-field">
            <span>{t("assembly.glass")}</span>
            <select
              aria-label={t("assembly.glass")}
              disabled={busy}
              value={bay.glass_article_sku ?? ""}
              onChange={(event) =>
                pickGlazing({
                  glass_article_sku: event.target.value || null,
                  glass_spec:
                    event.target.value == null || event.target.value === ""
                      ? bay.glass_spec
                      : (glassSpecs.find((item) => item.sku === event.target.value)?.spec ?? null),
                })
              }
            >
              <option value="">{t("assembly.noGlass")}</option>
              {glassSkus.map((sku) => (
                <option key={sku} value={sku}>
                  {glassLabel(sku, glassSpecs)}
                </option>
              ))}
            </select>
          </label>
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
                  {panelLabel(sku, panelChoices)}
                </option>
              ))}
            </select>
          </label>
        )}
        <DraftField
          label={t("assembly.handleHeight")}
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
    <section className="assembly-inspector inspector-summary" data-section="overview">
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
                        <td>{fmtMm(cut.length_mm)}</td>
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
                          {fmtMm(glass.width_mm)} × {fmtMm(glass.height_mm)}
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
                          {fmtMm(panel.width_mm)} × {fmtMm(panel.height_mm)}
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
  glassProducts,
  glassFindings,
  glazingThicknesses,
  panelSkus,
  panelChoices,
  mullionSkus,
  couplerSkus,
  openingOptions,
  busy,
  commit,
  onAskAssistant,
}: {
  module: ProductJson["assembly"]["modules"][number];
  product: ProductJson;
  members: MemberGeometry;
  glassSkus: string[];
  glassSpecs: GlassSpecChoice[];
  glassProducts: GlassProductChoice[];
  glassFindings: GlassSafetyFinding[];
  glazingThicknesses: string[];
  panelSkus: string[];
  panelChoices: PanelChoice[];
  mullionSkus: Partial<Record<SplitType, string>>;
  couplerSkus: string[];
  /** Declared opening repertoire — undefined shows all options. */
  openingOptions?: readonly OpeningOption[];
  busy: boolean;
  commit(next: ProductJson): void;
  onAskAssistant?(): void;
}): JSX.Element {
  const opening = moduleOpening(module);
  const favoriteGlass = useCanvasStore((state) => state.favoriteGlass);
  const recentGlass = useCanvasStore((state) => state.recentGlass);
  const toggleFavoriteGlass = useCanvasStore((state) => state.toggleFavoriteGlass);
  const pushRecentGlass = useCanvasStore((state) => state.pushRecentGlass);
  const openingActiveKey = (OPTION_SPEC_KEY as Record<string, string>)[opening] ?? opening;
  const isDoor = opening === "DOOR_ENTRY" || opening.startsWith("DOOR:");
  const slidingBay = isSlidingOpening(opening as Opening) ? modulePrimaryBay(module) : null;
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
      <details className="inspector-section" open data-section="opening">
        <summary>{t("assembly.opening")}</summary>
        <OpeningGrid
          openingOptions={openingOptions}
          activeKey={openingActiveKey}
          activeChoice={opening}
          busy={busy}
          onPick={(value) => commit(setModuleOpening(product, module.id, value))}
        />
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
      <details className="inspector-section" open data-section="measures">
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
      <details className="inspector-section" open data-section="glazing">
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
        {glassProducts.length > 0 ? (
          <GlazingPicker
            value={modulePrimaryBay(module) ?? {}}
            products={glassProducts}
            glazingThicknesses={glazingThicknesses}
            findings={glassFindings}
            busy={busy}
            favoriteGlass={favoriteGlass}
            recentGlass={recentGlass}
            onPick={(patch) => {
              if (patch.glass_article_sku) pushRecentGlass(patch.glass_article_sku);
              commit(setModuleGlazing(product, module.id, patch));
            }}
            onToggleFavorite={toggleFavoriteGlass}
          />
        ) : (
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
                  {glassLabel(sku, glassSpecs)}
                </option>
              ))}
            </select>
          </label>
        )}
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
                  {panelLabel(sku, panelChoices)}
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
  members,
  busy,
  commit,
  onAskAssistant,
}: {
  coupling: CouplingJson;
  product: ProductJson;
  ordinal: number;
  couplerSkus: string[];
  members: MemberGeometry;
  busy: boolean;
  commit(next: ProductJson): void;
  onAskAssistant?(): void;
}): JSX.Element {
  // P06 — la lista se filtra por la envolvente de ángulo que el catálogo
  // declara (|ángulo|); el cople asignado siempre aparece aunque el motor
  // ya lo esté marcando incompatible — la UI nunca esconde el dato real.
  const angleDeg = Number(coupling.angle_deg);
  const couplerLabel = (sku: string): string => {
    const spec = members.couplerFor(sku);
    return spec?.name ? `${spec.name} · ${sku}` : sku;
  };
  const shownSkus = couplerSkus.filter(
    (sku) =>
      sku === coupling.coupler_profile_sku || couplerFitsAngle(members.couplerFor(sku), angleDeg),
  );
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
        rejectHint={t("assembly.fieldAngleRange")}
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
          {shownSkus.map((sku) => (
            <option key={sku} value={sku}>
              {couplerLabel(sku)}
            </option>
          ))}
        </select>
      </label>
      {shownSkus.length < couplerSkus.length && (
        <p className="inspector-note">
          {t("assembly.couplerFilteredNote").replace(
            "{count}",
            String(couplerSkus.length - shownSkus.length),
          )}
        </p>
      )}
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
    opening: <path d="M3 3h10v10H3z M3 3l7 5 M13 3l-7 5" />,
    glazing: <path d="M3 3h10v10H3z M5 11l6-8 M8 11l5-6.7" />,
    measure: <path d="M2 11l9-9 3 3-9 9z M5 8.5l1.5 1.5 M7.5 6l1.5 1.5 M10 3.5l1.5 1.5" />,
    inspector: <path d="M5 3h8v10H5z M1 5h4 M1 8h4 M1 11h4" />,
    shortcuts: <path d="M2 4h12v9H2z M4 6.5h1.5 M7 6.5h1.5 M10 6.5h1.5 M4 10h7" />,
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
  vano = null,
  onPickStarter,
  dock = {},
  quoteProposal,
  currency = "CLP",
  currentLineNet = null,
  shellToolbar,
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
  /** D07 — el vano de obra con holgura por lado; el lienzo dibuja la cota
   * doble (vano + fabricación) cuando el registro existe. */
  vano?: VanoDim | null;
  /** Pick a creation recipe — the rail's Tipologías flyout calls back with
   * the catalog-filtered definition and the parent commits the product. */
  onPickStarter?(definition: StarterDefinition): void;
  /** Bottom dock content — the object tree is built in; positions and BOM
   * panels come from the position page. */
  dock?: { positions?: JSX.Element | null; bom?: JSX.Element | null };
  /** Quote a proposal product at the position's live-price gate — the
   * ghost bar's Δ. Structural type (never the projects feature). */
  quoteProposal?(product: ProductJson): Promise<{
    unitNet: string;
    lineNet: string;
    netless: boolean;
  } | null>;
  currency?: string;
  /** The current design's live line net — Δ base for the proposal bar. */
  currentLineNet?: string | null;
  /** Extra controls the shell mounts on the canvas' top-right (Interior/
   * Exterior and side surface toggles from the position page). */
  shellToolbar?: JSX.Element | null;
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
  // D05: the picked finish's per-face render record tints every member —
  // binary-era systems without a color catalog keep the material tokens.
  const finish = useMemo(
    () =>
      finishForSelection(
        options?.color_options,
        inputs.color,
        inputs.colorExterior && inputs.colorExterior !== inputs.color ? inputs.colorExterior : null,
      ),
    [options?.color_options, inputs.color, inputs.colorExterior],
  );
  const members = useMemo(() => {
    const base = resolveMembers(options);
    return finish ? tintMembers(base, finish) : base;
  }, [options, finish]);
  const [tool, setTool] = useState<EditorTool>("select");
  /** Right-rail detail level — overview/design/technical over the same
   * selection; complexity stays hidden until the user asks for it. */
  const [detail, setDetail] = useState<DetailLevel>("design");
  // P05 — vista declarada del alzado (interior/exterior).
  const [frontView, setFrontView] = useState<"interior" | "exterior">("interior");
  // P06 — la planta acoplada vive en una franja inferior del lienzo con
  // altura arrastrable; cuando el conjunto tiene uniones en ángulo, la
  // elevación puede leerse Desarrollada (un módulo tras otro) o Proyectada
  // (cada columna con su escorzo w·cos(rumbo)).
  const [planOpen, setPlanOpen] = useState(true);
  const [planStripHeight, setPlanStripHeight] = useState(168);
  // La franja plegada deja solo el encabezado (~2rem): el cuerpo flotante del
  // dock flota por encima de la franja usando --plan-strip-height (ver CSS).
  const PLAN_STRIP_COLLAPSED_H = 32;
  const [projected, setProjected] = useState(false);
  const [view3dOpen, setView3dOpen] = useState(false);
  /** Interior/Exterior view selector — the 2D front is DIN-interior by
   * convention; Exterior flips the 3D inset open on its outside side. */
  const [viewOutside, setViewOutside] = useState(false);
  /** P04 — the canvas-first surface: flyout/pickers/measure/ghost state
   * plus the responsive contracts (icon rail + inspector drawer ≤1279,
   * read-only <1024). */
  const compact = useMediaQuery("(max-width: 1279px)");
  const readOnly = useMediaQuery("(max-width: 1023px)");
  const requestFit = useCanvasStore((state) => state.requestFit);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [coupleMenu, setCoupleMenu] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [picker, setPicker] = useState<{ moduleId: string; bayId: string } | null>(null);
  // Screen-space anchor for the picker popover — the bay's module rect
  // projected through the live view transform (set on every picker open).
  const [pickerPos, setPickerPos] = useState<{ x: number; y: number } | null>(null);
  const pickerAnchorRef = useRef<HTMLSpanElement>(null);
  const [inspectorDrawer, setInspectorDrawer] = useState(false);
  const [dockOpen, setDockOpen] = useState(true);
  const [dockTab, setDockTab] = useState<"tree" | "positions" | "bom">("tree");
  const [proposal, setProposal] = useState<CommandProposal | null>(null);
  const [proposalQuote, setProposalQuote] = useState<{
    value: string | null;
    pending: boolean;
  }>({ value: null, pending: false });
  const [measure, setMeasure] = useState<MeasurePoint[]>([]);
  const [measureCursor, setMeasureCursor] = useState<MeasurePoint | null>(null);
  const [sectionFocus, setSectionFocus] = useState<{
    key: string;
    nonce: number;
  } | null>(null);
  const viewRef = useRef<ViewTransform | null>(null);
  const sideRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const libraryAnchorRef = useRef<HTMLButtonElement>(null);
  const coupleAnchorRef = useRef<HTMLButtonElement>(null);
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  /** Queued prompt for the assistant — "" means focus only. Every "…with
   * DEKOPEN" affordance funnels here; the human always confirms. */
  const [assistantDraft, setAssistantDraft] = useState<{
    text: string;
    submit?: boolean;
  } | null>(null);
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
  function askAssistant(prompt: string, submit = false): void {
    assistantSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setAssistantDraft({ text: prompt, submit });
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
          // IA2 — las ops estructurales miden con la geometría de miembros
          // del sistema activo; sin ella el split/equalize no puede
          // posicionar y el apply queda sin efecto (rechazo honesto).
          if (product) commit(applyDesignOps(product, ops, undefined, members));
        }
      : null,
  );

  // Hooks before the empty branch — a starter pick flips product
  // null→object on the SAME mounted instance, so any early return placed
  // ahead of a hook crashes with "Rendered more hooks".
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
  const front = useMemo(
    () => (product ? frontLayout(product, { projected }) : null),
    [product, projected],
  );
  const frontBox = useMemo(
    () =>
      front
        ? frontBounds(
            front,
            vano,
            detail === "technical"
              ? technicalExtraBottom(front.rects, members, front.height, members.frame.faceWidthMm)
              : 0,
          )
        : null,
    [front, vano, detail, members],
  );

  /** Open the opening picker anchored at the bay's module on screen — a
   * popover glued to the whole canvas would land off-center at any zoom. */
  function openPicker(moduleId: string, bayId: string): void {
    setPicker({ moduleId, bayId });
    const rect = front?.rects.find((item) => item.module.id === moduleId);
    const view = viewRef.current;
    if (front && rect && view) {
      setPickerPos({
        x: (rect.x + rect.w / 2) * view.scale + view.tx,
        y: (front.height - rect.sill - rect.h / 2) * view.scale + view.ty,
      });
    } else {
      setPickerPos(null);
    }
  }
  const selectionBox = useMemo(
    () => (front ? frontModuleBox(front, selection) : null),
    [front, selection],
  );

  // The shared command registry: palette, keyboard and AI all dispatch the
  // same typed commands; `commit` inside is the single undoable transaction.
  const commandCtx = useMemo<CommandContext | null>(() => {
    if (!product) return null;
    return {
      product,
      selection,
      catalog: {
        glassThicknesses: options?.glazing_thicknesses ?? [],
        glassSkus,
        couplerSkus,
        panelSkus,
        mullionSkus,
      },
      members,
      disabled: busy,
      commit,
      select,
      setTool,
      focusAssistant: () => askAssistant(""),
      fitView: requestFit,
      showShortcuts: () => setShortcutsOpen(true),
      focusSection: (section) => {
        setSectionFocus({ key: section, nonce: Date.now() });
        if (compact) setInspectorDrawer(true);
      },
      openOpeningPicker: () => {
        const sel = useCanvasStore.getState().selection;
        if (sel === null || !sel.includes("/")) return;
        const [moduleId, bayId] = sel.split("/");
        if (!moduleId || !bayId) return;
        const module = product.assembly.modules.find((item) => item.id === moduleId);
        const node = module ? findNode(module.tree, bayId) : null;
        if (node?.type === "BAY") openPicker(moduleId, bayId);
      },
      openCoupleMenu: () => setCoupleMenu(true),
      toggleLibrary: () => setLibraryOpen((value) => !value),
      previewProposal: (next) => setProposal(next),
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
    };
    // `commit` is re-declared per render and always sees current inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    product,
    selection,
    options,
    members,
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
    requestFit,
    compact,
  ]);
  const surface = useMemo(
    () =>
      commandCtx ? { commands: resolveCommands(commandCtx, assemblyCommands(commandCtx)) } : null,
    [commandCtx],
  );
  // Every chord the surface advertises (menus, palette) is reserved while the
  // editor is mounted — a filtered-out command's shortcut must not leak to
  // the browser (Ctrl+D opened the bookmark dialog).
  const reservedShortcuts = useMemo(() => {
    if (!commandCtx) return [];
    const specs = assemblyCommands(commandCtx);
    return specs.flatMap((spec) => {
      const s = spec.shortcut;
      return s === undefined ? [] : Array.isArray(s) ? [...s] : [s];
    });
  }, [commandCtx]);
  useRegisterCommands(surface);
  useCommandShortcuts(surface, reservedShortcuts);

  // Armed tools land the picked bay's inspector section in view. React's
  // <details open> diff only writes when the prop flips, so an imperative
  // open survives the next render pass untouched.
  useEffect(() => {
    if (!sectionFocus) return;
    const target = sideRef.current?.querySelector(`[data-section="${sectionFocus.key}"]`);
    if (target instanceof HTMLElement) {
      const details = target.closest("details");
      if (details && !details.open) details.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      target.querySelector<HTMLElement>("input, select, button, summary")?.focus();
    }
  }, [sectionFocus]);

  // Quote the staged proposal for the Δ chip — same live gate as the
  // strip's price, so "what does this typed op cost" is engine-priced.
  useEffect(() => {
    if (!proposal || !quoteProposal) {
      setProposalQuote({ value: null, pending: false });
      return;
    }
    let live = true;
    setProposalQuote({ value: null, pending: true });
    void quoteProposal(proposal.product).then((quote) => {
      if (!live) return;
      setProposalQuote({
        value: quote && !quote.netless ? quote.lineNet : null,
        pending: false,
      });
    });
    return () => {
      live = false;
    };
  }, [proposal, quoteProposal]);

  /** Snap vertices the Medir ruler offers: module corners + seam tops, the
   * same rects the elevation draws (frontLayout space = model mm). Must
   * stay above the early return — hooks can't live past a conditional. */
  const measureAnchors = useMemo(
    () =>
      tool === "measure" && front
        ? front.rects.flatMap((rect) => {
            const top = front.height - rect.sill - rect.h;
            const bottom = front.height - rect.sill;
            return [
              { x: rect.x, y: top },
              { x: rect.x + rect.w, y: top },
              { x: rect.x, y: bottom },
              { x: rect.x + rect.w, y: bottom },
            ];
          })
        : [],
    [tool, front],
  );

  // Leaving the tool drops the in-progress ruler — a leftover path would
  // confuse the next measurement.
  useEffect(() => {
    if (tool !== "measure") {
      setMeasure([]);
      setMeasureCursor(null);
    }
  }, [tool]);

  const objectTree = useMemo(
    () => (product ? buildObjectTree(product, members, issues, t, options) : null),
    [product, members, issues, options],
  );

  if (!product || !front || !frontBox || !commandCtx || !surface || !objectTree) {
    return (
      <section
        className={`assembly-editor editor-surface is-empty${compact ? " is-compact" : ""}${readOnly ? " is-readonly" : ""}`}
      >
        <div className="editor-rail-wrap">
          <nav className="editor-rail" aria-label={t("assembly.tools")}>
            {onPickStarter && (
              <>
                <button
                  type="button"
                  ref={libraryAnchorRef}
                  className={`rail-item${libraryOpen ? " is-active" : ""}`}
                  aria-expanded={libraryOpen}
                  aria-haspopup="dialog"
                  onClick={() => setLibraryOpen((open) => !open)}
                >
                  <ToolIcon name="tree" />
                  <span className="rail-item__label">{t("assembly.starterLibrary")}</span>
                </button>
                {libraryOpen && (
                  <div className="editor-flyout">
                    <TypologyFlyout
                      members={members}
                      openingOptions={options?.opening_options}
                      disabled={disabled}
                      onPick={(definition) => {
                        setLibraryOpen(false);
                        onPickStarter(definition);
                      }}
                    />
                  </div>
                )}
              </>
            )}
          </nav>
        </div>
        <div className="assembly-canvas canvas-empty">
          <p className="assembly-hint">{t("assembly.pickStarter")}</p>
        </div>
        {!compact && (
          <aside className="assembly-side">
            {positionPanel ?? <p className="assembly-hint">{t("assembly.elementHint")}</p>}
          </aside>
        )}
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
  const planBox = couplings.length > 0 && evaluation?.plan ? planBounds(evaluation.plan) : null;
  const statusText = `${formatDims(front.totalW, front.height)} mm`;
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

  function coupleUnit(side: "left" | "right"): void {
    const next = addAdjacentUnit(productJson, side);
    commit(next);
    select(
      next.assembly.modules[side === "left" ? 0 : next.assembly.modules.length - 1]?.id ?? null,
    );
  }

  const splitReady = { SPLIT_V: mullionSkus.SPLIT_V, SPLIT_H: mullionSkus.SPLIT_H };

  /** Capture-phase key arbitration inside the canvas surface: with a
   * proposal staged, Enter applies and Esc discards; otherwise Enter
   * descends the selection (module → first bay → opening picker), Esc
   * ascends (bay → module → clear → unarm tool), and arrows nudge the
   * selected element 1 mm (Shift 10 mm). With nothing selected arrows
   * fall through to the viewport's pan. */
  function onCanvasKeyDownCapture(event: ReactKeyboardEvent<HTMLDivElement>): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
    if (proposal) {
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        const staged = proposal;
        setProposal(null);
        staged.apply();
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setProposal(null);
      }
      return;
    }
    if (event.key === "Enter" && selection && product) {
      if (selectedModule && !selectedBayModule && !selectedDivisionModule) {
        const firstBay = intentBays(selectedModule.tree)[0];
        if (firstBay) {
          event.preventDefault();
          event.stopPropagation();
          select(`${selectedModule.id}/${firstBay.id}`);
        }
      } else if (selectedBayModule && selectedBayNode) {
        event.preventDefault();
        event.stopPropagation();
        openPicker(selectedBayModule.id, selectedBayNode.id);
      }
      return;
    }
    if (event.key === "Escape") {
      if (selectedBayModule) {
        event.preventDefault();
        event.stopPropagation();
        select(selectedBayModule.id);
      } else if (selectedDivisionModule) {
        event.preventDefault();
        event.stopPropagation();
        select(selectedDivisionModule.id);
      } else if (tool !== "select") {
        event.preventDefault();
        event.stopPropagation();
        setTool("select");
      }
      // A bare Esc with the selection tool falls through to the registry's
      // esc → deselect command.
      return;
    }
    if (!event.key.startsWith("Arrow") || !product || busy) return;
    const horizontal = event.key === "ArrowLeft" || event.key === "ArrowRight";
    const step =
      (event.shiftKey ? 10 : 1) * (event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1);
    if (selectedDivisionModule && selectedDivisionNode) {
      // A split only moves along its own axis — cross-axis arrows keep
      // panning the viewport.
      const verticalSplit = selectedDivisionNode.type === "SPLIT_H";
      if (verticalSplit === horizontal) return;
      event.preventDefault();
      event.stopPropagation();
      const current = Number(selectedDivisionNode.split_offset_mm ?? 0) || 0;
      commit(
        moveModuleDivision(
          product,
          selectedDivisionModule.id,
          selectedDivisionNode.id,
          fmtWire(current + step),
        ),
      );
      return;
    }
    if (selectedModule) {
      event.preventDefault();
      event.stopPropagation();
      if (horizontal) {
        commit(
          setModuleWidth(
            product,
            selectedModule.id,
            fmtWire(Number(selectedModule.width_mm) + step),
          ),
        );
      } else {
        commit(
          setModuleHeight(
            product,
            selectedModule.id,
            fmtWire(Number(selectedModule.height_mm) + step),
          ),
        );
      }
      return;
    }
    // No element selected → the viewport's arrow pan keeps the key.
  }

  function onCanvasDoubleClick(): void {
    // Double-click a bay opens the opening picker — by the time dblclick
    // fires, the second click already selected it (discrete events flush
    // before the next one), so the live selection IS the clicked bay.
    if (tool !== "select") return;
    const sel = selectionRef.current;
    if (!sel || !sel.includes("/") || !product) return;
    const [moduleId, nodeId] = sel.split("/");
    if (!moduleId || !nodeId) return;
    const module = product.assembly.modules.find((item) => item.id === moduleId);
    const node = module ? findNode(module.tree, nodeId) : null;
    if (node?.type === "BAY") openPicker(moduleId, nodeId);
  }

  function onCanvasBayPick(moduleId: string, bayId: string): void {
    if (tool === "measure") return; // anchors decide — clicks don't select
    select(`${moduleId}/${bayId}`);
    if (tool === "opening") {
      openPicker(moduleId, bayId);
    } else if (tool === "glazing") {
      setSectionFocus({ key: "glazing", nonce: Date.now() });
      if (compact) setInspectorDrawer(true);
    }
  }

  /** Medir: convert a client point into the model mm the overlay draws in. */
  function measureFromEvent(event: ReactPointerEvent<HTMLDivElement>): MeasurePoint | null {
    const view = viewRef.current;
    if (!view) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left - view.tx) / view.scale,
      y: (event.clientY - rect.top - view.ty) / view.scale,
    };
  }

  function onCanvasPointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    if (tool !== "measure") return;
    const point = measureFromEvent(event);
    setMeasureCursor(point);
  }

  const pickerModule = picker
    ? product.assembly.modules.find((item) => item.id === picker.moduleId)
    : undefined;
  const pickerBay = pickerModule && picker ? findNode(pickerModule.tree, picker.bayId) : null;
  const proposalDelta =
    proposalQuote.value !== null && currentLineNet !== null
      ? fmtWire(Number(proposalQuote.value) - Number(currentLineNet))
      : null;

  const inspectorSections = (
    <>
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
      {/* P05 — vista declarada del alzado + bloque plegable de
          simbología: el contrato de lectura va pegado al dibujo. */}
      <div className="view-levels" role="group" aria-label={t("assembly.viewLabel")}>
        {(["interior", "exterior"] as const).map((level) => (
          <button
            key={level}
            type="button"
            className={`detail-levels__btn${frontView === level ? " is-active" : ""}`}
            aria-pressed={frontView === level}
            onClick={() => setFrontView(level)}
          >
            {t(level === "exterior" ? "assembly.viewExterior" : "assembly.viewInterior")}
          </button>
        ))}
      </div>
      <details className="symbols-legend">
        <summary>{t("assembly.symbolsLegend")}</summary>
        <p>{t("assembly.symbolsHint")}</p>
      </details>
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
                    true,
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
                `${formatDims(Number(selectedModule.width_mm), Number(selectedModule.height_mm))} mm`,
              ],
              [
                t("assembly.opening"),
                t(
                  OPENING_OPTIONS.find(([value]) => value === moduleOpening(selectedModule))?.[1] ??
                    "intent.fixed",
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
          glassProducts={options?.glass_products ?? []}
          glassFindings={
            evaluation?.modules
              ?.find((item) => item.module_id === selectedModule.id)
              ?.result?.glasses?.flatMap((glass) => glass.safety_findings ?? []) ?? []
          }
          glazingThicknesses={options?.glazing_thicknesses ?? []}
          panelSkus={panelSkus}
          panelChoices={options?.panel_choices ?? []}
          mullionSkus={mullionSkus}
          couplerSkus={couplerSkus}
          openingOptions={options?.opening_options}
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
          kits={options?.hardware_kits ?? []}
          hardwareFamilies={options?.hardware_families ?? []}
          hardwareOptions={options?.hardware_options ?? []}
          resolvedHardware={
            evaluation?.modules
              ?.find((item) => item.module_id === selectedBayModule.id)
              ?.result?.hardware_items?.find((item) => item.bay_id === selectedBayNode.id) ?? null
          }
          openingOptions={options?.opening_options}
          members={members}
          leafWeightKg={
            evaluation?.modules
              ?.find((item) => item.module_id === selectedBayModule.id)
              ?.result?.leaf_weights?.find((w) => w.bay_id === selectedBayNode.id)
              ?.total_weight_kg != null
              ? Number(
                  evaluation.modules
                    .find((item) => item.module_id === selectedBayModule.id)!
                    .result!.leaf_weights!.find((w) => w.bay_id === selectedBayNode.id)!
                    .total_weight_kg,
                )
              : null
          }
          glassSkus={glassSkus}
          glassSpecs={options?.glass_specs ?? []}
          glassProducts={options?.glass_products ?? []}
          glassFindings={
            evaluation?.modules
              ?.find((item) => item.module_id === selectedBayModule.id)
              ?.result?.glasses?.filter((glass) => glass.bay_id === selectedBayNode.id)
              ?.flatMap((glass) => glass.safety_findings ?? []) ?? []
          }
          glazingThicknesses={options?.glazing_thicknesses ?? []}
          panelSkus={panelSkus}
          panelChoices={options?.panel_choices ?? []}
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
          members={members}
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
    </>
  );

  const planStripOffset =
    couplings.length > 0 && evaluation?.plan && planBox
      ? planOpen
        ? planStripHeight
        : PLAN_STRIP_COLLAPSED_H
      : 0;

  return (
    <div
      className={`assembly-editor editor-surface${compact ? " is-compact" : ""}${readOnly ? " is-readonly" : ""}`}
      aria-label={t("assembly.frontView")}
    >
      <div className="editor-rail-wrap">
        <nav className="editor-rail" role="toolbar" aria-label={t("assembly.tools")}>
          {onPickStarter && (
            <>
              <button
                type="button"
                ref={libraryAnchorRef}
                className={`rail-item${libraryOpen ? " is-active" : ""}`}
                title={`${t("assembly.starterLibrary")} — B`}
                aria-label={t("assembly.starterLibrary")}
                aria-pressed={libraryOpen}
                aria-expanded={libraryOpen}
                aria-haspopup="dialog"
                disabled={busy}
                onClick={() => setLibraryOpen((value) => !value)}
              >
                <ToolIcon name="tree" />
                <span className="rail-item__label">{t("assembly.starterLibrary")}</span>
              </button>
              <span className="editor-rail__divider" aria-hidden="true" />
            </>
          )}
          <button
            type="button"
            className={`rail-item${tool === "select" ? " is-active" : ""}`}
            title={`${t("assembly.toolSelect")} — V`}
            aria-label={t("assembly.toolSelect")}
            aria-pressed={tool === "select"}
            onClick={() => setTool("select")}
          >
            <ToolIcon name="select" />
            <span className="rail-item__label">{t("assembly.toolSelect")}</span>
          </button>
          <button
            type="button"
            className={`rail-item${tool === "split_v" ? " is-active" : ""}`}
            title={`${t("assembly.toolDivideV")} — |`}
            aria-label={t("assembly.toolDivideV")}
            aria-pressed={tool === "split_v"}
            disabled={busy || splitReady.SPLIT_V === undefined}
            onClick={() => setTool(tool === "split_v" ? "select" : "split_v")}
          >
            <ToolIcon name="split_v" />
            <span className="rail-item__label">{t("assembly.toolDivideV")}</span>
          </button>
          <button
            type="button"
            className={`rail-item${tool === "split_h" ? " is-active" : ""}`}
            title={`${t("assembly.toolDivideH")} — -`}
            aria-label={t("assembly.toolDivideH")}
            aria-pressed={tool === "split_h"}
            disabled={busy || splitReady.SPLIT_H === undefined}
            onClick={() => setTool(tool === "split_h" ? "select" : "split_h")}
          >
            <ToolIcon name="split_h" />
            <span className="rail-item__label">{t("assembly.toolDivideH")}</span>
          </button>
          <button
            type="button"
            className={`rail-item${tool === "opening" ? " is-active" : ""}`}
            title={`${t("assembly.toolOpening")} — A`}
            aria-label={t("assembly.toolOpening")}
            aria-pressed={tool === "opening"}
            onClick={() => setTool(tool === "opening" ? "select" : "opening")}
          >
            <ToolIcon name="opening" />
            <span className="rail-item__label">{t("assembly.toolOpening")}</span>
          </button>
          <button
            type="button"
            className={`rail-item${tool === "glazing" ? " is-active" : ""}`}
            title={`${t("assembly.toolGlazing")} — G`}
            aria-label={t("assembly.toolGlazing")}
            aria-pressed={tool === "glazing"}
            onClick={() => setTool(tool === "glazing" ? "select" : "glazing")}
          >
            <ToolIcon name="glazing" />
            <span className="rail-item__label">{t("assembly.toolGlazing")}</span>
          </button>
          <button
            type="button"
            ref={coupleAnchorRef}
            className={`rail-item${coupleMenu ? " is-active" : ""}`}
            title={`${t("assembly.toolCouple")} — C`}
            aria-label={t("assembly.toolCouple")}
            aria-expanded={coupleMenu}
            aria-haspopup="menu"
            disabled={busy}
            onClick={() => setCoupleMenu((value) => !value)}
          >
            <ToolIcon name="couple_right" />
            <span className="rail-item__label">{t("assembly.toolCouple")}</span>
          </button>
          <button
            type="button"
            className={`rail-item${tool === "measure" ? " is-active" : ""}`}
            title={`${t("assembly.toolMeasure")} — M`}
            aria-label={t("assembly.toolMeasure")}
            aria-pressed={tool === "measure"}
            onClick={() => setTool(tool === "measure" ? "select" : "measure")}
          >
            <ToolIcon name="measure" />
            <span className="rail-item__label">{t("assembly.toolMeasure")}</span>
          </button>
          <span className="editor-rail__spacer" aria-hidden="true" />
          <button
            type="button"
            className="rail-item"
            title={`${t("canvas.fit")} — F`}
            aria-label={t("canvas.fit")}
            onClick={requestFit}
          >
            <ToolIcon name="equalize" />
            <span className="rail-item__label">{t("canvas.fit")}</span>
          </button>
          <button
            type="button"
            className="rail-item"
            title={`${t("assembly.shortcutsTitle")} — ?`}
            aria-label={t("assembly.shortcutsTitle")}
            onClick={() => setShortcutsOpen(true)}
          >
            <ToolIcon name="shortcuts" />
            <span className="rail-item__label">{t("assembly.shortcutsTitle")}</span>
          </button>
          {compact && (
            <button
              type="button"
              className={`rail-item${inspectorDrawer ? " is-active" : ""}`}
              title={t("assembly.inspectorToggle")}
              aria-label={t("assembly.inspectorToggle")}
              aria-pressed={inspectorDrawer}
              onClick={() => setInspectorDrawer((value) => !value)}
            >
              <ToolIcon name="inspector" />
              <span className="rail-item__label">{t("assembly.inspectorToggle")}</span>
            </button>
          )}
        </nav>
        {libraryOpen && (
          <div className="editor-flyout" role="presentation">
            <TypologyFlyout
              members={members}
              openingOptions={options?.opening_options}
              disabled={busy}
              onPick={(definition) => {
                setLibraryOpen(false);
                onPickStarter?.(definition);
              }}
            />
          </div>
        )}
        {coupleMenu && (
          <div className="editor-flyout editor-flyout--menu">
            <Menu
              onClose={() => setCoupleMenu(false)}
              items={[
                {
                  key: "left",
                  label: t("assembly.addUnitLeft"),
                  onSelect: () => coupleUnit("left"),
                },
                {
                  key: "right",
                  label: t("assembly.addUnitRight"),
                  onSelect: () => coupleUnit("right"),
                },
                {
                  key: "above",
                  label: t("cmd.stackAbove"),
                  disabled: couplings.length === 0,
                  onSelect: () => {
                    const command = surface?.commands.find(
                      (item) => item.id === "module.stack-above",
                    );
                    command?.run({});
                  },
                },
              ]}
            />
          </div>
        )}
      </div>
      <div
        className="assembly-canvas"
        ref={canvasRef}
        onContextMenu={(event) => {
          event.preventDefault();
          setContextMenu({ x: event.clientX, y: event.clientY });
        }}
        onDoubleClick={onCanvasDoubleClick}
        onKeyDownCapture={onCanvasKeyDownCapture}
        onPointerMove={onCanvasPointerMove}
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
          onViewChange={(view) => {
            viewRef.current = view;
          }}
        >
          <ProductFrontContent
            product={product}
            members={members}
            selectedId={selectedModule?.id ?? null}
            issues={issues}
            disabled={busy || readOnly}
            divideTool={divideToolType}
            dimLevel={detail}
            onSelectModule={pickModule}
            onSelectBay={onCanvasBayPick}
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
            vano={vano}
            view={frontView}
            projected={projected}
          />
          {tool === "measure" && (
            <MeasureLayer
              anchors={measureAnchors}
              path={measureCursor && measure.length > 0 ? [...measure, measureCursor] : measure}
              k={viewRef.current?.scale ?? 1}
              onAnchor={(point) => setMeasure((points) => [...points, point])}
            />
          )}
          {proposal && (
            <GhostLayer
              proposal={proposal.product}
              members={members}
              k={viewRef.current?.scale ?? 1}
            />
          )}
        </CanvasViewport>
        {couplings.length > 0 && evaluation?.plan && planBox && (
          <div
            className={`plan-strip${planOpen ? "" : " plan-strip--collapsed"}`}
            role="complementary"
            aria-label={t("assembly.planView")}
            style={planOpen ? { height: planStripHeight } : undefined}
          >
            {planOpen && (
              <div
                className="plan-strip__resize"
                role="separator"
                aria-orientation="horizontal"
                aria-label={t("assembly.planStripHint")}
                title={t("assembly.planStripHint")}
                onPointerDown={(event) => {
                  // Altura arrastrable: el borde superior de la franja se
                  // toma y la altura sigue el puntero hasta soltar. El
                  // anclaje es el borde inferior (pegado al pie del lienzo),
                  // por eso la altura es bottom − y del puntero.
                  event.preventDefault();
                  const stripEl = event.currentTarget.parentElement;
                  const canvasEl = canvasRef.current;
                  if (!stripEl || !canvasEl) return;
                  const pointerId = event.pointerId;
                  const canvasRect = canvasEl.getBoundingClientRect();
                  const minH = 96;
                  const maxH = Math.max(minH, canvasRect.height * 0.45);
                  const onMove = (move: PointerEvent) => {
                    if (move.pointerId !== pointerId) return;
                    const next = canvasRect.bottom - move.clientY;
                    setPlanStripHeight(Math.max(minH, Math.min(maxH, next)));
                  };
                  const detach = () => {
                    window.removeEventListener("pointermove", onMove);
                    window.removeEventListener("pointerup", detach);
                    window.removeEventListener("pointercancel", detach);
                  };
                  window.addEventListener("pointermove", onMove);
                  window.addEventListener("pointerup", detach);
                  window.addEventListener("pointercancel", detach);
                }}
              />
            )}
            <div className="plan-strip__header">
              <button
                type="button"
                className="plan-strip__fold"
                aria-expanded={planOpen}
                aria-label={
                  planOpen ? t("assembly.planStripCollapse") : t("assembly.planStripExpand")
                }
                onClick={() => setPlanOpen((value) => !value)}
              >
                {t("assembly.planView")}
                <span aria-hidden="true" className="plan-strip__chevron">
                  {planOpen ? "▾" : "▴"}
                </span>
              </button>
              {planOpen && (
                <>
                  <span className="plan-strip__measures" aria-label={t("assembly.elevationLabel")}>
                    <span>
                      {t("assembly.developedLength")}{" "}
                      {Math.round(planMeasures(evaluation.plan).developedMm)}
                    </span>
                    <span>
                      {t("assembly.chordLength")}{" "}
                      {Math.round(planMeasures(evaluation.plan).chordMm)}
                    </span>
                    <span>
                      {t("assembly.projection")}{" "}
                      {Math.round(planMeasures(evaluation.plan).projectionMm)}
                    </span>
                  </span>
                  <div className="view-seg plan-strip__elevation" role="group">
                    <button
                      type="button"
                      className={projected ? "" : "is-active"}
                      aria-pressed={!projected}
                      onClick={() => setProjected(false)}
                    >
                      {t("assembly.elevationDeveloped")}
                    </button>
                    <button
                      type="button"
                      className={projected ? "is-active" : ""}
                      aria-pressed={projected}
                      onClick={() => setProjected(true)}
                    >
                      {t("assembly.elevationProjected")}
                    </button>
                  </div>
                </>
              )}
            </div>
            {planOpen && (
              <svg
                className="plan-strip__svg"
                viewBox={`${planBox.x} ${planBox.y} ${planBox.w} ${planBox.h}`}
                preserveAspectRatio="xMidYMid meet"
                role="img"
                aria-label={t("assembly.planView")}
              >
                <BowPlanContent
                  plan={evaluation.plan}
                  couplings={couplings}
                  members={members}
                  selectedModuleId={
                    selectedModule?.id ??
                    selectedBayModule?.id ??
                    selectedDivisionModule?.id ??
                    null
                  }
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
            )}
          </div>
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
                inside={!viewOutside}
                onInsideChange={(inside) => setViewOutside(!inside)}
              />
            </Suspense>
          </div>
        ) : (
          <button type="button" className="model3d-toggle" onClick={() => setView3dOpen(true)}>
            {t("assembly.view3d")}
          </button>
        )}
        <div className="canvas-viewbar" role="group" aria-label={t("assembly.detailLevels")}>
          {shellToolbar}
          <div className="view-seg" role="group">
            <button
              type="button"
              className={viewOutside ? "" : "is-active"}
              aria-pressed={!viewOutside}
              onClick={() => setViewOutside(false)}
            >
              {t("assembly.viewInside")}
            </button>
            <button
              type="button"
              className={viewOutside ? "is-active" : ""}
              aria-pressed={viewOutside}
              onClick={() => {
                setViewOutside(true);
                setView3dOpen(true);
              }}
            >
              {t("assembly.viewOutside")}
            </button>
          </div>
          <div className="view-seg" role="group">
            <button
              type="button"
              className={detail !== "technical" ? "is-active" : ""}
              aria-pressed={detail !== "technical"}
              onClick={() => setDetail("design")}
            >
              {t("assembly.viewCommercial")}
            </button>
            <button
              type="button"
              className={detail === "technical" ? "is-active" : ""}
              aria-pressed={detail === "technical"}
              onClick={() => setDetail("technical")}
            >
              {t("assembly.viewTechnical")}
            </button>
          </div>
          <div className="view-seg" role="group">
            <button
              type="button"
              className={view3dOpen ? "" : "is-active"}
              aria-pressed={!view3dOpen}
              onClick={() => setView3dOpen(false)}
            >
              {t("assembly.view2d")}
            </button>
            <button
              type="button"
              className={view3dOpen ? "is-active" : ""}
              aria-pressed={view3dOpen}
              onClick={() => setView3dOpen(true)}
            >
              {t("assembly.view3d")}
            </button>
          </div>
          {planBox && (
            <button
              type="button"
              className={`view-toggle${planOpen ? " is-active" : ""}`}
              aria-pressed={planOpen}
              onClick={() => setPlanOpen((value) => !value)}
            >
              {t("assembly.viewPlan")}
            </button>
          )}
        </div>
        {tool === "measure" && (
          <MeasureChip
            path={measure}
            liveMm={
              measure.length > 0 && measureCursor
                ? Math.hypot(
                    measureCursor.x - (measure[measure.length - 1]?.x ?? 0),
                    measureCursor.y - (measure[measure.length - 1]?.y ?? 0),
                  )
                : null
            }
          />
        )}
        {readOnly && (
          <p className="canvas-readonly" role="note">
            {t("assembly.readonlyNotice")}
          </p>
        )}
      </div>
      {picker && pickerPos && (
        <span
          ref={pickerAnchorRef}
          aria-hidden="true"
          className="picker-anchor"
          style={{ left: pickerPos.x, top: pickerPos.y }}
        />
      )}
      {picker && pickerModule && pickerBay?.type === "BAY" && (
        <Popover
          anchorRef={pickerAnchorRef}
          onClose={() => {
            setPicker(null);
            if (tool === "opening") setTool("select");
          }}
        >
          <OpeningGrid
            openingOptions={options?.opening_options}
            activeKey={nodeSpecKey(pickerModule.tree, pickerBay)}
            activeChoice={pickerBay.opening_type ?? "FIXED"}
            busy={busy}
            doorBlocked={topIntent(pickerModule.tree).id !== pickerBay.id}
            onPick={(choice) => {
              commit(
                setModuleTree(
                  product,
                  pickerModule.id,
                  changeOpening(pickerModule.tree, pickerBay.id, choice),
                ),
              );
              setPicker(null);
            }}
          />
        </Popover>
      )}
      {shortcutsOpen && <ShortcutsDialog onClose={() => setShortcutsOpen(false)} />}
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
      {!compact ? (
        <aside className="assembly-side" ref={sideRef}>
          {inspectorSections}
        </aside>
      ) : inspectorDrawer ? (
        <Drawer title={t("assembly.inspectorToggle")} onClose={() => setInspectorDrawer(false)}>
          <div className="assembly-side assembly-side--drawer" ref={sideRef}>
            {inspectorSections}
          </div>
        </Drawer>
      ) : null}
      <footer className="editor-dock" data-open={dockOpen || undefined}>
        {/* In-flow row inside the dock: an absolute bar over the canvas bottom
            is covered by the dock's floating body whenever it is open — the
            proposal actions must stay reachable with the tree expanded. */}
        {proposal && (
          <ProposalBar
            delta={proposalDelta}
            pending={proposalQuote.pending}
            currency={currency}
            onApply={() => {
              const staged = proposal;
              setProposal(null);
              staged.apply();
            }}
            onDiscard={() => setProposal(null)}
          />
        )}
        <div className="editor-dock__bar" role="tablist" aria-label={t("assembly.dockTree")}>
          <button
            type="button"
            role="tab"
            aria-selected={dockOpen && dockTab === "tree"}
            className={`editor-dock__tab${dockTab === "tree" ? " is-active" : ""}`}
            onClick={() => {
              setDockTab("tree");
              setDockOpen(true);
            }}
          >
            {t("assembly.dockTree")}
          </button>
          {dock.positions ? (
            <button
              type="button"
              role="tab"
              aria-selected={dockOpen && dockTab === "positions"}
              className={`editor-dock__tab${dockTab === "positions" ? " is-active" : ""}`}
              onClick={() => {
                setDockTab("positions");
                setDockOpen(true);
              }}
            >
              {t("assembly.dockPositions")}
            </button>
          ) : null}
          {dock.bom ? (
            <button
              type="button"
              role="tab"
              aria-selected={dockOpen && dockTab === "bom"}
              className={`editor-dock__tab${dockTab === "bom" ? " is-active" : ""}`}
              onClick={() => {
                setDockTab("bom");
                setDockOpen(true);
              }}
            >
              {t("assembly.dockBom")}
            </button>
          ) : null}
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
          <span className="editor-dock__dims">{statusText}</span>
          {selectedLabel && <span className="editor-dock__selection">{selectedLabel}</span>}
          {issues.length > 0 && (
            <button
              type="button"
              className="editor-dock__issues"
              onClick={() => {
                const first = issues[0];
                if (
                  first &&
                  (first.target.startsWith("module:") || first.target.startsWith("coupling:"))
                ) {
                  select(first.target.slice(first.target.indexOf(":") + 1));
                }
                if (compact) setInspectorDrawer(true);
                else
                  issuesListRef.current?.scrollIntoView({
                    behavior: "smooth",
                    block: "nearest",
                  });
              }}
            >
              {t("assembly.issueCount").replace("{count}", String(issues.length))}
            </button>
          )}
          <button
            type="button"
            className="editor-dock__fold"
            aria-expanded={dockOpen}
            aria-label={dockOpen ? t("assembly.dockFold") : t("assembly.dockUnfold")}
            title={dockOpen ? t("assembly.dockFold") : t("assembly.dockUnfold")}
            onClick={() => setDockOpen((value) => !value)}
          >
            {dockOpen ? "▾" : "▴"}
          </button>
        </div>
        {dockOpen && (
          <div
            className="editor-dock__body"
            role="tabpanel"
            style={
              planStripOffset > 0
                ? { bottom: `calc(100% + 0.85rem + ${planStripOffset}px)` }
                : undefined
            }
          >
            {/* Every tab body stays mounted (hidden when inactive): fresh
                data on switch, and the BOM is always in the DOM for tests. */}
            <div className="dock-tree" hidden={dockTab !== "tree"}>
              <ObjectTree
                root={objectTree}
                selection={selection}
                onSelect={(id) => {
                  if (id !== null && modules.some((module) => module.id === id)) pickModule(id);
                  else select(id);
                }}
                onContextMenu={(id, pos) => {
                  if (modules.some((module) => module.id === id)) pickModule(id);
                  else select(id);
                  setContextMenu(pos);
                }}
                title={t("tree.title")}
              />
            </div>
            <div hidden={dockTab !== "positions"}>{dock.positions}</div>
            <div hidden={dockTab !== "bom"}>{dock.bom}</div>
          </div>
        )}
      </footer>
    </div>
  );
}
