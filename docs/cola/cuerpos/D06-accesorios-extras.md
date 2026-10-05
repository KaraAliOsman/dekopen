# D06 — Accesorios y extras por posición y por proyecto: lo que de verdad se cobra

**Depende de:** D01 (roles SILL, FRAME_EXTENSION y COVER_TRIM). Coordina con P07 (cascada de precio) y P09 (sublíneas en el DOC-01).

## Problema
Una cotización real de ventanas no es solo “ventana × precio”. Lleva vierteaguas, ensanches, tapajuntas, mosquiteros, palillaje, manillas especiales, instalación por metro lineal, sellado, retiro de la ventana existente y flete. Hoy no hay un modelo para esto. (Referencia: el *Musterangebot* adjunto muestra cada posición con sublíneas “Fensterbankanschluss 4,5 m × 11,00 = 49,50”, “sondergriff 3 Stück × 21,00”, etc.)

## Alcance
1. **Tipos de extra**, como datos del catálogo o de la organización (importables):
   - **Ligados a la geometría**, con largo o cantidad derivados por el motor: vierteaguas o alféizar (largo = ancho + vuelos), ensanches por lado (cortes reales), tapajuntas por lado y palillaje (D02).
   - **Por unidad:** mosquitero fijo, enrollable o corredera (medida derivada de la hoja o del vano), manilla especial, limitador, aireador o ventilación.
   - **Por proyecto:** instalación (por posición, por m² o por metro lineal de perímetro, según la regla), sellado y espuma (metro lineal), retiro de ventana existente, andamio y flete (por zona o fijo).
2. **Motor:** cada extra produce su **sublínea** (cantidad × precio unitario = total), su costo y su BOM, y los cortes cuando corresponde (perfiles de ensanche o vierteaguas en el plan de corte de P13). Golden tests.
3. **UI:**
   - En el inspector del editor, “Extras de la posición” con los compatibles del sistema.
   - En la página de proyecto (P21), “Servicios del proyecto” (instalación, flete y retiro).
   - Plantillas de extras por defecto por organización (por ejemplo, “instalación estándar” agregada a toda posición nueva, configurable en Ajustes, P22).
4. **Documentos:** el DOC-01 (P09) muestra las sublíneas bajo cada posición y los servicios del proyecto en el resumen comercial. La política de la organización define si las sublíneas se muestran con precio o agrupadas en el precio de la posición.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador que cobra lo que de verdad se instala. Debe sentir: “no se me escapa nada”.
- **Anatomía:** Extras como sublíneas de la posición (estilo Musterangebot) y del proyecto (instalación, flete, retiro), con su precio desde el motor.
- **Momento de firma (preservar o crear):** En el DOC-01 los extras aparecen bajo su posición, alineados, como en las mejores cotizaciones del sector.
- **Idea que sube el techo (obligatoria, con el motor):** El sistema sugiere los extras que suelen acompañar a una tipología (vierteaguas en ventanas de fachada, ensanche si el vano lo exige) con su causa; el usuario acepta o descarta.
- **Slop a eliminar aquí:** Extras como texto libre con precio manual, listas sin agrupación, sugerencias sin causa.
- **Preguntas del pase editorial:** ¿Se puede olvidar cobrar la instalación? ¿Cada sugerencia explica por qué aparece?

## Criterios de aceptación
- Golden tests: vierteaguas de una posición de 1500 de ancho con vuelos de 30 + 30 → 1560 mm; instalación por metro lineal de perímetro; plantillas aplicadas a una posición nueva.
- Las sublíneas suman exacto al total de la posición (test).
- El perfil de ensanche aparece en el plan de corte y en el BOM de la OT (test).
- Captura del inspector, de los servicios del proyecto y de una página del DOC-01 con sublíneas.
