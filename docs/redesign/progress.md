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
