import { Link } from "react-router-dom";

import type { PositionResponse } from "../../api/generated/models";
import { formatMoney } from "../../format";
import { t } from "../../i18n/es-CL";

/** Project positions filmstrip in the bottom dock — cross-position
 * context while editing (which vanos exist, their price), one click to
 * jump between them. The current position stays selected; "Nuevo vano"
 * is a real link (the dirty guard asks before leaving). */
export function PositionStrip({
  projectId,
  positions,
  currentId,
  currency,
}: {
  projectId: string;
  positions: readonly PositionResponse[];
  currentId: string | null;
  currency: string;
}): JSX.Element {
  return (
    <div className="position-strip" role="list" aria-label={t("projects.positionStrip")}>
      {positions.map((position) => (
        <Link
          key={position.id}
          role="listitem"
          className={`position-strip__item${position.id === currentId ? " is-active" : ""}`}
          aria-current={position.id === currentId ? "page" : undefined}
          to={`/projects/${projectId}/positions/${position.id}/edit`}
        >
          <span className="position-strip__index">
            {t("projects.positionIndex").replace("{n}", String(position.position_index))}
          </span>
          <span className="position-strip__location">
            {position.location_tag || t("crumb.positionFallback")}
          </span>
          <span className="position-strip__meta">
            ×{position.quantity} · {formatMoney(position.price_net, currency)}
          </span>
        </Link>
      ))}
      <Link
        className="position-strip__item position-strip__item--new"
        to={`/projects/${projectId}/positions/new`}
      >
        {t("projects.position")}
      </Link>
    </div>
  );
}
