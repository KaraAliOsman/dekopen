# Phase-07 — commercial proposal live flows

HEAD `e82e17e` · branch `devin/1790335313-commercial-workspace` · live dev stack
(Vite :5173 / Django :8000 / Supabase :25321), fixture org. Roles: OWNER (aal2) for
emit/link ops; customer portal is unauthenticated.

> **Setup:** Django was serving pre-`e82e17e` code (started 12:45, commit landed 13:36) —
> restarted `--noreload` so the backend matches HEAD. Owner session re-minted (aal2 via TOTP).

## Captures (`docs/redesign/captures/phase07/live/`)
| File | What |
|---|---|
| `01-emitted-panel.png` / `_setup-emitted-revb.png` | Quotation panel — REV-B emitted in history |
| `02-pdf-compact-dochead.png` | **DOC-01 REV-B page 1 — compact dochead** |
| `03-portal-desktop-top.png` / `03b-…-decision.png` | Portal desktop 1440 — proposal + decision form |
| `04-portal-mobile-top.png` / `04b-…-cta.png` | Portal mobile 390 — single column, CTA reachable |
| `05-portal-decision-form.png` | Decision form filled (nombre + RUT) |
| `06-portal-approved.png` / `06b-…-state.png` | **APPROVED** state — no active buttons |
| `07-parity-quotepanel.png` | Project panel total $423.515 |
| `08-portal-superseded.png` | **Superseded banner** (REV-A link) |
| `09-portal-revoked.png` | **Revoked** banner |
| `10-portal-expired.png` | **Expired** banner |
| `11-portal-declined.png` | **DECLINED** state (request-changes) |
| `12-payment-return.png` | `/pago/retorno` → "Pago recibido" |
| `13-panel-links.png` | Internal link list — all statuses |
| `14-parity-trio.png` | Panel / PDF / portal totals side-by-side |

## Results

### 1. EMIT fresh DOC-01 ✅
- `Crear nueva revisión` → `start_successor` → project DRAFT → REV-B; new calc →
  `Aprobar y aplicar precios` → APPLIED op; `Preparar emisión` → emit form (locations +
  policies + terms **prefilled** from REV-A inputs) → `Emitir cotización` → **REV-B sealed**
  (`project_versions` REV-B, project QUOTED, gross **$423.515**).
- `Abrir cotización emitida` lazily generates + downloads `COT-P-000001-REV-B.pdf` (DOC-01, 4 pg).
- **Compact dochead confirmed** — page 1 is a dense commercial header (doc meta box, prepared-for,
  hero line, TOTAL $423.515, pago/válida), **not** a standalone cover. Project has **4 distinct
  configurations ≤ 8** → compact layout. Pages: resumen → per-position cards → Inversión →
  Condiciones + Aceptación (the e82e17e unified closing band).

### 2. Portal ✅
- **Desktop 1440** single column, positions + totals + decision form render.
- **Mobile 390** `scrollWidth=390` (no h-overflow), CTA visible/reachable.
- **Approve** → `Aprobar propuesta` → `DECLINED`→**APPROVED**; no active buttons remain;
  `decided_by="Vivienda Particular SpA · 77.123.456-7"` recorded; project → APPROVED.
- **Idempotency** ✅ — re-POST decide (DECLINED then APPROVED) on the decided token returns
  `HTTP 200` replaying the sealed state; `decided_at`/`decided_by` unchanged; still **1** decided
  row. (By design: the write is `UPDATE … WHERE status='PENDING'` — atomic, so replays/de-dupes
  return the sealed state. `quote_already_decided`→409 only when still PENDING but project moved.)
- **Real decline** — fresh REV-C link → `Solicitar cambios` (nombre + motivo) → **DECLINED**,
  note recorded ("…cambiar el vidrio del living…"), buttons gone.
- **Superseded** — REV-A link → banner "Esta cotización fue reemplazada por una revisión nueva." ✅
  *(note: it only informs — no link/CTA to the current revision; a stale token can't mint it,
  and no issuer-contact is shown on the superseded page. Mild UX gap — see below.)*
- **Revoked** — revoked link → "Este enlace fue revocado; solicita uno nuevo." ✅
- **Expired** — link with `expires_at` in the past → "Esta cotización ya no está vigente;
  solicita un enlace nuevo." ✅ *(fixture-set via DB `expires_at` — none pre-seeded.)*

### 3. Payment ⚠ BLOCKED — defect found
- `/pago/retorno` renders "Pago recibido" (static ack; Flow confirm settles async). ✅ captured.
- **The "Pagar ahora" CTA is unreachable.** `portal.service.portal_quote` sets `payment_url`
  from `project_payment_links` (PENDING + url + CLP), but that query runs under
  `SET LOCAL ROLE portal_backend`. The table's RLS policy `project_payment_links_isolation`
  requires `org_id IN current_user_org_ids()`, and `current_user_org_ids()` resolves via
  `auth.uid()` — **null for the unauthenticated portal role**. `_scope_org` sets
  `app.portal_org_id`, which `current_user_org_ids()` does not read.
  **Result:** `portal_backend` sees `0` payment links (verified) → `payment_url` always `null`
  → the CTA can never render, even with a minted Flow link. No Flow integration is configured
  in the fixture either (`org_payment_integrations` empty), so this also can't be demoed live.
  *Evidence:* inserted a real PENDING link row (`023f67a0`, url set) → portal still shows no CTA;
  `SELECT … AS portal_backend` → `visible_links = 0`. The row is left in place as repro.
  *(Also worth noting: if it were visible, the CTA would render on a DECLINED quote — the
  `payment_url` gate checks superseded/expired but not the decision state.)*

### 4. Parity ✅
Same revision **REV-B**: quote panel **$423.515** = DOC-01 PDF **$423.515** = portal **$423.515**
(neto $355.895 / impuesto $67.620). See `14-parity-trio.png`.

## Defects found
1. **🔴 Portal payment CTA is structurally unreachable** — `project_payment_links` is invisible
   to the `portal_backend` role under RLS (`current_user_org_ids()` uses `auth.uid()`, null for
   token-only portal; `app.portal_org_id` isn't consulted). `payment_url` can never populate →
   "Pagar ahora" never shows on the customer portal. Fix: scope the payment-link read by
   `app.portal_org_id` (or give the portal path a non-RLS read on the minted-link projection).
2. **🟡 Superseded link gives no route to the current revision** — banner says "reemplazada por
   una revisión nueva" but offers no link/issuer-contact to reach the live revision. Architecturally
   the stale token can't mint the new link, so at minimum an issuer-contact affordance would help.
3. **🟡 (edge)** If a payment link WERE reachable, the CTA would render even on a DECLINED
   proposal — `payment_url` doesn't gate on decision state.

## Honest notes
- Flow integration not configured in the fixture (`org_payment_integrations` empty) — no real
  charge possible; the `/pago/retorno` page was captured standalone.
- "Expired" link produced by a DB `expires_at` update (no expired fixture pre-seeded).
- Emit form on REV-B/REV-C prefilled location/policies/terms from REV-A inputs — only
  `valid_until` + confirm needed. Handle-height "Usar sugeridas" was already confirmed.
- I created extra link rows on vivienda (PENDING/REVOKED/expired/DECLINED) and a synthetic
  PENDING `project_payment_links` row (`023f67a0`) as defect repro — flag before any reseed.
