# Progreso — fase 00 · base confiable y verificable

Base de trabajo: `devin/1790335313-commercial-workspace` (snapshot de diagnóstico
`a3785f7`; esta fase se evaluó sobre `297f121`, 199 commits sobre `origin/main`).
El commit de este paquete está en `evidence-index.md`.

Estados: **hecho** (implementado), **probado** (verificado ejecutando),
**pendiente** (en cola reconocida), **bloqueado por datos** (necesita entrada
externa, ver `blocked-inputs.md`).

## Recon e integración

- **probado** — `origin/main` (`5fa9936`) completamente contenido en la rama;
  ninguno de los 4 commits exclusivos de main pendiente de integración.
- **probado** — los 174→199 commits de la rama ya incluyen el único commit de la
  rama de skills observado como pendiente (idéntico).
- **hecho** — nada duplicado ni re-integrado; la rama avanza en HEAD.

## Los 4 fallos conocidos

- **probado** F1 `purchase_retry` — migración re-fechada tras `order_cancellation`;
  instalación limpia + pgTAP `170_purchase_retry` (15 aserciones: claim único,
  liberación, reintento, suplementarias, sin doble compra).
- **probado** F2 emisión service_role — `transaction.atomic` en el test; emisión
  e idempotencia bajo el rol real.
- **probado** F3 guía de despacho — el test afirma `delivery.address` sellado;
  ediciones posteriores del proyecto no lo mutan.
- **probado** F4 guard de estilos — tokens semánticos `var(--theme-surface-panel)`;
  `#fff` de la firma queda literal documentado (papel impreso).

## Defectos nuevos encontrados por el gate (y corregidos)

- **probado** `analytics/summary` 409 — `p.currency` inexistente; moneda ahora
  desde la operación `APPLIED` vigente vía `JOIN LATERAL`. Test nuevo:
  `test_analytics_schema.py` ejecuta el resumen sobre el esquema real (fail-fast
  sin Postgres).
- **probado** SKUs e2e obsoletos tras `20261227000001_seed_reference_labels.sql`
  (`DEMO-*` → `COMPRA-*`/`VIDRIO-*`/`ACERO-*` en auth/canvas specs).
- **probado** Nav e2e — `Administración` es OWNER|WM; el spec ESTIMATOR afirma
  su ausencia.
- **probado** Cache React Query — lecturas afirmadas desde backend forzadas con
  `page.reload()` tras volver del editor (proyectos + auth specs).

## Gates

- **probado** `make lint` — ruff, ESLint, prettier, generated-API sync, guards.
- **probado** `make typecheck` — mypy engine, django check, tsc.
- **probado** `make test` — 462 engine + goldens byte-exactos + 1024 backend + 436 frontend.
- **probado** `make test-db` — reset limpio (todas las migraciones en orden),
  `db lint` sin warnings, pgTAP completo, integración RLS, e2e Playwright,
  `verify_postgres16`. Resultado exacto en `evidence-index.md`.

## Mapa funcional

- **hecho** `docs/redesign/route-map.md` — inventario por área (acceso,
  onboarding, proyectos, clientes, Studio, precios, documentos/portal, compras,
  inventario, producción, CNC, catálogos, IA, ajustes, facturación): componente
  real, API, permiso por rol, estado vacío/error y siguiente paso, más contratos
  principales identificados.

## Entorno y fixtures

- **hecho/probado** `scripts/dev_fixture.py` — org + 5 cuentas por rol +
  clientes + reglas + cost-list cubriendo 88 SKUs + stock de inventario +
  3 proyectos (vivienda, obra grande, incompleta) + estado comercial completo:
  inputs documentales, pricing aplicado, REV-A congelada, liberación a
  producción y optimización de 4 OT con pack de cortes. Idempotente (uuid5).
- **hecho** distinción demo vs fabricable documentada (`decisions.md` D4,
  `blocked-inputs.md`).

## Capturas base

- **hecho/probado** — 32 PNG (12 superficies a 1440×900 y 1280×800, Studio
  claro/oscuro y congelado, 4 móviles a 390×844) + exportaciones
  `doc01-quotation-P-000001-REV-A.pdf` y `cutpack-OT-P-000001-REV-A-01.pdf` en
  `docs/redesign/captures/`, sobre `297f121`. Detalle en `evidence-index.md`.

## Pendiente conocido (backlog explícito, no de esta fase)

