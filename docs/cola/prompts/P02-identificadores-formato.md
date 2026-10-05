# P02 — Identificadores humanos y números legibles de punta a punta

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

**Depende de:** P00 (detectores) y P01 (formateadores `<Money>`, `<Dims>`, `<Qty>`, `<Percent>`, `<EntityCode>` y `domainLabels`).

## Objetivo
Que cada entidad que una persona necesita nombrar en voz alta, en una pantalla, un PDF o una etiqueta física tenga un **código humano estable**, y que **todo número visible** tenga el formato correcto según su naturaleza. Es lo que hace que un jefe de planta diga “la OC 000123 del retazo RT-000045” y no “la PO-D2CFA2D8FD52”.

## Situación actual (verificada en main `b3d1c9b`)
- `backend/purchasing/service.py:593`: `order_code = f"PO-{order_id.hex[:12].upper()}"`, es decir, las órdenes de compra se identifican con un hash.
- Los proyectos ya usan `P-000123` con una secuencia global (`supabase/migrations/20261213000000_project_code_sequence.sql`). Esa decisión fue deliberada (opacidad) y **se mantiene**.
- Recibos (`RC-0001`), guías (`GD-0001`) y facturas (`FAC-0001`) ya tienen código humano (ver `20261009000000_payment_receipts.sql`, `20261010000000_dispatch_notes.sql` y `20261011000000_project_invoices.sql`). Úsalos como patrón.
- (auditoría) Se vieron: OT `OT-P-2EE71A6B787C-REV-B-01` en builds antiguos (hoy `OT-P-000005-REV-A-03`); cantidades `24.0000`; `aprovechamiento 92.5333%`; vidrio `1310.00×1310.00`; `CLP 3462901.00` sin formato; remanentes con ID truncado; y hashes de proyecto en las tarjetas del inicio.

## Alcance
1. **Códigos por organización** para lo que hoy no tiene código humano. Usa el mismo mecanismo que recibos, guías y facturas: contador por `org_id`, seguro bajo concurrencia, nunca reutilizado e inmutable una vez asignado.
   - `OC-000123` para órdenes de compra. El prefijo “OC” es el usual en Chile; si cambiarlo rompe contratos, mantén “PO-” pero numérico y documenta la decisión.
   - `RT-000045` para retazos.
   - `REC-000012` para recepciones de compra, si no existe ya.
   - La migración rellena las filas existentes de forma determinista por `created_at`, con test en `make test-db`.
2. **Identidad de pieza única** en UI, pack de corte PDF, CSV, DXF, etiquetas y QR. El pack de corte ya usa etiquetas como `P01-U02-M03`: conviértelas en la única forma visible. El QR codifica el ID estable más la etiqueta humana. Agrega un test que genere los artefactos de una OT del fixture y compruebe que el conjunto de etiquetas es idéntico en todos.
3. **Barrido de formato** en backend (`backend/documents/renderers.py` y demás renderers) y frontend (usando los formateadores de P01). Aplica esta tabla y documéntala en `docs/ENGINEERING.md`:

   | Magnitud | Formato |
   |---|---|
   | mm | entero, salvo precisión declarada por la autoridad |
   | m, m² | 2 decimales |
   | kg | 1 decimal |
   | unidades | entero |
   | % | 1 decimal |
   | CLP | sin decimales, `$1.435.471` |
   | USD | `US$ 1.234,56` (o el formato que defina el locale; documéntalo) |
   | ángulos | entero salvo que sea fraccionario (`22,5°`) |

   Nunca se muestra un `Decimal` con ceros de cola (`1200.00`).
4. **Sin UUID ni hash visibles** en superficies de cliente y de taller. Los IDs técnicos van solo en “Detalles técnicos” mediante `<EntityCode>`. La huella de plan y documento queda **solo** en el pie de página, abreviada.

## Fuera de alcance
No cambies la numeración de proyectos ni la de cotizaciones; los folios SII de facturación dependen del CAF de SII y no se tocan. No rediseñes pantallas: solo formato e identificadores.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Todas, en especial el jefe de taller y el estimador, que nombran entidades en voz alta (“la OT 000123”) y las leen en papel y etiquetas.
- **Anatomía:** Constitución §3.3 (números y unidades) y §4 (voz). Los códigos van en Mono con `<EntityCode>`; los IDs técnicos solo en “Detalles técnicos”.
- **Momento de firma (preservar o crear):** F2 (la huella en el cajetín) se alimenta de estos códigos: el código humano y la huella aparecen juntos y siempre en el mismo lugar.
- **Idea que sube el techo (obligatoria, con el motor):** El código es una dirección: escribir `OT-000123` o `RT-000045` en la paleta de comandos lleva directo a la entidad, y escanear su QR en el taller abre la misma vista.
- **Slop a eliminar aquí:** Códigos con hash, prefijos en inglés (PO, WO), formatos distintos para la misma magnitud en pantallas distintas, `.00` sobrantes.
- **Preguntas del pase editorial:** ¿Un operario puede dictar cada código por radio sin deletrear? ¿El mismo número se ve idéntico en la pantalla, el PDF, el CSV y la etiqueta?

## Criterios de aceptación
- Test de concurrencia: dos creaciones simultáneas en la misma organización obtienen códigos consecutivos distintos; organizaciones distintas tienen contadores independientes; un rollback no deja huecos visibles (o, si los deja, está documentado y aceptado).
- Test de render de documentos: el texto extraído (PyMuPDF si está disponible en las dependencias de test; si no, verifica el HTML intermedio) no contiene hex de 10 o más caracteres fuera del pie, ni `.0000`, ni `%` con más de 1 decimal.
- `ux:capture` (P00) en las rutas de compras, inventario, producción, proyectos e inicio: **0** hallazgos de UUID/hex/decimales largos.
- Test de igualdad de etiquetas de pieza entre PDF, CSV, DXF y etiquetas para la OT de 12 posiciones del fixture.
- `make test-db` en verde con la migración y el relleno.
