import type { PlanGeometry, PlanModule } from "../../api/generated/models";
import type { ContourJson, ProductJson, ProductModuleJson } from "./productEditing";
import { modulePrimaryBay, resolveStacks } from "./productEditing";
import type { IntentNode } from "./intentEditing";
import { resolvedSlidingLayout } from "./intentEditing";
import { insetContourPoints } from "./contourGeometry";
import { frontLayout } from "./ProductFrontSvg";
import type { MemberGeometry, MemberSpec } from "./members";

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
  | "spacer";

export interface BoxSolid {
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
export interface ShapeSolid {
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
}

/** Member run with a declared catalog cross-section (§05-B): `outline` is
 * the normalized section — u the face direction across the member slot,
 * v interior-positive depth with the exterior face at v = 0. `axis` is
 * the direction the member runs in module space ("x" for rails, "y" for
 * posts); the run spans a0..a1 and the (u,v) origin sits at (u0, v0).
 * Never approximate — the polygon IS the manufacturer declaration. */
export interface ProfileSolid {
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
export interface PrismSolid {
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
const HANDLE_OFFSET_MM = 14;
const HINGE_MM = 14;
const TRACK_MM = 10;

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
): void {
  const igu = iguSpec(spec);
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
): void {
  const outline = insetContourPoints(contour, insetMm).map((p) => [p.x, p.y] as Pt2);
  if (outline.length < 3) return;
  const igu = iguSpec(spec);
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

/** DIN hinge side per leaf: the opening name carries it for windows;
 * a door carries it as declared `door_handedness` (hinge side — the
 * handle mounts opposite). Undeclared doors default to LEFT, the same
 * convention the intent layer seeds, so editor 3D never silently mirrors
 * a product the freeze path would refuse. */
function leafHingeSide(bay: IntentNode): "LEFT" | "RIGHT" | null {
  const opening = bay.opening_type;
  if (opening === "TURN_LEFT" || opening === "TILT_TURN_LEFT") return "LEFT";
  if (opening === "TURN_RIGHT" || opening === "TILT_TURN_RIGHT") return "RIGHT";
  if (opening === "DOOR_ENTRY") return bay.door_handedness === "RIGHT" ? "RIGHT" : "LEFT";
  return null;
}

/** A lever handle on the leaf's free stile: escutcheon rose standing
 * proud of the interior sash face, spindle block, lever ~120 mm hanging
 * down (the EN closed pose). `faceZ` is the leaf's interior face; every
 * piece protrudes +z (room side) from it. */
function leverHandle(
  solids: Solid3D[],
  owner: string,
  x: number,
  y: number,
  faceZ: number,
  cylinder: boolean,
): void {
  const roseW = 26;
  const roseH = 56;
  const leverLen = 120;
  const leverH = 16;
  solids.push(
    box(owner, "handle", "STEEL", x, y - roseH / 2, faceZ, roseW, roseH, 10),
    box(owner, "handle", "STEEL", x + (roseW - 20) / 2, y - 10, faceZ + 10, 20, 20, 22),
    // Lever hangs down from the rose — the EN closed pose; a horizontal
    // lever pointing at the hinges reads mid-operation.
    box(
      owner,
      "handle",
      "STEEL",
      x + roseW / 2 - leverH / 2,
      y - leverLen,
      faceZ + 30,
      leverH,
      leverLen,
      leverH,
    ),
  );
  if (cylinder) {
    solids.push(
      box(owner, "handle", "STEEL", x + (roseW - 14) / 2, y - roseH / 2 - 46, faceZ, 14, 36, 9),
    );
  }
}

/** Operable-leaf hardware: hinge barrels on the hinge edge (subtle —
 * closed casement hinges hide behind the rebate), a lever handle opposite
 * them at the declared handle height (the conventional 1050 mm when
 * undeclared — a presentation convention; the declared value wins). */
function hardwareSolids(
  solids: Solid3D[],
  owner: string,
  bay: IntentNode,
  leafRegion: Region,
  sashW: number,
  zInterior: number,
  sashD: number,
): void {
  const opening = bay.opening_type;
  // Rebate hardware lives in the cavity between the sash's outer face and
  // the aperture edge — buried in neither member, hidden head-on, visible
  // in the gap at a three-quarter view exactly like the real fitting.
  const rebateZ = zInterior - sashD - 6;
  if (opening === "AWNING") {
    // Top-hung: two hinge barrels along the head plus a centre handle at
    // the bottom stile (the leaf's free edge).
    for (const frac of [0.2, 0.8]) {
      solids.push(
        box(
          owner,
          "hinge",
          "STEEL",
          leafRegion.x + leafRegion.w * frac - HINGE_MM / 2,
          leafRegion.y + leafRegion.h - sashW * 0.9,
          rebateZ,
          HINGE_MM,
          sashW * 0.7,
          10,
        ),
      );
    }
    solids.push(
      box(
        owner,
        "handle",
        "STEEL",
        leafRegion.x + leafRegion.w / 2 - 8,
        leafRegion.y + 30,
        zInterior,
        16,
        24,
        14,
      ),
    );
    return;
  }
  const hinge = leafHingeSide(bay);
  if (!hinge) return;
  const door = opening === "DOOR_ENTRY";
  const tiltTurn = opening === "TILT_TURN_LEFT" || opening === "TILT_TURN_RIGHT";
  const hingeX = hinge === "LEFT" ? leafRegion.x + 2 : leafRegion.x + leafRegion.w - HINGE_MM - 2;
  // Taller leaves carry more hinges — the fitting schedule scales with
  // the leaf, not a fixed two/three per opening type.
  const hingeCount = door ? (leafRegion.h > 2200 ? 4 : 3) : leafRegion.h > 1700 ? 3 : 2;
  for (let index = 0; index < hingeCount; index += 1) {
    const frac = 0.14 + (0.86 - 0.14) * (index / (hingeCount - 1));
    solids.push(
      box(
        owner,
        "hinge",
        "STEEL",
        hingeX,
        leafRegion.y + leafRegion.h * frac,
        rebateZ,
        HINGE_MM,
        Math.min(leafRegion.h * 0.1, door ? 130 : 110),
        10,
      ),
    );
  }
  if (tiltTurn) {
    // The top scissor stay runs from the hinge-side corner across the head
    // — the fitting a tilt-turn physically needs on top of its hinges.
    solids.push(
      box(
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
    );
  }
  const declaredHandle = Number(bay.handle_height_mm);
  // Module space measures up from the module's outer bottom edge — the
  // same OUTER_BOTTOM datum the manufacturing authority resolves. Clamp
  // onto the leaf so a stale value still lands on its free stile.
  const handleY = Math.min(
    Math.max(
      Number.isFinite(declaredHandle) && declaredHandle > 0 ? declaredHandle : HANDLE_HEIGHT_MM,
      leafRegion.y + 40,
    ),
    leafRegion.y + leafRegion.h - 40,
  );
  // The handle mounts on the stile OPPOSITE the hinges, offset inward.
  const roseX =
    hinge === "LEFT"
      ? leafRegion.x + leafRegion.w - HANDLE_OFFSET_MM - 26
      : leafRegion.x + HANDLE_OFFSET_MM;
  leverHandle(solids, owner, roseX, handleY, zInterior, door);
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
): void {
  const owner = `${module.id}/${bay.id}`;
  const bead = members.beadFor(bay.glass_thickness_mm ?? null);
  const sliding = resolvedSlidingLayout(bay);
  const operable = sliding !== null || (bay.opening_type != null && bay.opening_type !== "FIXED");
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
    sliding.panels.forEach((panel, index) => {
      // FIXED panels declare track:null — they sit on the outer glazing
      // plane (front-most slot), not on a moving rail.
      const track =
        panel.track ??
        (panel.kind === "FIXED" ? sliding.tracks - 1 : index % Math.max(sliding.tracks, 1));
      const z0 = Math.min(glassZ + (sliding.tracks - 1 - track) * trackStep, depth - glassT);
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
      // seeds for manufacturing (L1 right, every later leaf left). It stands
      // proud of the leaf's interior face at handle height, never deeper
      // than the track step so it can't punch the leaf on the next rail.
      const pullX = index === 0 ? leafX + leafW - sashW + 6 : leafX + sashW - 22;
      const pullH = Math.min(360, Math.max(region.h * 0.4, 140));
      const pullY =
        region.y +
        Math.min(
          Number.isFinite(Number(bay.handle_height_mm)) && Number(bay.handle_height_mm) > 0
            ? Number(bay.handle_height_mm)
            : HANDLE_HEIGHT_MM,
          region.h - pullH / 2,
        ) -
        pullH / 2;
      solids.push(
        box(
          owner,
          "handle",
          "STEEL",
          pullX,
          pullY,
          z0,
          16,
          pullH,
          Math.min(glassT + 12, Math.max(trackStep - 1, 6)),
        ),
      );
      tagLeaf(solids, leafFrom, leafId);
      // Presentation only: a leaf slides toward its neighbouring slot(s),
      // capped to stay inside the bay — the product declares no travel.
      // On a two-leaf slider both leaves moving at once just swap slots
      // and reveal nothing; physically one leaf (the inner-rail sash)
      // slides over the other to open half the bay.
      const allMoving2 =
        sliding.panels.length === 2 && sliding.panels.every((p) => p.kind === "MOVING");
      if (!(allMoving2 && index === 1)) {
        const dir = index * 2 < sliding.panels.length ? 1 : -1;
        const room = dir > 0 ? region.x + region.w - leafX - leafW : leafX - region.x;
        leaves.push({
          leafId,
          kind: "slide",
          pivot: 0,
          dir,
          travel: Math.max(0, Math.min(pitch, room)),
        });
      }
    });
    // Sliding leaves ride rails — the track channels at the sill plane are
    // a physical detail, one per declared track.
    for (let track = 0; track < sliding.tracks; track += 1) {
      solids.push(
        box(
          owner,
          "track",
          "ALUMINIUM",
          region.x,
          region.y,
          Math.min(glassZ + (sliding.tracks - 1 - track) * trackStep, depth - glassT),
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
    const leafId = owner;
    const leafFrom = solids.length;
    const sashW = Math.min(members.sash.faceWidthMm, region.w / 3, region.h / 3);
    const sashD = depth * 0.45;
    // The sash overhangs the aperture onto the frame face by the rebate
    // overlap, and its interior face stands a step proud of the frame's —
    // no coplanar z-fight, and the closed leaf reads as a leaf seated in a
    // frame, not geometry inscribed inside a hole.
    const overlap = Math.min(10, sashW * 0.25);
    const leafRegion: Region = {
      x: region.x - overlap,
      y: region.y - overlap,
      w: region.w + overlap * 2,
      h: region.h + overlap * 2,
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
    hardwareSolids(solids, owner, bay, leafRegion, sashW, sashFace, sashD);
    tagLeaf(solids, leafFrom, leafId);
    // Hinge conventions mirror hardwareSolids: TURN_LEFT/DOOR hinge on the
    // leaf's left edge, TURN_RIGHT on the right; TILT_TURN tips the top in
    // on a bottom pivot, AWNING swings its bottom out on a top pivot.
    const opening = bay.opening_type;
    if (opening === "AWNING") {
      leaves.push({
        leafId,
        kind: "tilt",
        pivot: leafRegion.y + leafRegion.h,
        dir: 1,
        travel: 0,
      });
    } else if (opening === "TILT_TURN_LEFT" || opening === "TILT_TURN_RIGHT") {
      // Both motions exist on the same leaf: TURN swings on the side
      // hinge, TILT tips the top in on the bottom pivot. The view poses
      // the leaf — CLOSED/TURN/TILT are presentation states only.
      const hinge = leafHingeSide(bay);
      leaves.push({
        leafId,
        kind: "tilt_turn",
        pivot: hinge === "RIGHT" ? leafRegion.x + leafRegion.w : leafRegion.x,
        dir: hinge === "RIGHT" ? 1 : -1,
        travel: 0,
        tiltPivot: leafRegion.y,
      });
    } else {
      const hinge = leafHingeSide(bay);
      const hingeLeft = hinge !== "RIGHT";
      leaves.push({
        leafId,
        kind: "swing",
        pivot: hingeLeft ? leafRegion.x : leafRegion.x + leafRegion.w,
        dir: hingeLeft ? -1 : 1,
        travel: 0,
      });
    }
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
      solids.push(
        box(
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
      );
      continue;
    }
    const qty = Math.max(Math.floor(support.qty) || 2, 1);
    const horizontal = support.edge === "top" || support.edge === "bottom";
    for (let i = 0; i < qty; i += 1) {
      const t = qty === 1 ? 0.5 : i / (qty - 1);
      const cx = horizontal ? span.x + t * Math.max(span.w - FITTING_BLOCK_MM, 0) : span.x;
      const cy = horizontal ? span.y : span.y + t * Math.max(span.h - FITTING_BLOCK_MM, 0);
      solids.push(
        box(
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
      );
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
      solids.push(
        box(
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
      );
    } else if (fitting.kind === "LOCK") {
      const lockY = Math.min(1000, h * 0.7);
      solids.push(
        box(
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
      );
    } else if (fitting.kind === "HINGE") {
      const spot = edgeRun("left", index);
      solids.push(
        box(
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
      );
    } else if (fitting.kind === "CONNECTOR" || fitting.kind === "SEAL") {
      const spot = edgeRun("top", index);
      solids.push(
        box(
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
      );
    } else {
      const spot = edgeRun("bottom", index + 1);
      solids.push(
        box(
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
      );
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
      if (sillLeaves.some((leaf) => leaf.node.opening_type === "DOOR_ENTRY")) {
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
          if (leaf.node.opening_type === "DOOR_ENTRY") {
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
        leafSolids(solids, leaves, module, leaf.node, leaf.region, members, depth);
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

  if (worldPoints.length === 0) {
    return { modules: moduleScenes, couplers, center: [0, 0, 0], radius: 1000 };
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
  return { modules: moduleScenes, couplers, center, radius };
}
