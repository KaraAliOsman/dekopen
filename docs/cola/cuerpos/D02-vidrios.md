# D02 — Vidrios de verdad: composición estructurada, tipos, seguridad (NCh 135), límites, precio y pedido al proveedor

**Depende de:** D01 (importador y sistemas). Coordina con P04 (selector en el editor) e IA2 (`set_glass`).

## Problema
Hoy el vidrio es **un string** (`glass_spec`, por ejemplo “4-16-4”) que `engine/src/dekopen_engine/glass.py` parsea con regex para obtener espesor y peso (2,5 kg/m²·mm), más unos pocos SKU de catálogo. No existen los tipos de vidrio (templado, laminado, low-e, control solar, color), ni las cámaras con su gas y su separador, ni reglas de seguridad, límites de tamaño, recargos o el pedido al vidriero. Para una fábrica, el vidrio es entre el 25 y el 40 % del costo de una ventana.

## Alcance
1. **Modelo de composición** (motor y BD), ordenado de **exterior a interior**:
   - **Lámina:** tipo (float incoloro, float color bronce/gris/verde, templado, termoendurecido, laminado con n láminas + PVB de 0,38 o 0,76 mm o acústico, low-e con cara de la capa, control solar, reflectivo, espejo, satinado/arenado, impreso), espesor y SKU del proveedor.
   - **Cámara:** separador (aluminio o borde cálido) con su ancho, gas (aire o argón) y sellante.
   - **Producto de vidrio:** composición + nombre comercial + datos **solo si vienen del proveedor** (Ug, g, transmisión luminosa, clase de seguridad NCh 135 A/B/C, peso por m²).
   - **Notación** con parser y formateador de ida y vuelta: “4 / 12 aire / 4”, “5 / 12 Ar / 4 Low-E (c3)”, “3+3 PVB 0,38”, “4+4 / 16 / 6 templado”, “DVH 5-12-5”. Los `glass_spec` existentes se migran a la composición estructurada; si no se pueden parsear, quedan **UNKNOWN y marcados para revisión**.
2. **Derivados en el motor:**
   - espesor total y espesor neto;
   - peso, incluido el PVB;
   - selección de **junquillo por espesor total**, usando la `glazing_bead_matrix` existente;
   - medida de corte del vidrio = luz − deducciones del sistema (ya existe; mantenla y exponla);
   - área facturable con **área mínima** por producto.
3. **Reglas** como datos editables por organización, con fuente citada:
   - **Seguridad (NCh 135/2):** áreas de riesgo como puertas, paneles laterales, paños a menos de 800 mm del piso y grandes ventanales. NCh 135 es una práctica recomendada, así que el resultado es un **aviso o recomendación**, no un bloqueo, salvo que la organización lo configure como obligatorio. El texto de las tablas normativas **no se inventa**: deja la estructura completa con reglas de ejemplo marcadas como sintéticas y editables por la organización, y la carga de las reglas oficiales por la misma ingesta de catálogo (D01), para que el dueño suba la norma después. Regístralo en `ACTIVACION.md` como dato pendiente.
   - **Límites:** tamaño máximo y mínimo por tipo y espesor, relación de aspecto, y “el templado no se recorta: se pide a medida exacta”.
   - **Compatibilidad:** espesor total dentro del rango de junquillos del sistema; peso de la hoja compatible con los herrajes (D04).
4. **Precio:** costo por m² por producto de vidrio, recargos (templado, canto pulido, perforación, palillaje/georgian bars con su patrón y costo por metro o cruce) y área mínima. Todo en el motor, con golden tests.
5. **Pedido al vidriero:** por OT o lote, lista con medidas de corte en mm enteros, composición, cantidad, posición, recargos y etiqueta de vidrio con QR (enlaza con P13). Exportación en PDF y CSV.
6. **UI del selector** en el inspector del editor (coordina con P04):
   - **Básico:** tarjetas de los productos del catálogo compatibles con la bahía (“Termopanel 5-12-5 incoloro”, “Termopanel Low-E”, “Laminado de seguridad 3+3”), con espesor, peso y precio relativo.
   - **Avanzado:** compositor visual de capas (exterior → interior), con validación en vivo, Ug y g si hay datos, y avisos.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador eligiendo vidrio. Debe sentir: “elijo rápido y sé lo que estoy poniendo”.
- **Anatomía:** Básico: tarjetas de productos compatibles (nombre comercial, espesor, peso, precio relativo). Avanzado: compositor de capas exterior → interior con validación en vivo.
- **Momento de firma (preservar o crear):** El compositor dibuja el corte del termopanel a escala (láminas, cámara, gas, separador) con el mismo lenguaje del lienzo.
- **Idea que sube el techo (obligatoria, con el motor):** El aviso de seguridad (NCh 135) aparece en la bahía exacta del dibujo con la alternativa compatible a un clic.
- **Slop a eliminar aquí:** Un desplegable con 80 códigos, composiciones como texto libre, avisos genéricos.
- **Preguntas del pase editorial:** ¿Un estimador nuevo elige el vidrio correcto sin conocer la notación? ¿El avanzado sirve a un vidriero?

## Criterios de aceptación
- Tests de ida y vuelta del parser y el formateador con 30 notaciones reales, incluidas mayúsculas y minúsculas, comas decimales y espacios.
- Golden tests de peso (con PVB), de selección de junquillo, de área mínima y de recargos.
- Test de la regla de seguridad: una puerta vidriada con vidrio común → aviso con la referencia de la regla.
- Test de migración de `glass_spec` (parseables y no parseables).
- Pedido al vidriero de la OT de 12 posiciones: medidas iguales a las del motor (test). Capturas del selector básico y avanzado.
