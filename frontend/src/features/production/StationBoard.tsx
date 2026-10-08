/** P12 — el tablero del jefe: la planta de un vistazo. Una columna por
 * estación de la ruta configurada, tarjetas de OT con obra/compromiso/
 * avance/bloqueos y filtros reales. Nada de capacidad inventada: la
 * columna «Salida» junta lo terminado, y «sin fecha agendada» es un estado
 * honesto, no una promesa. */

import type { ProductionOrder, ProductionPrep } from "../../api/generated/models";
import { formatDate, formatPercent, formatRevision } from "../../format";
import { t } from "../../i18n/es-CL";
import { StatusChip } from "../../ui";
import {
  ORDER_STATUS_KEY,
  ORDER_STATUS_TONE,
  commitmentBucket,
  boardColumns,
  boardMatches,
  orderChips,
} from "./board";
import type { BoardChip, BoardFilters } from "./board";
import { stationCodeLabel } from "./labels";
import type { StationQueueGroup } from "./queue";
import { OUTBOUND_COLUMN } from "./board";

const CHIP_KEY: Record<BoardChip, Parameters<typeof t>[0]> = {
  shortage: "production.chipShortage",
  blocked: "production.chipBlocked",
  qc: "production.chipQc",
  unplanned: "production.chipUnplanned",
  stale_plan: "production.chipStalePlan",
  remake: "production.chipRemake",
  dispatch: "production.chipDispatch",
};

const CHIP_NEEDS_PERSON = new Set<BoardChip>(["blocked", "qc", "shortage"]);

