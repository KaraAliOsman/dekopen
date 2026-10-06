# Simbología de aperturas — contrato de dibujo técnico (P05)

**Estado:** vigente — implementado por P05, congelado por los fixtures de
`engine/tests/fixtures/symbols/`.
**Dueños del contrato:** `engine/src/dekopen_engine/opening_symbols.py`
(autoridad) y `frontend/src/features/canvas/openingSymbols.ts` (gemelo
estricto). Toda divergencia entre ambos rompe los tests de paridad.

Este documento define la única gramática con la que DEKOPEN dibuja un
alzado. El objetivo: **cualquier tallerista lee un alzado DEKOPEN sin
leyenda privada** — la lectura es la convención DIN/EN-12519 que el rubro
ya conoce, en las tres superficies que dibujan (editor canvas, PDF de
documentos emitidos, portal público).

## 1. Reglas del contrato

1. **Hoja abatible = triángulo.** La BASE del triángulo es el canto con
   bisagras; el VÉRTICE toca el canto opuesto al **40 %** desde su inicio
   (`APEX_AT = 0.4`). El vértice marca la manilla. 40 %, no 50 %: el
   vértice asimétrico se lee como marca de plano, nunca como botón.
2. **Oscilobatiente = dos triángulos.** El de la bisagra lateral más el
   de la bisagra inferior (modo basculante). Ambos comparten el trazo.
3. **Proyectante (awning) = triángulo con base arriba.** En vista
   interior sale discontinuo — abre siempre hacia afuera.
4. **Hacia el observador = trazo continuo; alejándose = discontinuo.**
   `direction` se declara desde el interior (`INWARD`/`OUTWARD`); en
   vista interior `OUTWARD` se discontinúa. En vista exterior el patrón
   se invierte: `INWARD` se discontinúa porque abre alejándose del que
   mira desde fuera.
5. **Corredera = flecha horizontal paralela al carril**, en la dirección
   `travel` declarada del panel (`LEFT`/`RIGHT`). Nunca triángulo. Una
   hoja corrediza sin `travel` declarado dibuja la flecha igual pero con
   la marca **`dirección inferida`** (trazo atenuado): la dirección es la
   convención de presentación, no verdad de fabricación.
6. **Fijo = silencio.** Una hoja `FIXED` no dibuja símbolo: el cristal
   quieto no lleva marca. El fijo en hoja (`fixed_in_sash`) dibuja el
   contorno de su hoja pero ninguna marca de apertura.
7. **Puerta en alzado = triángulos + umbral.** El arco de barrido solo
   existe en la vista de planta, nunca en el alzado. La línea de umbral
   (acento naranjo `#E56A32`) corre bajo TODA hoja de puerta no fija —
   activa y pasiva pisan el mismo umbral; un paño fijo conserva su marco.
8. **Manilla = marca de cruz** sobre el canto libre (montante opuesto a
   la bisagra) a la cota `handle_height_mm` declarada, medida desde la
   línea de umbral del módulo. Sin `handle_height_mm` declarada no hay
   marca — nunca se inventa una cota.
9. **Vista declarada en toda elevación.** Todo alzado lleva la leyenda
   "Vista interior" o "Vista exterior". El cambio de vista es un espejo
   horizontal de la lámina completa (geometría + glifos) con la inversión
   de trazo del punto 4; el mobiliario del plano (cotas, leyendas, corte
   de planta) NO se espeja.
10. **`travel` es verdad de fabricación.** El motor valida: una hoja no
    puede viajar hacia una jamba sin espacio (slot 0→LEFT ni último
    slot→RIGHT son `SlidingLayoutError`), y dos paneles móviles
    adyacentes no comparten carril. El editor ofrece `travel` por panel
    con la opción "inferida" explícita — nunca un default silencioso.
11. **Trazo idéntico en las tres superficies.** Las cadenas `d` del path
    salen de `glyph_paths` (engine) / `glyphPaths` (canvas); los fixtures
    JSON congelan primitivas y paths por caso y vista. Si el canvas y el
    PDF dibujaran distinto, el test de paridad falla.

## 2. Casos congelados

Cada caso vive en `engine/tests/fixtures/symbols/<id>.json` con sus
primitivas y paths exactos en ambas vistas. Las ilustraciones de esta
tabla se generan con `scripts/gen_symbol_doc_assets.py` — son el engine
dibujando, no un dibujo a mano.

