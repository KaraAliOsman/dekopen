## Resumen

P24 — Analítica que sirve para decidir: página `/analitica` con conversión comercial, margen real vs. cotizado por obra (con desglose de causas §8), merma y tiempos de producción, e instalación/postventa, todo leído de datos reales vía SQL en Supabase con RLS por organización. Lo desconocido se declara «Sin dato» con su causa, nunca 0. Cada cifra lleva «¿Cómo se calcula?» a su definición versionada en `docs/analytics/metricas.md`, y el detalle de cada fuente es exportable a CSV.

## Flujos probados

| Flujo | Resultado |
|---|---|
| Jefe de taller entra a Analítica → ve las 4 secciones con datos del fixture (3 emitidas, conversión 50,0 %, pipeline $777.000, margen cotizado 40,0 % vs real 83,3 %, merma real 5.500 mm vs plan 2.500 mm, entregas 50,0 % a tiempo) | OK — capturas |
| «¿Cómo se calcula?» en Tasa de conversión → diálogo con fórmula, fuente (`project_versions.emitted_at × customer_approvals.status`) y período | OK — captura `como-se-calcula-1440-light.png` |
| «Desglose» en obra PA-101 → cotizado 40,0 %, real 83,3 %, costo real $16.700, causas (material −$28.840, horas −$10.000, descuento $10.000, descarte $40, remakes $5.500), «costo de instalación no medido», OTs enlazadas | OK — captura `desglose-margen-1440-light.png` |
| Selector de período 7d/30d/90d/12m/a medida → recarga con `?period/desde/hasta` en la URL | OK — captura `analitica-1440x900-light-7d.png` |
| Exportar CSV (Cotizaciones) → `dekopen-analitica-quotes-2026-09-07-a-2026-10-07.csv` con las mismas filas de la tabla + ids técnicos | OK — verificado 200 + `Content-Disposition` vía navegador |
| Detalle con pestañas (Cotizaciones/Obras/Órdenes/Estaciones/Remakes/Entregas/Incidencias/Garantías) → columnas con etiqueta chilena, dinero/fechas formateados, nulos como «Sin dato» | OK — captura `analitica-1440x900-light-detalle.png` |
| Rol sin permiso (ESTIMATOR/INSTALLER/OPERATOR) → estado denegado con texto; rol sin permiso financiero → opera sin montos con aviso | OK — cubierto por tests unitarios + guardia SQL `42501` en pgTAP |
| pgTAP `187_p24_analitica.test.sql` — 49 tests: valor por métrica calculado a mano sobre fixture, RLS (org B no ve A), «sin datos suficientes», permisos financieros | OK — 49/49 en `make test-db` |
| Puertas completas | `make lint` ✓, `make typecheck` ✓, `make test` (engine 770 + backend 1350 + vitest 736) ✓, `make build` ✓, `make test-db` ✓ (pgTAP 1288, integración 290, e2e 37) |

## Capturas

`docs/redesign/captures/p24-analitica/`

- Antes: `antes-inicio-1440-light.png` (Inicio era la única vista operativa)
- Después: `analitica-1440x900-light.png`, `analitica-1440x900-dark.png`, `analitica-1280x800-light.png`, `analitica-1280x800-dark.png`, `analitica-1024x768-light.png`, `analitica-1024x768-dark.png`, `analitica-390x844-light.png`, `analitica-390x844-dark.png`, `analitica-1440x900-light-7d.png`, `analitica-1440x900-light-mid.png`, `analitica-1440x900-light-detalle.png`, `como-se-calcula-1440-light.png`, `desglose-margen-1440-light.png`

## Rúbrica editorial §9.3 — un FALLA bloquea el merge