- Catálogo real con autoridad de fabricación → `blocked-inputs.md`.
- Credenciales externas (Flow, SII CAF/cert, provider IA) → `blocked-inputs.md`.

# Fase 01 — Lenguaje visual y navegación (cerrada en `6c61859`)

## Sistema visual

- **hecho/probado** tokens de tres capas en `tokens.css` (ver `decisions.md` D7):
  `--theme-*` interfaz, estructura, `--mat-*` físicos invariantes de tema.
  Tema claro cálido (`#f7f6f3` canvas), grafitos legibles en oscuro.
- **hecho** escala tipográfica y de espacios del mandato + densidades
  28/36/44px (`decisions.md` D8).
- **hecho/probado** guard de estilos verde (`scripts/check_guards.py` PASS) —
  los colores directos migraron a tokens sin desactivar el guard.

## Componentes (`frontend/src/ui/`)

- **hecho/probado** Button (variantes, loading con ancho estable, protección
  doble envío, `disabledReason`), Field (etiqueta persistente + ayuda + error
  asociado), TextInput (prefijo/sufijo), NumberField (precisión veraz),
  SelectField (mensaje de incompatibilidad), Tabs (semántica real + teclado),
  PageHeader, TechDetails (diagnóstico colapsado + copiar), Toast.
  Pruebas de comportamiento: `Controls.test.tsx` + `Tabs.test.tsx` (11 tests).

## Navegación

- **hecho/probado** rail con iconos + etiquetas; en Studio 64px icon-only
  verificado en el editor real (D9). Sin menús duplicados.
- **hecho/probado** matriz de roles por enlace directo: OPERATOR →
  `/pricing/commercial` y `/catalogs/systems` devuelven "Sin acceso" con
  retorno útil (evidencia `phase01/operator-denied-catalogs.png`).

## Migración de superficies reales

- **hecho** headers migrados a PageHeader en dashboard, proyectos (lista +
  detalle), clientes, compras, producción, precios, catálogo, facturación,
  ajustes, jobs. Tabla de proyectos a `ui-table` con cifras alineadas.
  Navegaciones de precios y catálogo a `Tabs`.

## Verificación (QA sobre stack real, fixtures de 00)

- **hecho/probado** 30 PNG en `docs/redesign/captures/phase01/` — mismas
  superficies que 00 a 1440×900/1280×800/390×844, Studio claro+oscuro.
- **hecho/probado** recorrido de teclado: skip-link → rail → contenido;
  ⌘K con flechas/filtro/Esc; tablists con flechas auto-activan; foco
  visible 2px+4px teal en ambos temas.
- **hecho/probado** contraste AA en ambos temas (claro h1 13.6 / muted 6.24 /
  primario 6.35; oscuro 15.8 / 8.44 / 7.18).
- **hecho/probado** 390px sin scroll horizontal en dashboard (`scrollWidth=390`)
  tras corregir min-content de KPI/rows/activity.
- **hecho/probado** defecto de QA corregido: banner de validación ya no
  persiste tras cancelar en clientes/proyectos.

## Gates

- **hecho/probado** tsc estricto, vitest 436/436, prettier, guard de estilos.

## Pendiente conocido

- Las listas de clientes y algunos paneles internos conservan markup propio
  (migración incremental deliberada — el sistema ya existe para fases 02+).
- Los `title` del rail compacto de Studio solo aparecen en hover (tradeoff
  estándar de icon-rail; AT recibe `aria-label`).

# Fase 03 — Corregir el producto visual (SHA b8bc600)

## Herrajes por familia

- **hecho/probado** `hardwareVisual.ts`: contrato por hoja (kit contents +
  política de manilla + convención marcada); tests de resolución, datum,
  mano y familia (20 tests nuevos).
- **hecho/probado** emitters por familia en `Product3DScene.ts`: palanca
  batiente (roseta 30×64 + collar + palanca cónica), puerta (escudo 240mm
  doble cara + cilindro + pulsador), proyectante (manilla central riel
  inferior + compases + bisagras de testero), corredera (uñero embutido /
  tirador superficial / elevable por nombre de kit; tamaño físico fijo —
  el defecto del tirador proporcional al alto está eliminado).
- **hecho/probado** bisagras: barril + aleta + tapas; conteo desde línea
  HINGE del kit cuando existe; convención marcada `approximate` en caso
  contrario. Herrajes de sin-marco marcados esquemáticos.
