# D04 — Herrajes reales: familias, clases por tamaño y peso, componentes cortables, manillas y reglas

**Depende de:** D03 (modelo de apertura). Coordina con P14 (perforaciones y CNC).

## Problema
`engine/src/dekopen_engine/hardware.py` elige **un kit** por apertura según el ancho y alto de la hoja y el peso máximo. El seed tiene un kit por tipo (KIT-TURN, KIT-TILT-TURN, KIT-SLIDING, KIT-AWNING-16 y KIT-DOOR-MULTIPOINT), con `contents` en JSON. En la realidad, un herraje oscilobatiente se compone de piezas según la clase de tamaño:
- cremona o falleba con su transmisión **cortada a medida**;
- reenvíos de esquina;
- compás según el ancho;
- puntos de cierre según el alto;
- bisagras según el peso;
- cerraderos, manilla y tapas.

Las correderas usan carros según el peso; las puertas, bisagras según el peso y cerradura con cilindro. Hoy nada de esto existe.

## Alcance
1. **Familia de herraje** por sistema × apertura (D03), con **clases** por rango de ancho, alto y peso de hoja. Cada clase lista sus **componentes** con su regla de cantidad (por ejemplo, puntos de cierre = f(alto)) y su regla de largo para los cortables (por ejemplo, transmisión = alto de hoja − X), todo como datos del catálogo e importable con la plantilla de D01.
2. **Motor:** resuelve la clase, expande los componentes con cantidades y largos, suma el peso y el costo, y valida las restricciones: peso máximo, relación ancho/alto (la hoja oscilobatiente muy ancha y baja no es válida si la regla lo dice) y alto mínimo para el compás.
   - Los mensajes de falla dicen la restricción y el valor real, por ejemplo: “Hoja de 1450 × 2300 mm, 96 kg: la clase estándar admite hasta 80 kg; usa bisagras reforzadas (clase pesada) o reduce el ancho”.
   - Golden tests.
3. **Manillas:** modelo (estándar, con llave, con botón o de puerta con escudo), color (D05) y altura de manilla con su regla (centrada en la hoja, a altura fija desde la base o según el rango del herraje). Es editable dentro del rango, y el motor valida y avisa si queda fuera.
4. **Opciones vendibles** por posición, solo si el catálogo las tiene: seguridad (puntos antipalanca o clase RC si hay datos), limitador de apertura, microventilación, manilla con llave y bisagras ocultas. Con precio y BOM.
5. **Producción:** lista de picking de herrajes por OT (componentes, cantidades y largos de corte de transmisiones) y operaciones de mecanizado declaradas por componente (cerradero, alojamiento de cremona y bisagras), que alimentan P14. **Sin coordenadas inventadas**: si el catálogo no las trae, la operación queda “declarada no emitida”.
6. **UI:** en el inspector del editor (P04), “Herrajes” muestra la clase resuelta y su resumen (de solo lectura para el usuario básico) y el detalle de componentes en “Avanzado”; en el documento al cliente, solo lo vendible (modelo y color de manilla, y opciones).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El técnico o estimador avanzado revisando herrajes. Debe sentir: “el herraje es el correcto y sé por qué”.
- **Anatomía:** En el inspector “Avanzado”: kit seleccionado, clase por tamaño y peso, componentes, puntos de cierre y la regla que lo eligió.
- **Momento de firma (preservar o crear):** F6: “¿Por qué este kit?” muestra el peso de la hoja, el rango del kit y la fuente.
- **Idea que sube el techo (obligatoria, con el motor):** Si la hoja supera la clase del kit, el aviso propone la clase siguiente o la división de la bahía, con el Δ de precio.
- **Slop a eliminar aquí:** Un solo nombre de kit sin detalle, selección silenciosa, errores sin eje de falla.
- **Preguntas del pase editorial:** ¿Puede quedar un herraje incompatible sin aviso? ¿El técnico entiende por qué se eligió cada componente?

## Criterios de aceptación
- Golden tests de expansión por clase: dos tamaños de oscilobatiente, una corredera pesada y una puerta.
- Tests de cada restricción, con su mensaje.
- La lista de picking de la OT de 12 posiciones es igual a la suma del motor (test).
- Importación de herrajes desde la plantilla de D01 (test de ida y vuelta). Captura del inspector y del picking.
