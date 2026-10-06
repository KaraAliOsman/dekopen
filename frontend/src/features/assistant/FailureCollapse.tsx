import { useState } from "react";

import { t } from "../../i18n/es-CL";

/** §P17 — los fallos se colapsan: «3 intentos fallidos · Reintentar ·
 * Detalles técnicos». La línea humana lleva el mensaje del motor; el código
 * técnico queda plegado — nunca un stack ni un token crudo en el hilo.
 * `onRetry` solo se pasa cuando el backend permite el reintento. */
export function FailureCollapse({
  message,
  code,
  attempts = 1,
  onRetry,
  retryBusy = false,
}: {
  /** Mensaje humano ya traducido (jobErrorKey o equivalente). */
  message: string;
  /** El código técnico — se muestra solo dentro de «Detalles técnicos». */
  code?: string | null;
  attempts?: number;
  onRetry?: () => void;
  retryBusy?: boolean;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <div className="failure-collapse">
      <p className="failure-collapse__line">
        {attempts > 1
          ? t("assistant.failAttempts").replace("{count}", String(attempts))
          : t("assistant.failOne")}
        {" — "}
        {message}
        {onRetry ? (
          <>
            {" · "}
            <button
              type="button"
              className="failure-collapse__link"
              disabled={retryBusy}
              onClick={onRetry}
            >
              {t("aiws.retry")}
            </button>
          </>
        ) : null}
        {code ? (
          <>
            {" · "}
            <button
              type="button"
              className="failure-collapse__link"
              aria-expanded={open}
              onClick={() => setOpen((value) => !value)}
            >
              {t("assistant.techDetails")}
            </button>
          </>
        ) : null}
      </p>
      {open && code ? <code className="failure-collapse__code">{code}</code> : null}
    </div>
  );
}
