# D05 — Colores y acabados: interior y exterior, foliados, RAL/anodizado, restricciones, SKU, precio y render

**Depende de:** D01.

## Problema
Los acabados son strings libres en `SystemParams.finishes` (`["WHITE","FOILED"]` en DEMO_60), con una sola diferencia técnica, la holgura de vidrio blanco vs. foliado. No hay colores reales ni color interior distinto del exterior. No existen las restricciones (el foliado o el color oscuro exigen refuerzo y reducen los tamaños máximos), los SKU por color para stock y compras, el recargo por color, ni la representación fiel en el 2D, el 3D, el portal y el PDF. (auditoría) Los foliados se ven rosados en el 3D.

## Alcance
1. **Catálogo de colores** por sistema:
   - PVC: masa (blanco, crema), foliado en una o dos caras (int, ext o ambas, cada una con su color y su base) y coextruido si aplica.
   - Aluminio: RAL (código y brillo), anodizado y efecto madera.
   - Cada color lleva su código del fabricante, el nombre comercial y, para render, el color lineal (y la textura si el catálogo la aporta; si no, “aproximado”).
2. **Por posición:** color interior y color exterior, más el color de herrajes y manillas (blanco, plata, negro, bronce, si existen). Validación de combinaciones permitidas.
3. **Reglas en el motor**, como datos importables: refuerzo obligatorio por color (conectado con D01), límites de tamaño por color, holguras por acabado (ya existe; generalízalo) y **SKU de perfil por color** para el BOM, el stock y las compras. El faltante por color se detecta (la fase 14 ya bloqueaba `physical_stock_color_mismatch`; mantenlo).
4. **Precio:** recargo por color (por metro de perfil, % o fijo por posición, según la regla del catálogo), calculado en el motor.
5. **Render:** el editor 2D (vista comercial), el 3D (P19), el portal y el PDF usan el color del catálogo. La vista interior muestra el color interior y la exterior, el exterior.
6. **UI:** selector en el editor con muestras reales y la opción “igual en ambas caras”. En la cotización, “Color: Nogal exterior / Blanco interior”.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador y el cliente eligiendo color. Debe sentir: “veo el color real, por dentro y por fuera”.
- **Anatomía:** Selector con cara interior y exterior, carta del catálogo (foliados, RAL, anodizados), restricciones y recargo/plazo visibles.
- **Momento de firma (preservar o crear):** El lienzo y el 3D muestran el bicolor real; el documento lo declara por cara.
- **Idea que sube el techo (obligatoria, con el motor):** Elegir un foliado oscuro avisa del refuerzo obligatorio y del plazo extra en el mismo lugar, con el Δ de precio.
- **Slop a eliminar aquí:** Colores como texto libre, muestras que no coinciden con el render, recargos ocultos.
- **Preguntas del pase editorial:** ¿El cliente ve en el portal el color que va a recibir? ¿Cada restricción se explica?

## Criterios de aceptación
- Golden tests: foliado → refuerzo obligatorio; SKU por color en el BOM; recargo calculado.
- Test de combinaciones inválidas, con su mensaje.
- Captura del selector y de una posición bicolor en vista interior y exterior. El 3D sin tonos rosados (comparación del color del material con el catálogo).
