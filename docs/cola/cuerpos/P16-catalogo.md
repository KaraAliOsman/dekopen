# P16 — Catálogo técnico: fichas de artículo, procedencia que no se autocertifica y revisión de importación con IA

**Depende de:** P01 y P02.

## Objetivo
Que el catálogo sea la **autoridad visible** del producto: cada perfil, refuerzo, vidrio y herraje muestra qué es, de dónde viene su dato, quién lo revisó y si el sistema está listo para cotizar y fabricar, con la **misma regla** que usan la emisión y la liberación.

## Situación actual
- `frontend/src/features/catalogs/` (`CatalogPage.tsx`, `SectionImportPanel.tsx`); backend en `backend/catalogs` y `backend/ingest`; seed `DEMO_60` en `supabase/seed.sql`.
- (auditoría, sesión f5305cc9 “catalog-workspace” y otras)
  - Lista de sistemas a la izquierda; escalera de *readiness*; “Mapa de relaciones”.
  - Tarjetas de perfil con miniaturas diminutas e insignias “Verificado” y “DECLARADO”.
  - La lectura de *readiness* no siempre coincidía con los gates reales de emisión y congelado.
  - Los conjuntos de SKU de prueba eran mínimos.
  - Importación con IA sin evidencia por línea.
- Riesgos (`known-risks.md`): mapeos de rol duplicados, errores global vs. tenant, demo tratado como certificado, importación IA sin procedencia durable, UNKNOWN convertido en valor por defecto, y secciones importadas con escala, origen u orientación sin verificar.

## Alcance
1. **Página de sistema:** encabezado con nombre, material, profundidad, procedencia (DEMO, DECLARADO por el fabricante o VERIFICADO con documento y revisor) y **readiness PASS/WARN/BLOCK** calculado con **la misma función** que usan los gates de emisión y liberación. Agrega un test de paridad: para cada fixture, el resultado del catálogo es igual al resultado del gate.
2. **Pestañas:** Perfiles · Refuerzos · Vidrios (composiciones y formatos de lámina) · Herrajes (kits por tipo de apertura y rango de medidas) · Reglas de compatibilidad · Costos (cobertura, enlazada a P07) · Historial.
3. **Ficha de artículo:**
   - Miniatura de la sección **desde la geometría real**, con escala, origen y orientación visibles.
   - Rol en español, ancho de cara, masa por metro, pérdida de soldadura y largo de barra.
   - Insignia de procedencia que abre: documento de origen, página o línea, revisor y fecha.
   - Validaciones de la sección: autointersección, profundidad vs. bounding box y origen local; si fallan, el artículo no puede pasar a VERIFICADO.
4. **Procedencia protegida en la base de datos:** un miembro no puede elevar la procedencia a VERIFICADO sin el rol de revisor técnico (trigger o RLS). Un test de `make test-db` lo demuestra. Revisa los defectos históricos de autorización global vs. organización en paneles (el PR #107 los dejó en verde; agrega un test de regresión si no existe).
5. **Revisión de importación (IA):** tabla de candidatos con confianza, **evidencia de origen** (extracto de página o línea del PDF o XLSX), diff contra el artículo existente y conflictos marcados. LOW y REVIEW_REQUIRED quedan **desmarcados por defecto**. Lo no extraído queda UNKNOWN. Al confirmar se re-deriva desde el candidato guardado. Identidad del revisor y hora, y auditoría inmutable desde la importación hasta la publicación.
6. **Bloqueadores con deep link:** cada BLOCK enlaza al artículo o regla exacta que lo causa.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño o el técnico que mantiene el catálogo. Debe sentir: “sé de dónde viene cada dato y si puedo fabricar con él”.
- **Anatomía:** Catálogo como autoridad: cada registro con procedencia (manual o IA), revisor, estado (DEMO, importado, revisado, certificado) y readiness con la misma regla que la emisión y la liberación.
- **Momento de firma (preservar o crear):** `DemoBadge` en todo lo sintético; la sección de perfil dibujada (F10) en la ficha del perfil.
- **Idea que sube el techo (obligatoria, con el motor):** Subir cualquier archivo (PDF, planilla, foto) y revisar los candidatos de la IA campo por campo con la fuente resaltada junto al valor extraído.
- **Slop a eliminar aquí:** Tablas planas sin procedencia, readiness que no coincide con los gates, datos sintéticos sin marca.
- **Preguntas del pase editorial:** ¿Se puede confundir un dato DEMO con uno certificado? ¿Cada valor extraído por IA muestra su fuente?

## Criterios de aceptación
- Test de paridad readiness ↔ gates en los fixtures DEMO_60 y en uno incompleto.
- Test de BD: autocertificación rechazada para el rol miembro.
- e2e: importar el PDF de fixture → revisar → desmarcar o corregir → publicar → el artículo muestra su procedencia con evidencia → la auditoría lista cada paso.
- Sin mensajes nativos (P01 ya corrige los `pattern=` de `CatalogPage.tsx`; verifica). Capturas de la página de sistema, la ficha y la revisión de importación.
