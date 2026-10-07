# D08 — Tipologías avanzadas · plan de verificación E2E

Rama `devin/D08-tipologias-avanzadas`. Stack local levantado:
Supabase `:25321` (migraciones + seed.sql aplicados — 6 sistemas DEMO nuevos),
Django `:8000`, Vite `:5173`, Mailpit `:25324`.
Login ESTIMATOR (`demo-estimator@fixture.dekopen.local`) ya hecho en el navegador
real vía magic-link. Org: Ventanas del Sur SpA `548b9ce5-746b-5a4a-9127-733c4dcd0582`.
Proyecto borrador: `383fbda7-e9a8-4843-b2ef-47be74128aba` (Casa El Roble).

## Valores esperados (verificados contra la API real)

`opening_options` emitidas por sistema (POST /api/v1/projects/design-options/<id>):

| Serie (id) | Claves relevantes | Starters admitidas |
|---|---|---|
| DEMO_60 `3067da09` | 28, ninguna avanzada | ninguna de las 6 |
| DEMO_70 `462fbff1`, ALU_65 `d551e7cc`, GLASS_45 `300d16e1` | sin claves avanzadas | ninguna |
| DEMO_CORREDERA_60 `f9398347`, ALU_CORREDERA_70 `0ddb3e56` | `PRIMARY:SLIDE` | ninguna (slidingDoor exige `DOOR:PRIMARY:SLIDE`) |
| DEMO_ELEVACION_90 `b9bf39be` | `PRIMARY:LIFT_SLIDE`, `DOOR:PRIMARY:LIFT_SLIDE`, `PRIMARY:SLIDE`, `DOOR:PRIMARY:SLIDE` | hst + slidingDoor |
| DEMO_PSK_90 `35d0cdfa` | `PRIMARY:PARALLEL_SLIDE` (+DOOR) | psk |
| DEMO_PLEGABLE_70 `82e89f05` | 124, incl. `L1:FOLD:LEFT:INWARD:ACTIVE|L2:FOLD:LEFT:INWARD:PASSIVE|L3:FOLD:LEFT:INWARD:PASSIVE` | foldable |
| DEMO_PIVOTANTE_120 `c34d77a9` | `PRIMARY:PIVOT_H`, `DOOR:PRIMARY:PIVOT_H`, `DOOR:PRIMARY:PIVOT_V` | pivot |
| DEMO_GUILLOTINA_60 `f29dd018` | `PRIMARY:VERTICAL_SLIDE`, `TOP:VERTICAL_SLIDE|BOTTOM:VERTICAL_SLIDE`, `TOP:FIXED|BOTTOM:VERTICAL_SLIDE` | guillotina |
| DEMO_PUERTA_CORREDERA_70 `829d9f05` | `PRIMARY:SLIDE`, `DOOR:PRIMARY:SLIDE` | slidingDoor |

"La admiten:" usa `system.name` (no code): "Sistema Demo Elevable HST 90mm PVC — referencia sintética", etc.

Rutas UI: `/projects/<id>/positions/new` → chip "Serie de perfiles" (popover `<select>`)
→ rail "Biblioteca de tipologías" (icono árbol) → `TypologyFlyout`.
Grupo "Avanzadas" solo renderiza si alguna avanzada está admitida; bloqueadas van al
`<details>` "No disponibles en esta serie (N)" con causa por tarjeta + consulta perezosa
(`engineSystems` + `projectDesignOptions` por serie) que solo dispara al abrir el details.
Tema: botón "Cambiar tema" en la barra lateral del shell.

## Tests

### T1 — Biblioteca bajo serie clásica DEMO_60 (flujo 1)
1. Ir a `/projects/383fbda7-e9a8-4843-b2ef-47be74128aba/positions/new`.
2. Chip de serie → elegir "Sistema Demo 60mm PVC — referencia sintética".
3. Abrir "Biblioteca de tipologías".
   - PASS: NO hay sección "Avanzadas" entre los grupos admitidos (todas bloqueadas);
     existe `<details>` "No disponibles en esta serie (N)" (N ≥ 6 — probablemente 9
     con sliding2/sliding3/slidingFixed, que tampoco admite DEMO_60).
   - FAIL si: el grupo "Avanzadas" aparece con tarjetas clicables, o no hay details.
