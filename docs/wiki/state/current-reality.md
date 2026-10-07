---
type: state
status: active
updated: 2026-10-07
volatility: high
verified_ref: 773342c6278c2f06ef47a9d74bc9fb662736d4bc
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
  - P02 identificadores/formato PR https://github.com/KaraAliOsman/dekopen/pull/27
  - P04 editor canvas-first PR https://github.com/KaraAliOsman/dekopen/pull/24
  - P09 DOC-01 propuesta PR https://github.com/KaraAliOsman/dekopen/pull/34
  - P03 shell/Hoy PR https://github.com/KaraAliOsman/dekopen/pull/32
  - P17 asistente/Orb PR https://github.com/KaraAliOsman/dekopen/pull/35
  - P07 workspace precios PR https://github.com/KaraAliOsman/dekopen/pull/33
  - P12 producción PR https://github.com/KaraAliOsman/dekopen/pull/40
  - ED1 pase editorial PR https://github.com/KaraAliOsman/dekopen/pull/42
  - P13 pack corte etiquetas PR https://github.com/KaraAliOsman/dekopen/pull/44
  - P06 bow acoplados PR https://github.com/KaraAliOsman/dekopen/pull/46
  - P15 compras inventario PR https://github.com/KaraAliOsman/dekopen/pull/47
  - P14 CNC mecanizado PR https://github.com/KaraAliOsman/dekopen/pull/52
  - P11 cobranza facturación PR https://github.com/KaraAliOsman/dekopen/pull/51
  - P16 catálogo PR https://github.com/KaraAliOsman/dekopen/pull/55
  - P08 cotización emisión PR https://github.com/KaraAliOsman/dekopen/pull/50
  - ED2 pase editorial PR https://github.com/KaraAliOsman/dekopen/pull/58
  - P21 proyecto hub PR https://github.com/KaraAliOsman/dekopen/pull/60
  - P22 clientes ajustes PR https://github.com/KaraAliOsman/dekopen/pull/61
  - D08 tipologías avanzadas PR https://github.com/KaraAliOsman/dekopen/pull/65
  - P15 compras/inventario branch devin/P15-compras-inventario
  - P08 emisión/cotización branch devin/P08-cotizacion-emision
  - P17 asistente IA/trabajos/Orb branch devin/P17-asistente-orb
  - P22 clientes/ajustes branch devin/P22-clientes-ajustes
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

