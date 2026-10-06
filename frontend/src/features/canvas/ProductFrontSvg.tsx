import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import type { ProductIssue } from "../../api/generated/models";
import { fmtMm, parseLocaleNumber, fmtMmCanonical, fmtWire } from "../../format";
import { t } from "../../i18n/es-CL";
import type { IntentNode, UnitKind } from "./intentEditing";
import {
  bayLeafTraces,
  isSlidingOpening,
  OPTION_SPEC_KEY,
  panelTravel,
  resolvedSlidingLayout,
  travelInferred,
  type OpeningSpecPayload,
  type SlidingLayout,
} from "./intentEditing";
import {
  glyphPaths,
  leafPrimitives,
  slidingPrimitives,
  type ElevationView,
} from "./openingSymbols";
import { OPENING_OPTIONS } from "./openings";
import { memberSurface, type MemberSurface } from "./materials";
import { contourOutset, contourPathD, insetContourPoints, pointsPathD } from "./contourGeometry";
import type { MemberGeometry } from "./members";
import {
  elevationLayoutMm,
  MIN_MODULE_WIDTH_MM,
  resolveStacks,
  type FramelessEdge,
  type FramelessFittingJson,
  type FramelessSpecJson,
  type ProductJson,
} from "./productEditing";
import { useViewportScale } from "./CanvasViewport";
// The front view's fills/strokes live in canvas.css — importing it here
// keeps the renderer self-contained: surfaces outside the editor
// (/benchmark, thumbnails, alternatives) get the same real drawing.
import "./canvas.css";

/** Front elevation of the compositional product as a real fenestration
 * drawing: frame/sash/mullion/bead/threshold members at their catalog face
 * widths, glass and panel infills, handle levers, signature dimension chains
 * with extension lines and ticks. The engine stays the authority — this view
 * only renders and dispatches typed edits. */

type SeverityMap = Map<string, "error" | "warning">;

function severityByModule(issues: ProductIssue[]): SeverityMap {
  const map: SeverityMap = new Map();
  for (const issue of issues) {
    const target = issue.target;
    if (!target.startsWith("module:")) continue;
    const id = target.slice("module:".length);
    const current = map.get(id);
    if (current !== "error") map.set(id, issue.severity);
  }
  return map;
}

/** Click-to-edit dimension rendered on the canvas: idle text, input on click. */
function SvgDim({
  x,
  y,
  value,
  label,
  active,
  disabled,
  onCommit,
}: {
  x: number;
  y: number;
  value: string;
  label: string;
  active?: boolean;
  disabled: boolean;
  onCommit(normalized: string): void;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [invalid, setInvalid] = useState(false);
  // Escape must discard the typed draft, but `setState` hasn't flushed when
  // `blur()` fires — the onBlur below would commit the stale value. A ref
  // flag lets the blur branch tell a cancel apart from a commit.
  const cancelRef = useRef(false);
  useEffect(() => {
    if (!editing) {
      setDraft(value);
      setInvalid(false);
    }
  }, [value, editing]);
  const fontSize = 34;
  if (!editing || disabled) {
    // Click target: an invisible padded pill around the glyphs — the text
    // alone is a few px at fit zoom, so most clicks used to miss and hit the
    // bay behind instead. Hover/focus shows the pill as an edit affordance.
    const hitWidth = Math.max(fmtMm(value).length * fontSize * 0.62 + 36, 96);
    const hitHeight = fontSize + 22;
    return (
      <g
        className={`canvas-dim-wrap${active ? " is-active" : ""}`}
        role="button"
        aria-label={label}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && setEditing(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (!disabled) setEditing(true);
          }
        }}
      >
        <rect
          className="canvas-dim-hit"
          x={x - hitWidth / 2}
          y={y - hitHeight / 2}
          width={hitWidth}
          height={hitHeight}
          rx={10}
        />
        <text
          className="canvas-dim"
          x={x}
          y={y}
          fontSize={fontSize}
          textAnchor="middle"
          dominantBaseline="central"
          pointerEvents="none"
        >
          {fmtMm(value)}
        </text>
      </g>
    );
  }
  return (
    <foreignObject x={x - 70} y={y - fontSize} width={140} height={fontSize + 26}>
      <input
        className={`canvas-dim-input${invalid ? " is-invalid" : ""}`}
        aria-label={label}
        aria-invalid={invalid || undefined}
        autoFocus
        inputMode="decimal"
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
          setInvalid(false);
        }}
        onFocus={(event) => event.target.select()}
        onBlur={() => {
          if (cancelRef.current) {
            cancelRef.current = false;
            setEditing(false);
            return;
          }
          const normalized = normalizeDimension(draft);
          if (normalized === null) {
            // Reject like Enter does — flag the editor and stay open so a
            // mistyped dimension never silently snaps back.
            setDraft(value);
            setInvalid(true);
            return;
          }
          if (normalized !== value) onCommit(normalized);
          setEditing(false);
        }}
        onKeyDown={(event) => {
          // Enter on an unparseable value keeps the editor open and flags
          // it — reverting silently reads as the input being ignored.
          if (event.key === "Enter") {
            if (normalizeDimension(draft) === null) {
              setInvalid(true);
            } else {
              event.currentTarget.blur();
            }
          }
          if (event.key === "Escape") {
            cancelRef.current = true;
            event.currentTarget.blur();
          }
        }}
      />
    </foreignObject>
  );
}

/** Sanity ceiling for a typed dimension: well past any real module/assembly
 * size, it exists to catch slips (e.g. a stray comma) — not an engineering
 * bound; kit/system limits still apply downstream. */
const MAX_DIMENSION_MM = 30000;

function normalizeDimension(candidate: string): string | null {
  const value = parseLocaleNumber(candidate.trim().replace(/[°\s]/g, ""));
  if (value === null || value <= 0 || value > MAX_DIMENSION_MM) return null;
  return fmtWire(value);
}

/** Parse an emitted spec key — "TURN:LEFT:OUTWARD[:ROLE]" or the DOOR:
 * prefixed leaf form — into the parts the glyph needs. */
function glyphSpec(kind: string): {
  movement: string;
  hinge: "LEFT" | "RIGHT" | "TOP" | "BOTTOM" | null;
  direction: "INWARD" | "OUTWARD" | null;
} | null {
  const body = kind.startsWith("DOOR:") ? kind.slice(5) : kind;
  const parts = body.split(":");
  const movement = parts[0];
  if (!movement || !/^[A-Z_]+$/.test(movement) || !parts[1]) return null;
  const hinge = ["LEFT", "RIGHT", "TOP", "BOTTOM"].includes(parts[1])
    ? (parts[1] as "LEFT" | "RIGHT" | "TOP" | "BOTTOM")
    : null;
  const direction = parts[2] === "OUTWARD" ? "OUTWARD" : parts[2] === "INWARD" ? "INWARD" : null;
  return { movement, hinge, direction };
}

/** Leaf spec from an opening key — legacy enum (`TURN_LEFT`, `AWNING`,
 * `DOOR_ENTRY`) or the D03 spec key (`TURN:LEFT:OUTWARD`,
 * `DOOR:TURN:RIGHT:INWARD:ACTIVE`). Shared by the elevation glyph and
 * the /dev/ui symbol table so both read the same vocabulary. */
export function glyphLeafSpec(
  kind: string,
  doorHinge?: "left" | "right",
): { opening: OpeningSpecPayload; unit: "WINDOW" | "DOOR" } | null {
  const isDoor = kind === "DOOR_ENTRY" || kind === "DOOR_DOUBLE" || kind.startsWith("DOOR:");
  const legacy: Record<string, OpeningSpecPayload> = {
    FIXED: { movement: "FIXED" },
    TURN_LEFT: { movement: "TURN", hinge_side: "LEFT", direction: "INWARD" },
    TURN_RIGHT: { movement: "TURN", hinge_side: "RIGHT", direction: "INWARD" },
    TILT_TURN_LEFT: { movement: "TILT_TURN", hinge_side: "LEFT", direction: "INWARD" },
    TILT_TURN_RIGHT: { movement: "TILT_TURN", hinge_side: "RIGHT", direction: "INWARD" },
    AWNING: { movement: "TOP_HUNG", hinge_side: "TOP", direction: "OUTWARD" },
    DOOR_ENTRY: {
      movement: "TURN",
      hinge_side: doorHinge === "right" ? "RIGHT" : "LEFT",
      direction: "INWARD",
    },
    DOOR_DOUBLE: {
      movement: "TURN",
      hinge_side: doorHinge === "right" ? "RIGHT" : "LEFT",
      direction: "INWARD",
      leaf_role: "ACTIVE",
    },
    SLIDING: { movement: "SLIDE" },
    SLIDING_2L: { movement: "SLIDE" },
    SLIDING_3L: { movement: "SLIDE" },
    SLIDING_4L: { movement: "SLIDE" },
  };
  const direct = legacy[kind];
  if (direct) return { opening: direct, unit: isDoor ? "DOOR" : "WINDOW" };
  const parsed = glyphSpec(kind);
  if (!parsed) return null;
  return {
    opening: {
      movement: parsed.movement as OpeningSpecPayload["movement"],
      hinge_side: parsed.hinge,
      direction: parsed.direction,
      leaf_role: kind.split(":").includes("PASSIVE") ? "PASSIVE" : null,
    },
    unit: isDoor ? "DOOR" : "WINDOW",
  };
}

/** Industry opening glyph driven by the shared symbology contract
 * (`openingSymbols.ts` = the engine's `opening_symbols.py`): DIN
 * triangle lines with the apex at 40 % of the free edge, dashed when the
 * leaf opens away from the viewer, sliding leaves as horizontal arrows,
 * door leaves as triangles (the swing arc belongs to the plan view),
 * fixed leaves as silence. `view` flips only the stroke — the mirror
 * lives on the sheet. */
export function OpeningGlyph({
  opening,
  x,
  y,
  w,
  h,
  doorHinge,
  view = "interior",
}: {
  opening: string | null | undefined;
  x: number;
  y: number;
  w: number;
  h: number;
  doorHinge?: "left" | "right";
  view?: ElevationView;
}): JSX.Element {
  const kind = opening ?? "FIXED";
  const spec = glyphLeafSpec(kind, doorHinge);
  const prims = spec
    ? leafPrimitives(spec.opening, view, { unit: spec.unit })
    : [{ k: "none" as const }];
  const paths = glyphPaths(prims, x, y, w, h);
  return (
    <g
      className={`opening-glyph opening-${kind.toLowerCase().replace(/[:|]/g, "-")}`}
      aria-hidden="true"
    >
      {paths.map((entry, index) => (
        <path
          key={`glyph-path-${index}`}
          d={entry.d}
          fill="none"
          strokeDasharray={entry.dash ?? undefined}
          className={`glyph-${entry.k}${entry.inferred ? " glyph-inferred" : ""}`}
        />
      ))}
    </g>
  );
}

type Region = { x: number; y: number; w: number; h: number };

/** Rectangular member drawn as a filled ring segment — frame, sash, mullion,
 * threshold and coupler all share it. When the member is wide enough, its
 * material family's interior detail is drawn inside (PVC chamber rebate /
 * aluminium thermal break) so sections read as real extrusions. */
function Member({
  x,
  y,
  w,
  h,
  surface,
  className,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  surface: MemberSurface;
  className: string;
}): JSX.Element {
  const thin = Math.min(w, h);
  const detail = surface.detail !== "none" && thin >= 26;
  const inset = Math.min(thin * 0.3, 12);
  // Thermal break: a narrow strip just off-center along the member's long
  // axis — the insulating zone between an alu profile's exterior/interior.
  const vertical = h >= w;
  const strip = Math.min(thin * 0.09, 3.5);
  return (
    <>
      <rect
        className={`member ${className}`}
        x={x}
        y={y}
        width={w}
        height={h}
        fill={surface.fill}
        stroke={surface.edge}
        strokeWidth={2.5}
      />
      {detail && (
        <rect
          className={`member-inner member-inner--${surface.detail}`}
          x={x + inset}
          y={y + inset}
          width={Math.max(w - inset * 2, 0)}
          height={Math.max(h - inset * 2, 0)}
          stroke={surface.highlight}
        />
      )}
      {detail &&
        surface.detail === "thermal" &&
        (vertical ? (
          <rect
            className="member-thermal-strip"
            x={x + w * 0.42}
            y={y}
            width={strip}
            height={h}
            fill={surface.edge}
          />
        ) : (
          <rect
            className="member-thermal-strip"
            x={x}
            y={y + h * 0.42}
            width={w}
            height={strip}
            fill={surface.edge}
          />
        ))}
    </>
  );
}

