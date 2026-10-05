# IA2 — Que la IA haga lo que se le pide: registro único de operaciones (UI = IA), herramientas del motor y aclaraciones

## Contrato común DEKOPEN (vale para todo este encargo)

Trabajas como ingeniero/a senior y diseñador/a de producto en DEKOPEN, el sistema operativo para fábricas de ventanas y puertas de PVC y aluminio. Repo: https://github.com/KaraAliOsman/framedex.

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

**Depende de:** IA1 (arnés y línea base). Mejor si D02 y D03 ya están mergeados (vidrios y aperturas estructurados); si no, cubre lo que exista y deja casos marcados como pendientes de esos encargos.

## Objetivo
Que la IA pueda hacer **todo lo que un usuario hace con la UI** en el editor y en el proyecto, usando **exactamente las mismas operaciones tipadas**; que calcule con el motor en vez de rechazar números derivados; y que pregunte cuando falta un dato. Meta medible: **≥ 85 % de éxito** en los casos E y J del arnés de IA1 con el proveedor real, y **0** casos en las categorías `accion_consecuente_ejecutada` o `resultado_incorrecto` con números inventados.

## Situación actual
Ver IA1: el vocabulario de `design_assist` es estrecho (~18 operaciones, 8 aperturas); el frontend tiene su propio vocabulario (`designOps.ts`, `productEditing.ts`, `intentEditing.ts`); el grounding literal rechaza números derivados; no hay tool calling; y los topes del agente son 8 pasos, 3 consultas y 3 rondas.

## Diseño
1. **Registro único de operaciones** (`engine` o `backend/projects/ops_registry.py`, más un esquema JSON exportado en OpenAPI y generado para TS). Cada operación tiene nombre, esquema de parámetros, precondiciones, la función del motor que la aplica, una descripción en español para el modelo y ejemplos.
   - La **UI**, la **IA** y la **API** usan este registro. Migra los comandos del frontend para que emitan estas operaciones; los atajos y comandos existentes deben seguir funcionando (tests).
   - Operaciones mínimas, además de las actuales:
     - **Geometría:** `split_bay {bay, axis: V|H, offset_mm, from: START|END|CENTER}`, `move_divider`, `remove_divider`, `set_bay_size`, `equalize_bays`.
     - **Correderas:** `set_sliding_layout {panels X/O, tracks}` y `set_travel` (si P05 o D03 lo agregaron).
     - **Aperturas:** todas las del motor (D03).
     - **Atributos de la hoja o del producto:** `set_handle_height`, `flip_handing`, `set_glass {composition|sku}` (D02), `set_finish {interior, exterior}` (D05) y `set_system`.
     - **Posición:** `set_location`, `set_quantity`, `add_position {template, dims, location}`, `duplicate_position`, `remove_position` y `apply_to_positions {filter, ops}` (cambios globales).
     - **Acciones consecuentes:** solo como preparación, sin ejecución: `prepare_emit`, `prepare_release`, `prepare_purchase` y `prepare_payment_link`.
2. **Herramientas del motor** para el modelo (tool calling o function calling): `calculate_position`, `validate_position`, `price_position`, `price_project`, `explain_price_delta`, `list_catalog_options {system, kind}`, `get_blockers` y `simulate_ops {ops}` (aplica en sandbox y devuelve el producto, la validez y el Δ de precio).
   - **Los números que la IA cita deben venir de la salida de una herramienta del turno o del contexto.** El verificador de grounding acepta esos valores. Rechazar un número derivado correcto es un bug.
3. **Aclaraciones:** si falta un dato o la petición es ambigua (caso E08), la IA devuelve `clarify {question, options[]}`. La UI lo muestra como chips de respuesta y la respuesta continúa el mismo trabajo.
4. **Planes con vista previa:** la propuesta final siempre es `ops[]` + la salida de `simulate_ops`. La UI (P17) muestra antes y después; “Aplicar” ejecuta las mismas operaciones en una sola transacción deshacible.
5. **Prompt de sistema en español de Chile**, versionado en el repo, con:
   - un glosario de dominio: termopanel/DVH, junquillo, palillaje, corredera, proyectante, oscilobatiente, abatible, manilla, cremona, burlete, felpa, montante, travesaño, inversor, umbral, vierteaguas, premarco, vano;
   - las convenciones de apertura del motor;
   - las reglas: “nunca inventes SKU ni medidas; usa `list_catalog_options`; pregunta si falta información”;
   - ejemplos pocos y precisos, generados desde el registro.
6. **Topes razonables y configurables** (por ejemplo, 20 pasos, 6 consultas y 6 rondas), con un timeout total. Métricas por trabajo en `backend/ai_gateway/metrics.py`.

## Fuera de alcance
La UI del dock y del Orb (P17) y la configuración del proveedor (IA3). Si no hay una credencial real en el entorno, desarrolla contra MOCK y un proveedor simulado con respuestas guionadas por caso, y **declara en el PR** que la meta del 85 % queda pendiente de IA3.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Cualquier usuario que le pide algo a la IA. Debe sentir: “hace lo que pido, o me pregunta”.
- **Anatomía:** Las operaciones son las mismas de la UI (registro único); la IA nunca tiene un camino propio para cambiar el modelo.
- **Momento de firma (preservar o crear):** La aclaración con chips: cuando falta un dato, la pregunta trae las opciones reales del catálogo.
- **Idea que sube el techo (obligatoria, con el motor):** Pedidos compuestos (“divide en tres, centro fijo, laterales oscilobatientes hacia el centro, termopanel Low-E”) se resuelven en un solo plan simulado con el motor y un único diff.
- **Slop a eliminar aquí:** Respuestas largas en vez de acciones, “no puedo hacer eso” cuando la UI sí puede, números escritos por el modelo.
- **Preguntas del pase editorial:** ¿Hay algo que la UI hace y la IA no? ¿Algún número de la respuesta no viene de una herramienta?

## Criterios de aceptación
- La suite de IA1 se re-ejecuta y se commitea el informe comparativo (línea base vs. ahora) por caso y por categoría de fallo.
- Tests unitarios de cada operación nueva (motor y validador) y de paridad: la UI y la IA producen el mismo modelo para la misma operación.
- Test de grounding: un número derivado y presente en la salida de una herramienta se acepta; uno inventado se rechaza.
- e2e: E02, E04, E08 (aclaración) y J02 desde la UI del asistente, con capturas.
