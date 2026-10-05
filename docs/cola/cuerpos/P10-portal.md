# P10 — Portal de propuesta v2: marca del fabricante, decisión con evidencia y estados honestos

**Depende de:** P01, P02 y P08. Mejor después de P09 (coherencia visual con el PDF).

## Objetivo
Que el cliente final reciba un enlace que parezca **del fabricante**, no de DEKOPEN; que entienda qué compra y cuánto paga por cada ítem; que apruebe, pida cambios o rechace con una evidencia válida; y que nunca vea un estado engañoso.

## Situación actual
- Ruta pública `/cotizacion/:token` (`frontend/src/features/portal/`) y `/pago/retorno`; backend en `backend/portal`.
- (auditoría, sesiones 746af5bf, f6e17536 y 65e8ad7f)
  - Tarjetas de producto pequeñas y un selector Visual/Técnica.
  - El formulario de aprobación pide nombre, RUT y comentario.
  - Un enlace revocado muestra un genérico “No pudimos cargar la cotización”.
  - Con un banner de “reemplazada” **sigue visible “Pagar ahora”**.
  - Rechazar una cotización ya aprobada da un 409 confuso.
  - Pie “Generado con DEKOPEN”.
  - La ruta de retorno del pago es incorrecta en algunos casos.
  - En 390 px funciona, pero sin optimizar.

## Diseño objetivo
1. **Encabezado** del emisor: logo, razón social y contacto. Título del documento y favicon del emisor. El pie “Generado con DEKOPEN” solo si la organización lo permite (ajuste).
2. **Hero:** obra, cliente, total con IVA en la moneda real, vigencia (“Válida hasta 27-10-2026 · quedan 12 días”) y estado.
3. **Posiciones:** render grande y ampliable (zoom y pan táctil), selector Comercial/Técnica (con vista declarada, P05), medidas, cantidad, especificaciones clave, y **precio unitario y total de línea IVA incluido**. La suma de líneas es igual al total del encabezado; el redondeo es explícito si existe. Las alternativas van marcadas aparte.
4. **Condiciones y documentos:** calendario de pagos, plazos, instalación, exclusiones, garantía y descarga del PDF **de la misma revisión**.
5. **Panel de decisión:**
   - **Aprobar:** nombre, RUT validado y checkbox “Acepto la propuesta COT-P-000123-REV-B por $X IVA incluido y sus condiciones”.
   - **Solicitar cambios:** comentario obligatorio.
   - **Rechazar:** motivo opcional.
   - Después de decidir, se explican los próximos pasos (“El fabricante te contactará para coordinar la medición final y el anticipo”).
   - Se guarda la **evidencia**: fecha y hora, IP, user agent, revisión y su huella, nombre y RUT. El estimador la ve en el proyecto.
6. **Pago:** el CTA aparece **solo** si la revisión está aprobada y sellada, no reemplazada ni vencida, y con saldo mayor a 0. El monto es menor o igual al saldo (sin sobrepago). El retorno de Flow vuelve al portal correcto con el estado del pago. Con el proveedor simulado (Flow es integración diferida), el CTA funciona de punta a punta y muestra la insignia discreta “Modo de prueba”; si ningún proveedor de pago está habilitado para la organización, el CTA no aparece y no se muestra un error.
7. **Estados dedicados**, cada uno con su página: revocada, expirada, reemplazada (con enlace a la vigente si el emisor lo permite), ya decidida (muestra la decisión, sin un 409 crudo) y no encontrada. Todas explican qué pasó y a quién contactar.
8. **Seguimiento:** apertura y vistas registradas; aprobación, cambios y rechazo generan ítems de atención para el estimador (P03).
9. **Móvil primero:** 390×844 es una experiencia completa.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El cliente final, en el celular, sin vocabulario técnico. Debe sentir: “entiendo qué compro y confío”.
- **Anatomía:** Constitución §5.9, densidad `document`, perfecta a 390 px: portada de la obra, resumen en lenguaje simple, posiciones con dibujo (y 3D si P19 existe), alternativas comparables, condiciones, una acción (Aprobar) y estado honesto del enlace.
- **Momento de firma (preservar o crear):** F11: una revisión reemplazada lo dice con claridad y lleva a la vigente; nunca muestra “Pagar ahora” donde no corresponde.
- **Idea que sube el techo (obligatoria, con el motor):** Comparar alternativas lado a lado (A: PVC blanco / B: foliado nogal) con dibujo y precio, y aprobar la elegida; pedir cambios marcando la posición exacta.
- **Slop a eliminar aquí:** Plantilla de marketing genérica, botones flotantes múltiples, errores 409 crudos, la marca DEKOPEN por encima de la del fabricante.
- **Preguntas del pase editorial:** ¿Una persona de 60 años aprueba desde el celular sin llamar a la fábrica? ¿Algún estado puede engañar?

## Criterios de aceptación
- e2e por estado: vigente, aprobada, cambios solicitados, rechazada, revocada, expirada, reemplazada y no encontrada. Capturas a 1440 y 390.
- Test: la suma de líneas es igual al encabezado en el proyecto de 12 posiciones; moneda USD correcta en un fixture USD.
- Test de que el CTA de pago está oculto en reemplazada, vencida, no aprobada y sin saldo; test de sobrepago rechazado (backend).
- Test de que la evidencia de aceptación se persiste completa e inmutable.
- axe sin *serious*; Lighthouse móvil con rendimiento ≥ 80 en el fixture local (repórtalo aunque no sea gate).
