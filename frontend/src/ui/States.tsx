import { type PropsWithChildren, type ReactNode } from "react";

import { t } from "../i18n/es-CL";

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}): JSX.Element {
  return (
    <div className="ui-empty">
      <p className="ui-empty__title">{title}</p>
      {body ? <p className="ui-empty__body">{body}</p> : null}
      {action ? <div className="ui-empty__action">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title,
  body,
  onRetry,
}: {
  title?: string;
  body?: string;
  onRetry?: () => void;
}): JSX.Element {
  return (
    <div className="ui-empty ui-empty--error" role="alert">
      <p className="ui-empty__title">{title ?? t("ui.errorTitle")}</p>
      {body ? <p className="ui-empty__body">{body}</p> : null}
      {onRetry ? (
        <div className="ui-empty__action">
          <button className="ui-button--primary" onClick={onRetry} type="button">
            {t("ui.retry")}
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Permission wall: a role landed on a surface it cannot operate — give the
 * reason, the way out, and a lock glyph instead of a bare alert line on an
 * otherwise empty page (review VM7). */
export function DeniedState({ reason }: { reason: string }): JSX.Element {
  return (
    <div className="ui-empty ui-empty--denied" role="alert">
      <svg className="ui-empty__glyph" aria-hidden="true" viewBox="0 0 16 16">
        <rect x="3" y="7" width="10" height="7" rx="1.5" />
        <path d="M5.5 7V5.5a2.5 2.5 0 0 1 5 0V7" />
      </svg>
      <p className="ui-empty__title">{t("ui.deniedTitle")}</p>
      <p className="ui-empty__body">{reason}</p>
      <div className="ui-empty__action">
        {/* Plain anchor — permission walls render outside the router in unit
         * tests, and a full reload is acceptable on this rare path. */}
        <a className="ui-button" href="/dashboard">
          {t("ui.backToDashboard")}
        </a>
      </div>
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }): JSX.Element {
  return (
    <div aria-busy="true" className="ui-skeleton" role="status">
      {Array.from({ length: lines }, (_, index) => (
        <span className="ui-skeleton__line" key={index} style={{ width: `${88 - index * 14}%` }} />
      ))}
    </div>
  );
}

/** Technical banner for blocking/unknown-authority surfaces — a fact plus
 * the action that resolves it, not a decorative alert. */
export function WarningBanner({
  tone = "warning",
  title,
  action,
  children,
}: PropsWithChildren<{
  tone?: "warning" | "danger" | "blocked" | "unknown" | "info";
  title: string;
  action?: ReactNode;
}>): JSX.Element {
  return (
    <div className={`ui-banner ui-banner--${tone}`} role="status">
      <div className="ui-banner__text">
        <p className="ui-banner__title">{title}</p>
        {children ? <div className="ui-banner__body">{children}</div> : null}
      </div>
      {action ? <div className="ui-banner__action">{action}</div> : null}
    </div>
  );
}

/** A compact reference to the evidence/source behind a value — document,
 * page, row, or system of record. */
export function EvidenceChip({ label, title }: { label: string; title?: string }): JSX.Element {
  return (
    <span className="ui-evidence" title={title}>
      {label}
    </span>
  );
}
