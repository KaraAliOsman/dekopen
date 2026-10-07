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

## [2026-10-05] D06 | accesorios y extras de verdad

- `ExtraArticle` + `ServiceArticle` como datos de catalogo/org (migracion `20261231000000_d06_extras.sql`): kinds de corte (SILL/FRAME_EXTENSION/COVER_TRIM/SKIRT, `origin=EXTRA` en plan de corte y OT) y contados (MOSQUITO_SCREEN/VENTILATOR, `bom.fittings`), predicados `families`/`unit_kinds`, `suggestion_reason` como acompanante con causa, plantillas org por sistema/proyecto.
- Motor `extras.py`: medicion geometrica — vierteaguas = corrido inferior exterior continuo + `vuelo` por extremo (1500+30+30 → 1560 mm en 1 corte; columnas interrumpidas = tramos aparte), sided = lados exteriores declarados, contados = hojas operables (override `qty`), servicios = unidades/m2/ml perimetro/cargo unico. `merge_extra_templates` agrega sin pisar selecciones; `bom.extra_lines` (cantidad x precio = total) suma exacta del total de posicion.
- Pricing: `service_lines` en el resultado sellado (servicios incluidos en el neto, no doble cobro); extras contados pasan el gate `fitting_purchase_mapping_missing_or_ambiguous` del congelado — `seed.sql` siembra mappings globales para articulos contados globales.
- UI: "Extras de la posición" en el rail Vista general del editor (vuelos/lados/cantidad, sublineas del motor, sugerencias aceptar/descartar, preseleccion de plantillas en vano nuevo), "Servicios del proyecto" como `<details>` perezoso en la pagina del proyecto, tarjeta "Accesorios y servicios" en Ajustes (`extras_display` + plantillas).
- DOC-01: sublineas EXTRA por posicion y bloque `.service-lines` propio — antes el parrafo dentro de la columna `.doc-duo` irrompible se recortaba en silencio al desbordar pagina (bug hallado renderizando la REV real); `extras_display` DETAILED/GROUPED de la org gobierna el detalle.
- Errores corregidos en caliente: BOM renderizaba `kind` crudo (MOSQUITO_SCREEN) — ahora `assembly.fittingKind` con fallback `catalog.extraKind`; identidad de piezas con `numeric_collapsed` para no romper el binding `"1500.00"` ≡ `"1500"`.
- Hallazgo E2E corregido: en vanos de un solo módulo `designPayload()` plegaba a la forma clásica (IntentNode pelado) y `product.extras` se perdía al guardar — ahora una posición simple CON extras persiste como `product-v2`, y `pickStarter` conserva `extras` al cambiar de starter (antes borraba las declaradas por plantilla).
- Verificado: lint/typecheck/test/build verdes, `make test-db` (pgTAP + integracion + e2e), goldens vierteaguas/instalacion-ml, 30 capturas antes/despues (incl. 2 paginas DOC-01) en `docs/redesign/captures/d06-accesorios-extras/`, ux:capture sin hallazgos nuevos.

## [2026-10-05] IA3 | proveedor de IA real

- Encargo IA3 (ola D2): proveedor de IA real confiable y con costo controlado, branch `devin/IA3-proveedor-real` sobre `integracion/v1`.
- Transporte: reintentos acotados en transitorios (default 2, cap 4, backoff exponencial + Retry-After), timeout por ruta, tool calling nativo con fallback a JSON estricto una sola vez, `tools_enabled` por ruta.
- Durabilidad: `ai_invocations` registra cada llamada post-commit/post-rollback; `est_cost_usd` sellado con la auditoría; presupuesto mensual por org con `ai_budget_exceeded` suave.
- MiMo repineado `mimo-v2.6-pro`; sonda: cuota token-plan agotada (429 en 26/26 evals) — pendiente credencial pay-as-you-go para la verificación real, causa exacta en el PR.
- OWNER: Ajustes › IA (estado, modelos, probar conexión, presupuesto, consumo); /jobs gana panel Actividad de IA filtrable; miembros ven badge "Modo de prueba" cuando MOCK sirve; el agente reporta fases (contexto/modelo/propuesta) al Orb.
- Decisiones en `docs/decisions/valores-por-defecto.md` sección IA3; config en `.env.example` + `docs/operations/AI_PROVIDERS.md`.

## [2026-10-06] P25 | marca e identidad visual

- Encargo P25 (ola 1): identidad completa DEKOPEN — marca «La sección» (anillo 24×24, alma 2→1/3) como `SECTION_PATH` canónico, wordmark con O-marca, DocLockup «La cota», favicon auto-tema por media query, iconos + manifest.
- Acceso/onboarding = hoja técnica (papel sobre mesa, marco con inglete, una acción por hoja); `ui/Stepper` corregido (is-done/is-current/is-blocked).
- Outbox de correo `mail_messages` + 5 plantillas transaccionales es-CL + providers sandbox/smtp + jobs `mail.*` emitidos in-transaction + `/dev/correos` dev-only; white-label `brand_color` AA-validado con fallback teal-800 aplicado a DOC-01/portal/correos desde el snapshot sellado; `doc_dekopen_credit` opt-in.
- `EmptyIllustration` (5 láminas técnicas) en EmptyState + 404/500/sin conexión; Orb recoloreado cyan→teal en tokens.
- Bugs hallados verificando en vivo y corregidos: `projects.currency` inexistente en `_project_mail_row` (JOIN a org), DRF `Response` sobre PNG → 500 (ahora `HttpResponse`), `DocumentaryError` transitoria → `JobPermanentError` en handlers `mail.*`.
- Verificado: `make lint|typecheck|test|build` + `make test-db` verdes (`PY=.venv/bin/python`), entrega real `SENT sandbox` con color de org en `html_body`, capturas en `docs/redesign/captures/p25-marca/` y `.../marca/`; decisiones en sección P25 de `valores-por-defecto.md`.

## [2026-10-06] P05 | dibujo técnico: geometría de glifos y cotas

- Contrato de simbología único (`engine/.../opening_symbols.py` + gemelo `frontend/.../openingSymbols.ts`): `leaf_primitives`/`sliding_primitives` emiten primitivas simbólicas (`tri`/`arrow`/`handle`/`sill`/`none`), `glyph_paths` las convierte en `d` canónicas; 14 fixtures JSON congelan ambos lados por caso × vista (paridad exacta, divergencia rompe ambos tests).
- `SlidingPanel.travel` (LEFT|RIGHT) declarado por hoja móvil; `validate_sliding_layout` rechaza viaje hacia jamba sin espacio y rieles compartidos entre móviles adyacentes; `panel_travel` resuelve la convención documentada y `inferred` marca "dirección inferida" en toda superficie.
- Vista declarada: `view` interior/exterior en el editor (selector + espejo de lámina, mobiliario sin espejar, vista exterior de solo lectura); PDF declara "Vista interior" en toda figura; cotas enteras `tabular-nums` en canaletas fuera del dibujo; corte de planta corredera bajo el alzado (EXTERIOR/muro arriba, rieles numerados, flechas por slot).
- Puerta en alzado = triángulos + umbral naranjo bajo toda hoja no fija (el arco de barrido solo existe en planta); DOC-01 técnica dibuja el corte de planta por bay corredizo.
- `ui/icons.tsx` `OpeningGlyph` ahora dibuja el contrato real (antes era una aproximación a mano al 50 %); `SignatureSection` de /dev/ui lista el vocabulario completo.
- Decisiones registradas en `docs/decisions/valores-por-defecto.md` (sección P05); contrato en `docs/PRD/opening-symbols.md` con ilustraciones generadas por el engine.

