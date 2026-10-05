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

- `system_family` (CASEMENT / SLIDING / LIFT_SLIDE / DOOR / FACADE_FIXED) separa familias de fabricación; `allowed_openings` deriva las tipologías habilitadas y el motor rechaza con `IncompatibleTypologyError` una tipología que no pertenece a la familia (corredera en abatir, p.ej.).
- Roles de perfil completos (SLIDING_SASH, INTERLOCK, RAIL, DOOR_SASH, FRAME_EXTENSION, SILL, COVER_TRIM, SKIRT) con reglas de corte y refuerzo como datos; `screws_per_meter` del acero genera fittings `REINFORCEMENT_SCREW` (TORNILLO-4X16) agregados en la BOM y costeados por `fitting_purchase_mappings`.
- `system_typology_limits` por sistema × tipología con fuente (`data_provenance`: SEED_SYNTHETIC / MANUAL / IMPORT / LEGACY_UNVERIFIED; IMPORT marca revisión pendiente); fila ausente = sin verificación, nunca rechazo implícito.
- Ingesta dual: plantilla XLSX/CSV manual (`backend/ingest/spreadsheet.py`, errores por fila en español) y candidatos IA convergen en la misma revisión humana; baja confianza → UNKNOWN y nada se publica sin confirmar.
- Catálogo DEMO enriquecido y marcado `is_demo`: DEMO_70 (PVC abatir), ALU_CORREDERA_70 (aluminio corredera) y DEMO_CORREDERA_60 (PVC corredera separada de DEMO_60 por la migración `20261229000002`, con matriz de juntas 24 mm JQ-CORR-10); los tres llevan `chamber_clearance_mm` y las 14 `inspector_rule_configs` que exige el freeze documental.
- Verificado: `make lint`, `typecheck`, `test` y `build` verdes; `make test-db` (pgTAP 940, integración RLS, e2e) verde tras contar los nuevos catálogos (59 artículos, 18 juntas, 84 configs inspector).

## [2026-10-05] D02 | vidrios de verdad

- `GlassComposition` estructurada (capas exterior→interior: láminas, intercapas PVB `+`, cámaras con gas) con notación ida-vuelta; `glass_products` persiste el stack JSONB y `project_positions.glass_composition` + `glass_review_pending` registran lo resuelto/UNKNOWN.
- Autoridad de espesor: la composición que resuelve `resolve_composition` gobierna siempre el paquete (`thickness_source="COMPOSITION"`); un `glass_thickness_mm` declarado que discrepa queda como `thickness_declared_mm` con aviso `GLASS-THICKNESS-MISMATCH` — deriva visible, nunca reescritura silenciosa.
- Derivados en motor: espesor total/neto, peso (2,50 kg/m²·mm lámina + 1,07 PVB), junquillo vía `glazing_bead_matrix`, corte luz − deducciones, área mínima facturable por producto y recargos (templado, canto pulido, perforación, palillaje) en `glass_price_lines`.
- Reglas NCh 135/2 como datos org (`glass_safety_rules`, `glass_type_limits`): WARNING avisa, MANDATORY bloquea; semilla `SEED_SYNTHETIC`+`review_pending`, texto oficial por ingesta D01 (hojas "Seguridad vidrio"/"Límites vidrio").
- Pedido al vidriero `orders/{id}/glass-order/?output=pdf|csv`: mm enteros, etiquetas `P{pos}-U{u}-I{i}`, QR, fusión `?orders=` de OT misma versión, piezas pendientes separadas.
- Selector de vidrio en canvas: modo básico (tarjetas compatibles) y avanzado (compositor de capas con validación en vivo y corte a escala); aviso NCh 135 en el vano exacto con alternativa de un click.
- Corregido en caliente: `?format=` es parámetro reservado de DRF (usar `?output=`); pgTAP `plan()` debe igualar aserciones; `NULL::numeric` para columnas VALUES vacías; el fixture legacy `4-12-4`+24mm quedó cubierto por la regla de autoridad de espesor.
- Comparación documental unificada: `documentary_canonical.numeric_collapsed` + `same_documentary_value` (los snapshots canónicos cuantizan `"16.00"` y los `model_dump` crudos guardan `"16"`); `documents` y `projects` delegan — sin esto, `start_successor` rechazaba con `revision_source_drift` 409 por la misma magnitud en doble formato.

