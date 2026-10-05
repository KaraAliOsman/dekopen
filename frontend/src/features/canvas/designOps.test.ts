import { describe, expect, it } from "vitest";

import { applyDesignOp, applyDesignOps, describeDesignOp } from "./designOps";
import { makeBowProduct, totalModuleWidth } from "./productEditing";
import { resolveMembers } from "./members";

function bow(modules = 3) {
  return makeBowProduct({ moduleCount: modules, widthMm: 2100, heightMm: 1400, angleDeg: 15 });
}

describe("applyDesignOps", () => {
  it("applies a module count change", () => {
    const next = applyDesignOps(bow(3), [{ op: "set_module_count", count: 5 }]);
    expect(next.assembly.modules).toHaveLength(5);
    expect(next.assembly.couplings).toHaveLength(4);
  });

  it("scales the total width", () => {
    const next = applyDesignOps(bow(2), [{ op: "set_total_width", width_mm: "2400" }]);
    expect(totalModuleWidth(next)).toBeCloseTo(2400, 1);
  });

  it("sets an opening on a module by index", () => {
    const next = applyDesignOps(bow(2), [{ op: "set_opening", module: 1, opening: "SLIDING_2L" }]);
    const tree = next.assembly.modules[1]!.tree;
    const child = tree.children?.[0] ?? tree;
    expect(child.opening_type).toBe("SLIDING_2L");
  });

  it("sets coupling angles per index", () => {
    const next = applyDesignOps(bow(3), [
      { op: "set_coupling_angle", coupling: 0, angle_deg: "30" },
      { op: "set_coupling_angle", coupling: 1, angle_deg: "30" },
    ]);
    // Wire ops and palette runs converge on the canonical decimal form.
    expect(next.assembly.couplings[0]!.angle_deg).toBe("30.0");
    expect(next.assembly.couplings[1]!.angle_deg).toBe("30.0");
  });

  it("drops ops against missing indices instead of corrupting the product", () => {
    const product = bow(2);
    const next = applyDesignOps(product, [
      { op: "set_opening", module: 7, opening: "FIXED" },
      { op: "set_coupling_angle", coupling: 9, angle_deg: "10" },
    ]);
    expect(next).toBe(product);
  });

  it("never mutates on an unknown op", () => {
    const product = bow(2);
    expect(applyDesignOp(product, { op: "delete_all" })).toBe(product);
  });

  it("adds a unit on the left", () => {
    const next = applyDesignOps(bow(2), [{ op: "add_unit", side: "left" }]);
    expect(next.assembly.modules).toHaveLength(3);
    expect(next.assembly.couplings).toHaveLength(2);
  });

  it("keeps module and coupling ids unique across remove + regrow", () => {
    const next = applyDesignOps(bow(3), [
      { op: "remove_unit", module: 1 },
      { op: "set_module_count", count: 3 },
    ]);
    const moduleIds = next.assembly.modules.map((module) => module.id);
    const couplingIds = next.assembly.couplings.map((coupling) => coupling.id);
    expect(new Set(moduleIds).size).toBe(moduleIds.length);
    expect(new Set(couplingIds).size).toBe(couplingIds.length);
    expect(next.assembly.modules).toHaveLength(3);
  });

  it("parts expansion matches the backend's sequential per-cut ops (IA2 parity)", () => {
    // Paridad UI/IA: el wire `split_bay {parts:3}` expande dentro del reducer
    // a los mismos cortes que el validador acepta por separado — la raíz con
    // centerline absoluta (520) y el anidado con offset local (442.50), cada
    // uno direccionado por la ref sintética added_b1 como en el backend.
    const product = makeBowProduct({
      moduleCount: 1,
      widthMm: 1500,
      heightMm: 1200,
      angleDeg: 15,
    });
    const members = {
      ...resolveMembers(undefined),
      mullionV: { sku: "MULL-60", material: "PVC", faceWidthMm: 70 },
      mullionH: { sku: "MULL-60", material: "PVC", faceWidthMm: 70 },
    };
    const expanded = applyDesignOps(
      product,
      [{ op: "split_bay", axis: "V", module: "m1", parts: 3, mullion_sku: "MULL-60" }],
      undefined,
      members,
    );
    const sequential = applyDesignOps(
      product,
      [
        {
          op: "split_bay",
          axis: "V",
          module: "m1",
          bay: "m1",
          offset_mm: "520.00",
          mullion_sku: "MULL-60",
        },
        {
          op: "split_bay",
          axis: "V",
          module: "m1",
          bay: "added_b1",
          offset_mm: "442.50",
          mullion_sku: "MULL-60",
        },
      ],
      undefined,
      members,
    );
    // Misma topología y mismos offsets — los ids pueden diferir (acuñación
    // local), la geometría guardada no.
    const offsets = (root: unknown): string[] =>
      root && typeof root === "object" && "type" in root
        ? [
            ...((root as { type: string }).type.startsWith("SPLIT")
              ? [String((root as { split_offset_mm?: string }).split_offset_mm)]
              : []),
            ...(((root as { children?: unknown[] }).children ?? []).flatMap(offsets) as string[]),
          ]
        : [];
    const treeA = expanded.assembly.modules[0]!.tree;
    const treeB = sequential.assembly.modules[0]!.tree;
    expect(offsets(treeA)).toEqual(offsets(treeB));
    expect(offsets(treeA)).toEqual(["520.00", "442.50"]);
    const countBays = (node: unknown): number =>
      node && typeof node === "object" && "type" in node
        ? (node as { type: string }).type === "BAY"
          ? 1
          : ((node as { children?: unknown[] }).children ?? []).reduce(
              (acc: number, child) => acc + countBays(child),
              0,
            )
        : 0;
    expect(countBays(treeA)).toBe(3);
    expect(countBays(treeB)).toBe(3);
  });
});

