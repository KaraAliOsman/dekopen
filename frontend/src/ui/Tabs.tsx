import { matchPath, NavLink, useLocation } from "react-router-dom";
import { useCallback, useRef, type KeyboardEvent } from "react";

/** Tab strip — selection is legible without color (underline + weight +
 * aria-selected). `to` makes each tab a real route (URL is the state, so
 * reload/share keep the tab); omit `to` for in-page state tabs. */
export type TabItem = {
  id: string;
  label: string;
  /** When present the tab is a NavLink to this route. */
  to?: string;
  /** End-match for route tabs (default true so /a doesn't light /a/b). */
  end?: boolean;
  disabled?: boolean;
};

export function Tabs({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem[];
  /** Required for in-page (non-route) tabs. */
  value?: string;
  onChange?: (id: string) => void;
  label: string;
}): JSX.Element {
  // State-only tabs never touch the router, so the strip works in tests and
  // embedded contexts that mount without one.
  if (items.some((item) => item.to)) {
    return <RoutedTabs items={items} label={label} />;
  }
  return <StateTabs items={items} label={label} onChange={onChange} value={value} />;
}

function useRovingFocus(): {
  listRef: React.RefObject<HTMLDivElement>;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
} {
  const listRef = useRef<HTMLDivElement>(null);
  const onKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const tabs = Array.from(
      listRef.current?.querySelectorAll<HTMLElement>('[role="tab"]:not([aria-disabled="true"])') ??
        [],
    );
    const index = tabs.indexOf(document.activeElement as HTMLElement);
    if (index < 0) return;
    event.preventDefault();
    const next =
      event.key === "ArrowRight"
        ? tabs[(index + 1) % tabs.length]
        : tabs[(index - 1 + tabs.length) % tabs.length];
    next?.focus();
    next?.click();
  }, []);
  return { listRef, onKeyDown };
}

function StateTabs({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem[];
  value?: string;
  onChange?: (id: string) => void;
  label: string;
}): JSX.Element {
  const { listRef, onKeyDown } = useRovingFocus();
  return (
    <div aria-label={label} className="ui-tabs" onKeyDown={onKeyDown} ref={listRef} role="tablist">
      {items.map((item) => (
        <button
          aria-disabled={item.disabled || undefined}
          aria-selected={value === item.id}
          className={`ui-tab${value === item.id ? " is-active" : ""}`}
          disabled={item.disabled || undefined}
          key={item.id}
          onClick={() => onChange?.(item.id)}
          role="tab"
          tabIndex={value === item.id ? 0 : -1}
          type="button"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function RoutedTabs({ items, label }: { items: TabItem[]; label: string }): JSX.Element {
  const { listRef, onKeyDown } = useRovingFocus();
  const { pathname } = useLocation();
  return (
    <div aria-label={label} className="ui-tabs" onKeyDown={onKeyDown} ref={listRef} role="tablist">
      {items.map((item) => (
        <NavLink
          aria-disabled={item.disabled || undefined}
          aria-selected={routeActive(item, pathname)}
          className={({ isActive }) => `ui-tab${isActive ? " is-active" : ""}`}
          end={item.end ?? true}
          key={item.id}
          role="tab"
          tabIndex={routeActive(item, pathname) ? 0 : -1}
          to={item.to ?? ""}
        >
          {item.label}
        </NavLink>
      ))}
    </div>
  );
}

function routeActive(item: TabItem, pathname: string): boolean {
  if (!item.to) return false;
  return (
    matchPath({ path: item.to, end: item.end ?? true }, pathname) !== null ||
    // Nested-mount safety: match a trailing segment too.
    matchPath({ path: `*/${item.to.replace(/^\//, "")}`, end: item.end ?? true }, pathname) !== null
  );
}
