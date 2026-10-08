# IA1 — Diagnóstico de la IA y arnés de evaluación por resultado: medir antes de arreglar

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

**Depende de:** nada; puede correr en la ola 0, en paralelo con P00 y P01. Usa el fixture de P00 si ya está mergeado; si no, `scripts/dev_fixture.py` tal como está.

## Problema (palabras del dueño)
“La IA no funciona, no hace lo que le pides.” Hoy no hay una medición de cuánto falla ni de por qué. Este encargo **no arregla la IA**: construye la vara para medirla, mide la línea base y entrega un diagnóstico con causas. IA2 e IA3 corrigen después contra esta misma vara.

## Hechos verificados en main `b3d1c9b` (punto de partida del diagnóstico)
- `backend/ai_gateway/providers.py`: el proveedor **MOCK** es el valor por defecto cuando `DEBUG=1` o con `AI_GATEWAY_MOCK_ENABLED=1`, y responde de forma determinista (“Respuesta determinista del proveedor MOCK.”). Hay `OpenAICompatibleProvider` con `temperature=0` y `response_format=json_object`, **sin tool calling**.
- `backend/projects/design_assist.py`: el modelo solo puede proponer ~18 operaciones a nivel de módulo de ensamblaje (`set_module_count`, `add_unit`, `remove_unit`, `duplicate_module`, `insert_module`, acoples, `set_module_width`, `set_total_width`, `set_height`, `equalize_*`, `set_opening`, `set_glass_thickness`, `set_glass`, `set_panel`). Además:
  - `OPENINGS` acepta solo 8 aperturas; faltan `SLIDING_3L`, `SLIDING_4L`, `SLIDING` con layout y `DOOR_DOUBLE`.
  - **No hay** operaciones para dividir una bahía con montante o travesaño en una posición dada, mover divisores, altura de manilla, color o acabado, sistema, ubicación o cantidad, ni para crear o duplicar posiciones.
- `backend/ai_gateway/agent.py`: el plan tiene topes de `MAX_STEPS=8`, `MAX_QUERIES=3` y `MAX_ROUNDS=3`. Hay una **verificación de números “grounded”**: una respuesta con un número que no aparece literal en el contexto o en el texto del usuario se rechaza (con 1 ronda correctiva) y el trabajo falla. Un número **derivado** (por ejemplo, 1500/2 = 750) puede tumbar una respuesta correcta.
- Los paneles de IA del frontend tienen su propio vocabulario de operaciones, distinto (`frontend/src/features/canvas/designOps.ts`, `productEditing.ts`, `intentEditing.ts`).

## Alcance
1. **Arnés** en `backend/ai_gateway/evals/`, ejecutable con `python -m ai_gateway.evals.run --provider <MOCK|configurado> --out docs/ai/evals/<fecha>.json`.
   - Por cada caso: carga el contexto del fixture, envía la petición por **la misma ruta que usa la UI** (endpoint del asistente o agente), aplica las operaciones propuestas en un **sandbox** (una copia del producto o proyecto, sin persistir) y evalúa el **resultado**, no el texto.
   - Registra latencia, rondas, operaciones propuestas, operaciones rechazadas con su motivo, respuestas rechazadas por grounding y errores del proveedor.
2. **Taxonomía de fallos.** Cada caso fallido se clasifica en una de estas causas:
   - `proveedor_no_configurado`
   - `proveedor_error`
   - `formato_invalido`
   - `op_no_soportada` (no existe en el vocabulario)
   - `op_rechazada_validador`
   - `grounding_rechazo`
   - `contexto_insuficiente`
   - `resultado_incorrecto`
   - `no_pidio_aclaracion` (inventó en vez de preguntar)
   - `accion_consecuente_ejecutada` (debía solo preparar)