| Caso | Vista interior | Vista exterior |
|---|---|---|
| Fijo | ![fijo](assets/opening-symbols/fixed-interior.svg) | ![fijo](assets/opening-symbols/fixed-exterior.svg) |
| Abatible izq. | ![abi](assets/opening-symbols/casement-left-interior.svg) | ![abe](assets/opening-symbols/casement-left-exterior.svg) |
| Abatible izq. exterior | ![abio](assets/opening-symbols/casement-left-outward-interior.svg) | ![abeo](assets/opening-symbols/casement-left-outward-exterior.svg) |
| Abatible der. | ![abd](assets/opening-symbols/casement-right-interior.svg) | ![abde](assets/opening-symbols/casement-right-exterior.svg) |
| Oscilobatiente izq. | ![obi](assets/opening-symbols/tilt-turn-left-interior.svg) | ![obe](assets/opening-symbols/tilt-turn-left-exterior.svg) |
| Oscilobatiente der. | ![obd](assets/opening-symbols/tilt-turn-right-interior.svg) | ![obde](assets/opening-symbols/tilt-turn-right-exterior.svg) |
| Proyectante | ![pri](assets/opening-symbols/awning-interior.svg) | ![pre](assets/opening-symbols/awning-exterior.svg) |
| Puerta simple izq. | ![psi](assets/opening-symbols/door-single-left-interior.svg) | ![pse](assets/opening-symbols/door-single-left-exterior.svg) |
| Puerta doble | ![pdi](assets/opening-symbols/door-double-interior.svg) | ![pde](assets/opening-symbols/door-double-exterior.svg) |
| Corredera 2 hojas | ![c2i](assets/opening-symbols/sliding-2l-interior.svg) | ![c2e](assets/opening-symbols/sliding-2l-exterior.svg) |
| Corredera 2 hojas inferida | ![c2fi](assets/opening-symbols/sliding-2l-inferred-interior.svg) | ![c2fe](assets/opening-symbols/sliding-2l-inferred-exterior.svg) |
| Corredera 3 hojas | ![c3i](assets/opening-symbols/sliding-3l-interior.svg) | ![c3e](assets/opening-symbols/sliding-3l-exterior.svg) |
| Corredera 4 hojas | ![c4i](assets/opening-symbols/sliding-4l-interior.svg) | ![c4e](assets/opening-symbols/sliding-4l-exterior.svg) |
| Corredera O/X/X/O | ![oxxoi](assets/opening-symbols/sliding-oxxo-interior.svg) | ![oxxoe](assets/opening-symbols/sliding-oxxo-exterior.svg) |

## 3. Semántica de `track` y `travel`

`SlidingLayout.tracks` = cuántos rieles del marco ocupa la disposición.
`track` 0 es el riel MÁS EXTERIOR: en el corte de planta se dibuja arriba
(y el observador interior lo ve detrás de los paneles de rieles más
internos). `panels` lista los slots de izquierda a derecha en alzado
interior. Notación X/O: `MOVING` = X, `FIXED` = O — O/X/X/O es
`[FIXED, MOVING@0, MOVING@1, FIXED]` sobre 2 rieles.

`travel` (LEFT/RIGHT) nombra la jamba hacia la que viaja la hoja en vista
interior. Paneles guardados antes del contrato lo resuelven por la
convención documentada (`index*2 < count → RIGHT, si no LEFT`) y toda
superficie que dibuje la flecha la marca **dirección inferida**.

## 4. Superficies que consumen el contrato

| Superficie | Consumo | Vista |
|---|---|---|
| Editor canvas (`ProductFrontSvg.tsx`) | `OpeningGlyph` + selector interior/exterior + bloque "Simbología" | usuario |
| Iconos de producto (`ui/icons.tsx`) | `OpeningGlyph` icono 24px — mismo `glyphPaths` | interior/exterior por prop |
| PDF técnico (`backend/documents/renderers.py`) | `glyph_paths` por hoja + corte de planta bajo cada corredera | interior |
| `/dev/ui` — sección Firma | tabla completa del vocabulario | ambas |
| Portal | SVG emitido por el backend — hereda el contrato | interior |

## 5. Cotas del dibujo técnico

- **Cadena exterior** (total): ancho arriba, alto a la izquierda — mm
  enteros, `tabular-nums`.
- **Cadena interior por paño**: eje a eje de partidor bajo el alzado —
  solo en el nivel "técnico" del editor.
- **Cota de manilla**: marca de eje a `handle_height_mm` sobre el umbral
  del módulo, con el valor declarado.
- Las cotas no se solapan con el dibujo: viven en canaletas que el
  `viewBox`/bounds expanden.

## 6. Corte de planta de correderas

Bajo cada paño corredizo del alzado técnico se dibuja el corte: barra de
muro del lado EXTERIOR (arriba), un riel numerado por `track`, cada hoja
en su slot con su flecha de `travel`, y la etiqueta INTERIOR abajo. La
convención permite leer qué hoja pasa por delante sin abrir el 3D.

## 7. Anti-reglas

- Nunca un arco en alzado de puerta (eso es planta).
- Nunca un símbolo en hoja `FIXED`.
- Nunca una flecha corredera sin `dir` resuelto ni marca `inferred`.
- Nunca `direction` asumida — un producto antiguo sin `travel` muestra
  "dirección inferida"; si no hay manera de resolverla, flecha doble.
- Nunca hex fuera de la paleta del contrato en superficies nuevas.
- El espejo de "Vista exterior" es solo lectura: drags de partidores y
  edición de cotas quedan deshabilitados en exterior (un drag espejado
  invertiría el delta contra la intención del usuario).

## 8. Verificación

- `engine/tests/test_opening_symbols_p05.py` — 20 tests: fixtures ×
  vistas, reglas de `travel`, umbral de puerta, formato de paths.
- `frontend/src/features/canvas/openingSymbols.test.ts` — 29 tests:
  mismo archivo de fixtures contra el gemelo TS.
- `scripts/gen_symbol_fixtures.py` — ÚNICA vía para regenerar los
  fixtures (`PYTHONPATH=engine/src .venv/bin/python scripts/gen_symbol_fixtures.py`).
- `scripts/gen_symbol_doc_assets.py` — regenera las ilustraciones de este
  documento.
