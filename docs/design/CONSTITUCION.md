# DEKOPEN — Constitución de diseño y calidad

> **Estado:** obligatoria. P00 la commitea en `docs/design/CONSTITUCION.md`. A partir de ahí es la fuente de verdad del diseño. Prevalece sobre cualquier gusto personal, convención SaaS o "lo que suele hacerse". Si un encargo la contradice, gana la constitución; si la constitución no cubre un caso, decide según el §1 y deja la decisión registrada en el PR.
>
> **Origen:** consolida el punto de vista que DEKOPEN ya había definido y nunca adoptó: `dekopen-visual-identity-study.md`, `dekopen_interaction_study.md` y los tableros board-01 a board-06. Agrega la voz, las superficies, los momentos de firma, la lista anti-slop y el pase editorial.

---

## 0. Por qué existe este documento

Un modelo de lenguaje, cuando no tiene un punto de vista, entrega **el promedio estadístico de lo que ya existe**: tarjetas redondeadas, sombras suaves, un degradado morado, "¡Bienvenido de nuevo!", un dashboard con cuatro KPI. Se ve terminado en segundos y no resuelve nada. Eso es la **UI zombi**: software desechable, sin coherencia y sin alguien detrás que se haya preocupado.

DEKOPEN no puede ser eso, por cinco razones:

1. **Terminado no es bueno.** Una pantalla con bordes redondeados y sombras sutiles no está resuelta: solo tiene barniz. Un trabajo está bueno cuando un estimador cotiza 12 posiciones más rápido que con su software actual, sin dudar de ningún número.
2. **El punto de vista viene antes que la pantalla.** Si no lo fijamos nosotros, la IA impone el suyo, que es genérico y mira al pasado. Este documento es el nuestro.
3. **Se diseña el sistema que genera las pantallas.** Cada estándar de este documento se convierte en token, componente, guarda de lint o test (P01). Así no solo se escala la consistencia: se escala la intención.
4. **La calidad se filtra al final, con un editor implacable.** Producir es barato. Por eso cada PR termina con un pase editorial (§9) que revisa el flujo completo, se hace responsable de cada decisión y elimina lo arbitrario.
5. **La IA sirve para subir el techo, no solo para llegar más rápido al piso.** Cada superficie tiene un momento propio (§7) y una idea que va más allá de lo evidente (§8). Lo singular se protege (*protect the strange*).

---

## 1. Punto de vista

### 1.1 La frase

> **DEKOPEN se dibuja como se dibuja una ventana.**

Líneas finas, ingletes a escuadra, uniones visibles, números tabulares en milímetros y un único acento deliberado. La interfaz tiene la estética propia del oficio, ejecutada con disciplina de estudio de diseño. **No es un SaaS moderno ni un ERP del 2005.**

**La prueba del manual Schüco:** si una captura podría ser la promo de un plugin de Figma (sombras suaves, tarjetas redondeadas, degradado de acento, copy simpático), falla. Si podría ser una página de un manual técnico de perfiles o el plano de una pieza mecanizada (líneas finas, números monoespaciados, un teal controlado), pasa.

### 1.2 Para quién diseñamos y qué debe sentir

| Persona | Contexto real | Lo que debe sentir | Densidad |
|---|---|---|---|
| **Estimador/a** | Oficina, monitor de 24", 30 a 80 posiciones por obra, presión de plazo | "Esto entiende ventanas y me ahorra horas" | `office` |
| **Dueño/a de la fábrica** | Notebook o celular, entre visitas a obra | "Sé dónde se gana y dónde se pierde plata hoy" | `office` |
| **Jefe/a de taller** | Pantalla en planta, con guantes, ruido | "Sé qué cortar, en qué orden y qué falta" | `workshop` |
| **Operario/a** | Tablet en la estación, de pie, 2 m de distancia | "Una pieza, una pantalla, cero dudas" | `workshop` |
| **Instalador/a** | Celular en obra, sol, una mano | "Sé qué llevar, dónde va y cómo cerrar el trabajo" | `workshop` |
| **Cliente final** | Celular o PC, sin vocabulario técnico | "Esta empresa es seria; entiendo qué compro y cuánto cuesta" | `document` |

### 1.3 Las cinco promesas (en este orden)

1. **"Esto entiende ventanas."** Cada dibujo obedece la lógica de la fenestración: vista declarada, simbología correcta, correderas en carriles, manilla del lado de cierre.
2. **"Es dramáticamente más fácil."** El usuario básico llega al precio con sistema, medidas, apertura, vidrio y color. Nada más.
3. **"Conecta lo que antes hacía a mano."** Cotización, compra, corte, producción, despacho e instalación salen del mismo modelo, sin volver a digitar.
4. **"Trabaja por mí."** Lo que el motor puede derivar, no se le pregunta al usuario. La IA ejecuta, no solo conversa.
5. **"Confío en los números."** Cada cifra tiene una fuente visible a un clic. Lo desconocido se muestra como desconocido.

### 1.4 Lo que DEKOPEN NO es

- No es un dashboard SaaS genérico con KPI decorativos.
- No es un formulario gigante con un dibujo de adorno.
- No es un chatbot pegado al costado.
- No es una demo: ningún botón existe sin efecto real.
- No es simpático: es preciso, tranquilo y confiable. La personalidad está en el rigor, no en los chistes.