| Ítem | Estado | Nota |
|---|---|---|
| R1 Números Mono tabular con unidad §3.3 | PASA | `Money`, `Percent`, `UnknownValue`, `formatQty` con unidad (mm, mm², h, d) |
| R2 Radios ≤ 4 px; inglete solo en hojas | PASA | `--theme-radius`/`--theme-radius-sm`; sin ingletes |
| R3 Jerarquía por borde/peso/espacio; ≤ 1 flotante | PASA | Secciones como paneles con borde sutil; un solo diálogo a la vez |
| R4 Naranja solo como marca o «requiere persona» ≤ 3 % | PASA | Sin naranja en métricas; barras teal |
| R5 Teal como único croma del cromo | PASA | Barras `--theme-accent`; gráficos sobrios monocromo |
| R6 Vocabulario del taller y voz §4 | PASA | «Obra», «OT», «retazo», «merma», «a tiempo»; causas en castellano |
| R7 Densidad correcta a 768 px | PASA | Verificado 1024×768 y 390×844: tarjetas apilan, nada corta |
| R8 Los 5 estados explícitos con texto y causa | PASA | Cargando, vacío («Sin filas en el período»), error, denegado, sin dato con causa |
| R9 Lienzo/documento es papel sobre mesa | PASA | Panel estándar `--theme-surface-panel` |
| R10 Selección = contorno + tinte + manijas | PASA | Sin superficie de selección; tablas de solo lectura |
| R11 Íconos monolínea 1,5 px; simbología de apertura | PASA | Sin íconos nuevos; tipografía y barras |
| R12 Foco visible y operable por teclado | PASA | Botones/diálogo nativos; Escape cierra; SegmentedControl accesible |
| R13 Movimiento ≤ 280 ms en un eje; reduce-motion | PASA | Sin animaciones nuevas (transición de diálogo heredada) |
| R14 Una acción principal por región | PASA | Una acción por tarjeta («¿Cómo se calcula?»), una por sección detalle («Exportar CSV») |
| R15 Números con fuente; lo desconocido «Sin dato» | PASA | `{value, n, cause}` por métrica; `n` visible («sobre 2»); «¿Cómo se calcula?» con fórmula/fuente/período |
| R16 Cero degradados, blur, brillo, morado IA | PASA | Solo tokens planos |
| R17 Sin scroll horizontal ni cortes en los anchos | PASA | Verificado 1440/1280/1024/390 |
| R18 Nada muerto ni código paralelo | PASA | Todo el SQL/UI está cableado; sin TODOs |
| R19 Conserva o implementa su momento de firma §7 | PASA | La «cifra que se explica sola»: cada número lleva su fórmula versionada a un clic |
| R20 La idea §8 funciona de verdad, con el motor | PASA | Desglose de margen obra a obra con causas y OT de origen — decisión accionable, no decoración |

## Momento de firma e idea del §8

Cada cifra de la página se explica a sí misma: «¿Cómo se calcula?» abre la fórmula, la tabla y columna fuente y el período que usa — la misma definición que `docs/analytics/metricas.md` versiona. La idea del §8 es el desglose de margen real vs. cotizado por obra: cotizado sellado en `snapshot_json` vs. costo real valorizado (consumo OC/lista + retazos + horas × tarifa + remakes), descompuesto en causas (material, horas, descuento, descarte, remakes) con la OT de origen enlazada.

## Lo que se quitó

- Columnas `*_id`/uuid del detalle en pantalla: quedan en el CSV (artefacto de máquina); la tabla humana usa códigos y nombres.
- Tarjetas de métricas sin `n` en el período: solo se muestran métricas con datos, como pide el contrato.

## Decisiones registradas

En `docs/decisions/valores-por-defecto.md` → «Decisiones de implementación — P24» (ventana 30 días America/Santiago, cohorte por emisión, roles lectura OWNER+WORKSHOP_MANAGER, roles financieros configurables en Ajustes → Analítica, tarifa horaria de la org para valorizar horas, descuento pactado como causa separada, puntualidad por `scheduled_date`, garantías por vencer en 60 días, «sin dato» con causa, export CSV con llaves de fila, permiso financiero solo OWNER por defecto).

## Integraciones en sandbox

Ninguna — la analítica lee exclusivamente de Postgres local (funciones `private.analytics_*` SECURITY DEFINER con guardia de membresía + rol financiero por `tenancy_organizations.analytics_financial_roles`).

## No hecho / riesgos

- El costo real de instalación no se mide (no hay fuente de horas de terreno en P23) — se declara como causa «costo de instalación no medido» en el desglose.
- La merma de placas depende de consumo registrado por placa; sin datos muestra «Sin dato» con causa (verificado en fixture).
- `analytics_hourly_rate_clp` vacía → horas sin valorizar + causa «tarifa horaria no configurada»; se configura en Ajustes → Analítica.
- Hallazgo en verificación E2E real: psycopg entrega el `jsonb` como `str`, así que `decision.py` ahora decodifica con `_jsonb()` — sin esto el overview llegaba doble-serializado y la página quedaba vacía.
