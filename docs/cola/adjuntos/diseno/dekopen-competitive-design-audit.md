# DEKOPEN — Competitive Design Audit

*How professional fenestration/engineering software looks, and where DEKOPEN's teal/graphite identity + emitted PDFs sit against it.*

**Method:** live screenshots of Logikal 12.x (Orgadata), PrefSuite PrefOne, Oknosoft light builder inspected; DEKOPEN audited directly from source — `frontend/src/styles/tokens.css`, `index.css`, `features/canvas/canvas.css`, radius/font usage across `src/`, and `backend/documents/renderers.py` (`_CSS`, `_position_svg` — SVG output rendered verbatim, see attached board).

---

## 1. What the incumbents actually look like

Three archetypes, all shipping commercially credible product:

**Logikal (Orgadata) — desktop suite, "MS Office" chrome.** A dense checkbox ribbon on a Windows-blue band; a left wizard checklist (`Element → Verglasung → Beschläge → … → Abschließen`); the CAD canvas takes the whole middle: 3D element + profile-section drawings on the right/bottom. Dated chrome, but *every catalog dimension is reachable* — credibility comes from completeness and convention, not finish. *(ref-Orgadata-2.jpg)*

**PrefSuite — desktop suite, drafting-first.** PrefOne's editor is a pure technical drawing: white canvas, thin grey frame linework, cyan glass tint, profile **sections pinned to the perimeter dimension lines** (the fenestration "shop drawing" convention), raw mm labels `L1 = 750`, `A2 = 700`, `Vão = 1.505`. Zero decoration; the drawing IS the interface. *(ref-prefsuite.png)*

**Oknosoft — open-source web builder, ERP chrome.** Dhtmlx enterprise grid: toolbar + order table + left status filter tree, typology thumbnails as the only drawn surface. Grey/neutral, dense, 1C-style — credibility comes from data coverage. *(ref-oknosoft-orderlist.png)*

**Modern engineering tools (Linear/Figma/pro-app tier)** — the other pole: restrained chrome, one accent, border-first elevation, mono for anything numeric, keyboard-first. Credibility = restraint + precision.

**The shared grammar** — what reads "engineering" in all of them:

| Pattern | Credibility it buys |
|---|---|
| White/light canvas; drawing is the hero, chrome recedes | seriousness of purpose |
| Thin neutral linework for frames; ONE cold glass tint | drafting convention |
| Opening triangles (EN-12519: apex = hinge, solid = toward) | trade literacy |
| mm dimensions as first-class annotations in mono | precision as identity |
| Dense but *complete* surfaces — every parameter reachable | competence |
| Zero decorative color on the canvas; accent reserved for semantics | restraint |

**Immaturity markers** (none of the incumbents have them): rounded bubbly chrome, decorative color families, drop-shadow cards, gradients, icon sets that don't match the domain's drawing conventions, generic invoice-table documents.

---

## 2. Audit matrix — DEKOPEN today

| Surface | What's there now | Verdict |
|---|---|---|
| Base type | IBM Plex Sans already declared (`index.css:19`) | Credible — migration started |
| Mono | IBM Plex Mono declared but JetBrains Mono still primary in 8 files | Mixed — finish the swap |
| Radii | `0.5rem`/8px dominant (×11), 12px + `999px` pill outliers | **Immature** — generic-SaaS softness vs the machined ≤4px language |
| Elevation | Border-first: only ONE box-shadow in `src/` (an inset accent bar) | Credible — matches modern-tool restraint |
| Prohibited look | Zero gradients, zero `backdrop-filter` in `src/` | Credible — no decoration debt |
| Accent discipline | Teal accent tokens, orange `--theme-mark` `#E56A32` | Credible |
| Canvas ink | Teal accent strokes, mono dims, EN opening glyphs | Credible grammar |
| Canvas semantics | `resize-handle` uses `--theme-warning` orange | **Off-signal** — orange should mean coupler/attention, not affordance |
| **Emitted drawing** (`_position_svg`) | Correct EN grammar + coupling already `#E56A32`; **but** element ink navy `#163B66`, glass pale-blue `#EEF3F8`, threshold red `#991B1B`, module labels slate `#64748B` | **Immature** — right grammar, wrong ink; reads as a different product; red reads as an error |
| **Document chrome** (`_CSS`) | Arial + navy/slate, all-bordered tables, uppercase-th-on-grey | **Immature** — generic invoice look; disconnected from the product's own voice |
| Document signature | `bom-identity` hash in footer, letter portrait, es-CL | Credible — the frozen-BOM fingerprint is a real brand asset |

**Headline:** the *product chrome* is ~80% of the way to credible-modern (cleanest part is what it does NOT do — no gradients, no shadow stack); the two gaps are radius scale and the mono remnant. The *emitted artifacts* — the thing a customer actually holds — are the immature layer: a navy/Arial identity that predates the product's own system.

## 3. Credible vs immature — the short list

**Immature today (fix in order):**
1. PDF layer identity disconnect — Arial + `#163B66` navy + slate: swap to Plex/graphite/teal; keep letter portrait, `bom-identity`, es-CL; promote the hash to a visible "BOM fingerprint" field per the identity study's title-block spec.
2. Emitted SVG ink — recolor `#163B66→#252D31` graphite, `#EEF3F8→teal-50` glass, `#991B1B→#252D31` (a threshold is not an error); keep `#E56A32` couplings — already correct.
3. Radii — `0.5rem → ≤4px` scale, remove `999px` pill and 12px outliers; keeps the machined language.
4. JetBrains Mono remnants — 8 files; complete the Plex Mono switch.
5. Canvas `resize-handle` — migrate from `--theme-warning` to `--theme-mark` so orange keeps a single meaning.
6. Document tables — replace full `1px` grids with horizontal hairlines only (incumbent documents and pro invoices both rule rows, not cages).

**Already credible — keep:**
- Single-envelope brand: teal/graphite/orange with orange = coupler/attention only.
- EN-12519 glyph grammar shared identically between canvas and emitted drawings — the *grammar* is right; only the ink is wrong.
- `bom-identity` fingerprint — an authenticity mark incumbents don't have.
- Density direction: DEKOPEN already favors dense technical surfaces over padded cards — aligned with the credibility axis.

## 4. The positioning call

DEKOPEN's defensible spot is the **intersection of the two poles**: the incumbents' drafting convention (sections, triangles, mm — the trade's own literacy) delivered through modern-tool restraint (one accent, border-first, mono, no decoration). Logikal and PrefSuite prove convention sells to fabricators; they are also the evidence that the convention can survive 30 years unchanged — DEKOPEN does not need to invent a drawing language, it needs to speak theirs *cleanly*, on the web, with a document layer that looks like the same product drew it.

## References
- `ref-Orgadata-2.jpg` — Logikal 12.x (ribbon + wizard + CAD, profiel-online.nl)
- `ref-prefsuite.png` — PrefSuite PrefOne 2D typology editor (prefsuite.com.br)
- `ref-oknosoft-orderlist.png` — Oknosoft dealer order UI (oknosoft.ru)
- `board-audit-position-drawing.png` — DEKOPEN's real emitted SVG rendered verbatim vs brand-restored