/** Insulated glazing hint: a thin inner ring inside the pane reads as the
 * second lite + spacer of a DVH unit. Only when the catalog thickness says
 * the unit is insulated (>= 12 mm). */
function InsulatedRing({ pane }: { pane: Region }): JSX.Element | null {
  const inset = Math.min(Math.min(pane.w, pane.h) * 0.06, 9);
  if (Math.min(pane.w, pane.h) < 60) return null;
  return (
    <rect
      className="module-glass-ig"
      x={pane.x + inset}
      y={pane.y + inset}
      width={Math.max(pane.w - inset * 2, 0)}
      height={Math.max(pane.h - inset * 2, 0)}
    />
  );
}

/** A glass-only module (mandate §14): the pane IS the module — drawn edge to
 * edge, never with a phantom frame. Declared supports run along their edge
 * (continuous CHANNEL seat, spaced CLAMPS) and fittings mark their edge/corner
 * positions. Support/fitting marks are presentation conventions; articles and
 * counts come from the model. */
function FramelessModule({
  spec,
  x,
  top,
  w,
  h,
}: {
  spec: FramelessSpecJson;
  x: number;
  top: number;
  w: number;
  h: number;
}): JSX.Element {
  const channelD = Math.min(24, Math.min(w, h) * 0.18);
  const clamp = Math.min(26, Math.min(w, h) * 0.22);
  const edgeRect = (edge: FramelessEdge, depth: number): Region => {
    if (edge === "top") return { x, y: top, w, h: depth };
    if (edge === "bottom") return { x, y: top + h - depth, w, h: depth };
    if (edge === "left") return { x, y: top, w: depth, h };
    return { x: x + w - depth, y: top, w: depth, h };
  };
  const along = (edge: FramelessEdge, index: number, count: number): Region => {
    const frac = count <= 1 ? 0.5 : (index + 0.5) / count;
    const horizontal = edge === "top" || edge === "bottom";
    const rect = edgeRect(edge, channelD);
    const offset = clamp / 2;
    return horizontal
      ? { x: rect.x + rect.w * frac - offset, y: rect.y, w: clamp, h: clamp }
      : { x: rect.x, y: rect.y + rect.h * frac - offset, w: clamp, h: clamp };
  };
  // Fittings have no positional authority in the model — mark them by kind at
  // conventional spots: corner patches, left-edge hinges, right-edge locks,
  // top connectors, bottom supports. A seal draws as the dashed inset line.
  const fittingSpot = (kind: FramelessFittingJson["kind"], index: number): Region => {
    const size = Math.min(20, Math.min(w, h) * 0.16);
    const spots: Record<FramelessFittingJson["kind"], Region> = {
      PATCH_FITTING: [
        { x, y: top, w: size, h: size },
        { x: x + w - size, y: top, w: size, h: size },
        { x, y: top + h - size, w: size, h: size },
        { x: x + w - size, y: top + h - size, w: size, h: size },
      ][index % 4] as Region,
      CLAMP: along("bottom", index, 3),
      HINGE: along("left", index, 3),
      LOCK: along("right", index, 3),
      CONNECTOR: along("top", index, 3),
      SEAL: { x, y: top, w: size, h: size },
      SUPPORT: along("bottom", index + 1, 4),
    };
    const spot = spots[kind];
    return {
      x: spot.x,
      y: spot.y,
      w: Math.min(spot.w, size),
      h: Math.min(spot.h, size),
    };
  };
  const fittingIndex = new Map<string, number>();
  return (
    <g className="module-frameless">
      <rect className="module-glass" x={x} y={top} width={w} height={h} />
      {w > 30 && h > 30 && (
        <line
          className="glass-sheen"
          x1={x + w * 0.18}
          y1={top + h * 0.82}
          x2={x + w * 0.82}
          y2={top + h * 0.18}
        />
      )}
      {(spec.exposed_edges ?? []).map((edge) => {
        const rect = edgeRect(edge, Math.min(10, channelD * 0.5));
        return (
          <rect
            key={`exposed-${edge}`}
            className="frameless-exposed"
            x={rect.x}
            y={rect.y}
            width={rect.w}
            height={rect.h}
          />
        );
      })}
      {spec.supports.map((support, index) => {
        if (support.kind === "CHANNEL") {
          const rect = edgeRect(support.edge, channelD);
          return (
            <rect
              key={`support-${index}`}
              className="frameless-channel"
              x={rect.x}
              y={rect.y}
              width={rect.w}
              height={rect.h}
            >
              <title>
                {support.article_sku
                  ? `${t("assembly.framelessKindChannel")} · ${support.article_sku}`
                  : t("assembly.framelessKindChannel")}
              </title>
            </rect>
          );
        }
        return Array.from({ length: Math.max(support.qty, 1) }, (_, at) => {
          const rect = along(support.edge, at, Math.max(support.qty, 1));
          return (
            <rect
              key={`support-${index}-${at}`}
              className="frameless-clamp"
              x={rect.x}
              y={rect.y}
              width={rect.w}
              height={rect.h}
            >
              <title>
                {support.article_sku
                  ? `${t("assembly.framelessKindClamps")} · ${support.article_sku}`
                  : t("assembly.framelessKindClamps")}
              </title>
            </rect>
          );
        });
      })}
      {spec.fittings.some((fitting) => fitting.kind === "SEAL") && (
        <rect
          className="frameless-seal"
          x={x + 6}
          y={top + 6}
          width={Math.max(w - 12, 0)}
          height={Math.max(h - 12, 0)}
        />
      )}
      {spec.fittings
        .filter((fitting) => fitting.kind !== "SEAL")
        .flatMap((fitting) => {
          const index = fittingIndex.get(fitting.kind) ?? 0;
          fittingIndex.set(fitting.kind, index + fitting.qty);
          return Array.from({ length: Math.max(fitting.qty, 1) }, (_, at) => {
            const rect = fittingSpot(fitting.kind, index + at);
            return (
              <rect
                key={`fitting-${fitting.kind}-${index + at}`}
                className={`frameless-fitting frameless-fitting--${fitting.kind.toLowerCase()}`}
                x={rect.x}
                y={rect.y}
                width={rect.w}
                height={rect.h}
              >
                <title>
                  {fitting.sku
                    ? `${t(`assembly.fittingKind.${fitting.kind}`)} · ${fitting.sku}`
                    : t(`assembly.fittingKind.${fitting.kind}`)}
                </title>
              </rect>
            );
          });
        })}
    </g>
  );
}

/** Handle lever on the sash's handle edge (≈55% up, EN convention). */
function HandleLever({
  x,
  y,
  side,
  invalid,
  declaredMm,
}: {
  x: number;
  y: number;
  side: "left" | "right";
  /** The declared datum landed off the leaf — the drawing shows the
   * handle where it clamped AND flags it, never silently corrects. */
  invalid?: boolean;
  declaredMm?: number;
}): JSX.Element {
  const dir = side === "left" ? 1 : -1;
  return (
    <g className={`handle-lever${invalid ? " is-datum-invalid" : ""}`} aria-hidden={!invalid}>
      {invalid && (
        <>
          <title>
            {t("assembly.handleDatumOutOfRange").replace("{declared}", String(declaredMm ?? ""))}
          </title>
          <circle className="handle-datum-flag" cx={x} cy={y} r={11} />
        </>
      )}
      <line x1={x} y1={y - 10} x2={x} y2={y + 16} strokeWidth={5} strokeLinecap="round" />
      <line x1={x} y1={y} x2={x + dir * 18} y2={y} strokeWidth={5} strokeLinecap="round" />
    </g>
  );
}

/** A leaf bay: sash ring (when operable), glazing bead sightline, glass or
 * panel infill, opening glyph and handle lever. Spec leaves (D03) render
 * per leaf — a french pair draws two sashes meeting at the inversor. */
