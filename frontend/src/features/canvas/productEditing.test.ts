import { describe, expect, it } from "vitest";

import {
  addAdjacentUnit,
  addStackedUnit,
  duplicateModule,
  insertModuleBetween,
  moduleNeighbors,
  swapModules,
  makeTrapezoidModule,
  elevationLayoutMm,
  equalizeCouplingAngles,
  equalizeModuleWidths,
  isProductModel,
  isSingleUnit,
  removeUnit,
  scaleModuleWidths,
  makeBowProduct,
  moduleGlassSku,
  moduleOpening,
  modulePanelSku,
  setModuleGlassThickness,
  moveModuleDivision,
  resizeModuleSeam,
  setModulePanel,
  setAllCouplingAngles,
  setCouplerSku,
  setModuleGlass,
  setCouplerSkuAll,
  setCouplingAngle,
  setModuleCount,
  setModuleFrameless,
  setModuleOpening,
  setModuleWidth,
  setAllModuleHeights,
  splitModuleBay,
  totalModuleWidth,
  wrapTreeAsProduct,
  type ProductJson,
} from "./productEditing";
import { resolveMembers } from "./members";

const TEST_MEMBERS = resolveMembers(undefined);
// Nested splits need declared mullion geometry — an undeclared mullion can
// no longer bound a bay region, so tests spell out the members they mean.
const MULLION_MEMBERS = {
  ...TEST_MEMBERS,
  mullionV: { sku: "MULL-60", material: "PVC", faceWidthMm: 70 },
  mullionH: { sku: "MULL-60", material: "PVC", faceWidthMm: 70 },
};

function bow(): ReturnType<typeof makeBowProduct> {
  return makeBowProduct({
    moduleCount: 3,
    widthMm: 2100,
    heightMm: 1400,
    angleDeg: 15,
  });
}

describe("makeBowProduct", () => {
  it("builds modules + couplings that sum to the nominal width", () => {
    const product = bow();
    expect(product.version).toBe("product-v2");
    expect(product.assembly.modules.map((m) => m.id)).toEqual(["m1", "m2", "m3"]);
    expect(product.assembly.couplings.map((c) => c.id)).toEqual(["c1", "c2"]);
    expect(totalModuleWidth(product)).toBeCloseTo(2100, 5);
    expect(isProductModel(product)).toBe(true);
    expect(isProductModel({ version: "product-v1" })).toBe(false);
  });
});