- **hecho/probado** sólo la hoja de la pista interior puede llevar tirador
  sobresaliente — ninguna pieza atraviesa la hoja vecina.

## Datum, mano y diagnósticos

- **hecho/probado** altura declarada trazada desde `OUTER_BOTTOM`; fuera
  de hoja o fuera de la banda de política → `handle_out_of_range` /
  `handle_datum_unsupported` visibles (chips 3D + anillo punteado en 2D),
  nunca clamp silencioso.
- **hecho/probado** mano desde la vista declarada: `TURN_LEFT` dibuja
  bisagras izquierda / palanca derecha; puerta lee `door_handedness`.
  Hoja pasiva no hereda herrajes de la activa.

## Escenario 3D y materiales

- **hecho/probado** `--theme-viewport-stage/ground` por tema + suelo +
  sombra de contacto; colores `--mat-*` físicos inalterables por tema.
- **hecho/probado** vidrio: opacidad 0.30/0.38, depthWrite off, espesor
  real, junquillos/juntas separados.
- **hecho** arcos con error de cuerda ≤0.4mm (`arcSteps`) en lugar de
  acordes fijos de 5mm — sin facetas poligonales en radios cerrados.

## Contrato API + datos

- **hecho/probado** `kitChoice.contents` (sku/name/qty/unit/category) y
  `designOptions.handle_policy` (slots con host/mount band/refs) —
  openapi regenerado, fixtures actualizados.
- **hecho/probado** seed: 14 kits DEMO_60/ALU_65/GLASS_45 con contents
  categorizados; `handle_requirement_policies` v2 ya poblada y leída.

## Rendimiento

- **hecho/probado** signature de `MemberGeometry` incluye contents de kits
  + política — un cambio de conteo invalida la escena cacheada (test).
- **hecho** fallback sin WebGL + estado de carga + caption ilustrativo.

## Pendiente

- ~~Capturas de matriz + close-ups + video~~ **hecho/probado** —
  `docs/redesign/captures/phase03/` (59 archivos + REPORT.md) + video de
  estados; close-ups de herraje verificados.

# Fase 04 — Catalogos que gobiernan sin abrumar

- **hecho/probado** Registro de evidencia de parametros:
  `catalog_parameter_evidence` (migracion 20261227000002) + servicio
  `catalogs/evidence.py` + API GET/POST `/catalogs/evidence/` +
  POST `/evidence/{id}/review/` — sellos solo servidor; pgTAP 172
  (12 checks: member no escribe, org B no ve, sello requiere revisor,
  url http(s), unidad valida) + 10 tests unitarios del servicio.
- **hecho/probado** Import sella evidencia: `confirm_catalog_import` fija
  `stamp_import_evidence` por articulo creado (por campo, ON CONFLICT);
  `actor_id` entra por firma — 2 tests nuevos, 31 tests de ingest verdes.
- **hecho/probado** Auditoria PostgREST real: `authenticated` tenia
  TRUNCATE/TRIGGER/REFERENCES en 5 tablas de autoridad (TRUNCATE ignora
  RLS) — revocado en `20261228000001`, pgTAP 173 (15 checks). DELETE se
  conserva: el delete de app corre bajo `authenticated` + RLS.
- **hecho/probado** Entrada de catalogo enriquecida: fabricante, familia,
  version, material, global/propio/demo, `review_pending`, ladder de
  capacidades con primer bloqueo — sin tabla cruda de 20 columnas.
- **hecho/probado** Workspace: nueva seccion "Fuentes" — evidencia por
  sistema con objeto/parametro/valor/fuente/ambito/estado + acciones de
  revision solo para roles de escritura.
- **hecho/probado** Studio muestra compatibilidad: inspector de vano con
  picker de kits rankeado (compatible → indecidible → incompatible con
  razon), ejes identicos al engine (apertura, envelope via
  `bayEnvelopeMm`, masa via `leaf_weights` del calculo); 10 tests de
  `kitCompatibility`.
- **probado** Aislamiento de revision sellada: ya cubierto por
  `guard_referenced_catalog` + `test_historical_render_uses_frozen_
  snapshot_after_catalog_change` — el catalogo nuevo no muta REV-A.
- **hecho** Inventario de autoridad faltante real en `blocked-inputs.md`
  (sin numeros de demostracion).
