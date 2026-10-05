# DEKOPEN — Interaction Architecture Study

Interaction-model research on modern canvas-first creative/engineering tools, distilled into
adoptable specifications for the DEKOPEN editor (viewport + object tree + contextual inspector +
command palette + typed operations). Every claim below cites a concrete mechanic observed in
a shipping product — pixel behavior, key bindings, state drawings — not adjectives.

**Products studied:** Figma (canvas, selection, inspector, auto-layout, quick actions, shortcuts
panel), tldraw + Excalidraw (floating chrome, zoom cluster, minimap, contextual menus), Linear
(command menu, keyboard UX, density), Shapr3D (dimension-label editing, constraint display,
drag-to-constrain), Onshape (view cube, zoom-to-fit/window/selection, inference wake-up + Shift
suppression), Adobe Illustrator/Photoshop (panel docking, Properties panel, label scrubbing),
Apple pro-app conventions (single inspector driven by selection, disclosure sections, transient
HUDs), Blender/Spline (single-key tools, search-first command surface, panel-over-canvas discipline),
Tinkercad (progressive disclosure for novices).

**Figures (attached):**
- `ref_excalidraw_inspector.png` — Excalidraw: selection chrome (bounds + handles + rotation grip) with the contextual editing panel docked left (color swatches, segmented stroke/style/sloppiness/edges, opacity slider, Layers + Actions icon rows with shortcut tooltips), floating tool island, zoom cluster bottom-left.
- `ref_excalidraw_contextmenu.png` — Excalidraw right-click menu: grouped sections with separators, right-aligned `<kbd>` hints, destructive action (Delete) in red at the bottom.
- `ref_tldraw_stylepanel.png` — tldraw: multi-select (shared bounding box + per-shape lighter bounds), right-side style panel (12-swatch color grid, segmented Fill/Dash/Size/Font, contextual Shape/Line/Arrows groups), Actions strip enabling now that a selection exists, "2 shapes selected" status text.
- `ref_tldraw_minimap.png` — tldraw viewport chrome: zoom out / `100%` / zoom in / minimap-toggle cluster bottom-left with the live minimap open.
- `ref_tldraw_zoommenu.png` — tldraw zoom menu: Zoom in `Ctrl+=`, Zoom out `Ctrl+-`, Zoom to 100% `⇧+0` **disabled because already at 100%**, Zoom to fit `⇧+1`, Zoom to selection `⇧+2` — availability reflects current state.
- `ref_linear_commandmenu.png` — Linear command menu: scope chip (`Issue · LIN-1615`) above the input, grouped actions with icons + single-key hints (`A` assign, `I` assign to me, `S` status, `P` priority, `E` estimate, `L` label).

---

## 1. Viewport interaction specification

### 1.1 Chrome anatomy — everything floats, nothing frames

Both Excalidraw and tldraw keep the canvas edge-to-edge and float **small islands** over it.
Adopt the same four-island layout for DEKOPEN:

| Island | Position | Contents |
|---|---|---|
| Tool island | top-center | 6–10 tools, each icon + single-letter/number badge, tooltip = `Name — Key` (Excalidraw renders `"Selection — V or 1"`, `"Hand (panning tool) — H"`). Include a lock toggle ("Keep selected tool active after drawing — Q") so a draw tool can stay armed. |
| Zoom cluster | bottom-left | `−`, zoom-percentage button (`100%`), `+`, minimap toggle. The percentage button opens a zoom menu (§1.3). tldraw's DOM literally exposes `Navigation: [Zoom out — Ctrl+-] [Zoom — 100%] [Zoom in — Ctrl+=] [Toggle minimap]`. |
| Action strip | bottom-center (above tool island, tldraw) or merged into tool island | Undo `Ctrl+Z`, Redo `Ctrl+⇧+Z`, Duplicate `Ctrl+D`, Delete `⌫`, overflow `⋯` ("Actions" menu). **Availability is visible:** tldraw disables Delete/Duplicate/Undo with no selection — the strip teaches state. |
| Context status | bottom-left of canvas edge or inside zoom cluster | `"2 shapes selected"`, `1 500 × 1 400 mm`, drag readout. One line, never a paragraph. |

