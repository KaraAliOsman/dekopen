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
- pgTAP: `supabase test db` only works from the MAIN repo dir (`cd /home/ubuntu/repos/framedex`), but the test file path may point into a worktree. NEVER run `supabase db reset` to clean a dirty DB when working from a worktree: the CLI is bound to the main repo, so the reset applies only the main checkout's migrations and wipes every newer worktree migration + fixture. Repair instead by applying the missing migrations manually in order (`docker exec -i supabase_db_dekopen psql -v ON_ERROR_STOP=1 -U postgres -d postgres -f /dev/stdin < <file>`) and recording each version in `supabase_migrations.schema_migrations`.

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

## §05 renderer review

- Verify declared-profile extrusion via the **Corte clip cut-face** — the stepped Z-profile cross-section is the cleanest discriminator vs a flat box; surface orbits don't distinguish it.
- Starter cards are `button.starter-card` containing `.starter-card-title`.
- Coupling angle/coupler commits on a dirty product raise the unsaved-changes navigation guard — commit via blur only and expect every navigation to prompt until Guardar.
- `/benchmark` 3D captures are click-to-activate (studio still → "Orbitar"); they no longer keep ~10 live contexts, so prior `Context Lost` warnings are gone — a still means "not activated", not a failed render.
- Selected members glow accent-teal in 3D (not amber) — a warm tint on unlit side faces while a module/bay is selected is the old highlight hue, not a material bug; verify selection state in the tree before reporting tint.
- For coordinate-level hardware checks, temporarily expose the scene on window: `useEffect(()=>{(window as any).__scene3d=scene;},[scene])` in Model3DView + `(window as any).__leafT` leaf refs in LeafGroup — then read per-solid `surface/leafId/center/z0` via CDP instead of squinting at pixels. **Revert before reporting** (hook is not shippable). Solids: `surface∈{frame,sash,glass,bead,gasket,hinge,handle,pull,escutcheon,panel,threshold,sill,coupler,mullion,track}`.
- Hardware-fidelity facts (4259465): hinges live in the rebate cavity, count = `leafH>1700?3:2` windows / `leafH>2200?4:3` doors (so a 2000 window / 2400 door exercises the +1); handle = rose+spindle+**lever hanging down** (lever centre y < rose y) + cylinder escutcheon on doors; doors get a 3-sided frame + `threshold` bar (30mm) under the leaf — leaf bottom sits on it, never reaches the floor; handle_height_mm measures from module OUTER_BOTTOM.
- Sliding-leaf open: each MOVING leaf carries `dir`(± toward adjacent slot) + `travel`(bounded by rail room) and the Abrir pose animates by `dir*travel` — on all-MOVING 2L only the inner-rail leaf moves (both moving just swaps slots and reveals nothing); 3L/4L asymmetric dirs open real gaps. FIXED panels glaze directly (no sash/pull/motion).
- Transom/stacked products: build via the editor's "Dividir en horizontal/vertical" button (renders a `mullion` member between panes). POSTing a hand-written SPLIT_H `parametric_tree` to `/positions/` returns `validation_error` — the manual-tree path doesn't accept splits, so use the UI.

## §17 commercial / portal proposal chain

