/** CommandPalette — Ctrl+K abre, flechas navegan, Enter ejecuta. El
 * registro es extensible: las superficies inscriben sus comandos y la
 * paleta los encuentra por nombre y palabras clave. P03 conecta los
 * comandos reales del producto; aquí vive la mecánica. */
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { t } from "../i18n/es-CL";

export type Command = {
  key: string;
  /** Nombre del comando — el usuario lo teclea para encontrarlo. */
  title: string;
  /** Palabras extra que también lo encuentran. */
  keywords?: string[];
  /** Sección para agrupar («Proyecto», «Navegación»…). */
  section?: string;
  shortcut?: string;
  run: () => void;
};

type Registry = { commands: Command[] };

const registry: Registry = { commands: [] };
const listeners = new Set<() => void>();

export function registerCommand(command: Command): () => void {
  registry.commands = [...registry.commands, command];
  listeners.forEach((fn) => fn());
  return () => {
    registry.commands = registry.commands.filter((c) => c.key !== command.key);
    listeners.forEach((fn) => fn());
  };
}

export function registerCommands(commands: Command[]): () => void {
  const offs = commands.map(registerCommand);
  return () => offs.forEach((off) => off());
}

function useCommands(): Command[] {
  const [, bump] = useState(0);
  useEffect(() => {
    const fn = () => bump((v) => v + 1);
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  }, []);
  return registry.commands;
}

/** Abre/cierra la paleta con Ctrl+K (o Cmd+K) en cualquier parte. */
export function usePaletteShortcut(onToggle: () => void): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        // Ctrl+K abre la paleta desde cualquier parte, incluidos campos:
        // es el punto de entrada único a comandos (§3.6 interacción).
        event.preventDefault();
        onToggle();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onToggle]);
}

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}): JSX.Element | null {
  const commands = useCommands();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      inputRef.current?.focus();
    }
  }, [open]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((cmd) =>
      [cmd.title, ...(cmd.keywords ?? [])].some((w) => w.toLowerCase().includes(q)),
    );
  }, [commands, query]);
  if (!open) return null;
  const run = (cmd: Command) => {
    onClose();
    cmd.run();
  };
  return createPortal(
    <div className="ui-palette-scrim" onClick={onClose} role="presentation">
      <div
        aria-label={t("ui.palettePlaceholder")}
        aria-modal="true"
        className="ui-palette"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <input
          aria-activedescendant={
            filtered[active] ? `ui-palette-${filtered[active].key}` : undefined
          }
          aria-autocomplete="list"
          aria-expanded
          className="ui-palette__input"
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((i) => Math.min(i + 1, filtered.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            } else if (event.key === "Enter" && filtered[active]) {
              event.preventDefault();
              run(filtered[active]);
            } else if (event.key === "Escape") {
              onClose();
            }
          }}
          placeholder={t("ui.palettePlaceholder")}
          ref={inputRef}
          role="combobox"
          type="text"
        />
        <ul className="ui-palette__list" role="listbox">
          {filtered.length === 0 ? (
            <li className="ui-palette__empty">{t("ui.paletteEmpty")}</li>
          ) : (
            filtered.map((cmd, index) => (
              <li
                aria-selected={index === active}
                className={`ui-palette__item${index === active ? " is-active" : ""}`}
                id={`ui-palette-${cmd.key}`}
                key={cmd.key}
                onClick={() => run(cmd)}
                onMouseEnter={() => setActive(index)}
                role="option"
              >
                <span className="ui-palette__title">{cmd.title}</span>
                {cmd.section ? <span className="ui-palette__section">{cmd.section}</span> : null}
                {cmd.shortcut ? <kbd className="ui-palette__key">{cmd.shortcut}</kbd> : null}
              </li>
            ))
          )}
        </ul>
      </div>
    </div>,
    document.body,
  );
}

/** Monta la paleta y su atajo — un solo punto en el shell de la app. */
export function PaletteHost(): JSX.Element {
  const [open, setOpen] = useState(false);
  usePaletteShortcut(() => setOpen((v) => !v));
  return <CommandPalette onClose={() => setOpen(false)} open={open} />;
}