function Bay({
  node,
  region,
  members,
  selected = false,
  onSelect,
  moduleBottom,
  unitKind = "WINDOW",
  view = "interior",
  technical = false,
}: {
  node: IntentNode;
  region: Region;
  members: MemberGeometry;
  selected?: boolean;
  onSelect?(): void;
  /** Sheet-space y of the module's outer bottom edge — the datum the
   * declared handle height measures up from (OUTER_BOTTOM authority). */
  moduleBottom?: number;
  /** Declared unit kind of the unit root (door units draw thresholds). */
  unitKind?: UnitKind;
  /** Declared elevation view — "exterior" flips the dash convention. */
  view?: ElevationView;
  /** Technical verbosity adds handle-height datum marks beside the lever. */
  technical?: boolean;
}): JSX.Element {
  const leafTraces = bayLeafTraces(node);
  const opening = node.opening_type ?? "FIXED";
  const emittedKey = leafTraces.some((leaf) => leaf.opening)
    ? leafTraces.map((leaf) => `${leaf.slot}:${leaf.key}`).join("|")
    : null;
  const ariaLabelKey = emittedKey
    ? (OPENING_OPTIONS.find(
        ([value]) =>
          OPTION_SPEC_KEY[value] === emittedKey || OPTION_SPEC_KEY[value] === `DOOR:${emittedKey}`,
      )?.[1] ?? "intent.fixed")
    : (OPENING_OPTIONS.find(([value]) => value === opening)?.[1] ?? "intent.fixed");
  const bead = members.beadFor(node.glass_thickness_mm ?? null);
  const insulated = Number(node.glass_thickness_mm ?? "0") >= 12;
  const sashSurface = memberSurface(members.sash.material, members.sash.finish?.exterior);
  const baySelectProps = onSelect
    ? {
        onClick: (event: React.MouseEvent) => {
          event.stopPropagation();
          onSelect();
        },
        role: "button" as const,
        "aria-label": `${t("intent.bay")} · ${t(ariaLabelKey)}`,
        tabIndex: 0,
        onKeyDown: (event: React.KeyboardEvent) => {
          if (event.key === "Enter" || event.key === " ") {
            event.stopPropagation();
            event.preventDefault();
            onSelect();
          }
        },
        style: { cursor: "pointer" },
      }
    : {};
  const selectRing = selected ? (
    <rect
      className="bay-select-ring"
      x={region.x}
      y={region.y}
      width={Math.max(region.w, 0)}
      height={Math.max(region.h, 0)}
    />
  ) : null;

  // Sliding topology (mandate §12): panels on rails — each slot is pitch
  // wide, a moving leaf covers its slot plus the meeting-stile overlap;
  // rear track draws first so the front leaf covers the interlock. Fixed
  // panels glaze their slot directly like a fixed bay.
  if (isSlidingOpening(opening)) {
    const layout = resolvedSlidingLayout(node);
    const panels = layout?.panels ?? [];
    const panelPrims = layout ? slidingPrimitives(layout, view) : [];
    const interlock = members.sash.faceWidthMm;
    const pitch = region.w / Math.max(panels.length, 1);
    const leafW = pitch + interlock;
    const leafSashT = members.sash.faceWidthMm;
    const order = panels
      .map((panel, index) => ({ panel, index }))
      .sort((a, b) => (a.panel.track ?? -1) - (b.panel.track ?? -1));
    return (
      <g
        className={`module-bay module-bay--sliding${selected ? " is-selected" : ""}${onSelect ? " bay-pickable" : ""}`}
        {...baySelectProps}
      >
        {/* Rail notation: two head/sill grooves behind the leaves — the
         * corredera reading a reviewer could not see (review M3). */}
        <line
          className="sliding-track"
          x1={region.x}
          y1={region.y + 4}
          x2={region.x + region.w}
          y2={region.y + 4}
        />
        <line
          className="sliding-track"
          x1={region.x}
          y1={region.y + region.h - 4}
          x2={region.x + region.w}
          y2={region.y + region.h - 4}
        />
        {order.map(({ panel, index }) => {
          const slotX = region.x + pitch * index;
          if (panel.kind === "FIXED") {
            return (
              <g key={`leaf-${index}`} className="sliding-leaf sliding-leaf--fixed">
                <rect
                  className="member-bead"
                  x={slotX + bead}
                  y={region.y + bead}
                  width={Math.max(pitch - bead * 2, 0)}
                  height={Math.max(region.h - bead * 2, 0)}
                />
                <rect
                  className="module-glass"
                  x={slotX + bead * 2}
                  y={region.y + bead * 2}
                  width={Math.max(pitch - bead * 4, 0)}
                  height={Math.max(region.h - bead * 4, 0)}
                />
              </g>
            );
          }
          const leafX = Math.min(
            Math.max(slotX - interlock / 2, region.x),
            region.x + region.w - leafW,
          );
          const beadX = leafX + leafSashT;
          const beadY = region.y + leafSashT;
          const beadW = leafW - leafSashT * 2;
          const beadH = region.h - leafSashT * 2;
          return (
            <g
              key={`leaf-${index}`}
              className={`sliding-leaf sliding-leaf--${(panel.track ?? 0) === 0 ? "rear" : "front"}`}
            >
              <Member
                x={leafX}
                y={region.y}
                w={leafW}
                h={region.h}
                surface={sashSurface}
                className="member-sash"
              />
              <rect
                className="member-bead"
                x={beadX}
                y={beadY}
                width={Math.max(beadW, 0)}
                height={Math.max(beadH, 0)}
              />
              <rect
                className="module-glass"
                x={beadX + bead}
                y={beadY + bead}
                width={Math.max(beadW - bead * 2, 0)}
                height={Math.max(beadH - bead * 2, 0)}
              />
              {insulated && (
                <InsulatedRing
                  pane={{
                    x: beadX + bead,
                    y: beadY + bead,
                    w: Math.max(beadW - bead * 2, 0),
                    h: Math.max(beadH - bead * 2, 0),
                  }}
                />
              )}
              {/* Travel arrow from the shared symbology contract: the
               * declared `travel` direction drives the glyph; leaves with no
               * declaration keep the legacy presentation convention and are
               * flagged `glyph-inferred` ("dirección inferida" — a surface
               * reads it as assumed, never as manufacturing truth). */}
              {glyphPaths(panelPrims[index] ?? [], leafX, region.y, leafW, region.h).map(
                (entry, entryIndex) => (
                  <path
                    key={`travel-${entryIndex}`}
                    className={`sliding-arrow${entry.inferred ? " glyph-inferred" : ""}`}
                    d={entry.d}
                    fill="none"
                  />
                ),
              )}
            </g>
          );
        })}
        {selectRing}
      </g>
    );
  }

  const isDoor = opening === "DOOR_ENTRY" || unitKind === "DOOR";
  const reveal = 3;

  /** Resolve a leaf's declared/legacy hinge side. */
  const leafHinge = (
    openingSpec: OpeningSpecPayload | null,
    key: string,
  ): "LEFT" | "RIGHT" | "TOP" | "BOTTOM" | null => {
    if (openingSpec?.hinge_side && openingSpec.hinge_side !== "NONE") {
      return openingSpec.hinge_side;
    }
    if (key.includes("LEFT")) return "LEFT";
    if (key.includes("RIGHT")) return "RIGHT";
    if (key === "AWNING") return "TOP";
    if (key === "DOOR_ENTRY") return node.door_handedness ?? "LEFT";
    return null;
  };

  const leafCount = leafTraces.length;
  const leafDraws = leafTraces.map((leaf) => {
    const operable = leaf.opening ? leaf.opening.movement !== "FIXED" : leaf.key !== "FIXED";
    // Fijo en hoja draws its sash ring but takes no opening glyph.
    const sash = operable || leaf.opening?.fixed_in_sash === true;
    const hinge = leafHinge(leaf.opening, leaf.key);
    const passive = leaf.opening?.leaf_role === "PASSIVE";
    return { leaf, operable, sash, hinge, passive };
  });
  const anySash = leafDraws.some((leaf) => leaf.sash);

  const thresholdH = isDoor ? (members.threshold?.faceWidthMm ?? 30) : 0;
  const sashArea: Region = anySash
    ? {
        x: region.x + reveal,
        y: region.y + reveal,
        w: region.w - reveal * 2,
        h: region.h - reveal * 2 - thresholdH,
      }
    : region;
  const sashT = members.sash.faceWidthMm;
  // Each leaf owns an equal column of the sash area — pair leaves meet at
  // the inversor stile straddling the boundary.
  const leafBoxes: Region[] = leafDraws.map((_, index) => ({
    x: sashArea.x + (sashArea.w * index) / leafCount,
    y: sashArea.y,
    w: sashArea.w / leafCount,
    h: sashArea.h,
  }));
  const leafGeom = leafDraws.map((leaf, index) => {
    const box = leafBoxes[index]!;
    const glassBox: Region = leaf.sash
      ? { x: box.x + sashT, y: box.y + sashT, w: box.w - sashT * 2, h: box.h - sashT * 2 }
      : { x: box.x + bead, y: box.y + bead, w: box.w - bead * 2, h: box.h - bead * 2 };
    const pane: Region = leaf.sash
      ? {
          x: glassBox.x + bead,
          y: glassBox.y + bead,
          w: glassBox.w - bead * 2,
          h: glassBox.h - bead * 2,
        }
      : glassBox;
    // DIN: the handle sits opposite the hinges; a top/bottom-hinged leaf
    // centres its handle on the free member.
    const handleSide: "left" | "right" | null =
      leaf.operable && !leaf.passive
        ? leaf.hinge === "LEFT"
          ? "right"
          : leaf.hinge === "RIGHT"
            ? "left"
            : null
        : null;
    const handleTop =
      leaf.operable && !leaf.passive && (leaf.hinge === "BOTTOM" || leaf.hinge === "TOP");
    const doorHinge =
      leaf.hinge === "RIGHT"
        ? ("right" as const)
        : leaf.hinge === "LEFT"
          ? ("left" as const)
          : undefined;
    return { ...leaf, box, glassBox, pane, handleSide, handleTop, doorHinge };
  });
  const isPanel = Boolean(node.panel_article_sku);
  // OUTER_BOTTOM datum resolution shared with the 3D scene: a declared
  // height that lands off the leaf is reported (is-datum-invalid flag),
  // not silently clamped into a plausible-looking position.
  const declaredRaw = Number(node.handle_height_mm);
  const declaredMm = Number.isFinite(declaredRaw) && declaredRaw > 0 ? declaredRaw : null;
  const heightMm = declaredMm ?? 1050;
  const rawDatum =
    moduleBottom !== undefined ? moduleBottom - heightMm : sashArea.y + sashArea.h - heightMm;
  const datumInvalid =
    declaredMm !== null && (rawDatum < sashArea.y || rawDatum > sashArea.y + sashArea.h);
  const datumY = Math.min(Math.max(rawDatum, sashArea.y + 60), sashArea.y + sashArea.h - 60);

  return (
    <g
      className={`module-bay${selected ? " is-selected" : ""}${onSelect ? " bay-pickable" : ""}`}
      {...baySelectProps}
    >
      {leafGeom.map(
        (leaf, index) =>
          leaf.sash && (
            <g key={`sash-${index}`}>
              <Member
                x={leaf.box.x}
                y={leaf.box.y}
                w={leaf.box.w}
                h={Math.max(leaf.box.h, 0)}
                surface={sashSurface}
                className="member-sash"
              />
              {/* glazing beads: sightline ring inside the sash */}
              <rect
                className="member-bead"
                x={leaf.glassBox.x}
                y={leaf.glassBox.y}
                width={Math.max(leaf.glassBox.w, 0)}
                height={Math.max(leaf.glassBox.h, 0)}
              />
            </g>
          ),
      )}
      {leafCount > 1 && (
        <Member
          x={sashArea.x + sashArea.w / 2 - sashT * 0.45}
          y={sashArea.y}
          w={sashT * 0.9}
          h={Math.max(sashArea.h, 0)}
          surface={sashSurface}
          className="member-inversor"
        />
      )}
      {leafGeom.map((leaf, index) =>
        isPanel ? (
          <rect
            key={`pane-${index}`}
            className="bay-panel"
            x={leaf.pane.x}
            y={leaf.pane.y}
            width={Math.max(leaf.pane.w, 0)}
            height={Math.max(leaf.pane.h, 0)}
          />
        ) : (
          <g key={`pane-${index}`}>
            <rect
              className="module-glass"
              x={leaf.pane.x}
              y={leaf.pane.y}
              width={Math.max(leaf.pane.w, 0)}
              height={Math.max(leaf.pane.h, 0)}
            />
            {/* The sheen only belongs on inert glass — under an operable leaf
             * it crosses the opening glyph and reads as a scribble. */}
            {leaf.pane.w > 30 && leaf.pane.h > 30 && !leaf.operable && (
              <line
                className="glass-sheen"
                x1={leaf.pane.x + leaf.pane.w * 0.18}
                y1={leaf.pane.y + leaf.pane.h * 0.82}
                x2={leaf.pane.x + leaf.pane.w * 0.82}
                y2={leaf.pane.y + leaf.pane.h * 0.18}
              />
            )}
            {insulated && <InsulatedRing pane={leaf.pane} />}
          </g>
        ),
      )}
      {isDoor && thresholdH > 0 && (
        <Member
          x={region.x}
          y={region.y + region.h - thresholdH}
          w={region.w}
          h={thresholdH}
          surface={memberSurface(
            members.threshold?.material ?? members.frame.material,
            (members.threshold ?? members.frame).finish?.exterior,
          )}
          className="member-threshold"
        />
      )}
      {leafGeom.map((leaf, index) =>
        leaf.operable && leaf.pane.w > 60 && leaf.pane.h > 60 ? (
          <OpeningGlyph
            key={`glyph-${index}`}
            opening={leaf.leaf.key}
            x={leaf.pane.x}
            y={leaf.pane.y}
            w={leaf.pane.w}
            h={leaf.pane.h}
            doorHinge={leaf.doorHinge ?? (node.door_handedness === "RIGHT" ? "right" : "left")}
            view={view}
          />
        ) : null,
      )}
      {/* Technical verbosity: the declared handle height reads as a datum
       * tick on the leaf's free edge plus its mm from the module's outer
       * bottom — the mark a workshop sheet carries next to the lever. */}
      {technical &&
        leafGeom.map((leaf, index) => {
          if (!leaf.operable || leaf.passive || !leaf.handleSide) return null;
          const tickX =
            leaf.handleSide === "right" ? leaf.box.x + leaf.box.w - sashT : leaf.box.x + sashT;
          const labelX = leaf.handleSide === "right" ? tickX - 10 : tickX + 10;
          return (
            <g
              key={`datum-${index}`}
              className={`handle-datum${datumInvalid ? " is-invalid" : ""}`}
              aria-hidden="true"
            >
              <line
                x1={tickX}
                y1={datumY}
                x2={tickX + (leaf.handleSide === "right" ? -34 : 34)}
                y2={datumY}
              />
              <text
                x={labelX}
                y={datumY - 8}
                textAnchor={
                  leaf.handleSide === "right"
                    ? view === "exterior"
                      ? "start"
                      : "end"
                    : view === "exterior"
                      ? "end"
                      : "start"
                }
                transform={
                  view === "exterior" ? `translate(${labelX * 2} 0) scale(-1 1)` : undefined
                }
              >
                {fmtMm(Math.round(heightMm))}
              </text>
            </g>
          );
        })}
      {leafGeom.map((leaf, index) => {
        if (!leaf.operable || leaf.passive) return null;
        if (leaf.handleTop) {
          // Banderola / abatimiento: handle centred on the free (top) member.
          const hx = leaf.box.x + leaf.box.w / 2;
          const hy = leaf.box.y + sashT * 0.9;
          return (
            <g key={`handle-${index}`} transform={`rotate(-90 ${hx} ${hy})`}>
              <HandleLever x={hx} y={hy} side="right" invalid={false} />
            </g>
          );
        }
        if (!leaf.handleSide) return null;
        return (
          <HandleLever
            key={`handle-${index}`}
            x={
              leaf.handleSide === "right"
                ? leaf.box.x + leaf.box.w - sashT * 0.55
                : leaf.box.x + sashT * 0.55
            }
            // The lever mounts at the declared height measured up from the
            // module's outer bottom edge — the OUTER_BOTTOM datum the
            // manufacturing authority resolves (1050 mm when undeclared). A
            // declared value that lands off the leaf draws clamped AND
            // flagged — the incompatibility is shown, never hidden.
            y={datumY}
            side={leaf.handleSide}
            invalid={datumInvalid}
            declaredMm={declaredMm ?? undefined}
          />
        );
      })}
      {leafGeom.map((leaf, index) =>
        leaf.passive && leaf.hinge && (leaf.hinge === "LEFT" || leaf.hinge === "RIGHT") ? (
          <g key={`falleba-${index}`} className="falleba-bolts" aria-hidden="true">
            {/* Flush bolts at the passive leaf's free stile, top and bottom. */}
            <rect
              x={
                leaf.hinge === "LEFT"
                  ? leaf.box.x + leaf.box.w - sashT * 0.8
                  : leaf.box.x + sashT * 0.45
              }
              y={leaf.box.y + sashT * 0.35}
              width={sashT * 0.35}
              height={Math.min(leaf.box.h * 0.06, 22)}
            />
            <rect
              x={
                leaf.hinge === "LEFT"
                  ? leaf.box.x + leaf.box.w - sashT * 0.8
                  : leaf.box.x + sashT * 0.45
              }
              y={leaf.box.y + leaf.box.h - sashT * 0.35 - Math.min(leaf.box.h * 0.06, 22)}
              width={sashT * 0.35}
              height={Math.min(leaf.box.h * 0.06, 22)}
            />
          </g>
        ) : null,
      )}
      {isDoor &&
        leafGeom.map((leaf, index) =>
          leaf.operable && leaf.doorHinge ? (
            <g key={`hinges-${index}`} className="door-hinges" aria-hidden="true">
              {[0.18, 0.5, 0.82].map((ratio) => (
                <rect
                  key={ratio}
                  className="door-hinge"
                  x={
                    leaf.doorHinge === "left" ? leaf.box.x : leaf.box.x + leaf.box.w - sashT * 0.34
                  }
                  y={leaf.box.y + leaf.box.h * ratio - sashT * 0.28}
                  width={sashT * 0.34}
                  height={sashT * 0.56}
                />
              ))}
            </g>
          ) : null,
        )}
      {selectRing}
    </g>
  );
}