---

## 2. Principios (con "sí" y "no" concretos)

| # | Principio | Sí | No |
|---|---|---|---|
| P1 | **El dibujo es la interfaz.** | El lienzo ocupa ≥ 60 % del editor; se edita sobre la cota, en el lugar | Formularios de ancho completo con el dibujo como miniatura |
| P2 | **Un número, una fuente.** | Cada monto, medida o peso abre "¿De dónde sale?" con la traza del motor | Cifras calculadas en el frontend o escritas por la IA |
| P3 | **Lo desconocido se ve.** | "Sin dato · falta el peso del vidrio · Completar" | `0`, `—` sin causa, o un valor por defecto silencioso |
| P4 | **Divulgación progresiva.** | Básico: 6 decisiones. Avanzado: perfiles, refuerzos, herrajes, trazas | Las 40 opciones del sistema en la primera pantalla |
| P5 | **Nada es arbitrario.** | Cada color, radio, espacio y tamaño sale de un token con un rol | `margin: 13px`, `#3b82f6`, `border-radius: 12px` |
| P6 | **Hablar como el taller.** | Hoja, marco, junquillo, montante, travesaño, termopanel, manilla | `SASH`, `GLAZING_BEAD`, "ítem", "elemento", "objeto" |
| P7 | **Una acción principal por región.** | Un solo botón primario visible por panel; el resto, secundarios | Tres botones teal compitiendo en la misma franja |
| P8 | **El sistema trabaja.** | Prellenar, derivar, sugerir con causa, aplicar en lote con diff | Preguntar lo que ya se sabe; pedir confirmar lo obvio |
| P9 | **La inmutabilidad se ve.** | Revisión emitida con sello, huella y "Crear revisión B" | Editar un documento emitido "porque se puede" |
| P10 | **El estado es explícito.** | Etiqueta + tono + ícono + causa ("Bloqueada · falta perfil MARCO-70") | Puntos de color sin texto; "Error" a secas |
| P11 | **Proteger lo extraño.** | Ingletes, huella en el cajetín, cargador de cota, Orb con estados reales | Quitar lo singular "para que se vea más limpio" |
| P12 | **Borrar antes que apilar.** | Cada rediseño elimina el componente viejo y su CSS muerto | Dejar la versión vieja escondida "por si acaso" |

---

## 3. Lenguaje visual

### 3.1 Color

Proporción en pantalla: **~75 % grafito, ~20 % teal, ≤ 3 % naranja, ~2 % semánticos.** El teal es el metal (anodizado, de ingeniería). El naranja es la marca y significa **"esto necesita a una persona"**. Nunca va en un CTA, en una insignia decorativa ni como adorno.

**Rampas (tema claro)**

| Grafito | Hex | Rol |
|---|---|---|
| g-950 | `#161C1F` | Tinta, texto principal, trazo de perfil |
| g-900 | `#252D31` | Cromo oscuro (barra de comandos) |
| g-700 | `#465158` | Texto secundario, texto de cotas, íconos |
| g-500 | `#727D82` | Texto atenuado (solo grande o metadato ≥ 12 px), guías |
| g-400 | `#9AA6A9` | Placeholder y deshabilitado |
| g-300 | `#CDD5D6` | Borde por defecto, reglas de tabla |
| g-200 | `#E0E6E5` | Línea fina, separadores |
| g-100 | `#EEF2F1` | Hover, relleno inset |
| g-50 | `#F5F7F6` | Fondo de la app (mesa de trabajo) |
| g-25 | `#FCFDFC` | Superficie de panel |
| paper | `#FFFFFF` | Hoja de dibujo y documento: **el papel es blanco, el metal es blanco roto** |

| Teal | Hex | Rol |
|---|---|---|
| teal-950 | `#042E2C` | Texto sobre tinte |
| teal-900 | `#064440` | Presionado sobre relleno |
| teal-800 | `#075F5A` | **Relleno primario** (botones), texto blanco 7.5:1 |
| teal-700 | `#0B7770` | **Texto interactivo** y enlaces sobre blanco (5.3:1) |
| teal-600 | `#0F8F85` | Bordes, anillo de foco, trazos del lienzo (3.9:1, nunca texto chico) |
| teal-500 | `#20A79A` | Interactivo en tema oscuro |
| teal-400 | `#48BCAF` | Gráficos |
| teal-200/100/50 | `#B0E4DC` / `#D4EFEA` / `#E6F4F2` | Rellenos suaves, selección, tinte del vidrio |

| Naranja (la marca) | Hex | Rol |
|---|---|---|
| orange-700 | `#A84418` | Texto sobre tinte naranja |
| orange-500 | `#E56A32` | Marca + aviso de "requiere persona" + manijas de manipulación en el lienzo |
| orange-100 | `#FBEBE2` | Superficie de aviso |

**Semánticos** (texto siempre con ≥ 4.5:1 sobre su fondo suave)