Merged into `integracion/v1` as squash `80860f3ef9fe1cf94abf1c564ff00506ef6686b0` (dekopen PR #26):

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

## D08 state

Merged into `integracion/v1` as squash `773342c6278c2f06ef47a9d74bc9fb662736d4bc` (dekopen PR #65):

Delivered on branch `devin/D08-tipologias-avanzadas` (verified at `c564c055987d7a5edc1967a1642fce3e3b19d3d8`, PR head rebased on `b6b18f0a`):

- Six advanced typologies run the full engine vertical slice — model, `assert_opening_allowed` validation (`families_admitting_spec`), cuts, BOM, hardware kits, DIN symbology and es-CL human names: puerta corredera elevable/HST (`LIFT_SLIDE`), osciloparalela/PSK (`PARALLEL_SLIDE`), plegable (`FOLD` n+m with ACTIVE pass-leaf), pivotante (`PIVOT_V`/`PIVOT_H` + `axis_offset_mm`), guillotina (`VERTICAL_SLIDE`, simple/doble) and puerta corredera (`DOOR` + `SLIDE`).
- New `SystemFamily` values LIFT_SLIDE/PARALLEL_SLIDE/FOLDING/PIVOT/VERTICAL_SLIDE + `FAMILY_MOVEMENTS`/`FAMILY_UNIT_KINDS` repertoire per family; `SystemParams` gained `fold_guide_clearance_mm`, `fold_leaf_clearance_mm`, `pivot_clearance_mm`.
- Catalog: migration `20270218000000_d08_tipologias_avanzadas.sql` seeds six synthetic DEMO systems (`DEMO_ELEVACION_90`, `DEMO_PSK_90`, `DEMO_PLEGABLE_70`, `DEMO_PIVOTANTE_120`, `DEMO_GUILLOTINA_60`, `DEMO_PUERTA_CORREDERA_70`) with opening capabilities, kits (`LIFT_SLIDE`/`PARALLEL_SLIDE`/`FOLD`/`PIVOT`/`VERTICAL_SLIDE`/`DOOR_SLIDING` enum values added to `KitOpeningTypeEnum` + regenerated openapi/orval client), cut and reinforcement rules — marked SEED_SYNTHETIC, never real manufacturer data.
- Backend: `IncompatibleTypologyError` now propagates through `adapter.calculate_from_api` + `derivative_views` as 400 `typology_incompatible` with `compatible_systems` resolved via `list_visible` + `families_admitting_spec` — the contract is live, not dead code.
- Frontend: the typology library gained an "Avanzadas" group; `starterCompatible` checks every bay's emitted spec key via `openingSpecKeyAdmitted` (spec bays) or `openingOptionAdmitted` (enum bays); blocked cards show the cause and a lazy per-system query names which catalog systems admit the recipe (§8 "La admiten:" list) — a typology is never invented, only offered where the catalog declares it.
- Plan symbols: `opening_symbols.py` + TS mirror gained folded-package, lift-slide rail, pivot-axis and vertical-slide primitives; the F5 extended plan shows real travel per the P05 glyph pipeline; fixtures under `engine/tests/fixtures/symbols/`.
- Decisions registered in `docs/decisions/valores-por-defecto.md` (D08 section); captures under `docs/redesign/captures/d08-tipologias-avanzadas/`.

Verification: `make lint|typecheck|test|build` and `make test-db` green (`PY=.venv/bin/python`) — 1185 pgTAP incl. `185_d08_tipologias.test.sql`, 283 backend integration, 27 e2e, engine 742, backend unit 1315, frontend 723; golden per typology + capability rejection naming admitting systems.

## D03 state

Merged into `integracion/v1` as squash `db136a7207487e4e843b17f36f03a4c78a54b79b` (dekopen PR #9):

- `Opening{movement, hinge_side, direction, leaf_role, fixed_in_sash}` + `BayLeaf{slot, opening}` + `OpeningSpec{unit_kind, leaves}` is the real opening model (`engine/.../models.py`, `openings.py`); the legacy `opening_type` enum stays accepted for one version and maps totally to/from specs (`spec_for_legacy`/`legacy_openings_for_spec`) — migrated goldens are byte-identical.
- Movements declared: FIXED, TURN, TILT, TILT_TURN, TOP_HUNG, BOTTOM_HUNG, SLIDE, LIFT_SLIDE, PARALLEL_SLIDE, FOLD, PIVOT_V, PIVOT_H, VERTICAL_SLIDE — all implemented (D08 gave the last six model, validation, cuts, BOM, hardware, symbols and human names); sliding still routes through the legacy `sliding_layout` path.
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

Merged into `integracion/v1` as squash `acc90900e872e10cd93167f98d3911fbda19c61f` (dekopen PR #27):

- Migración `20270107000001_p02_human_codes.sql`: `private.next_human_code(org_id, kind)` (advisory lock por org+kind → folio `OC-`/`RT-`/`REC-` de 6 dígitos), `private.guard_human_code` BEFORE UPDATE (42501 si alguien reescribe el código), columnas `inventory_remnants.remnant_code` y `order_receipts.receipt_code` NOT NULL UNIQUE(org) con backfill determinista por `created_at`; órdenes de compra nuevas llevan `OC-` y las selladas pre-P02 conservan `PO-`. Huecos por rollback documentados (folio abortado no se recicla en otra fila).
- Identidad de pieza `P{pos}-U{u}-M{i}`/`-I{sec}` única en paquete de corte HTML, `bars.csv`, `sheets.csv` (columna `piece_label`), DXF (`_placement_code`) y etiquetas QR; test `test_piece_identity.py` exige conjuntos idénticos entre artefactos.
- Formato §3.3 aplicado backend+frontend: mm enteros con espacio fino U+2009, coma decimal es-CL, CLP `$1.435.471`, `US$`/`UF`, `%` un decimal, `dd-mm-aaaa`; `frontend/src/format.ts` (`fmtMm`, `fmtMmCanonical` para inputs — decimal canónico en la frontera de edición/persistencia — `fmtPct`, `shortTechnicalId`), `<EntityCode>` para ids técnicos; CSV/DXF siguen canónicos/ASCII; huella digital 8-hex sólo en pie/cajetín (QR conserva 16 hex); sin UUID/hash ≥10 hex en superficies de cliente/taller.
- Búsqueda global resuelve `OC-000012`, `RT-000003`, `REC-000004` y códigos OT/posición (CommandPalette + `search/service.py` grupos remnants/receipts).
- Verificado: `make lint|typecheck|test|build` verdes (`PY=.venv/bin/python`); `make test-db` verde (pgTAP 1034 incl. `179_p02` 21 aserciones, integración 275 incl. 2 tests de concurrencia de folios, e2e Playwright); e2e `canvas.spec.ts` actualizado a expectativa `1 006 mm`.

## P03 shell + Inicio «Hoy» state

Merged into `integracion/v1` as squash `473d027426321995fb90b071ca416a77cdbfe7fb` (dekopen PR #32):

- Riel lateral por flujo: Inicio; Ventas (Clientes, Proyectos, Cotizaciones, Precios con gate); Ingeniería (Catálogo técnico); Operación (Compras, Inventario, Producción, Despacho); Asistente (Asistente, Trabajos — solo `AI_SURFACE_ROLES`); Ajustes. Plegable a icono+tooltip; secciones vacías no se renderizan por rol; <1024 px colapsa a drawer.
- Topbar: migas de pan humanas (códigos `P-`/OT en vez de ids), switchers org/proyecto, `Ctrl K` paleta global (clientes, proyectos, cotizaciones, OT, OC, retazos por código/nombre — retazos por remnant_code/SKU/rack/material/nota → `/inventory`), campana de atención, ayuda `?`.
- «Hoy» (`/dashboard`): `GET /api/v1/today/` (backend `analytics/today.py`) devuelve por rol una cola ordenada por consecuencia — ítem = frase + código de entidad + CTA + razón, urgencias `overdue/today/soon/when_free`; contadores solo accionables+filtrados; estado vacío único «Todo al día». El frontend nunca agrega.
- `AI_SURFACE_ROLES`/`hasAiSurface` (`app/shellUtils.ts`) espeja `_AGENT_CALLERS`/`_JOB_READERS` del backend (OWNER/ESTIMATOR/WORKSHOP_MANAGER): OPERATOR/INSTALLER no montan Orb, AskDekopen ni ven rutas /assistant, /jobs — elimina los 403s de `/ai/*` que OPERATOR recibía en cada carga del shell.
- Destinos táctiles ≥44 px bajo 1024 px; fix `overflow-x` en settings (`.payments-form select` `max-width:100%`).
- Verificado: lint/typecheck/test/build + `make test-db` verdes; capturas 5 roles en `docs/redesign/captures/p03-shell-hoy/` (0 hallazgos en rutas dashboard) + `p03-shell-hoy-full/`; axe-shell sin serious/critical; e2e búsqueda resuelve `P-000012`, `OC-*` real minteada, `RT-000045`, `OT-P-000005-REV-A-03` y nombre de cliente con aislamiento tenant.

## P04 editor canvas-first state

Merged into `integracion/v1` as squash `970ecbfc548800eaae19367e3294567d3863d39a` (dekopen PR #24):

P04 rebuilds the position editor into a CAD-like, canvas-first surface (branch `devin/1791248623-p04-editor-canvas`):

- `ProjectPositionEditor` now mounts `AssemblyEditor` inside a fixed shell: 48px strip (crumbs, editable location, quantity, Serie/Acabado chip popovers, save state, undo/redo, `LivePriceChip`, "Qué falta"), labeled left tool rail (Seleccionar, Dividir V/H, Apertura, Vidrio, Acoplar, Medir) + `TypologyFlyout` starter library, center canvas (fit-on-open, wheel zoom-at-cursor, bounded pan, `F` recenters), right inspector 320–360px, collapsible bottom dock (Árbol/Vanos/Materiales with the BOM).
- Interactions: click selects bay, double-click opens the opening picker anchored to the module (anchor point projected through the view transform), dimension click edits inline (Enter/Esc), `V`/`|`/`-` divide, `Ctrl+Z`/`Ctrl+Y`, `Supr`, arrows nudge 1 mm (Shift 10 mm), `?` shortcuts dialog, debounced non-blocking engine recalc; `LivePriceChip` reads `design_batch_preview` (new nullable `position_id` + net fields) and shows "calculando"/"—", never a stale number.
- Responsive: `useMediaQuery` — ≥1280 full layout, 1024–1279 icon-only rail + inspector drawer, <1024 read-only surface with the notice "Vista de lectura — la edición está disponible desde 1024 px de ancho".
- `StarterGallery.tsx` deleted (library lives in the rail flyout); `openingOptionAdmitted` unit-tested; e2e `tests/e2e/editor-canvas.spec.ts` covers canvas ≥60%×75%, ≤6-interaction window build, 10.000px pan recenter, rail labels/aria, Spanish + capability-filtered opening grid, dirty-guard on editor links incl. dock "Nuevo vano", and the <1024 read-only view.
- Verified: `make lint|typecheck|test|build` green; ux:capture after-shots `docs/redesign/captures/p04-editor-canvas/` with zero new findings vs `baseline-2026-10-05` (the 18 remaining — svg gradient + inset-shadow accents — are pre-existing in the canvas glyphs/strip and belong to P05's scope).

## P09 DOC-01 propuesta comercial v2 state

Merged into `integracion/v1` as squash `9731e0c790a7754bd420710f41646f7b2c08e674` (dekopen PR #34):

Open PR (branch `devin/P09-doc01-propuesta`, rebased on `integracion/v1` post-P04):

- `documents/renderers.py::_doc01` rebuilds DOC-01 as a commercial document: portada (cuando `len(groups) > 6 or total_units > 12`) con hero del renderer real + "Preparado para" + total/condiciones, resumen de posiciones con KPIs y tabla de anchos fijos (thead repetido, subtotal en tfoot), detalle por densidad automática (≤6 ficha completa con `Campo N` + cadenas de cotas por paño + corte de planta product-v2; 7–24 fichas compactas con bloque de precio; >24 tabla `resumen mini` con miniaturas), resumen comercial reconciliado al motor (posiciones post-descuento + extras + servicios → neto → IVA → total), condiciones (pago/vigencia/entrega/`doc_terms`), aceptación con firma/RUT/fecha y bloque "Acepta en línea" con QR segno.
- `_position_svg` gana `fields`: numeración de campos por DFS de bahías (`_bay_fields`), cadenas `_chain_h`/`_chain_v` eje-a-eje en el margen, `_assembly_plan_strip` para product-v2 con polígonos de módulo + wedges de acople + cadena frontal INTERIOR (eje `y - min_y`). Bajo modo comercial se suprimen ids de módulo y el ángulo de acople pasa al borde superior de la junta.
- `share_quote` (portal) opera dos canales de aprobación (`customer_approvals.channel`, migración `20261006000002_p09_approval_channels.sql`): `EMAIL` rota en cada share (los PENDING previos del canal se revocan) y `DOCUMENT` se mintea la primera vez que se produce el slot DOC-01 — el artefacto es evidencia inmutable (`reject_immutable_evidence`, sin grant UPDATE/DELETE), así que el QR impreso lleva un token que ningún re-share mata. Slot ya ocupado → no se mintea ni re-renderiza nada; excepción de render revoca ambos mints. `render_pdf_document` acepta `render_context` sólo para DOC-01.
- Ajustes de organización (migración `20261006000001_p09_doc_settings.sql` + pgTAP 180): `doc_paper_size` LETTER/LEGAL/A4 (override `@page size` sólo DOC-01) y `doc_terms` JSONB con llaves `plazo_entrega/instalacion/exclusiones/garantia/jurisdiccion` validadas por `doc_terms_is_valid()` — serializers, openapi, `OrgBrandingCard` (select + 5 textareas) e i18n.
- Descuento: `discount_pct > 1` se interpreta como porcentaje humano (`/100`); rótulo `10 %` entero / `12,5 %` fracción.
- Tests `backend/tests/test_doc01_render.py` (38, PyMuPDF fijado `pymupdf==1.26.6` en requirements-dev): escalera de densidad 1/12/24/100, ≤45 páginas a 100 posiciones, sin página sólo-pie, sin solapamiento de bboxes de texto, total igual al motor, USD `US$`, sin hex ≥10 fuera del pie, wrap de nombres 120 caracteres, papel A4, QR con approval_url, reconciliación descuento+extras.
- No hecho conocido: no existe modelo de cuotas — el "calendario de pagos" imprime `payment_terms` sellado (registrado en valores-por-defecto y en el PR).

## P17 asistente IA + trabajos + Orb state

Merged into `integracion/v1` as squash `bb713d8710e22c89b41949a674e491e8e3124123` (dekopen PR #35):

Opened on branch `devin/P17-asistente-orb` (PR pendiente sobre `integracion/v1`); verification at HEAD of that branch:

- `OrbState` (`frontend/src/features/assistant/states.ts`) is the single state vocabulary (idle/queued/thinking/working/waiting/success/error/canceled). `useAssistantPresence(context)` derives the Orb state from the org's most pressing `ai_job` scoped by surface+refs; the topbar launcher, dock header, avatars and empty states all read it; unknown states degrade to `idle` (frozen by unit tests).
- `BotFigure`/`Orb` implement the owner's orb spec (adjuntos `docs/cola/adjuntos/bot/`): anthracite sphere + capsule eyes + state-colored orbital ring, sizes 16/20/28/64/160, unique SVG gradient ids per instance, `prefers-reduced-motion` freezes every animation — the Orb is the only continuously animated element and only while working (F8).
- AskDekopen dock is a 400px contextual drawer: surface chip with the legible "where you are" (e.g. "Pos. 01 Segundo piso · P-000001"), per-screen suggestions (`SURFACE_SUGGESTIONS`), Preguntar (context_assist) / Agente (agent turns) tabs.
- Reviewable artifacts: `OpsProposalCard` renders Antes/Después via `ProductPreviewFigure` (real `ProductFrontSvg` renderer) + engine verdict from `design_batch_preview`; apply runs the typed ops (Ctrl+Z undo verified live); discard + "Ver auditoría" open `/assistant?job=`. `BatchOpsStep` (§8) shows per-position diffs with declared Ug — the AI never prints a number the engine didn't compute.
- Honest engine states: whole-batch 422 (no pricing rules/cost list) → card declares "Sin reglas de precio…" with apply still possible (save revalidates the same contract); per-item `ok:false` → apply blocked with cause. Provider failures collapse in `FailureCollapse` ("N intentos fallidos · Reintentar · Detalles técnicos"); the "Proveedor de prueba" badge mounts only in DEV when `member_status().mock`; real provider state lives in Ajustes › Inteligencia artificial (OWNER only).
- Role parity: `canUseAssistant` mirrors `_AGENT_CALLERS` (nav/orb/badge/dock unmounted for OPERATOR/INSTALLER) and `canReadJobs` mirrors `_JOB_READERS` — floor roles see "Tu rol no puede ver los trabajos de la organización." instead of firing a 403-bound query; React Query doesn't retry 403s.
- `/jobs` = legible queue: Spanish job type, human object code (Pos. NN · P-######), StatusChip state, duration, actor, result, state filter in the URL, 100-row pages with "Mostrar más", retry only when the backend allows it, "Abrir en el asistente" per agent row. Mobile status select ≥44px (`--density-loose` under 720px).
- Verified live on the "Taller P17" fixture org (real pricing rules + 479-item cost list seeded): "divide la hoja en dos oscilobatientes" → card Δ +$103.822 → Aplicar (2 tilt-turn leaves, Neto $443.944, "Cambios sin guardar") → Ctrl+Z ($231.064) → audit job f5953da7… (8 créditos, 2192 tokens, "Esperando aprobación"); Orb thinking→working→waiting→success. Provider: MOCK (MiMo quota 429 documented in IA3); the surface declares "Respuesta determinista del proveedor MOCK". `make lint|typecheck|test|build` green; ux:capture `/assistant` 0 findings, `/jobs` only pre-existing shell-chrome findings; captures `docs/redesign/captures/p17-asistente-orb/`.

## P07 pricing workspace v2 state

Merged into `integracion/v1` as squash `c7cde331c0c4763c4133928dcc4abe442a446b03` (dekopen PR #33):

- `engine/.../cascade.py` nuevo: `price_cascade` (waterfall exacto proyecto+posición — familias de costo → merma → MO → residuo de redondeo → costo → margen → recargos venta → lista → descuento → neto → extras → IVA → total; tolera residual de cuantización ≤0,0001×unidades +0,51 en los hitos y lo expone como fila `rounding_residual`/`rounding`; una divergencia mayor sigue rechazando `inconsistent_pricing_result`), `delta_contributions` (Δ por impulsor, orden canónico `quantity→dimensions→glass→hardware→cost_list→fx→selections→commercial→discount→services`, telescopio exacto), `band_state` (IN_BAND/BELOW_MIN/ABOVE_MAX; `None`→BELOW_MIN).
- `pricing_rules` gana `margin_min_pct`/`margin_max_pct` (0,25/0,60 por defecto, CHECK min<max y ≥0) vía migración `20270201000000_p07_margin_band.sql` + pgTAP `180`; editables en `/pricing` › Reglas (solo OWNER). `margin_pct` opcional en el request de precio.
- Puerta de banda: preview fuera de banda de no-OWNER nace `PENDING`; OWNER fuera de banda exige `confirmed` (`owner_confirmation_required`); misma puerta en `apply_operation` (un PREVIEW viejo fuera de banda no se cuela). Frontend: botón pasa a "Solicitar aprobación" con motivo precargado.
- Aviso al solicitante: `mail.pricing_decision` emitido en la transacción que sella APPLIED/REJECTED/WITHDRAWN-por-dueño (idempotencia `mail:pricing-decision:{op}:{outcome}`); `deliver_pricing_decision` materializa `mail_message` al `requested_by_email` (SKIPPED sin destinatario; proveedor sandbox).
- `operation_public` enriquece históricas con `margin_realized`/`band`/`cascade`/`delta` (read-model determinista sobre el snapshot — no hay backfill). Filtros `?state=` (enum) y `?project_id=`; ESTIMATOR solo ve sus operaciones (causa raíz del "No se pudieron cargar los datos").
- Cobertura SKU: `coverage` une identidades de compra (perfil, refuerzo, vidrio técnica+compra, rellenos, paneles, kits de herraje, herraje compra, fijaciones) — lista los SKU emitidos sin costo vigente. Migración `20270202000000_p07_coverage_grants.sql` + pgTAP `181`: GRANT SELECT a `pricing_backend` en los 4 mapeos que le faltaban (vidrio/panel/herraje/fijación — el 42501 que devolvía 409) y política `*_pricing_read` en las 7 tablas cuyo `TO authenticated` las dejaba en filas vacías silenciosas.
- Frontend `/projects/:id/pricing` + `/pricing/commercial`: `MarginBand` (gauge min→max con objetivo y realizado, chip de estado del servidor), `PriceCascade` (waterfall + cascada por posición + autoridades como procedencia), `DeltaBreakdown` (aportes por impulsor con neto/costo/neto resultante), campos de banda en `rules`, `margin_pct` en el formulario, confirmBand + errOwnerConfirm.
- Verificado: `make lint|typecheck|test|build` verdes (`PY=.venv/bin/python`); 16 tests P07 motor (golden 12/100 posiciones cierra exacto), 48 tests de página, integración `test_margin_band_gates_preview_apply_and_notifies`; capturas en `docs/redesign/captures/p07-precios/`; decisiones en sección P07 de `valores-por-defecto.md`.

## P12 producción: tablero, OT y operario state

Merged into `integracion/v1` as squash `5bbd04ce401863faec5f35a0b6f7fe9b900603f5` (dekopen PR #40):

Open PR (branch `devin/P12-produccion`, on `integracion/v1`):

- `/production` splits by role into three surfaces. Manager board: kanban whose columns are exactly the stations holding open steps (`station_queue` entries grouped by step code) plus an «Salida» outbound column; each card shows order code, obra (`project_code` + `client_name`), units, real commitment (`MIN(deliveries.scheduled_date)` — «Sin fecha agendada» when none), `steps_done/steps_total` progress and chips (shortage, bloqueada, QC rechazado, sin plan, plan vencido, repetición, guía pendiente; the three "needs a person" chips carry the orange accent). Filters: text, obra, commitment bucket (vencida/≤7 días/más tarde/sin fecha), issue kind. Deep links `?blocked=1`, `?shortage=1`, `?status=` still resolve.
- Order detail: fixed header (code, `ORDER_STATUS_KEY` label, commitment, progress, actions) + compact horizontal stepper + tabs Resumen·Piezas·Corte·Mecanizado·Vidrios·Herrajes·Calidad·Embalaje·Trazabilidad; the open step edits in a right Drawer. `PieceList` hand-virtualizes (40px rows, 44px sticky group headers, overscan 6) grouped `P{pos}-U{u}` with tolerant search; `HumanTrace` renders day-grouped `HH:MM · actor · acción` with actor/type filters and the raw event log under «Detalles técnicos».
- Operator surface (`OPERATOR` role): auto `density="workshop"` (dark + ≥44px targets, 1024×768 default), station pick persisted per user (`localStorage dekopen.operatorStation.<userId>`), only own station's queue (`Siguiente` = first `is_next` entry), scan input in topbar opens the F9 single-piece screen (code ≥2.5rem mono), action bar Completar·Bloquear·Nota with five one-tap block reasons + «Otro motivo»; no client/price/margin anywhere.
- Backend (no migrations): `list_production_orders` returns `project_code`, `project_name`, `client_name`, `committed_date`, `steps_blocked`, `qc_blocked`, `plan_state`; `_board_context` batch-resolves documentary project names and earliest scheduled delivery.
- Fixture: P-ESCALA seals + releases (~100 live OTs on the board; first optimized). e2e `production-operator.spec.ts` runs inside `make test-db` (operator completes a step, blocks the next order, manager sees it on the board and in «Hoy»).

## ED1 pase editorial de la ola 1 state

Merged into `integracion/v1` as squash `c1ba32063f8177ce4b42a3703f57549061b18c4c` (dekopen PR #42):

PR sobre `integracion/v1` (branch `devin/ED1-pase-editorial-ola1`); encargo sin funcionalidad nueva — coherencia, dedup y pulido del conjunto:

- **Wire vs. display**: `fmtWire(value, decimals)` en `format.ts` es el único serializador del contrato máquina (decimales fijos `"1400.00"`/`"15.0"`); `fmtMmCanonical` queda sólo para inputs editables (decimal canónico, cero recorte); `fmtMm`/`formatDims` son presentación (espacio fino + agrupación). Todos los puntos wire del lienzo, posición y asistente migrados; `.toFixed()` desapareció de features (guarda `ui-tofixed` 87→2 — quedan la definición en `format.ts` y el muestrario dev `/dev/ui/mal`).
- **Estado crudo**: guarda `ui-raw-status` a 0 — patrón sancionado `const xStatus = x.status` + `<StatusChip enumName value>`; fallbacks "—" por helper. `importStatus.ts` (catalogs) concentra etiqueta+tono del ciclo de importación, compartido entre `CatalogImportsPanel` y `ProjectImportsPanel`.
- **Género del glosario**: los estados de operación de precio van en femenino (`pricing.operationState.*` + `domainLabels.PriceResponseStateEnum`: Aplicada/Rechazada/Retirada) — el estado describe «la operación».
- **Piso tipográfico y mono**: `small` fijado a `--type-dense` (12 px) en `base.css` (el default UA caía a 10,8 px — 42 hallazgos `font-too-small` resueltos de una vez); `code/samp/kbd` heredan `--font-mono`; el código de serie en el listado de sistemas va en `<code>`.
- **Ruido de red erradicado**: la ruta dev `/projects/demo/positions/g1/edit` ya no dispara `where-am-I` (refs vacías); `payment-integration` sólo se consulta con `isOwner` (adiós 403 del estimador); rutas de captura declaran `toleratedHttpStatuses` (410 de portal revocado/reemplazado) y `expectViolations` (muestrario dev).
- **Probe de captura corregido**: `contrast-aa` compone alfa sobre el fondo real (falsos positivos teal del portal resueltos); el escáner de vocabulario excluye contextos de identificador (`code`, `pre`, `samp`, `kbd`, `.fmt-code`, `.ui-code`, `[data-code]`) — un SKU/código en mono ya no cuenta como enum-token.
- **Limpieza**: alias muerto `--shadow-lg` eliminado de `tokens.css`; baseline de guardas regenerada sólo a la baja (`raw-status`, `font<11`, `hex-inline`, `shadow-off` → 0; `ui-tofixed` 87→2).
- Verificado: `make lint|typecheck|test|build` verdes; ux:capture antes/después en `docs/redesign/captures/ed1/`; decisiones en sección ED1 de `valores-por-defecto.md`.


## P13 pack de corte, etiquetas e identidad entre artefactos state

Merged into `integracion/v1` as squash `3f3cf8a66169efb31a0afaa04c657b9c71981d99` (dekopen PR #44):

Open PR (branch `devin/P13-pack-corte-etiquetas`, on `integracion/v1`):

- `production/cut_pack.py` reescrito como pack imprimible para el operario de sierra: lista de corte apaisada con badge de origen por barra («barra nueva» / «retazo RT-…» + rack), diagrama SVG por barra con etiquetas por instancia y colocación por niveles, cierre exacto Decimal en `.bar-balance` («cierra exacto» / «diferencia sin asignar N mm») y línea de destino del remanente (folio `RT-` real leído de `inventory_remnants` con `origin_order_id`, o «folio RT- al cerrar el corte», o «→ desecho»).
- Secciones: «Cortes agrupados — sierra manual» (misma spec agrupada con cantidad y lista de etiquetas — trazabilidad preservada), «Refuerzos y junquillos» con la etiqueta de la pieza padre, «Plan de láminas» + «Vidrios» (mm enteros, composición, cantidad, posición, destino), «Piezas no ubicadas» con motivo → acción de catálogo, e «Identidad» con QR `DEKOPEN|OT|CUTPACK|huella16`.
- Hoja de etiquetas configurable por organización: `tenancy_organizations.workshop_label_format` (`GRID` default / `THERMAL_100X50`, migración `20270204000000` + grant a `documentary_backend`), `Ajustes › Documentos`, serializers + `org_branding.py` + openapi/orval regenerados. Grilla 64,7×38 mm en página `piece-labels` del papel documental, o página 100×50 mm rollo; etiqueta = código grande, OT+huella, posición/vano-hoja, rol ES, largo+ángulos+color, QR `DEKOPEN|OT|código|huella8`, siguiente estación (routing payload o `operation_station_map`); etiquetas de retazo anexan al final. La sección corre en `@page` nombrada y la grilla va en flujo de línea — un `display:flex` de WeasyPrint no fragmenta entre páginas.
- Consistencia P02 por instancia (no por spec): `_bar_assignments`/`_sheet_assignments` en renderers.py resuelven `(bar|sheet_index, sequence) → (código, entity_id)` y las comparten PDF, `bars.csv`/`sheets.csv` (`_cnc_bars_csv`/`_cnc_sheets_csv` con `bar_codes`/`sheet_codes`, schema `work_order_cnc_export_v3`) y DXF (`dxf_files(bar_instance=, sheet_instance=)`); `test_same_codes_in_pdf_csv_dxf_and_labels` exige igualdad de conjuntos entre los 4 artefactos + etiqueta.
- DXF sube a AC1027 + `$DWGCODEPAGE=UTF-8` — texto en español intacto (`Junquillo`, `Ñ`, `·R`); `_dxf_text` sólo mapea `⟳`→`(rot)`. Parseo verificado con `ezdxf==1.4.2` (nueva dependencia dev).
- Legibilidad: piso de 8 pt en todo el pack (`.workshop th`, `.tb-label`, `.sign-label`, mono de barras y etiquetas ≥8 pt; texto SVG ≥3 mm de alto); `test_cut_pack_p13.py` verifica OTs de 1/12/100 posiciones — páginas acotadas, cero colisión de bbox de palabras, cierre exacto por barra.
- Columnas CSV documentadas como formato genérico DEKOPEN en `docs/formatos/corte-csv.md` (ningún formato propietario de sierra/CNC). Decisión registrada en `valores-por-defecto.md` (etiquetas grilla por defecto). Capturas raster en `docs/redesign/captures/p13-pack-corte/` (lista de corte, vidrios, etiquetas).
- Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`; backend 1236, pgTAP 1080 incl. `181_p13_workshop_label_format`, integración 279, e2e Playwright).

## P06 bow/bay y conjuntos acoplados state

Merged into `integracion/v1` as squash `301ebfb65f75489ea3f4c2f444a8f625c189db3d` (dekopen PR #46):

Open PR (branch `devin/P06-bow-acoplados`, on `integracion/v1` post-ED1):

- El bow/acoplado se diseña en el mismo editor canvas-first: franja inferior `.plan-strip` (altura arrastrable 96px–45%, plegable) dibuja la planta real del motor (`front_chain` + módulos + cuñas de cople) bajo el alzado, con encabezado de cotas del conjunto (Ancho desarrollado, Frente/cuerda, Proyección) y selector de elevación Desarrollada/Proyectada (`w·|cos(rumbo)|` por columna — cotas redondeadas a 0,01 mm y de solo-lectura en proyectada; un rumbo > 90° muestra el ancho aparente del módulo replegado, nunca negativo).
- Selección bidireccional plan↔frente (mismo `select()` del canvas store); el ángulo de cada unión se edita en la etiqueta de la planta (click → input) o arrastrando: el mango de bisagra y el arrastre de módulo giran la cola de la cadena con imanes {0,±10,±15,±22,5,±30,±45,±90}° (tolerancia 3,5°, umbral de gesto 5px, límite editorial ±90°) — al soltar se llama `setCouplingAngle` y el motor repliega plano, coples y precio.
- Coples filtrados por envolvente de ángulo declarada en catálogo (`coupler_angle_min/max_deg`, migración `20270205000000_p06_coupler_angle_envelope`); envolvente no declarada = desconocida, nunca rechaza. El motor emite `coupler_angle_incompatible` (range en params); el plano marca `!` en la cuña exacta y el chip nombra la unión y el rango admisible.
- Precio por módulo en el chip vivo: `module_net_after` de `design_batch_preview` reparte el neto por costo de material atribuido (`module_id` en líneas de composición); chip muestra «M1 $x · M2 $y» bajo el neto unitario.
- Biblioteca: Bow ×3 canónico (centro fijo, laterales oscilobatiente, 2×22,5°), Bow ×5, Bay 45°, Puerta + lateral, Ventana + sobreluz, Esquina 90° — todas plantillas sobre la misma composición.
- e2e `bow-acoplados.spec.ts` (dentro de `make test-db`): bow 600/1200/600 @2×22,5° en 5 gestos ≤10 + guardar/reabrir idéntico, selección plan↔frente, proyectada más corta que desarrollada.


## P15 compras, recepción, inventario y retazos state

Merged into `integracion/v1` as squash `f67c3c8b12ab174e38e4b8bb452f422e00d88b07` (dekopen PR #47):

PR sobre `integracion/v1` (branch `devin/P15-compras-inventario`):

- **Separación Compras/Inventario**: `/inventory` es superficie propia (stock por SKU con reservado-por-OT y en tránsito, retazos, libro de movimientos); `/purchasing` queda solo de compras (necesidades → propuesta por proveedor → OC → envío → recepción) y ya no monta el panel de stock.
- **Compras**: propuesta editable con `unit_price` por línea (columna nueva en `purchase_allocations`; el precio se sella al confirmar la OC y alimenta `total_net`); `send_order` envía correo al proveedor (`mail.order_sent` con audiencia `SUPPLIER` + adjunto PDF generado por `jobs`) sólo tras clic humano, idempotente, sin romper la transición si el outbox falla; recepción por línea con `supplier_delivery_ref`/`supplier_delivery_date`, `damaged`, lote y rack; sobre-recepción rechaza 422 `receipt_over_received` salvo `allow_over_receipt:true` (la UI pide confirmación explícita); el stock se actualiza dentro de la misma tx.
- **Inventario**: `inventory_movements` acepta sujeto `remnant_id` (CHECK `num_nonnulls(item_id, remnant_id) = 1`; `quantity` requerido sólo para sujeto item — migración separada porque el enum `MOVE` no puede usarse en la misma tx que `ADD VALUE`). Acciones de retazo `move`/`reserve`/`scrap` escriben al libro con actor humano; `scrap` exige `reason`; `remnant_label` devuelve SVG QR `DEKOPEN|REMNANT|RT-######`. `list_movements` enriquece cada fila con código de documento (OC/REC/OT/RT) y `actor_label`.
- **Alerta de retazos viejos**: `tenancy_organizations.remnant_alert_days` (default 30, editable en Ajustes › Organización, grant UPDATE restringido a esa columna); los retazos `AVAILABLE` más viejos que el umbral se marcan `is_old` y se destacan.
- **Compatibilidad retazo↔faltante**: el motor decide — `coverage` devuelve `remnant_pool{kind,key,count,total_mm}` por línea de faltante; la UI (`RemnantOffer`) sólo ofrece y pide elegir la OT destino. Los retazos producidos almacenan ahora `physical_stock_identity` resuelta vía `stock_authority_id` (psi de la barra que los originó) y `bar_remnants`/`list_remnants` resuelven psi por COALESCE con las autoridades; migración `20270212000000` hace backfill — antes quedaban psi NULL y el pool devolvía 0.
- **Causa raíz «error al cargar el stock»**: lectura de `order_requirement_lines` bajo el rol lector sin grant SELECT (42501→409) — ya corregido en la base (`a1b08c07`); regresión cubierta con test de acceso 200 de los 3 roles + pgTAP de grants en `182_p15_receiving_remnants.test.sql` (16 aserciones).
- Integraciones: correo y PDF por proveedor sandbox + «No conectado» en Ajustes › Integraciones + `docs/operations/ACTIVACION.md`. Verificado: `make lint|typecheck|test|build|test-db` verdes; ux:capture 0 hallazgos en `/purchasing` e `/inventory`; capturas en `docs/redesign/captures/p15-compras-inventario/`; decisiones en sección P15 de `valores-por-defecto.md`.


## P14 CNC y mecanizado state

Merged into `integracion/v1` as squash `cd64b5ae6fe60c09e104af73cf0cdc0e8b3b0a2f` (dekopen PR #52):

Open PR (branch `devin/p14-cnc-mecanizado`, on `integracion/v1`):

- `cnc_readiness` ahora devuelve `plan` (huella del plan sellado + `plan_seed`), `members[*]` con metadatos físicos (SKU de taller, rol, largo, ángulos, cara) y `declared_gaps`: intención declarada que no emitió operación — anotaciones de taller (`bottom_drain_holes_mm`, `closing_points_perimeter_mm`, `has_coupler`), `handle_intents` y `hardware_machining` — cada una con `cause` (`no_rule`/`no_coordinates`) y evaluación por máquina (`can_run` + causa: `no_tool`, `unsupported_kind`, `unassessable`, `emitter_not_implemented`). Lo que el motor no emitió nunca se esconde.
- Emisores por registro, no por configuración: `_POSTPROCESSORS` (`neutral-ops-v1` implementado). Una máquina con `postprocessor_id` desconocido marca `emitter_implemented=false`, suma un BLOCK sintético `emitter_not_implemented` en readiness y `generate_program` rechaza con `cnc_emitter_not_implemented` — nunca se emite neutro disfrazado de formato propietario.
- `cnc_machines` gana `machine_type` (MACHINING_CENTER|ROUTER|SAW_DRILL_LINE|COPY_ROUTER|OTHER), `axes_count` (2–6) y `travel_x/y/z_mm`; `cnc_programs` gana `superseded_by` (self-FK → sucesor). Nueva tabla append-only `cnc_authority_events` (máquina/herramienta × created/updated/deactivated/reactivated, actor + diff `from→to`): `authenticated` sólo lee, `documentary_backend` sólo inserta (migración `20270206000000` + pgTAP `182`).
- `list_programs` expone `plan_fingerprint`, `plan_seed`, `superseded_by.program_no` («Reemplazado por») y marca de stale por huella plan+máquina; `generate_program` liga la fila vieja al programa vigente. Nuevo endpoint `GET /cnc/programs/{id}/compare/{other_id}` dife los `operations.json` persistidos (added/removed/changed por campo) — lo que realmente se generó, nunca una re-derivación.
- Frontend (`CncPanel.tsx` reescrito): tarjeta por miembro con identidad física (SKU·rol·material·eje·largo·ángulos — sin ángulos inventados cuando faltan), vista por caras a escala (carriles exterior/interior/cantos/extremos + «cara no declarada»), tabla de ops con coordenadas X/Y/u, profundidad, herramienta y fuente de regla; chips de veredicto clicables que abren la tarjeta; sección «Intención declarada sin operación» por OT y por máquina; programas con semilla, enlace «Reemplazado por», descargas y botón Comparar → diff visible antes de mandar a celda. Workspace gana columnas Tipo/Ejes/Carreras/Emisor (emisor faltante en rojo), campos nuevos en el formulario y la lista de auditoría.
- Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`; pgTAP 1089 incl. `182_p14_cnc_authority`, backend 18 tests CNC incl. determinismo de huella y 403 de roles).


## P11 cobranza, pagos y facturación state

Merged into `integracion/v1` as squash `feb2be5e04da203d2994a63daf0f1f8fdcd2e469` (dekopen PR #51):

Open PR (branch `devin/P11-cobranza-facturacion`, on `integracion/v1` post-P13):

- **Calendario de cobro real**: `payments.py::_schedule` deriva ANTICIPO (vence al aprobar el cliente — `customer_approvals.decided_at` — o a la emisión si aún no hay aprobación) y SALDO (vence contra `deliveries.scheduled_date` — «Contra entrega» sin fecha inventada). % desde `payment_terms` sellado o 50/50 con `pct_source="default"`. Reparto: ANTICIPO/PARCIAL cubren la cuota más antigua primero; SALDO cubre saldo y el excedente baja al anticipo. La respuesta `GET /payments/` expone `schedule`, `movements`, `sii`, `reminder`.
- **Línea de tiempo (F6 aplicada)**: `_movements` cruza en un UNION pagos, anulaciones, links, facturas, notas de crédito y envíos SII — cada fila con actor (`private.user_email`) y su documento respaldo (RC-/FAC-/NC-).
- **F-09 causa raíz**: el estado `payment-integration` (sólo OWNER) vivía dentro del mismo `Promise.all` que la lista de links — un 403 ocultaba todo el panel. Consultas separadas (`enabled: isOwner`); regresión fijada en `ProjectPaymentLinksPanel.test.tsx`.
- **Honestidad tributaria**: `sii_envio.py::integration_state` (`{adapter, certificate, caf_available, certified}`) — `certified` sólo con `sii-ws` + certificado + CAF. Sin certificación, todos los renderers imprimen «Documento interno — no válido como documento tributario electrónico» y ningún timbre se imita; el resumen expone `sii` y la UI lo dice en texto. `sii_envios.status` gana `OBSERVED` («Aceptado con observaciones», veredicto real del SII).
- **Proveedores simulados (opt-in explícito)**: `FLOW_WS_MOCK=1` → `MockFlowClient` + checkout local `/billing/flow-sim/<token>/` (pagar/rechazar → mismo `payment_status` que el webhook real; cargo desconocido nunca reporta pagado). `SII_WS_ENVIO_MOCK=1` + `SII_WS_ENVIO_MOCK_VERDICT` → envío simulado ACCEPTED/OBSERVED/REJECTED. Sin la env → 404, jamás fallback silencioso. Ajustes muestra Flow «Simulado»/«No conectado» y SII con `certified`.
- **Recordatorio IA**: capability `collection_reminder` (ruta `ai_routes` anclada a MIMO como todas — pgTAP 126). `POST …/collection-reminder/` prepara asunto+cuerpo desde hechos del ledger (la IA no calcula montos) auditado en `ai_audit_logs`; `…/send/` encola el correo sólo con clic explícito. `ai_audit_logs` gana `GRANT SELECT` a `documentary_backend` + `EXECUTE documentary_role` (mismo patrón billing/pricing) — sin él el resumen 409aba 42501 (hallado por el gate e2e).
- **Hoy**: la cola del dueño lista cobranza pendiente (`status IN APPROVED/IN_PRODUCTION/COMPLETED` con `total > collected`) y marca «recordatorio preparado» cuando ya existe borrador (`reminder_drafted` via LATERAL a `ai_audit_logs`).
- Migración `20270213000000_p11_cobranza.sql`: `project_payment_links.expires_at` (TTL 72 h, backfill), `sii_envios` check +`OBSERVED`, ruta `collection_reminder`, grants de lectura del rastro IA. Migración `20270214000000_p11_webhook_scope.sql`: `private.payment_link_public_scope` (SECURITY DEFINER) resuelve `{org_id, project_id, created_by}` por id/token opaco — el webhook público delega las claims del `created_by` y todo el settle corre dentro de una sola tx (antes 500 `payment_link_not_found` por claims tx-local expiradas + RLS ciego al anónimo).
- Post-verificación: timbre PDF417 con TED real (CAF embebido ~1100+ chars) — minify XML + columnas ≤30 + redundancia 5→0 (`sii_repr.py`); `GRANT UPDATE (repr_storage_object_key, repr_file_sha256)` sobre `project_dtes` a `documentary_backend` (migración `20270215000000_p11_dte_repr_update_grant` — las columnas repr_* de `20261208` nunca tuvieron grant; `_seal_repr` 409aba 42501, falla latente detrás del crash PDF417); timeline con `status` localizado + actor `sent_by` del envío; `recorded_by` del pago por link = `created_by`; nota del ledger sin UUID; scroll-x de tablas ≤1280 px; recordatorio con fallback `clients.email`.
- Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`); pgTAP 1089 (126_ai_gateway cuenta 10 capacidades; 183_p11_webhook_scope cubre el webhook, 184_p11_dte_repr_grant el sello); integración 279; e2e 20/20; backend 1290; unitarios cobranza en `test_p11_cobranza.py`; settle público + emit_dte con timbre real verificados en vivo (POST anónimo → 302 → PAID → RC; DTE-33 folio 1 con PDF417); decisiones en `valores-por-defecto.md` sección P11.


## P16 catálogo como autoridad visible state

Merged into `integracion/v1` as squash `ae7fa66efc306bae474a324c515b16d03be3c806` (dekopen PR #55):

PR sobre `integracion/v1` (branch `devin/P16-catalogo`):

- **Página de sistema = autoridad visible**: encabezado con nombre, material, profundidad, autoridad de proceso, procedencia (`provenanceLabel` — DEMO/DECLARADO/VERIFICADO derivado de `data_provenance`+`technical_reviewed_at`, jamás verificado sin sello) y escalera de *readiness* con niveles y blockers **deduplicados por primer nivel**, cada uno con deep link a la pestaña/fila exacta (`targets[]` `{kind,id,label,tab}` resueltos en base desde las mismas poblaciones que cuenta el blocker; tope 12 por blocker).
- **Paridad readiness↔gates**: un solo `catalog_readiness(system_id, org_id)` alimenta la página y los gates de emisión/liberación; `test_p16_catalog_parity.py` demuestra igualdad de niveles/blockers/quote_ready en DEMO_60 y en un catálogo clonado incompleto (`copy_fixed_catalog`), y que cada blocker trae target con `tab`+`label`.
- **Pestañas del workspace**: Perfiles · Refuerzos · Vidrios (composiciones + formatos de lámina) · Herrajes (kits por apertura+rango, familias, modelos/colores/opciones, identidades de compra) · Reglas de compatibilidad (cortes, refuerzos, límites por tipología, capacidades de apertura, reglas de montaje, inspector) · Costos (cobertura por SKU enlazada a P07) · Historial (importaciones con sello revisor + eventos de auditoría).
- **Ficha de artículo** (`GET /articles/{id}/ficha/` + `ArticleFichaDialog`): miniatura desde la geometría real (`SectionPreviewSvg`) con escala/origen/orientación; rol en español, ancho de cara, kg/m, pérdida de soldadura, largo de barra; insignia de procedencia que despliega documento origen + página/línea + revisor + fecha (tabla de evidencia `catalog_parameter_evidence`); validaciones de sección `section_check.py` (polígono válido, autointersección, profundidad vs bbox, origen local).
- **Procedencia protegida en BD**: `private.can_review_catalog(org)` = WORKSHOP_MANAGER cualquier aal u OWNER aal2; trigger `guard_catalog_certification()` en las tablas de catálogo rechaza 42501 estampados sin rol (INSERT con sello) y los column-grants niegan el UPDATE directo a `authenticated`; `catalog_import_events` append-only (miembros solo leen por org; `authenticated`/`anon` sin INSERT/UPDATE/DELETE — los default privileges los dejaban mutables).
- **Revisión de importación IA**: candidatos con confianza + evidencia de origen (página/línea) + `diff` re-derivado en vivo contra el artículo `existing` actual (campos `_DIFF_FIELDS`, comparación Decimal); LOW y REVIEW_REQUIRED nacen desmarcados; lo no extraído queda UNKNOWN; confirmar re-deriva desde el candidato guardado y sella `reviewed_by`/`reviewed_at` (COALESCE — el primer sello gana); eventos UPLOADED→EXTRACTED→CONFIRMED en `catalog_import_events` con actor y detalle.
- **pgTAP `183` (21 aserciones)**: `can_review_catalog` por rol/aal/org (regresión PR #107 global vs organización), INSERT certificado sin rol → 42501, UPDATE directo sin columna → 42501, filtrado RLS por org, ledger de importación readable/solo-backend/aislado. Convención runner: pgTAP vive en schema `extensions` — `catalog_backend` no tiene USAGE ahí, así que los asserts corren bajo `authenticated` y el DML crudo bajo el rol backend con captura `DO`+GUC.
- Proveedor IA en desarrollo: MOCK documentado (MIMO en 429). Integraciones sin cambios. Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`); capturas en `docs/redesign/captures/p16-catalogo/`; decisiones en sección P16 de `valores-por-defecto.md`.

## P08 emisión canónica, checklist y enlace state

Merged into `integracion/v1` as squash `efdc1533927ac85084f3e6f356b2970ef861356e` (dekopen PR #50):

Abierto en la rama `devin/P08-cotizacion-emision` (PR pendiente sobre `integracion/v1`, merge SHA `__P08_MERGE_SHA__`); verificación en HEAD de esa rama:

- Compuerta de emisión en `freeze` (`documents/service.py::_emission_missing`): códigos ordenados `client→delivery_address→positions→valid_until→payment_terms→term:{plazo_entrega,instalacion,exclusiones,garantia}` → `emission_checklist_incomplete` + `extra.missing`. El RUT se valida por módulo 11 (`backend/rut.py::rut_mod11_valid`, mismo algoritmo que `format.ts::isValidRut`); la vigencia debe ser fecha ISO parseable — vencida no bloquea («expirada» es un estado diseñado del enlace: el portal la muestra y `decide` rechaza con `quote_validity_expired`), lo que permite sellar P-EXPIRADA. La preparación expone `inspector_blocked` por posición (evaluación FAIL en regla RED del inspector — mismo umbral que el freeze), que el checklist declara con salto a la tarjeta en vez de dejarlo explotar en el 422.
- Condiciones comerciales: `tenancy_organizations.doc_terms` guarda las plantillas de Ajustes (claves `pago`/`plazo_entrega`/`instalacion`/`exclusiones`/`garantia`/`jurisdiccion` — `pago` alimenta `default_payment_terms`) y `doc_validity_days` (1–365) la vigencia propuesta; `project_documentary_inputs.doc_terms` guarda la edición por cotización (texto vacío = omite la línea de la plantilla). Las claves efectivas se congelan dentro del snapshot de la revisión (migración `20270217000000_p08_emission.sql`).
- Vista previa real: `POST /documents/projects/<id>/quote-preview/` arma el mismo snapshot DOC-01 que sella freeze (`_revision_snapshot(preview=True)`) sin persistir nada; el panel lo muestra en iframe `sandbox=""` con huella `bom_hash`, y el diálogo de confirmación repite folio/total/vigencia/destinatario/consecuencia/huella antes de emitir.
- Un solo camino de emisión: Guardar → confirmar → `freeze` → `quote-link` → copiar. `documentaryFreeze*`/`projectQuoteLinkCreate` sólo se llaman desde `ProjectQuotationPanel`; los botones compartir/WhatsApp/email alternativos se eliminaron.
- Ciclo de vida del enlace: `customer_approvals.status` gana `CHANGES_REQUESTED` (VARCHAR(20)); el portal decide APROBAR/RECHAZAR/SOLICITAR CAMBIOS (nota obligatoria en este último y `decide` acepta decidir después de pedir cambios); `share_quote` reemplaza enlaces EMAIL vivos (PENDING+CHANGES_REQUESTED) de la misma revisión; `PATCH /projects/<id>/quote-links/<approval_id>/` mueve sólo el vencimiento; «Hoy»/campana y `quote_state` aprenden el estado nuevo (mail interno `quote_changes_requested`). Stepper Enviada→Vista×N→Decisión + «Reemplazada» derivado de `revision_code !== revisión vigente`.
- Cambios globales: `GlobalChangesPanel` usa el registro `apply_to_positions {filter, ops}` (vidrio/color/serie/manilla por filtro) con preview de precio antes de aplicar y deshacer por retiro — nunca un camino paralelo. Vive en toda revisión DRAFT (posiciones de `preparation` o del detalle del proyecto); con precios aplicados queda bloqueado con la causa declarada (`commercial_revision_required` es el contrato del PUT de posiciones), y 0 aplicadas ⇒ aviso de fallo honesto, nunca éxito falso. Sólo las filas validadas por el batch preview del motor se aplican.
- Verificado: `make lint|typecheck|test|build` verdes (`PY=.venv/bin/python`); `make test-db` con fixtures actualizados a la compuerta; capturas `docs/redesign/captures/p08-emision/`; decisiones sección P08 de `valores-por-defecto.md`.

## ED2 pase editorial de la ola 2 state

Merged into `integracion/v1` as squash `26757d403f29f446b1f6a934690a636a0a82c575` (dekopen PR #58):

PR sobre `integracion/v1` (branch `devin/ED2-pase-editorial-ola2`); encargo sin funcionalidad nueva — corrección, unificación y pulido del conjunto, con foco en las superficies de la ola 2 (compras, producción/CNC, cotización, proyectos, portal, asistente) y continuidad con las decisiones vinculantes de ED1:

- **Vocabulario en una voz**: `typologyLabel`/`colorLabel` compartidos en `i18n/es-CL.ts` (los mapas por superficie se eliminaron — «Abatible» se lee igual en proyecto, OT y portal); `enumI18nKey` cubre los enums sin `<StatusChip>`; los mapas CAPS `orderStatusLabels`/`orderTypeLabels` y las claves `purchasing.*` en mayúsculas se borraron — OrderStatusEnum/OrderTypeEnum van por StatusChip+domainLabels (patrón ED1), al igual que `CollectionReminderSendResponseStatusEnum` (jobs) y el contexto `DEFAULT`→«Predeterminada» de pricing.
- **Formato §3.3 cerrado**: `fmtQty` agrupa miles con espacio fino (`50 000`); `quantize` (BigInt, half-up) formatea `fmtPct`/`fmtWire` → guard `ui-tofixed` en 0 en producción; `order.expected_at` viaja por `formatDate`; plurales reales barra/plancha/retazo.
- **Fuga backend saneada**: `_declared_gaps` (CNC) emite `declared_offsets_mm` como lista — el `repr` Python `['300.0000', …]` ya no llega a la UI; `plan_seed` va por `shortTechnicalId` y `required_tool_ids` por `tOptional`.
- **Sistema de capas y veladuras**: `--z-raise`/`--z-raise-top`/`--z-menu` completan la escala; los 8 literales de `z-index` migran a tokens. `--scrim-overlay` es el único scrim (overlay, rail móvil, `::backdrop`); el override oscuro duplicado se eliminó.
- **Contraste y slop**: todos los textos warn/persona usan la variante `-ink` (AA); el skeleton pierde el shimmer (`ui-sheen`, `--theme-skeleton-sheen` y la huérfana `--surface-active` borradas); `ui-empty-inline` unifica tres clases de estado vacío idénticas; `ui-button--primary` es la única acción principal; peso 800 residual → 600.
- **Espaciado por escala**: ~1.300 literales px/rem → `var(--space-*)`/`var(--r-*)` (exacto o vecino ≤30 %) en ~35 hojas; ~420 fallbacks `var(…, Npx)` muertos eliminados.
- **Guards**: baseline regenerada a 1 sola regla (`ui-motion>280` = 21: orb/spinners legítimos); raw-status, toFixed, empty-state slop, spacing literals, z-index literals, scrims duplicados y hex inline quedan en 0.
- **Rutas auditadas**: `ux:capture` cubre `production-order`, `production-order-blocked` y `quotations`; `deliveries` se captura como manager (rol correcto).
- Verificado: `make lint|typecheck|test|build` verdes (`PY=.venv/bin/python`; engine 714, backend 1301, frontend 692); capturas antes/después en `docs/redesign/captures/ed2/`; decisiones en sección ED2 de `valores-por-defecto.md`.
- **Ronda de verificación UI** (grabación sobre fixture): corregidos `changesRequested` crudo (clave `quotations.state.changesRequested` + tono person), `REV-A` → `formatRevision` en cotizaciones/pipeline/tablero/precio/traza, y orden de cascada del bloque táctil OT (al final de `production.css`; el input «Buscar pieza» quedaba en 32 px). Re-capturas afectadas con 0 findings.

## P21 hub del proyecto: centro de trabajo del estimador

Merged into `integracion/v1` as squash `51e2c87cbbb0a0bef37999d724a8d0cdbb3ebfbb` (dekopen PR #60):

- `/projects/<id>` es ahora un hub de 8 pestañas (`ProjectHub.tsx`): Posiciones (predeterminada) · Servicios · Cotización · Precio · Cobranza · Producción · Documentos · Actividad. Los paneles de la ola 2 (`ProjectQuotationPanel` P08, cobranza P11, precio P07, servicios D06, documentos, actividad) se montan como pestañas sin reescribirse; la pila de acordeones anterior se eliminó completa. `?tab=<id>` es canónico; `?section=quote|services|payments|imports|compare` sigue resolviendo vía `SECTION_TO_TAB` para enlaces antiguos de «Hoy»/campana.
- Encabezado: código+ nombre, cliente enlazado, obra/dirección, stepper del ciclo comercial, total con IVA + vigencia, y UNA acción siguiente por estado (`projectNextAction`: borrador → añadir/cotizar/emitir; cotizado → compartir o «esperando respuesta» si el enlace sigue vivo; aprobado → abono/saldo/liberar según rol; en producción → ir a producción). Roles sin permiso ven encabezado honesto sin CTA muerto.
- Posiciones (`ProjectPositionsTab.tsx`): grilla con render real del producto (thumbnail del canvas) o lista densa de 12 columnas (`?vista=`), agrupación `?grupo=ubicacion|tipologia|sistema` con contador plural-real, columna Estado derivada (`positionStatusKey`: borrador→evaluada→con precio→congelada→en producción — nunca columna nueva), columna «falta» honesta vía `positionIssues`.
- Edición en fila: medidas ancho×alto por posición (Enter/blur confirma, Escape revierte) vía `set_total_width`/`set_height` sobre el árbol paramétrico + PUT con candado optimista; cantidad igual. Tipologías no decodificables declaran la limitación.
- Lote: checkbox/roving-tabindex → barra con Duplicar, Cambiar ubicación, Cambiar cantidad, Cambios globales (§8 con preview Δ costo del motor y deshacer), Eliminar — cada acción muestra progreso `done/total`.
- Reorden: nuevo `POST /api/v1/positions/<id>/move/` `{to_index, expected_updated_at}` porque `position_index` no es escribible por PUT; UI = `Alt+↑/↓` o botones Subir/Bajar en la lista sin agrupar. Sin arrastrar-y-soltar (el orden es folio impreso).
- Pestañas perezosas: los paneles se montan al primer uso y quedan montados ocultos — tests/e2e navegan con `role="tab"` clic.
- Backend nuevo cubierto por pgTAP/RLS + tests de integración del move (permiso, orden, candado); la ruta entra en el allowlist de `test_openapi.py`.
- Verificado: `make lint|typecheck|test|build|test-db` (`PY=.venv/bin/python`); e2e auth+projects verde contra stack real; ux:capture 48 tomas 0 hallazgos; capturas `docs/redesign/captures/p21-proyecto-hub/`; decisiones en sección P21 de `valores-por-defecto.md`.

## P10 portal de propuesta v2 state

Merged into `integracion/v1` as squash `__P10_MERGE_SHA__` (dekopen PR #`__P10_PR_NUM__`):

Abierto en la rama `devin/P10-portal-v2` (PR pendiente sobre `integracion/v1`, merge SHA `__P10_MERGE_SHA__`); verificación en HEAD de esa rama:

- **El portal es del fabricante, no de DEKOPEN**: header con logo (`brand_logo_url`), razón social, RUT y contacto del emisor siempre visibles — también en las páginas de estado; `document.title` y favicon toman la marca; «Generado con DEKOPEN» sólo aparece si `doc_dekopen_credit` sellado lo permite (`dekopen_credit` en la respuesta). `--theme-accent` se recalcula con `brand_color` y `--theme-accent-onfill` con `brandOnFill` (misma curva sRGB que `documents/brand.py`); la marca como TEXTO usa `--theme-accent-ink` porque brand_color oscuro falla AA en tema oscuro.
- **Estados honestos con 200**: `portal_quote.state` ∈ live/approved/declined/changes_requested/superseded/validity_expired/link_expired/revoked/unavailable — `superseded` se evalúa PRIMERO (un link revocado porque su revisión fue reemplazada dice «reemplazada», no «revocada»); cada estado tiene página dedicada con causa y contexto del emisor; `quote_not_found` sigue 404 con página propia. Reemplazada/expirada con revisión vigente exponen `follow_available` + `POST /portal/quotes/{token}/follow/` que minta un link `channel=FOLLOW` (cap 5) a la revisión vigente — «Ver la cotización vigente» navega al token nuevo.
- **Decisión con evidencia válida**: aprobar exige nombre + RUT módulo 11 (`rut_mod11_valid`) + checkbox con el literal «Acepto la propuesta COT-…-REV-B por $X IVA incluido y sus condiciones»; solicitar cambios exige comentario; rechazar con motivo opcional. La evidencia (`decided_rut`, `decision_ip`, `decision_user_agent`, `acceptance_text`, `decision_revision_code`, `decision_bom_hash`, `decision_positions`) se persiste en `customer_approvals` y queda inmutable por trigger `guard_approval_decision_terminal` (42501 `decision_evidence_immutable`); `customer_approval_events` (append-only) registra VIEW/DECISION/FOLLOW; `list_approvals` la expone al estimador y `quotes_changes` alimenta la atención P03.
- **Pago gateado y honesto**: `payment.payable` exige aprobada + vigente + no reemplazada + CLP + saldo>0 + proveedor (o `FLOW_WS_MOCK`); la razón de bloqueo viaja declarada (`unsupported_currency` para USD — el CTA no existe, no falla). `POST /portal/quotes/{token}/pay/` reutiliza o minta link con `payer_return_url=/cotizacion/{token}`; el retorno Flow aterriza en el portal con estado resuelto («Pagado»/«Abonado parcial» con recaudado y saldo); `GET /portal/payments/{flow_token}/` resuelve el retorno genérico. Sobrepago rechazado en backend (`payment_exceeds_balance`).
- **Alternativas estructurales**: `project_positions.is_option` — el pricing las precifica pero las excluye del total (`deal_cost_net`/`option_indexes`), se sellan en `position_inputs` y DOC-01 las dibuja en «Alternativas — no incluidas en el total»; en el portal van en su propia sección ámbar fuera de la suma, con Δ de precio vs la incluida equivalente.
- **Portal v2**: hero (render + tipología + medidas), suma de líneas = total del header verificada en e2e con el proyecto de 12 posiciones (vitrina) y con el proyecto chico (vigente — la deriva de redondeo por línea se absorbe en la línea mayor, como el ajuste del SII), selector de vista Comercial/Técnica, zoom lightbox con pan táctil, posiciones expandibles con medidas/cantidad/specs/unitario/total línea IVA incluido, condiciones del documento, comparador A/B de alternativas.
- pgTAP `185_p10_portal_v2` cubre `is_option`, evidencia inmutable, eventos append-only, `payer_return_url`, grants; e2e `portal.spec.ts` cubre los 10 escenarios (vigente, decisión, evidencia pública, estados, seguimiento, no encontrada, ciclo de pago simulado, USD, móvil 390, axe). Contrato a11y del canvas: dim deshabilitada = `role="img"`+`tabindex="-1"` (axe + spec del editor).
- Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`; pgTAP 1147, integración 281, e2e 34/34); capturas `docs/redesign/captures/p10-portal/` (80 shots, 0 findings); Lighthouse móvil 80 (perf, build de producción; a11y 100, bp 100, seo 92); decisiones en sección P10 de `valores-por-defecto.md`.

## P22 clientes, empresa y ajustes state

Merged into `integracion/v1` as squash `b6b18f0aa29f483283a3516ee986a8f0a0a894dc` (dekopen PR #61):

PR sobre `integracion/v1` (branch `devin/P22-clientes-ajustes`): la configuración que hace real lo demás — ficha de cliente completa y Ajustes agrupados por dominio con permisos por rol.

- **Clientes**: lista con búsqueda por nombre/RUT/correo y filtro (todos, persona, empresa, con saldo); ficha con persona natural o empresa, RUT validado módulo-11, giro, contactos con rol (reemplazo total por guardado), direcciones de obra múltiples, proyectos del cliente, cotizaciones, pagos con facturado/cobrado/saldo, documentos emitidos y bitácora de notas append-only con autor y fecha. `clients.notes` migró a `client_notes` (backfill con autoría del `created_by`).
- **Duplicados y fusión**: `GET clients/duplicates/` agrupa por RUT canónico; `POST clients/merge/` repunta proyectos, cotizaciones, pagos, documentos, contactos y notas al sobreviviente en una transacción y deja auditoría en `client_merges` (actor, timestamp, payload). El duplicado queda `merged_into` + inactivo. Grant excepcional: `UPDATE (client_id)` a nivel columna en `client_notes` — el cuerpo sigue append-only (REVOKE de UPDATE/DELETE tabla).
- **Ajustes por secciones**: `/settings/:section` con nav lateral; `SECTION_KEYS = general, empresa, usuarios, comercial, documentos, numeracion, produccion, integraciones, plan`. Secciones de encargos no mergeados deshabilitadas con «Disponible cuando…». `usuarios`/`plan` bloqueadas para no-OWNER (`settings.lockedOwner`).
- **API org-settings por dominio**: `backend/projects/org_settings.py` — snapshot `GET /organization/settings/` + PUT por sección (`company`, `commercial`, `documents`, `workshop`, `branding`) más `document-preview` (vista previa real con el `_CSS` del PDF) e `integrations` (estado Flow/SII/correo/IA sin exponer secretos). Roles: lectura OWNER/ESTIMATOR/WORKSHOP_MANAGER, escritura OWNER/ESTIMATOR, miembros solo OWNER.
- **Usuarios y roles**: invitar por correo con rol, cambio de rol, desactivación; `claim_own_invitations` en `AuthMeView` auto-reclama invitaciones al entrar.
- **Comercial**: moneda (`OrgCurrencyEnum` — renombra el `CurrencyEnum` anterior a `PricingCurrencyEnum` para pricing), IVA, vigencia por defecto, condiciones plantilla (`doc_terms` con `pago`/`garantia`), banda de margen min/max y `approval_threshold` (nuevo campo `discount_state`, default 0,10) — `null` = mantener valor.
- **Numeración**: folios por tipo en solo lectura (la secuencia es autoridad de P02, no se edita).
- **Onboarding**: paso «Ajustes» (índice 1) tras identidad — Empresa + Comercial + Documentos con defaults §11 editables (Carta, anticipo 50 %, vigencia 15 d, IVA 19 %, margen 35 %/25 %, pie DEKOPEN oculto). Etiquetas de paso acortadas (overflow-x a 8 pasos).
- **Vista previa documental**: `render_document_html(..., embed_fonts=True)` embebe los Plex TTF como `data:` solo en el HTML de pantalla — el `<iframe>` no puede leer `file://` del servidor; el PDF sellado sigue con `_url_fetcher` congelado. Mismo patrón en `org_settings.document_preview` (`_CSS_EMBEDDED`).
- **Migración** `20270220000000_p22_clientes_ajustes.sql` + pgTAP `183` (27 asserts); guard `to_regclass('auth.users')` en el backfill DO para pg vainilla.
- Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`); pgTAP 1162, integración 281, e2e 27/27, pg16 vainilla limpio, vitest 692; ux:capture 72 shots 0 hallazgos (corregidos enums crudos en estaciones, `file://` de fuentes en preview, overflow del stepper); capturas en `docs/redesign/captures/p22-clientes-ajustes/`; decisiones en sección P22 de `valores-por-defecto.md`.
