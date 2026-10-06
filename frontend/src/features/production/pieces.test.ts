import { describe, expect, it } from "vitest";

import {
  buildPieceList,
  groupPieces,
  normalizePieceQuery,
  parsePieceCode,
  pieceMatches,
  type WorkPiece,
} from "./pieces";

/** P12 — la etiqueta impresa es la identidad de la pieza: su código se
 * interpreta siempre igual, en la pestaña Piezas y en el escáner del
 * operario. */

describe("parsePieceCode", () => {
  it("parses the physical P01-U02-M03 family codes", () => {
    expect(parsePieceCode("P01-U02-M03")).toEqual({
      kind: "member",
      positionIndex: 1,
      unitIndex: 2,
    });
    expect(parsePieceCode("p04-u07-i1")).toEqual({
      kind: "infill",
      positionIndex: 4,
      unitIndex: 7,
    });
    expect(parsePieceCode("P01-U02-MAN01")).toEqual({
      kind: "handle",
      positionIndex: 1,
      unitIndex: 2,
    });
  });

  it("marks reinforcement labels (R suffix) as reinforcement pieces", () => {
    expect(parsePieceCode("P01-U02-M03R").kind).toBe("reinforcement");
    expect(parsePieceCode("P01-U02-M03·R").kind).toBe("reinforcement");
  });

  it("parses legacy single-letter codes without indices", () => {
    expect(parsePieceCode("M-12")).toEqual({
      kind: "member",
      positionIndex: null,
      unitIndex: null,
    });
    expect(parsePieceCode("R-03").kind).toBe("reinforcement");
    expect(parsePieceCode("I-7").kind).toBe("infill");
    expect(parsePieceCode("V-1").kind).toBe("bay");
    expect(parsePieceCode("H-2").kind).toBe("leaf");
  });

  it("falls back to a generic piece for unrecognised codes", () => {
    expect(parsePieceCode("QR-UNKNOWN").kind).toBe("piece");
  });
});

describe("buildPieceList", () => {
  it("lists every labelled piece even without a cut plan", () => {
    const trace = {
      labels: { "piece-a": "P01-U01-M01", "piece-b": "P01-U01-M02" },
      plan: null,
    };
    const pieces = buildPieceList(trace);
    expect(pieces.map((piece) => piece.code)).toEqual(["P01-U01-M01", "P01-U01-M02"]);
    expect(pieces.every((piece) => !piece.placed)).toBe(true);
  });

  it("enriches labelled pieces with plan measures when the bar exists", () => {
    const trace = {
      labels: { a: "P01-U01-M01", b: "P01-U01-M02" },
      plan: {
        bars: [
          {
            bar_index: 3,
            cuts: [
              { code: "P01-U01-M01", length_mm: "1200.00", workshop_sku: "PF-45", role: "FRAME" },
            ],
          },
        ],
        sheets: [],
        unnested: [],
      },
    };
    const pieces = buildPieceList(trace);
    const placed = pieces.find((piece) => piece.code === "P01-U01-M01");
    const loose = pieces.find((piece) => piece.code === "P01-U01-M02");
    expect(placed).toMatchObject({
      placed: true,
      lengthMm: 1200,
      sku: "PF-45",
      stockRef: "B3",
      role: "FRAME",
    });
    expect(loose?.placed).toBe(false);
  });

  it("sorts by unit then code so the workshop reads it like packing", () => {
    const trace = {
      labels: {
        a: "P01-U03-M01",
        b: "P01-U01-M02",
        c: "P01-U01-M01",
        d: "P01-U02-M01",
      },
    };
    expect(buildPieceList(trace).map((piece) => piece.code)).toEqual([
      "P01-U01-M01",
      "P01-U01-M02",
      "P01-U02-M01",
      "P01-U03-M01",
    ]);
  });
});

describe("pieceMatches", () => {
  const piece = { code: "P01-U02-M03" } as WorkPiece;

  it("finds a piece by full or partial code, tolerating separators", () => {
    for (const query of ["P01-U02-M03", "p01 u02 m03", "M03", "U02M03"]) {
      expect(pieceMatches(piece, query), query).toBe(true);
    }
    expect(pieceMatches(piece, "M99")).toBe(false);
    expect(pieceMatches(piece, "")).toBe(true);
  });

  it("normalizes queries for glove typing", () => {
    expect(normalizePieceQuery("p01-u02 m03")).toBe("P01U02M03");
  });
});

describe("groupPieces", () => {
  it("groups by packing unit and leaves unassigned pieces last", () => {
    const make = (code: string, unitIndex: number | null): WorkPiece => ({
      code,
      kind: "member",
      positionIndex: null,
      unitIndex,
      role: null,
      lengthMm: null,
      widthMm: null,
      heightMm: null,
      sku: null,
      stockRef: null,
      placed: false,
    });
    const groups = groupPieces([make("P01-U02-M01", 2), make("P01-U01-M01", 1), make("X-9", null)]);
    expect(groups.map((group) => group.key)).toEqual(["U01", "U02", "—"]);
    expect(groups[0]?.pieces[0]?.code).toBe("P01-U01-M01");
  });
});
