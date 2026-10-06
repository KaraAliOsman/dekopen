# Verificación E2E real — P08 Cotización/emisión (rama devin/P08-cotizacion-emision)

Fecha: 2026-10-06 · Probado en navegador real (Chrome) contra stack local completo
(Supabase :25321, Django :8000, Vite :5173) · Proyecto P-000002 P-COTIZADO.
Grabación de pantalla + anotaciones adjunta en la sesión Devin.

## Veredicto por punto del flujo de aceptación

1. **Checklist guía hasta completar → emisión REV-A** — VERIFICADO.
   Checklist "Qué falta para emitir" con ítems enlazados (scroll+highlight),
   "Todo listo — puedes emitir.", acción canónica "Emitir y enviar al cliente",
   diálogo de confirmación con revisión/total/vigencia/destinatario/consecuencia,
   toast + caja de enlace `/cotizacion/{token}`.
2. **Portal fresco + vista registrada + "Solicitar cambios"** — VERIFICADO.
   Propuesta renderiza en contexto incógnito; cada GET suma `view_count`
   (Vista ×N); "Solicitar cambios" con comentario → link sigue vigente,
   card "Pediste cambios".
3. **Hoy + campana** — VERIFICADO (ítem "El cliente pidió cambios…" en Hoy;
   campana muestra conteos agregados por categoría).
4. **Cambio global de vidrio + emitir REV-B** — EJECUTADO CON DEFECTOS
   (ver abajo). REV-B emitida; diálogo muestra "la Revisión A quedará reemplazada".
