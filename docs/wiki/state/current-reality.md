---
type: state
status: active
updated: 2026-10-05
volatility: high
verified_ref: 388e79bdc0ff111a9c2e76a445260bd9f18b92c3
sources:
  - repository main
  - P00 evidence-harness PR https://github.com/KaraAliOsman/dekopen/pull/1
  - P01 design-system PR https://github.com/KaraAliOsman/dekopen/pull/4
  - D01 systems/profiles PR https://github.com/KaraAliOsman/dekopen/pull/6
  - D02 glass PR https://github.com/KaraAliOsman/dekopen/pull/10
  - D04 hardware PR https://github.com/KaraAliOsman/dekopen/pull/8
  - integracion/v1 merge 747c528b67d234d697624929ccbcc7098261ed54
  - open PR metadata observed 2026-09-27/28
  - AGENTS.md
  - docs/PRODUCT.md
  - docs/ENGINEERING.md
---

# Current reality

**Warning:** this is a volatile navigation page. Re-check the repository before relying on it for implementation decisions.

## Verified repository baseline

At the verification ref (`747c528b67d234d697624929ccbcc7098261ed54` on `integracion/v1`), the repository identifies DEKOPEN as:

- a pure deterministic engine under `engine/`;
- Django modular monolith under `backend/`;
- React + TypeScript + Vite under `frontend/`;
- Supabase/Postgres migrations and RLS under `supabase/`;
- product/engineering specifications under `docs/`.

Hard invariants documented by the repo include:

- Decimal for millimetres/money;
- no LLM/free-text numeric engineering truth;
- 0.00 mm deterministic golden behavior;
- tenant `org_id` + RLS;
- immutable issued artifacts/history;
- explicit human action for externally consequential events.

## Product direction already present in the repo

`docs/PRODUCT.md` already encodes:

- unified product-centered workspace;
- compositional assemblies/modules/couplings;
- bow/bay as templates over composition rather than enum branches;
- direct manipulation + typed operations + undo/redo;
- AI using the same typed operations as UI;
- workshop-language validation;
- Oknosoft/WindowBuilder as a domain reference.

## D01 state