- **pendiente-capturas** `docs/redesign/captures/phase04/` — dos
  experiencias (Fuentes + picker Studio), en curso via testing agent.

### phase-04 · cierre de bloqueo design-options (422)

El picker de kits era inalcanzable: `GET /api/v1/projects/design-options/<system>` devolvía 422 `technical_authority_required` en las tres series sembradas. Causa doble: (a) los `authority` JSONB guardaban numéricos como strings y los `EngineModel strict` rechazan la coerción str→Decimal/str→enum; (b) `load_handle_policy` hacía `model_validate` directo — insatisfiable por construcción para cualquier payload con enums. Se corrigió el loader (no solo los datos): parsers canónicos en `dekopen_engine.manufacturing` compartidos por `engine_api` y `documents`. Migración `20261228000002` inserta nuevas versiones con numéricos nativos y `version` embebido sincronizado; `seed.sql` y las tres migraciones históricas quedaron reparadas para instalaciones frescas. pgTAP 174 guarda el invariante (latest-version sin numéricos string, versión embebida consistente). Verificado: 200 HTTP con token tenant real en DEMO_60/ALU_65/GLASS_45 (`kits=5`, `handle_policy` presente), 248 tests backend verdes, 467 engine, pgTAP 172–174 verdes, `db reset` limpio de 130 migraciones.

### phase-05 · unificar trabajo comercial

- **hecho/probado** Lista de proyectos: búsqueda `?q=` por código/nombre/cliente, filtro `?status=` con UI propia, orden `?sort=` (reciente/nombre/código), columna Revisión (`current_revision`, mono), columna "Siguiente paso" por estado comercial, scroll restaurado al volver. Test e2e-dom: params en URL + navegación detalle→lista conserva valores.
- **hecho/probado** Cronología humana en el proyecto: sección "Actividad" (lazy) con cotización emitida, enlace enviado/aprobado/cambios/revocado, pagos y anulaciones con autor, facturas/NC, posiciones modificadas — ordenada por fecha, sin eventos fabricados. Test dom verifica los tres tipos.
- **hecho/probado** Duplicar posición explica lo conservado: banner "Copia de P{n}…" en el editor al llegar por `?copy=`; la posición nueva guarda con identidad propia (cubierto por tests existentes del copy flow).
- **hecho** Filas de posición ganan resumen tipología+acabado; qty inline ya recalcula vía `positionsUpdate` + refetch (totales y producción futura desde backend).
- **documentado** Sin UI de reorden (D23): `position_index` es clave industrial emitida. Sin edición en lote: no existe endpoint; el mandato conserva endpoints.
- **pendiente-capturas** captures desktop/mobile + video del recorrido de aceptación vía testing agent.

- **probado** Aceptación en vivo (`docs/redesign/captures/phase05/`, video del recorrido): crear cliente (sin email + nombre 110 chars) → proyecto → 3 posiciones → duplicar (banner "Copia de P1…", nueva identidad P4, original intacta) → cantidad inline recalcula → Studio → volver (contexto intacto) → precio/revisión. WORKSHOP_MANAGER lectura pura sin controles de edición; OPERATOR "Sin acceso" por diseño; obra de 100 posiciones sin overflow a 1440 ni 390.
- **corregido** Defectos de la corrida: `.position-row` reflows a dos filas bajo 640px (scrollWidth 521→390); Guardar nombra el bloqueo real cuando falta vidrio/panel (`glazingMissing`); summary "Importar" renombrado "Documentos de origen" (leía como acción habilitada en roles de lectura — el upload ya estaba gateado por canWrite).

## Fase 06 — Decisión de precio confiable

- **hecho/probado** Tabla de decisión gana columnas Unitario y Desc. por línea (desde `line_detail` sellado, no derivado), miniatura real de la posición (`PositionThumb` — dibujo SVG, no icono), importes con `white-space:nowrap` para que ningún monto se parta.
- **hecho/probado** Modo 1 renombrado "Margen sobre venta" + hint con fórmula (D26); test engine congela `costo/(1−margen)` → 133,33 sobre costo 100, y `gross_margin_pct` lee 0.25 del precio resultante.
- **hecho/probado** Bloqueo posicionado "P04 · …" en alerta con enlace `?focus=glass` a cost-lists (owner) o instrucción para estimador (D28); FIXABLE_CODES cubre las 9 causas de catálogo.
- **hecho/probado** Contrato `line_detail` probado end-to-end: preview→apply→response con cantidad 3, unitario exacto y descuento 5% ⇒ neto línea 90000 cuantizado; operaciones legacy sin el campo responden `lines` idénticas a antes.
- **pendiente-capturas** evidencia en vivo (margen editado, comparación, bloqueo+resolución, paridad pantalla/PDF/portal) vía testing agent.