| Rol | Base | Suave | Tinta |
|---|---|---|---|
| Correcto / en tolerancia | `#1E7A4C` | `#E3F2EA` | `#13502F` |
| Atención / restricción blanda | `#B25E09` | `#FDF1E3` | `#7A3D05` |
| Bloqueo / inválido / destructivo | `#B3372F` | `#FBE9E7` | `#7E1F19` |
| Información | teal-700 | teal-50 | teal-900 |
| Requiere persona (fabricación) | orange-500 | orange-100 | orange-700 |

**Roles funcionales (claro):** `bg-app` g-50 · `surface-panel` g-25 · `surface-card` g-100 · `surface-sheet` paper · `surface-hover` `#E2E8E7` · `surface-active` `#D4DEDD` · `surface-selected` teal-50 + barra izquierda de 2 px teal-700 · `border-subtle` g-200 · `border-default` g-300 · `border-strong` `#A9B4B6` · `border-focus` teal-600 · `text-primary` g-950 · `text-secondary` g-700 · `text-muted` g-500 · `interactive` teal-700 · `interactive-fill` teal-800 (hover teal-700, presionado teal-900) · `mark` orange-500.

**Tema oscuro (roles):** `bg-app` `#0F1416` · `surface-panel` `#151B1E` · `surface-card` `#1B2326` · `surface-sheet` `#182024` (el lienzo; los documentos impresos son siempre claros) · `border-subtle` `#243033` · `border-default` `#2F3C3F` · `text-primary` `#E7EDEC` · `text-secondary` `#AEB9BB` · `text-muted` `#86928F` · `interactive` teal-400 · `interactive-fill` teal-500 con texto g-950 · `mark` orange-400 `#ED8653`. **La densidad `workshop` usa el tema oscuro por defecto.** Ambos temas pasan el test de contraste AA.

**Lienzo:** hoja `paper` sobre `bg-app` · grilla `#DCE4E2` · perfil g-950 de 1,5 px · cotas g-700 en Plex Mono 11 · vidrio `rgba(15,143,133,.07)` con trazo teal-600 · símbolo de apertura g-700 de 1,25 px (continuo = hacia el observador, discontinuo = alejándose) · selección teal-600 1,5 px + 8 % de relleno · manija orange-500 con borde paper · ajuste (snap) verde discontinuo `6 4` · vista previa orange-500 discontinua `8 5` · inválido = color de bloqueo + achurado a 45° (legible sin color).

### 3.2 Tipografía: una superfamilia, dos voces

**IBM Plex Sans** habla de interfaz. **IBM Plex Mono** habla de medidas. Se autoalojan (WOFF2, subconjunto latino, `font-display: swap`). La familia actual se reemplaza.

| Rol | Especificación | Uso |
|---|---|---|
| Display | Sans SemiBold 32/36, −1 % | Títulos de documento, héroe de estado vacío |
| Título L | Sans SemiBold 20/26 | Título de página y de diálogo |
| Título M | Sans SemiBold 14/18 | Encabezado de panel y de grupo |
| Etiqueta técnica | Sans Medium 11/14, MAYÚSCULAS, +6 % | Etiquetas de campo, encabezados de tabla: la voz de lámina técnica |
| Cuerpo | Sans Regular 13/18 (`office`) · 14/20 (`document`) · 16/22 (`workshop`) | Texto de interfaz |
| Celda densa | Sans Regular 12/16 | Filas de tabla densa, texto secundario de lista |
| **Medida** | **Mono Regular 13/16** | Toda magnitud: `2 400 × 1 800 mm`, `$1.435.471`, cantidades, códigos |
| Micro-medida | Mono Regular 11/14, g-500 | Tolerancias, coordenadas, huellas |

Reglas:
- **Mínimo absoluto: 11 px.** Nada visible bajo 11 px.
- Pesos 400, 500 y 600 en la app. **El 700 vive solo en el papel** (total del documento). El producto nunca grita.
- `font-variant-numeric: tabular-nums` es obligatorio donde haya números que se alinean o cambian.
- Glifos reales: `×` (no `x`), `−` (no `-`) para negativos, `²`, `°`, `·`. Comillas «» o “” en el copy, nunca `"`.

### 3.3 Números y unidades (decisión cerrada)

| Magnitud | Formato | Ejemplo |
|---|---|---|
| **Medidas en mm** (cotas, cortes, vanos) | Enteros, **espacio fino** (U+2009) como separador de miles, unidad en minúscula al 85 % y en g-500 | `2 400 × 1 800 mm` |
| Medidas con precisión declarada | Coma decimal según la autoridad | `1 249,5 mm` |
| **CLP** | `$` + punto de miles, sin decimales | `$1.435.471` |
| USD / UF | 2 decimales / 4 decimales si la autoridad lo declara | `US$ 1.234,50` · `UF 38,4521` |
| Porcentaje | 1 decimal, coma | `32,5 %` |
| Área | 2 decimales | `2,16 m²` |
| Peso | 1 decimal | `38,4 kg` |
| Uw / Ug | 2 decimales | `1,40 W/m²K` |
| Fecha | `dd-mm-aaaa`, America/Santiago; relativa en listas con la absoluta en tooltip | `04-10-2026` · `hace 2 h` |

