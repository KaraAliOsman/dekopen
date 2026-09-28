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

## D21 — Autoridad JSONB: el parseo canónico vive en el motor

El contrato estricto (`EngineModel strict=True`) no puede validar JSONB crudo: JSON no produce instancias de enum ni `Decimal`, así que `model_validate` sobre `authority` era insatisfiable — `design-options` devolvía 422 en todas las series. En vez de relajar el modelo, el motor ahora exporta `handle_policy_from_json` / `placement_policy_from_json` / `reinforcement_policy_from_json` (manufacturing.py): coerción campo a campo (str→enum, str/number→Decimal, rechaza bool/NaN/no-finito) y luego el modelo estricto valida el resultado. `engine_api` y `documents` usan el mismo parser; el parseo tolerante ya no puede divergir del contrato. Los valores numéricos históricos almacenados como string se corrigen por nueva versión (`20261228000002`), nunca por UPDATE — la inmutabilidad de autoridad se respeta incluso en la reparación. El `version` embebido en el payload se sincroniza con la versión de fila.

## D22 — Estado de la lista de proyectos vive en la URL

Búsqueda (`?q=`), filtro de estado (`?status=`) y orden (`?sort=`) se guardan en los search params con `replace` — volver de un detalle conserva contexto sin store paralelo y el dashboard puede deeplink (`/projects?status=QUOTED`). La posición de scroll va en `sessionStorage` por org y se restaura solo cuando las filas existen. La columna "Siguiente paso" usa sólo `status` (el listado no trae cobranza/aprobaciones); la acción precisa vive en `projectNextAction` del detalle. Revisión se muestra como columna propia (`current_revision`) — estado comercial y referencia de revisión no comparten badge.

## D23 — Reordenar posiciones no rekeya identidad industrial

`position_index` es la clave emitida: congelación, compare, packs de corte y documentos la referencian. Una UI de reordenar implicaría renumerar posiciones ya emitidas — identidad industrial mutable. No se ofrece reorden; el orden nuevo de trabajo se expresa creando/duplicando posiciones (código nuevo, P4, P5…). Documentado aquí porque el mandato exige que el reorden "no cambie claves industriales ya emitidas": sin UI de reorden, la invariante no puede violarse.

## D24 — Duplicar = intención editable con identidad nueva, explicada

`/positions/new?copy=<id>` ya cargaba el diseño fuente sin baseline (siempre dirty, guarda como posición nueva). Ahora el editor muestra un banner explícito — "Copia de P{n}: conserva diseño, sistema, acabado, vidrio y ubicación; al guardar se crea una posición nueva con código propio" — para que el origen no sea ambiguo. La fuente nunca se toca.

## D25 — Cronología = evidencia persistida, nunca actividad inferida

La sección "Actividad" del proyecto compone eventos sólo desde filas reales: `versions.emitted_at` (cotización emitida), `quote_links.created_at/decided_at/revoked_at` (envío/aprobación/cambios/revocación), `payments.recorded_at/voided_at` + `recorded_by`, `invoices`/`credit_notes.created_at`, y `positions.updated_at` (top-5 recientes). Sin fila, no hay evento — ningún "visto" o "abierto" fabricado. La sección monta sus queries al abrirse (react-query dedup por key con el header).

## D26 — Margen es sobre venta; recargo sobre costo no comparte el nombre

`COST_PLUS_MARGIN` (modo 1) siempre calculó `costo / (1 − margen)` — margen sobre venta — pero la UI lo etiquetaba "Costo más margen", que lee como recargo. El label pasa a "Margen sobre venta" con hint que muestra la fórmula con los números del mandato (100 → 133,33 a 25%). El test `test_mode_one_is_margin_on_sale_not_markup` congela la semántica (133,33 ≠ 125). Otros modos no tocan esta fórmula: PRICE_PER_M2 usa precios de lista, no márgenes.

## D27 — Detalle de venta por línea viaja en el resultado sellado

El `lines` público histórico sólo llevaba `(position_index, net)` — importe de línea, nunca unitario (el contrato del mandato: "un precio por posición no es necesariamente un precio por unidad"). `preview`/`apply` ahora persisten `line_detail` dentro del `result` jsonb (inmutable con la operación): `quantity`, `unit_price` (exact_unit_price engine cuantizado a 0.0001 — en modo TARGET el unitario asignado), `discount_pct` (fracción del contrato). La respuesta pública lo funde por position_index en las líneas; operaciones antiguas simplemente omiten los campos (nullable). La UI nunca deriva unitarios — los lee.

