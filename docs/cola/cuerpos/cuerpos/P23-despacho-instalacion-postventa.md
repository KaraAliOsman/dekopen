# P23 — Despacho, medición e instalación en obra, y postventa con trazabilidad

**Depende de:** P01, P02 y P12. Coordina con D07 (rectificación de medidas).

## Problema
La cadena termina en la obra, y hoy termina en un botón “Despachado” y una guía PDF básica. El rol INSTALLER existe, pero sin una herramienta de trabajo real. No hay medición en obra desde el móvil, checklist de instalación, recepción firmada por el cliente ni garantía o servicio enlazados a la pieza fabricada.

## Alcance
1. **Planificación de despacho:** calendario por día y vehículo o equipo, OTs embaladas listas para despacho, carga (bultos con etiqueta QR de P13) y guía de despacho `GD-xxxx` (ya existe; mejora su layout con P01 y P09).
2. **App de terreno** (390×844, densidad `workshop` de P01, funciona con mala conexión: cola local y sincronización):
   - **Medición en obra** (D07): por posición, vano en 3 puntos, tipo de muro, montaje y fotos → “rectificada en obra”.
   - **Instalación:** agenda del día, obra con dirección (enlace a mapas), checklist por posición (instalada, nivelada, sellada, regulada y limpia), fotos y escaneo del QR del bulto o de la posición.
   - **Recepción:** firma del cliente en pantalla con nombre y RUT, observaciones y acta PDF inmutable.
3. **Incidencias:** daño, medida incorrecta, faltante o regulación, con fotos → genera según el tipo un remake (OT `RM` existente), una compra o un servicio, y queda enlazada a la posición y a sus piezas (trazabilidad de producción existente).
4. **Postventa:** ticket de garantía o servicio con cliente, obra, posición, pieza, foto, diagnóstico, visita agendada y cierre. Plazo de garantía según las condiciones de la revisión aprobada.
5. **Avisos** en “Hoy” (P03): instalaciones del día, incidencias abiertas y garantías por vencer.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Despachador, instalador en obra (celular, sol, una mano) y postventa. Deben sentir: “sé qué llevar, dónde va y cómo cierro”.
- **Anatomía:** Densidad `workshop` en móvil (390 px): ruta del día, posición con su ubicación en la obra, checklist de carga, cierre con foto y firma; postventa con trazabilidad a la OT y a la pieza.
- **Momento de firma (preservar o crear):** F9 aplicada a obra: una posición, una pantalla; F2: la etiqueta escaneada abre la posición exacta.
- **Idea que sube el techo (obligatoria, con el motor):** La medición en obra rectifica el vano (D07) y crea la revisión automáticamente con el diff para el estimador; la incidencia de postventa sabe qué perfil, vidrio y herraje lleva esa ventana.
- **Slop a eliminar aquí:** Formularios de escritorio en el celular, fotos sin contexto, incidencias como texto libre sin trazabilidad.
- **Preguntas del pase editorial:** ¿Un instalador cierra una instalación con una mano en menos de 1 minuto? ¿Una incidencia de hace 2 años encuentra su ventana?

## Criterios de aceptación
- e2e móvil: el instalador ve su agenda → abre la obra → escanea el QR → completa el checklist con foto → reporta una incidencia → el cliente firma la recepción → el jefe ve la incidencia y crea un remake → la postventa queda enlazada.
- Test de la cola sin conexión (la acción hecha offline se sincroniza una sola vez).
- Acta inmutable (test). Capturas a 390 px.
