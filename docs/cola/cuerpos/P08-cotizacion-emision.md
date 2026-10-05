# P08 — Constructor de cotización, emisión canónica, ciclo de vida del enlace y cambios globales

**Depende de:** P01, P02 y P07. Coordina con P09 (documento) y P10 (portal).

## Objetivo
Que emitir una cotización sea **un flujo guiado, sin sorpresas**: el sistema dice qué falta, muestra exactamente lo que va a ver el cliente, pide confirmación y deja una revisión sellada con un enlace cuyo estado (vigente, vista, revocada, expirada, reemplazada) se puede seguir.

## Situación actual
- Archivos: `frontend/src/features/projects/ProjectQuotationPanel.tsx` y `ProjectPages.tsx`; backend en `backend/projects`, `backend/documents` y `backend/portal`.
- (auditoría) Formulario de emisión largo (sesión a693d250 “A-13-emission-form-top”); hay varios caminos a “Enviar al cliente”; copiar el enlace falla sin alternativa; el portal público dio 409 (“A-16-public-quote-409”); validaciones en inglés; el RUT no se validaba; los límites de medidas no estaban atados a los límites de fabricación.
- La fase 14 (`docs/redesign/phase14-close-report.md`) verificó: emisión REV-A, sucesora REV-B con edición bloqueada en la emitida (409 `revision_required`) y comparación REV-A ↔ REV-B. **Esa lógica se conserva.**

## Diseño objetivo (pestaña “Cotización” del proyecto)
1. **Checklist “Qué falta para emitir”**, siempre visible y en el orden en que se resuelve: cliente con RUT válido; dirección de obra; todas las posiciones válidas y con precio (o con bloqueo explicado); vigencia; condiciones de pago; plazo de entrega; alcance de instalación; exclusiones; garantía. Cada ítem enlaza y hace scroll al campo, que queda resaltado.
2. **Condiciones comerciales** con plantillas por organización (en Ajustes): calendario de pagos (por ejemplo, 50 % anticipo / 50 % contra entrega), plazo, instalación, exclusiones, garantía y jurisdicción. Son editables por cotización y quedan **congeladas** en la revisión.
3. **Vista previa real** del documento que va a recibir el cliente (el mismo template de P09, en HTML o PDF), al lado del formulario.
4. **Confirmación** antes de emitir: revisión, total, moneda, vigencia, destinatario y lo que va a pasar (“Se sellará REV-B; la REV-A quedará reemplazada”).
5. **Una sola acción canónica:** “Emitir y enviar al cliente”. Sella la revisión, genera el enlace y envía el correo con la infraestructura de correo existente. Ofrece “Copiar enlace”, con fallback de selección manual si el portapapeles falla, y “Descargar PDF”. Elimina los caminos alternativos duplicados.
6. **Ciclo de vida del enlace:** estado (vigente, vista N veces, última vista, decisión), revocar, regenerar, cambiar vencimiento y línea de tiempo del proyecto (emitida → vista → cambios solicitados → REV-B → aprobada).
7. **Cambios globales** (patrón de Windowmaker Web “Global Changes”): cambiar vidrio, color o acabado, serie o altura de manilla en **todas** o en las posiciones seleccionadas, con vista previa del impacto en precio y validez, y aplicación con una sola operación deshacible. Usa la operación `apply_to_positions {filter, ops}` del registro único de IA2; si aún no está mergeada, agrégala **al registro** (no una vía paralela) y coordina con P21, que usa la misma operación desde la página de proyecto.
8. **Validación** en español (P01), RUT módulo 11 y límites de medidas desde el catálogo o el motor (límites de fabricación del sistema), con un mensaje que cite el límite y su fuente.

## Fuera de alcance
Layout del PDF (P09), páginas del portal (P10) y cobranza (P11).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador en el momento de mayor riesgo: emitir. Debe sentir: “no hay sorpresas”.
- **Anatomía:** Un solo camino de emisión: checklist “Qué falta” → vista previa real del PDF → confirmación con consecuencia → sello. Estado del enlace como `Stepper`.
- **Momento de firma (preservar o crear):** F11 (sello de revisión) y F2 (huella en el cajetín) visibles en la confirmación.
- **Idea que sube el techo (obligatoria, con el motor):** El checklist se cumple solo a medida que se completa la obra, y cada faltante lleva al lugar exacto donde se resuelve; la vista previa es el PDF real, no una maqueta.
- **Slop a eliminar aquí:** Varios botones de emitir en lugares distintos, “¿Está seguro?” sin consecuencia, vista previa que no coincide con el PDF.
- **Preguntas del pase editorial:** ¿Es imposible emitir algo que no se vio? ¿El estado del enlace se entiende sin leer documentación?

## Criterios de aceptación
- e2e completo con el fixture: el estimador abre el proyecto de 12 posiciones → el checklist lo guía hasta completar → emite REV-A → copia el enlace → el cliente lo abre (vista registrada) → solicita cambios con comentario → el estimador recibe el ítem en “Hoy” y en la campana → hace un cambio global de vidrio → emite REV-B (el enlace de REV-A pasa a “reemplazada”) → el cliente aprueba REV-B.
- Test de inmutabilidad: la REV-A sellada no cambia después del cambio global.
- Test del fallback del portapapeles. Test de que no queda ningún camino de emisión alternativo (búsqueda de llamadas al endpoint de emisión).
- Capturas de cada estado del checklist y del enlace.
