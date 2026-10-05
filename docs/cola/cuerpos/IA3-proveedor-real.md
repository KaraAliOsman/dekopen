# IA3 — Proveedor de IA real: configuración, tool calling, costos y observabilidad

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
