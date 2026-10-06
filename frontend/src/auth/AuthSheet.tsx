/** AuthSheet — la pantalla de entrada como hoja técnica (P25):
 * papel sobre la mesa g-50, marco con inglete y la marca en el rótulo.
 * Una sola acción por hoja; densidad office y perfecta a 390 px. */
import type { ReactNode } from "react";

import { Wordmark } from "../brand";
import { t } from "../i18n/es-CL";

export function AuthSheet({
  children,
  testId,
  labelledBy,
}: {
  children: ReactNode;
  testId?: string;
  labelledBy?: string;
}): JSX.Element {
  return (
    <main className="auth-screen" data-testid={testId}>
      <section aria-labelledby={labelledBy} className="auth-card auth-sheet">
        <div className="auth-sheet__masthead">
          <Wordmark size={15} />
          <span className="brand-os">{t("app.brandOs")}</span>
        </div>
        {children}
      </section>
    </main>
  );
}
