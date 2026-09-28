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

# Índice de evidencia — fase 01

SHA del paquete: `6c61859` (+ capturas en este commit). Fixtures: `scripts/dev_fixture.py`
(vivienda congelada/REV-A + OT optimizadas, obra grande, incompleta). Cuentas:
`demo-owner` (aal2) y `demo-operator` (magic link).

## Capturas (todas en `docs/redesign/captures/phase01/`)

| Superficie                                                             | Capturas                                                      | Contraste con 00                                                      |
| ---------------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------- |
| Dashboard, Proyectos, Clientes, Compras, Producción, Precios, Catálogo | `*-1440.png`, `*-1280.png`                                    | PageHeader unificado, rail con iconos, tema claro cálido              |
| Proyecto vivienda (congelado)                                          | `project-vivienda-{1440,1280}.png`                            | —                                                                     |
| Studio editable                                                        | `studio-light-{1440,1280}.png`, `studio-dark-{1440,1280}.png` | rail 64px icon-only; materiales físicos idénticos en ambos temas (D7) |
| Móvil                                                                  | `m-dashboard-390.png`, `m-projects-390.png`                   | scrollWidth=390 verificado; rows refluyen                             |
| Roles                                                                  | `operator-denied-catalogs.png`                                | enlace directo OPERATOR → catálogo/precio = "Sin acceso" útil         |
| Extras                                                                 | `settings/jobs/billing/assistant-1440.png`                    | —                                                                     |
| Defecto QA (corregido)                                                 | `defect-stale-error-clients-1440.png`                         | banner de validación persistía tras cancelar — fix `73f5620`          |

## Verificaciones ejecutadas

| Mandato                                              | Método                                       | Resultado                                   |
| ---------------------------------------------------- | -------------------------------------------- | ------------------------------------------- |
| Jerarquía a zoom 100%                                | recorrido visual de las capturas vs baseline | jerarquía legible; sin overflow             |
| Teclado: crear/editar, tab, menú, error, cancelación | QA con teclado real (Tab, ⌘K, flechas, Esc)  | pasa; banner post-cancel corregido          |
| Contraste ambos temas                                | ratios computados WCAG                       | AA superado (≥4.5 texto)                    |
| Roles por enlace directo                             | OPERATOR navega directo a rutas vetadas      | denied-state útil, sin crash                |
| Componentes migrados                                 | `ui/` + migraciones en páginas reales        | ver `decisions.md` D7–D14                   |
| Pruebas de comportamiento                            | vitest                                       | 436/436 + 11 nuevas del kit                 |
| Studio/impresión/bot no subordinados al tema         | `--mat-*` en `:root` sin tematizar           | documentado D7; capturas Studio ambos temas |

## Fase 03 (`docs/redesign/captures/phase03/`, SHA c6a0456)

| Archivo | Qué evidencia |
|---|---|
| `benchmark-page-{pvc,pvcfoil,alu}.png` | página completa del muro por acabado |
| `benchmark-<fixture>-<finish>-3d.png` | 11 fixtures × 3 acabados, 3D activado |
| `hw-lever-tiltturn.png` | palanca batiente — roseta+collar+palanca cónica, metal satinado |
| `hw-hinge-tiltturn.png` | bisagra de galce — barril+aleta con highlight metálico |
| `hw-escutcheon-door-{interior,exterior}.png` | escudo 240mm doble cara + cilindro |
| `hw-pull-sliding-cup.png` / `hw-pull-sliding-tirador.png` | uñero embutido / tirador D superficial |
| `hw-centrelever-awning.png`, `hw-tophinge-awning.png` | manilla central + bisagras testero |
| `theme-{light,dark}-{pvc,alu}.png`, `theme-invariance-*.png` | RGB físico idéntico entre temas |
| `diag-chips-3d.png`, `diag-handle-outofrange-2d.png`, `studio-handle-outofrange.png` | datum fuera de rango + herraje esquemático — sin clamp silencioso |
| `2d-alzado-{tiltturn,door}.png` | mano correcta en 2D (palanca opuesta a bisagras) |
| `before-after-sheet.png` | lámina comparativa fase-00 vs fase-03 |
| `REPORT.md` | manifiesto del set con veredictos |
| video (screencasts) `rec-37b9cdc4-…-edited.mp4` | giro/abatir/corredera/despiece sin acumulación |

## Fase 04 (SHA pendiente de commit)

