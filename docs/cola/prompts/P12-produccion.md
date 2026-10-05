# P12 — Producción: tablero por estación, detalle de OT escalable y vista de operario táctil

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

**Depende de:** P01 y P02.

## Objetivo
Que el jefe de producción vea la planta de un vistazo, que una OT de 100 posiciones se navegue sin muros de tablas, y que el operario en una tablet con guantes sepa **qué hacer ahora**, con botones grandes y sin datos comerciales.

## Situación actual
- `frontend/src/features/production/`; backend en `backend/production`; motor en `engine/src/dekopen_engine/manufacturing.py`, `manufacturing_trace.py`, `cutting.py`, `nesting.py` y `operations.py`.
- La fase 14 verificó el ciclo completo: estaciones, QC FAIL → HOLD, remake `OT-…-RM-01`, embalaje, etiquetas y despacho. **La lógica se conserva.**
- (auditoría, sesiones 65e8ad7f, fde66b2e y 0af1700d, y video A-Z)
  - La OT tiene 9 tarjetas de paso, cada una con Iniciar/Bloquear/Anotar, y forma un muro vertical.
  - La tabla de mecanizado filtra enums (SASH, GLAZING_BEAD, FRAME, “cara interior”).
  - Con 100 posiciones aparecen tablas de piezas gigantes (minutos 15–22 del video).
  - La trazabilidad es un log crudo.
  - La tarjeta de faltante y el modal “Motivo del bloqueo” son básicos.
  - El operario usa una vista oscura con letra pequeña.

## Diseño objetivo
1. **Tablero (jefe de producción):** columnas por estación (Corte, Mecanizado, Soldadura, Limpieza, Armado, Herrajes, Vidriado, Control de calidad, Embalaje, Despacho), solo las que existen en la ruta configurada. Cada tarjeta de OT muestra código, obra/cliente, unidades, fecha comprometida, avance x/y y chips de bloqueo (faltante, QC, sin optimizar). Filtros por obra, compromiso y bloqueo. Sin capacidad inventada: si no hay datos de capacidad, no muestres capacidad.
2. **Detalle de OT:**
   - Encabezado: código, estado, compromiso, avance y acciones principales.
   - Pestañas: Resumen · Piezas (virtualizada, agrupada por posición y unidad, con búsqueda por etiqueta de pieza `P01-U02-M03`) · Corte (plan y documentos, P13) · Mecanizado (P14) · Vidrios · Herrajes · Calidad · Embalaje · Trazabilidad.
   - Los **pasos** son una línea compacta (stepper horizontal con estado), no 9 tarjetas. El detalle del paso se abre en un panel.
3. **Trazabilidad humana:** “14:32 · Juan Pérez · Corte de perfiles completado (24 piezas)”, con filtros, y el log crudo solo en “Detalles técnicos”.
4. **Vista de operario** (rol OPERATOR, densidad `workshop` de P01, tablet de 1024×768, oscuro por defecto):
   - Solo la cola de su estación.
   - Una tarjeta grande “Siguiente” con qué hacer y la lista de piezas del paso, con checkbox o escaneo de QR (si hay cámara; si no, input).
   - Botones Completar · Bloquear (motivos predefinidos + otro) · Nota, de 44 px o más.
   - Sin precios, clientes ni márgenes.
   - Texto en lenguaje de taller.
5. **Bloqueos y faltantes:** tarjeta con qué falta (SKU humano, cantidad y color), por qué bloquea y la acción (ir a Compras con la necesidad precargada o usar un retazo compatible si P15 lo ofrece).
6. **Sin enums visibles:** todo pasa por `domainLabels` (P01).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Jefe de taller (planta de un vistazo) y operario (tablet, guantes, 2 m). Deben sentir: “sé qué hacer ahora”.
- **Anatomía:** Constitución §5.10 y densidad `workshop` (oscuro, base 16 px, objetivos ≥ 44 px, idealmente 56). Tablero por estación; OT de 100 posiciones agrupada, no en muros de tablas.
- **Momento de firma (preservar o crear):** F9 (una pieza, una pantalla: código ≥ 32 px en Mono, qué hacer, medida, destino, siguiente) y F7 (naranja = requiere persona).
- **Idea que sube el techo (obligatoria, con el motor):** Escanear la etiqueta es la entrada principal: la estación muestra la pieza, la acción y lo que sigue; QC FAIL crea el remake con un toque y avisa al jefe.
- **Slop a eliminar aquí:** Tablas densas de oficina en la tablet, enums, datos comerciales en la vista del operario, 9 tarjetas de pasos, gestos ocultos.
- **Preguntas del pase editorial:** ¿Un operario con guantes completa su estación sin leer párrafos? ¿El jefe ve el cuello de botella en 5 segundos?

## Criterios de aceptación
- La OT del proyecto de 100 posiciones (fixture) es interactiva en menos de 2 s en local (mide y reporta), y no hay más de 2 pantallas de scroll antes de las pestañas.
- e2e del operario en 1024×768 oscuro: ve solo su estación → completa un paso → bloquea con motivo → el jefe ve el bloqueo en el tablero y en “Hoy”.
- `ux:capture`: 0 enums y 0 objetivos táctiles bajo 44 px en las rutas de operario.
- Tests de etiquetas y de virtualización (renderiza menos de 100 filas DOM con 2.000 piezas).
- Capturas: tablero, detalle y operario.