describe("describeDesignOp", () => {
  it("renders human es-CL labels", () => {
    const product = bow(3);
    expect(describeDesignOp({ op: "set_module_count", count: 3 }, product)).toBe("3 módulos");
    expect(describeDesignOp({ op: "equalize_widths" }, product)).toBe("anchos iguales");
    expect(describeDesignOp({ op: "set_total_width", width_mm: "2400" }, product)).toContain(
      "2400",
    );
    expect(describeDesignOp({ op: "set_opening", module: 0, opening: "DOOR_ENTRY" }, product)).toBe(
      "módulo 1: puerta",
    );
  });
});

describe("stable domain refs", () => {
  it("addresses a module by its own id, not its slot", () => {
    const product = bow(3);
    const id = product.assembly.modules[2]!.id;
    const next = applyDesignOps(product, [
      { op: "remove_unit", module: product.assembly.modules[0]!.id },
      { op: "set_opening", module: id, opening: "AWNING" },
    ]);
    // The ref kept naming the same module after index 0 was removed — an
    // index would have silently hit a different unit.
    const target = next.assembly.modules.find((module) => module.id === id)!;
    const child = target.tree.children?.[0] ?? target.tree;
    expect(child.opening_type).toBe("AWNING");
    expect(next.assembly.modules).toHaveLength(2);
  });

  it("resolves added_m{n} to the units the sequence itself created", () => {
    const next = applyDesignOps(bow(2), [
      { op: "add_unit", side: "right", ref: "added_m1" },
      { op: "set_opening", module: "added_m1", opening: "DOOR_ENTRY" },
    ]);
    expect(next.assembly.modules).toHaveLength(3);
    const created = next.assembly.modules[2]!;
    const child = created.tree.children?.[0] ?? created.tree;
    expect(child.opening_type).toBe("DOOR_ENTRY");
  });

  it("describes mid-sequence refs with the replayed product", () => {
    const product = bow(2);
    const ops = [
      { op: "add_unit", side: "right", ref: "added_m1" },
      { op: "set_opening", module: "added_m1", opening: "AWNING" },
    ];
    expect(describeDesignOp(ops[1]!, product, ops.slice(0, 1))).toBe("módulo nueva 1: proyectante");
  });
});
