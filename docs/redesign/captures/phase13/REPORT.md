# Phase-13 — First impression + first project — acceptance report

Stack: worktree `wt-commercial` @ `875655d`. Vite `localhost:5173` + `127.0.0.1:5173`, Django :8000, Supabase :25321/:25322, Mailpit :25324, Chrome CDP. All flows run live in the browser; the magic-link round trip used real Mailpit mail + the gotrue verify URL (never pre-fetched).

## Mandate checklist

| Item | Result | Evidence |
|---|---|---|
| Anonymous `/` → public landing (hero, real product webp, Bot secondary, Entrar→/login) | ✅ PASS | `01/01b/01c` 1440, `02/02b` 1280, `03/03b` ~390(iw=500 floor). scrollW 1425/1265/500 = no scroll-x; `background-image: none` (no generic gradients); 6 real webp shots load (`studio/cotizacion/plan-corte/produccion/asistente.webp`, naturalWidth>0). "Ver el producto" scrolls (y=767), "Entrar" → /login. |
| Authenticated `/` → /dashboard (commercial) or /production (floor) | ✅ PASS | estimator → `/dashboard`; OPERATOR + INSTALLER → `/production` (`21`,`22`). |
| Return-to-destination | ✅ PASS | Anonymous → `/projects/…/positions/…/edit` → `/login` stashes `dk:returnTo` (pathname+search) → real magic link → gotrue → `/auth/callback` → **lands on the position editor**, stash consumed. `05`,`06`,`08`. |
| Malicious `from` | ✅ PASS | `//evil.com`, `https://evil.com/x`, `\\evil`, `/auth/callback`, `/login` all → `/dashboard` fallback (validation in `returnTo.ts`). |
| Expired link | ✅ PASS | `/auth/callback#error=access_denied&error_code=otp_expired` → "El enlace venció. Solicita uno nuevo para entrar." + Volver al acceso. `04`. |
| Existing user → no forced onboarding | ✅ PASS | Estimator dashboard shows attention queue + resume rows; onboarding only linked when a project list is empty. `09`. |
| Onboarding finish → `/projects/<id>` | ✅ PASS | Full wizard run live: identidad → sistema (DEMO_60) → datos (demo) → cliente "Constructora Fase13 Demo SpA" → proyecto "Edificio Fase13 Piloto" (P-000009) → "Abrir editor de vanos" → position editor `/positions/new` → glass+location → Guardar (position `ca8b29b9`, "Guardado") → "Abrir cotización" → `/pricing` → finish → `/projects/f5243b02`. Second full run on video created "Cliente Video F13"/"Proyecto Video F13" (`ad73d43e`) — finish → `/projects/ad73d43e`. `10`–`20`, journey.mp4. |
| index.html title + description | ✅ PASS | `DEKOPEN — De la ventana que diseñas al trabajo que entregas` + meta description present. |

## Public claims ↔ real features (each touched live)

1. **"Studio — editor paramétrico con cotas en vivo"** — position editor reached from onboarding; live cotas (svg dims), split controls, glass assignment gate ("Falta asignar vidrio…" cleared on assignment) → Guardar persisted. ✅
2. **"Cotización nace del modelo"** — `/projects/<id>/pricing` renders margin modes, currency/FX context, position list; estimators correctly read-gated ("Sin acceso… modificar precios" — owner used). `23`. ✅
3. **"Plan de corte con identidad física por pieza"** — piece search `P03-U01-M06` → trace rows show order + `Barra 3` + piece set `(mec.)` machining flag + SASH/1302mm/9-9 steps. `25`. ✅
4. **"Trazabilidad de la pieza a la entrega"** — trace shows piece→order→station chain incl. remake order `-RM-01`; delivery/POD chain verified live in phase-10 on this stack. ✅
5. **"Asistente con evidencia real"** — phase-12 verified this stack: ops card → explicit Aplicar + server outcome; claims render `· evidencia:` labels. ✅

## Findings

- **F13-1 🟡 env/config caveat (not app code):** gotrue `SITE_URL=http://127.0.0.1:5173` and `GOTRUE_URI_ALLOW_LIST` only allows `127.0.0.1:5173/auth/callback`. Browsing `localhost:5173` makes `emailRedirectTo` fail validation → magic links fall back to site root `/`, which (a) lands on a **different origin** so `sessionStorage dk:returnTo` is unreadable, and (b) even same-origin, `HomeRedirect` on `/` never calls `consumeReturnTo` — destination silently lost. Verified: on `127.0.0.1` origin the full returnTo round-trip works. Suggest `HomeRedirect` consume `dk:returnTo` as a defense-in-depth for any path where the callback is bypassed.
- **F13-2 🟢 note:** module dimension inputs in the position editor don't commit on `input`+`blur` events (same as phase-12 observation) — a position saved at 1000×1000 default works fine; manual entry needs the proper gesture (this is a test-driver limitation note, dimensions edited via other controls commit fine).
- **F13-3 🟢 note:** the two video-run artifacts left fixture rows: client "Cliente Video F13", project "Proyecto Video F13" (P-…, draft) + "Constructora Fase13 Demo SpA"/"Edificio Fase13 Piloto" (P-000009). Harmless demo data; clean up if fixture purity matters.

## Assets
`journey.mp4` (217s CDP screencast: landing scroll → expired link → deep-link→login→magic-link→lands-on-editor → dashboard → full onboarding wizard → editor → pricing → finish → project → operator/installer → /production), PNGs `01`–`25` incl. all viewport landing shots.
