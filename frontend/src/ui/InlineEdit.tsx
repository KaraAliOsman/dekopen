import { useEffect, useRef, useState } from "react";

import { t } from "../i18n/es-CL";
import { Icon } from "./icons";

/** Click-to-edit for single-line text. Enter commits, Esc cancels. */
export function InlineEdit({
  value,
  onCommit,
  placeholder,
  ariaLabel,
}: {
  value: string;
  onCommit: (next: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  function commit(): void {
    setEditing(false);
    const next = draft.trim();
    if (next && next !== value) onCommit(next);
    else setDraft(value);
  }

  if (!editing) {
    return (
      <button
        aria-label={ariaLabel ?? t("ui.edit")}
        className="ui-inline-edit"
        onClick={() => {
          setDraft(value);
          setEditing(true);
        }}
        type="button"
      >
        {value || <span className="ui-inline-edit__placeholder">{placeholder}</span>}
        <span aria-hidden className="ui-inline-edit__hint">
          <Icon name="edit" size={11} />
        </span>
      </button>
    );
  }

  return (
    <input
      aria-label={ariaLabel}
      className="ui-inline-edit__input"
      onBlur={commit}
      onChange={(event) => setDraft(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") commit();
        if (event.key === "Escape") {
          setDraft(value);
          setEditing(false);
        }
      }}
      ref={inputRef}
      value={draft}
    />
  );
}
