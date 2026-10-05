# D07 — Del vano de obra a la medida de fabricación: tipo de montaje, holguras, rectificación de medidas

**Depende de:** D01. Coordina con P21 (proyecto) y P23 (medición en obra desde el móvil).

## Problema
En la obra se mide el **vano**, pero se fabrica la **ventana**. La diferencia depende del tipo de montaje y de las holguras, y es una de las mayores fuentes de errores y remakes. Hoy DEKOPEN solo conoce la medida del producto, que el usuario debe calcular a mano.

## Alcance
1. **Datos del vano** por posición: ancho y alto (opcionalmente en 3 puntos, en cuyo caso se usa el menor y se avisa si la diferencia supera la tolerancia), tipo de muro (albañilería, hormigón, tabique o madera) y escuadra o desplome si se midió.
2. **Tipo de montaje**, con reglas por organización y sistema, como datos: en vano con holgura perimetral, con premarco, sobre vano o traslapado, y renovación sobre marco existente. Cada regla define la holgura por lado, los ensanches necesarios (D06) y los accesorios de fijación.
3. **Motor:** medida de fabricación = f(vano, montaje, holguras), con su desglose (“Vano 1520 − holgura 10 + 10 = 1500 mm de fabricación”). El usuario puede **fijar** la medida de fabricación manualmente; la fijación queda registrada y el sistema avisa si no es coherente con el vano. Golden tests.
4. **Estados de medida:** “cotizada con medidas del cliente” → “rectificada en obra” (P23) → “confirmada para producción”. Si la rectificación cambia las medidas después de la aprobación, se crea una **revisión** con su Δ de precio (P08), y la producción no se libera con medidas sin confirmar (gate en el backend, test).
5. **UI:** en el editor, el chip “Vano 1520 × 1220 · Fabricación 1500 × 1200 · En vano con holgura 10 mm”; en el inspector, la sección “Vano y montaje”. Los documentos muestran la medida que corresponde: al cliente, la del vano y la del producto; al taller, solo la de fabricación.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador y el medidor en obra. Debe sentir: “mido el vano y el sistema calcula la fabricación”.
- **Anatomía:** Entrada por vano (ancho, alto, tipo de montaje) con la medida de fabricación derivada y sus holguras visibles en el dibujo.
- **Momento de firma (preservar o crear):** Cota doble en el lienzo: vano y fabricación, con la holgura entre ambas.
- **Idea que sube el techo (obligatoria, con el motor):** Ingresar varias medidas del vano (arriba, medio, abajo) elige la menor, avisa del descuadre y lo deja registrado en la revisión.
- **Slop a eliminar aquí:** Pedir la medida de fabricación al usuario, holguras ocultas, cálculos manuales.
- **Preguntas del pase editorial:** ¿Algún usuario necesita una calculadora? ¿La holgura se ve y se explica?

## Criterios de aceptación
- Golden tests por tipo de montaje.
- Test del gate: la OT no se libera con medidas sin confirmar.
- Test del ciclo con revisión: una rectificación posterior a la aprobación genera una revisión con su Δ.
- Captura del chip, del inspector y del aviso de incoherencia.