describe("addAdjacentUnit", () => {
  it("appends a unit inheriting the edge module and outermost joint", () => {
    const base = setCouplerSkuAll(bow(), "ACOPLE-60");
    const grown = addAdjacentUnit(base, "right");
    expect(grown.assembly.modules.map((m) => m.id)).toEqual(["m1", "m2", "m3", "m4"]);
    expect(grown.assembly.couplings.map((c) => c.id)).toEqual(["c1", "c2", "c3"]);
    const added = grown.assembly.modules.at(-1)!;
    expect(added.width_mm).toBe(base.assembly.modules.at(-1)!.width_mm);
    expect(added.height_mm).toBe(base.assembly.modules.at(-1)!.height_mm);
    expect(grown.assembly.couplings.at(-1)!.angle_deg).toBe("15.0");
    expect(grown.assembly.couplings.at(-1)!.coupler_profile_sku).toBe("ACOPLE-60");
  });

  it("prepends on the left and starts straight when no joint exists", () => {
    const single = wrapTreeAsProduct(
      { id: "g1", type: "BAY", opening_type: "FIXED" },
      "1000.00",
      "1200.00",
    );
    expect(isSingleUnit(single)).toBe(true);
    const grown = addAdjacentUnit(single, "left");
    expect(grown.assembly.modules.map((m) => m.id)).toEqual(["m2", "m1"]);
    expect(grown.assembly.couplings).toEqual([
      {
        id: "c1",
        angle_deg: "0.0",
        coupler_profile_sku: null,
        kind: "INLINE",
        modules: ["m2", "m1"],
        edges: ["right", "left"],
      },
    ]);
    expect(isSingleUnit(grown)).toBe(false);
    // the inherited unit is a deep copy, not a shared tree reference
    expect(grown.assembly.modules[0]!.tree).not.toBe(grown.assembly.modules[1]!.tree);
  });

  it("a single frameless pane stays product-v2, never classic", () => {
    const pane = wrapTreeAsProduct(
      { id: "g1", type: "BAY", opening_type: "FIXED", glass_spec: "4" },
      "1200.00",
      "2100.00",
    );
    const frameless = setModuleFrameless(pane, "m1", {
      supports: [{ kind: "CHANNEL", edge: "bottom", article_sku: "UCHANNEL-12", qty: 1 }],
      fittings: [],
      exposed_edges: ["top", "right", "bottom", "left"],
    });
    // The classic tree has nowhere to carry supports/fittings — serializing
    // as a framed single unit would silently drop the glass-only spec.
    expect(isSingleUnit(frameless)).toBe(false);
    expect(isSingleUnit(setModuleFrameless(frameless, "m1", null))).toBe(true);
  });

  it("carries the edge module's contour — scaled, never silently rect", () => {
    const trapezoid: ProductJson = {
      version: "product-v2",
      assembly: {
        modules: [
          makeTrapezoidModule("m1", "2400.00", "1400.00", 200, 200, {
            id: "g1",
            type: "BAY",
            opening_type: "FIXED",
          }),
        ],
        couplings: [],
      },
    };
    const grown = addAdjacentUnit(trapezoid, "right", { widthMm: "1200.00" });
    const added = grown.assembly.modules.at(-1)!;
    expect(added.contour).toBeDefined();
    expect(added.width_mm).toBe("1200.00");
    // Scaled to the new width: right edge lands on 1200, top corners keep
    // the same proportional inset (200/2400 → 100/1200).
    const xs = added.contour!.vertices.map((v) => Number(v.x_mm));
    expect(Math.max(...xs)).toBeCloseTo(1200, 2);
    expect(Math.min(...xs)).toBeCloseTo(0, 2);
    expect(Number(added.contour!.vertices[2]!.x_mm)).toBeCloseTo(1100, 2);
    expect(Number(added.contour!.vertices[3]!.x_mm)).toBeCloseTo(100, 2);
  });
});

describe("removeUnit", () => {
  it("drops an edge module with its one adjacent coupling", () => {
    const removed = removeUnit(bow(), "m1");
    expect(removed.assembly.modules.map((m) => m.id)).toEqual(["m2", "m3"]);
    expect(removed.assembly.couplings.map((c) => c.id)).toEqual(["c2"]);
  });

  it("heals interior removals by merging the deflection so orientation survives", () => {
    const bent = setAllCouplingAngles(bow(), "10.0");
    const removed = removeUnit(bent, "m2");
    expect(removed.assembly.modules.map((m) => m.id)).toEqual(["m1", "m3"]);
    // heading of m3 was 0 + 10 + 10 — the merged joint preserves it
    expect(removed.assembly.couplings).toHaveLength(1);
    expect(removed.assembly.couplings[0]!.angle_deg).toBe("20.0");
  });

  it("refuses to remove the last module or an unknown id", () => {
    const single = wrapTreeAsProduct(
      { id: "g1", type: "BAY", opening_type: "FIXED" },
      "1000.00",
      "1200.00",
    );
    expect(removeUnit(single, "m1")).toBe(single);
    expect(removeUnit(bow(), "nope")).toEqual(bow());
  });
});

