# P13 — Pack de corte, etiquetas de pieza y consistencia de identidad entre artefactos

**Depende de:** P02 (identidad de pieza y formato). Coordina rebase con P09 y P05 (`backend/documents/renderers.py`).

## Objetivo
Que el cortador pueda trabajar **solo con el papel o la pantalla**: qué barra tomar, en qué orden cortar, con qué ángulos, qué etiqueta pegar a cada pieza y adónde va el sobrante. Y que la misma pieza tenga el mismo nombre en el PDF, el CSV, el DXF, la etiqueta y el QR.

## Situación actual
- Render en `backend/documents/renderers.py` (packs de corte y de producción); optimizador en `engine/src/dekopen_engine/cutting.py` y `nesting.py`.
- El pack “DESPUÉS” del archivo (auditoría, `cutpack-DESPUES.pdf`) ya tiene un buen esqueleto que **se conserva**:
  - diagrama de barra con etiquetas legibles;
  - tabla SEC / PIEZA / FUNCIÓN / VANO-HOJA / CORTE MM / ∠IZQ / ∠DER / OBS;
  - línea de cierre “6000 mm = 5480 piezas + 16 disco + 30 despuntes + 474 remanente — cierra exacto”;
  - huella del plan;
  - QR de identidad.
- Problemas (auditoría):
  - Solo cabe ~1,5 barras por página (6 barras en 4 páginas).
  - Vidrio “1310.00×1310.00”.
  - Vidrio no ubicado con un escueto “Sin lámina declarada”.
  - No hay agrupación de cortes idénticos para sierras manuales.
  - No hay hoja de etiquetas de pieza.
  - En versiones anteriores: etiquetas diminutas que colisionaban, ID de remanente truncado, UTF-8 corrupto en el DXF y enums crudos.
- Referencias: FeneCAM (“BAR 6000 ×4 · CUT 1485 L45 R45 → W-01 · REM 1068 → warehouse”), la secuencia de corte por grupo de costo de Windowmaker y los módulos de etiquetas de producción de Stolcad.

## Alcance
1. **Lista de corte compacta** por SKU de perfil + color, en apaisado, con 3 a 5 barras por página. Cada fila de barra lleva:
   - SKU humano y color;
   - largo de stock;
   - origen (barra nueva o retazo `RT-000045`);
   - cortes **en secuencia** con largo, ángulos (iconos L45/R45 o 90) y etiqueta de pieza;
   - remanente → destino (`RT-000046` al stock o desecho) y aprovechamiento con 1 decimal.
   - Debajo, la línea de cierre exacta (Decimal) por barra.
2. **Vista agrupada** opcional: cortes idénticos agregados con su cantidad, para sierras manuales, sin perder la trazabilidad (la lista de etiquetas se agrupa por corte).
3. **Refuerzos y junquillos** en su propia sección, con la relación a la pieza padre. **Vidrios** con medidas en mm enteros, composición, cantidad y posición. Los ítems no ubicados se explican con una acción, por ejemplo: “El vidrio V-01 no tiene formato de lámina declarado en el catálogo → Catálogo › Vidrios › Formatos”.
4. **Hoja de etiquetas de pieza** en un formato configurable por organización: A4 o Carta con una grilla de etiquetas, o rollo térmico de 100×50 mm. Cada etiqueta lleva etiqueta de pieza grande, OT, posición/unidad, rol en español, largo, ángulos, color, QR (ID estable + etiqueta) y siguiente estación. También etiquetas de retazo.
5. **Consistencia:** la misma etiqueta y la misma secuencia en PDF, CSV, DXF, etiquetas y QR. DXF en UTF-8 con caracteres en español. Columnas del CSV documentadas en `docs/` como **formato genérico de DEKOPEN**. **No inventes formatos propietarios** de sierras o CNC.
6. **Legibilidad de impresión:** texto de cuerpo de al menos 8 pt en el PDF impreso; etiquetas en el diagrama de barra sin superposición (algoritmo de colocación con niveles o callouts).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El cortador, con papel o pantalla. Debe sentir: “sé qué barra tomar y dónde va cada pieza”.
- **Anatomía:** Lámina técnica (§5.8) para el pack; densidad `workshop` para la vista en pantalla. La misma pieza con el mismo nombre en PDF, CSV, DXF, etiqueta y QR.
- **Momento de firma (preservar o crear):** F2 (huella en cada hoja del pack y en cada etiqueta) y la barra dibujada a escala con sus piezas y el destino del retazo.
- **Idea que sube el techo (obligatoria, con el motor):** Cada barra se ve dibujada con sus cortes en orden, ángulos y el retazo con su código y ubicación de destino; la etiqueta se imprime en la secuencia de corte.
- **Slop a eliminar aquí:** Pocas barras por página, tablas sin dibujo, vidrio no ubicado sin acción, etiquetas con IDs técnicos.
- **Preguntas del pase editorial:** ¿Se puede cortar toda una OT solo con el papel? ¿Cada retazo tiene destino?

## Criterios de aceptación
- Tests de render para OTs de 1, 12 y 100 posiciones: páginas ≤ ceil(barras / 3) + secciones fijas; sin superposición de bbox de texto; la línea de cierre suma exacto para cada barra.
- Test de igualdad de etiquetas entre PDF, CSV, DXF y etiquetas.
- Test de parseo del DXF, con `ezdxf` si está disponible (si no, agrégalo como dependencia de test fijada), con texto en español intacto (“Junquillo”, “Ñ”).
- Capturas raster de una página de lista, una de vidrios y una de etiquetas, commiteadas.
