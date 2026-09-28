# DEKOPEN — mapa funcional de rutas (baseline fase 00)

Base: `devin/1790335313-commercial-workspace` @ `297f121` (post-snapshot `a3785f7` + 31 commits).
Fuente: `frontend/src/App.tsx` (tabla de rutas), páginas en `frontend/src/features/`, APIs en `backend/*/urls.py` bajo `/api/v1/`.

Roles: `OWNER`, `ESTIMATOR`, `WORKSHOP_MANAGER` (WM), `OPERATOR`, `INSTALLER`, `CUSTOMER` (portal público). La rail de navegación filtra por rol (`AppShell.navigationAllowed`) y replica los conjuntos del backend — un enlace visible nunca aterriza en 403.

## Acceso

| Ruta                   | Componente               | API                               | Permiso     | Vacío/error                        | Siguiente paso                               |
| ---------------------- | ------------------------ | --------------------------------- | ----------- | ---------------------------------- | -------------------------------------------- |
| `/login`               | `LoginPage`              | Supabase Auth (magic link)        | público     | estado enviado / link expirado     | email → Mailpit `/verify` → `/auth/callback` |
| `/auth/callback`       | `AuthCallbackPage`       | `auth/v1/verify` + `auth/me/`     | público     | token inválido → login             | org única → app; multi-org → select          |
| `/auth/mfa`            | `MfaPage`                | `auth/v1/challenge/verify` (TOTP) | aal1        | factor no inscrito → enroll inline | `aal2` → app                                 |
| `/select-organization` | `SelectOrganizationPage` | `tenancy_organizations` (RLS)     | autenticado | sin membresías → mensaje           | selecciona org → `/`                         |

## Núcleo comercial

| Ruta                                            | Componente                       | API                                                                                   | Permiso                             | Vacío/error                                                                      | Siguiente paso                                                      |
| ----------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `/`                                             | `HomeRedirect`                   | —                                                                                     | cualquier rol                       | —                                                                                | floor roles → `/production`; resto → `/dashboard`                   |
| `/dashboard`                                    | `DashboardPage`                  | `analyticsOperationalSummary`, `projectsList`, `aiJobs*`                              | O/E/WM                              | atención vacía ("sin pendientes"); 409 → "No pudimos cargar la operación de hoy" | cola de atención → deep link por ítem                               |
| `/onboarding`                                   | `OnboardingPage`                 | `catalogSystemList`, `clientsCreate`, `projectsCreate`                                | autenticado                         | wizard por pasos                                                                 | identidad → sistema → demo → cliente → proyecto → vano → cotización |
| `/projects`                                     | `ProjectListPage`                | `projectsList`                                                                        | O/E/WM                              | "No hay proyectos que coincidan." + Crear proyecto                               | proyecto → `/projects/:id`                                          |
| `/projects/:id`                                 | `ProjectWorkspacePage`           | `projectsRetrieve`, `projectsPositions`, artifacts, quote-link, payments, invoices    | O/E/WM (`canWrite`=O/E; envío O/WM) | desk vacío + hint de selección                                                   | posición → editor; cotización → pricing; aprobación → portal        |
| `/projects/:id/positions/new` y `…/:posId/edit` | `ProjectPositionEditor` (Studio) | `assembly/calculate`, `design-options`, `positions` POST/PUT                          | O/E                                 | eval inválida → Guardar deshabilitado + semáforo                                 | guardar → lista; emitir → pricing                                   |
| `/projects/demo/positions/g1/edit`              | `CanvasEditor2DView` (demo)      | engine calc                                                                           | cualquiera                          | —                                                                                | sandbox de diseño                                                   |
| `/projects/:id/pricing`                         | `PricingDecisionsPage`           | `pricingPreview`, `design-batch-preview`, `operations`, `apply`, `withdraw`, `audits` | O/E                                 | sin reglas → 422 `pricing_rules_not_found`                                       | aplicar → emitir revisión                                           |
| `/pricing/commercial`                           | `CommercialPricingPage`          | cost-lists/config/fx admin                                                            | O/E                                 | listas vacías                                                                    | `pricing/cost-lists`                                                |
| `/pricing/cost-lists`                           | `PricingPage`                    | `pricingAdmin*` (cost_lists, items, rules, configs, fx, audits)                       | O/E; sección reglas solo OWNER      | vacíos por recurso                                                               | items → preview                                                     |
| `/clients/:id?`                                 | `ClientsPage`                    | `clients*`                                                                            | O/E/WM (write O/E)                  | lista vacía → crear                                                              | cliente → proyectos                                                 |

## Documentos y portal

