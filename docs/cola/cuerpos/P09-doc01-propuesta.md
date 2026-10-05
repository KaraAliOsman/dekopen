# P09 — DOC-01 Propuesta comercial v2: un documento que un fabricante firmaría con orgullo

**Depende de:** P02 (formato e identificadores). Mejor si P05 ya está mergeado (símbolos y vista declarada). Coordina rebase con P05 y P13 (`backend/documents/renderers.py`).

## Objetivo
Rehacer el layout y el contenido del DOC-01 para que sea un documento comercial de nivel profesional, white-label, legible a 1, 12, 24 y 100 posiciones, sin colisiones ni páginas vacías, y con la estructura por posición que usan los mejores del sector.

## Situación actual
- Render en `backend/documents/renderers.py` (y templates asociados); fixtures en `backend/scripts/render_doc_fixtures.py`.
- (auditoría, PDF del archivo) Hay **colisiones de columnas** en la tabla: “1200.00 × 1200” se monta sobre el vidrio y “$ 293.38$ 293.385” mezcla precio unitario y neto. Hay **una página en blanco** (“Vistas de los productos”) en el documento de 24 posiciones, medidas con `.00`, la flecha de la corredera mal en la portada de builds antiguos y el tamaño Carta. El documento de 100 posiciones tiene 31 páginas.
- Lo bueno, que se conserva: bloque emisor; “Preparado para” (RUT, giro, comuna, dirección, contacto, entrega); tabla “Solución propuesta”; resumen comercial; condiciones; aceptación con firmas.

## Referencia de estructura (adjunto `fenster-musterangebot.pdf` y las capturas de Orgadata y Logikal)
Cada posición se presenta como un bloque con:
- nombre del recinto (“01 Living”);
- **vista declarada** (“Vista interior”);
- dibujo con cota total y cotas por campo;
- lista por campo (“Campo 1.1: Oscilobatiente, bisagras a la izquierda”);
- descripción del sistema (serie, color interior y exterior);
- vidrio con composición (4/16/4) y U **solo si es dato autoritativo**;
- accesorios como sublíneas *cantidad × precio unitario = total*;
- subtotal de la posición.

Las posiciones alternativas van marcadas como “no incluidas en el total”, y cada página lleva el folio, la revisión y el número de página.

## Estructura objetivo
1. **Portada:** logo, razón social, RUT, giro, dirección y contacto del emisor. “Preparado para”: cliente, RUT, obra, dirección y contacto. Folio `COT-P-000123-REV-B`, fecha y **vigencia**. Total destacado con su moneda. Resumen de condiciones (pago, plazo, instalación). Imagen de la posición más representativa, con el renderer real y la vista declarada.
2. **Resumen de posiciones:** tabla compacta (Pos., Ubicación, Tipología, Ancho × Alto, Cant., P. unit. neto, Total neto) con **anchos de columna fijos y ajuste de línea**, que nunca se superponen; cifras tabulares; repetición del encabezado en cada página.
3. **Detalle por posición:** de 1 a 3 posiciones por página según su alto, con el bloque de referencia descrito arriba, la leyenda de simbología y la planta si es un conjunto o bow (P06). En los documentos de cliente **no se muestran valores técnicos desconocidos**: se omite la línea, sin “Sin dato”.
4. **Resumen comercial:** neto, descuento, neto con descuento, IVA 19 % y total; tabla del calendario de pagos con montos; plazos; instalación; exclusiones; garantía; vigencia y jurisdicción.
5. **Aceptación:** nombre, RUT, fecha y firma, más “Acepta en línea” con QR y enlace al portal de la misma revisión.
6. **Pie de cada página:** folio · revisión · página n/N · datos legales del emisor y, en tamaño pequeño, la huella abreviada.
7. **Ajuste de la organización:** papel Carta u Oficio o A4 (por defecto, el actual), logo, color de acento (dentro de la paleta permitida) y textos legales. **Nunca** se muestran costo, margen, UUID ni hash en el cuerpo.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El cliente final que recibe el PDF y el dueño que lo firma. Debe sentir: “esta empresa es seria”.
- **Anatomía:** Constitución §5.8: lámina técnica white-label, filete teal-800, inglete, cajetín ISO 7200 con huella, ficha por posición (elevación con vista declarada + tabla de especificación), totales con un único momento fuerte, Carta, Plex embebida.
- **Momento de firma (preservar o crear):** F1, F2 y F11: el documento está cortado como el marco que cotiza y lleva su huella como un número de plano.
- **Idea que sube el techo (obligatoria, con el motor):** El mismo documento se lee bien con 1, 12 o 100 posiciones (ficha completa, ficha compacta o tabla con miniaturas, elegido automáticamente por densidad) y cada vidrio muestra composición y Ug cuando existen.
- **Slop a eliminar aquí:** Azul marino genérico y Arial, cebra en tablas, columnas que colisionan, páginas en blanco, `.00`, logos de DEKOPEN sobre la marca del cliente.
- **Preguntas del pase editorial:** ¿Lo firmaría con orgullo el dueño de Schüco? ¿Se puede cortar contra cada medida impresa?

## Criterios de aceptación
- Tests de render con 1, 12, 24 y 100 posiciones (fixtures). Usa PyMuPDF si está en las dependencias de test; si no, agrégalo como dependencia de test fijada.
  - **Sin superposición** de cajas de texto dentro de las tablas (test de intersección de bbox).
  - Ninguna página tiene solo pie.
  - El total del documento es igual al total del motor.
  - Moneda correcta en una cotización en USD.
  - Sin hex de 10 o más caracteres fuera del pie.
- 100 posiciones en ≤ 45 páginas; nombres de cliente y ubicación de 120 caracteres hacen wrap sin romper el layout (test).
- Snapshots raster commiteados (portada, resumen y una página de detalle) para 12 posiciones, en `docs/redesign/captures/doc01-v2/`.
- La simbología del documento coincide con el editor (si P05 está mergeado, usa sus fixtures de paridad).
