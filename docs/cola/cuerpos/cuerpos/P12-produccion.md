# P12 — Producción: tablero por estación, detalle de OT escalable y vista de operario táctil

**Depende de:** P01 y P02.

## Objetivo
Que el jefe de producción vea la planta de un vistazo, que una OT de 100 posiciones se navegue sin muros de tablas, y que el operario en una tablet con guantes sepa **qué hacer ahora**, con botones grandes y sin datos comerciales.

## Situación actual
- `frontend/src/features/production/`; backend en `backend/production`; motor en `engine/src/dekopen_engine/manufacturing.py`, `manufacturing_trace.py`, `cutting.py`, `nesting.py` y `operations.py`.
- La fase 14 verificó el ciclo completo: estaciones, QC FAIL → HOLD, remake `OT-…-RM-01`, embalaje, etiquetas y despacho. **La lógica se conserva.**
- (auditoría, sesiones 65e8ad7f, fde66b2e y 0af1700d, y video A-Z)
  - La OT tiene 9 tarjetas de paso, cada una con Iniciar/Bloquear/Anotar, y forma un muro vertical.
  - La tabla de mecanizado filtra enums (SASH, GLAZING_BEAD, FRAME, “cara interior”).
  - Con 100 posiciones aparecen tablas de piezas gigantes (minutos 15–22 del video).
  - La trazabilidad es un log crudo.
  - La tarjeta de faltante y el modal “Motivo del bloqueo” son básicos.
  - El operario usa una vista oscura con letra pequeña.

## Diseño objetivo
1. **Tablero (jefe de producción):** columnas por estación (Corte, Mecanizado, Soldadura, Limpieza, Armado, Herrajes, Vidriado, Control de calidad, Embalaje, Despacho), solo las que existen en la ruta configurada. Cada tarjeta de OT muestra código, obra/cliente, unidades, fecha comprometida, avance x/y y chips de bloqueo (faltante, QC, sin optimizar). Filtros por obra, compromiso y bloqueo. Sin capacidad inventada: si no hay datos de capacidad, no muestres capacidad.
2. **Detalle de OT:**
   - Encabezado: código, estado, compromiso, avance y acciones principales.
   - Pestañas: Resumen · Piezas (virtualizada, agrupada por posición y unidad, con búsqueda por etiqueta de pieza `P01-U02-M03`) · Corte (plan y documentos, P13) · Mecanizado (P14) · Vidrios · Herrajes · Calidad · Embalaje · Trazabilidad.
   - Los **pasos** son una línea compacta (stepper horizontal con estado), no 9 tarjetas. El detalle del paso se abre en un panel.
3. **Trazabilidad humana:** “14:32 · Juan Pérez · Corte de perfiles completado (24 piezas)”, con filtros, y el log crudo solo en “Detalles técnicos”.
4. **Vista de operario** (rol OPERATOR, densidad `workshop` de P01, tablet de 1024×768, oscuro por defecto):
   - Solo la cola de su estación.
   - Una tarjeta grande “Siguiente” con qué hacer y la lista de piezas del paso, con checkbox o escaneo de QR (si hay cámara; si no, input).
   - Botones Completar · Bloquear (motivos predefinidos + otro) · Nota, de 44 px o más.
   - Sin precios, clientes ni márgenes.
   - Texto en lenguaje de taller.
5. **Bloqueos y faltantes:** tarjeta con qué falta (SKU humano, cantidad y color), por qué bloquea y la acción (ir a Compras con la necesidad precargada o usar un retazo compatible si P15 lo ofrece).
6. **Sin enums visibles:** todo pasa por `domainLabels` (P01).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Jefe de taller (planta de un vistazo) y operario (tablet, guantes, 2 m). Deben sentir: “sé qué hacer ahora”.
- **Anatomía:** Constitución §5.10 y densidad `workshop` (oscuro, base 16 px, objetivos ≥ 44 px, idealmente 56). Tablero por estación; OT de 100 posiciones agrupada, no en muros de tablas.
- **Momento de firma (preservar o crear):** F9 (una pieza, una pantalla: código ≥ 32 px en Mono, qué hacer, medida, destino, siguiente) y F7 (naranja = requiere persona).
- **Idea que sube el techo (obligatoria, con el motor):** Escanear la etiqueta es la entrada principal: la estación muestra la pieza, la acción y lo que sigue; QC FAIL crea el remake con un toque y avisa al jefe.
- **Slop a eliminar aquí:** Tablas densas de oficina en la tablet, enums, datos comerciales en la vista del operario, 9 tarjetas de pasos, gestos ocultos.
- **Preguntas del pase editorial:** ¿Un operario con guantes completa su estación sin leer párrafos? ¿El jefe ve el cuello de botella en 5 segundos?

## Criterios de aceptación
- La OT del proyecto de 100 posiciones (fixture) es interactiva en menos de 2 s en local (mide y reporta), y no hay más de 2 pantallas de scroll antes de las pestañas.
- e2e del operario en 1024×768 oscuro: ve solo su estación → completa un paso → bloquea con motivo → el jefe ve el bloqueo en el tablero y en “Hoy”.
- `ux:capture`: 0 enums y 0 objetivos táctiles bajo 44 px en las rutas de operario.
- Tests de etiquetas y de virtualización (renderiza menos de 100 filas DOM con 2.000 piezas).
- Capturas: tablero, detalle y operario.
