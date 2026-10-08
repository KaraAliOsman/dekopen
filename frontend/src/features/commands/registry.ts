import { useEffect, useSyncExternalStore } from "react";

import { t } from "../../i18n/es-CL";
import type {
  CommandArgs,
  CommandContext,
  CommandSpec,
  CommandSurface,
  DesignOp,
  DesignOpState,
  ResolvedCommand,
} from "./types";
import type { ProductJson } from "../canvas/productEditing";

/** One registered command surface at a time (the editor contributes its
 * commands while mounted). Listeners fire on register/unregister so an open
 * palette always reflects the live surface. */
let current: CommandSurface | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Register the surface's commands while the surface is mounted. Pass a
 * memoized `CommandSurface` — the palette reads it directly. */
export function useRegisterCommands(surface: CommandSurface | null): void {
  useEffect(() => {
    if (!surface) return;
    current = surface;
    emit();
    return () => {
      if (current === surface) {
        current = null;
        emit();
      }
    };
  }, [surface]);
}

export function useCommandSurface(): CommandSurface | null {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );
}

/** Resolve the registry's specs against the live context into the surface
 * list: titles translated, params collected, `run` bound to the single
 * dispatch path. */
export function resolveCommands(ctx: CommandContext, specs: CommandSpec[]): ResolvedCommand[] {
  return specs
    .filter(
      // Inapplicable commands are never offered anywhere — palette, context
      // menu and shortcuts share this list. A mutating command is also
      // unavailable while the editor is disabled (saving, busy).
      (spec) =>
        spec.applicable?.(ctx) !== false &&
        !(ctx.disabled && (spec.apply !== undefined || spec.mutates === true)),
    )
    .map((spec) => {
      const shortcuts =
        spec.shortcut === undefined
          ? undefined
          : Array.isArray(spec.shortcut)
            ? [...spec.shortcut]
            : [spec.shortcut];
      return {
        id: spec.id,
        title: t(spec.title),
        keywords: spec.keywords,
        shortcut: shortcuts?.[0],
        shortcuts,
        params: spec.params?.(ctx),
        describe: spec.describe,
        preview:
          spec.apply === undefined || ctx.previewProposal === undefined
            ? undefined
            : (args: CommandArgs) => {
                try {
                  const next = spec.apply!(ctx, args);
                  // A refused/no-op apply has nothing to preview — run the
                  // command through the normal path so its postCommit or
                  // silent no-op behaves exactly like a direct dispatch.
                  if (next === ctx.product) return false;
                  ctx.previewProposal!({
                    product: next,
                    apply: () => runCommand(ctx, spec, args),
                  });
                  return true;
                } catch {
                  // apply may throw for edge args (out-of-range mm) — the
                  // normal path surfaces that honestly; previewing must
                  // never fail worse than committing would.
                  return false;
                }
              },
        run: (args: CommandArgs) => runCommand(ctx, spec, args),
      };
    });
}

/** Execute a command through the single shared path: mutation commands commit
 * `apply`'s result (one undoable transaction), non-mutating commands run their
 * own effect. Palette, shortcuts, context menus and AI all land here. */
export function runCommand(ctx: CommandContext, spec: CommandSpec, args: CommandArgs = {}): void {
  if (spec.apply) {
    const before = ctx.product;
    const next = spec.apply(ctx, args);
    // A no-op apply (stale target, refused condition) commits nothing and
    // must not overwrite the repeatable-mutation history.
    if (next === before) return;
    ctx.commit(next);
    ctx.recordMutation?.(spec.id, args);
    spec.postCommit?.(ctx, before, next, args);
  } else {
    spec.run?.(ctx, args);
  }
}

/** Match a spec shortcut ("mod+shift+z", "v", "delete") against a keyboard
 * event. mod = Ctrl or Meta so one binding covers every platform. */
