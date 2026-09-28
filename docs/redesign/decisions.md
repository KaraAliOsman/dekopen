# Decisiones de la fase 00 (base confiable)

Base: `devin/1790335313-commercial-workspace` @ HEAD (ver `evidence-index.md` para el SHA exacto del commit de este paquete; la evaluación se hizo sobre `297f121`).

## D1 — Moneda del proyecto vive en la operación aplicada, no en `projects`

`analytics/_summary` referenciaba `p.currency`, columna que nunca existió; el bloque
comercial se rompía en toda instalación limpia (HTTP 409 en `/analytics/summary`).
Corrección: la moneda se deriva de `pricing_operations.request->>'currency'` de la
operación `APPLIED` vigente de la revisión actual — la misma autoridad que usa
`projects/service._pricing_authority`. Pagos agregados vía `LEFT JOIN LATERAL`
sobre `project_payments` no anulados. Motivo: no añadir una columna nueva
(`projects.currency` sería datos duplicados que pueden divergir de la operación
que realmente fijó el precio).

## D2 — No revertir fixes post-snapshot

El mandato listaba 4 fallos sobre el snapshot `a3785f7`. Tres ya estaban corregidos
en commits posteriores; se verificaron en vez de revertir:

- F1 `purchase_retry`: migración re-fechada tras `order_cancellation` (que crea
  `orders.cancelled_at`); pgTAP `170_purchase_retry` pasa (15 tests: claim único,
  liberación, reintento, órdenes suplementarias, sin doble compra).
- F2 emisión bajo `service_role`: test parcheado con `transaction.atomic` (`ea7b040`).
- F3 sello de guía: el test afirma `payload["delivery"]["address"]` sellado.
- F4 hex fuera de tokens: convención `var(--theme-surface-panel)` para texto sobre
  acento; la firma conserva `#fff` literal documentado (se sella al POD impreso).

## D3 — El gate encontró defectos reales: corregir en origen, no relajar checks

Además del 409 de analytics, el gate E2E detectó fixtures e2e obsoletas frente a
`20261227000001_seed_reference_labels.sql` (SKUs `DEMO-*` → `COMPRA-*/VIDRIO-*/ACERO-*`)
y supuestos de navegación inválidos:

- `Administración` solo existe para OWNER|WM — el spec ESTIMATOR ahora afirma su
  ausencia (aserción más fuerte, no más débil).
- React Query `staleTime` sirve el proyecto cacheado al volver del editor —
  las lecturas que el test afirma desde el backend ahora se fuerzan con
  `page.reload()` explícito (la página seguiría mostrando "Añadir vano" con
  el proyecto cacheado de `position_count=0`).

## D4 — Fixtures sintéticos con identidad determinista

`scripts/dev_fixture.py` crea la org `DEKOPEN Demo Fixture`, una cuenta por rol
(OWNER/ESTIMATOR/WM/OPERATOR/INSTALLER), clientes, reglas de precio y lista de
costos que cubre TODOS los SKUs de compra del catálogo de referencia (consultados
dinámicamente de las tablas de autoridad). Proyectos: vivienda (4 posiciones),
obra grande (8 posiciones × qty 4), proyecto incompleto (posición guardada sin
precio). IDs por `uuid5` — la ejecución es idempotente.

Delimitación honesta: todo usa la familia `DEMO_60`, que NO tiene autoridad de
fabricación completa (solo cotización). Ningún fixture fabrica autoridad;
fabricar exige datos reales de fabricante (ver `blocked-inputs.md`).

## D5 — `make test-db` es la puerta única

El gate real encadena: `supabase start` → `db reset` (instalación limpia con todas
las migraciones en orden) → `db lint --fail-on warning` → `supabase test db`
(pgTAP completo) → `pytest backend/tests/integration/` → Playwright auth e2e con
servidores propios (rechaza puertos ocupados — matar dev servers antes) →
`verify_postgres16` (contenedor postgres:16-alpine fresco). Nada se reporta por
inferencia: un paso que no corre se reporta como bloqueado con su salida.

## D6 — Sin fusiones ni despliegues

PR #107 permanece abierto como visibilidad del trabajo continuo de la rama.
No se empujó a `main` ni se desplegó durante esta cola.

# Decisiones de la fase 01 (lenguaje visual y navegación)

