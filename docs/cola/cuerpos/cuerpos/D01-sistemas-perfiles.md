# D01 — Sistemas y perfiles de verdad: familias separadas, roles completos, reglas de corte y refuerzo, límites e importador de catálogo

**Depende de:** nada; puede correr en la ola 0. Coordina con P16 (UI de catálogo) y con IA2/IA3 (la ingesta por IA usa el proveedor real y sus artefactos `catalog candidates`/`catalog review`).

## Problema
DEKOPEN hoy calcula sobre un catálogo de juguete, y por eso todo “funciona a medias”: cualquier cotización, BOM o corte solo es tan real como el catálogo que hay detrás.

## Hechos verificados en main `b3d1c9b`
- `supabase/seed.sql`: hay **3 sistemas, todos sintéticos**: `DEMO_60` (“Sistema Demo 60mm PVC — referencia sintética”), `ALU_65` y `GLASS_45`. DEMO_60 tiene perfiles MARCO, HOJA, POSTE-V, POSTE-H, JQ-10/14/24 y UMBRAL-ALU, acabados `["WHITE","FOILED"]` y un kit por tipo de apertura.
- `engine/src/dekopen_engine/models.py`: `SystemParams` mezcla en **un mismo sistema** parámetros de practicable (traslape de hoja, holgura de vidrio) y de corredera (`central_overlap_mm`, `pulley_height_mm`, `sliding_glazing_deduction_*`). En la vida real, la corredera es **otra serie con otros perfiles**.
- `ProfileRole` tiene solo 10 roles (FRAME, SASH, MULLION_V, MULLION_H, INVERSOR, GLAZING_BEAD, COUPLER, ADDITIONAL, THRESHOLD, CHANNEL). `MaterialType` solo admite PVC y ALUMINIUM. Los acabados son strings libres.

## Alcance
1. **Familia de sistema** (`system_family`): `CASEMENT` (practicable y oscilobatiente), `SLIDING` (corredera), `LIFT_SLIDE` (elevable), `DOOR` (puerta de entrada) y `FACADE_FIXED` (fijos de gran formato), con las tipologías que cada familia admite.
   - El motor **rechaza** una tipología incompatible con la familia; por ejemplo, una corredera en un sistema practicable, con un mensaje en español que propone sistemas compatibles del catálogo.
   - Separa los parámetros por familia: los parámetros de corredera viven solo en sistemas `SLIDING`.
   - Migración: divide `DEMO_60` en `DEMO_60` (practicable) y `DEMO_CORREDERA_60` (corredera), ambos sintéticos, y migra los productos guardados (las posiciones de corredera pasan al sistema corredera) con un test de migración.
2. **Roles de perfil completos, solo los que el motor necesita para calcular:**
   - hoja de corredera (`SLIDING_SASH`), encuentro o traslapo de corredera (`INTERLOCK`) y riel o guía si el marco corredera lo separa;
   - hoja de puerta (`DOOR_SASH`);
   - ensanche o ampliación de marco (`FRAME_EXTENSION`), vierteaguas o alféizar (`SILL`) y tapajuntas (`COVER_TRIM`), estos tres conectados con D06;
   - zócalo, si aplica.
   - Para cada rol: **regla de corte** (ángulo 45/90, pérdida de soldadura por extremo, descuento por encuentro), su perfil de refuerzo compatible y el redondeo de corte.
