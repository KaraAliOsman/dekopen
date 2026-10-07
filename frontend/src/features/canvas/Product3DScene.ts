import type { PlanGeometry, PlanModule } from "../../api/generated/models";
import type { ContourJson, ProductJson, ProductModuleJson } from "./productEditing";
import { modulePrimaryBay, resolveStacks } from "./productEditing";
import type { IntentNode, OpeningSpecPayload } from "./intentEditing";
import { bayIsDoor, panelTravel, resolvedSlidingLayout } from "./intentEditing";
import { insetContourPoints } from "./contourGeometry";
import { frontLayout } from "./ProductFrontSvg";
import type { MemberGeometry, MemberSpec } from "./members";
import type { HandleKind, LeafSpecInput, SceneDiagnostic } from "./hardwareVisual";
import { hingeSide, resolveHardwareVisual } from "./hardwareVisual";
import { leafPart, solidZCenter } from "./leafPose";

/** Pure 3D scene builder — the §16 view derives every solid from the SAME
 * product model the 2D elevation renders (front layout, bay tree, catalog
 * member geometry, engine plan corners). There is no separate 3D data
 * model: if a fact isn't declared (section depth, plan depth), the solid
 * falls back to a neutral convention, never to a fabricated declaration. */

export type Pt2 = [number, number];
export type Vec3 = [number, number, number];

export type SolidKind =
  | "frame"
  | "sash"
  | "mullion"
  | "glass"
  | "panel"
  | "coupler"
  | "support"
  | "fitting"
  | "bead"
  | "gasket"
  | "handle"
  | "hinge"
  | "track"
  | "threshold"
  | "spacer"
  | "wall";

/** D05 per-face finish stamped from the picked catalog colors — hex swatch
 * + optional grain texture name; `*Interior` carries the room face so the
 * inside view can show the real bicolor pair. */
export interface SolidFinish {
  tint?: string | null;
  tintInterior?: string | null;
  texture?: string | null;
  textureInterior?: string | null;
}

export interface BoxSolid extends SolidFinish {
  kind: "box";
  owner: string;
  surface: SolidKind;
  material: string;
  center: Vec3;
  size: Vec3;
  /** True when the solid is a neutral convention (no declared catalog
   * section) — renderers must show it as approximate, never as the
   * manufacturer profile. */
  approximate?: boolean;
  /** Presentation grouping: the operable leaf this solid belongs to, so
   * the view can swing/slide it without touching the owner→selection
   * convention. Fixed members carry no leafId. */
  leafId?: string;
}

/** Member ring / pane extruded along the module's depth axis from a
 * module-local outline (x right, y up — the contour space). The extrusion
 * spans z0..z0+depth so glazing can sit inside the profile depth. */
export interface ShapeSolid extends SolidFinish {
  kind: "shape";
  owner: string;
  surface: SolidKind;
  material: string;
  outline: Pt2[];
  holes: Pt2[][];
  z0: number;
  depth: number;
  approximate?: boolean;
  leafId?: string;
  /** Weld vertices + smooth normals — curved outlines (contour arcs) read
   * faceted otherwise, since ExtrudeGeometry emits per-face normals. */
  smooth?: boolean;
}

/** Member run with a declared catalog cross-section (§05-B): `outline` is
 * the normalized section — u the face direction across the member slot,
 * v interior-positive depth with the exterior face at v = 0. `axis` is
 * the direction the member runs in module space ("x" for rails, "y" for
 * posts); the run spans a0..a1 and the (u,v) origin sits at (u0, v0).
 * Never approximate — the polygon IS the manufacturer declaration. */
export interface ProfileSolid extends SolidFinish {
  kind: "profile";
  owner: string;
  surface: SolidKind;
  material: string;
  outline: Pt2[];
  axis: "x" | "y";
  a0: number;
  a1: number;
  u0: number;
  v0: number;
  /** Flips the section across its own u-extent — asymmetric sections on
   * right posts / top rails face the aperture the same way the left/bottom
   * runs do instead of extruding the mirror image of the real profile. */
  mirrorU?: boolean;
  /** Never set on profile solids — a declared section is never approximate;
   * the field exists so the union keeps one schema. */
  approximate?: boolean;
  leafId?: string;
}

/** Coupler wedge in world space: a plan polygon (x,z) extruded vertically. */
export interface PrismSolid extends SolidFinish {
  kind: "prism";
  owner: string;
  surface: SolidKind;
  material: string;
  outline: Pt2[];
  y0: number;
  y1: number;
  approximate?: boolean;
  leafId?: string;
}

export type Solid3D = BoxSolid | ShapeSolid | PrismSolid | ProfileSolid;

/** §05-E — a leaf's presentation motion, derived from its declared opening
 * type and region. This is UI state only: it never changes the product
 * model, dimensions or BOM — the engine stays the authority on what the
 * product IS; the motion only shows how it would open.
 *
 * Coordinates live in module space (x right, y up, z into the wall — +z is
 * the room side). `pivot` is the hinge edge: the leaf's left/right edge x
 * for a swing, its bottom/top edge y for a tilt. `dir` signs the pose:
 * swing −1 opens a left-hinge leaf, +1 a right-hinge leaf (rotation about
 * +Y at pivotX so the free edge moves +z); tilt +1 tips the free edge
 * toward the room (TILT_TURN bottom pivot) or out (AWNING top pivot, same
 * sign — the pivot placement makes the difference); slide ±1 along +x by
 * `travel`. */
export interface LeafMotion {
  leafId: string;
  kind: "swing" | "tilt" | "slide" | "tilt_turn";
  pivot: number;
  dir: number;
  travel: number;
  /** TILT_TURN only: the bottom-edge y the leaf tips about in the TILT
   * pose — `pivot` stays the side hinge for the TURN pose. */
  tiltPivot?: number;
  /** Tilt angle for `kind === "tilt"` — a proyectante opens wider than
   * the oscilobatiente vent; omitted = the ~10° tilt convention. */
  rad?: number;
  /** Leaf centre in module space — the despiece guide-line anchor and
   * the Detalle camera preset's fallback target. */
  cx: number;
  cy: number;
  /** Closed z-centres of the leaf's exploded parts (sash assembly /
   * bead+gasket kit / pane) — the guide lines connect each separated
   * piece back to its seat. */
  partZ: { sash: number; glazing: number; bead: number };
  /** Detalle camera anchor — the leaf's handle mount point when it
   * carries one. */
  detail?: Vec3;
}

export interface ModuleScene {
  moduleId: string;
  /** World placement of the module-local frame (x right, y up, z into the
   * wall): from the engine plan corners — start corner → position, heading
   * → rotation about +Y. */
  position: Vec3;
  rotationY: number;
  /** Module depth — stack coupler bars are emitted in this local frame. */
  depth: number;
  solids: Solid3D[];
  leaves: LeafMotion[];
}

export interface Scene3D {
  modules: ModuleScene[];
  couplers: Solid3D[];
  /** Camera-fit volume over the whole scene. */
  center: Vec3;
  radius: number;
  /** World-space bounds of every emitted solid — the stage grounds the
   * product on `min[1]` instead of guessing from the bounding sphere. */
  bounds: { min: Vec3; max: Vec3 };
  /** Build diagnostics the view must surface: impossible declared datums,
   * unknown kit selections, visual-only conventions standing in for
   * authority. The drawing still renders — the incompatibility is shown,
   * never hidden by a silent clamp. */
  diagnostics: SceneDiagnostic[];
}

/** Neutral drawing depth when no authority declares one — the plan carries
 * the system's depth_mm whenever an evaluation exists; the fallback only
 * applies offline. */
const FALLBACK_DEPTH_MM = 60;
const GLASS_DEFAULT_MM = 20;
const SUPPORT_CHANNEL_MM = 14;
const FITTING_BLOCK_MM = 90;
const GASKET_MM = 3;
const BEAD_DEPTH_MM = 10;
const HANDLE_HEIGHT_MM = 1050;
const TRACK_MM = 10;
/** The proyectante's open pose reads wider than the oscilobatiente vent —
 * same axis (top), different amplitude. Kept in module scope so the scene
 * builder does not import the view's pose constants. */
const AWNING_POSE_RAD = (24 * Math.PI) / 180;

type Region = { x: number; y: number; w: number; h: number };
type NodeRegion = { node: IntentNode; region: Region };

const SPACER_MM = 10;
const SPACER_INSET_MM = 5;

/** Parse a declared glass composition — "4-16-4" (pane/cavity/pane) or
 * "4-16-4-16-4" (triple glazing): panes at even indices, air chambers at
 * odd. Free text like "4 Float Incoloro" and implausible numbers return
 * null — the renderer then draws one slab, never a fabricated stack. */
export function iguSpec(
  spec: string | null | undefined,
): { panes: number[]; chambers: number[] } | null {
  if (!spec) return null;
  const parts = spec.split("-").map((part) => Number(part.trim()));
  if (parts.length < 3 || parts.length % 2 === 0 || parts.some((part) => !Number.isFinite(part))) {
    return null;
  }
  const panes = parts.filter((_, index) => index % 2 === 0);
  const chambers = parts.filter((_, index) => index % 2 === 1);
  if (panes.some((t) => t < 2 || t > 19) || chambers.some((t) => t < 4 || t > 40)) {
    return null;
  }
  return { panes, chambers };
}

/** D02 structured stack → the scene's panes/chambers. The parsed
 * composition is the authority when it exists — notations that `iguSpec`
 * cannot read (laminated "3+3 PVB 0,38", slash-separated "4 / 12 / 4")
 * still draw their real stack instead of degrading to a slab. */
export function iguFromComposition(
  composition: { layers?: unknown } | null | undefined,
): { panes: number[]; chambers: number[] } | null {
  const layers = Array.isArray(composition?.layers) ? composition.layers : null;
  if (!layers || layers.length < 3) return null;
  const panes: number[] = [];
  const chambers: number[] = [];
  for (const layer of layers) {
    const item = layer as Record<string, unknown>;
    if (item.type === "lamina") {
      const paneList = Array.isArray(item.panes) ? item.panes : [];
      panes.push(
        paneList.reduce((sum, pane) => sum + (Number(String(pane).replace(",", ".")) || 0), 0) +
          (item.interlayer ? 0.38 : 0),
      );
    } else if (item.type === "chamber") {
      chambers.push(Number(String(item.width_mm).replace(",", ".")) || 0);
    }
  }
  return panes.length >= 2 && chambers.length === panes.length - 1 ? { panes, chambers } : null;
}

/** The aluminium edge spacer of a real IGU cavity — a perimeter bar just
 * inside the glazing edge, the thin metal line visible at the glass
 * border on any real insulated unit. */
function spacerRing(
  solids: Solid3D[],
  owner: string,
  x: number,
  y: number,
  z0: number,
  w: number,
  h: number,
  t: number,
): void {
  const inset = Math.min(SPACER_INSET_MM, w / 8, h / 8);
  const bar = Math.min(SPACER_MM, w / 4, h / 4);
  const sx = x + inset;
  const sy = y + inset;
  const sw = w - 2 * inset;
  const sh = h - 2 * inset;
  solids.push(box(owner, "spacer", "ALUMINIUM", sx, sy, z0, sw, bar, t));
  solids.push(box(owner, "spacer", "ALUMINIUM", sx, sy + sh - bar, z0, sw, bar, t));
  solids.push(box(owner, "spacer", "ALUMINIUM", sx, sy + bar, z0, bar, sh - 2 * bar, t));
  solids.push(box(owner, "spacer", "ALUMINIUM", sx + sw - bar, sy + bar, z0, bar, sh - 2 * bar, t));
}

