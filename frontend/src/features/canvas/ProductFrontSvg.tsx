import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import type { ProductIssue } from "../../api/generated/models";
import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";
import type { IntentNode } from "./intentEditing";
import { isSlidingOpening, resolvedSlidingLayout } from "./intentEditing";
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
          const normalized = normalizeDimension(draft);
          if (normalized !== null && normalized !== value) onCommit(normalized);
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
            setDraft(value);
            event.currentTarget.blur();
          }
        }}
      />
    </foreignObject>
  );
}

function normalizeDimension(candidate: string): string | null {
  const value = Number(candidate.trim().replace(",", ".").replace(/[°\s]/g, ""));
  if (!Number.isFinite(value) || value <= 0) return null;
  return value.toFixed(2);
}

/** Industry opening glyph: hinge side = triangle base, handle = apex. */
export function OpeningGlyph({
  opening,
  x,
  y,
  w,
  h,
  doorHinge,
}: {
  opening: string | null | undefined;
  x: number;
  y: number;
  w: number;
  h: number;
  doorHinge?: "left" | "right";
}): JSX.Element {
  const padX = w * 0.2;
  const padY = h * 0.2;
  const left = x + padX;
  const right = x + w - padX;
  const top = y + padY;
  const bottom = y + h - padY;
  const cx = x + w / 2;
  const cy = y + h / 2;
  const kind = opening ?? "FIXED";
  return (
    <g className={`opening-glyph opening-${kind.toLowerCase()}`} aria-hidden="true">
      {kind.includes("RIGHT") && (
        <polyline points={`${right},${top} ${left},${cy} ${right},${bottom}`} fill="none" />
      )}
      {kind.includes("LEFT") && (
        <polyline points={`${left},${top} ${right},${cy} ${left},${bottom}`} fill="none" />
      )}
      {kind.startsWith("TILT") && (
        <polyline points={`${left},${bottom} ${cx},${top} ${right},${bottom}`} fill="none" />
      )}
      {/* Awning is top-hinged — its triangle mirrors the issued doc (base at
          the top edge), not the tilt glyph. */}
      {kind === "AWNING" && (
        <polyline points={`${left},${top} ${cx},${bottom} ${right},${top}`} fill="none" />
      )}
      {kind.startsWith("SLIDING") &&
        (() => {
          const panes = { SLIDING_3L: 3, SLIDING_4L: 4 }[kind] ?? 2;
          const paneW = (right - left) / panes;
          return Array.from({ length: panes }, (_, index) => {
            const boundary = left + paneW * index;
            const mid = boundary + paneW / 2;
            const arrow = paneW * 0.22;
            return (
              <g key={`sliding-${index}`}>
                {index > 0 && <line x1={boundary} y1={top} x2={boundary} y2={bottom} />}
                <path
                  d={`M${mid - arrow} ${cy} H${mid + arrow} M${mid + arrow * 0.5} ${cy - h * 0.05} L${mid + arrow} ${cy}`}
                  fill="none"
                />
              </g>
            );
          });
        })()}
      {/* A door glyph shows its swing: quarter-arc centred on the bottom
       * hinge corner plus a jamb tick on the hinge side. */}
      {kind === "DOOR_ENTRY" &&
        (() => {
          const hingeX = doorHinge === "right" ? right : left;
          const sweepTo =
            doorHinge === "right" ? right - Math.min(w, h) * 0.8 : left + Math.min(w, h) * 0.8;
          const arcR = Math.min(w, h) * 0.8;
          const sweep = doorHinge === "right" ? 1 : 0;
          return (
            <>
              <line x1={hingeX} y1={top} x2={hingeX} y2={bottom} opacity={0.5} />
              <path
                d={`M ${sweepTo} ${bottom} A ${arcR} ${arcR} 0 0 ${sweep} ${hingeX} ${bottom - arcR}`}
                fill="none"
              />
            </>
          );
        })()}
      {kind === "FIXED" && <line x1={left} y1={top} x2={right} y2={bottom} opacity={0.18} />}
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
            />
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
            />
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
              />
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
}: {
  x: number;
  y: number;
  side: "left" | "right";
}): JSX.Element {
  const dir = side === "left" ? 1 : -1;
  return (
    <g className="handle-lever" aria-hidden="true">
      <line x1={x} y1={y - 10} x2={x} y2={y + 16} strokeWidth={5} strokeLinecap="round" />
      <line x1={x} y1={y} x2={x + dir * 18} y2={y} strokeWidth={5} strokeLinecap="round" />
    </g>
  );
}

