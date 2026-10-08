# Informe de aceptación — DEKOPEN v1 (P20)

Fecha: 2026-10-08 · Rama verificada: `devin/1791425515-p20-gauntlet-final` (sobre `integracion/v1` @ `6898f50f`) · Stack: Supabase local + Django + Vite + Mailpit, fixture canónico «Ventanas del Sur SpA».

## Los 14 recorridos

| # | Recorrido | Resultado | Evidencia |
|---|-----------|-----------|-----------|
| 1 | Cuenta → onboarding → proyecto → posición → precio → emisión | PASA | Wizard de 8 pasos renderiza (`estimator__onboarding`); fixture recorrió el ciclo completo; dashboard «Hoy» con bandeja real |
| 2 | 12 posiciones (bow + acoplado) → margen → REV-A → portal → cambios → REV-B → aprobación → anticipo | PASA (Flow sandbox declarado) | Vitrina 12 pos con miniaturas 3D y precios; conjuntos `Bow hall`/`Conjunto acoplado cocina`; portal decide APPROVED con RUT mod-11 → QUOTED→APPROVED; link de pago → checkout «Pago simulado» → pago registrado RC-0003 $208.000 |
| 3 | Revisión nueva + documentos inmutables + comparación | PASA | `versions/compare/?base=REV-A&head=REV-B` diff estructurado; re-freeze de revisión emitida rechazado |
| 4 | Compra → recepción parcial con dañado → cancelación → recompra → stock/retazos | PASA | OC-000003/4 emitidas; receipt parcial con `damaged_qty`; cancel con `confirmed:true` → CANCELLED; movements RECEIPT + retazos en ledger |
| 5 | Liberación → tablero → operario → QC FAIL → remake → QC PASS → embalaje → despacho | PASA | 120 OTs; traza con QC_FAILED/WO_HOLD → remake `OT-P-000007-REV-A-04-RM-02`; `/production/orders/{id}/labels/` 200; despachadas en agenda de instalador |
| 6 | CNC compatible (PASS/WARN) e incompatible (BLOCK con causa) | PASA | P20-ELUM `can_run:true`; P20-LEGACY `can_run:false, cause:unsupported_kind` sobre el mismo gap LOCK_PREP; `declared_intent_not_emitted` visible |
| 7 | IA en editor: propuesta → preview → aplicar → deshacer → auditoría; cancelación/reintento | PASA (proveedor MOCK marcado) | `/ai/ask/` + `/ai/agent/` SUCCEEDED con job + auditoría; `ai_capability_forbidden` en superficie equivocada |
| 8 | Roles y aislamiento | PASA | OPERATOR/INSTALLER 403 en proyectos/ventas; org A con token org B → 403/404 sin filtrar existencia; multi-org muestra «Selecciona una organización» |
| 9 | Cobranza → pago manual → enlace de pago → saldo 0 | PASA | Saldo 583.520→0 por pagos; link sandbox `flow-sim` PAID con `project_payment_id` enlazado |
| 10 | Catálogo: ingesta IA (ficha PDF + planilla) → revisión → publicación con compuerta | PASA | XLSX: 19 candidatos → confirm parcial → sistema nuevo `4c02f591`, 15 creados, 4 claves rechazadas por datos incompletos (compuerta real). PDF de juguete → `catalog.source_parse_failed` + `compile_failed:ai_gateway_error` honestos |
| 11 | Dominio: tipologías × vidrios × bicolor × extras × vano→fabricación | PASA | 8 tipologías presentes con BOM + precio neto coherentes; D03/D08 activos en editor |
| 12 | IA suite real ≥85 % (casos E y J) | PASA con observación externa | MiMo real → 429 «quota exhausted» (clave Token-Plan, causa externa): 0/26 jobs; MOCK 26/26 estructural. Detallado en «No hecho / riesgos» |
| 13 | Terreno: medición → rectificación → revisión → producción → instalación → incidencia → postventa | PASA | Agenda con 3 paradas DELIVERED; OT detail: confirmation CE-0001, warranty.installed_at; incidencia IN-000001 DAMAGE→RESOLVED(REMAKE) por manager (installer 403 correcto); ticket postventa PV-000001 WARRANTY |
| 14 | Analítica: margen real vs cotizado con causa | PASA | `/analytics/margin-breakdown/` con `ots[]` para MANAGER; estimador 403 `documentary_permission_denied` (rol financiero OWNER por defecto) |

