/** P12 — «Piezas» de la OT: todas las piezas etiquetadas, agrupadas por
 * unidad, con búsqueda directa. Virtualizada por filas fijas — una OT de
 * 2.000 piezas monta solo las filas visibles (< 100 en el DOM). */

import { useCallback, useMemo, useRef, useState } from "react";

import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";
import { cutRoleLabel } from "./labels";
import { groupPieces, type WorkPiece } from "./pieces";

const ROW_H = 40;
const GROUP_H = 44;
const OVERSCAN = 6;
const VIEWPORT = 460;

type FlatRow =
  | { type: "group"; key: string; label: string; count: number }
  | { type: "piece"; piece: WorkPiece };

function flatten(pieces: WorkPiece[]): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const group of groupPieces(pieces)) {
    rows.push({ type: "group", key: group.key, label: group.label, count: group.pieces.length });
    for (const piece of group.pieces) rows.push({ type: "piece", piece });
  }
  return rows;
}

function measure(row: FlatRow): number {
  return row.type === "group" ? GROUP_H : ROW_H;
}

function offsets(rows: FlatRow[]): { tops: number[]; total: number } {
  const tops = new Array<number>(rows.length);
  let acc = 0;
  rows.forEach((row, index) => {
    tops[index] = acc;
    acc += measure(row);
  });
  return { tops, total: acc };
}

function firstVisible(tops: number[], scrollTop: number): number {
  let low = 0;
  let high = tops.length - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if ((tops[mid] ?? -1) <= scrollTop) low = mid;
    else high = mid - 1;
  }
  return low;
}

export function PieceList({
  pieces,
  emptyLabel,
  highlight,
  onSelect,
  selectedCode,
  dense,
}: {
  pieces: WorkPiece[];
  emptyLabel: string;
  /** Código a resaltar (pieza recién escaneada). */
  highlight?: string | null;
  onSelect?: (piece: WorkPiece) => void;
  selectedCode?: string | null;
  dense?: boolean;
}): JSX.Element {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const rows = useMemo(() => flatten(pieces), [pieces]);
  const { tops, total } = useMemo(() => offsets(rows), [rows]);
  const rowHeight = dense ? 36 : ROW_H;

  const onScroll = useCallback(() => {
    setScrollTop(scrollRef.current?.scrollTop ?? 0);
  }, []);

  if (!rows.length) {
    return <p className="production-trace-empty">{emptyLabel}</p>;
  }
  const start = Math.max(0, firstVisible(tops, scrollTop) - OVERSCAN);
  const viewportEnd = scrollTop + VIEWPORT + OVERSCAN * rowHeight;
  let end = start;
  while (end < rows.length && (tops[end] ?? Number.POSITIVE_INFINITY) < viewportEnd) end += 1;
  const visible = rows.slice(start, end);
  const visibleHeight = visible.reduce((acc, row) => acc + measure(row), 0);

  return (
    <div
      className="piece-list"
      onScroll={onScroll}
      ref={scrollRef}
      role="list"
      style={{ maxHeight: VIEWPORT }}
    >
      <div style={{ height: tops[start] ?? 0 }} aria-hidden />
      {visible.map((row) =>
        row.type === "group" ? (
          <div className="piece-list__group" key={`g-${row.key}`} role="presentation">
            <span className="piece-list__unit">{row.label}</span>
            <span className="piece-list__count">
              {row.count} {t("production.piecesUnit")}
            </span>
          </div>
        ) : (
          <PieceRow
            highlighted={highlight === row.piece.code}
            key={row.piece.code}
            onSelect={onSelect}
            piece={row.piece}
            selected={selectedCode === row.piece.code}
          />
        ),
      )}
      <div
        style={{ height: Math.max(0, total - (tops[start] ?? 0) - visibleHeight) }}
        aria-hidden
      />
    </div>
  );
}

function PieceRow({
  piece,
  highlighted,
  selected,
  onSelect,
}: {
  piece: WorkPiece;
  highlighted: boolean;
  selected: boolean;
  onSelect?: (piece: WorkPiece) => void;
}): JSX.Element {
  const measure =
    piece.lengthMm != null
      ? `${fmtMm(piece.lengthMm)} mm`
      : piece.widthMm != null && piece.heightMm != null
        ? `${fmtMm(piece.widthMm)} × ${fmtMm(piece.heightMm)}`
        : "—";
  const classes = ["piece-list__row"];
  if (highlighted) classes.push("is-highlight");
  if (selected) classes.push("is-selected");
  const body = (
    <>
      <span className="piece-list__code">{piece.code}</span>
      <span className="piece-list__measure">{measure}</span>
      <span className="piece-list__sku">{piece.sku ?? "—"}</span>
      <span className="piece-list__role">{piece.role ? cutRoleLabel(piece.role) : "—"}</span>
      <span className="piece-list__stock">{piece.stockRef ?? "—"}</span>
      <span className="piece-list__state">
        {piece.placed ? t("production.piecePlaced") : t("production.pieceUnplaced")}
      </span>
    </>
  );
  if (!onSelect) {
    return (
      <div className={classes.join(" ")} role="listitem">
        {body}
      </div>
    );
  }
  return (
    <button
      aria-pressed={selected}
      className={classes.join(" ")}
      onClick={() => onSelect(piece)}
      role="listitem"
      type="button"
    >
      {body}
    </button>
  );
}
