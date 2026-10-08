# IA2 — Que la IA haga lo que se le pide: registro único de operaciones (UI = IA), herramientas del motor y aclaraciones

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
