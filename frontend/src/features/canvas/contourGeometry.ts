import type { ContourJson } from "./productEditing";

/** Module-local contour geometry for canvas rendering.
 *
 * Engine contours live in a y-up, CCW space; the front elevation draws
 * y-down, so paths are emitted with `y = heightMm − y` (the flip mirrors the
 * winding and flips the arc sweep flag relative to the math convention).
 * Only what the canvas needs is implemented — the engine remains the
 * authority for every measured number. */

export type ContourPoint = { x: number; y: number };

function vertex(contour: ContourJson, index: number): ContourPoint {
  const n = contour.vertices.length;
  const v = contour.vertices[index % n]!;
  return { x: Number(v.x_mm), y: Number(v.y_mm) };
}

function bulgeOf(contour: ContourJson, index: number): number {
  const raw = contour.bulges[index % contour.bulges.length];
  return raw === null || raw === undefined ? 0 : Number(raw);
}

/** Center/radius of the arc p0→p1 with signed sagitta (right-of-edge). */
function arcParams(
  p0: ContourPoint,
  p1: ContourPoint,
  sagitta: number,
): { cx: number; cy: number; r: number } {
  const chord = Math.hypot(p1.x - p0.x, p1.y - p0.y);
  const half = chord / 2;
  const s = Math.abs(sagitta);
  const r = (s * s + half * half) / (2 * s);
  const mx = (p0.x + p1.x) / 2;
  const my = (p0.y + p1.y) / 2;
  const nx = -(p1.y - p0.y) / chord; // left unit normal
  const ny = (p1.x - p0.x) / chord;
  const off = r - s;
  return sagitta > 0
    ? { cx: mx + nx * off, cy: my + ny * off, r }
    : { cx: mx - nx * off, cy: my - ny * off, r };
}

/** SVG path for the closed contour, flipped into y-down screen space. */
export function contourPathD(contour: ContourJson, heightMm: number): string {
  const n = contour.vertices.length;
  const first = vertex(contour, 0);
  const parts = [`M ${fmt(first.x)} ${fmt(heightMm - first.y)}`];
  for (let i = 0; i < n; i += 1) {
    const p1 = vertex(contour, i + 1);
    const s = bulgeOf(contour, i);
    const y = heightMm - p1.y;
    if (s === 0) {
      parts.push(`L ${fmt(p1.x)} ${fmt(y)}`);
    } else {
      const { r } = arcParams(vertex(contour, i), p1, s);
      // Engine space: s>0 bulges right of the edge. After the y-flip the
      // same arc curves left of travel on screen → SVG sweep flag 0.
      parts.push(`A ${fmt(r)} ${fmt(r)} 0 0 ${s > 0 ? 0 : 1} ${fmt(p1.x)} ${fmt(y)}`);
    }
  }
  parts.push("Z");
  return parts.join(" ");
}

function fmt(value: number): string {
  return value.toFixed(2);
}

type OffsetEdge =
  | { kind: "line"; a: ContourPoint; b: ContourPoint }
  | { kind: "arc"; a: ContourPoint; b: ContourPoint; cx: number; cy: number; r: number; s: number };

/** Perpendicular-inset copy of the contour for the visible glass opening.
 * Lines shift along the interior normal; arcs keep their center and shrink
 * (outward bulge) or grow (inward) their radius. Corners are resolved by
 * intersecting adjacent offset edges nearest the original vertex. Returns
 * the inset boundary as edge descriptors ready for sampling. */
