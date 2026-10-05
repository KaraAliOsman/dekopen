# DEKOPEN — Visual Identity Study

*A design-language proposal for a parametric engineering & quoting OS for PVC/aluminium fenestration.*

Companion boards (attached): `board-01-color-system.png` · `board-02-mark-studies.png` · `board-03-type-spacing.png` · `board-04-icon-grammar.png` · `board-05-document-direction.png` · `board-06-engineer-vs-premium.png`

---

## 0. Derivation thesis

Strong industrial identities are not applied to products — they are *extracted* from them. Braun's brand is Rams's product language; Vercel's mark is a deployment glyph; Mastercard's is the mechanics of interlocking; Aicher's FSB identity was built from the door handle itself; Cooper Hewitt's typeface was generated from the geometry of the museum collection. The pattern: find the artifact's own geometry, codify it into rules, and let every brand decision fall out of those rules.

DEKOPEN's artifact is the **fenestration unit**: a frame assembled from extruded profiles, jointed at miters, dimensioned in millimetres, holding an operable opening. Its identity should therefore be derived from four domain primitives:

| Primitive | What it is | What it yields in the brand |
|---|---|---|
| **Profile section** | The cross-section of an extruded frame member — walls, chambers, webs | Logomark geometry; concentric/offset shape language; icon stroke model |
| **Miter joint** | Two members meeting at 45°; the seam is drawn, never hidden | Signature clipped corner; join rules for strokes & icons; "assembly" motion |
| **Opening** | The void the frame exists to create; in elevation drawings, a triangle whose apex marks the hinge | Icon grammar; the casement glyph; the counterform inside the mark |
| **Dimension** | mm-precision annotation; the dimension line with oblique ticks | Plex Mono as second voice; tick motifs; title-block document structure; selection/handle affordances |

The single sentence for the system: **DEKOPEN is drawn the way the product is drawn** — hairline rules, square miters, visible joints, tabular numbers, and one deliberate accent where a machined surface meets an opening.

Category context matters: fenestration incumbents (Schüco, Reynaers, Jansen) speak in profile-section imagery and engineering greys; fenestration *software* (Klaes, FeneVision, PrefGestalt, the Oknosoft lineage DEKOPEN studies) looks like 2005 enterprise admin. The whitespace: a tool that looks like it was drawn by the people who draw windows. That is the bar — not "modern SaaS", but *the native aesthetic of the trade, executed with Pentagram-level discipline*.

---

## 1. Design language

### 1.1 Shape language — machined, not soft

Corner radius is a semantic signal, not a preference. Fenestration members are cut, milled, and folded — edges are crisp; small chamfers exist to break a sharp edge, not to look friendly.

| Token | Value | Context |
|---|---|---|
| `r-0` | `0` | Canvas objects, drawing sheet, table cells, dimension chips, SVG geometry. The artifact is never rounded. |
| `r-1` | `2px` | Inputs, buttons, chips, badges, menu items — "de-burred edge." Default interactive radius. |
| `r-2` | `4px` | Cards, panels, dialogs, popovers — "folded sheet metal." Maximum radius inside the product. |
| `r-3` | `8px` | Marketing/hero surfaces only. **Banned inside the product** — 8px+ reads consumer SaaS. |
| `r-pill` | `999px` | Status dots and the handle cursor affordance only. Never a pill button; pills read SaaS-generic. |

**Signature detail — the mitered corner.** Exactly one 45° clipped corner may appear on "sheet" surfaces: the drawing canvas, issued documents, the primary preview card, and the brand mark itself. Cut = `8px` legs at the top-right corner (`clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 0 100%)`). Rules: never on controls smaller than 24px (it eats the hit area), never more than one cut corner per surface, never on buttons. A single miter reads as a joint; several read as decoration.

### 1.2 Elevation model — delineation over shadow

Engineering drawings separate planes with line weight, not blur. DEKOPEN uses border-and-tint elevation; shadows exist only for surfaces that genuinely leave the plane (menus, dialogs, drag previews).

