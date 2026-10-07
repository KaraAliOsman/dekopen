# Capturas — P22 Clientes, empresa y ajustes

Fecha: 2026-10-07 · Rama: `devin/P22-clientes-ajustes` · Fixture `dekopen-demo` (OWNER: `demo-owner@fixture.dekopen.local`, ESTIMATOR: `demo-estimator@fixture.dekopen.local`).

## antes/ (base `26757d40`, ED2 — último merge en `integracion/v1`)

Reutiliza las rutas del conjunto `ed2/antes` que toca este encargo: `settings-general` (la página larga de ajustes antes de la agrupación por dominio), `settings-billing`, `settings-wallet`, `clients-list` (lista de clientes previa a la ficha completa) y `onboarding` (asistente sin el paso de configuración). Las secciones nuevas (Empresa, Usuarios y roles, Comercial, Documentos, Numeración, Producción, Integraciones) no existían como rutas — su contenido vivía dentro de la página única `settings-general`.

## despues/ (rama P22 — 72 capturas, 0 hallazgos)

- `shots/settings-general--*.png` — ajustes con navegación lateral por secciones; General reúne identidad, rotulado y datos fiscales.
- `shots/settings-empresa--*.png` — datos de la empresa (nombre, RUT, giro, dirección, contacto comercial).
- `shots/settings-usuarios--*.png` — miembros, invitaciones pendientes, cambio de rol y desactivación (solo OWNER).
- `shots/settings-comercial--*.png` — moneda, IVA, vigencia, banda de margen y umbral de descuento con aprobación.
- `shots/settings-documentos--*.png` — papel, textos legales, pie white-label y vista previa en vivo del documento (momento de firma §8).
- `shots/settings-numeracion--*.png` — folios por tipo de documento en solo lectura (§10).
- `shots/settings-produccion--*.png` — política de producción (remanentes, rotulado) y centros de trabajo con el tipo traducido.
- `shots/settings-integraciones--*.png` — estado de Flow, SII, correo e IA sin exponer secretos, con pasos de ACTIVACION.
- `shots/settings-billing--*.png` / `shots/settings-wallet--*.png` — rutas preexistentes no regresionadas.
- `shots/clients-list--*.png` — lista con búsqueda por nombre/RUT/correo y filtros, ficha lateral con contactos, obras, proyectos, cotizaciones, pagos, documentos y notas.
- `shots/onboarding--*.png` — asistente con el paso "Ajustes" nuevo (Empresa + Comercial + Documentos con defaults §11 editables).

## Cómo se generaron

`cd frontend && node --experimental-strip-types scripts/ux-capture/index.ts --out docs/redesign/captures/p22-clientes-ajustes/despues --routes "settings-*"` más una pasada por ruta para `clients-list` y `onboarding`, con el stack local completo (Supabase CLI, Django `:8000`, runjobs, Vite `:5173` con `VITE_SUPABASE_*`) y fixture sembrado. Viewports 1440×900, 1280×800, 1024×768 en claro y oscuro.

Hallazgos de la pasada corregidos en la misma rama: enums crudos en las estaciones de Producción (`CUT_SAW` → tipo traducido vía `WorkCenterRequestKindEnum`), `file://` de las fuentes Plex en la vista previa documental (ahora `data:` embebida solo en el HTML de pantalla) y desborde horizontal del asistente por las etiquetas de paso largas (etiquetas cortas + `min-width: 0` acotado a `.onboarding`).
