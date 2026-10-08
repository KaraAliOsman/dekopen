import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { t } from "../i18n/es-CL";
import { EmptyIllustration } from "../ui";

/** «Sin conexión» — la lámina ocupa la pantalla hasta que vuelve la red.
 * Una sola acción: reintentar (recarga). El listener vive aquí porque el
 * overlay decide solo por eventos del navegador, sin estado global.
 * Las rutas /field/* quedan fuera: la app de terreno gestiona su propia
 * cola offline, el instalador no puede quedarse ante una lámina sin obra. */
export function OfflineOverlay(): JSX.Element | null {
  const [offline, setOffline] = useState(() => !navigator.onLine);
  const { pathname } = useLocation();

  useEffect(() => {
    const goOffline = (): void => setOffline(true);
    const goOnline = (): void => setOffline(false);
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
    };
  }, []);

  if (!offline || pathname.startsWith("/field")) return null;
  return (
    <div className="app-offline" role="alert">
      <div className="app-error-card">
        <EmptyIllustration kind="bar" />
        <h1>{t("app.offlineTitle")}</h1>
        <p>{t("app.offlineBody")}</p>
        <div className="app-error-card__actions">
          <button
            className="ui-button ui-button--primary"
            onClick={() => window.location.reload()}
            type="button"
          >
            {t("app.errorReload")}
          </button>
        </div>
      </div>
    </div>
  );
}