| Tier | Mechanic | Use |
|---|---|---|
| **E0 — base** | Flat `g-50` | App frame / workbench |
| **E1 — surface** | `1px` `border-subtle`, no shadow | Panels, cards, inspector — *the default* |
| **E2 — floating** | `1px` border + `0 1px 2px rgb(22 28 31 / 5%), 0 4px 12px rgb(22 28 31 / 8%)` | Menus, popovers, tooltips |
| **E3 — modal** | `1px` border + `0 2px 6px rgb(22 28 31 / 6%), 0 12px 32px rgb(22 28 31 / 14%)` | Dialogs, command bar, drag-ghost |
| **Sheet** | Paper white + `1px` `border-default` + `0 1px 3px rgb(22 28 31 / 7%)` | The drawing/document canvas only |

Banned: colored shadows, shadow spread > 40px, blur/backdrop-filter, inner-glow, multiple simultaneous shadows on a screen (one floating layer at a time — more than one floating surface is a hierarchy bug, not an elevation need).

### 1.3 Density & spacing

DEKOPEN is a professional tool: density should sit between Linear and a CAD inspector — closer to `28px` controls than `40px` marketing buttons.

**Spacing scale (4px base):** `2 · 4 · 6 · 8 · 12 · 16 · 24 · 32 · 48 · 64`. Everything snaps; no `10px`, `14px`, `18px` exceptions — where optical adjustment is needed, it's annotated in code review, not sneaked.

| Context | Value |
|---|---|
| Icon ↔ label gap | `4` (dense) / `6` (default) |
| Control padding (x) | `8` (dense) / `12` (default) |
| Panel padding | `12`–`16`; never `24` inside a rail |
| Field row height (inspector) | `26`–`28` |
| Control height | `28` dense · `32` default · `40` touch-mode only |
| Section gap inside panels | `16`–`24` |
| Rail widths | Inspector `280–320`, project tree `240–280`, tool strip `48–56` |

Density target: an inspector shows **≥ 8 spec fields without scrolling** at 768px viewport height. If a settings surface can't, it's over-padded, not under-sized.

### 1.4 Typography — one superfamily, two voices

**IBM Plex Sans + IBM Plex Mono** is a single engineered system (Plex was literally designed as a coordinated family — the typeface equivalent of a profile system). Plex Mono replaces the current JetBrains Mono: same job, one family.

| Role | Spec | Usage |
|---|---|---|
| Display | Plex Sans SemiBold `32/36`, `-1%` tracking | Document titles, empty-state hero |
| Title L | Plex Sans SemiBold `20/26` | Dialog titles, doc section heads |
| Title M | Plex Sans SemiBold `13/16` | Panel headers, group labels |
| Spec label | Plex Sans Medium `10.5/12`, `+8%` tracking, uppercase, `g-500` | Field labels, table headers, units keys — the "drawing sheet" voice |
| Body | Plex Sans Regular `13/18` | Default UI text |
| Body strong | Plex Sans Medium `13/18` | Emphasis in lists/tables |
| Dense cell | Plex Sans Regular `12/16` | Table rows, list secondary |
| **Dimension** | **Plex Mono Regular `12/14`** | All measured values: `2 400 × 1 800 mm`, prices, counts, IDs |
| Micro-dim | Plex Mono Regular `10.5/12`, `g-500` | Coordinates, tolerances, hashes |

Number rules (they carry the brand):

- `font-variant-numeric: tabular-nums` is **mandatory** wherever numbers can update or align in columns.
- Thousands separated by thin space (`12 400`), never comma-localized in engineering contexts; decimal per locale.
- Real glyphs: `×` not `x`, `−` not `-`, units always present and lowercase (`mm`, `m²`, `kg`, `°`).
- Units render at `~85%` size in `g-500` when inline with a dim value: `2 400`▸`mm`.
- Weights: 400/500/600 only. 700 appears in issued documents only — the product never shouts.

### 1.5 Motion — assemble, don't animate

Motion communicates manufacturing: parts move along axes and *dock*; nothing blobs, bounces, or breathes.

