import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PieceList } from "./PieceList";
import type { WorkPiece } from "./pieces";

/** P12 — la pestaña Piezas de una OT de 2.000 piezas monta solo las filas
 * visibles: el DOM jamás lleva más de ~100 filas (la pizarra del jefe y la
 * tablet del operario siguen respondiendo en una OT gigante). */

function makePieces(count: number): WorkPiece[] {
  const pieces: WorkPiece[] = [];
  for (let index = 1; index <= count; index += 1) {
    const unit = Math.ceil(index / 20);
    const seq = index % 20 || 20;
    pieces.push({
      code: `P01-U${String(unit).padStart(2, "0")}-M${String(seq).padStart(2, "0")}`,
      kind: "member",
      positionIndex: 1,
      unitIndex: unit,
      role: "FRAME",
      lengthMm: 1000 + seq,
      widthMm: null,
      heightMm: null,
      sku: "PF-45",
      stockRef: "B1",
      placed: true,
    });
  }
  return pieces;
}

describe("PieceList virtualization", () => {
  it("mounts far fewer than 100 rows for a 2000-piece order", () => {
    const pieces = makePieces(2000);
    const { container } = render(<PieceList emptyLabel="vacío" pieces={pieces} />);
    const rows = container.querySelectorAll(".piece-list__row");
    const groups = container.querySelectorAll(".piece-list__group");
    expect(rows.length).toBeLessThan(100);
    expect(rows.length + groups.length).toBeLessThan(100);
    expect(rows.length).toBeGreaterThan(0);
    expect(container.querySelectorAll("[role='listitem']").length).toBe(rows.length);
  });

  it("renders rows near the scroll position, not the whole list", () => {
    const pieces = makePieces(2000);
    const { container } = render(<PieceList emptyLabel="vacío" pieces={pieces} />);
    const scroller = container.querySelector(".piece-list");
    expect(scroller).toBeTruthy();
    // Jump deep into the list — the DOM window follows the scroll offset.
    fireEvent.scroll(scroller as HTMLElement, { target: { scrollTop: 40 * 1500 } });
    const codes = [...container.querySelectorAll(".piece-list__code")].map(
      (node) => node.textContent,
    );
    // Row 1500 of the flattened list lands inside unit ~72 (21 rows por unidad).
    expect(codes.some((code) => /U7[0-9]/.test(code ?? ""))).toBe(true);
    expect(codes.some((code) => code === "P01-U01-M01")).toBe(false);
  });
});
