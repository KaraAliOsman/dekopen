# DEKOPEN canvas editor — UX audit vs. modern creative-software patterns

**Scope:** `frontend/src/features/{canvas,inspector,projects}` at commit `566416e`.
**Reference set:** Figma, Linear, Notion, Blender — plus CAD-adjacent web canvases (Shapr3D,
Onshape, Excalidraw, tldraw). This is a gap audit against the interaction study, not a re-spec:
status = ✅ adopted · ◐ partial · ✗ missing, each with the mechanic the references ship.

**Verdict:** DEKOPEN has adopted the *gesture* layer unusually well (click-to-edit dimensions,
preview-vs-commit drag, glyph pickers, issue chips) but is missing the *navigation* layer
entirely — no zoom, pan, fit, tree, palette, or multi-select exists anywhere in the codebase.
The editor can edit one module precisely but cannot *get around* a real product. For a
fenestration professional quoting 3–6-module bows and tall doors, that inversion is the audit
in one line.

---

## A. What DEKOPEN has already adopted (keep — most are reference-grade)

| # | Pattern | Where | Reference equivalent |
|---|---|---|---|
| 1 | **Click-to-edit dimension labels** — focus selects-all, Enter commits, Esc/blur reverts, `mm` unit ghost | `canvas/EditableDimension.tsx`, `SvgDim` in `ProductFrontSvg.tsx` | Shapr3D's core gesture: every sketch element carries a live dimension label |
| 2 | **Glyph segmented picker** — 8-way opening-type grid with `aria-pressed`, icons not words | `AssemblyEditor.tsx` opening-grid | Excalidraw segmented stroke/style groups; Figma icon toggles |
| 3 | **DraftField semantics** — commit on blur/Enter, revert on Esc, `,`→`.` normalization, unit span | `AssemblyEditor.tsx` (~L100–125), `DraftField` | Figma numeric fields |
| 4 | **Preview-vs-commit drag** — pointer capture, local preview rect + snap-guide flash, ONE typed commit on `pointerup`, Esc cancels | `CADViewportSvg.tsx` (~L74–105) | Figma resize; correct split of cheap-local-preview / engine-commit |
| 5 | **Issue chips that select their target** — click chip → canvas selection jumps to the module/coupling | `AssemblyEditor.tsx` (~L523–536) | Onshape/Blender error-navigation; the germ of two-way selection sync |
| 6 | **Hover-visible `+` add-handles** on canvas edges | `AddHandle` circles in `ProductFrontSvg.tsx` | Notion's hover-revealed `+` / `⋮⋮` block handles |
| 7 | **Canvas issue tinting** — `.has-error`/`.has-warning` classes mark the module itself, not only a list | `ProductFrontSvg.tsx`, `canvas.css` | invalid-state drawing (red/amber on the entity) |
| 8 | **Keyboard hygiene guard** — global keydown skips `input/select/textarea` targets | `ProjectPositionEditor.tsx` (~L387–422) | required pre-condition for single-key tools |
| 9 | **Undo/redo buttons + dirty tracking + unsaved-changes guard** | `ProjectPositionEditor.tsx` header, `UnsavedChangesGuard` | Linear status surfaces (partial — see B12) |
| 10 | **Ratio preset buttons** (`½`, `⅓`, `⅔`) for split offsets | `IntentEditor.tsx` | proto version of palette parameter presets |
| 11 | **Before/After diff preview** for inspection findings with Apply/Cancel | `InspectorModal.tsx` aside | rare even in pro tools — genuinely ahead |
| 12 | **role=status live regions**, `tabIndex=0` on SVG handles, aria-pressed toggles | throughout | accessibility base most canvas apps skip |

---

## B. What's missing or partial — ranked by leverage for a fenestration professional

### Tier 1 — the editor cannot navigate its own product (blocks canvas-first entirely)

