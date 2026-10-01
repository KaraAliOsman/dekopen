import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { t } from "../i18n/es-CL";

import { useAuthSession } from "./AuthSessionProvider";

export function ReadyGuard({ children }: PropsWithChildren): JSX.Element {
  const auth = useAuthSession();
  const location = useLocation();
  if (auth.status === "loading" || auth.status === "resolving") {
    return <p role="status">{t("auth.resolving")}</p>;
  }
  if (auth.status === "anonymous") {
    return (
      <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
    );
  }
  if (auth.status === "mfa_required") {
    return <Navigate to="/auth/mfa" replace />;
  }
  if (auth.status === "organization_required") {
    return <Navigate to="/select-organization" replace />;
  }
  if (auth.status !== "ready") {
    return (
      <main className="auth-screen">
        <p role="alert">
          {t(auth.status === "no_membership" ? "auth.noMembership" : "auth.unavailable")}
        </p>
        <button type="button" onClick={() => void auth.signOut()}>
          {t("auth.signOut")}
        </button>
      </main>
    );
  }
  return <>{children}</>;
}

export function SessionGuard({ children }: PropsWithChildren): JSX.Element {
  const auth = useAuthSession();
  const location = useLocation();
  if (auth.status === "loading") return <p role="status">{t("auth.resolving")}</p>;
  if (auth.status === "anonymous") {
    return (
      <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
    );
  }
  return <>{children}</>;
}
