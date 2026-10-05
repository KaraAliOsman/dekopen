# P09 — DOC-01 Propuesta comercial v2: un documento que un fabricante firmaría con orgullo

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

**Depende de:** P02 (formato e identificadores). Mejor si P05 ya está mergeado (símbolos y vista declarada). Coordina rebase con P05 y P13 (`backend/documents/renderers.py`).

## Objetivo
Rehacer el layout y el contenido del DOC-01 para que sea un documento comercial de nivel profesional, white-label, legible a 1, 12, 24 y 100 posiciones, sin colisiones ni páginas vacías, y con la estructura por posición que usan los mejores del sector.

## Situación actual
- Render en `backend/documents/renderers.py` (y templates asociados); fixtures en `backend/scripts/render_doc_fixtures.py`.
- (auditoría, PDF del archivo) Hay **colisiones de columnas** en la tabla: “1200.00 × 1200” se monta sobre el vidrio y “$ 293.38$ 293.385” mezcla precio unitario y neto. Hay **una página en blanco** (“Vistas de los productos”) en el documento de 24 posiciones, medidas con `.00`, la flecha de la corredera mal en la portada de builds antiguos y el tamaño Carta. El documento de 100 posiciones tiene 31 páginas.
- Lo bueno, que se conserva: bloque emisor; “Preparado para” (RUT, giro, comuna, dirección, contacto, entrega); tabla “Solución propuesta”; resumen comercial; condiciones; aceptación con firmas.

## Referencia de estructura (adjunto `fenster-musterangebot.pdf` y las capturas de Orgadata y Logikal)
Cada posición se presenta como un bloque con:
- nombre del recinto (“01 Living”);
- **vista declarada** (“Vista interior”);
- dibujo con cota total y cotas por campo;
- lista por campo (“Campo 1.1: Oscilobatiente, bisagras a la izquierda”);
- descripción del sistema (serie, color interior y exterior);
- vidrio con composición (4/16/4) y U **solo si es dato autoritativo**;
- accesorios como sublíneas *cantidad × precio unitario = total*;
- subtotal de la posición.

Las posiciones alternativas van marcadas como “no incluidas en el total”, y cada página lleva el folio, la revisión y el número de página.

## Estructura objetivo
1. **Portada:** logo, razón social, RUT, giro, dirección y contacto del emisor. “Preparado para”: cliente, RUT, obra, dirección y contacto. Folio `COT-P-000123-REV-B`, fecha y **vigencia**. Total destacado con su moneda. Resumen de condiciones (pago, plazo, instalación). Imagen de la posición más representativa, con el renderer real y la vista declarada.
2. **Resumen de posiciones:** tabla compacta (Pos., Ubicación, Tipología, Ancho × Alto, Cant., P. unit. neto, Total neto) con **anchos de columna fijos y ajuste de línea**, que nunca se superponen; cifras tabulares; repetición del encabezado en cada página.
3. **Detalle por posición:** de 1 a 3 posiciones por página según su alto, con el bloque de referencia descrito arriba, la leyenda de simbología y la planta si es un conjunto o bow (P06). En los documentos de cliente **no se muestran valores técnicos desconocidos**: se omite la línea, sin “Sin dato”.
4. **Resumen comercial:** neto, descuento, neto con descuento, IVA 19 % y total; tabla del calendario de pagos con montos; plazos; instalación; exclusiones; garantía; vigencia y jurisdicción.
5. **Aceptación:** nombre, RUT, fecha y firma, más “Acepta en línea” con QR y enlace al portal de la misma revisión.
6. **Pie de cada página:** folio · revisión · página n/N · datos legales del emisor y, en tamaño pequeño, la huella abreviada.
7. **Ajuste de la organización:** papel Carta u Oficio o A4 (por defecto, el actual), logo, color de acento (dentro de la paleta permitida) y textos legales. **Nunca** se muestran costo, margen, UUID ni hash en el cuerpo.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El cliente final que recibe el PDF y el dueño que lo firma. Debe sentir: “esta empresa es seria”.
- **Anatomía:** Constitución §5.8: lámina técnica white-label, filete teal-800, inglete, cajetín ISO 7200 con huella, ficha por posición (elevación con vista declarada + tabla de especificación), totales con un único momento fuerte, Carta, Plex embebida.
- **Momento de firma (preservar o crear):** F1, F2 y F11: el documento está cortado como el marco que cotiza y lleva su huella como un número de plano.
- **Idea que sube el techo (obligatoria, con el motor):** El mismo documento se lee bien con 1, 12 o 100 posiciones (ficha completa, ficha compacta o tabla con miniaturas, elegido automáticamente por densidad) y cada vidrio muestra composición y Ug cuando existen.
- **Slop a eliminar aquí:** Azul marino genérico y Arial, cebra en tablas, columnas que colisionan, páginas en blanco, `.00`, logos de DEKOPEN sobre la marca del cliente.
- **Preguntas del pase editorial:** ¿Lo firmaría con orgullo el dueño de Schüco? ¿Se puede cortar contra cada medida impresa?

## Criterios de aceptación
- Tests de render con 1, 12, 24 y 100 posiciones (fixtures). Usa PyMuPDF si está en las dependencias de test; si no, agrégalo como dependencia de test fijada.
  - **Sin superposición** de cajas de texto dentro de las tablas (test de intersección de bbox).
  - Ninguna página tiene solo pie.
  - El total del documento es igual al total del motor.
  - Moneda correcta en una cotización en USD.
  - Sin hex de 10 o más caracteres fuera del pie.
- 100 posiciones en ≤ 45 páginas; nombres de cliente y ubicación de 120 caracteres hacen wrap sin romper el layout (test).
- Snapshots raster commiteados (portada, resumen y una página de detalle) para 12 posiciones, en `docs/redesign/captures/doc01-v2/`.
- La simbología del documento coincide con el editor (si P05 está mergeado, usa sus fixtures de paridad).
