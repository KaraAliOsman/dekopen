# D01 — Sistemas y perfiles de verdad: familias separadas, roles completos, reglas de corte y refuerzo, límites e importador de catálogo

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

**Depende de:** nada; puede correr en la ola 0. Coordina con P16 (UI de catálogo) y con IA2/IA3 (la ingesta por IA usa el proveedor real y sus artefactos `catalog candidates`/`catalog review`).

## Problema
DEKOPEN hoy calcula sobre un catálogo de juguete, y por eso todo “funciona a medias”: cualquier cotización, BOM o corte solo es tan real como el catálogo que hay detrás.

## Hechos verificados en main `b3d1c9b`
- `supabase/seed.sql`: hay **3 sistemas, todos sintéticos**: `DEMO_60` (“Sistema Demo 60mm PVC — referencia sintética”), `ALU_65` y `GLASS_45`. DEMO_60 tiene perfiles MARCO, HOJA, POSTE-V, POSTE-H, JQ-10/14/24 y UMBRAL-ALU, acabados `["WHITE","FOILED"]` y un kit por tipo de apertura.
- `engine/src/dekopen_engine/models.py`: `SystemParams` mezcla en **un mismo sistema** parámetros de practicable (traslape de hoja, holgura de vidrio) y de corredera (`central_overlap_mm`, `pulley_height_mm`, `sliding_glazing_deduction_*`). En la vida real, la corredera es **otra serie con otros perfiles**.
- `ProfileRole` tiene solo 10 roles (FRAME, SASH, MULLION_V, MULLION_H, INVERSOR, GLAZING_BEAD, COUPLER, ADDITIONAL, THRESHOLD, CHANNEL). `MaterialType` solo admite PVC y ALUMINIUM. Los acabados son strings libres.

## Alcance
1. **Familia de sistema** (`system_family`): `CASEMENT` (practicable y oscilobatiente), `SLIDING` (corredera), `LIFT_SLIDE` (elevable), `DOOR` (puerta de entrada) y `FACADE_FIXED` (fijos de gran formato), con las tipologías que cada familia admite.
   - El motor **rechaza** una tipología incompatible con la familia; por ejemplo, una corredera en un sistema practicable, con un mensaje en español que propone sistemas compatibles del catálogo.
   - Separa los parámetros por familia: los parámetros de corredera viven solo en sistemas `SLIDING`.
   - Migración: divide `DEMO_60` en `DEMO_60` (practicable) y `DEMO_CORREDERA_60` (corredera), ambos sintéticos, y migra los productos guardados (las posiciones de corredera pasan al sistema corredera) con un test de migración.
2. **Roles de perfil completos, solo los que el motor necesita para calcular:**
   - hoja de corredera (`SLIDING_SASH`), encuentro o traslapo de corredera (`INTERLOCK`) y riel o guía si el marco corredera lo separa;
   - hoja de puerta (`DOOR_SASH`);
   - ensanche o ampliación de marco (`FRAME_EXTENSION`), vierteaguas o alféizar (`SILL`) y tapajuntas (`COVER_TRIM`), estos tres conectados con D06;
   - zócalo, si aplica.
   - Para cada rol: **regla de corte** (ángulo 45/90, pérdida de soldadura por extremo, descuento por encuentro), su perfil de refuerzo compatible y el redondeo de corte.
