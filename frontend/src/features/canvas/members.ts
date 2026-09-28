import type {
  DesignOptions,
  HandlePolicy,
  KitChoice,
  ProfileSection,
} from "../../api/generated/models";

/** Drawing hierarchy resolved from the catalog: member face widths and the
 * system's rebate/overlap geometry. Everything optional — the demo/DOM paths
 * without options fall back to sane PVC-60 proportions so the drawing still
 * reads as a real window. */

export interface MemberSpec {
  sku: string | null;
  /** Human catalog name for the resolved article — what the UI shows;
   * the SKU stays available for identity, not display. */
  name?: string | null;
  material: "PVC" | "ALUMINIUM" | string;
  faceWidthMm: number;
  /** Declared catalog cross-section; absent means the renderer must stay
   * approximate — never a fabricated declaration. */
  section?: ProfileSection | null;
}

export interface MemberGeometry {
  frame: MemberSpec;
  sash: MemberSpec;
  mullionV: MemberSpec | null;
  mullionH: MemberSpec | null;
  threshold: MemberSpec | null;
  /** bead sightline width by glass thickness (mm). */
  beadFor(glassThicknessMm: string | null): number;
  /** The bead as a member — section included when the catalog declares it.
   * Null when the thickness resolves to the neutral convention only. */
  beadSpecFor(glassThicknessMm: string | null): MemberSpec | null;
  couplerFor(sku: string | null): MemberSpec | null;
  /** Declared hardware kit by sku — contents carry the real component
   * counts (hinges, handles, locks) the visuals bind to. Null when the
   * sku is not in the system's kit list. */
  kitFor(sku: string | null): KitChoice | null;
  /** The system's declared handle-mounting policy, or null when none is
   * on file — callers must not silently invent datum conventions. */
  handlePolicy: HandlePolicy | null;
  rebateMm: number;
  sashOverlapMm: number;
  /** Serializable digest of the lookup tables the functions close over —
   * JSON.stringify drops functions, so caches that key on this object need
   * the bead/coupler mappings rendered as data. */
  signature?: string;
}

export const FALLBACK_MEMBERS = {
  frame: 60,
  sash: 72,
  mullion: 70,
  threshold: 30,
  bead: 18,
  rebate: 20,
  sashOverlap: 8,
} as const;

const FALLBACK = FALLBACK_MEMBERS;

function member(
  options: DesignOptions | undefined,
  role: string,
  fallbackWidth: number,
): MemberSpec {
  const profile = options?.profiles.find((item) => item.role === role);
  const faceWidth = profile ? Number(profile.face_width_mm) : NaN;
  return {
    sku: profile?.sku ?? null,
    name: profile?.name ?? null,
    material: profile?.material ?? "PVC",
    faceWidthMm: profile && Number.isFinite(faceWidth) && faceWidth > 0 ? faceWidth : fallbackWidth,
    section: profile?.section ?? null,
  };
}

export function resolveMembers(options: DesignOptions | undefined): MemberGeometry {
  const couplers = new Map<string, MemberSpec>();
  for (const item of options?.coupler_profiles ?? []) {
    const faceWidth = Number(item.face_width_mm);
    couplers.set(item.sku, {
      sku: item.sku,
      name: item.name,
      material: item.material,
      faceWidthMm: Number.isFinite(faceWidth) && faceWidth > 0 ? faceWidth : FALLBACK.mullion,
      section: item.section ?? null,
    });
  }
  const beads = new Map<string, MemberSpec>();
  for (const bead of options?.glazing_beads ?? []) {
    const width = Number(bead.bead_width_mm);
    if (Number.isFinite(width) && width > 0) {
      beads.set(bead.glass_thickness_mm, {
        sku: bead.sku,
        material: "PVC",
        faceWidthMm: width,
        section: bead.section ?? null,
      });
    }
  }
  const kits = new Map<string, KitChoice>();
  for (const item of options?.hardware_kits ?? []) {
    kits.set(item.sku, item);
  }
  const signature = JSON.stringify({
    beads: [...beads.entries()],
    couplers: [...couplers.entries()],
    // The kit's declared contents, not just its sku — a contents update
    // (hinge count, handle lines) must invalidate every visual that bound
    // to it.
    kits: [...kits.values()].map((item) => [item.sku, item.contents]),
    handlePolicy: options?.handle_policy ?? null,
  });
  const rebate = Number(options?.rebate_depth_mm);
  const sashOverlap = Number(options?.sash_overlap_mm);
  return {
    frame: member(options, "FRAME", FALLBACK.frame),
    sash: member(options, "SASH", FALLBACK.sash),
    mullionV: options?.profiles.some((item) => item.role === "MULLION_V")
      ? member(options, "MULLION_V", FALLBACK.mullion)
      : null,
    mullionH: options?.profiles.some((item) => item.role === "MULLION_H")
      ? member(options, "MULLION_H", FALLBACK.mullion)
      : null,
    threshold: options?.profiles.some((item) => item.role === "THRESHOLD")
      ? member(options, "THRESHOLD", FALLBACK.threshold)
      : null,
    beadFor(glassThicknessMm) {
      if (glassThicknessMm !== null && beads.has(glassThicknessMm))
        return beads.get(glassThicknessMm)!.faceWidthMm;
      // Unresolved or unknown thickness → neutral drawing convention, never
      // an arbitrary catalog bead presented as selected.
      return FALLBACK.bead;
    },
    beadSpecFor(glassThicknessMm) {
      if (glassThicknessMm !== null && beads.has(glassThicknessMm))
        return beads.get(glassThicknessMm)!;
      return null;
    },
    couplerFor(sku) {
      if (sku) return couplers.get(sku) ?? null;
      // Null selection only resolves when the catalog offers exactly one
      // coupler; ambiguity returns unresolved so the drawing stays neutral.
      return couplers.size === 1 ? (couplers.values().next().value ?? null) : null;
    },
    kitFor(sku) {
      return sku ? (kits.get(sku) ?? null) : null;
    },
    handlePolicy: options?.handle_policy ?? null,
    rebateMm: Number.isFinite(rebate) && rebate > 0 ? rebate : FALLBACK.rebate,
    sashOverlapMm:
      Number.isFinite(sashOverlap) && sashOverlap >= 0 ? sashOverlap : FALLBACK.sashOverlap,
    signature,
  };
}

/** Same resolved geometry, different declared material — surfaces that only
 * know the sealed finish (portal thumbnails) re-skin the neutral member set
 * instead of drawing every window as white PVC. */
export function reSkinMembers(base: MemberGeometry, material: string): MemberGeometry {
  const spec = (item: MemberSpec | null): MemberSpec | null =>
    item ? { ...item, material } : item;
  return {
    ...base,
    frame: { ...base.frame, material },
    sash: { ...base.sash, material },
    mullionV: spec(base.mullionV),
    mullionH: spec(base.mullionH),
    threshold: spec(base.threshold),
    beadSpecFor: (glassThicknessMm) => spec(base.beadSpecFor(glassThicknessMm)),
    couplerFor: (sku) => spec(base.couplerFor(sku)),
  };
}