/** A leaf bay: sash ring (when operable), glazing bead sightline, glass or
 * panel infill, opening glyph and handle lever. */
function Bay({
  node,
  region,
  members,
  selected = false,
  onSelect,
  moduleBottom,
}: {
  node: IntentNode;
  region: Region;
  members: MemberGeometry;
  selected?: boolean;
  onSelect?(): void;
  /** Sheet-space y of the module's outer bottom edge — the datum the
   * declared handle height measures up from (OUTER_BOTTOM authority). */
  moduleBottom?: number;
}): JSX.Element {
  const opening = node.opening_type ?? "FIXED";
  const bead = members.beadFor(node.glass_thickness_mm ?? null);
  const insulated = Number(node.glass_thickness_mm ?? "0") >= 12;
  const sashSurface = memberSurface(members.sash.material);
  const baySelectProps = onSelect
    ? {
        onClick: (event: React.MouseEvent) => {
          event.stopPropagation();
          onSelect();
        },
        role: "button" as const,
        "aria-label": `${t("intent.bay")} · ${t(OPENING_OPTIONS.find(([value]) => value === opening)?.[1] ?? "intent.fixed")}`,
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
          const midX = leafX + leafW / 2;
          const midY = region.y + region.h / 2;
          const arrow = Math.min(leafW, region.h) * 0.16;
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
              <path
                className="sliding-arrow"
                // Travel convention shared with the 3D pose: a leaf opens
                // toward its neighbouring slot — leaves in the left half of
                // the bay slide right, the right half slides left. The
                // product model declares no travel, so this stays a
                // presentation convention, not manufacturing truth.
                d={(() => {
                  const dir = index * 2 < panels.length ? 1 : -1;
                  const tip = midX + arrow * dir;
                  const tail = midX - arrow * dir;
                  const barb = tip - dir * arrow * 0.5;
                  return `M${tail} ${midY} H${tip} M${barb} ${midY - arrow * 0.4} L${tip} ${midY} L${barb} ${midY + arrow * 0.4}`;
                })()}
                fill="none"
              />
            </g>
          );
        })}
        {selectRing}
      </g>
    );
  }

  const isDoor = opening === "DOOR_ENTRY";
  const operable = opening !== "FIXED";
  const reveal = 3;

  const thresholdH = isDoor ? (members.threshold?.faceWidthMm ?? 30) : 0;
  const sashArea: Region = operable
    ? {
        x: region.x + reveal,
        y: region.y + reveal,
        w: region.w - reveal * 2,
        h: region.h - reveal * 2 - thresholdH,
      }
    : region;
  const sashT = members.sash.faceWidthMm;
  const glass: Region = operable
    ? {
        x: sashArea.x + sashT,
        y: sashArea.y + sashT,
        w: sashArea.w - sashT * 2,
        h: sashArea.h - sashT * 2,
      }
    : {
        x: region.x + bead,
        y: region.y + bead,
        w: region.w - bead * 2,
        h: region.h - bead * 2,
      };
  const pane: Region = operable
    ? { x: glass.x + bead, y: glass.y + bead, w: glass.w - bead * 2, h: glass.h - bead * 2 }
    : glass;
  const isPanel = Boolean(node.panel_article_sku);
  // DIN: the opening name is the hinge side; the handle sits opposite. A
  // door carries no side in its opening type — the declared
  // `door_handedness` (hinge side) decides, defaulting to hinge-left.
  const handleSide = opening.includes("LEFT")
    ? "right"
    : opening.includes("RIGHT")
      ? "left"
      : isDoor
        ? node.door_handedness === "RIGHT"
          ? "left"
          : "right"
        : null;

  return (
    <g
      className={`module-bay${selected ? " is-selected" : ""}${onSelect ? " bay-pickable" : ""}`}
      {...baySelectProps}
    >
      {operable && (
        <>
          <Member
            x={sashArea.x}
            y={sashArea.y}
            w={sashArea.w}
            h={Math.max(sashArea.h, 0)}
            surface={sashSurface}
            className="member-sash"
          />
          {/* glazing beads: sightline ring inside the sash */}
          <rect
            className="member-bead"
            x={glass.x}
            y={glass.y}
            width={Math.max(glass.w, 0)}
            height={Math.max(glass.h, 0)}
          />
        </>
      )}
      {isPanel ? (
        <rect
          className="bay-panel"
          x={pane.x}
          y={pane.y}
          width={Math.max(pane.w, 0)}
          height={Math.max(pane.h, 0)}
        />
      ) : (
        <g>
          <rect
            className="module-glass"
            x={pane.x}
            y={pane.y}
            width={Math.max(pane.w, 0)}
            height={Math.max(pane.h, 0)}
          />
          {/* The sheen only belongs on inert glass — under an operable leaf
           * it crosses the opening glyph and reads as a scribble. */}
          {pane.w > 30 && pane.h > 30 && !node.opening_type && (
            <line
              className="glass-sheen"
              x1={pane.x + pane.w * 0.18}
              y1={pane.y + pane.h * 0.82}
              x2={pane.x + pane.w * 0.82}
              y2={pane.y + pane.h * 0.18}
            />
          )}
          {insulated && <InsulatedRing pane={pane} />}
        </g>
      )}
      {isDoor && thresholdH > 0 && (
        <Member
          x={region.x}
          y={region.y + region.h - thresholdH}
          w={region.w}
          h={thresholdH}
          surface={memberSurface(members.threshold?.material ?? members.frame.material)}
          className="member-threshold"
        />
      )}
      {pane.w > 60 && pane.h > 60 && (
        <OpeningGlyph
          opening={node.opening_type}
          x={pane.x}
          y={pane.y}
          w={pane.w}
          h={pane.h}
          doorHinge={node.door_handedness === "RIGHT" ? "right" : "left"}
        />
      )}
      {handleSide && operable && (
        <HandleLever
          x={
            handleSide === "right"
              ? sashArea.x + sashArea.w - sashT * 0.55
              : sashArea.x + sashT * 0.55
          }
          // The lever mounts at the declared height measured up from the
          // module's outer bottom edge — the OUTER_BOTTOM datum the
          // manufacturing authority resolves (1050 mm when undeclared).
          // Clamped onto the sash so a stale value still lands on the leaf.
          y={(() => {
            const declared = Number(node.handle_height_mm);
            const heightMm = Number.isFinite(declared) && declared > 0 ? declared : 1050;
            const datum =
              moduleBottom !== undefined
                ? moduleBottom - heightMm
                : sashArea.y + sashArea.h - heightMm;
            return Math.min(Math.max(datum, sashArea.y + 60), sashArea.y + sashArea.h - 60);
          })()}
          side={handleSide}
        />
      )}
      {isDoor && operable && (
        <g className="door-hinges" aria-hidden="true">
          {[0.18, 0.5, 0.82].map((ratio) => (
            <rect
              key={ratio}
              className="door-hinge"
              x={handleSide === "left" ? sashArea.x + sashArea.w - sashT * 0.34 : sashArea.x}
              y={sashArea.y + sashArea.h * ratio - sashT * 0.28}
              width={sashT * 0.34}
              height={sashT * 0.56}
            />
          ))}
        </g>
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
        />
        <Member
          x={bar.x}
          y={bar.y}
          w={Math.max(bar.w, 0)}
          h={Math.max(bar.h, 0)}
          surface={memberSurface(mullion?.material ?? members.frame.material)}
          className={`member-mullion${selectedDivisionId === node.id ? " is-selected" : ""}`}
        />
        {showSplitDims && (
          <text
            className="split-dim"
            x={vertical ? bar.x + bar.w + 6 : bar.x + 8}
            y={vertical ? bar.y + 16 : bar.y - 6}
          >
            {offset.toFixed(0)}
          </text>
        )}
        {onDividerDown && (
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
              onDividerDown({
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
        {!onDividerDown && onSelectDivision && (
          <rect
            className="divider-grip"
            x={vertical ? axis - grip / 2 : bar.x}
            y={vertical ? bar.y : axis - grip / 2}
            width={vertical ? grip : Math.max(bar.w, 0)}
            height={vertical ? Math.max(bar.h, 0) : grip}
            onClick={(event) => {
              event.stopPropagation();
              onSelectDivision(node.id);
            }}
          />
        )}
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
        />
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
    />
  );
}

const TOP_GUTTER = 150;
const SIDE_GUTTER = 130;
const BOTTOM_GUTTER = 120;
const LEFT_GUTTER = 195;

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

/** The drawable extent of the front elevation including gutters and chains. */
export function frontBounds(source: ProductJson | FrontLayout) {
  const { totalW, height, lift, dip, leftOver, rightOver } = asLayout(source);
  return {
    x: -LEFT_GUTTER - leftOver,
    y: -TOP_GUTTER,
    w: totalW + LEFT_GUTTER + SIDE_GUTTER + leftOver + rightOver,
    h: height + TOP_GUTTER + BOTTOM_GUTTER + lift + dip,
  };
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
  return [{ id: node.id, region, origin }];
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
}): JSX.Element {
  const { couplings } = product.assembly;
  const frameT = members.frame.faceWidthMm;
  const frameSurface = memberSurface(members.frame.material);
  // Layout derivation runs over every module — memoize so seam/division
  // drags (per-pointermove renders) don't rebuild the whole elevation.
  const { rects, columns, joints, totalW, height, lift } = useMemo(
    () => frontLayout(product),
    [product],
  );
  const issueMap = useMemo(() => severityByModule(issues), [issues]);
  const midY = height / 2;
  const interactive = !preview && !disabled;
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
            onMoveDivision(moduleId, info.divisionId, snapMm(last).toFixed(2));
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
      onCommitDivide(moduleId, hovered.bayId, hovered.mm.toFixed(2));
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
        value={totalW.toFixed(2)}
        label={t("assembly.totalWidth")}
        disabled={disabled}
        onCommit={onCommitTotalWidth}
      />
      {/* the drawing band lifts for arc overshoot: sill stays shared. */}
      <g transform={`translate(0 ${lift})`}>
        {/* height chain */}
        <DimRun marks={[0, height]} edge={0} at={-160} vertical={true} />
        <g transform={`rotate(-90 ${-160} ${midY})`}>
          <SvgDim
            x={-160}
            y={midY}
            value={height.toFixed(2)}
            label={t("assembly.height")}
            disabled={disabled}
            onCommit={onCommitHeight}
          />
        </g>
        {/* per-column width chain — stacked members share the column span
            (design/technical only: overview keeps the overall W/H). */}
        {dimLevel !== "overview" && (
          <>
            <DimRun
              marks={columns.flatMap((column) => [column.x, column.x + column.w])}
              edge={height}
              at={height + 80}
              vertical={false}
            />
            {columns.map((column) => (
              <SvgDim
                key={`dim-${column.rootId}`}
                x={column.x + column.w / 2}
                y={height + 80}
                value={column.w.toFixed(2)}
                label={`${t("assembly.module")} ${column.rootId} ${t("assembly.width")}`}
                active={column.rootId === selectedId}
                disabled={disabled}
                onCommit={(value) => onCommitModuleWidth(column.rootId, value)}
              />
            ))}
          </>
        )}
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
            return (
              <g key={`member-dims-${column.rootId}-${columnIndex}`}>
                <DimRun
                  marks={marks}
                  edge={column.x + column.w}
                  at={column.x + column.w + 30}
                  vertical={true}
                />
                {membersOf.map((rect) => (
                  <text
                    key={`member-dim-${rect.module.id}`}
                    className="member-dim"
                    x={column.x + column.w + 38}
                    y={height - rect.sill - rect.h / 2}
                  >
                    {rect.h.toFixed(0)}
                  </text>
                ))}
              </g>
            );
          })}
        <AddHandle
          x={-70}
          y={midY}
          label={t("assembly.addUnitLeft")}
          disabled={disabled}
          onAdd={() => onAddUnit("left")}
        />
        <AddHandle
          x={totalW + 70}
          y={midY}
          label={t("assembly.addUnitRight")}
          disabled={disabled}
          onAdd={() => onAddUnit("right")}
        />
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
                      interactive && onMoveDivision && !divideTool
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
          const surface = memberSurface(
            members.couplerFor(coupling?.coupler_profile_sku ?? null)?.material ??
              members.frame.material,
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
        {interactive &&
          onResizeSeam &&
          !divideTool &&
          columns.slice(0, -1).map((column, index) => {
            const neighbor = columns[index + 1];
            const seamW = Math.min(
              hitMm,
              Math.max(12, Math.min(column.w, neighbor?.w ?? column.w) * 0.5),
            );
            return (
              <rect
                key={`seam-${index}`}
                className="seam-grip"
                x={column.x + column.w - seamW / 2}
                y={0}
                width={seamW}
                height={height}
                onPointerDown={beginSeamDrag(index)}
              />
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
              {`${seamLeftMm.toFixed(0)} | ${seamRightMm.toFixed(0)}`}
            </text>
          </g>
        )}
      </g>
    </g>
  );
}

/** Standalone front elevation with its own viewBox — the sheet viewer
 * (CanvasViewport) renders `ProductFrontContent` inside its own transform
 * instead; this wrapper stays for any consumer that just wants an SVG. */
export function ProductFrontSvg(props: Parameters<typeof ProductFrontContent>[0]): JSX.Element {
  const bounds = frontBounds(props.product);
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