Page/file menu top-left, share/export top-right. Nothing else. No heading bar inside the viewport
(our `cad-viewport__heading` with `POSICIÓN DEMO · G1` + `Editor paramétrico 2D` inside the canvas
section is chrome the reference tools would never render — that context belongs in the app header).

### 1.2 Zoom & pan mechanics

- **Zoom-to-cursor, always.** `Ctrl+wheel` (or pinch) zooms anchored at the pointer — the canvas
  point under the cursor stays fixed on screen. Center-anchored zoom is the single most common
  way to make a canvas feel wrong.
- **Wheel = pan** (vertical), `Shift+wheel` = horizontal pan (Figma, Excalidraw), middle-drag = pan,
  `Space+drag` = pan everywhere (all four of Figma/Excalidraw/tldraw/Onshape agree; Excalidraw
  shows it on the empty canvas: `"To move canvas, hold Scroll wheel or Space while dragging, or
  use the hand tool"`).
- **Arrow keys pan** when nothing is selected; `Shift+arrow` pans faster, distance scales with zoom
  (Figma help: "distance changes based on your current zoom level").
- Keyboard zoom: `Ctrl+=`/`Ctrl+-` step zoom (to next nice stop, not linear — e.g. 25→50→75→100→
  150→200→400→800%).
- **Reset to a real size:** `Shift+0` (tldraw) / `Ctrl+0` (Excalidraw) → 100%. For DEKOPEN, 100%
  should mean a stable reference (e.g. 10 px = 100 mm) — pick and document it.
- **Fit:** `Shift+1` zoom-to-fit all modules; `Shift+2` zoom-to-selection (Figma, Excalidraw,
  tldraw all use ⇧1/⇧2). Onshape adds `f` = zoom-to-fit and `w` = zoom-to-window (drag a box);
  double-click middle-button also fits. Adopt `F` (fit) and `W` (window zoom) too — they're free.
- Zoom range: clamp ~5%–1600%. Below ~15% switch text/dimensions to a simplified "overview"
  rendering (Figma culls labels at low zoom).

### 1.3 Zoom menu (the `100%` button)

Clicking the zoom percentage opens a small menu — tldraw's exact list:

```
Zoom in            Ctrl+=
Zoom out           Ctrl+-
Zoom to 100%       ⇧+0      (disabled when already at 100%)
Zoom to fit        ⇧+1
Zoom to selection  ⇧+2
```

Availability mirrors state: at 100%, "Zoom to 100%" is greyed. DEKOPEN additions: "Front view /
Plan view" toggle and "Reset camera" (fit + 0° rotation).

### 1.4 Minimap & orientation

- tldraw ships a **minimap toggle** in the zoom cluster: a thumbnail showing all content plus the
  viewport rectangle; clicking/dragging inside pans. For DEKOPEN — where a 4-module bow is wide
  and low — a minimap earns its place once zoom > 200%.
- Orientation: DEKOPEN is elevation + plan, not free 3D, so don't copy Onshape's view cube
  literally. Copy the *pattern*: a persistent orientation control anchored in a viewport corner
  (Onshape puts the cube top-right of the graphics area; clicking it lists Top/Front/Iso/…).
  DEKOPEN equivalent: a two-state `Front / Plan` pill (or a 3-state with `Detail`), `R` to flip.

### 1.5 Grid & snapping surface

- Grid: `Ctrl+'` toggles (Excalidraw `Ctrl+'`, Figma `Ctrl+'`/`Shift+'`). Render adaptive mm
  intervals (1 m major / 100 mm / 10 mm) that fade out when lines would land < ~8 px apart —
  Figma's pixel grid does exactly this fade.
- Snap state is a **setting with a shortcut and an icon toggle**, not a text button reading
  `Snap ON` (ours at `CanvasEditor2DView.tsx`). Toggle `G`; suppression while dragging = `Alt`
  (Excalidraw uses Alt for no-snap; Onshape uses `Shift` to suppress inferences — pick one,
  document it in the tooltip `Snap — G (hold Alt to suppress)`).
- **Snap feedback during drag:** when within threshold (~5 screen px), draw a full-height/width
  guide line *through the snap target* plus the snapped value inline (e.g. `700` next to the line).
  We currently draw a 4 px `snap-guide` rect and clear it on commit — upgrade: keep it while
  dragging, label it, and flash the *target* element it snapped to (Onshape highlights the related
  entity in orange while drawing a dotted inference line).

