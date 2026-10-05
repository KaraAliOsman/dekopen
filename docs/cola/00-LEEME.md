# DEKOPEN v1 — Auditoría, constitución de diseño y cola de trabajo para Codex

Fecha: 2026-10-04 · Repo auditado: `KaraAliOsman/framedex` en `main@b3d1c9b` (2026-10-01)
Fuentes: 81 sesiones (565 adjuntos), revisados en 70 hojas de contacto de 431 capturas, 21 videos (39 hojas de fotogramas, incluido el recorrido A-Z de 27 min), 12 PDF (82 páginas), ~95 reportes de auditoría, el código actual de main, los metadatos de GitHub (112 PR) e investigación externa (Orgadata/Logikal, Windowmaker, Stolcad, FeneCAM, ProF2, Alumilcal, Moxisys, PandaDoc/Qwilr, OGUC y NCh).

---

## 0. En 30 segundos

1. **Qué es:** el programa completo para llevar DEKOPEN de demo a producto: **39 encargos** para Codex + **1 orquestador** + la **constitución de diseño** que define la UI y el estándar de calidad.
2. **Cómo se usa:** en PowerShell, desde esta carpeta, corre `.\ejecutar-cola.ps1`. El script crea un clon limpio del repo, le copia tu `.env` (con la clave de IA) y la cola, y abre **una sesión de Codex nueva por encargo**, en orden, hasta el PR final hacia `main` con una guía de revisión. Codex no te pregunta nada. Detalle en `GUIA-COMO-EJECUTAR.pdf`.
3. **Qué haces tú al final:** revisas con `docs/GUIA-REVISION.md`, mergeas y conectas Railway, Flow, SII y correo con `docs/operations/ACTIVACION.md`.

**Archivos de esta carpeta:** `00-LEEME.md` (esto) · `CONSTITUCION-DISENO.md` (punto de vista y estándar de UI) · `prompts/` (40 prompts listos para pegar) · `cuerpos/` (fuentes editables + `_contrato.md`) · `adjuntos/` (referencias visuales) · `ejecutar-cola.ps1` (lanza la cola con Codex) · `GUIA-COMO-EJECUTAR.pdf` (paso a paso) · `dekopen-secrets.env` (copia de tu clave; el script usa el `.env` de `Downloads\framedex`, que ya la tiene).

---

## 1. Estado real (verificado)

**Repositorio y CI**
- `main` es la línea de integración. El PR #107 (pase completo 00–14: +100k líneas, 1.292 archivos) está **MERGEADO** con los 4 checks en verde (Lint & Typecheck, Test Suite, Frontend Build, Database Gate). Después se mergearon #112 (correcciones del swarm: gates de producción, DTE, jobs de IA), #113 (bot 2D) y #111 (wiki LLM en `docs/wiki/`). El #109 está cerrado y fue reemplazado por el #110.
- Por lo tanto, **ya no aplica** la recomendación anterior de “estabilizar el PR #107”: los fallos de CI de RBAC y de drift de OpenAPI quedaron resueltos en main.
- Tamaño: backend ~91k líneas, frontend ~115k, motor ~19k, supabase ~16k, docs ~9k. Hay 111 ramas, casi todas históricas.

**Funcionalidad: corrección importante (2026-10-03).** La “fase 14” (`docs/redesign/phase14-close-report.md`) marca 8 recorridos como “PASA”, pero eso es **la autoevaluación de Devin**, hecha con el proveedor de IA **MOCK** y con un catálogo **100 % sintético**. El dueño tiene razón: **es una demo**. La revisión del código lo confirma:

