# Phase-08 — Compras → Recepción → Stock → Retazos (live verification)

Branch `devin/1790335313-commercial-workspace`, HEAD `c685f5b` + fix commits through `f6da4de`.
Stack: Vite `:5173`, Django `:8000` (restarted to pick up fixes), Supabase local `:25321/:25322`, Mailpit.
Roles used: OWNER (purchasing writes), WORKSHOP_MANAGER (receptions), ESTIMATOR (read-only check).
Fixture org `548b9ce5-…`, project P-000008 (REV-A), emitted version `e7fe66a1`.

> **Environment caveat:** the session's X server died mid-run — all evidence was captured
> on a self-hosted Xvfb :99 + CDP Chrome :9333 (no video recording possible).
> Viewport floor on this WM is ~500 px (Emulation.setDeviceMetricsOverride is inert on
> Chrome 137 headful), so mobile evidence is at iw=500 with mobile CSS active.

## New UI flags (this commit)

| Flag | Result |
|---|---|
| Orders index "Recepciones" col + red `dañado: N` when damaged_qty>0 | ✅ PASS — `2 dañado: 1.00` renders on COMPLETADA (PO-BA828…) and ANULADA (PO-4D0C…) rows (`j3-final-orders-index-danado.png`) |
| CANCELLED order "liberado al cancelar: N" + "Volver a pedir" deep-link | ✅ PASS — card shows "Anulada el 28-09-26 · liberado al cancelar: 3.0000"; clicking scrolls to `#purchasing-type-SUPPLIER_GLASS_PO` (scrollY 0→1835, anchor at top=0) (`j3-final-cancelled-card.png`) |
| `consolidateHint` on duplicate purchasing_sku sections | ✅ PASS — "con el mismo SKU de compra se consolidan en la misma orden al asignar un solo proveedor; la traza …" (`01-consolidate-hint-glass.png`) |
| "Unidades recibidas con incidencia" alert when damaged_qty>0 | ✅ PASS — "Unidades recibidas con incidencia: 1.00" on the cancelled glass card |
| Spanish error detail (69a8ff8) | ✅ PASS (API level) — `order_state_invalid` → "El pedido no admite esa acción en su estado actual; revisa recepciones y estado."; `request()` renders `error.detail` in the banner (code path verified) |

## Acceptance journeys

### J1 — need→order→partial reception w/ damage→remaining→reserve→consume ✅
Perfil (COMPRA-*) need → eligibility → allocation → confirm → PO-BA828D59850D (SENT) →
partial reception w/ `damaged_qty>0` → remaining reception → optimize OT → stock
reservation → CUT START+COMPLETE consumption. Conservation exact; traceability refs
(M-29…M-32) on requirement rows + "Movimientos recientes" receipts carry rack/user/lot.
(`00-08`, `j1-final-traceability.png`, `j1-final-movements.png`)

**Damaged units never reach stock** — verified in `inventory_movements`: receipt
recv3/dmg1 → RECEIPT movement 2.00 only; cancelled-order line recv1/dmg1 → **no
movement at all**. Usable glass = 4 = original demand (1 kept + 3 reordered, both
SPEC rows: aa63=3, 4f90=1@RG).

### J2 — cancel DRAFT/SENT un-received ✅
3 hardware orders cancelled (PO-56D3…/6848…/9BFA…). Need re-appears pending;
"Volver a pedir" present; re-buy did NOT duplicate demand.

### J3 — cancel with partial reception ✅ (after fixes 67b1fd5 → f6da4de)
PO-4D0CD9D0F336 (glass): received 1 good @ Galpón B + 1 recv/1 dmg @ Galpón A, Acceso
unreceived → cancel → `released_qty = 3.0000` (1+0+2 exactly); kept good still covers;
requirements reopen with `open_qty` 2+1; re-confirm creates PO-215FE6334C1B covering
exactly 3 (not the original 4) — no dup demand. Dialog copy explains "lo ya recibido
se conserva… sólo lo no recibido vuelve".

**Fixes verified live** (each was a defect I hit and escalated):
- `cc5167f` — purchasing_state SQL split by trailing `", "` (was 500).
- `18a06d8` — `list_remnants` `set→sorted` for `ANY(::uuid[])` (was 500).
- `19bc848` — migration 20261228000005 adds PARTIALLY_RECEIVED→CANCELLED to
  `guard_order_evidence` (was 409 documentary_transaction_rejected; UI silent).
- `5b1fb2d` — confirm no longer requires len(allocations)==len(unclaimed)
  (was 422 order_type_allocation_incomplete).
- `69a8ff8` — Spanish error detail map (verified order_state_invalid text).
- `f6da4de` — `_line_snapshot(quantity_override=)` kwarg (was 500 TypeError).

### J4 — concurrent cover / idempotent retry ✅
`confirm_order_type_batch` advisory-locked; re-confirm on an already-claimed type
returns the live orders (same id + snapshot hash, no duplicates). Verified again after
the partial-release rewrite: re-confirm SUPPLIER_GLASS_PO → same PO-215FE6334C1B.

