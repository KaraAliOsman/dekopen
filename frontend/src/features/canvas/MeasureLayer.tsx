import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";

export interface MeasurePoint {
  x: number;
  y: number;
}

/** Model-space overlay for the Medir tool — renders inside the canvas
 * transform, so every coordinate is a millimeter. `k` (the viewport zoom)
 * counter-scales labels and hit targets so they stay legible at any zoom.
 * Anchors are the snap vertices (bay corners) the tool offers; `path` is
 * the measured polyline (last vertex is the live cursor while measuring). */
export function MeasureLayer({
  anchors,
  path,
  k,
  onAnchor,
}: {
  anchors: readonly MeasurePoint[];
  path: readonly MeasurePoint[];
  /** viewport scale — text/radius are divided by it to stay screen-sized. */
  k: number;
  onAnchor(point: MeasurePoint): void;
}): JSX.Element {
  const fontSize = 14 / Math.max(0.01, k);
  const hitRadius = 9 / Math.max(0.01, k);
  const dotRadius = 3 / Math.max(0.01, k);
  let total = 0;
  for (let i = 1; i < path.length; i += 1) {
    const from = path[i - 1];
    const to = path[i];
    if (from && to) total += Math.hypot(to.x - from.x, to.y - from.y);
  }
  const last = path[path.length - 1];
  return (
    <g className="measure-layer" aria-hidden="true">
      {anchors.map((anchor, index) => (
        <circle
          key={index}
          className="measure-anchor"
          cx={anchor.x}
          cy={anchor.y}
          r={hitRadius}
          onClick={(event) => {
            event.stopPropagation();
            onAnchor(anchor);
          }}
        />
      ))}
      {path.length > 1 && (
        <polyline
          className="measure-path"
          points={path.map((point) => `${point.x},${point.y}`).join(" ")}
          fill="none"
        />
      )}
      {path.map((point, index) => (
        <circle key={index} className="measure-vertex" cx={point.x} cy={point.y} r={dotRadius} />
      ))}
      {last && total > 0 && (
        <text className="measure-label" x={last.x + 14 / k} y={last.y - 14 / k} fontSize={fontSize}>
          {fmtMm(Math.round(total))} mm
        </text>
      )}
    </g>
  );
}

/** Screen-space readout for the measure tool's live state — the chip over
 * the canvas, not the model layer. */
export function MeasureChip({
  path,
  liveMm,
}: {
  path: readonly MeasurePoint[];
  /** distance from the last vertex to the cursor, while moving. */
  liveMm: number | null;
}): JSX.Element | null {
  let total = 0;
  for (let i = 1; i < path.length; i += 1) {
    const from = path[i - 1];
    const to = path[i];
    if (from && to) total += Math.hypot(to.x - from.x, to.y - from.y);
  }
  const text =
    path.length === 0
      ? t("assembly.measureHint")
      : liveMm !== null
        ? t("assembly.measureToCursor")
            .replace("{total}", `${fmtMm(Math.round(total))} mm`)
            .replace("{live}", `${fmtMm(Math.round(liveMm))} mm`)
        : t("assembly.measureTotal").replace("{total}", `${fmtMm(Math.round(total))} mm`);
  return (
    <output className="measure-chip" data-testid="measure-chip">
      {text}
    </output>
  );
}
