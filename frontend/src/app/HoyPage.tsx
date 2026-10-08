import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "../api/apiMutator";
import { analyticsTodayQueue } from "../api/generated/dekopen";
import type { TodayQueue, TodayQueueItem } from "../api/generated/models";
import { useAuthSession } from "../auth/AuthSessionProvider";
import { t } from "../i18n/es-CL";
import { domainLabel } from "../i18n/domainLabels";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "../ui";

import "./hoy.css";

/** §8 — Inicio «Hoy»: la cola de qué hacer hoy, ordenada por consecuencia,
 * armada por el backend (frase, razón y enlace ya vienen listos). El
 * frontend solo dibuja — nada de agregados calculados aquí. */
export function HoyPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;

  const query = useQuery<TodayQueue>({
    queryKey: ["hoy", org?.id],
    enabled: org !== undefined,
    queryFn: async ({ signal }) => {
      const response = await analyticsTodayQueue({
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data;
    },
  });

  const items = query.data?.items ?? [];
  const panels = query.data?.panels ?? [];

  return (
    <section className="hoy" aria-labelledby="page-title">
      <PageHeader
        context={org?.name ?? t("org.none")}
        headingId="page-title"
        title={t("hoy.title")}
      />

      {query.isPending ? (
        <LoadingState shape="table" />
      ) : query.isError ? (
        <ErrorState title={t("hoy.loadError")} onRetry={() => void query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t("hoy.allClear")} body={t("hoy.allClearDetail")} />
      ) : (
        <div className="hoy-layout">
          <ol className="hoy-queue">
            {items.map((item, index) => (
              <HoyRow item={item} key={`${item.kind}-${index}`} />
            ))}
          </ol>
          {panels.length > 0 ? (
            <aside className="hoy-panels">
              {panels.map((panel) => (
                <section className="hoy-panel" key={panel.kind}>
                  <h2 className="eyebrow">{panel.title}</h2>
                  <ul>
                    {panel.rows.map((row) => (
                      <li key={row.label}>
                        <span className="hoy-panel__label">{row.label}</span>
                        <span className="hoy-panel__value">{row.value}</span>
                        <span className="hoy-panel__count">{row.count}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </aside>
          ) : null}
        </div>
      )}
    </section>
  );
}

function HoyRow({ item }: { item: TodayQueueItem }): JSX.Element {
  return (
    <li className={`hoy-item hoy-item--${item.urgency}`}>
      <Link to={item.to} className="hoy-item__link">
        <span className="hoy-item__urgency">{domainLabel("UrgencyEnum", item.urgency).label}</span>
        <span className="hoy-item__main">
          <span className="hoy-item__phrase">{item.phrase}</span>
          {item.entity_code || item.entity_label ? (
            <span className="hoy-item__entity">
              {item.entity_code}
              {item.entity_code && item.entity_label ? " · " : ""}
              {item.entity_label}
            </span>
          ) : null}
          {item.reason ? <span className="hoy-item__reason">{item.reason}</span> : null}
        </span>
        {item.count !== null && item.count !== undefined && item.count > 0 ? (
          <span className="hoy-item__count">{item.count}</span>
        ) : null}
        <span className="hoy-item__cta">{item.cta} →</span>
      </Link>
    </li>
  );
}
