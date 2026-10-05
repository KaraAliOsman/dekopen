import { expect, it } from "vitest";

import type { DesignOptions } from "../../api/generated/models";
import { resolveMembers } from "./members";

const CATALOG: DesignOptions = {
  profiles: [
    { sku: "FRAME-70", role: "FRAME", name: "Marco 70", material: "PVC", face_width_mm: "70.00" },
    { sku: "SASH-80", role: "SASH", name: "Hoja 80", material: "PVC", face_width_mm: "80.00" },
    { sku: "MULL-70", role: "MULLION_V", name: "Mullión", material: "PVC", face_width_mm: "70.00" },
    {
      sku: "THR-30",
      role: "THRESHOLD",
      name: "Umbral",
      material: "ALUMINIUM",
      face_width_mm: "30.00",
    },
  ],
  glazing_thicknesses: ["24.00", "28.00"],
  handle_policy: null,
  hardware_kits: [],
  glass_skus: [],
  glass_products: [],
  glass_specs: [],
  coupler_skus: ["CPL-90"],
  coupler_profiles: [{ sku: "CPL-90", name: "Coplana", material: "PVC", face_width_mm: "90.00" }],
  glazing_beads: [
    { glass_thickness_mm: "24.00", bead_width_mm: "18.00", sku: "BEAD-24" },
    { glass_thickness_mm: "28.00", bead_width_mm: "15.00", sku: "BEAD-28" },
  ],
  panel_skus: [],
  panel_choices: [],
  colors: ["WHITE"],
  rebate_depth_mm: "20.00",
  sash_overlap_mm: "8.00",
  depth_mm: "70.00",
};

it("resolves member face widths and materials from the catalog", () => {
  const members = resolveMembers(CATALOG);
  expect(members.frame.faceWidthMm).toBe(70);
  expect(members.sash.faceWidthMm).toBe(80);
  expect(members.mullionV?.faceWidthMm).toBe(70);
  expect(members.mullionH).toBeNull(); // no H mullion article in this catalog
  expect(members.threshold?.material).toBe("ALUMINIUM");
  expect(members.beadFor("28.00")).toBe(15);
  expect(members.couplerFor("CPL-90")?.faceWidthMm).toBe(90);
  expect(members.rebateMm).toBe(20);
  expect(members.sashOverlapMm).toBe(8);
});

it("falls back to drawing conventions when options are missing", () => {
  const members = resolveMembers(undefined);
  expect(members.frame.faceWidthMm).toBeGreaterThan(0);
  expect(members.sash.faceWidthMm).toBeGreaterThan(0);
  expect(members.mullionV).toBeNull();
  expect(members.beadFor(null)).toBeGreaterThan(0);
  expect(members.couplerFor("CPL-90")).toBeNull();
});

it("resolves a null coupler only when the catalog offers exactly one", () => {
  const members = resolveMembers(CATALOG);
  expect(members.couplerFor(null)?.sku).toBe("CPL-90");

  const ambiguous = resolveMembers({
    ...CATALOG,
    coupler_skus: ["CPL-90", "CPL-40"],
    coupler_profiles: [
      ...CATALOG.coupler_profiles,
      { sku: "CPL-40", name: "Coplana 40", material: "PVC", face_width_mm: "40.00" },
    ],
  });
  expect(ambiguous.couplerFor(null)).toBeNull();
  expect(ambiguous.couplerFor("CPL-40")?.faceWidthMm).toBe(40);
});

it("returns the neutral bead convention for unknown thicknesses", () => {
  const members = resolveMembers(CATALOG);
  expect(members.beadFor("999.00")).toBe(18); // convention, not a catalog bead
  expect(members.beadFor("24.00")).toBe(18); // catalog match still wins
});

it("beadSpecFor returns the catalog bead member, section included", () => {
  const section = {
    source: "POLYGON" as const,
    polygon: [
      { x_mm: "0", y_mm: "0" },
      { x_mm: "12", y_mm: "0" },
      { x_mm: "12", y_mm: "10" },
      { x_mm: "0", y_mm: "10" },
    ],
    depth_mm: "10.00",
  };
  const members = resolveMembers({
    ...CATALOG,
    glazing_beads: [
      { glass_thickness_mm: "24.00", bead_width_mm: "18.00", sku: "BEAD-24", section },
      { glass_thickness_mm: "28.00", bead_width_mm: "15.00", sku: "BEAD-28" },
    ],
  });
  expect(members.beadSpecFor("24.00")?.section?.source).toBe("POLYGON");
  expect(members.beadSpecFor("24.00")?.sku).toBe("BEAD-24");
  expect(members.beadSpecFor("28.00")?.section).toBeNull();
  expect(members.beadSpecFor("999.00")).toBeNull();
  expect(members.beadSpecFor(null)).toBeNull();
});

it("carries a declared catalog section through to the member spec", () => {
  const section = {
    source: "POLYGON" as const,
    polygon: [
      { x_mm: "0", y_mm: "0" },
      { x_mm: "60", y_mm: "0" },
      { x_mm: "60", y_mm: "60" },
      { x_mm: "0", y_mm: "60" },
    ],
    depth_mm: "60.00",
  };
  const members = resolveMembers({
    ...CATALOG,
    profiles: [{ ...CATALOG.profiles[0]!, section }, ...CATALOG.profiles.slice(1)],
  });
  expect(members.frame.section?.source).toBe("POLYGON");
  expect(members.frame.section?.polygon).toHaveLength(4);
  expect(members.sash.section).toBeNull();
});

it("signature invalidates on kit contents and handle-policy changes, not on shape alone", () => {
  const base = resolveMembers({
    ...CATALOG,
    hardware_kits: [
      {
        sku: "K1",
        name: "Kit",
        opening_type: "TURN",
        min_leaf_width_mm: "400",
        max_leaf_width_mm: "1600",
        min_leaf_height_mm: "400",
        max_leaf_height_mm: "2400",
        max_leaf_weight_kg: "120",
        weight_kg: null,
        contents: [{ sku: "H", name: "hinge", qty: "3", unit: "unit", category: "HINGE" }],
      },
    ],
  });
  const same = resolveMembers({
    ...CATALOG,
    hardware_kits: [
      {
        sku: "K1",
        name: "Kit",
        opening_type: "TURN",
        min_leaf_width_mm: "400",
        max_leaf_width_mm: "1600",
        min_leaf_height_mm: "400",
        max_leaf_height_mm: "2400",
        max_leaf_weight_kg: "120",
        weight_kg: null,
        contents: [{ sku: "H", name: "hinge", qty: "3", unit: "unit", category: "HINGE" }],
      },
    ],
  });
  const moreHinges = resolveMembers({
    ...CATALOG,
    hardware_kits: [
      {
        sku: "K1",
        name: "Kit",
        opening_type: "TURN",
        min_leaf_width_mm: "400",
        max_leaf_width_mm: "1600",
        min_leaf_height_mm: "400",
        max_leaf_height_mm: "2400",
        max_leaf_weight_kg: "120",
        weight_kg: null,
        contents: [{ sku: "H", name: "hinge", qty: "4", unit: "unit", category: "HINGE" }],
      },
    ],
  });
  const withPolicy = resolveMembers({
    ...CATALOG,
    handle_policy: {
      policy_id: "p1",
      version: 1,
      slots: [],
    } as never,
  });
  expect(base.signature).toBe(same.signature);
  expect(base.signature).not.toBe(moreHinges.signature);
  expect(base.signature).not.toBe(withPolicy.signature);
});
