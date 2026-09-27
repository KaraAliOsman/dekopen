---
name: testing-framedex
description: Local dev-stack recipe for DEKOPEN E2E testing — Supabase CLI stack, Django/Vite env vars, ESTIMATOR fixture creation, magic-link login via Mailpit, catalog seeding for bow/assembly features.
---

# DEKOPEN local E2E stack

## Start services

1. Supabase local stack: `cd <repo> && /home/ubuntu/.local/bin/supabase start` (CLI 2.116.x in ~/.local/bin; if missing, download the linux-amd64 tarball from supabase/cli releases). Ports: API `:25321`, Postgres `:25322`, Mailpit UI `:25324`. `supabase status -o env` prints `ANON_KEY`/`SERVICE_ROLE_KEY`/`API_URL`.
2. Django: `cd backend && DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:25322/postgres SUPABASE_URL=http://127.0.0.1:25321 SUPABASE_ANON_KEY=<anon> SUPABASE_SERVICE_ROLE_KEY=<svc> SUPABASE_JWT_VERIFY_MODE=auth_server CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173 ../.venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload`. Venv at repo root (`uv venv .venv && uv pip install --python .venv`); `--noreload` means restart after every backend commit.
3. Vite: `export PATH="/home/ubuntu/node22/bin:$PATH"; cd frontend && VITE_SUPABASE_URL=http://127.0.0.1:25321 VITE_SUPABASE_ANON_KEY=<anon> npm run dev` → `http://127.0.0.1:5173` (Node 22 at ~/node22, `npm ci` first if needed).

## Fixture (user + org)

- Create user via `${SUPA}/auth/v1/admin/users` POST `{email, password, email_confirm:true}` with `apikey`+`Authorization: Bearer <service_role>` headers.
- Org: POST `${SUPA}/rest/v1/tenancy_organizations {id, name}` (service key), membership: POST `tenancy_memberships {user_id, org_id, role}` — use **ESTIMATOR** (OWNER triggers aal2/MFA).
- Backend API calls need `Authorization: Bearer <supabase access_token>` + `X-Organization-ID: <org_id>` headers.

## Login (magic-link only — no password form in UI)

1. UI: `/login` → type email → "Enviar Magic Link".
2. Fetch the link from Mailpit: `GET http://127.0.0.1:25324/api/v1/messages` → `GET /api/v1/message/{id}` → regex the `/verify?token=...&type=signup|magiclink` URL → open it in the browser (redirect URL must be allowed or use `token_hash` form).

## Catalog seeding for bow/assembly testing

- Couplers: `profile_articles` rows `role='COUPLER'`, `org_id NULL` — e.g. COPLE-60/COPLE-90 (needs migration 20260922150000 applied or singleton-role CHECK fails; apply via `docker exec -i supabase_db_dekopen psql -U postgres -d postgres -f <file>`; avoid `supabase db reset`, it wipes the fixture org).
- Glass SKUs come from `glass_purchase_mappings.technical_sku` (DEMO_60 has GLASS-BASE). Panel SKUs from `infill_articles` (DEMO_60 has PANEL-SANDWICH-DEMO-24).
- DEMO_60 system_id: `3067da09-3119-5ad0-a1d5-498cd2dfd753` (global demo, quote_ready).
- psql isn't installed on the host — use `docker exec supabase_db_dekopen psql -U postgres -d postgres`.

## Gotchas

- Bow editor: DOOR_ENTRY modules fail evaluation below the door kit's min leaf width (~<700mm) with a generic "no pudo evaluarse" issue; they also need a panel to reach VALID.
- Selecting a profile system in "Vano único" mode then switching to bow locks the editor (pending flag cleared only by classic validation) — switch to bow FIRST, then pick the series.
- UnsavedChangesGuard intercepts Vite hot-reloads mid-edit → "Reload site?" dialogs when files change under you.

## Quotation/documentary flow (emission → artifacts)

