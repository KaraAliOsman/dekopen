import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CutPlanView, type WorkOrderOptimization } from "./CutPlanView";

const optimization: WorkOrderOptimization = {
  schema: "work_order_optimization_v1",
  color: "BLANCO",
  units: 1,
  optimized_at: "2026-09-24T10:00:00Z",
  bars: {
    workshop_cut_plan: [
      {
        bar_index: 1,
        commercial_sku: "MARCO-60",
        material: "PVC",
        color: "BLANCO",
        stock_length_mm: "6000",
        head_trim_mm: "10",
        tail_trim_mm: "10",
        kerf_mm: "5",
        remainder_mm: "950",
        waste_mm: "950",
        yield_pct: "82.50",
        cuts: [
          {
            piece_id: "M-01",
            source_kind: "PROFILE",
            workshop_sku: "M-60",
            material: "PVC",
            color: "BLANCO",
            length_mm: "2000",
            source_position_id: "pos-aaaa-0001",
            bay_id: "bay-1",
            leaf_id: null,
            role: "FRAME",
            unit_index: 1,
            angle_left: "45",
            angle_right: "45",
            sequence: 1,
          },
          {
            piece_id: "M-02",
            source_kind: "PROFILE",
            workshop_sku: "M-60",
            material: "PVC",
            color: "BLANCO",
            length_mm: "3035",
            source_position_id: "pos-aaaa-0001",
            bay_id: "bay-1",
            leaf_id: null,
            role: "FRAME",
            unit_index: 1,
            angle_left: "45",
            angle_right: "45",
            sequence: 2,
          },
        ],
      },
      {
        bar_index: 2,
        commercial_sku: "HOJA-60",
        material: "PVC",
        color: "BLANCO",
        stock_length_mm: "6000",
        head_trim_mm: "10",
        tail_trim_mm: "10",
        kerf_mm: "5",
        remainder_mm: "4000",
        waste_mm: "4000",
        yield_pct: "32.00",
        cuts: [
          {
            piece_id: "H-01",
            source_kind: "PROFILE",
            workshop_sku: "H-60",
            material: "PVC",
            color: "BLANCO",
            length_mm: "1990",
            source_position_id: "pos-aaaa-0001",
            bay_id: "bay-1",
            leaf_id: "leaf-1",
            role: "SASH",
            unit_index: 1,
            sequence: 1,
          },
        ],
      },
    ],
  },
  sheets: [
    {
      sheet_index: 1,
      purchasing_sku: "VID-4MM",
      sheet_width_mm: "3210",
      sheet_height_mm: "2250",
      yield_pct: "44.0",
      placements: [
        {
          piece_id: "V-01",
          workshop_sku: "VID-4MM",
          x_mm: "0",
          y_mm: "0",
          width_mm: "1400",
          height_mm: "1000",
          rotated: false,
          source_position_id: "pos-aaaa-0001",
          bay_id: "bay-1",
          leaf_id: null,
          unit_index: 1,
          sequence: 1,
        },
        {
          piece_id: "V-02",
          workshop_sku: "VID-4MM",
          x_mm: "1400",
          y_mm: "0",
          width_mm: "1400",
          height_mm: "1000",
          rotated: true,
          source_position_id: "pos-aaaa-0002",
          bay_id: "bay-2",
          leaf_id: null,
          unit_index: 1,
          sequence: 2,
        },
      ],
    },
  ],
};

describe("CutPlanView", () => {
  it("renders a visual bar per cut plan and a sheet per layout", () => {
    const { container } = render(<CutPlanView optimization={optimization} />);
    expect(container.querySelectorAll(".cutplan-bar")).toHaveLength(2);
    expect(container.querySelectorAll(".cutplan-sheet")).toHaveLength(1);
    // two pieces on bar 1 + one on bar 2 + two placements on the sheet
    expect(container.querySelectorAll(".cutplan-cut")).toHaveLength(3);
    expect(container.querySelectorAll(".cutplan-nest")).toHaveLength(2);
    // remainder starts after the trailing kerf, matching the engine's
    // process_consumed_mm: head 10 + (2000+5) + (3035+5) = 5055 of 6000.
    const remainder = container.querySelector(".cutplan-remainder") as Element;
    expect(Number(remainder.getAttribute("x"))).toBeCloseTo((5055 / 6000) * 1000);
  });

  it("clicking a piece shows its detail and cross-highlights the member", () => {
    const { container } = render(<CutPlanView optimization={optimization} />);
    const first = container.querySelectorAll(".cutplan-cut")[0] as Element;
    fireEvent.click(first);
    const aside = container.querySelector(".cutplan-detail") as Element;
    expect(aside.textContent).toContain("M-60 · B1-1");
    expect(aside.textContent).toContain("Marco");
    expect(aside.textContent).toContain("2000 mm");
    // member key = interchangeable spec (location+role+sku+measure+angles)
    // — M-01 (2000 mm) and M-02 (3035 mm) are different physical pieces.
    const members = container.querySelectorAll(".is-member");
    expect(members.length).toBe(1);
    expect(first.classList.contains("is-selected")).toBe(true);
  });

  it("selecting a different member moves the highlight", () => {
    const { container } = render(<CutPlanView optimization={optimization} />);
    const nest = container.querySelectorAll(".cutplan-nest")[1] as Element;
    fireEvent.click(nest);
    const members = container.querySelectorAll(".is-member");
    expect(members.length).toBe(1);
    expect(nest.classList.contains("is-selected")).toBe(true);
    const aside = container.querySelector(".cutplan-detail") as Element;
    expect(aside.textContent).toContain("VID-4MM · S1-2");
    expect(aside.textContent).toContain("1400×1000");
  });
});
