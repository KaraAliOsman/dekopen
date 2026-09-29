# Phase-10 — Full 4-role workshop journey (acceptance run)

HEAD `f1bfc95`→`d410de0`→`b4a59a3` (fixes landed mid-run; Django restarted on backend commits, Vite HMR for frontend). Stack: Vite :5173, Django :8000 (`--noreload`), Supabase :25321/DB :25322, Mailpit :25324. Roles exercised live: OWNER (aal2), WORKSHOP_MANAGER, OPERATOR, INSTALLER, ESTIMATOR via magic-link sessions.

No video possible this session (dead X display) — evidence is CDP `Page.captureScreenshot` PNGs + real generated PDFs + DB/API responses. Mobile measured at iw=500 (Xvfb window floor; `Emulation.setDeviceMetricsOverride` inert on this Chrome build) — overflow metrics are exact.

## Journey executed (verbatim mandate)

`recibir orden → material → corte → mecanizado/herraje → ensamblaje → vidrio → QC → rechazo y remake → embalaje → despacho parcial → entrega final`

- **OT-P-000008-REV-A-03** (tilt-turn, 9 steps) — OPERATOR drove CUT→MACHINING (ops checkbox declared, HANDLE_PREP on P03-U01-M06) →WELD→CLEAN→SASH_ASSEMBLE→HARDWARE→GLAZE via the sticky action bar in the operator card; OPERATOR logged QC evidence (FAIL: "Escuadra del marco 92°" on P03-U01-M06·R); WM signed qc_result=FAIL → step BLOCKED, order→HOLD, QC_FAILED event. WM created remake → **OT-…-03-RM-01** (payload.remake_of=original, remake_reason={qc_item,note}, banner "Reposición de: P03-U01-M06·R"). RM-01 re-optimized (packing/plan dropped by design) → full route → QC PASS evidence + WM sign → PACK → COMPLETED. Then rework path also verified: UNBLOCK original → re-QC pass → COMPLETED. Progress never read 100% while the reject was open (7/9 pasos shown, station board "1 bloqueadas").
- **OT-P-000008-REV-A-01** (×2 units, 6 steps) — COMPLETED → schedule delivery (whole saldo) → **dispatch sealed GD-0001 {1,2}** → ON_ROUTE → **FAILED** (units freed: pending=[1,2]) → trip 2 scheduled `unit_indexes=[1]` → **GD-0002 {1}** → ON_ROUTE → POD **CE-0001** (WM) → trip 3 `[2]` → **GD-0003 {2}** → ON_ROUTE → POD **CE-0002** (INSTALLER, after fix) → all delivered → **install → INSTALLED** (installer, idempotent replay verified). UI trips list shows all three trips with own guía+comprobante links; "Saldo pendiente de despacho" line + "Programar siguiente viaje" verified on RM-01 after FAILED.
- **OT-P-000008-REV-A-02** — concurrency probe: two simultaneous dispatches → ONE guía (GD-0004); ON_ROUTE → two concurrent POD confirms → ONE CE-0003 (UNIQUE(delivery_id) + advisory lock; both callers got the same code).
- **RM-01 install journey via installer UI**: En ruta → Confirmar entrega (typed signature) → Emitir comprobante → CE-0004 → Confirmar instalación → INSTALLED.

## Defects found → fixed by lead mid-run (all re-verified PASS)

| # | Defect | Fix | Re-verify |
|---|--------|-----|-----------|
| 1 | floor roles (OPERATOR/INSTALLER) got 422 on `/trace/` — `projects` read under `authenticated` denied by `project_manual_read` | `0296d19` reads under `documentary_backend` | 200 for opr/ins/mgr; whitelisted projection (project code/name only) |
| 2 | dispatch 409 `documentary_transaction_rejected` — `issue_dispatch_note` reads `public.clients` under `documentary_backend` with no grant | `b7254ed` grant SELECT + org-scoped policy | dispatch → 200, GD-0001 sealed w/ client RUT fallback |
| 3 | INSTALLER POD confirm → 404 — `project_documentary_backend_read` excludes INSTALLER; `project_row(FOR UPDATE)` | `f1bfc95` signature-only POD skips project lock | ins confirm → **CE-0002** sealed |
| 4 | second-trip confirm → 422 `ambiguous_authority` — open-trip `one()` matched DELIVERED sibling + ON_ROUTE | `f1bfc95` LIMIT 1 after ON_ROUTE-first | CE-0002 on trip 3 while trip 2 DELIVERED |
| 5 | INSTALLER saw zero delivery/install buttons — `canStep` excluded them though backend `_STEP_ACTORS`/confirm allow INS | `d410de0` `canField` gate | UI journey: En ruta → CE-0004 → Confirmar instalación → INSTALLED |
| 6 | `?piece=` deep link self-wiped — detail-load effect cleared pieceReport/pieceQuery before matches rendered | `b4a59a3` skip clears while `?piece=` live + single-order auto-nav | multi-order scan keeps matches panel; single-order lands on order |