## [2026-10-06] P02 | identificadores humanos y formato §3.3 en toda la app

- Encargo P02 (ola 1): cada entidad nombrable en voz alta gana código humano estable y todo número visible sigue la tabla §3.3; ejecutado en branch `devin/P02-identificadores-formato` sobre `integracion/v1`.
- `private.next_human_code(org_id, kind)`: contador por org bajo `pg_advisory_xact_lock` → `OC-######` (órdenes de compra nuevas; selladas pre-P02 conservan `PO-`), `RT-######` (retazos), `REC-######` (recepciones). `private.guard_human_code` (BEFORE UPDATE, 42501) sella `order_code`/`remnant_code`/`receipt_code`. Política de huecos documentada: rollback libera el lock y el folio no persistido se reintenta; nunca se recicla en otra fila. Backfill determinista por `created_at`; pgTAP `179` (21 aserciones) + `146` con folios obligatorios.
- Identidad de pieza `P{pos}-U{u}-M{i}`/`-I{sec}`: única forma visible en HTML del paquete de corte, `bars.csv`, `sheets.csv`, DXF y etiqueta QR; `dxf._placement_code` conserva `-U{n}` cuando el resuelto ya lo trae. Test de igualdad entre artefactos.
- Barrido §3.3: backend `documents/renderers.py` (mm espacio fino, coma decimal, CLP, dd-mm-aaaa, huella 8-hex sólo en pie/cajetín) y frontend `format.ts` + `<EntityCode>`; la frontera de edición usa `fmtMmCanonical` (punto, sin agrupación — `fmtMm` en inputs rompía el parse); CSV/DXF quedan canónicos/ASCII para round-trip; QR conserva 16 hex.
- Búsqueda por código: CommandPalette y `search/service.py` resuelven OC-/RT-/REC-/OT-/P## (grupos nuevos remnants/receipts con `remnant_code`/`receipt_code` en payload y QR `DEKOPEN|REMNANT|RT-…`).
- Tests: concurrencia (dos workers → folios consecutivos distintos, orgs independientes, rollback), render sin hex≥10/`.0000`/`%`>1dp en _doc01/02/03/06/07, igualdad de etiquetas pieza; `make test-db` y `lint|typecheck|test|build` verdes (`PY=.venv/bin/python`); e2e `canvas.spec.ts` ajustado a `1 006 mm` (espacio fino).
- Aprendizaje: `django_db(transaction=True)` en tests de integración vacía el esquema Supabase real (sin migraciones Django) — usar `django_db_blocker` + autocommit; normalización de whitespace de `getByText`/`toHaveText` (U+2009→espacio) obliga a expectativas con espacio simple.

## [2026-10-06] P04 | editor canvas-first: layout e interacción

- Editor reestructurado a superficie canvas-first: franja 48 px (migas, ubicación, cantidad, chips Serie/Acabado en popovers, estado de guardado, undo/redo, `LivePriceChip`, "Qué falta", Guardar), riel de herramientas etiquetado con flyout "Biblioteca de diseños" (`TypologyFlyout`, 15 starters agrupados filtrados por `openingOptionAdmitted`), lienzo central (fit-on-open, wheel zoom-at-cursor, pan acotado + F), inspector 320–360 px y dock colapsable (Árbol/Vanos/Materiales con el BOM siempre montado).
- Interacciones: doble-click abre el picker de apertura anclado al módulo (ancla proyectada vía `viewRef`), edición de cotas inline Enter/Esc, atajos `V`/`|`/`-`/`Ctrl+Z`/`Ctrl+Y`/`Supr`/flechas 1 mm (Shift 10)/`F`/`?`, `MeasureLayer` y `ProposalGhost` (§8, propuesta fantasma con Δ de precio vía `design_batch_preview`).
- Backend: `design_batch_preview` admite `position_id` nullable + campos neto para cotizar diseños no guardados; serializador, servicio, contrato y orval regenerados.
- Responsivo por `useMediaQuery`: ≥1280 completo, 1024–1279 riel icon-only + inspector drawer, <1024 vista de lectura con aviso.
- Correcciones de rúbrica en caliente: animación de precio pendiente 0,9 s violaba `ui-motion>280` → atenuación estática; `font-size 0,65rem` violaba `ui-font<11` → `--type-dense`; z-index literales → escala `var(--z-*)`; contraste AA del detalle del árbol y del readout del viewport en dark (muted 4,32:1) → `--theme-text-secondary`; el cuerpo del dock dejó de empujar el lienzo (overlay flotante) para mantener ≥75 % de alto.
- Verificado: `make lint|typecheck|test|build` verdes; e2e `editor-canvas.spec.ts` 7/7 + `projects.spec.ts` adaptada (10/10 total); ux:capture `p04-editor-canvas` sin hallazgos nuevos vs baseline (18 preexistentes de glifos/strip, alcance P05); decisiones en `docs/decisions/valores-por-defecto.md` sección P04.

## [2026-10-06] P09 | DOC-01 propuesta comercial v2

- Reescritura del documento comercial en `documents/renderers.py::_doc01` (rama `devin/P09-doc01-propuesta`): portada condicional (>6 grupos o >12 unidades) con hero del renderer real, tabla resumen de anchos fijos con thead repetido, detalle por densidad (ficha completa / compacta / mini-tabla con miniaturas), resumen comercial reconciliado al motor, aceptación con QR.
- Firma del documento: campos `Campo N` por DFS de bahías (misma `_opening_labels` que el editor P05), cadenas de cotas eje-a-eje por paño en el margen del dibujo, corte de planta sellado (`PlanGeometry`) para conjuntos/bow con INTERIOR abajo — los tres signature F1/F2/F11 se conservan (inglete, huella 8-hex en cajetín, sello de revisión).
- `share_quote` reordena mint → render → emit con dos canales: `customer_approvals.channel ∈ {EMAIL, DOCUMENT}` (migración `20261006000002`). El QR sellado en el DOC-01 lleva el token `DOCUMENT` — el artefacto es inmutable (`reject_immutable_evidence`, sin grant UPDATE/DELETE) así que re-renderizarlo por cada share era imposible; `share_quote` revoca sólo enlaces `EMAIL` al compartir de nuevo y mintea el `DOCUMENT` la primera vez que produce el slot. Lección: `document_artifacts` nunca acepta UPDATE ni DELETE — el diseño correcto separa el enlace efímero (correo) del impreso (documento).
- Ajustes de documento por organización: `doc_paper_size` (Carta/Oficio/A4 → `@page size` sólo DOC-01) y `doc_terms` (5 claves legales, vacío omite la línea — §7 «sin valores desconocidos») en migración 180 + serializers + openapi + `OrgBrandingCard`.
- Aprendizajes: `segno.make(...).svg_inline()` no acepta `line_color` (usa `dark=`/`light=`); el segno inline necesita `_Raw` o `mark_safe` en celdas de tabla; `_assembly_plan_strip` mapea `y - min_y` (los cantos traseros quedan arriba = EXTERIOR, la cadena frontal abajo = INTERIOR); `discount_pct` del motor llega como porcentaje humano (>1 ⇒ `/100`).
- Verificado: 38 tests PyMuPDF nuevos + contratos/portal verdes; `make lint|typecheck|test|build` y `make test-db` verdes (`PY=.venv/bin/python`); capturas `docs/redesign/captures/doc01-v2/` (portada, resumen, detalle, cierre); decisiones en `docs/decisions/valores-por-defecto.md` sección P09.
- No hecho: tabla de calendario de pagos con montos — no existe modelo de cuotas; el documento imprime `payment_terms` sellado (rubrica R-riesgo declarada en el PR).

