import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { productionDeliveries } from "../../api/generated/dekopen";
import type { DeliveryListItem, ProductionDeliveriesWhen } from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { formatDate } from "../../format";
import { t, tDynamic, type TranslationKey } from "../../i18n/es-CL";
import {
  DeniedState,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusChip,
  Tabs,
} from "../../ui";

import "./deliveries.css";

const DELIVERY_ROLES = ["OWNER", "WORKSHOP_MANAGER", "INSTALLER"];
const WINDOWS = ["open", "today", "overdue", "all"] as const;

const STATUS_TONE: Record<string, string> = {
  SCHEDULED: "info",
  ON_ROUTE: "info",
  DELIVERED: "ok",
  FAILED: "danger",
};

/** Despacho — hoja de ruta de entregas e instalaciones. La ventana («hoy»
 * del tenant) la decide el backend; aquí solo se elige la vista. */
export function DeliveriesPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const allowed = org != null && DELIVERY_ROLES.includes(org.role);
  const [params, setParams] = useSearchParams();
  const whenParam = params.get("when") ?? "open";
  const when: ProductionDeliveriesWhen = (WINDOWS as readonly string[]).includes(whenParam)
    ? (whenParam as ProductionDeliveriesWhen)
    : "open";

  const query = useQuery<DeliveryListItem[]>({
    queryKey: ["deliveries", org?.id, when],
    enabled: allowed,
    queryFn: async ({ signal }) => {
      const response = await productionDeliveries(
        { when },
        {
          signal,
          headers: { "X-Organization-ID": org!.id },
        },
      );
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data.items;
    },
  });

  if (!allowed) {
    return <DeniedState reason={t("deliveries.denied")} />;
  }

  const items = query.data ?? [];

  return (
    <section className="deliveries" aria-labelledby="page-title">
      <PageHeader
        context={t("deliveries.subtitle")}
        headingId="page-title"
        title={t("deliveries.title")}
      />

      <Tabs
        label={t("deliveries.title")}
        items={WINDOWS.map((window) => ({
          id: window,
          label: t(`deliveries.tab.${window}` as TranslationKey),
        }))}
        value={when}
        onChange={(id) => {
          const next = new URLSearchParams(params);
          next.set("when", id);
          setParams(next);
        }}
      />

      {query.isPending ? (
        <LoadingState shape="table" />
      ) : query.isError ? (
        <ErrorState title={t("deliveries.loadError")} onRetry={() => void query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t("deliveries.empty")} illustration="order" />
      ) : (
        <div className="deliveries-table__wrap">
          <table className="deliveries-table">
            <thead>
              <tr>
                <th scope="col">{t("deliveries.colOrder")}</th>
                <th scope="col">{t("deliveries.colProject")}</th>
                <th scope="col">{t("deliveries.colWhen")}</th>
                <th scope="col">{t("deliveries.colWindow")}</th>
                <th scope="col">{t("deliveries.colAddress")}</th>
                <th scope="col">{t("deliveries.colInstaller")}</th>
                <th scope="col">{t("deliveries.colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const status = item.status;
                const installPending = status === "DELIVERED" && item.order_status === "DISPATCHED";
                return (
                  <tr key={item.id}>
                    <td>
                      <Link
                        className="deliveries-order"
                        to={`/production?order=${item.order_code}`}
                      >
                        {item.order_code}
                      </Link>
                    </td>
                    <td>
                      <span className="deliveries-project">
                        <span className="mono">{item.project_code}</span>
                        <span className="deliveries-project__name">{item.project_name}</span>
                      </span>
                    </td>
                    <td>
                      <time dateTime={item.scheduled_date}>{formatDate(item.scheduled_date)}</time>
                    </td>
                    <td>{tDynamic("deliveries.window", item.time_window)}</td>
                    <td>{item.address}</td>
                    <td>{item.installer_name ?? "—"}</td>
                    <td>
                      <StatusChip
                        label={tDynamic("deliveries.status", status)}
                        tone={STATUS_TONE[status] ?? "neutral"}
                        value={status}
                      />
                      {installPending ? (
                        <span className="deliveries-install-pending">
                          {t("deliveries.installPending")}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
