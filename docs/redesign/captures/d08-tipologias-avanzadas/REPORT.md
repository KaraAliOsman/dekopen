# Capturas — D08 Tipologías avanzadas (HST, PSK, plegable, pivotante, guillotina, puerta corredera)

Fecha: 2026-10-05 · Rama: `devin/D08-tipologias-avanzadas` · Fixture `dekopen-demo` (ESTIMATOR: `demo-estimator@fixture.dekopen.local`).

## antes/

No se capturó: el cambio es aditivo (el grupo "Avanzadas" no existía en la base, y la serie DEMO_60 nunca lo muestra — la misma ruta `project-position-new` sin grupo ya queda cubierta por `despues/shots/project-position-new--*`).

## despues/ (rama D08)

### shots/ — arnés `npm run ux:capture`

`npm --prefix frontend run ux:capture -- --out docs/redesign/captures/d08-tipologias-avanzadas/despues/shots --routes "project-position-*"` con el stack `make test-db` levantado: 12 capturas (2 rutas × 3 viewports × claro/oscuro), 0 findings del detector.

- `project-position-new--*` — editor de posición nueva: no-regresión de la ruta.
- `project-position-edit--*` — posición sellada del proyecto vitrina: no-regresión.

### manual/ — sesión interactiva

- `biblioteca-bloqueadas-demo60-la-admiten.png` / `biblioteca-bloqueadas-fila-final.png` — DEMO_60 (serie clásica): `<details>` "No disponibles en esta serie (9)" expandido; las 6 tarjetas avanzadas bloqueadas, cada una con causa + "La admiten:" nombrando las series DEMO correctas.
- `biblioteca-bloqueadas-correderas-la-admiten.png` — las 3 correderas clásicas bloqueadas bajo DEMO_60 con sus 4 series admitidas.
- `avanzadas-admitidas-elevacion.png` — DEMO_ELEVACION_90: grupo "Avanzadas" con "Corredera elevable" + "Puerta corredera" clicables.
- `hst-invalido-sliding-layout.png` — **BUG**: la starter HST construye un paño sin `sliding_layout` → motor devuelve `sliding_layout_invalid` ("La distribución corredera del módulo 1 no es fabricable"), Guardar deshabilitado. Mismo defecto para Osciloparalela (PSK) y Puerta corredera (verificado por API).
- `plegable-3mas0-frente-glifos.png` — DEMO_PLEGABLE_70: "Plegable 3+0" construye 3 hojas FOLD con glifo de paquete plegado en la jamba (visible en nivel Comercial y Técnica); evalúa `MANUFACTURING_INCOMPLETE` (solo faltan autoridades de catálogo).
- `avanzadas-admitidas-pivotante.png` — DEMO_PIVOTANTE_120: solo "Puerta pivotante" admitida del grupo.
- `pivotante-lienzo-evaluado.png` — puerta pivotante 1200×2200 construida (unit_kind DOOR + axis_offset_mm); evalúa `MANUFACTURING_INCOMPLETE` (warning `pivot_clearance_mm` de catálogo).
- `biblioteca-bloqueadas-{1440x900,1280x800,1024x768}-{claro,oscuro}.png` — biblioteca con details expandido en los 3 viewports × 2 temas; sin desbordes, "La admiten" legible; a 1024 la shell colapsa el menú a hamburguesa y el inspector a toggle.
- `biblioteca-colapsada-{oscuro,1024-claro}.png` — details cerrado en ambos temas.
- `biblioteca-bloqueadas-avanzadas-1600.png` — fila de tarjetas avanzadas bloqueadas a viewport amplio.

## Verificación funcional (resumen)

- Gating por serie correcto en DEMO_60 / ELEVACION_90 / PLEGABLE_70 / PIVOTANTE_120 (verificado contra `opening_options` reales de la API).
- Backend: `POST /api/v1/engine/calculate` con tipología no declarada → 400 `typology_incompatible` + `compatible_systems` correcto.
- **Defecto**: starters de familia corredera (HST/PSK/puerta corredera) construyen paños sin `sliding_layout` → `sliding_layout_invalid` en el motor; imposible fabricar desde cualquier camino de creación. Pivotante, guillotina y plegable sí evalúan.
- Teclado: `B` abre la biblioteca, Tab alcanza el `<summary>` (13 tabs desde buscador), Enter lo abre/cierra. Esc no cierra el flyout (es panel no modal: deselecciona el lienzo).

## Cómo se generaron

- `despues/shots/`: arnés `ux:capture` (Playwright + storageState del fixture) con stack local levantado.
- `despues/manual/`: sesión interactiva en el navegador de la VM (Chrome, login ESTIMATOR real), viewports fijados con `wmctrl`; tema oscuro vía `localStorage["dekopen.theme"]`.