| Área | Lo que hay realmente en main | Veredicto |
|---|---|---|
| Catálogo | 3 sistemas, todos “referencia sintética” (`DEMO_60` PVC, `ALU_65`, `GLASS_45`); en DEMO_60, ~8 perfiles y un kit de herraje por tipo de apertura | Juguete |
| Sistemas | Parámetros de corredera y de practicable mezclados en un mismo sistema; solo 10 roles de perfil; acabados como texto (“WHITE”, “FOILED”) | Modelo incompleto |
| Vidrios | Un **string** (`"4-16-4"`) parseado con regex; sin tipos (templado, laminado, low-e…), gas, separador, seguridad NCh 135, límites, recargos ni pedido al vidriero | Casi inexistente |
| Aperturas | Enum de 12 valores; no hay abatible hacia afuera, solo abatimiento, francesa con inversor, fijo en hoja, elevable, plegable… | Muy limitado |
| Herrajes | 1 kit por tipo, con validación por rango de medidas y peso; sin componentes cortables, clases, puntos de cierre ni reglas de manilla | Básico |
| Extras y servicios | No existen (vierteaguas, ensanches, mosquiteros, instalación, flete…) | Falta |
| Vano → fabricación | No existe; el usuario calcula a mano | Falta |
| IA | MOCK por defecto; ~18 operaciones posibles (no puede dividir una bahía, cambiar el color, crear una posición…); solo 8 aperturas aceptadas; un verificador de números que rechaza cifras derivadas; sin tool calling | **No hace lo que se le pide** (explica la queja del dueño) |
| Flujos (cotizar → producir → despachar) | Existen como esqueleto y se recorren, pero sobre los datos anteriores | Esqueleto |
| UI y documentos | Ver el mapa de brechas | Prototipo |

**Conclusión:** hay que rehacer **dominio + IA + UI**. La arquitectura (motor puro con Decimal, Django, RLS, revisiones inmutables) es sana y **se conserva**. Todo lo que se construye sobre ella (catálogo, tipologías, vidrios, herrajes, IA y pantallas) se rehace o se completa. Por eso la cola tiene ahora **39 encargos** (frentes D, IA y P, más dos pases editoriales) y un **orquestador** que los ejecuta todos.

## 2. Mapa de brechas (por severidad)

**A. Dominio e IA — lo que separa la demo del producto (frentes D e IA)**

1. **Catálogo sintético.** `DEMO_60`, `ALU_65` y `GLASS_45` son fixtures (“referencia sintética” dice el seed): una sola serie por material, ~8 perfiles, sin geometría de sección ni proveniencia certificada. → D01 + P16
2. **Vidrio = un string.** `"4-16-4"` parseado con regex: sin templado/laminado/low-e, gas, separador, seguridad NCh 135, límites ni pedido al vidriero. → D02
3. **Tipologías limitadas.** 12 aperturas; faltan proyectante/abatible real hacia afuera, solo abatimiento, francesa con inversor, fijo en hoja, corredera elevable, plegable, puerta doble real. → D03 + D08
4. **Herrajes básicos.** 1 kit por tipo de apertura, validado solo por rango de medidas y peso; sin componentes, clases, puntos de cierre ni reglas de manilla. → D04
5. **Acabados = texto libre.** Sin carta de colores, sin caras interior/exterior distintas, sin recargo ni plazo. → D05
6. **Sin extras ni servicios.** Vierteaguas, ensanches, mosquiteros, tapajuntas, instalación, retiro y flete no existen como concepto modelado. → D06
7. **Sin vano → fabricación.** El usuario calcula las holguras y deducciones a mano. → D07
8. **La IA no hace lo que se le pide.** MOCK por defecto; ~18 operaciones de ensamblaje (no divide una bahía, no cambia un color, no crea posiciones); solo 8 aperturas aceptadas; el verificador de grounding rechaza números derivados correctos; sin tool calling. → IA1 + IA2 + IA3

**B. Críticas de confianza visual (frente P)**