*Por qué el espacio fino en medidas:* es la convención ISO del dibujo técnico, no se confunde con la coma decimal y separa visualmente el mundo de la ingeniería (mm) del mundo comercial (pesos). Es una decisión deliberada y se aplica en todas partes: lienzo, tablas, documentos, etiquetas y la IA.

### 3.4 Espaciado, radios, elevación y capas

**Espaciado (base 4):** `2 · 4 · 6 · 8 · 12 · 16 · 24 · 32 · 48 · 64`. No hay excepciones de 10, 14 ni 18 px. Si un ajuste óptico es necesario, se anota en el PR.

| Contexto | Valor |
|---|---|
| Alto de control | 28 denso · 32 por defecto · **44 en `workshop`** (y en el portal móvil) |
| Fila de inspector | 28 |
| Relleno de panel | 12–16 (nunca 24 dentro de un riel) |
| Rieles | Inspector 300–320 · árbol de proyecto 240–280 · franja de herramientas 48 |
| Densidad objetivo | El inspector muestra **≥ 8 campos sin scroll** a 768 px de alto |

**Radios (mecanizados, no blandos):** `r-0` 0 (lienzo, hoja, celdas, geometría) · `r-1` 2 px (inputs, botones, chips) · `r-2` 4 px (paneles, diálogos, popovers: **máximo dentro del producto**) · `r-pill` solo para puntos de estado. **Prohibido ≥ 8 px dentro del producto.** Prohibidos los botones píldora.

**Firma: la esquina en inglete.** Una única esquina recortada a 45° (catetos de 8 px, arriba a la derecha, `clip-path`) aparece **solo** en superficies tipo hoja: el lienzo, los documentos emitidos, la tarjeta de vista previa principal y la marca. Nunca en controles, nunca más de una por superficie. Una lee como unión; varias leen como decoración.

**Elevación por delineado, no por sombra:**

| Nivel | Mecánica | Uso |
|---|---|---|
| E0 | `bg-app` plano | Mesa de trabajo |
| E1 | 1 px `border-subtle`, sin sombra | Paneles, inspector, tarjetas (**por defecto**) |
| E2 | Borde + `0 1px 2px rgb(22 28 31/5%), 0 4px 12px rgb(22 28 31/8%)` | Menús, popovers, tooltips |
| E3 | Borde + `0 2px 6px rgb(22 28 31/6%), 0 12px 32px rgb(22 28 31/14%)` | Diálogos, paleta de comandos, fantasma de arrastre |
| Hoja | paper + 1 px `border-default` + `0 1px 3px rgb(22 28 31/7%)` | Solo lienzo y documento |

Una sola capa flotante a la vez. Prohibidos: sombras de color, desenfoque, `backdrop-filter`, resplandor interior.

**Capas (z-index):** base 0 · sticky 10 · riel 20 · popover 40 · drawer 50 · diálogo 60 · toast 70 · paleta de comandos 80. Prohibidos los literales fuera de esta escala.

### 3.5 Movimiento: ensamblar, no animar

| Token | Valor | Uso |
|---|---|---|
| `t-micro` | 90 ms | Hover |
| `t-state` | 160 ms | Presionar, alternar, seleccionar |
| `t-spatial` | 220 ms | Paneles, diálogos, pestañas |
| `t-max` | **280 ms** | Techo absoluto |

Entradas `cubic-bezier(.2,0,.38,1)`; salidas `cubic-bezier(.4,.14,1,1)` en ≤ 120 ms. **Movimiento en un solo eje**: las superficies *calzan* en su lugar, como un perfil en su unión. Zoom y paneo del lienzo son directos (1:1). Desfase escalonado ≤ 30 ms × ≤ 3 elementos. `prefers-reduced-motion` desactiva todo lo no esencial. Prohibidos: rebote, elástico, transiciones con blur, degradados animados, *shimmer* en los esqueletos y spinners decorativos. **El cargador es una cota que se dibuja de 0 a 100 %.**

### 3.6 Iconografía: gramática de fenestración

- Monolínea de 1,5 px en grilla de 24 px, margen de 2 px, **puntas cuadradas y uniones en inglete**. El estado activo cambia trazo por relleno, nunca agrega un fondo de color.
- La familia de aperturas usa la convención de dibujo real: la línea parte de las esquinas del lado de las bisagras y el vértice apunta a la manilla; continuo = hacia el observador, discontinuo = alejándose; abatimiento desde abajo; oscilobatiente = ambos símbolos; corredera = flecha paralela al carril; fijo = silencio (sin símbolo). **Es la misma gramática en ícono, lienzo, documento y 3D.** El usuario la aprende una vez.
- Vocabulario propio: montante, travesaño, acople, junquillo, sección de perfil, cota, lista de corte, tronzadora, manilla, bisagra, soldadura. Los herrajes se dibujan seccionados, no como siluetas.
- Una sola librería base para lo genérico (la que ya use el repo), restilizada al trazo y las uniones de arriba. Prohibidos: íconos rellenos tipo blob, emoji, perspectiva y degradados.

### 3.7 Densidades

`data-density` en el contenedor raíz de cada superficie:

