# P16 — Catálogo técnico: fichas de artículo, procedencia que no se autocertifica y revisión de importación con IA

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

**Depende de:** P01 y P02.

## Objetivo
Que el catálogo sea la **autoridad visible** del producto: cada perfil, refuerzo, vidrio y herraje muestra qué es, de dónde viene su dato, quién lo revisó y si el sistema está listo para cotizar y fabricar, con la **misma regla** que usan la emisión y la liberación.

## Situación actual
- `frontend/src/features/catalogs/` (`CatalogPage.tsx`, `SectionImportPanel.tsx`); backend en `backend/catalogs` y `backend/ingest`; seed `DEMO_60` en `supabase/seed.sql`.
- (auditoría, sesión f5305cc9 “catalog-workspace” y otras)
  - Lista de sistemas a la izquierda; escalera de *readiness*; “Mapa de relaciones”.
  - Tarjetas de perfil con miniaturas diminutas e insignias “Verificado” y “DECLARADO”.
  - La lectura de *readiness* no siempre coincidía con los gates reales de emisión y congelado.
  - Los conjuntos de SKU de prueba eran mínimos.
  - Importación con IA sin evidencia por línea.
- Riesgos (`known-risks.md`): mapeos de rol duplicados, errores global vs. tenant, demo tratado como certificado, importación IA sin procedencia durable, UNKNOWN convertido en valor por defecto, y secciones importadas con escala, origen u orientación sin verificar.

## Alcance
1. **Página de sistema:** encabezado con nombre, material, profundidad, procedencia (DEMO, DECLARADO por el fabricante o VERIFICADO con documento y revisor) y **readiness PASS/WARN/BLOCK** calculado con **la misma función** que usan los gates de emisión y liberación. Agrega un test de paridad: para cada fixture, el resultado del catálogo es igual al resultado del gate.
2. **Pestañas:** Perfiles · Refuerzos · Vidrios (composiciones y formatos de lámina) · Herrajes (kits por tipo de apertura y rango de medidas) · Reglas de compatibilidad · Costos (cobertura, enlazada a P07) · Historial.
3. **Ficha de artículo:**
   - Miniatura de la sección **desde la geometría real**, con escala, origen y orientación visibles.
   - Rol en español, ancho de cara, masa por metro, pérdida de soldadura y largo de barra.
   - Insignia de procedencia que abre: documento de origen, página o línea, revisor y fecha.
   - Validaciones de la sección: autointersección, profundidad vs. bounding box y origen local; si fallan, el artículo no puede pasar a VERIFICADO.
4. **Procedencia protegida en la base de datos:** un miembro no puede elevar la procedencia a VERIFICADO sin el rol de revisor técnico (trigger o RLS). Un test de `make test-db` lo demuestra. Revisa los defectos históricos de autorización global vs. organización en paneles (el PR #107 los dejó en verde; agrega un test de regresión si no existe).
5. **Revisión de importación (IA):** tabla de candidatos con confianza, **evidencia de origen** (extracto de página o línea del PDF o XLSX), diff contra el artículo existente y conflictos marcados. LOW y REVIEW_REQUIRED quedan **desmarcados por defecto**. Lo no extraído queda UNKNOWN. Al confirmar se re-deriva desde el candidato guardado. Identidad del revisor y hora, y auditoría inmutable desde la importación hasta la publicación.
6. **Bloqueadores con deep link:** cada BLOCK enlaza al artículo o regla exacta que lo causa.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño o el técnico que mantiene el catálogo. Debe sentir: “sé de dónde viene cada dato y si puedo fabricar con él”.
- **Anatomía:** Catálogo como autoridad: cada registro con procedencia (manual o IA), revisor, estado (DEMO, importado, revisado, certificado) y readiness con la misma regla que la emisión y la liberación.
- **Momento de firma (preservar o crear):** `DemoBadge` en todo lo sintético; la sección de perfil dibujada (F10) en la ficha del perfil.
- **Idea que sube el techo (obligatoria, con el motor):** Subir cualquier archivo (PDF, planilla, foto) y revisar los candidatos de la IA campo por campo con la fuente resaltada junto al valor extraído.
- **Slop a eliminar aquí:** Tablas planas sin procedencia, readiness que no coincide con los gates, datos sintéticos sin marca.
- **Preguntas del pase editorial:** ¿Se puede confundir un dato DEMO con uno certificado? ¿Cada valor extraído por IA muestra su fuente?

## Criterios de aceptación
- Test de paridad readiness ↔ gates en los fixtures DEMO_60 y en uno incompleto.
- Test de BD: autocertificación rechazada para el rol miembro.
- e2e: importar el PDF de fixture → revisar → desmarcar o corregir → publicar → el artículo muestra su procedencia con evidencia → la auditoría lista cada paso.
- Sin mensajes nativos (P01 ya corrige los `pattern=` de `CatalogPage.tsx`; verifica). Capturas de la página de sistema, la ficha y la revisión de importación.
