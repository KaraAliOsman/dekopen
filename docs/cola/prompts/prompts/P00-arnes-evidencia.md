# P00 — Fundación del programa: rama de integración, constitución en el repo, arnés de evidencia visual, datos demo realistas e higiene de rutas

## Contrato común DEKOPEN (vale para todo este encargo)

Trabajas como ingeniero/a senior y diseñador/a de producto en DEKOPEN, el sistema operativo para fábricas de ventanas y puertas de PVC y aluminio. Repo: https://github.com/KaraAliOsman/dekopen.

**Entorno: Codex local en Windows.** Trabajas en un clon local del repo (la raíz del repo es tu directorio de trabajo), con acceso completo a la terminal, Docker, el CLI de Supabase, Node, Python (`.venv`) y `gh` (ya autenticado como el dueño). La cola completa está en **`docs/cola/`** (prompts, cuerpos, LEEME, constitución y `adjuntos/`): cuando un encargo menciona un adjunto, ábrelo desde `docs/cola/adjuntos/` según la tabla del §6 de `docs/cola/00-LEEME.md`. La verificación “en navegador real” se hace con **Playwright** (Chromium headless) desde el repo: capturas y recorridos automatizados que tú mismo inspeccionas. Si la shell es PowerShell, usa su sintaxis o invoca `bash` de Git cuando un script lo exija (los `make` del repo).

**Modo de trabajo: autonomía total.** El dueño revisará todo al final, no durante el trabajo. **No le hagas preguntas ni esperes su aprobación:** decide como lo haría un/a ingeniero/a senior con criterio de producto, aplica la constitución de diseño y registra cada decisión en el PR. Tu objetivo no es "terminado": es **lo mejor posible**, 100 % funcional y verificado.

**Ramas.** Toda la cola se integra en la rama **`integracion/v1`** (si no existe, créala desde el `origin/main` más reciente). Crea tu rama `codex/<id-del-encargo>-<slug>` desde el último `integracion/v1` y abre **un PR hacia `integracion/v1`**. Cuando los 4 checks de CI estén en verde y el pase editorial esté documentado, **mergea tú mismo con squash** y deja la rama actualizada. **Nunca hagas push ni PR a `main`**: eso lo hace solo el encargo final (P20) para la revisión del dueño. Si al empezar `integracion/v1` avanzó, rebasea antes de abrir el PR.

**Lee antes de tocar código:** `AGENTS.md`, `docs/ENGINEERING.md`, `docs/PRODUCT.md`, **`docs/design/CONSTITUCION.md`** (si todavía no está, usa `docs/cola/CONSTITUCION-DISENO.md`: es la misma), `docs/wiki/index.md` y sus páginas relevantes (sobre todo `docs/wiki/product/fenestration-and-ux.md` y `docs/wiki/quality/known-risks.md`), y la skill `.agents/skills/testing-framedex/SKILL.md` (stack local de Supabase, Django y Vite, fixture en `scripts/dev_fixture.py`, login por Mailpit). Usa `npm --prefix frontend run ux:capture` (lo crea P00) para las capturas de antes y después.

**Reglas no negociables**
1. **El motor (`engine/`) es la única fuente de números.** Ningún texto, plantilla, componente ni LLM fabrica medidas, cortes, precios ni valores técnicos. Lo desconocido se muestra como “Sin dato” con su causa y su acción; nunca como 0 ni con un valor por defecto silencioso.
2. **`Decimal`** para milímetros y dinero en el motor, el backend y SQL (`NUMERIC`). Si un cálculo cambia, agrega un caso golden (`make goldgen` y revisa el diff).
3. **Toda tabla de tenant lleva `org_id` + RLS.** Los permisos se aplican en el backend y la base de datos; la UI solo los refleja.
4. **Las revisiones emitidas, los documentos sellados y el historial de precios y auditoría son inmutables.**
5. **Conserva la arquitectura y los invariantes; las pantallas se rehacen sin miedo.** El motor puro, Django, RLS, la inmutabilidad y las operaciones tipadas se mantienen. Las superficies de UI que tu encargo cubre se rediseñan por completo si hace falta. **Borra antes que apilar:** elimina el componente, el CSS y la ruta viejos que quedan muertos; no dejes versiones paralelas. Si cambias la API, regenera `backend/openapi.yaml` y el cliente orval en el mismo PR.
6. **Esto no es una demo.** Algo está terminado solo cuando funciona de punta a punta con datos realistas, con los cinco estados (vacío, carga, error, sin permiso y bloqueado), verificado en el navegador. No hay botones sin efecto, TODO disfrazados, "Próximamente", datos demo hardcodeados en producción ni funcionalidades que existan solo en la UI. Lo sintético (el catálogo demo con precios aleatorios) se marca **DEMO** en todas partes y nunca se presenta como certificado.
7. **Constitución de diseño obligatoria.** Punto de vista: *“DEKOPEN se dibuja como se dibuja una ventana”*. Usa solo los tokens, la tipografía (IBM Plex Sans + Mono), los radios (≤ 4 px), la elevación por delineado, el movimiento (≤ 280 ms, un eje), la iconografía y las densidades (`office`, `workshop`, `document`) de la constitución. **Prohibido el SaaS genérico:** degradados, blur, brillos, morado de IA, tarjetas redondeadas de 8 px o más, botones píldora, sombras de color, KPI decorativos, emoji y copy de marketing. Preserva los **momentos de firma** (§7) e implementa la idea que **sube el techo** (§8) de cada superficie que toques.
8. **Idioma y formato.** Español de Chile: la app tutea, los documentos y el portal tratan de usted. Sin enums crudos, UUID ni hashes como identificador visible (solo en “Detalles técnicos”), sin inglés y sin validación nativa del navegador. Vocabulario del taller (hoja, marco, junquillo, montante, travesaño, termopanel, manilla). Formatos del §3.3: medidas `2 400 × 1 800 mm` (espacio fino, Mono tabular); CLP `$1.435.471`; porcentajes `32,5 %`; fechas `dd-mm-aaaa` en America/Santiago.
9. **Fidelidad de fenestración.** Cada elevación declara su vista (“Vista interior” por defecto). Simbología DIN: las líneas parten de las esquinas del lado de las bisagras y el vértice apunta a la manilla; el abatimiento parte de las esquinas inferiores y llega al centro superior; continuo = abre hacia el observador, discontinuo = se aleja. Las correderas nunca se dibujan ni se modelan como abatibles, y dos hojas móviles adyacentes no comparten carril. La manilla va del lado de cierre. Solo se ofrecen tipologías y combinaciones compatibles con el sistema elegido, según el catálogo y el motor.
10. **Divulgación progresiva y el sistema trabaja.** El usuario básico elige sistema, medidas, apertura, vidrio y color, y ve el precio. Lo que el motor puede derivar no se pregunta. La ingeniería vive en “Avanzado”. Toda acción en lote o propuesta de la IA muestra un diff antes de aplicar y se puede deshacer.