| Densidad | Superficies | Base | Control | Tema |
|---|---|---|---|---|
| `office` | Hoy, proyectos, editor, precios, compras, catálogo, ajustes, analítica | 13 px | 28–32 | Claro (oscuro opcional) |
| `workshop` | Estación de operario, kiosko de taller, app de instalador | 16 px | **≥ 44** | **Oscuro** |
| `document` | Portal del cliente, vistas imprimibles, PDF | 14 px | 40 (portal) | Claro siempre |

### 3.8 Retícula y puntos de quiebre

Diseño a **1440 × 900**. Debe funcionar sin scroll horizontal a 1280 × 800 y 1024 × 768. Las superficies `workshop` y `document` funcionan a 390 × 844. Bajo 1280, los rieles laterales se pliegan a íconos y pasan a un *drawer*; el lienzo nunca baja del 55 % del ancho.

---

## 4. Voz y microcopy

- **Español de Chile, profesional y directo.** La interfaz interna **tutea** con verbos en imperativo ("Emitir cotización", "Completar peso"). Los documentos y el portal del cliente tratan de **usted**.
- **Fórmula de un error:** qué pasó + por qué + qué hacer. *"No se puede emitir: la posición 4 no tiene vidrio. Elige un vidrio en la posición 4."* Con un botón que lleva exactamente ahí.
- **Fórmula de una confirmación:** pregunta de ficha técnica + consecuencia. *"¿Aplicar termopanel 5-12-5 a 3 posiciones? El total sube $84.300."*
- **Prohibido:** signos de exclamación, emoji, "¡Genial!", "¡Ups!", "Algo salió mal", palabras en inglés en la UI, MAYÚSCULAS para enfatizar, "Por favor" repetido, jerga de marketing, "ítem" o "elemento" donde existe la palabra del taller.
- **Estados vacíos:** dicen por qué está vacío y ofrecen **una** acción. *"Este proyecto aún no tiene posiciones. Agrega la primera ventana o importa una planilla de vanos."*
- **Números en el texto:** siempre con su formato (§3.3) y su fuente si son calculados.

**Glosario canónico (usar · no usar)**

| Usar | No usar |
|---|---|
| Posición | Ítem, línea, producto (en contexto de obra) |
| Hoja · Marco · Junquillo · Montante · Travesaño · Inversor · Umbral | SASH, FRAME, GLAZING_BEAD, poste, mainel |
| Termopanel (DVH) · Laminado · Templado | Doble vidrio, IGU |
| Abatible · Oscilobatiente · Proyectante · Corredera · Fijo | Batiente (salvo que el catálogo lo use), tilt-turn |
| Vano · Medida de fabricación · Holgura | Hueco, tamaño |
| Cotización · Revisión · Emitir | Presupuesto (salvo preferencia del cliente), versión, publicar |
| Orden de trabajo (OT) · Estación · Lote | Job, tarea, ticket |
| Sin dato | N/A, null, —, 0 |

---

## 5. Superficies: anatomía obligatoria

### 5.1 Shell
Barra superior de 48 px: marca, búsqueda/paleta de comandos (`Ctrl+K`), Orb, usuario. Navegación por **flujo** (Hoy · Proyectos · Producción · Compras · Catálogo · Clientes · Analítica · Ajustes), no por tablas de la base de datos. Las migas muestran la entidad con su código (`P-000123 · Edificio Los Robles`). Un solo nivel de navegación lateral.

### 5.2 Hoy (inicio por rol)
No es un dashboard: es **la lista de lo que esta persona debe hacer ahora**, ordenada por consecuencia. Estimador: cotizaciones por vencer, aprobaciones pendientes, posiciones bloqueadas. Dueño: margen de la semana vs. objetivo, cobranza vencida, cuellos de botella. Taller: OT de hoy por estación, faltantes. Cada fila tiene un verbo. Sin contadores en 0 decorativos.

### 5.3 Proyecto
Encabezado con la entidad, el estado del ciclo de vida (Stepper) y **una** acción principal según el estado. Debajo, la lista de posiciones con miniatura del dibujo real, medidas, tipología, vidrio, cantidad, precio y estado "Qué falta". Selección múltiple con cambios en lote y diff de precio antes de aplicar.

### 5.4 Editor (canvas-first)
Lienzo de borde a borde con **islas flotantes**: herramientas arriba al centro, zoom abajo a la izquierda, acciones abajo al centro, estado de selección en una línea. Inspector acoplado a la derecha (300–320 px) que **cambia según la selección**, con lo más usado primero y "Avanzado" plegado. Cotas encadenadas editables en el lugar. Vista en planta con carriles para correderas. "Qué falta" como lista accionable, no como banners. Atajos de teclado según el estudio de interacción (`V`, `H`, `F`, `Shift+1`, `Ctrl+K`, etc.).

### 5.5 Tablas
Reglas finas, **sin cebra**, encabezado fijo con etiqueta técnica, números alineados a la derecha en Mono, orden y filtro, selección con barra de acciones en lote, virtualización sobre 200 filas, estados vacío/carga/error.

### 5.6 Formularios
Etiqueta arriba, ayuda breve debajo, error en español debajo del campo, unidad como sufijo. `noValidate` siempre. Un formulario largo se divide por secciones con títulos, nunca en un muro. Lo que se puede derivar no se pide.

