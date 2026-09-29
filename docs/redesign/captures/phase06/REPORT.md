# Phase-06 — Pricing decision-table evidence

HEAD `280ab98` · branch `devin/1790335313-commercial-workspace` · live dev stack
(Vite :5173 / Django :8000 / Supabase :25321), fixture org. Roles: OWNER (aal2) + ESTIMATOR.

> **Setup caveat:** the running Django `--noreload` was started before `280ab98` landed, so the
> first calc returned `lines` without `unit_price`/`quantity`/`discount_pct` (the new per-line
> selling detail). Restarting Django picked up the new backend — after that the columns populate.
> If evidence ever shows a bare `{position_index, line_net}` line, restart the backend first.

## Captures (desktop 1440×900 unless noted)
- `01-decision-table.png` — pricing decision table: position thumbnails (PositionThumb SVG),
  `Precio unitario` $80.907, `Desc.` −5 %, `Costo línea`, `Neto` with list-price breakdown
  "($161.815 −5%)", `Margen s/neto`, per-line `Δ`.
- `01b-totals.png` — totals column: COSTO TOTAL $246.098 · MARGEN S/NETO $113.585 · 31.6 %
  (flagged "Bajo el margen objetivo") · PRECIO LISTA $378.614 · NETO $359.683 · IMPUESTO $68.340 ·
  TOTAL $428.023.
- `02-compare-band.png` — CURRENT → PROPOSED compare band ("Actual $428.023 → Propuesta …
  Diferencia $0 (0.0%)").
- `03-quote-pdf.png` — emitted quotation PDF page 1 (COT-P-000001-REV-A), TOTAL $428.023.
- `03-portal.png` — customer portal `/cotizacion/<token>`, TOTAL $428.023 (neto/impuesto match).
- `04-blocker-owner.png` — positioned blocker "Falta la cotización de moneda…" + Resolver link.
- `04b-costlists.png` — Resolver link lands on `/pricing/cost-lists` ("Costos y precios").
- `04c-blocker-estimator.png` — same blocker as ESTIMATOR: "Pide al propietario completar este
  dato en Costos y precios." — a `span`, **not** a link.
- `m-pricing-table.png` — mobile 390 pricing (see defect below).

## Results

| Check | Result |
|---|---|
| Decision table: thumbnail + unit price + per-line discount + totals | ✅ all render; mode1 "Margen sobre venta" + formula hint shown |
| `unit_price` renders "—" for old ops | ✅ correct — pre-`line_detail` ops show "—"; fresh ops populate |
| qty>1 consistency | ✅ unit_price 80907.34 × qty 2 × (1−0.05) = 153724 = line_net |
| Margin-compare band | ⚠ band renders ("Actual → Propuesta → Diferencia") but delta is $0 — a real non-zero delta needs a successor revision; the applied REV-A seals the rev so re-calc is blocked by `commercial_revision_required` |
| Missing-price blocker + Resolver (OWNER) | ✅ positioned reason + `/pricing/cost-lists` link |
| Same blocker as ESTIMATOR | ✅ "pídele al administrador"-style hint (span, no link) |
| Amount parity (screen / PDF / portal) | ✅ TOTAL **$428.023** identical on all three |
| Mobile 390 reflow | ✅ **fixed** — `.operation-lines` wrapped in `.operation-lines__wrap{overflow-x:auto}`; page scrollWidth now **390** (was 841), table scrolls internally (wrap scrollW 803 > clientW 316). Capture `10-mobile-390.png` (+ `10b` internally-scrolled). |

## Defects found
1. ~~**Mobile pricing decision table overflows at 390px**~~ — **FIXED.** `.operation-lines` is now
   inside `.operation-lines__wrap{overflow-x:auto}` with `min-width:48rem` on the table → the page
   no longer h-scrolls (`documentElement.scrollWidth=390`, was 841); the ~803px table scrolls
   inside its own container (wrap `scrollWidth 803 > clientWidth 316`, `scrollLeft` verified at
   300). Amount cells stay `nowrap` so figures never split mid-number. Re-captured
   `10-mobile-390.png` / `10b-mobile-390-scrolled.png` at 390×844.

## Honest notes / non-findings
- **Glass-price gap (`missing_glass_authority`):** the fixture has none — `VIDRIO-BASE` /
  `VIDRIO-TERMINADO` are priced, the position editor only offers priced glass, design validation
  rejects unknown glass SKUs at create time, and no `pricing_configurations` rows exist for the
  m² mode (so the mode-2 path that raises it isn't reachable). I exercised the same positioned-
  blocker + Resolver-link machinery via **`missing_fx_authority`** (USD calc, no fx snapshot) —
  identical code path (`BLOCKER_FIX_CODES` → `pricing-fix`). Glass-specific blocker is untested
  for lack of fixture data, not for lack of the feature.
- Emit required confirming suggested handle heights per operable leaf ("Usar sugeridas") before
  "Emitir cotización" enabled — that's the `legacy_handle_migration_confirmed` gate working.
- Non-zero CURRENT→PROPOSED delta not shown because applying REV-A seals the revision; a
  successor revision is required to re-quote (by design, `commercial_revision_required`).
