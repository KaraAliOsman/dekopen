# P05 — Fidelidad del dibujo técnico 2D: símbolos, vista declarada, correderas por modelo, cotas y formas especiales

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

**Depende de:** P01 y D03 (modelo de apertura; si D03 no está mergeado, cubre el enum actual y deja los fixtures listos para extender). Puede correr en paralelo con P04 (P05 es dueño de la geometría de glifos y cotas; P04, del layout). Coordina rebase con P09 y P13, que también tocan `backend/documents/renderers.py`, aunque en otras funciones.

## Objetivo
Que cualquier fabricante que mire un dibujo de DEKOPEN, en el editor, el PDF o el portal, lo lea sin ambigüedad: qué lado bisagra, hacia dónde abre, desde qué lado se mira, qué hoja de la corredera se mueve y hacia dónde, y cuáles son las medidas. **Un solo contrato de simbología, el mismo en todas las superficies.**

## Situación actual (verificada en main `b3d1c9b`)
- La simbología está **duplicada**: frontend en `frontend/src/features/canvas/ProductFrontSvg.tsx` (y `openings.ts`, `presentationGeometry.ts`) y backend en `backend/documents/renderers.py` (~líneas 600–760).
- Abatible y oscilobatiente siguen la convención DIN: vértice hacia la manilla y abatimiento desde las esquinas inferiores al centro superior. **Esto está bien y se mantiene.**
- **No hay vista declarada** (interior/exterior) en las elevaciones, y **no hay distinción continua/discontinua**: el proyectante (`AWNING`), que abre hacia afuera, se dibuja con línea continua igual que las aperturas hacia adentro. Con vista interior, el proyectante debe ir **discontinuo**.
- La dirección de las correderas es **una convención de presentación**: “las hojas de la mitad izquierda corren a la derecha y las de la derecha a la izquierda” (`ProductFrontSvg.tsx:706–719` y `renderers.py:684–695`). Los comentarios lo dicen: “the product model declares no travel”. `SlidingLayout`/`SlidingPanel` (`engine/src/dekopen_engine/models.py:66–93`) tienen `kind` (MOVING/FIXED) y `track`, pero ni dirección de recorrido ni cuál carril es exterior o interior. En 3 hojas, la del centro queda arbitraria. (auditoría) En builds antiguos la corredera de 2 hojas mostraba → → en el editor y en la portada del DOC-01.
- Las puertas se dibujan en elevación con un arco de giro discontinuo. Los arcos de giro pertenecen a la **planta**; en elevación usa el triángulo DIN como en las ventanas y deja el arco solo para la vista en planta.
- (auditoría, sesiones 9e41dc53 y 83488a85) El **arco se renderizaba como trapecio**, el **trapecio dejaba el lienzo en blanco** y las formas especiales salían como polígonos rellenos oscuros en la vista técnica.

## Alcance
1. **Contrato de simbología** en `docs/PRD/opening-symbols.md`, con una ilustración por caso: fijo (“F” o sin símbolo, según la convención actual), abatible izquierda/derecha, oscilobatiente izquierda/derecha, proyectante, corredera 2, 3 y 4 hojas, O/X/X/O, puerta simple izquierda/derecha y puerta doble. Para cada uno, en vista interior y exterior. En vista exterior se espeja izquierda/derecha y se invierte continuo/discontinuo. Reglas de grosor, color y escala de los glifos.
2. **Modelo:** agrega a `SlidingPanel` un `travel: "LEFT" | "RIGHT" | None` (None solo para FIXED). Agrega a la documentación del modelo la semántica de `track` (qué índice es el carril más exterior). Si el catálogo o el perfil del sistema ya declaran el orden de carriles, úsalo; si no, documenta la convención elegida y que no es autoridad del fabricante.
   - Compatibilidad hacia atrás: los productos guardados sin `travel` se cargan con la convención actual y se marcan como “dirección inferida”; al editar, el usuario puede cambiarla en el inspector (P04 consume esto) y se persiste.
   - Validaciones en el motor: una hoja no puede recorrer hacia una jamba sin espacio; dos hojas móviles adyacentes no comparten carril (ya existe, mantenlo).
   - Golden tests.