### 5.7 Los cinco estados (obligatorios en toda superficie)
**Vacío** (por qué + una acción) · **Cargando** (esqueleto con la forma real, sin shimmer; cargador de cota si dura > 1 s) · **Error** (fórmula del §4 + "Detalles técnicos" plegable + reintentar) · **Sin permiso** (qué rol lo puede hacer y a quién pedírselo) · **Bloqueado** (qué falta, quién lo resuelve, botón al lugar exacto).

### 5.8 Documentos (DOC-01 y siguientes)
Hoja de lámina técnica: cabecera con la marca de la empresa del cliente (white-label), filete teal-800 de 1,5 pt, la esquina en inglete y el **cajetín** (estilo ISO 7200) al pie con proyecto · documento · número · revisión · fecha · página · **huella de la BOM**. Cada posición es una ficha: elevación a la izquierda (vista declarada, simbología del §3.6) y tabla de especificación a la derecha. Totales con un único momento fuerte por página. Sin cebra. Carta por defecto.

### 5.9 Portal del cliente
Una página que vende con autoridad: portada con la obra, resumen de lo que compra en lenguaje simple, posiciones con dibujo y opción de ver en 3D, alternativas comparables, condiciones claras, **una** acción (Aprobar) y el estado honesto del enlace (vigente, reemplazado, vencido, revocado). Funciona perfecto en 390 px.

### 5.10 Taller y obra (`workshop`)
**Una pieza, una pantalla.** Código grande (≥ 32 px Mono), qué hacer, medida, destino, siguiente. Botones de ≥ 44 px (idealmente 56). Escaneo de etiqueta como entrada principal. Funciona con guantes y a 2 m. Confirmaciones táctiles inequívocas, sin gestos ocultos.

### 5.11 Asistente y Orb
El Orb es un indicador de estado real (inactivo, escuchando, pensando, trabajando, esperando confirmación, listo, error) conectado a trabajos reales. El panel del asistente muestra **artefactos** (propuesta de cambios con antes/después, plan de compra, comparación), no solo texto. Estados visibles y distintos: **propuesto · en vista previa · esperando confirmación · aplicado · falló · bloqueado.** Nunca dice "listo" si no aplicó.

---

## 6. Patrones de interacción transversales

- **Paleta de comandos** (`Ctrl+K`): navegar, crear, ejecutar operaciones del registro tipado (las mismas que usa la IA) y buscar entidades por código.
- **Deshacer siempre:** toda edición en el editor y en lote es deshacible (`Ctrl+Z`) hasta guardar; las acciones consecuentes piden confirmación explícita.
- **Vista previa antes de aplicar:** cambios en lote, propuestas de la IA, importaciones y emisiones muestran el diff (qué cambia, cuánto cambia el precio) antes del clic.
- **"¿De dónde sale?"**: cualquier número calculado abre una traza breve (fórmula, entradas, autoridad del catálogo, versión del motor).
- **Foco visible** de 2 px teal-600 con 1 px de separación en todo elemento interactivo; orden de tabulación lógico; todo es operable por teclado.
- **Accesibilidad:** AA en ambos temas, objetivos ≥ 24 px en `office` y ≥ 44 px en `workshop`, `aria-label` en todo botón de ícono, sin información transmitida solo por color.

---

## 7. Momentos de firma (proteger lo extraño)

Son lo que hace que DEKOPEN no se parezca a nada más. **No se quitan por "limpieza"**. Si un encargo toca una superficie que tiene uno, debe preservarlo o mejorarlo.

| # | Momento | Dónde | Por qué importa |
|---|---|---|---|
| F1 | **La esquina en inglete** | Lienzo, documentos, tarjeta de vista previa, marca | La hoja está cortada como el marco que cotiza |
| F2 | **La huella en el cajetín** | Todo documento emitido, etiquetas, OT | La autoridad congelada se vuelve visible, como un número de plano |
| F3 | **El cargador de cota** | Toda espera > 1 s | Esperar se ve como medir |
| F4 | **La cota editable en el lugar** | Editor, vista de proyecto | Se cambia la medida donde se lee |
| F5 | **La franja de planta con carriles** | Editor y documento de correderas | Las correderas se entienden por fin |
| F6 | **"¿De dónde sale?"** | Todo número calculado | "Confío en los números" deja de ser una promesa |
| F7 | **Naranja = requiere persona** | Lienzo, OT, documentos | Un color con un único significado |
| F8 | **El Orb conectado a trabajos reales** | Shell, asistente, artefactos | La IA tiene presencia y honestidad |
| F9 | **Una pieza, una pantalla** | Estación de taller | El operario no lee: mira y actúa |
| F10 | **La sección de perfil en la marca** | Marca, favicon, etiquetas | `DEK⧈PEN`: la O es el producto (dirección B del estudio de identidad) |
| F11 | **El sello de revisión** | Cotizaciones emitidas, portal | Lo emitido no se toca; se revisa |

---

## 8. Subir el techo: lo que la competencia no hace

Cada superficie debe tener **al menos una** capacidad que vaya más allá de lo evidente. Siempre respaldada por el motor, nunca de adorno.

