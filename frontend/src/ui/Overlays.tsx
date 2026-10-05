/** Capas — popover, menú contextual y cajón. Z según la escala §3.4;
 * posicionamiento anclado al invocador; Esc y clic fuera cierran. */
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

/* ---------- Popover ---------- */

/** Panel flotante anclado a un invocador — contenido breve de apoyo
 * (trazas, detalles, formularios cortos). Esc/cierran con clic fuera. */
export function Popover({
  anchorRef,
  onClose,
  children,
  side = "bottom",
}: {
  anchorRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  children: ReactNode;
  side?: "bottom" | "top";
}): JSX.Element {
  const panelRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    const panel = panelRef.current;
    if (!anchor || !panel) return;
    const rect = anchor.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const top =
      side === "top"
        ? rect.top + window.scrollY - panelRect.height - 8
        : rect.bottom + window.scrollY + 8;
    const left = Math.max(
      8,
      Math.min(rect.left + window.scrollX, window.innerWidth - panelRect.width - 8),
    );
    setPos({ top, left });
  }, [anchorRef, side]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointer = (event: MouseEvent) => {
      const panel = panelRef.current;
      const anchor = anchorRef.current;
      if (
        panel &&
        !panel.contains(event.target as Node) &&
        anchor &&
        !anchor.contains(event.target as Node)
      ) {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [anchorRef, onClose]);

  return createPortal(
    <div
      className="ui-popover"
      ref={panelRef}
      role="dialog"
      style={pos ? { top: pos.top, left: pos.left } : { visibility: "hidden" }}
    >
      {children}
    </div>,
    document.body,
  );
}

/* ---------- Menu / ContextMenu ---------- */

export type MenuItem = {
  key: string;
  label: ReactNode;
  shortcut?: string;
  disabled?: boolean;
  danger?: boolean;
  onSelect?: () => void;
};

/** Menú de acciones — el invocador decide su superficie (popover anclado
 * o posición de puntero). Navegación por flechas, Enter selecciona. */
export function Menu({ items, onClose }: { items: MenuItem[]; onClose: () => void }): JSX.Element {
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])')
      ?.focus();
  }, []);
  const enabled = items.filter((item) => !item.disabled);
  return (
    <ul
      className="ui-menu"
      onKeyDown={(event) => {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setActive((i) => Math.min(i + 1, enabled.length - 1));
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          setActive((i) => Math.max(i - 1, 0));
        } else if (event.key === "Enter" && enabled[active]) {
          event.preventDefault();
          enabled[active].onSelect?.();
          onClose();
        } else if (event.key === "Escape") {
          onClose();
        }
      }}
      ref={listRef}
      role="menu"
      tabIndex={-1}
    >
      {items.map((item) => {
        const index = enabled.indexOf(item);
        return (
          <li key={item.key} role="none">
            <button
              aria-disabled={item.disabled || undefined}
              className={`ui-menu__item${item.danger ? " is-danger" : ""}${
                index === active ? " is-active" : ""
              }`}
              disabled={item.disabled}
              onClick={() => {
                item.onSelect?.();
                onClose();
              }}
              onMouseEnter={() => setActive(index)}
              role="menuitem"
              type="button"
            >
              <span className="ui-menu__label">{item.label}</span>
              {item.shortcut ? <kbd className="ui-menu__key">{item.shortcut}</kbd> : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Menú contextual en la posición del puntero — uso típico: clic derecho
 * sobre una fila/entidad del lienzo. */
export function ContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number;
  y: number;
  items: MenuItem[];
  onClose: () => void;
}): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);
  return createPortal(
    <div className="ui-context-menu" ref={ref} style={{ top: y, left: x }}>
      <Menu items={items} onClose={onClose} />
    </div>,
    document.body,
  );
}

/* ---------- Drawer ---------- */

const DrawerTitleContext = createContext<string>("");

/** Cajón lateral — flujo que necesita más espacio que un popover pero sin
 * abandonar la página. z-drawer, entra por la derecha con t-spatial. */
export function Drawer({
  title,
  onClose,
  children,
  footer,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}): JSX.Element {
  const titleId = useContext(DrawerTitleContext) || "ui-drawer-title";
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    panelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="ui-drawer-scrim" onClick={onClose} role="presentation">
      <aside
        aria-labelledby={titleId}
        aria-modal="true"
        className="ui-drawer"
        onClick={(event) => event.stopPropagation()}
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="ui-drawer__head">
          <h2 className="ui-drawer__title" id={titleId}>
            {title}
          </h2>
          <button aria-label="Cerrar" className="ui-drawer__close" onClick={onClose} type="button">
            ×
          </button>
        </header>
        <div className="ui-drawer__body">{children}</div>
        {footer ? <footer className="ui-drawer__foot">{footer}</footer> : null}
      </aside>
    </div>,
    document.body,
  );
}
