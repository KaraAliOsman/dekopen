import { describe, expect, it } from "vitest";
import type { HandlePolicy, HandleSlot, KitChoice } from "../../api/generated/models";
import type { IntentNode } from "./intentEditing";
import type { MemberGeometry } from "./members";
import { resolveHardwareVisual, slidingPullKind, type Region } from "./hardwareVisual";

/** Minimal MemberGeometry stub — only kitFor/handlePolicy matter here. */
function members(kits: KitChoice[], policy: HandlePolicy | null = null): MemberGeometry {
  const spec = {
    sku: "P",
    faceWidthMm: 60,
    depthMm: 60,
    sightlineMm: 60,
    material: "PVC" as const,
  };
  return {
    frame: spec,
    sash: spec,
    mullionV: null,
    mullionH: null,
    threshold: null,
    beadFor: () => 18,
    beadSpecFor: () => null,
    couplerFor: () => null,
    kitFor: (sku) => kits.find((kit) => kit.sku === sku) ?? null,
    handlePolicy: policy,
    rebateMm: 20,
    sashOverlapMm: 8,
  };
}

function kit(sku: string, contents: KitChoice["contents"]): KitChoice {
  return { sku, name: `Kit ${sku}`, opening_type: "TURN", contents } as KitChoice;
}

function slot(over: Partial<HandleSlot> = {}): HandleSlot {
  return {
    opening_type: "TURN_LEFT",
    leaf_slot: "LEAF",
    leaf_handedness: null,
    handle_domain_slot: "HANDLE",
    host_member_side: "LEFT",
    horizontal_reference: "HOST_MEMBER_AXIS",
    horizontal_offset_mm: "0",
    permitted_vertical_references: ["OUTER_BOTTOM"],
    mounting_min_from_leaf_top_mm: "300",
    mounting_max_from_leaf_top_mm: "1200",
    ...over,
  } as HandleSlot;
}

function policy(slots: HandleSlot[]): HandlePolicy {
  return { policy_id: "demo", version: 1, slots } as HandlePolicy;
}

const LEAF: Region = { x: 40, y: 50, w: 700, h: 1450 };

function bay(opening: string, over: Partial<IntentNode> = {}): IntentNode {
  return {
    id: "bay-1",
    type: "BAY",
    opening_type: opening as IntentNode["opening_type"],
    ...over,
  };
}

describe("resolveHardwareVisual — kit binding", () => {
  it("counts hinges from the kit's declared HINGE lines", () => {
    const visual = resolveHardwareVisual(
      bay("TURN_LEFT", { hardware_set_sku: "K1" }),
      LEAF,
      members([
        kit("K1", [{ sku: "H", name: "hinge", qty: "4", unit: "unit", category: "HINGE" }]),
      ]),
      "o1",
    );
    expect(visual.hinges).toEqual({ count: 4, authority: "kit" });
  });

  it("marks heuristic hinge counts as visual conventions", () => {
    const visual = resolveHardwareVisual(bay("TURN_LEFT"), LEAF, members([]), "o1");
    expect(visual.hinges?.authority).toBe("convention");
    expect(visual.diagnostics.map((d) => d.code)).toContain("hardware_convention");
  });

  it("reports an unresolved kit sku instead of assuming its pieces", () => {
    const visual = resolveHardwareVisual(
      bay("TURN_RIGHT", { hardware_set_sku: "MISSING" }),
      LEAF,
      members([]),
      "o1",
    );
    expect(visual.diagnostics.map((d) => d.code)).toContain("kit_unknown");
  });

  it("warns when the kit's declared bill carries no handle line", () => {
    const visual = resolveHardwareVisual(
      bay("TURN_LEFT", { hardware_set_sku: "K1" }),
      LEAF,
      members([
        kit("K1", [{ sku: "H", name: "hinge", qty: "3", unit: "unit", category: "HINGE" }]),
      ]),
      "o1",
    );
    expect(visual.handle?.kitBound).toBe(false);
    expect(visual.diagnostics.some((d) => d.code === "kit_unknown")).toBe(true);
  });
});