| Token | Value | Use |
|---|---|---|
| `t-micro` | `90ms` | Hover color/opacity |
| `t-state` | `160ms` | Press, toggle, selection |
| `t-spatial` | `220ms` | Panel slide, dialog in/out, tab switch |
| `t-max` | `280ms` | Hard ceiling — nothing exceeds this |

- **Easing:** enters `cubic-bezier(.2, 0, .38, 1)`; exits `cubic-bezier(.4, .14, 1, 1)` at ≤`120ms`. No overshoot springs on UI chrome.
- **Axis-locked:** panels translate on X or Y only — never diagonal scale-and-fade. The signature: surfaces *dock* into place, like a member seating into a joint.
- **Canvas:** wheel zoom and pan are direct 1:1 (no tween); programmatic fit-to-view may use a single `250ms` ease-out.
- **Stagger:** sequential docking may stagger ≤`30ms` × ≤3 items (e.g., inspector groups). More = choreography, not engineering.
- **Banned:** elastic/bounce on chrome, blur transitions, animated gradients, loading spinners that rotate decorative shapes (use the dimension-tick loader: a tick drawing itself 0→100%).

---

## 2. Brand-mark thinking

Four directions, each derived from a fenestration primitive. All assume the wordmark `DEKOPEN` set in **Plex Sans SemiBold, uppercase, tracking `+0.06em`**, `g-950`; on dark surfaces `g-25`. The wordmark never gets a gradient, an outline, or a ligature gimmick.

### Direction A — *The Miter* (joint)

**Construction:** two rectangular members (ratio `7:1`, wall `w`) meeting at a corner. The joint line is drawn as a `45°` seam — the seam is the mark. At display size the two members form a corner that reads as an abstract `D` opening; at small size it's a clean corner glyph.

- Geometry: outer corner `24×24`, member width `w = 4.5` (≈ `1.5×` the icon stroke), seam line `w×0.5` at `45°`.
- The seam is `paper`-colored (knockout) — the joint is *visible*, which is the brand idea: assembly is honest.
- Favicon: corner glyph, `teal-800` members on paper, or knockout teal on `g-950`.
- Risk/character: most abstract; reads "engineering" to anyone who's ever cut a frame, reads "corner bracket" to everyone else. Strong favicon.

### Direction B — *The Section* (profile cross-section) — **recommended primary**

**Construction:** a square ring — the cut face of a hollow extruded profile — with one internal web dividing the chamber. Literal product: the thing DEKOPEN manufactures.

- Geometry: outer `24×24`, `r-1` outer corners, wall `2.5`, inner web `2` placed at `1/3` width (asymmetric — symmetric reads like a grid icon).
- The counterform (the chamber) is the "opening" — the mark literally contains the product's purpose.
- Drops into the wordmark's `O`: `DEK`⧈`PEN` — the section *is* the O. This is the ownable moment: a letter replaced by the artifact.
- Favicon: section on `teal-800`, chambers knocked to paper.
- Scales perfectly: at 16px it's a ring with a web; at 160px the web/chamber logic still holds. Print on profile stickers, BOM sheets, machine labels — it IS the part.

### Direction C — *The Casement* (opening symbol)

**Construction:** the elevation drawing itself — a `24×20` frame containing the opening triangle (apex on the hinge edge, per drawing convention §4). Optionally dashed for "opens away" variants.

- Geometry: frame stroke `2`, triangle stroke `1.5`, apex at `40%` along the edge (real drafting places it off-center; center reads like a play button — avoid center).
- Character: the most domain-native; instantly legible to anyone in the trade as "a window that opens."
- Risk: conflicts with §4's icon grammar — inside the product the same glyph already *means* "operable sash." Recommend keeping the casement grammar for icons/documents rather than the primary mark, or using it as the **product** mark while Section is the **company** mark (a viable two-tier system).

### Direction D — *The Dimension* (measurement)

**Construction:** the wordmark framed by a dimension line — extension ticks at the `D` and `N` stems, oblique `45°` ticks at the measurement points, dimension text `9 80` (arbitrary mm) set in Plex Mono `10.5` beneath.

