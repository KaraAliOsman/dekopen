import { describe, expect, it } from "vitest";

import type { DesignOptions, PlanGeometry } from "../../api/generated/models";
import type { ProductJson } from "./productEditing";
import { makeBowProduct, wrapTreeAsProduct } from "./productEditing";
import type { IntentNode } from "./intentEditing";
import { resolveMembers } from "./members";
import { buildScene3D, type BoxSolid, type ShapeSolid } from "./Product3DScene";

const members = resolveMembers(undefined);

function optionsWithMullion(): DesignOptions {
  return {
    profiles: [
      {
        role: "MULLION_V",
        sku: "MV-1",
        material: "PVC",
        face_width_mm: "70.00",
        section: null,
      },
      {
        role: "FRAME",
        sku: "FR-1",
        material: "PVC",
        face_width_mm: "60.00",
        section: null,
      },
    ],
  } as DesignOptions;
}

function splitModule(offsetMm = 450): IntentNode {
  return {
    id: "split",
    type: "SPLIT_V",
    split_offset_mm: offsetMm.toFixed(2),
    children: [
      { id: "b1", type: "BAY", opening_type: "FIXED", glass_thickness_mm: "4.00" },
      { id: "b2", type: "BAY", opening_type: "TURN_LEFT", glass_thickness_mm: "4.00" },
    ],
  };
}

