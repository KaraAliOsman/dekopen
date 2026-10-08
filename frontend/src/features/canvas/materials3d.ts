import * as THREE from "three";
import { fmtWire } from "../../format";

import type { Solid3D } from "./Product3DScene";

/** Wood-grain skin for foil-finished members (§05-C): a generated
 * CanvasTexture, license-free, with streaks running along the member's
 * run axis — never a flat brown fill. One base per orientation; solids
 * clone it with a repeat matched to their run length so grain density
 * stays physical. */
const grainCache = new Map<string, THREE.Texture>();

function drawGrain(axis: "u" | "v"): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "rgb(255,255,255)";
    ctx.fillRect(0, 0, 256, 256);
    // Grain needs real contrast to read at member scale (review M7) —
    // faint 4–11% streaks vanished against the foil base coat.
    for (let index = 0; index < 46; index += 1) {
      const at = Math.random() * 256;
      const wave = 4 + Math.random() * 14;
      const alpha = 0.1 + Math.random() * 0.16;
      ctx.strokeStyle = `rgba(52, 34, 16, ${fmtWire(alpha, 3)})`;
      ctx.lineWidth = 0.9 + Math.random() * 3.2;
      ctx.beginPath();
      if (axis === "u") {
        ctx.moveTo(-8, at);
        ctx.bezierCurveTo(64, at + wave, 192, at - wave, 264, at + wave * 0.5);
      } else {
        ctx.moveTo(at, -8);
        ctx.bezierCurveTo(at + wave, 64, at - wave, 192, at + wave * 0.5, 264);
      }
      ctx.stroke();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
}

/** The member's run length in mm — the axis the grain follows. */
export function runLength(solid: Solid3D): number {
  switch (solid.kind) {
    case "box":
      return Math.max(solid.size[0], solid.size[1]);
    case "profile":
      return Math.max(Math.abs(solid.a1 - solid.a0), 1);
    case "prism":
      return Math.max(Math.abs(solid.y1 - solid.y0), 1);
    default: {
      let extent = 1;
      for (const [x, y] of solid.outline) {
        extent = Math.max(extent, Math.abs(x), Math.abs(y));
      }
      return extent;
    }
  }
}

/** Per-solid grain texture: a clone of the cached base with a repeat
 * matching the member's run. Callers own disposal of the returned clone. */
export function foilGrainTexture(axis: "u" | "v", runMm: number): THREE.Texture {
  let base = grainCache.get(axis);
  if (!base) {
    base = drawGrain(axis);
    grainCache.set(axis, base);
  }
  const texture = base.clone();
  const repeat = Math.max(1, Math.round(runMm / 400));
  if (axis === "u") texture.repeat.set(repeat, 1);
  else texture.repeat.set(1, repeat);
  return texture;
}

/** Physical presentation materials (§05-C): the renderer's surface response
 * per catalog material and detail surface — two modes share one table.
 * TECHNICAL keeps the engineering-drawing look (matte, restrained);
 * COMMERCIAL steps toward PBR (metalness on aluminium/steel, lower
 * roughness, real glass transparency). A solid's `approximate` flag keeps
 * undeclared members visibly different from declared profiles. */

export type MaterialMode = "technical" | "commercial";

export interface SolidMaterial {
  colorToken: string;
  colorFallback: string;
  roughness: number;
  metalness: number;
  transparent: boolean;
  opacity: number;
  /** Glass gets depthWrite off + ior-ish clarity; others depth-write. */
  glass: boolean;
  /** Detail surfaces render as lines/dark in technical mode. */
  detail: boolean;
  /** Wood-grain axis for foil-finished members: "u" runs grain along the
   * texture's u coordinate (long box axis, contour sidewalls), "v" along v
   * (profile extrusion run, prism run). Undefined = no grain map. */
  grain?: "u" | "v";
}

const MEMBER_TOKENS: Record<string, string> = {
  PVC: "--member-pvc-fill",
  PVC_FOIL: "--member-foil-fill",
  ALUMINIUM: "--member-aluminium-fill",
  ALUMINIUM_ANTHRACITE: "--member-anthracite-fill",
};

/** PBR-ish response per member material in commercial mode — aluminium
 * families read as coated metal, polymer as satin plastic, foil as a
 * wood-toned skin over PVC. Unknown materials stay neutral. */
const MEMBER_RESPONSE: Record<string, { color: string; roughness: number; metalness: number }> = {
  // PVC blanco stays a desaturated polymer white — the previous warm
  // (rgb(214,211,201)) cast read as tan under the key light (review M6).
  PVC: { color: "rgb(223,225,220)", roughness: 0.55, metalness: 0.08 },
  PVC_FOIL: { color: "rgb(123,90,59)", roughness: 0.5, metalness: 0.05 },
  ALUMINIUM: { color: "rgb(143,149,154)", roughness: 0.42, metalness: 0.55 },
  // Powder-coated anthracite is near-matte — the previous metalness 0.6
  // caught the environment and washed to grey (review M7 / §05-H notes).
  ALUMINIUM_ANTHRACITE: { color: "rgb(54,58,64)", roughness: 0.55, metalness: 0.35 },
};
const MEMBER_RESPONSE_DEFAULT = { color: "rgb(223,225,220)", roughness: 0.55, metalness: 0.08 };

/** Grain follows the member's run axis: a long box's long dimension, a
 * profile's extrusion direction (v), a contour ring's perimeter (u). */
function grainAxis(solid: Solid3D): "u" | "v" {
  if (solid.kind === "box") return solid.size[0] >= solid.size[1] ? "u" : "v";
  if (solid.kind === "shape") return "u";
  return "v";
}