- Geometry: extension lines overshoot the baseline by `2`; dimension line `0.75` weight, ticks `45°` × `3` long.
- Character: "we are the measurement" — the most explicitly engineering statement of the four; strong as a lockup variant for documents/splash, weak as a 16px favicon.
- Recommend as **secondary lockup** (letterhead, quote cover, about screen) rather than the app icon.

**Recommendation:** Direction B as primary mark (ownable, scales, literal product, O-slot trick is the memorable moment); Direction D as document lockup; Direction C's grammar stays inside the product as the opening-symbol icon family where it carries real meaning.

---

## 3. Complete color system

The palette is ~75% graphite, ~20% teal, ≤3% orange, ~2% semantic — per the palette contract already in `tokens.css`. Teal is the metal (anodized, engineered); orange is the mark — used only where the brand signs something or the artifact needs attention.

### 3.1 Ramps

**Graphite** (cool, slight teal cast — "machined steel", never warm grey):

| Step | Hex | Primary roles |
|---|---|---|
| g-950 | `#161C1F` | Ink / primary text / profile strokes |
| g-900 | `#252D31` | Strong secondary, dark chrome (command bar) |
| g-700 | `#465158` | Secondary text, dimension text, icon stroke |
| g-500 | `#727D82` | Muted text, guides, disabled-strong |
| g-400 | `#9AA6A9` | Disabled text, placeholder |
| g-300 | `#CDD5D6` | Border default, table rules |
| g-200 | `#E0E6E5` | Hairline border-subtle, separators |
| g-100 | `#EEF2F1` | Hover wash, inset/card fill, disabled bg |
| g-50 | `#F5F7F6` | App background / workbench |
| g-25 | `#FCFDFC` | Panel surface |
| paper | `#FFFFFF` | Drawing sheet / document surface |

**Teal** (the metal):

| Step | Hex | Primary roles |
|---|---|---|
| teal-950 | `#042E2C` | Deepest text-on-tint, print accents |
| teal-900 | `#064440` | Pressed state on fills, doc accents |
| teal-800 | `#075F5A` | **Primary fill** (buttons), brand deep, white text (7.5:1) |
| teal-700 | `#0B7770` | **Interactive text/links** on white (5.3:1), dim accents |
| teal-600 | `#0F8F85` | Borders, focus ring, icons, canvas accents (3.9:1 — no small text) |
| teal-500 | `#20A79A` | Large-area fills on tints, dark-theme interactive |
| teal-400 | `#48BCAF` | Charts, secondary canvas marks |
| teal-300 | `#7FD4C8` | Tinted strokes, highlights on teal surfaces |
| teal-200 | `#B0E4DC` | Soft fills |
| teal-100 | `#D4EFEA` | Softer fills |
| teal-50 | `#E6F4F2` | Selection wash, glass/glazing tint base |

**Orange — "the mark":**

| Step | Hex | Use |
|---|---|---|
| orange-700 | `#A84418` | Text on orange tints |
| orange-600 | `#C24E1E` | Pressed / strong flag |
| orange-500 | `#E56A32` | **Brand mark + attention flags** — the signature |
| orange-400 | `#ED8653` | Hover on mark elements |
| orange-300 | `#F3AC84` | Flag tint stroke |
| orange-100 | `#FBEBE2` | Flag surface |

**Semantics** (aligned to existing `tokens.css` values):

| Role | Base | Soft | Ink (text on soft) |
|---|---|---|---|
| Success / in-tolerance | `#1E7A4C` | `#E3F2EA` | `#13502F` |
| Warning / soft constraint | `#B25E09` | `#FDF1E3` | `#7A3D05` |
| Danger / invalid, destructive | `#B3372F` | `#FBE9E7` | `#7E1F19` |
| Info | `teal-700` | `teal-50` | `teal-900` |
| **Manufacturing-attention** | `#E56A32` | `orange-100` | `orange-700` |