describe("resolveHardwareVisual — families", () => {
  it("mounts the lever opposite the hinge side named by the opening", () => {
    // TURN_LEFT = hinges on the left → lever on the right.
    const left = resolveHardwareVisual(bay("TURN_LEFT"), LEAF, members([]), "o1");
    expect(left.handle?.mountSide).toBe("right");
    const right = resolveHardwareVisual(bay("TURN_RIGHT"), LEAF, members([]), "o1");
    expect(right.handle?.mountSide).toBe("left");
  });

  it("doors read handedness from the declared door_handedness", () => {
    const door = resolveHardwareVisual(
      bay("DOOR_ENTRY", { door_handedness: "RIGHT" }),
      { x: 40, y: 30, w: 900, h: 2100 },
      members([]),
      "o1",
    );
    expect(door.family).toBe("DOOR");
    expect(door.handle?.kind).toBe("door_lever");
    expect(door.handle?.exterior).toBe(true);
    expect(door.handle?.mountSide).toBe("left");
    // A multipoint door without a kit keeps the cylinder convention.
    expect(door.handle?.cylinder).toBe(true);
  });

  it("awning leaves get a bottom-rail centre lever, never the side lever", () => {
    const visual = resolveHardwareVisual(bay("AWNING"), LEAF, members([]), "o1");
    expect(visual.handle?.kind).toBe("centre_lever");
    expect(visual.handle?.mountSide).toBe("bottom");
  });

  it("sliding leaves get a pull whose size is fixed by family, not leaf height", () => {
    const visual = resolveHardwareVisual(bay("SLIDING"), LEAF, members([]), "o1");
    expect(visual.handle?.kind).toBe("recessed_pull");
    expect(visual.handle?.interior).toBe(true);
    expect(visual.handle?.exterior).toBe(false);
  });

  it("a policy-declared host member beats the hinge-opposite convention", () => {
    const visual = resolveHardwareVisual(
      bay("TURN_LEFT"),
      LEAF,
      members([], policy([slot({ host_member_side: "RIGHT" })])),
      "o1",
    );
    expect(visual.handle?.mountSide).toBe("right");
  });
});

describe("resolveHardwareVisual — datum honesty", () => {
  it("traces the declared height from the module's outer bottom", () => {
    const visual = resolveHardwareVisual(
      bay("TURN_LEFT", { handle_height_mm: "1100" }),
      LEAF,
      members([]),
      "o1",
    );
    expect(visual.handle?.heightMm).toBe(1100);
    expect(visual.handle?.declaredMm).toBe(1100);
    expect(visual.handle?.diagnostics).toHaveLength(0);
  });

  it("flags a declared height outside the leaf instead of silently clamping", () => {
    const visual = resolveHardwareVisual(
      bay("TURN_LEFT", { handle_height_mm: "1800" }),
      LEAF,
      members([]),
      "o1",
    );
    const out = visual.diagnostics.find((d) => d.code === "handle_out_of_range");
    expect(out?.values.declared).toBe(1800);
    // The drawing still gets a clamped display position.
    expect(visual.handle?.heightMm).toBeLessThan(1800);
    // …but the declared value stays visible on the spec.
    expect(visual.handle?.declaredMm).toBe(1800);
  });

  it("flags a declared height outside the policy's mounting band", () => {
    // Leaf top = 1500 → band [300..1200] below top → y in [300, 1200].
    // Declared 1400 lands inside the leaf but above the band's hi=1200.
    const visual = resolveHardwareVisual(
      bay("TURN_LEFT", { handle_height_mm: "1400" }),
      LEAF,
      members([], policy([slot()])),
      "o1",
    );
    const out = visual.diagnostics.find((d) => d.code === "handle_out_of_range");
    expect(out?.values.declared).toBe(1400);
    expect(out?.values.max).toBe(1200);
  });

  it("reports when the policy's permitted references can't express the declared datum", () => {
    const visual = resolveHardwareVisual(
      bay("TURN_LEFT", { handle_height_mm: "800" }),
      LEAF,
      members([], policy([slot({ permitted_vertical_references: ["LEAF_TOP"] })])),
      "o1",
    );
    expect(visual.diagnostics.map((d) => d.code)).toContain("handle_datum_unsupported");
  });
});

describe("slidingPullKind", () => {
  it("reads the pull family from the kit's declared name", () => {
    expect(slidingPullKind("Kit corredera elevable")).toBe("lift_slide");
    expect(slidingPullKind("Tirador superficial")).toBe("surface_pull");
    expect(slidingPullKind("Kit uñero")).toBe("recessed_pull");
    expect(slidingPullKind(null)).toBe("recessed_pull");
  });
});
