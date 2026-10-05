# Capturas — D07 Del vano de obra a la medida de fabricación

Fecha: 2026-10-05 · Rama: `devin/D07-vano-fabricacion` · Fixture `dekopen-demo` (ESTIMATOR: `demo-estimator@fixture.dekopen.local`).

## antes/ (base `db136a72`, ruta `project-position-edit`)

Arnés `npm run ux:capture` sobre la posición V01 del proyecto vitrina: el editor de posición con la posición sellada — aún sin chip de vano ni sección "Vano y montaje". Prueba de no-regresión de la ruta.

## despues/ (rama D07)

- `shots/project-position-edit--*.png` — misma ruta vitrina con la rama D07: la ruta no se rompe (la posición sellada muestra el banner "Revisión cerrada para edición"; la medida queda de solo lectura).
- `shots/project-position-vano--*.png` — posición "Dormitorio principal" del proyecto borrador Casa El Roble: chip "Vano 1620 × 1220 · Fabricación 1600 × 1200 · En vano con holgura perimetral" en la cabecera y cota doble en el lienzo (vano punteado + cotas exteriores + producto con sus cotas interiores).
- `shots/project-position-inspector-vano--*.png` — inspector "Vista general": sección "Vano y montaje" abierta con estado "Confirmada para producción · Confirmada 2026-10-05" y acción "Reabrir medida".
- `shots/project-position-inspector-vano-detalle--*.png` — detalle del desglose: "Derivada del vano", holguras por lado (−10 mm), aviso "Descuadre 80 mm — manda la menor" (se midió ancho en 2 puntos: 1620 y 1700) y "Accesorios de fijación".
- `manual/editor-aviso-incoherencia.png` — aviso al fijar una medida de fabricación incoherente con el vano ("La medida fijada no es coherente…").
- `manual/editor-fijacion-manual-chip.png` — fijación manual aplicada: el chip pasa a "Fijada manual".
- `manual/editor-descuadre-se-usa-la-menor.png` — medida en 2 puntos con "Se usa la menor" resaltado.
- `manual/editor-confirmada-reabrir.png` — estado confirmado con sello de fecha y acción "Reabrir medida".

## Cómo se generaron

- `antes/` y `despues/shots/project-position-edit--*`: `npm --prefix frontend run ux:capture -- --out docs/redesign/captures/d07-vano-fabricacion/{antes,despues}` con stack `make test-db` levantado.
- `despues/shots/project-position-*` restantes: sonda Playwright ad-hoc (eliminada del commit) con `storageState` del login ESTIMATOR, 3 viewports × light/dark sobre la posición del proyecto borrador.
- `manual/*`: capturas de la sesión interactiva en el navegador de la VM durante la verificación manual del flujo completo (medir → descuadre → fijar incoherente → guardar → confirmar → reabrir).
