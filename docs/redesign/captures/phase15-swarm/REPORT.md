# Phase-15 — Barrido exhaustivo en vivo (final user-facing validation pass)

HEAD `9f9e8c3` (`devin/1790335313-commercial-workspace`). Stack en vivo: Vite :5173, Django :8000, Supabase docker (:25321/:25322), Mailpit :25324, runjobs con `AI_GATEWAY_MOCK_ENABLED=1`, Chrome CDP :9333. Grabación continua con anotaciones durante todo el barrido.

## Veredicto

Barrido hostil completado: todas las secciones del mandato (1–9) ejercitadas en vivo. Sin hallazgos críticos bloqueantes. 2 defectos visuales móviles, varias notas menores.

## Recorridos

### (1) Jornada comercial — PASS
P-000004 "Cien posiciones F14": segunda posición creada 100% por UI (biblioteca → serie → vidrio por hoja → altura manilla → guardar). Precio vía UI: extra instalación $150.000 → "Calcular y revisar" → "Aprobar y aplicar" (probe doble-click: botón deshabilita en vuelo, una sola op APPLIED). Emisión REV-A por UI ("Preparar emisión": términos + vigencia + "Usar sugeridas" + confirmación → emitió quote-only por bloqueos de producción del inspector — correcto). Link compartido → portal público → aprobación con doble-click → estado único "Propuesta aprobada". Capturas 10–19.

### (2) Producción incl. QC fail→remake — PASS
OT-02: 6/6 pasos por UI → packing → GD-0003. OT-04: pasos → QC "Rechazar" con motivo → orden HOLD + QC BLOCKED → "Rehacer orden" → RM-01 RELEASED con motivo → guard de optimización verificado (sin Iniciar antes del plan) → 6/6 pasos → packing+etiquetas → GD-0002. Ambas despachadas muestran "Confirmar instalación" + "Emitir DTE-52". Capturas 20–35.

### (3) Compras — PASS
PO-C0F11389D095 (Perfiles): BORRADOR → "Registrar envío al proveedor" (form inline fecha+contacto+confirm) → ENVIADA → recepción parcial por UI (JQ-10: 6 pedidas, 5 recibidas con 1 dañada → `outstanding=2`, el dañado NO cubre; ACERO-MARCO 2/5) → PARTIALLY_RECEIVED con alerta "Unidades recibidas con incidencia: 1.00" → "Cancelar orden" (diálogo con copy claro) → ANULADA conservando evidencia "1 dañado: 1.00"; cobertura recalculada (Recibido 4.00 efectivo). Capturas 36–44.

### (4) Inventario — PASS
Ajuste de stock: ADJUSTMENT +5 a COMPRA-ACERO-CANAL-U con nota obligatoria → registrado en `inventory/movements` (actor owner). Retazos: "Etiqueta" muestra tarjeta con QR + identidad + medidas + rack; "Imprimir etiqueta" → `window.print()` con CSS `@media print` que aísla solo la etiqueta (correcto). "Desechar" con diálogo de confirmación → tab Desechado(1). Capturas 45–50.

### (5) IA — PASS (con nota)
Ask contextual (MOCK, datos reales: "5 proyectos y 5 órdenes de producción abiertas") + 2 agent jobs → respuestas deterministas + "ver trabajo". **Reload restaura el transcript completo incl. respuestas — el bug F12-1 de respuestas restauradas en blanco está resuelto.** Cancel mid-run no ejercible: rondas MOCK <100ms (limitación honesta; cancel QUEUED/WAITING ya verificado en fase 12). Capturas 51–56.

### (6) Nav sweep — PASS con 2 hallazgos
10 rutas × claro/oscuro/390px. Desktop (1600) y oscuro: sin scroll-x, jerarquía legible. Móvil 390: limpio excepto F-15.1 y F-15.2. Capturas 61–65.

### (7) Orb/BotFigure nuevo — PASS
`orb is-idle/success` en dock (22/26px): esfera grafito + ojos cápsula cian + anillo orbital bajo. `bot-figure` hero en /assistant (120px): esfera + anillo + sombra + panel contextual translúcido — se lee correctamente. Capturas 57–60.

### (8) Documentos — PASS
Generados por UI y verificados: DOC-01 (3pp, cotización), DOC-02 (1pp pedido vidrio), DOC-03 (12pp matriz ensamble), DOC-04 (5pp pedido perfiles), DOC-05 (14pp plan de corte), DOC-06 (1pp checklist QC), DOC-07 (1pp informe costos), PO genérico — todos `%PDF-1.7` + `%%EOF` + texto extraíble real. XLSX (DOC-02/04/PO) zips válidos (PK magic, testzip ok). Archivos en este directorio.

### (9) Errores — PASS
- Enlace vencido `/auth/callback#...otp_expired...` → "El enlace venció. Solicita uno nuevo para entrar." + "Volver al acceso". (66)
- OPERATOR → /projects → "Sin acceso. Tu rol no permite editar proyectos." + rail reducido correcto. (68)
- Login email inválido → validación nativa bloquea envío. (67)
- Offline total → página de error del navegador (la SPA no tiene service worker — comportamiento esperado, no degradación in-app). (69)

## Hallazgos

| # | Sev | Hallazgo | Repro / evidencia |
|---|-----|----------|-------------------|
| F-15.1 | 🟡 | `/catalogs/systems` overflow móvil: sw=516 @ 390 (header del detalle sw=987 — nombres largos de sistema no envuelven, título cortado a la derecha) | 390px → seleccionar GLASS_45 → scroll-x. `64-mob-catalog.png` |
| F-15.2 | 🟢 | `/production` overflow móvil menor: sw=419 @ 390 — input "ID de la pieza" / tarjetas de orden se pasan ~29px | `65-mob-production.png` |
| F-15.3 | 🟢 | Etiqueta de retazo no tiene botón cerrar (queda renderizada en línea hasta abrir otra) | `48-remnant-label.png` |
| F-15.4 | 🟢 | Cancel mid-run de IA no ejercible con MOCK (rondas <100ms) — limitación de prueba, no defecto | — |
| F-15.5 | 🟢 | Sin service worker: navegación offline muestra error del navegador, no shell degradado | `69-offline.png` |
| F-15.6 | 🟢 | Copy: pricing muestra "Cotización inicialprimera cotización f15" (concatenación de motivo+label) | captura pricing sección 1 |

## Notas de infraestructura (para el lead)
- Dos procesos runjobs pueden estar corriendo (pids vistos tras rebuild) — verificar singleton.
- La mutación de fixture incluye: P-000004 aprobado con 2 posiciones, OT-02/OT-04-RM-01 despachadas (GD-0002/03), PO perfiles anulada, retazo desechado, ajuste stock +5, jobs IA MOCK.

## Evidencia
PNGs `01–69` + PDFs/XLSX generados en este directorio. Video: `sweep-full.mp4` (44:28 toma continua completa, concatenada de `raw-*.mkv`) + `sweep-annotated.mp4` (ventanas de anotación). Raw: `/home/ubuntu/screencasts/rec-ba1a063b-d72e-4fbc-90b3-87a7fa021553/`.