## Fase 07 — Propuesta comercial que se entienda

- **hecho/probado** Política editorial por contenido: `.cover` sólo cuando `len(groups) > 8`; el resto lleva `.dochead` compacto con identidad del emisor + cliente/proyecto + inversión. Cierre `.doc-duo` incondicional (Inversión | Condiciones | Aceptación en 3 columnas, `break-inside:avoid`). Páginas verificadas: 1pos=1, 5grp=3, 11grp=6, 100pos=31, puerta=1 — sin huérfana de firma.
- **hecho/probado** Ficha de posición: dibujo ~35% + specs (Sistema, Apertura humana desde `parametric_tree` con mano, Vista=Exterior, Vidrio, Acabado, Incluye primeros 4 + "+N"), código+ubicación "P03 · Dormitorio", dims, qty, precio unitario/descuento/importe; `overflow-wrap:anywhere` en nombres largos; agrupación por unidades idénticas intacta; `.compact` >6 grupos.
- **hecho/probado** Totales: extras sellados como nota "Incluye… — dentro del neto" (D30 — nunca sumados de nuevo); anticipo/cobrado/saldo y vigencia/plazo/condiciones del contrato existente preservados.
- **hecho/probado** Share honesto: "Abrir en WhatsApp" / "Abrir correo" / "Copiar enlace" → "Enlace copiado al portapapeles"; evento de actividad "Enlace de aprobación creado" (nunca "correo enviado").
- **hecho/probado** Otros documentos (NC/despacho/factura/comprobante/pedido) comparten masthead y lenguaje de referencia conservando reglas propias — NC parcial referencia partidas y origen sin alterarlo.
- **hecho/probado** Portal en vivo (testing agent): header sobrio, ficha+imagen, inversión, condiciones, CTA; 390px una columna; estados borrador/emitida/aprobada/rechazada/vencida/sustituida; aprobar y pedir-cambios idempotentes (doble clic/refresh/reintento no duplican); enlace antiguo identifica y enruta; sin botones activos tras cambio de estado; token no expone costos/márgenes.
- **corregido** Defecto real: `project_payment_links` invisible para `portal_backend` → "Pagar ahora" inalcanzable. Migración `20261228000003_portal_payment_link_read` (D32) verificada end-to-end con `portal_quote` — `payment_url` devuelto.
- **documentado** Alternativas fuera del DOC-01 (D31); `missing` opcional → "—" sin "None"; Carta/A4 declarados con fuentes embebidas; legible en grises.
- **pendiente honesto** `payment` state en portal devuelve `None` hasta que existe una fila `project_payments` — correcto (sin abono registrado no hay abono); banner de sustituida enlaza a la vigente.

## Fase 08 — Visibilidad de compras/recepción/stock/retazos

Recon: la maquinaria del backend ya era profunda (ledger idempotente con `receipt_key`, lock `version_id:order_type`, `cancel_order` con `released_at`, retazos con reserva atómica y lineage). Los huecos reales eran de superficie.