### 1.6 Selection rendering — five states, five drawings

| State | Drawing (Figma/tldraw consensus) |
|---|---|
| Hover | 1 px outline (accent blue), no fill change, no handles. Cheap, per-frame. |
| Primary selected | 2 px outline + 4 corner handles + rotation grip above top-center + (Excalidraw) dashed marching selection box. Name chip follows top-left corner. |
| Multi-select | One shared bounding box around the group **plus** a lighter 1 px per-object bounds (tldraw draws both — see `ref_tldraw_stylepanel.png`). Status line: "N selected". |
| Parent/child | Click selects the outermost node (module); `Enter` or double-click descends (module → bay → leaf); `Esc` ascends back up the chain. Figma: `Enter` on a parent enters it, `Shift+Enter` selects parent. |
| Invalid/has-issue | Severity tint on the element itself (amber/red border + corner badge), not just a chip in a side list — Onshape marks the sketch entity, not only the constraint list. Our `has-error`/`has-warning` classes on `.front-module` already do the right thing; extend to bays and couplings, and make the issue chip hover flash the target. |

### 1.7 Direct manipulation — preview vs. commit

The consensus model (Figma resize, Shapr3D drag, our own `CADViewportSvg` resize handles):

1. `pointerdown` on a handle/divider → capture pointer, mark drag start, record undo checkpoint.
2. **During drag, preview locally only** — move a cheap overlay (our `.resize-preview` rect);
   never hit the engine mid-drag. Figma resizes the shape instantly; the "true" re-layout settles
   on commit. Show a **live dimension readout next to the cursor** (Shapr3D: the dimension label
   travels with the drag and shows the current value).
3. **Typed input must coexist with drag:** while dragging, typing a number replaces the drag value
   (Shapr3D and SketchUp both accept typing mid-operation — the readout becomes an input). Release
   or `Enter` commits it. This is the fastest path to exact values and nobody's inspector field
   competes with it.
4. `pointerup` → dispatch **one** typed operation (`resize module m1 → 620.00 mm`) → single engine
   call → single undo step. Never stream intermediate commits.
5. `Esc` during drag cancels cleanly and restores pre-drag geometry (our `cancelDrag` does this —
   keep it).

### 1.8 Dimension editing — the Shapr3D pattern (already half-built in `SvgDim`/`EditableDimension`)

- Every dimension is a **live label, not a dead annotation**: click the label → it becomes an
  input, pre-selected (we already `onFocus → select()`).
- Commit on `Enter`/blur-if-valid; revert on `Esc` (we do this — keep).
- **Accept math:** `1200+50`, `2900/3`, `2*750` evaluate client-side before commit — Shapr3D
  documents `12+34` and `50/2` on the dimension label. For a quoting tool this is genuinely
  useful (opening = rough opening − tolerance).
- Accept unit-less input, `,`→`.` decimal normalization, `°` suffix stripping — our
  `normalizeDimension`/`normalizeAngle` already do most of this.
- `Tab`/`Shift+Tab` cycles dimension fields in reading order (total width → module widths →
  height → coupling angles).
- `↑`/`↓` on a focused dimension increments by small nudge; `Shift` = big nudge
  (Figma: small nudge = 1, big nudge = 10, user-configurable in Preferences → Nudge amount).
- Dragging a divider/edge **and** editing its label are the same operation — the label is just
  the precise form of the gesture. That's the core of "dimension-first modeling": the number is
  the object.
- Shapr3D's "Distance Type" badge next to a dimension (Absolute/Horizontal/Vertical) maps to a
  DEKOPEN need: offset labels could carry a "from left / centered / from right" badge to disambiguate
  split offsets.

---

## 2. Inspector + property-control specification

### 2.1 Container: docked panel, never a modal