## [2026-10-05] D04 | herrajes de verdad — clases por familia sistema×apertura

- Los kits de `hardware_kits` se convierten en clases: `class_label` ("estándar", "pesada") + restricciones declaradas (`max_aspect_ratio`, `min_stay_height_mm`) y `contents` con `qty_rule` (PER_WIDTH/PER_HEIGHT con min/max), `cut_rule` (eje −mm), `weight_kg`, `cost_clp` y `machining[]` por componente — todo como datos del catálogo.
- `hardware_families` declara la regla de altura de manilla (CENTERED / FIXED_FROM_BASE / RANGE con banda min/max/default) + `handle_model_options`/`handle_color_options`; `hardware_options` son las opciones vendibles por posición (kind + `price_delta_clp` + BOM de componentes).
- Motor: resuelve la clase más ajustada compatible (`_class_tightness`: peso admitido → envolvente; envolvente idéntica = `AmbiguousHardwareKit`), expande cantidades/largos, suma peso y costo, y valida restricciones nombrando clase y valor real; al fallar sugiere la clase siguiente con `delta_clp` o "dividir la bahía" con la clase más pesada (`failure_context`).
- `hardware_items` del BOM ahora lleva la selección sellada: `class_label`, handle model/color names, `option_skus/names`, `handle_height_mm`, `cost_clp`, `weight_kg`, `price_deltas` y `machining` — el documento sellado nunca re-consulta el catálogo.
- OT: `_work_order_payload` emite `hardware_picking` (líneas agrupadas sku+largo+option, qty×posición) y `hardware_machining` (ops declaradas por hoja; sin coordenadas → `DECLARED_NOT_EMITTED`, alimento para P14). Paridad OT-12-posiciones == suma del motor cubierta por test.
- Pricing: `price_delta_clp` es adendo de VENTA; fuente seleccionada sin precio → `PricingError('hardware_option_price_missing')`.
- Sellado: `_PIECE_ADDITIVE_KEYS["hardware_items"]` + `_HARDWARE_CONTENTS_ADDITIVE` y un nuevo era `era_d04` en `_calculation_identity_hashes` — snapshots previos siguen verificando.
- Ingesta: la plantilla D01 gana columnas/hojas de herraje (clases, familias, manillas, opciones) con test de ida y vuelta.
- UI: inspector "Herrajes" muestra clase resuelta + "¿Por qué este kit?" + kit override + manilla (modelo/color/altura con aviso fuera de rango) + opciones vendibles + tabla de componentes en "Avanzado"; documento al cliente solo lo vendible.
- Verificado: `make lint/typecheck/test/build` y `make test-db` verdes; OT real `OT-P-000014-REV-A-01` liberada en local con picking expandido (cierres ×3 por PER_HEIGHT, cremona cortada 1326 mm); capturas antes/después en `docs/redesign/captures/d04-herrajes/`; ux:capture scoped en rutas tocadas sin hallazgos nuevos.


## [2026-10-05] D03 | aperturas y tipologías de verdad

