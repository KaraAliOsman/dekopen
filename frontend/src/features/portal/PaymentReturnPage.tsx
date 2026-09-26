import { t } from "../../i18n/es-CL";
import "./portal.css";

/** Public payer return — Flow sends the customer here after checkout. The
 * confirm webhook settles asynchronously, so the page only acknowledges:
 * the comprobante arrives by email once the payment seals. */
export function PaymentReturnPage(): JSX.Element {
  return (
    <main className="portal-page">
      <section className="portal-card portal-card--narrow">
        <p className="eyebrow">DEKOPEN</p>
        <h1>{t("paymentReturn.title")}</h1>
        <p>{t("paymentReturn.body")}</p>
        <p className="portal-return__close">{t("paymentReturn.close")}</p>
      </section>
    </main>
  );
}