## [2026-10-06] P03 | shell por flujo + Inicio «Hoy» por rol

- Encargo P03 (ola 1): barra lateral agrupada por flujo (Inicio / Ventas / Ingeniería / Operación / Asistente / Ajustes, plegable a icono+tooltip, secciones vacías ocultas por rol), topbar con migas de pan humanas + switchers org/proyecto + `Ctrl K` + campana de atención + ayuda `?`, y «Hoy» como cola ordenada por consecuencia (no dashboard).
- Backend: `GET /api/v1/today/` devuelve la cola por rol (ítem = frase + código de entidad + CTA + razón, urgencias `overdue/today/soon/when_free`); contadores solo si accionables y filtrados; vacío único «Todo al día». Búsqueda global cubre clientes, proyectos, cotizaciones, OT, OC (folios reales `OC-` minteados por `next_human_code` vía el flujo documental completo: eligibility→allocation→confirm batch) y retazos (remnant_code/SKU/rack/material/nota, path `/inventory`); `_INSTALLER_EXCLUDED_GROUPS` excluye grupos no visibles para INSTALLER.
- Matriz rol→nav espejo del backend: `AI_SURFACE_ROLES`/`hasAiSurface` replica `_AGENT_CALLERS`/`_JOB_READERS` (OWNER/ESTIMATOR/WORKSHOP_MANAGER) — OPERATOR e INSTALLER no montan Orb ni AskDekopen ni ven /assistant//jobs (OPERATOR antes recibía 403s en `/ai/*` en cada carga).
- Responsive: <1024 px el riel colapsa a drawer; destinos táctiles ≥44 px en `@media (max-width:1024px)` (rail-toggle, topbar, búsqueda, skip-link); 390 px usable para estimator+installer.
- Firma v1: Orb en topbar refleja jobs reales; cota-loader F3 en transiciones. Fixes de verificación: `overflow-x` 1503>1440 en settings-general (`.payments-form select` sin `max-width` — la opción más larga `Nombre · SKU · clase` desbordaba el documento); `touch-too-small` de chrome del shell; claves duplicadas `remnants` (residuo de rebase) en CommandPalette/es-CL.
- Verificado: `make lint|typecheck|test|build` + `make test-db` verdes (`PY=.venv/bin/python`, pgTAP 1044, integración 278 incl. `test_shell_p03.py` — OC real, aislamiento tenant, exclusión INSTALLER); capturas 5 roles ×1440/390×claro/oscuro en `docs/redesign/captures/p03-shell-hoy/` (0 hallazgos en dashboard) + corrida completa `p03-shell-hoy-full/`; `ux:axe-shell` (axe 5 roles ×2 temas) sin violaciones serious/critical; paleta Ctrl K probada en vivo (`P-000012` → proyecto). Hallazgos netos restantes viven en páginas internas de otros encargos (production-*, portal, catalogs).
- Decisiones registradas en `docs/decisions/valores-por-defecto.md` (sección P03: grupos del riel, matriz rol→nav, spec de cola por rol, migas humanas, grupos de paleta, campana, 44 px, columnas de retazos, `AI_PROVIDER=mock`).

## [2026-10-06] P17 | asistente IA, trabajos y Orb vivo

