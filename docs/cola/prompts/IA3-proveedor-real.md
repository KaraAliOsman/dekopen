# IA3 — Proveedor de IA real: configuración, tool calling, costos y observabilidad

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

**Depende de:** IA1. Corre en paralelo con IA2 (IA3 es la capa de proveedor; IA2, las operaciones y herramientas). **Usa la clave real ya configurada** en el `.env` local (`AI_GATEWAY_MIMO_API_KEY`; ver el contrato). Si por algún motivo la llamada real falla (red, cuota), construye y prueba todo contra un proveedor simulado, deja la verificación real como el único punto pendiente en el PR con la causa exacta y **sigue**: no es un bloqueo del resto del encargo.

## Objetivo
Que en producción la IA use un modelo real, de forma confiable y con costo controlado, y que el dueño vea en Ajustes si está funcionando, sin tener que leer logs.

## Situación actual
- `backend/ai_gateway/providers.py`: MOCK por defecto con `DEBUG=1`; `OpenAICompatibleProvider` usa `json_object` sin tools; hay timeouts por proveedor y resolución de host (protección SSRF).
- `docs/operations/AI_PROVIDERS.md` documenta las variables. `backend/ai_gateway/metrics.py` existe.
- La fase 14 dejó pendiente el proveedor real (F14-7).

## Proveedor objetivo (decisión del dueño)
- **API compatible con OpenAI** en `https://api.primalabs.ai/v1` (endpoint `POST /chat/completions`), modelo `primalabs-ai/MiMo-V2.6-Pro`.
- Configuración con la convención existente del gateway: **`AI_GATEWAY_MIMO_API_KEY`**, **`AI_GATEWAY_MIMO_BASE_URL`** y **`AI_GATEWAY_MIMO_MODEL`** (ya presentes en el `.env` local; nunca en el repo, en un prompt, en logs ni en el frontend). Reutiliza esos nombres y los que `AI_PROVIDERS.md` ya defina; no inventes otros. Las rutas de `ai_routes` de las capacidades reales deben apuntar al proveedor `MIMO`, no a `MOCK`.
- **Revisa `AI_GATEWAY_MOCK_ENABLED`:** el `.env` local lo trae en `1` (dos veces). Con el proveedor real configurado, el entorno de desarrollo debe usar MIMO por defecto; MOCK queda solo para tests y para el “Modo de prueba” explícito. Documenta en `.env.example` y `AI_PROVIDERS.md` la configuración correcta (sin valores secretos).
- **Primera tarea de verificación:** sondea si el modelo soporta `tools`/`tool_choice` nativo y si acepta entradas multimodales (imagen/PDF). Documenta el resultado en el PR:
  - Si soporta tools → tool calling nativo (alcance 1).
  - Si no → fallback a JSON estricto con esquema, ya previsto.
  - Si no acepta imágenes/PDF → la ingesta de catálogo por IA (D01) necesita una capa OCR previa (extracción de texto/tabla) o un segundo modelo de visión configurable por capacidad; déjalo previsto en el ruteo por capacidad `catalog_import` y documéntalo como bloqueo si no hay alternativa configurada.

## Alcance
1. **Tool calling** en el protocolo compatible con OpenAI (`tools` y `tool_choice`) y en cualquier otro protocolo que ya soporte el registro (`AI_GATEWAY_{P}_PROTOCOL`). Si un modelo no soporta tools, usa un fallback a JSON estricto con esquema y valídalo. Los esquemas de las herramientas salen del registro de IA2; mientras IA2 no esté mergeado, usa las herramientas actuales.
2. **Ruteo por capacidad** (`design_assist`, `agent`, `context_assist`, `catalog_import`): proveedor y modelo configurables por capacidad, timeouts, 2 reintentos con backoff solo en errores transitorios, e idempotencia por `operation_key` (ya existe; mantenla).
3. **Respuesta en streaming** hacia la UI (SSE o el mecanismo que ya use el frontend para los trabajos), con estados intermedios: “consultando proyecto”, “calculando con el motor”, “preparando propuesta”. Estos estados alimentan el Orb (P17).
4. **Costos:** tokens y costo estimado por trabajo, por usuario y por organización; presupuesto mensual configurable por organización, con bloqueo suave al superarlo (mensaje claro y aviso al dueño).
5. **Ajustes › Inteligencia artificial** (solo OWNER):
   - estado del proveedor (Conectado, Sin credencial o Error, con la última causa legible);
   - modelo por capacidad;
   - botón “Probar conexión” (un caso mínimo del arnés de IA1);
   - consumo del mes y presupuesto.
   - **La clave nunca se muestra ni viaja al frontend**: solo se indica “configurada” o “no configurada”.
6. **Producción segura:** en el build de producción, `MOCK` solo se usa con un flag explícito, y en ese caso la UI muestra la insignia “Modo de prueba” (no la palabra MOCK). Agrega un test de que `DEBUG` no activa MOCK en la configuración de producción.
7. **Observabilidad:** log estructurado por trabajo (capacidad, modelo, latencia, rondas, tokens y resultado) sin contenido sensible, y un panel en `/jobs` filtrable por capacidad y estado.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño revisando si la IA funciona y cuánto cuesta.
- **Anatomía:** Ajustes › Inteligencia artificial: estado del proveedor, modelo por capacidad, “Probar conexión”, consumo y presupuesto. La clave nunca viaja al frontend.
- **Momento de firma (preservar o crear):** Los estados intermedios del trabajo (“consultando proyecto”, “calculando con el motor”) alimentan el Orb en tiempo real.
- **Idea que sube el techo (obligatoria, con el motor):** Cada trabajo de IA muestra su costo y su traza (qué consultó, qué herramientas usó, cuánto tardó) en lenguaje de negocio.
- **Slop a eliminar aquí:** Errores crudos del proveedor, la palabra MOCK, logs con contenido sensible.
- **Preguntas del pase editorial:** ¿El dueño sabe, sin leer logs, si la IA está funcionando? ¿Hay algún camino por el que la clave se exponga?

## Criterios de aceptación
- Con `AI_GATEWAY_MIMO_API_KEY` presente: la suite de IA1 corre contra `primalabs-ai/MiMo-V2.6-Pro` y se reporta su resultado por caso; “Probar conexión” en verde (captura).
- Sin credencial: Ajustes muestra “Sin credencial” con instrucciones, sin errores crudos (captura); test de que la clave no se expone por la API ni en logs.
- Reporte de capacidades del modelo en el PR (tools sí/no, visión sí/no) con la evidencia de la llamada de prueba.
- Tests de reintento, timeout, presupuesto superado y fallback a JSON estricto.