3. **Casos (redactados por el dueño del producto; impleméntalos tal cual, como fixtures YAML).**
   - Base de la vista Editor: posición vacía 1500 × 1200 mm del sistema practicable del fixture.
   - Las convenciones de apertura son las del motor: `TURN_LEFT` / `TILT_TURN_LEFT` = bisagras a la izquierda y manilla a la derecha, vista interior.

   | ID | Petición | Resultado esperado |
   |---|---|---|
   | E01 | “divide la ventana en dos hojas iguales” | 2 bahías separadas por un montante con eje en 750 mm. Aperturas: las que tenían (FIXED) o una aclaración. |
   | E02 | “la izquierda fija y la derecha oscilobatiente con la manilla a la derecha” | 2 bahías: izquierda FIXED, derecha TILT_TURN_LEFT. |
   | E03 | “hazla de 1,8 metros de ancho por 1350 de alto” | 1800 × 1350. |
   | E04 | “agrega un travesaño a 400 mm desde arriba para una banderola fija” | Travesaño horizontal; bahía superior de 400 mm de alto, FIXED. |
   | E05 | “cambia el vidrio a termopanel 4-12-4” | Vidrio = el SKU del catálogo con composición 4-12-4, o la lista de opciones disponibles si no existe (nunca un SKU inventado). |
   | E06 | “pon vidrio laminado 4+4” (no está en el catálogo del fixture) | Sin operación; responde que no está disponible y lista las alternativas reales. |
   | E07 | “conviértela en corredera de dos hojas” (el sistema no admite corredera) | Sin operación; explica la incompatibilidad y propone un sistema compatible si existe. |
   | E08 | “manilla a 1050 del piso” | **Pide aclaración**: falta la altura de instalación sobre el piso. Sin operación. |
   | E09 | “¿cuánto pesa la hoja derecha?” (después de E02) | Cifra igual a la del motor, o “sin dato” con la causa. |
   | E10 | “¿por qué no puedo guardar?” | Lista exactamente los bloqueos que devuelve la validación del motor. |
   | E11 | “aser la bentana 20 cm mas ancha” | Ancho + 200 mm. |
   | E12 | “pon la manilla al otro lado” (en una TILT_TURN_LEFT) | TILT_TURN_RIGHT. |
   | E13 | “tres hojas: fija al centro y abatibles a los lados” | 3 bahías: TURN_LEFT · FIXED · TURN_RIGHT (bisagras en las jambas exteriores y manillas hacia el centro), anchos iguales salvo instrucción. |

   Vista Proyecto (fixture de 12 posiciones):

   | ID | Petición | Resultado esperado |
   |---|---|---|
   | J01 | “cambia el vidrio de todas las ventanas del segundo piso a [SKU existente]” | Lote solo sobre las posiciones cuya ubicación indica 2º piso. Si la ubicación no lo permite, aclaración. |
   | J02 | “crea una corredera de 2 hojas de 1600 × 1100 para la cocina” | Posición nueva con esa tipología, medidas y ubicación (o la incompatibilidad explicada). |
   | J03 | “duplica la posición 3 cuatro veces para los dormitorios” | 4 posiciones nuevas iguales a la 3, o la cantidad +4, según el modelo, documentado. |
   | J04 | “¿cuál es la posición más cara y por qué?” | Identifica la posición correcta según el motor; cifras grounded. |
   | J05 | “baja el precio un 5 %” | Propuesta que requiere aprobación si cae bajo la banda; **no se aplica sola**. |
   | J06 | “emite la cotización” | Tarjeta de preparación con un deep link; nada emitido. |
   | J07 | “¿qué falta para emitir?” | Exactamente los faltantes del backend. |
   | J08 | “compara la REV-A con la REV-B” | Artefacto de comparación con las diferencias reales. |

   Vista Producción / Compras:

   | ID | Petición | Resultado esperado |
   |---|---|---|
   | F01 | “¿qué OT están bloqueadas y por qué?” | Lista exacta del backend. |
   | F02 | “¿cuántas barras de marco usa la OT [código]?” | Número igual al del plan de corte. |
   | F03 | “prepara la compra de lo que falta” | Artefacto de plan de compra; nada enviado. |

   Generales:

   | ID | Petición | Resultado esperado |
   |---|---|---|
   | G01 | “dame un precio aproximado de una ventana de 2 × 2 sin crearla” | No inventa; ofrece crear un borrador y calcularlo con el motor. |
   | G02 | “¿qué diferencia hay entre oscilobatiente y abatible?” | Explicación correcta, sin números inventados. |

4. **Corrida base:** con MOCK y, si el entorno tiene una credencial real configurada (**no la pidas ni la imprimas**), también con el proveedor real. Commitea los JSON de resultados y un `docs/ai/evals/README.md` con: tasa de éxito por vista y por caso, la taxonomía de fallos con conteos, y las **5 causas raíz principales con evidencia** (archivo y línea), ordenadas por impacto.
5. **CI:** agrega un job opcional (no bloqueante) o un comando en `make` que corra la suite con MOCK, para que nadie rompa el arnés.

## Fuera de alcance
Cambiar prompts, el vocabulario de operaciones o los proveedores (eso es IA2 e IA3). Si encuentras un bug trivial que impide correr el arnés, corrígelo y documéntalo.

## Criterios de aceptación
- Los 26 casos corren de punta a punta con un solo comando y el resultado es reproducible.
- La evaluación es por resultado: comparación estructural del modelo resultante (medidas exactas en mm, aperturas, SKU de vidrio), no del texto.
- El informe de línea base y la lista de causas raíz están commiteados.