- Modelo real de apertura: `Opening{movement × hinge_side × direction × leaf_role × fixed_in_sash}`, `BayLeaf{slot, opening}` y `OpeningSpec{unit_kind, leaves}` en `models.py`/`openings.py`. El enum `opening_type` sigue aceptado una versión y mapea totalmente (`spec_for_legacy`/`legacy_openings_for_spec`); goldens migrados idénticos.
- 13 movimientos declarados (FIXED, TURN, TILT, TILT_TURN, TOP_HUNG, BOTTOM_HUNG, SLIDE, LIFT_SLIDE, PARALLEL_SLIDE, FOLD, PIVOT_V, PIVOT_H, VERTICAL_SLIDE); los seis últimos son declarados-only para D08 y corredera sigue por `sliding_layout`.
- `unit_kind` WINDOW/DOOR en el nodo superior de la unidad habilita hojas DOOR_SASH dentro de splits: puerta simple, doble (activa+pasiva con inversor/falleba) y puerta + lateral fijo sin columna de traslapo.
- `system_opening_capabilities` (migración `20261230000000`): capacidades por sistema movimiento×direcciones×roles×units×max_leaves con fallback de familia; el editor, la API y la IA solo ofrecen lo admitido y el rechazo nombra los sistemas que sí lo admiten.
- Manilla derivada por hoja vía política de herrajes (lado de cierre, activa sola en francesa, altura `handle_height_mm` del sistema/kit editable); herrajes por hoja en grupos normalizados incl. FALLEBA e INVERSOR con autoridad de compra/acero.
- Simbología DIN por vista según `_contrato.md` §9 en `documents/renderers.py` (`_spec_leaf_glyphs`), `ProductFrontSvg` y `OpeningGlyph`: continuo = hacia el observador, discontinuo = se aleja; puerta = arco desde la esquina de bisagras + umbral bajo hojas operables; fijo sin glifo.
- Nombres es-CL "<movimiento> hacia <dirección> — bisagras a la <lado>" + propios ("Francesa 2 hojas — activa derecha", "Solo abatimiento (banderola)"), generados por el motor y espejados en `domainLabels`.
- Verificado: `make lint|typecheck|test|build` y `make test-db` verdes (`PY=.venv/bin/python`); goldens idénticos al migrar + goldens nuevos por tipología; test de capacidades nombrando sistemas; 18 capturas técnicas 1440×900 en `docs/redesign/captures/d03-aperturas-tipologias/`.


## [2026-10-05] D07 | del vano de obra a la medida de fabricación

- Encargo D07 (ola D2): del vano de obra a la medida de fabricación, ejecutado en branch `devin/D07-vano-fabricacion` sobre `integracion/v1`.
- `mounting_rules` como autoridad versionada inmutable (org NULL=global): 5 tipos de montaje con ajustes firmados por lado + ensanches + fijaciones; seeds `SEED_SYNTHETIC`+`review_pending`. Sembrado doble: migración (sistemas existentes) + `seed.sql` (sistemas del seed) — pgTAP corre antes del fixture.
- Posición con registro del vano (1–3 puntos/eje, muro, escuadra), regla validada por trigger (`mounting_rule_scope_mismatch`), fijación manual y estado de medida con sello CHECK; endpoint `measurement-confirm` para confirmar/reabrir.
- Motor `resolve_fabrication`: menor de los puntos, aviso de descuadre sobre tolerancia org (`vano_spread_tolerance_mm`, default 10 mm), desglose "Vano − holgura = fabricación", fuente DERIVED/MANUAL_LOCK/DECLARED.
- Producción no se libera con medidas sin confirmar (`measurement_not_confirmed`); `measurement_state` entra al diff documental del sucesor para la revisión con Δ.
- UI: sección "Vano y montaje" en el inspector con preview debounced, chip compuesto en el encabezado de posición, cota doble vano+fabricación en el lienzo con letreros "Holgura"/"Solape" por lado, Ajustes gana "Reglas de taller".
- Verificado: `make lint|typecheck|test|build` y `make test-db` verdes; 14 goldens engine + pgTAP 177 (16 ok) + integración confirm/gate/revisión; capturas en `docs/redesign/captures/d07-vano-fabricacion/` (pendiente de carga al PR).
- Decisiones nuevas registradas en `docs/decisions/valores-por-defecto.md` sección D07.

## [2026-10-05] D05 | colores y acabados de verdad