## Open findings (not fixed this run)

- 🔴 **Mobile overflow on production floor** — at iw=500 the `.production-orders` sidebar stays ~857px → page `scrollWidth=867`. Same fix class as phase-06 wrap (media-query stack or internal scroll). Floor/mobile mandate unmet. `24-mobile-500-operator.png`, `25-mobile-500-orderdetail.png`, `34*`.
- 🟡 **QC reject by OPERATOR is silent in UI** — Rechazar/Completar on QC → 422 `qc_requires_supervisor` (correct, API-verified) but no toast/banner tells the operator why. `12*`.
- 🟡 **Piece-match → station preselection unverifiable on closed orders** — match click navigates to order but operator card shows last station (all steps DONE). Live-order landing untested (no open order left post-journey).
- 🟡 No explicit "tiene refabricación →RM-01" banner on the ORIGINAL order (only station-board buttons + event log link the two; the remake side shows "Reposición de" correctly).
- ℹ️ Dispatch subset picker (unit chips when pendingUnits>1) — API subsets verified (GD-0002{1}/GD-0003{2}); the chip picker UI not captured (needs pending>1 on a dispatchable order — transient state missed; code path inspected at ProductionPage.tsx:2723).

## Re-verified gates (2505edf regression)

- OPERATOR: schedule/dispatch/optimize → 403 `documentary_permission_denied`; step transitions allowed (all workshop steps recorded `demo-operator`); QC COMPLETE → 422 supervisor-required; QC_CHECK evidence logging allowed.
- INSTALLER: step transition → 403; delivery transitions/install/POD allowed (UI now matches post-d410de0).
- ESTIMATOR: all mutations → 403; UI renders zero mutating controls (doc links only).
- **Multi-org isolation**: synthetic WORKSHOP_OT in foreign org → absent from list, direct GET → `work_order_not_found`, trace → same; `X-Organization-ID` switch to foreign org → 403 `organization_access_denied`. Row cleaned up.
- Install gating: undelivered order → 422 `installation_requires_dispatched`; partial manifest → `installation_requires_delivered` (verified via code path + state machine).
- Idempotency: install replay → same state; dispatch retry → single guía; concurrent POD confirm → single CE; double step transitions on completed order → 422 `work_order_completed`.

## Piece-data linkage (Pxx-Uxx-Mxx through dispatch) — verified

- `cut-pack-ot03.pdf` (4pp): all P03-U01-M01…M12 (+·R) codes on bars w/ angles.
- `production-pack-ot03.pdf` (13pp): same codes incl. `P03-U01-I01` glass.
- `labels-rm01.json`: `label_code` `OT-…-RM-01-U01`, `qr_payload` `DEKOPEN|OT-P-000008-REV-A-03-RM-01|…-U01|22`, real `qr_svg`.
- `gd-0001/2/3.pdf`: per-trip guías listing exactly the units dispatched (U01+U02 / U01 / U02).
- `ce-0001/2.pdf`: per-trip PODs with signature block "Recibido conforme".
- Piece trace: `P03-U01-M06` resolves to bar 3, SASH, seq #1–4 across OT-03 + RM-01 — cut plan → QC item → remake → labels all name the same codes.

## Captures

`docs/redesign/captures/phase10/` — PNGs 01–37 + PDFs (gd-0001..3, ce-0001..2, cut-pack-ot03, production-pack-ot03) + labels-rm01.json.
