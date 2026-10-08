# P21 — Página de proyecto: el centro de trabajo del estimador, con posiciones de verdad

**Depende de:** P01, P02 y P03. Mejor después de D06 y D07 (extras y vano).

## Problema
El proyecto es donde el estimador pasa el día, y hoy es una pila de acordeones. (auditoría, video A-Z y sesiones f5305cc9 y f6e17536)
- El stepper de fases (Cotizada · Enviada · Aprobada · Anticipo · Saldo · Liberada) está bien.
- Las miniaturas de las posiciones son diminutas.
- El panel “Vano seleccionado” muestra datos sueltos.
- Cotización, Cobranza, Importar, Comparar revisiones, Documentos de origen y Actividad quedan ocultos en acordeones.
- Montos como “Precio neto 2910001.00”.
- No se pueden ver, agrupar ni editar 12 o 100 posiciones con comodidad.

Archivos: `frontend/src/features/projects/` (`ProjectPages.tsx`, `ProjectPositionEditor.tsx`, `PositionThumb.tsx`, `ProjectImportsPanel.tsx` y `useProject.ts`).

## Diseño objetivo
1. **Encabezado:** código y nombre, cliente (con enlace), obra y dirección, estado con el stepper de fases, total con IVA, vigencia y **próxima acción** (un solo CTA según el estado: “Completar 2 posiciones”, “Emitir cotización”, “Registrar anticipo”, “Liberar a producción”).
2. **Pestañas:** Posiciones · Cotización (P08) · Precio (P07) · Cobranza (P11) · Producción (estado de las OT y avance) · Documentos (todos los generados, por revisión) · Actividad (línea de tiempo humana).
3. **Posiciones** (pestaña por defecto):
   - Vista **grilla** (miniaturas grandes con el renderer real, en vista interior) o **lista** densa.
   - Agrupación por piso, recinto o eje.
   - Columnas: N.º, Ubicación, Tipología (nombre humano), Vano / Fabricación (D07), Sistema, Color int/ext, Vidrio, Cant., P. unitario, Total y Estado (válida / avisos / bloqueada, con el motivo en un tooltip).
   - Multiselección con acciones en lote: duplicar, eliminar, cambios globales (P08), reordenar y cambiar ubicación o cantidad.
   - Alta rápida desde la biblioteca de tipologías (con el mismo flyout del editor) y desde “Importar” (documento o plano, con la IA del flujo existente `project_from_documents`).
   - Teclado: flechas para navegar, Enter para abrir y Supr para eliminar (con confirmación).
4. **Servicios del proyecto** (D06): instalación, flete y retiro.
5. **Estados vacíos** útiles: “Agrega la primera posición: elige una tipología o importa un plano”.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador trabajando una obra completa. Debe sentir: “tengo la obra entera bajo control”.
- **Anatomía:** Constitución §5.3: encabezado con entidad, Stepper del ciclo de vida y una acción principal según el estado; lista de posiciones con miniatura real, medidas, tipología, vidrio, cantidad, precio y “Qué falta”; selección múltiple con lote.
- **Momento de firma (preservar o crear):** F4 en la lista: medidas editables en la fila; miniaturas que son el dibujo real, no un ícono.
- **Idea que sube el techo (obligatoria, con el motor):** Cambio global con diff: seleccionar por filtro (piso, tipología, vidrio), elegir el cambio y ver posiciones afectadas + Δ de precio + Δ de Uw antes de aplicar; deshacer en un clic.
- **Slop a eliminar aquí:** Filas de texto sin dibujo, acciones repetidas en cada fila, pestañas para todo, estados sin causa.
- **Preguntas del pase editorial:** ¿Se puede llevar una obra de 40 posiciones de borrador a emitible sin salir de esta página? ¿Cada posición dice qué le falta?

## Criterios de aceptación
- El proyecto de 100 posiciones es fluido (lista virtualizada; interactivo en menos de 2 s en local, medido y reportado).
- e2e: crear un proyecto → agregar 3 posiciones desde la biblioteca → agrupar por piso → duplicar en lote → cambio global de color → ver el total actualizado.
- Ningún acordeón oculta un flujo principal; el CTA de próxima acción es correcto en cada fase del fixture (test por fase).
- Capturas en grilla y lista a 1440 y 1024, claro y oscuro.