| Archivo / evidencia | Qué prueba |
|---|---|
| `supabase/migrations/20261227000002_catalog_parameter_evidence.sql` | tabla de evidencia con sellos servidor, CHECKs de unidad/url/pagina/revision, indice dedup, RLS |
| `supabase/tests/database/172_catalog_parameter_evidence.test.sql` | 12 checks: member no inserta/actualiza/borra, org B no lee, sello sin revisor rechazado, url no-http rechazada |
| `supabase/migrations/20261228000001_catalog_table_privilege_hygiene.sql` | REVOKE REFERENCES/TRIGGER/TRUNCATE de `authenticated` en 12 tablas de autoridad |
| `supabase/tests/database/173_catalog_privilege_hygiene.test.sql` | 15 checks: sin TRUNCATE (bypass RLS), sin TRIGGER, sin REFERENCES |
| `backend/tests/test_catalog_evidence.py` | 10 tests: declare/review/stamp_import — org-scoping, actores server-side, idempotencia |
| `backend/tests/test_catalog_ingest.py` (+2) | confirm fija evidencia del parser; sin evidencia no escribe nada |
| `frontend/src/features/canvas/kitCompatibility.ts` + test | ejes del engine replicados; compatible/indecidible/incompatible + `bayEnvelopeMm` |
| `frontend/src/features/catalogs/SystemWorkspace.tsx` — sección Fuentes | evidencia visible por sistema + acciones de revision por rol |
| `docs/redesign/captures/phase04/` | capturas de ambas experiencias (pendiente de la ejecución del agente) |

### phase-04 · reparación de autoridad (design-options)

| Evidencia | Qué prueba | Dónde |
|---|---|---|
| design-options 200 en DEMO_60/ALU_65/GLASS_45 | El bloqueo headline (422) está muerto; kits + handle_policy llegan al editor | verificación HTTP con token ESTIMATOR real sobre :8000 |
| `supabase/tests/database/174_policy_authority_native_numerics.test.sql` | Latest-version authorities sin numéricos string; versión embebida = versión de fila | pgTAP 9/9 verde |
| `engine/tests/test_manufacturing_jsonb_parse.py` | Parsers aceptan nativo + legacy-string, rechazan payload malformado / enum inválido / side TOP | pytest 5/5 |
| `supabase/migrations/20261228000002` | Reparación por nueva versión respetando `immutable_authority` | migración aplicada en reset |
| `docs/redesign/captures/phase04/` | Recorrido catálogo + Fuentes + picker de kits + razones de incompatibilidad | 6 PNG + REPORT.md del agente de testing |

## Fase 07 (commits `20b214b`, `e82e17e` + este commit)

| Archivo / evidencia | Qué prueba |
|---|---|
| `backend/documents/renderers.py` `_doc01` | Política editorial por contenido: `.cover` >8 grupos, `.dochead` resto; `.doc-duo` de cierre incondicional; ficha dibujo+spec con apertura humana y mano desde `parametric_tree`; extras como nota dentro del neto |
| `docs/redesign/captures/phase07/doc01-1pos-v4.pdf` + PNG | 1 posición = 1 página, sin portada vacía ni huérfana |
| `docs/redesign/captures/phase07/doc01-5grp-v3.pdf` + PNGs | 5 grupos = 3 páginas bien continuadas |
| `docs/redesign/captures/phase07/doc01-11grp-v3.pdf` + PNGs | 11 grupos = 6 páginas |
| `docs/redesign/captures/phase07/doc01-100pos.pdf` | 100 posiciones = 31 páginas, banda de cierre integrada |
| `docs/redesign/captures/phase07/doc01-door-extras.pdf` + PNG | Puerta estrecha + extras sellados "dentro del neto" |
| `frontend/src/i18n/es-CL.ts` | Share honesto: abrir canal ≠ enviado; "Enlace copiado al portapapeles" |
| `supabase/migrations/20261228000003_portal_payment_link_read.sql` | SELECT + policy org-scoped para `portal_backend` en `project_payment_links`; `portal_quote` devuelve `payment_url` real (verificado vía servicio) |
| `docs/redesign/captures/phase07/live/` | 17 PNG + REPORT.md + video `rec-86d733b8-…-edited.mp4`: portal desktop/móvil, estados emitida/aprobada/rechazada/vencida/sustituida, aprobación idempotente, enlace antiguo→vigente, paridad UI/PDF/portal en misma revisión |