- `orders_index` + `purchasing_state` proyectan `released_qty`, `damaged_qty`, `receipt_count` (D33). Pedido cancelado → muestra liberado + CTA "Volver a pedir"; incidencia → alerta + columna Recepciones en el índice.
- Necesidades con SKU duplicado declaran su agregabilidad (D35). "Fecha necesaria" documentada como ausente sin autoridad (D34) — no fabricada.
- Tests: `test_orders_index_projects_orders_with_received_totals` extendido (39 verdes); vitest purchasing 15 verdes.
- **hecho/probado en vivo** Fase 08 aceptación completa (agente de testing, stack live @ `eb02e73`): J1 necesidad→pedido→recepción parcial con daño→restante→reserva→consumo con conservación exacta y trazabilidad M-xx; el dañado nunca llega a stock. J2 cancelar sin recibir → pendiente + "Volver a pedir" sin duplicar. J3 cancelar PARTIALLY_RECEIVED → `released_qty=3` exacto, re-compra cubre sólo el remanente (D36). J4 doble confirmación concurrente → un pedido, retry idempotente. J5 vidrios parecidos no fusionan; J6 retazos BAR/SHEET con reserva atómica y linaje `origin_order_id`. J8 DOC-02 PDF/XLSX coincide con pantalla (proveedor, líneas, total m², trazabilidad).
- **corregido en vivo** 6 defectos reales encontrados por la prueba: split SQL de `purchasing_state`, set→`ANY` en retazos, `PARTIALLY_RECEIVED→CANCELLED` rechazado por el guard de pedido, check de conteo en confirm, kwarg `_line_snapshot`, detalle de errores en español. Más: buscador SKU/especificación en stock y retazos (`spec_text` desde `attributes` almacenado — migración `20261228000006`), scroll de recepción móvil, excedente "Pendiente 0 (+N)".
- **pendiente honesto** "Pendiente" admite sobre-recepción (por diseño) y la muestra como `0 (+N excedente)`. Sin video (X server de sesión caído) — evidencia en PNG + PDF/XLSX reales.

## Fase 09 — Pack de taller con criterio de operario

- **hecho** Identidad física `Pnn-Umm-Mkk` por unidad en plan, alzado, tabla, etiqueta y QC (D37); agrupaciones llevan lista/rango de identidades, nunca "M-06 · +3" solo.
- **hecho** Bloque de barra completo: origen, convención, sección declarada o aviso explícito, diagrama con guías/carriles, tabla encuadrada, conservación + disposición de retazo (D38) — en `cut_pack.py` y `pack.py`.
- **hecho** Pantalla de optimización honesta (D39): insumos, estrategias con efecto real, cantidades separadas con denominador, compare sin "óptimo global", causas de sin-solución.
- **hecho** Etiquetas 100×50 mm reales + QR con quiet zone escaneado con zxing-cpp (D40); alzado con largo de corte; piso tipográfico 7 pt.
- **probado** `aceptacion-casos.pdf` (5 p: unidades iguales, 12 piezas cortas, 45°/90°, pieza casi largo útil, retazo recuperable/no, sin solución, vidrio no rectangular) + `aceptacion-100pos.pdf` (60 p): 0 solapamientos, 0 texto fuera del papel, grises legibles; conservación "cierra exacto" o desbalance señalado en rojo.
- **pruebas** 3 tests nuevos en `test_production.py` (identidad física por unidad, fallback sin unit_index, conservación); 114 verdes en test_production.

## Fase 10 — Taller: hacer, comprobar y entregar

Recon: la ruta industrial y sus autorizaciones ya existían (proceso declarado → pasos por estación → QC → embalaje → despacho → POD). El trabajo fue jerarquía por rol y despacho parcial real.

