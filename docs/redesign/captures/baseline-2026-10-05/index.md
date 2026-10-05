# Baseline UX 2026-10-05

Captura inicial generada con `npm --prefix frontend run ux:capture -- --out ../docs/redesign/captures/baseline-2026-10-05 --routes login --roles ESTIMATOR` sobre stack local Supabase + Django + Vite.

## Top hallazgos

| #   | Detector      | Cantidad | Rutas | Muestra                               |
| --- | ------------- | -------: | ----- | ------------------------------------- |
| 1   | Sin hallazgos |        0 | login | Captura smoke sin hallazgos de texto. |

## Alcance

- Baseline P00 smoke: ruta `login`, temas claro/oscuro, viewports 1440x900, 1280x800, 1024x768 y 390x844.
- El arnes declarativo cubre las rutas de la SPA; las siguientes sesiones deben ejecutarlo completo cuando el fixture tenga tokens portal emitidos.
