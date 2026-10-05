# D08 — Tipologías avanzadas: elevable (HST), osciloparalela (PSK), plegable, pivotante, guillotina y puerta corredera

**Depende de:** D03 (modelo `Opening`), D04 (herrajes) y P05 (simbología).

## Objetivo
Completar los movimientos que D03 dejó declarados, sin ramas de enum y **solo donde el catálogo del sistema lo permita**. Si un sistema no trae los datos de una tipología, la UI la muestra como no disponible para ese sistema, con su causa; nunca la inventa.

## Alcance (por cada tipología: modelo, validación, cortes, BOM, herrajes, símbolo y nombre humano)
1. **Elevable-corredera (HST, `LIFT_SLIDE`):** familia de sistema `LIFT_SLIDE` (D01) con sus esquemas (A: 1 fijo + 1 móvil; C: 2 móviles al centro; G y K si el catálogo los trae), umbral específico, carros por peso y manilla de elevación. Símbolo: flecha de desplazamiento con un quiebre que indica la elevación.
2. **Osciloparalela (PSK, `PARALLEL_SLIDE`):** hoja que bascula y se desplaza paralela; herraje específico por peso; símbolo de basculante + flecha.
3. **Plegable (`FOLD`):** n hojas con sus esquemas de plegado (3+0, 2+1, etc.), hoja de paso opcional, carros y guías; símbolo en zigzag en la planta y triángulos por hoja en la elevación.
4. **Pivotante vertical u horizontal (`PIVOT_V` / `PIVOT_H`):** eje desplazado declarado y herraje de pivote; símbolo según la convención documentada.
5. **Guillotina (`VERTICAL_SLIDE`):** simple o doble, con contrapesos o muelles según el catálogo; flecha vertical.
6. **Puerta corredera** (de entrada o de patio): hoja corredera de puerta con su umbral y cerradura.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador cotizando tipologías avanzadas. Debe sentir: “también entiende las ventanas difíciles”.
- **Anatomía:** Las mismas superficies de P04/P05: elevable, osciloparalela, plegable, pivotante, guillotina y puerta corredera con su simbología y su planta.
- **Momento de firma (preservar o crear):** F5 extendida: la planta muestra el recorrido real (paquete plegado, hoja elevable en su carril, pivote con su eje).
- **Idea que sube el techo (obligatoria, con el motor):** Elegir una tipología avanzada muestra en el lugar qué sistemas del catálogo la permiten y qué falta para habilitarla.
- **Slop a eliminar aquí:** Tipologías “disponibles” sin datos del catálogo, símbolos inventados, planta ausente.
- **Preguntas del pase editorial:** ¿Un fabricante de HST reconoce su producto en el dibujo? ¿Se puede ofrecer una tipología sin datos?

## Criterios de aceptación
- Por tipología: un golden test de cortes, BOM y herrajes con el fixture sintético de la familia correspondiente (marcado como DEMO), un test de capacidades (no disponible en un sistema que no la declara), el fixture de símbolo (paridad de P05) y una captura técnica y comercial.
- Las tipologías se ofrecen en la biblioteca del editor solo cuando el sistema seleccionado las admite (test).