## D28 — Error de pricing posicionado en texto, con enlace de acción por rol

El backend ya producía "P04 · Falta precio de vidrio 4/12/4…" via `PRICING_ERROR_DETAILS`; el frontend renderizaba el primer término como clave i18n y perdía el posicionamiento. Ahora el alerta usa `payload.error.detail` y un mapa `FIXABLE_CODES` enlaza a `/pricing/cost-lists` (OWNER) o muestra "Pídele al administrador…" (ESTIMATOR, que no puede editar catálogo). El código i18n queda como resumen, no como única salida.

## D29 — Portada editorial por contenido, no por regla universal

`.cover { break-after: page }` imponía portada vacía a una cotización de una posición. La política nueva decide por contenido: `len(groups) > 8` → `.cover` completo; el resto → `.dochead` (banda compacta de identidad emisor + "Preparado para…" + inversión + pie del emisor). El bloque de cierre (Inversión | Condiciones | Aceptación) es una banda `.doc-duo` incondicional de 3 columnas con `break-inside:avoid` — ninguna propuesta termina en una página huérfana de dos líneas de firma (1pos=1p, 100pos=31p verificado).

## D30 — Extras sellados se muestran dentro del neto, nunca sumados otra vez

`pricing.request.extras` ya está dentro de `total_price_net`. Renderizarlos como filas aditivas los cobraría dos veces en pantalla. `_pricing_extras` los dibuja como nota de inversión — "Incluye {label} ($ amt | sin costo) — dentro del neto" — dentro del neto declarado, inequívoco como pide el mandato.

## D31 — Las alternativas no existen en el snapshot comercial sellado

Las alternativas viven sólo en el flujo AI de design-alternatives, fuera del `frozen_revision` que alimenta DOC-01. No hay sección de alternativas porque no hay datos sellados que mostrar — se documenta en vez de fabricar la sección. Si una alternativa se materializa, llega como nueva posición/revisión y entonces sí participa.

## D32 — Portal lee `project_payment_links` bajo `app.portal_org_id`

La policy `project_payment_links_isolation` usa `current_user_org_ids()` que devuelve vacío para `portal_backend` (auth.uid() nulo por diseño — el token es la única capacidad). Resultado: el portal nunca veía el link de pago y "Pagar ahora" era inalcanzable aunque hubiera link PENDING. La migración `20261228000003` otorga SELECT + policy org-scoped idéntica a la de `project_payments` (`20261207000000`) — el token acota la org por `app.portal_org_id`, ninguna otra org es visible. Verificado end-to-end: `portal_quote` devuelve `payment_url` real.

## D33 — Incidencia de recepción visible en el índice, no sólo al abrir el pedido

`orders_index` sólo agregaba `total_qty`/`good_qty`/`outstanding`; un pedido PARTIALLY_RECEIVED con unidades dañadas era indistinguible de uno sano, y un pedido CANCELLED no declaraba cuánto liberó. Ahora el índice proyecta `receipt_count`, `damaged_qty` (JOIN a `order_receipts`/`order_receipt_lines`) y `released_qty` (`released_at` estampado por `cancel_order`). La columna "Recepciones" marca `dañado: N` en rojo cuando hay incidencia; el pedido cancelado muestra la cantidad liberada y un CTA "Volver a pedir" que enlaza a la necesidad abierta (el lote liberado ya vuelve a `unclaimed_requirements` por el mismo `released_at`). `purchasing_state` (vista por versión) recibe los mismos tres campos.

## D34 — "Fecha necesaria" documentada como no disponible, no inventada

El mandato pide "fecha necesaria" por necesidad. El modelo real no la tiene: `purchase_requirement_lines` no lleva fecha y `deliveries.scheduled_date` está scoped a la OT, no a la necesidad de compra. En lugar de fabricar un campo, la necesidad muestra lo que sí tiene autoridad (requerido, reservado/disponible, pendiente, obra/revisión) y el gap queda registrado aquí. Si se decide un "needed-by", la fuente correcta es la fecha de entrega planificada de la OT que origina la necesidad — vía `purchase_allocations`, no una columna nueva sobre la línea.

## D35 — Agregabilidad declarada en la lista de necesidades

Cuando varios requisitos comparten `purchasing_sku`, la sección muestra `consolidateHint` explicando que se consolidan en la misma orden al asignar un proveedor y que cada línea conserva su traza (positions de origen ya viajan en `requirement_lines[].positions`). No se presentan como duplicados sin explicación ni se fusionan en una sola fila perdiendo la relación línea→posición.