9. **Correderas sin dirección en el modelo.** La dirección de las flechas es una convención de presentación (`ProductFrontSvg.tsx:706`, `renderers.py:684`); `SlidingPanel` no tiene `travel` ni orden de carriles. En builds antiguos el editor y la portada del DOC-01 mostraban → → (dos hojas hacia el mismo lado). → P05 (+ modelo en D03)
10. **Elevaciones sin vista declarada** (interior/exterior) y **sin distinción continua/discontinua**: el proyectante, que abre hacia afuera, se dibuja igual que una apertura interior. → P05 (+ D03)
11. **Formas especiales:** el arco se renderizaba como trapecio y el trapecio dejaba el lienzo en blanco (auditoría). → P05 + D08
12. **DOC-01 con colisiones de columnas y página en blanco**, y medidas con `.00`. → P09
13. **Identificadores con hash:** órdenes de compra `PO-{hex}` (`purchasing/service.py:593`); históricamente también OT y proyectos. → P02
14. **Mensajes nativos del navegador en inglés** (`pattern=` en 6 lugares, incluida Cobranza). → P01
15. **Portal con estados engañosos:** “Pagar ahora” visible en una revisión reemplazada, un error genérico en enlaces revocados y un 409 crudo. → P10
16. **Ruta demo** `/projects/demo/positions/g1/edit` registrada en producción (`App.tsx:177`). → P00

**C. Altas (usabilidad del núcleo)**

17. **Editor:** el lienzo ocupa ~1/3 de la pantalla bajo formularios de ancho completo; herramientas sin etiqueta; paleta de aperturas críptica; se rompe a 1366 y a 768. → P04
18. **Bow/acoplados** en un formulario aparte, con errores poco accionables. → P06 + D08
19. **Precios:** formulario crudo antes que la información; no hay cascada ni explicación del Δ; no hay banda de margen visible. → P07
20. **Emisión:** varios caminos, sin checklist, sin vista previa real y sin ciclo de vida del enlace. → P08
21. **Producción a escala:** 100 posiciones generan muros de tablas; 9 tarjetas de pasos; enums visibles; el operario no tiene una vista táctil real. → P12
22. **Pack de corte:** pocas barras por página; sin hoja de etiquetas ni agrupación; vidrio no ubicado sin acción. → P13
23. **Inicio vacío** (contadores en 0) y navegación por módulos en vez de por flujo. → P03
24. **Orb:** un punto que no refleja trabajos reales; fallos repetidos que llenan el chat. → P17 (motor en IA2/IA3)
25. **Página de proyecto débil:** posiciones como filas sin el centro de trabajo del estimador. → P21
26. **Superficies vacías o a medias:** clientes/ajustes (P22), despacho→instalación→postventa (P23), analítica (P24).

**D. Medias (profundidad y diferenciación)**

27. CNC: operaciones declaradas no emitidas poco visibles; sin CRUD de herramientas. → P14
28. Inventario sin ruta propia; error al cargar el stock (auditoría); retazos incompletos. → P15
29. Catálogo: la readiness no siempre coincide con los gates; procedencia y revisión de la importación IA. → P16 + D01
30. Cobranza: error en los enlaces de pago; ambigüedad sobre la validez de los documentos tributarios. → P11
31. Térmico y normativa chilena (OGUC 4.1.10, vigente desde el 28-11-2025): no existe. Es una **oportunidad diferenciadora**, pero solo con datos certificados. → P18 + D02
32. 3D: poses irreales (hojas flotando), foliados rosados, herrajes toscos. → P19

**E. Sistémicas (en todo el producto)**
- Letra de 11–12 px, contraste bajo, CTA en competencia, muros de tarjetas, variables CSS fantasma y estilos dispersos en 4 archivos grandes. → P01
- Enums, `[object Object]` (ya corregido en Precios), `undefined`, 4 decimales y porcentajes como `92.5333%`. → P01 + P02
- Datos demo con aspecto de prueba (“Taller Devin”, “Bow Test Org”). → P00
- Sin marca aplicada: favicon, login, correos y estados vacíos genéricos; los documentos del cliente no son white-label de verdad. → P25
- Ninguna revisión del conjunto: cada PR se juzga solo. → ED1, ED2 y P20