| Superficie | Idea que sube el techo |
|---|---|
| Editor | Escribir "partir en tres, centro fijo" en la paleta y ver la propuesta dibujada antes de aplicar; las cotas responden como en Shapr3D |
| Proyecto | Cambio global con diff: "todo el 2º piso a termopanel Low-E" → lista de posiciones afectadas + Δ de precio + Δ de Uw antes de aplicar |
| Precios | Cascada viva del costo al precio con banda de margen; mover el margen muestra el efecto en la utilidad de la obra, no solo en el total |
| Cotización | Checklist "Qué falta para emitir" que se cumple sola a medida que se completa; vista previa real del PDF antes de emitir |
| Portal | El cliente compara alternativas lado a lado (A: PVC blanco / B: foliado nogal) con el dibujo y el precio de cada una, y aprueba la que elige |
| Producción | Plan de corte que muestra cada barra con sus piezas y el destino del retazo; la estación dice qué cortar a continuación |
| Compras | "Comprar lo que falta" calcula contra stock y retazos, agrupa por proveedor y deja la orden lista para enviar con un clic |
| Instalación | El instalador ve en el celular la posición, su ubicación en la obra, qué llevar y cierra con foto y firma |
| Analítica | Margen real vs. cotizado por obra, con la causa de la diferencia (merma, remake, horas) |
| IA | Un pedido en lenguaje natural produce un plan de operaciones tipadas, una simulación con el motor y un diff aplicable; si falta un dato, pregunta con opciones |

---

## 9. El pase editorial (terminado ≠ bueno)

### 9.1 Definición

- **Terminado:** compila, los tests pasan, la pantalla existe.
- **Bueno:** un usuario real completa el flujo más rápido que con su herramienta actual, sin dudar de un número, sin encontrar un estado roto y sin un solo detalle arbitrario.

**Ningún PR se entrega en "terminado".** Antes de entregar, el autor hace el pase editorial y lo documenta en el PR.

### 9.2 Cómo se hace

1. **Recorre el flujo completo** de la superficie con datos realistas, como la persona del §1.2 (no solo la pantalla tocada: de dónde viene el usuario y adónde va después).
2. **Para cada elemento visible pregunta:** ¿justifica su existencia? ¿Si lo quito, algo empeora? Si la respuesta es no, **se quita**.
3. **Pasa la rúbrica** (§9.3) en 1440 claro y oscuro, en 1024 y, si aplica, en 390. Todo ítem que falle se corrige antes de entregar.
4. **Tres veces mejor:** identifica las 3 cosas más débiles que quedan y mejóralas. Repite una vez más.
5. **Documenta** en el PR la tabla de la rúbrica con PASA/FALLA, capturas de antes y después, lo que se quitó y por qué, y el momento de firma y la idea del §8 que la superficie implementa.

### 9.3 Rúbrica (todo debe pasar)

| # | Revisión | Falla si… |
|---|---|---|
| R1 | Números en Mono tabular, con unidad y formato del §3.3 | Dígitos proporcionales, `x` por `×`, sin unidad, `.00` sobrantes |
| R2 | Radios ≤ 4 px; inglete solo en hojas | Tarjetas de 8–16 px, botones píldora |
| R3 | Jerarquía por borde, peso y espacio; ≤ 1 superficie flotante | Sombras grandes o de color, tarjetas sobre tarjetas, brillo |
| R4 | Naranja solo como marca o "requiere persona", ≤ 3 % de píxeles | Naranja en CTA, insignias decorativas |
| R5 | Teal como único croma del cromo | Colores aleatorios por módulo |
| R6 | Vocabulario del taller y voz del §4 | Enums, inglés, "ítem", exclamaciones, emoji |
| R7 | Densidad: inspector ≥ 8 campos sin scroll a 768 px | Páginas de relleno, controles de 48 px en escritorio |
| R8 | Estados explícitos con texto y causa; los 5 estados existen | Puntos de color sin texto, estados faltantes |
| R9 | El lienzo/documento es papel sobre mesa | Lienzo y cromo del mismo gris |
| R10 | Selección = contorno + tinte + manijas | Brillo al pasar el mouse, tarjetas que se elevan |
| R11 | Íconos monolínea 1,5 px, simbología de apertura correcta | Íconos mixtos, rellenos, símbolo de apertura erróneo |
| R12 | Foco visible en todo; operable por teclado | Sin foco o anillo azul del navegador |
| R13 | Movimiento ≤ 280 ms en un eje; reduce-motion respetado | Rebote, fade-up escalonado, shimmer |
| R14 | Una acción principal por región | Varios primarios compitiendo |
| R15 | Cada número calculado tiene fuente; lo desconocido dice "Sin dato" | Ceros falsos, valores inventados |
| R16 | **Cero degradados, cero blur, cero brillo, cero morado IA** | Cualquiera = falla automática |
| R17 | Sin scroll horizontal y nada cortado en los anchos exigidos | Desbordes, textos truncados sin tooltip |
| R18 | Nada muerto: sin botones sin efecto, sin código viejo paralelo | Botones decorativos, componentes duplicados |
| R19 | La superficie conserva o implementa su momento de firma (§7) | Lo singular se quitó "por limpieza" |
| R20 | La idea del §8 funciona de verdad, con el motor | Una maqueta que no hace nada |