**Decisiones de producto pendientes:** no te detengas. Usa el valor por defecto de la constitución (§11), hazlo **configurable en Ajustes** y regístralo en `docs/decisions/valores-por-defecto.md`. Si tu encargo necesita una decisión que no está ahí, tómala con criterio, agrégala a ese archivo con la justificación y sigue.

**Integraciones externas diferidas** (el dueño las conecta después de aceptar el producto): despliegue en Railway u otro hosting, pagos reales con Flow, emisión real de DTE en el SII, correo con dominio propio, webhooks productivos y cualquier otra credencial de terceros. Para cada una: **construye la integración completa** detrás de un adaptador, con un proveedor **sandbox o simulado** que permita recorrer el flujo de punta a punta; muestra en Ajustes › Integraciones el estado (“No conectado”, con las instrucciones), y agrega los pasos exactos de activación en `docs/operations/ACTIVACION.md`. Esto **no es un bloqueo**: no te detengas por eso. **Excepción, el proveedor de IA: ya está conectado.** El archivo `.env` de la raíz del repo (ignorado por git) trae `AI_GATEWAY_MIMO_API_KEY`, `AI_GATEWAY_MIMO_BASE_URL=https://api.primalabs.ai/v1` y `AI_GATEWAY_MIMO_MODEL=primalabs-ai/MiMo-V2.6-Pro` (API compatible con OpenAI), que es la convención que ya usa `backend/ai_gateway/providers.py` (`AI_GATEWAY_{PROVIDER}_*`). Cárgalo en el entorno del proceso antes de levantar Django y el worker, y úsalo para todas las verificaciones de IA. **Nunca** imprimas, registres, copies a otro archivo ni commitees su valor; nunca lo pongas en el frontend.

**Verificación obligatoria**
- `make lint`, `make typecheck`, `make test` y `make build` en verde; `make test-db` si tocas migraciones, RLS, permisos o SQL.
- Prueba cada pantalla tocada en un navegador real con la skill testing-framedex: 1440×900, 1280×800 y 1024×768, en tema claro y oscuro; agrega 390×844 en el portal, el inicio y las vistas `workshop`. Prueba el **flujo completo** de la persona, no solo la pantalla: de dónde viene y adónde va.
- `ux:capture` sin hallazgos nuevos en las rutas tocadas.
- Capturas de antes y después en `docs/redesign/captures/<slug>/` (PNG comprimidos, 1440 claro como mínimo), enlazadas en el PR.
- **Pase editorial (constitución §9), obligatorio:** recorre el flujo, quita todo lo que no justifique su existencia, pasa la rúbrica R1–R20 y mejora las 3 cosas más débiles que queden (dos rondas). Documenta en el PR la tabla de la rúbrica con PASA/FALLA, lo que quitaste y por qué, y el momento de firma y la idea del §8 que implementaste. **Un ítem en FALLA impide el merge.**
- Espera a que los 4 checks de CI (Lint & Typecheck, Test Suite, Frontend Build, Database Gate) estén en verde. No debilites ningún check.

**Entrega final (en el PR y en tu último mensaje):** URL del PR, SHA del merge en `integracion/v1`, estado de los 4 checks, flujos probados con su resultado, capturas, tabla de la rúbrica, decisiones tomadas (con su registro en `valores-por-defecto.md`), integraciones dejadas en sandbox y una sección honesta de “No hecho / riesgos”. Actualiza `docs/wiki/state/current-reality.md` (`verified_ref` = tu SHA) y agrega una entrada en `docs/wiki/log.md` según `docs/wiki/SCHEMA.md`.

**Detente solo si** cumplir el encargo exige romper una regla no negociable, borrar datos reales o cambiar un contrato de dominio de forma incompatible con encargos ya mergeados. En ese caso, haz todo lo demás, deja el punto bloqueado aislado y explícalo. Las observaciones marcadas como “(auditoría)” vienen de capturas históricas: **re-verifícalas en el código actual antes de corregirlas**, porque algunas ya pueden estar resueltas.

---

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
