# D03 — Aperturas y tipologías: de un enum de 12 valores a un modelo de apertura real

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

**Depende de:** D01 (familias de sistema). Debe mergearse **antes** de P05 (simbología) y de IA2 (operaciones) o, si van en paralelo, esos encargos rebasean y cubren lo que este agregue.

## Problema
`BayOpeningType` (`engine/src/dekopen_engine/models.py:49`) tiene 12 valores fijos: FIXED, TURN_L/R, TILT_TURN_L/R, SLIDING_2L/3L/4L, SLIDING, AWNING, DOOR_ENTRY y DOOR_DOUBLE. `hardware.py` los normaliza en TURN, TILT_TURN, SLIDING, DOOR y AWNING, y `design_assist` acepta solo 8. Así **no se pueden expresar** tipologías básicas del mercado chileno:
- abatible **hacia afuera**, típica del aluminio;
- **solo abatimiento** (banderola interior);
- **ventana francesa de 2 hojas con inversor**, con hoja activa y pasiva;
- **fijo en hoja**;
- puerta doble activa/pasiva, con sus manillas;
- puerta con lateral fijo.

Combinar todo en un enum hace que cada tipología nueva se convierta en una rama de código.

## Diseño
1. **Objeto `Opening`** en el motor, que reemplaza el enum como fuente de verdad:
   - `movement`: FIXED · TURN · TILT · TILT_TURN · TOP_HUNG (proyectante) · BOTTOM_HUNG · SLIDE · LIFT_SLIDE · PARALLEL_SLIDE · FOLD · PIVOT_V · PIVOT_H · VERTICAL_SLIDE (guillotina). Las últimas siete las implementa D08; aquí solo se declaran.
   - `hinge_side`: LEFT · RIGHT · TOP · BOTTOM · NONE.
   - `direction`: INWARD · OUTWARD.
   - `leaf_role`: ACTIVE · PASSIVE (inversor) · SINGLE.
   - `fixed_in_sash`: bool.
   - **Compatibilidad hacia atrás:** un mapeo total y probado enum ↔ `Opening`. Los productos guardados se leen y migran sin cambiar su geometría ni su precio (golden tests antes/después **idénticos**). La API acepta ambos durante una versión.
2. **Capacidades por sistema** (catálogo, D01): qué combinaciones de movimiento × dirección × rol admite cada sistema, y con qué herrajes (D04). El editor, la IA y la API solo ofrecen lo que el sistema admite.
3. **Implementa completas** (motor, BOM, cortes, herrajes, validación, simbología en el contrato de P05 si existe, y etiquetas en `domainLabels`):
   - abatible hacia adentro y hacia afuera (izquierda y derecha);
   - oscilobatiente (izquierda y derecha);
   - solo abatimiento (bisagras abajo, hacia adentro);
   - proyectante (bisagras arriba, hacia afuera);
   - fijo en marco y fijo en hoja;
   - **ventana francesa de 2 hojas** con inversor (rol INVERSOR existente): activa a la derecha o a la izquierda, con la pasiva con falleba;
   - puerta simple (izquierda y derecha, hacia adentro y hacia afuera);
   - puerta doble activa/pasiva;
   - puerta + lateral fijo.
4. **Manillas:** posición derivada (lado de cierre; en la ventana francesa, solo en la activa), altura según la regla del sistema o herraje (D04) y editable dentro de su rango.
5. **Nombres humanos** en español para cada combinación. Ejemplos: “Abatible hacia afuera — bisagras a la izquierda”, “Francesa 2 hojas — activa derecha”, “Solo abatimiento (banderola)”.

## Fuera de alcance
Elevable, osciloparalela, plegable, pivotante y guillotina (D08). UI del editor (P04 consume las capacidades).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador eligiendo la apertura. Debe sentir: “solo veo lo que este sistema puede hacer, y se ve como es”.
- **Anatomía:** Paleta de aperturas con `OpeningGlyph` (P01) y nombres del glosario; solo las compatibles con el sistema; las no disponibles, con su causa.
- **Momento de firma (preservar o crear):** Los íconos de apertura son la misma gramática del lienzo y del documento.
- **Idea que sube el techo (obligatoria, con el motor):** Al pasar sobre una apertura, la bahía muestra la vista previa dibujada (con la manilla y el lado de bisagra correctos) antes de elegirla.
- **Slop a eliminar aquí:** Abreviaturas crípticas, íconos genéricos de “ventana”, aperturas incompatibles ofrecidas y luego rechazadas.
- **Preguntas del pase editorial:** ¿Un estimador distingue proyectante de abatible sin leer? ¿Se puede elegir algo que el sistema no fabrica?

## Criterios de aceptación
- Migración enum → `Opening` con golden tests de cortes, BOM y precio **idénticos** para todos los productos del fixture.
- Golden tests nuevos para cada tipología de la lista: cortes, herrajes y peso por hoja.
- Test de capacidades: un sistema sin “hacia afuera” rechaza esa dirección con un mensaje que nombra los sistemas que sí la admiten.
- Paridad de símbolos (si P05 está mergeado): fixtures nuevos para cada tipología.
- Captura de cada tipología renderizada (técnica, vista interior).