- Full quoted→portal chain (all via `/api/v1/`): `POST pricing/preview` `{project_id,pricing_mode,context_code:'DEFAULT',currency:'CLP',effective_date,discount_pct,target_margin,segment:'RETAIL',confirmed:false,reason}` → `POST pricing/operations/{op}/apply/` `{reason,confirmed:true}` → **save documentary inputs** `PUT documents/projects/{pid}/inputs/` (requires `payment_terms` non-blank + `quotation_valid_until` date + per-position `{position_id,calculation_hash,manufacturing_placement_policy_id,handle_requirement_policy_id,reinforcement_cut_policy_id,workshop_annotations,structural_inputs,glass_polishing,handle_intents,accessory_schedule}` — build from the GET /inputs response; `handle_intents` from each `handle_requirements[].requirements[]` `{bay_id,leaf_id,handle_domain_slot}` + `requested_height_mm` + `vertical_reference` ∈ OUTER_TOP/OUTER_BOTTOM/LEAF_TOP/LEAF_BOTTOM) → `POST documents/projects/{pid}/freeze/` `{pricing_operation_id,confirmed:true}` (NOT `allow_incomplete_workshop` — that's a param, not a field) → project `QUOTED` → `POST projects/{pid}/quote-link/` (no body) returns `{token,expires_at}` → portal route is **`/cotizacion/<token>`** (NOT `/portal/quote/`). Public read `GET portal/quotes/{token}/`; decide `POST portal/quotes/{token}/decide/` `{decision,decided_by,note,decided_rut}`.
- `cost_list_not_found` at preview means a **commercial/purchasing SKU** lacks a `cost_list_items` row — the priced keys are NOT catalog SKUs: profiles via `profile_purchase_mappings.commercial_sku` (DEMO-BAR-*), steel via `reinforcement_articles.commercial_sku` (DEMO-STEEL-BAR-*), glass via `glass_purchase_mappings.purchasing_sku` BUT the position's declared `glass_article_sku` (e.g. GLASS-BASE, unit M2), panels via `panel_purchase_authorities.purchasing_sku`, kits via the catalog `kit_sku` (unit KIT). Seed ALL of them in an active `cost_lists` row (valid_from<=date, valid_to null-or-future). pricing_rules: `tax_rate_pct` is a FRACTION (0.19), `waste_factor_pct=0.08` exact, margins `default_margin_pct`∈[0,1).
- Portal reads run `SET LOCAL ROLE portal_backend` + `app.portal_org_id` GUC; a `portal_transaction_rejected` on a valid token = a missing `portal_backend` GRANT/portal-scoped RLS policy — check `git status`/`supabase db push --local` for a pending migration before calling it a code bug (this exact trap hit on `project_payment_links`).
- `--noreload` Django serves stale bytecode — restart it after any backend edit or you'll test old code (a `decide_quote` label drifted mid-session because of this).
- Decided/superseded: `approval_status≠PENDING` renders the decided banner; `superseded` (current_revision≠version.revision_code) renders `portal.superseded`; a second decision on a decided deal → `quote_already_decided`/`quote_link_stale` (409, handled gracefully by re-fetch). `decided_by`/`decided_note` are intentionally NULL in the public payload.
- Rasterize DOC-01 PDFs locally: fetch `quote_pdf_url` (signed Supabase storage URL) then `pymupdf` → `pg.get_pixmap(matrix=fitz.Matrix(2,2))` per page.

## Production page / workshop surfaces (hostile-review batches)

- Sidebar piece-trace lookup sits between the status filters and the order list;
  match chips deep-link to the order. A work order's detail route is
  `/production/orders/{id}` (order_code like OT-…-01; remix orders suffixed `-RM-NN`).
- Work-order events (`Historial`) come from `production_step_events`. The QC_FAIL
  row only renders `qc_item`/`note` if `event.payload` is a parsed object — one
  regression mode is the backend emitting `payload` as a raw jsonb string (check
  `typeof payload` in `GET /production/orders/{id}/`; a `str` means the serializer
  skipped `json.loads`). The remake card's `remake_reason.qc_item` is a separate,
  decoded path.
- CSV / DXF / Operaciones buttons should generate+download in ONE click — assert a
  browser download fires (watch `chrome.downloads`/`page.on('download')` or the
  Downloads dir), not just that an event is appended.
- Dispatch "Agendar entrega": date defaults to tomorrow, address from the sealed
  project's delivery_address. Typed-signature mode should draw the canvas live on
  `input` (not on blur).

## Position-editor save gating + dead-click / door-position trap

- Guardar `disabled = uncertainCreate || busy || !result || assemblyUnsaveable`;
  `save()` early-returns on a SUPERSET (adds mutationLock/color/product/systemId/
  quantity). So a REAL click on a `disabled` button is swallowed by the browser,
  and a synthetic `dispatchEvent('click')` bypasses `disabled` to reach the handler
  but still no-ops in `save()` — a "programmatic click works, real click dead"
  report usually means the design was unsaveable/in-flight, not an overlay. Verify
  with `elementFromPoint` at the button (it returns the button — no coverer) and
  check `disabled` + the `.handle-pending` hint before calling it a dead click.
- The "Puerta + lateral" (`doorSide`) starter emits BARE bays — door missing
  `panel_article_sku`, sidelight missing glass, coupling missing
  `coupler_profile_sku` — so the position is UNSAVEABLE out of the box (eval =
  `MANUFACTURING_INCOMPLETE`, Guardar disabled, no save POST). To reach a save POST
  you must assign panel + sidelight glass + a coupler (e.g. COPLE-60) AND give the
  door leaf a real size. There is no single-door starter — doors come via the
  "Puerta de acceso" aperture on a lone unit or this coupled template.
- A 400 "missing node id" is NOT a literal backend string — the only trigger is
  `parse_parametric_node` "Every node requires string id and type" → generic
  `validation_error` ("El diseño no es válido…"/"Request validation failed"), and
  the frontend always emits uuid `id`s (walkIntent throws client-side first). An
  eval issue reason like `DOOR_ENTRY <uuid> requires panel_article_sku` embeds a
  node id and can be misread as "missing node id". Capture `POST
  /engine/assembly/calculate/` for the real product-v2 payload.

## Whole-product pass gotchas (final E2E)

- **`--noreload` Django serves stale bytecode — restart after every commit.** Two real
  incidents: a newly-added route (`production/station-queue/`) 404'd until restart, and a
  stale server *masked* a live regression (portal view-tracking `rows(UPDATE)` → 500) — the
  proposal looked fine on pre-commit bytecode and only broke after a restart loaded current
  code. Always restart Django before trusting a result; confirm with
  `curl localhost:8000/api/v1/<new-route>` returning non-404.
- **Restart Django with the full env**, not just DATABASE_URL: SUPABASE_URL/ANON/SERVICE_KEY,
  JWT_SECRET, and `AI_GATEWAY_MIMO_API_KEY`+`AI_GATEWAY_MIMO_BASE_URL` (both required or the
  AI provider reports unavailable). Correct gateway: base `https://token-plan-sgp.xiaomimimo.com/v1`,
  model `mimo-v2.6-pro`, key = org secret `AI_GATEWAY_MIMO_API_KEY` (an `sk-` LiteLLM virtual key —
  the `tp-…` key in the dev .env is for a different LiteLLM gateway and 401s).
- **WORKSHOP_MANAGER login for production:** magic-link redirects to `127.0.0.1` while the app
  runs on `localhost` — mismatched origins lose the session. Inject the session JSON into
  `sb-127-auth-token` AND set `dekopen.active_org.<userId>` to the org id on the *localhost*
  origin, or `auth.me` returns no active org → "Sin acceso".
- **`portal_quote` write-vs-read trap:** `rows()` is SELECT-only (iterates `cursor.description`,
  None after UPDATE). Using it for the view-tracking UPDATE crashes the public proposal GET → 500.
- **AI dock (AskDekopen):** the "IA" header button toggles open/closed — don't double-click.
  Ask = synchronous POST `/ai/ask/` (`surface`, `refs:{project_id}`, `question`,
  `operation_key`), not a queued job. The dock renders its own failure state on
  `ai_provider_error` — that IS the intentional path.

## Phase-03 3D-render capture notes (fenestration evidence)
- Benchmark route `/benchmark` is public — fixture cards `.benchmark-fixture`
  (idx: 0=fixed,1=tiltTurn,2=twoSash,3=sliding,4=sliding3,5=awning,6=door,7=corner,
  8=bow,9=frameless,10=trapezoid,11=arch). 3D activates via `.benchmark-three-activate`
  ("Orbitar"); enlarge the card with `.model3d-view{position:fixed;inset:2%;z-index:9999}`
  (r3f auto-resizes) — then wheel-zoom (OrbitControls dollies to controls.target=center,
  NOT the cursor — zoom toward center then drag the part to middle).
- Close-ups: full-viewport `Page.captureScreenshot` then PIL-crop by
  `getBoundingClientRect` × (pngW/innerWidth). `clip=` param is unreliable under
  emulation (DSF mismatch). Left-drag=orbit, middle-drag=pan, wheel=dolly.
- **WebGL in a fresh CDP chrome**: launch needs `--use-gl=angle --use-angle=swiftshader
  --enable-unsafe-swiftshader` else the 3D card shows "Tu navegador no puede mostrar WebGL".
- **Theme is React state, not data-theme**: `useTheme()` reads a provider that only
  initializes from `localStorage['dekopen.theme']` ON MOUNT — to flip the 3D stage you
  must set localStorage THEN `Page.navigate`/reload. Setting `documentElement.dataset.theme`
  alone changes the page bg but NOT the r3f stage (`--theme-viewport-stage`/`--model3d-*`).
- **DraftField commits on real `focusout` only** — synthetic `FocusEvent("blur")` does
  NOT trigger React onBlur. Use real CDP input: click the field, Ctrl+A, type, then
  Enter (calls `.blur()` → commit) or Tab. Setting `.value` + `input` event leaves it
  as a draft that reverts.
- **UnsavedChangesGuard blocks `Page.navigate`** with a "Leave site?" dialog after any
  dirty editor edit — dismiss it (real click "Leave") or the nav recv() hangs.
- Handle-height out-of-range → 2D `.handle-lever.is-datum-invalid` + `.handle-datum-flag`
  red dashed ring + `<title>` text; 3D `.model3d-diagnostics` chips ("Herraje esquemático",
  "Altura de manilla fuera de rango"). Manilla inspector field = "Altura de manilla (mm)".
- `--model3d-handle`(#4a5055)/`--model3d-steel`(#a9b2b8) use metalness≤0.9 with NO envMap
  → hardware renders near-black/flat. Metalness needs an `<Environment>`/HDRI to read metallic.

## Phase-04 evidence + kit-picker recipes
- **Estimator (aal1) token via magic link**: `POST :25321/auth/v1/otp {email,create_user:false}` →
  read Mailpit `:25324/api/v1/message/<id>` → the email links `…/auth/v1/verify?token=XXX&type=magiclink&redirect_to=…`.
  Do NOT `POST /verify` (returns `otp_expired`/`validation_failed`); instead GET that URL
  **without following redirects** → `Location:` fragment carries `#access_token=…`. Save it for Bearer.
- **Evidence endpoints** live under `/api/v1/catalogs/evidence/` (POST declare→PENDING, GET `?system_id=`,
  POST `<id>/review/ {review_state:REVIEWED|REJECTED}`). Read roles can GET; write roles (OWNER,
  WORKSHOP_MANAGER) needed for POST/review → ESTIMATOR gets `403 catalog_permission_denied`.
- **Declaring evidence LOCKS the system**: it sets `profile_systems.technical_locked`, after which
  `guard_referenced_catalog` blocks any further catalog-row INSERT/UPDATE on it. To clone a catalog
  for testing, do the clone BEFORE declaring evidence on that system.
- **Reaching the Studio kit picker**: `GET /api/v1/projects/design-options/<sys>` returns **422
  `technical_authority_required`** if the system's `handle_requirement_policies.authority` JSONB
  fails `HandleRequirementPolicyV1.model_validate` (strict EngineModel rejects string-typed enums/
  Decimals). Seeded systems are all malformed → picker unreachable. Workaround: `POST /systems/` a
  fresh ORG system with correct `finishes`, clone the whole catalog (articles, bead matrix, kits,
  glass map, infill, manufacturing+reinforcement policies), set `rebate_depth_mm`, then
  `POST /projects/<proj>/positions/` → position saves → editor renders the `Herrajes` select.
- `parametric_tree` node numeric fields are decimal **strings**; top-level `nominal_*_mm` are
  Decimals (serializer). Passing strings top-level → `'<' str vs Decimal` TypeError.

## Phase-06 pricing-testing notes
- **Backend code needs a restart** — `manage.py runserver --noreload` does NOT hot-reload. If a
  new commit's backend fields are missing (e.g. pricing `lines` returning bare
  `{position_index, line_net}` with no `unit_price`), kill + relaunch Django, then re-check —
  do NOT report it as a code bug until the running process is confirmed on the new HEAD.
- **OWNER needs aal2 for pricing writes** — magic-link gives aal1 → `/auth/mfa` wall. Mint aal2:
  POST `/auth/v1/factors/{factor_id}/challenge` then `/verify` {challenge_id, pyotp_code}. Owner
  TOTP secret lives in `auth.mfa_factors.secret` (fixture owner = `NPPECYRXWHNRYC6MCFI4YDWOQ4L25YOY`).
- **Emit gate:** `Emitir cotización` stays disabled until each operable leaf's suggested handle
  height is confirmed via its "Usar sugeridas" button (`legacy_handle_migration_confirmed`).
- **Blocker→Resolver:** `missing_glass_authority` needs a mode-2 `pricing_configuration` with a
  gap (fixture has none). To demo the positioned-blocker + `/pricing/cost-lists` link (OWNER) vs
  `pricing-fix` span (ESTIMATOR), run a USD calc — no fx snapshot → `missing_fx_authority`.
- **Amount parity:** emitted PDF = `POST /documents/artifacts/{id}/access/` → signed_url (storage);
  PyMuPDF (`fitz`) renders/extracts it. Portal = `/cotizacion/<token>` from "Compartir cotización".

## Phase-07 proposal/portal-testing notes
- **Emit a fresh DOC-01 on an already-quoted project:** `Crear nueva revisión`
  (`start_successor` → DRAFT + next REV-x) → pricing page `Calcular y revisar` (preview) →
  `Aprobar y aplicar precios` (APPLIED op) → detail `Preparar emisión` → check confirm →
  `Emitir cotización`. Revisions reuse saved documentary inputs → emit form prefills
  (only valid_until + confirm). `Abrir cotización emitida` lazily generates + downloads the PDF.
- **Share link** = `POST /api/v1/projects/<id>/quote-link/` (OWNER/ESTIMATOR) → `{token,path}`.
  Portal = `GET /cotizacion/<token>` (public). Decide = `POST /api/v1/portal/quotes/<token>/decide/`
  `{decision:APPROVED|DECLINED, decided_by, decided_rut?, note?}` (note required for DECLINED).
- **Decision states** live in `customer_approvals` (token hashed; keep the plaintext token at mint).
  States: PENDING / APPROVED / DECLINED / REVOKED + superseded(`version != project.current_revision`)
  + expired(`expires_at<now`). Idempotent: replays return sealed state, `WHERE status='PENDING'` write is atomic.
- **Portal payment CTA is RLS-hidden** — `payment_url` reads `project_payment_links` under
  `portal_backend` role; RLS keys on `auth.uid()` (null unauthenticated) → always null. To demo
  the CTA a real Flow link must exist AND the role must see it — currently can't.
- **Magic-link mint:** the mail's `verify?token=<long-hex>&type=magiclink` — GET it with
  `allow_redirects=False`, read `#access_token` from the Location fragment; then GET `/user`.

## Phase-08 purchasing/receiving-testing notes
- **Purchasing writers** = OWNER + WORKSHOP_MANAGER (`_ALLOWED`); ESTIMATOR is read-only and
  the UI renders ZERO mutating controls for it (canWrite gate) — use it to verify the gate.
- **Flow:** `GET purchasing/versions/<id>/` (purchasing_state: requirements w/ `open_qty`,
  eligibilities, allocations, orders) → `POST eligibilities/` → `PUT requirements/<id>/allocation/`
  → `POST versions/<id>/confirm/` (advisory-locked batch; **idempotent** — re-confirm on a fully
  claimed type returns live orders, same id+snapshot_hash) → `POST orders/<id>/send/` or
  `/cancel/` (requires `{confirmed:true}`) → `GET/POST inventory/orders/<id>/receiving|receipts/`
  `{receipt_key, lines:[{order_line_id,received_qty,damaged_qty,lot_code,rack_location}]}`.
- **Partial-release:** `order_requirement_lines.released_qty`; coverage = SUM(quantity−released_qty).
  `cancel_order` accepts PARTIALLY_RECEIVED (needs migration 20261228000005's
  `guard_order_evidence` transition; without it → 409 `documentary_transaction_rejected` and the
  UI confirm click is SILENT). good = received−damaged keeps covering; released = quantity−good.
  FULFILLED never cancels (422 `order_state_invalid` — Spanish detail strings since 69a8ff8).
- **Over-receipt is allowed** (no cap vs ordered); surfaces as negative `Pendiente` on the
  orders index — cosmetic, flag it.
- **Remnants:** `reserve_remnants` = atomic `UPDATE…WHERE status='AVAILABLE'` in the caller txn;
  a partial claim raises `remnant_unavailable`. `record_produced_remnants` links child remnants
  via `origin=PRODUCTION`+`origin_order_id`. GET `inventory/remnants/` 500s if any backend code
  passes a `set` to `ANY(::uuid[])` — use `sorted()`.
- **Verify the backend actually restarted** after each fix commit — `--noreload` serves stale
  code silently; a stale process made new purchasing columns look absent until a relaunch.
- **When the session X server dies** (Xtigervnc hung, screenshots/computer-use all timeout):
  run your own `Xvfb :99` + chrome via a persistent `shell_id` exec with `&` — one-shot/setsid
  launches die before DevTools binds. `Emulation.setDeviceMetricsOverride` is INERT on headful
  Chrome 137 and the WM clamps window width to ≥500 px — true 390 px may be unreachable;
  measure `documentElement.scrollWidth` at iw=500 (mobile CSS still applies) as the evidence.

### Phase-10 production/workshop notes
- **Role matrix** (`backend/production/views.py`): `_READERS`=all 5 incl ESTIMATOR; `_STEP_ACTORS`=OWN/WM/INS (delivery transitions, install); `_WORKSHOP_STEP_ACTORS`=OWN/WM/OPR (step transitions); `_WRITERS`=OWN/WM (schedule, dispatch, optimize, remake, packing); `_LEDGER_WRITERS`=OWN/EST (POD payment). QC COMPLETE by OPERATOR → 422 `qc_requires_supervisor` (operator logs QC_CHECK evidence; supervisor signs). Confirm POD needs a **structurally valid PNG** (magic+IHDR crc+IEND; bare b64, no data-uri — helper `_chunk`+zlib in test_delivery_confirmations.py).
- **Partial delivery**: `deliveries.unit_indexes` (NULL=whole saldo), one open trip per order (`deliveries_one_open_trip`); schedule=**PUT** `/delivery/`; subset dispatch `{unit_indexes}`; FAILED frees units; `pending_units = manifest − claimed(non-FAILED)`; trips each carry own guía+POD (`dispatch-note/?note=<id>`, `delivery/confirmation/?delivery=<id>`). Install requires DISPATCHED + full manifest DELIVERED + ≥1 confirmation.
- **Remake**: `POST /orders/<id>/remake/` on HOLD order → `-RM-nn` w/ `payload.remake_of`+`remake_reason`; drops optimization+packing → `optimize/` + `packing/` must re-run before steps start (422 `work_order_plan_missing`).
- **Backend-role RLS gotchas**: code under `documentary_backend()` can only touch tables/columns granted to that role — `clients`, `projects`(OWN/EST/WM policy), `deliveries`, `dispatch_notes`, `orders`(WORKSHOP_OT), `production_step_events`. New reads inside sealing txns → 42501 → 409 `documentary_transaction_rejected`; check `docker logs supabase_db_dekopen` for the actual `permission denied for table X`.
- **`?piece=<code>` deep link** fires `pieces/<code>/trace/` → matches panel (multi-order) or auto-nav (single-order); piece codes like `P03-U01-M06` map to plan codes via trace.labels.
- UI selectors: `li.production-step.step-<status>`, `.operator-card-actions` (sticky), `.operator-qc` (QC form — only when trace loaded), `fieldset.production-delivery-units` (subset chips, pending>1), `ul.production-delivery-trips`, `.production-delivery-pending` (saldo line), `.production-trace-matches`.

### Phase-11 CNC/machining notes
- **CNC fixture** via API as WM: `POST production/cnc/tools/` (`code` `saw|drill|end_mill|mark`, ToolKind must be a valid enum — `MARKING` is NOT one; use `kind: "MILLING"` for end_mill/drill) then `POST production/cnc/machines/` (`coordinate_systems` valid values: `MEMBER_PLAN`,`BAR_AXIS` — `BAR_PLAN` 422s). Tools map by `code` to op `tool_id`.
- **Readiness** = `GET orders/<id>/cnc/readiness/` → `members[]` × `verdicts[machine_id]`; machine gates run FIRST (coordinate_unsupported/unsupported_kind/no_compatible_tool BLOCK), authority gaps after (tool_undeclared/depth_undeclared BLOCK — **unreachable on real plans**, ops always carry tool_id; engine-test only). HANDLE_PREP → `feature_point_only` WARN.
- **Programs**: `POST orders/<id>/cnc/programs/` `{machine_id,member_id}` → `program_no = {order}-{member_label(alnum12)}-{machine_code}-{seq:02d}`; `input_fingerprint`=`plan_fp+machine_fp` — PATCHing machine clamps/tools/postprocessor SUPERSEDES on next list; `GET cnc/programs/<id>/file/<name>` serves operations.json|operations.csv|manifest.json (422 `cnc_program_superseded` if stale). UI hardcodes the two non-manifest names — manifest only reachable via API.
- **404 gotcha**: a program 404s the moment a NEWER seq row exists for same order+member — only the latest program is addressable by id; superseded ones stay listed (stale flag) but file endpoints 404.
- **`generate_program` had NO status guard** — works on terminal orders too.
- **L/R mirror check** without UI: ops-export `members` is a **dict keyed by member hash** (not list); HANDLE_PREP host x≈52 = left stile, x≈1148 = right stile; sliding leaves prep facing stiles.
- `test_operations.py` gate: `test_drill_without_authorized_depth_is_an_exact_blocker` (depth_undeclared), `test_member_op_without_tool_is_blocked` (tool_undeclared), `test_point_prep_is_reference_not_depth_blocked`, `test_manual_custom_op_passes_with_declared_datum`.

### Phase-12 assistant/Bot notes
- **MOCK provider flip** (lead-approved when MiMo is dead): `update ai_routes set provider='MOCK', provider_model='mimo-v2.6-pro'` + `AI_GATEWAY_MOCK_ENABLED=1` exported on **both** runserver and runjobs (worker runs `ai.agent.run` jobs — it needs its own env AND a restart on every backend commit; it does NOT auto-reload). MiMo: `tp-…` key rejected by api.primalabs.ai, 429 quota on token-plan-sgp for all models.
- **Agent ops path under mock**: `input_payload["product"]` (top level, sent by the dock) drives the `kind:"ops"` step on the `position` surface; goal must match mock regexes — `ancho de N mm`/`ancho total de N`, openings corred→SLIDING_2L, puerta→DOOR_ENTRY, oscil→TILT_TURN_LEFT, fijo→FIXED. Invalid values → transcript `rejected:[{op,reason}]` (e.g. `ancho_invalido`), no apply button.
- **Apply gating**: `AgentBody.applyOps` — in-session turns identity-compare `turn.product !== bridge.product`; restored turns compare `product_sig` = `productFingerprint(designAssistProduct(product))` (module dims+couplings only — intra-module edits like splits do NOT invalidate). Stale-op tests must change module dims/couplings or switch position refs.
- **Job lifecycle API**: POST `/ai/agent/` (202; `operation_key` replays same job_id, recycled key+diff goal → 409 `ai_operation_key_conflict`), DELETE `/jobs/<id>/` cancel (409 `ai_job_terminal` once done), POST `/jobs/<id>/retry/` (FAILED_RETRYABLE→202; SUCCEEDED→409 `ai_job_not_retryable`), POST `/jobs/<id>/outcome/` (applied/declined/apply_failed dedupe on turn+step+action). RUNNING window is <100ms under mock — catch it by polling at 100ms or test cancel on QUEUED/WAITING_FOR_APPROVAL.
- **Role gates**: `_AGENT_CALLERS`=OWNER/ESTIMATOR/WORKSHOP_MANAGER — OPERATOR/INSTALLER get 403 `documentary_permission_denied` (validation errors 400 BEFORE role check, so send a fully valid body when testing the 403). OPERATOR hits the editor route-gate ("Sin acceso") anyway.
- **Ask thread restore**: GET `/ai/ask/?surface=..&refs=<json>` (GET on the ask path itself, no `/thread/` subpath). Watch `answer` arrive as a JSON string vs object — phase-12 defect F12-1: restored turns render blank answers.
- **Dock**: `.topbar-ai` opens; mode buttons `.ask-dock__mode` ("Agente"); goal textarea placeholder "¿Qué necesitas lograr?", submit "Ejecutar"; ask mode uses a text INPUT ("Pregunta sobre esta superficie…"), submit "Enviar". React inputs need native setter + input event. `/assistant` workspace lists jobs w/ states + outcome metrics; `button.aiws-job` opens detail with per-turn claims + `evidencia:` labels.

### Phase-13 landing/auth-flow notes
- **Magic-link origin must match `site_url`** (`supabase/config.toml` = `http://127.0.0.1:5173`, allow-list `127.0.0.1:5173/auth/callback`). Browse `127.0.0.1:5173` (not `localhost:5173`) when testing magic links — mismatch makes `emailRedirectTo` fall back to site root AND strands `sessionStorage dk:returnTo` cross-origin.
- **Never GET the verify URL to inspect it** — magic-link tokens are single-use; extract the URL from Mailpit text and navigate the browser to it directly.
- `/auth/callback#error=access_denied&error_code=otp_expired` renders the expired-link copy. Guards stash `from` via router state → LoginPage writes `dk:returnTo` sessionStorage → consumed in callback/mfa/select-org (`returnTo.ts` validates: no `//`, no scheme, no `\`, no `/login` or `/auth/*`).
- **Onboarding** `/onboarding`: 7 steps (identity→system→data→client→project→position→quote); draft persists in `sessionStorage onboarding:<orgId>`; "Abrir editor de vanos" deep-links to `/projects/<new>/positions/new`; finish lands `/projects/<id>`; only linked from dashboard when 0 projects. Position editor requires glass assignment before Guardar enables.
- **Floor-role home**: OPERATOR/INSTALLER land on `/production` via `HomeRedirect`/`isFloorRole`.

## Phase-14 closure notes

- **`/auth/v1/otp` is now `otp_disabled`** (`create_user:false` in gotrue config). For API auth use password grant: `POST /auth/v1/token?grant_type=password` `{"email","password"}` — fixture password is `Demo-Fixture-2026!` for all roles.
- **DB wipe recovery** (after `supabase db reset` / `make test-db` — which also *stops* the stack): `supabase start` (re-applies 138 migrations + seed.sql) → `scripts/dev_fixture.py` **with `/home/ubuntu/repos/framedex/.venv/bin/python`** (system python lacks httpx) → re-insert `auth.mfa_factors` TOTP row for owner (new uid each fixture run — query `auth.users` first; secret `NPPECYRXWHNRYC6MCFI4YDWOQ4L25YOY`) → restart `runjobs` worker (stale DB conn stops draining jobs).
- **Full sale chain recipe**: project→positions→doc-inputs PUT (pass `workshop_suggestions` VERBATIM — dropping `finish_class`/`has_coupler` trips inspector R09; handle intents `LEAF_TOP`+400 not LEAF_BOTTOM+1000 which overflows short leaves)→pricing preview (`target_margin` as fraction `'0.35'`, `extras[{label,kind,amount}]`)→apply→freeze (`pricing_operation_id`+`confirmed`)→emit. Color must equal stocked physical color (DEMO_60 = WHITE; FOILED → `physical_stock_color_mismatch`).
- **Revisions**: emitted project positions 409 `revision_required`; `POST projects/<id>/successor/ {confirmed,expected_current_revision:'REV-A'}` → DRAFT REV-B. `reset-pricing/` clears APPLIED pricing to edit. Compare: `GET documents/projects/<pid>/versions/compare/?base=REV-A&head=REV-B`. Portal token stays bound to its emitted revision.
- **Purchasing**: suppliers→`versions/<v>/eligibilities/`→`requirements/<id>/allocation/` (PUT `supplier_eligibility_id`)→`versions/<v>/confirm/`→`orders/<id>/send/`→`inventory/orders/<id>/receipts/` (receipt_key+lines; damaged_qty excludes from usable). `orders/<id>/cancel/` on PARTIALLY_RECEIVED releases only unreceived balance.
- **Production**: transitions at `POST /production/steps/<id>/transition/` `{action:START|COMPLETE|BLOCK|NOTE|QC_CHECK,qc_result:PASS|FAIL}` — sequence enforced; QC FAIL → order HOLD; remake needs `optimize/` first (`work_order_plan_missing`); then steps→packing→labels→dispatch (needs COMPLETED).
- **CNC enums** (serializer whitelists, reject extras): ToolKind=`SAW_BLADE|DRILL_BIT|END_MILL|ROUTER_BIT|PUNCH|MARKING|CUSTOM` (NOT "MILLING"); faces=`OUTSIDE_FACE|INSIDE_FACE|TOP_EDGE|BOTTOM_EDGE` (NOT A/B/C/D); kinds=OperationKind values. manifest.json hash-verifies program files.
- **Strict serializers** reject extra keys (400): no `confirmed` on withdraw/cancel, no `reason` on cancel.
- **Payment**: `payments/` manual receipts OK; `payment-links/` → `flow_not_configured` unless Flow configured in Settings.
- **Mobile floor**: window manager min ≈500px — use iw=500 as the mobile proxy; check `document.documentElement.scrollWidth` for overflow and walk all elements >iw to find culprits.
- **Recorder captures the real display `:0`** — Chrome may be running on virtual display `:99` (invisible to the recorder). Relaunch it with `DISPLAY=:0` before recording; beware `pkill -f chrome` matching your own shell command string.
- **Recorder "edited" output keeps only annotation windows** — for a full-length demo, concatenate the `raw-*.mkv` segments instead (see `docs/redesign/captures/phase14-demo/`).
- **CNC plan references tools by `code`** — seeding a tool requires `tool_id` whose `code` (e.g. `'drill'`) matches what the plan references, not just the kind.

## Phase-15 sweep notes
- Purchasing UI is fully index-driven: order send needs inline form (date+contact+confirm checkbox); receiving form lives inside the order's `details.purchasing-receiving` on `/purchasing` — it's React-controlled, click the `summary` (setting `.open=true` doesn't render children); revision picker is a native `<select>` (prototype setter + change event).
- Stock adjust: `details.inventory-adjust` → per-item "Ajustar" opens `.inventory-remnant-form` (qty+note required); verify in `/api/v1/inventory/movements/`.
- Remnant "Etiqueta" renders `.inventory-label` inline (no close button); "Imprimir" → `window.print()` w/ `@media print` isolating the label (24-page count in dialog is harmless — hidden content). Print dialog BLOCKS CDP websocket — cancel it via GUI before continuing.
- Doc generators ("Generar / abrir", DOC-0x PDF/XLSX) call `window.open(signed_storage_url)` — stub `window.open` to capture the URL, then `urlretrieve` and verify `%PDF`+`%%EOF`/PK.
- Mobile pass: `Emulation.setDeviceMetricsOverride width=390 dsf=0 mobile=false` — must re-check `innerWidth` after nav (mobile=true can yield iw≠width).

## Phase-16 evidence-harness notes
- **OWNER TOTP vault**: `dev_fixture.py` does NOT enroll a factor — `frontend/scripts/ux-capture/auth.ts` enrolls on first run and persists the base32 secret to `.fixture-state.json` under `totp` (`{"<email>": "<BASE32>"}`). Reuse it for manual tests:
  `cd frontend && node -e "const O=require('otpauth');console.log(new O.TOTP({digits:6,period:30,secret:O.Secret.fromBase32('<B32>')}).generate())"`.
  With a factor enrolled, `/auth/mfa` shows the challenge form directly.
- **Multi-org selector**: `/select-organization` only renders when `/api/v1/auth/me` 409s `organization_selection_required` — no persisted org pick. The app stores it in `localStorage["dekopen.active_org.<user-id>"]`; sign-out does NOT clear it. To force the selector in a reused profile: DevTools → Application → Local Storage → delete `dekopen.active_org.*`, keep `sb-` auth-token, navigate to `/select-organization`.
- **Expected console noise** in the owner login: `me` 409 (org-selection) then 403 `mfa_required` — the contract, not errors.
- **Fixture rerun safety**: `supabase start` after a container wipe creates a FRESH DB — re-run `SUPABASE_SERVICE_ROLE_KEY=… .venv/bin/python scripts/dev_fixture.py` and re-read `.fixture-state.json` (the script is idempotent per-DB; a state file from a wiped DB is stale but harmless — it just re-seeds).
- `node` resolves via nvm (v24.x) — `npm run ux:capture` (`--experimental-strip-types`) works as-is; `~/node22` is stale.
- `browser_console`/CDP only works when Chrome was launched with `--remote-debugging-port`; otherwise use F12 DevTools UI.

## D04 herrajes inspector/OT notes
- **Design-options API** (`/api/v1/projects/design-options/{system_id}/`): kits under `hardware_kits` (not `kits`), parts under `contents` (not `components`). Decimals serialize as STRINGS (`"60"`, `"500"`) — `typeof x === "number"` checks fail silently on these fields; use the `num()` coercion helper (qty_rule's `per_mm > 0` survives coercion; `cut_rule.minus_mm` typeof checks do not).
- **Inspector «Herrajes»**: bay select = click the tree `button:has-text("Oscilobatiente izquierda")` (or the bay rect); section is a `<details>` CLOSED when the bay has no explicit `hardware_set_sku` — click its `summary`; nested «¿Por qué este kit?» and «Avanzado» each need their own summary click. «Altura de manilla (mm)» DraftField lives in the «Relleno» section; the out-of-range hint renders inside «Herrajes».
- **Avanzado table prefers engine-emitted BOM lines** (`resolvedHardware.contents` with real `qty`/`length_mm` from the finished leaf) when the last calc covers the same kit + option set; the local mirror on the bay envelope is only the pre-calculation fallback. If inspector Largo ≠ OT picking length, that's the bug signature.
- **OT deep-link**: `/production?order=<order_uuid>` selects the order directly; `hardware_picking`/`hardware_machining` live in `public.orders.payload_json` — no dedicated UI, verify via API/DB.
- **Playwright scripts outside `frontend/` can't resolve `@playwright/test`** — import via absolute path `"/home/ubuntu/repos/dekopen/frontend/node_modules/@playwright/test/index.mjs"`.
- **Mailpit**: message DETAIL has no `Created` field (only `Date`); filter newest on the `/api/v1/messages` LIST item's `Created` before fetching detail.
- `locator.screenshot()` on `<details>` can fail ("not visible or not an HTMLElement") — take a `page.screenshot()` after `summary.scrollIntoView()`.
- Force theme in a fresh context: `context.addInitScript(() => localStorage.setItem("dekopen.theme", "dark"))` (values `"light"`/`"dark"`, applied to `documentElement.dataset.theme`).

## D03 aperturas/emisión notes
- **Emit happy path**: project → "Agregar vanos" → starter → Serie de perfiles → inspector «Relleno»: pick Espesor + Vidrio (required or Guardar stays disabled) → "Cotizar proyecto" → confirm → "Calcular y revisar" → "Aprobar y aplicar precios" → ▼Cotización → "Preparar emisión" → pago + validez + per-vano selects (manillas/refuerzos stay on "Seleccionar autoridad técnica", NOT auto-selected) → "Usar sugeridas" on suggested handle heights → confirm → "Emitir cotización". Freeze is all-or-nothing across vanos.
- **runjobs needs the runserver env**: `manage.py runjobs --once` without `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_JWT_VERIFY_MODE` permanently fails `document.artifact.generate` with `document_storage_not_configured` — missing env, NOT a missing bucket. Requeue: `UPDATE job_runs SET state='QUEUED', attempt=0, error=NULL, run_after=now(), locked_at=NULL, locked_by=NULL, completed_at=NULL, started_at=NULL WHERE id=...`.
- **FIXED_SASH leaf facts take no kit by design** (`opening:{movement:FIXED, fixed_in_sash:true}` → `FIXED_SASH`/`DOOR:FIXED_SASH` leaf with `kit=None`, zero candidates). D03 shipped the inspector skip (`inspector.py` continues past leaves whose trace key ends `:FIXED_SASH`); before it, `NoCompatibleHardwareKit` aborted every freeze containing one. Diagnose leaf kits in-shell via `documents.service._position_calculations(tree, params)` → `leaf.selected_kit`/`leaf.candidates`.
- **R02 door-ratio is YELLOW, not a block**: seeded R02 = [0.40, 2.50]; standard door leaves run ~2.7–2.9 → `Proporción de la hoja` warning, never `inspector_red_blocks` (R02 is in `_YELLOW_RULES`; status stays YELLOW → freeze proceeds, incomplete-documentary at worst). To keep a door finding-free on the fixture, size leaf w ≥ h/2.5.
- **Freeze error surface is generic**: the UI banner ("Falta o no coincide una autoridad técnica") hides the per-vano reason — it travels in `DocumentaryError.extra["inspector_failures"]` (rule/severity/bay/leaf per entry). Reproduce without UI in `manage.py shell` via `documents.service.freeze_revision_a(..., allow_incomplete_workshop=True)`; `ValueError`s wrap as `Vano «N»: <error>`.
- **Fitting SKUs need EA cost items**: any `fitting.sku` (e.g. `TORNILLO-4X16`) must exist in `cost_list_items` with `unit='EA'`, else pricing 422s `cost_list_not_found`. Seeded into D03 Test Supplier `11111111-2222-3333-4444-555555555555` (keep it).
- **Door-unit sidelights**: frame-fixed lateral = `opening:{movement:FIXED}` + glass; sash-fixed inside a DOOR unit = `fixed_in_sash:true` + `panel_article_sku` (door sash requires panel, glass-only is rejected).

## D07 vano→fabricación inspector notes
- **Inspector mechanics**: clicking the canvas SELECTS a pane, it does not deselect — press **Escape** (`edit.deselect`) AND activate the "Vista general" tab in the inspector's detail switcher to reach "Vano y materiales" → `<details> "Vano y montaje"`. The right inspector is its own scroll container; the canvas zoom/fit control can render offscreen — verify fine print with zoom-region screenshots.
- **Measurement state machine**: CLIENT_DECLARED → SITE_RECTIFIED → CONFIRMED. `positionsMeasurementConfirm {confirmed}` toggles CONFIRMED ↔ SITE_RECTIFIED ("Confirmar para producción" / "Reabrir medida"). A save whose measurement payload differs resets CONFIRMED→SITE_RECTIFIED; an unchanged payload keeps the state ("1700"→"1700.00" is unchanged semantically). CONFIRMED carries `Confirmada YYYY-MM-DD`.
- **Guardar gates**: no dirty gate — disabled only by validation flags, notably `vanoInvalid` when "Fijar medida de fabricación a mano" is checked but dims are empty. An *incoherent* lock only warns, Guardar stays enabled; saving with an unconfirmed measure works (the confirm gate lives in OT release, not the editor).
- **Descuadre vs tolerance**: >1 point per axis shows "Se usa la menor" + `Descuadre {spread} mm — manda la menor.` whenever spread>0, but the red engine warning fires only when spread is STRICTLY > org `vano_spread_tolerance_mm` (default 10). Spread == tolerance shows the note WITHOUT the warning — useful boundary.
- **Preview + chip reactivity**: header chip and inspector preview come from a 350 ms-debounced `positionsMeasurementResolve` — they update live on keystrokes, no save needed. Manual lock shows badge "Fijada a mano" + headline lock dims + warnings "La medida fijada no es coherente…" / "El producto no se está fabricando con la medida fijada manualmente."
- **Fixings/extensions render**: `authority.fixings` seeds use `{label, qty_per_unit, note}` and `frame_extensions` use `{side, label, mm}` — NOT `code`. VanoSection maps label+qty (`"Anclaje perimetral ×8"`). (Bug found & fixed in D07: reading `fixing.code` rendered an always-empty line.)
- **DB check**: `docker exec supabase_db_dekopen psql -U postgres -d postgres -tA -c "SELECT rough_opening_input, measurement_state, measurement_confirmed_at, fabrication_lock, mounting_rule_id FROM project_positions WHERE id='…';"` — fixture record: `width_points_mm:["1620.00","1700.00"]`, `height_points_mm:["1220.00"]`, CONFIRMED, lock NULL, rule EN_VANO (`d441e283-4005-45a3-be70-5324284327e4`, −10 mm/side).

## D06 extras/servicios inspector notes

## Extras panel ("Extras de la posición") gating

- The right-rail extras panel renders ONLY when the detail level is "Vista general"
  AND nothing is selected in the tree/canvas. Detail level defaults to "Diseño"
  (AssemblyEditor.tsx). To reach it: click empty canvas or press Escape (may need
  two attempts — the first Escape can land on a focused input), then click the
  "Vista general" tab button, then scroll the `devin-scrollable` rail — the panel
  sits below "Vano y materiales".
- Suggestion chips (e.g. "Mosquitero enrollable — Las ventanas practicables suelen
  llevar mosquitero") appear only when the article isn't already in the extras list
  and the engine's `extra_suggestions` emit a cause.

## Page layout quirk on /positions/new and /edit

- The editor page does NOT scroll — it's a fixed-height app shell. An expanded
  "Biblioteca de diseños" `<details>` pushes the canvas+tree+rail row below the
  viewport with no way to scroll to it. Click the "Biblioteca de diseños" summary
  to collapse it and reveal the canvas row. The right rail scrolls independently
  inside `devin-scrollable`.

## Unsaved-change guards (two distinct ones)

- In-app React-Router guard on internal navigation: dialog "Hay cambios sin
  guardar. ¿Quieres salir y descartarlos?" with Cancelar/Confirmar — Confirmar
  discards and proceeds.
- Browser beforeunload "Leave site?" fires on ctrl+l URL-bar navigation with
  dirty state; clicking "Leave" sometimes reloads in place instead of navigating
  — prefer in-app links ("Volver al proyecto") and the in-app guard.

## Extras persistence — defect signature and the fixed shape (D06)

- FIXED at 6ae7a3c4 (devin/D06-accesorios-extras): `designPayload()` in
  ProjectPositionEditor.tsx used to emit `parametric_tree: single.tree` (raw
  IntentNode) for `isSingleUnit(product)`, dropping `product.extras` on the
  product-v2 wrapper. Now gated by `hasExtras`: single+extras →
  `parametric_tree: product` (version "product-v2"); single+NO extras still
  saves the classic bare tree. `pickStarter()` also copies `product.extras`
  onto the swapped starter product (template-seeded extras survive a
  design-library swap).
- Pre-fix symptom (if it regresses): add extras → Guardar → "Cambios
  guardados." → reload → "Sin accesorios declarados para este vano." DB check:
  `parametric_tree->>'version'` NULL, `parametric_tree->'extras'` NULL,
  `bom_snapshot->'extra_lines'` = [].
- Post-fix DB shape for a single-unit position WITH extras: `version` =
  "product-v2", `extras` array (e.g. `[{"sku":"EXT-MOSQ-ENR",...}]`),
  `extra_lines` populated. Removing all extras + save round-trips back to
  classic (version/extras NULL) — both directions are worth checking.
- The extras panel also renders on /positions/new BEFORE first save (org
  templates pre-merge into the default product) — you can verify template
  seeding and starter-swap survival without ever saving the position.

## BOM (Despiece y materiales) on the project page

- Select a position row, expand "Despiece y materiales" in the right rail; it
  contains Perfil cuts, Vidrio, kit, Herrajes (Artículo | Herrajes | Cantidad),
  Refuerzos tables. Counted extras land as Herrajes rows with the article SKU in
  the Artículo column and the human name (e.g. "Mosquitero") in the Herrajes
  column — raw enum values like MOSQUITO_SCREEN must not appear; length extras
  appear as profile cuts (e.g. ENS-PVC-60).
- BOM tables also render inside the /edit page below the canvas ("Despiece y
  materiales" details).

## Interaction traps hit while testing (computer-use)

- Chrome omnibox autocompletes typed paths to history entries — typing a
  project URL can land on a recently-visited /positions/<id>/edit instead.
  Prefer in-app links ("Volver al proyecto", breadcrumbs, position rows);
  reserve URL-bar nav for fresh paths or verify the landed URL afterwards.
- Label-vs-input misclick: in the position editor form, the "Ubicación del
  vano" label sits ~20px above its input — clicking the label does nothing and
  the subsequent typing goes nowhere (looks like a silent failure). Click the
  rendered field TEXT, not the label; verify via DOM `text=` that the value
  changed before saving.
- An in-app link click can silently no-op (no navigation, no dialog) — retry
  once, then fall back to URL-bar nav + the native beforeunload dialog.

## Coupled-position build recipe (needed to exercise extras persistence)

- /positions/new → pick a coupled starter OR: single module → "Agregar unidad a
  la derecha" toolbar button. Then every module needs Marco+Hoja+Vidrio assigned
  and the joint needs an Acoplador article (select the "Acoplador ? · 0.0°" tree
  node → Acoplador select → COPLE-60 for 0°). Guardar enables at "Geometría
  válida" even with fabricación-incompleta observations in some builds; fully
  assigned modules clear all observations.

## ai_gateway (IA3) surfaces

- **Modes — env AND DB must agree**: LIVE needs `AI_GATEWAY_MIMO_API_KEY`+`BASE_URL` set, `AI_GATEWAY_MOCK_ENABLED=0`/unset AND `ai_routes.provider='MIMO'`; TEST needs `AI_GATEWAY_MOCK_ENABLED=1` AND `UPDATE ai_routes SET provider='MOCK'`. `MOCK_ENABLED` alone doesn't reroute. Restart `runserver --noreload` AND `runjobs` after either change.
- **Worker required**: `manage.py runjobs --poll 1.5` — agent jobs are async; no worker = QUEUED forever. MOCK rounds finish <250ms; to verify phase UI inject a RUNNING `ai_jobs`+`job_runs` row with `progress_phase='context'|'model'|'proposal'` and open `/assistant?job=<id>`.
- **pgrep footgun**: `pgrep -f "manage[.]py" | xargs kill` can match your own exec shell's cmdline — `ps aux | grep -E 'manage[.]py (runserver|runjobs)'` and kill explicit PIDs; `cd` does not carry to a second `setsid` in one call (use absolute manage.py path).
- **Headless capture reuse**: `frontend/scripts/ux-capture/auth.ts` `loginAs(page, email, {totp, orgName})` does real magic-link+TOTP login; standalone scripts must live under `frontend/scripts/` (module resolution is file-relative — /tmp scripts can't import @playwright/test); `context.storageState()` once → loop `{viewport, colorScheme, url}`; theme = colorScheme, not localStorage.
- **OWNER TOTP bootstrap**: fixture creates no MFA — `INSERT INTO auth.mfa_factors (id,user_id,factor_type,status,secret,created_at,updated_at) VALUES (uuid,uid,'totp','verified',<base32>,now(),now())` (created_at/updated_at NOT NULL) + store same secret in `.fixture-state.json` `totp["<email>"]`.
- **aal2 token via REST (curl aal2-gated APIs like /ai/ops-contract/)**: `POST /auth/v1/token?grant_type=password` (apikey: anon) → aal1 token; `GET /auth/v1/user` → `factors[0].id`; `POST /auth/v1/factors/<id>/challenge` → challenge_id; TOTP via hmac(base32decode(secret), time//30, sha1); `POST /auth/v1/factors/<id>/verify {challenge_id, code}` → aal2 token; `curl -H "Authorization: Bearer <aal2>"`.
- **Probes vs consumption**: `/ai/provider/check/` writes `kind='probe'` rows (visible in activity) but month usage counts `kind='call'` only — probes never raise "Con error" or consume budget.

## P25 additions (brand/mail E2E)

- **Stale code trap generalizes**: `runserver --noreload` serves the code from
  launch time — after ANY backend commit kill and relaunch with env sourced,
  or fixes appear absent (verified: a portal payload change looked missing
  until restart).
- **Zero-factor OWNER TOTP enroll via UI** (no SQL): if admin API shows
  `factors: []`, the MFA sheet offers "Configurar autenticador" → manual
  secret at `data-testid="totp-secret"` → 6-digit code via stdlib TOTP
  (`base64.b32decode(secret)` + hmac-sha1 + `struct.pack('>Q', t//30)`) →
  "Verificar" lands on dashboard as Propietario.
- **Fixture accounts** (`.fixture-state.json`): `demo-estimator@…` (ESTIMATOR,
  no MFA, best default), `demo-manager@…` (WORKSHOP_MANAGER), `demo-owner@…`
  (aal2), `demo-multi@…` (org selector → pick "Ventanas del Sur SpA" via
  `.org-option`).
- **browser_console async**: promise results aren't serialized — write to
  `window.__x` in `.then()` and read `window.__x` on the next call.
- **Endpoint checks without cookie tricks**: in-page
  `fetch('/api/v1/…', {headers:{'X-Organization-ID': orgId}})` exercises the
  same auth path as the app; assert status/content-type directly (verified
  `branding/logo/` → 200 `image/png`).
- **OfflineOverlay**: `window.dispatchEvent(new Event('offline'))` hits the
  real component; dispatch `'online'` to clear.
- **iframe mail previews**: `/dev/correos` (DEV-only; 404 unless DEBUG or
  MAIL_DEV_PREVIEWS=1) renders `iframe.dev-mail__frame` — assert
  `frame.srcdoc` contains `data:image/png;base64` + org hex instead of
  shooting every template.
- **Mobile viewport without devtools**: `wmctrl -r :ACTIVE: -b
  remove,maximized_vert,maximized_horz && wmctrl -r :ACTIVE: -e
  0,300,10,430,740`.
- **Dark login capture**: `dekopen.theme` in localStorage only applies inside
  the shell — to shoot a dark login, toggle dark while logged in, sign out,
  then `/login` renders dark.
## Settings / org-branding surface (P09)

- `/settings/general` is behind ReadyGuard only — NO route-level role gate.
  The left-rail "Administración" nav item is gated
  `OWNER || WORKSHOP_MANAGER` (AppShell `navigationAllowed`), but the
  org-branding card (incl. the "Documento comercial" fieldset:
  `doc_paper_size` select + 5 `doc_terms` textareas) renders for
  `OWNER || ESTIMATOR` (`canWriteDocs`). An ESTIMATOR fixture user can view
  AND save org doc settings — navigate to `/settings/general` directly; the
  nav link simply isn't shown.
- Org-branding/doc-settings UI testing does NOT need an OWNER account
  (avoids the aal2/MFA enrollment wall). ESTIMATOR suffices: RLS policy
  `tenancy_organizations_branding_update` allows `OWNER`/`ESTIMATOR` and the
  column grant covers `doc_paper_size`/`doc_terms`.
- Fixture org insert needs only `{id, name, tax_id}` — every other
  `tenancy_organizations` column (country, currency, subscription_tier,
  doc_paper_size='LETTER', doc_terms='{}') has a default.
- Save path: one shared "Guardar marca" submit writes brand fields + doc
  fields together; empty/whitespace `doc_terms` values are stripped
  client-side before POST and land as absent keys (verify with
  `SELECT doc_paper_size, doc_terms FROM tenancy_organizations`).

## P03 shell/stack learnings (2026-10-06)

- `supabase status -o env` emits `KEY="VALUE"` shell lines, NOT JSON — extract with `grep -o 'SERVICE_ROLE_KEY="[^"]*"' | cut -d'"' -f2`. A JSON-shaped grep returns empty silently → `invalid_token` 401 everywhere and magic links never reaching Mailpit.
- Fixture `scripts/dev_fixture.py` orgs: "Ventanas del Sur SpA" (6 miembros) + "Cristales del Norte Ltda." (2, casi sin datos — `demo-multi` es ESTIMATOR en ambas y es el único camino fiable al estado vacío «Todo al día»). Cuentas `demo-{owner,estimator,manager,operator,installer,multi}@fixture.dekopen.local`; estado en `.fixture-state.json` (incluye la semilla TOTP del OWNER aal2 — TOTP se deriva con hmac-sha1 sobre el base32, counter=time//30, sin pyotp).
- Códigos del fixture que existen: `P-000001..13`, `OC-000001..4`, `RT-000001..72`, OTs de taller solo `OT-P-000007/8/9-REV-A-*` (no existe `OT-P-000005*`); cliente «Inmobiliaria Los Alerces Ltda.».
- `GET /api/v1/analytics/today/` es la cola «Hoy» (no `/api/v1/today/`). Destinos de búsqueda Ctrl K: proyectos→`/projects/{id}`, clientes→`/clients`, OC→`/purchasing`, RT→`/inventory`, OT→`/production`.
- Superficie IA (orb, AskDekopen, badge «Modo de prueba», /assistant, /jobs) monta SOLO para OWNER/ESTIMATOR/WORKSHOP_MANAGER — OPERATOR/INSTALLER deben emitir 0 requests `/api/v1/ai/*` (verificar con `performance.getEntriesByType('resource')` + log de Django).
- StrictMode firma de bug: página monta directo en estado de error con los GETs 200 — el doble-montaje aborta el primer fetch y `.catch→setFailed` gana la carrera contra el segundo fetch. Todo `useRef(new AbortController())` reemplazado en effect + precedencia `failed` sobre datos es sospechoso también en remontajes por cambio de org.
- `?` no se puede teclear vía xdotool (`key "?"`/`type "?"` llegan como `\u0000`) — usar `key shift+slash`. `wmctrl -r :ACTIVE: -e 0,x,y,w,h` redimensiona la ventana. Para 390px usar DevTools device toolbar con preset iPhone y verificar `document.documentElement.clientWidth` (innerWidth miente). Overflow horizontal: `scrollWidth` vs `clientWidth` — `scrollLeft` se clampa a 0 cuando el overflow viene de elementos fijos.
- Node real del box: `~/.nvm/versions/node/v24.19.0/bin` (la referencia vieja a `~/node22` puede no existir — comprobar).

## AskDekopen dock + assistant/jobs surface (P17 learnings)

- The AskDekopen dock (section aria-label="Preguntar a DEKOPEN") is a 400px
  right drawer: at viewport ≥1024px the workspace reserves its width (content
  pushes left); below that it overlays the page — close it via the × before
  clicking right-edge controls; it reopens via the topbar "IA"/orb button and
  its open state persists across navigations (sessionStorage `dk:askdock`).
- Agent runs settle in <1s under the MOCK provider — screenshotting a live
  thinking/working Orb mid-run is luck. Capture the DOM busy line
  ("N% · En cola/Ejecutando… · Cancelar") instead; the 15fps recording still
  shows ring animation frames.
- Sending a dock prompt with chips: suggestion chips sit at the bottom of the
  thread — coordinates drift as turns stream in; re-screenshot before clicking.
- OpsProposalCard: "Aplicar N operaciones" is disabled with title
  "El producto cambió — genera de nuevo para aplicar." whenever the live product
  sig differs from the proposal's (stale guard). After Ctrl+Z restores the
  product, older pending cards become apply-able again (sig matches).
- Dock cards DO restore applied/declined outcomes on remount: `threadFromJob`
  seeds each turn's outcome sets from `job.outcomes` (server dedupes per
  (turn, step, action)); the workspace /assistant?job=<id> reads the same
  source — both surfaces agree after a reload/reopen.
- /jobs: state filter sets ?state=QUEUED etc. via a native <select> — click the
  element then Down/Return; it must be focused (dock must not cover it).
  Actor column is resolved via memberships→auth.users; object label is
  "Pos. NN <location> · P-######" built in SQL from position_index.
- Audit deep-link: dock card "Ver auditoría" and jobs "Abrir en el asistente"
  both land on /assistant?job=<ai_job_id> (the job_runs.payload->>'ai_job_id'
  provides the link). The "N créditos · N tokens" header counts that job's
  operation_key plus its :rN/:gN round suffixes — a separate send is a
  separate ai_jobs row with its own key, so per-job spend is correct
  (verified: header == the job's own invocations exactly).
- Role gate recipe: login as a fixture OPERATOR/INSTALLER (magic link via
  Mailpit) — the SPA restores the last URL, so landing directly on /jobs after
  login exercises the denied view: nav collapses to role-allowed entries, no
  orb/badge/dock mount, denied text renders instantly (query disabled).
- Magic-link: the /verify?token=...&redirect_to= URL from Mailpit can be pasted
  straight into the address bar — no need to click it inside an email client.

## P07 pricing-workspace learnings

- **Mail delivery requires SMTP env on the runjobs worker**: default `MAIL_PROVIDER=sandbox` only writes `mail_messages` rows — nothing reaches Mailpit. To see real mail (pricing_decision, quote emails) restart the worker with `MAIL_PROVIDER=smtp MAIL_SMTP_HOST=127.0.0.1 MAIL_SMTP_PORT=25325 MAIL_SMTP_TLS=0 MAIL_FROM=noreply@dekopen.cl` (Mailpit SMTP is :25325, UI :25324). The runserver process may keep `sandbox`; the Ajustes → "Correo transaccional" card then shows Sandbox while worker-delivered mail lands in Mailpit — expected, not a bug.
- **Verify mail end-to-end**: `mail_messages` (status/provider/error/to_email/template) + `job_runs` (columns: type,state,error,attempt — NOT kind/status). `pricing_decision` mails go to `requested_by_email` with subject `[DEKOPEN] Precios {aprobada|rechazada|retirada} — {project}`.
- **Pricing admin tabs run under `SET LOCAL ROLE pricing_backend`**: any new table touched by `/api/v1/pricing/admin/*` needs a GRANT+RLS policy for `pricing_backend` or the endpoint 409s with "Pricing transaction rejected (ProgrammingError)" and the tab shows "No se pudieron cargar los datos". Reproduce in psql: `SET ROLE pricing_backend; SELECT 1 FROM public.<table> LIMIT 1;`. Observed missing on `glass_purchase_mappings`, `panel_purchase_authorities`, `hardware_purchase_mappings`, `fitting_purchase_mappings` (coverage endpoint).
- **Zero-factor OWNER TOTP enroll works via UI**: MfaPage "Configurar autenticador" → `data-testid="totp-secret"` → stdlib TOTP (base32 + hmac-sha1 + struct time//30) → input `id="totp-code"` → "Verificar". After enroll, "Verificación en dos pasos: Activa" shows in Ajustes.
- **Pricing workspace routes**: project ops at `/projects/:id/pricing`; owner admin at `/pricing/cost-lists` (tabs: listas/insumos/cobertura/reglas/tarifas/matriz/fx/historial); margin band fields live in "Reglas comerciales" (margin_min_pct/margin_max_pct as percents, stored as fractions). "Editar registro" leaves % fields blank — retype all before "Guardar cambio auditado".
- **Owner pricing form has an extra mode**: `TARGET_GROSS_MARGIN_PROJECT` ("Margen objetivo del proyecto") is owner-only in the pricing_mode select.
- **Cascade "sin desglose exacto" signature**: `Operación anterior a la cascada — sin desglose exacto.` means `_cascade_payload` returned None — usually engine `_position_cascade` raising `inconsistent_pricing_result` when materials+waste+labour != stored unit_cost (4dp-quantized snapshots vs recompute drift). Check stored `input_snapshot.unit_cost` vs recomputed cost_net.

## Pack de corte (P13) — receta de verificación

- Ruta UI: `/production?order=<order_uuid>` → detalle de OT → tab **Corte** →
  «Pack de corte (PDF)» (requiere `payload_json.optimization` no invalidado; el
  botón se deshabilita con tooltip «plan invalidado» tras re-optimizar).
  Endpoint: `GET /api/v1/production/orders/<id>/cut-pack/` (200 application/pdf;
  errores `cut_pack_requires_optimization`, `plan_invalidated`). ESTIMATOR
  alcanza para descargarlo.
- `workshop_label_format` (migración 20270204000000): select en Ajustes ›
  Documentos — GRID=«Grilla en hoja», THERMAL_100X50=«Rollo térmico 100×50 mm».
  Se guarda con «Guardar marca» del formulario de branding y aterriza en
  `tenancy_organizations.workshop_label_format` (round-trip al recargar).
- La prueba dura de que el formato conduce el render: rasterizar/extraer el PDF
  descargado con pymupdf (`fitz`, en `.venv`). GRID → etiquetas en página del
  papel documental (Carta vertical 612×792, h2 «Etiquetas de pieza — en
  secuencia de corte», muchas etiquetas por página + RETAZO al final).
  THERMAL_100X50 → una página de 100×50 mm (283×142 pt) por etiqueta, sin
  cajetín; el bloque «Identidad» queda en página full-size al final.
- Secciones esperadas del PDF (apaisado, en español): stats de cabecera,
  «Lista de corte» con bloques por barra + badges «BARRA NUEVA»/«retazo RT-…»,
  línea de cierre Decimal exacto por barra, «Retazo N mm → stock de retazos
  (folio RT- al cerrar el corte)», «Cortes agrupados — sierra manual»,
  «Refuerzos y junquillos», «Plan de láminas»/«Vidrios», «Piezas no ubicadas»
  (motivo → acción), etiquetas con QR y «→ siguiente estación», línea
  `OT-… · plan <fp8>`, firma «Identidad».
- Las OT de `dev_fixture.py` ya vienen optimizadas: la de vitrina (10
  posiciones) ejercita cada sección, incl. «Piezas no ubicadas» («Sin formato
  de lámina declarado en el catálogo → Catálogo › Vidrios › Formatos»).
- Gotcha: el pack se renderiza al descargar, así que cambiar el setting de la
  org y re-descargar la MISMA OT es la prueba A/B más limpia (la segunda
  descarga aterriza como `… (1).pdf` en ~/Downloads).

## P11 cobranza — env vars y patrones nuevos
- `SII_CAF_KEK=<64-hex>` — REQUIRED for any CAF upload or DTE stamp; missing →
  503 «SII_CAF_KEK no está configurado». Generate with
  `python -c "import secrets;print(secrets.token_hex(32))"` and relaunch
  runserver + runjobs.
- `FLOW_WS_MOCK=1` exposes `/api/v1/billing/flow-sim/<token>/` (public).
- `SII_WS_ENVIO_MOCK=1` + `SII_WS_ENVIO_MOCK_VERDICT=OBSERVED` makes «Enviar al
  SII» land «SII · Aceptado con reparos».
- `AI_GATEWAY_MOCK_ENABLED=1` + `UPDATE ai_routes SET provider='MOCK' WHERE
  capability='collection_reminder'` when MiMo is 429 — env alone is not enough.

Direct-SQL writes (link expiry, client_email, invoice payload fixes):

- `projects` UPDATE needs service role + claims GUC or the
  guard/RLS silently returns 0 rows:
  `BEGIN; SET LOCAL ROLE pricing_backend;
   SET LOCAL request.jwt.claims='{"sub":"<uid>","role":"authenticated","aal":"aal2"}';
   UPDATE ...; COMMIT;`
- Plain psql as postgres works for reads and non-guarded tables
  (`project_payment_links.expires_at`, `project_invoices.payload_json`,
  `ai_routes`).

Fixture data gaps found (P11): all clients lack `client_rut`/`client_giro`/
`client_comuna`/`client_address` → DTE stamping 422s «RUT de receptor
válido» / «giro, comuna y dirección». `projects.client_email` is empty →
«Enviar recordatorio» 422s `reminder_no_client_email` (no clients.email
fallback). Fix via guarded UPDATEs above or patch the sealed
`project_invoices.payload_json->project` with `jsonb_set` (UTF-8 chars
outside ISO-8859-1 — e.g. ’ — are rejected at stamp time).

Devin Secrets needed: none (all keys come from `supabase status` / .fixture-state.json).