/** Where a pointerdown on a divider grip lands: everything the drag loop
 * needs to convert pointer movement into a candidate split_offset_mm. */
export type DividerDragInfo = {
  event: React.PointerEvent<SVGRectElement>;
  divisionId: string;
  vertical: boolean;
  localOrigin: { x: number; y: number };
  /** Absolute start of the split region on the drag axis (front-elevation
   * mm) — offsets measure from `localOrigin`, so the clamp needs this to
   * keep the mullion inside the region, not just positive. */
  regionLoMm: number;
  /** Extent of the region the divider splits — the clamp range for offsets. */
  extentMm: number;
};

/** Render a module's parametric tree inside a region: splits become mullion
 * members at their catalog face width, bays render the full member hierarchy. */
function ModuleTree({
  node,
  region,
  localOrigin,
  members,
  liveOffsets,
  hitMm,
  onDividerDown,
  moduleId,
  selectedBayId,
  onSelectBay,
  selectedDivisionId = null,
  onSelectDivision,
  showSplitDims = false,
  moduleBottom,
  unitKind = "WINDOW",
  view = "interior",
  technical = false,
}: {
  node: IntentNode;
  region: Region;
  /** Sheet-space origin the node's split_offset_mm measures from — engine
   * parity: (0,0) = module outer edge for the top node, the node's own rect
   * origin for children. */
  localOrigin: { x: number; y: number };
  members: MemberGeometry;
  /** In-flight divider drags: division node id → candidate offset mm. The
   * preview value flows through the same layout math so the whole tree
   * breathes while the user drags. */
  liveOffsets?: Map<string, number>;
  /** Grip width in mm — sized from the viewport scale so it stays ~12px. */
  hitMm?: number;
  onDividerDown?: (info: DividerDragInfo) => void;
  moduleId: string;
  selectedBayId?: string | null;
  onSelectBay?: (bayId: string) => void;
  /** Division (mullion/transom) selection + technical split labels. */
  selectedDivisionId?: string | null;
  onSelectDivision?: (divisionId: string) => void;
  showSplitDims?: boolean;
  /** Sheet-space y of the module's outer bottom edge, threaded to bays for
   * the declared handle datum. */
  moduleBottom?: number;
  /** The unit root's declared kind — bays below a door unit draw door
   * rails/thresholds without repeating the declaration per bay. */
  unitKind?: UnitKind;
  /** Declared elevation view — "exterior" inverts the dash convention. */
  view?: ElevationView;
  /** Technical verbosity — bays add handle-height datum marks. */
  technical?: boolean;
}): JSX.Element {
  if (node.type === "ROOT" && node.children?.length === 1 && node.children[0]) {
    return (
      <ModuleTree
        node={node.children[0]}
        region={region}
        localOrigin={localOrigin}
        members={members}
        liveOffsets={liveOffsets}
        hitMm={hitMm}
        onDividerDown={onDividerDown}
        moduleId={moduleId}
        selectedBayId={selectedBayId}
        onSelectBay={onSelectBay}
        selectedDivisionId={selectedDivisionId}
        onSelectDivision={onSelectDivision}
        showSplitDims={showSplitDims}
        moduleBottom={moduleBottom}
        unitKind={node.children[0].unit_kind ?? "WINDOW"}
        view={view}
        technical={technical}
      />
    );
  }
  if ((node.type === "SPLIT_V" || node.type === "SPLIT_H") && node.children?.length === 2) {
    const [first, second] = node.children;
    const vertical = node.type === "SPLIT_V";
    const mullion = vertical ? members.mullionV : members.mullionH;
    const barW = mullion?.faceWidthMm ?? Math.max(Math.min(region.w, region.h) * 0.05, 20);
    const lo = vertical ? region.x : region.y;
    const extent = vertical ? region.w : region.h;
    const stored = Number(node.split_offset_mm);
    const offset = liveOffsets?.get(node.id) ?? stored;
    // Engine parity (geometry._walk_node): the mullion centerline sits at
    // local-origin + split_offset_mm. The top node's origin is the module's
    // outer edge; each child's origin is its own rect's origin. Clamped into
    // the region for display only — the engine flags out-of-range offsets.
    const desired = (vertical ? localOrigin.x : localOrigin.y) + offset;
    const axis =
      Number.isFinite(offset) && offset > 0
        ? Math.min(Math.max(desired, lo + barW / 2), lo + extent - barW / 2)
        : lo + extent / 2;
    const firstRegion: Region = vertical
      ? { x: region.x, y: region.y, w: axis - barW / 2 - region.x, h: region.h }
      : { x: region.x, y: region.y, w: region.w, h: axis - barW / 2 - region.y };
    const secondRegion: Region = vertical
      ? {
          x: axis + barW / 2,
          y: region.y,
          w: region.x + region.w - (axis + barW / 2),
          h: region.h,
        }
      : {
          x: region.x,
          y: axis + barW / 2,
          w: region.w,
          h: region.y + region.h - (axis + barW / 2),
        };
    const bar: Region =
      node.type === "SPLIT_V"
        ? { x: axis - barW / 2, y: region.y, w: barW, h: region.h }
        : { x: region.x, y: axis - barW / 2, w: region.w, h: barW };
    const grip = Math.min(Math.max(barW + 8, hitMm ?? 46), extent * 0.6);
    return (
      <>
        <ModuleTree
          node={first!}
          region={firstRegion}
          localOrigin={{ x: firstRegion.x, y: firstRegion.y }}
          members={members}
          liveOffsets={liveOffsets}
          hitMm={hitMm}
          onDividerDown={onDividerDown}
          moduleId={moduleId}
          selectedBayId={selectedBayId}
          onSelectBay={onSelectBay}
          selectedDivisionId={selectedDivisionId}
          onSelectDivision={onSelectDivision}
          showSplitDims={showSplitDims}
          moduleBottom={moduleBottom}
          unitKind={node.unit_kind ?? unitKind}
          view={view}
          technical={technical}
        />
        <ModuleTree
          node={second!}
          region={secondRegion}
          localOrigin={{ x: secondRegion.x, y: secondRegion.y }}
          members={members}
          liveOffsets={liveOffsets}
          hitMm={hitMm}
          onDividerDown={onDividerDown}
          moduleId={moduleId}
          selectedBayId={selectedBayId}
          onSelectBay={onSelectBay}
          selectedDivisionId={selectedDivisionId}
          onSelectDivision={onSelectDivision}
          moduleBottom={moduleBottom}
          showSplitDims={showSplitDims}
          unitKind={node.unit_kind ?? unitKind}
          view={view}
          technical={technical}
        />
        {/* The mullion, its dim and the grip draw after both subtrees so the
            bar stays selectable and its label stays visible where the second
            region's bays overlap the hit zone. */}
        <Member
          x={bar.x}
          y={bar.y}
          w={Math.max(bar.w, 0)}
          h={Math.max(bar.h, 0)}
          surface={memberSurface(
            mullion?.material ?? members.frame.material,
            (mullion ?? members.frame).finish?.exterior,
          )}
          className={`member-mullion${selectedDivisionId === node.id ? " is-selected" : ""}`}
        />
        {showSplitDims && (
          <text
            className="split-dim"
            x={vertical ? bar.x + bar.w + 6 : bar.x + 8}
            y={vertical ? bar.y + 16 : bar.y - 6}
            {...(view === "exterior"
              ? {
                  // Contra-espejo del rótulo dentro del grupo espejado:
                  // el texto queda legible y anclado en el mismo punto.
                  transform: `translate(${(vertical ? bar.x + bar.w + 6 : bar.x + 8) * 2} 0) scale(-1 1)`,
                  textAnchor: "end" as const,
                }
              : {})}
          >
            {fmtMm(Math.round(offset))}
          </text>
        )}
        {(onDividerDown || onSelectDivision) && (
          <rect
            className={`divider-grip${vertical ? " is-vertical" : " is-horizontal"}${selectedDivisionId === node.id ? " is-selected" : ""}`}
            x={vertical ? axis - grip / 2 : bar.x}
            y={vertical ? bar.y : axis - grip / 2}
            width={vertical ? grip : Math.max(bar.w, 0)}
            height={vertical ? Math.max(bar.h, 0) : grip}
            onClick={(event) => {
              event.stopPropagation();
              onSelectDivision?.(node.id);
            }}
            onPointerDown={(event) =>
              onDividerDown?.({
                event,
                divisionId: node.id,
                vertical,
                localOrigin,
                regionLoMm: lo,
                extentMm: extent,
              })
            }
          />
        )}
        {(onDividerDown || onSelectDivision) && (vertical ? bar.h : bar.w) > grip * 1.6 && (
          <g className="divider-grip-dots" pointerEvents="none" aria-hidden="true">
            {[-1, 0, 1].map((slot) => (
              <circle
                key={slot}
                cx={vertical ? axis : bar.x + bar.w / 2 + slot * grip * 0.22}
                cy={vertical ? bar.y + bar.h / 2 + slot * grip * 0.22 : axis}
                r={Math.max(grip * 0.07, 1.4)}
              />
            ))}
          </g>
        )}
      </>
    );
  }
  return (
    <Bay
      node={node}
      region={region}
      members={members}
      selected={selectedBayId === node.id}
      onSelect={onSelectBay ? () => onSelectBay(node.id) : undefined}
      moduleBottom={moduleBottom}
      unitKind={node.unit_kind ?? unitKind}
      view={view}
      technical={technical}
    />
  );
}

const TOP_GUTTER = 150;
const SIDE_GUTTER = 130;
const BOTTOM_GUTTER = 120;
const LEFT_GUTTER = 195;

/** D07 · Cota doble — el vano de obra alrededor de la medida de
 * fabricación, con la holgura (o el solape) entre ambas rectas. El lienzo
 * sigue dibujando el producto igual; el vano entra como envolvente punteada
 * con su propia cadena de cotas por fuera de la del producto. */
export interface VanoDim {
  /** Medida usada del vano (la menor de los puntos medidos). */
  widthMm: number;
  heightMm: number;
  /** mm por lado entre el borde del vano y el del producto: positivo el
   * vano envuelve (holgura de montaje), negativo el producto solapa el
   * vano (montaje sobre vano / traslapado). */
  gap: { top: number; right: number; bottom: number; left: number };
  /** Etiqueta del tipo de montaje que produjo las holguras. */
  mountingLabel: string;
}
const VANO_TOP_AT = -115;
const VANO_LEFT_AT = -260;
const VANO_TOP_EXTRA = 150;
const VANO_LEFT_EXTRA = 150;

