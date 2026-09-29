import { type PropsWithChildren, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { t } from "../i18n/es-CL";

export type DialogProps = PropsWithChildren<{
  title: string;
  onClose: () => void;
  /** Optional footer actions (buttons). Enter triggers the first primary action. */
  footer?: React.ReactNode;
  width?: "s" | "m" | "l";
}>;

/**
 * Canonical modal surface. Esc closes; Enter (when focus is inside the
 * dialog, not in a textarea/multiline field) activates the first
 * data-primary control in the footer. Focus lands on the dialog on open and
 * returns to the invoking element on close.
 */
export function Dialog({
  title,
  onClose,
  footer,
  width = "m",
  children,
}: DialogProps): JSX.Element {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<Element | null>(null);

  useEffect(() => {
    previousFocus.current = document.activeElement;
    panelRef.current?.focus();
    return () => {
      (previousFocus.current as HTMLElement | null)?.focus?.();
    };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key === "Tab" && panelRef.current) {
        // Modal containment — Tab cycles inside the dialog, never reaching
        // the page behind the overlay.
        const focusables = panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) {
          event.preventDefault();
          panelRef.current.focus();
          return;
        }
        const first = focusables.item(0);
        const last = focusables.item(focusables.length - 1);
        const active = document.activeElement as HTMLElement | null;
        if (event.shiftKey) {
          if (
            active === first ||
            active === panelRef.current ||
            !panelRef.current.contains(active)
          ) {
            event.preventDefault();
            last.focus();
          }
        } else if (active === last || !panelRef.current.contains(active)) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
      if (event.key === "Enter" && panelRef.current?.contains(event.target as Node)) {
        const target = event.target as HTMLElement;
        if (target.tagName === "TEXTAREA" || target.tagName === "SELECT") return;
        const primary = panelRef.current.querySelector<HTMLElement>("[data-primary]");
        if (primary && target.tagName !== "BUTTON") {
          event.preventDefault();
          primary.click();
        }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return createPortal(
    <div className="ui-overlay" onClick={onClose} role="presentation">
      <div
        aria-label={title}
        aria-modal="true"
        className={`ui-dialog ui-dialog--${width}`}
        onClick={(event) => event.stopPropagation()}
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="ui-dialog__header">
          <h2 className="ui-dialog__title">{title}</h2>
          <button
            aria-label={t("ui.close")}
            className="ui-icon-button"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>
        <div className="ui-dialog__body">{children}</div>
        {footer ? <footer className="ui-dialog__footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  );
}
