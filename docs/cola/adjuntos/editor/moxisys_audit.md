# Moxisys (WindoorCraft) interaction audit — for DEKOPEN editor design

**Purpose:** product-interaction audit of Moxisys's window-drawing app and comparable tools, to inform DEKOPEN's canvas editor (modules/bays/openings, typed ops, roadmap toward direct drawing: mullion/transom splitting, drag resize, region selection).

**Sources & confidence:**
- Official guide: moxisys.com/window-design-software (19-chapter manual w/ screenshots) — **verified text**.
- Official tutorial videos (14-part YouTube series embedded in the guide): ch.04 window design, ch.05 casement, ch.06 sliding, ch.07 turncorner, ch.09 3D — **watched + transcripts analyzed**, screenshots extracted from video frames.
- WindoorCraft marketing site (windowcc.com) — newer branding of the same app — **verified text**.
- Live app at sa.windoorcraft.com — Vue.js + Vuetify SPA, login-gated (3-day trial, account issued by vendor); **not accessed past login** — all in-app mechanics below come from video + docs, marked accordingly.
- Competitors: Orgadata help docs (help.orgadata.com), OpenJanela KB, Selecta/Advance70 — **verified docs**.
- Independent reviews of Moxisys: **none found** (no G2/Capterra/Trustpilot footprint). Weakness analysis below is my inference from watching the videos, flagged as such.

**What Moxisys actually is:** a Chinese vendor (Moxisys Co., Jinan) whose primary business is uPVC/aluminium window machinery. The software — branded *WindoorCraft* — is a cloud SaaS sold in tiers: Trial (3 days) → Design Pro → BOM Pro (bill of materials + certification reports) → Team (20 sub-accounts) → optional modules: CRM, Finance, Workshop, Warehouse, **CNC machine connection**. It runs on desktop/tablet/phone with synced data, plus an AI photo-render feature ("photorealistic render in 10 seconds"). The editor is a real canvas app: DOM/canvas hybrid, frame-elevation 2D drawing with live dimension chains, property sheets, and a separate real-time 3D view.

---

## 1. The core creation loop, step by step

Task: make a rectangular window, one vertical mullion, casement sash in one bay.

1. **Enter Design module.** Login lands on a tile launcher (design / order / library / product / account). Clicking *design* opens the workspace: left vertical tool rail, top toolbar (undo, redo, delete, export, import, clean, align, save, 3D, settings, fullscreen, close), right panel with tabs (draw / order / color / glass) that becomes a property sheet for whatever is selected.
2. **Draw the frame.** Click the *frame* tool in the left rail → a flyout grid of **~45 outline shapes** (rectangles, round/gothic/segmental arches, circles, triangles, trapezoids, parallelograms, hexagons, corner shapes — see screenshot `m2_frame_dims.png`). Pick *rectangle*. Two ways to instantiate:
   - **single-click on canvas** → a standard-size frame with glass appears; or
   - **press-and-drag** → rubber-band the frame to size.
3. **Set exact size.** Frame is born with blue dimension labels on each side (e.g. 1500 × 2000). Resize either by **dragging a frame edge** (click-hold an edge and pull) or by **double-clicking a dimension number** → an inline numeric field with up/down spinner appears → type the value (screenshot `m4_sash_infobox.png` catches this mid-edit: 455 → 500).
4. **Add a mullion.** Click the *mullion* tool → pick a mullion type from the flyout (straight, plus layout presets; there are also arc/compound variants). **Press the left button and drag inside the frame: stroke direction determines orientation** — drag top-to-bottom → a vertical mullion is inserted; drag horizontally → a horizontal transom. The divider lands at the drag position and the dimension chains split (e.g. 2000 becomes 600 + 1400; heights become 500 + 1000 — screenshot `m3_mullions.png`). Reposition by **dragging the mullion body**, or double-click a bay dimension and type it.
5. **Assign a sash.** Click the *sash/placement* tool → pick sash kind (casement, sliding, folding, door, screen/antitheft) → **click inside the target pane/region** → the sash is placed into that bay. This is implicit region targeting: the pane under the cursor becomes the parent — the key mechanic DEKOPEN's roadmap calls "region selection."
6. **Configure it.** Click the sash → right panel becomes the sash property sheet (screenshot `m8_sash_options.png`): cut type (Angle/Vertical/Horizontal), open direction L/R, is-door, handle display + handle height (e.g. 448), open/closed display toggle, inside/outside swing, hinge count (hingetp two/three), slide direction, handle type. Same pattern for frame (cut type, lock-drag, topView, generate-wall) and glass (type, frosted, shade, spec e.g. 5mm, turning-frame).
7. **Refine/annotate.** *ExtraDim* tool → place custom dimension lines; *radius* tool → click an arc, it labels `r=1204.8`; *note* tool → type text, drag a blue anchor point. Selection feedback = **red squares on edges + a red diamond shape-handle**; dragging the mid-edge points bends the frame into an arc or bends/rotates a mullion (non-linear mullions confirmed on video).
8. **Finish.** Save → order/quotation generated; *3D* button opens a real-time render (wall generated around the opening, inner/outer material swatches, orbit controls, share link, "take photo" overlay onto a site photo, screenshot+annotate) — screenshot `m9_3d_render.png`.