### J5 — inventory no-merge + search ✅ (with one gap)
- Two VIDRIO-TERMINADO rows stay distinct (fixture 500 + received spec unit @RG) — no merge.
- Live filter "SKU o especificación…" works (VIDRIO-TERMINADO→2 rows, RG→1).
- **Gap:** composition text ("4-16-4", "Float") is NOT searchable — filter covers
  sku+name+racks only. If "search by specification" means glass spec text, it's partial.
- Remnant search: code/RET-id/SKU/material/color/rack all match; status-filter composes
  (Consumido + C53123FA → 1 row).

### J6 — remnants lifecycle ✅
2 BAR remnants created **via UI** (RET-36CE251F COMPRA-MARCO 1250 mm @RACK-B1;
RET-6A9917C8 COMPRA-JQ-10 480 mm @RACK-B2; Disponible 6→8). Identity/material/length/
rack/status columns render. 5500 mm remnant via API → optimize OT-03 consumed it
(`remnants_consumed:1`, atomic UPDATE … WHERE AVAILABLE, refuses partial claim) →
CUT COMPLETE → CONSUMED + child RET-0A89947B 4560 mm origin=PRODUCTION,
`origin_order_id=OT-03` (linked traceability). Consumed filter shows it; Desechar
hidden on consumed.

### J7 — mobile reception 🔶 PARTIAL (layout defect)
Could not reach true 390 px in this env (WM floor ~500; Emulation override inert).
At iw=500 with mobile CSS active:
- Page `scrollWidth` 830 → **1089** with receiving open; the reception table is
  **1052 px inside a plain `FORM` (`overflow-x:visible`)** — no scroll wrapper, no
  stacked layout. Same class of defect fixed for `.operation-lines` in phase 06.
- Controls DO work mechanically at that width (Recibir todo → Registrar recepción
  → order FULFILLED, 2+1 exact) but Lote/Rack inputs are off-screen — operators
  must hunt horizontally. (`j7-03…j7-06`)
- **Defect:** wrap `purchasing-receiving table` in `overflow-x:auto` or stack-card <640 px.

### J8 — PO document parity ✅
DOC-02 for the cancelled glass order: PDF (1 page) + XLSX match the screen —
Vidrios del Sur Ltda, PO-4D0CD9D0F336, P-000008 · REV-A, entrega 18-10-2026,
3 lines (2+1+1 EA), areas, TOTAL 6.531276 m². XLSX adds a Trazabilidad block
(I-01/I-02/I-04/I-03). (`doc02-pedido-vidrio.{pdf,xlsx}`, `j8-01`)
- **Wrap quirk:** SKU "VIDRIO-TERMINAD O" breaks mid-token without hyphen in PDF.

## Other observations

- `Pendiente` column shows **−4.0000** on PO-41EC4DF2EDDE — an over-receipt
  (5 vs 1 ordered) is allowed by design (fulfilment comment: "an over-receipt on one
  line must not hide a shortfall on another") but renders as negative pending instead
  of e.g. "0 (+4 excedente)". Cosmetic; flagging for a decision.
- Estimate-only roles (ESTIMATOR) see zero mutating controls on purchasing
  (canWrite gate) — verified by session.
- No offline/pending-queue claims made (per mandate scope).

## Defects / fixes during this run (all resolved unless noted)

| # | Severity | Item | Status |
|---|---|---|---|
| 1 | 🔴 | purchasing_state 500 — JOIN SQL split on `", "` | ✅ fixed `cc5167f` |
| 2 | 🔴 | inventory/remnants 500 — set→ANY(uuid[]) | ✅ fixed `18a06d8` |
| 3 | 🔴 | trigger missing PARTIALLY_RECEIVED→CANCELLED | ✅ fixed `19bc848` |
| 4 | 🔴 | confirm required len(alloc)==len(unclaimed) after partial cancel | ✅ fixed `5b1fb2d` |
| 5 | 🔴 | `_line_snapshot` kwarg `quantity` vs `quantity_override` → 500 | ✅ fixed `f6da4de` |
| 6 | 🔴→open | Mobile: reception table 1052 px, no scroll wrapper; page sw=1089 @iw500 | ❌ open |
| 7 | 🟡 | Over-receipt shows `Pendiente -4.0000` (negative) | ❌ open (cosmetic) |
| 8 | 🟡 | PDF SKU "VIDRIO-TERMINAD O" mid-token wrap (no hyphen) | ❌ open (cosmetic) |
| 9 | 🟡 | Spec/composition text not searchable in stock filter | ❌ open (gap) |

## Captures

`00-*`–`10-*` — J1/J2 original run; `j3-*` — cancel-partial chain + cancelled card +
re-buy; `j5-*` — stock no-merge + live filters; `j6-*` — remnants create/consume;
`j7-*` — mobile overflow + receiving at iw=500; `j8-*` + `doc02-pedido-vidrio.*` —
DOC-02 parity; `j1-final-*` — traceability refs + movements.
