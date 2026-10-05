# P01 — Sistema de diseño v2: la constitución convertida en código (tokens, primitivas, formateadores, guardas y detector de slop)

**Depende de:** P00 (constitución en `docs/design/CONSTITUCION.md`, arnés `ux:capture`). Adjunta: `CONSTITUCION-DISENO.md`, `diseno/*`.

## Objetivo
Que el punto de vista de DEKOPEN deje de depender de la memoria de quien programa. Cada estándar de la constitución se convierte en **token, componente, formateador, guarda de lint, test o detector**, de modo que hacer algo genérico sea más difícil que hacerlo bien. Aquí no se rediseñan páginas de producto: se fabrica el material con el que todas las demás se van a construir. **Esto es el sistema que genera las pantallas; tiene que ser impecable.**

## Por qué
El estudio de identidad (`dekopen-visual-identity-study.md`, board-01 a board-06) definió un lenguaje propio hace meses y **nunca se adoptó**: la app sigue con radios redondeados, letra de 11–12 px, variables CSS fantasma, estilos repartidos en 4 archivos grandes, enums visibles y validación del navegador en inglés. Sin un sistema que obligue, cada PR vuelve al promedio estadístico (el SaaS genérico).

## Situación actual (verificada en main `b3d1c9b`)
- `frontend/src/styles/tokens.css` (~340 líneas, ~226 variables). Estilos dispersos en `ui/ui.css` (~1000), `index.css` (~2060) y `features/canvas/canvas.css` (~2300).
- Primitivas en `frontend/src/ui/`: Controls, Dialog, ConfirmDialog, Tabs, Toast, States, StatusBadge, PageHeader, Layout, TechDetails, InlineEdit. Formato en `frontend/src/format.ts` y `frontend/src/features/money.ts`. i18n en `frontend/src/i18n/`.
- Validación nativa con `pattern=` (mensajes en inglés): `features/projects/ProjectPaymentsPanel.tsx:610`, `features/projects/ProjectPaymentLinksPanel.tsx:227`, `features/catalogs/SectionImportPanel.tsx:233`, `features/catalogs/CatalogPage.tsx:902/997/1083`.
- (auditoría) Letra de 11–12 px casi en todas partes, contraste bajo en texto atenuado, varios CTA primarios compitiendo, muros de tarjetas, enums visibles (SASH, GLAZING_BEAD, FRAME), cantidades como `24.0000` y `92.5333%`.

## Alcance

### 1. Tokens v2 (`frontend/src/styles/tokens.css`), exactamente los de la constitución §3
- Rampas completas: grafito (g-950 … g-25, paper), teal (950 … 50), naranja (700, 600, 500, 400, 300, 100) y semánticos (base, suave, tinta) con los hex de la constitución.
- Roles funcionales para **tema claro y oscuro** (`[data-theme="dark"]`), y roles del lienzo (`--canvas-*`). Migra las variables actuales a los roles (`--theme-accent` → `interactive`/`interactive-fill`; las manijas `--theme-warning` → `--canvas-handle` = mark).
- Tipografía: **IBM Plex Sans y IBM Plex Mono autoalojadas** (WOFF2, subconjunto latino, pesos 400/500/600, `font-display: swap`), reemplazando la familia actual. Escala del §3.2 como tokens (`--type-display`, `--type-title-l`, `--type-title-m`, `--type-label`, `--type-body`, `--type-dense`, `--type-dim`, `--type-micro`) y variantes por densidad.
- Espaciado `--space-*` (2 … 64), radios `--r-0/1/2/pill`, elevación `--e1/e2/e3/--sheet`, capas `--z-*`, movimiento `--t-micro/state/spatial/max` + curvas, y el **inglete** como utilidad `.sheet-miter` (clip-path de 8 px arriba a la derecha).
- Densidades `[data-density="office"|"workshop"|"document"]` con base, alto de control y tema por defecto del §3.7.
- **Test de tokens:** parsea todo el CSS y falla si hay un `var(--x)` sin definir o una variable definida que nadie usa (la segunda con línea base).
- **Test de contraste:** calcula el ratio de cada par texto/fondo declarado en ambos temas y falla bajo AA (4.5:1 texto normal, 3:1 texto grande e íconos).

