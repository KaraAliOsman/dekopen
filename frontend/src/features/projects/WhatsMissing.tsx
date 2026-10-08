import { useRef, useState } from "react";

import { t } from "../../i18n/es-CL";
import { Popover } from "../../ui";

/** One blocker/warning in workshop language — what the position still
 * needs before it can save. `anchor` is a CSS selector to focus when the
 * item is picked (a field, a rail button, the canvas). */
export interface MissingItem {
  key: string;
  reason: string;
  /** The suggested next step ("elegí una serie", "completá el vano"). */
  action?: string;
  anchor?: string;
}

/** Estado chip + "Qué falta" popover — replaces the orange banner. The
 * chip aggregates severity: Bloqueado (a hard blocker exists), N avisos
 * (only warnings), Válido (nothing missing). Each item explains in
 * workshop terms and jumps to its field. */
export function WhatsMissing({
  items,
  blocked,
  disabled = false,
}: {
  items: MissingItem[];
  /** True when a hard blocker exists — the chip reads "Bloqueado". */
  blocked: boolean;
  disabled?: boolean;
}): JSX.Element {
  const anchorRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const label = blocked
    ? t("projects.statusBlocked")
    : items.length > 0
      ? t("projects.statusWarnings").replace("{count}", String(items.length))
      : t("projects.statusReady");
  const tone = blocked ? "blocked" : items.length > 0 ? "warn" : "ok";
  return (
    <>
      <button
        type="button"
        ref={anchorRef}
        className={`missing-chip missing-chip--${tone}`}
        data-testid="whats-missing"
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        title={`${label} — ${t("projects.whatsMissing")}`}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open && (
        <Popover anchorRef={anchorRef} onClose={() => setOpen(false)} side="bottom">
          <div className="missing-panel" role="dialog" aria-label={t("projects.whatsMissing")}>
            <h3 className="missing-panel__title">{t("projects.whatsMissing")}</h3>
            {items.length === 0 ? (
              <p className="missing-panel__empty">{t("projects.missingNone")}</p>
            ) : (
              <ul className="missing-panel__list">
                {items.map((item) => (
                  <li key={item.key}>
                    <button
                      type="button"
                      className="missing-item"
                      onClick={() => {
                        setOpen(false);
                        const target = item.anchor
                          ? document.querySelector<HTMLElement>(item.anchor)
                          : null;
                        target?.scrollIntoView({ behavior: "smooth", block: "center" });
                        // Focus after the smooth scroll settles — focus()
                        // scrolls on its own, so deferring keeps the panel's
                        // scroll centered on the field.
                        if (target) setTimeout(() => target.focus(), 250);
                      }}
                    >
                      <span className="missing-item__reason">{item.reason}</span>
                      {item.action && <span className="missing-item__action">{item.action}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Popover>
      )}
    </>
  );
}
