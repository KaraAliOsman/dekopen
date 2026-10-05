# P17 — Asistente IA, Trabajos y Orb vivo: la IA hace trabajo visible, revisable y deshacible

**Depende de:** P01, IA2 (operaciones y herramientas) e IA3 (proveedor y streaming). Mejor después de P04 (el panel del asistente convive con el editor).

## Objetivo
Que la IA de DEKOPEN se sienta como **un colega técnico** que propone cambios concretos sobre el modelo, que se revisan con una vista previa real, se aplican con las mismas operaciones tipadas y se deshacen. El Orb comunica en todo momento su estado real.

## Situación actual
- `frontend/src/features/assistant/` (`Orb.tsx` de ~150 líneas, `BotFigure.tsx`, `orb.css` de ~450 líneas, workspace del asistente), `frontend/src/features/jobs/` y `frontend/src/app/JobsPage.tsx`; backend en `backend/ai_gateway`, `backend/jobs` y `backend/automations`; proveedores en `docs/operations/AI_PROVIDERS.md`.
- El PR #113 (mergeado) dejó la identidad del bot en 2D plano: esfera grafito sólida, ojos cápsula cyan y una sola línea orbital.
- Referencia del dueño (adjunto `image.png`): esfera antracita, dos ojos cápsula cyan, un anillo orbital cyan y paneles de vidrio que se transforman en ventana en la secuencia IDEA → FORMA → CONFIGURA → VISUALIZA → TU VENTANA. Especificación del Orb en los adjuntos `dekopen-orb-spec.md` y `dekopen-orb.html`: estados idle, queued, thinking, working, waiting, success, error y canceled; tamaños 20, 28 y 64; sin boca, sin filtros glow, sin estilo infantil; `prefers-reduced-motion`; IDs SVG únicos.
- (auditoría) En la app el Orb aparece como un punto diminuto y no refleja trabajos reales. El chat es una lista y un hilo básicos. Los fallos repetidos del proveedor llenan el hilo (“El proveedor externo no respondió” × N). En builds antiguos se vio la palabra “MOCK” y errores técnicos crudos en Trabajos (hoy hay un mapeo `jobFailure`; verifica).
- La fase 14 verificó, bajo MOCK, la idempotencia, la cancelación, el reintento y el 403 para OPERATOR/INSTALLER. El proveedor real está pendiente (F14-7) y necesita una credencial del dueño.

## Alcance
1. **Orb conectado al estado real:** un hook `useAssistantPresence(context)` deriva el estado del Orb del trabajo de IA más reciente del contexto actual (proyecto, posición u OT). Lo usan el lanzador en la barra superior, el encabezado del dock, los avatares, las tarjetas de artefacto y los estados vacíos. Agrega tests unitarios del mapeo estado del job → estado del Orb, incluido un estado desconocido → idle seguro.
2. **Dock contextual:** drawer derecho de 400 px que sabe dónde está el usuario (“Pos. 03 Living · P-000012”) y ofrece sugerencias **de esa pantalla** (en el editor: “Proponer división 1/3–2/3”, “Revisar compatibilidad de herrajes”; en precios: “Explicar por qué subió el total”).
3. **Artefactos revisables:** cada propuesta de la IA es una tarjeta con su vista previa. En el editor es un diff del modelo dibujado con el **renderer real** (antes y después) junto con el impacto en precio y validez que calcula el **motor**. Acciones: Aplicar (operaciones tipadas existentes, deshacible), Descartar y Ver auditoría. **La IA nunca escribe números**: solo propone operaciones que el motor evalúa.
4. **Fallos:** se colapsan (“3 intentos fallidos · Reintentar · Detalles técnicos”). El estado del proveedor se ve en Ajustes, no en el hilo. Nunca se muestra “MOCK” fuera de DEV; en DEV se muestra una insignia discreta “Proveedor de prueba”.
5. **Trabajos (`/jobs`):** lista con tipo en español, objeto (código humano), estado (`StatusChip`), duración, actor y resultado. Errores con un mensaje humano y “Detalles técnicos” plegable con el código. Reintento solo cuando el backend lo permite.
6. **Identidad del bot:** ajusta `BotFigure`/`Orb` a la referencia del dueño sin perder la especificación. Comunica los estados con los ojos (abiertos, entrecerrados, parpadeo, mirada lateral) y el anillo (progreso, color semántico de estado). Tamaños 16, 20, 28, 64 y 160. Agrega una animación de bienvenida opcional (ventana que se arma), desactivada con *reduced motion*.

## Fuera de alcance
La capa de proveedor (la hace IA3) y el vocabulario de operaciones (lo hace IA2). Verifica la experiencia con el modelo real (`AI_GATEWAY_MIMO_*` del `.env` local, ver el contrato).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Cualquier usuario que le pide algo a la IA. Debe sentir: “es un colega técnico que hace lo que pido y me dice la verdad”.
- **Anatomía:** Constitución §5.11: dock con artefactos (propuesta con antes/después, plan, comparación), estados distintos (propuesto, vista previa, esperando confirmación, aplicado, falló, bloqueado), aclaraciones como chips.
- **Momento de firma (preservar o crear):** F8: el Orb (spec `dekopen-orb-spec.md`) conectado a trabajos reales, con IDs de gradiente únicos, `prefers-reduced-motion` y semántica accesible. Excepción documentada: el Orb es el único elemento con animación continua, y solo mientras trabaja.
- **Idea que sube el techo (obligatoria, con el motor):** Pedir “todo el 2º piso a termopanel Low-E” produce un artefacto con la lista de posiciones, el diff dibujado, el Δ de precio y de Uw, y un botón Aplicar que ejecuta las mismas operaciones tipadas, deshacibles.
- **Slop a eliminar aquí:** Burbujas de chat con texto largo, “¡Listo!” sin haber aplicado, avatar morado con degradado, errores repetidos llenando el chat.
- **Preguntas del pase editorial:** ¿Hay algún camino en el que la IA diga “hecho” sin haber aplicado? ¿Cada propuesta se puede ver antes de aceptar?

## Criterios de aceptación
- e2e bajo el proveedor de prueba: en el editor, pedir “divide la hoja en dos oscilobatientes” → aparece la tarjeta con antes/después y Δ de precio → Aplicar → el modelo cambia → Deshacer restaura → la auditoría registra todo. Durante el flujo el Orb pasa por thinking → working → waiting → success (test).
- Tests de reduced motion e IDs SVG únicos con 3 Orbs en pantalla.
- `ux:capture` sin “MOCK” y sin errores crudos en `/assistant` y `/jobs`. Capturas claro y oscuro.
