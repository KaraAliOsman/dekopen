# D03 — Aperturas y tipologías: de un enum de 12 valores a un modelo de apertura real

**Depende de:** D01 (familias de sistema). Debe mergearse **antes** de P05 (simbología) y de IA2 (operaciones) o, si van en paralelo, esos encargos rebasean y cubren lo que este agregue.

## Problema
`BayOpeningType` (`engine/src/dekopen_engine/models.py:49`) tiene 12 valores fijos: FIXED, TURN_L/R, TILT_TURN_L/R, SLIDING_2L/3L/4L, SLIDING, AWNING, DOOR_ENTRY y DOOR_DOUBLE. `hardware.py` los normaliza en TURN, TILT_TURN, SLIDING, DOOR y AWNING, y `design_assist` acepta solo 8. Así **no se pueden expresar** tipologías básicas del mercado chileno:
- abatible **hacia afuera**, típica del aluminio;
- **solo abatimiento** (banderola interior);
- **ventana francesa de 2 hojas con inversor**, con hoja activa y pasiva;
- **fijo en hoja**;
- puerta doble activa/pasiva, con sus manillas;
- puerta con lateral fijo.

Combinar todo en un enum hace que cada tipología nueva se convierta en una rama de código.

## Diseño
1. **Objeto `Opening`** en el motor, que reemplaza el enum como fuente de verdad:
   - `movement`: FIXED · TURN · TILT · TILT_TURN · TOP_HUNG (proyectante) · BOTTOM_HUNG · SLIDE · LIFT_SLIDE · PARALLEL_SLIDE · FOLD · PIVOT_V · PIVOT_H · VERTICAL_SLIDE (guillotina). Las últimas siete las implementa D08; aquí solo se declaran.
   - `hinge_side`: LEFT · RIGHT · TOP · BOTTOM · NONE.
   - `direction`: INWARD · OUTWARD.
   - `leaf_role`: ACTIVE · PASSIVE (inversor) · SINGLE.
   - `fixed_in_sash`: bool.
   - **Compatibilidad hacia atrás:** un mapeo total y probado enum ↔ `Opening`. Los productos guardados se leen y migran sin cambiar su geometría ni su precio (golden tests antes/después **idénticos**). La API acepta ambos durante una versión.
2. **Capacidades por sistema** (catálogo, D01): qué combinaciones de movimiento × dirección × rol admite cada sistema, y con qué herrajes (D04). El editor, la IA y la API solo ofrecen lo que el sistema admite.
3. **Implementa completas** (motor, BOM, cortes, herrajes, validación, simbología en el contrato de P05 si existe, y etiquetas en `domainLabels`):
   - abatible hacia adentro y hacia afuera (izquierda y derecha);
   - oscilobatiente (izquierda y derecha);
   - solo abatimiento (bisagras abajo, hacia adentro);
   - proyectante (bisagras arriba, hacia afuera);
   - fijo en marco y fijo en hoja;
   - **ventana francesa de 2 hojas** con inversor (rol INVERSOR existente): activa a la derecha o a la izquierda, con la pasiva con falleba;
   - puerta simple (izquierda y derecha, hacia adentro y hacia afuera);
   - puerta doble activa/pasiva;
   - puerta + lateral fijo.
4. **Manillas:** posición derivada (lado de cierre; en la ventana francesa, solo en la activa), altura según la regla del sistema o herraje (D04) y editable dentro de su rango.
5. **Nombres humanos** en español para cada combinación. Ejemplos: “Abatible hacia afuera — bisagras a la izquierda”, “Francesa 2 hojas — activa derecha”, “Solo abatimiento (banderola)”.

## Fuera de alcance
Elevable, osciloparalela, plegable, pivotante y guillotina (D08). UI del editor (P04 consume las capacidades).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador eligiendo la apertura. Debe sentir: “solo veo lo que este sistema puede hacer, y se ve como es”.
- **Anatomía:** Paleta de aperturas con `OpeningGlyph` (P01) y nombres del glosario; solo las compatibles con el sistema; las no disponibles, con su causa.
- **Momento de firma (preservar o crear):** Los íconos de apertura son la misma gramática del lienzo y del documento.
- **Idea que sube el techo (obligatoria, con el motor):** Al pasar sobre una apertura, la bahía muestra la vista previa dibujada (con la manilla y el lado de bisagra correctos) antes de elegirla.
- **Slop a eliminar aquí:** Abreviaturas crípticas, íconos genéricos de “ventana”, aperturas incompatibles ofrecidas y luego rechazadas.
- **Preguntas del pase editorial:** ¿Un estimador distingue proyectante de abatible sin leer? ¿Se puede elegir algo que el sistema no fabrica?

## Criterios de aceptación
- Migración enum → `Opening` con golden tests de cortes, BOM y precio **idénticos** para todos los productos del fixture.
- Golden tests nuevos para cada tipología de la lista: cortes, herrajes y peso por hoja.
- Test de capacidades: un sistema sin “hacia afuera” rechaza esa dirección con un mensaje que nombra los sistemas que sí la admiten.
- Paridad de símbolos (si P05 está mergeado): fixtures nuevos para cada tipología.
- Captura de cada tipología renderizada (técnica, vista interior).