- Freeze needs pricing first: "Calcular precio" → "Preparar emisión" → per-position Ubicación + 3 policy selects (fabricación/manillas/refuerzos) → confirm → "Emitir cotización". Requires cost_list_items for EVERY priced SKU incl. kits (KIT-TURN, KIT-DOOR-MULTIPOINT, DEMO-LOCK-MULTIPOINT role=KIT) else 422 cost_list_not_found; cost/pricing tables only RLS-read under pricing_backend role — direct psql INSERT fine.
- Handle intents: `handle_requirement_policies` may require PRIMARY per operable leaf; the prep UI renders per-leaf height + vertical-reference inputs from `handle_requirements` (per policy option, namespaced bay ids like "m2|m2"). Intents can also be PUT directly via `/api/v1/documentary/inputs`.
- Inspector R02: leaf h/w ratio must be in [0.4,2.5] — FAIL blocks freeze regardless of allow_incomplete (only RED/MISSING_INPUT are tolerable, and views.py hardcodes allow_incomplete_workshop=True).
- Inputs seal once a version exists (sealed_documentary_inputs_immutable); version rows can't be DELETE'd without `SET session_replication_role=replica`.
- DOC-03 needs OWNER/WORKSHOP_MANAGER — create a second fixture user (admin API + tenancy_memberships role WORKSHOP_MANAGER; is_active default true). Quote-only versions reject DOC-03 with 422 production_document_blocked.
- Artifact access: POST `/api/v1/documents/artifacts/` {document_type, format, project_version_id} → GET `artifacts/<id>/access/` → signed_url. Supabase returns signedURL relative to `/storage/v1` — that prefix is resolved server-side; if an emitted-artifact link 404s check which revision is running (pre-#43 builds dropped it).
- No poppler/gs on box — open generated PDFs in Chrome via file:// for visual check.

## Merged stack (89d22e0+) extras

- **Job worker required**: artifact generation (DOC-01/03) is now async via the `jobs` queue — the UI polls `/api/v1/jobs/{id}/` forever unless a worker runs: `python backend/manage.py runjobs --poll 1.5` (same env as runserver). No worker = "Generando cotización…" spinner forever.
- **Async artifact open = popup-blocked**: the emitted-doc button calls `window.open` after the job poll, outside the user gesture → Chrome blocks it (watch omnibox popup icon; click the blocked URL). Not a signed-url bug — URL works when opened manually.
- **Fresh-DB column grants**: `authenticated` has column-level (not table-level) SELECT on `projects`/`project_positions`. New columns added without grants → `GET /projects` 409 `pricing_transaction_rejected` (SQLSTATE 42501). Check `information_schema.column_privileges` and GRANT the missing columns (`pricing_reset_at`, `client_id`, `client_*` were missing in a from-scratch migrate).
- **Fixture API shapes**: POST `/projects/`; POST `/projects/{id}/positions/` `{location_tag,quantity,design:{system_id,nominal_width_mm,nominal_height_mm,color,parametric_tree}}`; POST `/pricing/preview/` `{project_id,pricing_mode:COST_PLUS_MARGIN,context_code:DEFAULT,currency:CLP,effective_date,discount_pct,target_margin,segment:RETAIL,confirmed,reason}` then POST `/pricing/operations/{op}/apply/` `{reason,confirmed:true}`; GET/PUT `/documents/projects/{id}/inputs/`; POST `/documents/projects/{id}/freeze/` `{pricing_operation_id,confirmed:true}`; POST `/production/versions/{vid}/release/` (OWNER/WM only); POST `/production/orders/{oid}/optimize/` `{color}` (required!).
- **Org needs `pricing_rules` row** (`INSERT INTO public.pricing_rules(org_id,pricing_mode,default_margin_pct,tax_rate_pct,waste_factor_pct,labor_rate_per_m2,installation_rate_per_m2)`) else preview 422s `pricing_rules_not_found`.
- **Cost lookup mixes SKUs**: pricing calls `cost()` on purchasing SKU for profiles/steel (DEMO-BAR-*, DEMO-STEEL-BAR-*), but TECHNICAL sku for glass (GLASS-BASE @ M2) and kits (KIT-TURN @ KIT) — seed both forms.
- **workshop_annotations**: ONE record per (bay_id, leaf_id) target — when prep echoes `leaf_id: null`, merge drains+closing+tramo+finish+coupler into the single bay annotation; a second record with the same (bay,null) pair → freeze `Duplicate annotation target` → 422 documentary_authority_required.
- **Priced projects lock positions** — "Duplicar proyecto" needed to edit; demo canvas edits on an unpriced project instead.
- Production optimize UI requires typing a color (placeholder "BLANCO" is not a value) before the button enables.

## Contour slices (Phase-2) — trapezoid/arch specifics

- Trapecio/Arco starters live at the FAR RIGHT of the horizontally-scrolling design-library
  gallery on /positions/new. FORMA section appears on contour modules: "Desvío sup. izq./der."
  (trapezoid top-corner offsets) or "Flecha del arco" (arch rise). Width/height edits rescale
  the contour proportionally (offsets and rise auto-scale).
- KNOWN DEFECT signature: POST /engine/assembly/calculate → 400 for any contour whose cut
  angles aren't exact 0.1° multiples (trapezoid 2400×1400 @200mm offsets → miters 40.93°/49.07°).
  Root cause: engine/src/dekopen_engine/snapshot.py::_json_value enforces Decimal("0.1")
  quantum on fields literally named angle_left/angle_right → "Canonical output would lose
  precision: angle_left" → swallowed as generic validation_error. The SAME crash 500s
  save_position via calculation_response — contour positions are unsaveable through every path.
- Guardar button is gated on assemblyEval.status === "VALID" (ProjectPositionEditor.tsx) —
  MANUFACTURING_INCOMPLETE (arch) and eval-failure (trapezoid) both keep it disabled.
- Arch at spec values DOES evaluate: 1800×1600 rise 300 → "Geometría válida — fabricación
  incompleta" + issues "El miembro N de el módulo 1 necesita curvado (flecha X mm) — sin regla
  de curvado declarada". Its cut angles happen to be 0.1-multiples so it dodges the bug.
- To reproduce the exact engine error in-shell: authenticated_rls_context(claims) +
  SystemParamsRepository().load_visible + parse_product_model + evaluate_assembly_from_api +
  evaluation_response — mint a real token via Mailpit OTP link's verify?token= redirect
  Location header (access_token in the fragment), password grants don't exist for OTP users.
- Contour positions persist as product-v2 in project_positions.parametric_tree (isSingleUnit
  excludes contour modules). To insert one for testing: copy a valid bom_snapshot from an
  existing row and STRIP its "calculation_hash" key — position_public() revalidates stored
  hash vs design and 409s stored_calculation_invalid on mismatch; no-hash BOMs skip the check.
- Recurring flake: the whole in-memory design silently RESETS to a 1000×1000 default rect
  mid-edit (~3× observed). No console/error — just re-apply the starter. Also: wheel-scroll
  over the canvas PANS the SVG viewport (shape doesn't vanish, it pans away — scroll back).

## Gauntlet R2 (447efb9+) — emit/finance specifics

- **DB resets between sessions** — the shared supabase_db_dekopen container loses fixture
  orgs/users overnight. Rebuild recipe: `auth.admin/users` POST → `tenancy_organizations`
  (cols: name,tax_id,country,currency,subscription_active,credits_balance INT) →
  `tenancy_memberships` (cols: org_id,user_id,role,is_active) → `pricing_rules`
  (fractions 0–1, waste_factor_pct must equal exactly 0.08) → `cost_lists` +
  `cost_list_items` → `pricing_configurations` (has rate_per_m2/base_glass_sku/catalog_price
  /is_active/revision) → `clients` (cols: name,rut,email,phone,address,giro,comuna,
  is_active,created_by NOT NULL).
- **Emit gotea real seeds now**: GET inputs returns prefilled workshop_annotations
  (drains spaced to width, closing_points at R08 spacing, tramo=width, WHITE finish),
  glass_polishing all-false edges, accessory_schedule NONE_REQUIRED — but leaf-targeted
  rows still land with `leaf_id: null` on single-module positions → merge into the bay row
  before PUT or freeze 422s "Duplicate annotation target".
- **Freeze needs a real handle intent** per operable leaf (PRIMARY slot): PUT
  `handle_intents:[{schema_version:1,bay_id,leaf_id:null,handle_domain_slot:"PRIMARY",
  requested_height_mm,vertical_reference:"OUTER_BOTTOM"}]` — else 422 with the specific
  `ManufacturingAuthorityError` only visible in the Django log (API detail is generic).
- **Emission date input is automation-flaky**: `<input type=date required>` cleared on
  submit repeatedly; the native picker via Enter-on-focus also failed under tooling.
  Bypass via PUT inputs + POST freeze when only the submit needs proving.
- **Finance chain**: POST `projects/{id}/invoices/` → 201 FAC-XXXX; POST `invoices/{iid}/dte/`
  → 409 `sii_caf_exhausted` without a CAF (no UI surface for CAF/cert upload — API-only
  `siiCafRegister`/`siiCertificateUpload`). payment-links GET is now skipped (not 403) for
  non-write roles; `projects/payment-integration/` returns `{configured:false}`.
- **Optimize color now seeds** from sealed position finish (WHITE) — the R1
  placeholder-trap is fixed; step buttons survive optimize (busy reset in finally).
- **PDF rasterize**: no poppler — `uv pip install --python .venv/bin/python pymupdf` then
  `fitz.open(pdf)` → `page.get_pixmap(dpi=95)`. Signed storage URLs break in Chrome's
  URL bar (JWT chars mangled) — curl them instead.

## Worktree testing (e.g. /home/ubuntu/wt-main)

- A worktree shares the repo's venv — run backend as `<repo>/.venv/bin/python` with `PYTHONPATH=<worktree>/engine/src` and `cd <worktree>/backend`; runjobs worker needs the same env (`manage.py runjobs` alongside runserver or artifact jobs never complete).
- Frontend worktree: symlink `node_modules` from the main checkout (`ln -s <repo>/frontend/node_modules`) — package.json deltas are additive there.

## Routing / member ops facts (verified §29/§30)

- Member machining ops exist ONLY where sealed authority exists: `END_MACHINING` on mullions when `profile_systems.end_milling_overlap_mm > 0`, `HANDLE_PREP` on handle policies. A fixed-window order's MACHINING step legitimately shows an empty ops table.
- To see END_MACHINING live, seed a `SPLIT_V` position whose mullion SKU belongs to the system (ALU_65 → POSTE-A-V) — `mullion_profile_sku` must match a system article or the splitter resolves nothing.
- Step ladders follow `profile_systems.material`: PVC → CUT→(MACHINING if end_milling>0)→WELD→CLEAN→SASH_ASSEMBLE?→HARDWARE?→GLAZE?→QC→PACK; ALU → CUT→MACHINING→CRIMP→… . SASH_ASSEMBLE needs a SASH-role cut; HARDWARE needs fittings/hardware_items.
- The operator card trace refetches after mutating actions; still F5 before judging staleness.

## Emit → DOC-01 in the UI (walkthrough learnings)

- `/tmp/supa.env` regenerated via `supabase status --output json` exports `SERVICE_KEY` — Django needs `SUPABASE_SERVICE_ROLE_KEY` (same JWT). If missing: freeze jobs → `document_storage_not_configured`. Also `SUPABASE_URL`/`SUPABASE_ANON_KEY` must be exported (supa.env names them API_URL/ANON_KEY).
- Emit form per-leaf handle intents now SEED at load (and on placement/handle-policy change) with the displayed midpoint + first permitted reference — emitting untouched works; only requirements with unresolvable bounds keep the "pendiente" chip. Ubicación, date and condiciones are all required for emit. Committed intents display raw decimals (`1561.0000`) vs clean seeded values (`1552`) — cosmetic only.
- POST /api/v1/jobs/ is idempotent — a FAILED/CANCELED `job_runs` row now REQUEUES in place on retry (fresh attempt budget, carries the new request's payload + actor); SUCCEEDED stays deduped. No manual row deletion needed to retry "Abrir cotización emitida".
- Freeze can emit **quote-only** ("Sólo cotización") when production evidence is incomplete — the order never reaches production_allowed; use seeded versions for production demos.
- COMPLETE on a consuming step (e.g. CUT) is gated by `work_order_material_shortage` when the order's reservation has short SKUs — Iniciar works, Completar 422s. Expected, not a bug.
- No §16 3D view exists in current builds — don't hunt for it in routes/features.
- OWNER login requires MFA enrollment (aal2) on first run; use ESTIMATOR for edit flows, WM for production/purchasing — the position editor hard-blocks non-EST roles ("Tu rol no permite editar proyectos").

## §03 commercial-workspace testing (wt-commercial learnings)

- **Fresh fixture orgs are empty** — a brand-new org (e.g. devin-designsys, 1fcb95f8) has NO `pricing_rules`, NO `cost_lists`/`cost_list_items`, and only the seeded DEMO_60_* quotation authorities. `pricing_preview` 422s generically ("No se pudo cotizar…") — the real code is only in the response body (`pricing_rules_not_found`, `cost_list_not_found`, `incompatible_cost_unit`). Replay `POST /api/v1/pricing/preview/` with a GoTrue password-grant token (`POST $API_URL/auth/v1/token?grant_type=password` + `X-Organization-ID`) to read `error.code`.
- **Cost-item units must match the lookup contract**: profile purchase skus → `BAR` (falls back to `M`), reinforcement/steel commercial skus → `M`, technical glass/panel skus → `M2`, kit skus (`KIT-*`, `DEMO-BUY-KIT-*`) → `KIT`, fittings → `EA`. `incompatible_cost_unit` = item exists but unit wrong — update `cost_list_items.unit`, don't re-seed.
- **Emit-form controlled checkbox**: `label.quotation-confirm input` is React-controlled — coordinate clicks at ≤67% zoom often hit without toggling `confirmed`, leaving `Emitir cotización` disabled even when visually checked. Fallback: console `cb.click()` on it, then click the (now-enabled) button. Same trick works for `Calificar` / other disabled-until-confirm buttons.
- **Navigation instability at low zoom**: address-bar Enter and `<a>` clicks intermittently fail to navigate (autocomplete/hover-target issues); `location.href='…'` via console is the reliable fallback. The workspace is ~1440px-designed — run browser zoom ~50–67% and verify coordinates with `getBoundingClientRect()` + zoom factor, or the `devin-scrollable` aside's inner content will shift under your cursor.
- **Compare needs 2 sealed revisions**: apply → emit REV-A → `Editar cotización` (successor, confirms) → edit position → reprice → apply → emit REV-B. The `successor` POST frees prices; compare then shows real before→after diffs (dims, net price, spec-change note).
- **job_runs retry**: `POST /api/v1/jobs/{id}/retry/` requeues terminal FAILED rows in place (attempt reset). Seed a FAILED clone (`INSERT … SELECT` with `idempotency_key||'-x'` — unique index blocks identical keys) to exercise the UI Reintentar path; the runjobs worker must be running for the requeued job to reach Completado.
- **Analytics defect live in this build**: `GET /api/v1/analytics/summary/` 409s for members — `_summary` counts `job_runs` inside the documentary (authenticated) scope, but `rbac_repair` grants job_runs only to service_role/postgres. Dashboard "Necesita atención" shows "No pudimos cargar la operación de hoy." — a real defect, not env. Jobs views are fine (`job_scope()` verifies inside RLS then yields outside it).

## Merged stack (89d22e0+) extras

- **Job worker required**: artifact generation (DOC-01/03) is now async via the `jobs` queue — the UI polls `/api/v1/jobs/{id}/` forever unless a worker runs: `python backend/manage.py runjobs --poll 1.5` (same env as runserver). No worker = "Generando cotización…" spinner forever.
- **Async artifact open**: the emitted-doc button fetches the artifact and downloads it via an anchor — a post-job `window.open` runs outside the user gesture and gets popup-blocked. If a new open flow ever opens a tab after awaiting, it will hit the same block.
- **Fresh-DB column grants**: `authenticated` has column-level (not table-level) SELECT on `projects`/`project_positions`. New columns added without grants → `GET /projects` 409 `pricing_transaction_rejected` (SQLSTATE 42501). Any migration adding a column to a column-granted table must GRANT it (see 20261020000000 for the projects repair).
- **Fixture API shapes**: POST `/projects/`; POST `/projects/{id}/positions/` `{location_tag,quantity,design:{system_id,nominal_width_mm,nominal_height_mm,color,parametric_tree}}`; POST `/pricing/preview/` `{project_id,pricing_mode:COST_PLUS_MARGIN,context_code:DEFAULT,currency:CLP,effective_date,discount_pct,target_margin,segment:RETAIL,confirmed,reason}` then POST `/pricing/operations/{op}/apply/` `{reason,confirmed:true}`; GET/PUT `/documents/projects/{id}/inputs/`; POST `/documents/projects/{id}/freeze/` `{pricing_operation_id,confirmed:true}`; POST `/production/versions/{vid}/release/` (OWNER/WM only); POST `/production/orders/{oid}/optimize/` `{color}` (required!).
- **Org needs `pricing_rules` row** (`INSERT INTO public.pricing_rules(org_id,pricing_mode,default_margin_pct,tax_rate_pct,waste_factor_pct,labor_rate_per_m2,installation_rate_per_m2)`) else preview 422s `pricing_rules_not_found`.
- **Cost lookup mixes SKUs**: pricing calls `cost()` on purchasing SKU for profiles/steel (DEMO-BAR-*, DEMO-STEEL-BAR-*), but TECHNICAL sku for glass (GLASS-BASE @ M2) and kits (KIT-TURN @ KIT) — seed both forms.
- **workshop_annotations**: ONE record per (bay_id, leaf_id) target — when prep echoes `leaf_id: null`, merge drains+closing+tramo+finish+coupler into the single bay annotation; a second record with the same (bay,null) pair → freeze `Duplicate annotation target` → 422 documentary_authority_required.
- **Priced projects lock positions** — "Duplicar proyecto" needed to edit; demo canvas edits on an unpriced project instead.
- Production optimize UI requires typing a color (placeholder "BLANCO" is not a value) before the button enables.
- **Backend restart hazards**: `manage.py runserver` restarts must verify the old PID actually released :8000 (check log for "port is already in use", kill by exact PID) or the UI silently tests stale code. `supa.env` exports `ANON_KEY`/`SERVICE_ROLE_KEY`/`JWT_SECRET`/`API_URL`/`DB_URL` — map them to `SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_JWT_SECRET`/`SUPABASE_URL`/`DATABASE_URL` or every request 401s and the UI drops to "Acceso tenant no disponible" (expired session → fresh Mailpit magic link).
- **Phase-1 editor surface map**: one registry drives Ctrl+K palette + canvas right-click + toolbar; `+` handles add units; armed split commits at click offset; `wheel` pans the SVG. Native selects may need double-click. Context menu clamps into the viewport — if items clip, the measured-fit regressed. MOCK AI route: same (prompt,product,system) re-Generar replays the audit row — a 500 there is the jsonb `output_payload` decode bug.

## Branch switching + shared-tree hazards

- runserver uses `--noreload` — after `git checkout` of a new branch, RESTART Django or it serves the old commit (symptom: new API fields like `handle_requirements` missing). `/tmp/supa.env` exports `API_URL` (not `SUPABASE_URL`) — Django needs `SUPABASE_URL=$API_URL` else all tokens 401 `invalid_token`.
- `pkill -f "manage.py runserver"` matches your OWN shell command line and kills it — use `pgrep -f 'manage[.]py'` + `kill` instead. Start detached: `setsid nohup <script> >log 2>&1 </dev/null &`.
- Shared checkout may carry the lead's UNCOMMITTED WIP — check `git status --short` before backend restarts; a dirty `options.py`/`ProductFrontSvg.tsx` broke design-options (500 `.name`) and Vite builds (parse errors) mid-run. Workaround for backend: `git worktree add /tmp/wt-<sha> <sha>` and run manage.py from there; for the frontend there's no clean isolation — retry transient parse errors, or bypass the editor by creating positions via `POST /api/v1/projects/{id}/positions/` (product-v2 tree JSON, returns 201+BOM) and test the doc-prep UI from the project page.
- Date `<input type=date>` fills need a click ON the mm segment then digits only (09→23→2026 auto-advances); typing slashes or a focused omnibox leaks text into the address bar.
- R09/R07/R08 inspector rules gate documentary_complete: per-bay `workshop_annotations` need finish_class+continuous_width_mm+has_coupler (R09), bottom_drain_holes_mm (R07), closing_points_perimeter_mm (R08) — no UI editor for any of them; a UI-only emission always seals "Evidencia de diseño" even with handles filled via UI.

## Workshop inputs UI (branch workshop-inputs / later)

- "Datos de taller" collapsed `<details>` inside the position fieldset in "Preparar emisión" — per-bay Desagües inferiores (CSV mm), Tramo continuo, Acople de dilatación (Sí/No select); per-leaf Puntos de cierre (CSV mm, closing positions around leaf perimeter); per-span Exigencia estructural (Ix cm⁴ + Base de cálculo — only rendered when spans exist); per-glass Cantos pulidos select (Pendiente/Sin pulido/Con pulido — "Con pulido" reveals Superior/Derecha/Inferior/Izquierda edge checkboxes); Accesorios Cobertura select. Every unanswered control shows a "pendiente" chip.
- NO save button — "Emitir cotización" PUTs `/documents/projects/{pid}/inputs/` with all in-memory fields then POSTs `freeze/` atomically. A page reload loses unsaved edits (verify unsaved state is gone after F5 before re-typing).
- Inspector value checks (NOT just presence): R07 needs `bottom_drain_holes_mm` count ≥ required_bottom_drains for bays wider than width_trigger (DEMO_60: ≥3 holes for bays >800mm); R08 needs closing-point gaps ≤ max_spacing_mm (DEMO_60: 800mm) around the leaf perimeter (~4184mm for a 796×1296 leaf → ~6 points). Sparse-but-present values → FAIL → 422 `inspector_red_blocks_documentary_freeze`. The UI surfaces NO field-level error — diagnose via DB: `snapshot_json->'inspector'` on project_versions (after emit) or reproduce `dekopen_engine.inspector.inspect` in a Django shell (`config.settings`, tables `project_positions` + `position_documentary_inputs`).
- "Evidencia completa" = documentary_complete=true AND production_allowed=true → DOC-03 generatable (WM role). "Evidencia de diseño; faltan antecedentes de producción" = design-only → DOC-03 → 422 `manufacturing_document_incomplete`. Assemblies (product-v2) always force both false — quote-only by design.
- Labels: classic positions show "Vano N"/"Hoja N"/"Vidrio N"/"Travesaño N · X mm"; assembly targets namespace `<module_id>|<id>` — known leak: leaf labels use raw module id ("Unidad m2 · hoja 1") while bays/glass use ordinals ("Unidad 1 · Vano 1").
- Fixture shortcuts: project/position creation via POST `/api/v1/projects/` + `/projects/{id}/positions/` is faster than the editor for repeat fixtures (TURN_LEFT tree: `{"type":"BAY","opening_type":"TURN_LEFT","glass_thickness_mm":"4.00","glass_spec":"4.00","glass_article_sku":"GLASS-BASE"}` — but note a saved UI-built position folds to this same shape; position ids like `00000000-0000-4000-8000-0000000000aa` work).
- The split-position (Dividir en horizontal) produces a travesaño span target → structural editor appears; R12 is NOT_APPLICABLE for spans <4500mm so Ix/base are optional-but-stored (target_id "m1-sh1" = module-prefixed sash/sash-horizontal id).

## Agente live-provider (mimo)

- Source BOTH env files or the app silently breaks: `set -a; source /tmp/supa.env; source /home/ubuntu/.dekopen-mimo.env; set +a` — missing `/tmp/supa.env` → `invalid_token` + "Acceso tenant no disponible"; missing the mimo env → the gateway runs the MOCK provider (same goal, same product replays one audit row) and you are NOT testing real AI.
- Restart Django with `--noreload` after pulling agent changes; a stale server serves the old code (the ops-loop fixes shipped mid-session needed a restart to take effect).
- The agent endpoint is `POST /api/v1/ai/agent/` (capability `agent`, 8 credits/round — one goal debits per round, up to 3 rounds). Roles: OWNER/ESTIMATOR/WORKSHOP_MANAGER.
- Ops loop (position surface): goal → ops card → "Aplicar N operaciones" → canvas mutates (dirty "Cambios sin guardar") → Guardar persists. Verify the DB afterwards (`project_positions.parametric_tree`) — the card alone doesn't prove the save.
- `alto_no_declarado` / `*_no_declarado` rejections = the model emitted the wrong field names for an op (e.g. `value`/`refs.module_ids` instead of `height_mm`/`module`). Check the raw emitted JSON in `ai_audit_logs.output_payload` — the reason codes surface in `response.rejected`.
- prepare steps deep-link only to their action's route template (emit_revision → `/projects/{id}/pricing`, payments/documents → `/projects/{id}`, WO actions → `/production`, catalog → `/catalogs/systems`, cert → `/settings/general`) — a prepare pointing elsewhere is dropped server-side; a missing card is often a rejected path, not a model miss.
- `queries` chips include the caller's own surface (prepended) — "Consultó panel" appears even with zero model queries.
- Pricing a NEW demo project needs `DEMO-BAR-COPLE-*` rows in `cost_list_items` (27 SKUs) or preview 422s.
- `parametric_tree` comes back as undecoded text from raw cursors — if a projection shows modules/couplings null, suspect the decode, not the data.
