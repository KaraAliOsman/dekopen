# P00 — Fundación del programa: rama de integración, constitución en el repo, arnés de evidencia visual, datos demo realistas e higiene de rutas

**Depende de:** nada. Es el primero. Adjunta: `CONSTITUCION-DISENO.md`, `auditoria-hojas/*` (opcional).

## Objetivo
Dejar listo el terreno para los ~40 encargos que siguen: la rama donde se integran, la constitución de diseño como fuente de verdad dentro del repo, los registros de decisiones y de activación, y una herramienta reproducible que, con un solo comando, capture **todas** las pantallas de DEKOPEN con datos que parezcan de una fábrica real y detecte automáticamente los defectos de presentación más frecuentes. Todos los PR siguientes se evalúan con esta herramienta. **Este PR no rediseña ninguna pantalla.**

## 0. Fundación (haz esto primero)
1. **Rama `integracion/v1`** desde el `origin/main` más reciente; push. Este PR y todos los siguientes van hacia ella (el contrato lo explica). Verifica que el CI corre en PRs hacia esa rama (`.github/workflows/ci.yml` dispara en todo `pull_request`; confírmalo con este mismo PR).
2. **Constitución en el repo:** copia `docs/cola/CONSTITUCION-DISENO.md` tal cual a `docs/design/CONSTITUCION.md`. Enlázala desde `AGENTS.md` (sección “Hard invariants” → agrega “UI: `docs/design/CONSTITUCION.md` es obligatoria”) y desde `docs/wiki/index.md`. No la edites en este PR más allá de corregir rutas.
3. **`docs/decisions/valores-por-defecto.md`:** la tabla del §11 de la constitución, con una columna “Estado” (`por defecto` / `confirmado por el dueño`) y otra “Encargo que la implementa”. Los encargos siguientes agregan filas.
4. **`docs/operations/ACTIVACION.md`:** índice de integraciones externas diferidas (Railway/hosting, Flow, SII/DTE, correo con dominio, webhooks, proveedor de IA), cada una con: estado, adaptador, variables de entorno por **nombre** (nunca valores), pasos de activación y cómo verificarla. Los encargos siguientes completan cada sección.

## Por qué
Las auditorías anteriores se hicieron con capturas ad-hoc y datos como “Taller Devin”, “Bow Test Org” o “DEMO_60 SYNTHETIC FIXTURE”. Con eso todo parece un prototipo y no se puede comparar un antes con un después. Además, en esas capturas se repetían siempre los mismos defectos: UUID y hashes visibles, `[object Object]`, enums en MAYÚSCULAS, mensajes del navegador en inglés (“Please match the requested format.”), scroll horizontal, letra de menos de 11 px y textos “MOCK”.

## Alcance
1. **Script de capturas** `frontend/scripts/ux-capture/` (TypeScript + `@playwright/test` 1.62.1, que ya es devDependency) y el comando `npm --prefix frontend run ux:capture -- --out <dir> [--routes <glob>] [--roles <lista>]`.
   - Inicia sesión con los usuarios del fixture, por rol (OWNER, ESTIMATOR, WORKSHOP_MANAGER, OPERATOR, INSTALLER), y sigue el mecanismo de la skill testing-framedex (magic link por Mailpit + TOTP).
   - Recorre una **lista declarativa** de rutas (`routes.ts`) que cubra todas las rutas de `frontend/src/App.tsx` con IDs reales del fixture: proyecto, posición en edición, precios del proyecto, OT, pedido, cliente, catálogo, asistente, trabajos, ajustes, portal `/cotizacion/:token` en sus estados (vigente, aprobada, revocada, expirada, reemplazada) y `/pago/retorno`.
   - Captura cada ruta en 1440×900, 1280×800, 1024×768 y 390×844, en tema claro y oscuro.
   - Por cada captura escribe en `report.json`: overflow horizontal (`scrollWidth > innerWidth`), errores de consola, respuestas HTTP ≥ 400, y textos visibles que coincidan con los detectores: UUID, hex de 10 o más caracteres, `[object Object]`, `undefined`, `NaN`, `null`, enums `[A-Z]+(_[A-Z]+)+`, palabras en inglés de validación nativa (“Please”, “Fill out”), “MOCK”, números con 4 o más decimales y porcentajes con más de 2 decimales. También mide el tamaño de fuente computado bajo 11 px en texto visible y los objetivos táctiles bajo 44 px en las rutas de operario e instalador.
   - Genera un `index.html` liviano con miniaturas y los hallazgos de cada ruta.
2. **Fixture realista**: extiende `scripts/dev_fixture.py`, que ya existe. Debe ser idempotente (correrlo dos veces no duplica datos).
   - Organización A: “Ventanas del Sur SpA”, con RUT ficticio válido según módulo 11, giro, dirección en Concepción, teléfono, correo y un logo SVG simple. Organización B: otra empresa ficticia, para las pruebas de aislamiento.
   - 6 clientes (personas naturales y empresas, con RUT válidos) y 8 proyectos repartidos en fases: borrador, cotizado, enviado, aprobado con anticipo, en producción, despachado, instalado y rechazado.
   - Un proyecto de **12 posiciones** con una mezcla real (fijo, abatible, oscilobatiente, corredera de 2 hojas, corredera O/X/X/O, proyectante, puerta, bow de 3 módulos y conjunto acoplado), con extras y una posición alternativa. Otro proyecto de **100 posiciones** para pruebas de escala.
   - OTs en varios estados (liberada, en producción, bloqueada por faltante, QC fallido, remake, embalada, despachada), órdenes de compra, una recepción parcial y retazos.
   - Catálogo: usa `DEMO_60` tal cual. **No inventes valores técnicos nuevos.** Todo lo demo debe seguir marcado como DEMO en su procedencia. Usa nombres de personas y obras realistas en español de Chile.
3. **Higiene de rutas**: la ruta `/projects/demo/positions/g1/edit` (`frontend/src/App.tsx`, alrededor de la línea 177, prop `demoRoute`) está registrada también en producción. Muévela detrás de `import.meta.env.DEV`, como ya está `/benchmark`, o elimínala si nada la usa (revisa referencias y tests). Agrega un test que falle si una ruta dev-only queda disponible en el build de producción.
4. **Línea base**: corre el arnés sobre main y commitea en `docs/redesign/captures/baseline-<aaaa-mm-dd>/` solo `report.json`, `index.md` (los 30 hallazgos más frecuentes, ordenados por cantidad y con la ruta) y las PNG de 1440 en tema claro, comprimidas, con un total menor a 15 MB. El resto de las capturas no va al repo.

## Fuera de alcance
No cambies estilos, componentes ni textos de producto, salvo la ruta demo.

## Criterios de aceptación
- Desde un stack limpio, `make`/skill + `npm --prefix frontend run ux:capture` produce el set completo sin intervención manual.
- Los detectores tienen tests unitarios: cada regex con casos positivos y negativos, incluidos falsos positivos típicos como códigos legítimos `COT-P-000001-REV-A` o `OT-P-000005-REV-A-03`, que **no** deben marcarse.
- El fixture crea las dos organizaciones y todos los estados listados, y es idempotente (test).
- Ninguna ruta dev-only sirve contenido en el build de producción (test).
- El PR incluye el top-30 de hallazgos de la línea base. Los prompts siguientes lo usarán como lista de entrada.