5. **Supersedencia REV-A** — API correcta (`superseded:true`, decide → 409
   `quote_link_stale`), portal muestra banner "reemplazada" + card "Pediste
   cambios" sin formulario — PERO la app muestra la etiqueta INVERTIDA
   (DEFECTO #4).
6. **Aprobación cliente REV-B** — VERIFICADO. Portal "Aprobar propuesta" →
   link APPROVED, proyecto → APPROVED, stepper Aprobada→Anticipo.
7. **Inmutabilidad REV-A** — VERIFICADO. `COT-P-000002-REV-A.pdf` muestra
   vidrio "Termopanel incoloro 4·16·4" sellado; REV-B muestra
   "4 / 16 Ar / 4 Low-E (c3)".
8. **Fallback de portapapeles** — VERIFICADO. Con `clipboard.writeText`
   rechazando y `execCommand` lanzando: input readonly + "Selecciona el
   enlace y cópialo con Ctrl+C."; `window.prompt` nunca se invocó.
9. **Un solo camino de emisión** — VERIFICADO por grep: `documentaryFreeze*` /
   `projectQuoteLinkCreate` solo en `ProjectQuotationPanel.tsx`
   (ProjectPages.tsx solo llama `projectQuoteLinksList` — lectura).
10. **Acciones del enlace** — VERIFICADO: Cambiar vencimiento (modal + input
    fecha, expires_at actualizado), Revocar (confirmación "perderá acceso",
    status REVOKED), Regenerar (nuevo token minteado).

## Estados del portal /cotizacion/{token}

| Estado | API | UI observada |
|---|---|---|
| Vigente | 200 | Propuesta completa + formulario de decisión |
| Vista N | 200 | `view_count` incrementa por GET (incl. curl) |
| Cambios pedidos | 200 | Card "Pediste cambios" + formulario |
| Aprobada | 200 | Card "Propuesta aprobada", sin formulario |
| Expirada (vigencia) | 200 + `validity_expired` | "plazo vencido" + "ya no está vigente", sin formulario |
| Reemplazada (emit supersede) | 200 + `superseded` | Banner "reemplazada por una revisión nueva", sin formulario |
| Revocada | 410 `quote_revoked` | Card genérica "no existe o ya fue usado" |
| Reemplazada (fixture) | 410 `quote_revoked` | Misma card genérica |

Delta vs texto del encargo: "portal 410 del token viejo" — el superseded
real es 200+banner (solo links REVOKED dan 410). El token fixture
"reemplazada" está almacenado REVOKED, por eso da 410.

## DEFECTOS

### #1 — Panel "Cambios globales" muerto en todos los estados alcanzables
- **Ops de producto (vidrio/espesor/manilla/panel):** `positionsRetrieve`
  devuelve `design.parametric_tree` como árbol de módulos pelado
  (`{type:'SPLIT_V',children:[BAY…]}`); `isProductModel()` exige `assembly`
  → cada fila queda `status:"unsupported"` → "el motor no admite el cambio";
  nunca se envía el POST batch-preview; botón aplicar deshabilitado.
- **Ops acabado/sistema:** saltan `productOps` → `pricingDesignBatchPreview`
  devuelve 422 `technical_authority_required` (tragado → "sin costo
  referencial") → "Aplicar a N posiciones" dispara PUTs → todos 409
  `commercial_revision_required` → banner **mentiroso** "Cambio aplicado.
  0 de 5 posiciones actualizadas".
- Repro: proyecto cotizado → Cotización → Cambios globales → Vidrio →
  VIDRIO-LOWE-24 → Previsualizar (5× unsupported) / Acabado → Aplicar
  (0 de 5 con mensaje de éxito).

### #2 — `quote-preview/` 422 `pdf_value_not_scalar`
Preview DOC-01 falla siempre: `sealed_at` datetime sin serializar en el
snapshot. Panel muestra "La evidencia documental no pudo guardarse…";
el diálogo de emisión muestra "Huella del documento" = "…" (vacío).

### #3 — Fixture P-COTIZADO no emitible / checklist optimista
Inspector rojo R04 en posición 5 (DVH 1400×2200 > 2.6 m²) pero el checklist
muestra "Todo listo — puedes emitir." — el checklist no refleja bloqueantes
del inspector. Workaround: redimensionar pos5 a 1800.

### #4 — Etiqueta "Reemplazada" invertida (ProjectQuotationPanel.tsx:2415)
`latestRevision = project.versions?.[0]?.revision_code` toma la revisión
más VIEJA (REV-A) → `superseded = link.revision_code !== latestRevision`
marca como "Reemplazada — Revisión B → Revisión A" los enlaces NUEVOS
REV-B (vigentes) mientras las filas REV-A (realmente reemplazadas) siguen
mostrando estados vivos. Además la compuerta `link.revision_code ===
latestRevision` (línea ~2539) hace que "Copiar enlace" aparezca solo en
filas viejas. Evidencia: `evidence-DEFECT-reemplazada-invertida.png`.

### #5 — Hueco cross-system de vidrio (integridad de datos)
PUT /positions aceptó `glass_article_sku=VIDRIO-LOWE-24` en una posición
cuyo sistema (f9398347) no tiene mapping de compra para ese vidrio →
freeze posterior falla 422 `glass_purchase_mapping_missing_or_ambiguous`
con detalle genérico. El trigger `guard_referenced_catalog` bloquea
agregar el mapping a sistemas referenciados. Workaround usado: revertir
pos5 a DVH-20.

## Menores

- Portal 410 descarta el detalle "fue revocado; solicita uno nuevo" y
  muestra el genérico "no existe o ya fue usado".
- Card "Pediste cambios" dice "aún puedes aprobar o rechazar" en enlaces
  superseded donde no hay formulario (decide → 409).
- `view_count` sube con cualquier GET (curl/escáneres incluidos) — "Vista ×N"
  inflado.
- Diálogo "Regenerar" dice "revoca los enlaces vigentes" pero el enlace
  APPROVED sigue resolviendo 200 (semántica ambigua — decididos no se revocan).
- Botón portal con nombre vacío bloquea submit silenciosamente (sin error
  visible).

## Capturas

- `shots/` — 152 capturas ux:capture (portal-* 40, project-* 48,
  dashboard* 46, settings-* 18; 1440×900/1280×800/1024×768 claro+oscuro,
  390×844 en rutas extraMobile incl. portal) — **0 findings nuevos**.
- `evidence-*.png` — capturas manuales del flujo real (19).
- `COT-P-000002-REV-A.pdf` / `-REV-B.pdf` — evidencia de inmutabilidad.
- `report.json` / `index.html` — reporte ux:capture.

## Addendum post-rebase (sobre P06+ED1+P13+P15) — smoke PASS

Re-verificado en navegador real tras el rebase sobre `integracion/v1` final:
checklist 9/9 con compuerta real (bloqueó emisión por regla crítica del
inspector hasta corregir el vidrio), preview DOC-01 renderiza (defecto #2
resuelto — huella poblada), emit REV-A limpio, coexistencia y persistencia de
«Vigencia de la cotización» (P08) + «Etiquetas de pieza» (P13) en Ajustes,
portal + «Solicitar cambios» → Hoy/campana, claro/oscuro limpio.
Capturas `smoke-*.png` en este directorio.

Defectos #1–#4 corregidos en rama: #2 preview canonicaliza el snapshot antes
de renderizar; #4 `latestRevision` usa la revisión vigente (`at(-1)`); #3 el
checklist declara `inspector_blocked` por posición; #1 el panel de cambios
globales envuelve el árbol clásico (`wrapTreeAsProduct`) para correr las ops
por el registro del editor en vez de declarar «unsupported» en todo.
