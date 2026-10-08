import type { LeafMotion, Solid3D, SolidKind, Vec3 } from "./Product3DScene";

/** Presentation-pose math shared by the interactive orbit view and the
 * offscreen studio renderer — one contract so a "render export" can never
 * disagree with the live scene about how a leaf opens.
 *
 * Angles follow the real mechanism: a swing leaf rotates about its hinge
 * edge (Y), a tilt leaf about its bottom/top edge (X), a slide leaf along
 * its rail (X) — a single axis per pose, well under the 280 ms contract. */
export const SWING_RAD = (32 * Math.PI) / 180;
/** Oscilobatiente vent — ~10° on the bottom axis (P19). */
export const TILT_RAD = (10 * Math.PI) / 180;
/** Proyectante — a top-hung leaf reads opened wider than a tilt vent. */
export const AWNING_RAD = (24 * Math.PI) / 180;

/** The transforms a pose writes onto the leaf's nested groups:
 * outer pivots about the tilt edge (Rx), mid about the hinge edge (Ry),
 * inner carries the exploded lift — at most one rotation is nonzero per
 * pose, matching the real mechanism. */
export interface LeafPose {
  tiltPos: Vec3;
  tiltRotX: number;
  swingPos: Vec3;
  swingRotY: number;
  innerPos: Vec3;
}

/** Resolve a leaf's open/closed pose: `pose` 0..1 eases toward open,
 * `tilted` poses a tilt-turn leaf on its bottom pivot instead of its
 * side hinge. */
export function leafPose(motion: LeafMotion, pose: number, tilted: boolean): LeafPose {
  const tiltPivot = motion.tiltPivot ?? 0;
  if (motion.kind === "swing") {
    return {
      tiltPos: [0, 0, 0],
      tiltRotX: 0,
      swingPos: [motion.pivot, 0, 0],
      swingRotY: motion.dir * pose * SWING_RAD,
      innerPos: [-motion.pivot, 0, 0],
    };
  }
  if (motion.kind === "tilt") {
    const rad = motion.rad ?? TILT_RAD;
    return {
      tiltPos: [0, motion.pivot, 0],
      tiltRotX: motion.dir * pose * rad,
      swingPos: [0, -motion.pivot, 0],
      swingRotY: 0,
      innerPos: [0, 0, 0],
    };
  }
  if (motion.kind === "tilt_turn") {
    return {
      tiltPos: [0, tiltPivot, 0],
      tiltRotX: tilted ? pose * TILT_RAD : 0,
      swingPos: [motion.pivot, -tiltPivot, 0],
      swingRotY: tilted ? 0 : motion.dir * pose * SWING_RAD,
      innerPos: [-motion.pivot, 0, 0],
    };
  }
  // slide — translation along the rail, capped by the declared travel.
  return {
    tiltPos: [motion.dir * pose * motion.travel, 0, 0],
    tiltRotX: 0,
    swingPos: [0, 0, 0],
    swingRotY: 0,
    innerPos: [0, 0, 0],
  };
}

/** The despiece part a leaf solid plays — the ordered axial separation
 * pulls the sash assembly, the bead/gasket kit and the pane apart along
 * the glazing axis (marco → hojas → junquillos → vidrio). */
export type LeafPart = "sash" | "bead" | "glazing";

export function leafPart(surface: SolidKind): LeafPart {
  if (surface === "glass" || surface === "spacer" || surface === "panel") return "glazing";
  if (surface === "bead" || surface === "gasket") return "bead";
  return "sash";
}

/** Ordered despiece lifts along +z (toward the room): the sash leaves its
 * rebate first, then the pane, then the bead/gasket kit — the room-side
 * disassembly order (junquillo out first, closest to the viewer) — never
 * a single floating leaf block. The spread must read as an exploded
 * diagram at product scale, so it spans ~6× the profile depth (≈400 mm
 * on PVC) — ilustrativo, never a to-scale recorrido. `progress` 0..1
 * eases the separation. */
export function explodeLifts(
  depth: number,
  progress: number,
): { total: number; sash: number; bead: number; glazing: number } {
  const total = progress * Math.max(depth * 5.5, 400);
  return { total, sash: total * 0.32, glazing: total * 0.62, bead: total * 0.94 };
}

/** Mean z of a solid — the despiece guide anchor for its closed seat. */
export function solidZCenter(solid: Solid3D): number {
  switch (solid.kind) {
    case "box":
      return solid.center[2];
    case "shape":
      return solid.z0 + solid.depth / 2;
    case "profile":
      return solid.v0 + 15;
    default:
      return 0;
  }
}