The deliberate call: **manufacturing-attention = the signature orange.** Valid-but-needs-human-judgement (special machining, nonstandard tolerance, shop decision) is the one thing orange is *for* — so the brand mark and the attention flag share one ink. Orange therefore always means "this needs a person," which is why it must never appear on a CTA, badge spam, or decoration. Budget: ≤3% of pixels on any screen.

### 3.2 Functional roles — light theme

| Token | Value | Notes |
|---|---|---|
| `bg-app` | `g-50 #F5F7F6` | Workbench |
| `surface-panel` | `g-25 #FCFDFC` | Rails, inspector |
| `surface-card` | `g-100 #EEF2F1` | Inset regions |
| `surface-sheet` | `paper #FFFFFF` | Canvas/document sheet — *whiter than chrome*: paper is white, metal is off-white |
| `surface-hover` | `#E2E8E7` | Row/item hover |
| `surface-active` | `#D4DEDD` | Pressed state |
| `surface-selected` | `teal-50 #E6F4F2` | Selected row (+ `2px teal-700` left bar) |
| `surface-disabled` | `g-100` + `text g-400` | — |
| `border-subtle` | `g-200 #E0E6E5` | Hairlines inside panels |
| `border-default` | `g-300 #CDD5D6` | Panel/card edges, table rules |
| `border-strong` | `#A9B4B6` | Emphasis edges, hover borders |
| `border-focus` | `teal-600 #0F8F85` | `2px` ring, `1px` offset, always visible |
| `text-primary` | `g-950 #161C1F` | 15:1 on panel |
| `text-secondary` | `g-700 #465158` | ~7.4:1 |
| `text-muted` | `g-500 #727D82` | ≥ large text only |
| `text-disabled` | `g-400 #9AA6A9` | Non-interactive only |
| `text-on-fill` | `#FFFFFF` | On teal-800/900 |
| `interactive` | `teal-700 #0B7770` | Links, text buttons, interactive icons |
| `interactive-fill` | `teal-800 #075F5A` | Primary buttons; hover `teal-700`; pressed `teal-900` |
| `mark` | `orange-500 #E56A32` | Brand + attention flags only |

### 3.3 Canvas roles — the drawing speaks the same language

| Token | Value | Use |
|---|---|---|
| `canvas-sheet` | `paper` | The sheet floats on `bg-app` via `1px` border + E1 shadow |
| `canvas-grid` | `#DCE4E2` dots / `#EAF0EE` lines | Recessive; never fighting geometry |
| `canvas-member` | `g-950`, `1.5px` | Frame/profile strokes |
| `canvas-dim` | `g-700` text · `g-500` lines `1px` | Plex Mono `11px` on canvas scale |
| `canvas-glazing` | `rgba(15,143,133,.07)` fill · `teal-600` stroke | Existing `--theme-glass-tint` preserved |
| `canvas-opening-symbol` | `g-700`, `1.25px` | Solid = opens toward viewer; dashed = away |
| `canvas-selection` | `teal-600` outline `1.5px` + `teal-600 @8%` fill | Marquee = teal-600 dashed |
| `canvas-handle` | `orange-500` fill, `paper` stroke `1.5px` | Manipulation affordance = mark-orange (existing warning-orange handles migrate) |
| `canvas-snap` | `success` dashed `6 4` | Existing convention preserved |
| `canvas-preview` | `orange-500` dashed `8 5` | Resize/deform ghost |
| `canvas-invalid` | `danger` + `45°` hatch `danger @20%` | Invalid member — hatch ensures it's legible without color |

### 3.4 Mapping to existing tokens

The proposal extends rather than replaces `frontend/src/styles/tokens.css`: repo `--theme-accent #0f817a` sits between teal-700/600 — pick `teal-700 #0B7770` for text contexts, `teal-600` for stroke contexts, adding the ramp ends the repo lacks (950–900 deep teals, orange tints). `--theme-warning` on canvas handles/resize-preview should migrate to `mark` orange — attention meaning unified. Dark theme: existing dark tokens already map 1:1 onto this system (`#2aa69b ≈ teal-500`); no rework needed beyond naming.