/** Member-family surfaces a picked finish can recolor — detail surfaces
 * (gasket, handle, track, steel) keep their own material even on a foiled
 * window. Matches the stamp pass in buildScene3D. */
const TINTABLE_SURFACES: ReadonlySet<string> = new Set([
  "frame",
  "sash",
  "mullion",
  "bead",
  "coupler",
  "threshold",
]);

export type SolidFace = "exterior" | "interior";

export function solidMaterial(
  solid: Solid3D,
  mode: MaterialMode,
  face: SolidFace = "exterior",
): SolidMaterial {
  const commercial = mode === "commercial";
  const material = baseMaterial(solid, commercial);
  // A declared finish overrides the member-material token: the picked
  // catalog hex is the authoritative swatch, the grain its texture.
  const tint = face === "interior" ? (solid.tintInterior ?? solid.tint) : solid.tint;
  const texture = face === "interior" ? (solid.textureInterior ?? solid.texture) : solid.texture;
  if (tint && TINTABLE_SURFACES.has(solid.surface)) {
    material.colorToken = "";
    material.colorFallback = tint;
  }
  if (texture === "WOOD_GRAIN" && TINTABLE_SURFACES.has(solid.surface)) {
    material.grain = grainAxis(solid);
  }
  return material;
}

function baseMaterial(solid: Solid3D, commercial: boolean): SolidMaterial {
  switch (solid.surface) {
    case "glass":
      return {
        colorToken: "--model3d-glass",
        colorFallback: "rgb(143,184,204)",
        roughness: commercial ? 0.06 : 0.15,
        metalness: 0,
        transparent: true,
        opacity: commercial ? 0.3 : 0.38,
        glass: true,
        detail: false,
      };
    case "panel":
      return {
        colorToken: "--member-panel-fill",
        colorFallback: "rgb(185,188,192)",
        roughness: commercial ? 0.6 : 0.75,
        metalness: 0.05,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: false,
      };
    case "bead":
      return {
        colorToken: "--member-pvc-edge",
        colorFallback: "rgb(179,173,160)",
        roughness: commercial ? 0.55 : 0.7,
        metalness: 0,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: true,
      };
    case "gasket":
      return {
        colorToken: "--model3d-gasket",
        colorFallback: "rgb(46,49,52)",
        roughness: 0.9,
        metalness: 0,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: true,
      };
    case "track":
      return {
        colorToken: "--model3d-steel",
        colorFallback: "rgb(138,145,151)",
        roughness: commercial ? 0.35 : 0.55,
        metalness: commercial ? 0.75 : 0.55,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: true,
      };
    case "handle":
      // The lever reads as real hardware — graphite, not sash-tinted steel
      // that vanishes against white PVC at scene zoom (render P2-4).
      return {
        colorToken: "--model3d-handle",
        colorFallback: "rgb(74,80,85)",
        roughness: commercial ? 0.32 : 0.45,
        metalness: commercial ? 0.9 : 0.55,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: true,
      };
    case "hinge":
    case "fitting":
    case "support":
      return {
        colorToken: "--model3d-steel",
        colorFallback: "rgb(169,178,184)",
        roughness: commercial ? 0.3 : 0.45,
        metalness: commercial ? 0.85 : 0.55,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: true,
      };
    case "spacer":
      // IGU edge spacer — mill-finish aluminium, the thin metal line at
      // the glass border; a detail surface like the bead/track.
      return {
        colorToken: "--member-aluminium-fill",
        colorFallback: "rgb(185,189,194)",
        roughness: commercial ? 0.35 : 0.6,
        metalness: commercial ? 0.7 : 0.3,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: true,
      };
    case "coupler":
      return {
        colorToken: "--model3d-coupler",
        colorFallback: "rgb(93,100,105)",
        roughness: commercial ? 0.5 : 0.7,
        metalness: commercial ? 0.4 : 0.1,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: false,
      };
    case "threshold":
      return {
        colorToken: "--member-aluminium-fill",
        colorFallback: "rgb(154,160,165)",
        roughness: commercial ? 0.45 : 0.65,
        metalness: commercial ? 0.6 : 0.2,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: false,
      };
    case "wall":
      // The Vano context — plain plaster: matte, neutral, never tinted
      // (the wall is not part of the product model).
      return {
        colorToken: "--model3d-wall",
        colorFallback: "rgb(215,211,200)",
        roughness: 0.9,
        metalness: 0,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: false,
      };
    default: {
      const response = MEMBER_RESPONSE[solid.material] ?? MEMBER_RESPONSE_DEFAULT;
      return {
        colorToken: MEMBER_TOKENS[solid.material] ?? "--member-panel-fill",
        colorFallback: response.color,
        roughness: commercial ? response.roughness : 0.75,
        metalness: commercial ? response.metalness : 0.05,
        transparent: false,
        opacity: 1,
        glass: false,
        detail: false,
        // Foil reads as grain only when the catalog declares the texture —
        // a bare foil swatch stays flat and the scene reports it
        // aproximado (finish_convention), never a simulated laminate.
        grain: undefined,
      };
    }
  }
}

/** Radial contact-shadow texture for the 3D stage — soft dark ellipse
 * under the product so it reads grounded, not floating in a void. One
 * shared texture, never disposed. */
let shadowTexture: THREE.Texture | null = null;
export function contactShadowTexture(): THREE.Texture {
  if (shadowTexture) return shadowTexture;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const gradient = ctx.createRadialGradient(128, 128, 8, 128, 128, 126);
    gradient.addColorStop(0, "rgba(20,24,22,0.38)");
    gradient.addColorStop(0.55, "rgba(20,24,22,0.16)");
    gradient.addColorStop(1, "rgba(20,24,22,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 256, 256);
  }
  shadowTexture = new THREE.CanvasTexture(canvas);
  return shadowTexture;
}