/** The glazing infill of a bay. One slab when no composition is declared;
 * a real IGU stack — declared panes separated by spacer bars — when
 * `glass_spec` declares the pane/cavity layout. The stack scales into the
 * glazing slot thickness, so declared proportions stay intact and a
 * "4-16-4" never draws as a 20mm slab of glass. */
function glassInfill(
  solids: Solid3D[],
  owner: string,
  x: number,
  y: number,
  z0: number,
  w: number,
  h: number,
  glassT: number,
  spec: string | null | undefined,
  composition?: { layers?: unknown } | null,
): void {
  const igu = iguFromComposition(composition) ?? iguSpec(spec);
  if (!igu) {
    solids.push(box(owner, "glass", "GLASS", x, y, z0, w, h, glassT));
    return;
  }
  const declared =
    igu.panes.reduce((sum, t) => sum + t, 0) + igu.chambers.reduce((sum, t) => sum + t, 0);
  const scale = declared > 0 ? glassT / declared : 1;
  let cursor = z0;
  igu.panes.forEach((paneT, index) => {
    const thickness = paneT * scale;
    solids.push(box(owner, "glass", "GLASS", x, y, cursor, w, h, thickness));
    cursor += thickness;
    const cavityT = (igu.chambers[index] ?? 0) * scale;
    if (cavityT > 0) {
      spacerRing(solids, owner, x, y, cursor, w, h, cavityT);
      cursor += cavityT;
    }
  });
}

/** Contour glazing — the same IGU stack as `glassInfill`, but each pane is
 * the contoured outline and the spacer is a contour-inset ring, since a
 * rectangular bar would overhang a sloped or arched edge. */
function contourGlassInfill(
  solids: Solid3D[],
  owner: string,
  contour: ContourJson,
  insetMm: number,
  z0: number,
  glassT: number,
  spec: string | null | undefined,
  composition?: { layers?: unknown } | null,
): void {
  const outline = insetContourPoints(contour, insetMm).map((p) => [p.x, p.y] as Pt2);
  if (outline.length < 3) return;
  const igu = iguFromComposition(composition) ?? iguSpec(spec);
  if (!igu) {
    solids.push({
      kind: "shape",
      owner,
      surface: "glass",
      material: "GLASS",
      outline,
      holes: [],
      z0,
      depth: glassT,
      smooth: true,
    });
    return;
  }
  const declared =
    igu.panes.reduce((sum, t) => sum + t, 0) + igu.chambers.reduce((sum, t) => sum + t, 0);
  const scale = declared > 0 ? glassT / declared : 1;
  let cursor = z0;
  igu.panes.forEach((paneT, index) => {
    const thickness = paneT * scale;
    solids.push({
      kind: "shape",
      owner,
      surface: "glass",
      material: "GLASS",
      outline,
      holes: [],
      z0: cursor,
      depth: thickness,
      smooth: true,
    });
    cursor += thickness;
    const cavityT = (igu.chambers[index] ?? 0) * scale;
    if (cavityT > 0) {
      const ringOutline = insetContourPoints(contour, insetMm + SPACER_INSET_MM).map(
        (p) => [p.x, p.y] as Pt2,
      );
      const ringHole = insetContourPoints(contour, insetMm + SPACER_INSET_MM + SPACER_MM).map(
        (p) => [p.x, p.y] as Pt2,
      );
      if (ringOutline.length >= 3 && ringHole.length >= 3) {
        solids.push({
          kind: "shape",
          owner,
          surface: "spacer",
          material: "ALUMINIUM",
          outline: ringOutline,
          holes: [ringHole],
          z0: cursor,
          depth: cavityT,
          smooth: true,
        });
      }
      cursor += cavityT;
    }
  });
}

function box(
  owner: string,
  surface: SolidKind,
  material: string,
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  d: number,
): BoxSolid {
  return {
    kind: "box",
    owner,
    surface,
    material,
    center: [x + w / 2, y + h / 2, z + d / 2],
    size: [w, h, d],
  };
}

/** Declared section normalized into the member's local (u,v): u the face
 * direction across the member slot, v interior-positive with the exterior
 * face at v = 0 — `orientation` names which drawing edge is exterior. Only
 * a real polygon normalizes; anything else returns null and the caller
 * stays approximate. Exported for the technical section view, which draws
 * the same shapes in plan. */
