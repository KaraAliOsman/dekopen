# P15 — Compras, recepción, inventario y retazos como stock de primera clase

**Depende de:** P01 y P02 (códigos OC, RT y REC).

## Objetivo
Separar con claridad **Compras** (qué hay que comprar, a quién y cuándo llega) de **Inventario** (qué hay, dónde está, para qué está reservado y qué sobra), y tratar los retazos como material real, con código, ubicación y destino.

## Situación actual
- `frontend/src/features/purchasing/`; backend en `backend/purchasing` y `backend/inventory`; motor en `engine/src/dekopen_engine/purchasing.py`. `/inventory` redirige a `/purchasing` (`App.tsx`).
- La fase 14 verificó: elegibilidad → asignaciones → confirmar → enviar → recepción parcial con dañados → cancelar libera exactamente lo pendiente → recompra → FULFILLED. **La lógica se conserva.**
- (auditoría, sesiones c2f89c63, ef05295b y f6e17536)
  - En la sección “Stock de materiales” aparece **“No se pudo cargar esta sección — recarga la página”**.
  - Cantidades con 4 decimales y códigos OC con hash (P02).
  - La etiqueta de retazo con QR está bien.
  - En la página Trabajos aparecieron errores técnicos crudos (“IntegrityError … violates check constraint document_artifacts_check2”); P17 cubre esa página, pero aquí verifica que ninguna acción de compras produzca ese error.

## Alcance
1. **Causa raíz** del error al cargar el stock: reprodúcelo con el fixture, corrígelo y agrega un test que lo cubra.
2. **Compras** (`/purchasing`):
   - Necesidades agregadas desde las OTs liberadas.
   - Propuesta de compra por proveedor, editable.
   - OC `OC-000123` con estado, fechas y montos.
   - Envío al proveedor (PDF y correo, con un clic humano explícito).
   - Recepción.
3. **Recepción** por línea: cantidad recibida, dañada, lote, rack o ubicación, guía del proveedor y fecha. Advertencia de sobre-recepción con confirmación. El resultado se ve en el stock al instante.
4. **Inventario** (`/inventory`, ruta propia):
   - Stock por SKU, color y largo, con disponible, reservado (por qué OT) y en tránsito.
   - **Retazos** `RT-000045` con perfil y color (autoridad del catálogo), largo, rack, edad, OT de origen y reserva de destino. Acciones: mover de rack, reservar, desechar (con confirmación y motivo) e imprimir la etiqueta QR. Alerta de retazos viejos (días configurables).
   - **Libro de movimientos** con actor, rack, lote, documento de origen y fecha.
5. **Integración con producción:** si una OT tiene un faltante y existe un retazo compatible, se ofrece usarlo. La compatibilidad la decide el motor (largo útil ≥ requerido + mermas declaradas). Nunca la decide la UI.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Jefe de compras/bodega. Debe sentir: “sé qué falta, qué llega y qué sobra”.
- **Anatomía:** Compras e Inventario separados en la navegación; retazos como material real con código, ubicación y destino.
- **Momento de firma (preservar o crear):** F6 aplicada a necesidades: cada cantidad a comprar explica de qué OT y qué faltante sale.
- **Idea que sube el techo (obligatoria, con el motor):** “Comprar lo que falta” calcula contra stock y retazos, agrupa por proveedor y deja la orden lista para enviar con un clic (el envío real por correo es integración diferida: queda preparado).
- **Slop a eliminar aquí:** Stock sin ubicación, retazos como notas, compras y stock mezclados en la misma tabla.
- **Preguntas del pase editorial:** ¿Un retazo se puede encontrar físicamente con lo que dice la pantalla? ¿Cada compra se justifica?

## Criterios de aceptación
- e2e: liberar OT → aparecen las necesidades → generar OC → enviar → recepción parcial con 1 dañado → stock actualizado → reserva de la OT → consumo al cortar → el retazo resultante aparece con su código RT y su rack.
- Tests de sobre-recepción, de desecho con motivo y de movimiento de rack con auditoría (actor).
- Sin errores al cargar el stock (test) y `ux:capture` sin hallazgos en `/purchasing` ni `/inventory`.
