import { useEffect, useState } from "react";

import type { PlanGeometry, PlanPoint, ProductIssue } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { memberSurface } from "./materials";
import type { MemberGeometry } from "./members";
import type { CouplingJson } from "./productEditing";

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

function toSvg(point: PlanPoint): [number, number] {
  // Engine y grows upward; SVG y grows downward — mirror vertically so a
  // positive coupling angle reads as the bow curving up on screen.
  return [Number(point.x_mm), -Number(point.y_mm)];
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

/** Joint angle label: click to edit the coupling angle in place. */
function JointAngle({
  couplingId,
  x,
  y,
  angleDeg,
  fontSize,
  disabled,
  onCommit,
}: {
  couplingId: string;
  x: number;
  y: number;
  angleDeg: string;
  fontSize: number;
  disabled: boolean;
  onCommit(normalized: string): void;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(angleDeg);
  useEffect(() => {
    if (!editing) setDraft(angleDeg);
  }, [angleDeg, editing]);
  if (!editing || disabled) {
    return (
      <text
        className="plan-angle"
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
        {angleDeg}°
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
            onCommit(parsed.toFixed(1));
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

  return (
    <g className="bow-plan-svg" data-testid="bow-plan">
      {plan.modules.map((module) => (
        <polygon
          key={module.module_id}
          className={
            module.module_id === selectedModuleId ? "plan-module is-selected" : "plan-module"
          }
          style={{ fill: memberSurface(members.frame.material).fill }}
          points={polygonPoints(module.corners)}
          role="button"
          aria-label={`${t("assembly.module")} ${module.module_id}`}
          tabIndex={0}
          onClick={() => onSelectModule(module.module_id)}
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
        const surface = memberSurface(
          members.couplerFor(spec?.coupler_profile_sku ?? null)?.material ?? members.frame.material,
        );
        return (
          <g
            key={coupling.coupling_id}
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
            {spec && (
              <JointAngle
                couplingId={coupling.coupling_id}
                x={cx}
                y={cy - fontSize * 0.6}
                angleDeg={spec.angle_deg}
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
      <polyline
        className="plan-front-chain"
        points={chain.map((point) => toSvg(point).join(",")).join(" ")}
        fill="none"
      />
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