### 2. Consolidación del CSS
Reparte `ui/ui.css`, `index.css` y `canvas.css` por componente o por feature (CSS Modules o el mecanismo que ya use el repo; no agregues un framework nuevo de estilos). Elimina reglas muertas (usa cobertura del navegador sobre `ux:capture` para detectarlas). Meta: −30 % de líneas de CSS sin regresiones visuales en las rutas existentes, verificado con `ux:capture` antes/después.

### 3. Primitivas (`frontend/src/ui/`, exportadas desde `index.ts`), cada una con los 5 estados cuando aplique
- **Acciones:** `Button` (primary, secondary, ghost, danger; sm 28 / md 32 / touch 44; loading con el cargador de cota; **radio r-1, nunca píldora**), `IconButton` (aria-label y tooltip `Nombre — Atajo` obligatorios por tipo), `ButtonGroup` con la regla de un solo primary por región (advertencia en desarrollo si hay dos).
- **Formularios:** `Field` (etiqueta técnica arriba, ayuda, error en español, requerido), `TextField`, `NumberField` (sufijo de unidad; acepta `2400`, `2 400`, `2.400` y `1249,5` según la precisión declarada; entrega un string Decimal-safe, nunca float), `MoneyField` (CLP sin decimales; USD con 2), `Select`, `Combobox` con búsqueda, `Checkbox`, `Radio`, `SegmentedControl`, `Switch`.
- **Estructura:** `Panel`/`Section` (título M + reglas; las tarjetas solo para colecciones), `Tabs`, `Inspector` (riel 300–320 con grupos plegables y “Avanzado”), `KeyValue` (etiqueta técnica + valor Mono), `Stepper` (ciclo de vida), `Stat` (solo con decisión asociada: un KPI sin acción no se renderiza).
- **Datos:** `DataTable` (reglas finas, sin cebra, encabezado fijo, números a la derecha en Mono, orden, filtro, selección con barra de acciones en lote, virtualización sobre 200 filas, 5 estados).
- **Estado de dominio:** `StatusChip` (estado → etiqueta + tono + ícono por el mapa central; nunca solo color), `UnknownValue` (“Sin dato” + causa + acción).
- **Superposiciones:** `Drawer`, `Popover`, `Menu`/`ContextMenu`, `Tooltip`, `Dialog`, `ConfirmDialog` (pregunta de ficha técnica + consecuencia), `Toast` (sin exclamaciones), `CommandPalette` (`Ctrl+K`, con registro de comandos extensible; P03 la conecta).
- **Estados:** `EmptyState` (por qué + una acción), `LoadingState` (esqueleto con la forma real, sin shimmer; cargador de cota > 1 s), `ErrorState` (qué pasó + por qué + qué hacer + “Detalles técnicos” plegable + reintentar), `DeniedState` (qué rol y a quién pedirlo), `BlockedState` (qué falta + botón al lugar exacto).
- **Firma:** `DimLoader` (la cota que se dibuja de 0 a 100 %), `SheetSurface` (papel sobre la mesa, con inglete opcional), `TraceButton` (“¿De dónde sale?”: popover con fórmula, entradas, autoridad y versión del motor; recibe la traza del backend, nunca la calcula), `DemoBadge` (insignia DEMO para datos sintéticos).
- **Íconos:** set base restilizado al trazo de 1,5 px con puntas cuadradas y uniones en inglete, más la **familia de aperturas** del §3.6 como componentes SVG (`OpeningGlyph type view`) que P05 reutiliza en el lienzo y en los documentos.

### 4. Formateadores de dominio (componentes y funciones en `format.ts`), según la constitución §3.3
`<Money value currency>`, `<Dims w h>` (`2 400 × 1 800 mm` con espacio fino U+2009), `<Length mm>`, `<Area m2>`, `<Weight kg>`, `<Uvalue>`, `<Qty value unit>`, `<Percent value kind="fraction"|"points">` (tipo explícito para no multiplicar ni dividir de más), `<EntityCode kind code>` (Mono, copiar al clic, con fallback si falla el portapapeles), `<Timestamp>` (relativa + absoluta en tooltip, America/Santiago), `<DateOnly>`. `null`/`undefined` → `UnknownValue`. Unidades al 85 % en g-500. Elimina los formateadores duplicados que queden.

