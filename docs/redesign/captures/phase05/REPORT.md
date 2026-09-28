# Phase-05 — Commercial unification acceptance captures

HEAD `da45d88` · branch `devin/1790335313-commercial-workspace` · recorded live on the local
dev stack (Vite :5173 / Django :8000 / Supabase :25321), fixture org.

Journey exercised on camera: create client → create project → add 3 positions → duplicate →
change quantity → open in Studio → return → review price → consult revision. Then re-ran key
views as WORKSHOP_MANAGER (read-only) and OPERATOR (excluded), and on the 100-position obra.

## Captures (desktop 1440×900)
- `00-dashboard.png` — Panel with the new projects entry points
- `01-projects-list-filtered.png` — list with `?q=fase&status=DRAFT&sort=name` active
  (search + status filter + sort reflected in controls, single matching row)
- `02-project-detail.png` — project header + positions + facts rail
- `02-project-detail-activity.png` — Actividad `<details>` open, real events only
- `03-copy-banner.png` — `/positions/new?copy=` "Copia de P1…" banner
- `04-studio-editor.png` / `04-studio-return.png` — Studio editor / detail after back-nav
- `05-revision-compare.png` — "Comparar revisiones" honest empty state
- `06-manager-readonly.png` — WORKSHOP_MANAGER read-only project detail
- `06-operator-noacceso.png` — OPERATOR "Sin acceso" wall (by design)
- `07-obra-100pos-top.png` — 100-position obra list, dense uniform rows
- `edge-clients-1440.png` — no-email client + long-named client in the list

## Captures (mobile 390×844)
- `m-dashboard.png` — fits (scrollWidth 390)
- `m-project-detail.png` — **overflows (scrollWidth 521)** ⚠ defect
- `m-positions-list.png` — **overflows (scrollWidth 521)** ⚠ defect

## Result summary

| Check | Result |
|---|---|
| Client without email | ✅ saved + listed |
| Long-named client | ✅ renders, no layout break |
| Project create | ✅ "Fase5 Capturas" (P-000004), status DRAFT |
| 3 positions + spec line | ✅ "typology · finish" on every row |
| Duplicate → copy banner | ✅ "Copia de P1…" + new position, original untouched |
| Inline qty recalc | ✅ commits on blur, qty persisted via API |
| Studio edit → back | ✅ returns to detail, 4 positions intact |
| `?q/?status/?sort` URL persistence on back-nav | ✅ params + controls + filter all retained |
| Actividad = evidence-only | ✅ only real "Posición modificada" events + dates |
| Price / revision consult | ✅ Revisión A + honest "needs 2 revisions" empty state |
| WORKSHOP_MANAGER read-only | ✅ views list+detail, 0 edit controls, no qty inputs |
| OPERATOR | ✅ fully "Sin acceso" (list + detail + editor) — by design |
| 100-position list | ✅ uniform 40.9px rows, all spec lines, no h-overflow @1440 |
| **Mobile 390 project detail/positions** | ❌ scrollWidth 521 (>390) — `.position-row` min-content ~513 doesn't reflow |

## Defects found
1. **Mobile overflow on project detail + positions list** — `.position-row` (index + ubicación +
   dims + `.position-row__spec` + `.position-row__qty-input` + status) has ~513px min-content and
   doesn't reflow at 390px → page h-scrolls ~131px. Dashboard and projects list fit fine.
2. **Guardar silently no-ops when glass unassigned** — on `/positions/new`, clicking Guardar with
   an unselected glass does nothing (no error shown, no save). Selecting espesor+vidrio unblocks it.
   Users get no feedback about what's missing.
3. **"Importar documento" stays enabled for WORKSHOP_MANAGER** — a mutating affordance remains
   enabled on a read-only role (click opens no visible dialog; either a no-op or would 403 on
   submit). The other edit controls are correctly hidden.

## Notes
- The projects list URL params apply on load AND persist through back-nav — verified both directions.
- Duplicate creates a genuinely new position (own `id`/`position_index`, copied location/design);
  the source row is unchanged.
- First `npm run dev` ran from a stale checkout earlier this session; all evidence above is from
  `/home/ubuntu/wt-commercial` at `da45d88`.
