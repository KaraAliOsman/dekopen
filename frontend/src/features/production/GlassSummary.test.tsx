import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GlassSummary, glassSummaryCsv, type GlassPiece } from "./GlassSummary";

const glasses: GlassPiece[] = [
  {
    bay_id: "bay_1",
    width_mm: "680.00",
    height_mm: "1310.00",
    area_m2: "0.8908",
    weight_kg: "17.82",
    thickness_net_mm: "8.00",
    glass_spec: "4-16-4 Float Incoloro",
    article_sku: "GLS-441",
  },
  {
    bay_id: "bay_1",
    leaf_id: "leaf_1",
    width_mm: "680.00",
    height_mm: "1310.00",
    area_m2: "0.8908",
    weight_kg: "17.82",
    thickness_net_mm: "8.00",
    glass_spec: "4-16-4 Float Incoloro",
    article_sku: "GLS-441",
  },
  {
    bay_id: "bay_2",
    width_mm: "546.00",
    height_mm: "1176.00",
    area_m2: "0.6421",
    weight_kg: "12.84",
    thickness_net_mm: "9.00",
    glass_spec: "4.4.2-12-4 Laminado",
    article_sku: "GLS-LAM",
  },
];

describe("GlassSummary", () => {
  it("groups pieces by spec/sku/thickness, collapses equal sizes and scales by order quantity", () => {
    render(<GlassSummary glasses={glasses} polishing={[]} quantity={2} onExport={vi.fn()} />);
    expect(screen.getByText("Resumen de vidrios")).toBeTruthy();
    expect(screen.getByText("4-16-4 Float Incoloro")).toBeTruthy();
    expect(screen.getByText("4.4.2-12-4 Laminado")).toBeTruthy();
    // two identical panes collapse into one dims row, order qty 2 → 4
    expect(screen.getByText("680×1310 mm")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    // exact decimal sums: 2×0.8908=1.7816 → ×2 units = 3.5632; total 4.8474
    expect(screen.getByText("3.5632 m²")).toBeTruthy();
    expect(screen.getByText("4.8474 m²")).toBeTruthy();
    // weight 17.82*2*2 + 12.84*2 = 96.96
    expect(screen.getByText("96.96 kg")).toBeTruthy();
  });

  it("shows the sealed edge polishing per pane and exports a deterministic CSV", () => {
    const onExport = vi.fn();
    render(
      <GlassSummary
        glasses={glasses}
        polishing={[
          { bay_id: "bay_1", edges: { top: true, bottom: true } },
          { bay_id: "bay_1", leaf_id: "leaf_1", edges: { left: true } },
        ]}
        quantity={3}
        onExport={onExport}
      />,
    );
    const cells = screen.getAllByText(/^(S·I|Z)$/);
    expect(cells.length).toBe(2);
    fireEvent.click(screen.getByText("Exportar vidrios (CSV)"));
    expect(onExport).toHaveBeenCalledTimes(1);
    const groups = onExport.mock.calls[0]![0];
    const csv = glassSummaryCsv(groups, 3);
    expect(csv.startsWith("\uFEFF")).toBe(true); // BOM for Excel/es-CL
    const lines = csv.split("\n");
    expect(lines[0]).toContain("Composición");
    const polished = lines.find((line) => line.includes("S·I"));
    // per-row totals: pane count 1 → ×3 units, area 0.8908×3, weight 17.82×3
    expect(polished).toContain(";3;2.6724;53.46");
    const totals = lines[lines.length - 1]!;
    expect(totals).toContain("Totales");
    expect(totals).toContain(";9;7.2711;145.44"); // 3+3+3 panes, (1.7816+0.6421)*3, (17.82*2+12.84)*3
  });
});
