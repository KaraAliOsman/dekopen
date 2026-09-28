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