Base: `devin/1790335313-commercial-workspace` @ `6c61859`.

## D7 — Tres capas de tokens: tema, estructura, material físico

`tokens.css` quedó en tres tieres: (a) `--theme-*` colores de interfaz que
cambian con claro/oscuro (superficie, texto, borde, selección, foco, acción,
peligro, aviso, éxito, información, disabled); (b) estructura — tipografía,
espacios 4/8/12/16/24/32/48, radios, sombras, z; (c) `--mat-*` colores
**físicos** del material en `:root` sin tematizar: el acabado del producto
sobrevive al cambio de tema por contrato. `--member-*`, `--model3d-*`,
`--op-*`, `--theme-glass-pane`, `--signature-ink` quedan como alias de
compatibilidad hacia `--mat-*` — cero cambios en call-sites.

**Studio, impresión y bot NO se subordinan al tema de la app**: el PVC blanco,
el aluminio anodizado, el vidrio y las firmas en documentos impresos mantienen
su color físico en ambos temas. Los bots/exportadores consumen `--mat-*`
(constantes físicas), no `--theme-*`.

## D8 — Escala tipográfica del mandato

`--text-xs` 0.75rem (12px), `--text-s` 0.8125rem (13), `--text-body` 0.9375rem
(15), `--text-title` 1.1875rem (19), `--text-display` 1.625rem (26). Nada que
se opere cae por debajo de 12px. Densidad: `--density-compact` 28px,
`--control-height` 36px escritorio, `--density-loose` 44px táctil.

## D9 — Rail de dominio: iconos + etiqueta; en Studio 64px

La navegación global tiene icono + etiqueta accesible. En rutas del editor de
posición (`/projects/:id/positions/...`) la rail se contrae a una tira de 64px
de solo iconos con `aria-label`+`title` — el canvas es el protagonista; el
breadcrumb del topbar conserva el contexto del proyecto. No existen dos menús
simultáneos con la misma jerarquía: el modo contexto (proyecto/producción)
reemplaza al dominio, no lo acompaña.

## D10 — Cabecera de sección única (`PageHeader`)

Todas las superficies de dominio (dashboard, proyectos, clientes, compras,
producción, precios, catálogo, facturación, ajustes, jobs) migraron a
`PageHeader`: crumbs + título + contexto + acciones, con una sola acción
primaria. Las acciones peligrosas se distinguen por variante (`danger`), no
por posición.

## D11 — Tabs con semántica real

`ui/Tabs`: `role=tablist`/`tab`, `aria-selected`, roving `tabindex`, flechas
←/→ que activan. Tabs de estado no tocan el router; tabs con `to` resuelven
la selección desde la URL (NavLink + matchPath). Migradas las navegaciones de
secciones de precios y catálogo (antes `aria-pressed` ambiguo).

## D12 — Campos numéricos: valor veraz, formato en presentación

`NumberField` conserva el string del usuario verbatim mientras edita; aplica
formato es-CL solo al salir del foco. Cero, vacío y desconocido son tres
estados distintos. `Field` exige etiqueta persistente (nunca placeholder),
ayuda y error asociados por id.

## D13 — Errores persistentes junto al trabajo; toasts solo confirmación

`Toast` existe para confirmaciones breves (TTL 4.2s, aria-live); los errores
que requieren acción quedan junto al formulario/ trabajo — y ahora se limpian
al cancelar (defecto encontrado en QA: banner de validación sobrevivía al
discard del form de clientes).

## D14 — Móvil 390px: reorganización, no compresión

Las filas del dashboard refluyen a nombre+estado / cliente+código; las tarjetas
KPI bajan un tier tipográfico; la grilla móvil es `minmax(0,1fr)` para que el
contenido haga ellipsis en vez de scroll horizontal. Criterio verificado:
`scrollWidth = 390` en dashboard.

## D15 — Hardware visual vinculado a autoridad, no a proporciones

Cada hoja resuelve un `HardwareVisualSpec` (`hardwareVisual.ts`) desde dos
fuentes reales: `hardware_kits.contents` (líneas categorizadas
HANDLE/HINGE/LOCK/ROLLER/FITTING con cantidades) y
`handle_requirement_policies` (miembro anfitrión, banda de montaje
superior→inferior, referencias verticales permitidas). Cuando el kit
declara un conteo de bisagras, ese conteo gobierna; cuando falta, el
heurístico por altura dibuja `approximate` (aristas visibles) y reporta
`hardware_convention`. Cuando el sku no resuelve o el kit no declara línea
HANDLE, el render informa `kit_unknown` en vez de asumir piezas.

