# P04 — Editor de posición “canvas-first”: layout e interacción profesional

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

**Depende de:** P01, D02 (vidrios), D03 (aperturas), D05 (colores) y P05 (dibujo). El selector de apertura, el de vidrio y el de color consumen las capacidades que esos encargos exponen; si alguno no está mergeado, usa lo que exista y no inventes opciones. Puede correr en paralelo con P05 (P04 se ocupa de layout e interacción; P05, de la geometría de los símbolos). **No toques** la lógica de glifos de `ProductFrontSvg.tsx` ni `backend/documents/renderers.py`.

## Objetivo
El editor es la superficie que define el producto. Tiene que sentirse como una herramienta CAD de oficio técnico: el dibujo en el centro y protagonista, medidas editables sobre el propio dibujo, herramientas con nombre y un inspector que muestra solo lo que importa de la selección. La primera reacción esperada del usuario es: *“esto entiende de ventanas”*.

## Situación actual
- Archivos: `frontend/src/features/canvas/` (`CanvasEditor2DView.tsx`, `CanvasViewport.tsx`, `CADViewportSvg.tsx`, `EditableDimension.tsx`, `ObjectTree.tsx`, `StarterGallery.tsx`, `designLibrary.ts`, `productEditing.ts`, `intentEditing.ts`, `canvasStore.ts`, `snapping.ts`, `viewport.ts`, `canvas.css`), `frontend/src/features/projects/ProjectPositionEditor.tsx` y `frontend/src/features/inspector/`.
- (auditoría, varias sesiones) Antes del lienzo se apilan campos de ancho completo (Ubicación, Cantidad, Serie de perfiles, Acabado), un acordeón “Biblioteca de diseños” y un banner naranja largo (“No se puede guardar todavía…”). Resultado: a 1440×900 el lienzo ocupa apenas el tercio inferior de la pantalla.
- (auditoría) A 1366 la vista en planta se superpone; a 768 el lienzo desaparece; el pan con rueda puede dejar el dibujo fuera de vista sin forma obvia de volver; el riel de herramientas tiene íconos diminutos sin etiqueta; la paleta de aperturas es una grilla de glifos sin nombre (>, <, V, #, +); hay un enlace que no responde cuando hay cambios sin guardar (sesión 9e41dc53 “p3-dirty-link-dead-click”); y el árbol “Árbol del conjunto” es diminuto.
- Ya existen operaciones tipadas con deshacer y rehacer, un guard de cambios sin guardar (`app/UnsavedChangesGuard.tsx`) y `EditableDimension.tsx`. **Úsalos; no crees otra vía de mutación.**

## Diseño objetivo (≥ 1280 px)
- **Franja superior (≈ 48 px):** migas (Proyecto › Pos. 03), nombre o ubicación editable en línea, cantidad, y **chips** de Serie y Acabado que abren un popover. A la derecha: estado de guardado (“Guardado” o “Cambios sin guardar”), Deshacer/Rehacer, **chip de precio en vivo** (neto unitario y total de línea, ambos del motor) y **chip de estado** (“Válido” · “2 avisos” · “Bloqueado”) que abre el panel “Qué falta”. Ese panel reemplaza el banner naranja: cada ítem explica el problema en lenguaje de taller, propone una acción y enlaza al campo.
- **Izquierda: riel de herramientas con etiquetas** (Seleccionar, Dividir vertical, Dividir horizontal, Apertura, Vidrio, Acoplar, Medir), con tooltip y atajo. La **biblioteca de tipologías** es un flyout agrupado (Fijos, Abatibles, Oscilobatientes, Correderas, Proyectantes, Puertas, Conjuntos) con miniaturas dibujadas por el renderer real; solo muestra las tipologías que el sistema elegido admite, según el catálogo y el motor, nunca una lista fija.
- **Centro: lienzo** con al menos el 60 % del ancho y el 75 % del alto del viewport. Al abrir, “Ajustar a pantalla”. Zoom con rueda centrado en el cursor y pan con espacio + arrastre o con el botón medio. El pan queda **acotado**: el dibujo no puede salir por completo de la vista y siempre hay un botón “Centrar”. Selectores de vista: Interior/Exterior, Comercial/Técnica, 2D/3D y Planta (si aplica).
- **Derecha: inspector (320–360 px)** con secciones que dependen de la selección:
  - Medidas: ancho y alto, más las cotas parciales de la bahía.
  - Apertura: selector visual **con nombre**, por ejemplo “Abatible — bisagras a la izquierda”, “Oscilobatiente — manilla a la derecha” o “Corredera — hoja izquierda móvil”.
  - Vidrio: composición, por ejemplo 4-16-4.
  - Manilla: altura en mm; el lado lo deriva el motor.
  - Herrajes: kit derivado, de solo lectura.
  - “Avanzado”, plegado: roles de perfil, refuerzo y procedencia.
- **Abajo, plegable:** árbol del conjunto y tira de posiciones del proyecto para saltar entre ellas.

## Interacción
- Clic en una bahía la selecciona; doble clic abre el selector de apertura. Clic en una cota abre un input **en el lugar**: Enter confirma con la misma operación tipada que usa el inspector y Esc cancela.
- Teclado: V (seleccionar), | y – (dividir), Ctrl+Z / Ctrl+Y, Supr, flechas (mueven divisores 1 mm; con Shift, 10 mm), F (ajustar) y ? (atajos).
- Los cambios se recalculan con el motor (`useEngineCalculation`) con debounce y sin bloquear la UI; mientras tanto el precio muestra un estado “calculando”, nunca un número viejo sin indicarlo.
- **1024–1279 px:** el inspector pasa a drawer y el riel queda solo con íconos y tooltip. **Menos de 1024 px:** vista de lectura con medidas, precio y un aviso de “edición disponible desde 1024 px”. Tablet horizontal (1024×768) totalmente usable.

## Fuera de alcance
Símbolos y cotas técnicas (P05), edición de bow en planta (P06), 3D (P19) y lógica de precios.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador, 30 a 80 posiciones por obra, con presión de plazo. Debe sentir: “esto entiende ventanas y es más rápido que mi software”.
- **Anatomía:** Constitución §5.4 y estudio de interacción: lienzo de borde a borde (≥ 60 % del ancho) con islas flotantes, inspector acoplado de 300–320 px según la selección, cotas encadenadas editables en el lugar, vista en planta, atajos (`V`, `H`, `F`, `Shift+1`, `Shift+2`, `Ctrl+K`). Básico arriba, “Avanzado” plegado.
- **Momento de firma (preservar o crear):** F1 (lienzo como hoja con inglete sobre la mesa), F4 (cota editable en el lugar), F5 (franja de planta con carriles), F7 (manijas naranjas = manipulación).
- **Idea que sube el techo (obligatoria, con el motor):** Escribir en la paleta “partir en tres, centro fijo, laterales abatibles hacia el centro” muestra la propuesta dibujada en fantasma naranja con el Δ de precio antes de aplicar (operaciones del registro de IA2, sin IA si la frase es un comando directo).
- **Slop a eliminar aquí:** Formularios de ancho completo sobre el dibujo, encabezados dentro del lienzo, herramientas sin nombre ni atajo, banners de error en vez de “Qué falta”, modales para editar una medida.
- **Preguntas del pase editorial:** ¿Se puede diseñar una ventana completa sin tocar un formulario? ¿Un estimador nuevo encuentra cada herramienta sin preguntar? ¿El inspector muestra ≥ 8 campos a 768 px?

## Criterios de aceptación
- Test Playwright: a 1440×900 la caja del lienzo es ≥ 60 % del ancho y ≥ 75 % del alto del viewport; sin scroll horizontal entre 1024 y 1920.
- Desde una posición vacía, crear una “ventana de 2 hojas oscilobatientes, 1500 × 1200, vidrio 4-16-4” en **≤ 6 interacciones** (test e2e que las cuente).
- Pan extremo (10.000 px) → el dibujo sigue visible o se recentra (test).
- Todas las herramientas tienen etiqueta o tooltip y aria-label (test). El selector de apertura muestra nombres en español y solo opciones compatibles (test con un sistema que no admita corredera).
- El guard de cambios sin guardar funciona en todos los enlaces del editor, incluido el caso “dirty-link” (test).
- Los tests existentes de canvas y proyectos pasan, y hay capturas antes/después en 1440, 1280 y 1024, claro y oscuro.
