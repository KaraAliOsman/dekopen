import { Link } from "react-router-dom";

import { t } from "../i18n/es-CL";
import { EmptyIllustration } from "../ui";

/** 404 — la ruta no corresponde a ninguna lámina del plan. Una acción:
 * volver al taller. */
export function NotFoundPage(): JSX.Element {
  return (
    <main className="app-error-page" role="alert">
      <div className="app-error-card">
        <EmptyIllustration kind="elevation" />
        <h1>{t("app.notFoundTitle")}</h1>
        <p>{t("app.notFoundBody")}</p>
        <div className="app-error-card__actions">
          <Link className="ui-button ui-button--primary" to="/">
            {t("app.errorHome")}
          </Link>
        </div>
      </div>
    </main>
  );
}