- **hecho** Entrada por rol en `/production`: OPERARIO ve cola por estación (qué espera en su puesto) + trabajo activo + siguiente tarea; ENCARGADO ve órdenes con prioridad/fecha/material/bloqueos + tablero de estaciones; INSTALADOR sólo unidades/bultos/destino (rol de terreno, lectura); ESTIMADOR lectura. Cola filtrable y deep-linkable (`?status=`, `?station=`, `?order=`).
- **hecho** Estación: cabecera OT/revisión/estación/estado, tarjeta de operario con la pieza al centro y **barra de acción pegajosa** — iniciar/registrar/completar según transición real, siempre visible bajo el scroll de materiales/ops.
- **hecho** QR / enlace directo: `?piece=Pnn-Umm-Mkk` preselecciona la pieza exacta; `?order=` abre la OT. El código físico de la fase 09 sigue unido hasta despacho.
- **hecho** QC: Pass/Fail explícito por ítem (selector de ítem `qcItem`), nunca por abrir pantalla; rechazo → incidencia + disposición + OT de remake ligada a la original (`remake_reason`); avance no llega a 100% con rechazos sin resolver.
- **hecho** Embalaje/despacho parcial (D41): `deliveries.unit_indexes` + `deliveries_one_open_trip` (un viaje abierto por orden); `dispatch_notes.unit_indexes` + `delivery_id` — cada guía pertenece al viaje que la llevó; un viaje FAILED libera sus unidades para re-despacho bajo guía nueva; POD por viaje (`?delivery=`); `installation_requires_delivered` hasta cubrir el manifiesto completo; saldo pendiente explícito en UI.
- **corregido en vivo** DEFECTO fase 10: `trace` devolvía 422 a OPERARIO/INSTALADOR — lecturas de `projects`/`project_versions` bajo `authenticated` chocaban con `project_manual_read`. Ahora bajo `documentary_backend` (D42) con tests que fijan la frontera RLS (`_BackendGate`). Mismo hueco cerrado en `_order_ops` (archivos CNC).
- **pruebas** 1049 verdes backend (2 nuevas de frontera RLS), 14 vitest producción, migraciones 007/008 + pgTAP 133 (`plan(14)`, columna delivery_id).
- **probado en vivo** Aceptación de 4 roles completa (agente de testing, stack live, HEAD `b4a59a3`+): ruta OT-03 entera en UI como OPERARIO incl. ops de mecanizado en P03-U01-M06 y evidencia QC FAIL; signo WM → HOLD → remake RM-01 enlazado, ruta completa hasta COMPLETED; camino rework (UNBLOCK→QC pass) también probado. OT-01: despacho→FAILED libera unidades→dos viajes parciales (GD-0002={1}, GD-0003={2}) cada uno con guía+POD propios→instalación→INSTALLED. Los 403 de operador/instalador/estimador de `2505edf` se mantienen; aislamiento cross-org verificado (GET/trace → `work_order_not_found`, cambio de org → 403). Despachos y confirmaciones concurrentes → una guía/una CE; replays idempotentes; re-transición en orden completada → 422.
- **corregido en vivo** (7 defectos encontrados por la prueba): traza 422 a piso (D42), grant `clients` a `documentary_backend` (despacho 409), lock de proyecto sólo cuando hay cobro en POD (instalador 404), `LIMIT 1` en viaje abierto (segundo viaje 422), `canField` para acciones de terreno del instalador, deep-link `?piece=` que se auto-borraba en carga fría + auto-navegación a la orden única, overflow móvil de `.production-orders` (min-width:0 en ítems del grid — `scrollWidth` 963→500/390), rechazo QC silencioso → error de acción ahora es toast fijo visible bajo scroll.
- **pendiente honesto** Sin video (X server de la sesión caído) — evidencia en PNG + PDF reales. Auto-selección de estación post-scan no demostrable en órdenes ya completadas (el código existe; requiere orden activa). Picker de subconjunto de despacho no capturado visualmente (ventana transitoria); API de subconjuntos probada.

## Fase 11 — Mecanizado/CNC preciso, explicable y verificable

Recon (auditoría de lo vigente): la mayoría de los riesgos históricos ya estaban corregidos en HEAD — ordenación numérica de SAW_CUT, ángulos por cara en trims, `boundary_conflict`/`tail_sliver`, doble coordenada (plano del conjunto + u local con datum), herramientas reales con compatibilidad, ops sin estación visibles (`unclaimed`), exports con `unemitted_kinds` y verdict UNVERIFIED cuando no hay dry-run. Lo que seguía fallando: cambio de configuración de máquina no invalidaba programas, falta de profundidad/herramienta no producía bloqueo exacto, point_prep se leía como mecanizado ejecutable, la leyenda del pack decía "plano del conjunto" para una coordenada local, y ningún export llevaba manifiesto verificable.

- **hecho** Bloqueos exactos `depth_undeclared` / `tool_undeclared` (BLOCK, con miembro+clase en `detail`) en `validate_operations`; la pieza no ejecutable nunca llega a programa (D43).
- **hecho** Programa ligado a plan+máquina: `input_fingerprint` = plan_fp+machine_fp; edición de máquina/herramienta/postprocesador → SUPERSEDED en lectura y descarga (D43).
- **hecho** "Ref. montaje" para `point_prep` en pack PDF, tarjeta de estación y panel CNC; datum Ext. A/B marcado en la tira del pack y leyenda corregida a coordenada local del miembro.
- **hecho** `manifest.json` en todo export (ops export + programa CNC): archivos con sha256+bytes, conteos, identidad, hora, responsable. CSV gana columna `sequence_no`.
- **pruebas** 4 tests nuevos en `test_operations.py` (profundidad faltante, herramienta faltante, point_prep no bloquea por profundidad, op manual válida) + test de manifiesto en `test_production.py`. Suite CNC/producción verde.