describe("splitModuleBay", () => {
  it("splits the primary bay at the center with the given mullion", () => {
    const split = splitModuleBay(
      bow(),
      "m2",
      { type: "SPLIT_V", mullionSku: "MULL-60" },
      TEST_MEMBERS,
    );
    const tree = split.assembly.modules[1]!.tree;
    expect(tree.type).toBe("SPLIT_V");
    expect(tree.split_offset_mm).toBe("350.00");
    expect(tree.mullion_profile_sku).toBe("MULL-60");
    expect(tree.children).toHaveLength(2);
  });

  it("generates unique node ids across repeated splits", () => {
    const once = splitModuleBay(
      bow(),
      "m2",
      { type: "SPLIT_V", mullionSku: "MULL-60" },
      TEST_MEMBERS,
    );
    const twice = splitModuleBay(
      once,
      "m2",
      { type: "SPLIT_H", mullionSku: "MULL-60" },
      TEST_MEMBERS,
    );
    expect(twice).not.toBe(once);
  });

  it("refuses door bays and missing mullions", () => {
    const door = setModuleOpening(bow(), "m2", "DOOR_ENTRY");
    expect(
      splitModuleBay(door, "m2", { type: "SPLIT_V", mullionSku: "MULL-60" }, TEST_MEMBERS),
    ).toBe(door);
    expect(splitModuleBay(bow(), "m2", { type: "SPLIT_V", mullionSku: "" }, TEST_MEMBERS)).toEqual(
      bow(),
    );
  });

  it("splits at a pointer-chosen offset instead of the center", () => {
    const split = splitModuleBay(
      bow(),
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        offsetMm: "215.00",
      },
      TEST_MEMBERS,
    );
    expect(split.assembly.modules[1]!.tree.split_offset_mm).toBe("215.00");
  });

  it("splits the named leaf bay inside an already-divided module", () => {
    const once = splitModuleBay(
      bow(),
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        offsetMm: "350.00",
      },
      TEST_MEMBERS,
    );
    const secondBayId = once.assembly.modules[1]!.tree.children![1]!.id;
    const twice = splitModuleBay(
      once,
      "m2",
      {
        type: "SPLIT_H",
        mullionSku: "MULL-60",
        bayId: secondBayId,
        offsetMm: "500.00",
      },
      TEST_MEMBERS,
    );
    const tree = twice.assembly.modules[1]!.tree;
    // The first bay stays intact; the second child is now an SPLIT_H node.
    expect(tree.type).toBe("SPLIT_V");
    expect(tree.children![0]!.type).toBe("BAY");
    expect(tree.children![1]!.type).toBe("SPLIT_H");
    expect(tree.children![1]!.split_offset_mm).toBe("500.00");
  });

  it("centers nested splits inside the true bay region on off-center parents", () => {
    const once = splitModuleBay(
      bow(),
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        offsetMm: "200.00",
      },
      MULLION_MEMBERS,
    );
    const [leftBay, rightBay] = once.assembly.modules[1]!.tree.children!;
    // Fallback members (frame 60, mullion 70): left region [60, 165] is 105mm,
    // right region [235, 640] is 405mm — centering must use those spans, not
    // the raw parent offset.
    const left = splitModuleBay(
      once,
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        bayId: leftBay!.id,
      },
      MULLION_MEMBERS,
    );
    expect(left.assembly.modules[1]!.tree.children![0]!.type).toBe("SPLIT_V");
    expect(left.assembly.modules[1]!.tree.children![0]!.split_offset_mm).toBe("52.50");
    const right = splitModuleBay(
      once,
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        bayId: rightBay!.id,
      },
      MULLION_MEMBERS,
    );
    expect(right.assembly.modules[1]!.tree.children![1]!.type).toBe("SPLIT_V");
    expect(right.assembly.modules[1]!.tree.children![1]!.split_offset_mm).toBe("202.50");
  });

  it("refuses to bound a nested split without declared mullion geometry", () => {
    // A bay-local default derived from fallback member widths would persist a
    // guessed dimension as if it were authority — the split refuses instead.
    const once = splitModuleBay(
      bow(),
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        offsetMm: "200.00",
      },
      MULLION_MEMBERS,
    );
    const secondBayId = once.assembly.modules[1]!.tree.children![1]!.id;
    // Same-axis: the parent SPLIT_V's mullion bounds this bay's region —
    // without declared mullion members there is nothing honest to bound by.
    const refused = splitModuleBay(
      once,
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        bayId: secondBayId,
      },
      TEST_MEMBERS,
    ); // TEST_MEMBERS declares no mullion members
    expect(refused).toBe(once);
  });

  it("returns the same product for an unknown bayId", () => {
    const once = splitModuleBay(
      bow(),
      "m2",
      {
        type: "SPLIT_V",
        mullionSku: "MULL-60",
        offsetMm: "350.00",
      },
      TEST_MEMBERS,
    );
    const twice = splitModuleBay(
      once,
      "m2",
      {
        type: "SPLIT_H",
        mullionSku: "MULL-60",
        bayId: "no-such-bay",
      },
      TEST_MEMBERS,
    );
    // Unknown bay → no change.
    expect(twice).toBe(once);
  });
});

