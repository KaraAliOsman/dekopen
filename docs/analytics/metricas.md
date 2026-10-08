# Analítica — definiciones de métricas (P24)

Contrato de cada cifra que muestra `/analitica`. Una métrica existe sólo si
aquí está escrita: fórmula, fuente (tablas y columnas), filtros, tratamiento
de nulos, período y la consulta SQL versionada que la calcula.

Reglas comunes:

- **Ámbito**: toda métrica se calcula dentro de una organización
  (`org_id = target_org`). El acceso lo exige la función SQL: el llamante
  debe ser miembro activo de la org con rol `OWNER` o `WORKSHOP_MANAGER`
  (`private.documentary_role`) — organización ajena o rol sin permiso
  levanta `analytics_forbidden`. No existe ninguna agregación entre
  organizaciones.
- **Período**: `[desde, hasta]` inclusive, fechas calendario en la zona
  `America/Santiago`. Los `timestamptz` se filtran por
  `(ts AT TIME ZONE 'America/Santiago')::date BETWEEN desde AND hasta`.
  Período por defecto de la UI: últimos 90 días.
- **Permiso financiero**: montos y márgenes sólo se devuelven si el rol del
  llamante está en `tenancy_organizations.analytics_financial_roles`
  (por defecto `{OWNER}`). Sin ese permiso la función devuelve
  `"financial": false` y `null` en todo campo monetario — jamás una cifra
  "sanitizada" disfrazada.
- **«Sin dato»**: cada métrica responde `{value, n, cause}`. `value NULL`
  siempre va con `cause` (por qué falta). Un `0` es un número real (cero
  cotizaciones emitidas es un hecho), no un nulo; las tasas con denominador
  cero sí son `NULL` + causa.
- **Moneda**: montos netos en la moneda del documento (`CLP` salvo que la
  cotización se haya emitido en otra; la columna de detalle la declara).
- **SQL versionado**: las consultas viven como funciones
  `private.analytics_*` en la migración
  `supabase/migrations/<ts>_p24_analitica.sql`; cada test pgTAP en
  `supabase/tests/database/187_p24_analitica.test.sql` fija el valor
  esperado calculado a mano sobre el fixture.

---

## 1. Ventas

Cohorte base: **cotizaciones emitidas** = filas de `public.project_versions`
con `emitted_at` dentro del período (una revisión emitida = un documento
al cliente; re-emitir genera otra fila).

| Métrica | Definición |
| ------- | ---------- |
| `emitted` | `COUNT(*)` de la cohorte. `n` = filas. |
| `approved` | Cohortes cuya decisión actual (`customer_approvals.status` sobre la revisión, la fila vigente del enlace) es `APPROVED`. |
| `declined` | Ídem `DECLINED`. |
| `changes_requested` | Ídem `CHANGES_REQUESTED` (cliente pidió cambios — decisión viva, no terminal). |
| `pending` | Ídem `PENDING` (emitida, sin respuesta). |
| `revoked` | Ídem `REVOKED`. |
| `conversion_pct` | `100 × approved / (approved + declined)`. **Nulo** con causa `sin decisiones en la cohorte` si el denominador es 0 — `CHANGES_REQUESTED` no es rechazo ni aprobación. |
| `avg_decision_days` | Promedio de `decided_at - emitted_at` en días sobre la cohorte **decidida** (`APPROVED`/`DECLINED`). Nulo + causa si ninguna decidió. |
| `pipeline_net` | Neto de la cohorte aún abierta (`PENDING` + `CHANGES_REQUESTED`), sumado desde `snapshot_json->'pricing'->'result'->>'project_net'` (trato sin alternativas). Fases: `PENDIENTE` (vigente), `EN_CAMBIOS`, `VENCIDA` (`expires_at` pasado sin decisión). |
| `by_estimator` | Cohorte agrupada por `project_versions.emitted_by` → correo vía `private.user_email` (la identidad del emisor es quien emitió el documento). Emitidas/decididas/aprobadas + `conversion_pct` por estimador. |
| `by_typology` | Cohorte agrupada por **tipología principal** de la revisión: la `typology` de la `project_positions` con mayor `price_net` del proyecto (empate → menor `position_index`); si el proyecto quedó sin posiciones, `«Sin tipología»`. Emitidas/aprobadas/neto por grupo. |
| `rejection_reasons` | `decided_note` de los eventos `DECLINED` y `CHANGES_REQUESTED` (`customer_approval_events`) sobre la cohorte, agrupado por nota normalizada; nulo-vacío se reporta como `«Sin motivo escrito»`. |