| Rank | Pattern | Status | Reference mechanic | DEKOPEN today | Why it ranks here |
|---|---|---|---|---|---|
| **1** | **Viewport navigation** | ✗ | `Ctrl+wheel` zoom-to-cursor, `Space+drag`/wheel pan, `Shift+1` fit-all, `Shift+2` fit-selection, `W` zoom-to-window, zoom cluster + minimap (Figma/Excalidraw/tldraw/Onshape all agree) | Fixed `viewBox` + `preserveAspectRatio` in `CADViewportSvg`, `ProductFrontSvg`, `BowPlanSvg`; `grep` finds zero `onWheel`/zoom/pan handlers | A 4-module bow or 2400 mm door renders as a fixed-fit strip — dimension labels collide, couplings unreadable, and every other pattern below is crippled until this exists. **Nothing else can land first.** |
| **2** | **Every editable node is selectable on canvas** | ✗ | Click selects; Enter/double-click descends parent→child; Esc ascends (Figma) | Only *modules* are clickable in `ProductFrontSvg` (`.is-selected`); bays/splits are reachable ONLY via a `Vano 1/2/3` text `<select>` (`IntentEditor.tsx:192`); couplings only via plan view | The objects a fenestration pro edits most — bays, splits, glazing per bay — have no spatial identity. Selection-by-dropdown is selection ambiguity made literal. |
| **3** | **Object tree** | ✗ | Left docked panel, type icons, disclosure chevrons, two-way selection/hover sync, drag-to-reorder, severity badges (Figma layers; Blender outliner) | No tree component exists; `parametricTree` data renders only inside selects | With #1/#2 the tree is the escape hatch for occluded nodes AND the legible map of module→split→bay. Cheap to build once nodes are selectable. |
| **4** | **Dimension-first editing, completed** | ◐ | Shapr3D: labels accept math (`1200+50`, `2900/3`), `Tab` cycles fields, typing a number *while dragging* sets the drag value, `↑↓` nudges | Labels commit/revert correctly (row A1) but: no math eval, no Tab-cycle, no type-while-drag, no arrow nudges | A quoting tool lives and dies in its dimension path. The gesture exists; the 4 upgrades are days of work for the single highest-frequency action in the app. |
| **5** | **Contextual docked inspector** | ✗ | Right ~280px panel whose sections reorder by selection (Figma Design tab); modals only for true transactions | `InspectorModal.tsx:172` is a `<dialog>` that blocks the canvas with fake tab buttons; `IntentEditor.tsx` is a static 500-line form column | Blocks the canvas (modal) or ignores selection (static form) — the two failure modes the inspector pattern exists to kill. |

### Tier 2 — workflow velocity (the daily loop gets 2–5× faster)

| Rank | Pattern | Status | Reference mechanic | DEKOPEN today |
|---|---|---|---|---|
| **6** | **Searchable comboboxes for SKUs** | ✗ | Type-to-filter popover, icon/preview + spec subtitle, grouped by role; no fake `<option>Choose…` | **10 native `<select>`s:** bay `IntentEditor:192`, opening `:255`, division `:384`, template `:456`; glass thickness/glass/panel/coupler `AssemblyEditor:258/276/295/346`; system `ProjectPositionEditor:591`; coupler yes/no `InspectorModal:241` |
| **7** | **Commit-on-Enter fields, no Apply buttons** | ◐ | Field commits → immediate engine op + live preview; the commit IS the feedback | `IntentEditor` uses `<form onSubmit>` + "Aplicar dimensiones"/"Apply opening"/"Apply template" submit buttons (`:211`, `:246`, …) — two-step commit for the most common ops |
| **8** | **Snapping/inference surfacing** | ◐ | Onshape: dotted inference line + orange highlight on the related entity + constraint icon; `Shift`/`Alt` suppresses; labeled snap target | 4 px `snap-guide` rect flash, unlabeled, cleared on commit; snap toggle is a text button reading `Snap ON` (`CanvasEditor2DView.tsx:68–75`); no suppression modifier |
| **9** | **Multi-select + bulk ops** | ✗ | `Shift+click` add, `Ctrl+click` deep-select, shared bbox + per-shape bounds, `Mixed` values in fields, "N selected" status | Single-select only everywhere; no mass glazing/opening changes — changing 4 identical bays is 4 full trips through a form |
| **10** | **Command palette** | ✗ | `Ctrl+K` (Linear) / `Ctrl+/` (Figma) / `F3`-search (Blender) / `/` (Notion): scope chip, fuzzy+synonym match, context-filtered availability, parameter step, toast+Undo | Zero surface. The "typed operations" the rebuild is organized around have no keyboard front door — every op is buried in a form or missing entirely |