## 3. Punto de vista: la constitución de diseño

**`CONSTITUCION-DISENO.md`** (en esta carpeta) es la definición profesional de la UI y el estándar de calidad de todo el programa. P00 la commitea en el repo como `docs/design/CONSTITUCION.md`, P01 la convierte en código (tokens, guardas de lint, detectores) y **todos los prompts la exigen**. No es nueva: consolida el estudio de identidad y el de interacción que DEKOPEN ya tenía y **nunca adoptó** (el P01 anterior incluso lo contradecía, con radios de 8 px que el estudio prohíbe).

Resuelve los seis fundamentos que pediste:

| Fundamento | Cómo queda resuelto en la cola |
|---|---|
| **Evitar la UI zombi** | Punto de vista explícito (*“DEKOPEN se dibuja como se dibuja una ventana”*), prohibiciones concretas del SaaS genérico (degradados, blur, radios ≥ 8 px, píldoras, KPI decorativos, morado de IA, emoji) y la regla “borrar antes que apilar” en el contrato |
| **No confundir terminado con bueno** | Definición de “terminado” vs. “bueno” (§9.1); **pase editorial obligatorio** en cada PR con la rúbrica R1–R20; un ítem en FALLA impide el merge |
| **Tener un punto de vista** | §1: la frase, las personas y lo que cada una debe sentir, las 5 promesas, lo que DEKOPEN **no** es y 12 principios con “sí/no” concretos |
| **Codificar la intención** | §10 y P01: cada estándar se convierte en token, componente, formateador, guarda con trinquete, test de contraste y detector de slop sobre la app en vivo; plantilla de PR con la rúbrica |
| **Editar después de construir** | Pase editorial en cada PR, más **ED1** y **ED2** (un encargo de editor implacable después de cada ola) y el pase de producto completo en P20 |
| **Subir el techo** | §7: 11 momentos de firma que se protegen (*protect the strange*); §8: una idea que va más allá de la competencia por superficie, obligatoria y respaldada por el motor |

Cada prompt de UI tiene además su bloque **“Punto de vista y estándar de esta superficie”**: persona y lo que debe sentir, anatomía, momento de firma, idea que sube el techo, slop a eliminar y preguntas del pase editorial.

**Identidad en una línea:** grafito como estructura, teal como único acento funcional, naranja solo para la marca y para “esto necesita a una persona”; IBM Plex Sans para la interfaz y Plex Mono para toda medida; radios ≤ 4 px con una sola esquina en inglete en las hojas; elevación por líneas, no por sombras; movimiento ≤ 280 ms en un eje; tres densidades (oficina, taller y documento).

## 4. Cómo ejecutar la cola

**Modo de trabajo (tu pedido):** Codex trabaja con **autonomía total** y no te pregunta nada durante el programa. Las decisiones de producto pendientes usan los **valores por defecto** de la constitución (§11), quedan configurables en Ajustes y registradas en `docs/decisions/valores-por-defecto.md`. Las **integraciones externas** (Railway, Flow, SII, correo con dominio) se construyen completas detrás de adaptadores con un proveedor simulado, y quedan documentadas en `docs/operations/ACTIVACION.md` para que las conectes tú después de aceptar.

**Ramas:** todo se integra en **`integracion/v1`** (la crea P00). Cada encargo abre su PR hacia esa rama y Codex lo mergea cuando CI está en verde y el pase editorial está en PASA. **`main` no se toca** hasta el final: P20 abre el único PR `integracion/v1` → `main`, y **ese merge es tuyo**.

