# P20 — Aceptación final de punta a punta, pase editorial del producto completo y entrega al dueño

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

**Depende de:** todos los encargos anteriores mergeados en `integracion/v1`. Va al final, solo. Adjunta: `CONSTITUCION-DISENO.md`.

## Objetivo
Demostrar con evidencia que DEKOPEN está **100 % listo para que el dueño lo revise**: cada flujo funciona de punta a punta con datos realistas, los números son confiables, la presentación es la de la constitución en todas las superficies y no queda nada de demo salvo el catálogo marcado DEMO. Luego, abrir **el único PR hacia `main`** con una guía de revisión que permita al dueño comprobarlo todo por su cuenta.

**Este encargo corrige todo lo que encuentre.** Lo pequeño se corrige en este PR; si una corrección supera ~300 líneas, ábrela como PR propio hacia `integracion/v1` dentro de esta misma sesión, mergéala al pasar CI y vuelve a correr los recorridos afectados. Nada se “reporta para después” si se puede arreglar.

## 1. Recorridos (fixture de P00, usuarios reales por rol, navegador real, 1440 y 390 donde aplique)
1. Cuenta nueva → onboarding → primer proyecto → primera posición → precio → emisión.
2. Proyecto de 12 posiciones (incluye bow y acoplado) → precio con aprobación de margen → emisión REV-A → portal → cambios solicitados → cambio global → REV-B → aprobación → anticipo (Flow en sandbox o simulado, declarado).
3. Revisión nueva con documentos inmutables y comparación REV-A ↔ REV-B.
4. Compra → recepción parcial con dañado → cancelación y recompra → stock y retazos.
5. Liberación → tablero → operario en tablet (corte, mecanizado, …, QC FAIL → remake → QC PASS) → embalaje con etiquetas → despacho.
6. CNC: una máquina compatible (PASS o WARN) y una incompatible (BLOCK con causa); operaciones declaradas no emitidas visibles.
7. IA en el editor: propuesta → vista previa → aplicar → deshacer → auditoría; cancelación y reintento.
8. Roles y aislamiento: OWNER, ESTIMATOR, WORKSHOP_MANAGER, OPERATOR e INSTALLER; dos organizaciones; IDs adivinados → 404 o 403 sin filtrar existencia.
9. Cobranza: calendario → pago manual → enlace de pago (sandbox) → saldo 0.
10. Catálogo: **ingesta por IA** de una ficha PDF y de una planilla → revisión → publicación → readiness igual al gate; importación manual con plantilla.
11. Dominio: una posición de cada tipología (D03, D08) con cada familia de vidrio (D02), bicolor (D05), con extras (D06) y del vano a la fabricación (D07): cortes, BOM, herrajes y precio coherentes en el editor, el PDF, el portal, la OT y el 3D.
12. IA: suite de IA1 con el proveedor real (`AI_GATEWAY_MIMO_*`) ≥ 85 % en los casos E y J, **0** números inventados y **0** acciones consecuentes ejecutadas.
13. Terreno: medición → rectificación → revisión → producción → instalación con firma → incidencia → postventa (P23).
14. Analítica (P24): margen real vs. cotizado de una obra cerrada con la causa de la diferencia.

## 2. Pase editorial del producto completo (constitución §9)
No por pantalla: **por persona**. Recorre un día completo de cada persona del §1.2 (estimador, dueño, jefe de taller, operario, instalador y cliente final) y para cada uno:
- pasa la rúbrica R1–R20 en todas las superficies que usa, en ambos temas;
- verifica la **coherencia entre superficies**: el mismo componente, el mismo término, el mismo formato de número y la misma simbología en el editor, el PDF, el portal, la OT, la etiqueta y el 3D;
- confirma que cada superficie conserva su **momento de firma** (§7) y que su **idea del §8** funciona con el motor;
- elimina todo lo que no justifique su existencia y corrige lo que falle.

## 3. Verificaciones globales
- `ux:capture` completo (todas las rutas, roles, anchos y temas): **0 hallazgos** críticos y de slop; lista explícita de los menores que quedan, con justificación de cada uno.
- axe en todas las rutas: 0 *serious* y *critical*.
- Guardas de P01: línea base reducida respecto del inicio del programa (reporta el delta por guarda).
- Rendimiento: abrir una posición, recalcular un precio, abrir una OT de 100 posiciones y cargar el portal en móvil (4G simulada). Reporta p50/p95 y corrige lo que supere 1 s (interacción) o 3 s (carga del portal).
- Búsqueda de residuos de demo: ninguna aparición visible de “MOCK”, “Devin”, “Test Org”, “lorem”, “Próximamente”, “TODO” ni rutas DEV en el build de producción (test automatizado).
- `docs/redesign/phase14-findings-registry.md`: cada hallazgo marcado como resuelto (con evidencia), vigente o descartado (con motivo).
- `docs/decisions/valores-por-defecto.md` y `docs/operations/ACTIVACION.md` completos y coherentes con lo construido.

## 4. Entrega al dueño
1. **`docs/GUIA-REVISION.md`** (en español, para el dueño, no técnico): cómo levantar el producto localmente o en una preview, con qué usuario entrar en cada rol, y un **recorrido guiado de 30 minutos** por cada flujo con qué mirar y qué debería pasar; la lista de decisiones por defecto que puede cambiar en Ajustes; y la lista de integraciones a conectar (Railway, Flow, SII, correo) con el enlace a `ACTIVACION.md`.
2. **Informe** `docs/redesign/acceptance-<aaaa-mm-dd>.md`: tabla de recorridos (PASA / PASA con observaciones / FALLA), evidencia (capturas y artefactos), rúbrica por superficie, correcciones hechas en esta fase, problemas abiertos priorizados (solo los que de verdad no se pudieron resolver, con causa) y lo que depende del dueño.
3. Actualiza `docs/wiki/state/current-reality.md` con el mapa de capacidades verificado en tu SHA.
4. **Abre el PR `integracion/v1` → `main`** con el resumen del programa completo (encargos incluidos, PRs mergeados, capturas clave de cada superficie, guía de revisión y riesgos). **No lo mergees**: ese clic es del dueño.

## Criterios de aceptación
- Los 14 recorridos en PASA (los que dependen de una integración diferida, en PASA con el sandbox declarado).
- Rúbrica R1–R20 en PASA en todas las superficies, con la tabla en el informe.
- `ux:capture` y axe en 0 críticos; test anti-residuos de demo en verde.
- `GUIA-REVISION.md` probada siguiendo sus propios pasos desde un stack limpio.
- PR hacia `main` abierto, con los 4 checks en verde.