describe("moveModuleDivision", () => {
  it("moves the divider to a new offset", () => {
    const split = splitModuleBay(
      bow(),
      "m2",
      { type: "SPLIT_V", mullionSku: "MULL-60" },
      TEST_MEMBERS,
    );
    const divisionId = split.assembly.modules[1]!.tree.id;
    const moved = moveModuleDivision(split, "m2", divisionId, "420.00");
    expect(moved.assembly.modules[1]!.tree.split_offset_mm).toBe("420.00");
  });

  it("returns the same product for unknown ids or bays", () => {
    const product = bow();
    expect(moveModuleDivision(product, "m2", "m2-g1", "100.00")).toBe(product);
    expect(moveModuleDivision(product, "nope", "anything", "100.00")).toBe(product);
  });
});

describe("resizeModuleSeam", () => {
  it("grows the left module while shrinking the right — total holds", () => {
    const resized = resizeModuleSeam(bow(), 0, 120);
    const [m1, m2] = resized.assembly.modules;
    expect(Number(m1!.width_mm)).toBeCloseTo(820, 5);
    expect(Number(m2!.width_mm)).toBeCloseTo(580, 5);
    expect(totalModuleWidth(resized)).toBeCloseTo(2100, 5);
  });

  it("refuses drags that cross the minimum module width", () => {
    const product = bow();
    // each module is 700mm — a -560mm drag would leave 140mm on the left
    expect(resizeModuleSeam(product, 0, -560)).toBe(product);
    expect(resizeModuleSeam(product, 0, 560)).toBe(product);
    expect(resizeModuleSeam(product, 9, 10)).toBe(product);
  });
});

describe("setModuleCount", () => {
  it("grows by copying the last module and coupling", () => {
    const grown = setModuleCount(setCouplerSkuAll(bow(), "ACOPLE-60"), 4);
    expect(grown.assembly.modules).toHaveLength(4);
    expect(grown.assembly.couplings).toHaveLength(3);
    expect(grown.assembly.couplings[2]?.coupler_profile_sku).toBe("ACOPLE-60");
    expect(grown.assembly.couplings[2]?.angle_deg).toBe("15.0");
  });

  it("shrinks by trimming the tail", () => {
    const shrunk = setModuleCount(bow(), 2);
    expect(shrunk.assembly.modules.map((m) => m.id)).toEqual(["m1", "m2"]);
    expect(shrunk.assembly.couplings.map((c) => c.id)).toEqual(["c1"]);
  });
});

describe("equalizeModuleWidths", () => {
  it("preserves the total width with the last module absorbing rounding", () => {
    const uneven = setModuleWidth(bow(), "m1", "900.00");
    const total = totalModuleWidth(uneven);
    const equalized = equalizeModuleWidths(uneven);
    expect(totalModuleWidth(equalized)).toBeCloseTo(total, 5);
    const widths = equalized.assembly.modules.map((m) => Number(m.width_mm));
    expect(widths[0]).toBeCloseTo(766.67, 2);
    expect(widths[2]).toBeCloseTo(766.66, 2);
  });
});

