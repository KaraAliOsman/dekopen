import { useState } from "react";

import { t } from "../i18n/es-CL";

/**
 * Collapsed-by-default technical details: the raw diagnostic (hashes, ids,
 * payloads) stays available but never dominates the first view. One click
 * copies the diagnostic for a support/engineering handoff.
 */
export function TechDetails({
  summary,
  diagnostic,
  children,
}: {
  /** Short line on the closed row (defaults to "Detalles técnicos"). */
  summary?: string;
  /** Raw text copied by the copy button — include ids/hashes/payloads here. */
  diagnostic?: string;
  children?: React.ReactNode;
}): JSX.Element {
  const [copied, setCopied] = useState(false);
  return (
    <details className="ui-tech">
      <summary className="ui-tech__summary">
        <span>{summary ?? t("ui.details")}</span>
        {diagnostic !== undefined ? (
          <button
            className="ui-tech__copy"
            onClick={async (event) => {
              // Keep the click from toggling the <details> disclosure.
              event.preventDefault();
              try {
                await navigator.clipboard.writeText(diagnostic);
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1600);
              } catch {
                setCopied(false);
              }
            }}
            type="button"
          >
            {copied ? t("ui.copied") : t("ui.copyDiagnostics")}
          </button>
        ) : null}
      </summary>
      {children ? (
        <div className="ui-tech__body">{children}</div>
      ) : diagnostic !== undefined ? (
        <pre className="ui-tech__body ui-tech__pre">{diagnostic}</pre>
      ) : null}
    </details>
  );
}