### 9.4 Señales de "AI slop" (eliminar en el acto)

- Tarjetas idénticas en grilla para contenido que no es una colección.
- KPI decorativos sin decisión asociada.
- Copy genérico ("Gestiona tus proyectos de forma fácil y rápida").
- Íconos puestos "para rellenar" junto a cada título.
- Espaciados distintos entre secciones equivalentes.
- Dos componentes que hacen lo mismo con estilos distintos.
- Ilustraciones genéricas de personas o de nubes.
- Textos de relleno, lorem ipsum, "Próximamente".
- Un modal para algo que cabe en el inspector.
- Explicaciones que repiten lo que la interfaz ya muestra.

---

## 10. Cómo se codifica (para que no dependa de la memoria de nadie)

| Estándar | Mecanismo (P01, salvo que se indique otro) |
|---|---|
| Colores, tipos, espacios, radios, sombras, capas, movimiento | Tokens en `tokens.css`; test que falla con `var()` sin definir |
| Contraste AA | Test que calcula cada par texto/fondo en ambos temas |
| Hex inline, `border-radius` > 4 px, `box-shadow` fuera de tokens, `linear-gradient`/`radial-gradient`, `backdrop-filter`, `font-weight: 700` en la app, `transition` > 280 ms, `z-index` literal, `font-size` < 11 px, `.toFixed(` para mostrar, `pattern=` | Guardas con trinquete en `scripts/check_guards.py` (`make lint`) |
| Enums visibles | Test de exhaustividad de `domainLabels` contra el cliente generado |
| Formatos de número | Formateadores únicos con tests (`<Dims>`, `<Money>`, …) |
| UUID, hex, enums, inglés, exclamaciones, emoji, "MOCK", desbordes, fuente < 11 px, objetivos < 44 px en `workshop`, varios primarios por región, sombras/radios/degradados computados fuera de norma | Detectores de `ux:capture` (P00 + P01) sobre la app en vivo |
| Rúbrica del §9.3 | Plantilla de PR (`.github/pull_request_template.md`) con la tabla obligatoria |
| Muestrario | `/dev/ui` con todas las primitivas en ambos temas y las tres densidades |

---

## 11. Decisiones por defecto (el dueño puede cambiarlas después)

Los encargos **no se detienen** por estas decisiones: usan el valor por defecto, lo hacen **configurable en Ajustes** y lo registran en `docs/decisions/valores-por-defecto.md`.

| Decisión | Valor por defecto | Dónde se cambia |
|---|---|---|
| Papel de los documentos | **Carta** | Ajustes › Documentos |
| Anticipo | 50 % al aprobar, saldo contra entrega | Ajustes › Condiciones comerciales |
| Validez de la cotización | 15 días corridos | Ajustes › Condiciones comerciales |
| Garantía | Texto plantilla editable, sin plazo inventado: "[completar plazo]" visible solo en Ajustes, nunca impreso vacío | Ajustes › Condiciones comerciales |
| Plazo de entrega | Calculado desde la carga de producción si existe; si no, campo obligatorio por cotización | Cotización |
| Banda de margen | Objetivo 35 %, mínimo 25 %; bajo el mínimo requiere aprobación del dueño | Ajustes › Precios |
| IVA | 19 %, precios netos en la app y total con IVA en el documento | Ajustes › Impuestos |
| Pie "Generado con DEKOPEN" | **Oculto** en documentos del cliente (white-label); visible solo en el portal, discreto | Ajustes › Documentos |
| Nombre del asistente | "Asistente DEKOPEN" con el Orb. **No se usa "STARWIN"** (era una imagen de referencia) | Ajustes › Marca |
| Marca de la app | Dirección B del estudio de identidad (`DEK⧈PEN`) | P25 |
| Moneda | CLP; USD y UF opcionales | Ajustes › Moneda |
| Catálogo | Demo con precios aleatorios de semilla fija, marcado DEMO en todas partes | Catálogo › Importar |

---

## 12. Referencias y qué tomar de cada una

| Referencia | Tomar | No tomar |
|---|---|---|
| Linear | Paleta de comandos, atajos, densidad, velocidad percibida | Su estética morada |
| tldraw / Excalidraw | Islas flotantes, panel de estilo, menú de zoom, minimapa | El trazo a mano alzada |
| Shapr3D | Cotas editables en el lugar | — |
| Moxisys | Lienzo grande, cotas encadenadas, franja en planta con carriles | Su cromo recargado |
| Orgadata / LogiKal (Musterangebot) | Ficha por posición con vista declarada, vidrio con composición y U, accesorios como sublíneas | La densidad tipográfica de los 90 |
| Windowmaker Web | Cambios globales, cotización interactiva con 3D | — |
| FeneCAM / Stolcad | Corte en secuencia, destino del retazo, etiquetas | — |
| PandaDoc / Qwilr | La propuesta web que vende | Plantillas de marketing genéricas |
| Manuales técnicos Schüco / Reynaers | La autoridad visual: líneas finas, secciones, números | Su maquetación impresa en pantalla |
| Dieter Rams / Otl Aicher | "Menos, pero mejor"; la identidad extraída del producto | La nostalgia |