function insetEdges(contour: ContourJson, distanceMm: number): OffsetEdge[] {
  const n = contour.vertices.length;
  const edges: OffsetEdge[] = [];
  for (let i = 0; i < n; i += 1) {
    const p0 = vertex(contour, i);
    const p1 = vertex(contour, i + 1);
    const s = bulgeOf(contour, i);
    if (s === 0) {
      const dx = p1.x - p0.x;
      const dy = p1.y - p0.y;
      const len = Math.hypot(dx, dy);
      const nx = (-dy / len) * distanceMm;
      const ny = (dx / len) * distanceMm;
      edges.push({
        kind: "line",
        a: { x: p0.x + nx, y: p0.y + ny },
        b: { x: p1.x + nx, y: p1.y + ny },
      });
    } else {
      const { cx, cy, r } = arcParams(p0, p1, s);
      // endpoints are rewired to the resolved corners below
      edges.push({
        kind: "arc",
        a: p0,
        b: p1,
        cx,
        cy,
        r: s > 0 ? r - distanceMm : r + distanceMm,
        s,
      });
    }
  }

  // Resolve each corner as the intersection of adjacent offset edges.
  const corners: ContourPoint[] = [];
  for (let i = 0; i < n; i += 1) {
    const vertex0 = vertex(contour, i);
    const prev = edges[(i - 1 + n) % n]!;
    const next = edges[i]!;
    let p: ContourPoint | null = null;
    if (prev.kind === "line" && next.kind === "line") {
      p = lineIntersect(prev.a, prev.b, next.a, next.b);
    } else if (prev.kind === "arc" && next.kind === "line") {
      p = circleLine(prev.cx, prev.cy, prev.r, next.a, next.b, vertex0);
    } else if (prev.kind === "line" && next.kind === "arc") {
      p = circleLine(next.cx, next.cy, next.r, prev.a, prev.b, vertex0);
    } else if (prev.kind === "arc" && next.kind === "arc") {
      p = circleCircle(prev.cx, prev.cy, prev.r, next.cx, next.cy, next.r, vertex0);
    }
    corners.push(p ?? vertex0);
  }

  // Rewire each offset edge to run corner→corner.
  return edges.map((edge, i) => ({
    ...edge,
    a: corners[i]!,
    b: corners[(i + 1) % n]!,
  }));
}

/** Visual chord-error bound for arc sampling (mm). A chord of half-angle
 * θ deviates r·(1−cos θ) from the arc; keeping that under CHORD_ERR bounds
 * the flattening at any zoom — instead of a fixed chord length that shows
 * polygon facets on tight radii and wastes vertices on shallow arcs. */
const ARC_CHORD_ERR_MM = 0.4;

/** Steps for a radius/sweep pair honouring ARC_CHORD_ERR_MM. */
export function arcSteps(radius: number, sweep: number): number {
  if (radius <= 0) return 2;
  // sagitta of each chord: e = r(1 − cos(θ)), θ = sweep/(2·steps)
  const per = Math.acos(Math.max(1 - ARC_CHORD_ERR_MM / radius, -1)) * 2;
  return Math.max(2, Math.ceil(Math.abs(sweep) / per));
}

/** Inset boundary as sampled points (lines keep endpoints, arcs sampled
 * with a controlled chord error). */
export function insetContourPoints(contour: ContourJson, distanceMm: number): ContourPoint[] {
  const edges = insetEdges(contour, distanceMm);
  const points: ContourPoint[] = [];
  for (const edge of edges) {
    if (edge.kind === "line") {
      points.push(edge.a);
      continue;
    }
    const startAngle = Math.atan2(edge.a.y - edge.cy, edge.a.x - edge.cx);
    const endAngle = Math.atan2(edge.b.y - edge.cy, edge.b.x - edge.cx);
    // s>0 = right-of-edge bulge: the arc center sits on the concave side, so
    // travelling the edge sweeps counterclockwise around it (y-up space).
    const sweep = sweepBetween(startAngle, endAngle, edge.s > 0 ? 1 : -1);
    const steps = arcSteps(edge.r, sweep);
    for (let k = 0; k < steps; k += 1) {
      const angle = startAngle + (sweep * k) / steps;
      points.push({ x: edge.cx + edge.r * Math.cos(angle), y: edge.cy + edge.r * Math.sin(angle) });
    }
  }
  return points;
}

function lineIntersect(a0: ContourPoint, a1: ContourPoint, b0: ContourPoint, b1: ContourPoint) {
  const ax = a1.x - a0.x;
  const ay = a1.y - a0.y;
  const bx = b1.x - b0.x;
  const by = b1.y - b0.y;
  const det = ax * by - ay * bx;
  if (Math.abs(det) < 1e-9) return null;
  const t = ((b0.x - a0.x) * by - (b0.y - a0.y) * bx) / det;
  return { x: a0.x + ax * t, y: a0.y + ay * t };
}

function circleLine(
  cx: number,
  cy: number,
  r: number,
  a0: ContourPoint,
  a1: ContourPoint,
  near: ContourPoint,
): ContourPoint {
  const ax = a1.x - a0.x;
  const ay = a1.y - a0.y;
  const fx = a0.x - cx;
  const fy = a0.y - cy;
  const a = ax * ax + ay * ay;
  const b = 2 * (fx * ax + fy * ay);
  const c = fx * fx + fy * fy - r * r;
  const disc = b * b - 4 * a * c;
  if (disc <= 0 || a === 0) return near;
  const root = Math.sqrt(disc);
  let best = near;
  let bestD = Infinity;
  for (const sign of [1, -1]) {
    const t = (-b + sign * root) / (2 * a);
    const candidate = { x: a0.x + ax * t, y: a0.y + ay * t };
    const d = Math.hypot(candidate.x - near.x, candidate.y - near.y);
    if (d < bestD) {
      best = candidate;
      bestD = d;
    }
  }
  return best;
}

