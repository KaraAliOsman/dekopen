import { Link } from "react-router-dom";
import { type ReactNode } from "react";

export type Crumb = { label: string; to?: string };

/**
 * Section header contract: breadcrumb (where you are), title, short context
 * line, and the section's actions. Exactly one element in `actions` should be
 * primary; secondary/dangerous actions are distinguished by Button variant,
 * never by position alone.
 */
export function PageHeader({
  crumbs,
  title,
  context,
  actions,
  headingId,
}: {
  crumbs?: Crumb[];
  title: string;
  /** One line of operative context (e.g. client · code · state). */
  context?: ReactNode;
  actions?: ReactNode;
  /** id for the h1 — sections using aria-labelledby="page-title" pass it here. */
  headingId?: string;
}): JSX.Element {
  return (
    <header className="ui-page-header">
      {crumbs && crumbs.length > 0 ? (
        <nav aria-label="breadcrumb" className="ui-crumbs">
          {crumbs.map((crumb, index) => (
            <span className="ui-crumb" key={index}>
              {index > 0 ? (
                <span aria-hidden className="ui-crumb__sep">
                  /
                </span>
              ) : null}
              {crumb.to ? <Link to={crumb.to}>{crumb.label}</Link> : <span>{crumb.label}</span>}
            </span>
          ))}
        </nav>
      ) : null}
      <div className="ui-page-header__row">
        <div className="ui-page-header__main">
          <h1 className="ui-page-header__title" id={headingId}>
            {title}
          </h1>
          {context ? <p className="ui-page-header__context">{context}</p> : null}
        </div>
        {actions ? <div className="ui-page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