**Verified claims:** drag-to-draw frame ✓; drag horizontally/vertically to add mullion/transom ✓ (direction-of-stroke semantics); click-to-place sash ✓; arcs & non-rectangular frames ✓ (shape library + drag-shape handles); non-linear/rotatable mullions ✓; 3D view ✓ (separate real-time renderer); BOM ✓ (BOM Pro tier); quotation + PDF + e-signature share links ✓; workshop/warehouse/CNC modules ✓ (optional tiers). "Alt + mouse wheel" zoom documented on windowcc.com; handle can be dragged and "auto-aligns to keep same height" across bays.

---

## 2. Interaction patterns worth translating into DEKOPEN

**a) Direction-of-stroke splitting.** The single best idea to steal: no separate "vertical mullion"/"horizontal transom" tools — one *divide* gesture; the axis of the drag defines the member's axis. In DEKOPEN terms: pointer-down inside a bay + drag ⇒ `split bay` along stroke axis at pointer position. Two refinements worth adding that Moxisys lacks: show a live preview of the split line + the resulting dimension values *during* the drag, and a typed modifier (e.g. `Shift`) for equal-division (`split into N`).

**b) Region-targeted placement.** Sash assignment is "click inside the pane," not "select pane from a list." DEKOPEN should keep this: hovering a bay should highlight it as the drop target, then apply `add unit` to that region. Mark honestly: in the videos I could not confirm a hover-highlight affordance — if there is none, that's a weakness we can fix.

**c) Double-click-to-type on dimensions.** Every number on the canvas is editable in place (double-click → spinner input). This is how they reconcile fast gestures with millimeter precision without a dialog. Equivalent for DEKOPEN: click/double-click a dimension label → `set dimension` op with the typed value. Keep drag = approximate, type = exact.

**d) Selection → property sheet, not modal dialogs.** Clicking any element swaps the right panel into that element's property editor (frame cut angle / sash hardware / glass spec). No modal dialogs observed anywhere in creation — pro tools like LogiKal are modal-heavy by contrast.

**e) Shape-handle reshape.** Select → red points on the edges; dragging the mid-edge point of a frame turns a rectangle into an arc; dragging a mullion's points bends/rotates it. Cheap, discoverable way to reach non-rectangular designs without separate "arc mode." DEKOPEN can do better with: curvature as a typed property (radius/sag) in addition to drag.

**f) Property-level drag affordances.** Two under-noticed details: (1) hardware (handle) is itself draggable and *auto-aligns to equal handle height across sashes* — a real snapping behavior, the only one documented; (2) *lock drag* toggle per frame prevents accidental re-drag — an explicit "I'm done editing geometry" switch, useful for a gesture-heavy editor.

**g) Live dual views.** Below the elevation, a plan/section strip (OUTSIDE/INSIDE) renders swing-direction arrows per numbered bay — instant feedback on opening directions without opening the 3D view. Plus one-click jump to 3D render.

**h) Toolbar undo/redo.** Undo/redo/delete/export/import/clean/align/save are visible buttons (touch-friendly). No keyboard shortcut usage was ever demonstrated in 5 tutorial videos — Moxisys is effectively mouse-only.

**i) Preset layout flyout.** The left-rail flyouts contain not just atomic tools but **pre-subdivided layout icons** (e.g. "1 over 2 panes", "2×2 grid") — insert a whole bay pattern in one click. In DEKOPEN: template modules inserted as one op, then editable.

**j) Insert-at-gesture then fix numerically.** Mullions land where the stroke ends; exact position is set afterwards via the bay dims. Simpler than CAD "type offset then place" and adequate because dims are always visible/editable.

---

## 3. What the drawing looks like at each stage

