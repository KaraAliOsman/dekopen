import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { quotationsList } from "../../api/generated/dekopen";
import type { QuotationItem } from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { formatDate, formatMoney } from "../../format";
import { t, tDynamic } from "../../i18n/es-CL";
import {
  DeniedState,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusChip,
} from "../../ui";

import "./quotations.css";

const QUOTATION_ROLES = ["OWNER", "ESTIMATOR"];

const STATE_TONE: Record<string, string> = {
  sent: "info",
  viewed: "info",
  approved: "ok",
  declined: "danger",
  expired: "person",
  no_link: "neutral",
};

function viewedLabel(item: QuotationItem): string {
  const approval = item.approval;
  if (!approval) return "—";
  if (approval.view_count > 0) {
    const base = t("quotations.viewedYes").replace("{n}", String(approval.view_count));
    const when = approval.last_viewed_at ?? approval.first_viewed_at;
    return when ? `${base} — ${formatDate(when)}` : base;
  }
  if (approval.status === "APPROVED" || approval.status === "DECLINED") {
    return "—";
  }
  return t("quotations.viewedNo");
}

function validityLabel(item: QuotationItem): string {
  const expires = item.approval?.expires_at;
  if (!expires) return "—";
  if (item.quote_state === "expired") {
    return t("quotations.expiredOn").replace("{date}", formatDate(expires));
  }
  return formatDate(expires);
}

/** Cotizaciones — la lista transversal de lo emitido al cliente:
 * estado, vigencia y «vista por el cliente» en una sola lectura. */
export function QuotationsPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const allowed = org != null && QUOTATION_ROLES.includes(org.role);

  const query = useQuery<QuotationItem[]>({
    queryKey: ["quotations", org?.id],
    enabled: allowed,
    queryFn: async ({ signal }) => {
      const response = await quotationsList({
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return response.data.items;
    },
  });

  if (!allowed) {
    return <DeniedState reason={t("quotations.denied")} />;
  }

  const items = query.data ?? [];

  return (
    <section className="quotations" aria-labelledby="page-title">
      <PageHeader
        context={t("quotations.subtitle")}
        headingId="page-title"
        title={t("quotations.title")}
      />

      {query.isPending ? (
        <LoadingState shape="table" />
      ) : query.isError ? (
        <ErrorState title={t("quotations.loadError")} onRetry={() => void query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t("quotations.empty")} illustration="document" />
      ) : (
        <div className="quotations-table__wrap">
          <table className="quotations-table">
            <thead>
              <tr>
                <th scope="col">{t("quotations.colProject")}</th>
                <th scope="col">{t("quotations.colClient")}</th>
                <th scope="col">{t("quotations.colRevision")}</th>
                <th scope="col">{t("quotations.colAmount")}</th>
                <th scope="col">{t("quotations.colState")}</th>
                <th scope="col">{t("quotations.colViewed")}</th>
                <th scope="col">{t("quotations.colExpires")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.project_id}>
                  <td>
                    <Link className="quotations-project" to={`/projects/${item.project_id}`}>
                      <span className="quotations-code">{item.project_code}</span>
                      <span className="quotations-name">{item.project_name}</span>
                    </Link>
                  </td>
                  <td>{item.client_name}</td>
                  <td className="mono">{item.current_revision}</td>
                  <td className="mono">{formatMoney(item.total_price_gross, item.currency)}</td>
                  <td>
                    <StatusChip
                      label={tDynamic("quotations.state", item.quote_state)}
                      tone={STATE_TONE[item.quote_state] ?? "neutral"}
                      value={item.quote_state}
                    />
                  </td>
                  <td>{viewedLabel(item)}</td>
                  <td>{validityLabel(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