3. **Reglas de refuerzo** como datos y no como código: por perfil, color (foliado u oscuro → obligatorio) y largo mínimo; tipo de refuerzo; descuento de corte; tornillos por metro (BOM). Golden tests con casos: blanco de 900 mm sin refuerzo vs. foliado de 900 mm con refuerzo, según una regla de fixture.
4. **Límites dimensionales** por sistema × tipología: ancho y alto de hoja mínimo y máximo, peso máximo y relación de aspecto. El motor los usa para validar; el editor (P04) y la cotización (P08) los muestran con su fuente.
5. **Ingesta de catálogo por dos vías** (decisión del dueño: “se puede ingresar en cualquier formato y la IA lo analiza e integra; también manual”):
   - **Manual estructurado:** importador XLSX/CSV con una **plantilla oficial descargable** desde Catálogo. Hojas: Sistemas, Perfiles, Roles y reglas de corte, Refuerzos, Límites, Colores y SKU por color (D05), Vidrios (D02), Herrajes (D04) y Precios de costo. Validación fila por fila con errores en español (“Fila 14, columna ‘Pérdida de soldadura’: debe ser un número en mm”).
   - **Por IA, cualquier formato:** el usuario sube lo que tenga — ficha técnica en PDF, planilla del proveedor, foto o escaneo de una tabla, correo con precios, texto pegado — y la IA extrae los datos estructurados (OCR + análisis → candidatos tipados). Reutiliza la maquinaria existente de `catalog imports` y los artefactos `catalog candidates`/`catalog review` del `ai_gateway`; extiéndela a los tipos nuevos de este encargo (sistemas, roles, reglas de corte, límites). Si el proveedor configurado no acepta imágenes/PDF (ver IA3), la ingesta cubre texto/planillas con extracción y declara la limitación de escaneos.
   - **Ambas vías convergen en la misma revisión:** vista previa como diff contra lo existente, campos con confianza baja marcados para revisión humana, y **nada se publica sin el clic de un revisor**. Lo que la IA no puede extraer con certeza queda UNKNOWN, nunca con un valor por defecto ni inventado. Publicación con procedencia (archivo de origen, método — manual o IA — y revisor), usando las reglas de P16.
6. **Catálogo demo de arranque con precios aleatorios** (decisión del dueño: “primeramente iniciaremos con un catálogo demo con precios random”): fixtures sintéticos más ricos que hoy — PVC practicable 60 y 70 mm, PVC corredera, aluminio corredera y aluminio practicable — con valores y precios plausibles generados aleatoriamente (semilla fija, reproducible). **Todo con `is_demo = TRUE`**, la insignia “DEMO” visible en catálogo, editor, precios y documentos, y nunca presentado como certificado. Los datos reales los carga el dueño por cualquiera de las dos vías de ingesta.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño o técnico que carga el catálogo. Debe sentir: “subo lo que tengo y queda bien integrado”.
- **Anatomía:** Pantalla de ingesta con dos vías (plantilla y cualquier archivo) que convergen en la misma revisión con diff; DEMO marcado en todas partes.
- **Momento de firma (preservar o crear):** La revisión de la IA muestra la fuente (recorte del PDF o celda de la planilla) junto a cada valor extraído.
- **Idea que sube el techo (obligatoria, con el motor):** Arrastrar un PDF de ficha técnica del proveedor produce, en minutos, el sistema completo listo para revisar, con lo dudoso marcado como UNKNOWN.
- **Slop a eliminar aquí:** Un input de archivo sin explicación, errores en inglés, importaciones que publican sin revisión.
- **Preguntas del pase editorial:** ¿Se puede publicar algo que nadie revisó? ¿Cada error de fila dice exactamente qué corregir?

## Criterios de aceptación
- Golden tests de corte por rol (marco, hoja, montante y junquillo) en los dos sistemas practicables, y de corredera en el sistema corredera.
- El motor rechaza una corredera en un sistema practicable (test).
- Ida y vuelta del importador manual: la plantilla de fixture se importa y exporta igual; los errores por fila se testean; la publicación queda con procedencia.
- Ingesta por IA: con el proveedor real (o simulado con respuestas guionadas si no hay credencial), un PDF/planilla de fixture produce candidatos tipados; el test verifica que nada se publica sin revisión, que la confianza baja queda UNKNOWN y que un dato extraído mal no contamina el catálogo.
- Migración de los productos existentes, con test en `make test-db`.
- Capturas: importador con errores y con diff; pantalla de revisión de la ingesta por IA; insignia DEMO en catálogo y precios.