- **Empty workspace:** light canvas, left icon rail, top icon toolbar, right tab strip. Screenshot `m1_workspace_tools.png`.
- **Frame drawn:** thick **orange** profile outline, **cyan** glass fill, **blue** dimension labels on outer edges, OUTSIDE/INSIDE plan strip below. Screenshot `m2_frame_dims.png` (frame-shape flyout visible, ~45 shapes).
- **After mullion/transom:** orange bars; dimension **chains** split per bay — inner dims (600/1400, 500/1000) plus overall (2000/1500). Screenshot `m3_mullions.png`.
- **Sashes placed:** thinner inset outline per sash; **casement = dashed diagonal triangle** (hinge side + swing); **sliding = arrow glyph** in slide direction; **handles = small grey bars**; numbered bays ①② with swing arrows on the plan strip. Inline dimension edit = floating spinner input. Screenshot `m4_sash_infobox.png`.
- **Selection:** clicked element shows red squares at edges/vertices + red diamond corner handle; right panel switches to that element's sheet. Screenshot `m5_arc_redpoints.png`.
- **Arched/non-rectangular:** frame top edge dragged into an arc; `r=1204.8` radius callout; per-bay dims still chained. Screenshot `m6_radius_note.png` (also shows annotation tools: ExtraDim, radius, text note being typed).
- **Sash property sheet:** right panel = toggle/dropdown list (cut type, open L/R, is-door, handle display + height 448, open/closed, outside swing, hinge count, slide direction, handle type). Screenshot `m8_sash_options.png`.
- **3D stage:** separate renderer; wall auto-generated around unit; left = texture/color swatches per inner/outer face; right = orbit/animation/share/photo/screenshot buttons; bottom = profile/wall/board/glass tabs. Screenshot `m9_3d_render.png`.

Hierarchy is implicit in the drawing itself: frame > bays > sash — there is **no tree/layer panel** anywhere in the videos.

---

## 4. Where Moxisys is weak — DEKOPEN's openings

(All inferred from video/docs — the app itself is login-gated; not hands-on verified.)

