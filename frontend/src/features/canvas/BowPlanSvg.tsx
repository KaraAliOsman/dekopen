import { useEffect, useMemo, useRef, useState } from "react";

import type { PlanGeometry, PlanPoint, ProductIssue } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { memberSurface } from "./materials";
import type { MemberGeometry } from "./members";
import type { CouplingJson } from "./productEditing";
import { fmtWire } from "../../format";

type BowPlanSvgProps = {
  plan: PlanGeometry;
  couplings: CouplingJson[];
  members: MemberGeometry;
  selectedModuleId: string | null;
  selectedCouplingId: string | null;
  issues: ProductIssue[];
  disabled: boolean;
  onSelectModule(moduleId: string): void;
  onSelectCoupling(couplingId: string): void;
  /** Right-click on any plan element (module or coupling): select it and
   * open the registry menu at the cursor. */
  onContextMenuElement?(elementId: string, pos: { x: number; y: number }): void;
  onCommitAngle(couplingId: string, angleDeg: string): void;
};

const PAD_MM = 220;

/** P06 — snap set for angle drag: the couplers a real catalog sells cluster
 * on these deflections; the drag lands free in between. */
export const PLAN_ANGLE_SNAPS = [0, 10, 15, 22.5, 30, 45, 90] as const;
/** Degrees around a snap value that still magnet to it. */
const SNAP_TOLERANCE_DEG = 3.5;
/** Pointer travel (px of screen) before a module press becomes a rotation
 * drag instead of a plain select-click. */
const DRAG_THRESHOLD_PX = 5;
/** Editor-side bound mirroring the inspector's angle field (±90°). */
const MAX_PLAN_ANGLE_DEG = 90;

function toSvg(point: PlanPoint): [number, number] {
  // Engine y grows upward; SVG y grows downward — mirror vertically so a
  // positive coupling angle reads as the bow curving up on screen.
  return [Number(point.x_mm), -Number(point.y_mm)];
}

function svgToEngine(x: number, y: number): [number, number] {
  return [x, -y];
}

function enginePt(point: PlanPoint): [number, number] {
  return [Number(point.x_mm), Number(point.y_mm)];
}

function polygonPoints(points: PlanPoint[]): string {
  return points.map((point) => toSvg(point).join(",")).join(" ");
}

function centroid(points: PlanPoint[]): [number, number] {
  const sum = points.reduce<[number, number]>(
    (acc, point) => {
      const [x, y] = toSvg(point);
      return [acc[0] + x, acc[1] + y];
    },
    [0, 0],
  );
  return [sum[0] / points.length, sum[1] / points.length];
}

function midpoint(a: PlanPoint, b: PlanPoint): [number, number] {
  return [(Number(a.x_mm) + Number(b.x_mm)) / 2, -(Number(a.y_mm) + Number(b.y_mm)) / 2];
}

/** Degrees of a vector in engine space (y up), atan2 already in °. */
function dirDeg(dx: number, dy: number): number {
  return (Math.atan2(dy, dx) * 180) / Math.PI;
}

function normalizeDeg(deg: number): number {
  let value = deg % 360;
  if (value <= -180) value += 360;
  if (value > 180) value -= 360;
  return value;
}

/** Nearest snap value within the magnet band, else the free value — the
 * drag stays continuous except where a coupler's real geometry exists. */
export function snapAngleDeg(deg: number): number {
  let best = deg;
  let distance = SNAP_TOLERANCE_DEG + 1;
  for (const snap of PLAN_ANGLE_SNAPS) {
    for (const candidate of snap === 0 ? [0] : [snap, -snap]) {
      const gap = Math.abs(deg - candidate);
      if (gap < distance) {
        distance = gap;
        best = candidate;
      }
    }
  }
  return Math.max(-MAX_PLAN_ANGLE_DEG, Math.min(MAX_PLAN_ANGLE_DEG, best));
}

/** P06 — cotas del conjunto sobre la cadena del frente: desarrollo (suma de
 * módulos a lo largo del frente), cuerda (distancia recta entre extremos) y
 * proyección (salida máxima de la cadena respecto a la cuerda — lo que el
 * bow sale hacia fuera). */
