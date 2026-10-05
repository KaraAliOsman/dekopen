# IA1 — Diagnóstico de la IA y arnés de evaluación por resultado: medir antes de arreglar

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