describe("scaleModuleWidths", () => {
  it("scales so widths sum back to the requested total exactly", () => {
    const scaled = scaleModuleWidths(bow(), "2000.00");
    const widths = scaled.assembly.modules.map((module) => Number(module.width_mm));
    expect(widths.reduce((sum, width) => sum + width, 0)).toBeCloseTo(2000, 9);
    // proportional shares — largest-remainder allocation keeps the 0.00 mm sum
    expect(widths[0]).toBeCloseTo(666.67, 2);
    expect(widths[2]).toBeCloseTo(666.66, 2);
  });

  it("never produces zero-width modules on tiny totals", () => {
    const scaled = scaleModuleWidths(bow(), "0.05");
    const widths = scaled.assembly.modules.map((module) => Number(module.width_mm));
    expect(widths.reduce((sum, width) => sum + width, 0)).toBeCloseTo(0.05, 9);
    expect(widths.every((width) => width >= 0.01)).toBe(true);
    // unequal proportions still honor the positive floor for every module
    const skewed = scaleModuleWidths(
      {
        ...bow(),
        assembly: {
          ...bow().assembly,
          modules: bow().assembly.modules.map((module, index) => ({
            ...module,
            width_mm: index === 0 ? "10.00" : index === 1 ? "100.00" : "190.00",
          })),
        },
      },
      "0.03",
    );
    expect(skewed.assembly.modules.every((module) => Number(module.width_mm) >= 0.01)).toBe(true);
  });

  it("rejects totals too small to keep every module positive", () => {
    const product = bow();
    expect(scaleModuleWidths(product, "0")).toBe(product);
    expect(scaleModuleWidths(product, "abc")).toBe(product);
    expect(scaleModuleWidths(product, "0.02")).toBe(product);
  });

  it("scales the elevation envelope, not the stacked width sum", () => {
    // Door + transom share one column: widths sum 1800 but the elevation is
    // 900 wide — a 1200 request must produce a 1200 mm envelope, not 600 mm
    // of column plus a 600 mm overhang.
    const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 2100, angleDeg: 0 });
    const door = base.assembly.modules[0]!;
    const transom = wrapTreeAsProduct(
      makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 400, angleDeg: 0 }).assembly
        .modules[0]!.tree,
      "900.00",
      "400.00",
    ).assembly.modules[0]!;
    const stacked: ProductJson = {
      ...base,
      assembly: {
        modules: [door, { ...transom, id: "t1" }],
        couplings: [
          {
            id: "c1",
            modules: [door.id, "t1"],
            edges: ["top", "bottom"],
            kind: "STACKED",
            coupler_profile_sku: null,
            angle_deg: "0.00",
          },
        ],
      },
    } as ProductJson;
    const scaled = scaleModuleWidths(stacked, "1200.00");
    const layout = elevationLayoutMm(scaled);
    const envelope =
      Math.max(...layout.members.map((member) => member.x + member.w)) -
      Math.min(...layout.members.map((member) => member.x));
    expect(envelope).toBeCloseTo(1200, 2);
    expect(Number(scaled.assembly.modules[0]!.width_mm)).toBeCloseTo(1200, 2);
    expect(Number(scaled.assembly.modules[1]!.width_mm)).toBeCloseTo(1200, 2);
  });
});