describe("buildScene3D", () => {
  it("builds a frame ring plus a glass leaf for a fixed module", () => {
    const product = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1400, angleDeg: 0 });
    const scene = buildScene3D(product, members);
    expect(scene.modules).toHaveLength(1);
    const module = scene.modules[0]!;
    const frame = module.solids.filter((solid) => solid.surface === "frame") as BoxSolid[];
    expect(frame).toHaveLength(4);
    expect(frame.every((solid) => solid.owner === module.moduleId)).toBe(true);
    const glass = module.solids.filter((solid) => solid.surface === "glass") as BoxSolid[];
    expect(glass).toHaveLength(1);
    // leaf solids own the composite selection id the canvas uses
    expect(glass[0]!.owner).toMatch(/^m1\//);
    expect(module.position).toEqual([0, 0, 0]);
    expect(module.rotationY).toBe(0);
    expect(scene.radius).toBeGreaterThan(0);
  });

  it("emits a divider bar and per-leaf solids for a split module", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1400, angleDeg: 0 });
    const module = { ...base.assembly.modules[0]!, tree: splitModule() };
    const product = {
      ...base,
      assembly: { modules: [module], couplings: [] },
    } as ProductJson;
    const scene = buildScene3D(product, resolveMembers(optionsWithMullion()));
    const solids = scene.modules[0]!.solids;
    const mullions = solids.filter((solid) => solid.surface === "mullion") as BoxSolid[];
    expect(mullions).toHaveLength(1);
    expect(mullions[0]!.size[0]).toBeCloseTo(70, 5);
    // fixed leaf → glass only; operable leaf → sash ring + glass
    const sash = solids.filter((solid) => solid.surface === "sash");
    expect(sash).toHaveLength(4);
    const glass = solids.filter((solid) => solid.surface === "glass");
    expect(glass).toHaveLength(2);
  });

  it("places modules along their plan headings", () => {
    const product = makeBowProduct({ moduleCount: 2, widthMm: 1400, heightMm: 1400, angleDeg: 15 });
    const plan: PlanGeometry = {
      front_chain: [],
      couplings: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "1400",
      height_mm: "60",
      modules: [
        {
          module_id: "m1",
          corners: [
            { x_mm: "0", y_mm: "0" },
            { x_mm: "700", y_mm: "0" },
            { x_mm: "700", y_mm: "-60" },
            { x_mm: "0", y_mm: "-60" },
          ],
        },
        {
          module_id: "m2",
          corners: [
            { x_mm: "700", y_mm: "0" },
            { x_mm: "1376.09", y_mm: "181.16" },
            { x_mm: "1360.57", y_mm: "239.12" },
            { x_mm: "684.48", y_mm: "57.96" },
          ],
        },
      ],
    };
    const scene = buildScene3D(product, members, plan);
    const [first, second] = scene.modules;
    expect(first!.position[0]).toBeCloseTo(0, 5);
    expect(first!.position[1]).toBeCloseTo(0, 5);
    expect(first!.position[2]).toBeCloseTo(0, 5);
    expect(first!.rotationY).toBeCloseTo(0, 5);
    expect(second!.position[0]).toBeCloseTo(700, 5);
    expect(second!.position[1]).toBeCloseTo(0, 5);
    expect(second!.position[2]).toBeCloseTo(0, 5);
    expect(second!.rotationY).toBeCloseTo((15 * Math.PI) / 180, 3);
    // module depth comes from the plan back edge, not a constant
    const depth = Math.hypot(684.48 - 700, 57.96 - 0);
    const box = second!.solids.find((solid) => solid.kind === "box") as BoxSolid;
    expect(box.size[2]).toBeCloseTo(depth, 0);
  });

  it("extrudes the real contour outline for shaped modules", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 1200, heightMm: 1400, angleDeg: 0 });
    const module = {
      ...base.assembly.modules[0]!,
      contour: {
        vertices: [
          { x_mm: "0", y_mm: "0" },
          { x_mm: "1200", y_mm: "0" },
          { x_mm: "1200", y_mm: "1400" },
          { x_mm: "0", y_mm: "900" },
        ],
        bulges: [null, null, null, null],
      },
    };
    const product = { ...base, assembly: { modules: [module], couplings: [] } } as ProductJson;
    const scene = buildScene3D(product, members);
    const shapes = scene.modules[0]!.solids.filter(
      (solid) => solid.kind === "shape",
    ) as ShapeSolid[];
    const frame = shapes.find((solid) => solid.surface === "frame")!;
    expect(frame.outline).toHaveLength(4);
    expect(frame.holes).toHaveLength(1);
    expect(frame.owner).toBe(module.id);
    // the glazing conforms to the contoured opening — never a rectangle
    // that could overhang the sloped top edge
    const glass = shapes.find((solid) => solid.surface === "glass")!;
    expect(glass.outline).toHaveLength(4);
    expect(Math.max(...glass.outline.map(([, y]) => y))).toBeLessThan(1400);
    expect(glass.owner).toMatch(/^m1\//);
    expect(glass.z0).toBeGreaterThan(0);
    // and like the front view, no bay tree is drawn inside a contour
    expect(scene.modules[0]!.solids.some((solid) => solid.surface === "mullion")).toBe(false);
  });

  it("renders frameless modules as pane + declared supports", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1200, angleDeg: 0 });
    const module = {
      ...base.assembly.modules[0]!,
      frameless: {
        supports: [
          { kind: "CHANNEL" as const, edge: "bottom" as const, article_sku: "CH-1", qty: 1 },
        ],
        fittings: [],
      },
    };
    const product = { ...base, assembly: { modules: [module], couplings: [] } } as ProductJson;
    const scene = buildScene3D(product, members);
    const solids = scene.modules[0]!.solids;
    expect(solids.filter((solid) => solid.surface === "glass")).toHaveLength(1);
    expect(solids.filter((solid) => solid.surface === "support")).toHaveLength(1);
    expect(solids.some((solid) => solid.surface === "frame")).toBe(false);
  });

  it("emits a stack coupler bar at the member's sill line", () => {
    const door = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 2100, angleDeg: 0 });
    const transom = wrapTreeAsProduct(
      makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 400, angleDeg: 0 }).assembly
        .modules[0]!.tree,
      "900.00",
      "400.00",
    ).assembly.modules[0]!;
    const product = {
      ...door,
      assembly: {
        modules: [door.assembly.modules[0]!, { ...transom, id: "t1" }],
        couplings: [
          {
            id: "c1",
            modules: [door.assembly.modules[0]!.id, "t1"],
            edges: ["top", "bottom"],
            kind: "STACKED" as const,
            coupler_profile_sku: null,
            angle_deg: "0.00",
          },
        ],
      },
    } as ProductJson;
    const scene = buildScene3D(product, members);
    // the bar lives in the member's local frame, centred on its sill line
    const memberScene = scene.modules.find((item) => item.moduleId === "t1")!;
    const coupler = memberScene.solids.find((solid) => solid.owner === "c1") as BoxSolid;
    expect(coupler).toBeDefined();
    expect(coupler.kind).toBe("box");
    expect(coupler.center[1]).toBeCloseTo(0, 5);
    expect(memberScene.position[1]).toBeCloseTo(2100, 5);
  });

  it("keeps positional inline couplers visible as plan prisms", () => {
    const product = makeBowProduct({ moduleCount: 2, widthMm: 1400, heightMm: 1400, angleDeg: 15 });
    const plan: PlanGeometry = {
      front_chain: [],
      modules: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "1400",
      height_mm: "60",
      couplings: [
        {
          coupling_id: "c1",
          polygon: [
            { x_mm: "700", y_mm: "0" },
            { x_mm: "700", y_mm: "-60" },
            { x_mm: "760", y_mm: "40" },
          ],
        },
      ],
    };
    const scene = buildScene3D(product, members, plan);
    const prism = scene.couplers.find((solid) => solid.owner === "c1");
    expect(prism).toBeDefined();
    expect(prism?.kind).toBe("prism");
  });

  it("centres a narrower stacked member inside its root's plan footprint", () => {
    const door = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 2100, angleDeg: 0 });
    const transom = wrapTreeAsProduct(
      makeBowProduct({ moduleCount: 1, widthMm: 500, heightMm: 400, angleDeg: 0 }).assembly
        .modules[0]!.tree,
      "500.00",
      "400.00",
    ).assembly.modules[0]!;
    const product = {
      ...door,
      assembly: {
        modules: [door.assembly.modules[0]!, { ...transom, id: "t1" }],
        couplings: [
          {
            id: "c1",
            modules: [door.assembly.modules[0]!.id, "t1"],
            edges: ["top", "bottom"],
            kind: "STACKED" as const,
            coupler_profile_sku: null,
            angle_deg: "0.00",
          },
        ],
      },
    } as ProductJson;
    const plan: PlanGeometry = {
      front_chain: [],
      couplings: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "900",
      height_mm: "60",
      modules: [
        {
          module_id: "m1",
          corners: [
            { x_mm: "0", y_mm: "0" },
            { x_mm: "900", y_mm: "0" },
            { x_mm: "900", y_mm: "-60" },
            { x_mm: "0", y_mm: "-60" },
          ],
        },
        {
          module_id: "t1",
          corners: [
            { x_mm: "0", y_mm: "0" },
            { x_mm: "900", y_mm: "0" },
            { x_mm: "900", y_mm: "-60" },
            { x_mm: "0", y_mm: "-60" },
          ],
        },
      ],
    };
    const scene = buildScene3D(product, members, plan);
    const member = scene.modules.find((item) => item.moduleId === "t1")!;
    // (900 − 500)/2 = 200 mm inset along the column heading
    expect(member.position[0]).toBeCloseTo(200, 5);
  });

  it("walks the bay tree inside the frame aperture, not the outer rect", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1400, angleDeg: 0 });
    const module = { ...base.assembly.modules[0]!, tree: splitModule(450) };
    const product = {
      ...base,
      assembly: { modules: [module], couplings: [] },
    } as ProductJson;
    const frameT = 60;
    const scene = buildScene3D(product, resolveMembers(optionsWithMullion()));
    const solids = scene.modules[0]!.solids;
    const mullion = solids.find((solid) => solid.surface === "mullion") as BoxSolid;
    // the divider sits inside the frame opening (450 mm from the module edge)
    expect(mullion.center[0]).toBeCloseTo(450, 0);
    // glass stays inside the aperture: x ≥ frameT + bead, never beneath the frame
    for (const glass of solids.filter((solid) => solid.surface === "glass") as BoxSolid[]) {
      expect(glass.center[0] - glass.size[0] / 2).toBeGreaterThanOrEqual(frameT);
      expect(glass.center[1] - glass.size[1] / 2).toBeGreaterThanOrEqual(frameT);
    }
  });

  it("glazes fixed sliding panels directly while moving panels keep sashes", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 1200, heightMm: 1400, angleDeg: 0 });
    const bay: IntentNode = {
      id: "b1",
      type: "BAY",
      opening_type: "SLIDING",
      glass_thickness_mm: "4.00",
      sliding_layout: {
        tracks: 2,
        panels: [
          { slot: "S1", kind: "FIXED", track: null },
          { slot: "S2", kind: "MOVING", track: 1 },
        ],
      },
    };
    const module = {
      ...base.assembly.modules[0]!,
      tree: { id: "r", type: "ROOT" as const, children: [bay] },
    };
    const product = {
      ...base,
      assembly: { modules: [module], couplings: [] },
    } as ProductJson;
    const scene = buildScene3D(product, members);
    const solids = scene.modules[0]!.solids;
    // exactly one sash ring (4 bars) for the single MOVING panel
    expect(solids.filter((solid) => solid.surface === "sash")).toHaveLength(4);
    expect(solids.filter((solid) => solid.surface === "glass")).toHaveLength(2);
  });

  it("overlaps moving sliding leaves by the meeting-stile interlock", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 1200, heightMm: 1400, angleDeg: 0 });
    const bay: IntentNode = {
      id: "b1",
      type: "BAY",
      opening_type: "SLIDING",
      glass_thickness_mm: "4.00",
      sliding_layout: {
        tracks: 2,
        panels: [
          { slot: "S1", kind: "MOVING", track: 0 },
          { slot: "S2", kind: "MOVING", track: 1 },
        ],
      },
    };
    const module = {
      ...base.assembly.modules[0]!,
      tree: { id: "r", type: "ROOT" as const, children: [bay] },
    };
    const product = {
      ...base,
      assembly: { modules: [module], couplings: [] },
    } as ProductJson;
    const scene = buildScene3D(product, members);
    const solids = scene.modules[0]!.solids;
    const sash = solids.filter((solid) => solid.surface === "sash") as BoxSolid[];
    // two leaves × four bars, like the front view
    expect(sash).toHaveLength(8);
    // aperture 60..1140 → pitch 540, leaf 540+72: leaf0 spans 60..672 and
    // leaf1 spans 528..1140, so the meeting stiles overlap in (528, 672)
    const verticals = sash
      .filter((solid) => solid.size[1] > solid.size[0])
      .map((solid) => solid.center[0])
      .sort((a, b) => a - b);
    expect(verticals).toHaveLength(4);
    expect(verticals[0]).toBeCloseTo(96, 5);
    expect(verticals[1]).toBeCloseTo(564, 5);
    expect(verticals[2]).toBeCloseTo(636, 5);
    expect(verticals[3]).toBeCloseTo(1104, 5);
  });

  it("opens a two-leaf slider by sliding one leaf over the other", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 1200, heightMm: 1400, angleDeg: 0 });
    const bay: IntentNode = {
      id: "b1",
      type: "BAY",
      opening_type: "SLIDING",
      glass_thickness_mm: "4.00",
      sliding_layout: {
        tracks: 2,
        panels: [
          { slot: "S1", kind: "MOVING", track: 0 },
          { slot: "S2", kind: "MOVING", track: 1 },
        ],
      },
    };
    const module = {
      ...base.assembly.modules[0]!,
      tree: { id: "r", type: "ROOT" as const, children: [bay] },
    };
    const product = {
      ...base,
      assembly: { modules: [module], couplings: [] },
    } as ProductJson;
    const scene = buildScene3D(product, members);
    // Both leaves translating swaps their slots and reveals no aperture;
    // only the inner-rail leaf carries a slide motion (one pitch over).
    const slides = scene.modules[0]!.leaves.filter((leaf) => leaf.kind === "slide");
    expect(slides).toHaveLength(1);
    expect(slides[0]!.leafId).toBe("b1:0");
    // leaf0 (60..672, leafW 612) slides right until its edge meets the bay
    // edge at 1140 — travel 468 stacks it on leaf1's slot, opening the
    // left half of the aperture.
    expect(slides[0]!.travel).toBeCloseTo(468, 5);
  });

  it("wraps an operable panel door's infill in a sash", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 2100, angleDeg: 0 });
    const bay: IntentNode = {
      id: "b1",
      type: "BAY",
      opening_type: "DOOR_ENTRY",
      panel_article_sku: "P-1",
    };
    const module = {
      ...base.assembly.modules[0]!,
      tree: { id: "r", type: "ROOT" as const, children: [bay] },
    };
    const product = {
      ...base,
      assembly: { modules: [module], couplings: [] },
    } as ProductJson;
    const scene = buildScene3D(product, members);
    const solids = scene.modules[0]!.solids;
    expect(solids.filter((solid) => solid.surface === "sash")).toHaveLength(4);
    const panels = solids.filter((solid) => solid.surface === "panel") as BoxSolid[];
    expect(panels).toHaveLength(1);
    // the slab is inset by the sash face — the sash overlaps the aperture
    // by 10, so its left edge is 50 and the panel's left edge lands at 122
    expect(panels[0]!.center[0] - panels[0]!.size[0] / 2).toBeCloseTo(122, 5);
  });

  it("extrudes the frameless pane at the declared glass thickness", () => {
    const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1200, angleDeg: 0 });
    const module = {
      ...base.assembly.modules[0]!,
      frameless: { supports: [], fittings: [] },
    };
    const product = { ...base, assembly: { modules: [module], couplings: [] } } as ProductJson;
    const scene = buildScene3D(product, members);
    const glass = scene.modules[0]!.solids.find((solid) => solid.surface === "glass") as BoxSolid;
    // the primary bay declares 4 mm glass — the pane is 4 mm thick,
    // centred in the 60 mm module depth (z spans 28..32)
    expect(glass.size[2]).toBeCloseTo(4, 5);
    expect(glass.center[2]).toBeCloseTo(30, 5);
  });

  it("raises inline couplers to the taller stacked column top", () => {
    const door = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 2100, angleDeg: 0 });
    const transom = wrapTreeAsProduct(
      makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 400, angleDeg: 0 }).assembly
        .modules[0]!.tree,
      "900.00",
      "400.00",
    ).assembly.modules[0]!;
    const window_ = makeBowProduct({
      moduleCount: 1,
      widthMm: 900,
      heightMm: 2500,
      angleDeg: 0,
    }).assembly.modules[0]!;
    const product = {
      ...door,
      assembly: {
        modules: [door.assembly.modules[0]!, { ...transom, id: "t1" }, { ...window_, id: "w2" }],
        couplings: [
          {
            id: "c1",
            modules: [door.assembly.modules[0]!.id, "t1"],
            edges: ["top", "bottom"],
            kind: "STACKED" as const,
            coupler_profile_sku: null,
            angle_deg: "0.00",
          },
          {
            id: "c2",
            modules: [door.assembly.modules[0]!.id, "w2"],
            edges: ["right", "left"],
            kind: "INLINE" as const,
            coupler_profile_sku: null,
            angle_deg: "0.00",
          },
        ],
      },
    } as ProductJson;
    const plan: PlanGeometry = {
      front_chain: [],
      modules: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "1800",
      height_mm: "60",
      couplings: [
        {
          coupling_id: "c2",
          polygon: [
            { x_mm: "900", y_mm: "0" },
            { x_mm: "900", y_mm: "-60" },
            { x_mm: "930", y_mm: "0" },
          ],
        },
      ],
    };
    const scene = buildScene3D(product, members, plan);
    const prism = scene.couplers.find((solid) => solid.owner === "c2");
    expect(prism?.kind).toBe("prism");
    // the door's column top includes its 400 mm transom → 2500, not 2100
    if (prism?.kind === "prism") expect(prism.y1).toBeCloseTo(2500, 5);
  });

  it("draws a straight inline coupler as a bar on the seam", () => {
    const product = makeBowProduct({ moduleCount: 2, widthMm: 900, heightMm: 1400, angleDeg: 0 });
    const productWithCoupling = {
      ...product,
      assembly: {
        modules: product.assembly.modules,
        couplings: [
          {
            id: "c1",
            modules: [product.assembly.modules[0]!.id, product.assembly.modules[1]!.id],
            edges: ["right", "left"],
            kind: "INLINE" as const,
            coupler_profile_sku: null,
            angle_deg: "0.00",
          },
        ],
      },
    } as ProductJson;
    const plan: PlanGeometry = {
      front_chain: [],
      modules: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "1800",
      height_mm: "60",
      couplings: [
        {
          coupling_id: "c1",
          // a 0° joint's plan triangle degenerates to zero area
          polygon: [
            { x_mm: "900", y_mm: "0" },
            { x_mm: "900", y_mm: "-60" },
            { x_mm: "900", y_mm: "-60" },
          ],
        },
      ],
    };
    const scene = buildScene3D(productWithCoupling, members, plan);
    const coupler = scene.couplers.find((solid) => solid.owner === "c1") as BoxSolid;
    expect(coupler).toBeDefined();
    expect(coupler.kind).toBe("box");
    // the bar sits on the column seam (two 450 mm columns → x=450), full
    // height and module depth
    expect(coupler.center[0]).toBeCloseTo(450, 5);
    expect(coupler.size[1]).toBeCloseTo(1400, 5);
    expect(coupler.size[2]).toBeCloseTo(60, 5);
  });

  it("keeps a shallow-angle coupler as a prism", () => {
    const product = makeBowProduct({
      moduleCount: 2,
      widthMm: 900,
      heightMm: 1400,
      angleDeg: 0.01,
    });
    const productWithCoupling = {
      ...product,
      assembly: {
        modules: product.assembly.modules,
        couplings: [
          {
            id: "c1",
            modules: [product.assembly.modules[0]!.id, product.assembly.modules[1]!.id],
            edges: ["right", "left"],
            kind: "INLINE" as const,
            coupler_profile_sku: null,
            angle_deg: "0.01",
          },
        ],
      },
    } as ProductJson;
    const plan: PlanGeometry = {
      front_chain: [],
      modules: [],
      min_x_mm: "0",
      min_y_mm: "0",
      width_mm: "1800",
      height_mm: "60",
      couplings: [
        {
          coupling_id: "c1",
          // 0.01° still yields three distinct quantized points (~0.31 mm²)
          polygon: [
            { x_mm: "450", y_mm: "0" },
            { x_mm: "450", y_mm: "-60" },
            { x_mm: "450.01", y_mm: "-60" },
          ],
        },
      ],
    };
    const scene = buildScene3D(productWithCoupling, members, plan);
    const coupler = scene.couplers.find((solid) => solid.owner === "c1");
    expect(coupler?.kind).toBe("prism");
  });

  describe("§05 physical details", () => {
    function frameSectionOptions(): DesignOptions {
      return {
        profiles: [
          {
            role: "FRAME",
            sku: "FR-SEC",
            material: "PVC",
            face_width_mm: "60.00",
            section: {
              source: "POLYGON",
              depth_mm: "70.00",
              polygon: [
                { x_mm: "0", y_mm: "0" },
                { x_mm: "60", y_mm: "0" },
                { x_mm: "60", y_mm: "70" },
                { x_mm: "0", y_mm: "70" },
              ],
            },
          },
        ],
      } as DesignOptions;
    }

    it("extrudes a declared frame section as profile solids, not boxes", () => {
      const product = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1400, angleDeg: 0 });
      const scene = buildScene3D(product, resolveMembers(frameSectionOptions()));
      const profiles = scene.modules[0]!.solids.filter(
        (solid) => solid.kind === "profile" && solid.surface === "frame",
      );
      // the ring emits one run per side — posts on y, rails on x
      expect(profiles).toHaveLength(4);
      expect(profiles.every((solid) => solid.kind === "profile" && !solid.approximate)).toBe(true);
      const post = profiles[0]!;
      expect(post.kind).toBe("profile");
      if (post.kind === "profile") {
        expect(post.axis).toBe("y");
        expect(post.a1 - post.a0).toBeCloseTo(1400, 5);
        expect(post.outline.length).toBe(4);
      }
    });

    it("keeps undeclared members approximate boxes", () => {
      const product = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1400, angleDeg: 0 });
      const scene = buildScene3D(product, members);
      const frames = scene.modules[0]!.solids.filter(
        (solid) => solid.surface === "frame",
      ) as BoxSolid[];
      expect(frames).toHaveLength(4);
      expect(frames.every((solid) => solid.approximate === true)).toBe(true);
    });

    it("emits bead and gasket solids around a fixed pane", () => {
      const product = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1400, angleDeg: 0 });
      const scene = buildScene3D(product, members);
      const solids = scene.modules[0]!.solids;
      expect(solids.filter((solid) => solid.surface === "bead").length).toBe(4);
      expect(solids.filter((solid) => solid.surface === "gasket").length).toBe(4);
    });

    it("emits hinges and a handle on an operable leaf", () => {
      const base = makeBowProduct({ moduleCount: 1, widthMm: 900, heightMm: 1400, angleDeg: 0 });
      const module = {
        ...base.assembly.modules[0]!,
        tree: { id: "b1", type: "BAY", opening_type: "TURN_LEFT", glass_thickness_mm: "4.00" },
      } as (typeof base.assembly.modules)[number];
      const product = { ...base, assembly: { modules: [module], couplings: [] } } as ProductJson;
      const scene = buildScene3D(product, members);
      const solids = scene.modules[0]!.solids;
      expect(solids.filter((solid) => solid.surface === "hinge").length).toBe(2);
      expect(solids.filter((solid) => solid.surface === "handle").length).toBe(3);
    });

    it("emits one rail per declared sliding track", () => {
      const base = makeBowProduct({ moduleCount: 1, widthMm: 1800, heightMm: 1400, angleDeg: 0 });
      const module = {
        ...base.assembly.modules[0]!,
        tree: {
          id: "b1",
          type: "BAY",
          opening_type: "SLIDING_2L",
          glass_thickness_mm: "4.00",
        },
      } as (typeof base.assembly.modules)[number];
      const product = { ...base, assembly: { modules: [module], couplings: [] } } as ProductJson;
      const scene = buildScene3D(product, members);
      const tracks = scene.modules[0]!.solids.filter((solid) => solid.surface === "track");
      expect(tracks).toHaveLength(2);
    });
  });
});
