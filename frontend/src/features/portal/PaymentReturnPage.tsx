import { useEffect, useState } from "react";

import { portalPaymentStatus } from "../../api/generated/dekopen";
import { formatMoney } from "../../format";
import { t } from "../../i18n/es-CL";
import "./portal.css";

/** Public payer return — Flow sends the customer here after checkout with
 * only `flow_token`. We resolve the link's real status and offer the way
 * back to the quote that originated the charge (its sealed return URL);
 * settlement still arrives async, so the copy never claims "pagado"
 * before the row says it. */
export function PaymentReturnPage(): JSX.Element {
  const [status, setStatus] = useState<{
    status?: string;
    amount?: string;
    payer_return_url?: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const params = new URLSearchParams(window.location.search);
  const flowToken = params.get("flow_token") ?? params.get("token") ?? "";

  useEffect(() => {
    if (!flowToken) {
      setError(t("paymentReturn.noToken"));
      return;
    }
    let active = true;
    void (async () => {
      try {
        const response = await portalPaymentStatus(flowToken);
        if (!active) return;
        if (response.status !== 200) {
          setError(t("paymentReturn.error"));
          return;
        }
        setStatus(response.data);
      } catch {
        if (active) setError(t("paymentReturn.error"));
      }
    })();
    return () => {
      active = false;
    };
  }, [flowToken]);

  const settled = status?.status === "PAID";
  const failed = status?.status === "FAILED" || status?.status === "REJECTED";
  return (
    <main className="portal-page">
      <section className="portal-card portal-card--narrow">
        <h1>
          {settled
            ? t("paymentReturn.title")
            : failed
              ? t("paymentReturn.failedTitle")
              : t("paymentReturn.pendingTitle")}
        </h1>
        {error !== null ? <p role="alert">{error}</p> : null}
        {error === null ? (
          <p>
            {settled
              ? t("paymentReturn.body")
              : failed
                ? t("paymentReturn.failedBody")
                : t("paymentReturn.pendingBody")}
          </p>
        ) : null}
        {settled && status?.amount ? (
          <p className="portal-return__amount">{formatMoney(status.amount, "CLP")}</p>
        ) : null}
        {status?.payer_return_url ? (
          <a className="portal-doc" href={status.payer_return_url}>
            {t("paymentReturn.backToQuote")}
          </a>
        ) : null}
        <p className="portal-return__close">{t("paymentReturn.close")}</p>
      </section>
    </main>
  );
}
