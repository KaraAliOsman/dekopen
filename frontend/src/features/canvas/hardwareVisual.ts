import type { HandlePolicy, HandleSlot, KitChoice } from "../../api/generated/models";
import type { IntentNode } from "./intentEditing";
import type { MemberGeometry } from "./members";

/** Phase-03 hardware visual contract — binds what the renderers draw to
 * what the catalog actually declares.
 *
 * Authority model:
 * - A selected kit (`hardware_set_sku` → `hardware_kits.contents`) supplies
 *   real counts by component category (HANDLE, HINGE, LOCK, ROLLER, …).
 *   Geometry itself is always a schematic representation — the catalog
 *   declares no manufacturer dimensions, so no drawing may claim to be a
 *   replica of a specific product.
 * - The system's handle_requirement_policies row supplies the mounting
 *   authority: which member hosts the handle, where horizontally, and the
 *   allowed mounting band measured from the leaf's top.
 * - When neither exists the renderer falls back to declared visual
 *   conventions marked `approximate` (edge-lined, schematic look), never
 *   presented as certified fitting placement. */

export type Region = { x: number; y: number; w: number; h: number };

export type SceneDiagnosticCode =
  | "kit_unknown"
  | "handle_out_of_range"
  | "handle_datum_unsupported"
  | "hardware_convention"
  /** A foil-class member renders flat — the catalog declared no texture
   * for the face, so the swatch is an approximation, never a foil photo. */
  | "finish_convention";

export interface SceneDiagnostic {
  code: SceneDiagnosticCode;
  /** Selection id of the leaf/bay the diagnostic belongs to. */
  owner: string;
  /** Values interpolated into the i18n message. */
  values: Record<string, string | number>;
}

export type HandleKind =
  /** Casement/tilt-turn window lever: rose + spindle + lever arm. */
  | "lever"
  /** Door lever pair on a long escutcheon plate, both faces. */
  | "door_lever"
  /** Sliding flush cup pull (uñero / cierre embutido). */
  | "recessed_pull"
  /** Sliding surface bar pull (tirador). */
  | "surface_pull"
  /** Lift-slide: lever + surface grip. */
  | "lift_slide"
  /** Awning/projectante bottom-rail centre handle. */
  | "centre_lever";

export interface HandleSpec {
  kind: HandleKind;
  interior: boolean;
  exterior: boolean;
  /** Real cylinder lock under the handle — kit-declared LOCK, or the door
   * convention when a multipoint door has no kit on file. */
  cylinder: boolean;
  /** mm above the module's outer bottom edge — the declared datum of
   * `handle_height_mm` (same datum the manufacturing authority resolves). */
  heightMm: number;
  /** The declared value when one exists; null when the convention drew. */
  declaredMm: number | null;
  /** Which leaf member the handle mounts on. */
  mountSide: "left" | "right" | "bottom" | "top";
  /** Kit-bound when the kit's contents declare the handle line. */
  kitBound: boolean;
  diagnostics: SceneDiagnostic[];
}

export interface HingeSpec {
  count: number;
  /** "kit" when the count is the kit's declared HINGE qty; "convention"
   * when the visual heuristic placed them — the renderer must draw those
   * schematic (edges). */
  authority: "kit" | "convention";
}

export interface HardwareVisualSpec {
  family: "CASEMENT" | "TILT_TURN" | "DOOR" | "SLIDING" | "AWNING" | "BOTTOM_HUNG" | "FRAMELESS";
  kitSku: string | null;
  kitName: string | null;
  hinges: HingeSpec | null;
  handle: HandleSpec | null;
  diagnostics: SceneDiagnostic[];
}

const HANDLE_HEIGHT_MM = 1050;

/** Sum of kit contents lines in a category — qty 0 still counts as
 * declared (the kit states it carries none). */
function kitQty(kit: KitChoice, category: string): number {
  let qty = 0;
  for (const component of kit.contents ?? []) {
    if (component.category === category) qty += Number(component.qty) || 0;
  }
  return qty;
}

/** Best matching policy slot for a bay: opening type + leaf handedness —
 * a declared-handedness rule wins over the wildcard, the same precedence
 * the documentary resolver applies. */
function policySlotFor(
  policy: HandlePolicy | null,
  opening: string,
  handedness: "LEFT" | "RIGHT" | null,
): HandleSlot | null {
  if (!policy) return null;
  const candidates = policy.slots.filter((slot) => slot.opening_type === opening);
  const exact = candidates.find(
    (slot) => slot.leaf_handedness !== null && slot.leaf_handedness === handedness,
  );
  if (exact) return exact;
  return candidates.find((slot) => slot.leaf_handedness == null) ?? candidates[0] ?? null;
}

