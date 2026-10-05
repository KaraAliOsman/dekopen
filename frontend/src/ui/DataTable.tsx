/** DataTable — reglas finas, SIN cebra, encabezado fijo con etiqueta
 * técnica, números a la derecha en Plex Mono, orden y filtro, selección
 * con barra de acciones en lote, virtualización sobre 200 filas y los
 * cinco estados (carga / vacío / error / datos / bloqueo) explícitos. */
import { useMemo, useRef, useState, type ReactNode } from "react";

import { t } from "../i18n/es-CL";
import { Checkbox } from "./Controls";
import { EmptyState, ErrorState, Skeleton } from "./States";

export type Column<T> = {
  key: string;
  /** Etiqueta técnica del encabezado. */
  label: ReactNode;
  /** Contenido de la celda. */
  render: (row: T) => ReactNode;
  /** Valor ordenable — si existe, el encabezado ofrece orden. */
  sortValue?: (row: T) => string | number;
  /** Filtrable por texto libre. */
  filterText?: (row: T) => string;
  /** Alineación numérica a la derecha en Mono. */
  numeric?: boolean;
  width?: string;
};

type SortDir = "asc" | "desc";
const VIRTUAL_THRESHOLD = 200;
const ROW_HEIGHT = 36;
const OVERSCAN = 12;

export type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Estado controlado desde fuera. */
  state?: "data" | "loading" | "error" | "empty" | "blocked";
  loadingBody?: ReactNode;
  emptyTitle?: ReactNode;
  emptyBody?: ReactNode;
  errorBody?: ReactNode;
  onRetry?: () => void;
  blockedBody?: ReactNode;
  /** Selección — si se entrega `selection`, hay casilla por fila y barra
   * de lote cuando hay ≥1 seleccionada. */
  selection?: Set<string>;
  onSelectionChange?: (next: Set<string>) => void;
  bulkActions?: ReactNode;
  filterPlaceholder?: string;
  ariaLabel?: string;
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  state = "data",
  loadingBody,
  emptyTitle,
  emptyBody,
  errorBody,
  onRetry,
  blockedBody,
  selection,
  onSelectionChange,
  bulkActions,
  filterPlaceholder,
  ariaLabel,
}: DataTableProps<T>): JSX.Element {
  const [sort, setSort] = useState<{ key: string; dir: SortDir } | null>(null);
  const [filter, setFilter] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    let out = rows;
    if (q) {
      out = out.filter((row) => columns.some((c) => c.filterText?.(row).toLowerCase().includes(q)));
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col?.sortValue) {
        const get = col.sortValue;
        out = [...out].sort((a, b) => {
          const av = get(a);
          const bv = get(b);
          const cmp =
            typeof av === "number" && typeof bv === "number"
              ? av - bv
              : String(av).localeCompare(String(bv), "es-CL");
          return sort.dir === "asc" ? cmp : -cmp;
        });
      }
    }
    return out;
  }, [rows, columns, filter, sort]);

  const virtual = filtered.length > VIRTUAL_THRESHOLD;
  const viewportHeight = 560;
  const start = virtual ? Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN) : 0;
  const end = virtual
    ? Math.min(filtered.length, Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN)
    : filtered.length;
  const visible = virtual ? filtered.slice(start, end) : filtered;

  if (state === "loading") {
    return <>{loadingBody ?? <Skeleton lines={6} />}</>;
  }
  if (state === "error") {
    return (
      <ErrorState body={typeof errorBody === "string" ? errorBody : undefined} onRetry={onRetry} />
    );
  }
  if (state === "blocked") {
    return (
      <EmptyState title={typeof blockedBody === "string" ? blockedBody : t("ui.deniedTitle")} />
    );
  }
  if (state === "empty" || filtered.length === 0) {
    return (
      <EmptyState
        body={typeof emptyBody === "string" ? emptyBody : undefined}
        title={typeof emptyTitle === "string" ? emptyTitle : t("ui.paletteEmpty")}
      />
    );
  }

  const allSelected =
    selection !== undefined && selection.size === filtered.length && filtered.length > 0;
  const toggleAll = () => {
    if (!onSelectionChange) return;
    onSelectionChange(allSelected ? new Set() : new Set(filtered.map((row) => rowKey(row))));
  };

  return (
    <div className="ui-table">
      <div className="ui-table__bar">
        <input
          aria-label={filterPlaceholder ?? t("ui.filterPlaceholder")}
          className="ui-field__input ui-table__filter"
          onChange={(event) => setFilter(event.target.value)}
          placeholder={filterPlaceholder ?? t("ui.filterPlaceholder")}
          type="search"
          value={filter}
        />
        {selection && selection.size > 0 ? (
          <div className="ui-table__bulk" role="toolbar">
            <span className="ui-table__bulk-count">
              {t("ui.selectedCount").replace("{count}", String(selection.size))}
            </span>
            {bulkActions}
            <button
              className="ui-button ui-button--compact"
              onClick={() => onSelectionChange?.(new Set())}
              type="button"
            >
              {t("ui.clearSelection")}
            </button>
          </div>
        ) : null}
      </div>
      <div
        className="ui-table__scroll"
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        ref={scrollRef}
        style={virtual ? { maxHeight: viewportHeight, overflowY: "auto" } : undefined}
      >
        <table aria-label={ariaLabel}>
          <thead>
            <tr>
              {selection ? (
                <th className="ui-table__check">
                  <Checkbox
                    aria-label={allSelected ? t("ui.clearSelection") : t("ui.selectedCount")}
                    checked={allSelected}
                    label=""
                    onChange={toggleAll}
                  />
                </th>
              ) : null}
              {columns.map((col) => (
                <th
                  className={col.numeric ? "is-numeric" : undefined}
                  key={col.key}
                  scope="col"
                  style={col.width ? { width: col.width } : undefined}
                >
                  {col.sortValue ? (
                    <button
                      className="ui-table__sort"
                      onClick={() =>
                        setSort((prev) =>
                          prev?.key === col.key && prev.dir === "asc"
                            ? { key: col.key, dir: "desc" }
                            : { key: col.key, dir: "asc" },
                        )
                      }
                      type="button"
                    >
                      {col.label}
                      <span aria-hidden className="ui-table__sort-mark">
                        {sort?.key === col.key ? (sort.dir === "asc" ? "↑" : "↓") : ""}
                      </span>
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {virtual && start > 0 ? (
              <tr aria-hidden className="ui-table__spacer">
                <td
                  colSpan={columns.length + (selection ? 1 : 0)}
                  style={{ height: start * ROW_HEIGHT }}
                />
              </tr>
            ) : null}
            {visible.map((row) => {
              const key = rowKey(row);
              const selected = selection?.has(key) ?? false;
              return (
                <tr
                  aria-selected={selected || undefined}
                  className={selected ? "is-selected" : undefined}
                  key={key}
                >
                  {selection ? (
                    <td className="ui-table__check">
                      <Checkbox
                        aria-label={key}
                        checked={selected}
                        label=""
                        onChange={() => {
                          if (!onSelectionChange) return;
                          const next = new Set(selection);
                          if (selected) next.delete(key);
                          else next.add(key);
                          onSelectionChange(next);
                        }}
                      />
                    </td>
                  ) : null}
                  {columns.map((col) => (
                    <td className={col.numeric ? "is-numeric" : undefined} key={col.key}>
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
            {virtual && end < filtered.length ? (
              <tr aria-hidden className="ui-table__spacer">
                <td
                  colSpan={columns.length + (selection ? 1 : 0)}
                  style={{ height: (filtered.length - end) * ROW_HEIGHT }}
                />
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
