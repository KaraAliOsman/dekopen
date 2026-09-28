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