### Opción A — script `ejecutar-cola.ps1` (recomendada)
Corre `.\ejecutar-cola.ps1` en PowerShell. Abre una sesión `codex exec` nueva por encargo (contexto limpio en cada uno = mejor calidad), en el orden en serie de abajo, y solo pasa al siguiente cuando `docs/cola/ESTADO.md` en `integracion/v1` marca el encargo como `mergeado` o `bloqueado`. Si se corta, vuelve a correrlo: retoma solo. Opciones: `-Desde P07`, `-Solo IA3`, `-SoloPreparar`, `-Modelo <modelo>`.

### Opción B — a mano en Codex interactivo
Corre `.\ejecutar-cola.ps1 -SoloPreparar`, entra al clon (`cd $env:USERPROFILE\dekopen-v1`), abre `codex` y pega `docs/cola/prompts/ORQ-orquestador.md` (ejecuta toda la cola en una sesión) o cada `docs/cola/prompts/<ID>.md` en orden (**una sesión = un PR**). Los adjuntos ya están en `docs/cola/adjuntos/`.

| Ola | Encargos | Paralelo | Requisito |
|---|---|---|---|
| 0 | **P00** | Sola | Es el primero: crea `integracion/v1` y la constitución en el repo |
| 0b | P01 · IA1 · D01 | Hasta 3 | P00 mergeado |
| D1 | D02 · D03 · D04 | Hasta 3 | D01 mergeado |
| D2 | D05 · D06 · D07 · IA2 · IA3 | Hasta 5 | D01–D04 e IA1 mergeados |
| 1 | P02 · P03 · P04 · P05 · P07 · P09 · P12 · P17 · P25 | Hasta 9 | P01 y frente D mergeados |
| **ED1** | Pase editorial de la ola 1 | Sola | Ola 1 completa |
| 2 | P06 · P08 · P11 · P13 · P14 · P15 · P16 | Hasta 7 | ED1 mergeado |
| **ED2** | Pase editorial de la ola 2 | Sola | Ola 2 completa |
| 3 | D08 · P10 · P18 · P19 · P21 · P22 · P23 | Hasta 7 | ED2 mergeado |
| 4 | P24 | Sola | P23 mergeado |
| 5 | **P20** | Sola | Todo mergeado; abre el PR final a `main` |

**Orden en serie** (más seguro): P00, P01, IA1, D01, D02, D03, D04, D05, D06, D07, IA2, IA3, P02, P25, P04, P05, P09, P07, P03, P12, P17, ED1, P06, P08, P13, P15, P11, P14, P16, ED2, P21, P10, P22, P23, D08, P19, P18, P24, P20.

**Archivos con riesgo de conflicto entre PR paralelos:**
- `engine/src/dekopen_engine/models.py` y `supabase/seed.sql`: todo el frente D. **Mergea el frente D en serie o con rebase inmediato.**
- `backend/ai_gateway/` y `backend/projects/design_assist.py`: IA1, IA2 e IA3, en serie.
- `backend/documents/renderers.py`: P02 → P05 → P09 → P13, en ese orden, rebaseando antes de cada merge.
- `frontend/src/features/canvas/`: P04, P05, P06, P19 e IA2.
- `frontend/src/App.tsx`: P00, P03, P15, P21–P25 (rutas).

**Cuando todo termine (tu revisión):** abre `docs/GUIA-REVISION.md` del PR final. Trae cómo levantar el producto, con qué usuario entrar en cada rol y un recorrido guiado de 30 minutos por flujo. Si algo no te convence, pídeselo a Codex sobre `integracion/v1` antes de mergear a `main`.

## 5. Lo que te toca a ti

**Antes de empezar (5 minutos):**
1. **Clave de IA:** ya está. Tu `Downloads\framedex\.env` trae `AI_GATEWAY_MIMO_API_KEY` (la tuya) y `AI_GATEWAY_MIMO_BASE_URL=https://api.primalabs.ai/v1`; el script lo copia al clon y agrega `AI_GATEWAY_MIMO_MODEL=primalabs-ai/MiMo-V2.6-Pro`. Es la convención que ya usa el backend. El `.env` está en `.gitignore` y los prompts prohíben commitearlo.
2. Instalar Codex CLI (`npm install -g @openai/codex`), iniciar sesión (`codex login`) y tener Docker Desktop abierto.