describe("legacy positional couplings", () => {
  // Rows without modules/edges resolve coupling i to modules i↔i+1. Any
  // mutation that reorders modules must pin every joint to the pair it
  // actually joins — not let the saved assembly reconnect wrong units.
  function legacy(): ProductJson {
    const product = bow();
    return {
      ...product,
      assembly: {
        modules: [...product.assembly.modules],
        couplings: product.assembly.couplings.map((coupling) => ({
          id: coupling.id,
          angle_deg: coupling.angle_deg,
          coupler_profile_sku: coupling.coupler_profile_sku,
          kind: "INLINE" as const,
        })),
      },
    } as ProductJson;
  }

  it("pins joints on duplicate — the copy never hijacks an old seam", () => {
    const copied = duplicateModule(legacy(), "m1");
    const byId = new Map(copied.assembly.couplings.map((c) => [c.id, c]));
    // m1's right edge is claimed (legacy c1), so the copy lands on its left
    // at index 0 — without materialization c1 would resolve copy↔m1.
    expect(byId.get("c1")?.modules).toEqual(["m1", "m2"]);
    expect(byId.get("c1")?.edges).toEqual(["right", "left"]);
    expect(byId.get("c2")?.modules).toEqual(["m2", "m3"]);
    // The new coplanar joint names its endpoints too.
    expect(copied.assembly.couplings.at(-1)?.modules).toEqual([
      copied.assembly.modules[0]!.id,
      "m1",
    ]);
  });

  it("pins joints on prepend — addAdjacentUnit left keeps the chain", () => {
    const grown = addAdjacentUnit(legacy(), "left");
    const byId = new Map(grown.assembly.couplings.map((c) => [c.id, c]));
    expect(byId.get("c1")?.modules).toEqual(["m1", "m2"]);
    expect(byId.get("c2")?.modules).toEqual(["m2", "m3"]);
    expect(grown.assembly.couplings[0]?.modules).toEqual([grown.assembly.modules[0]!.id, "m1"]);
  });

  it("pins joints on insert between a positional seam", () => {
    const inserted = insertModuleBetween(legacy(), "c1");
    const byId = new Map(inserted.assembly.couplings.map((c) => [c.id, c]));
    const added = inserted.assembly.modules[1]!;
    // c1 keeps its id on the left↔new joint; the minted joint joins
    // new↔m2 explicitly; the untouched c2 stays on m2↔m3.
    expect(byId.get("c1")?.modules).toEqual(["m1", added.id]);
    expect(byId.get("c2")?.modules).toEqual(["m2", "m3"]);
    const minted = inserted.assembly.couplings.find(
      (c) => c.modules?.[0] === added.id && c.modules?.[1] === "m2",
    );
    expect(minted).toBeDefined();
  });

  it("reorders a conjunto — swap moves ids through every joint and column", () => {
    // Designer report: a conjunto could not reorder units (put the door at
    // the end). Swapping m1↔m2 rewires endpoints AND column order.
    const moved = swapModules(legacy(), "m1", "m2");
    expect(moved.assembly.modules.map((m) => m.id)).toEqual(["m2", "m1", "m3"]);
    const byId = new Map(moved.assembly.couplings.map((c) => [c.id, c]));
    // c1 was m1↔m2 — now joins m2↔m1 (same seam, order flipped); c2 keeps
    // joining m2↔m3 which after the move are m2's new right neighbour pair.
    expect(byId.get("c1")?.modules).toEqual(["m2", "m1"]);
    expect(byId.get("c1")?.edges).toEqual(["right", "left"]);
    expect(byId.get("c2")?.modules).toEqual(["m1", "m3"]);
    // Moving the edge member to the far end rewires both of its joints.
    const far = swapModules(legacy(), "m1", "m3");
    expect(far.assembly.modules.map((m) => m.id)).toEqual(["m3", "m2", "m1"]);
    const farById = new Map(far.assembly.couplings.map((c) => [c.id, c]));
    expect(farById.get("c1")?.modules).toEqual(["m3", "m2"]);
    expect(farById.get("c2")?.modules).toEqual(["m2", "m1"]);
    // Joints keep their declared angle/coupler through the rewire.
    expect(farById.get("c1")?.angle_deg).toBe(legacy().assembly.couplings[0]!.angle_deg);
  });

  it("names horizontal neighbours along the chain, not array neighbours", () => {
    const product = legacy();
    expect(moduleNeighbors(product, "m1")).toEqual({ left: null, right: "m2" });
    expect(moduleNeighbors(product, "m2")).toEqual({ left: "m1", right: "m3" });
    expect(moduleNeighbors(product, "m3")).toEqual({ left: "m2", right: null });
    // Stacked members report no horizontal neighbour from their stack joint.
    const stacked = addStackedUnit(product, "m2");
    const top = stacked.assembly.modules.at(-1)!.id;
    expect(moduleNeighbors(stacked, top)).toEqual({ left: null, right: null });
    expect(moduleNeighbors(stacked, "m2")).toEqual({ left: "m1", right: "m3" });
  });
});

