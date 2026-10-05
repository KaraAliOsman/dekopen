# P22 — Clientes, empresa y ajustes: la configuración que hace que todo lo demás sea real

**Depende de:** P01 y P02.

## Problema
Varias decisiones de producto necesitan ajustes que hoy no existen o están dispersos: condiciones comerciales por defecto (P08), banda de margen (P07), papel y textos legales (P09), pie white-label (P10), extras por defecto (D06), reglas de montaje (D07), presupuesto de IA (IA3) y numeración (P02). La ficha de cliente es básica. (auditoría, video A-Z min. 25) “Ajustes generales” mezcla cuenta, marca, documentos, Flow, SII y certificado en una sola página larga.

## Alcance
1. **Clientes:**
   - Lista con búsqueda por nombre o RUT y filtros (con proyectos activos, con saldo).
   - Ficha con: persona natural o empresa, RUT validado, giro, contactos (varios, con rol), **direcciones de obra múltiples**, proyectos, cotizaciones, pagos y saldo, documentos, y notas con autor y fecha.
   - Detección de duplicados por RUT; fusión con auditoría.
2. **Ajustes por secciones**, con navegación lateral y permisos por rol. Las secciones que dependen de un encargo no mergeado se muestran deshabilitadas con la leyenda “Disponible cuando…”; no se inventan.
   - **Empresa:** razón social, RUT, giro, dirección, contacto, logo y color de acento para documentos.
   - **Usuarios y roles:** invitar, asignar roles, 2FA obligatorio opcional y desactivar.
   - **Comercial:** IVA, moneda por defecto, vigencia por defecto, condiciones comerciales plantilla (pago, plazo, instalación, exclusiones, garantía y jurisdicción), banda de margen y umbral de descuento con aprobación.
   - **Documentos:** papel, textos legales y pie white-label.
   - **Numeración:** prefijos y siguiente número (solo lectura, salvo decisión explícita).
   - **Producción:** estaciones y ruta, reglas de montaje (D07) y retazos (antigüedad máxima).
   - **Integraciones:** estado de Flow, SII, correo e IA (configurado / no configurado / error), **sin mostrar secretos**.
3. **Onboarding:** el asistente inicial llena Empresa, Comercial y Documentos con valores sugeridos editables, y termina con el “primer proyecto” guiado.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño configurando su empresa una vez, y el estimador buscando clientes todos los días.
- **Anatomía:** Ajustes por secciones con títulos (empresa, marca, documentos, condiciones comerciales, precios, impuestos, integraciones, IA, usuarios y roles); clientes con su historial de obras.
- **Momento de firma (preservar o crear):** La vista previa en vivo del documento al cambiar la marca o las condiciones comerciales (el PDF real, en miniatura).
- **Idea que sube el techo (obligatoria, con el motor):** Ajustes › Integraciones muestra cada integración diferida con su estado y los pasos de activación de `ACTIVACION.md`; los valores por defecto de la constitución aparecen marcados como tales para que el dueño los confirme.
- **Slop a eliminar aquí:** Un muro de campos, guardar sin confirmar el efecto, ajustes sin explicación de dónde impactan.
- **Preguntas del pase editorial:** ¿El dueño entiende qué cambia en el documento del cliente al tocar cada ajuste? ¿Queda claro qué falta conectar?

## Criterios de aceptación
- e2e: crear un cliente empresa con 2 direcciones de obra → crear un proyecto eligiendo una de ellas → la cotización usa esa dirección.
- Test de duplicado por RUT y de fusión.
- Tests de permisos por sección (OWNER vs. ESTIMATOR vs. OPERATOR), en el backend (RLS) y en la UI.
- Cada ajuste que usa otro encargo tiene un test de consumo (por ejemplo, cambiar la vigencia por defecto se refleja en una cotización nueva). Capturas de cada sección.