**Durante el programa:** nada. Codex no te va a preguntar. Deja el PC encendido.

**Al final, después de aceptar el producto:**
1. Revisar y mergear el PR `integracion/v1` → `main`.
2. Confirmar o cambiar en Ajustes los valores por defecto (papel Carta, anticipo 50 %, validez 15 días, margen objetivo 35 % y mínimo 25 %, IVA 19 %, pie “Generado con DEKOPEN” oculto, asistente “Asistente DEKOPEN”, marca `DEK⧈PEN`). Están todos en `docs/decisions/valores-por-defecto.md`.
3. Conectar las integraciones siguiendo `docs/operations/ACTIVACION.md`: Railway, Flow (credenciales sandbox y luego producción), proveedor de DTE/SII y correo con dominio propio.
4. Cargar el catálogo real subiendo las fichas del proveedor (PDF, planillas o fotos) en Catálogo › Importar; la IA las procesa y tú revisas antes de publicar. Lo mismo para la lista de precios del vidriero y las normas (NCh 135, fichas térmicas).

## 6. Adjuntos por prompt

**No hay que adjuntar nada a mano:** el script copia todo a `docs/cola/` del clon y cada encargo lee sus referencias desde `docs/cola/adjuntos/` según esta tabla. La constitución está en `docs/cola/CONSTITUCION-DISENO.md` (y, después de P00, en `docs/design/CONSTITUCION.md`).

| Prompt | Referencias en `docs/cola/adjuntos/` |
|---|---|
| ORQ | Toda la cola en `docs/cola/` |
| P00 | `auditoria-hojas/*` (opcional, ejemplos de defectos) |
| P01 | `diseno/*` |
| P03 | `diseno/ref_linear_commandmenu.png` |
| P04 | `editor/*`, `diseno/ref_tldraw_*`, `diseno/ref_excalidraw_*`, `diseno/dekopen_interaction_study.md`, `auditoria-hojas/s043.png`, `s057.png`, `s063.png` |
| P05 | `editor/*`, `diseno/board-04-icon-grammar.png`, `auditoria-hojas/s036.png`, `s040.png`, `s043.png` |
| P06 | `auditoria-hojas/s063.png`, `s064.png`, `editor/*` |
| P07 | `auditoria-hojas/s034.png`, `s048.png` |
| P08, P09, P10 | `cotizacion/*`, `diseno/board-05-document-direction.png`, `auditoria-hojas/s051.png`, `s067.png`, `s039.png` |
| P11 | `auditoria-hojas/s067.png` |
| P12, P13, P14 | `produccion/*`, `auditoria-hojas/s069.png`, `s042.png`, `s035.png` |
| P15 | `auditoria-hojas/s046.png`, `s056.png` |
| P16 | `auditoria-hojas/s064.png` |
| P17 | `bot/*` |
| P19 | `auditoria-hojas/s040.png`, `s041.png`, `s062.png` |
| P25 | `diseno/board-02-mark-studies.png`, `diseno/dekopen-visual-identity-study.md`, `bot/*` |
| IA1, IA2, IA3 | Ninguno |
| D01 | Ninguno (el catálogo real se sube después en la app); opcional: una ficha PDF del proveedor como caso de prueba |
| D02 | `cotizacion/*` |
| D03 | `editor/*`, `diseno/board-04-icon-grammar.png` |
| D04 | `produccion/*` |
| D05 | `diseno/*` |
| D06 | `cotizacion/*` |
| D07 | `editor/*` |
| D08 | `auditoria-hojas/s063.png`, `s064.png` |
| P21, P22, P23, P24, ED1, ED2, P20 | Ninguno además de la constitución |