function circleCircle(
  c0x: number,
  c0y: number,
  r0: number,
  c1x: number,
  c1y: number,
  r1: number,
  near: ContourPoint,
): ContourPoint {
  const d = Math.hypot(c1x - c0x, c1y - c0y);
  if (d === 0 || d > r0 + r1 || d < Math.abs(r0 - r1)) return near;
  const a = (r0 * r0 - r1 * r1 + d * d) / (2 * d);
  const hSq = r0 * r0 - a * a;
  if (hSq < 0) return near;
  const h = Math.sqrt(hSq);
  const ux = (c1x - c0x) / d;
  const uy = (c1y - c0y) / d;
  const px = c0x + ux * a;
  const py = c0y + uy * a;
  const first = { x: px + uy * h, y: py - ux * h };
  const second = { x: px - uy * h, y: py + ux * h };
  return Math.hypot(first.x - near.x, first.y - near.y) <=
    Math.hypot(second.x - near.x, second.y - near.y)
    ? first
    : second;
}

/** SVG path (y-down) for a sampled polygon — used for the glass opening
 * inset, whose boundary comes back from `insetContour` as points. Arc
 * fidelity is visual-only: the engine's BOM carries the exact region. */
export function pointsPathD(points: ContourPoint[], heightMm: number): string {
  if (points.length === 0) return "";
  const parts = points.map((p, i) => `${i === 0 ? "M" : "L"} ${fmt(p.x)} ${fmt(heightMm - p.y)}`);
  parts.push("Z");
  return parts.join(" ");
}

function sweepBetween(a0: number, a1: number, dir: number): number {
  let sweep = a1 - a0;
  while (dir < 0 && sweep > 0) sweep -= Math.PI * 2;
  while (dir > 0 && sweep < 0) sweep += Math.PI * 2;
  return sweep;
}

function angleInSweep(a0: number, sweep: number, target: number): boolean {
  const rel = (((target - a0) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  if (sweep > 0) return rel <= sweep + 1e-9;
  return rel - Math.PI * 2 >= sweep - 1e-9;
}

/** Overshoot of a contour beyond its vertex bounding box, in engine y-up mm:
 * only arcs extend past the corners (an arch crown rises above the
 * springline, a side bow passes its nominal edge). The layout lifts/dips
 * the drawing band by `top`/`bottom` and widens it by `left`/`right`. */
export function contourOutset(contour: ContourJson): {
  top: number;
  bottom: number;
  left: number;
  right: number;
} {
  const n = contour.vertices.length;
  const xs = contour.vertices.map((v) => Number(v.x_mm));
  const ys = contour.vertices.map((v) => Number(v.y_mm));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  let top = 0;
  let bottom = 0;
  let left = 0;
  let right = 0;
  for (let i = 0; i < n; i += 1) {
    const s = bulgeOf(contour, i);
    if (s === 0) continue;
    const p0 = vertex(contour, i);
    const p1 = vertex(contour, i + 1);
    const { cx, cy, r } = arcParams(p0, p1, s);
    const a0 = Math.atan2(p0.y - cy, p0.x - cx);
    const a1 = Math.atan2(p1.y - cy, p1.x - cx);
    const sweep = sweepBetween(a0, a1, s > 0 ? 1 : -1);
    const apex = angleInSweep(a0, sweep, Math.PI / 2) ? cy + r : Math.max(p0.y, p1.y);
    const dip = angleInSweep(a0, sweep, -Math.PI / 2) ? cy - r : Math.min(p0.y, p1.y);
    const east = angleInSweep(a0, sweep, 0) ? cx + r : Math.max(p0.x, p1.x);
    const west = angleInSweep(a0, sweep, Math.PI) ? cx - r : Math.min(p0.x, p1.x);
    top = Math.max(top, apex - maxY);
    bottom = Math.max(bottom, minY - dip);
    right = Math.max(right, east - maxX);
    left = Math.max(left, minX - west);
  }
  return { top, bottom, left, right };
}