/** DIN convention: the opening name is the hinge side; the door carries
 * `door_handedness` (hinge side). Returns the hinge side — the handle
 * mounts opposite. */
export function hingeSide(bay: IntentNode): "LEFT" | "RIGHT" | null {
  const opening = bay.opening_type;
  if (opening === "TURN_LEFT" || opening === "TILT_TURN_LEFT") return "LEFT";
  if (opening === "TURN_RIGHT" || opening === "TILT_TURN_RIGHT") return "RIGHT";
  if (opening === "DOOR_ENTRY") return bay.door_handedness === "RIGHT" ? "RIGHT" : "LEFT";
  return null;
}

/** Per-leaf opening contract normalized from the spec form (D03
 * `opening`/`leaves`) — or the legacy enum mapped into the same shape —
 * so a pair's ACTIVE/PASSIVE leaves pose and carry hardware exactly as
 * declared instead of collapsing to the bay's enum. */
export interface LeafSpecInput {
  movement: string;
  hinge: "LEFT" | "RIGHT" | "TOP" | "BOTTOM" | null;
  direction: "INWARD" | "OUTWARD";
  role: "SINGLE" | "ACTIVE" | "PASSIVE" | null;
  door: boolean;
}

/** The opening vocabulary the handle policies are written in — spec
 * leaves map onto it so the declared host member/band still governs
 * (unknown movements get no slot and fall back to convention). */
function specOpeningKey(spec: LeafSpecInput): string {
  if (spec.door) return "DOOR_ENTRY";
  switch (spec.movement) {
    case "TILT_TURN":
      return spec.hinge === "RIGHT" ? "TILT_TURN_RIGHT" : "TILT_TURN_LEFT";
    case "TURN":
      return spec.hinge === "RIGHT" ? "TURN_RIGHT" : "TURN_LEFT";
    case "TOP_HUNG":
      return "AWNING";
    case "BOTTOM_HUNG":
    case "TILT":
      return "BOTTOM_HUNG";
    case "SLIDE":
    case "LIFT_SLIDE":
    case "PARALLEL_SLIDE":
      return "SLIDING";
    default:
      return spec.movement;
  }
}

/** The hinge side a spec leaf pivots on — TOP/BOTTOM hinges stay null
 * here because the handle mounts on the free edge, not a stile. */
export function specHingeSide(spec: LeafSpecInput): "LEFT" | "RIGHT" | null {
  return spec.hinge === "LEFT" || spec.hinge === "RIGHT" ? spec.hinge : null;
}

/** The handle's vertical position in module space: the declared
 * `handle_height_mm` measured up from the module's outer bottom edge.
 * When the declared point lands outside the policy's mounting band (or
 * outside the leaf altogether) the spec keeps the impossible value visible
 * through `diagnostics` — the drawing clamps for display only and the
 * incompatibility is reported, never silently corrected. */
function resolveHandleHeight(
  bay: IntentNode,
  leaf: Region,
  slot: HandleSlot | null,
  owner: string,
): { heightMm: number; declaredMm: number | null; diagnostics: SceneDiagnostic[] } {
  const diagnostics: SceneDiagnostic[] = [];
  const declaredRaw = Number(bay.handle_height_mm);
  const declaredMm = Number.isFinite(declaredRaw) && declaredRaw > 0 ? declaredRaw : null;
  let heightMm = declaredMm ?? HANDLE_HEIGHT_MM;

  const leafBottom = leaf.y;
  const leafTop = leaf.y + leaf.h;
  if (declaredMm !== null && (declaredMm < leafBottom || declaredMm > leafTop)) {
    diagnostics.push({
      code: "handle_out_of_range",
      owner,
      values: {
        declared: declaredMm,
        min: leafBottom,
        max: leafTop,
      },
    });
    heightMm = Math.min(Math.max(heightMm, leafBottom + 40), leafTop - 40);
  }

  if (slot) {
    const minTop = Number(slot.mounting_min_from_leaf_top_mm);
    const maxTop = Number(slot.mounting_max_from_leaf_top_mm);
    if (Number.isFinite(minTop) && Number.isFinite(maxTop) && maxTop > minTop) {
      // The policy bands the handle by distance below the leaf's top.
      const lo = leafTop - maxTop;
      const hi = leafTop - minTop;
      if (declaredMm !== null && (heightMm < lo - 0.01 || heightMm > hi + 0.01)) {
        diagnostics.push({
          code: "handle_out_of_range",
          owner,
          values: { declared: declaredMm, min: Math.round(lo), max: Math.round(hi) },
        });
        heightMm = Math.min(Math.max(heightMm, lo), hi);
      }
      const references = slot.permitted_vertical_references;
      const bottomOk = references.includes("OUTER_BOTTOM") || references.includes("LEAF_BOTTOM");
      if (!bottomOk && declaredMm !== null) {
        diagnostics.push({
          code: "handle_datum_unsupported",
          owner,
          values: { refs: references.join(", ") },
        });
      }
    }
  }
  return { heightMm, declaredMm, diagnostics };
}