Las manillas se diferencian por familia — batiente/oscilobatiente lleva
roseta+collar+palanca cónica; puerta, escudo largo de 240mm en ambas caras
con cilindro cuando el kit lo declara; corredera, uñero embutido por
defecto con tirador superficial solo en la hoja de la pista interior
(ninguna pieza atraviesa la hoja vecina); proyectante, manilla central en
el riel inferior. Tamaños físicos fijos del herraje — jamás porcentaje
del alto de la ventana.

El datum de manilla (`handle_height_mm`, referencia `OUTER_BOTTOM`) se
traza sin ocultar incompatibilidades: una altura declarada fuera de la
hoja o fuera de la banda de la política dibuja la pieza en posición
clamped **y** emite `handle_out_of_range`/`handle_datum_unsupported` —
chips en el viewport 3D y anillo de advertencia en el elevado 2D. Nada de
clamp silencioso.

## D16 — Colores físicos independientes del tema de interfaz

Los tokens `--mat-*` viven en `:root` sin tema y los consumen los
renderers 2D/3D; el bloque `[data-theme="dark"]` no los sobrescribe. El
viewport 3D añade un escenario neutro dedicado
(`--theme-viewport-stage`/`--theme-viewport-ground`, sí por tema) con
suelo y sombra de contacto — el acabado físico queda idéntico en ambos
temas; solo cambia el telón de fondo del estudio. PVC blanco se mantiene
blanco; antracita permanece antracita.

## D17 — El movimiento es presentación, no fabricación

Los estados Abrir/Abatir/Despiece son poses ilustrativas: pivotes por
familia (lateral para giro, inferior para oscilar), hoja+vidrio+herraje
mueven juntos y cada frame escribe transformaciones absolutas — cambiar
de modo no acumula desplazamiento. Cuando un producto no declara
recorrido autorizado, el viewport muestra el caption "Posición
ilustrativa" en vez de insinuar un límite de apertura real.

## D18 — La evidencia de parametros es una tabla, no un campo

`catalog_parameter_evidence` registra cada parametro critico con valor
tipado (texto, sin perdida de precision), unidad tipada, documento/pagina
fuente, URL solo http(s), ambito (SYSTEM/SERIES/GLOBAL/ORG), condicion de
aplicacion, declarador y estado de revision — sellos `declared_by`/
`reviewed_by`/`reviewed_at` escritos siempre en servidor bajo
`catalog_backend`; `authenticated` solo tiene SELECT. Una evidencia org
sobre una autoridad global queda org-scoped (un org atestigua lo que
reviso; no puede manchar el catalogo global). La importacion fija evidencia
automatica por campo del parser (`normalized`/`original`/`unit`/`source`)
con la fuente = archivo+import; idempotente por indice unico en
(tabla,fila,campo,documento,pagina).

## D19 — Higiene de privilegios: `authenticated` nunca TRUNCATE

Las tablas de autoridad de catalogo heredaban REFERENCES/TRIGGER/TRUNCATE
para `authenticated` por los default privileges de Supabase. TRUNCATE no
consulta RLS: una sesion SQL autenticada podria vaciar el catalogo de
todas las orgs + globales en una sentencia. Migracion
`20261228000001` revoca los tres privilegios en las 12 tablas de
autoridad; DELETE/UPDATE/INSERT se conservan porque el flujo de app los
ejecuta bajo `authenticated` + `can_manage_catalog`. pgTAP 173 lo fija.

## D20 — Compatibilidad fisica visible, no solo validada

`kitCompatibility.ts` replica los ejes del engine (apertura normalizada,
ancho/alto de hoja, masa maxima) sobre `KitChoice` enriquecido con el
envelope. El inspector de vano lista kits compatibles primero,
indecidibles marcados (`peso sin verificar` cuando `leaf_weight_kg` es
desconocido) e incompatibles consultables con su razon — nunca elegibles
como equivalentes. El engine revalida igual en el guardado; la UI informa,
no optimiza. `bayEnvelopeMm` reproduce la particion de `frontLayout`
(offset o mitad, menos media cara del premarco) para el tamano de hoja.
