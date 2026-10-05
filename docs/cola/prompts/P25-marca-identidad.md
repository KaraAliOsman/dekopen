# P25 — Marca e identidad: la sección de perfil como firma, del favicon al correo

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

**Depende de:** P01 (tokens, Plex, íconos). Ola 1, en paralelo con el resto. Adjunta: `CONSTITUCION-DISENO.md`, `diseno/board-02-mark-studies.png`, `diseno/dekopen-visual-identity-study.md`, `bot/*`.

## Objetivo
Que DEKOPEN tenga una identidad **extraída de su propio producto** y aplicada con disciplina en cada punto de contacto: la marca, el favicon, el ícono de la app, el login y el onboarding, los correos transaccionales, los estados vacíos, el bloqueo de documentos y la relación con el Orb. Y que la marca **se retire** donde manda la del fabricante (documentos y portal del cliente son white-label).

## Por qué
Hoy no hay una marca aplicada de forma consistente: el estudio de identidad propuso cuatro direcciones y recomendó una, pero nada se implementó. Los puntos de contacto que no son pantallas de trabajo (login, correos, favicon, estados vacíos) son justamente donde un producto parece demo o parece serio.

## Decisión de marca (constitución §11)
- **Marca principal: dirección B, “La sección”.** Anillo cuadrado (el corte de un perfil hueco extruido) con un tabique interno a 1/3 del ancho; exterior 24 × 24, radio r-1, pared 2,5, tabique 2. La sección **reemplaza la O** del logotipo: `DEK⧈PEN`. Logotipo en Plex Sans SemiBold, mayúsculas, tracking +0,06 em, g-950 (g-25 sobre oscuro). Nunca degradado, contorno ni efectos.
- **Bloqueo de documento: dirección D, “La cota”** (el logotipo enmarcado por una línea de cota con ticks a 45°), solo para la portada interna, la página “Acerca de” y los correos.
- **La gramática de aperturas (dirección C)** queda para los íconos, no para la marca.
- **Asistente:** “Asistente DEKOPEN” con el Orb (spec `bot/dekopen-orb-spec.md`). No se usa “STARWIN”. Verifica que el Orb actual (`Orb.tsx`, `BotFigure.tsx`) es coherente con la paleta y la forma de la marca (grafito, teal, una órbita); si no, ajústalo sin cambiar su API.

## Alcance
1. **Archivos de marca** en `frontend/src/brand/` como SVG optimizados y componentes React (`<BrandMark size>`, `<Wordmark>`, `<DocLockup>`), con construcción geométrica documentada en `docs/design/marca.md` (grilla, proporciones, zona de protección, tamaños mínimos: marca 16 px, logotipo 72 px) y usos prohibidos con ejemplos.
2. **Favicon y ícono de la app:** SVG + PNG 16/32/180/192/512 + `manifest.webmanifest` (nombre, colores de tema teal-800 y g-50). Variantes para tema claro y oscuro.
3. **Login, magic link y onboarding:** pantalla de entrada como **hoja técnica** (superficie paper con inglete sobre la mesa g-50, marca, una sola acción) en densidad `office`, perfecta a 390 px. El onboarding sigue la constitución: preguntas mínimas, cada paso con su porqué, progreso como `Stepper`, y termina en la primera posición dibujada (no en un dashboard vacío).
4. **Correos transaccionales** (magic link, cotización enviada al cliente, aprobación recibida, pago registrado, OT bloqueada): plantillas HTML compatibles con clientes de correo, white-label cuando el destinatario es el cliente final (marca y colores de la organización del fabricante; DEKOPEN no aparece), y con la marca DEKOPEN solo en los correos internos. Texto en español con la voz del §4 (usted hacia el cliente). Vista previa en `/dev/correos`. El envío real con dominio propio es integración diferida: deja el adaptador y la sección en `ACTIVACION.md`.
5. **Estados vacíos con lenguaje de dibujo:** en vez de ilustraciones genéricas, una pequeña **lámina** con el dibujo técnico de lo que falta (una elevación vacía con cotas fantasma para “sin posiciones”, una barra sin cortes para “sin plan de corte”), trazada con los tokens del lienzo. Componente `EmptyIllustration kind` reutilizable por `EmptyState`.
6. **Página 404/500 y “sin conexión”:** con la misma lámina y una acción.
7. **White-label en los entregables del cliente:** DOC-01, portal y correos al cliente usan la marca de la organización (logo, color primario validado por contraste AA contra paper; si no pasa, se usa teal-800 y se avisa en Ajustes). “Generado con DEKOPEN” oculto por defecto en documentos, discreto en el portal (constitución §11).

## Momento de firma de este encargo
F10: la sección de perfil en la O. Debe verse impecable a 16 px y a 160 px, impresa en una etiqueta de taller y en el favicon de una pestaña. Si a 16 px se pierde el tabique, ajusta la geometría óptica y documenta el ajuste.

## Fuera de alcance
Rediseñar superficies de trabajo (las hacen los demás encargos) y cambiar la API del Orb.

## Criterios de aceptación
- La marca pasa la prueba de tamaño (16, 24, 32, 72, 160 px) en claro y oscuro (capturas en `docs/redesign/captures/marca/`).
- Favicon y manifest correctos en el build de producción (test).
- Login, onboarding, 404/500 y los 5 correos con capturas a 1440 y 390, rúbrica R1–R20 en PASA.
- Test de white-label: un correo y un DOC-01 al cliente no contienen la palabra “DEKOPEN” ni su marca cuando el pie está oculto.
- Test de contraste del color de marca de la organización con fallback a teal-800.
- `docs/design/marca.md` commiteado con construcción y usos prohibidos.