describe("module commands", () => {
  it("sets opening type on every bay of the module tree", () => {
    const opened = setModuleOpening(bow(), "m2", "TILT_TURN_LEFT");
    expect(moduleOpening(opened.assembly.modules[1]!)).toBe("TILT_TURN_LEFT");
    expect(moduleOpening(opened.assembly.modules[0]!)).toBe("FIXED");
  });

  it("sets angle and sku on the matching coupling only", () => {
    const next = setCouplerSku(setCouplingAngle(bow(), "c2", "22.0"), "c2", "SK-9");
    expect(next.assembly.couplings[1]?.angle_deg).toBe("22.0");
    expect(next.assembly.couplings[1]?.coupler_profile_sku).toBe("SK-9");
    expect(next.assembly.couplings[0]?.coupler_profile_sku).toBeNull();
  });

  it("equalizes all coupling angles to the first", () => {
    const next = equalizeCouplingAngles(setCouplingAngle(bow(), "c1", "18.5"));
    expect(next.assembly.couplings.map((c) => c.angle_deg)).toEqual(["18.5", "18.5"]);
  });

  it("sets a shared height across modules", () => {
    const next = setAllModuleHeights(bow(), "1250.00");
    expect(next.assembly.modules.every((module) => module.height_mm === "1250.00")).toBe(true);
  });

  it("sets the commercial glass sku on the matching module only", () => {
    const glazed = setModuleGlass(bow(), "m2", "GLASS-A");
    expect(moduleGlassSku(glazed.assembly.modules[1]!)).toBe("GLASS-A");
    expect(moduleGlassSku(glazed.assembly.modules[0]!)).toBeNull();
  });

  it("picking a thickness seeds the monolithic spec only when unset", () => {
    const bare = wrapTreeAsProduct(
      { id: "g1", type: "BAY", opening_type: "FIXED" },
      "1200.00",
      "1500.00",
    );
    const picked = setModuleGlassThickness(bare, "m1", "20.00");
    const pickedBay = picked.assembly.modules[0]!.tree;
    expect(pickedBay.glass_thickness_mm).toBe("20.00");
    expect(pickedBay.glass_spec).toBe("20.00");

    const declared = wrapTreeAsProduct(
      { id: "g1", type: "BAY", opening_type: "FIXED", glass_spec: "4-16-4" },
      "1200.00",
      "1500.00",
    );
    const kept = setModuleGlassThickness(declared, "m1", "24.00");
    expect(kept.assembly.modules[0]!.tree.glass_spec).toBe("4-16-4");
  });

  it("assigns a panel sku to the matching module only", () => {
    const paneled = setModulePanel(bow(), "m2", "PANEL-70");
    expect(modulePanelSku(paneled.assembly.modules[1]!)).toBe("PANEL-70");
    expect(modulePanelSku(paneled.assembly.modules[0]!)).toBeNull();
  });

  it("clears the panel sku when the module leaves DOOR_ENTRY", () => {
    const doored = setModuleOpening(setModulePanel(bow(), "m2", "PANEL-70"), "m2", "DOOR_ENTRY");
    const fixed = setModuleOpening(doored, "m2", "FIXED");
    expect(modulePanelSku(doored.assembly.modules[1]!)).toBe("PANEL-70");
    expect(modulePanelSku(fixed.assembly.modules[1]!)).toBeNull();
  });
});
