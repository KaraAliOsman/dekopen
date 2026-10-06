import { Component, type ErrorInfo, type ReactNode } from "react";

import { t } from "../i18n/es-CL";
import { EmptyIllustration } from "../ui";

type Props = { children: ReactNode };
type State = { error: Error | null };

/** Catches a render crash in any route and keeps the app recoverable —
 * without it a single bad component takes the whole SPA down to a blank
 * page. Chunk-load failures (a new deploy mid-session) land here too and get
 * the same "recargar" recovery path. */
export class RouteErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("route_error", error, info.componentStack);
  }

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <main className="route-error" role="alert">
        <div className="route-error-card">
          <EmptyIllustration kind="document" />
          <h1>{t("app.errorTitle")}</h1>
          <p>{t("app.errorBody")}</p>
          <div className="route-error-actions">
            <button
              className="ui-button ui-button--primary"
              type="button"
              onClick={() => window.location.reload()}
            >
              {t("app.errorReload")}
            </button>
            <button
              type="button"
              className="route-error-secondary ui-button"
              onClick={() => {
                this.setState({ error: null });
                window.location.assign("/");
              }}
            >
              {t("app.errorHome")}
            </button>
          </div>
        </div>
      </main>
    );
  }
}
