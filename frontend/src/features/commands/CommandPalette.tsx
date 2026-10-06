import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import "./commands.css";

import { ApiError } from "../../api/apiMutator";
import { globalSearch } from "../../api/generated/dekopen";
import type { SearchResult } from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { MOD_K_HINT } from "../../platform";
import { useCommandSurface } from "./registry";
import type { CommandParam, ResolvedCommand } from "./types";

export interface NavCommandItem {
  to: string;
  label: string;
}

interface Listed {
  key: string;
  title: string;
  hint?: string;
  run(): void;
}

function normalize(value: string): string {
  return value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

function matches(query: string, title: string, keywords: string[] = []): boolean {
  if (!query) return true;
  const haystack = normalize([title, ...keywords].join(" "));
  return normalize(query)
    .split(/\s+/)
    .every((token) => haystack.includes(token));
}

// §7: record results ride the same list as commands — the group chip keeps
// them unmistakable, navigation is deterministic, nothing is re-ranked.
const SEARCH_GROUP_LABEL: Record<string, TranslationKey> = {
  projects: "search.groupProjects",
  clients: "search.groupClients",
  positions: "search.groupPositions",
  systems: "search.groupSystems",
  articles: "search.groupArticles",
  orders: "search.groupOrders",
  remnants: "search.groupRemnants",
  receipts: "search.groupReceipts",
  documents: "search.groupDocuments",
  inventory: "search.groupInventory",
};

export function CommandPalette({
  navItems,
  onNavigate,
  organizationId = null,
  openRequested = 0,
}: {
  navItems: NavCommandItem[];
  onNavigate(to: string): void;
  organizationId?: string | null;
  /** Incremental open signal — the topbar search entry pokes the palette open
   * the same way ⌘K toggles it. */
  openRequested?: number;
}): JSX.Element | null {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [pending, setPending] = useState<{
    command: ResolvedCommand;
    paramIndex: number;
    args: Record<string, string>;
  } | null>(null);
  const [invalidParam, setInvalidParam] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const searchSeq = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const paletteRef = useRef<HTMLDivElement>(null);
  const surface = useCommandSurface();

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setCursor(0);
    setPending(null);
    setSearchResults([]);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((previous) => !previous);
      } else if (event.key === "/" && !open) {
        // Chrome owns Ctrl+K while the omnibox has focus — "/" stays reachable.
        const target = event.target as HTMLElement | null;
        const inField =
          target instanceof HTMLElement &&
          (target.tagName === "INPUT" ||
            target.tagName === "TEXTAREA" ||
            target.tagName === "SELECT" ||
            target.isContentEditable);
        if (!inField) {
          event.preventDefault();
          setOpen(true);
        }
      } else if (event.key === "Escape" && open) {
        event.preventDefault();
        if (pending) {
          setPending(null);
          setQuery("");
          setCursor(0);
          setInvalidParam(false);
        } else close();
      } else if (event.key === "Tab" && open) {
        // aria-modal obliges a focus trap: cycle Tab/Shift+Tab inside the
        // palette (the input is the only tabbable — options use
        // aria-activedescendant).
        const root = paletteRef.current;
        const focusables = root
          ? Array.from(root.querySelectorAll<HTMLElement>("input, button:not([disabled])"))
          : [];
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (!first || !last) {
          event.preventDefault();
          return;
        }
        const active = document.activeElement;
        const outside = !root?.contains(active);
        if (event.shiftKey ? active === first || outside : active === last || outside) {
          event.preventDefault();
          (event.shiftKey ? last : first).focus();
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, pending, close]);

  useEffect(() => {
    if (openRequested > 0) setOpen(true);
  }, [openRequested]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open, pending]);

  // Debounced global search — results land in `searchResults` and merge into
  // the same navigable list below local commands/navigation.
  useEffect(() => {
    const needle = query.trim();
    if (!open || pending || !organizationId || needle.length < 2) {
      setSearchResults([]);
      return;
    }
    const seq = ++searchSeq.current;
    const timer = window.setTimeout(() => {
      void globalSearch({ q: needle }, { headers: { "X-Organization-ID": organizationId } })
        .then((response) => {
          if (response.status !== 200) throw new ApiError(response.status, response.data);
          if (searchSeq.current === seq) setSearchResults(response.data.results);
        })
        .catch(() => {
          if (searchSeq.current === seq) setSearchResults([]);
        });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, open, pending, organizationId]);

  const items = useMemo<Listed[]>(() => {
    const listed: Listed[] = [];
    for (const command of surface?.commands ?? []) {
      if (!matches(query, command.title, command.keywords)) continue;
      listed.push({
        key: command.id,
        title: command.title,
        hint: command.params?.[0] ? t("cmd.needsParams") : undefined,
        run: () => {
          if (command.params?.length) {
            setPending({ command, paramIndex: 0, args: {} });
            setQuery("");
            setCursor(0);
            setInvalidParam(false);
          } else {
            command.run({});
            close();
          }
        },
      });
    }
    for (const item of navItems) {
      if (!matches(query, item.label, ["ir", "abrir", "navegar", item.to])) continue;
      listed.push({
        key: `nav.${item.to}`,
        title: `${t("cmd.goTo")} ${item.label}`,
        run: () => {
          onNavigate(item.to);
          close();
        },
      });
    }
    for (const result of searchResults) {
      const group = t(SEARCH_GROUP_LABEL[result.group] ?? "search.groupResults");
      listed.push({
        key: `search.${result.group}.${result.id}`,
        title: result.title,
        hint: result.subtitle ? `${group} · ${result.subtitle}` : group,
        run: () => {
          onNavigate(result.path);
          close();
        },
      });
    }
    return listed;
  }, [query, surface, navItems, onNavigate, close, searchResults]);

  if (!open) return null;

  const currentParam: CommandParam | undefined = pending
    ? pending.command.params?.[pending.paramIndex]
    : undefined;

  const filteredOptions: { value: string; label: string }[] =
    pending && currentParam?.kind === "choice"
      ? currentParam.options.filter((option) => matches(query, option.label, [option.value]))
      : [];

  function advanceParam(value: string): void {
    if (!pending || !currentParam) return;
    const args = { ...pending.args, [currentParam.id]: value };
    const nextIndex = pending.paramIndex + 1;
    if ((pending.command.params?.length ?? 0) > nextIndex) {
      setPending({ command: pending.command, paramIndex: nextIndex, args });
      setQuery("");
      setCursor(0);
      setInvalidParam(false);
    } else {
      pending.command.run(args);
      close();
    }
  }

  function onInputKeyDown(event: React.KeyboardEvent): void {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      const limit = pending ? filteredOptions.length - 1 : items.length - 1;
      setCursor((value) => Math.min(value + 1, Math.max(limit, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (pending && currentParam) {
        if (currentParam.kind === "number") {
          const raw = (event.target as HTMLInputElement).value.trim();
          if (!raw) return;
          const value = currentParam.validate ? currentParam.validate(raw) : raw;
          if (value === null) {
            setInvalidParam(true);
            return;
          }
          advanceParam(value);
        } else {
          const option = filteredOptions[Math.min(cursor, filteredOptions.length - 1)];
          if (option) advanceParam(option.value);
        }
        return;
      }
      const item = items[Math.min(cursor, items.length - 1)];
      item?.run();
    }
  }

  return (
    <div
      className="command-palette-overlay"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        ref={paletteRef}
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label={t("cmd.palette")}
      >
        <div className="command-palette-input">
          <input
            ref={inputRef}
            value={query}
            placeholder={pending && currentParam ? currentParam.label : t("cmd.placeholder")}
            aria-label={pending && currentParam ? currentParam.label : t("cmd.placeholder")}
            aria-invalid={invalidParam || undefined}
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-results"
            aria-activedescendant={
              pending && currentParam
                ? filteredOptions.length > 0
                  ? `command-palette-option-${Math.min(cursor, filteredOptions.length - 1)}`
                  : undefined
                : items.length > 0
                  ? `command-palette-option-${Math.min(cursor, items.length - 1)}`
                  : undefined
            }
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
              setInvalidParam(false);
            }}
            onKeyDown={onInputKeyDown}
          />
          <kbd>{MOD_K_HINT}</kbd>
          <kbd>/</kbd>
        </div>
        {pending && currentParam ? (
          <ul className="command-palette-list" role="listbox" id="command-palette-results">
            {currentParam.kind === "choice" ? (
              filteredOptions.map((option, index) => (
                <li key={option.value}>
                  <button
                    type="button"
                    tabIndex={-1}
                    id={`command-palette-option-${index}`}
                    role="option"
                    aria-selected={index === cursor}
                    className={`command-palette-item${index === cursor ? " active" : ""}`}
                    onMouseEnter={() => setCursor(index)}
                    onClick={() => advanceParam(option.value)}
                  >
                    {option.label}
                  </button>
                </li>
              ))
            ) : (
              <li className="command-palette-hint">
                {currentParam.unit
                  ? `${currentParam.label} (${currentParam.unit})`
                  : currentParam.label}
                {currentParam.defaultValue ? ` · ${currentParam.defaultValue}` : ""}
              </li>
            )}
            {currentParam.kind === "choice" && filteredOptions.length === 0 && (
              <li className="command-palette-hint">{t("cmd.noResults")}</li>
            )}
            {invalidParam && (
              <li className="command-palette-hint command-palette-invalid">
                {t("cmd.invalidValue")}
              </li>
            )}
          </ul>
        ) : (
          <>
            <ul className="command-palette-list" role="listbox" id="command-palette-results">
              {items.map((item, index) => (
                <li key={item.key}>
                  <button
                    type="button"
                    tabIndex={-1}
                    id={`command-palette-option-${index}`}
                    role="option"
                    aria-selected={index === cursor}
                    className={`command-palette-item${index === cursor ? " active" : ""}`}
                    onMouseEnter={() => setCursor(index)}
                    onClick={() => item.run()}
                  >
                    <span>{item.title}</span>
                    {item.hint && <small>{item.hint}</small>}
                  </button>
                </li>
              ))}
              {items.length === 0 && <li className="command-palette-hint">{t("cmd.noResults")}</li>}
            </ul>
            {(() => {
              const described = (surface?.commands ?? [])
                .find((command) => command.id === items[cursor]?.key && !command.params?.length)
                ?.describe?.({});
              return described ? <p className="command-palette-describe">{described}</p> : null;
            })()}
          </>
        )}
      </div>
    </div>
  );
}
