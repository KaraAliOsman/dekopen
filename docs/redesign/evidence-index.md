# Índice de evidencia — fase 00

Conecta cada entregable con la tarea del mandato, la ruta/superficie, el fixture
usado y el SHA. Todo lo marcado `probado` fue ejecutado en esta sesión; ningún
resultado es por inferencia.

## Estado base

| Dato                 | Valor                                                                            |
| -------------------- | -------------------------------------------------------------------------------- |
| Rama                 | `devin/1790335313-commercial-workspace`                                          |
| SHA evaluado         | `297f121` (+ este commit de fase-00)                                             |
| Snapshot diagnóstico | `a3785f7` (ancestro del HEAD; no se retrocedió)                                  |
| `origin/main`        | `5fa9936` — contenido íntegramente; 4 commits exclusivos ya incorporados         |
| PR de visibilidad    | [#107](https://github.com/KaraAliOsman/framedex/pull/107) — abierto, sin mergear |

## Fallos del mandato → evidencia

| Fallo                                   | Verificación                                    | Archivo / ruta                                                                                       | Resultado                                                                     |
| --------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| F1 `purchase_retry` `cancelled_at`      | `supabase db reset` limpio + `supabase test db` | `supabase/migrations/20261219135000_purchase_retry.sql`, `170_purchase_retry.test.sql`               | 15 aserciones pgTAP verdes (claim único, liberación, retry, sin doble compra) |
| F2 emisión service_role devuelve `None` | `pytest backend/tests/` filtrado                | `test_emit_enqueues_under_service_role_with_idempotency` (parche `transaction.atomic` post-snapshot) | verde                                                                         |
| F3 guía sin `delivery_address`          | `pytest` filtrado                               | `test_issue_dispatch_note_payload_seals_manifest_and_destination`                                    | verde (sello de `delivery.address`)                                           |
| F4 24 hex fuera de tokens               | `python scripts/check_guards.py`                | `frontend/src/features/portal/portal.css`, `production.css`, `assistant.css`, `tokens.css`           | guard PASS                                                                    |

## Defectos encontrados por el gate en esta cola → evidencia

| Defecto                                                         | Fix                                                                                                                                        | Verificación                                                                                         |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `GET /analytics/summary` 409 `column p.currency does not exist` | `backend/analytics/service.py` — moneda desde `pricing_operations.request->>'currency'` (op APPLIED vigente) vía `JOIN LATERAL`            | e2e `GET /api/v1/analytics/summary/ → 200`; test nuevo `test_analytics_schema.py` sobre esquema real |
| SKUs e2e obsoletos tras relabeling                              | `auth.spec.ts`, `canvas.spec.ts` → `COMPRA-*`/`VIDRIO-*`/`ACERO-*`                                                                         | e2e 9/9 afectados + suite completa                                                                   |
| Nav ESTIMATOR afirmaba enlace inexistente                       | spec ahora afirma ausencia de `Catálogo`/`Administración`                                                                                  | `auth.spec.ts` verde                                                                                 |
| Cache React Query servía proyecto pre-save                      | `page.reload()` antes de afirmar lecturas de backend                                                                                       | `projects.spec.ts`, `auth.spec.ts` verdes                                                            |
| Drill pg16: `seed.sql` actual sobre esquema SHOT-08             | `scripts/check_pricing_upgrade.py` — sin replay de seed (el catálogo demo llega por sus migraciones; el drill inserta su propio histórico) | `verify_postgres16` PASS completo                                                                    |

## Gates — resultado exacto

| Comando                                | Resultado                                                                                                                                                                                            |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make lint`                            | PASS (ruff, eslint, prettier, api-generado byte-idéntico, guards)                                                                                                                                    |
| `make typecheck`                       | PASS (mypy 60 archivos, django check, tsc)                                                                                                                                                           |
| `make test`                            | 462 engine + goldens byte-check + 1024 backend + 436 frontend — todo verde                                                                                                                           |
| `make test-db`                         | reset limpio 129 migraciones + seed → `db lint` sin warnings → pgTAP completo → 266 tests integración/RLS → 11 e2e Playwright → `verify_postgres16` (upgrade drills + bootstrap + verify.sql) — PASS |
| Últimas 3 fallas ambientales conocidas | 3 tests de engine preexistentes (entorno), sin cambios — mismo estado que HEAD anterior                                                                                                              |

## Rutas (mapa: `route-map.md`)

| Área      | Ruta                                                                  | Fixture                                                                      |
| --------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Acceso    | `/login`, `/auth/callback`, `/auth/mfa`, `/select-organization`       | cuentas `demo-*@fixture.dekopen.local`                                       |
| Dashboard | `/` → `/dashboard`                                                    | org fixture                                                                  |
| Proyectos | `/projects`, `/projects/:id`                                          | `Vivienda demo — casa`, `Obra grande demo — edificio`, `Proyecto incompleto` |
| Studio    | `/projects/:id/positions/new`, `…/edit`                               | posiciones del fixture (fijo, oscilobatiente 2 hojas)                        |
| Precios   | `/projects/:id/pricing`, `/pricing/commercial`, `/pricing/cost-lists` | reglas + cost-list del fixture (todos los SKUs)                              |
| Portal    | `/cotizacion/:token`, `/pago/retorno`                                 | link de cotización emitido                                                   |
| Operación | `/purchasing`, `/production`, `/jobs`                                 | —                                                                            |
| Catálogo  | `/catalogs/systems`                                                   | `DEMO_60` (autoridad de cotización; sin fabricación)                         |
| IA        | `/assistant`, orb/dock                                                | —                                                                            |
| Ajustes   | `/settings/{general,billing,wallet}`                                  | —                                                                            |

## Capturas base y exportaciones

Todas capturadas en vivo sobre `297f121` como `demo-owner` (OWNER), Chrome con
viewport exacto vía CDP (`Emulation.setDeviceMetricsOverride`).

### Escritorio — 1440×900 y 1280×800 (mismo contenido en ambos)

| Archivo                                               | Superficie                                                                                                                     |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `captures/login-{1440,1280}.png`                      | acceso (magic link)                                                                                                            |
| `captures/dashboard-{1440,1280}.png`                  | panel OWNER completo                                                                                                           |
| `captures/projects-{1440,1280}.png`                   | lista de proyectos (3 fixtures)                                                                                                |
| `captures/project-vivienda-{1440,1280}.png`           | workspace del proyecto vivienda                                                                                                |
| `captures/studio-{light,dark}-{1440,1280}.png`        | Studio editable (posición draft del proyecto incompleto) — tema claro/oscuro vía ☾/☀ del rail (`data-theme` + `dekopen.theme`) |
| `captures/studio-locked-{light,dark}-{1440,1280}.png` | Studio en revisión congelada (vivienda REV-A) — estado read-only real                                                          |
| `captures/pricing-{1440,1280}.png`                    | pricing del proyecto vivienda                                                                                                  |
| `captures/quotation-{1440,1280}.png`                  | cotización REV-A + PDF emitido                                                                                                 |
| `captures/production-{1440,1280}.png`                 | producción (4 OT de vivienda optimizadas)                                                                                      |
| `captures/purchasing-{1440,1280}.png`                 | compras                                                                                                                        |
| `captures/catalogs-systems-{1440,1280}.png`           | workspace de sistemas de catálogo                                                                                              |
| `captures/assistant-{1440,1280}.png`                  | AI workspace (bot)                                                                                                             |
| `captures/settings-{1440,1280}.png`                   | ajustes general                                                                                                                |

### Móvil — 390×844

`captures/m-{dashboard,projects,project,production}-390.png`

### Exportaciones (`captures/exports/`)

| Archivo                                      | Qué muestra                                    | Origen                                                                 |
| -------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------- |
| `doc01-quotation-P-000001-REV-A.pdf` (33 KB) | Cotización DOC-01 de la revisión sellada REV-A | `artifacts/{id}/access` → URL firmada, proyecto `Vivienda demo — casa` |
| `cutpack-OT-P-000001-REV-A-01.pdf` (123 KB)  | Pack de cortes (barras/piezas/retazos)         | `GET /production/orders/{id}/cut-pack/` de OT-01 de vivienda           |

### Notas de captura

- Sin rutas en error o blanco: las 12 superficies renderizan contenido real.
- `studio-*` usa la posición editable del proyecto incompleto (la de vivienda
  está congelada — `studio-locked-*` documenta ese estado).
- `/inventory` no existe como ruta propia: redirige a `/purchasing`.
- Login OWNER exige aal2/TOTP (pyotp canónico); capturas hechas con sesión aal2.

## Comandos de entorno

```bash
# stack completo
cd /home/ubuntu/wt-commercial && supabase start
python backend/manage.py runserver 127.0.0.1:8000 \
  # con DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:25322/postgres \
  #     SUPABASE_URL=http://127.0.0.1:25321 SUPABASE_ANON_KEY/SERVICE_ROLE_KEY=... \
  #     SUPABASE_JWT_VERIFY_MODE=auth_server
npm --prefix frontend run dev   # :5173 (VITE_SUPABASE_* del stack)
python backend/manage.py runjobs --poll 0.5   # worker de artifacts

# fixture sintético
SUPABASE_SERVICE_ROLE_KEY=<status -o env> python scripts/dev_fixture.py
```
