/** Platform-adapted shortcut hint for the palette/mod key — ⌘ on Apple
 * platforms, Ctrl elsewhere, so the hint never contradicts the modifier the
 * listener actually requires (review m7). */
const APPLE = /Mac|iPhone|iPad|iPod/.test(
  typeof navigator === "undefined" ? "" : (navigator.userAgent ?? navigator.platform ?? ""),
);
/** Bare modifier glyph — used when composing hints like `⌘⇧Z`. */
export const MOD_KEY_HINT = APPLE ? "⌘" : "Ctrl ";
export const MOD_K_HINT = APPLE ? "⌘K" : "Ctrl K";
