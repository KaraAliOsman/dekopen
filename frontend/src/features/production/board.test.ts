import { describe, expect, it } from "vitest";

import type { ProductionOrder } from "../../api/generated/models";
import { boardColumns, boardMatches, EMPTY_BOARD_FILTERS, OUTBOUND_COLUMN } from "./board";
import type { StationQueueGroup } from "./queue";

/** P12 — el tablero del jefe: columnas en orden de ruta (no alfabético) y el
 * filtro «en espera» contando lo mismo que el «Hoy» del dashboard. */

function order(partial: Partial<ProductionOrder>): ProductionOrder {
  return {
    id: "o1",
    order_code: "OT-1",
    status: "IN_PROGRESS",
    shortage: 0,
    qc_blocked: false,
    steps_blocked: 0,
    remake_reason: null,
    dispatch_ready: false,
    plan_state: "ready",
    committed_date: null,
    created_at: "2026-01-01T00:00:00Z",
    project_code: "P-1",
    project_name: "Obra",
    client_name: "Cliente",
    next_step: null,
    ...partial,
  } as ProductionOrder;
}

function station(code: string, sequences: number[]): StationQueueGroup {
  return {
    code,
    label: code,
    pending: sequences.length,
    in_progress: 0,
    blocked: 0,
    entries: sequences.map((sequence, index) => ({
      step_id: `${code}-${index}`,
      order_id: `o-${code}-${index}`,
      order_code: `OT-${code}-${index}`,
      sequence,
      label: code,
      status: "PENDING",
      note: null,
      is_next: false,
    })),
  };
}

describe("boardColumns", () => {
  it("ordena las columnas por la secuencia de ruta, no alfabéticamente", () => {
    // CLEAN < CUT < GLAZE alfabéticamente, pero la ruta es CUT → GLAZE → CLEAN.
    const queue = [station("CLEAN", [9]), station("CUT", [1]), station("GLAZE", [5])];
    const columns = boardColumns(queue, []);
    expect(columns.map((column) => column.code)).toEqual(["CUT", "GLAZE", "CLEAN"]);
  });

  it("usa la sequence más temprana cuando una estación aparece varias veces", () => {
    const queue = [station("CUT", [7, 2]), station("GLAZE", [4])];
    const columns = boardColumns(queue, []);
    expect(columns.map((column) => column.code)).toEqual(["CUT", "GLAZE"]);
  });

  it("deja la columna de salida siempre al final", () => {
    const queue = [station("CUT", [1])];
    const done = order({ id: "o-done", status: "COMPLETED", next_step: null });
    const columns = boardColumns(queue, [done]);
    expect(columns.at(-1)?.code).toBe(OUTBOUND_COLUMN);
  });
});

describe("boardMatches — filtro «en espera» (?blocked=1)", () => {
  const filters = { ...EMPTY_BOARD_FILTERS, issue: "blocked" as const };

  it("incluye una OT en HOLD aunque sus pasos no estén bloqueados", () => {
    expect(boardMatches(order({ status: "HOLD" }), filters)).toBe(true);
  });

  it("incluye pasos bloqueados y rechazos de calidad", () => {
    expect(boardMatches(order({ steps_blocked: 1 }), filters)).toBe(true);
    expect(boardMatches(order({ qc_blocked: true }), filters)).toBe(true);
  });

  it("excluye OTs que avanzan sin detenerse", () => {
    expect(boardMatches(order({ status: "IN_PROGRESS" }), filters)).toBe(false);
    expect(boardMatches(order({ status: "RELEASED" }), filters)).toBe(false);
  });
});
