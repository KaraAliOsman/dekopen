---
type: state
status: active
updated: 2026-10-06
volatility: high
verified_ref: 2c04dcd64afb7cea16effb899ecaf33fe9e7aa67
sources:
  - repository main
  - P00 evidence-harness PR https://github.com/KaraAliOsman/dekopen/pull/1
  - P01 design-system PR https://github.com/KaraAliOsman/dekopen/pull/4
  - D01 systems/profiles PR https://github.com/KaraAliOsman/dekopen/pull/6
  - D02 glass PR https://github.com/KaraAliOsman/dekopen/pull/10
  - D04 hardware PR https://github.com/KaraAliOsman/dekopen/pull/8
  - D03 openings/typologies PR https://github.com/KaraAliOsman/dekopen/pull/9
  - D07 vano/fabricación PR https://github.com/KaraAliOsman/dekopen/pull/14
  - D05 colores/acabados PR https://github.com/KaraAliOsman/dekopen/pull/15
  - IA2 AI ops/tools PR https://github.com/KaraAliOsman/dekopen/pull/16
  - D06 accesorios/extras PR https://github.com/KaraAliOsman/dekopen/pull/17
  - IA3 proveedor real PR https://github.com/KaraAliOsman/dekopen/pull/22
  - P25 marca/identidad PR https://github.com/KaraAliOsman/dekopen/pull/26
  - P05 dibujo técnico PR https://github.com/KaraAliOsman/dekopen/pull/25
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

## P25 state

PR abierto a `integracion/v1` (pendiente de merge) desde `devin/P25-marca`:

- Marca canónica «La sección»: anillo cuadrado 24×24 con muro 2.5 y alma de 2 a 1/3 (la sección de perfil que el producto dibuja); `SECTION_PATH` único en `frontend/src/brand/BrandMark.tsx` (currentColor — una geometría pinta claro/oscuro), wordmark con la O reemplazada por la marca (~0.73em), DocLockup «La cota» para portadas internas/correos.
- `favicon.svg` se auto-colorea por `@media (prefers-color-scheme: dark)` interno (`.ink` #161c1f → #fcfdfc) — las capturas deben emular `colorScheme`, no recolorear el SVG; `manifest.webmanifest` + PNG 16/32/180/192/512 rasterizados; `theme-color` teal-800 sobre papel g-50 (maskable con safe-zone 78 %).
- Acceso/onboarding como hoja técnica (`auth/AuthSheet.tsx` + `styles/auth.css`): papel `--theme-canvas`, marco con inglete, una acción por hoja; onboarding usa `ui/Stepper` (se corrigieron sus estados `is-done`/`is-current`/`is-blocked`).
- Correos transaccionales (`backend/mail/`): outbox `public.mail_messages` (fila materializada pre-envío, audiencia CLIENT/INTERNAL, QUEUED/SENT/FAILED/SKIPPED, RLS solo roles comerciales), 5 plantillas es-CL «usted» (magic link en `supabase/templates/`, quote_sent, quote_approved, payment_received, step_blocked), provider `sandbox` por defecto / `smtp` con CID inline, emisión por jobs `mail.*` dentro de la transacción del caso de uso, vista previa dev-only en `/dev/correos` (`mail/views.py` reescribe CID a data-URI).
- White-label: `brand_color` #RRGGBB en `tenancy_organizations` (CHECK SQL), validado AA 4.5:1 contra papel blanco en `documents/brand.py` con fallback teal-800; el portal del cliente aplica el color como override local de `--theme-accent*` (leído del snapshot sellado en `_sealed_organization` — una renombría posterior NO rescribe cotizaciones ya emitidas); logo content-addressed `org_<id>/branding/logo_<sha12>.<ext>` con verificación sha256 en lectura; `doc_dekopen_credit` oculta «Generado con DEKOPEN» salvo opt-in.
- `EmptyIllustration` (elevation/bar/document/order/bench — lámina técnica 120×80) en `EmptyState.illustration` (proyectos, producción, `NotFoundPage`, `RouteErrorBoundary`, `OfflineOverlay`); Orb recoloreado de cyan a familia teal en tokens sin tocar su API.
- Bugs reales corregidos en verificación: (1) `mail.service._project_mail_row` seleccionaba `projects.currency` inexistente — ahora JOIN a `tenancy_organizations` (los jobs `mail.*` fallaban con `UndefinedColumn`); (2) `OrganizationBrandingLogoView.get` devolvía DRF `Response` sobre bytes PNG → 500 `UnicodeDecodeError` — ahora `HttpResponse`; (3) `DocumentaryError` en handlers `mail.*` se trataba como transitorio — ahora `JobPermanentError` (alineado con el handler de artifacts).
- Verificado: `make lint|typecheck|test|build` verdes y `make test-db` (pgTAP 1023 tests incl. `179_p25_brand_mail.test.sql`, integración 273, e2e 12, replay Postgres-16) con `PY=.venv/bin/python`; entrega real comprobada `SENT sandbox` con `brand_color` #B45309 embebido en `html_body`; capturas en `docs/redesign/captures/p25-marca/` + `docs/redesign/captures/marca/`; decisiones en `docs/decisions/valores-por-defecto.md` sección P25.

## D06 state

Merged into `integracion/v1` as squash `d7dc6a9c83d19958ca7730930ec27381c30c967c` (dekopen PR #17):

- `ExtraArticle` (catalogo global u org) y `ServiceArticle` (org) son datos: kinds SILL/FRAME_EXTENSION/COVER_TRIM/SKIRT (corte, `pricing_unit=METER`) y MOSQUITO_SCREEN/VENTILATOR (contados, `EACH`); `families`/`unit_kinds` predicados de aplicabilidad, `suggestion_reason` marca el articulo como acompanante sugerido con causa (migracion `20261231000000_d06_extras.sql`: `extra_articles`, `service_articles`, `extra_templates`, `service_templates`, `project_services`, `organizations.extras_display`).
- El motor (`engine/.../extras.py`) mide desde la geometria: vierteaguas = corrido inferior exterior continuo + `vuelo` por extremo (1500+30+30 → 1 corte de 1560 mm), ensanche/tapajunta = largos de los lados exteriores declarados, contados = hojas operables (override `qty`); servicios = unidades / m2 / ml de perimetro / cargo unico. Nada se digita: cantidad x precio = total por sublinea (`bom.extra_lines`) y por servicio (`service_lines` en pricing), y el plan de corte/BOM de OT recibe las piezas `origin=EXTRA` (perfil `cut_profile_sku` del articulo) y los `fittings` contados.
- Sugerencias: el articulo con `suggestion_reason` se ofrece (aceptar/descartar) en todo vano aplicable donde mediria algo; plantillas org (`extra_templates` por sistema, `service_templates` por proyecto) se fusionan al crear vanos/proyectos sin pisar selecciones existentes.
- UI: inspector "Extras de la posición" (en el rail "Vista general" sin seleccion) con vuelos/lados/cantidad + sublineas del motor + sugerencias; "Servicios del proyecto" (details en la pagina del proyecto) con cantidades derivadas; tarjeta "Accesorios y servicios" en Ajustes (`extras_display` DETAILED/GROUPED + plantillas).
- DOC-01: sublineas EXTRA bajo cada posicion ("Vierteaguas exterior — 1.66 M × $11.000 = $18.260") y bloque propio `.service-lines` "Servicios del proyecto — incluidos en el neto" (paginable, fuera de la columna irrompible que recortaba texto en silencio); `extras_display` de la org gobierna detalle vs solo nombres.
- Congelado: los `bom.fittings` de extras contados pasan por el gate `fitting_purchase_mapping_missing_or_ambiguous` igual que herrajes (semilla global en `seed.sql`); el neto sellado incluye sublineas + servicios y los precios historicos quedan congelados en el snapshot.
- Verificado: `make lint|typecheck|test|build` y `make test-db` verdes (`PY=.venv/bin/python`); golden 1500+30+30→1560 mm e instalacion por ml de perimetro; suma sublineas == total de posicion; plantillas aplicadas en vano nuevo; 30 capturas en `docs/redesign/captures/d06-accesorios-extras/` (antes 4, despues 24 + 2 DOC-01) + ux-audit sin hallazgos nuevos (enum MOSQUITO_SCREEN corregido en BOM con `catalog.extraKind`).

## D03 state

Merged into `integracion/v1` as squash `db136a7207487e4e843b17f36f03a4c78a54b79b` (dekopen PR #9):

- `Opening{movement, hinge_side, direction, leaf_role, fixed_in_sash}` + `BayLeaf{slot, opening}` + `OpeningSpec{unit_kind, leaves}` is the real opening model (`engine/.../models.py`, `openings.py`); the legacy `opening_type` enum stays accepted for one version and maps totally to/from specs (`spec_for_legacy`/`legacy_openings_for_spec`) — migrated goldens are byte-identical.
- Movements declared: FIXED, TURN, TILT, TILT_TURN, TOP_HUNG, BOTTOM_HUNG, SLIDE, LIFT_SLIDE, PARALLEL_SLIDE, FOLD, PIVOT_V, PIVOT_H, VERTICAL_SLIDE — the last six are declared-only (D08 implements them); sliding still routes through the legacy `sliding_layout` path.
- `unit_kind` (WINDOW/DOOR) is declared on the unit's top node (a split), not ROOT; a DOOR unit enables `DOOR_SASH` leaves inside splits → door+sidelight and double door without a meeting stile mullion; multi-leaf hinged bays are exactly 1 ACTIVE + PASSIVE (passive carries INVERSOR + falleba hardware).
- `system_opening_capabilities` (migration `20261230000000`) admits movement×directions×roles×unit_kinds×max_leaves per system, falling back to family defaults when the catalog declares no rows; rejection names the admitting families (engine) and systems (backend), and editor/API/AI only offer admitted combinations.
- Handle derivation is policy-driven per leaf: lock side opposite the hinges (french = active leaf only), height from the system's/kit's handle policy (`handle_height_mm`), editable.
- DIN symbology by view follows `_contrato.md` §9 — interior view draws INWARD solid / OUTWARD dashed, door leaves draw a swing arc from the hinge-side top corner plus a threshold accent under operable leaves only; fixed leaves draw no glyph. Implemented in `documents/renderers.py::_spec_leaf_glyphs`, `ProductFrontSvg` and `OpeningGlyph`.
- es-CL names follow "<movimiento> hacia <dirección> — bisagras a la <lado>" with proper names ("Francesa 2 hojas — activa izquierda", "Solo abatimiento (banderola)"); generated by `opening_leaf_name_es`/`spec_display_name_es` and mirrored in `domainLabels`/e2e selectors.
- Captures for every typology (technical, interior view) live under `docs/redesign/captures/d03-aperturas-tipologias/` (18 PNG, 1440×900 light); decisions registered in `docs/decisions/valores-por-defecto.md`.

Verification: `make lint|typecheck|test|build` and `make test-db` green locally (with `PY=.venv/bin/python`); new golden cases per typology plus identical migrated goldens; capability test names admitting systems.

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

## D05 state

Merged into `integracion/v1` as squash `85cf4d6019111c08421c01024b98556e31199934` (dekopen PR #15):

- Real per-system color catalog: `system_color_options` (code keys `profile_systems.finishes`; kind, manufacturer_code, gloss, render_color/texture, finish_class, film_clearance, glass_clearance_mm, dark, faces, pair_code, size_factor, surcharge_*, sort_order, data_provenance) plus `profile_systems.bicolor_allowed` (migration `20261230002000_d05_colores.sql`; seed rows are `SEED_SYNTHETIC`).
- Bicolor per position: `project_positions.color_exterior` (NULL/equal-to-interior = monocolor; the canonical preimage strips it so monocolor `calculation_hash` is unchanged). Engine combination rules in `finishes.resolve_color_selection`: face availability, `bicolor_allowed`, whole-bar kinds (ANODIZED) never bicolor, two MASS colours never on one bar, `pair_code` honoured both directions — each rejection names finish + face in es-CL.
- Colour rules as importable data: `film_clearance`/`finish_class` wire mandatory reinforcement and machining rules into D01 (`Positions check FOILED at freeze when the face colors require it`); `size_factor`/`dark` shrink the leaf envelope; `surcharge_kind` (PER_PROFILE_METER / PER_M2 / FIXED_PER_POSITION / PCT_OF_MATERIALS) is computed by the engine into `color_surcharges` and consumed by pricing.
- Per-colour SKU: `profile_purchase_mappings.stock_color` keys the plain code or the `EXT/INT` bicolor key; NULL is a legacy colour-agnostic bar serving any finish, two viable bars stay `AmbiguousStockAuthority`; the seed generates every valid key via a CROSS JOIN mirroring `resolve_color_selection`, and `physical_stock_color_mismatch` is preserved.
- Renders use catalog colours per face: 2D commercial canvas and technical SVGs, 3D (`materials3d`/`Model3DView` exterior/interior flip — wood foils render brown, no pink), portal and PDF; `finish_label` ("Nogal exterior / Blanco interior") is sealed in the engine result.
- `ColorSelector` (real swatches per face, "Igual en ambas caras", summary + surcharge hint, issue line) replaces the free finish dropdown when the system declares options; unchecking same-faces seeds the exterior with the first other valid option (the original derived state made the checkbox impossible to uncheck).
- Catalog readiness probes the series' declared base finish (first `finish_class='WHITE'`/`faces='BOTH'` option — NATURAL on anodized aluminium) instead of a hardcoded `'WHITE'`.

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

## IA2 AI operations and engine tools

The IA2 encargo gives the AI the same typed operations a user has in the editor and project, engine-backed tools for numbers, and a typed clarify channel:

- `backend/projects/ops_registry.py` is the single ops registry: 36 ops across `product`/`position`/`project` scopes plus `prepare_*` routes (emit/release/purchase/payment_link stay prepare-only). `ops_contract()` exports the registry into OpenAPI and `frontend/src/api/opsContract.generated.ts`; UI, API and AI execute the same ops.
- `design_assist._validate_ops(ops, summary, catalog, declared, declared_strict)` returns `(accepted, rejected, simulation)`; `declared_strict` limits "must be prompt-cited" to semantic decisions (e.g. `parts`), while derived numbers (`offset_mm`, prices, weights) are computed by the engine/sim — rejecting a correct derived number is now impossible by construction.
- Engine tools in `ai_gateway/tools.py`: `calculate_position`, `validate_position`, `price_position`, `price_project`, `explain_price_delta`, `list_catalog_options`, `get_blockers`, `simulate_ops` — the model cites numbers only from tool output or context.
- `clarify {question, options[]}` renders as chips in `AssistantPanel`; a chip submits `<prompt> — <option.label>` through the same channel (verified E08 end-to-end).
- `ai_gateway/context.py` now projects `systems:[{id, code, family}]`, per-position prices, revision diffs, cut bars, sash weights and validation blockers; `_system_opening_options` keeps the `legacy` alias so both D03 keys (`PRIMARY:TILT_TURN:LEFT:INWARD`) and legacy enums (`TILT_TURN_LEFT`) validate against `opening_keys`.
- Frontend parity: `assemblyCommands.ts` (incl. `parts` count), `positionOps.starterDesign` autofills glass only from single-option lists, `AgentBody` marks "Aplicado" solely when every op succeeds.
- Versioned es-CL system prompt (`projects/design_prompt.py`) with glossary/conventions; agent limits `ai_gateway/limits.py` (20 steps / 6 queries / 6 clarify rounds + timeout) with per-job `job_metrics`.
- Migration `20261230003000_ia2_mimo_wire_model.sql` pins `mimo-v2.6-pro` in `ai_routes`. The real provider remains 429 quota-blocked (verified 0/26); MOCK evals run 26/26 with zero rejected ops (`docs/ai/evals/2026-10-05-ia2-mock.json` / `-ia2-mimo.json`).
- Verified in a real browser: E02 split+openings, E04 travesaño, E08 clarify→chip→set_handle_height, J02 agent creates a SLIDING_2L position (captures `docs/redesign/captures/ia2-asistente/`); `make lint|typecheck|test|build|test-db` green.

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


## [2026-10-05] D07 | del vano de obra a la medida de fabricación

- `mounting_rules` (migración `20270105000000`): autoridad versionada inmutable por sistema×organización — los 5 tipos de montaje (`EN_VANO`, `PREMARCO`, `SOBRE_VANO`, `TRASLAPADO`, `RENOVACION`) con holgura/solape firmada por lado, ensanches y accesorios de fijación; semillas `SEED_SYNTHETIC` + `review_pending` para todo sistema sembrado.
- `project_positions` gana el registro del vano (`rough_opening_input`: 1–3 puntos por eje, tipo de muro, escuadra/desplome), `mounting_rule_id` (trigger rechaza reglas de otro sistema/tenant), `fabrication_lock` y `measurement_state` (`CLIENT_DECLARED`→`SITE_RECTIFIED`→`CONFIRMED`, sello exigido por CHECK).
- Motor `engine/rough_opening.py`: `fabrication = vano_menor + ajuste` con desglose por lado; spread > `tenancy_organizations.vano_spread_tolerance_mm` (Ajustes > Reglas de taller, default 10 mm) avisa y queda registrado; `MANUAL_LOCK` gana y divergencia = warning.
- Gate de producción: `release_production` rechaza `measurement_not_confirmed` con posiciones medidas sin confirmar; la rectificación en sucesor entra al diff documental con su Δ.
- UI: chip "Vano × Fabricación · montaje" en el editor, inspector "Vano y montaje" con preview en vivo, cota doble en el lienzo (vano punteado + holgura por lado) y tolerancia org en Ajustes.
- Verificado: `make lint|typecheck|test|build` y `make test-db` verdes (`PY=.venv/bin/python`); 14 goldens del motor; pgTAP 177 con trigger+check reales; tests de integración confirm/unconfirm/gate/revisión.


## [2026-10-05] IA3 | proveedor de IA real

- `ai_invocations` (migración `20270106000000`): log durable sin contenido por llamada (capability, modelo público, tokens, créditos, `est_cost_usd`, estado ok/error/blocked, `kind=call|probe`); la fila de error se escribe post-rollback vía `error.invocation` + `record_attached`, la de éxito via `on_commit` en la tx del caller. RLS: OWNER/ESTIMATOR/WORKSHOP_MANAGER leen, `ai_backend` inserta.
- `ai_org_settings.monthly_credit_budget`: techo mensual en créditos wallet verificado dentro del lock (`ai_budget_exceeded` 409, bloqueo suave que el OWNER ajusta en Ajustes).
- `ai_model_prices` + `ai_audit_logs.est_cost_usd`: costo USD estimado sellado por llamada; NULL sin tarifa (la UI dice "Sin tarifa registrada").
- `ai_routes` gana `timeout_s`, `retry_max`, `tools_enabled`; reintentos sólo transitorios (5xx/408/425/timeout/429+Retry-After) con backoff acotado; rechazo con tools → un reintento JSON estricto (`tools_fallback`).
- Proveedor MIMO repineado a `mimo-v2.6-pro` en `token-plan-sgp.xiaomimimo.com/v1` (el pin `primalabs-ai/...RL` divergía de la credencial y moría en 400/401). Los 26 evals IA1 corren con el pin corregido → 26/26 `ai_provider_quota`: la credencial token-plan está sin cuota; verificación real queda pendiente de una credencial pay-as-you-go (no es fallo de código).
- API nueva: `GET /ai/provider/status/` (miembros, {mode, mock}), `GET|PUT /ai/settings/` (OWNER), `POST /ai/provider/check/` (probe real sin débito), `GET /ai/activity/` (filtros capability/estado, keyset).
- UI: Ajustes › Inteligencia artificial (OWNER): estado, tabla por capacidad, Probar conexión, presupuesto y consumo del mes; panel "Actividad de IA" en /jobs con filtros; insignia "Modo de prueba" en el shell cuando MOCK sirve (miembros incluidos); el Orb lee fases del worker (`progress_phase`: contexto/modelo/propuesta); el job muestra su costo (créditos·tokens·≈USD).
- MOCK seguro en prod: sólo `AI_GATEWAY_MOCK_ENABLED=1` explícito lo abre en producción — DEBUG no lo abre (test congelado). La clave del proveedor nunca sale del servidor (test: no llega al response ni al log).
- Verificado: `make lint|typecheck|test|build` verdes; 23 tests nuevos `test_ia3_runtime.py` (reintento, timeout, presupuesto, fallback JSON, tools, gate MOCK, fuga de clave); evals MOCK 0/26 baseline + MIMO 0/26 por cuota documentados.


## [2026-10-06] P05 | dibujo técnico: geometría de glifos y cotas

Merged into `integracion/v1` as squash `2c04dcd64afb7cea16effb899ecaf33fe9e7aa67` (dekopen PR #25):

- Contrato de simbología único: `engine/src/dekopen_engine/opening_symbols.py` (autoridad) + `frontend/src/features/canvas/openingSymbols.ts` (gemelo estricto). `leaf_primitives`/`sliding_primitives` emiten primitivas simbólicas (`tri`/`arrow`/`handle`/`sill`/`none`); `glyph_paths`/`glyphPaths` las convierten a paths SVG canónicos; 14 fixtures JSON en `engine/tests/fixtures/symbols/` congelan primitivas y `d` por caso × vista — paridad exacta (20+29 tests).
- `SlidingPanel.travel` (`LEFT`/`RIGHT`) declarado por hoja móvil; `SlidingLayoutError` si una hoja viaja a jamba sin espacio o dos móviles adyacentes comparten riel; paneles sin `travel` dibujan la convención documentada marcada "dirección inferida" (opacidad/dash en flecha, badge en editor).
- Toda elevación declara la vista ("Vista interior/exterior"): el editor gana selector (espejo de lámina con mobiliario no espejado y exterior solo-lectura) + bloque "Simbología" plegable; las figuras PDF imprimen la leyenda y las cotas enteras `tabular-nums` en canaletas fuera del dibujo.
- Puerta en alzado = triángulos DIN + umbral naranjo bajo toda hoja no fija — el arco de barrido quedó solo en planta. Correderas dibujan flechas por `travel` declarado; O/X/X/O respeta slots fijos.
- Corte de planta bajo cada bay corredizo del alzado técnico (canvas + PDF): barra de muro EXTERIOR arriba, rieles numerados por `track` (0 = más exterior), hojas en su slot con flecha.
- Cotas del nivel técnico en canvas: cadena exterior total + cadena por paño eje-a-eje de partidor + datum de manilla cuando `handle_height_mm` declarada.
- `OpeningGlyph` (`ui/icons.tsx`) y la sección Firma de `/dev/ui` dibujan el contrato real — la tabla de símbolos del dev-canvas cubre el vocabulario completo.
- Contrato y anti-reglas en `docs/PRD/opening-symbols.md`; ilustraciones por caso/vista generadas por el engine (`scripts/gen_symbol_doc_assets.py`).

## [2026-10-06] P02 | identificadores humanos y formato §3.3

- Migración `20270107000001_p02_human_codes.sql`: `private.next_human_code(org_id, kind)` (advisory lock por org+kind → folio `OC-`/`RT-`/`REC-` de 6 dígitos), `private.guard_human_code` BEFORE UPDATE (42501 si alguien reescribe el código), columnas `inventory_remnants.remnant_code` y `order_receipts.receipt_code` NOT NULL UNIQUE(org) con backfill determinista por `created_at`; órdenes de compra nuevas llevan `OC-` y las selladas pre-P02 conservan `PO-`. Huecos por rollback documentados (folio abortado no se recicla en otra fila).
- Identidad de pieza `P{pos}-U{u}-M{i}`/`-I{sec}` única en paquete de corte HTML, `bars.csv`, `sheets.csv` (columna `piece_label`), DXF (`_placement_code`) y etiquetas QR; test `test_piece_identity.py` exige conjuntos idénticos entre artefactos.
- Formato §3.3 aplicado backend+frontend: mm enteros con espacio fino U+2009, coma decimal es-CL, CLP `$1.435.471`, `US$`/`UF`, `%` un decimal, `dd-mm-aaaa`; `frontend/src/format.ts` (`fmtMm`, `fmtMmCanonical` para inputs — decimal canónico en la frontera de edición/persistencia — `fmtPct`, `shortTechnicalId`), `<EntityCode>` para ids técnicos; CSV/DXF siguen canónicos/ASCII; huella digital 8-hex sólo en pie/cajetín (QR conserva 16 hex); sin UUID/hash ≥10 hex en superficies de cliente/taller.
- Búsqueda global resuelve `OC-000012`, `RT-000003`, `REC-000004` y códigos OT/posición (CommandPalette + `search/service.py` grupos remnants/receipts).
- Verificado: `make lint|typecheck|test|build` verdes (`PY=.venv/bin/python`); `make test-db` verde (pgTAP 1034 incl. `179_p02` 21 aserciones, integración 275 incl. 2 tests de concurrencia de folios, e2e Playwright); e2e `canvas.spec.ts` actualizado a expectativa `1 006 mm`.