- Encargo P17 (ola 1): la IA deja de ser un hilo de chat y pasa a trabajar visible — Orb conectado a trabajos reales, dock contextual de 400 px, propuestas revisables (diff dibujado + Δ del motor) y cola legible en /jobs. Branch `devin/P17-asistente-orb` sobre `integracion/v1`.
- `OrbState` único (`states.ts`) + `useAssistantPresence(context)`: el Orb del shell, el encabezado del dock, los avatares y los vacíos leen el mismo trabajo apremiante de la org (`ai_job` filtrado por superficie+refs; RUNNING/QUEUED/WAITING > terminales; desconocido → `idle`). Tests del mapeo job→Orb congelados, incl. estado desconocido.
- Identidad: `BotFigure` + `Orb` por spec del dueño (esfera antracita, ojos cápsula, anillo orbital con color por estado; tamaños 16/20/28/64/160; sin boca ni glow; IDs SVG únicos por instancia; `prefers-reduced-motion` detiene toda animación — test).
- Dock contextual: chip de superficie legible ("Pos. 01 Segundo piso · P-000001"), sugerencias por pantalla (`SURFACE_SUGGESTIONS`), pestañas Preguntar (context_assist) / Agente (turnos).
- Artefactos revisables: `OpsProposalCard` dibuja Antes/Después con el renderer real (`ProductPreviewFigure`→`ProductFrontSvg`) + verdict del motor vía `design_batch_preview` ("Válido según el motor · Δ +$103.822" o causa honesta); Aplicar ejecuta las ops tipadas (deshacible Ctrl+Z), Descartar, Ver auditoría → `/assistant?job=`. `BatchOpsStep` (§8): diff por posición + Ug declarado, nunca inventado por la IA.
- Honestidad de motor: lote 422 (taller sin reglas/lista) → "Sin reglas de precio…" con Aplicar habilitado; `ok:false` por ítem → Aplicar bloqueado con causa; `FailureCollapse` colapsa intentos fallidos con "Detalles técnicos"; insignia "Proveedor de prueba" sólo en DEV cuando `mock=true`; estado real en Ajustes › IA (sólo OWNER, captura owner verificada).
- Roles: `canUseAssistant`/`canReadJobs` espejan `_AGENT_CALLERS`/`_JOB_READERS` — nav, orb, badge y dock no se montan para OPERATOR/INSTALLER y /jobs declara "Tu rol no puede ver los trabajos" sin disparar la consulta (erradicó las 403 del audit); retry corta en 403; filtro de estado ≥44 px en móvil (`--density-loose` bajo 720 px).
- /jobs: tabla Tipo (ES) · Objeto (código humano Pos. NN · P-######) · Estado (`StatusChip`) · Duración · Actor · Resultado, filtros por estado en URL, paginación 100 + "Mostrar más", reintento sólo cuando el backend lo permite, enlace "Abrir en el asistente" al job.
- Verificado en vivo (fixture "Taller P17" + reglas/lista de costos reales sembradas): "divide la hoja en dos oscilobatientes" → tarjeta con diff + Δ +$103.822 → Aplicar (2 hojas, Neto $443.944, "Cambios sin guardar") → Ctrl+Z ($231.064) → auditoría (`job=f5953da7…`, 8 créditos, 2192 tokens, "Esperando aprobación") + Orb thinking→working→waiting→success; /jobs lista los 3 turnos reales; ux:capture assistant 0 hallazgos, jobs sólo hallazgos preexistentes de chrome; `make lint|typecheck|test|build` verdes.
- Proveedor: MOCK por cuota MiMo agotada (429 — IA3 lo documenta; la superficie declara "Respuesta determinista del proveedor MOCK", nunca lo presenta como real).

## [2026-10-06] P07 | workspace de precios v2: cascada, banda de margen y aprobaciones

- Motor `cascade.py` nuevo: `price_cascade` cierra exacto (Decimal) la cascada proyecto y por-posición — rechaza snapshots inconsistentes en vez de dibujar una cascada mentirosa; `delta_contributions` descompone el Δ por impulsor con orden canónico y telescopio exacto; `band_state` decide el estado de margen (None→BELOW_MIN, nunca silencio).
- `pricing_rules` gana `margin_min_pct`/`margin_max_pct` (defecto 0,25/0,60); `margin_pct` opcional por operación. Fuera de banda: estimador→PENDING directo, dueño→confirmación expresa; la puerta cubre preview y apply. Aviso `mail.pricing_decision` idempotente sella la notificación al solicitante en la misma transacción (proveedor sandbox).
- Read-model `_operation_enrichment` da banda/cascada/Δ a operaciones históricas sin backfill; `coverage` lista SKU de compra sin costo; `?state=`/`?project_id=` filtran el listado y ESTIMATOR ve solo lo suyo (raíz del loadError al montar).
- Frontend: `MarginBand`, `PriceCascade` (con autoridades como procedencia), `DeltaBreakdown`, campos de banda en reglas, `margin_pct`, "Solicitar aprobación" + motivo precargado fuera de banda; 16 tests motor + 2 de página + integración banda/notificación.
- Decisiones en `docs/decisions/valores-por-defecto.md` sección P07; capturas `docs/redesign/captures/p07-precios/`; `make lint|typecheck|test|build|test-db` (`PY=.venv/bin/python`).
- Correcciones tras QA grabado: la cascada no renderizaba nunca — el gate de igualdad exacta rechazaba los snapshots cuantizados a 4dp (unit_cost almacenado vs. recomputado difería en fracciones de centésima). Solución: `QUANTUM_SLACK`/`MONEY_SLACK` por unidad/proyecto con fila explícita `rounding_residual` (telescopio sigue exacto); una divergencia real (>0,5+ por proyecto) sigue rechazando. Cobertura devolvía 409: `pricing_backend` no tenía SELECT en los 4 mapeos de compra más nuevos ni políticas `TO pricing_backend` en 7 tablas (política `TO authenticated` no cubre un rol NOBYPASSRLS → error o filas vacías) — migración `20270202000000`. Menores UI: Δ por línea solo con `pricing_current` (sin base aplicada mostraba +neto completo), cantidades acumuladas en escala entera (adiós `5.6240000000000006`), `FITTING` traducido, historial hace upsert local tras crear (sin Recargar), "Editar" de Reglas dejaba los % en blanco porque `pctDisplay` devolvía coma decimal en un `<input type=number>` (nuevo `pctInput`).

## [2026-10-06] P12 | producción: tablero por estación, OT navegable y operario táctil

- `/production` se reestructura en tres superficies por rol: tablero kanban del jefe (columnas = estaciones con pasos abiertos en `station_queue` + «Salida», tarjetas con código/obra/unidades/compromiso real/avance/chips, filtros obra·compromiso·incidencia), ficha de OT (cabecera fija + stepper horizontal + 9 tabs con Piezas virtualizada <100 filas DOM a 2.000 piezas y Trazabilidad humana `HH:MM · actor · acción`), y superficie de operario (rol `OPERATOR`, density workshop → oscuro, 1024×768, estación persistente por usuario, tarjeta «Siguiente», escaneo de etiqueta → vista F9 pieza única ≥32 px mono, botones ≥44 px Completar/Bloquear/Nota, sin datos comerciales).
- Backend sin migraciones: `list_production_orders` gana `project_code/name`, `client_name`, `committed_date` (`MIN(deliveries.scheduled_date)`, «Sin fecha agendada» si no hay — nunca capacidad inventada), `steps_blocked`, `qc_blocked`, `plan_state`; `_board_context` resuelve proyectos/entregas en batch.
- Fixture: P-ESCALA (100 posiciones) se sella y libera → ~100 OTs reales en el tablero para la medición de interactividad <2 s; primera OT optimizada para que Corte/Mecanizado tengan datos.
- Bloqueos con motivos predefinidos de un toque (5 + Otro libre); el motivo queda como nota del paso para quien desbloquea. QC FAIL → `HOLD` → chip naranjo «requiere persona» en tablero.
- e2e `production-operator.spec.ts` (dentro de `make test-db`): operario en 1024×768 oscuro elige su estación → completa un paso (la OT sale de su cola) → bloquea la siguiente OT con motivo → el jefe ve «Bloqueada» en el tablero y «Pasos de producción bloqueados» en «Hoy».
- Aprendizajes: `t(key)` no acepta parámetros (`.replace("{x}", v)`); el trinquete §10 prohíbe `font-weight ≥700` y `{*.status}` crudo en JSX — se usó 600 + `StatusChip`/mapa compartido `ORDER_STATUS_KEY` en `board.ts`; `PlanStateEnum` (valores minúsculas) requirió etiqueta en `domainLabels`.
- Verificado: `make lint|typecheck|test|build` verdes (`PY=.venv/bin/python`); unitarios producción 26/26 (virtualización y etiquetas); decisiones en `docs/decisions/valores-por-defecto.md` sección P12.

## [2026-10-06] ED1 | pase editorial de la ola 1 (sin funcionalidad nueva)

- Recorrido por persona + captura `ux:capture` completa antes/después en `docs/redesign/captures/ed1/` (44 rutas, 300 disparos por corrida). Hallazgos reales corregidos: `small` al piso §3.1 vía `--type-dense` (42 `font-too-small`), estado crudo en JSX a 0 (`ui-raw-status`), identificadores en `<code>`/mono, 404 de la ruta dev demo (refs vacías en `useAssistantWhereAmI`), 403 de `payment-integration` para no-OWNER.
- Separamos tres naturalezas de formato que convivían: `fmtWire` (contrato máquina, decimales fijos), `fmtMmCanonical` (sólo inputs canónicos) y `fmtMm`/`formatDims` (presentación agrupada). `toFixed` fuera de `format.ts` quedó sólo en el muestrario dev intencional — guarda `ui-tofixed` 87→2.
- El escáner de captura aprendió contexto: `code/pre/samp/kbd/.fmt-code` exentos del vocabulario (un código SKU en mono no es un enum-token), y `contrast-aa` compone alfa sobre el fondo real. Rutas con 410 por diseño (portal revocado/reemplazado) y el muestrario dev declaran su contrato en `routes.ts`.
- Glosario: estados de operación de precio en femenino (la operación); `importStatus.ts` único para chips de importación; alias `--shadow-lg` muerto fuera; baseline de guardas regenerada a la baja (Δ −11).
- Decisiones durables en `docs/decisions/valores-por-defecto.md` sección ED1; verificación `make lint|typecheck|test|build` verde con `PY=.venv/bin/python`.


## [2026-10-06] P13 | pack de corte imprimible, etiquetas de pieza e identidad entre artefactos

- `cut_pack.py` se reescribe para el operario de sierra: origen por barra (barra nueva / retazo RT-…), cortes en secuencia con largo+ángulos+etiqueta por instancia, cierre exacto Decimal y remanente→destino con el folio `RT-` real de `inventory_remnants`; secciones agrupados-manual, refuerzos/junquillos con pieza padre, vidrios con destino y no-ubicados con acción de catálogo.
- Etiquetas de pieza configurables por org: nueva columna `workshop_label_format` (GRID | THERMAL_100X50) con migración + grant, select en Ajustes › Documentos, serializers/orval regenerados; grilla en hoja del papel documental o rollo 100×50 mm; cada etiqueta lleva código, OT, posición/unidad, rol ES, medidas, QR y siguiente estación. Etiquetas de retazo incluidas.
- Identidad por instancia compartida: `(bar|sheet_index, sequence) → código` resuelve la misma etiqueta en PDF, CSV (`work_order_cnc_export_v3`), DXF (AC1027 UTF-8 — `Junquillo`/`Ñ` intactos) y QR; `ezdxf` añadido como dep de test para el parseo. Columnas CSV documentadas en `docs/formatos/corte-csv.md` como formato genérico DEKOPEN.
- Lecciones duras: WeasyPrint no fragmenta `display:flex` entre páginas (la grilla de etiquetas va en flujo de línea con etiquetas `inline-flex`); la franja de título corre fuera de `<main>` así que el piso de 8pt necesita selectores sin prefijo en `_CSS_PACK`; `_value()` devuelve "—" truthy — no usar como guarda de "¿hay artículo?"; la misma folio RT- debe asignarse una vez y compartirse entre línea de barra y etiqueta de retazo (pre-asignar, no poppear dos veces).
- Verificado: `make lint|typecheck|test|build|test-db` verdes; tests nuevos OT 1/12/100 posiciones (páginas acotadas, sin superposición, cierre exacto), igualdad de etiquetas PDF/CSV/DXF/etiquetas, parseo DXF con ezdxf; capturas en `docs/redesign/captures/p13-pack-corte/`; decisión en `valores-por-defecto.md`.

## [2026-10-06] P06 | bow/bay y acoplados dentro del editor principal

- Vista planta acoplada como franja inferior del lienzo (`.plan-strip`, altura arrastrable/plegable) con cotas del conjunto y selector Desarrollada/Proyectada (`w·cos(rumbo)` por columna, misma convención de rumbo que `_plan_geometry`); la selección es bidireccional con el frente.
- Ángulos editables en la planta: etiqueta click-to-edit + arrastre de bisagra/módulo que gira la cola de la cadena con snapping {0,±10,±15,±22,5,±30,±45,±90}° (3,5° tolerancia) — el commit pasa por `setCouplingAngle` y recalcula geometría/coples/precio; las incompatibilidades se explican en la cuña exacta (`!` + issue `coupler_angle_incompatible` con rango).
- Envolvente de ángulo del cople declarada en catálogo (migración + `couplerFitsAngle` en el select del inspector; no-declarada = desconocida, nunca rechaza). `module_id` fluye del `bay_id` del BOM a las líneas de composición → `module_net_after` reparte el neto por material atribuido (restante repartido proporcional, último módulo cierra redondeo).
- Plantillas de biblioteca nuevas: Bay 45°, Puerta + lateral, Ventana + sobreluz, Esquina 90°; Bow ×3 pasa a canónico (fijo central + oscilobatientes laterales a 22,5°) — el e2e arma el diseño del encargo en 5 gestos.
- Aprendizajes: `CouplingJson.kind` ausente = INLINE por contrato — `moduleHeadingsDeg` necesitaba `?? "INLINE"` o el rumbo quedaba 0°; FittingPiece.bay_id es opcional (getattr); `--type-caption` no existe en tokens (vitest guarda tokens usados sin definir).
- Corrección post-verificación UI: el escorzo proyectado usaba `cos` con signo → anchos negativos y floats sin redondear a rumbo ≥ 90° (ahora `|cos|` + redondeo 0,01 mm en la cota), y las cotas del alzado proyectado eran editables y reescribían el ancho declarado con el valor escorzado (ahora solo-lectura; el ancho se edita en desarrollada). El reparto del chip sigue el orden de alzado (`moduleIds`), no el del payload.


## [2026-10-06] P15 | compras, recepción, inventario y retazos

- `/inventory` nace como superficie propia: stock por SKU (en bodega, reservado con la OT que reserva, en tránsito, ubicación), retazos `RT-######` (tipo, identidad, medidas, rack, OT origen, edad, destino) con acciones Mover/Reservar/Desechar+Etiqueta QR, alerta de retazos viejos por `remnant_alert_days` (Ajustes › Organización) y libro de movimientos con actor/lote/documento/rack. `/purchasing` queda sólo de compras.
- Compras: propuesta por proveedor editable con precios sellados en la OC (`purchase_allocations.unit_price` → `total_net`); `send_order` = clic humano → correo `order_sent` a audiencia `SUPPLIER` + job de PDF por tipo (perfil DOC-04, vidrio DOC-02, herraje/panel DOC-08), idempotente y tolerante a fallos del outbox; recepción por línea con guía/fecha del proveedor, dañados, lote y rack; sobre-recepción bloquea con 422 hasta `allow_over_receipt`.
- Retazos como stock de primera clase: `inventory_movements.remnant_id` + tipo `MOVE`; `scrap` exige motivo y reserva/movimiento escriben actor real; los retazos de producción guardan `physical_stock_identity` (vía `stock_authority`); `remnant_pool` en coverage y el filtro `stock_identity` resuelven autoridades — la UI sólo ofrece el retazo compatible que el motor calcula cuando una OT tiene faltante.
- Causa raíz del 409 al cargar stock ya estaba corregida en la base (`a1b08c07`, lectura bajo `documentary_backend`); se agregan tests de regresión (acceso por rol + grants pgTAP).
- Migraciones `20270210/11/12`; pgTAP `182` (16 aserciones); `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`); ux:capture 0 hallazgos `/purchasing`+`/inventory` tras llevar objetivos táctiles a 44 px (`.inventory-page` min-height incl. `summary` y `.fmt-code`); 14 capturas en `docs/redesign/captures/p15-compras-inventario/`; decisiones en `valores-por-defecto.md` §P15.


