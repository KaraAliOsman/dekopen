/** /dev/correos — vista previa de las cinco plantillas transaccionales
 * (P25) renderizadas por el backend con la marca real del org activo.
 * Solo existe en DEV y el endpoint responde solo con DEBUG/MAIL_DEV_PREVIEWS.
 */
import { useEffect, useState } from "react";

import { mailDevPreviews } from "../api/generated/dekopen";
import type { MailPreview } from "../api/generated/models/mailPreview";
import { t } from "../i18n/es-CL";
import { EmptyState, ErrorState, LoadingState, SegmentedControl } from "../ui";
import "./dev-ui.css";

type Preview = MailPreview;

const TEMPLATE_LABELS: Record<string, string> = {
  magic_link: "Enlace de acceso",
  quote_sent: "Cotización enviada",
  quote_approved: "Aprobación recibida",
  payment_received: "Pago registrado",
  work_order_blocked: "OT bloqueada",
};

export function DevMailPage(): JSX.Element {
  const [previews, setPreviews] = useState<Preview[] | null>(null);
  const [error, setError] = useState(false);
  const [width, setWidth] = useState<"1440" | "390">("1440");

  useEffect(() => {
    let cancelled = false;
    void mailDevPreviews()
      .then((response) => {
        if (cancelled) return;
        if (response.status === 200) setPreviews(response.data);
        else setError(true);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return <ErrorState title={t("devMail.errorTitle")} body={t("devMail.errorBody")} />;
  }
  if (previews === null) {
    return <LoadingState />;
  }
  if (previews.length === 0) {
    return <EmptyState title={t("devMail.empty")} />;
  }

  return (
    <main className="dev-mail">
      <header className="dev-mail__head">
        <h1>{t("devMail.title")}</h1>
        <SegmentedControl
          name="dev-mail-width"
          onValueChange={(value) => setWidth(value)}
          options={[
            { label: "1440 px", value: "1440" as const },
            { label: "390 px", value: "390" as const },
          ]}
          value={width}
        />
      </header>
      {previews.map((preview) => (
        <section className="dev-mail__item" key={preview.template}>
          <header className="dev-mail__meta">
            <h2>{TEMPLATE_LABELS[preview.template] ?? preview.template}</h2>
            <p>
              <code>{preview.template}</code> · {preview.audience} · {preview.subject}
            </p>
          </header>
          <iframe
            className="dev-mail__frame"
            sandbox=""
            srcDoc={preview.html}
            title={preview.subject}
            style={{ width: width === "390" ? "390px" : "100%" }}
          />
        </section>
      ))}
    </main>
  );
}