### Tier 3 — speed, polish, and learnability

| Rank | Pattern | Status | Reference mechanic | DEKOPEN today |
|---|---|---|---|---|
| **11** | **Keyboard map + discoverability** | ◐ | Single-key tools (`V`/`H`), `↑↓` nudge 1/`Shift` 10, `?` shortcuts sheet with used-keys highlighted, every tooltip ends `— Key`, right-click menus print `<kbd>` hints | Whole keymap = Esc / Delete / `Ctrl+Z` / `Ctrl+Y` (`ProjectPositionEditor:387–422`) + Enter/Esc on fields. No `?` sheet, no key hints in tooltips |
| **12** | **Status surfaces** | ◐ | Status *pill* (`VALID`/`INCOMPLETE`/`INVALID` chip), in-place skeletons, transient toast with `Undo` action | Prose spans: `calculando`, semaphore `<p>`, `role="status"` text lines; `savedState`/`unsaved` text at `ProjectPositionEditor:525` |
| **13** | **Orientation/grid/minimap controls** | ✗ | View-cube analog (`Front/Plan` pill, `R` to flip), `Ctrl+'` adaptive mm grid, minimap at >200% zoom | Front and Plan are separate fixed canvases; no grid, no minimap, no view switcher |
| **14** | **Density vocabulary** | ✗ | 28–32px property rows, icon+tooltip secondary actions, collapsible sections with count badges, chips for spatial data, tint-not-borders hierarchy | `<fieldset>/<legend>` groups, BOM = `<details>` + 4 bare `<table>`s (`ProjectPositionEditor:633–705`), drain holes = comma-separated regex-validated text input (`InspectorModal:225`), `<select>` for yes/no |
| **15** | **Context menus on canvas** | ✗ | Right-click → grouped menu near cursor, right-aligned `<kbd>` hints, destructive action red + last (Excalidraw/Linear) | Right-click on canvas = browser default menu |

---

## C. The ranked read — what this means for a fenestration pro

The adoption pattern is inverted vs. leverage: DEKOPEN nailed the *precision gestures*
(dimension labels, glyph pickers, preview-drag) before the *navigation substrate* they depend
on. In practical terms: the editor is good at editing a bay's number once you've already found
the bay — but finding it requires a text dropdown, the product can't be zoomed into, and there's
no map of what exists.

**Recommended order (highest leverage first, each unblocks the next):**

1. **Viewport navigation** (Rank 1): `Ctrl+wheel` zoom-to-cursor, `Space+drag` pan, `Shift+1/2`,
   zoom cluster bottom-left. ~1 component + transform state on existing SVGs.
2. **Selectable nodes + object tree** (Ranks 2–3): make bays/splits/couplings clickable on the
   elevation, dock a tree panel, wire two-way hover/selection sync (issue-chip jump already
   proves the plumbing works).
3. **Docked contextual inspector** (Rank 5): `InspectorModal`'s content becomes a right-panel
   `Inspect` section; `IntentEditor`'s forms become selection-driven property sections. Kills
   the modal + the 10 selects in one move (comboboxes, Rank 6, land inside it).
4. **Dimension path completion** (Rank 4): math eval, `Tab` cycling, type-while-drag, arrow
   nudges — small diffs on `EditableDimension`/`CADViewportSvg`, highest frequency-of-use payoff.
5. **Command palette** (Rank 10): `Ctrl+K`, shared command registry that later feeds the
   right-click menu (Rank 15) and toolbar — the natural front door for the typed-ops model.
6. Then density/status/keyboard-discovery (Ranks 11–14): mechanical once surfaces exist.

**Anti-pattern debt to retire while doing this** (all verified in current code): native `<select>`
for domain objects ×10, `<dialog>` inspector, `<form>` + Apply-buttons for canvas ops,
selection-by-dropdown, text-list entry for spatial data, prose status lines, zero viewport
chrome, 4-key keyboard map.