export function planMeasures(plan: PlanGeometry): {
  developedMm: number;
  chordMm: number;
  projectionMm: number;
} {
  const chain = plan.front_chain;
  let developedMm = 0;
  for (let i = 0; i + 1 < chain.length; i += 1) {
    developedMm += Math.hypot(
      Number(chain[i + 1]!.x_mm) - Number(chain[i]!.x_mm),
      Number(chain[i + 1]!.y_mm) - Number(chain[i]!.y_mm),
    );
  }
  const first = chain[0];
  const last = chain[chain.length - 1];
  const chordMm =
    first && last
      ? Math.hypot(Number(last.x_mm) - Number(first.x_mm), Number(last.y_mm) - Number(first.y_mm))
      : 0;
  let projectionMm = 0;
  if (first && last && chordMm > 0) {
    // Perpendicular distance of each chain vertex to the chord line —
    // the engine's plan space is metric mm so this is a plain 2D measure.
    const ux = (Number(last.x_mm) - Number(first.x_mm)) / chordMm;
    const uy = (Number(last.y_mm) - Number(first.y_mm)) / chordMm;
    for (const point of chain) {
      const dx = Number(point.x_mm) - Number(first.x_mm);
      const dy = Number(point.y_mm) - Number(first.y_mm);
      projectionMm = Math.max(projectionMm, Math.abs(dx * uy - dy * ux));
    }
  }
  return { developedMm, chordMm, projectionMm };
}

/** Joint angle label: click to edit the coupling angle in place. */
function JointAngle({
  couplingId,
  x,
  y,
  angleDeg,
  liveDeg = null,
  fontSize,
  disabled,
  onCommit,
}: {
  couplingId: string;
  x: number;
  y: number;
  angleDeg: string;
  /** While a plan drag is live this is the snapped candidate — the label
   * reads where the joint WOULD land, not where it is. */
  liveDeg?: number | null;
  fontSize: number;
  disabled: boolean;
  onCommit(normalized: string): void;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(angleDeg);
  useEffect(() => {
    if (!editing) setDraft(angleDeg);
  }, [angleDeg, editing]);
  const shown = liveDeg !== null ? fmtWire(liveDeg, 1).replace(/\.0$/, "") : angleDeg;
  if (!editing || disabled) {
    return (
      <text
        className={`plan-angle${liveDeg !== null ? " is-live" : ""}`}
        data-testid={`plan-angle-${couplingId}`}
        x={x}
        y={y}
        fontSize={fontSize}
        textAnchor="middle"
        role="button"
        aria-label={`${t("assembly.angle")} ${couplingId}`}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && setEditing(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (!disabled) setEditing(true);
          }
        }}
      >
        {shown}°
      </text>
    );
  }
  return (
    <foreignObject
      x={x - fontSize * 1.6}
      y={y - fontSize * 0.9}
      width={fontSize * 3.2}
      height={fontSize * 1.7}
    >
      <input
        className="canvas-dim-input"
        aria-label={`${t("assembly.angle")} ${couplingId}`}
        autoFocus
        inputMode="decimal"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onFocus={(event) => event.target.select()}
        onBlur={() => {
          const parsed = Number(draft.trim().replace(",", ".").replace(/[°\s]/g, ""));
          if (Number.isFinite(parsed) && parsed !== Number(angleDeg)) {
            onCommit(fmtWire(parsed, 1));
          }
          setEditing(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setDraft(angleDeg);
            event.currentTarget.blur();
          }
        }}
      />
    </foreignObject>
  );
}

/** Drawable extent of the plan view in its own mm space (engine y is already
 * mirrored into SVG space by `toSvg`). */
export function planBounds(plan: PlanGeometry) {
  return {
    x: Number(plan.min_x_mm) - PAD_MM,
    y: -(Number(plan.min_y_mm) + Number(plan.height_mm)) - PAD_MM,
    w: Number(plan.width_mm) + PAD_MM * 2,
    h: Number(plan.height_mm) + PAD_MM * 2,
  };
}

type PlanDrag = {
  /** Chain vertex index of the hinge the drag rotates about. */
  hingeIndex: number;
  /** Rigid rotation (engine deg, CCW+) applied to every chain element at or
   * after the hinge — the live preview is a rotate transform, not a reflow. */
  deltaDeg: number;
  /** Snapped angle the release will commit on the hinge's coupling. */
  angleDeg: number;
  couplingId: string;
  hinge: [number, number];
};