Merged into `integracion/v1` as squash `bc7ed09ed2df41df838f19ffdd3346326e646c4f` (dekopen PR #6):

- `profile_systems.system_family` (CASEMENT / SLIDING / LIFT_SLIDE / DOOR / FACADE_FIXED) separates fabrication families; `allowed_openings` maps each family to its typologies and the engine raises `IncompatibleTypologyError` when a design's typology does not belong to the system's family.
- Profile roles now cover sliding/door hardware (SLIDING_SASH, INTERLOCK, RAIL, DOOR_SASH, FRAME_EXTENSION, SILL, COVER_TRIM, SKIRT); cut rules and reinforcement (incl. `screws_per_meter` → TORNILLO-4X16 BOM fittings) are data, not code.
- `system_typology_limits` declares dimensional limits per system × typology with a `data_provenance` column (SEED_SYNTHETIC / MANUAL / IMPORT / LEGACY_UNVERIFIED; imported rows carry `review_pending`); a missing row means unchecked, never rejected.
- Catalog ingestion has two converging paths — manual XLSX/CSV template (`backend/ingest/spreadsheet.py`) and AI candidates — both landing on the same human review before publication.
- The global catalog grew: DEMO_70 (PVC abatir), ALU_CORREDERA_70 (aluminio corredera), DEMO_CORREDERA_60 (PVC corredera, split out of DEMO_60's sliding rows by migration `20261229000002`); all carry `is_demo` and the fourteen inspector rule configs + `chamber_clearance_mm` required by the documentary freeze.

## D02 state

Merged into `integracion/v1` as squash `b623a067fe3db3872138c036e24c39a631ed947c` (dekopen PR #10):

- `GlassComposition` is a structured exterior→interior layer model (láminas, PVB `+`, cámaras con gas) with round-trip notation (`parse_glass_notation`/`format_glass_notation`); `glass_products` stores the parsed stack as JSONB and `project_positions.glass_composition` persists the resolved map with `glass_review_pending` for UNKNOWN specs.
- Thickness authority: the parsed `glass_composition` always owns the package thickness when it resolves (`thickness_source="COMPOSITION"`); a declared `glass_thickness_mm` that disagrees is recorded as `thickness_declared_mm` and flagged with a `GLASS-THICKNESS-MISMATCH` warning — drift worth review, never a silent override. Engine derives total/net thickness, weight (2.50 kg/m²·mm panes + 1.07 PVB), bead selection, cut size and minimum billable area.
- NCh 135-family safety rules are org data (`glass_safety_rules`/`glass_type_limits`): WARNING advises, MANDATORY blocks; seed rules are `SEED_SYNTHETIC` + `review_pending` and the official text arrives via the D01 ingest sheets "Seguridad vidrio"/"Límites vidrio".
- Glazier cutting order: `GET /api/v1/production/orders/{id}/glass-order/?output=pdf|csv` (integer mm, `P{pos}-U{u}-I{i}` labels, QR, `?orders=` batch merge of same-version OTs); `review_pending` pieces list separately.
- Canvas glass selector: basic mode lists compatible product cards; advanced mode composes layers with live validation and a to-scale section; safety warnings attach to the bay with a one-click compatible alternative.

## D04 state

Merged into `integracion/v1` as squash `388e79bdc0ff111a9c2e76a445260bd9f18b92c3` (dekopen PR #8):

- Hardware kits are now **classes** per (system × opening): `hardware_kits.class_label` plus declared restrictions `max_aspect_ratio` and `min_stay_height_mm`; `contents` components carry `qty_rule` (PER_WIDTH/PER_HEIGHT with min/max), `cut_rule` (axis −mm), `weight_kg`, `cost_clp` and a declared `machining[]` list — all catalog data, importable with the D01 template.
- New catalog tables: `hardware_families` (opening-scoped handle-height rule CENTERED/FIXED_FROM_BASE/RANGE + sellable `handle_model_options`/`handle_color_options`) and `hardware_options` (sellable per-position options with `price_delta_clp` and component BOM).
- The engine resolves the tightest compatible class (`_class_tightness` — identical envelopes are `AmbiguousHardwareKit`, never a coin flip), expands quantities and cut lengths, sums weight/cost, and names restriction + real value on failure, suggesting the next heavier class with its CLP delta or bay-split with the heaviest class.
- BOM `hardware_items` seal the leaf's sellable choices (class label, handle model/colour names, option skus/names, resolved handle height, sums, `price_deltas`, machining), so issued documents never re-query the catalog; `hardware_picking` + `hardware_machining` fields are emitted in the work-order payload for P14 (no dedicated UI yet — machining without coordinates stays `DECLARED_NOT_EMITTED`).
- Editor inspector gains a full "Herrajes" section: resolved class summary, "¿Por qué este kit?", kit-class override, handle model/colour/height with out-of-range warning, sellable options, and the component table under "Avanzado"; the client document renders only the sellable side.

## P00 foundation state

P00 is complete across dekopen PR #1 (squash 747c528b; a partial first landing on framedex PR #114 carried over): it adds the v1 integration foundation:

- `integracion/v1` exists as the queue integration branch.
- `docs/design/CONSTITUCION.md` is the mandatory design constitution copied from the queue.
- `docs/decisions/valores-por-defecto.md` records constitution defaults for later implementation.
- `docs/operations/ACTIVACION.md` indexes deferred external integrations without secret values.
- `frontend/scripts/ux-capture/` provides a Playwright capture harness with text/presentation detectors and unit coverage.
- The production route table hides `/projects/demo/positions/g1/edit` behind the same dev-only mechanism as `/benchmark`.
- `scripts/dev_fixture.py` now seeds more realistic DEMO fixture identity, clients and project volume while preserving `DEMO_60` as synthetic reference data.

Verification: dekopen PR #1 passed all required GitHub checks (Lint & Typecheck, Test Suite, Frontend Build, Database Gate) and was verified end-to-end on the live local stack — the earlier caveat (login-only smoke baseline, portal tokens unavailable) is resolved: the committed baseline now covers 270 authenticated captures across 38 routes and the fixture carries all 5 portal token states.

## IA1 AI evaluation harness and baseline diagnosis

The IA1 encargo added a result-based AI evaluation harness under `backend/ai_gateway/evals/` (runnable via `make test-ai-evals` or `python scripts/ai_evals.py`): 26 YAML cases drive the real UI routes (`design_assist.assist`, `agent._act`, `assist.ask`) in-process with only I/O edges patched, apply proposed ops through the real frontend `applyDesignOps` reducer bundled via esbuild into a Node sandbox, and score the resulting product structure (mm measures, openings, glass SKUs) — never the reply text. A deterministic 10-category failure taxonomy classifies each miss. Committed baselines live in `docs/ai/evals/` (`2026-10-05-mock.json`, `2026-10-05-mimo.json`) with the diagnosis in `docs/ai/evals/README.md`; CI runs the MOCK suite in the non-blocking `AI Evals (MOCK, non-blocking)` job.

Baseline findings (2026-10-05, ordered by impact — verified file:line evidence in the README):

1. The configured real provider (MIMO) answers HTTP 429 `ai_provider_quota` on every call — all AI surfaces are down in production today.
2. `design_assist._summary` requires a flat `product["modules"]` list (`design_assist.py:103-115`), but agent batch ops load the persisted `parametric_tree` (`agent.py:761`) — every stored position is rejected `unsupported_product`: project-level batch ops are structurally broken.
3. The ops vocabulary covers only adjustments — no bay-split, position-create/duplicate or hardware ops; worse, `SLIDING_2L` is a valid `OPENINGS` value so a sliding conversion validates and applies on an incompatible system.
4. Context projections lack sash weight, engine validation blockers, per-position prices, version diffs and cut-plan bars — honest answers reduce to "sin dato".
5. `_declared_values` accepts only literal numbers — relative-measure instructions ("20 cm más ancha") are impossible, while absurd literal values pass range checks.

## P01 design-system state

P01 lands the design constitution as code (branch `devin/P01-sistema-diseno`, PR head `9e9941dd1435bfc14c32d03a4cf7ecf2d410207b`):

- `frontend/src/styles/tokens.css` is the single token file: ramps, light/dark roles, canvas roles, `--theme-*` compat aliases, IBM Plex Sans/Mono self-hosted latin subsets, type/space/radius/elevation/z/motion scales and `[data-density]` (office/workshop/document). `tokens.test.ts` fails on undefined `var()`, unused-token drift vs `tokens.unused.txt`, and text/background pairs under AA in both themes.
- `frontend/src/ui/` holds the primitive kit (actions, forms, structure, data, domain state, overlays, states, signature — `SheetSurface`, `DimLoader`, `TraceButton`, `OpeningGlyph` per §3.6) plus `ui/format.tsx` domain formatters (`<Money>`, `<Dims>`, `<Length>`, `<Area>`, `<Weight>`, `<Uvalue>`, `<Qty>`, `<Percent>`, `<EntityCode>`, `<Timestamp>`, `<DateOnly>`).
- `frontend/src/i18n/domainLabels.ts` labels every visible orval enum in Spanish with an exhaustiveness test; `StatusChip` resolves label+tone+icon from the enum.
- Spanish validation: `installSpanishValidation()` in `frontend/src/validation.ts` (loaded by `main.tsx`) covers all 36 `<form>`s with `noValidate` + es-CL messages and RUT módulo-11; `data-pattern`/`data-error-*` attributes carry per-field overrides.
- `scripts/check_guards.py` gains §10 ratchet guards (radius >4px, off-scale shadows, gradients, hex/rgb inline, font <11px, motion >280ms, `toFixed`, weight 700, literal z, raw status, emoji, exclamations) with committed count baseline `scripts/guards-baseline.txt` (`--write-baseline` regenerates; `frontend/src/dev/` is exempt by design).
- `frontend/scripts/ux-capture/` detectors extended: `primary-multi` per `data-region`, computed radius >4px (pills legal), off-scale shadows, gradients/backdrop-blur, real WCAG contrast <AA, emoji, exclamations, English text, touch <44px in workshop density, bare interactives — all with unit tests in `detectors.test.ts`.
- `/dev/ui` + `/dev/ui/mal` are DEV-only routes (`DEV_ONLY_ROUTE_PATHS`): the first is the full primitive/formatter/glyph muestrario across both themes × 3 densities; the second reproduces the board-06 Bien/Mal contrast.
- `index.css`, `ui.css` and `canvas.css` are split into contiguous-section partials (`styles/*`, `ui/styles/*`, `canvas-*.css`) without touching cascade order; the ~30% CSS reduction target is honestly deferred to P03+ because several chip/status rules intentionally compose across the two legacy files.
- `.github/pull_request_template.md` adds the Spanish PR template used by this encargo.

Verification: `make lint|typecheck|test|build` green locally (with `PY=.venv/bin/python`); `p01-antes`/`p01-despues` capture pairs under `docs/redesign/captures/`; editor verified `/dev/ui` live in both themes. Jammy VM needed the documented self-built `libharfbuzz-subset.so.0` (harfbuzz 2.7.4, subset only) before the 22 WeasyPrint backend tests passed.

## Recent branch/PR caution

The repository has accumulated many historical branches and stacked agent changes.

Do not assume “latest PR number = complete product”.

As of the latest observed metadata around 2026-09-27/28, PRs including #107 and #109 were open; their relevance/current CI must be checked again before use.

Historical audit notes reported periods where:

- commercial-workspace work existed on a large advanced branch;
- OpenAPI/client drift and catalog authorization defects blocked CI;
- documentation/testing PRs were not substitutes for missing product stabilization.

Treat these as leads for inspection, not timeless truth.

## Current-state procedure

Before changing a capability:

1. locate current implementation on the target ref;
2. inspect related migrations and generated API types;
3. inspect recent PRs/branches that may supersede main;
4. run focused tests;
5. use the real UI if behavior/UX is involved;
6. then update this page if a durable current-state fact materially changed.

A fuller capability-by-capability reality map should be added only after a fresh systematic repository + running-product audit.