## [2026-10-06] P14 | CNC: veredictos por máquina, tarjeta de miembro y auditoría

- La pestaña Mecanizado pasa de matriz densa a tarjeta por miembro: identidad física completa, vista por caras a escala con ops ubicadas desde el datum declarado (sin cara → carril «cara no declarada», nunca adivinada) y tabla con X/Y/u, profundidad, herramienta y fuente de regla.
- Lo declarado y no emitido es sección explícita por OT y por máquina (`declared_gaps`): anotaciones de taller, intención de manilla y mecanizado de herraje, con causa (`sin regla`, `sin coordenadas`) y, por máquina, si podría ejecutarlo (`sin herramienta`, `no soportada`, `sin tipo evaluable`, `emisor no implementado`).
- Emisores honestos: registro `_POSTPROCESSORS` en código; `postprocessor_id` desconocido → BLOCK `emitter_not_implemented` en readiness + rechazo `cnc_emitter_not_implemented` en generación. Nunca se manda formato neutro como si fuera propietario.
- CRUD máquinas (tipo/ejes/carreras/emisor) y herramientas bajo OWNER+WORKSHOP_MANAGER; migración `20270206000000` crea `cnc_authority_events` append-only (org-scoped, diff from→to) y `cnc_programs.superseded_by` enlaza el programa reemplazado con el vigente; nuevo diff `compare` entre versiones del programa.
- Aprendizajes: `test_openapi` mantiene una allowlist de paths — cada endpoint nuevo hay que registrarlo; `verify`/`capture` regeneran PNGs de capturas anteriores (difs binarios) — no committear ruido; los tests sin `@pytest.mark.django_db` no pueden tocar la conexión aunque sea para `documentary_backend()` — la validación de enums va antes del `with`.
- Verificado: `make lint|typecheck|test|build|test-db` verdes; capturas en `docs/redesign/captures/p14-cnc-mecanizado/`; decisiones en sección P14 de `valores-por-defecto.md`.


