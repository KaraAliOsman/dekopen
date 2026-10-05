# DEKOPEN Wiki Log

Append-only chronology. Keep newest entries at the bottom.

## [2026-09-28] bootstrap | LLM Wiki instantiated

- Read Andrej Karpathy's canonical `llm-wiki.md` idea file.
- Adapted the pattern to DEKOPEN's stronger requirement that current implementation claims must be revalidated against the repository.
- Seeded schema, index, product direction, owner decisions, current-state page, known-risk page, competitor map and source pages.
- Established separation between current repo fact, owner intent, historical context and external research.
- No attempt was made to turn the wiki into an alternative source of engineering numeric truth.

## [2026-10-05] P00 | foundation branch, constitution and visual evidence harness

- Created the v1 foundation changes for `integracion/v1`: design constitution in-repo, defaults/activation records, queue state, route hygiene and `ux:capture`.
- Added a realistic DEMO fixture direction for Ventanas del Sur SpA while keeping `DEMO_60` explicitly synthetic and non-certified.
- Verified local focused tests, engine/backend/frontend unit suites, frontend typecheck and build. Local generated-API drift check was blocked by Windows application control on the `rpds` DLL.
- Captured a smoke baseline for `/login`; full-route capture remains a follow-up once every portal/token fixture state exists.

## [2026-10-05] P00 | merge status reconciled

- Confirmed PR #114 is merged into `integracion/v1` at `a096f85b2e56e21eda024c1ec92a456ed9d30b03`.
- Confirmed the four required GitHub checks passed: Lint & Typecheck, Test Suite, Frontend Build and Database Gate.
- Updated the queue state and current-reality verification ref so the next session can advance from P00.


## [2026-10-05] P00 | evidence harness completed end-to-end

- Replaced the login-only smoke baseline with the full authenticated harness: per-role Mailpit magic-link logins, org selection and TOTP aal2 for the OWNER, declarative route table over all App.tsx routes (41 capture jobs), and report.json + index.html output.
- Baseline `docs/redesign/captures/baseline-2026-10-05/` now covers 270 captures (38 routes with findings, 2276 findings) with committed 1440×900 light shots.
- Realistic fixture: two tenant orgs, 12 lifecycle projects, 5 portal token states and `.fixture-state.json` for route interpolation; idempotency proven by `frontend/tests/e2e/fixture.spec.ts` under `make test-db`.
- Fixed a real dead-end found by the harness: `/select-organization` did not redirect `mfa_required` sessions to `/auth/mfa`, stranding multi-org OWNER logins.
- Local jammy VM needed a self-built `libharfbuzz-subset.so.0` (harfbuzz 2.7.4) for WeasyPrint PDF tests; CI already installs `libharfbuzz-subset0`.


## [2026-10-05] IA1 | AI evaluation harness + baseline diagnosis

- Built `backend/ai_gateway/evals/`: 26 result-based cases (E01-E13 editor, J01-J08 project, F01-F03 production/purchasing, G01-G02 general) run through the real UI routes in-process (`design_assist.assist`, `agent._act`, `assist.ask`) with only I/O edges patched; proposed ops are applied via the real frontend `applyDesignOps` bundled with esbuild into a Node sandbox; scoring compares the resulting product structure (mm, openings, glass SKUs) — not text.
- Deterministic 10-category failure taxonomy per the encargo; prompt-echo is stripped from the text corpus so a quoted question is not a clarification.
- Committed baselines `docs/ai/evals/2026-10-05-mock.json` (0/26 — MOCK is the echo floor) and `2026-10-05-mimo.json` (0/26 — configured provider answers HTTP 429 `ai_provider_quota` on every call; diagnosed quota exhaustion, not transient rate-limit).
- Five root causes ordered by impact in `docs/ai/evals/README.md`: provider quota down; `_summary` flat-modules gate rejects every persisted `parametric_tree` (`unsupported_product` — batch ops structurally dead); ops vocabulary lacks bay-split/create-duplicate/hardware ops while `SLIDING_2L` validates on incompatible systems; context projections lack weight/validation/price/diff/bars data; `_declared_values` forbids arithmetic so relative-measure instructions are impossible.
- Non-blocking hook: `make test-ai-evals` + CI job `AI Evals (MOCK, non-blocking)` uploading `ci-mock.json` (gitignored).
- Harness does not fix the IA — IA2/IA3 correct against this same vara.


## [2026-10-05] P01 | sistema de diseño v2 — Constitución como código

- Implemented `docs/design/CONSTITUCION.md` as enforceable code: token architecture with light/dark/canvas/density roles, IBM Plex self-hosted fonts, primitive kit in `frontend/src/ui/` (incl. signature components: SheetSurface, DimLoader, TraceButton, OpeningGlyph), domain formatters, exhaustive `domainLabels` vs orval enums, and global Spanish form validation with RUT módulo-11.
- Split the three monolithic stylesheets into contiguous-section partials preserving cascade order; documented the ~30% reduction as deferred — duplicated chip/status rules still compose across the legacy split.
- Added §10 static guards in `scripts/check_guards.py` with committed ratchet baseline, and live slop detectors in `ux:capture` (multi-primary per region, radius/shadow/gradient/blur, WCAG contrast, emoji/exclamations, English, workshop touch targets, bare interactives) with unit tests.
- Built DEV-only `/dev/ui` muestrario (both themes × 3 densities) and `/dev/ui/mal` reproducing the board-06 forbidden-pattern contrast; fixed chips showing raw enum text and the prohibited «Algo salió mal» title found during the editorial pass.
- Replaced prohibited voice strings in `es-CL.ts`; committed PR template at `.github/pull_request_template.md`; before/after captures under `docs/redesign/captures/p01-antes|p01-despues/`.


## [2026-10-05] D01 | sistemas y perfiles de verdad

- `system_family` (CASEMENT / SLIDING / SPECIALIZED) separa familias de fabricación; `allowed_openings` deriva las tipologías habilitadas y el motor rechaza con `IncompatibleTypologyError` una tipología que no pertenece a la familia (corredera en abatir, p.ej.).
- Roles de perfil completos (SLIDING_SASH, INTERLOCK, RAIL, DOOR_SASH, FRAME_EXTENSION, SILL, COVER_TRIM, SKIRT) con reglas de corte y refuerzo como datos; `screws_per_meter` del acero genera fittings `REINFORCEMENT_SCREW` (TORNILLO-4X16) agregados en la BOM y costeados por `fitting_purchase_mappings`.
- `typology_limits` por sistema × tipología con fuente (SEED_SYNTHETIC / MANUAL / AI_GENERATED); fila ausente = sin verificación, nunca rechazo implícito.
- Ingesta dual: plantilla XLSX/CSV manual (`backend/ingest/spreadsheet.py`, errores por fila en español) y candidatos IA convergen en la misma revisión humana; baja confianza → UNKNOWN y nada se publica sin confirmar.
- Catálogo DEMO enriquecido y marcado `is_demo`: DEMO_70 (PVC abatir), ALU_CORREDERA_70 (aluminio corredera) y DEMO_CORREDERA_60 (PVC corredera separada de DEMO_60 por la migración `20261229000002`, con matriz de juntas 24 mm JQ-CORR-10); los tres llevan `chamber_clearance_mm` y las 14 `inspector_rule_configs` que exige el freeze documental.
- Verificado: `make lint`, `typecheck`, `test` y `build` verdes; `make test-db` (pgTAP 940, integración RLS, e2e) verde tras contar los nuevos catálogos (59 artículos, 18 juntas, 84 configs inspector).