3. **Reglas de refuerzo** como datos y no como código: por perfil, color (foliado u oscuro → obligatorio) y largo mínimo; tipo de refuerzo; descuento de corte; tornillos por metro (BOM). Golden tests con casos: blanco de 900 mm sin refuerzo vs. foliado de 900 mm con refuerzo, según una regla de fixture.
4. **Límites dimensionales** por sistema × tipología: ancho y alto de hoja mínimo y máximo, peso máximo y relación de aspecto. El motor los usa para validar; el editor (P04) y la cotización (P08) los muestran con su fuente.
5. **Ingesta de catálogo por dos vías** (decisión del dueño: “se puede ingresar en cualquier formato y la IA lo analiza e integra; también manual”):
   - **Manual estructurado:** importador XLSX/CSV con una **plantilla oficial descargable** desde Catálogo. Hojas: Sistemas, Perfiles, Roles y reglas de corte, Refuerzos, Límites, Colores y SKU por color (D05), Vidrios (D02), Herrajes (D04) y Precios de costo. Validación fila por fila con errores en español (“Fila 14, columna ‘Pérdida de soldadura’: debe ser un número en mm”).
   - **Por IA, cualquier formato:** el usuario sube lo que tenga — ficha técnica en PDF, planilla del proveedor, foto o escaneo de una tabla, correo con precios, texto pegado — y la IA extrae los datos estructurados (OCR + análisis → candidatos tipados). Reutiliza la maquinaria existente de `catalog imports` y los artefactos `catalog candidates`/`catalog review` del `ai_gateway`; extiéndela a los tipos nuevos de este encargo (sistemas, roles, reglas de corte, límites). Si el proveedor configurado no acepta imágenes/PDF (ver IA3), la ingesta cubre texto/planillas con extracción y declara la limitación de escaneos.
   - **Ambas vías convergen en la misma revisión:** vista previa como diff contra lo existente, campos con confianza baja marcados para revisión humana, y **nada se publica sin el clic de un revisor**. Lo que la IA no puede extraer con certeza queda UNKNOWN, nunca con un valor por defecto ni inventado. Publicación con procedencia (archivo de origen, método — manual o IA — y revisor), usando las reglas de P16.
6. **Catálogo demo de arranque con precios aleatorios** (decisión del dueño: “primeramente iniciaremos con un catálogo demo con precios random”): fixtures sintéticos más ricos que hoy — PVC practicable 60 y 70 mm, PVC corredera, aluminio corredera y aluminio practicable — con valores y precios plausibles generados aleatoriamente (semilla fija, reproducible). **Todo con `is_demo = TRUE`**, la insignia “DEMO” visible en catálogo, editor, precios y documentos, y nunca presentado como certificado. Los datos reales los carga el dueño por cualquiera de las dos vías de ingesta.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño o técnico que carga el catálogo. Debe sentir: “subo lo que tengo y queda bien integrado”.
- **Anatomía:** Pantalla de ingesta con dos vías (plantilla y cualquier archivo) que convergen en la misma revisión con diff; DEMO marcado en todas partes.
- **Momento de firma (preservar o crear):** La revisión de la IA muestra la fuente (recorte del PDF o celda de la planilla) junto a cada valor extraído.
- **Idea que sube el techo (obligatoria, con el motor):** Arrastrar un PDF de ficha técnica del proveedor produce, en minutos, el sistema completo listo para revisar, con lo dudoso marcado como UNKNOWN.
- **Slop a eliminar aquí:** Un input de archivo sin explicación, errores en inglés, importaciones que publican sin revisión.
- **Preguntas del pase editorial:** ¿Se puede publicar algo que nadie revisó? ¿Cada error de fila dice exactamente qué corregir?

## Criterios de aceptación
- Golden tests de corte por rol (marco, hoja, montante y junquillo) en los dos sistemas practicables, y de corredera en el sistema corredera.
- El motor rechaza una corredera en un sistema practicable (test).
- Ida y vuelta del importador manual: la plantilla de fixture se importa y exporta igual; los errores por fila se testean; la publicación queda con procedencia.
- Ingesta por IA: con el proveedor real (o simulado con respuestas guionadas si no hay credencial), un PDF/planilla de fixture produce candidatos tipados; el test verifica que nada se publica sin revisión, que la confianza baja queda UNKNOWN y que un dato extraído mal no contamina el catálogo.
- Migración de los productos existentes, con test en `make test-db`.
- Capturas: importador con errores y con diff; pantalla de revisión de la ingesta por IA; insignia DEMO en catálogo y precios.