export function StationBoard({
  orders,
  queue,
  prepVersions,
  canWrite,
  busy,
  releaseBusy,
  onRelease,
  onOpen,
  filters,
  onFilters,
}: {
  orders: ProductionOrder[];
  queue: StationQueueGroup[];
  prepVersions: ProductionPrep["versions"];
  canWrite: boolean;
  busy: boolean;
  releaseBusy: string | null;
  onRelease: (versionId: string) => void;
  onOpen: (orderId: string) => void;
  filters: BoardFilters;
  onFilters: (next: BoardFilters) => void;
}): JSX.Element {
  const visible = orders.filter((order) => boardMatches(order, filters));
  const columns = boardColumns(queue, visible);
  const projects = [
    ...new Set(orders.map((order) => order.project_code).filter(Boolean)),
  ].sort() as string[];

  return (
    <div className="board">
      <div className="board-filters" role="search">
        <input
          aria-label={t("production.boardSearch")}
          className="board-filters__q"
          onChange={(event) => onFilters({ ...filters, q: event.target.value })}
          placeholder={t("production.boardSearchPlaceholder")}
          type="search"
          value={filters.q}
        />
        <select
          aria-label={t("production.boardFilterProject")}
          onChange={(event) => onFilters({ ...filters, project: event.target.value })}
          value={filters.project}
        >
          <option value="">{t("production.boardAllProjects")}</option>
          {projects.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
        <select
          aria-label={t("production.boardFilterCommitment")}
          onChange={(event) =>
            onFilters({ ...filters, commitment: event.target.value as BoardFilters["commitment"] })
          }
          value={filters.commitment}
        >
          <option value="">{t("production.boardAllCommitments")}</option>
          <option value="overdue">{t("production.boardCommitmentOverdue")}</option>
          <option value="week">{t("production.boardCommitmentWeek")}</option>
          <option value="later">{t("production.boardCommitmentLater")}</option>
          <option value="none">{t("production.boardCommitmentNone")}</option>
        </select>
        <select
          aria-label={t("production.boardFilterIssue")}
          onChange={(event) =>
            onFilters({ ...filters, issue: event.target.value as BoardFilters["issue"] })
          }
          value={filters.issue}
        >
          <option value="">{t("production.boardAllIssues")}</option>
          <option value="blocked">{t("production.chipBlocked")}</option>
          <option value="qc">{t("production.chipQc")}</option>
          <option value="shortage">{t("production.chipShortage")}</option>
          <option value="unplanned">{t("production.chipUnplanned")}</option>
          <option value="stale_plan">{t("production.chipStalePlan")}</option>
          <option value="remake">{t("production.chipRemake")}</option>
          <option value="dispatch">{t("production.chipDispatch")}</option>
        </select>
        <span className="board-filters__count">
          {t("production.boardOrderCount").replace("{count}", String(visible.length))}
        </span>
      </div>

      {prepVersions.length ? (
        <section aria-label={t("production.prepTitle")} className="board-prep">
          <h3>{t("production.prepTitle")}</h3>
          <ul>
            {prepVersions.map((version) => (
              <li key={version.version_id}>
                <span className="board-prep__project">{version.project_code}</span>
                <span className="board-prep__meta">
                  {formatRevision(version.revision_code)} · {version.positions}{" "}
                  {version.positions === 1
                    ? t("production.prepPositionOne")
                    : t("production.prepPositions")}
                </span>
                <button
                  disabled={busy || !canWrite || releaseBusy === version.version_id}
                  title={!canWrite ? t("production.releaseRequiresManager") : undefined}
                  onClick={() => onRelease(version.version_id)}
                  type="button"
                >
                  {releaseBusy === version.version_id
                    ? t("production.prepReleasing")
                    : t("production.prepRelease")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {columns.every((column) => !column.orders.length) ? (
        <p className="production-trace-empty">{t("production.boardEmpty")}</p>
      ) : (
        <div aria-label={t("production.boardTitle")} className="board-columns" role="list">
          {columns.map((column) => (
            <section
              aria-label={
                column.code === OUTBOUND_COLUMN
                  ? t("production.boardOutbound")
                  : stationCodeLabel(column.code)
              }
              className="board-col"
              key={column.code}
            >
              <header className="board-col__head">
                <strong>
                  {column.code === OUTBOUND_COLUMN
                    ? t("production.boardOutbound")
                    : stationCodeLabel(column.code)}
                </strong>
                <span className="board-col__count">{column.orders.length}</span>
              </header>
              <ol className="board-col__cards">
                {column.orders.map((order) => (
                  <BoardCard key={order.id} onOpen={onOpen} order={order} />
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function BoardCard({
  order,
  onOpen,
}: {
  order: ProductionOrder;
  onOpen: (orderId: string) => void;
}): JSX.Element {
  const chips = orderChips(order);
  const bucket = commitmentBucket(order.committed_date);
  const orderStatus = order.status;
  const statusKey = ORDER_STATUS_KEY[orderStatus] ?? "production.orderReleased";
  const statusTone = ORDER_STATUS_TONE[orderStatus] ?? "neutral";
  const progress = order.steps_total > 0 ? order.steps_done / order.steps_total : 0;
  return (
    <li>
      <button
        className={`board-card${bucket === "overdue" ? " is-overdue" : ""}`}
        onClick={() => onOpen(order.id)}
        type="button"
      >
        <span className="board-card__code">{order.order_code}</span>
        <span className="board-card__work">
          {order.project_code ?? t("production.boardNoProject")}
          {order.client_name ? ` · ${order.client_name}` : ""}
        </span>
        <span className="board-card__meta">
          {order.quantity != null
            ? `${order.quantity} ${order.quantity === 1 ? t("production.unitsOne") : t("production.units")}`
            : t("production.boardNoUnits")}
          {" · "}
          {order.committed_date ? (
            <time dateTime={order.committed_date}>{formatDate(order.committed_date)}</time>
          ) : (
            <span className="board-card__nocommit">{t("production.boardNoCommit")}</span>
          )}
        </span>
        <span className="board-card__progress">
          <progress
            aria-label={t("production.boardProgress")}
            max={order.steps_total || 1}
            value={order.steps_done}
          />
          <span>
            {order.steps_done}/{order.steps_total} · {formatPercent(progress)}
          </span>
        </span>
        <span className="board-card__next">
          {order.next_step ? (
            order.next_step.label
          ) : (
            <StatusChip label={t(statusKey)} tone={statusTone} value={null} />
          )}
        </span>
        {chips.length ? (
          <span className="board-card__chips">
            {chips.map((chip) => (
              <em
                className={`board-chip${CHIP_NEEDS_PERSON.has(chip) ? " needs-person" : ""}`}
                key={chip}
              >
                {t(CHIP_KEY[chip])}
              </em>
            ))}
          </span>
        ) : null}
      </button>
    </li>
  );
}