/** Architectural dimension run: extension lines from the measured edge out
 * to the dim line (overshooting it slightly), diagonal ticks at each mark,
 * mono labels placed by the caller between them. */
function DimRun({
  marks,
  edge,
  at,
  vertical,
}: {
  /** axis positions (x for horizontal runs, y for vertical) of each measured edge */
  marks: number[];
  /** cross-axis coordinate where the measured edge sits (extensions start here) */
  edge: number;
  /** cross-axis coordinate of the dim line itself */
  at: number;
  vertical: boolean;
}): JSX.Element {
  const first = Math.min(...marks);
  const last = Math.max(...marks);
  const direction = at > edge ? 1 : -1;
  const overshoot = at + direction * 14;
  return (
    <g className="dim-run" aria-hidden="true">
      {marks.map((mark, index) =>
        vertical ? (
          <line
            key={`ext-${index}`}
            className="dim-extension"
            x1={edge}
            y1={mark}
            x2={overshoot}
            y2={mark}
          />
        ) : (
          <line
            key={`ext-${index}`}
            className="dim-extension"
            x1={mark}
            y1={edge}
            x2={mark}
            y2={overshoot}
          />
        ),
      )}
      {vertical ? (
        <line className="dim-line" x1={at} y1={first} x2={at} y2={last} />
      ) : (
        <line className="dim-line" x1={first} y1={at} x2={last} y2={at} />
      )}
      {marks.map((mark, index) =>
        vertical ? (
          <line
            key={`tick-${index}`}
            className="dim-tick"
            x1={at - 8}
            y1={mark + 8}
            x2={at + 8}
            y2={mark - 8}
          />
        ) : (
          <line
            key={`tick-${index}`}
            className="dim-tick"
            x1={mark - 8}
            y1={at + 8}
            x2={mark + 8}
            y2={at - 8}
          />
        ),
      )}
    </g>
  );
}

function AddHandle({
  x,
  y,
  label,
  disabled,
  onAdd,
}: {
  x: number;
  y: number;
  label: string;
  disabled: boolean;
  onAdd(): void;
}): JSX.Element {
  return (
    <g
      className="add-handle"
      role="button"
      aria-label={label}
      tabIndex={disabled ? -1 : 0}
      onClick={() => !disabled && onAdd()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (!disabled) onAdd();
        }
      }}
    >
      <circle cx={x} cy={y} r={34} />
      <path d={`M${x - 14} ${y} H${x + 14} M${x} ${y - 14} V${y + 14}`} />
    </g>
  );
}

export interface FrontModuleRect {
  module: ProductJson["assembly"]["modules"][number];
  x: number;
  w: number;
  /** Member's bottom edge above the assembly baseline (0 for column roots). */
  sill: number;
  h: number;
}

export interface FrontColumn {
  rootId: string;
  x: number;
  w: number;
  top: number;
}

export interface FrontJoint {
  couplingId: string | null;
  /** Seam position: x for a column seam, the member's sill for a stack. */
  x: number;
  top: number;
  w: number;
  y: number;
  kind: "column" | "stack";
  angleDeg: string | null;
}

export interface FrontLayout {
  rects: FrontModuleRect[];
  columns: FrontColumn[];
  joints: FrontJoint[];
  totalW: number;
  /** The nominal top edge — tallest (sill + height) across members. */
  height: number;
  /** mm the drawing band lifts/dips for arc overshoot past the vertex box. */
  lift: number;
  dip: number;
  /** mm side bows extend past the nominal member extents (0 when none). */
  leftOver: number;
  rightOver: number;
}

/** Front elevation layout — mirrors the engine's `elevation_layout`: front
 * columns advance left→right at each root's declared width, STACKED members
 * share their column and pile bottom-up (a member's sill is its partner's
 * top edge), and narrower members centre. Couplers overlay their seam: an
 * INLINE seam draws vertically between columns, a STACKED contact draws
 * horizontally across the hanging member. */
export function frontLayout(product: ProductJson): FrontLayout {
  const { pairs, stackParent, stackRoot } = resolveStacks(product);
  const layoutMm = elevationLayoutMm(product);
  const rects: FrontModuleRect[] = layoutMm.members.map((member) => ({
    module: member.module,
    x: member.x,
    w: member.w,
    sill: member.sill,
    h: member.h,
  }));
  const columns: FrontColumn[] = layoutMm.columns;

  // A stacked member wider than its column protrudes past the column band —
  // shift the whole layout so the leftmost member edge lands at x=0 and
  // totalW spans member extents (mirrors the engine's envelope).
  const left = rects.length > 0 ? Math.min(...rects.map((rect) => rect.x)) : 0;
  const right = rects.length > 0 ? Math.max(...rects.map((rect) => rect.x + rect.w)) : 0;
  const shift = -left;
  if (shift !== 0) {
    for (const rect of rects) rect.x += shift;
    for (const column of columns) column.x += shift;
  }

  // Column seams carry the bound INLINE coupling's angle; stack contacts
  // carry the coupling that declared them — the member's own sill line.
  const pairCoupling = new Map<string, (typeof pairs)[number]["coupling"]>();
  for (const { coupling, pair } of pairs) {
    const rootA = stackRoot.get(pair[0]) ?? pair[0];
    const rootB = stackRoot.get(pair[1]) ?? pair[1];
    if (rootA !== rootB) {
      const key = [rootA, rootB].sort().join("|");
      if (!pairCoupling.has(key)) pairCoupling.set(key, coupling);
    }
  }
  const memberCoupling = new Map<string, string>();
  for (const { coupling, pair } of pairs) {
    if (coupling.kind !== "STACKED") continue;
    const member = pair.find(
      (id) => stackParent.get(id) === pair[0] || stackParent.get(id) === pair[1],
    );
    if (member !== undefined) memberCoupling.set(member, coupling.id);
  }
  const rectById = new Map(rects.map((rect) => [rect.module.id, rect]));
  const joints: FrontJoint[] = [];
  for (let i = 0; i + 1 < columns.length; i += 1) {
    const left = columns[i]!;
    const right = columns[i + 1]!;
    const coupling = pairCoupling.get([left.rootId, right.rootId].sort().join("|"));
    joints.push({
      couplingId: coupling?.id ?? null,
      kind: "column",
      x: left.x + left.w,
      top: Math.min(left.top, right.top),
      w: Math.min(left.w, right.w),
      y: 0,
      angleDeg:
        !coupling || coupling.kind === "INLINE" || coupling.kind === undefined
          ? (coupling?.angle_deg ?? null)
          : null,
    });
  }
  for (const [memberId, couplingId] of memberCoupling) {
    const rect = rectById.get(memberId);
    if (rect) {
      joints.push({
        couplingId,
        kind: "stack",
        x: rect.x,
        y: rect.sill,
        w: rect.w,
        top: 0,
        angleDeg: null,
      });
    }
  }

  // Arc crowns overshoot the springline band; the whole drawing lifts so
  // the silhouette stays inside the bounds instead of clipping the gutter.
  const height =
    rects.length > 0
      ? Math.max(...rects.map((rect) => rect.sill + rect.h)) -
        Math.min(...rects.map((rect) => rect.sill))
      : 0;
  let lift = 0;
  let dip = 0;
  let leftOver = 0;
  let rightOver = 0;
  for (const rect of rects) {
    if (!rect.module.contour) continue;
    const outset = contourOutset(rect.module.contour);
    lift = Math.max(lift, rect.sill + rect.h + outset.top - height);
    dip = Math.max(dip, outset.bottom - rect.sill);
    // A side-bowed edge bulges past the module's nominal side — expand the
    // drawing band horizontally like lift/dip expand it vertically.
    leftOver = Math.max(leftOver, outset.left - rect.x);
    rightOver = Math.max(rightOver, rect.x + rect.w + outset.right - (right - left));
  }
  return {
    rects,
    columns,
    joints,
    totalW: right - left,
    height,
    lift,
    dip,
    leftOver,
    rightOver,
  };
}

function isFrontLayout(value: ProductJson | FrontLayout): value is FrontLayout {
  return "rects" in value && "totalW" in value;
}

function asLayout(value: ProductJson | FrontLayout): FrontLayout {
  return isFrontLayout(value) ? value : frontLayout(value);
}

/** The drawable extent of the front elevation including gutters and chains.
 * `extraBottomMm` reserves room for the technical furniture under the sill
 * (per-bay chain + sliding plan strips) — ProductFrontContent reports the
 * real budget via `technicalExtraBottom`. */
export function frontBounds(
  source: ProductJson | FrontLayout,
  vano?: VanoDim | null,
  extraBottomMm = 0,
) {
  const { totalW, height, lift, dip, leftOver, rightOver } = asLayout(source);
  // La cadena del vano corre por fuera de la del producto: el sheet crece
  // solo cuando hay registro del vano que mostrar.
  const extraTop = vano ? VANO_TOP_EXTRA : 0;
  const extraLeft = vano ? VANO_LEFT_EXTRA : 0;
  return {
    x: -LEFT_GUTTER - leftOver - extraLeft,
    y: -TOP_GUTTER - extraTop,
    w: totalW + LEFT_GUTTER + SIDE_GUTTER + leftOver + rightOver + extraLeft,
    h: height + TOP_GUTTER + BOTTOM_GUTTER + lift + dip + extraTop + extraBottomMm,
  };
}

/** Extra bottom gutter a technical sheet needs: per-bay chain row plus a
 * plan strip under every sliding bay (strips sit under their own bay, so
 * one strip row covers them all — only a taller track count grows it). */
export function technicalExtraBottom(
  rects: FrontModuleRect[],
  members: MemberGeometry,
  height: number,
  frameT: number,
): number {
  const bays = leafBaysOf(rects, members, height, frameT);
  let bottom = BAY_CHAIN_AT + 70;
  for (const bay of bays) {
    const layout = resolvedSlidingLayout(bay.node);
    if (!bay.node.opening_type || !isSlidingOpening(bay.node.opening_type) || !layout) continue;
    const stripBottom =
      PLAN_STRIP_AT + Math.max(layout.tracks, 1) * PLAN_TRACK_H + PLAN_STRIP_BOTTOM;
    bottom = Math.max(bottom, stripBottom);
  }
  return bottom;
}

/** Sheet-space box of a module's frame — the Shift+2 / zoom-to-selection target. */
export function frontModuleBox(source: ProductJson | FrontLayout, moduleId: string | null) {
  if (!moduleId) return null;
  const layout = asLayout(source);
  const rect = layout.rects.find((item) => item.module.id === moduleId);
  if (!rect) return null;
  const top = layout.height - rect.sill - rect.h;
  return { x: rect.x - 30, y: top - 60, w: rect.w + 60, h: rect.h + 150 };
}

/** A leaf bay's sheet-space rect plus the origin a split inside it measures
 * from (engine parity: module outer edge for the top node, the bay's own
 * rect for nested ones). */
type LeafRegion = {
  id: string;
  region: Region;
  origin: { x: number; y: number };
  node: IntentNode;
};

/** Leaf bays under a node with the same layout math ModuleTree renders —
 * lets the divide tool hit-test the actual bay under the cursor. */
function bayRegions(
  node: IntentNode,
  region: Region,
  origin: { x: number; y: number },
  members: MemberGeometry,
): LeafRegion[] {
  if (node.type === "ROOT" && node.children?.length === 1 && node.children[0]) {
    return bayRegions(node.children[0], region, origin, members);
  }
  if ((node.type === "SPLIT_V" || node.type === "SPLIT_H") && node.children?.length === 2) {
    const [first, second] = node.children;
    const vertical = node.type === "SPLIT_V";
    const mullion = vertical ? members.mullionV : members.mullionH;
    const barW = mullion?.faceWidthMm ?? Math.max(Math.min(region.w, region.h) * 0.05, 20);
    const lo = vertical ? region.x : region.y;
    const extent = vertical ? region.w : region.h;
    const offset = Number(node.split_offset_mm);
    const desired = (vertical ? origin.x : origin.y) + offset;
    const axis =
      Number.isFinite(offset) && offset > 0
        ? Math.min(Math.max(desired, lo + barW / 2), lo + extent - barW / 2)
        : lo + extent / 2;
    const firstRegion: Region = vertical
      ? { x: region.x, y: region.y, w: axis - barW / 2 - region.x, h: region.h }
      : { x: region.x, y: region.y, w: region.w, h: axis - barW / 2 - region.y };
    const secondRegion: Region = vertical
      ? {
          x: axis + barW / 2,
          y: region.y,
          w: region.x + region.w - (axis + barW / 2),
          h: region.h,
        }
      : {
          x: region.x,
          y: axis + barW / 2,
          w: region.w,
          h: region.y + region.h - (axis + barW / 2),
        };
    return [
      ...bayRegions(first!, firstRegion, { x: firstRegion.x, y: firstRegion.y }, members),
      ...bayRegions(second!, secondRegion, { x: secondRegion.x, y: secondRegion.y }, members),
    ];
  }
  return [{ id: node.id, region, origin, node }];
}