## [2026-10-06] P11 | cobranza, pagos y facturación: calendario, documentos y honestidad SII

- `GET /projects/{id}/payments/` pasa de «lista de pagos» a resumen de cobranza: `schedule` (ANTICIPO vence al aprobar, SALDO contra entrega — nunca una fecha inventada), `movements` (UNION pagos/anulaciones/links/facturas/NC/envíos con actor y documento respaldo — F6 aplicada a los saldos), `sii` (estado de integración honesto) y `reminder` (borrador IA vigente).
- Causa raíz de «No pudimos cargar los links de pago»: el estado `payment-integration` (sólo OWNER) compartía el `Promise.all` de la lista — un 403 para el estimador mataba el panel entero. Consultas separadas; regresión vitest.
- Honestidad tributaria end-to-end: `integration_state.certified` exige `sii-ws` + certificado + CAF; sin eso, cada documento declara «Documento interno — no válido como documento tributario electrónico». `sii_envios` gana `OBSERVED` («aceptado con reparos») como estado propio con etiqueta ES.
- Simuladores de punta a punta detrás del adaptador: `FLOW_WS_MOCK=1` (checkout local pagar/rechazar → mismo `payment_status` del webhook; un cargo desconocido jamás reporta pagado) y `SII_WS_ENVIO_MOCK=1` (`_VERDICT` = ACCEPTED/OBSERVED/REJECTED). Sin opt-in → 404, sin fallback silencioso. Ajustes declara ambos.
- Recordatorio de cobranza IA (capability `collection_reminder`, MIMO como toda ruta): preparar genera el borrador auditado desde hechos del ledger — la IA no calcula montos; enviar exige clic explícito y encola correo real. La cola «Hoy» marca la cobranza pendiente y si ya hay borrador.
- Aprendizajes: `ai_audit_logs` no tenía grant a `documentary_backend` (el resumen 409aba con 42501 — lo pilló `dev_fixture` en e2e, no un test unitario); el pgTAP de `ai_routes` cuenta capacidades exactas (9→10 al agregar la ruta); pg16 replay vía mirror.gcr.io cuando Docker Hub rate-limita.
- Correcciones post-verificación UI: el settle público del link (webhook Flow + checkout simulado) respondía 500 `payment_link_not_found` — sin JWT la política org-scope no ve la fila y las claims tx-local expiraban antes del `_settle`; se agregó `private.payment_link_public_scope` (SECURITY DEFINER, por id/token opaco) + claims delegadas del `created_by` dentro de **una sola transacción** — verificado en vivo: POST anónimo → 302 → PAID → pago + RC. El timbre PDF417 explotaba con un TED real (CAF embebido → >90 filas a 6 columnas / techo 928 codewords): minify XML + columnas escaladas ≤30 + redundancia 5→0, honesto si aún no cabe. Menores: timeline con `status` localizado + actor del envío, `recorded_by` del link (era el UUID del actor HTTP), nota del ledger sin UUID, scroll-x en tablas ≤1280 px, recordatorio con fallback a `clients.email`. Re-verificación delta: `emit_dte` 409aba aún con el PDF417 arreglado — `_seal_repr` escribe `repr_storage_object_key`/`repr_file_sha256` y `documentary_backend` no tenía `GRANT UPDATE` sobre `project_dtes` (latente desde `20261208`, oculto por el crash); migración `20270215000000_p11_dte_repr_update_grant` (column-level, patrón P15) + pgTAP `184`. Con el grant: emisión completa verificada en vivo (DTE-33 folio 1, PDF417 real, envío «Aceptado con reparos»).
- Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`); pgTAP 1089, integración 279, e2e 20/20; decisiones en `valores-por-defecto.md` sección P11; capturas `docs/redesign/captures/p11-cobranza/`.

## [2026-10-06] P16 | catálogo: fichas de artículo, procedencia que no se autocertifica y revisión de importación con IA

- Página de sistema convertida en la autoridad visible: encabezado con identidad + procedencia + escalera de readiness con blockers deduplicados y deep links `targets[]` resueltos en base; pestañas Perfiles/Refuerzos/Vidrios/Herrajes/Reglas/Costos/Historial sobre un solo endpoint de workspace.
- Ficha de artículo nueva (`articles/{id}/ficha/`): miniatura desde la geometría real con escala/origen/orientación, validaciones de sección (`section_check.py`), insignia de procedencia que abre documento origen + página/línea + revisor + fecha.
- Procedencia protegida en base: `private.can_review_catalog` + trigger `guard_catalog_certification` (42501 sin rol de revisor) y ledger `catalog_import_events` append-only; pgTAP 183 demuestra rechazo de autocertificación por miembro directo y por la vía backend.
- Revisión de importación: `diff` campo a campo re-derivado en vivo contra el artículo actual, evidencia de origen por candidato, LOW/REVIEW_REQUIRED desmarcados por defecto, sello `reviewed_by/at` + auditoría UPLOADED→EXTRACTED→CONFIRMED.
- Lección dura del runner pgTAP: las funciones viven en schema `extensions`; `catalog_backend` no tiene USAGE → cualquier assert bajo ese rol falla «does not exist». Convención (156): DML crudo bajo el rol backend, `RESET ROLE` → `authenticated` para asserts; capturas de excepción con `DO`+GUC.
- Paridad: `catalog_readiness` único alimenta página y gates; test de paridad en DEMO_60 + catálogo incompleto. Verificado `make lint|typecheck|test|build|test-db` (`PY=.venv/bin/python`); IA MOCK documentado en ACTIVACION.md (MIMO 429).

## [2026-10-06] P08 | emisión canónica: checklist guiado, condiciones comerciales y ciclo de vida del enlace

- La emisión pasa a ser un flujo guiado único: checklist «Qué falta para emitir» siempre visible en el orden de resolución (cliente con RUT módulo 11 → obra → posiciones → vigencia → pago → claves comerciales), cada ítem navega y resalta su campo; confirmación con folio/total/vigencia/destinatario/consecuencia/huella `bom_hash`; una sola acción «Emitir y enviar al cliente» (los botones compartir alternativos se eliminaron — búsqueda de llamadas a `freeze`/`quote-link` confirma un solo camino).
- `freeze` ahora es la compuerta: `emission_checklist_incomplete` + `extra.missing` en el mismo orden del checklist (servidor = autoridad; el panel se resincroniza con `prepare` al recibirlo). Condiciones comerciales en dos niveles: plantillas de org en `tenancy_organizations.doc_terms` (incluye clave `pago` → `default_payment_terms` y `doc_validity_days` para la vigencia propuesta) editables en Ajustes, y edición por cotización en `project_documentary_inputs.doc_terms` (texto vacío omite la línea); las claves efectivas se congelan en el snapshot — una cotización sellada nunca cambia de condiciones.
- `quote-preview` arma el snapshot DOC-01 real sin persistir: la vista previa del constructor ES el documento del cliente (iframe sandbox + huella), no una maqueta.
- Ciclo de vida del enlace: estado `CHANGES_REQUESTED` en `customer_approvals` (migración + mail interno `quote_changes_requested` para «Hoy»/campana), `decide` acepta decidir tras pedir cambios, `share_quote` reemplaza enlaces EMAIL vivos, `PATCH` mueve vencimiento; el stepper Enviada→Vista×N→Decisión deriva «Reemplazada» de `revision_code` sin migrar estados viejos. Token opaco: «Copiar enlace» usa la URL recién minteada con fallback manual (execCommand → input readonly).
- Cambios globales por el registro `apply_to_positions {filter, ops}` con preview de precio y deshacer — el mismo camino que cualquier edición de posiciones.
- Aprendizajes: `current_pricing_operation_id` es campo derivado del API (no columna de `projects` — consultar `pricing_operations` APPLIED); los fixtures de integración que sellan ahora declaran `doc_terms` porque la org del fixture no tiene plantilla; la vigencia del checklist exige fecha parseable (no futura) porque «expirada» es un estado diseñado del enlace — el fixture P-EXPIRADA sella con `valid_until` de ayer. `versions` es ASCENDENTE por `emitted_at` — el más reciente es `.at(-1)`, nunca `[0]` (bug «reemplazada» invertida). `parametric_tree` guarda un IntentNode pelado (no product-v2 con `assembly.modules`) — las ops de producto marcan «unsupported» honesto. Posiciones con precios aplicados rechazan PUT con `commercial_revision_required`: los cambios globales viven en borrador sin precio o tras liberar precios, y el panel declara el bloqueo en vez de fallar al aplicar.
- Verificado: `make lint|typecheck|test|build|test-db` (`PY=.venv/bin/python`); decisiones en `docs/decisions/valores-por-defecto.md` sección P08; capturas `docs/redesign/captures/p08-emision/`.

## [2026-10-07] ED2 | pase editorial de la ola 2 (sin funcionalidad nueva)

- Unificación de vocabulario y enums: `typologyLabel`/`colorLabel`/`enumI18nKey` compartidos en `i18n/es-CL.ts`; compras migra sus mapas CAPS locales al par StatusChip+domainLabels; jobs (estado de envío de recordatorio), cotizaciones (`no_link`), pricing (contexto `DEFAULT`), producción y portal dejan de imprimir enums crudos o términos divergentes.
- Formatos §3.3 terminados: `fmtQty` agrupa (`50 000`), `quantize` elimina los últimos `.toFixed()` de producción (guard `ui-tofixed` 2→0), fechas ISO crudas por `formatDate`, plurales reales.
- Backend: `production/cnc.py::_declared_gaps` emite `declared_offsets_mm` estructurado — el `repr` de lista Python dejaba de ser legible en la tarjeta de mecanizado.
- Sistema visual: escala de capas completada (`--z-raise`, `--z-raise-top`, `--z-menu`), un solo scrim (`--scrim-overlay`), tintas `-ink` para warn/persona, skeleton sin shimmer, `ui-empty-inline` único, `ui-button--primary` único, ~1.300 literales de espaciado → tokens y ~420 fallbacks var() muertos fuera.
- Baseline de guards: de 6 reglas/68 violaciones a 1 regla (`ui-motion>280` 21 — animaciones legítimas). Rutas nuevas auditadas por ux:capture: production-order(+blocked), quotations; deliveries corregido a rol manager.
- Verificado `make lint|typecheck|test|build` verde (`PY=.venv/bin/python`); decisiones en sección ED2 de `valores-por-defecto.md`; capturas `docs/redesign/captures/ed2/` (antes/después).

## [2026-10-07] P21 | página de proyecto: hub del estimador con posiciones de verdad

- `/projects/<id>` deja de ser pila de acordeones: hub de 8 pestañas (Posiciones predeterminada, Servicios, Cotización, Precio, Cobranza, Producción, Documentos, Actividad) que monta los paneles mergeados de la ola 2 sin reescribirlos. `?tab=` canónico; `?section=` heredado sigue resolviendo al dueño actual del flujo.
- Encabezado: identidad (código+nombre, cliente, obra), stepper comercial, total con IVA y vigencia, y una sola acción siguiente por estado derivada de capacidades (`projectNextAction`) — nunca un CTA muerto.
- Posiciones de verdad: grilla con render real o lista densa de 12 columnas (scroll dentro de su zona, precedente P15), agrupación por ubicación/tipología/sistema, edición de medidas y cantidad en fila, multiselección con barra de lote (duplicar/ubicación/cantidad/cambios globales §8/eliminar) y navegación por teclado (flechas, Enter, Supr, Alt+↑↓ para reordenar).
- API nueva: `POST /positions/<id>/move/` — el índice de orden no es campo escribible del PUT; la transacción renumera el rango y conserva el candado `expected_updated_at`.
- Lecciones: la especificidad `elemento:pseudo` (0,1,1) vence a una clase plana (0,1,0) — la tinta de `.ui-button--primary` se redeclara en `:hover` para que los enlace-boton no queden turquesa-sobre-turquesa; los paneles perezosos permanecen montados ocultos, así que los tests deben clicar la pestaña antes de buscar contenido; `pgrep -f "manage[.]py"` es el matasanos correcto (un pkill suelto mata tu propio shell).
- Verificado: `make lint|typecheck|test|build|test-db` verde; e2e auth+projects; ux:capture 48 tomas sin hallazgos; decisiones P21 en `valores-por-defecto.md`.

## [2026-10-07] P10 | portal de propuesta v2: marca del fabricante, decisión con evidencia y estados honestos

- El enlace del cliente ahora llega con la marca del fabricante (logo, razón social, RUT, contacto, favicon, `document.title`); «Generado con DEKOPEN» sólo cuando el emisor lo permite (`doc_dekopen_credit` sellado).
- `portal_quote.state` declara el estado real (live/approved/declined/changes_requested/superseded/validity_expired/link_expired/revoked/unavailable) con páginas dedicadas en 200 — la reemplazada lleva `follow` al link vigente (`POST .../follow/`, channel=FOLLOW, cap 5) y `superseded` gana sobre `revoked` en la clasificación.
- La decisión queda con evidencia: RUT módulo 11 + nombre + checkbox de aceptación literal (folio+total+revisión), IP/UA del request, hash de la BOM y posiciones en `customer_approvals`, inmutable por trigger y con bitácora append-only `customer_approval_events` que el estimador ve vía `list_approvals` (y atención `quotes_changes`).
- Pago sólo cuando corresponde: aprobada + vigente + no reemplazada + CLP + saldo + proveedor; `payer_return_url` devuelve al portal («Pagado»/«Abonado parcial»), USD declara `unsupported_currency` sin botón; sobrepago rechazado en backend; `FLOW_WS_MOCK=1` etiqueta «Modo de prueba» en UI.
- `is_option` vuelve las alternativas estructurales (precificadas por línea, fuera del total, sección propia en DOC-01 y en el portal con Δ vs la incluida); la convención textual «Alternativa» en `location_tag` se eliminó del fixture.
- Aprendizajes: el detector contrast-aa no evalúa `color-mix` translúcido ni compone `--theme-surface-panel` en dark — tinta sobre marca siempre `--theme-accent-onfill` (brandOnFill) y marca-como-texto `--theme-accent-ink`; el `<g>` SVG deshabilitado cumple axe+editor con `role="img"`+`tabindex="-1"`; el fixture gana slugs `parcial`/`rechazada`/`cambios`/`usd` y repara el token `aprobada` verificando hash+estado contra la base (el state file sobrevive al `db reset` del gate).
- Verificado: `make lint|typecheck|test|build|test-db` verdes (`PY=.venv/bin/python`; pgTAP 1147, integración 281, e2e 34/34, portal 10/10); capturas `docs/redesign/captures/p10-portal/` 80 shots 0 findings; Lighthouse móvil 80/100/100/92 (prod build); decisiones sección P10 de `valores-por-defecto.md`.

## [2026-10-07] P22 | clientes, empresa y ajustes

- Clientes pasa a dominio completo: persona/empresa con RUT módulo-11 y giro, contactos con rol, direcciones de obra múltiples, y ficha que junta proyectos, cotizaciones, pagos (facturado/cobrado/saldo), documentos y notas append-only con autor. `clients.notes` se migra a `client_notes`; la fusión de duplicados por RUT canónico repunta todo en una transacción y audita en `client_merges` — la única escritura posterior sobre notas es `UPDATE (client_id)` a nivel columna.
- Ajustes se agrupa por dominio en `/settings/:section` con permisos por rol y secciones no mergeadas deshabilitadas («Disponible cuando…»). `backend/projects/org_settings.py` concentra el snapshot por sección + `document-preview` (momento de firma §8: el mismo `_CSS` y markup del PDF, fuentes embebidas `data:` porque el iframe no lee `file://`) e `integrations` con estado sin secretos.
- Onboarding gana el paso «Ajustes» con los defaults §11 editables; `AuthMeView.claim_own_invitations` auto-reclama invitaciones al entrar.
- Aprendizajes: los grants de Supabase dan ALL a `authenticated` por defecto — tablas append-only necesitan REVOKE explícito y grant a nivel columna cuando existe un camino legítimo de escritura; el patrón `SET check_function_bodies` no basta para DML ejecutado (DO blocks) — envolver con `to_regclass('auth.users')`; el min-content de un stepper es la suma de las palabras más largas de cada etiqueta — 8 pasos largos desbordan aunque se permita contraer.
- Verificado: `make lint|typecheck|test|build|test-db` (`PY=.venv/bin/python`); pgTAP 1162 (incl. `183_p22_clientes_ajustes` 27 asserts), integración 281, e2e 27/27, pg16 vainilla; ux:capture 72 shots 0 hallazgos; capturas `docs/redesign/captures/p22-clientes-ajustes/`; decisiones en sección P22 de `valores-por-defecto.md`.