### 5. Etiquetas centralizadas
`frontend/src/i18n/domainLabels.ts` traduce todos los enums visibles con el glosario de la constitución §4 (aperturas, estados de proyecto/cotización/OT/pedido/pago/trabajo de IA, roles, pasos, estaciones, roles de perfil y códigos de error). **Test de exhaustividad** contra los enums del cliente orval: un enum nuevo sin etiqueta rompe CI (demuéstralo en el PR).

### 6. Validación en español
Todo `<form>` lleva `noValidate` y valida con un hook común (mensajes del §4, foco y scroll al primer error). Reutiliza el validador de RUT módulo 11 si existe; si no, créalo en un solo lugar con tests. Corrige los 6 `pattern=`.

### 7. Guardas con trinquete (`scripts/check_guards.py`, ya corre en `make lint`)
Cada guarda tiene una línea base con las violaciones actuales; CI falla si aparece una nueva. En `frontend/src/**` (excepto `/dev/` y los tokens):
- hex/rgb inline (usar tokens); `border-radius` > 4 px salvo `--r-pill` en puntos de estado; `box-shadow` fuera de `--e*`/`--sheet`; `linear-gradient`/`radial-gradient`/`conic-gradient`; `backdrop-filter` y `filter: blur`; `font-weight: 700` o `bold`; `font-size` < 11 px o en px literales fuera de tokens; `transition`/`animation` > 280 ms; `z-index` literal; `.toFixed(` para mostrar; `pattern=`; render de `{x.status}` o enum crudo sin `domainLabels` (heurística documentada); emoji en strings de UI; signos de exclamación (`¡` y `!`) en strings de UI; palabras en inglés de una lista negra en strings visibles.

### 8. Detectores de slop en vivo (extiende `ux:capture` de P00)
Sobre la app renderizada, por ruta: más de un botón primario visible por región (`data-region`), radios computados > 4 px, sombras computadas fuera de la escala, degradados y blur computados, contraste real bajo AA, fuente computada < 11 px, objetivos < 44 px en `workshop`, texto en inglés, emoji, exclamaciones y elementos interactivos sin efecto (botones sin handler ni `href`). Cada detector con tests positivos y negativos.

### 9. Muestrario `/dev/ui` (DEV-only)
Todas las primitivas, los formateadores y los íconos de apertura en ambos temas y en las tres densidades, con datos del fixture; incluye una página **“Bien / Mal”** que reproduce el board-06 (SaaS genérico vs. DEKOPEN) como referencia viva para los encargos siguientes.

### 10. Plantilla de PR
`.github/pull_request_template.md` con: resumen, flujos probados, capturas antes/después, **tabla de la rúbrica R1–R20** (PASA/FALLA), momento de firma y la idea del §8, lo que se quitó, decisiones registradas, integraciones en sandbox y “No hecho / riesgos”.

## Momento de firma de este encargo
El muestrario es la prueba: abierto a 1440, debe leerse como una página de manual técnico de perfiles, no como un kit de UI. `DimLoader`, `SheetSurface` con inglete, `TraceButton` y `OpeningGlyph` son las piezas singulares; tienen que verse y sentirse perfectas.

## Fuera de alcance
Rediseñar pantallas de producto (lo hacen P03 en adelante). Solo migra los 6 `pattern=`, la consolidación del CSS y lo mínimo para que las rutas actuales adopten los tokens sin romperse.

## Criterios de aceptación
- `/dev/ui` completo en claro y oscuro y en las tres densidades; axe sin violaciones *serious* ni *critical*.
- Tests de tokens (sin fantasmas), de contraste AA en ambos temas y de exhaustividad de enums en verde.
- Tests de formateadores: 0, negativos, null, 1e9, CLP vs USD, `2400` vs `2 400` vs `2.400` vs `1249,5`, y redondeo (documenta cuál usa el motor y respétalo).
- Guardas y detectores activos, con línea base commiteada y tests propios.
- `ux:capture` antes/después de todas las rutas: sin regresiones; reducción medible de hallazgos (radios, fuentes, sombras) por la adopción de tokens.
- Plantilla de PR commiteada y usada en este mismo PR.
- Ningún mensaje nativo en inglés en Cobranza ni en Catálogo (captura de un error de validación en español).