export function BowPlanContent({
  plan,
  couplings,
  members,
  selectedModuleId,
  selectedCouplingId,
  issues,
  disabled,
  onSelectModule,
  onSelectCoupling,
  onContextMenuElement,
  onCommitAngle,
}: BowPlanSvgProps): JSX.Element {
  const bounds = planBounds(plan);
  const width = bounds.w;
  const height = bounds.h;
  const fontSize = Math.max(width, height) * 0.035;
  const dimOffset = Math.max(width, height) * 0.06;
  const chain = plan.front_chain;
  const flaggedCouplings = new Set(
    issues
      .filter((issue) => issue.target.startsWith("coupling:"))
      .map((issue) => issue.target.slice("coupling:".length)),
  );
  const [drag, setDrag] = useState<PlanDrag | null>(null);
  const groupRef = useRef<SVGGElement>(null);
  const dragCleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => dragCleanup.current?.(), []);

  /** Rotation index of a plan module: its own index for front-chain roots,
   * the anchor column's index for stacked members (their plan corners are
   * the anchor's own — the engine copies them verbatim). */
  const frontIndexOf = useMemo(() => {
    const map = new Map<string, number>();
    plan.modules.forEach((module, index) => {
      if (map.has(module.module_id)) return;
      const first = module.corners[0];
      const anchorIndex = plan.modules.findIndex(
        (candidate) =>
          Math.abs(Number(candidate.corners[0]?.x_mm ?? NaN) - Number(first?.x_mm ?? NaN)) < 0.5 &&
          Math.abs(Number(candidate.corners[0]?.y_mm ?? NaN) - Number(first?.y_mm ?? NaN)) < 0.5,
      );
      map.set(module.module_id, anchorIndex >= 0 ? anchorIndex : index);
    });
    return map;
  }, [plan.modules]);

  /** screen px → svg-mm (the outer svg's CTM holds the viewBox scale). */
  const pointInPlan = (clientX: number, clientY: number): DOMPoint | null => {
    const svg = groupRef.current?.ownerSVGElement;
    const ctm = svg?.getScreenCTM();
    if (!ctm) return null;
    return new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  };

  /** Coupling id ↔ the chain vertex it hinges at: the engine builds each
   * coupler wedge as [joint, backEnd, backLeft] — polygon[0] is the shared
   * front vertex, so the coupling keys to the chain index it sits on. */
  const vertexCoupling = useMemo(() => {
    const map = new Map<number, string>();
    for (const coupling of plan.couplings) {
      const first = coupling.polygon[0];
      if (!first) continue;
      const index = chain.findIndex(
        (point, i) =>
          i > 0 &&
          Math.abs(Number(point.x_mm) - Number(first.x_mm)) < 0.5 &&
          Math.abs(Number(point.y_mm) - Number(first.y_mm)) < 0.5,
      );
      if (index > 0 && index < chain.length - 1) map.set(index, coupling.coupling_id);
    }
    return map;
  }, [plan.couplings, chain]);
  const couplingVertex = useMemo(() => {
    const map = new Map<string, number>();
    for (const [index, id] of vertexCoupling) map.set(id, index);
    return map;
  }, [vertexCoupling]);

  /** Window-level drag bound to ONE pointer — the plan mirrors the front
   * canvas' trackDrag pattern: release commits once, cancel never commits. */
  const trackPlanDrag = (
    pointerId: number,
    onMove: (event: PointerEvent) => void,
    onRelease: (event: PointerEvent) => void,
    onAbort: () => void,
  ): void => {
    dragCleanup.current?.();
    const detach = () => {
      window.removeEventListener("pointermove", guardedMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
    };
    const guardedMove = (event: PointerEvent) => {
      if (event.pointerId === pointerId) onMove(event);
    };
    const onUp = (event: PointerEvent) => {
      if (event.pointerId !== pointerId) return;
      detach();
      dragCleanup.current = null;
      onRelease(event);
    };
    const onCancel = (event: PointerEvent) => {
      if (event.pointerId !== pointerId) return;
      detach();
      dragCleanup.current = null;
      onAbort();
    };
    dragCleanup.current = detach;
    window.addEventListener("pointermove", guardedMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
  };

  /** Joint handle drag — the cursor IS the next segment's desired heading:
   * angle = dir(hinge→cursor) − heading of the previous segment, snapped
   * to the coupler's real deflections. */
  const beginJointDrag = (event: React.PointerEvent<SVGElement>, couplingId: string): void => {
    if (disabled) return;
    const vertex = couplingVertex.get(couplingId);
    const coupling = couplings.find((item) => item.id === couplingId);
    if (vertex === undefined || !coupling) return;
    const hingePoint = chain[vertex];
    const prevPoint = chain[vertex - 1];
    if (!hingePoint || !prevPoint) return;
    event.preventDefault();
    event.stopPropagation();
    const [hx, hy] = enginePt(hingePoint);
    const prevDir = dirDeg(
      Number(hingePoint.x_mm) - Number(prevPoint.x_mm),
      Number(hingePoint.y_mm) - Number(prevPoint.y_mm),
    );
    const hingeSvg = toSvg(hingePoint);
    const downX = event.clientX;
    const downY = event.clientY;
    let active = false;
    let last = Number(coupling.angle_deg);
    const onMove = (move: PointerEvent) => {
      // Same press/drag split as the modules: under the threshold the press
      // stays a click — releasing at the hinge measures a zero-length
      // direction and would snap the angle to noise.
      if (!active) {
        if (Math.hypot(move.clientX - downX, move.clientY - downY) < DRAG_THRESHOLD_PX) return;
        active = true;
      }
      const pt = pointInPlan(move.clientX, move.clientY);
      if (!pt) return;
      const [ex, ey] = svgToEngine(pt.x, pt.y);
      const desired = normalizeDeg(dirDeg(ex - hx, ey - hy) - prevDir);
      const snapped = snapAngleDeg(desired);
      last = snapped;
      setDrag({
        hingeIndex: vertex,
        deltaDeg: snapped - Number(coupling.angle_deg),
        angleDeg: snapped,
        couplingId,
        hinge: hingeSvg,
      });
    };
    trackPlanDrag(
      event.pointerId,
      onMove,
      (up) => {
        const wasDragging = active;
        if (wasDragging) onMove(up);
        setDrag(null);
        if (!wasDragging) {
          // A click on the hinge selects the union (the handle sits on top of
          // the coupling wedge, so it is the surface a click really lands on).
          onSelectCoupling(couplingId);
        } else if (last !== Number(coupling.angle_deg)) {
          onCommitAngle(couplingId, fmtWire(last, 1));
        }
      },
      () => setDrag(null),
    );
  };

  /** Module press: a click selects; a real drag rotates the module (and the
   * rest of the chain) about its left hinge — the coupling's angle becomes
   * start + rotation, live-snapped. Module 0 anchors the chain: no hinge. */
  const beginModulePress = (
    event: React.PointerEvent<SVGPolygonElement>,
    moduleId: string,
  ): void => {
    if (disabled) return;
    event.preventDefault();
    event.stopPropagation();
    // A stacked member presses on its column's footprint — the hinge it
    // rotates about is the column's own front index, never its slot in
    // `plan.modules` (stacked entries are appended after the chain).
    const moduleIndex = frontIndexOf.get(moduleId) ?? -1;
    const couplingId = moduleIndex >= 0 ? vertexCoupling.get(moduleIndex) : undefined;
    const coupling = couplingId ? couplings.find((item) => item.id === couplingId) : null;
    const hingePoint = couplingId !== undefined ? chain[moduleIndex] : undefined;
    const downX = event.clientX;
    const downY = event.clientY;
    let active = false;
    let last = coupling ? Number(coupling.angle_deg) : 0;
    // Baseline direction: hinge → the point where the press started. The
    // rotation delta measures from there — pressing anywhere on the module
    // starts dead-neutral (no angle jump on drag start).
    const startPt = pointInPlan(downX, downY);
    const startDir =
      hingePoint && startPt
        ? dirDeg(
            svgToEngine(startPt.x, startPt.y)[0] - Number(hingePoint.x_mm),
            svgToEngine(startPt.x, startPt.y)[1] - Number(hingePoint.y_mm),
          )
        : 0;
    const onMove = (move: PointerEvent) => {
      if (!active) {
        if (Math.hypot(move.clientX - downX, move.clientY - downY) < DRAG_THRESHOLD_PX) return;
        if (!coupling || !hingePoint) return;
        active = true;
      }
      if (!coupling || !hingePoint) return;
      const pt = pointInPlan(move.clientX, move.clientY);
      if (!pt) return;
      const [ex, ey] = svgToEngine(pt.x, pt.y);
      const now = dirDeg(ex - Number(hingePoint.x_mm), ey - Number(hingePoint.y_mm));
      const delta = normalizeDeg(now - startDir);
      const snapped = snapAngleDeg(Number(coupling.angle_deg) + delta);
      last = snapped;
      setDrag({
        hingeIndex: moduleIndex,
        deltaDeg: snapped - Number(coupling.angle_deg),
        angleDeg: snapped,
        couplingId: coupling.id,
        hinge: toSvg(hingePoint),
      });
    };
    trackPlanDrag(
      event.pointerId,
      onMove,
      (up) => {
        onMove(up);
        const wasDragging = active;
        setDrag(null);
        if (!wasDragging) {
          onSelectModule(moduleId);
        } else if (coupling && last !== Number(coupling.angle_deg)) {
          onCommitAngle(coupling.id, fmtWire(last, 1));
        }
      },
      () => setDrag(null),
    );
  };

  /** Whether an element bound to chain vertex `index` rotates in the live
   * preview — everything downstream of the dragged hinge moves rigidly. */
  const rotates = (vertexIndex: number): boolean => drag !== null && vertexIndex >= drag.hingeIndex;
  const rotateTransform = (): string | undefined =>
    drag ? `rotate(${-drag.deltaDeg} ${drag.hinge[0]} ${drag.hinge[1]})` : undefined;
  const liveAngleFor = (couplingId: string): number | null =>
    drag && drag.couplingId === couplingId ? drag.angleDeg : null;

  return (
    <g className="bow-plan-svg" data-testid="bow-plan" ref={groupRef}>
      {plan.modules.map((module) => (
        <polygon
          key={module.module_id}
          className={
            module.module_id === selectedModuleId ? "plan-module is-selected" : "plan-module"
          }
          data-testid={`plan-module-${module.module_id}`}
          style={{
            fill: memberSurface(members.frame.material, members.frame.finish?.exterior).fill,
          }}
          points={polygonPoints(module.corners)}
          transform={
            rotates(frontIndexOf.get(module.module_id) ?? -1) ? rotateTransform() : undefined
          }
          role="button"
          aria-label={`${t("assembly.module")} ${module.module_id}`}
          tabIndex={0}
          onPointerDown={(event) => beginModulePress(event, module.module_id)}
          onContextMenu={(event) => {
            if (!onContextMenuElement) return;
            event.preventDefault();
            event.stopPropagation();
            onContextMenuElement(module.module_id, { x: event.clientX, y: event.clientY });
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onSelectModule(module.module_id);
            }
          }}
        />
      ))}
      {plan.couplings.map((coupling) => {
        const spec = couplings.find((item) => item.id === coupling.coupling_id);
        const flagged = flaggedCouplings.has(coupling.coupling_id);
        const [cx, cy] = centroid(coupling.polygon);
        const couplerSpec = members.couplerFor(spec?.coupler_profile_sku ?? null);
        const surface = memberSurface(
          couplerSpec?.material ?? members.frame.material,
          (couplerSpec ?? members.frame).finish?.exterior,
        );
        const vertex = couplingVertex.get(coupling.coupling_id);
        const jointVertex = coupling.polygon[0];
        const [jx, jy] = jointVertex ? toSvg(jointVertex) : [cx, cy];
        return (
          <g
            key={coupling.coupling_id}
            transform={vertex !== undefined && rotates(vertex) ? rotateTransform() : undefined}
            onContextMenu={(event) => {
              if (!onContextMenuElement) return;
              event.preventDefault();
              event.stopPropagation();
              onContextMenuElement(coupling.coupling_id, {
                x: event.clientX,
                y: event.clientY,
              });
            }}
          >
            <polygon
              className={`plan-coupling${
                coupling.coupling_id === selectedCouplingId ? " is-selected" : ""
              }${flagged ? " has-issue" : ""}`}
              style={{ fill: surface.fill }}
              points={polygonPoints(coupling.polygon)}
              stroke="transparent"
              strokeWidth={fontSize * 1.4}
              data-testid={`plan-coupling-${coupling.coupling_id}`}
              role="button"
              aria-label={`${t("assembly.coupling")} ${coupling.coupling_id}`}
              tabIndex={0}
              onClick={() => onSelectCoupling(coupling.coupling_id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectCoupling(coupling.coupling_id);
                }
              }}
            />
            {spec && vertex !== undefined && spec.kind !== "STACKED" && (
              <circle
                className={`plan-joint-handle${
                  drag?.couplingId === coupling.coupling_id ? " is-dragging" : ""
                }`}
                data-testid={`plan-joint-${coupling.coupling_id}`}
                cx={jx}
                cy={jy}
                r={fontSize * 0.62}
                role="button"
                aria-label={`${t("assembly.angle")} ${coupling.coupling_id}`}
                tabIndex={disabled ? -1 : 0}
                onPointerDown={(event) => beginJointDrag(event, coupling.coupling_id)}
              />
            )}
            {spec && (
              <JointAngle
                couplingId={coupling.coupling_id}
                x={cx}
                y={cy - fontSize * 0.6}
                angleDeg={spec.angle_deg}
                liveDeg={liveAngleFor(coupling.coupling_id)}
                fontSize={fontSize}
                disabled={disabled}
                onCommit={(value) => onCommitAngle(coupling.coupling_id, value)}
              />
            )}
            {flagged && (
              <text
                className="plan-issue-flag"
                x={cx}
                y={cy + fontSize * 1.1}
                fontSize={fontSize}
                textAnchor="middle"
              >
                !
              </text>
            )}
          </g>
        );
      })}
      {(() => {
        // Front chain splits at the live hinge: the tail rotates rigidly with
        // the drag, the head stays — same preview the engine will reflow.
        if (!drag) {
          return (
            <polyline
              className="plan-front-chain"
              points={chain.map((point) => toSvg(point).join(",")).join(" ")}
              fill="none"
            />
          );
        }
        const head = chain.slice(0, drag.hingeIndex + 1);
        const tail = chain.slice(drag.hingeIndex);
        return (
          <>
            <polyline
              className="plan-front-chain"
              points={head.map((point) => toSvg(point).join(",")).join(" ")}
              fill="none"
            />
            <g transform={rotateTransform()}>
              <polyline
                className="plan-front-chain"
                points={tail.map((point) => toSvg(point).join(",")).join(" ")}
                fill="none"
              />
            </g>
          </>
        );
      })()}
      {chain.slice(0, -1).map((point, index) => {
        const next = chain[index + 1];
        if (!next) return null;
        const [mx, my] = midpoint(point, next);
        const segmentLength = Math.hypot(
          Number(next.x_mm) - Number(point.x_mm),
          Number(next.y_mm) - Number(point.y_mm),
        );
        const normalX = -(Number(next.y_mm) - Number(point.y_mm)) / segmentLength;
        const normalY = (Number(next.x_mm) - Number(point.x_mm)) / segmentLength;
        return (
          <text
            key={`dim-${index}`}
            className="plan-dimension"
            x={mx + normalX * dimOffset}
            y={my - normalY * dimOffset}
            fontSize={fontSize}
            textAnchor="middle"
            transform={rotates(index) ? rotateTransform() : undefined}
          >
            {Math.round(segmentLength)}
          </text>
        );
      })}
      <text
        className="plan-dimension plan-dimension--total"
        x={Number(plan.min_x_mm) + Number(plan.width_mm) / 2}
        y={-(Number(plan.min_y_mm) + Number(plan.height_mm)) - fontSize}
        fontSize={fontSize}
        textAnchor="middle"
      >
        {Math.round(Number(plan.width_mm))} mm
      </text>
    </g>
  );
}

/** Standalone plan with its own viewBox — the sheet viewer renders
 * `BowPlanContent` inside its own transform instead. */
export function BowPlanSvg(props: BowPlanSvgProps): JSX.Element {
  const bounds = planBounds(props.plan);
  return (
    <svg
      className="bow-plan-svg"
      viewBox={`${bounds.x} ${bounds.y} ${bounds.w} ${bounds.h}`}
      role="img"
      aria-label={t("assembly.planView")}
    >
      <title>{t("assembly.planView")}</title>
      <BowPlanContent {...props} />
    </svg>
  );
}
