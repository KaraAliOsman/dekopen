/** P12 — modelo plano de piezas de una OT para la pestaña «Piezas».
 *
 * Fuentes, todas selladas: `trace.labels` (identidad impresa completa — toda
 * pieza existe aunque no haya plan), `trace.plan.bars/sheets/unnested`
 * (medidas y SKU cuando hay optimización). Una pieza sin fila de plan
 * aparece igual — el taller la tiene etiquetada desde el sellado. */

export type WorkPieceKind =
  "member" | "reinforcement" | "infill" | "handle" | "sheet" | "bay" | "leaf" | "piece";

export type WorkPiece = {
  code: string;
  kind: WorkPieceKind;
  positionIndex: number | null;
  unitIndex: number | null;
  role: string | null;
  lengthMm: number | null;
  widthMm: number | null;
  heightMm: number | null;
  sku: string | null;
  /** Barra/plancha origen en el plan ("B3", "P1" — null sin plan). */
  stockRef: string | null;
  /** La pieza está ubicada en el plan de corte vigente. */
  placed: boolean;
};

type TraceLike = {
  labels?: Record<string, unknown> | null;
  plan?: {
    bars?: Array<Record<string, unknown>> | null;
    sheets?: Array<Record<string, unknown>> | null;
    unnested?: Array<Record<string, unknown>> | null;
  } | null;
} | null;

const PHYSICAL_RE = /^P(\d+)-U(\d+)-(MAN|M|I)(\d+)([·\-*_]?R)?$/i;
const LEGACY_RE = /^(M|R|I|MAN|V|H)-(\d+)$/i;

export function parsePieceCode(code: string): {
  kind: WorkPieceKind;
  positionIndex: number | null;
  unitIndex: number | null;
} {
  const physical = PHYSICAL_RE.exec(code.trim());
  if (physical) {
    const family = String(physical[3] ?? "").toUpperCase();
    return {
      kind:
        family === "MAN"
          ? "handle"
          : family === "I"
            ? "infill"
            : physical[5]
              ? "reinforcement"
              : "member",
      positionIndex: Number(physical[1]),
      unitIndex: Number(physical[2]),
    };
  }
  const legacy = LEGACY_RE.exec(code.trim());
  if (legacy) {
    const family = String(legacy[1] ?? "").toUpperCase();
    return {
      kind:
        family === "R"
          ? "reinforcement"
          : family === "I"
            ? "infill"
            : family === "MAN"
              ? "handle"
              : family === "V"
                ? "bay"
                : family === "H"
                  ? "leaf"
                  : "member",
      positionIndex: null,
      unitIndex: null,
    };
  }
  return { kind: "piece", positionIndex: null, unitIndex: null };
}

function num(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function mergePlanPiece(
  pieces: Map<string, WorkPiece>,
  raw: Record<string, unknown>,
  kind: WorkPieceKind,
  stockRef: string | null,
): void {
  const code = typeof raw.code === "string" && raw.code.trim() ? raw.code.trim() : null;
  if (!code) return;
  const parsed = parsePieceCode(code);
  const existing = pieces.get(code);
  const merged: WorkPiece = {
    code,
    kind: kind === "sheet" || existing?.kind === "piece" ? kind : (existing?.kind ?? parsed.kind),
    positionIndex: existing?.positionIndex ?? parsed.positionIndex,
    unitIndex: existing?.unitIndex ?? parsed.unitIndex ?? num(raw.unit_index),
    role: (raw.role as string | null) ?? existing?.role ?? null,
    lengthMm: num(raw.length_mm) ?? existing?.lengthMm ?? null,
    widthMm: num(raw.width_mm) ?? existing?.widthMm ?? null,
    heightMm: num(raw.height_mm) ?? existing?.heightMm ?? null,
    sku: (raw.workshop_sku as string | null) ?? existing?.sku ?? null,
    stockRef: stockRef ?? existing?.stockRef ?? null,
    placed: true,
  };
  pieces.set(code, merged);
}

/** Lista completa de piezas de la OT — todo lo etiquetado, enriquecido con
 * las medidas del plan cuando existe. Sin plan: todas `placed: false` pero
 * visibles (la OT ya nació con sus etiquetas). */
export function buildPieceList(trace: TraceLike): WorkPiece[] {
  const pieces = new Map<string, WorkPiece>();
  for (const rawCode of Object.values(trace?.labels ?? {})) {
    const code = String(rawCode ?? "").trim();
    if (!code) continue;
    const parsed = parsePieceCode(code);
    pieces.set(code, {
      code,
      kind: parsed.kind,
      positionIndex: parsed.positionIndex,
      unitIndex: parsed.unitIndex,
      role: null,
      lengthMm: null,
      widthMm: null,
      heightMm: null,
      sku: null,
      stockRef: null,
      placed: false,
    });
  }
  for (const bar of trace?.plan?.bars ?? []) {
    const barRef = bar.bar_index != null ? `B${String(bar.bar_index)}` : null;
    for (const cut of (bar.cuts as Array<Record<string, unknown>> | undefined) ?? []) {
      mergePlanPiece(pieces, cut, "member", barRef);
    }
  }
  for (const sheet of trace?.plan?.sheets ?? []) {
    const sheetRef = sheet.sheet_index != null ? `P${String(sheet.sheet_index)}` : null;
    for (const piece of (sheet.pieces as Array<Record<string, unknown>> | undefined) ?? []) {
      mergePlanPiece(pieces, piece, "sheet", sheetRef);
    }
  }
  for (const pane of trace?.plan?.unnested ?? []) {
    mergePlanPiece(pieces, pane, "sheet", null);
  }
  const ordered = [...pieces.values()];
  ordered.sort((a, b) => {
    const unit = (a.unitIndex ?? 999) - (b.unitIndex ?? 999);
    if (unit) return unit;
    return a.code.localeCompare(b.code, "es", { numeric: true });
  });
  return ordered;
}

/** Búsqueda tolerante: `p01 u02 m03`, `P01-U02-M03` o `m03` encuentran la
 * misma pieza — el operario escribe como puede con guantes. */
export function normalizePieceQuery(text: string): string {
  return text.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function pieceMatches(piece: WorkPiece, query: string): boolean {
  const needle = normalizePieceQuery(query);
  if (!needle) return true;
  return normalizePieceQuery(piece.code).includes(needle);
}

export type PieceGroup = { key: string; label: string; pieces: WorkPiece[] };

/** Agrupa por unidad de embalaje (U01…); piezas sin unidad van a su propio
 * grupo al final. La OT es de una posición, así que la unidad es el nivel
 * que el taller cuenta. */
export function groupPieces(pieces: WorkPiece[]): PieceGroup[] {
  const groups = new Map<string, WorkPiece[]>();
  for (const piece of pieces) {
    const key = piece.unitIndex != null ? `U${String(piece.unitIndex).padStart(2, "0")}` : "—";
    let list = groups.get(key);
    if (!list) {
      list = [];
      groups.set(key, list);
    }
    list.push(piece);
  }
  return [...groups.entries()]
    .sort(([a], [b]) =>
      a === "—" ? 1 : b === "—" ? -1 : a.localeCompare(b, "es", { numeric: true }),
    )
    .map(([key, list]) => ({
      key,
      label: key,
      pieces: list,
    }));
}
