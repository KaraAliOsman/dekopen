import type { ProductJson } from "../canvas/productEditing";
import type { TranslationKey } from "../../i18n/es-CL";

/** The validated op contract returned by POST /positions/<id>/design-assist/.
 * The server has already bounds-checked every index, enum and range against
 * the actual assembly; the client still refuses unknown ops so a newer
 * backend can never silently drive an older editor. */
export type DesignOp = { op: string } & Record<string, unknown>;

/** Resolution state threaded through an op sequence: the real entity ids that
 * earlier structural ops created, in creation order — what the wire's
 * synthetic `added_m{n}`/`added_c{n}` refs point at. */
export interface DesignOpState {
  addedModules: string[];
  addedCouplings: string[];
  /** The product as the op sequence's author saw it. Numeric addresses and
   * `m{n}`/`c{n}` positional refs resolve against THIS list — the same
   * original-index contract the backend validator applies — never against
   * the live product an earlier structural op already mutated. */
  origin?: ProductJson;
}

/** Editor tools a command may arm. */
export type EditorTool = "select" | "split_v" | "split_h";

/** String args collected by surfaces (palette fields, AI wire ops). */
export type CommandArgs = Record<string, string>;

/** Catalog options a command may offer as choices. */
export interface CommandCatalog {
  glassThicknesses: string[];
  glassSkus: string[];
  couplerSkus: string[];
  panelSkus: string[];
  mullionSkus: Partial<Record<"SPLIT_V" | "SPLIT_H", string>>;
}

/** Everything a command may touch — product state plus the editor affordances
 * (selection, tool arming, history). Non-editor surfaces pass what they have;
 * commands guard optional affordances. */
export interface CommandContext {
  product: ProductJson;
  selection: string | null;
  catalog: CommandCatalog;
  disabled: boolean;
  commit(next: ProductJson): void;
  select(id: string | null): void;
  setTool?(tool: EditorTool): void;
  /** Focus the design assistant's prompt (editor affordance — UI commands
   * like "Preguntar a DEKOPEN" and context-menu entries land here). */
  focusAssistant?(): void;
  undo?(): void;
  redo?(): void;
  canUndo?: boolean;
  canRedo?: boolean;
  /** Spec clipboard (power-user copy/apply): module carries the whole bay
   * structure, bay carries transferable spec fields only. */
  specClipboard?: SpecClipboard | null;
  writeSpecClipboard?(clipboard: SpecClipboard): void;
  /** The last mutating command that ran (id + args) — powers edit.repeat. */
  lastMutation?: { specId: string; args: CommandArgs } | null;
  recordMutation?(specId: string, args: CommandArgs): void;
}

/** What "Copiar especificación" stores for "Aplicar especificación". */
export type SpecClipboard =
  | { kind: "module"; tree: import("../canvas/intentEditing").IntentNode }
  | { kind: "bay"; spec: Partial<import("../canvas/intentEditing").IntentNode> };

/** A parameter a surface collects before running a command. Number params
 * accept the engine's decimal-string contract; choice params render as the
 * palette's own filtered list. */
export type CommandParam =
  | {
      kind: "number";
      id: string;
      label: string;
      unit?: string;
      defaultValue?: string;
      /** Normalize or reject the typed value (returns the committed string or
       * null to keep the parameter step open with an invalid hint). */
      validate?(raw: string): string | null;
    }
  | {
      kind: "choice";
      id: string;
      label: string;
      options: { value: string; label: string }[];
    };

/** The ONE command definition every surface shares: palette rows, keyboard
 * shortcuts, context menus and AI ops all dispatch through `apply`/`run`.
 * `ai` binds the wire op a backend-validated proposal carries. */
export interface CommandSpec {
  id: string;
  title: TranslationKey;
  keywords?: string[];
  /** Global keyboard shortcut — "mod+z", "mod+shift+z", "v", "delete".
   * mod = Ctrl (Windows/Linux) or Meta (macOS). Only param-less commands
   * may bind one. A list binds several keys to the same command (first is
   * the displayed hint). */
  shortcut?: string | readonly string[];
  /** Params the palette collects in order before running. */
  params?(ctx: CommandContext): CommandParam[];
  /** Listing predicate — absent or true means the command is offered. */
  applicable?(ctx: CommandContext): boolean;
  /** Mark a `run` command that mutates product state (history, dispatched
   * removes). While `ctx.disabled` these are withheld like `apply` commands. */
  mutates?: boolean;
  /** Human preview shown under the palette row / in AI proposals. */
  describe?(args: CommandArgs): string;
  /** Product mutation: returns the next product (never commits itself). */
  apply?(ctx: CommandContext, args: CommandArgs): ProductJson;
  /** Follow-up side effects after an apply commits — selection moves to the
   * created/affected element. `before`/`next` are the committed pair; the
   * ctx still carries the pre-commit product. AI `apply` paths skip this. */
  postCommit?(ctx: CommandContext, before: ProductJson, next: ProductJson, args: CommandArgs): void;
  /** Non-mutating commands (tool arming, history, view). */
  run?(ctx: CommandContext, args: CommandArgs): void;
  /** AI exposure: the wire op name plus a decoder back into args. `state`
   * threads the ids minted by earlier structural ops in the same sequence so
   * synthetic refs (added_m1, added_c2) resolve to the real modules they
   * produced. */
  ai?: {
    op: string;
    decode(op: DesignOp, product: ProductJson, state?: DesignOpState): CommandArgs | null;
  };
}

/** A command resolved against the live context — what the palette and other
 * surfaces render and run. `run` dispatches through `runCommand`. */
export interface ResolvedCommand {
  id: string;
  /** es-CL title shown in the palette list. */
  title: string;
  /** Extra searchable terms (synonyms, English, object kinds). */
  keywords?: string[];
  /** Primary keyboard shortcut (spec format) — rendered as the palette
   * hint. `shortcuts` carries every bound key for the dispatcher. */
  shortcut?: string;
  shortcuts?: readonly string[];
  /** Parameters collected sequentially before `run`. */
  params?: CommandParam[];
  /** A short preview of what the command will change. Rendered under the list
   * while the command is selected. */
  describe?(args: CommandArgs): string;
  run(args: CommandArgs): void;
}

/** A surface's live command list (rebuilt when product/selection change). */
export interface CommandSurface {
  commands: ResolvedCommand[];
}

export type { TranslationKey };