1. **Keyboard is nearly absent.** One documented shortcut (`Alt+wheel` zoom). No arrow-key nudge, no Escape, no Enter-to-commit shown; every action goes menu → pick → gesture. DEKOPEN: full keyboard map for power users (Esc cancel, arrows nudge, `=` equalize, typed-command palette matching its typed-ops model).
2. **No visible snapping.** No grid, no object snap, no alignment guides shown during drags; the only documented snap is handle-height alignment. Drags are "approximately right, then type the number." DEKOPEN can show live snap targets (bay midlines, other mullions, equal-spacing ticks) during the gesture.
3. **No multi-select / marquee.** Everything demonstrated is single-object select → edit. No rubber-band region select, no batch edit, no copy-paste of bays — repeating a 3-sash bay means doing it three times. DEKOPEN: marquee + multi-select + `equalize`/`repeat` ops.
4. **No constraint ops.** No equalize, mirror, distribute, or array commands observed (the "align" toolbar button's semantics are unclear from docs). Making three equal bays = edit three numbers by hand. DEKOPEN already has `equalize` typed — keep it one keystroke away.
5. **Gesture-first ordering forces a correction pass.** Split lands at drag position; you then fix the number. Fine for one mullion; tedious for precise multi-splits — a `split` op taking explicit position(s) in one step beats it.
6. **Selection feedback is minimal.** Red points on select, but no visible hover-state, no region highlight on sash insertion (unconfirmed), no cursor state changes per tool observed. Mode tools (pick tool → it stays active) with no visible "what tool am I in" cue beyond the highlighted flyout icon.
7. **No element tree/inspector.** Complex designs (arched frame + nonlinear mullions + mixed sashes) exist only as the picture — clicking a tiny mullion target on a dense drawing is the only way to select it. DEKOPEN's module/bay/opening hierarchy should be surfacing (tree or breadcrumb) for selection.
8. **Undo semantics unclear.** Toolbar undo/redo exist, but no history panel; whether undo covers property changes vs. only geometry is undemonstrated.
9. **Precision readouts during drag.** Dims update live while dragging, but no snap-increment or direct typing-during-drag; you can't do "drag and type 600" in one motion (SketchUp-style). Easy DEKOPEN win.
10. **Translation/UX polish.** Terse machine-translated labels ("handst", "hingetp", "topView", "cut type"), tutorial videos narrated in heavily translated English. Not a functional weakness, but signals low UX budget — DEKOPEN can win on clarity alone.

---

## 5. The 10 most important interaction requirements for a modern window editor (ranked)

1. **One continuous edit loop: gesture creates, numbers correct.** Draw/split by pointer, fix by typing — without ever opening a dialog. (Moxisys gets this half right: correction exists, but no typed-input-during-gesture.)
2. **Direction-of-stroke division.** A single split gesture whose axis = member axis; works for mullion AND transom AND multi-split (`split into N`), inside any selected region — not just the root frame.
3. **First-class region selection.** Hover-highlighted bays, click-targets, marquee, and a visible hierarchy (tree/breadcrumb). Every typed op (`add unit`, `remove`, `equalize`) applies to the current selection context.
4. **Live dimensions as UI, not decoration.** Always-on chained dims per bay + overall; every number is click-editable; typing during an active drag commits the value mid-gesture (SketchUp-style).
5. **Snapping with explicit targets.** Snap to bay midlines, thirds, other members, equal handle heights; show the snap target and the snapped value *during* drag; `Alt/Shift` to disable/constrain. (Moxisys demonstrates almost none of this.)
6. **Multi-select + constraint ops.** Rubber-band or shift-click selection; then `equalize`, `distribute`, `align`, `mirror` as one-step ops. This is the biggest quantifiable gap vs. Moxisys — their workflow can't express "make these three bays equal."
7. **Selection → contextual property sheet.** Never a modal: whatever is selected owns the inspector (frame cut, sash swing/hardware, glass spec), with changes applied live.
8. **Undo/redo as a typed-op history.** Not just Ctrl+Z buttons: a named history of ops (`split`, `set dimension`, `add sash`) the user can step back through — natural fit for DEKOPEN's op model, and stronger than Moxisys's opaque undo.
9. **Symbols that encode, not decorate.** Opening-direction triangles, slide arrows, handle glyphs, plan-view strip — the drawing itself answers "which way does it open" without inspecting properties.
10. **Escape hatches for non-rectangular geometry.** Shape library for insertion + drag-points or typed curvature for reshape. Moxisys proves arc-by-drag is discoverable; DEKOPEN should add `set radius/sag` typing to make it precise.

---

## Appendix — competitive landscape for context

| Tool | Model | Interaction |
|---|---|---|
| **Moxisys / WindoorCraft** | SaaS editor + quote + BOM + factory modules | Gesture canvas: drag frame, stroke-direction splits, click-in-region sash, live dims, 3D render. Fastest creation loop seen. |
| **Orgadata LogiKal** | Pro desktop suite (€€€) | Dialog/grid input: Edit→Mullions→type position in mm; "mullion in partial field" → pick field → count → auto-space. Precise, valid, slow. Deep BOM/CNC. |
| **OpenJanela** | Web CPQ/configurator | Wizard: series → family → design → opening type → options → glass. Rules engine; no freehand canvas. |
| **Manufacturer designers (e.g. Selecta Advance70)** | Lead-gen for dealers | Template picker: thousands of preset configs + colour/hardware choices + photo visualiser. Zero drawing — homeowner audience. |
| **Generic canvas editors (Figma/SketchUp as reference)** | — | The bar for snapping, marquee select, type-during-drag, keyboard — none of the fenestration tools reach it. DEKOPEN can. |

**Net:** Moxisys owns the "30-second window" niche — gesture-first, forgiving, mobile-capable; it trades away precision, multi-select, and constraints. Pro tools (LogiKal) own precision via dialogs and lose speed. Nobody combines gesture speed with a typed-ops constraint model — that's precisely DEKOPEN's lane.

## Screenshot manifest

- `m1_workspace_tools.png` — workspace: tool rail, top toolbar (undo/redo/delete/export/import/clean/align/save/3D), right tabs.
- `m2_frame_dims.png` — frame-shape flyout (~45 shapes) + drawn frame w/ live dims.
- `m3_mullions.png` — bay subdivision, chained dims, layout-preset flyout.
- `m4_sash_infobox.png` — casement + sliding sashes, symbols, plan strip, inline dimension edit.
- `m5_arc_redpoints.png` — selection handles (red points/diamond) + frame property toggles.
- `m6_radius_note.png` — arched frame, r= callout, annotation tools, text note.
- `m8_sash_options.png` — sash property sheet (open dir, handle height, hinges, swing, slide dir).
- `m9_3d_render.png` — real-time 3D: wall/floor materials, orbit, share, photo overlay.

(Extracted from Moxisys's own tutorial videos — ch.04 `eo6qYc_rZlI`, ch.05 `stui2w0pr_4`, ch.09 `7ITEeClahF8` on YouTube — hosted at moxisys.com/window-design-software.)
