// §06-G — the import review flow: upload → pick outline → confirm scale →
// the polygon lands on the section editor as DXF_REFERENCE evidence.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { t } from "../../i18n/es-CL";
import { SectionImportPanel } from "./SectionImportPanel";

const RESULT = {
  document_path: "section-imports/org-1/abc/frame.dxf",
  format: "dxf",
  parser_version: "section-import/1.0",
  mm_per_unit: "1",
  warnings: [],
  candidates: [
    {
      index: 0,
      tag: "LWPOLYLINE#1",
      points: [
        ["0.0", "0.0"],
        ["60.0", "0.0"],
        ["60.0", "70.0"],
        ["0.0", "70.0"],
      ],
      area: "4200.00",
    },
    {
      index: 1,
      tag: "LWPOLYLINE#2",
      points: [
        ["0.0", "0.0"],
        ["20.0", "0.0"],
        ["20.0", "20.0"],
        ["0.0", "20.0"],
      ],
      area: "400.00",
    },
  ],
};

function fileInput(container: HTMLElement): HTMLInputElement {
  return container.querySelector("input[type=file]")!;
}

describe("SectionImportPanel", () => {
  it("uploads, picks the outline, scales and applies DXF_REFERENCE evidence", async () => {
    const api = { sectionImport: vi.fn(async () => RESULT) };
    const onApply = vi.fn();
    const { container } = render(
      <SectionImportPanel api={api as never} onApply={onApply} onClose={() => {}} />,
    );
    fireEvent.change(fileInput(container), {
      target: { files: [new File(["dxf-bytes"], "frame.dxf", { type: "application/dxf" })] },
    });
    await waitFor(() => expect(api.sectionImport).toHaveBeenCalled());

    // Pick the smaller outline explicitly (nothing auto-picks with 2+).
    fireEvent.click(screen.getByRole("button", { name: /LWPOLYLINE#2/ }));
    fireEvent.change(screen.getByLabelText(t("catalog.sectionImport.scale") as never), {
      target: { value: "2" },
    });
    await waitFor(() => expect(screen.getByText(/40\.0 × 40\.0 mm/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: t("catalog.sectionImport.apply") }));

    expect(onApply).toHaveBeenCalledWith({
      drawingRef: RESULT.document_path,
      vertices: [
        { x_mm: "0.00", y_mm: "0.00" },
        { x_mm: "40.00", y_mm: "0.00" },
        { x_mm: "40.00", y_mm: "40.00" },
        { x_mm: "0.00", y_mm: "40.00" },
      ],
    });
  });

  it("auto-picks a single candidate and blocks apply without a valid scale", async () => {
    const api = {
      sectionImport: vi.fn(async () => ({
        ...RESULT,
        mm_per_unit: null,
        candidates: [RESULT.candidates[0]!],
      })),
    };
    const { container } = render(
      <SectionImportPanel api={api as never} onApply={vi.fn()} onClose={() => {}} />,
    );
    fireEvent.change(fileInput(container), {
      target: { files: [new File(["x"], "frame.svg")] },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: t("catalog.sectionImport.apply") })).toBeDisabled(),
    );
  });
});