---

## 4. Iconography — the fenestration icon grammar

Icons are technical drawings at 24px, not pictograms. Two rules define the whole system:

1. **Stroke model:** `1.5px` monoline on a `24px` grid, `2px` safe margin, **square caps and miter joins** (the joint signature — round caps read as friendly-SaaS), interior corner radius ≤`1px`. Active state swaps stroke for fill — never a colored background blob.
2. **The opening-symbol family uses real drafting convention** (EN 12519 lineage): the sash carries a triangle; the **apex sits on the hinge edge**, the open base on the handle edge. **Solid line = opens toward viewer; dashed = opens away** (hidden-line logic). This is the same grammar the canvas, the icons, and the issued documents share — a user learns it once.

| Glyph | Construction |
|---|---|
| Fixed glazing | Plain sash rectangle — no triangle. Fixed = silent. |
| Casement L/R | Triangle apex on left/right edge (apex ≈ `40%` along edge, not centered — centered reads "play") |
| Tilt (bottom-hung) | Apex at bottom |
| Awning (top-hung) | Apex at top |
| Tilt-turn | Two triangles: apex side + apex bottom — the mechanism drawn honestly |
| Sliding | Arrow line parallel to track, `↔` or directional `→`; pocket = dashed |
| Folding | Zig-zag sash division + direction arrow |
| Door / swing | Quarter-arc from hinge corner (plan convention) |
| Pivot | Centerline + rotation arrows |

Supporting vocabulary, same stroke model: **mullion, transom, coupler, glazing bead, profile section (the Direction-B ring — logo reuse as icon), dimension (oblique tick line), cutting list, miter saw, handle, hinge, weld seam**. Hardware drawings are sectioned, not silhouetted. Prohibited in icons: gradients, second colors beyond semantic accents, perspective/3D, drop shadows, emoji-adjacent faces.

---

## 5. Document / PDF direction — the quotation as drawing sheet

Current state (`backend/documents/renderers.py`): HTML→WeasyPrint, es-CL locale, US Letter (`carta` — correct for Chile), and an off-brand navy `#163b66` + slate system with Arial. The pipeline is right; the design language isn't DEKOPEN yet. The fix is a palette/type swap plus one structural upgrade.

**The structural upgrade — the title block.** Engineering sheets carry an ISO-7200-style title block. DEKOPEN documents get one: a bottom-strip field grid (project · doc type · doc no · rev · date · page · **BOM fingerprint**) in `0.35pt` rules, `6.5pt` uppercase spec labels, `8pt` Plex Mono values. The frozen BOM hash — already generated as `bom-identity` and currently buried in a footer string — moves *into* the title block as a named field. The product's core invariant (frozen authority) becomes a visible brand feature: **every DEKOPEN document carries its fingerprint in the same place, like a drawing number.**

**Layout spec (Letter, `14/12/18mm` margins as existing):**

- **Masthead:** wordmark left `teal-800`; right-aligned mono meta (`DOC-01 · REV B · 2026-09-23`) `g-700`; `1.5pt` `teal-800` rule beneath, then `0.35pt` `g-300` hairline. Signature move: the header block carries the `8px` miter cut top-right — the sheet is mitered like the frame it quotes.
- **Position cards:** each line item is a card: left `45mm` column = elevation drawing **using the §4 opening-symbol grammar** (the icon system pays off on paper); right = spec table (profile system · glazing · Uw · finish) hairline-ruled, values in mono.
- **Lines table:** `0.35pt` `g-300` rules, header row `g-50` fill + `7pt` uppercase spec labels, **no zebra striping** — engineering tables separate with rules, not tint. Numbers right-aligned, mono, tabular.
- **Totals:** right column, thin `teal-800` top rule, grand total `14pt` SemiBold `g-950` — one loud moment per page.
- **Orange:** appears only for attention flags (special machining, manual check) — on paper it reads as the flagged dimension on a shop drawing. Correct and rare.
- **Palette swap:** `#163b66 → teal-800`, `#e7edf4 → g-50`, `#cbd5e1 → g-300`, `#475569 → g-700`, `#eef3f8 → teal-50` (hero), `#991b1b → danger ink`. Arial → embedded Plex Sans/Mono.