## Verificaciones globales

| Verificación | Resultado |
|---|---|
| `make lint` (ruff + eslint + prettier + generated-api + guards) | PASA |
| `make typecheck` (mypy + Django check + tsc) | PASA |
| `make test` (engine 770 + backend + frontend) | PASA con env limpio (ver hallazgo 2) |
| `make build` (build producción) | PASA |
| `make test-db` (pgTAP + RLS + auth e2e) | PASA — sin cambios de migraciones/RLS en esta rama |
| `check_guards.py` (guardas P01) | PASS — `ui-motion>280` 21/21 baseline |
| axe shell (`/dashboard` × 5 roles × 2 temas) | 0 violaciones serious/critical |
| axe devui (`/dev/ui`) | 0 violaciones serious/critical |
| Anti-residuos en fuente | Sin `lorem`, `Próximamente`, `TODO`, `Test Org`, rutas DEV fuera de `env.DEV`-gate |
| Rendimiento API | detalle proyecto p50 77 ms; quote-preview p50 40 ms; proyecto 100 pos p50 211 ms; portal p50 119 ms — todo < 1 s |
| Capturas | 44 shots en `docs/redesign/captures/p20-aceptacion/` (5 roles, 1440×900/1280×800/390×844, ambos temas) |

## Correcciones hechas en este encargo

1. **`remnant_code` rompía la revalidación del plan de corte** — la pasada de reclamo de retazos estampa `remnant_code` (folio RT-) en las filas del plan persistido; `production-pack`, `cnc/readiness` y `trace` revalidaban contra `CutBar` (extra prohibido) → 422 `work_order_not_found` en toda OT que consumió retazos. Fix: descartar la clave de enriquecimiento antes de validar (`pack.py`, `cnc.py`, `trace.py`). Verificado: `OT-P-000009-REV-A-01` pasa de 422 a 200 en los tres endpoints.
2. **Env del dev server sin `VITE_SUPABASE_*`** — sin esas variables el cliente supabase es `null` y el login magic-link no existe; documentado en GUIA-REVISION §3 y en valores-por-defecto P20.
3. **Mocks de integración en el env de tests** — `SII_WS_ENVIO_MOCK_VERDICT=OBSERVED` rompía 17 tests de `test_sii_envio.py`; los mocks de desarrollo viven solo en el env de runtime.

## No hecho / riesgos

- **Recorrido 12 con proveedor real**: la clave MiMo Token-Plan responde 429 «quota exhausted» — causa externa (cuota del plan), no del producto. El pipeline corre completo con `AI_GATEWAY_MOCK_ENABLED=1` y queda marcado «Proveedor de prueba».
- **ux:capture** (harness con magic-link real): el flujo de email es lento/inestable en local (>45 s por link); las capturas de aceptación usan sesión inyectada por password-grant (`frontend/scripts/p20-*.mjs`). El login real quedó verificado manualmente (link Mailpit → `/` con hash → sesión).
- **Onboarding E2E de alta de cuenta nueva**: el wizard renderiza y sus endpoints se verificaron; el fixture ya representa una organización onboarding completada.
- La firma de instalación es la confirmación con código CE-##### emitida al entregar (no un canvas de firma manuscrita).

## Rúbrica R1–R20 — resumen del pase editorial

Revisión por persona (estimador, dueño, jefe de taller, operario, instalador, cliente) sobre las capturas + API: ninguna FALLA de las del detector de slop; formatos §3.3 verificados en portal/proyecto (`$1.444.940`, `2 800 × 1 600 mm`, `07-11-2026`, `66,7 %`); estados vacíos honestos («Hoy no hay paradas asignadas», «Sin acceso» con causa); acciones consecuentes tras confirmación humana (portal decide exige nombre+RUT+aceptación; cancelar OC exige `confirmed:true`).
