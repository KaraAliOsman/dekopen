# ORQ — Orquestador del programa DEKOPEN v1: ejecuta la cola completa de punta a punta

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

**Para qué:** el dueño quiere que la IA haga absolutamente todo y le entregue el producto 100 % listo para revisar. Este prompt te convierte en **líder técnico del programa**: ejecutas los 39 encargos de la cola en el orden correcto, controlas la calidad entre olas y terminas con un único PR hacia `main` que el dueño revisa. Trabajas con **Codex local**: la cola completa ya está copiada en **`docs/cola/`** del clon (`prompts/`, `cuerpos/`, `CONSTITUCION-DISENO.md`, `00-LEEME.md` y `adjuntos/`).

## 0. Dos formas de correr este programa
- **Con el script `ejecutar-cola.ps1` (lo normal).** El script lanza **una sesión de Codex nueva por encargo**, en el orden del §2, y te indica al inicio cuál es tu encargo (`ENCARGO ACTUAL: <ID>`). En ese caso **haces solo ese encargo**, de punta a punta, siguiendo el §3 y el §4, y terminas. El script lee `docs/cola/ESTADO.md` para saber si puede pasar al siguiente: deja tu fila en `mergeado` (o `bloqueado`, con la causa) antes de terminar.
- **Pegado directo en una sesión interactiva de Codex.** Entonces ejecutas tú la cola entera en serie, en el orden del §2, releyendo cada prompt completo antes de empezarlo.

## 1. Preparación (solo la primera vez, antes de P00)
1. Lee `docs/cola/00-LEEME.md`, `docs/cola/CONSTITUCION-DISENO.md` y `docs/cola/cuerpos/_contrato.md` completos antes de hacer nada.
2. Ejecuta **P00** tal como está escrito (crea `integracion/v1`, commitea la constitución y los registros).
3. En el mismo PR de P00 commitea la cola bajo **`docs/cola/`** tal como está (~21 MB con `adjuntos/`). **No commitees ningún `.env` ni secretos** (`docs/cola/` no contiene ninguno; verifícalo antes de commitear). Así cada sesión siguiente relee su encargo y sus adjuntos desde el repo.
4. Crea **`docs/cola/ESTADO.md`**: una tabla con una fila por encargo, con este formato exacto de columnas: `| ID | Ola | Estado | PR | SHA | Notas |`, y `Estado` ∈ `pendiente` / `en curso` / `mergeado` / `bloqueado`. Actualízala al empezar y al terminar cada encargo (commit directo a `integracion/v1` con mensaje `cola: estado <ID>`). Es la memoria del programa.

## 2. Orden de ejecución
| Ola | Encargos | Puerta de salida |
|---|---|---|
| 0 | **P00** | `integracion/v1` existe; constitución, `docs/cola/` y `ESTADO.md` en el repo |
| 0b | P01 · IA1 · D01 | Tokens y guardas activos; línea base de la IA medida; sistemas, ingesta y catálogo demo |
| D1 | D02 · D03 · D04 | Vidrio, aperturas y herrajes estructurados en el motor |
| D2 | D05 · D06 · D07 · IA2 · IA3 | Dominio completo; IA con operaciones tipadas y proveedor real |
| 1 | P02 · P03 · P04 · P05 · P07 · P09 · P12 · P17 · P25 | Superficies núcleo rediseñadas |
| **ED1** | Pase editorial de la ola 1 | Rúbrica en PASA en todo lo construido |
| 2 | P06 · P08 · P11 · P13 · P14 · P15 · P16 | Flujos comerciales y de planta completos |
| **ED2** | Pase editorial de la ola 2 | Rúbrica en PASA, coherencia con ED1 |
| 3 | D08 · P10 · P18 · P19 · P21 · P22 · P23 | Superficies restantes |
| 4 | P24 | Analítica sobre datos reales del flujo |
| 5 | **P20** | Aceptación final y PR `integracion/v1` → `main` |

Se ejecutan **en serie**, en este orden exacto (respeta los archivos con riesgo de conflicto del §4 del LEEME): P00, P01, IA1, D01, D02, D03, D04, D05, D06, D07, IA2, IA3, P02, P25, P04, P05, P09, P07, P03, P12, P17, ED1, P06, P08, P13, P15, P11, P14, P16, ED2, P21, P10, P22, P23, D08, P19, P18, P24, P20. **Un encargo empieza solo cuando el anterior está mergeado en `integracion/v1` con CI en verde** (o `bloqueado` con su causa).

## 3. Cómo ejecutar cada encargo
1. `git fetch` y actualiza `integracion/v1`. Marca la fila `en curso` en `ESTADO.md`.
2. **Lee completos** `docs/cola/prompts/<ID>.md` (trae el contrato) y la constitución. No trabajes de memoria ni con resúmenes.
3. Crea la rama `codex/<ID>-<slug>` desde `integracion/v1`. Cumple el encargo **entero**: código, migraciones, tests, OpenAPI y orval si cambia la API, wiki.
4. Levanta el stack local (skill `testing-framedex`; carga el `.env` de la raíz en el entorno del proceso) y verifica el flujo con Playwright en los tamaños y temas del contrato. Guarda las capturas.
5. Haz el pase editorial (constitución §9) y deja la rúbrica R1–R20 en el PR.
6. `gh pr create --base integracion/v1`. Espera los 4 checks (`gh pr checks --watch`); si algo falla, corrígelo en la misma rama hasta que estén en verde. No debilites ningún check.
7. `gh pr merge --squash --delete-branch`. Registra PR y SHA en `ESTADO.md`, fila en `mergeado`.

Un encargo, una rama, un PR. Nunca mezcles dos encargos en un PR.

## 4. Reglas del orquestador
- **Calidad antes que velocidad.** No acortes ningún encargo para avanzar más rápido. Si un encargo deja algo a medias, no lo marques `mergeado`: termínalo.
- **Coherencia del programa.** Antes de cada encargo, relee las decisiones registradas en `docs/wiki/log.md` y `docs/decisions/valores-por-defecto.md`; respétalas.
- **Conflictos:** rebasea sobre `integracion/v1` antes de abrir y antes de mergear el PR.
- **Bloqueos reales** (contrato, “Detente solo si”): marca `bloqueado` en `ESTADO.md` con la causa, haz todo lo que no dependa del bloqueo y deja el resto aislado. Las integraciones diferidas (Railway, Flow, SII, correo) **no son bloqueos**.
- **Nunca** mergees a `main`, nunca imprimas ni commitees secretos (el `.env` jamás entra a git), nunca debilites un check de CI, nunca hagas `push --force` sobre `integracion/v1` ni `main`.
- **Informe de avance:** al cerrar cada ola, agrega a `ESTADO.md` un resumen de 5 líneas (qué quedó, capturas clave, riesgos).

## 5. Entrega
El programa termina cuando P20 abre el PR `integracion/v1` → `main` con los 4 checks en verde, `docs/GUIA-REVISION.md` probada y `ESTADO.md` con todos los encargos en `mergeado`. Último mensaje (de P20, o tuyo si corres la cola entera): enlace al PR final, la tabla de `ESTADO.md`, el informe de aceptación y la lista de lo que el dueño debe conectar (de `ACTIVACION.md`).

## Criterios de aceptación
- Los 39 encargos en `mergeado` en `ESTADO.md`, cada uno con su PR y su SHA (o `bloqueado` con causa y lo que se hizo alrededor).
- ED1, ED2 y el pase editorial de P20 documentados con su rúbrica en PASA.
- PR final hacia `main` abierto y sin mergear.
