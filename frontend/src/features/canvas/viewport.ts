/** Viewport math for the canvas sheet: a pan/zoom transform in px-space over
 * mm-space content. Pure functions — the component layer wires wheel/pointer
 * events to these. */

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ViewTransform {
  /** px per mm */
  scale: number;
  /** translation in px applied before scale */
  tx: number;
  ty: number;
}

export const IDENTITY: ViewTransform = { scale: 1, tx: 0, ty: 0 };

/** Reference zoom: "100%" means 50 px per 100 mm — large enough to read as a
 * drawing on a typical display, small enough to keep a 2.1 m window on screen. */
export const SCALE_100 = 0.5;
export const SCALE_MIN = 0.03;
export const SCALE_MAX = 6;
export const FIT_PADDING = 24;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/** Fit a content box into a container, centered, with even padding. */
export function fitTransform(box: Box, width: number, height: number): ViewTransform {
  if (box.w <= 0 || box.h <= 0 || width <= 0 || height <= 0) return IDENTITY;
  const scale = clamp(
    Math.min((width - FIT_PADDING * 2) / box.w, (height - FIT_PADDING * 2) / box.h),
    SCALE_MIN,
    SCALE_MAX,
  );
  return {
    scale,
    tx: width / 2 - (box.x + box.w / 2) * scale,
    ty: height / 2 - (box.y + box.h / 2) * scale,
  };
}

/** Zoom around a fixed screen point: the mm point under (px,py) stays under it. */
export function zoomAt(view: ViewTransform, px: number, py: number, factor: number): ViewTransform {
  const scale = clamp(view.scale * factor, SCALE_MIN, SCALE_MAX);
  const factorReal = scale / view.scale;
  return {
    scale,
    tx: px - (px - view.tx) * factorReal,
    ty: py - (py - view.ty) * factorReal,
  };
}

export function panBy(view: ViewTransform, dx: number, dy: number): ViewTransform {
  return { ...view, tx: view.tx + dx, ty: view.ty + dy };
}

/** Pan hard-stop: at least PAN_MARGIN px of the content stays on-screen —
 * unbounded wheel/drag panning can otherwise fling the whole drawing off
 * the viewport with no obvious way back. */
export const PAN_MARGIN = 48;

export function clampViewToBox(
  view: ViewTransform,
  box: Box,
  width: number,
  height: number,
): ViewTransform {
  if (box.w <= 0 || box.h <= 0 || width <= 0 || height <= 0) return view;
  const left = box.x * view.scale + view.tx;
  const top = box.y * view.scale + view.ty;
  const right = left + box.w * view.scale;
  const bottom = top + box.h * view.scale;
  let tx = view.tx;
  let ty = view.ty;
  if (left > width - PAN_MARGIN) tx += width - PAN_MARGIN - left;
  if (right < PAN_MARGIN) tx += PAN_MARGIN - right;
  if (top > height - PAN_MARGIN) ty += height - PAN_MARGIN - top;
  if (bottom < PAN_MARGIN) ty += PAN_MARGIN - bottom;
  return tx === view.tx && ty === view.ty ? view : { ...view, tx, ty };
}

/** Auto-fit policy: whether the viewport should re-fit the content box.
 * A wholesale content replacement (epoch bump — e.g. a starter pick) always
 * refits, even after the user took manual pan/zoom control; otherwise refit
 * tracks box/container changes only while the view is still automatic. */
export function shouldRefitView(args: {
  contentEpochChanged: boolean;
  boxChanged: boolean;
  containerResized: boolean;
  userInteracted: boolean;
}): boolean {
  if (args.contentEpochChanged) return true;
  if (args.userInteracted) return false;
  return args.boxChanged || args.containerResized;
}

export function unionBox(a: Box, b: Box | null): Box {
  if (!b) return a;
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  return {
    x,
    y,
    w: Math.max(a.x + a.w, b.x + b.w) - x,
    h: Math.max(a.y + a.h, b.y + b.h) - y,
  };
}
