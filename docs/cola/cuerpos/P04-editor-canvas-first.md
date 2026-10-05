# P04 — Editor de posición “canvas-first”: layout e interacción profesional

**Depende de:** P01, D02 (vidrios), D03 (aperturas), D05 (colores) y P05 (dibujo). El selector de apertura, el de vidrio y el de color consumen las capacidades que esos encargos exponen; si alguno no está mergeado, usa lo que exista y no inventes opciones. Puede correr en paralelo con P05 (P04 se ocupa de layout e interacción; P05, de la geometría de los símbolos). **No toques** la lógica de glifos de `ProductFrontSvg.tsx` ni `backend/documents/renderers.py`.

## Objetivo
El editor es la superficie que define el producto. Tiene que sentirse como una herramienta CAD de oficio técnico: el dibujo en el centro y protagonista, medidas editables sobre el propio dibujo, herramientas con nombre y un inspector que muestra solo lo que importa de la selección. La primera reacción esperada del usuario es: *“esto entiende de ventanas”*.

## Situación actual
- Archivos: `frontend/src/features/canvas/` (`CanvasEditor2DView.tsx`, `CanvasViewport.tsx`, `CADViewportSvg.tsx`, `EditableDimension.tsx`, `ObjectTree.tsx`, `StarterGallery.tsx`, `designLibrary.ts`, `productEditing.ts`, `intentEditing.ts`, `canvasStore.ts`, `snapping.ts`, `viewport.ts`, `canvas.css`), `frontend/src/features/projects/ProjectPositionEditor.tsx` y `frontend/src/features/inspector/`.
- (auditoría, varias sesiones) Antes del lienzo se apilan campos de ancho completo (Ubicación, Cantidad, Serie de perfiles, Acabado), un acordeón “Biblioteca de diseños” y un banner naranja largo (“No se puede guardar todavía…”). Resultado: a 1440×900 el lienzo ocupa apenas el tercio inferior de la pantalla.
- (auditoría) A 1366 la vista en planta se superpone; a 768 el lienzo desaparece; el pan con rueda puede dejar el dibujo fuera de vista sin forma obvia de volver; el riel de herramientas tiene íconos diminutos sin etiqueta; la paleta de aperturas es una grilla de glifos sin nombre (>, <, V, #, +); hay un enlace que no responde cuando hay cambios sin guardar (sesión 9e41dc53 “p3-dirty-link-dead-click”); y el árbol “Árbol del conjunto” es diminuto.
- Ya existen operaciones tipadas con deshacer y rehacer, un guard de cambios sin guardar (`app/UnsavedChangesGuard.tsx`) y `EditableDimension.tsx`. **Úsalos; no crees otra vía de mutación.**

## Diseño objetivo (≥ 1280 px)
- **Franja superior (≈ 48 px):** migas (Proyecto › Pos. 03), nombre o ubicación editable en línea, cantidad, y **chips** de Serie y Acabado que abren un popover. A la derecha: estado de guardado (“Guardado” o “Cambios sin guardar”), Deshacer/Rehacer, **chip de precio en vivo** (neto unitario y total de línea, ambos del motor) y **chip de estado** (“Válido” · “2 avisos” · “Bloqueado”) que abre el panel “Qué falta”. Ese panel reemplaza el banner naranja: cada ítem explica el problema en lenguaje de taller, propone una acción y enlaza al campo.
- **Izquierda: riel de herramientas con etiquetas** (Seleccionar, Dividir vertical, Dividir horizontal, Apertura, Vidrio, Acoplar, Medir), con tooltip y atajo. La **biblioteca de tipologías** es un flyout agrupado (Fijos, Abatibles, Oscilobatientes, Correderas, Proyectantes, Puertas, Conjuntos) con miniaturas dibujadas por el renderer real; solo muestra las tipologías que el sistema elegido admite, según el catálogo y el motor, nunca una lista fija.
- **Centro: lienzo** con al menos el 60 % del ancho y el 75 % del alto del viewport. Al abrir, “Ajustar a pantalla”. Zoom con rueda centrado en el cursor y pan con espacio + arrastre o con el botón medio. El pan queda **acotado**: el dibujo no puede salir por completo de la vista y siempre hay un botón “Centrar”. Selectores de vista: Interior/Exterior, Comercial/Técnica, 2D/3D y Planta (si aplica).
- **Derecha: inspector (320–360 px)** con secciones que dependen de la selección:
  - Medidas: ancho y alto, más las cotas parciales de la bahía.
  - Apertura: selector visual **con nombre**, por ejemplo “Abatible — bisagras a la izquierda”, “Oscilobatiente — manilla a la derecha” o “Corredera — hoja izquierda móvil”.
  - Vidrio: composición, por ejemplo 4-16-4.
  - Manilla: altura en mm; el lado lo deriva el motor.
  - Herrajes: kit derivado, de solo lectura.
  - “Avanzado”, plegado: roles de perfil, refuerzo y procedencia.
- **Abajo, plegable:** árbol del conjunto y tira de posiciones del proyecto para saltar entre ellas.

## Interacción
- Clic en una bahía la selecciona; doble clic abre el selector de apertura. Clic en una cota abre un input **en el lugar**: Enter confirma con la misma operación tipada que usa el inspector y Esc cancela.
- Teclado: V (seleccionar), | y – (dividir), Ctrl+Z / Ctrl+Y, Supr, flechas (mueven divisores 1 mm; con Shift, 10 mm), F (ajustar) y ? (atajos).
- Los cambios se recalculan con el motor (`useEngineCalculation`) con debounce y sin bloquear la UI; mientras tanto el precio muestra un estado “calculando”, nunca un número viejo sin indicarlo.
- **1024–1279 px:** el inspector pasa a drawer y el riel queda solo con íconos y tooltip. **Menos de 1024 px:** vista de lectura con medidas, precio y un aviso de “edición disponible desde 1024 px”. Tablet horizontal (1024×768) totalmente usable.

## Fuera de alcance
Símbolos y cotas técnicas (P05), edición de bow en planta (P06), 3D (P19) y lógica de precios.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador, 30 a 80 posiciones por obra, con presión de plazo. Debe sentir: “esto entiende ventanas y es más rápido que mi software”.
- **Anatomía:** Constitución §5.4 y estudio de interacción: lienzo de borde a borde (≥ 60 % del ancho) con islas flotantes, inspector acoplado de 300–320 px según la selección, cotas encadenadas editables en el lugar, vista en planta, atajos (`V`, `H`, `F`, `Shift+1`, `Shift+2`, `Ctrl+K`). Básico arriba, “Avanzado” plegado.
- **Momento de firma (preservar o crear):** F1 (lienzo como hoja con inglete sobre la mesa), F4 (cota editable en el lugar), F5 (franja de planta con carriles), F7 (manijas naranjas = manipulación).
- **Idea que sube el techo (obligatoria, con el motor):** Escribir en la paleta “partir en tres, centro fijo, laterales abatibles hacia el centro” muestra la propuesta dibujada en fantasma naranja con el Δ de precio antes de aplicar (operaciones del registro de IA2, sin IA si la frase es un comando directo).
- **Slop a eliminar aquí:** Formularios de ancho completo sobre el dibujo, encabezados dentro del lienzo, herramientas sin nombre ni atajo, banners de error en vez de “Qué falta”, modales para editar una medida.
- **Preguntas del pase editorial:** ¿Se puede diseñar una ventana completa sin tocar un formulario? ¿Un estimador nuevo encuentra cada herramienta sin preguntar? ¿El inspector muestra ≥ 8 campos a 768 px?

## Criterios de aceptación
- Test Playwright: a 1440×900 la caja del lienzo es ≥ 60 % del ancho y ≥ 75 % del alto del viewport; sin scroll horizontal entre 1024 y 1920.
- Desde una posición vacía, crear una “ventana de 2 hojas oscilobatientes, 1500 × 1200, vidrio 4-16-4” en **≤ 6 interacciones** (test e2e que las cuente).
- Pan extremo (10.000 px) → el dibujo sigue visible o se recentra (test).
- Todas las herramientas tienen etiqueta o tooltip y aria-label (test). El selector de apertura muestra nombres en español y solo opciones compatibles (test con un sistema que no admita corredera).
- El guard de cambios sin guardar funciona en todos los enlaces del editor, incluido el caso “dirty-link” (test).
- Los tests existentes de canvas y proyectos pasan, y hay capturas antes/después en 1440, 1280 y 1024, claro y oscuro.