Función: `private.analytics_sales(target_org, desde, hasta)` → `jsonb`.

## 2. Margen — cotizado vs. real por obra

Cohorte: **obras aprobadas en el período** = proyectos con una decisión
`APPROVED` (`customer_approvals.status`, `decided_at` dentro del período).
La revisión que manda es la aprobada (`customer_approvals.project_version_id`).

**Margen cotizado**: del resultado de precificación sellado en la revisión
(`snapshot_json->'pricing'->'result'`):
`cotizado_neto = project_net`, `cotizado_costo = deal_cost_net`,
`cotizado_margen_pct = 100 × (neto − costo) / neto` (idéntico a
`margin_realized`, recalculado aquí para no depender de la clave).
Revisión anterior a P07 sin `result` → `«Sin dato»` con causa
`revisión sin resultado de precio`.

**Costo real** de la obra — sólo componentes medibles:

| Componente | Fuente y valoración |
| ---------- | ------------------- |
| Material consumido | `inventory_movements` `CONSUMPTION` + `SCRAP` con `order_id` ∈ OT de la obra (incluye remakes). Cantidad × precio: (a) último `order_requirement_lines.line_snapshot->>'unit_price'` para ese `purchasing_sku` en una OC no anulada — precio pagado real; (b) `cost_list_items.unit_cost` vigente (misma lista que cotizó); (c) sin precio → no suma y queda en `unpriced` con causa `sku sin precio`. |
| Retazos consumidos | Movimiento `CONSUMPTION` con `remnant_id`: `length_mm × precio/mm` del artículo autoridad (`profile_purchase_mappings.commercial_sku` → precio ÷ `profile_articles.commercial_length_mm`; `reinforcement_articles.commercial_sku` → precio ÷ `stock_length_mm`). Sin cadena de precio → `unpriced`. |
| Mano de obra real | `Σ (finished_at − started_at)` de `production_steps` DONE de las OT × `tenancy_organizations.analytics_hourly_rate_clp`. Tarifa nula → componente `«Sin dato»` con causa `tarifa horaria no configurada` y la obra declara `partial: true`. |
| Costo de instalación real | No existe fuente (horas de terreno no se registran) → declarado en `missing` como `costo de instalación no medido`; nunca se inventa. |

`real_margen_pct = 100 × (neto_aprobado − costo_real) / neto_aprobado`;
con componentes incompletos la obra se muestra igual pero marcada
`partial` y su causa explícita — nunca una cifra silenciosa.

**Desviación** `deviation_pp = real − cotizado` en puntos porcentuales y
`deviation_net` en CLP. Agregados: promedio por tipología; globales sólo
sobre obras `COMPLETED` (todas las OT terminadas/instaladas) — una obra en
curso muestra su acumulado marcado `EN_PRODUCCION`.

**Descomposición por causa** (roof-raiser §8) — `analytics_margin_breakdown`:
`Δcosto = material_extra + remake + descarte + horas` con el monto de cada
causa y el enlace al origen:

- `material_extra` = costo real de material − material cotizado
  (`Σ materials_cost` de `input_snapshot.positions`, posiciones incluidas).
- `remake` = consumo valorizado de las OT con `payload_json->>'remake_of'`.
- `descarte` = movimientos `SCRAP` valorizados.
- `horas` = costo laboral real − labor cotizada (`Σ area_m2 × labor_rate_per_m2`).
- `descuento` (informativo) = `Σ (precio sin descuento por línea) − project_net`,
  del `line_detail` sellado.
- Filas origen: OTs (`code`, estado, remakes), movimientos valorizados
  (`sku`, cantidad, precio, fuente del precio), horas por estación.

Funciones: `private.analytics_margins(target_org, desde, hasta)`,
`private.analytics_margin_breakdown(target_org, project_id)` → `jsonb`.

## 3. Producción

Cohorte de OT: `orders` `WORKSHOP_OT` de la org que **reportan en el
período** — las que tuvieron algún consumo (`CONSUMPTION`/`SCRAP`) o fueron
completadas (`WO_COMPLETED`) dentro de la ventana. La merma de cada OT se
mide con su libro de consumos completo (una OT se consume una sola vez);
el período elige qué OTs reportan, no recorta su ledger.