/** Sliding pull family from the selected kit's declared name — "uñero" /
 * "embutido" flush cups, "tirador" surface bars, "elevable" lift-slide
 * levers. An unrecognized name keeps the flush-cup schematic. */
export function slidingPullKind(kitName: string | null): HandleKind {
  if (!kitName) return "recessed_pull";
  const name = kitName.toLowerCase();
  if (/elevable|lift|alzante/.test(name)) return "lift_slide";
  if (/tirador|asa\b/.test(name)) return "surface_pull";
  return "recessed_pull";
}

/** Resolve the visual contract for one bay leaf. Pure — no three.js, no
 * DOM. `leaf` is the sash leaf region in module space (y-up, outer
 * bottom = 0). */
export function resolveHardwareVisual(
  bay: IntentNode,
  leaf: Region,
  members: MemberGeometry,
  owner: string,
  spec?: LeafSpecInput,
): HardwareVisualSpec {
  const diagnostics: SceneDiagnostic[] = [];
  const kitSku = bay.hardware_set_sku ?? null;
  const kit = kitSku ? members.kitFor(kitSku) : null;
  if (kitSku && !kit) {
    diagnostics.push({ code: "kit_unknown", owner, values: { sku: kitSku } });
  }
  const kitName = kit?.name ?? null;
  const opening = spec ? specOpeningKey(spec) : (bay.opening_type ?? "FIXED");
  const door = spec ? spec.door : opening === "DOOR_ENTRY";
  const awning = spec ? spec.movement === "TOP_HUNG" : opening === "AWNING";
  const tiltTurn = spec ? spec.movement === "TILT_TURN" : opening.startsWith("TILT_TURN");
  const bottomHung = spec ? spec.movement === "BOTTOM_HUNG" || spec.movement === "TILT" : false;
  const sliding = spec ? spec.movement === "SLIDE" : opening.startsWith("SLIDING");
  const family = door
    ? "DOOR"
    : awning
      ? "AWNING"
      : tiltTurn
        ? "TILT_TURN"
        : bottomHung
          ? "BOTTOM_HUNG"
          : sliding
            ? "SLIDING"
            : "CASEMENT";

  const policy = members.handlePolicy;
  const handedness = spec ? specHingeSide(spec) : hingeSide(bay);
  const slot = policySlotFor(policy, opening, handedness === "LEFT" ? "LEFT" : handedness);

  // Hinges: a kit-declared HINGE quantity is the authority; otherwise the
  // height heuristic draws a schematic count explicitly marked convention.
  let hinges: HingeSpec | null = null;
  if (family === "BOTTOM_HUNG") {
    // Bottom-hung pivots: two corner shoes carry the leaf — declared HINGE
    // qty is the authority when the kit names it.
    const declared = kit ? kitQty(kit, "HINGE") : 0;
    hinges =
      declared > 0
        ? { count: Math.max(Math.round(declared), 2), authority: "kit" }
        : { count: 2, authority: "convention" };
    if (hinges.authority === "convention") {
      diagnostics.push({ code: "hardware_convention", owner, values: { what: "hinges" } });
    }
  } else if (family !== "SLIDING" && opening !== "FIXED" && handedness !== null) {
    if (awning) {
      const declared = kit ? kitQty(kit, "HINGE") : 0;
      hinges =
        declared > 0
          ? { count: Math.max(Math.round(declared), 2), authority: "kit" }
          : { count: 2, authority: "convention" };
    } else {
      const declared = kit ? kitQty(kit, "HINGE") : 0;
      hinges =
        declared > 0
          ? { count: Math.max(Math.round(declared), 1), authority: "kit" }
          : {
              count: door ? (leaf.h > 2200 ? 4 : 3) : leaf.h > 1700 ? 3 : 2,
              authority: "convention",
            };
      if (hinges.authority === "convention") {
        diagnostics.push({ code: "hardware_convention", owner, values: { what: "hinges" } });
      }
    }
  }

  const declaredLock = kit ? kitQty(kit, "LOCK") > 0 : false;
  const declaredHandle = kit ? kitQty(kit, "HANDLE") > 0 : null;
  let handle: HandleSpec | null = null;
  if (spec?.role === "PASSIVE") {
    // The passive leaf locks through the espagnolette bolt into the
    // meeting stile — it never carries the bay's handle (the falleba cue
    // is drawn by the scene builder instead).
    handle = null;
  } else if (family === "CASEMENT" || family === "TILT_TURN" || family === "DOOR") {
    const hinge = handedness ?? "LEFT";
    // The policy's host member wins over the hinge-opposite convention —
    // a door kit can mount on a declared stile; BOTTOM hosts mean a
    // bottom-rail centre handle.
    const mountSide: HandleSpec["mountSide"] =
      slot && slot.host_member_side === "LEFT"
        ? "left"
        : slot && slot.host_member_side === "RIGHT"
          ? "right"
          : slot && slot.host_member_side === "BOTTOM"
            ? "bottom"
            : hinge === "LEFT"
              ? "right"
              : "left";
    const height = resolveHandleHeight(bay, leaf, slot, owner);
    diagnostics.push(...height.diagnostics);
    if (declaredHandle === false) {
      // The selected kit's declared bill carries no handle line — the
      // block stays visible as a diagnostic rather than an assumed piece.
      diagnostics.push({
        code: "kit_unknown",
        owner,
        values: { sku: `${kitSku} (sin línea HANDLE)` },
      });
    }
    handle = {
      kind: family === "DOOR" ? "door_lever" : "lever",
      interior: true,
      exterior: family === "DOOR",
      cylinder: family === "DOOR" ? declaredLock || !kit : declaredLock,
      heightMm: height.heightMm,
      declaredMm: height.declaredMm,
      mountSide,
      kitBound: declaredHandle === true,
      diagnostics: height.diagnostics,
    };
  } else if (family === "AWNING") {
    const height = resolveHandleHeight(bay, leaf, slot, owner);
    diagnostics.push(...height.diagnostics);
    handle = {
      kind: "centre_lever",
      interior: true,
      exterior: false,
      cylinder: false,
      // Awning handles conventionally mount centred on the bottom rail —
      // the declared datum, when present, is traced but the pull sits on
      // the leaf's bottom member, so a value above mid-leaf is reported.
      heightMm: height.declaredMm !== null ? height.heightMm : leaf.y + 30,
      declaredMm: height.declaredMm,
      mountSide: "bottom",
      kitBound: declaredHandle === true,
      diagnostics: height.diagnostics,
    };
    if (declaredHandle === false) {
      diagnostics.push({
        code: "kit_unknown",
        owner,
        values: { sku: `${kitSku} (sin línea HANDLE)` },
      });
    }
  } else if (family === "BOTTOM_HUNG") {
    const height = resolveHandleHeight(bay, leaf, slot, owner);
    diagnostics.push(...height.diagnostics);
    handle = {
      kind: "centre_lever",
      interior: true,
      exterior: false,
      cylinder: false,
      // A bottom-hung leaf opens on its top edge — the handle mounts
      // centred on the TOP rail (mirror of the awning convention).
      heightMm: height.declaredMm !== null ? height.heightMm : leaf.y + leaf.h - 30,
      declaredMm: height.declaredMm,
      mountSide: "top",
      kitBound: declaredHandle === true,
      diagnostics: height.diagnostics,
    };
    if (declaredHandle === false) {
      diagnostics.push({
        code: "kit_unknown",
        owner,
        values: { sku: `${kitSku} (sin línea HANDLE)` },
      });
    }
  } else if (family === "SLIDING") {
    const height = resolveHandleHeight(bay, leaf, slot, owner);
    diagnostics.push(...height.diagnostics);
    handle = {
      kind: slidingPullKind(kitName),
      interior: true,
      exterior: false,
      cylinder: declaredLock,
      heightMm: height.heightMm,
      declaredMm: height.declaredMm,
      mountSide: "right",
      kitBound: declaredHandle === true,
      diagnostics: height.diagnostics,
    };
  }

  return {
    family,
    kitSku,
    kitName,
    hinges,
    handle,
    diagnostics,
  };
}