## [2026-10-07] D08 | tipologías avanzadas (HST, PSK, plegable, pivotante, guillotina, puerta corredera)

- Las seis tipologías recorren el slice vertical completo del motor: modelo (`LIFT_SLIDE`, `PARALLEL_SLIDE`, `FOLD`, `PIVOT_V/H`, `VERTICAL_SLIDE`, `DOOR+SLIDE`), validación por familias (`families_admitting_spec`), cortes, BOM, herrajes (kits `LIFT_SLIDE`/`PARALLEL_SLIDE`/`FOLD`/`PIVOT`/`VERTICAL_SLIDE`/`DOOR_SLIDING`), simbología DIN (paquete plegado, riel elevable, eje pivote, desplazamiento vertical) y nombres es-CL.
- Catálogo: migración `20270218000000` con seis series sintéticas DEMO (`DEMO_ELEVACION_90`, `DEMO_PSK_90`, `DEMO_PLEGABLE_70`, `DEMO_PIVOTANTE_120`, `DEMO_GUILLOTINA_60`, `DEMO_PUERTA_CORREDERA_70`) — capacidades, kits, reglas de corte/refuerzo; marcadas sintéticas, nunca datos de fabricante.
- Contrato revivido: `IncompatibleTypologyError` llega como 400 `typology_incompatible` con `compatible_systems` (lo tragaba el `except ValueError` genérico del adaptador); bug `compatible` en `assert_opening_allowed` corregido (comparaba enum con strings de familia — siempre True).
- Biblioteca del editor: grupo "Avanzadas"; `starterCompatible` exige la clave de composición exacta por vano (`openingSpecKeyAdmitted`/`openingOptionAdmitted`); tarjetas bloqueadas con causa y consulta perezosa por serie que nombra qué series la admiten (§8 — nunca se inventa).
- Verificado `make lint|typecheck|test|build|test-db` verde (`PY=.venv/bin/python`): 1185 pgTAP, 283 integración, 27 e2e, 742 motor, 1315 backend, 723 frontend; goldens por tipología + fixtures de símbolos; decisiones en `valores-por-defecto.md` (sección D08); capturas en `docs/redesign/captures/d08-tipologias-avanzadas/`.