export function normalizedSection(
  spec: MemberSpec,
): { outline: Pt2[]; width: number; depth: number } | null {
  const section = spec.section;
  if (!section || section.polygon.length < 3) return null;
  const points = section.polygon.map((point) => [Number(point.x_mm), Number(point.y_mm)] as Pt2);
  if (points.some(([x, y]) => !Number.isFinite(x) || !Number.isFinite(y))) return null;
  const rotated = points.map(([x, y]): Pt2 => {
    switch (section.orientation) {
      case "EXTERIOR_UP":
        return [-x, -y];
      case "EXTERIOR_LEFT":
        return [-y, x];
      case "EXTERIOR_RIGHT":
        return [y, -x];
      default:
        return [x, y];
    }
  });
  const xs = rotated.map((point) => point[0]);
  const ys = rotated.map((point) => point[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const width = Math.max(...xs) - minX;
  const depth = Math.max(...ys) - minY;
  if (width <= 0 || depth <= 0) return null;
  return {
    outline: rotated.map(([x, y]) => [x - minX, y - minY] as Pt2),
    width,
    depth,
  };
}

/** One member run: a declared catalog section extrudes the real profile —
 * straight-cut ends meet at corners (the miter is a fabrication detail,
 * not a visual one). Without a section the member stays an explicitly
 * approximate box, never a fabricated declaration. `mirrorU` flips the
 * section across its own u-extent so an asymmetric profile faces the
 * aperture on the right post / top rail the same way it does on the
 * left post / bottom rail — the real orientation, not a reflection. */
function memberBar(
  solids: Solid3D[],
  owner: string,
  surface: SolidKind,
  spec: MemberSpec,
  axis: "x" | "y",
  a0: number,
  a1: number,
  uCenter: number,
  uSize: number,
  z0: number,
  depth: number,
  mirrorU = false,
): void {
  if (a1 - a0 <= 0) return;
  const section = normalizedSection(spec);
  if (section !== null) {
    solids.push({
      kind: "profile",
      owner,
      surface,
      material: spec.material,
      outline: section.outline,
      axis,
      a0,
      a1,
      u0: uCenter - section.width / 2,
      v0: z0,
      ...(mirrorU ? { mirrorU: true } : {}),
    });
    return;
  }
  solids.push({
    ...box(
      owner,
      surface,
      spec.material,
      axis === "x" ? a0 : uCenter - uSize / 2,
      axis === "x" ? uCenter - uSize / 2 : a0,
      z0,
      axis === "x" ? a1 - a0 : uSize,
      axis === "x" ? uSize : a1 - a0,
      depth,
    ),
    approximate: true,
  });
}

/** Four-member ring inside a region (long sides full span, caps between). */
function memberBarRing(
  solids: Solid3D[],
  owner: string,
  surface: SolidKind,
  spec: MemberSpec,
  region: Region,
  barW: number,
  depth: number,
  z0: number,
): void {
  const w = Math.min(barW, region.w / 2);
  const h = Math.min(barW, region.h / 2);
  memberBar(
    solids,
    owner,
    surface,
    spec,
    "y",
    region.y,
    region.y + region.h,
    region.x + w / 2,
    w,
    z0,
    depth,
  );
  memberBar(
    solids,
    owner,
    surface,
    spec,
    "y",
    region.y,
    region.y + region.h,
    region.x + region.w - w / 2,
    w,
    z0,
    depth,
    true,
  );
  memberBar(
    solids,
    owner,
    surface,
    spec,
    "x",
    region.x + w,
    region.x + region.w - w,
    region.y + h / 2,
    h,
    z0,
    depth,
  );
  memberBar(
    solids,
    owner,
    surface,
    spec,
    "x",
    region.x + w,
    region.x + region.w - w,
    region.y + region.h - h / 2,
    h,
    z0,
    depth,
    true,
  );
}

/** Thin bar ring (bead or gasket) inset inside an aperture — the glazing
 * seat and the rubber line that closes it. */
function thinRing(
  solids: Solid3D[],
  owner: string,
  surface: SolidKind,
  material: string,
  region: Region,
  lineW: number,
  z0: number,
  depth: number,
): void {
  if (region.w <= lineW * 2 || region.h <= lineW * 2 || depth <= 0) return;
  solids.push(
    box(owner, surface, material, region.x, region.y, z0, lineW, region.h, depth),
    box(
      owner,
      surface,
      material,
      region.x + region.w - lineW,
      region.y,
      z0,
      lineW,
      region.h,
      depth,
    ),
    box(
      owner,
      surface,
      material,
      region.x + lineW,
      region.y,
      z0,
      region.w - 2 * lineW,
      lineW,
      depth,
    ),
    box(
      owner,
      surface,
      material,
      region.x + lineW,
      region.y + region.h - lineW,
      z0,
      region.w - 2 * lineW,
      lineW,
      depth,
    ),
  );
}

// hingeSide — imported from hardwareVisual so hardware and motion
// pivots can never disagree on a leaf's hand.

/** Rounded-corner plate outline centred at the origin — the rose /
 * escutcheon silhouette a real handle mounts on instead of a bare box. */
function plateOutline(w: number, h: number, r: number): Pt2[] {
  const radius = Math.min(r, w / 2, h / 2);
  const pts: Pt2[] = [];
  const corner = (cx: number, cy: number, a0: number, a1: number): void => {
    for (let i = 0; i <= 4; i += 1) {
      const a = a0 + ((a1 - a0) * i) / 4;
      pts.push([cx + radius * Math.cos(a), cy + radius * Math.sin(a)]);
    }
  };
  corner(-w / 2 + radius, h / 2 - radius, Math.PI, Math.PI / 2);
  corner(w / 2 - radius, h / 2 - radius, Math.PI / 2, 0);
  corner(w / 2 - radius, -h / 2 + radius, 0, -Math.PI / 2);
  corner(-w / 2 + radius, -h / 2 + radius, -Math.PI / 2, -Math.PI);
  return pts;
}

/** Lever arm silhouette hanging −y from the spindle centre: hub, tapered
 * neck, rounded tip — proportioned like a real ~135 mm window lever. */
function leverOutline(length: number): Pt2[] {
  const tipR = 5.5;
  const L = Math.max(length, 40);
  const pts: Pt2[] = [
    [-10, -2],
    [-8.5, -16],
    [-6, -L + tipR],
  ];
  // Rounded tip — a semicircle under the arm.
  for (let i = 0; i <= 6; i += 1) {
    const a = Math.PI + (Math.PI * i) / 6;
    pts.push([tipR * Math.cos(a), -L + tipR + tipR * Math.sin(a)]);
  }
  pts.push([6, -L + tipR], [8.5, -16], [10, -2], [7.5, 5], [0, 9], [-7.5, 5]);
  return pts;
}

/** Extrude a centred outline onto a face plane: `dir` > 0 protrudes +z
 * (interior/room face), < 0 protrudes −z (exterior/street face). */
function facePlate(
  solids: Solid3D[],
  owner: string,
  material: string,
  outline: Pt2[],
  cx: number,
  cy: number,
  faceZ: number,
  depth: number,
  dir: 1 | -1,
  approximate = false,
): void {
  solids.push({
    kind: "shape",
    owner,
    surface: "handle",
    material,
    outline: outline.map(([x, y]) => [cx + x, cy + y] as Pt2),
    holes: [],
    z0: dir > 0 ? faceZ : faceZ - depth,
    depth,
    approximate,
  });
}

/** A casement/tilt-turn lever on one face: rounded rose plate, collar
 * boss, tapered lever hanging down (the EN closed pose — a lever pointing
 * at the hinges reads as mid-operation). */
function leverOnFace(
  solids: Solid3D[],
  owner: string,
  cx: number,
  cy: number,
  faceZ: number,
  dir: 1 | -1,
  approximate: boolean,
): void {
  facePlate(solids, owner, "STEEL", plateOutline(30, 64, 9), cx, cy, faceZ, 4, dir, approximate);
  const zCollar = dir > 0 ? faceZ + 4 : faceZ - 18;
  solids.push({
    ...box(owner, "handle", "STEEL", cx - 9, cy - 9, zCollar, 18, 18, 14),
    approximate,
  });
  const zLever = dir > 0 ? faceZ + 18 : faceZ - 31;
  facePlate(solids, owner, "STEEL", leverOutline(132), cx, cy, zLever, 13, dir, approximate);
}

/** Door lever set per the selection: escutcheon plate + lever on each
 * face the contract declares, cylinder under the rose when the kit/leaf
 * carries a lock, interior thumb turn opposite the keyhole. */
function doorLeverSet(
  solids: Solid3D[],
  owner: string,
  cx: number,
  cy: number,
  leafBottom: number,
  zInterior: number,
  zExterior: number,
  cylinder: boolean,
  approximate: boolean,
): void {
  // The escutcheon plate runs below the spindle so its tail carries the
  // cylinder — clamped onto the leaf so a tall plate never punches the
  // sill.
  const plateH = 240;
  const py = Math.max(cy - 92, leafBottom + plateH / 2 + 6);
  facePlate(
    solids,
    owner,
    "STEEL",
    plateOutline(30, plateH, 10),
    cx,
    py,
    zInterior,
    4,
    1,
    approximate,
  );
  facePlate(
    solids,
    owner,
    "STEEL",
    plateOutline(30, plateH, 10),
    cx,
    py,
    zExterior,
    4,
    -1,
    approximate,
  );
  leverOnFace(solids, owner, cx, cy, zInterior + 4, 1, approximate);
  leverOnFace(solids, owner, cx, cy, zExterior - 4, -1, approximate);
  if (cylinder) {
    const barrelY = py - plateH / 2 + 58;
    // Exterior: the keyed barrel boss. Interior: the thumb-turn paddle.
    solids.push(
      {
        ...box(owner, "handle", "STEEL", cx - 9, barrelY - 17, zExterior - 16, 18, 34, 16),
        approximate,
      },
      {
        ...box(owner, "handle", "STEEL", cx - 7, barrelY - 12, zInterior + 4, 14, 24, 12),
        approximate,
      },
    );
  }
}

/** A projectante/awning centre handle on the bottom rail — the fitting
 * those leaves actually carry, not a side-stile window lever. */
function centreLever(
  solids: Solid3D[],
  owner: string,
  cx: number,
  cy: number,
  faceZ: number,
  approximate: boolean,
): void {
  facePlate(solids, owner, "STEEL", plateOutline(34, 22, 7), cx, cy, faceZ, 5, 1, approximate);
  const zLever = faceZ + 5;
  solids.push({
    ...box(owner, "handle", "STEEL", cx - 6, cy + 6, zLever, 12, 46, 14),
    approximate,
  });
  solids.push({
    ...box(owner, "handle", "STEEL", cx - 16, cy + 44, zLever, 32, 10, 14),
    approximate,
  });
}

/** Sliding pull families — sized by the fitting, never a percentage of
 * the leaf height. `kind` comes from the selected kit's declared name. */
function slidingPull(
  solids: Solid3D[],
  owner: string,
  kind: HandleKind,
  stileX: number,
  cy: number,
  faceZ: number,
  sashW: number,
  approximate: boolean,
): void {
  if (kind === "surface_pull" || kind === "lift_slide") {
    // Stand-off grip: two feet + a vertical bar — 200 mm travel of hand,
    // fixed regardless of leaf height.
    for (const dy of [-82, 82]) {
      solids.push({
        ...box(owner, "handle", "STEEL", stileX - 7, cy + dy - 14, faceZ, 14, 28, 18),
        approximate,
      });
    }
    solids.push({
      ...box(owner, "handle", "STEEL", stileX - 8, cy - 100, faceZ + 18, 16, 200, 16),
      approximate,
    });
    if (kind === "lift_slide") {
      leverOnFace(solids, owner, stileX, cy - 190, faceZ, 1, approximate);
    }
    return;
  }
  // Uñero / cierre embutido: a flush cup recessed into the meeting stile's
  // interior face — dark cavity inside a thin metallic rim.
  const cupW = Math.min(20, sashW - 8);
  solids.push(
    {
      ...box(owner, "handle", "GASKET", stileX - cupW / 2, cy - 56, faceZ - 8, cupW, 112, 9),
      approximate,
    },
    {
      ...box(owner, "handle", "STEEL", stileX - 12, cy - 66, faceZ - 2, 24, 132, 4),
      approximate,
    },
    // Finger lip over the cavity's centre.
    {
      ...box(owner, "handle", "STEEL", stileX - 8, cy - 22, faceZ - 2, 16, 44, 5),
      approximate,
    },
  );
}

/** One rebate hinge: knuckle barrel on the sash's rebate edge, leaf flag
 * folding inward across the cavity, end caps — enough silhouette to read
 * as a hinge at close zoom while staying behind the galce head-on. */
function hingeAt(
  solids: Solid3D[],
  owner: string,
  hingeX: number,
  y: number,
  rebateZ: number,
  len: number,
  inward: 1 | -1,
  door: boolean,
  approximate: boolean,
): void {
  const barrelW = door ? 11 : 9;
  const flagW = 13;
  solids.push(
    {
      ...box(owner, "hinge", "STEEL", hingeX, y, rebateZ, barrelW, len, 11),
      approximate,
    },
    {
      ...box(
        owner,
        "hinge",
        "STEEL",
        inward > 0 ? hingeX + barrelW - 2 : hingeX - flagW + 2,
        y + 4,
        rebateZ + 1,
        flagW,
        len - 8,
        4,
      ),
      approximate,
    },
    {
      ...box(owner, "hinge", "STEEL", hingeX, y - 4, rebateZ + 1, barrelW, 5, 9),
      approximate,
    },
    {
      ...box(owner, "hinge", "STEEL", hingeX, y + len - 1, rebateZ + 1, barrelW, 5, 9),
      approximate,
    },
  );
}

/** Operable-leaf hardware bound to the visual contract: hinge count comes
 * from the selected kit's declared bill when present (heuristic otherwise,
 * marked schematic); the handle's family, faces and datum come from
 * `resolveHardwareVisual` — impossible declared positions draw clamped
 * AND report a diagnostic, never silently corrected. */
function hardwareSolids(
  solids: Solid3D[],
  owner: string,
  bay: IntentNode,
  leafRegion: Region,
  sashW: number,
  zInterior: number,
  sashD: number,
  members: MemberGeometry,
  diagnostics: SceneDiagnostic[],
  leafSpec?: LeafSpecInput,
): Vec3 | null {
  const spec = resolveHardwareVisual(bay, leafRegion, members, owner, leafSpec);
  diagnostics.push(...spec.diagnostics);
  // Rebate hardware lives in the cavity between the sash's outer face and
  // the aperture edge — buried in neither member, hidden head-on, visible
  // in the gap at a three-quarter view exactly like the real fitting.
  const rebateZ = zInterior - sashD - 6;
  const zExterior = zInterior - sashD;
  const door = spec.family === "DOOR";
  const hinge = leafSpec
    ? leafSpec.hinge === "LEFT" || leafSpec.hinge === "RIGHT"
      ? leafSpec.hinge
      : null
    : hingeSide(bay);

  if (spec.family === "BOTTOM_HUNG") {
    // A bottom-hung leaf rides pivot shoes at its bottom corners and
    // scissor stays on the jambs; the handle sits centred on the TOP
    // rail — the leaf's free edge.
    const pivotCount = spec.hinges?.count ?? 2;
    for (let index = 0; index < pivotCount; index += 1) {
      const px =
        pivotCount === 1
          ? leafRegion.x + leafRegion.w / 2
          : leafRegion.x + leafRegion.w * (index === 0 ? 0.08 : 0.92);
      solids.push({
        ...box(owner, "hinge", "STEEL", px - 6, leafRegion.y + 4, rebateZ, 12, 42, 10),
        approximate: spec.hinges?.authority !== "kit",
      });
    }
    for (const side of [0.08, 0.92]) {
      solids.push({
        ...box(
          owner,
          "hinge",
          "STEEL",
          leafRegion.x + leafRegion.w * side - 4,
          leafRegion.y + leafRegion.h * 0.5 - 75,
          rebateZ + 2,
          8,
          150,
          7,
        ),
        approximate: true,
      });
    }
    if (spec.handle) {
      centreLever(
        solids,
        owner,
        leafRegion.x + leafRegion.w / 2,
        spec.handle.heightMm,
        zInterior,
        !spec.handle.kitBound,
      );
      return [leafRegion.x + leafRegion.w / 2, spec.handle.heightMm, zInterior + 30];
    }
    return null;
  }

  if (spec.family === "AWNING") {
    // Top-hung: hinge barrels along the head plus stays at the jambs and a
    // centre handle on the bottom rail (the leaf's free edge).
    const count = spec.hinges?.count ?? 2;
    const len = Math.min(140, sashW * 0.9);
    for (let index = 0; index < count; index += 1) {
      const frac = count === 1 ? 0.5 : 0.14 + 0.72 * (index / (count - 1));
      solids.push({
        ...box(
          owner,
          "hinge",
          "STEEL",
          leafRegion.x + leafRegion.w * frac - 5,
          leafRegion.y + leafRegion.h - len * 0.75,
          rebateZ,
          10,
          len * 0.75,
          11,
        ),
        approximate: spec.hinges?.authority !== "kit",
      });
    }
    // Scissor stays — the arms a top-hung leaf physically needs; positions
    // are the presentation convention, flagged schematic.
    for (const side of [0.08, 0.92]) {
      solids.push({
        ...box(
          owner,
          "hinge",
          "STEEL",
          leafRegion.x + leafRegion.w * side - 4,
          leafRegion.y + leafRegion.h - 160,
          rebateZ + 2,
          8,
          150,
          7,
        ),
        approximate: true,
      });
    }
    if (spec.handle) {
      centreLever(
        solids,
        owner,
        leafRegion.x + leafRegion.w / 2,
        spec.handle.heightMm,
        zInterior,
        !spec.handle.kitBound,
      );
      return [leafRegion.x + leafRegion.w / 2, spec.handle.heightMm, zInterior + 30];
    }
    return null;
  }

  if (!hinge || spec.family === "SLIDING") return null;
  const tiltTurn = spec.family === "TILT_TURN";
  const hingeX =
    hinge === "LEFT" ? leafRegion.x + 2 : leafRegion.x + leafRegion.w - (door ? 13 : 11);
  const inward = hinge === "LEFT" ? 1 : -1;
  const hingeCount = spec.hinges?.count ?? (door ? 3 : 2);
  const hingeLen = door ? 130 : 110;
  for (let index = 0; index < hingeCount; index += 1) {
    const frac = hingeCount === 1 ? 0.5 : 0.12 + (0.88 - 0.12) * (index / (hingeCount - 1));
    hingeAt(
      solids,
      owner,
      hingeX,
      leafRegion.y + leafRegion.h * frac,
      rebateZ,
      hingeLen,
      inward,
      door,
      spec.hinges?.authority !== "kit",
    );
  }
  if (tiltTurn) {
    // The top scissor stay runs from the hinge-side corner across the head
    // — the fitting a tilt-turn physically needs on top of its hinges.
    solids.push({
      ...box(
        owner,
        "hinge",
        "STEEL",
        hinge === "LEFT"
          ? leafRegion.x + 2
          : leafRegion.x + leafRegion.w - Math.min(leafRegion.w * 0.42, 340),
        leafRegion.y + leafRegion.h - 16,
        rebateZ + 4,
        Math.min(leafRegion.w * 0.42, 340),
        10,
        8,
      ),
      approximate: true,
    });
  }

  if (!spec.handle) return null;
  const handleY = spec.handle.heightMm;
  // The handle mounts on the declared stile — opposite the hinges by the
  // policy's host-member declaration or the DIN convention.
  const stileX =
    spec.handle.mountSide === "left"
      ? leafRegion.x + sashW / 2
      : spec.handle.mountSide === "right"
        ? leafRegion.x + leafRegion.w - sashW / 2
        : leafRegion.x + leafRegion.w / 2;
  const approximate = !spec.handle.kitBound;
  if (spec.handle.kind === "door_lever") {
    doorLeverSet(
      solids,
      owner,
      stileX,
      handleY,
      leafRegion.y,
      zInterior,
      zExterior,
      spec.handle.cylinder,
      approximate,
    );
  } else {
    leverOnFace(solids, owner, stileX, handleY, zInterior, 1, approximate);
    if (spec.handle.exterior) {
      leverOnFace(solids, owner, stileX, handleY, zExterior, -1, approximate);
    }
  }
  return [stileX, handleY, zInterior + 30];
}

/** Split walk that emits both divider bars and leaf bays — the same layout
 * math `ModuleTree`/`bayRegions` render in 2D. */
function walkNode(
  node: IntentNode,
  region: Region,
  origin: { x: number; y: number },
  members: MemberGeometry,
  out: { bars: { node: IntentNode; region: Region; vertical: boolean }[]; leaves: NodeRegion[] },
): void {
  if (node.type === "ROOT" && node.children?.length === 1 && node.children[0]) {
    walkNode(node.children[0], region, origin, members, out);
    return;
  }
  if ((node.type === "SPLIT_V" || node.type === "SPLIT_H") && node.children?.length === 2) {
    const [first, second] = node.children;
    const vertical = node.type === "SPLIT_V";
    const mullion = vertical ? members.mullionV : members.mullionH;
    const barW = mullion?.faceWidthMm ?? Math.max(Math.min(region.w, region.h) * 0.05, 20);
    const lo = vertical ? region.x : region.y;
    const extent = vertical ? region.w : region.h;
    const offset = Number(node.split_offset_mm);
    // split_offset_mm measures from the node's own top edge (document space,
    // y grows downward); these regions are y-up world, so the horizontal
    // axis sits region.h − offset above the region's bottom.
    const desired = vertical ? origin.x + offset : region.y + region.h - offset;
    const axis =
      Number.isFinite(offset) && offset > 0
        ? Math.min(Math.max(desired, lo + barW / 2), lo + extent - barW / 2)
        : lo + extent / 2;
    const firstRegion: Region = vertical
      ? { x: region.x, y: region.y, w: axis - barW / 2 - region.x, h: region.h }
      : {
          x: region.x,
          y: axis + barW / 2,
          w: region.w,
          h: region.y + region.h - (axis + barW / 2),
        };
    const secondRegion: Region = vertical
      ? { x: axis + barW / 2, y: region.y, w: region.x + region.w - (axis + barW / 2), h: region.h }
      : { x: region.x, y: region.y, w: region.w, h: axis - barW / 2 - region.y };
    walkNode(first!, firstRegion, { x: firstRegion.x, y: firstRegion.y }, members, out);
    walkNode(second!, secondRegion, { x: secondRegion.x, y: secondRegion.y }, members, out);
    out.bars.push({
      node,
      vertical,
      region: vertical
        ? { x: axis - barW / 2, y: region.y, w: barW, h: region.h }
        : { x: region.x, y: axis - barW / 2, w: region.w, h: barW },
    });
    return;
  }
  out.leaves.push({ node, region });
}

/** Module world placement from the engine plan corners — corners are
 * [start, end, back_end, back_start] in plan (x right, y up). World maps
 * (px, py) → (px, −py): the front heading becomes +X and the back edge
 * runs into +Z. rotationY = θ puts local +X along the heading. */
function planTransform(
  planModule: PlanModule | undefined,
  rect: { x: number; sill: number },
  fallbackDepth: number,
  declared?: { x: number; y: number; theta: number },
): { position: Vec3; rotationY: number; depth: number; fromPlan: boolean } {
  if (planModule && planModule.corners.length >= 4) {
    const [start, end, , backStart] = planModule.corners;
    if (start && end && backStart) {
      const theta = Math.atan2(
        Number(end.y_mm) - Number(start.y_mm),
        Number(end.x_mm) - Number(start.x_mm),
      );
      const depth = Math.hypot(
        Number(backStart.x_mm) - Number(start.x_mm),
        Number(backStart.y_mm) - Number(start.y_mm),
      );
      return {
        position: [Number(start.x_mm), rect.sill, -Number(start.y_mm)],
        rotationY: theta,
        depth: Number.isFinite(depth) && depth > 0 ? depth : fallbackDepth,
        fromPlan: true,
      };
    }
  }
  if (declared) {
    // No engine plan — reproduce the plan's front chain from the declared
    // coupling angles: the member starts at its column's chain point and
    // runs along the accumulated heading. Only the front edge is
    // authoritative here; the back edge keeps the fallback depth.
    return {
      position: [declared.x, rect.sill, declared.y === 0 ? 0 : -declared.y],
      rotationY: declared.theta,
      depth: fallbackDepth,
      fromPlan: true,
    };
  }
  return {
    position: [rect.x, rect.sill, 0],
    rotationY: 0,
    depth: fallbackDepth,
    fromPlan: false,
  };
}

/** Mark the solids appended since `from` as belonging to `leafId`. */
function tagLeaf(solids: Solid3D[], from: number, leafId: string): void {
  for (let index = from; index < solids.length; index += 1) {
    const solid = solids[index];
    if (solid) solid.leafId = leafId;
  }
}

/** The leaf's opening contract, normalized from the spec form (D03
 * `opening`/`leaves`) or the legacy enum into the same shape — a spec
 * pair's ACTIVE/PASSIVE leaves pose independently and a spec single leaf
 * poses exactly like the enum it mirrors, never as fixed glazing. */
type ResolvedLeaf = LeafSpecInput & {
  slot: string;
  /** Draw a sash ring — operable leaf or a FIXED leaf declared in-sash. */
  sash: boolean;
};

const LEGACY_LEAF: Record<
  string,
  Pick<ResolvedLeaf, "movement" | "hinge" | "direction" | "role" | "sash">
> = {
  TURN_LEFT: { movement: "TURN", hinge: "LEFT", direction: "INWARD", role: "SINGLE", sash: true },
  TURN_RIGHT: {
    movement: "TURN",
    hinge: "RIGHT",
    direction: "INWARD",
    role: "SINGLE",
    sash: true,
  },
  TILT_TURN_LEFT: {
    movement: "TILT_TURN",
    hinge: "LEFT",
    direction: "INWARD",
    role: "SINGLE",
    sash: true,
  },
  TILT_TURN_RIGHT: {
    movement: "TILT_TURN",
    hinge: "RIGHT",
    direction: "INWARD",
    role: "SINGLE",
    sash: true,
  },
  AWNING: {
    movement: "TOP_HUNG",
    hinge: "TOP",
    direction: "OUTWARD",
    role: "SINGLE",
    sash: true,
  },
  DOOR_ENTRY: {
    movement: "TURN",
    hinge: "LEFT",
    direction: "INWARD",
    role: "SINGLE",
    sash: true,
  },
  FIXED: { movement: "FIXED", hinge: null, direction: "INWARD", role: "SINGLE", sash: false },
};

function specLeaf(slot: string, spec: OpeningSpecPayload, door: boolean): ResolvedLeaf {
  const hinge =
    spec.hinge_side === "LEFT" ||
    spec.hinge_side === "RIGHT" ||
    spec.hinge_side === "TOP" ||
    spec.hinge_side === "BOTTOM"
      ? spec.hinge_side
      : null;
  return {
    slot,
    movement: spec.movement,
    hinge,
    // The declared direction wins; TOP_HUNG defaults outward (a
    // proyectante opens to the street), everything else inward.
    direction: spec.direction ?? (spec.movement === "TOP_HUNG" ? "OUTWARD" : "INWARD"),
    role: spec.leaf_role ?? "SINGLE",
    sash: spec.movement !== "FIXED" || spec.fixed_in_sash === true,
    door,
  };
}

function resolvedLeaves(bay: IntentNode, door: boolean): ResolvedLeaf[] {
  if (bay.leaves?.length) {
    return bay.leaves.map((leaf) => specLeaf(leaf.slot, leaf.opening, door));
  }
  if (bay.opening) {
    return [specLeaf("PRIMARY", bay.opening, door)];
  }
  const opening = bay.opening_type ?? "FIXED";
  const base = LEGACY_LEAF[opening];
  if (!base) {
    return [
      {
        slot: "PRIMARY",
        movement: "FIXED",
        hinge: null,
        direction: "INWARD",
        role: "SINGLE",
        sash: false,
        door,
      },
    ];
  }
  // A door's hand is declared on the node, not in the opening name.
  const hinge =
    opening === "DOOR_ENTRY" ? (bay.door_handedness === "RIGHT" ? "RIGHT" : "LEFT") : base.hinge;
  return [{ ...base, slot: "PRIMARY", hinge, door }];
}

/** Closed z-centres of the leaf's despiece parts — the guide-line anchors. */
function leafPartZ(
  solids: Solid3D[],
  leafId: string,
  fallbackZ: number,
): { sash: number; glazing: number; bead: number } {
  const acc: Record<"sash" | "glazing" | "bead", { sum: number; n: number }> = {
    sash: { sum: 0, n: 0 },
    glazing: { sum: 0, n: 0 },
    bead: { sum: 0, n: 0 },
  };
  for (const solid of solids) {
    if (solid.leafId !== leafId) continue;
    const part = leafPart(solid.surface);
    acc[part].sum += solidZCenter(solid);
    acc[part].n += 1;
  }
  return {
    sash: acc.sash.n ? acc.sash.sum / acc.sash.n : fallbackZ,
    glazing: acc.glazing.n ? acc.glazing.sum / acc.glazing.n : fallbackZ,
    bead: acc.bead.n ? acc.bead.sum / acc.bead.n : fallbackZ,
  };
}

/** The presentation motion a resolved leaf performs — the pose follows
 * the real mechanism: TURN/TILT_TURN swing on the declared hinge edge
 * (the declared direction flips it inward/outward), TILT/BOTTOM_HUNG tip
 * on the bottom axis ~10°, TOP_HUNG swings its bottom out on the top
 * axis. Movements the renderer has no honest pose for emit nothing —
 * the leaf stays closed rather than fabricating a motion. */
function leafMotionFor(leafId: string, leafRegion: Region, spec: ResolvedLeaf): LeafMotion | null {
  const out = spec.direction === "OUTWARD";
  const anchor = { cx: leafRegion.x + leafRegion.w / 2, cy: leafRegion.y + leafRegion.h / 2 };
  if (
    spec.movement === "TILT" ||
    spec.movement === "BOTTOM_HUNG" ||
    (spec.movement === "TURN" && spec.hinge === "BOTTOM")
  ) {
    return {
      leafId,
      kind: "tilt",
      pivot: leafRegion.y,
      dir: out ? -1 : 1,
      travel: 0,
      ...anchor,
      partZ: { sash: 0, glazing: 0, bead: 0 },
    };
  }
  if (spec.movement === "TOP_HUNG" || (spec.movement === "TURN" && spec.hinge === "TOP")) {
    return {
      leafId,
      kind: "tilt",
      pivot: leafRegion.y + leafRegion.h,
      dir: out ? 1 : -1,
      travel: 0,
      rad: AWNING_POSE_RAD,
      ...anchor,
      partZ: { sash: 0, glazing: 0, bead: 0 },
    };
  }
  if (spec.movement === "TILT_TURN") {
    const right = spec.hinge === "RIGHT";
    return {
      leafId,
      kind: "tilt_turn",
      pivot: right ? leafRegion.x + leafRegion.w : leafRegion.x,
      dir: (right ? 1 : -1) * (out ? -1 : 1),
      travel: 0,
      tiltPivot: leafRegion.y,
      ...anchor,
      partZ: { sash: 0, glazing: 0, bead: 0 },
    };
  }
  if (spec.movement === "TURN" || spec.door) {
    const right = spec.hinge === "RIGHT";
    return {
      leafId,
      kind: "swing",
      pivot: right ? leafRegion.x + leafRegion.w : leafRegion.x,
      dir: (right ? 1 : -1) * (out ? -1 : 1),
      travel: 0,
      ...anchor,
      partZ: { sash: 0, glazing: 0, bead: 0 },
    };
  }
  return null;
}

/** One sash'd leaf of a bay: ring + pane + glazing seat + bound hardware
 * + its presentation motion. Pair leaves each occupy their own slot
 * column; the passive leaf carries the inversor stile and the falleba
 * cues instead of the handle. Returns nothing it cannot honestly pose. */
function operableLeaf(
  solids: Solid3D[],
  leaves: LeafMotion[],
  module: ProductModuleJson,
  bay: IntentNode,
  slotRegion: Region,
  spec: ResolvedLeaf,
  leafIndex: number,
  pairPeer: ResolvedLeaf | null,
  members: MemberGeometry,
  depth: number,
  diagnostics: SceneDiagnostic[],
): void {
  const owner = `${module.id}/${bay.id}`;
  const leafId = `${bay.id}:${leafIndex}`;
  const leafFrom = solids.length;
  const declaredT = Number(bay.glass_thickness_mm);
  const glassT = Math.max(
    Number.isFinite(declaredT) && declaredT > 0 ? declaredT : GLASS_DEFAULT_MM,
    4,
  );
  const sashW = Math.min(members.sash.faceWidthMm, slotRegion.w / 3, slotRegion.h / 3);
  const sashD = depth * 0.45;
  // The sash overhangs its slot column onto the frame face by the rebate
  // overlap, and its interior face stands a step proud of the frame's —
  // no coplanar z-fight, and the closed leaf reads as a leaf seated in a
  // frame, not geometry inscribed inside a hole.
  const overlap = Math.min(10, sashW * 0.25);
  const leafRegion: Region = {
    x: slotRegion.x - overlap,
    y: slotRegion.y - overlap,
    w: slotRegion.w + overlap * 2,
    h: slotRegion.h + overlap * 2,
  };
  const sashFace = depth + 2;
  memberBarRing(solids, owner, "sash", members.sash, leafRegion, sashW, sashD, sashFace - sashD);
  // Glazing seats inside the sash from its interior face — recessed a
  // few millimetres, never proud of the sash and never coplanar with it.
  const glassRecess = Math.max(2, Math.min(6, sashD - glassT));
  const leafGlassZ = Math.max(sashFace - sashD + 1, sashFace - glassRecess - glassT);
  if (bay.panel_article_sku) {
    solids.push(
      box(
        owner,
        "panel",
        members.frame.material,
        leafRegion.x + sashW,
        leafRegion.y + sashW,
        leafGlassZ,
        Math.max(leafRegion.w - 2 * sashW, 1),
        Math.max(leafRegion.h - 2 * sashW, 1),
        glassT,
      ),
    );
  } else {
    glassInfill(
      solids,
      owner,
      leafRegion.x + sashW,
      leafRegion.y + sashW,
      leafGlassZ,
      Math.max(leafRegion.w - 2 * sashW, 1),
      Math.max(leafRegion.h - 2 * sashW, 1),
      glassT,
      bay.glass_spec,
      bay.glass_composition,
    );
  }
  gasketAndBead(
    solids,
    owner,
    leafRegion,
    sashW,
    sashFace,
    leafGlassZ + glassT,
    members.beadSpecFor(bay.glass_thickness_mm ?? null),
  );

  let anchor: Vec3 | null = null;
  if (spec.movement !== "FIXED") {
    anchor = hardwareSolids(
      solids,
      owner,
      bay,
      leafRegion,
      sashW,
      sashFace,
      sashD,
      members,
      diagnostics,
      spec,
    );
  }
  if (spec.role === "PASSIVE" && pairPeer) {
    // Falleba: the passive leaf locks top and bottom through the meeting
    // stile — two flush bolt cues on its interior face where the cremona
    // pins would throw.
    const meetingX =
      spec.hinge === "LEFT" ? leafRegion.x + leafRegion.w - sashW / 2 : leafRegion.x + sashW / 2;
    for (const boltY of [leafRegion.y + sashW, leafRegion.y + leafRegion.h - sashW - 80]) {
      solids.push({
        ...box(owner, "handle", "STEEL", meetingX - 7, boltY, sashFace + 1, 14, 80, 9),
        approximate: true,
      });
    }
    // The inversor is the passive leaf's astragal — a profile on its
    // meeting edge covering the pair's joint, moving with this leaf.
    const boundary = meetingX;
    solids.push(
      box(
        owner,
        "sash",
        members.sash.material,
        boundary - Math.min(sashW * 0.45, 26),
        leafRegion.y + sashW * 0.5,
        sashFace + 2,
        Math.min(sashW * 0.9, 52),
        leafRegion.h - sashW,
        10,
      ),
    );
  }
  tagLeaf(solids, leafFrom, leafId);
  const motion = leafMotionFor(leafId, leafRegion, spec);
  if (motion) {
    motion.partZ = leafPartZ(solids, leafId, depth * 0.75);
    motion.detail = anchor ?? undefined;
    leaves.push(motion);
  }
}

/** Leaf bay solids: sliding panes ride their declared tracks at stepped
 * depths, operable leaves get a sash ring + pane, fixed leaves a pane,
 * panels an opaque slab. Operable leaves also register a presentation-only
 * LeafMotion so the view can open them. */
function leafSolids(
  solids: Solid3D[],
  leaves: LeafMotion[],
  module: ProductModuleJson,
  bay: IntentNode,
  region: Region,
  members: MemberGeometry,
  depth: number,
  diagnostics: SceneDiagnostic[],
): void {
  const owner = `${module.id}/${bay.id}`;
  const bead = members.beadFor(bay.glass_thickness_mm ?? null);
  const sliding = resolvedSlidingLayout(bay);
  const door = bayIsDoor(module.tree, bay);
  const leafSpecs = resolvedLeaves(bay, door);
  const operable = sliding !== null || leafSpecs.some((leaf) => leaf.sash);
  const declaredT = Number(bay.glass_thickness_mm);
  const glassT = Math.max(
    Number.isFinite(declaredT) && declaredT > 0 ? declaredT : GLASS_DEFAULT_MM,
    4,
  );
  const glassZ = Math.max((depth - glassT) / 2, 0);

  if (sliding && sliding.panels.length > 0) {
    // Slot geometry mirrors the front view: each slot is `pitch` wide, a
    // moving leaf covers its slot plus the meeting-stile interlock and is
    // clamped inside the bay; fixed panels glaze their slot directly.
    const pitch = region.w / sliding.panels.length;
    const interlock = members.sash.faceWidthMm;
    const leafW = pitch + interlock;
    const trackStep = Math.min(24, Math.max(depth * 0.18, 10));
    const sashD = Math.min(24, depth * 0.4);
    // P19 — riel 0 is the EXTERIOR rail (the model's declared order); each
    // next track steps toward the room face. A leaf is delante/detrás of
    // its neighbour purely by its declared track.
    const trackZ = (track: number): number => Math.min(glassZ + track * trackStep, depth - glassT);
    // The leaf a user actually opens: the declared `primary_index` when
    // the layout carries it, else the room-side rail's moving leaf — on a
    // two-leaf slider moving both would just swap the leaves and reveal
    // nothing.
    const movingIndexes = sliding.panels
      .map((panel, index) => ({ panel, index }))
      .filter((entry) => entry.panel.kind === "MOVING");
    const innermost = movingIndexes.reduce(
      (best, entry) => ((entry.panel.track ?? 0) > (best?.panel.track ?? -1) ? entry : best),
      movingIndexes[0],
    );
    const primaryIndex = sliding.primary_index ?? innermost?.index ?? 0;
    sliding.panels.forEach((panel, index) => {
      // FIXED panels declare track:null — they glaze the outermost plane,
      // outside every rail, not on a moving track.
      const track =
        panel.track ?? (panel.kind === "FIXED" ? -1 : index % Math.max(sliding.tracks, 1));
      const z0 = track < 0 ? Math.max(glassZ - trackStep, 2) : trackZ(track);
      const slotX = region.x + pitch * index;
      if (panel.kind === "FIXED") {
        // Fixed slots glaze directly — no sash, same as the front view.
        glassInfill(
          solids,
          owner,
          slotX + bead,
          region.y + bead,
          z0,
          Math.max(pitch - 2 * bead, 1),
          Math.max(region.h - 2 * bead, 1),
          glassT,
          bay.glass_spec,
          bay.glass_composition,
        );
        return;
      }
      // The engine gives each leaf its slot plus the full central overlap
      // to the right — the renderer draws the same coverage, clamped inside
      // the bay for the last leaf whose slot has no room left.
      const leafX = Math.min(Math.max(slotX, region.x), region.x + region.w - leafW);
      const paneRegion: Region = { x: leafX, y: region.y, w: leafW, h: region.h };
      const leafId = `${bay.id}:${index}`;
      const leafFrom = solids.length;
      const sashW = Math.min(members.sash.faceWidthMm, leafW / 3, region.h / 3);
      memberBarRing(
        solids,
        owner,
        "sash",
        members.sash,
        paneRegion,
        sashW,
        sashD,
        Math.max(z0 - sashD, 0),
      );
      // The glazing seats inside the sash from its interior face — a pane
      // never sits proud of the sash that carries it.
      const glassRecess = Math.max(2, Math.min(6, sashD - glassT));
      const leafGlassZ = Math.max(z0 - sashD + 2, z0 - glassRecess - glassT);
      glassInfill(
        solids,
        owner,
        paneRegion.x + sashW,
        paneRegion.y + sashW,
        leafGlassZ,
        Math.max(leafW - 2 * sashW, 1),
        Math.max(paneRegion.h - 2 * sashW, 1),
        glassT,
        bay.glass_spec,
        bay.glass_composition,
      );
      gasketAndBead(
        solids,
        owner,
        paneRegion,
        sashW,
        z0,
        leafGlassZ + glassT,
        members.beadSpecFor(bay.glass_thickness_mm ?? null),
      );
      // Pull on the meeting stile — the same convention the handle policy
      // seeds for manufacturing (L1 right, every later leaf left). The
      // pull family comes from the selected kit's declared name (uñero /
      // tirador / elevable); its size is the fitting's real size, never a
      // percentage of the leaf height, and it stays inside the track step
      // so it can't punch the leaf on the next rail.
      const visual = resolveHardwareVisual(
        bay,
        { x: leafX, y: region.y, w: leafW, h: region.h },
        members,
        owner,
      );
      if (index === 0) diagnostics.push(...visual.diagnostics);
      const stileX = index === 0 ? leafX + leafW - sashW / 2 : leafX + sashW / 2;
      const pullCy = Math.min(
        Math.max(visual.handle?.heightMm ?? region.y + HANDLE_HEIGHT_MM, region.y + 90),
        region.y + region.h - 90,
      );
      if (visual.handle) {
        // Only the primary leaf's pull may stand proud of its face — a
        // surface bar on an inner track would punch through the leaf that
        // crosses in front of it; those always draw the flush cup.
        const kind: HandleKind = index === primaryIndex ? visual.handle.kind : "recessed_pull";
        slidingPull(solids, owner, kind, stileX, pullCy, z0, sashW, !visual.handle.kitBound);
      }
      tagLeaf(solids, leafFrom, leafId);
      // Presentation only: the PRIMARY leaf slides toward its neighbouring
      // slot in its declared `travel` direction (P05 — the documented
      // convention only when nothing is declared), capped so it can never
      // leave the frame. Only one leaf animates: translating two leaves
      // on the same rail means they interpenetrate mid-animation, and
      // opening anything but the room-side leaf reads wrong from inside.
      if (index === primaryIndex) {
        const declared = panelTravel(panel, index, sliding.panels.length);
        const dir = declared === "LEFT" ? -1 : 1;
        const room = dir > 0 ? region.x + region.w - leafX - leafW : leafX - region.x;
        const travel = Math.max(0, Math.min(pitch, room));
        if (travel > 1) {
          leaves.push({
            leafId,
            kind: "slide",
            pivot: 0,
            dir,
            travel,
            cx: leafX + leafW / 2,
            cy: region.y + region.h / 2,
            partZ: leafPartZ(solids, leafId, z0 - sashD / 2),
            detail: visual.handle ? [stileX, pullCy, z0 + glassT + 8] : undefined,
          });
        }
      }
    });
    // Sliding leaves ride rails — the track channels at the sill plane are
    // a physical detail, one per declared track, in the same track order
    // (riel 0 = el más exterior).
    for (let track = 0; track < sliding.tracks; track += 1) {
      solids.push(
        box(
          owner,
          "track",
          "ALUMINIUM",
          region.x,
          region.y,
          trackZ(track),
          region.w,
          TRACK_MM,
          TRACK_MM,
        ),
      );
    }
    return;
  }

  if (bay.panel_article_sku && !operable) {
    solids.push(
      box(
        owner,
        "panel",
        members.frame.material,
        region.x + bead,
        region.y + bead,
        glassZ,
        Math.max(region.w - 2 * bead, 1),
        Math.max(region.h - 2 * bead, 1),
        glassT,
      ),
    );
    return;
  }

  if (operable) {
    // Each resolved leaf owns an equal column of the aperture — the same
    // equal-split convention the 2D elevation draws for spec pairs. A
    // single leaf takes the whole region.
    const pitch = region.w / leafSpecs.length;
    const activeIndex = Math.max(
      leafSpecs.findIndex((leaf) => leaf.role !== "PASSIVE"),
      0,
    );
    leafSpecs.forEach((spec, index) => {
      const slot: Region = {
        x: region.x + pitch * index,
        y: region.y,
        w: pitch,
        h: region.h,
      };
      if (!spec.sash) {
        // A FIXED leaf inside a spec pair glazes its column directly —
        // same reading as a fixed bay, no sash ring.
        glassInfill(
          solids,
          owner,
          slot.x + bead,
          slot.y + bead,
          glassZ,
          Math.max(slot.w - 2 * bead, 1),
          Math.max(slot.h - 2 * bead, 1),
          glassT,
          bay.glass_spec,
          bay.glass_composition,
        );
        gasketAndBead(
          solids,
          owner,
          slot,
          bead,
          depth,
          glassZ + glassT,
          members.beadSpecFor(bay.glass_thickness_mm ?? null),
        );
        return;
      }
      // The peer the inversor faces: the ACTIVE leaf of a pair — a
      // passive leaf's astragal covers the joint toward it.
      const peer = spec.role === "PASSIVE" ? (leafSpecs[activeIndex] ?? null) : null;
      operableLeaf(
        solids,
        leaves,
        module,
        bay,
        slot,
        spec,
        index,
        peer,
        members,
        depth,
        diagnostics,
      );
    });
    return;
  }

  glassInfill(
    solids,
    owner,
    region.x + bead,
    region.y + bead,
    glassZ,
    Math.max(region.w - 2 * bead, 1),
    Math.max(region.h - 2 * bead, 1),
    glassT,
    bay.glass_spec,
    bay.glass_composition,
  );
  gasketAndBead(
    solids,
    owner,
    region,
    bead,
    depth,
    glassZ + glassT,
    members.beadSpecFor(bay.glass_thickness_mm ?? null),
  );
}

/** The glazing seat around a pane: the bead ring straddles the glass edge
 * on the member's interior face (half its width lands on the sash/frame
 * face, half covers the glass perimeter — the real glazing-bead geometry),
 * and the gasket line hugs the glass just behind it. `inset` is the member
 * face that frames the pane, `faceZ` the member's interior face, and
 * `glassTopZ` the pane's interior plane. */
function gasketAndBead(
  solids: Solid3D[],
  owner: string,
  region: Region,
  inset: number,
  faceZ: number,
  glassTopZ: number,
  beadSpec?: MemberSpec | null,
): void {
  const beadW = Math.max(Math.min(inset * 0.45, 20), 10);
  const ring: Region = {
    x: region.x + inset - beadW / 2,
    y: region.y + inset - beadW / 2,
    w: Math.max(region.w - inset * 2 + beadW, beadW * 2),
    h: Math.max(region.h - inset * 2 + beadW, beadW * 2),
  };
  const beadZ = faceZ - 1;
  const beadDepth = Math.min(BEAD_DEPTH_MM, 9);
  // A declared bead section extrudes the real profile; anything else stays
  // the explicitly-approximate thin ring.
  if (beadSpec && normalizedSection(beadSpec) !== null) {
    memberBarRing(solids, owner, "bead", beadSpec, ring, beadW, beadDepth, beadZ);
  } else {
    thinRing(solids, owner, "bead", "PVC", ring, beadW, beadZ, beadDepth);
  }
  thinRing(
    solids,
    owner,
    "gasket",
    "GASKET",
    {
      x: region.x + inset - GASKET_MM / 2,
      y: region.y + inset - GASKET_MM / 2,
      w: region.w - inset * 2 + GASKET_MM,
      h: region.h - inset * 2 + GASKET_MM,
    },
    GASKET_MM,
    Math.min(glassTopZ, beadZ) - GASKET_MM,
    GASKET_MM,
  );
}

/** Glass-only module: the pane IS the module. Supports map to their
 * declared edges; fittings carry no position authority, so they render at
 * conventional spots (patch corners, lock at handle height) purely as a
 * visualization cue — counts and SKUs stay exact. */
function framelessSolids(
  solids: Solid3D[],
  module: ProductModuleJson,
  w: number,
  h: number,
  depth: number,
): void {
  const spec = module.frameless;
  if (!spec) return;
  const owner = module.id;
  const reveal = 6;
  // The pane is the bay's declared glass — the primary bay carries the
  // selected thickness, falling back to the neutral default only when
  // nothing is declared.
  const declaredT = Number(modulePrimaryBay(module)?.glass_thickness_mm);
  const glassT = Math.max(
    Number.isFinite(declaredT) && declaredT > 0 ? declaredT : GLASS_DEFAULT_MM,
    4,
  );
  glassInfill(
    solids,
    owner,
    reveal,
    reveal,
    Math.max((depth - glassT) / 2, 0),
    Math.max(w - 2 * reveal, 1),
    Math.max(h - 2 * reveal, 1),
    glassT,
    modulePrimaryBay(module)?.glass_spec,
    modulePrimaryBay(module)?.glass_composition,
  );
  const edgeSpan = (edge: string): Region => {
    switch (edge) {
      case "left":
        return { x: 0, y: 0, w: SUPPORT_CHANNEL_MM, h };
      case "right":
        return { x: w - SUPPORT_CHANNEL_MM, y: 0, w: SUPPORT_CHANNEL_MM, h };
      case "top":
        return { x: 0, y: h - SUPPORT_CHANNEL_MM, w, h: SUPPORT_CHANNEL_MM };
      default:
        return { x: 0, y: 0, w, h: SUPPORT_CHANNEL_MM };
    }
  };
  for (const support of spec.supports) {
    const span = edgeSpan(support.edge);
    if (support.kind === "CHANNEL") {
      solids.push({
        ...box(
          owner,
          "support",
          "ALUMINIUM",
          span.x,
          span.y,
          depth * 0.35,
          span.w,
          span.h,
          SUPPORT_CHANNEL_MM * 2,
        ),
        approximate: true,
      });
      continue;
    }
    const qty = Math.max(Math.floor(support.qty) || 2, 1);
    const horizontal = support.edge === "top" || support.edge === "bottom";
    for (let i = 0; i < qty; i += 1) {
      const t = qty === 1 ? 0.5 : i / (qty - 1);
      const cx = horizontal ? span.x + t * Math.max(span.w - FITTING_BLOCK_MM, 0) : span.x;
      const cy = horizontal ? span.y : span.y + t * Math.max(span.h - FITTING_BLOCK_MM, 0);
      solids.push({
        ...box(
          owner,
          "support",
          "ALUMINIUM",
          cx,
          cy,
          depth * 0.35,
          horizontal ? FITTING_BLOCK_MM : span.w,
          horizontal ? span.h : FITTING_BLOCK_MM,
          SUPPORT_CHANNEL_MM * 2,
        ),
        approximate: true,
      });
    }
  }
  const size = FITTING_BLOCK_MM * 0.6;
  // Same conventional layout the front view draws: patches cycle the
  // corners, locks mount on the right edge, hinges the left, connectors
  // top, clamps/supports bottom.
  const fittingIndex = new Map<string, number>();
  const edgeRun = (edge: "left" | "right" | "top" | "bottom", index: number, count = 3) => {
    const frac = ((index % count) + 0.75) / (count + 0.5);
    return edge === "left"
      ? { x: 0, y: (h - size) * frac }
      : edge === "right"
        ? { x: w - size, y: (h - size) * frac }
        : edge === "top"
          ? { x: (w - size) * frac, y: h - size }
          : { x: (w - size) * frac, y: 0 };
  };
  for (const fitting of spec.fittings) {
    const index = fittingIndex.get(fitting.kind) ?? 0;
    fittingIndex.set(fitting.kind, index + 1);
    if (fitting.kind === "PATCH_FITTING") {
      const corner = [
        { x: 0, y: 0 },
        { x: w - size, y: 0 },
        { x: 0, y: h - size },
        { x: w - size, y: h - size },
      ][index % 4]!;
      solids.push({
        ...box(
          owner,
          "fitting",
          "STEEL",
          corner.x,
          corner.y,
          depth * 0.3,
          size,
          size,
          SUPPORT_CHANNEL_MM * 2,
        ),
        approximate: true,
      });
    } else if (fitting.kind === "LOCK") {
      const lockY = Math.min(1000, h * 0.7);
      solids.push({
        ...box(
          owner,
          "fitting",
          "STEEL",
          w - size,
          lockY + index * size,
          depth * 0.3,
          size,
          size,
          SUPPORT_CHANNEL_MM * 2,
        ),
        approximate: true,
      });
    } else if (fitting.kind === "HINGE") {
      const spot = edgeRun("left", index);
      solids.push({
        ...box(
          owner,
          "fitting",
          "STEEL",
          spot.x,
          spot.y,
          depth * 0.3,
          size,
          size,
          SUPPORT_CHANNEL_MM * 2,
        ),
        approximate: true,
      });
    } else if (fitting.kind === "CONNECTOR" || fitting.kind === "SEAL") {
      const spot = edgeRun("top", index);
      solids.push({
        ...box(
          owner,
          "fitting",
          "STEEL",
          spot.x,
          spot.y,
          depth * 0.3,
          size,
          size,
          SUPPORT_CHANNEL_MM * 2,
        ),
        approximate: true,
      });
    } else {
      const spot = edgeRun("bottom", index + 1);
      solids.push({
        ...box(
          owner,
          "fitting",
          "STEEL",
          spot.x,
          spot.y,
          depth * 0.3,
          size,
          size,
          SUPPORT_CHANNEL_MM * 2,
        ),
        approximate: true,
      });
    }
  }
}

/** Build the full 3D scene from the product + catalog member geometry +
 * engine plan (optional). World space: x = plan.x, y = elevation up,
 * z = −plan.y (depth into the wall). */
export function buildScene3D(
  product: ProductJson,
  members: MemberGeometry,
  plan?: PlanGeometry | null,
): Scene3D {
  const { rects, joints, columns } = frontLayout(product);
  const frameT = members.frame.faceWidthMm;
  const fallbackDepth = Math.max(
    Number(members.frame.section?.depth_mm) || FALLBACK_DEPTH_MM,
    frameT,
  );
  const planById = new Map((plan?.modules ?? []).map((module) => [module.module_id, module]));
  const moduleById = new Map(product.assembly.modules.map((module) => [module.id, module]));
  const moduleScenes: ModuleScene[] = [];
  const worldPoints: Vec3[] = [];
  const diagnostics: SceneDiagnostic[] = [];

  const stacks = resolveStacks(product);
  // Declared-angle front chain for plan-less products — mirrors the engine's
  // plan walk: column i's heading adds the seam's angle_deg, each column's
  // front-start is the previous one's front-end. Corner/bow assemblies
  // fold; a straight chain degenerates to the flat elevation.
  const columnTransform = new Map<string, { x: number; y: number; theta: number }>();
  {
    const columnSeams = joints.filter((joint) => joint.kind === "column");
    const couplingById = new Map(
      product.assembly.couplings.map((coupling) => [coupling.id, coupling]),
    );
    let chainX = 0;
    let chainY = 0;
    let theta = 0;
    columns.forEach((column, index) => {
      columnTransform.set(column.rootId, { x: chainX, y: chainY, theta });
      chainX += column.w * Math.cos(theta);
      chainY += column.w * Math.sin(theta);
      const seam = columnSeams[index];
      // The elevation nulls angleDeg on non-INLINE seams because a front
      // view does not bend — the scene walk still folds on every declared
      // coupling angle, so a CORNER joint angles the following columns.
      const angleDeg =
        seam?.angleDeg ?? (seam?.couplingId ? couplingById.get(seam.couplingId)?.angle_deg : null);
      if (angleDeg) theta += (Number(angleDeg) * Math.PI) / 180;
    });
  }
  for (const rect of rects) {
    const module = rect.module;
    const w = Number(module.width_mm);
    const h = Number(module.height_mm);
    const rootId = stacks.stackRoot.get(module.id) ?? module.id;
    const { position, rotationY, depth, fromPlan } = planTransform(
      planById.get(module.id),
      rect,
      fallbackDepth,
      columnTransform.get(rootId),
    );
    // A stacked member shares its root's plan footprint; the elevation
    // centres it inside the column, so offset along the root heading by
    // the same width difference (negative when the member protrudes).
    if (fromPlan && stacks.stackRoot.has(module.id)) {
      const root = moduleById.get(stacks.stackRoot.get(module.id) as string);
      const delta = (Number(root?.width_mm ?? w) - w) / 2;
      if (delta !== 0) {
        position[0] += delta * Math.cos(rotationY);
        position[2] += -delta * Math.sin(rotationY);
      }
    }
    const solids: Solid3D[] = [];
    const leaves: LeafMotion[] = [];

    if (module.frameless) {
      framelessSolids(solids, module, w, h, depth);
    } else if (module.contour) {
      // Contour modules extrude the real outline; like the 2D front view
      // they render no bay tree — the glazing is the contoured opening
      // itself, so the pane can never overhang a sloped or arched edge.
      solids.push({
        kind: "shape",
        owner: module.id,
        surface: "frame",
        material: members.frame.material,
        outline: insetContourPoints(module.contour, 0).map((p) => [p.x, p.y] as Pt2),
        holes: [insetContourPoints(module.contour, frameT).map((p) => [p.x, p.y] as Pt2)],
        z0: 0,
        depth,
        smooth: true,
      });
      const primaryBay = modulePrimaryBay(module);
      const bead = members.beadFor(primaryBay?.glass_thickness_mm ?? null);
      const declaredT = Number(primaryBay?.glass_thickness_mm);
      const glassT = Math.max(
        Number.isFinite(declaredT) && declaredT > 0 ? declaredT : GLASS_DEFAULT_MM,
        4,
      );
      contourGlassInfill(
        solids,
        primaryBay ? `${module.id}/${primaryBay.id}` : module.id,
        module.contour,
        frameT + bead,
        Math.max((depth - glassT) / 2, 0),
        glassT,
        primaryBay?.glass_spec,
        primaryBay?.glass_composition,
      );
    } else {
      const out = {
        bars: [] as { node: IntentNode; region: Region; vertical: boolean }[],
        leaves: [] as NodeRegion[],
      };
      // The bay tree lives inside the frame aperture; split offsets stay
      // absolute from the module's outer corner, as ModuleTree does in 2D.
      walkNode(
        module.tree,
        { x: frameT, y: frameT, w: w - frameT * 2, h: h - frameT * 2 },
        { x: 0, y: 0 },
        members,
        out,
      );

      // A leaf touching the sill owns its bottom member: a door leaf
      // closes on the declared threshold (the engine models the door frame
      // as 3-sided — the threshold IS its bottom member), anything else
      // sits on the frame's bottom profile. Posts run full height and the
      // head spans between them.
      const sillLeaves = out.leaves
        .filter((leaf) => leaf.region.y <= frameT + 0.5)
        .sort((a, b) => a.region.x - b.region.x);
      // Spec doors (`unit_kind: "DOOR"` or a DOOR opening) get the same
      // 3-sided frame + threshold as the legacy DOOR_ENTRY — the door is
      // a door regardless of which form declared it.
      if (sillLeaves.some((leaf) => bayIsDoor(module.tree, leaf.node))) {
        const thresholdW = Math.min(members.threshold?.faceWidthMm ?? frameT, h / 4);
        const thresholdSpec = members.threshold ?? members.frame;
        memberBar(
          solids,
          module.id,
          "frame",
          members.frame,
          "y",
          0,
          h,
          frameT / 2,
          frameT,
          0,
          depth,
        );
        memberBar(
          solids,
          module.id,
          "frame",
          members.frame,
          "y",
          0,
          h,
          w - frameT / 2,
          frameT,
          0,
          depth,
          true,
        );
        memberBar(
          solids,
          module.id,
          "frame",
          members.frame,
          "x",
          frameT,
          w - frameT,
          h - frameT / 2,
          frameT,
          0,
          depth,
          true,
        );
        let cursor = frameT;
        for (const leaf of sillLeaves) {
          if (leaf.region.x > cursor) {
            memberBar(
              solids,
              module.id,
              "frame",
              members.frame,
              "x",
              cursor,
              leaf.region.x,
              frameT / 2,
              frameT,
              0,
              depth,
            );
          }
          if (bayIsDoor(module.tree, leaf.node)) {
            memberBar(
              solids,
              module.id,
              "threshold",
              thresholdSpec,
              "x",
              leaf.region.x,
              leaf.region.x + leaf.region.w,
              thresholdW / 2,
              thresholdW,
              0,
              depth,
            );
            leaf.region = {
              x: leaf.region.x,
              y: thresholdW,
              w: leaf.region.w,
              h: leaf.region.y + leaf.region.h - thresholdW,
            };
          } else {
            memberBar(
              solids,
              module.id,
              "frame",
              members.frame,
              "x",
              leaf.region.x,
              leaf.region.x + leaf.region.w,
              frameT / 2,
              frameT,
              0,
              depth,
            );
          }
          cursor = Math.max(cursor, leaf.region.x + leaf.region.w);
        }
        if (cursor < w - frameT) {
          memberBar(
            solids,
            module.id,
            "frame",
            members.frame,
            "x",
            cursor,
            w - frameT,
            frameT / 2,
            frameT,
            0,
            depth,
          );
        }
      } else {
        memberBarRing(
          solids,
          module.id,
          "frame",
          members.frame,
          { x: 0, y: 0, w, h },
          frameT,
          depth,
          0,
        );
      }
      for (const bar of out.bars) {
        const mullion = bar.vertical ? members.mullionV : members.mullionH;
        const mullionSection = mullion !== null ? normalizedSection(mullion) : null;
        if (mullionSection !== null) {
          solids.push({
            kind: "profile",
            owner: module.id,
            surface: "mullion",
            material: mullion!.material,
            outline: mullionSection.outline,
            axis: bar.vertical ? "y" : "x",
            a0: bar.vertical ? bar.region.y : bar.region.x,
            a1: bar.vertical ? bar.region.y + bar.region.h : bar.region.x + bar.region.w,
            u0: bar.vertical
              ? bar.region.x + bar.region.w / 2 - mullionSection.width / 2
              : bar.region.y + bar.region.h / 2 - mullionSection.width / 2,
            v0: 0,
          });
          continue;
        }
        solids.push({
          ...box(
            module.id,
            "mullion",
            mullion?.material ?? members.frame.material,
            bar.region.x,
            bar.region.y,
            0,
            Math.max(bar.region.w, 0.5),
            Math.max(bar.region.h, 0.5),
            depth,
          ),
          approximate: true,
        });
      }
      for (const leaf of out.leaves) {
        leafSolids(solids, leaves, module, leaf.node, leaf.region, members, depth, diagnostics);
      }
    }

    moduleScenes.push({ moduleId: module.id, position, rotationY, depth, solids, leaves });

    const cos = Math.cos(rotationY);
    const sin = Math.sin(rotationY);
    const corners: Vec3[] = [
      [0, 0, 0],
      [w, 0, 0],
      [0, h, 0],
      [w, h, 0],
      [0, 0, depth],
      [w, h, depth],
    ];
    for (const [cx, cy, cz] of corners) {
      worldPoints.push([
        position[0] + cx * cos + cz * sin,
        position[1] + cy,
        position[2] - cx * sin + cz * cos,
      ]);
    }
  }

  // Couplers: INLINE wedges come from the plan's coupling polygons; stack
  // contacts become horizontal bars at the member's sill line. Coupler
  // pair endpoints use the declared `modules` binding when present, else
  // the positional chain order (same convention the engine resolves).
  const couplers: Solid3D[] = [];
  // Pairs resolve with the same explicit-or-positional convention the
  // layout uses: `coupling.modules`, else index i binds modules i and i+1.
  const pairByCoupling = new Map(stacks.pairs.map(({ coupling, pair }) => [coupling.id, pair]));
  // A joint's top matches the front view's seam: the min of the two bound
  // ROOT columns' tops, where a column top counts every stacked member — a
  // transom's sill + height raises the seam above the root's own height.
  const topByRoot = new Map(columns.map((column) => [column.rootId, column.top]));
  const couplingHeight = (couplingId: string | null): number => {
    const pair = couplingId === null ? undefined : pairByCoupling.get(couplingId);
    if (!pair) return 0;
    const tops = pair
      .map((id) => topByRoot.get(stacks.stackRoot.get(id) ?? id))
      .filter((top): top is number => typeof top === "number");
    return tops.length > 0 ? Math.min(...tops) : 0;
  };
  const jointByCoupling = new Map(
    joints
      .filter((joint) => joint.kind === "column" && joint.couplingId !== null)
      .map((joint) => [joint.couplingId as string, joint]),
  );
  for (const polygon of plan?.couplings ?? []) {
    const coupling = product.assembly.couplings.find((item) => item.id === polygon.coupling_id);
    const height = couplingHeight(polygon.coupling_id);
    if (polygon.polygon.length < 3 || height <= 0) continue;
    const material =
      members.couplerFor(coupling?.coupler_profile_sku ?? null)?.material ?? members.frame.material;
    // Straight joints extrude nothing: an exactly-0° coupling collapses
    // its plan triangle to coincident points — detect true degeneracy in
    // the polygon itself (the emitted geometry is the authority), not the
    // tiny real wedges a shallow angle legitimately produces.
    const uniquePoints = new Set(polygon.polygon.map((p) => `${Number(p.x_mm)},${Number(p.y_mm)}`))
      .size;
    const degenerate =
      uniquePoints < 3 ||
      Math.abs(
        polygon.polygon.reduce((acc, p, i) => {
          const q = polygon.polygon[(i + 1) % polygon.polygon.length]!;
          return acc + Number(p.x_mm) * Number(q.y_mm) - Number(q.x_mm) * Number(p.y_mm);
        }, 0) / 2,
      ) === 0;
    if (degenerate) {
      const joint = jointByCoupling.get(polygon.coupling_id);
      if (!joint) continue;
      const pair = pairByCoupling.get(polygon.coupling_id) ?? [];
      const depths = pair
        .map((id) => moduleScenes.find((scene) => scene.moduleId === id)?.depth)
        .filter((d): d is number => typeof d === "number");
      const depth = depths.length > 0 ? Math.min(...depths) : fallbackDepth;
      const couplerSpec = members.couplerFor(coupling?.coupler_profile_sku ?? null);
      const couplerSection = couplerSpec ? normalizedSection(couplerSpec) : null;
      const barW = couplerSpec?.faceWidthMm ?? frameT;
      // A straight joint's coupler runs vertically — its declared section
      // extrudes along the seam; undeclared stays an approximate bar.
      if (couplerSection !== null) {
        couplers.push({
          kind: "profile",
          owner: polygon.coupling_id,
          surface: "coupler",
          material,
          outline: couplerSection.outline,
          axis: "y",
          a0: 0,
          a1: height,
          u0: joint.x - couplerSection.width / 2,
          v0: 0,
        });
      } else {
        couplers.push({
          ...box(
            polygon.coupling_id,
            "coupler",
            material,
            joint.x - barW / 2,
            0,
            0,
            barW,
            height,
            depth,
          ),
          approximate: true,
        });
      }
      worldPoints.push([joint.x - barW / 2, 0, 0], [joint.x + barW / 2, height, depth]);
      continue;
    }
    couplers.push({
      kind: "prism",
      owner: polygon.coupling_id,
      surface: "coupler",
      material,
      outline: polygon.polygon.map((p) => [Number(p.x_mm), -Number(p.y_mm)] as Pt2),
      y0: 0,
      y1: height,
    });
    for (const p of polygon.polygon) {
      const x = Number(p.x_mm);
      const z = -Number(p.y_mm);
      worldPoints.push([x, 0, z], [x, height, z]);
    }
  }
  // Stack couplers live inside the member's local frame: the bar centres
  // on the member's sill line and follows its column's plan heading.
  for (const joint of joints) {
    if (joint.kind !== "stack" || !joint.couplingId) continue;
    const coupling = product.assembly.couplings.find((item) => item.id === joint.couplingId);
    const pair = pairByCoupling.get(joint.couplingId);
    const memberId = pair?.find((id) =>
      pair.some((other) => other !== id && stacks.stackParent.get(id) === other),
    );
    const memberScene = memberId
      ? moduleScenes.find((scene) => scene.moduleId === memberId)
      : undefined;
    const memberModule = memberId ? moduleById.get(memberId) : undefined;
    const couplerSpec = members.couplerFor(coupling?.coupler_profile_sku ?? null);
    const couplerSection = couplerSpec ? normalizedSection(couplerSpec) : null;
    const barW = couplerSpec?.faceWidthMm ?? 30;
    const run = memberModule ? Number(memberModule.width_mm) : joint.w;
    const depth = memberScene?.depth ?? fallbackDepth;
    const solid: Solid3D =
      couplerSection !== null
        ? {
            kind: "profile",
            owner: joint.couplingId,
            surface: "coupler",
            material: couplerSpec?.material ?? members.frame.material,
            outline: couplerSection.outline,
            axis: "x",
            a0: 0,
            a1: run,
            u0: -couplerSection.width / 2,
            v0: 0,
          }
        : {
            ...box(
              joint.couplingId,
              "coupler",
              couplerSpec?.material ?? members.frame.material,
              0,
              -barW / 2,
              0,
              run,
              barW,
              depth,
            ),
            approximate: true,
          };
    if (memberScene) {
      memberScene.solids.push(solid);
    } else {
      // Profile solids carry their own placement, so the orphan path (no
      // member scene to inherit from) keeps the declarative box which the
      // caller repositions.
      const bar =
        solid.kind === "box"
          ? solid
          : box(
              joint.couplingId,
              "coupler",
              couplerSpec?.material ?? members.frame.material,
              0,
              -barW / 2,
              0,
              run,
              barW,
              depth,
            );
      bar.center[0] = joint.x + bar.size[0] / 2;
      bar.center[1] = joint.y - barW / 2 + bar.size[1] / 2;
      couplers.push({ ...bar, approximate: true });
      worldPoints.push([joint.x, joint.y, 0], [joint.x + joint.w, joint.y, 0]);
    }
  }

  // D05: stamp the picked finish on member-family surfaces — the exterior
  // swatch rides the street face, the interior swatch the room face; the
  // same stamped pair drives the inside view's bicolor flip. A foil-class
  // material with no catalog texture renders its flat swatch flagged as an
  // approximation — never a simulated grain.
  const finish = members.frame.finish;
  if (finish) {
    const catalogTexture =
      (finish.exterior.texture ?? null) !== null || (finish.interior.texture ?? null) !== null;
    if (members.frame.material.includes("FOIL") && !catalogTexture) {
      diagnostics.push({
        code: "finish_convention",
        owner: "assembly",
        values: { material: members.frame.material },
      });
    }
    const sanitizeHex = (value: string | null | undefined): string | null =>
      value && /^#[0-9a-f]{6}$/i.test(value) ? value : null;
    const tintable: ReadonlySet<SolidKind> = new Set([
      "frame",
      "sash",
      "mullion",
      "bead",
      "coupler",
      "threshold",
    ]);
    const stamp = (solid: Solid3D): void => {
      if (!tintable.has(solid.surface)) return;
      solid.tint = sanitizeHex(finish.exterior.color);
      solid.tintInterior = sanitizeHex(finish.interior.color);
      solid.texture = finish.exterior.texture ?? null;
      solid.textureInterior = finish.interior.texture ?? null;
    };
    moduleScenes.forEach((module) => module.solids.forEach(stamp));
    couplers.forEach(stamp);
  }

  if (worldPoints.length === 0) {
    return {
      modules: moduleScenes,
      couplers,
      center: [0, 0, 0],
      radius: 1000,
      bounds: { min: [0, 0, 0], max: [0, 0, 0] },
      diagnostics,
    };
  }
  const min: Vec3 = [Infinity, Infinity, Infinity];
  const max: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (const p of worldPoints) {
    for (let i = 0; i < 3; i += 1) {
      min[i] = Math.min(min[i]!, p[i]!);
      max[i] = Math.max(max[i]!, p[i]!);
    }
  }
  const center: Vec3 = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
  const radius = Math.max(Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2, 200);
  return {
    modules: moduleScenes,
    couplers,
    center,
    radius,
    bounds: { min, max },
    diagnostics,
  };
}

/* ---------- Vano de muro (P19) ---------- */

const WALL_THICKNESS_MM = 140;
const WALL_REVEAL_MM = 160;
const WALL_GAP_MM = 8;
const SILL_BOARD_MM = 38;

/** The vano the "Vano" context toggle draws around the assembly: a plain
 * plastered reveal (three jambs + head, no insulation detail) plus the
 * interior sill board proud of the room face — enough context for a door
 * or window to read seated in its opening instead of floating in the
 * studio void. Solids come back in scene-world coordinates (the same
 * space `buildScene3D.bounds` describes) and render on the "wall" surface.
 * The wall is presentation context only — it never joins the model: no
 * owner selection, not part of explode groups. */
export function wallContext(bounds: { min: Vec3; max: Vec3 }): Solid3D[] {
  const x0 = bounds.min[0];
  const y0 = bounds.min[1];
  const x1 = bounds.max[0];
  const y1 = bounds.max[1];
  const w = x1 - x0;
  // The wall wraps the frame depth: it starts just behind the product's
  // outermost z and runs the declared wall thickness toward the room.
  const zStart = bounds.min[2] - 20;
  const headH = y1 + WALL_GAP_MM;
  return [
    // Head reveal — spans across the side jambs.
    box(
      "__wall__",
      "wall",
      "WALL",
      x0 - WALL_REVEAL_MM - WALL_GAP_MM,
      headH,
      zStart,
      w + 2 * (WALL_REVEAL_MM + WALL_GAP_MM),
      WALL_REVEAL_MM,
      WALL_THICKNESS_MM,
    ),
    // Jamb reveals.
    box(
      "__wall__",
      "wall",
      "WALL",
      x0 - WALL_REVEAL_MM - WALL_GAP_MM,
      y0 - WALL_GAP_MM,
      zStart,
      WALL_REVEAL_MM,
      headH - y0 + WALL_GAP_MM,
      WALL_THICKNESS_MM,
    ),
    box(
      "__wall__",
      "wall",
      "WALL",
      x1 + WALL_GAP_MM,
      y0 - WALL_GAP_MM,
      zStart,
      WALL_REVEAL_MM,
      headH - y0 + WALL_GAP_MM,
      WALL_THICKNESS_MM,
    ),
    // Interior sill board — noses proud of the room face, the way a real
    // tapajuntas interior reads.
    box(
      "__wall__",
      "wall",
      "WALL",
      x0 - WALL_REVEAL_MM / 2,
      y0 - SILL_BOARD_MM - WALL_GAP_MM,
      zStart - 30,
      w + WALL_REVEAL_MM,
      SILL_BOARD_MM,
      WALL_THICKNESS_MM + 90,
    ),
  ];
}