| Métrica | Definición |
| ------- | ---------- |
| `merma_plan_mm` | `Σ payload_json->'optimization'->'bars'->'metrics'->>'process_waste_mm'` (merma declarada por el optimizador: kerf + refilados + colas no reutilizables). OT sin `optimization` → `«Sin dato»` por OT, excluida del agregado. |
| `merma_real_mm` | `mm_consumidos − productive_length_mm − mm_retazos_devueltos + mm_desechados`. Consumidos = barras del plan (`workshop_cut_plan[].stock_length_mm`) acreditadas por el ledger (CONSUMPTION) + `length_mm` de retazos consumidos; desechados = `SCRAP` con equivalencia a mm (ítem barra × largo del plan o retazo). Retazos devueltos = `produced_bars[].remainder_mm`. Una barra consumida cuyo `stock_sku` no aparece en el plan no tiene largo medible → la OT queda `unmeasured` y sale del agregado (nunca suma 0). Positivo sobre el plan = merma no prevista. |
| `merma_placas_mm2` | En placas (m²): `mm²_consumidos − mm²_colocados − mm²_retazos_producidos + mm²_desechados`. Consumidos = ítems hoja del inventario (`attributes.sheet_width_mm × sheet_height_mm`) y retazos SHEET; colocados = `sheets[].placements` del plan; producidos = `sheets[].produced_remnants`. `«Sin dato»` si no hubo placas. |
| `aprovechamiento_pct` | `100 × productive_length_mm / mm_consumidos` por OT y en agregado (Σ productivo / Σ consumido). Nulo + causa si no hay mm consumidos. |
| `retazos` | Consumidos (`CONSUMPTION` con `remnant_id`), generados (`produced_bars`/`produced_sheets` + `origin='PRODUCTION'`), desechados (`SCRAP` sobre retazos). Cantidades y mm. |
| `station_times` | Por `production_steps.code` de pasos `DONE` en el período: promedio y mediana (`percentile_cont(0.5)`) de `finished_at − started_at` en horas, `n` = pasos. Paso sin `started_at` → excluido con causa en el detalle. |
| `ot_punctuality` | OT con evento `WO_COMPLETED` en el período × `committed_date = MIN(deliveries.scheduled_date)`: `A_TIEMPO` si `completed::date ≤ committed_date`, `ATRASADA` si mayor, `SIN_PLAZO` si la OT jamás tuvo entrega agendada. La tasa usa sólo con-plazo; los `SIN_PLAZO` se listan aparte. |
| `remakes` | Órdenes con `payload_json ? 'remake_of'` creadas en el período: count + detalle `{remake_code, origen, causa}` donde causa = `remake_reason` (ítem QC o incidencia de obra; sin motivo → `«Sin causa registrada»`). |

Función: `private.analytics_production(target_org, desde, hasta)` → `jsonb`.

## 4. Instalación y postventa

| Métrica | Definición |
| ------- | ---------- |
| `deliveries_punctuality` | Viajes (`deliveries`) con `scheduled_date` en el período: `A_TIEMPO` si el evento `WO_DELIVERY_DELIVERED` (o `updated_at` cuando quedó `DELIVERED` sin evento) cayó ≤ `scheduled_date`; `ATRASADA`, `FALLIDA`, `PENDIENTE`. `delivered_pct` y `on_time_pct` con `n`. |
| `installations` | Órdenes con `WO_INSTALLED` en el período (count) y `installation_checks` emitidos en el período (count). |
| `incidents` | `site_incidents` reportadas en el período: por `kind` (DAMAGE/WRONG_MEASURE/MISSING/ADJUSTMENT) y por tipología de la unidad afectada (`orders → payload_json->>'position_id' → project_positions.typology`); abiertas a la fecha. |
| `warranties` | `service_tickets` `kind='WARRANTY'`: abiertas (`OPEN|SCHEDULED|IN_PROGRESS`) a la fecha, creadas en el período, y `warranty_until` vencidas próximas (≤ 60 días) con obra/OT enlazada. |

Función: `private.analytics_field(target_org, desde, hasta)` → `jsonb`.

## 5. Detalle y exportación

`private.analytics_export_rows(target_org, metric, desde, hasta)` devuelve
las filas detrás de una métrica — claves `quotes` (detalle de ventas),
`obras` (margen por obra), `ots` (merma por OT), `steps` (tiempos por
estación), `remakes`, `deliveries`, `incidents`, `warranties`: la firma
F6 — toda cifra se abre hasta las obras, OT y movimientos que la componen —
y la exportación CSV usa exactamente estas filas (decimales canónicos, sin
formato local). Cada sección ya incrusta su propio detalle con el mismo
contenido.

Los textos visibles («¿Cómo se calcula?») los sirve la API desde
`backend/analytics/definitions.py`, espejo literal de este documento: si
una definición cambia, cambian ambos en el mismo commit.
