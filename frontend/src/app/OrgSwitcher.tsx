import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuthSession } from "../auth/AuthSessionProvider";
import { t } from "../i18n/es-CL";
import { useConfirm } from "../ui";

import { allowNextGuardedNavigation, hasUnsavedWork, roleLabel, useDismiss } from "./shellUtils";

/** Current org identity + switcher. One membership renders read-only — a
 * switcher with nothing to switch to is noise. */
export function OrgSwitcher(): JSX.Element | null {
  const auth = useAuthSession();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const org = auth.me?.active_organization;
  const [open, setOpen] = useState(false);
  const rootRef = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  if (!org) return null;
  const others = auth.memberships.filter((member) => member.organization_id !== org.id);

  async function switchOrganization(organizationId: string): Promise<void> {
    setOpen(false);
    // Switching orgs remounts the session context, bypassing the route
    // blocker — gate on the shared dirty registry instead.
    if (hasUnsavedWork()) {
      if (
        !(await confirm({
          title: t("shell.leaveUnsavedTitle"),
          body: t("shell.leaveUnsavedBody"),
          confirmLabel: t("ui.confirm"),
        }))
      )
        return;
      // The user already confirmed the discard — the route blocker must not
      // ask again, and the context reload may unmount it before it resolves.
      allowNextGuardedNavigation();
    }
    // Entity routes (project, position, work order) belong to the old org —
    // land on a tenant-neutral surface before the new context resolves.
    navigate("/dashboard");
    void auth.selectOrganization(organizationId);
  }
  return (
    <div className="org-switcher" ref={rootRef}>
      <button
        type="button"
        className="org-switcher__current"
        aria-haspopup={others.length > 0 ? "menu" : undefined}
        aria-expanded={open || undefined}
        disabled={others.length === 0}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="org-switcher__name">{org.name}</span>
        <span className="org-switcher__role">{t(roleLabel[org.role])}</span>
        {others.length > 0 && (
          <span className="org-switcher__chevron" aria-hidden>
            ▾
          </span>
        )}
      </button>
      {open && others.length > 0 && (
        <ul className="shell-menu" aria-label={t("shell.switchOrg")}>
          {others.map((member) => (
            <li key={member.organization_id}>
              <button
                type="button"
                className="shell-menu__item"
                onClick={() => void switchOrganization(member.organization_id)}
              >
                <span>{member.organization_name}</span>
                <span className="shell-menu__meta">{t(roleLabel[member.role])}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
