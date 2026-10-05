# P05 — Fidelidad del dibujo técnico 2D: símbolos, vista declarada, correderas por modelo, cotas y formas especiales

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