/** Leaf bays of every module in sheet space — the shared math between the
 * technical bay chain and the sliding plan strips. */
function leafBaysOf(
  rects: FrontModuleRect[],
  members: MemberGeometry,
  height: number,
  frameT: number,
): LeafRegion[] {
  return rects.flatMap((rect) => {
    if (rect.module.frameless || rect.module.contour) return [];
    const top = height - rect.sill - rect.h;
    return bayRegions(
      rect.module.tree,
      {
        x: rect.x + frameT,
        y: top + frameT,
        w: Math.max(rect.w - frameT * 2, 0),
        h: Math.max(rect.h - frameT * 2, 0),
      },
      { x: rect.x, y: top },
      members,
    );
  });
}

/** Technical drawing budget under the sill: the per-bay chain sits at
 * +130 and a sliding bay's plan strip at +210 (rail rows + labels). */
const BAY_CHAIN_AT = 130;
const PLAN_STRIP_AT = 210;
const PLAN_TRACK_H = 26;
const PLAN_STRIP_BOTTOM = 70;

/** P05 — cinta de planta bajo el alzado técnico de una corredera: corte
 * horizontal con los rieles numerados (riel 1 = el más exterior), las
 * hojas en su posición declarada y la flecha de desplazamiento. EXTERIOR
 * arriba / INTERIOR abajo, como el dibujo a mano alzada del taller. */
function SlidingPlanStrip({
  region,
  layout,
  top,
  mirrored,
  totalW,
}: {
  region: Region;
  layout: SlidingLayout;
  top: number;
  mirrored: boolean;
  totalW: number;
}): JSX.Element {
  const bx = mirrored ? totalW - region.x - region.w : region.x;
  const bw = region.w;
  const tracks = Math.max(layout.tracks, 1);
  const count = Math.max(layout.panels.length, 1);
  const pitch = bw / count;
  const stripH = tracks * PLAN_TRACK_H;
  const labelX = bx + bw + 14;
  return (
    <g className="sliding-plan" aria-hidden="true">
      <rect className="plan-wall" x={bx} y={top} width={bw} height={stripH} />
      {Array.from({ length: tracks }, (_, track) => (
        <g key={`rail-${track}`}>
          <line
            className="plan-rail"
            x1={bx}
            y1={top + PLAN_TRACK_H * (track + 0.5)}
            x2={bx + bw}
            y2={top + PLAN_TRACK_H * (track + 0.5)}
          />
          <text
            className="plan-rail-no"
            x={labelX}
            y={top + PLAN_TRACK_H * (track + 0.5)}
            dominantBaseline="central"
          >
            {track + 1}
          </text>
        </g>
      ))}
      {layout.panels.map((panel, index) => {
        const track = panel.track ?? 0;
        // El riel 0 es el más exterior — dibujado arriba del corte.
        const slotX = mirrored ? bx + bw - pitch * (index + 1) : bx + pitch * index;
        const midY = top + PLAN_TRACK_H * (track + 0.5);
        const travel = panel.kind === "MOVING" ? panelTravel(panel, index, count) : null;
        const dir =
          travel === null ? null : mirrored ? (travel === "LEFT" ? "RIGHT" : "LEFT") : travel;
        return (
          <g
            key={`plan-panel-${index}`}
            className={`plan-panel plan-panel--${panel.kind.toLowerCase()}`}
          >
            <rect
              x={slotX + 2}
              y={midY - PLAN_TRACK_H * 0.32}
              width={Math.max(pitch - 4, 0)}
              height={PLAN_TRACK_H * 0.64}
            />
            {dir !== null &&
              glyphPaths(
                [{ k: "arrow", dir, inferred: travelInferred(panel) }],
                slotX,
                top + PLAN_TRACK_H * track,
                pitch,
                PLAN_TRACK_H,
              ).map((entry, entryIndex) => (
                <path
                  key={`plan-arrow-${entryIndex}`}
                  className={`plan-arrow${entry.inferred ? " glyph-inferred" : ""}`}
                  d={entry.d}
                  fill="none"
                />
              ))}
          </g>
        );
      })}
      <text
        className="plan-side"
        x={bx - 10}
        y={top + PLAN_TRACK_H * 0.5}
        textAnchor="end"
        dominantBaseline="central"
      >
        {t("assembly.planExterior")}
      </text>
      <text
        className="plan-side"
        x={bx - 10}
        y={top + stripH - PLAN_TRACK_H * 0.5}
        textAnchor="end"
        dominantBaseline="central"
      >
        {t("assembly.planInterior")}
      </text>
    </g>
  );
}