A premium quotation reads: sober sheet, one teal rule, a mitered corner, elevation drawings that look like the product, mono numbers you could cut against, a fingerprint in the title block. Premium here = *authority*, not decoration.

---

## 6. "Engineer tool" vs "premium product" — the critique checklist

Apply to screenshots. Each item is pass/fail; the right column is what "generic SaaS" does instead.

| # | Check (engineer/premium reads YES) | SaaS tell (reads NO) |
|---|---|---|
| 1 | Every number in Plex Mono + tabular, units present (`2 400 mm`) | Proportional digits, `2400`, "x" for `×`, missing units |
| 2 | Radii ≤`4px` product-wide; sheets carry the `8px` miter | `8–16px` cards, pill buttons, squircle everything |
| 3 | Hierarchy by border + weight + spacing; ≤1 floating shadow on screen | Colored/large shadows, stacked cards on cards, glow |
| 4 | Orange = flag/mark only, ≤3% of pixels, always meaningful | Orange on CTAs, badges, decorative accents |
| 5 | Teal-800 fills / teal-700 text; no other chroma in chrome | Random hues per feature, rainbow nav |
| 6 | Field labels uppercase `10.5px +8%` spec voice; terminology = sash/mullion/transom/glazing/tolerance | "Settings", "Stuff", marketing verbs, emoji |
| 7 | Inspector shows ≥8 fields above fold at 768px; 28–32px controls | 48px touch targets on desktop, page-of-padding |
| 8 | States are explicit: mono badges, ticks, rules, hatch | Colored dots without labels, vibes-based status |
| 9 | Canvas = paper sheet on workbench; chrome and paper are different values | Canvas and UI blend into one grey soup |
| 10 | Selection = outline + tint + handles (drawing-tool behavior) | Hover-glow, lift-on-hover cards |
| 11 | Icons: `1.5px` miter-joined monoline, opening triangles per convention | Mixed stroke weights, filled blob icons, 3D emoji |
| 12 | Focus ring `2px` teal-600 visible everywhere | No visible focus, or browser-default blue ring |
| 13 | Motion ≤`280ms`, axis-locked docking | Bounce, fade-up-stagger hero animations, animated skeleton shimmer |
| 14 | Dialogs ask spec-sheet questions: *"Apply to 3 positions?"* | Exclamation points, "Awesome!", playful error jokes |
| 15 | Tables rule-separated; docs carry title block + fingerprint | Zebra stripes, rounded table containers, hash hidden |
| 16 | Zero gradients, zero blur-glass, zero glow, zero AI-purple | Any of those = automatic fail, full stop |

**The summary heuristic:** if a screenshot could be a Figma plugin promo — soft shadows, rounded cards, gradient accent, friendly copy — it fails. If it could be a page from a Schüco technical manual or a machined-part drawing — hairlines, mono numbers, one controlled teal — it passes. Premium ≠ decorated; premium = *nothing is arbitrary*.

---

## Appendix — token delta for `tokens.css`

```css
/* proposed additions on top of existing tokens */
--g-400: #9AA6A9;              /* disabled text */
--border-subtle: #E0E6E5;      /* hairline (was #d9dfde — keep either, pick one) */
--teal-800: #075F5A;           /* primary fill */
--teal-700: #0B7770;           /* interactive text */
--teal-600: #0F8F85;           /* strokes/focus */
--teal-50:  #E6F4F2;           /* selection wash (≈ existing accent-soft) */
--orange-700: #A84418; --orange-100: #FBEBE2;
--attention: var(--theme-mark); /* manufacturing-attention = mark orange */
--canvas-handle: var(--theme-mark);   /* migrate from --theme-warning */
--font-dim: "IBM Plex Mono";   /* replaces JetBrains Mono — one superfamily */
```