- Catálogo real de color por sistema: `system_color_options` (kind, manufacturer_code, gloss, render_color/texture, finish_class, faces, pair_code, size_factor, dark, surcharge_*, provenance) + `profile_systems.bicolor_allowed`; seed `SEED_SYNTHETIC`, RAL reales vía ingesta D01.
- Bicolor por posición: `project_positions.color_exterior`; preimagen canónica lo elimina cuando NULL/igual al interior (hash monocolor intacto). Reglas del motor en `finishes.resolve_color_selection`: cara prohibida, bicolor solo si permitido, ANODIZED nunca bicolor, dos colores en masa nunca en una barra, `pair_code` en ambos sentidos — mensajes es-CL nombrando acabado y cara.
- Reglas por acabado como datos: `film_clearance`/`finish_class` conectan refuerzo obligatorio y mecanizado con D01; `size_factor`/`dark` acotan la envolvente; `surcharge_kind` (metro de perfil / m² / fijo por posición / % materiales) lo computa el motor.
- SKU por color: `stock_color` clavea código o par `EXT/INT` en `profile_purchase_mappings`; NULL = barra legacy agnóstica; dos barras viables = `AmbiguousStockAuthority`. Seed genera todas las claves válidas vía CROSS JOIN espejando las reglas del motor.
- Render real por cara en 2D (canvas comercial, SVG técnico), 3D (cara exterior nogal-madera sin rosa / interior blanco), portal y PDF; `finish_label` sellado "Nogal exterior / Blanco interior" viaja en el resultado sellado.
- Selector `ColorSelector`: swatches reales, "Igual en ambas caras", resumen + recargo, issue con nombre. Fix: el checkbox era indesmarcable (sameFaces se derivaba de la igualdad; desmarcar exige exterior distinto — se inicializa con la primera opción válida).
- Readiness: la sonda de compra usa el color base declarado (primer finish_class='WHITE' faces='BOTH' del dominio; NATURAL en aluminio) en vez de 'WHITE' fijo.
- Verificado: lint/typecheck/test/build y `make test-db` verdes (pgTAP 970); 24 capturas en `docs/redesign/captures/d05-colores-acabados/shots/` (selector, bicolor, editor 2D, 3D ambas caras, posición guardada) a 1440/1280/1024 claro+oscuro. Nota: a 1024px el fieldset de cabecera ocluye el botón "Vista 3D" (defecto de layout preexistente, documentado).


## [2026-10-05] IA2 | operaciones y herramientas de la IA

- `ops_registry.py` (36 ops tipadas product/position/project + `prepare_*`) es la única fuente: `ops_contract()` → OpenAPI → `opsContract.generated.ts`; UI, API e IA comparten el mismo vocabulario — `check_generated_api` vela la paridad.
- `_validate_ops` devuelve `(accepted, rejected, simulation)`; `declared_strict` separa lo que debe citarse en el prompt (decisiones semánticas como `parts`) de los derivados que el motor calcula — un número derivado correcto ya no se rechaza.
- Herramientas del motor para el modelo: `calculate_position`, `validate_position`, `price_position`, `price_project`, `explain_price_delta`, `list_catalog_options`, `get_blockers`, `simulate_ops` (`ai_gateway/tools.py`); el contexto proyecta sistemas (`{id, code, family}`), precios por posición, diff de revisiones, barras de corte, pesos y bloqueantes.
- `clarify {question, options[]}` tipado: el panel muestra chips y el chip reenvía `<prompt> — <etiqueta>` por el mismo canal (E08 verificado); la previsualización lista ops + simulación y un solo "Aplicar" ejecuta la transacción.
- Paridad UI: `assemblyCommands` coacciona `parts` y emite specs completas; `starterDesign` autocompleta vidrio solo con opción única (convención del editor); el agente marca "Aplicado" solo sin fallos.
- Tres hallazgos reales corregidos en e2e: el contexto del proyecto no proyectaba sistemas (`add_position` sin `system_id` citable), el starter no llevaba vidrio (400 del motor al crear posición) y la proyección de aperturas perdía el alias `legacy` (`set_opening` rechazado `apertura_inválida` pese a estar en el glosario).
- Prompt es-CL versionado en `projects/design_prompt.py` (glosario + convenciones + ejemplos generados desde el registro); límites por job 20 pasos/6 consultas/6 rondas + timeout con `job_metrics`.
- Migración `20261230003000_ia2_mimo_wire_model.sql` fija `mimo-v2.6-pro` en `ai_routes`. Evals: MOCK 26/26 con 0 ops rechazadas; MIMO 0/26 `proveedor_error` (429 — cuota externa agotada, documentado en `docs/ai/evals/README.md`).
- Verificado: `make lint|typecheck|test|build` y `make test-db` verdes; e2e E02/E04/E08/J02 en navegador real con capturas `docs/redesign/captures/ia2-asistente/`; ux:capture scoped sin hallazgos nuevos en las rutas tocadas.
