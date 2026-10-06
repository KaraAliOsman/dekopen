# Formato de corte CSV — DEKOPEN (genérico, no propietario)

Los archivos que la orden de trabajo exporta para la sierra y la mesa de
láminas son un **formato genérico de DEKOPEN** — ninguna marca de sierra ni
CNC los define. Una fila por pieza física, orden determinista, decimales de
máquina (punto, precisión del plano, sin separador de miles) y la misma
etiqueta de pieza que imprime el pack de corte, el DXF y la etiqueta
pegable. Codificación UTF-8, cabecera con `#` para contexto de emisión.

## bars.csv — `work_order_cnc_export_v3`

Una fila por corte, ordenada por barra y luego por posición dentro de la
barra (`bar_index`, `sequence_in_bar`).

| Columna | Tipo | Significado |
|---|---|---|
| `bar_index` | entero | Número de barra en el plan (1..n). |
| `stock_sku` | texto | SKU comercial de la barra de stock consumida. |
| `stock_length_mm` | decimal | Largo de la barra de stock en mm. |
| `sequence_in_bar` | entero | Orden de corte dentro de la barra (1..k). |
| `piece_label` | texto | **Etiqueta de pieza por instancia** — `P{pos}-U{unidad}-M{seq}`, `-I{seq}` para vidrio/panel, `·R` para refuerzo de la pieza padre. Coincide con el pack, el DXF y la etiqueta pegable; dos cortes idénticos en barras distintas llevan etiquetas distintas. |
| `piece_id` | texto | Huella técnica de la especificación del corte (sha). No es la identidad física — es la clave de spec que agrupa piezas idénticas. |
| `cut_length_mm` | decimal | Largo de corte en mm. |
| `angle_left_deg` | decimal | Ángulo del extremo izquierdo en grados. |
| `angle_right_deg` | decimal | Ángulo del extremo derecho en grados. |
| `unit_index` | entero | Unidad física de la posición (repetición). |
| `bay_id` | texto | Vano destino de la pieza. |
| `leaf_id` | texto | Hoja destino (vacío cuando no aplica). |
| `source_position_id` | texto | Posición de la cotización que origina la pieza. |

## sheets.csv — `work_order_cnc_export_v3`

Una fila por ubicación anidada, ordenada por lámina, luego Y, luego X —
convención de mesa de corte (arriba-izquierda primero).

| Columna | Tipo | Significado |
|---|---|---|
| `sheet_index` | entero | Número de lámina en el plan (1..n). |
| `purchasing_sku` | texto | SKU de compra de la lámina. |
| `sheet_width_mm` | decimal | Ancho de la lámina en mm. |
| `sheet_height_mm` | decimal | Alto de la lámina en mm. |
| `x_mm` | decimal | Origen X de la pieza en la lámina. |
| `y_mm` | decimal | Origen Y de la pieza en la lámina. |
| `width_mm` | decimal | Ancho cortado en mm. |
| `height_mm` | decimal | Alto cortado en mm. |
| `rotated` | booleano | La pieza se anida rotada 90°. |
| `piece_id` | texto | Huella de spec (ver `bars.csv`). |
| `unit_index` | entero | Unidad física de la posición. |
| `bay_id` / `leaf_id` | texto | Vano / hoja destino. |
| `piece_label` | texto | Etiqueta por instancia — el mismo `P{pos}-U{unidad}-I{seq}` del pack y de la etiqueta. |

## DXF (AC1027, mm, UTF-8)

`bars.dxf` dibuja cada barra como franja horizontal con marcas de corte;
`sheet_{n}.dxf` dibuja el contorno de la lámina y una polilínea por pieza
con su etiqueta en capa `LABEL`. El texto viaja en UTF-8 con los caracteres
en español intactos (`Junquillo`, `Ñ`, `·R`); los códigos de capa son
`OUTLINE`, `CUT`, `LABEL`, `MARK`. Insunidades = 4 (milímetros).