- Right-docked ~280 px column, collapsible (`Shift+Cmd/Ctrl+\` hides the left sidebar in Figma;
  expose `Ctrl+B`-style toggles for both side panels).
- **Kill the modal.** Our inspection UI is a `<dialog>` (`InspectorModal`) that blocks the canvas,
  uses fake tab buttons (`aria-pressed` nav), and must be opened/closed with buttons. In every
  reference product, properties are a resident surface; the only modal left should be true
  transactions (export, confirm destructive).
- Tabs only for genuinely different *workspaces*: Figma Design/Prototype = edit vs. connect.
  DEKOPEN analog: `Design` (geometry/openings/glazing) vs. `Inspect` (findings, cutting, readiness)
  as a segmented header — still docked, not modal.

### 2.2 Selection-driven content — most-common-first

Figma's right sidebar shows file/page properties when nothing is selected and layer properties
when something is. Adopt the same contract:

| Selection | Inspector shows (top → bottom) |
|---|---|
| Nothing | Position/project context: system series combobox, color, location tag, quantity, product-wide dims. Today's `position-materials` `<fieldset>` becomes this. |
| Module | Geometry (W/H), Aperture glyph-grid, Splits, Glazing, Hardware, Issues-for-module |
| Bay (inside module) | Aperture glyph-grid first, then Glazing/Panel, then Dimension(s), then Annotations |
| Split | Offset field + axis segmented + presets `½ ⅓ ⅔` |
| Coupling | Angle field (°), coupler combobox, "Straighten" action |
| Multi | Count + mass-apply controls; differing values show `Mixed` |

Sections are collapsible (`>` chevron + title row, hit area = full row), open-state persisted per
node type. Order = frequency of use, not data-model order: Aperture before Glass before
Annotations.

### 2.3 Property-control vocabulary (concrete behaviors)

**Property row:** 28–32 px tall, label or icon left (~80 px), control right-aligned. Hover reveals
secondary affordances (steppers, "more"). Focus ring only on focus. Unit suffix inside the field
as ghost text (`mm`, `°`) — our `DraftField` already does `value + unit span`; move the unit inside
the input visually.

**Numeric field ("DraftField" evolved):**
- Commit: `Enter` or valid blur. Revert: `Esc`. Auto-select-all on focus. All three already exist —
  standardize them on *every* numeric field.
- `↑`/`↓` = ±small nudge, `Shift+↑/↓` = big nudge; wheel-over-focused-field = same. (Adobe and Figma
  both support arrow-stepping in fields.)
- Label scrub: press-dragging the *label* scrubs the value horizontally (Adobe Properties panel
  convention) — optional power feature, cursor `ew-resize` on the label.
- Math input per §1.8.
- **Mixed values:** multi-selection with different values → field shows `Mixed` in italic grey;
  typing a new value sets all. Figma uses `Mixed`; never leave the field blank.

**Segmented control** for ≤5 discrete choices: one row of equal-width buttons, selected filled,
each icon+short-label, tooltip carries the shortcut if any (Excalidraw's Stroke-width
Thin/Medium/Bold; tldraw Size S/M/L/XL; our `opening-grid` is already the best instance —
8 glyph buttons with `aria-pressed`). Keep the glyph grid; move it to the inspector top for bays.

**Combobox (replaces every `<select>`):**
- Trigger shows current value with icon/preview (opening glyph, glass thumbnail swatch, coupler
  section symbol).
- Popover: type-to-filter list, grouped by role (`Mullions`, `Couplers`, `Glass`), each row =
  SKU + short name + spec subtitle (e.g. `COPLE-90 · coplanar · 90°`).
- Multi-line-of-truth: no fake first `<option value="">Choose…</option>` — placeholder text inside
  the field instead. Empty state = `None` row.
- Today's `<select>` for system/coupler/glass/panel/thickness/bay/template/division all become
  comboboxes or — better — disappear into direct canvas selection.

**Icon-button action rows:** Layers order (send/bring), Duplicate `Ctrl+D`, Delete `⌫`, Link
`Ctrl+K` — Excalidraw packs them as 4–6 icon buttons under `Layers`/`Actions` fieldsets with
shortcut tooltips (`"Send backward — Ctrl+["`). Adopt for module ops: `Split V`, `Split H`,
`Duplicate`, `Delete` as icon buttons — but split *with offset* should be a canvas gesture
(click position = offset) or palette command with parameter, not a bare button.

**Boolean:** switch/toggle, never a 3-state `<select>` (our coupler `unconfirmed/no/yes` select
→ segmented `— | No | Yes` or checkbox-with-indeterminate).

**Chip list** for coordinate sets: drain holes today are a comma-separated text input with a regex
(`^\d+(\.\d{1,4})?$`) — replace with a chip editor: `+ Add`, each chip `[100 mm] ×`, values also
visible as markers on the canvas edge where the holes live. Text-parsing fields for spatial data
is a category error — the data belongs on the drawing.

### 2.4 Density & spacing rules (how pro tools pack without spreadsheet-dump)

- 4 px base grid; row height 28–32 px; 16 px icons; section gap 12 px; panel padding 8–12 px.
- **Information hierarchy via tint, not borders:** no fieldset legends or boxed groups — a section
  is a small-caps/grey title row + rows beneath; separators only between major groups.
- Visual value types where possible: color swatches > hex text; opening glyphs > opening names;
  segmented > radio lists; icon buttons > text buttons. (Every reference product does this; our
  glyph grid proves we can.)
- Right-align all secondary text (shortcuts, units, counts). Grey it one step.
- One-line status with semantic styling: a status *pill* (`VALID` / `MANUFACTURING_INCOMPLETE` /
  `INVALID` colored chip), not a prose `<span>`; the assembly toolbar's status text becomes this.
- Progressive disclosure: collapsed-by-default for infrequent sections; count badge on collapsed
  headers (`Issues · 3`).
- Loading = in-place skeleton/spinner on the affected row, plus a non-blocking progress shimmer on
  the affected canvas region; never a blocking `calculando` text that disables the whole form
  (today `busy`/`isPending` disables every field — lock only the pending subtree).

---

## 3. Command palette specification (Linear + Figma synthesis)

**Trigger:** `Ctrl+K`/`Cmd+K` primary (Linear convention), `Ctrl+/` alias (Figma quick actions).
Also opens when clicking a control that has a command-menu equivalent (Linear opens the menu
*anchored to the element* when invoked by mouse — e.g. clicking an assignee pill).

**Surface:**
- Overlay ~560 px wide, top-third centered (keyboard invocation) or anchored next to the invoking
  element (mouse invocation — Linear moved the menu next to the control after 2019; keep both).
- Input row with scope chip: `Module m2` when a selection exists, `Canvas` otherwise — Linear
  renders `Issue · LIN-1615` above the input.
- Results list: grouped sections with grey headers, icon left, action name, right-aligned `<kbd>`
  hint, hover/keyboard selection highlight. Footer hints: `↑↓ navigate · ↵ run · esc close`.

**Matching:** fuzzy subsequence over name + keywords + synonyms (`mullion`, `poste`, `divide`,
`split v` → "Split bay vertically"); rank = context-section-first, then exact > prefix >
subsequence; a `Recent` group pins the last 5 executed commands at top (Linear recents + Figma
actions both do this).

**Availability is computed, not static:** every command has a `when(selection, mode)` predicate.
Inapplicable commands either hide or render greyed with the reason (`Split — needs a bay
selected`). Unavailable commands must never execute with a toast error afterward — Linear's
context-groups exist precisely so you only see what's legal here.

**Execution:**
- `Enter` runs the highlighted command; the palette closes.
- Parameterized commands become an inline parameter step: `Move split…` → the input turns into a
  dimension field showing current value + preset rows (`½`, `⅓`, `⅔`) — one `Enter` commits.
- Destructive commands (`Remove module`) confirm in-palette (press `Enter` again, or `⌘↵` to
  force) — never a separate dialog.

**Feedback:** after execution, a transient toast/status near the bottom-center with the applied
op + `Undo` (`"Split m2 at 700 mm — Undo"`), and the created/changed node becomes the selection
(Figma jumps selection to the result of quick actions). Errors stay in the palette as a red
inline note — the palette doesn't close on failure.

**Shared registry:** the same command list powers the palette, the right-click context menu
(Excalidraw-style grouped menu with kbd hints), and toolbar buttons — one definition, three
surfaces, availability always honored.

---

## 4. Object tree specification

Docked left panel ~240 px, toggleable. This is the missing surface in our current UI — bays and
splits exist only inside `parametricTree` and are reachable today by a `<select>` listing
`Vano 1, Vano 2…` (IntentEditor) or not at all (ProductFrontSvg only renders modules as
clickable).

- **Rows** 28–32 px: type icon (module ▦, bay □ with tiny opening glyph, split ┃/━, coupling ⟩⟨),
  name, hover-only action cluster (eye, rename, `⋯`).
- **Hierarchy:** indent 12–16 px per level, disclosure chevron on containers
  (`module ▸ SPLIT_V ▸ [bay A | bay B]`). Collapse state persists.
- **Naming:** auto-names carry semantics, not indexes: `Puerta`, `Fijo`, `Vano corredera` +
  disambiguator (`Fijo 2`). `Enter` on a focused row (or double-click the name) renames — Figma
  pattern; alias is user metadata, never the identity.
- **Selection sync is two-way and hover-linked:**
  - Canvas click → row highlights + scroll-into-view (Figma scrolls the layer list to the
    selection).
  - Row click → canvas selection; row **hover** → hover-outline on the element (the cheap 1px
    hover state from §1.6).
  - `Shift+click` range-select, `Ctrl+click` toggle-select; multi-selection shows all rows.
  - Esc on a row = ascend to parent (same chain as canvas Esc).
- **Badges:** severity dot on the row for issues targeting it; issue chips in the inspector link
  back to the row too. A `filter` box appears once > 12 nodes (type to filter, `Ctrl+F` scope
  optional — keep simple).
- **Reorder = semantics:** dragging a module row left/right reorders modules (and redraws the
  elevation); drop indicator is a 2 px insertion line between rows, never a highlight box.
  Bay/coupling reorder where meaningless = no drag affordance.
- Keep it honest: the tree is the *same* `product`/`parametricTree` structure — one node = one
  row = one selectable canvas region. If a node can't be clicked on canvas, its row still selects
  it (tree is the escape hatch for occluded elements — that's why every pro tool has one).

---

## 5. Keyboard map — top 25 for DEKOPEN

Merged from Figma/Excalidraw/tldraw/Onshape/Shapr3D conventions; `Ctrl` shown (Cmd on macOS):

| # | Key | Action | Source convention |
|---|---|---|---|
| 1 | `V` | Select tool | Figma/Excalidraw/tldraw |
| 2 | `H` | Hand tool (temporary: `Space+drag`) | Figma/Excalidraw/tldraw |
| 3 | `Space+drag` | Pan (any tool) | universal |
| 4 | `Ctrl+=` / `Ctrl+-` / `Ctrl+wheel` | Zoom in/out to cursor | universal |
| 5 | `Shift+1` | Zoom to fit product | Figma/Excalidraw/tldraw |
| 6 | `Shift+2` | Zoom to selection | Figma/Excalidraw/tldraw |
| 7 | `Shift+0` | Zoom to 100% (reference mm scale) | tldraw |
| 8 | `W` | Zoom to window (drag box) | Onshape |
| 9 | `F` | Zoom to fit (alias of 5; muscle memory from CAD) | Onshape `f` |
| 10 | `Ctrl+K` / `Ctrl+/` | Command palette / quick actions | Linear / Figma |
| 11 | `Ctrl+Z` / `Ctrl+Shift+Z` (`Ctrl+Y` alias) | Undo / redo | universal (we have this) |
| 12 | `Ctrl+D` | Duplicate selection (module/bay) | Figma/Excalidraw/tldraw |
| 13 | `Alt+drag` | Duplicate-by-drag | Excalidraw/Figma |
| 14 | `Delete`/`Backspace` | Delete selection | we have for modules — extend to splits/bays |
| 15 | `Esc` | Cancel drag → deselect → ascend → close menus (staged) | universal |
| 16 | `Enter` | Descend into selection (module→bay→leaf); on dim label = edit; in field = commit | Figma descend pattern |
| 17 | `Tab` / `Shift+Tab` | Cycle dimension fields / nodes; in tree = next row | Figma field traversal |
| 18 | `↑↓←→` | Nudge selection 1 mm (module position is reflow, so: move split offset ±1 mm; with nothing selected, pan) | Figma small nudge |
| 19 | `Shift+↑↓←→` | Nudge ×10 (10 mm); Shift+arrows also = fast pan when empty | Figma big nudge |
| 20 | `Shift+click` | Add to selection | universal |
| 21 | `Ctrl+click` | Deep-select child (bay inside module without entering) | Figma cmd-click |
| 22 | `Ctrl+G` / `Ctrl+Shift+G` | Group/ungroup — map to "wrap bays under a split" / "dissolve split" | Excalidraw |
| 23 | `G` or `Ctrl+'` | Toggle grid/snap | Excalidraw `Ctrl+'` |
| 24 | `R` | Flip view Front ↔ Plan | Onshape orientation |
| 25 | `?` (`Ctrl+Shift+?`) | Shortcuts panel — bottom sheet, grouped, used-shortcuts highlighted (Figma); also reachable from Help | Figma/Excalidraw |

**Modal rules:** typed-while-dragging sets exact values (§1.7); `Shift` during drag constrains
axis/preserves ratio; `Alt` during drag suppresses snapping; `Enter`/`Esc` commit/revert every
text field; single-key tools only when no field is focused (today's handler already skips
input/select/textarea targets — keep that guard and extend it to `contentEditable`).

**Discoverability system** (the part that makes a keyboard map real):
- Every toolbar/menu/palette item's tooltip ends with `— Key` (Excalidraw does this verbatim).
- Right-click context menus print `<kbd>` hints (Excalidraw screenshot).
- `?` opens the shortcuts sheet; already-used shortcuts render highlighted (Figma).
- On empty canvas, render the one-line hint Excalidraw shows: *"Drag to draw · Space+drag to pan ·
  Scroll to zoom · `?` for shortcuts"*.

---

## 6. Anti-patterns — what the references avoid, where we commit them

| Anti-pattern (none of the products ship this) | Where we commit it | Fix direction |
|---|---|---|
| **Form-as-inspector**: giant `<fieldset>/<legend>` + stacked `<label><input>` blocks | `IntentEditor.tsx` (entire file), `ProjectPositionEditor.tsx` `position-materials` aside, `InspectorModal.tsx` annotations fieldset | §2 row vocabulary; sections with chevrons; no `<form>` per region |
| **Native `<select>` for domain objects** — no search, no preview, fake first option | bay select (`IntentEditor` ~L192), opening (~L255), division (~L384), template (~L456), system (`ProjectPositionEditor` ~L591), glass/thickness/panel/coupler (`AssemblyEditor` ~L256–311), coupler yes/no (`InspectorModal` ~L241) | combobox with filter + previews, or direct canvas selection; yes/no → segmented |
| **Modal property surface**: `<dialog>` that blocks the canvas, fake tab nav | `InspectorModal.tsx` whole component | docked right inspector; findings panel inline; reserve dialogs for true transactions |
| **Selection by text dropdown** — "Vano 1/Vano 2" with no spatial link | `IntentEditor` bay `<select>`; conversely `ProductFrontSvg` renders only *modules* selectable — bays/splits unreachable by click | object tree (§4) + click/descend (§1.6) so every node is selectable in ≥2 places |
| **Apply-buttons after typed forms** — type, click "Aplicar", wait, hope | "Apply dimensions"/"Apply opening"/"Apply template" submits (`IntentEditor` ~L211, ~L272, ~L471) | commit-on-Enter/blur with live preview; the operation *is* the feedback |
| **Blanket locking**: `dimensionsPending || !!offset` disables unrelated controls (bay select, opening, template) | `IntentEditor` throughout (`disabled={dimensionsPending || !!offset}`) | lock only the pending subtree; let the user keep exploring |
| **Status as prose**: `<span>calculando</span>`, semaphore paragraph, `role="status"` text | `CanvasEditor2DView` ~L76–89, `AssemblyEditor` status span, `InspectorModal` semaphore `<p>` | status pill + in-place skeleton + non-blocking progress (§2.4) |
| **Zero viewport chrome**: no zoom/pan/fit/grid/minimap; `viewBox` fixed-fit means the product just shrinks | `CADViewportSvg`, `ProductFrontSvg`, `BowPlanSvg` — no zoom handlers exist anywhere (`grep wheel|zoom` → none) | §1 four-island chrome + zoom menu + minimap |
| **Text-list spatial data**: comma-separated mm input with regex validation | drain holes field (`InspectorModal` ~L225) | chip editor + on-canvas markers |
| **Tables as data dumps**: BOM in `<details>` + bare `<table>` ×4 | `ProjectBom` (`ProjectPositionEditor` ~L631–727) | collapsible groups w/ counts, property-list rows, copy/export actions |
| **No keyboard system**: only `Ctrl+Z/Y`, `Del`, `Esc` exist; no tool keys, no nudge, no palette, no `?` sheet, tooltips have no hints | `ProjectPositionEditor` `onKey` (~L379–422) is the whole keymap | §5 map + discoverability system |
| **Toggle as text button**: `Snap ON` / `Snap OFF` prose button | `CanvasEditor2DView` ~L68–75 | icon toggle + `aria-pressed` + tooltip with `G` |
| **Error as alert-text + manual dismiss**: `role="alert"` paragraph with a "Revisar" dismiss button | `IntentEditor` error block (~L488–494) | inline field error or issue chip that selects its target on click (extend our existing issue-chip pattern) |
| **Custom lists/regex for undo**: our Undo/Redo buttons exist but no `?`-sheet, no visible `Ctrl+Z` hint anywhere | `ProjectPositionEditor` header buttons (~L526–531) | put shortcut hints in tooltips/menus everywhere |

**Seeds already good — keep and extend:**
- `SvgDim`/`EditableDimension`: click-label → input → Enter/Esc/blur semantics (§1.8).
- `opening-grid` glyph segmented control (`ModuleInspector`): the single most "pro" control we
  have — promote it to inspector top.
- `DraftField` normalize + commit-on-blur + Esc-revert + unit span.
- Add-handles (`AddHandle` circles) — direct add-unit affordance on canvas.
- Issue chips that select their target on click (`AssemblyEditor` ~L523–536) — the germ of
  selection-sync; extend to hover-flash and tree badges.
- Pointer-capture drag with snap guide + preview rect (`CADViewportSvg` ~L74–105) — correct
  preview-vs-commit split; needs live readout, typing-during-drag, labeled snap guides.

---

## Sources

- Figma Learn: "Use Figma products with a keyboard" (arrows pan, Shift = faster pan, distance
  scales with zoom; Ctrl+Shift+? shortcuts panel with used-shortcuts highlighted; Ctrl+Space
  keyboard box-select); "Set small and big nudge values" (1 / 10, configurable);
  "…right sidebar" (Design/Prototype tabs, nothing-selected vs layer-selected content);
  "Select keyboard layout" (quick actions `Cmd/Ctrl+/`, Show/hide UI `Cmd\`, `Shift+1`/`Shift+2`,
  pixel grid `Shift+'`, select parent `\`).
- Excalidraw live UI + docs (tool island key badges V/1 R/2 … E/0, `?` help dialog, `Ctrl+'`
  grid, `Alt+drag` duplicate, footer zoom actions, context-menu groups with kbd hints).
- tldraw live UI (minimap toggle, zoom menu w/ state-aware disabling, Actions strip disabled
  without selection, "N shapes selected", style panel segmented groups).
- Linear changelog/now: contextual command menu (menu anchors to invoking element), "New command
  menu" (context-first grouping + icons), "Invisible details" (right-click menus teach shortcuts;
  `?` shortcut list; single-key issue actions).
- Shapr3D Help Center: "Editing sketch dimensions" (dimension label click-to-edit, numpad, math
  expressions `12+34`, `50/2`, Distance Type badge); "Adding and removing constraints"
  (context-adaptive constraint menu, drag-and-drop constraints, purple midpoint, filled-point
  states); sketch-controls walkthroughs (type value while drawing, Enter accepts).
- Onshape Help: "Zoom to Fit, Window, and Selection" (`f`, `w` drag-box, zoom-to-selection,
  double-click wheel = fit); "View Navigation and the View Cube" (`Z`/`Shift+Z`, scroll zoom,
  view cube menus planes/iso); "Automatic Inferencing" (hover to *wake up* inferences, dotted
  line + orange-highlighted related entity + constraint icon, `Shift` suppresses).
- Adobe/Apple/Blender/Spline conventions per their public docs and long-standing app behavior
  (label scrubbing, Tab-hides-panels, single-inspector-per-selection, F3-style search).
- Current DEKOPEN code: `frontend/src/features/canvas/{IntentEditor,CADViewportSvg,
  EditableDimension,ProductFrontSvg,AssemblyEditor}.tsx`, `features/inspector/InspectorModal.tsx`,
  `features/projects/ProjectPositionEditor.tsx`.