3. **Fuente única de glifos:** crea fixtures JSON compartidos (`engine/tests/fixtures/symbols/*.json` o una ubicación equivalente accesible a los tests de Python y de TS). Cada uno tiene el producto de entrada y las primitivas esperadas en mm (líneas, discontinuo sí/no, flechas y punto de manilla), y tanto el renderer TS como el Python se testean contra esos mismos fixtures. Un test de **paridad** falla si divergen.
4. **Vista declarada** en cada elevación: leyenda “Vista interior” o “Vista exterior” en el editor, el PDF y el portal; selector en el editor (P04 pone el control y P05 implementa el render). Agrega un bloque “Simbología” plegable en el editor y como leyenda breve en los PDF técnicos.
5. **Cotas** en la vista Técnica:
   - cadena exterior total (ancho y alto);
   - cadena interior por bahía (montantes y travesaños, a ejes);
   - marca de altura de manilla en hojas practicables, desde el dato del modelo;
   - las cotas no se superponen con los glifos (algoritmo de desplazamiento por niveles);
   - números con `tabular-nums` y en mm enteros.
   - Referencia: Moxisys (adjuntos m2, m3 y m4), con cadenas de cotas y un input editable en el lugar (ese input lo pone P04).
6. **Formas especiales:** el arco de medio punto, el arco rebajado, el trapecio y el triángulo se renderizan correctamente en el lienzo, en el render técnico y en el PDF, a partir de `contourGeometry.ts` y `engine/.../contour.py`, sin rellenos oscuros: marco, hoja y vidrio con los mismos estilos que una rectangular. Agrega fixtures con cada forma.
7. **Corredera en planta:** debajo de la elevación técnica, una franja de corte horizontal con la indicación EXTERIOR/INTERIOR, los carriles numerados y la posición de cada hoja (referencia: Moxisys m2). Solo si el modelo tiene los datos; si no, no la dibujes.

## Fuera de alcance
3D (P19), layout del editor (P04) y bow en planta (P06).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Cualquier fabricante, instalador o cliente que mira un dibujo. Debe sentir: “se lee sin ambigüedad”.
- **Anatomía:** Constitución §3.1 (roles del lienzo) y §3.6 (gramática de aperturas). Un solo componente de simbología (`OpeningGlyph` de P01) para lienzo, PDF, portal, etiqueta y 3D.
- **Momento de firma (preservar o crear):** F5 (planta con carriles para correderas) y la vista declarada como sello en cada elevación (“Vista interior”).
- **Idea que sube el techo (obligatoria, con el motor):** Alternar vista interior/exterior en un clic invierte correctamente la simbología (continuo ↔ discontinuo, lado de bisagra espejado) y es imposible dibujar una combinación que el modelo no permite.
- **Slop a eliminar aquí:** Flechas de corredera por convención de índice, símbolos centrados que parecen “play”, grosores mezclados, cotas proporcionales, arcos dibujados como trapecios.
- **Preguntas del pase editorial:** ¿Un instalador sabe hacia dónde abre cada hoja sin leer texto? ¿El PDF y el editor son pixel a pixel la misma gramática?

## Criterios de aceptación
- Tests de paridad TS ↔ Python en verde para los 13 casos base y para cada tipología que D03 o D08 hayan agregado, en vista interior y exterior.
- Corredera de 2 hojas → flechas opuestas hacia el encuentro; O/X/X/O → las dos centrales hacia afuera o hacia adentro según `travel`; 3 hojas → dirección explícita.
- Proyectante en vista interior → discontinuo; puerta en elevación → triángulo, sin arco.
- Arco y trapecio dibujados correctamente en el lienzo y en el PDF (capturas y snapshot SVG).
- Productos antiguos sin `travel` cargan sin error y se marcan como “dirección inferida” (test de migración o compatibilidad).
- Capturas de la tabla completa de símbolos (`/dev/ui` o una página de pruebas DEV) commiteadas.