4. Expandir el details (click o Enter sobre el summary).
   - PASS: las 6 tarjetas avanzadas presentes (Corredera elevable, Osciloparalela,
     Plegable 3+0, Puerta pivotante, Guillotina, Puerta corredera), cada una con
     "La serie activa no declara esta tipología en su catálogo." y, tras la carga
     perezosa, "La admiten: <nombres>" con EXACTAMENTE los sistemas de la tabla
     (slidingDoor nombra 2: Elevación HST 90 + Puerta Corredera 70).
   - Las tarjetas bloqueadas NO son botones (div `starter-card--blocked`,
     aria-disabled) — click no construye nada.
   - FAIL si: "La admiten" nombra una serie incorrecta/ausente, o dice "Ninguna
     serie…" pese a existir filas capability.
5. Consola sin errores (browser_console).

### T2 — Cambio de serie desbloquea y construye HST (flujo 2)
1. Chip de serie → "Sistema Demo Elevable HST 90mm PVC — referencia sintética".
2. Reabrir biblioteca.
   - PASS: grupo "Avanzadas" visible con exactamente "Corredera elevable" y
     "Puerta corredera" clicables; details muestra las otras 4 bloqueadas.
3. Click "Corredera elevable".
   - PASS: flyout se cierra, el lienzo dibuja un módulo con hoja LIFT_SLIDE
     (riel + glifo de elevación, simbología de corredera), la evaluación corre
     (POST /engine/assembly/calculate → estado distinto de "idle"), sin errores
     de consola. El árbol de objetos muestra la hoja corredera elevable.
   - FAIL si: la tarjeta no construye, el lienzo queda vacío, o la hoja dibuja
     simbología de apertura incorrecta (abatibles).

### T3 — Plegable 3+0 bajo DEMO_PLEGABLE_70 (flujo 3)
1. Chip de serie → "Sistema Demo Plegable 70mm PVC — referencia sintética".
2. Biblioteca → "Plegable 3+0" admitida en "Avanzadas" (hst/slidingDoor ahora
   bloqueadas: PLEGABLE no declara SLIDE/LIFT).
   - PASS: exactamente foldable admitida del grupo avanzado.
3. Click "Plegable 3+0".
   - PASS: lienzo dibuja 3 hojas FOLD con paquete plegado (glyph cluster en la
     jamba), evaluación corre, consola limpia.
   - Nota: la franja de planta del editor solo existe para productos acoplados
     (couplings>0); en módulo único no aparece — se documenta honestamente.
     Se prueba el toggle "Técnico" si aporta recorridos.

### T4 — Contrato backend: tipología no declarada → 400 (API)
1. POST `/api/v1/projects/383fbda7.../positions/` con diseño LIFT_SLIDE bajo
   DEMO_60 (o POST `/api/v1/engine/assembly/calculate/` si el primero exige más
   campos) con token ESTIMATOR.
   - PASS: HTTP 400, `code: typology_incompatible`, `compatible_systems`
     contiene `DEMO_ELEVACION_90`.
   - FAIL si: 200/201, 409 genérico, o compatible_systems vacío.

### T5 — Responsivo + tema + teclado (flujo 4)
1. Biblioteca abierta bajo DEMO_60 con details expandido en viewports
   1440×900, 1280×800, 1024×768 (ventana redimensionada por wmctrl en la sesión
   real + sonda Playwright con storageState para pixel-exacto si hace falta),
   en claro y oscuro.
   - PASS: modal sin desbordes, textos legibles, tarjetas completas; navegación
     por teclado: Tab alcanza el summary, Enter/Space abre/cierra el details,
     Esc/click fuera cierra el flyout.
2. Capturas al directorio `despues/manual/` + `despues/shots/` vía
   `npm run ux:capture -- --routes "project-position-*"`.

## Capturas (convención del repo)
- `docs/redesign/captures/d08-tipologias-avanzadas/despues/shots/` — ux:capture
  sobre rutas project-position-new / project-position-edit.
- `despues/manual/` — capturas del flujo en el navegador real + sonda Playwright
  para los 3 viewports × claro/oscuro de la biblioteca.
- `antes/` — intentar worktree del commit base (`git worktree` + node_modules
  enlazado + Vite :5174) capturando la misma ruta; si no es viable se omite con
  nota honesta en REPORT.md.
- `REPORT.md` describiendo cada captura, siguiendo el formato de d07.
