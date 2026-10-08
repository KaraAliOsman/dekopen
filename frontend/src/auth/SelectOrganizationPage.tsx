import { useState } from "react";
import { Navigate } from "react-router-dom";

import { t } from "../i18n/es-CL";
import { roleLabel } from "../app/shellUtils";
import { StatusBadge } from "../ui";

import { AuthSheet } from "./AuthSheet";
import { useAuthSession } from "./AuthSessionProvider";
import { consumeReturnTo } from "./returnTo";

export function SelectOrganizationPage(): JSX.Element {
  const auth = useAuthSession();
  const [pendingId, setPendingId] = useState<string | null>(null);
  if (auth.status === "ready") return <Navigate to={consumeReturnTo()} replace />;
  // OWNER picks an org → the next /me flips to mfa_required. Without this
  // redirect the user was stranded on the selector with no path forward.
  if (auth.status === "mfa_required") return <Navigate to="/auth/mfa" replace />;

  return (
    <AuthSheet testId="organization-selector" labelledBy="org-title">
      <>
        <header className="auth-card__header">
          <h1 id="org-title">{t("org.select")}</h1>
          <p className="auth-hint">{t("org.selectDescription")}</p>
        </header>
        <div className="organization-list">
          {auth.memberships.map((membership) => {
            const pending = pendingId === membership.organization_id;
            return (
              <button
                key={membership.organization_id}
                type="button"
                className="org-option"
                disabled={pendingId !== null}
                aria-busy={pending}
                onClick={() => {
                  setPendingId(membership.organization_id);
                  void auth
                    .selectOrganization(membership.organization_id)
                    .finally(() => setPendingId(null));
                }}
              >
                <span className="org-option__glyph" aria-hidden>
                  {membership.organization_name.trim().slice(0, 1).toUpperCase()}
                </span>
                <span className="org-option__meta">
                  <strong>{membership.organization_name}</strong>
                  <span className="org-option__sub">
                    {pending ? t("org.pending") : t("org.enter")}
                  </span>
                </span>
                <StatusBadge
                  tone={membership.role === "OWNER" ? "info" : "neutral"}
                  label={t(roleLabel[membership.role])}
                />
              </button>
            );
          })}
        </div>
      </>
    </AuthSheet>
  );
}