| Ruta                 | Componente                  | API                                                                             | Permiso          | Vacío/error                                        | Siguiente paso                 |
| -------------------- | --------------------------- | ------------------------------------------------------------------------------- | ---------------- | -------------------------------------------------- | ------------------------------ |
| (en proyecto)        | `ProjectQuotationPanel`     | `documents/inputs`, `freeze`, `artifacts`, `access`                             | O/E; DOC-03 + WM | inputs sellan al versionar; freeze 422 con códigos | emitir → DOC-01 → link portal  |
| `/cotizacion/:token` | `PortalQuotePage` (público) | `portalQuoteRetrieve`, `portalQuoteDecide`, `positionDesign`, `positionMembers` | token            | expirado/revocado → estado dedicado                | aprobar / pedir cambio / pagar |
| `/pago/retorno`      | retorno Flow                | `flow/confirm`                                                                  | público          | pago fallido → mensaje                             | vuelve al portal               |
| facturas/DTE         | dentro de proyecto          | `invoices`, `dte`, `sii/cafs`, `sii/certificate`, `envios`                      | O                | CAF ausente → `sii_caf_exhausted` (API)            | registrar CAF + cert           |

## Operación

| Ruta                                    | Componente       | API                                                                                                                                                                             | Permiso                                                      | Vacío/error                                                 | Siguiente paso                         |
| --------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------- | -------------------------------------- |
| `/purchasing` (`/inventory` → redirige) | `PurchasingPage` | requirements, orders, `orderRetry`, inventory items/movements/remnants                                                                                                          | O/WM/E                                                       | grupos vacíos por proveedor                                 | borrador OC → recibir → reserva        |
| `/production`                           | `ProductionPage` | `productionPrep`, `versions/:id/release`, `orders`, `optimize`, `cancel`, `materialRecheck`, `stationQueue`, `stepTransition`, `cncExport`, `trace`, DTE-52/dispatch/labels/POD | O/WM/OPERATOR/INSTALLER (lectura), transiciones por estación | cola vacía por estación; `?blocked=1`,`?shortage=1` filtros | soltar OT → estaciones → QC → despacho |
| `/jobs`                                 | `JobsPage`       | `jobsList`, `retry`, `cancel`                                                                                                                                                   | no-INSTALLER                                                 | cola vacía                                                  | reintentar fallidos                    |

## Catálogo

| Ruta                              | Componente            | API                                                                                                               | Permiso                  | Vacío/error                                             | Siguiente paso                 |
| --------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------- | ------------------------------ |
| `/catalogs` → `/catalogs/systems` | `CatalogsSystemsPage` | `catalogSystemList`/`Retrieve`, `workspace`, `process-profiles`, articles/glazing/hardware-kits, `catalogImports` | O/WM (read: autenticado) | sistema sin autoridad → escalera readiness con bloqueos | importar → revisar → readiness |

## IA

| Ruta         | Componente               | API                                                         | Permiso      | Vacío/error            | Siguiente paso                     |
| ------------ | ------------------------ | ----------------------------------------------------------- | ------------ | ---------------------- | ---------------------------------- |
| `/assistant` | `AssistantWorkspacePage` | `aiJob*` (create/list/retrieve/cancel), `aiAgent`, `ai/ask` | no-INSTALLER | sin jobs → sugerencias | trabajo con artifacts/aprobaciones |
| orb/dock     | `OrbDock` + inline       | `ai/ask`, `aiJob*`                                          | no-INSTALLER | —                      | contextual por superficie          |

## Ajustes

| Ruta                | Componente            | API                                                      | Permiso | Vacío/error        | Siguiente paso  |
| ------------------- | --------------------- | -------------------------------------------------------- | ------- | ------------------ | --------------- |
| `/settings/general` | `SettingsPage`        | org, branding (`organization/branding[/logo]`), usuarios | O/WM    | —                  | identidad/brand |
| `/settings/billing` | `SettingsBillingPage` | wallet, subscription, checkout                           | O/WM    | trial sin plan     | checkout        |
| `/settings/wallet`  | `SettingsWalletPage`  | `wallet*` (ledger, topup)                                | O/WM    | saldo/ledger vacío | recargar        |

## Dev

| `/benchmark` | fixtures renderer | engine calc | dev only | — | matriz visual |

## Contratos principales identificados

- **Auth**: magic-link OTP (GoTrue) → JWT; `X-Organization-ID` en cada llamada; `auth/me` resuelve rol; OWNER exige aal2 (TOTP).
- **Engine**: `POST /engine/assembly/calculate` (producto v2) + `POST /engine/inspect` — números solo del engine; hash `calculation_hash` sella BOM.
- **Precios**: preview → operación → apply; `pricing_operations.request->>'currency'` es la autoridad de moneda (no hay `projects.currency`).
- **Documentos**: inputs → freeze (versión inmutable) → artifacts async via `job_runs` → `artifacts/:id/access` signed URL.
- **Producción**: release (versión sellada) → OT con steps por routing template; transiciones consumen material; optimize→plan fingerprint; DOC-02/03/labels POD sellados.
- **Comercial**: quote-link portal → decisión (APPROVED/CHANGES) → pagos `project_payments` (idempotentes, `operation_key`) → DTE-33/61/52 con CAF.
- **Catálogo**: autoridad explícita (provenance, readiness DESIGN/QUOTE/MANUFACTURING/CNC), import → review humana; nada se auto-certifica.
- **IA**: jobs durables con plan/pasos/artifacts/aprobaciones; herramientas canónicas; sin SQL libre.