export function shortcutMatches(shortcut: string, event: KeyboardEvent): boolean {
  const parts = shortcut.toLowerCase().split("+");
  const key = parts[parts.length - 1]!;
  const wantMod = parts.includes("mod");
  const wantShift = parts.includes("shift");
  const wantAlt = parts.includes("alt");
  // AltGr produces Ctrl+Alt on several layouts ("|" is AltGr+1 in es-CL) —
  // those modifier bits belong to the character, not to a chord.
  const altGr = event.getModifierState?.("AltGr") === true;
  const modHeld = (event.ctrlKey || event.metaKey) && !altGr;
  const altHeld = event.altKey && !altGr;
  if (wantMod !== modHeld) return false;
  if (wantAlt !== altHeld) return false;
  // Punctuation keys can only be produced WITH Shift on many layouts
  // ("?" is Shift+/, "|" is Shift+\) — for those, Shift belongs to the
  // character. Letters/digits keep strict shift matching (Shift+A ≠ A).
  const punct = key.length === 1 && !/[a-z0-9]/.test(key);
  if (wantShift !== event.shiftKey && !punct) return false;
  const eventKey = event.key.toLowerCase();
  if (key === "del") return eventKey === "delete" || eventKey === "backspace";
  if (key === "esc") return eventKey === "escape";
  return key === eventKey;
}

/** Human-readable form of a spec shortcut for hints ("⌘⇧Z" / "Ctrl+Mayús+Z"
 * depending on platform — keep the ASCII form everywhere for legibility). */
export function formatShortcut(shortcut: string): string {
  return shortcut
    .split("+")
    .map((part) => {
      if (part === "mod") return "Ctrl";
      if (part === "shift") return "Mayús";
      if (part === "alt") return "Alt";
      if (part === "del") return "Supr";
      if (part === "esc") return "Esc";
      return part.length === 1 ? part.toUpperCase() : part;
    })
    .join("+");
}

/** Global keyboard dispatch: every command carrying a `shortcut` fires when
 * its binding matches — unless the user is typing in a field. Only
 * param-less commands qualify (param collection is the palette's job).
 * `reserved` lists every chord the surface advertises anywhere (menus,
 * palette): a reserved chord whose command is momentarily inapplicable is
 * still swallowed, so e.g. Ctrl+D never falls through to the browser's
 * bookmark dialog while the editor teaches the binding. */
export function useCommandShortcuts(
  surface: CommandSurface | null,
  reserved: readonly string[] = [],
): void {
  useEffect(() => {
    if (!surface) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest("input, textarea, select, [contenteditable='true']")
      ) {
        return;
      }
      for (const command of surface.commands) {
        if (command.params?.length) continue;
        const bindings = command.shortcuts ?? (command.shortcut ? [command.shortcut] : []);
        if (bindings.some((binding) => shortcutMatches(binding, event))) {
          event.preventDefault();
          command.run({});
          return;
        }
      }
      if (reserved.some((binding) => shortcutMatches(binding, event))) {
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [surface, reserved]);
}

/** Apply one backend-validated wire op through the shared command table. The
 * op decodes to the same args a palette would collect, then hits the same
 * `apply` a human action uses. Unknown/undecodable ops are refused. Several
 * specs may share an op name (e.g. add_unit left/right) — the first whose
 * decoder accepts the op wins. */
export function applyDesignOpOn(
  specs: CommandSpec[],
  product: ProductJson,
  op: DesignOp,
  state?: DesignOpState,
): ProductJson {
  for (const spec of specs) {
    if (spec.ai?.op !== op.op || !spec.apply) continue;
    const args = spec.ai.decode(op, product, state);
    if (args === null) continue;
    const ctx: CommandContext = {
      product,
      selection: null,
      catalog: {
        glassThicknesses: [],
        glassSkus: [],
        couplerSkus: [],
        panelSkus: [],
        mullionSkus: {},
      },
      // IA2 — los comandos de división miden con la geometría de miembros
      // del sistema: viaja por el estado de la secuencia (AssistantPanel la
      // inyecta desde resolveMembers(options)).
      ...(state?.members ? { members: state.members } : {}),
      disabled: false,
      commit: () => {},
      select: () => {},
    };
    return spec.apply(ctx, args);
  }
  return product;
}