export function ProductFrontContent({
  product,
  members,
  selectedId,
  selectedBayId = null,
  selectedDivisionId = null,
  issues,
  disabled,
  preview = false,
  divideTool = null,
  dimLevel = "design",
  onSelectModule,
  onSelectBay,
  onSelectDivision,
  onSelectCoupling,
  onContextMenuModule,
  onAddUnit,
  onCommitModuleWidth,
  onCommitTotalWidth,
  onCommitHeight,
  onCommitDivide,
  onMoveDivision,
  onResizeSeam,
  vano = null,
  view = "interior",
}: {
  product: ProductJson;
  members: MemberGeometry;
  selectedId: string | null;
  issues: ProductIssue[];
  disabled: boolean;
  /** Thumbnail mode: draws the members but strips every interactive
   * affordance (roles, tab stops, handlers) so it can live inside a
   * single outer button. */
  preview?: boolean;
  /** Armed divide tool — hovering shows where the mullion lands and
   * clicking splits the leaf bay under the cursor at the cursor offset. */
  divideTool?: "SPLIT_V" | "SPLIT_H" | null;
  onSelectModule(moduleId: string): void;
  /** Click a leaf bay: selects the "moduleId/bayId" composite — the right
   * rail then edits that leaf's opening, glazing and handle. */
  onSelectBay?(moduleId: string, bayId: string): void;
  /** The leaf inside the selected module that owns the selection ring —
   * a composite selection highlights the bay, not the whole module. */
  selectedBayId?: string | null;
  /** The selected division node (mullion/transom) — highlights its bar. */
  selectedDivisionId?: string | null;
  /** §04-E dimension verbosity: overview = overall W/H only, design adds
   * per-column widths, technical adds split offsets + member heights. */
  dimLevel?: "overview" | "design" | "technical";
  onSelectDivision?(moduleId: string, divisionId: string): void;
  /** Click the coupler band between members → selects the coupling (the
   * object that owns the joint, not either neighbor module). */
  onSelectCoupling?(couplingId: string): void;
  /** Right-click on a module: select it and open the registry menu at the
   * cursor — commands always resolve against the clicked element, never a
   * stale earlier selection. */
  onContextMenuModule?(moduleId: string, pos: { x: number; y: number }): void;
  onAddUnit(side: "left" | "right"): void;
  onCommitModuleWidth(moduleId: string, widthMm: string): void;
  onCommitTotalWidth(totalMm: string): void;
  onCommitHeight(heightMm: string): void;
  onCommitDivide?(moduleId: string, bayId: string | null, offsetMm?: string): void;
  onMoveDivision?(moduleId: string, divisionId: string, offsetMm: string): void;
  onResizeSeam?(seamIndex: number, deltaMm: number): void;
  /** D07 — el vano de obra con sus holguras por lado; cuando viene, se
   * dibuja la cota doble (vano + fabricación) por fuera de la del
   * producto. */
  vano?: VanoDim | null;
  /** P05 — vista declarada del alzado: "exterior" espeja el dibujo e
   * invierte la convención continuo/discontinuo (un paño que abre hacia
   * dentro se dibuja discontinuo visto desde afuera). La vista exterior
   * es de lectura: edición y arrastres solo en vista interior. */
  view?: ElevationView;
}): JSX.Element {
  const { couplings } = product.assembly;
  const frameT = members.frame.faceWidthMm;
  const frameSurface = memberSurface(members.frame.material, members.frame.finish?.exterior);
  // Layout derivation runs over every module — memoize so seam/division
  // drags (per-pointermove renders) don't rebuild the whole elevation.
  const { rects, columns, joints, totalW, height, lift } = useMemo(
    () => frontLayout(product),
    [product],
  );
  const issueMap = useMemo(() => severityByModule(issues), [issues]);
  const midY = height / 2;
  const mirrored = view === "exterior";
  const mx = (value: number) => (mirrored ? totalW - value : value);
  const leafBays = useMemo(
    () => leafBaysOf(rects, members, height, frameT),
    [rects, members, height, frameT],
  );
  const slidingBays = useMemo(
    () =>
      leafBays
        .filter((bay) => bay.node.opening_type && isSlidingOpening(bay.node.opening_type))
        .map((bay) => ({ bay, layout: resolvedSlidingLayout(bay.node) }))
        .filter((entry): entry is { bay: LeafRegion; layout: SlidingLayout } =>
          Boolean(entry.layout),
        ),
    [leafBays],
  );
  const interactive = !preview && !disabled;
  // En vista exterior el alzado es de lectura: se puede seleccionar pero
  // no arrastrar divisiones ni costuras (un drag espejado invertiría el
  // delta contra la intención del usuario).
  const dragsEnabled = interactive && !mirrored;
  const sheetScale = useViewportScale();
  // ~12px on screen is the smallest usable drag target (W3C pointer
  // guidance); never wider than a third of the smallest affected span.
  const hitMm = Math.min(160, Math.max(24, 12 / sheetScale));

  const frontRef = useRef<SVGGElement>(null);
  const [liveOffsets, setLiveOffsets] = useState<Map<string, number>>(new Map());
  const [seamDrag, setSeamDrag] = useState<{ index: number; deltaMm: number } | null>(null);
  const [dividePreview, setDividePreview] = useState<{
    moduleId: string;
    line: { x1: number; y1: number; x2: number; y2: number };
  } | null>(null);
  const divideHover = useRef<{ bayId: string; mm: number } | null>(null);

  /** Active drag teardown: cancelling removes the window listeners AND runs
   * the drag's own abort, so its live preview is always cleared — on
   * pointercancel, on unmount, or when a second pointer starts a new drag. */
  const dragDetach = useRef<(() => void) | null>(null);
  useEffect(() => () => dragDetach.current?.(), []);

  /** Installs window-level drag listeners bound to ONE pointer: a second
   * finger or pen can neither steer nor commit another pointer's drag.
   * `onRelease` runs on pointerup (commit), `onAbort` on pointercancel or
   * unmount — never a commit. Starting a new drag CANCELS the old one: its
   * listeners are removed and its abort runs, so no preview state leaks. */
  const trackDrag = (
    pointerId: number,
    onMove: (event: globalThis.PointerEvent) => void,
    onRelease: (event: globalThis.PointerEvent) => void,
    onAbort: () => void,
  ): void => {
    dragDetach.current?.();
    const detach = (): void => {
      window.removeEventListener("pointermove", onGuardedMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      if (dragDetach.current === cancel) dragDetach.current = null;
    };
    const cancel = (): void => {
      detach();
      onAbort();
    };
    const onGuardedMove = (event: globalThis.PointerEvent): void => {
      if (event.pointerId === pointerId) onMove(event);
    };
    const onUp = (event: globalThis.PointerEvent): void => {
      if (event.pointerId !== pointerId) return;
      detach();
      onRelease(event);
    };
    const onCancel = (event: globalThis.PointerEvent): void => {
      if (event.pointerId !== pointerId) return;
      cancel();
    };
    window.addEventListener("pointermove", onGuardedMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    dragDetach.current = cancel;
  };

  /** Client coordinates → front-elevation millimetres (inverse CTM works at
   * any pan/zoom the viewport applies). */
  const pointInFront = (clientX: number, clientY: number) => {
    const el = frontRef.current;
    const ctm = el?.getScreenCTM();
    if (!el || !ctm) return null;
    return new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  };

  const snapMm = (mm: number) => Math.round(mm / 5) * 5;

  /** Divider grip: live-preview the whole layout while dragging, commit the
   * snapped offset on release. */
  const beginDividerDrag =
    (moduleId: string) =>
    (info: DividerDragInfo): void => {
      if (!interactive || !onMoveDivision) return;
      info.event.preventDefault();
      info.event.stopPropagation();
      let last = Number.NaN;
      // The stored offset measures from the bay's own origin, which can sit
      // before the region start (top level: module outer edge vs frame inset).
      // Clamp the offset so the centerline stays 60mm inside the region.
      const originAxis = info.vertical ? info.localOrigin.x : info.localOrigin.y;
      const lo = info.regionLoMm - originAxis + 60;
      const hi = info.regionLoMm + info.extentMm - originAxis - 60;
      const clamp = (mm: number) => Math.min(Math.max(mm, lo), Math.max(lo, hi));
      const onMove = (event: globalThis.PointerEvent) => {
        const pt = pointInFront(event.clientX, event.clientY);
        if (!pt) return;
        last = clamp(info.vertical ? pt.x - info.localOrigin.x : pt.y - info.localOrigin.y);
        setLiveOffsets(new Map([[info.divisionId, last]]));
      };
      trackDrag(
        info.event.pointerId,
        onMove,
        (event) => {
          onMove(event);
          setLiveOffsets(new Map());
          if (Number.isFinite(last))
            onMoveDivision(moduleId, info.divisionId, fmtWire(snapMm(last)));
        },
        () => setLiveOffsets(new Map()),
      );
    };

  /** Module seam: left module grows, right module shrinks — total width
   * holds. A ghost line tracks the candidate seam; commit on release. */
  const beginSeamDrag = (seamIndex: number) => (event: PointerEvent<SVGRectElement>) => {
    if (!interactive || !onResizeSeam) return;
    event.preventDefault();
    event.stopPropagation();
    const left = columns[seamIndex];
    const right = columns[seamIndex + 1];
    if (!left || !right) return;
    const origin = pointInFront(event.clientX, event.clientY);
    if (!origin) return;
    let last = 0;
    const lo = MIN_MODULE_WIDTH_MM - left.w;
    const hi = right.w - MIN_MODULE_WIDTH_MM;
    const onMove = (move: globalThis.PointerEvent) => {
      const pt = pointInFront(move.clientX, move.clientY);
      if (!pt) return;
      last = Math.min(Math.max(pt.x - origin.x, lo), hi);
      setSeamDrag({ index: seamIndex, deltaMm: last });
    };
    trackDrag(
      event.pointerId,
      onMove,
      (up) => {
        onMove(up);
        setSeamDrag(null);
        // Snap first, then re-clamp — a 5mm rounding step can otherwise push
        // the seam outside the range the preview itself allowed.
        const snapped = Math.min(Math.max(snapMm(last), lo), hi);
        if (snapped !== 0) onResizeSeam(seamIndex, snapped);
      },
      () => setSeamDrag(null),
    );
  };

  /** The leaf bay + snapped bay-local offset a client point divides — shared
   * by hover preview and click commit so a touch tap (no prior pointermove)
   * resolves the same bay a mouse hover would. */
  const divideHit = (moduleId: string, clientX: number, clientY: number) => {
    const pt = pointInFront(clientX, clientY);
    if (!pt) return null;
    const rect = rects.find((item) => item.module.id === moduleId);
    if (!rect) return null;
    const memberTop = height - rect.sill - rect.h;
    const bay = bayRegions(
      rect.module.tree,
      { x: rect.x + frameT, y: memberTop + frameT, w: rect.w - frameT * 2, h: rect.h - frameT * 2 },
      { x: rect.x, y: memberTop },
      members,
    ).find(
      (leaf) =>
        pt.x >= leaf.region.x &&
        pt.x <= leaf.region.x + leaf.region.w &&
        pt.y >= leaf.region.y &&
        pt.y <= leaf.region.y + leaf.region.h,
    );
    if (!bay) return null;
    const vertical = divideTool === "SPLIT_V";
    const lo = (vertical ? bay.region.x : bay.region.y) + 60;
    const hi = lo - 60 + Math.max(0, (vertical ? bay.region.w : bay.region.h) - 60);
    const originAxis = vertical ? bay.origin.x : bay.origin.y;
    const axis = Math.min(Math.max(vertical ? pt.x : pt.y, lo), hi);
    const mm = snapMm(axis - originAxis);
    return {
      bayId: bay.id,
      mm,
      line: vertical
        ? { x1: axis, y1: bay.region.y, x2: axis, y2: bay.region.y + bay.region.h }
        : { x1: bay.region.x, y1: axis, x2: bay.region.x + bay.region.w, y2: axis },
    };
  };

  /** Armed divide tool: hit-test the leaf bay under the cursor and preview
   * the mullion inside it; the snapped bay-local offset commits on click. */
  const previewDivide = (moduleId: string) => (event: PointerEvent) => {
    if (!divideTool) return;
    const hit = divideHit(moduleId, event.clientX, event.clientY);
    if (!hit) {
      divideHover.current = null;
      setDividePreview(null);
      return;
    }
    divideHover.current = { bayId: hit.bayId, mm: hit.mm };
    setDividePreview({ moduleId, line: hit.line });
  };

  const endDivide = (moduleId: string, clientX?: number, clientY?: number) => {
    // A touch tap produces a click without any pointermove: resolve the bay
    // from the click coordinates then. Only a keyboard commit (no pointer
    // position at all) falls back to centering the primary bay.
    const hovered =
      divideHover.current ??
      (clientX !== undefined && clientY !== undefined
        ? divideHit(moduleId, clientX, clientY)
        : null);
    setDividePreview(null);
    divideHover.current = null;
    if (!divideTool || !onCommitDivide) return;
    if (!rects.some((item) => item.module.id === moduleId)) return;
    if (hovered) {
      onCommitDivide(moduleId, hovered.bayId, fmtWire(hovered.mm));
    } else if (clientX === undefined && clientY === undefined) {
      // Only a keyboard commit (no pointer position) may fall back to
      // centering the primary bay — a pointer click that landed on frame,
      // coupler or empty canvas must not guess a bay.
      onCommitDivide(moduleId, null);
    }
  };

  const seamLeftMm =
    seamDrag !== null && columns[seamDrag.index]
      ? columns[seamDrag.index]!.w + seamDrag.deltaMm
      : null;
  const seamRightMm =
    seamDrag !== null && columns[seamDrag.index + 1]
      ? columns[seamDrag.index + 1]!.w - seamDrag.deltaMm
      : null;

  return (
    <g className="product-front-svg" data-testid="product-front" ref={frontRef}>
      {/* overall width chain — untranslated so it always clears the
          tallest silhouette point (arc crowns sit at viewBox y ≥ 0). */}
      <DimRun marks={[0, totalW]} edge={0} at={-70} vertical={false} />
      <SvgDim
        x={totalW / 2}
        y={-70}
        value={fmtMmCanonical(totalW)}
        label={t("assembly.totalWidth")}
        disabled={disabled}
        onCommit={onCommitTotalWidth}
      />
      {/* P05 — la vista declarada queda rotulada en el alzado mismo;
          es la referencia que fija la convención continuo/discontinuo.
          Fuera del lift: el rótulo ancla al borde superior de la lámina. */}
      {!preview && (
        <text
          className="view-legend"
          x={totalW}
          y={-TOP_GUTTER + 44}
          textAnchor="end"
          data-view={view}
        >
          {t(view === "exterior" ? "assembly.viewExterior" : "assembly.viewInterior")}
        </text>
      )}
      {/* the drawing band lifts for arc overshoot: sill stays shared. */}
      <g transform={`translate(0 ${lift})`}>
        {/* D07 — cota doble: el vano de obra envuelve la fabricación con la
            holgura por lado; la propia cadena corre por fuera de la del
            producto. gap<0 (sobre vano / traslapado) el producto solapa el
            vano y la envolvente queda por dentro. En vista exterior la
            holgura izquierda del dato se dibuja a la derecha de la lámina. */}
        {vano !== null &&
          (() => {
            const gapL = mirrored ? vano.gap.right : vano.gap.left;
            const gapR = mirrored ? vano.gap.left : vano.gap.right;
            return (
              <g className="vano-overlay" aria-hidden="true">
                <rect
                  className="vano-outline"
                  x={-gapL}
                  y={-vano.gap.top}
                  width={gapL + totalW + gapR}
                  height={vano.gap.top + height + vano.gap.bottom}
                />
                <DimRun
                  marks={[-gapL, totalW + gapR]}
                  edge={-vano.gap.top}
                  at={VANO_TOP_AT}
                  vertical={false}
                />
                <text className="vano-dim" x={totalW / 2} y={VANO_TOP_AT - 30} textAnchor="middle">
                  {`${t("assembly.vano")} ${fmtMm(vano.widthMm)}`}
                </text>
                {vano.mountingLabel !== "" && (
                  <text
                    className="vano-dim vano-dim--mount"
                    x={totalW / 2}
                    y={VANO_TOP_AT - 72}
                    textAnchor="middle"
                  >
                    {vano.mountingLabel}
                  </text>
                )}
                <DimRun
                  marks={[-vano.gap.top, height + vano.gap.bottom]}
                  edge={-gapL}
                  at={VANO_LEFT_AT}
                  vertical={true}
                />
                <g transform={`rotate(-90 ${VANO_LEFT_AT} ${midY})`}>
                  <text className="vano-dim" x={VANO_LEFT_AT} y={midY} textAnchor="middle">
                    {`${t("assembly.vano")} ${fmtMm(vano.heightMm)}`}
                  </text>
                </g>
                {vano.gap.top !== 0 && (
                  <text
                    className="vano-gap"
                    x={totalW / 2}
                    y={-vano.gap.top / 2 + 10}
                    textAnchor="middle"
                  >
                    {`${vano.gap.top > 0 ? t("assembly.vanoClearance") : t("assembly.vanoOverlap")} ${fmtMm(Math.abs(vano.gap.top))}`}
                  </text>
                )}
                {gapL !== 0 && (
                  <g transform={`rotate(-90 ${-gapL / 2} ${midY})`}>
                    <text className="vano-gap" x={-gapL / 2} y={midY} textAnchor="middle">
                      {`${gapL > 0 ? t("assembly.vanoClearance") : t("assembly.vanoOverlap")} ${fmtMm(Math.abs(gapL))}`}
                    </text>
                  </g>
                )}
                {gapR !== 0 && (
                  <g transform={`rotate(90 ${totalW + gapR / 2} ${midY})`}>
                    <text className="vano-gap" x={totalW + gapR / 2} y={midY} textAnchor="middle">
                      {`${gapR > 0 ? t("assembly.vanoClearance") : t("assembly.vanoOverlap")} ${fmtMm(Math.abs(gapR))}`}
                    </text>
                  </g>
                )}
              </g>
            );
          })()}
        {/* height chain */}
        <DimRun marks={[0, height]} edge={0} at={-160} vertical={true} />
        <g transform={`rotate(-90 ${-160} ${midY})`}>
          <SvgDim
            x={-160}
            y={midY}
            value={fmtMmCanonical(height)}
            label={t("assembly.height")}
            disabled={disabled}
            onCommit={onCommitHeight}
          />
        </g>
        {/* per-column width chain — stacked members share the column span
            (design/technical only: overview keeps the overall W/H). En vista
            exterior la cadena se dibuja en coordenadas espejadas: la columna
            declarada a la izquierda aparece a la derecha de la lámina. */}
        {dimLevel !== "overview" && (
          <>
            <DimRun
              marks={columns
                .flatMap((column) => [mx(column.x), mx(column.x + column.w)])
                .sort((a, b) => a - b)}
              edge={height}
              at={height + 80}
              vertical={false}
            />
            {columns.map((column) => (
              <SvgDim
                key={`dim-${column.rootId}`}
                x={mx(column.x + column.w / 2)}
                y={height + 80}
                value={fmtMmCanonical(column.w)}
                label={`${t("assembly.module")} ${column.rootId} ${t("assembly.width")}`}
                active={column.rootId === selectedId}
                disabled={disabled || mirrored}
                onCommit={(value) => onCommitModuleWidth(column.rootId, value)}
              />
            ))}
          </>
        )}
        {/* P05 — vista técnica: cadena interior por vanos (anchos de bay
            bajo su módulo) y cintas de planta bajo cada corredera. */}
        {dimLevel === "technical" &&
          rects.map((rect) => {
            const moduleBays = leafBays
              .filter(
                (bay) =>
                  bay.region.x >= rect.x - 0.01 &&
                  bay.region.x + bay.region.w <= rect.x + rect.w + 0.01,
              )
              .sort((a, b) => a.region.x - b.region.x);
            if (moduleBays.length < 2) return null;
            const marks = [
              ...new Set(
                moduleBays.flatMap((bay) => [mx(bay.region.x), mx(bay.region.x + bay.region.w)]),
              ),
            ].sort((a, b) => a - b);
            return (
              <g key={`bay-chain-${rect.module.id}`}>
                <DimRun marks={marks} edge={height} at={height + BAY_CHAIN_AT} vertical={false} />
                {marks.slice(0, -1).map((mark, index) => {
                  const segW = marks[index + 1]! - mark;
                  if (segW < 110) return null;
                  return (
                    <text
                      key={`bay-dim-${index}`}
                      className="member-dim"
                      x={mark + segW / 2}
                      y={height + BAY_CHAIN_AT}
                      textAnchor="middle"
                      dominantBaseline="central"
                    >
                      {fmtMm(Math.round(segW))}
                    </text>
                  );
                })}
              </g>
            );
          })}
        {dimLevel === "technical" &&
          slidingBays.map(({ bay, layout }) => (
            <SlidingPlanStrip
              key={`plan-${bay.id}`}
              region={bay.region}
              layout={layout}
              top={height + PLAN_STRIP_AT}
              mirrored={mirrored}
              totalW={totalW}
            />
          ))}
        {/* technical adds member heights for stacked columns — a transom
            over a unit is dimensioned like a shop drawing, right gutter. */}
        {dimLevel === "technical" &&
          columns.map((column, columnIndex) => {
            const membersOf = rects.filter(
              (rect) =>
                rect.x + rect.w / 2 >= column.x && rect.x + rect.w / 2 <= column.x + column.w,
            );
            if (membersOf.length < 2) return null;
            const marks = [
              ...new Set(
                membersOf.flatMap((rect) => [height - rect.sill, height - rect.sill - rect.h]),
              ),
            ].sort((a, b) => a - b);
            // En exterior la canaleta derecha del dato es la izquierda de la
            // lámina: la cadena corre del lado que la vista muestra.
            const chainX = mirrored ? column.x - 30 : column.x + column.w + 30;
            const textX = mirrored ? column.x - 38 : column.x + column.w + 38;
            return (
              <g key={`member-dims-${column.rootId}-${columnIndex}`}>
                <DimRun
                  marks={marks}
                  edge={mirrored ? column.x : column.x + column.w}
                  at={chainX}
                  vertical={true}
                />
                {membersOf.map((rect) => (
                  <text
                    key={`member-dim-${rect.module.id}`}
                    className="member-dim"
                    x={textX}
                    y={height - rect.sill - rect.h / 2}
                    textAnchor={mirrored ? "end" : "start"}
                  >
                    {fmtMm(Math.round(rect.h))}
                  </text>
                ))}
              </g>
            );
          })}
        <AddHandle
          x={mx(0) - 70}
          y={midY}
          label={t("assembly.addUnitLeft")}
          disabled={disabled || mirrored}
          onAdd={() => onAddUnit("left")}
        />
        <AddHandle
          x={mx(totalW) + 70}
          y={midY}
          label={t("assembly.addUnitRight")}
          disabled={disabled || mirrored}
          onAdd={() => onAddUnit("right")}
        />
        {/* Vista exterior: el dibujo se espeja completo (scale(-1,1) sobre
            el eje central) — cotas, leyendas y cintas de planta viven fuera
            y se posicionan en coordenadas espejadas vía `mx()`. */}
        <g
          transform={mirrored ? `translate(${totalW} 0) scale(-1 1)` : undefined}
          data-view-group={view}
        >
          {rects.map(({ module, x, w, sill, h }) => {
            const top = height - sill - h;
            return (
              <g
                key={module.id}
                className={`front-module${module.id === selectedId ? " is-selected" : ""}${issueMap.get(module.id) === "error" ? " has-error" : issueMap.get(module.id) === "warning" ? " has-warning" : ""}${divideTool ? " is-divide-target" : ""}`}
                {...(preview
                  ? { role: "presentation", "aria-hidden": true }
                  : {
                      role: "button",
                      "aria-label": `${t("assembly.module")} ${module.id}`,
                      "aria-pressed": module.id === selectedId,
                      tabIndex: disabled ? -1 : 0,
                      onClick: (event) =>
                        divideTool
                          ? endDivide(module.id, event.clientX, event.clientY)
                          : onSelectModule(module.id),
                      onContextMenu: (event) => {
                        if (!onContextMenuModule) return;
                        event.preventDefault();
                        event.stopPropagation();
                        onContextMenuModule(module.id, { x: event.clientX, y: event.clientY });
                      },
                      onKeyDown: (event: KeyboardEvent) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          if (divideTool) endDivide(module.id);
                          else onSelectModule(module.id);
                        }
                      },
                      onPointerMove: divideTool ? previewDivide(module.id) : undefined,
                      onPointerLeave: divideTool
                        ? () => {
                            setDividePreview(null);
                            divideHover.current = null;
                          }
                        : undefined,
                    })}
              >
                {module.frameless ? (
                  <g transform={`translate(${x} ${top})`}>
                    <FramelessModule spec={module.frameless} x={0} top={0} w={w} h={h} />
                  </g>
                ) : module.contour ? (
                  <g transform={`translate(${x} ${top})`}>
                    <path
                      className="member-frame"
                      d={contourPathD(module.contour, h)}
                      fill={frameSurface.fill}
                      stroke={frameSurface.edge}
                      strokeWidth={2}
                    />
                    <path
                      className="module-opening module-opening--lite"
                      d={pointsPathD(insetContourPoints(module.contour, frameT), h)}
                    />
                  </g>
                ) : (
                  <>
                    <Member
                      x={x}
                      y={top}
                      w={w}
                      h={h}
                      surface={frameSurface}
                      className="member-frame"
                    />
                    <rect
                      className="module-opening"
                      x={x + frameT}
                      y={top + frameT}
                      width={Math.max(w - frameT * 2, 0)}
                      height={Math.max(h - frameT * 2, 0)}
                    />
                    <ModuleTree
                      moduleId={module.id}
                      selectedBayId={selectedBayId}
                      onSelectBay={
                        interactive && !divideTool && onSelectBay
                          ? (bayId) => onSelectBay(module.id, bayId)
                          : undefined
                      }
                      selectedDivisionId={selectedDivisionId}
                      onSelectDivision={
                        interactive && !divideTool && onSelectDivision
                          ? (divisionId) => onSelectDivision(module.id, divisionId)
                          : undefined
                      }
                      showSplitDims={dimLevel === "technical"}
                      technical={dimLevel === "technical"}
                      view={view}
                      node={module.tree}
                      region={{
                        x: x + frameT,
                        y: top + frameT,
                        w: w - frameT * 2,
                        h: h - frameT * 2,
                      }}
                      localOrigin={{ x, y: top }}
                      moduleBottom={top + h}
                      members={members}
                      liveOffsets={liveOffsets}
                      hitMm={hitMm}
                      onDividerDown={
                        dragsEnabled && onMoveDivision && !divideTool
                          ? beginDividerDrag(module.id)
                          : undefined
                      }
                    />
                  </>
                )}
                {dividePreview?.moduleId === module.id && (
                  <line className="divide-preview-line" {...dividePreview.line} />
                )}
              </g>
            );
          })}
          {joints.map((joint, index) => {
            const coupling = joint.couplingId
              ? couplings.find((item) => item.id === joint.couplingId)
              : undefined;
            const width =
              members.couplerFor(coupling?.coupler_profile_sku ?? null)?.faceWidthMm ?? 60;
            const couplerSpec = members.couplerFor(coupling?.coupler_profile_sku ?? null);
            const surface = memberSurface(
              couplerSpec?.material ?? members.frame.material,
              (couplerSpec ?? members.frame).finish?.exterior,
            );
            const pickable = interactive && !divideTool && onSelectCoupling && joint.couplingId;
            const jointRect =
              joint.kind === "column"
                ? { x: joint.x - width / 2, y: height - joint.top, w: width, h: joint.top }
                : { x: joint.x, y: height - joint.y - width / 2, w: joint.w, h: width };
            const selectedJoint = selectedId === joint.couplingId;
            return (
              <g key={joint.couplingId ?? `joint-${index}`}>
                <Member
                  x={jointRect.x}
                  y={jointRect.y}
                  w={jointRect.w}
                  h={jointRect.h}
                  surface={surface}
                  className={`member-coupler${selectedJoint ? " is-selected" : ""}`}
                />
                {pickable && (
                  <rect
                    className={`joint-hit${selectedJoint ? " is-selected" : ""}`}
                    x={jointRect.x}
                    y={jointRect.y}
                    width={jointRect.w}
                    height={jointRect.h}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (joint.couplingId) onSelectCoupling?.(joint.couplingId);
                    }}
                  />
                )}
              </g>
            );
          })}
          {/* Seam grips render above the coupler members so the drag target is
          not swallowed by the coupler rect — one grip per column boundary. */}
          {dragsEnabled &&
            onResizeSeam &&
            !divideTool &&
            columns.slice(0, -1).map((column, index) => {
              const neighbor = columns[index + 1];
              const seamW = Math.min(
                hitMm,
                Math.max(12, Math.min(column.w, neighbor?.w ?? column.w) * 0.5),
              );
              return (
                <g key={`seam-${index}`}>
                  <rect
                    className="seam-grip"
                    x={column.x + column.w - seamW / 2}
                    y={0}
                    width={seamW}
                    height={height}
                    onPointerDown={beginSeamDrag(index)}
                  />
                  {/* Resting drag affordance: three dots mid-seam so the grip
                  doesn't need a lucky hover to be discovered. */}
                  {height > seamW * 2.4 &&
                    [-1, 0, 1].map((slot) => (
                      <circle
                        key={slot}
                        className="seam-grip-dot"
                        cx={column.x + column.w}
                        cy={height / 2 + slot * seamW * 0.5}
                        r={Math.max(seamW * 0.1, 1.4)}
                        pointerEvents="none"
                      />
                    ))}
                </g>
              );
            })}
          {seamDrag && seamLeftMm !== null && seamRightMm !== null && (
            <g className="seam-preview" aria-hidden="true">
              <line
                className="seam-preview-line"
                x1={columns[seamDrag.index]!.x + columns[seamDrag.index]!.w + seamDrag.deltaMm}
                y1={0}
                x2={columns[seamDrag.index]!.x + columns[seamDrag.index]!.w + seamDrag.deltaMm}
                y2={height}
              />
              <text
                className="seam-preview-label"
                x={columns[seamDrag.index]!.x + columns[seamDrag.index]!.w + seamDrag.deltaMm}
                y={-40}
                textAnchor="middle"
              >
                {`${fmtMm(Math.round(seamLeftMm))} | ${fmtMm(Math.round(seamRightMm))}`}
              </text>
            </g>
          )}
        </g>
      </g>
    </g>
  );
}

/** Standalone front elevation with its own viewBox — the sheet viewer
 * (CanvasViewport) renders `ProductFrontContent` inside its own transform
 * instead; this wrapper stays for any consumer that just wants an SVG. */
export function ProductFrontSvg(props: Parameters<typeof ProductFrontContent>[0]): JSX.Element {
  const front = frontLayout(props.product);
  const extraBottom =
    props.dimLevel === "technical"
      ? technicalExtraBottom(
          front.rects,
          props.members,
          front.height,
          props.members.frame.faceWidthMm,
        )
      : 0;
  const bounds = frontBounds(front, props.vano ?? null, extraBottom);
  return (
    <svg
      className="product-front-svg"
      viewBox={`${bounds.x} ${bounds.y} ${bounds.w} ${bounds.h}`}
      role="img"
      aria-label={t("assembly.frontView")}
    >
      <ProductFrontContent {...props} />
    </svg>
  );
}
