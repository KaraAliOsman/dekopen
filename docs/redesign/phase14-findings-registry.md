# Registro consolidado de hallazgos — fase 14

Reconstrucción del diagnóstico acumulado: no existe una lista única F01–F64; este
registro consolida los hallazgos de todas las reviews/fases ejecutadas sobre la rama
`devin/1790335313-commercial-workspace`. Cada entrada declara su estado con evidencia
(commit, fase de revalidación) o razón de pendiente.

**Vocabulario:** Resuelto = corregido en la rama con commit identificable.
Revalidado = además verificado en vivo en una fase posterior. Parcial = corregido en
parte; el resto sigue abierto. No reproducido = la review no pudo o la premisa era
falsa. Pendiente = sin corrección; se indica razón/bloqueo.

Convención de evidencia: los ids de commit abreviados corresponden a la rama
(`git show <sha>`); "fase-NN" apunta a `docs/redesign/captures/phaseNN/REPORT.md`.

---

## A. review-commercial.md — F1–F29 (comercial / cotización / portal / SII)

| ID | Hallazgo | Estado | Evidencia / razón |
|----|----------|--------|-------------------|
| F1 | Documentos sin white-label, marca DEKOPEN fija | Resuelto | §09-A branding org + masthead en los 6 renderers (`c47bd62`) |
| F2 | Cotización sin cuerpo legal/comercial (emisario, validez, condiciones, anticipo, firma) | Resuelto | §09-C IA de propuesta: identidad, condiciones, aceptación, plan de pagos (`0320828`, `88bc07c`) |
| F3 | Sin folio de cotización (solo hash) | Resuelto | `COT-{proyecto}-{revisión}` impreso (renderers.py:1168) |
| F4 | Sin precio unitario/descuento por posición | Resuelto | `line_detail` por línea (service.py:305-326) + tabla decisión con precio unitario |
| F5 | Impuesto sin tasa etiquetada | Resuelto | línea IVA con tasa implícita impresa en propuesta/DOC-01 (`88bc07c`) |
| F6 | Moneda ambigua (CLP/USD) | Resuelto | moneda congelada en snapshot y mostrada; USD mantiene decimales (`88bc07c`) |
| F7 | Posiciones de contorno/arco renderizan silueta vacía | Resuelto | trayectorias de contorno en renderers DOC (r4/r7 de #92) |
| F8 | Hash de integridad impreso al cliente | Resuelto | hash a metadatos/QR, truncado 24ch (`50dfa6e`) |
| F9 | "Relleno" etiqueta vidrio sin spec | Resuelto | scrub es-CL de etiquetas (batches `7cea1f8`/`e462037`) |
| F10 | Payload del portal omite moneda/posiciones | Resuelto | enriquecimiento §09 del portal (`03ad2eb`) |
| F11 | Propuesta totals-only | Resuelto | propuesta interactiva: posiciones agrupadas, 2D/estudio, comparar revisiones, decisión (`0320828`) |
| F12 | Enlaces compartidos irrevocables | Resuelto | revocación + endpoint (`c47bd62`, F12 comercial) |
| F13 | "Enlace copiado" sin evidencia de entrega | Resuelto | canales de envío reales + tracking de vista (`2fb168f`, `bad5ee3`) |
| F14 | Aceptación solo con dibujo de firma | Resuelto | alternativa de firma tipeada con identidad (batch a11y A1) |
| F15 | Rechazo del cliente invisible internamente | Resuelto | estado declined visible (`c47bd62`) |
| F16 | Enum interno `SHARE` se filtra al payload | Resuelto | `c47bd62` |
| F17 | Comparación de revisiones solo interna | Resuelto | portal permite comparar revisiones (§09-F) |
| F18 | Pagos registrables sobre trato no sellado | Resuelto | `422` sin deal sellado (`c47bd62`) |
| F19 | Sobrecobro posible | Resuelto | guardia de balance (`c47bd62`) |
| F20 | Retorno Flow a ruta muerta | Resuelto | `/pago/retorno` pública + guardia `payer_return_not_configured` (`88bc07c`) |
| F21 | Facturas/notas sin identidad del emisor | Resuelto | bloques de emisor por branding §09-A |
| F22 | DTE-33 sin líneas ni medios de pago | Resuelto | Detalle por posición + FmaPago/TermPagoGlosa (`c47bd62`, #466) |
| F23 | Factura emitible sobre cotización no aprobada | Parcial | `issue_invoice` exige deal sellado (`invoice_no_sealed_deal`); aprobación del cliente no es condición adicional — decisión de negocio pendiente |
| F24 | DTE-61 sin referencia/condiciones | Resuelto | líneas + términos (batch #441) |
| F25 | Sin boleta para venta B2C | Pendiente | boleta electrónica (DTE-39) no implementada; requiere decisión comercial + CAF 39 |
| F26 | Documento fiscal nunca llega al cliente | Parcial | portal expone documentos emitidos (§09-F); canal de envío fiscal por email/descarga no automatizado |
| F27 | Dos identificadores desconectados por orden | Resuelto | códigos unificados OT-/FAC-/GD-/CE- consecutivos |
| F28 | Sin moneda UF | Pendiente | universo de monedas CLP/USD; UF requiere política comercial autorizada |
| F29 | Presentación de precio se detiene en propuesta | Resuelto | workspace de pricing: waterfall, historia, auditoría (#463–#465) |

## B. hostile-review-production-usability.md — 15 hallazgos (piso/operador)

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | "Buscar pieza" no resuelve códigos impresos | Resuelto | `trace_piece` acepta QR `DEKOPEN|…` y códigos `-U<nn>` (`712fc08`) |
| 2 | Tres nombres por pieza | Resuelto | identidad `Pxx-Uxx-Mxx` unificada plan→etiqueta→guía→traza (fase-10) |
| 3 | Plan invalidado sigue alimentando la sierra | Resuelto | `*_file_stale` 422 + SUPERSEDED + export rechaza COMPLETED (`01e9571`) |
| 4 | Órdenes bloqueadas sin razón | Resuelto | BLOCK exige nota server-side; UNBLOCK limpia la nota (`87d9bc4`) |
| 5 | Tema oscuro blanco-sobre-crema | Resuelto | batch de contraste (`74e0b56`) |
| 6 | "Iniciar" habilitado en paso no-vigente | Resuelto | solo el paso accionable muestra START (`ec74d72`) |
| 7 | Barras retazo sin identidad física | Resuelto | REM-<id>+rack en filas del plan (`ec74d72`) |
| 8 | Ops de mecanizado sin miembro | Resuelto | códigos bay/leaf en ops (`712fc08`) |
| 9 | GLAZE no distingue el vidrio | Resuelto | checklist de piezas selladas en estaciones (`87d9bc4` B4) |
| 10 | Recepción totalmente dañada no registrable | Resuelto | incidencia `damaged≠fulfilled` (`bf4641f`) |
| 11 | Compras oculta fallos de carga | Resuelto | empty-state no renderiza bajo error (`9baf827`) |
| 12 | Piezas pequeñas sin etiqueta | Resuelto | leyenda de piezas bajo diagramas (`ec74d72`) |
| 13 | Etiquetas de embalaje letras V/H ambiguas | Resuelto | glifos PER/REF/VID/PAN/HER (`ec74d72`) |
| 14 | Provenance del remake invisible | Resuelto | "Reposición de / Reemplazada por" (`ec74d72`; fase-10) |
| 15 | Caídas de barra no registrables | Resuelto | endpoint de retazo BAR (`ec74d72`) |

## C. ai-hostile-review.md — 17 hallazgos (runtime del asistente)

| # | Hallazgo | Estado | Evidencia / razón |
|---|----------|--------|-------------------|
| 1 | Fuga cross-org: contexto de otra org en hilo persistente | Resuelto | conversaciones org-scoped durables; aislamiento verificado fase-12 |
| 2 | Cancel mid-run nunca alcanza el loop | Resuelto | `ai_job_cancel_signals`; cancel verificado fase-12 |
| 3 | Follow-up a job en vuelo se queda QUEUED | Resuelto | cola de instrucciones mid-run (`95be457`) |
| 4 | Reintento reproduce el goal original | Resuelto | FAILED_RETRYABLE persiste fuera de la tx + claim atómico al resume (#107 r5) |
| 5 | Historial provisto por cliente envenena grounding | Resuelto | historial tratado como contenido de prompt; claims anclados a contexto/herramientas |
| 6 | Entidades citadas sin anclaje numérico | Parcial | grounding tipado por proyecciones; números validados contra prompt (#88 r2). Cobertura total de claims no demostrable |
| 7 | WAITING_FOR_APPROVAL desaparece al refrescar | Resuelto | estado dedicado + ledger de aprobaciones (`80a444a`) |
| 8 | Ops obsoletas aplicables tras reload | Resuelto | alternativas se marcan stale al cambiar producto (#98 r2) |
| 9 | Follow-ups concurrentes ejecutan act() en paralelo | Resuelto | cola serializa seguimientos (`95be457`) |
| 10 | Modelo ciego a propuestas previas del turno | Resuelto | transcript + artifacts visibles al follow-up |
| 11 | Deep-link review-position muerto | Resuelto | deep links reparados fases 10–12 |
| 12 | `/clients/:id` enlaza a dashboard | Resuelto | mapa de superficies corregido |
| 13 | list_turns devuelve los primeros 50 | Resuelto | restauración de turnos reparada + cursor reciente (`544b1be`) |
| 14 | Deep-link de artifact deriva tras reaplicar | Resuelto | un desenlace terminal por paso (`544b1be`) |
| 15 | Continuidad del dock por coincidencia parcial | Resuelto | dedupe por (surface, refs) (#107 r6) |
| 16 | `_record_turn` traga errores de persistencia | Resuelto | `544b1be` |
| 17 | Respuestas descartadas igual cobran créditos | Pendiente | política de débito en fallo de persistencia sin cambio; requiere decisión de facturación |

## D. cnc-programmer-review.md — 16 hallazgos

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | SAW_CUT ordenado alfabéticamente | Resuelto | orden numérico por índice de barra/rank/u (`d85b90b`) |
| 2 | Head trim pierde ángulo izquierdo de la pieza | Resuelto | ángulos de cara reales head/tail (`d85b90b`) |
| 3 | Fronteras compartidas contradictorias | Resuelto | flag `boundary_conflict` conservando la op (`d85b90b`) |
| 4 | Doc de ops no auto-contenido (MEMBER_PLAN) | Resuelto | geometría de miembros en ops_document (`d85b90b`) |
| 5 | Sin cara/datum/flip | Resuelto | u_mm + reference + face; datum Ext.A/B dibujado (fase-11) |
| 6 | Modelo de ángulo no expresa inglete real | Resuelto | autoridad de ángulos por cara (fase-11) |
| 7 | END_MACHINING profundidad fabricada | Resuelto | `depth_undeclared` BLOCK exacto (fase-11 `24d0f1c` via guardias) |
| 8 | HANDLE_PREP solo un punto | Resuelto | renombrado "Ref. montaje", datum dibujado (fase-11) |
| 9 | tool_id/MachineProfile decorativos | Resuelto | capabilities/tools/compatible_kinds + envelope (`af89574`) |
| 10 | operation_id sensible a representación | Resuelto | ids content-hashed decimales (`d85b90b`) |
| 11 | piece_id mezcla spec con pieza física | Resuelto | identidad física Pxx-Uxx-Mxx |
| 12 | Cortes fantasma/contradictorios en bordes de barra | Resuelto | tail sliver como issue documental (`d85b90b`) |
| 13 | Coverage puede fabricar respuestas | Resuelto | coverage counts + issues explícitos (`d85b90b`) |
| 14 | Detalle de op más pobre que el CSV | Resuelto | estación por fila + etiquetas de miembro (`01e9571`) |
| 15 | Sin semántica de proceso / orden alfabético | Resuelto | sequence_no explícito en orden de plan |
| 16 | Código muerto / docstrings desalineados | Resuelto | limpieza en `d85b90b` |

## E. cnc-manager-review.md — 13 hallazgos

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | Ops enrutadas a estación inexistente | Resuelto | station_map + validación de asignación |
| 2 | MACHINING arrancable/completable sin plan | Resuelto | plan gate en START + ops_done en COMPLETE (`01e9571`) |
| 3 | Programas sin identidad de generación | Resuelto | fingerprint + nombres de archivo + manifest (fase-11) |
| 4 | Programa de sierra irreconciliable con pieza etiquetada | Resuelto | piece codes en CSV/etiquetas |
| 5 | Escaneo inunda todas las órdenes | Resuelto | QR parse acotado por orden (`712fc08`) |
| 6 | Doc de ops no nombra estación | Resuelto | columna estación + station_map (`01e9571`) |
| 7 | Dos fuentes para "hay mecanizado" | Resuelto | autoridad única `resolved_via` |
| 8 | Sin vista por estación | Resuelto | `station_queue()` + GET + UI (`01e9571`) |
| 9 | El cortador puede aprobar su propio QC | Resuelto | `qc_requires_supervisor` 422 (`01e9571`) |
| 10 | Remake hereda asignaciones muertas | Resuelto | re-resolución de routing en remake (fase-10 RM-01) |
| 11 | Fetch de archivo stale falla mal | Resuelto | `*_file_stale` 422 (`01e9571`) |
| 12 | Export en orden COMPLETED | Resuelto | rechazo explícito (`01e9571`) |
| 13 | Export de plan invalidado muere en backend | Resuelto | UI oculta Generar en BLOCK + 422 (fase-11) |

## F. cnc-operator-review.md — 8 hallazgos

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | OPERATOR no puede abrir producción | Resuelto | rol OPERATOR creado (`87d9bc4` M7, `2505edf`) |
| 2 | Sin ejecución por operación | Resuelto | `ops_done` obligatorio al completar paso (`01e9571`) |
| 3 | Verificación = tabla de coordenadas | Resuelto | tiras de miembro dibujadas con marcas numeradas (`712fc08`) |
| 4 | Escaneo en callejón sin salida | Resuelto | deep-link a paso de estación (`712fc08`; fase-10) |
| 5 | Ops no agrupadas por pieza | Resuelto | vista de ops por pieza (fase-11) |
| 6 | Miembros idénticos con identidades distintas | Resuelto | códigos de miembro estables |
| 7 | Enums crudos (TOOL_KIND etc.) | Resuelto | mapas es-CL (`e462037`) |
| 8 | Diseño de escritorio, no de celda | Parcial | overflow móvil corregido (`e5abfb7`); targets grandes §11-G; no hay modo de planta dedicado |

## G. report-purchasing-inventory.md — P0-1..4, P1-1..5

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P0-1 | Sección de stock siempre rota | Resuelto | SQL corregido (`9d072a1` B1) + glance reparado (`fde77fd`) |
| P0-2 | Retazos no registrables | Resuelto | §11-B/C inventario + endpoint retazo BAR (`ec74d72`, `f93fa56`) |
| P0-3 | Sin movimientos manuales | Resuelto | ajuste/movimiento con actor y ledger (`f93fa56`) |
| P0-4 | Cancelar mata la recompra | Resuelto | migración `cancelled_at` + release de claims + unique ignorando CANCELLED (`3019d67`, #536) |
| P1-1 | PO de vidrio nunca se genera | Resuelto | DOC-02 PDF emitible (`4e8a6aa`) |
| P1-2 | DOC-08 falla en ambos formatos | Resuelto | `_spec_detail` aplana dicts anidados (#539) |
| P1-3 | Recepción de vidrio mezcla specs | Resuelto | `stock_variant_key` por spec hash (#537, `3019d67`) |
| P1-4 | Contadores nunca se mueven | Resuelto | tiles netos de drafts/open orders (#541) |
| P1-5 | DOC-04 sin acabado ni precios | Resuelto | color en requirements → Acabado (#540, `3019d67`) |

## H. review-purchasing.md — B1-B2, A1-A6, M1-M5

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| B1 | "Todas las órdenes" nunca carga | Resuelto | `9d072a1` B1 |
| B2 | Crear/abrir proyecto roto | Resuelto | `project_versions` vía documentary_backend (`9d072a1` B2) |
| A1 | DOC-04 volcado de hashes | Resuelto | etiquetas de origen selladas en vez de hashes (`9d072a1`) |
| A2 | "Para cuándo" sin dato | Resuelto | `expected_at`/fechas compromiso (`bf4641f`) |
| A3 | Directorio de proveedores = libreta | Resuelto | directorio estructurado + eligibility + expiración (`72bdb2c`, `bf4641f`) |
| A4 | "Enviar" es mentira | Resuelto | `sent_to` hecho inmutable (`9d072a1`) |
| A5 | Tabla de cobertura no responde | Resuelto | workspace compras: necesidad/pedido recomendado/proveedor/cuándo (§11-A) |
| A6 | Órdenes sin precios | Parcial | precios de proveedor no inventables por mandato; cantidad/descuento presentes; precio unitario de compra sigue ausente por falta de fuente autorizada |
| M1 | Inventario sin dimensión física | Resuelto | racks/retazos/stock físico (`f93fa56`) |
| M2 | Auditoría incompleta | Resuelto | ledger con actor/timestamps |
| M3 | ESTIMATOR sin acceso a compras | Resuelto | lectura purchasing para ESTIMATOR (`9d072a1`) |
| M4 | Tarjeta de orden esconde estado | Resuelto | estado visible en tarjetas |
| M5 | Sin cancelación informada | Resuelto | evidencia + recompra (`3019d67`) |

## I. commercial-docs-review.md — C1-C3, H4-H6, M9-M15

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| C1 | Portal sin white-label | Resuelto | portal con branding org (#466) |
| C2 | Aprobación sin notas de alcance | Resuelto | notas/exclusiones en propuesta (§09-C) |
| C3 | Sin contacto del vendedor | Resuelto | línea de contacto en docs (#466) |
| H4 | Factura/NC sin dinero por línea | Resuelto | (#441, #466) |
| H5 | Descuento invisible | Resuelto | visibilidad de descuento (#466) |
| H6 | Leaks de enums | Resuelto | mapas es-CL (#466) |
| M9 | Tarjeta portal vuelca ubicaciones | Resuelto | posiciones agrupadas (§09-D) |
| M10 | Facts aplastan la propuesta | Resuelto | diseño por posición §09-D |
| M11 | Visuales ignoran acabado | Resuelto | thumbs por acabado declarado (`88bc07c`) |
| M12 | Páginas con encabezados huérfanos | Resuelto | reglas orphans/widows + page-break |
| M13 | Comprobante imprime jerga interna | Resuelto | scrub es-CL (#466) |
| M14 | Convenciones money/fecha inconsistentes | Resuelto | `_money`/`_cldate` normalizados |
| M15 | Aprobación portal más débil que firma | Resuelto | mitigado: captura de identidad + tracking + evidencia (M15 queda como diferencia de fuerza probatoria inherente al canal) |

## J. catalog-admin-report.md — P0-1, P1-1..5

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P0-1 | Importación de catálogo muerta | Resuelto | claims JWT por sesión en worker (`a1b08c0`) |
| P1-1 | Badge de procedencia se auto-certifica | Resuelto | triple procedencia + niveles de confianza (§2a, D=253) |
| P1-2 | "undefined · NN mm" | Resuelto | displays null-safe (§2d) |
| P1-3 | Selector de perfil de proceso vacío | Resuelto | refetch tras montaje abortado (`fde77fd`) |
| P1-4 | Stock de compras roto | Resuelto | (= G/P0-1) |
| P1-5 | missing-authority medio-accionable | Resuelto | blockers con deep-link + CTA Resolver (§06-D) |

## K. findings.md — pricing (16)

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | Formación de precio invisible | Resuelto | desglose de costo + waterfall (#463-465) |
| 2 | Segmento/contexto son inputs muertos | Resuelto | validación segment/context (#463) |
| 3 | Aprobación anónima | Resuelto | identidad del requester + approved_by/at |
| 4 | Herrajes imposibles de cotizar EA | Resuelto | unidad EA + pricing de fittings (#192) |
| 5 | Todos los fallos un error genérico | Resuelto | `PRICING_ERROR_DETAILS` con códigos nombrados (`487aa11`) |
| 6 | "Costo unitario" muestra total | Resuelto | `unit_price` por línea (#585-586) |
| 7 | Sin waterfall | Resuelto | waterfall UI (#464) |
| 8 | Margen ambiguo | Resuelto | warning + etiquetas explícitas (#464) |
| 9 | Historial de ops inutilizable | Resuelto | feed de auditoría legible (#465) |
| 10 | Auditoría = tabla admin | Resuelto | feed estructurado |
| 11 | CRUD de costos soldado | Resuelto | autoridades organizadas |
| 12 | FKs en texto libre | Resuelto | selects tipados (#464) |
| 13 | Gating de emisión opaco | Resuelto | checklist de emisión + deep-links de error (#465, #587) |
| 14 | Borrador rápido FIXED siempre | Resuelto | borrador usa diseño real |
| 15 | Sin precio por posición | Resuelto | neto por posición en vanos (#465) |
| 16 | Inconsistencias/pulido | Resuelto | batch de pulido (#465) |

## L. findings.md — purchasing (16)

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | DOC-04 siempre falla | Resuelto | fix + aplanado de spec (`3019d67`, #539) |
| 2 | Faltante ignora pedidos en camino | Resuelto | netting por-comprar (`fde77fd`, #541) |
| 3 | Stock compartido doble-cuenta | Resuelto | shortage por orden (P-10) |
| 4 | Dañado cuenta como entregado | Resuelto | `bf4641f` |
| 5 | "Asignado" sin fila de stock | Resuelto | etiquetas honestas |
| 6 | Sin dimensión temporal | Resuelto | `expected_at`/lead times autoritativos |
| 7 | Cobertura limitada a una versión | Parcial | compras sigue acotado por proyecto; no existe vista cross-proyecto consolidada |
| 8 | Tarjetas de orden sin contenido | Resuelto | contenido + líneas (`bf4641f`) |
| 9 | Órdenes de herraje/panel sin documento | Resuelto | DOC-08 (#539) |
| 10 | Códigos de error tragados | Resuelto | detalle es-CL (`69a8ff8`) |
| 11 | "Enviar" solo cambia estado, sin cancelar | Resuelto | `sent_to` + cancelación con evidencia |
| 12 | Elegibilidad proveedor texto libre, sin expiración | Resuelto | `bf4641f` |
| 13 | Recepción un clic "todo recibido" | Resuelto | parcial/lote/dims/incidencia (fase-08) |
| 14 | sha256 expuesto al usuario | Resuelto | etiquetas en vez de hashes |
| 15 | Cobertura por línea, no agregada | Resuelto | necesidades agregadas |
| 16 | ESTIMATOR sin acceso | Resuelto | (`9d072a1`) |

## M. findings.md — documentos de taller (19)

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | Identidad de pieza M-xx irreconocible | Resuelto | códigos Pxx-Uxx-Mxx extremo a extremo (fases 9-10) |
| 2 | DXF rechazado por parsers estrictos | Resuelto | marcadores AcDb + DXF válido (#467) |
| 3 | Texto de diagrama de barra ~1mm | Resuelto | rework del diagrama (fase-09, `50dfa6e`) |
| 4 | Colisión V-xx vano/vidrio | Resuelto | glifos VID/piece codes (`ec74d72`) |
| 5 | DXF TEXT muro de hash / mojibake | Resuelto | (#467) |
| 6 | Encabezados de sección huérfanos | Resuelto | reglas de page-break |
| 7 | Tarjeta de operario intercala barras | Resuelto | tiras por pieza (`712fc08`) |
| 8 | Identidad web≠impreso | Resuelto | códigos unificados |
| 9 | Marcador de manilla recortado | Resuelto | (fase-09) |
| 10 | Códigos de miembro colisionan | Resuelto | namespace por unidad |
| 11 | Leaks de enums/policy | Resuelto | (`e462037`, `50dfa6e`) |
| 12 | Tabla de ops en coords de plan, no de pieza | Resuelto | u_mm por miembro (`712fc08`) |
| 13 | Vidrio con forma pierde outline | Resuelto | dibujos de contorno (#92 r4/r7) |
| 14 | operations.csv sin correlación | Resuelto | columna piece_label (`01e9571`) |
| 15 | Etiquetas de líder se apilan en piezas chicas | Resuelto | leyendas (`ec74d72`) |
| 16 | Badge de retazo trunca id | Resuelto | REM-ids legibles |
| 17 | Cross-highlight por memberKey | Resuelto | keys estables |
| 18 | Tarjeta de estación sin ruta de impresión | Resuelto | packs imprimibles por OT (fase-10) |
| 19 | Detalles menores de presentación | Resuelto | batches de pulido |

## N. hostile-r2-factory.md — P0-1..4, P1-1..7, P2-1..5

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P0-1 | Shortage como trampa de un sentido | Resuelto | recheck de material + desbloqueo (`9551ff7`) |
| P0-2 | WO liberada sin cancelación | Resuelto | cancelación de orden (`9551ff7`) |
| P0-3 | Búsqueda de pieza del operario 404 | Resuelto | `0296d19` + deep-links de escaneo |
| P0-4 | Dashboard del operario roto | Resuelto | landing por rol |
| P1-1 | "Sin material" marca todas las órdenes | Resuelto | shortage por orden (P-10, `434e9b8`) |
| P1-2 | Operario no optimiza pero sí desbloquea | Resuelto | UNBLOCK supervisor-gated (`9551ff7`) |
| P1-3 | Historial fuga enums | Resuelto | actor labels + eventos traducidos |
| P1-4 | Códigos internos en ops | Resuelto | etiquetas es-CL |
| P1-5 | Header de plan fuga telemetría | Resuelto | |
| P1-6 | Imprimir en blanco | Resuelto | packs con contenido real |
| P1-7 | Home del operario con errores crípticos | Resuelto | estados honestos |
| P2-1..5 | P2 batch (microcopy, densidad, enlaces) | Resuelto | batch P2 `beb1bb5`-era + fase-10 verificación |

## O. hostile-r2-commercial.md — P1×9, P2×6

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| P1 | Dimensiones revierten en silencio | Resuelto | recuperación de borrador + commit explícito (`036db2b`, `468355a`) |
| P1 | Sin límite dimensional superior | Resuelto | validación de rangos (#99 r1 era parcial; bounds en `scaleModuleWidths`) |
| P1 | Cantidad inline revierte en silencio | Resuelto | `PositionQtyInput` parse estricto (#99 r1) |
| P1 | Validaciones en inglés / RUT sin validar | Resuelto | validaciones es-CL + RUT (`b836035`) |
| P1 | UUID en pricing | Resuelto | claves con etiqueta |
| P1 | Leaks test-data/enums en catálogo | Resuelto | |
| P1 | "Enviar al cliente" muerto | Resuelto | canales de envío reales (`2fb168f`) |
| P1 | "Enlace copiado" falso | Resuelto | copy honesto de share (#595) |
| P1 | Dashboard owner sin dinero | Resuelto | cola de atención + estado comercial (§03-A/F) |
| P2 | Warning quote-only viejo | Resuelto | |
| P2 | Editor apretado en 532px | Resuelto | canvas-first §04-A |
| P2 | "Ver producción" fuera de viewport | Resuelto | CTA primario por etapa (§05) |
| P2 | Leaks GLASS-BASE/MOVING-FIXED | Resuelto | mapas es-CL |
| P2 | MFA forzado sin explicación | Parcial | aal2 exigido en acciones sensibles; copy de explicación mejorable |
| P2 | Catálogos 100% sintéticos | Pendiente | contenido real requiere importación de fabricante; ruta documentada |

## P. gauntlet_workflow.md — hallazgos rankeados

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | Portal público 409 en GET+decide | Resuelto | grant a `portal_backend` + pgTAP (`e152404`) |
| 2 | Sin aprobación interna | Resuelto | "Marcar aprobada" interna (G-WF) |
| 3 | Submit síncrono 40-90s a ciegas | Resuelto | job card en vivo + submit asíncrono |
| 4 | Tipeo en vuelo corrompe el prompt | Resuelto | textarea aislada del job en curso |
| 5 | Blockers del ladder inaccionables | Resuelto | deep-links a resolver + work-center UI (§11-I) |
| 6 | Catch-22 WO con mensaje erróneo | Resuelto | `work_order_replan_step_in_progress` nombrado + Bloquear/Desbloquear documentado |
| 7 | Share-link revoca el anterior sin aviso | Resuelto | warning + visibilidad de enlaces activos (G-WF) |
| 8 | Emisión = form-soup en sidebar | Resuelto | formulario dedicado fuera del sidebar (G-WF) |
| 9 | Commit de pricing bajo el fold | Resuelto | CTA dedupe + pricing apply visible (G-WF) |
| 10 | Lock post-pricing obliga duplicar proyecto | Resuelto | revisión nueva desde posición (compare pipeline §03-E) |
| 11 | Enums de error crudos al usuario | Resuelto | lenguaje de error es-CL (G-WF microcopy) |
| 12 | "Reintentable" sin botón de reintento | Resuelto | retry real |
| 13 | Colisión "Trabajos" jobs vs AI jobs | Resuelto | renombrado |
| 14 | "8 faltantes" vs filtro Faltantes vacío | Resuelto | conceptos de shortage unificados (P-10) |
| 15 | Compare solo agregados | Resuelto | diff por vano (§03-E) |
| LOW | CTAs duplicados, microcopy, etc. | Resuelto | batch G-WF + microcopy pass |

## Q. gauntlet_perf_a11y_cleanup.md — perf P1..P11, a11y A1..A6

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P1 | `list_projects` N+1 sin paginar | Resuelto | hooks compartidos + colapso de GETs (`74e0b56`); paginación de lista vía cursor |
| P2 | `frontLayout` recompute por pointermove | Resuelto | memoización compartida del layout |
| P3 | N+1 por SKU en prep documental | Resuelto | batching de autoridades por SKU |
| P4 | `GET /jobs` SELECT * | Resuelto | proyección de columnas |
| P5 | Endpoints sin límite/cursor | Resuelto | cursores keyset en listados principales (#107 r9 list_jobs) |
| P6 | `PositionThumb` re-layaout por render | Resuelto | memoizado |
| P7 | Paginación serial de JobsPage | Resuelto | cursor keyset |
| P8 | `CADViewportSvg` recompute por render | Resuelto | useMemo |
| P9 | MutationObserver por StudioImage | Resuelto | observer compartido |
| P10 | Bundle inicial con es-CL eager | Parcial | aceptable ~90kB gzip; split diferido |
| P11 | telemetry-vendor dormido | Resuelto | comentario/muerto documentado |
| A1 | BowPlanSvg sin nombre accesible | Resuelto | aria-label + roles (batch a11y #438) |
| A2 | aria-label hardcoded en español | Resuelto | vía `t()` |
| A3 | Contraste disabled ~2.2:1 | Resuelto | bump ≥3:1 en tokens |
| A4 | ConfirmDialog input sin label | Resuelto | label obligatorio |
| A5 | reduced-motion solo en inspector.css | Resuelto | guard global |
| A6 | /jobs inalcanzable | Resuelto | nav affordance añadida |

## R. gauntlet_ai_security.md — HIGH-1, MEDIUM-1..3, LOW-1..7

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| HIGH-1 | Bypass por claim-text | Resuelto | numerics grounded + ops rechazadas si el número no está en el prompt (#88 r2) |
| MEDIUM-1..3 | Grants/proyección/superficies | Resuelto | RBAC revoke + proyecciones role-safe (tarea B=251) |
| LOW-1..7 | Storage/upload/limits menores | Resuelto | sanitizer de storage key + caps SVG/DXF (#107 r6/r8) |

## S. dekopen-ai-hostile-review.md — 15 hallazgos

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1-15 | Superficie/orb/workspace (WAITING_FOR_APPROVAL evanescente, binding del dock por subset, links de artifact, follow-ups, cancelación, historial) | Resuelto | overhaul AI (tareas 468-477, 515-520) + `544b1be` + `80a444a`; verificado fase-12 gauntlet |

## T. review-report ×4 (render/editor/configurator)

| Fuente | Hallazgos | Estado | Evidencia |
|--------|-----------|--------|-----------|
| render B1-B3, M1-M7 | Cara/material/jamb | Resuelto | pases de fidelidad (tareas 481-490, 526-535) |
| editor B1-B4, M1-M6 | Configurator UX | Resuelto | canvas-first §04 + rescue slices |
| configurator B1-B3, M1-M9 | Idem | Resuelto | idem |

## U. review-catalog.md — CAT-01..CAT-07+

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| CAT-01 | Triple de procedencia escribible por member | Resuelto | grants ajustados + §2a (pgTAP 173) |
| CAT-02 | Re-apertura de review solo en servicio | Resuelto | invariante replicada a trigger/DB |
| CAT-03 | QUOTE_READY diverge de freeze | Resuelto | readiness consulta mismos sets que freeze |
| CAT-04 | Autoridad de proceso al release | Resuelto | ManufacturingProcessProfile explícito (#105 r1/r2) |
| CAT-05 | Geometría de sección sin validar | Resuelto | rechazo de polígonos degenerados (#97 r1) |
| CAT-06 | Tracking de revisión de sección | Resuelto | compare normalizado |
| CAT-07 | Endpoint de review sin If-Match | Resuelto | review con diff/versión |

## V. review-documents.md — DOC-001..DOC-032

Resueltos por batches de documentos (`50dfa6e`, `a3785f7`, #466, #467, fase-07/09).
Pendientes declarados: **DOC-011** IT1 >40 chars en TED (pendiente de capar según spec SII), **DOC-021** campos del emisor CAF sin cross-validar, **DOC-024** RUT de 7-8 dígitos excluye RUTs bajos legítimos, **DOC-026** NC parcial → **Resuelto** (`a3785f7` NC parcial + DTE-61 rechaza parciales), **DOC-025** guía sin anulación → **Resuelto** (`d937e2d` ciclo de vida de anulación), **DOC-031/032** fallbacks/formatos → Resueltos en scrub es-CL. Resto de medios/bajos corregidos en las mismas batches; los tres pendientes quedan con razón explícita arriba.

## W. review-assembly.md — B1-B4, H1-H6, M1-M5

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| B1 | Confirmación de entrega falla | Resuelto | grant `portal_backend`/documentary + fase-10 verificó confirm/dispatch |
| B2 | Etiquetas de unidad ambiguas | Resuelto | códigos U-nn + QR |
| B3 | Tarjetas sin contexto | Resuelto | contexto de orden/estación (fase-10) |
| B4 | Tarjetas vacías en estaciones no-consumidoras | Resuelto | checklist sellado (`87d9bc4` B4) |
| H1 | GLAZE sin vidrio identificable | Resuelto | spec por pieza |
| H2 | Códigos internos | Resuelto | |
| H3 | Piezas idénticas indistinguibles | Resuelto | unit_index + location codes |
| H4 | Sin actor en eventos | Resuelto | actor_label via JWT (`87d9bc4`) |
| H5 | QC no ancla ítem | Resuelto | QC por ítem + rechazo→remake (fase-10) |
| H6 | Plan stale invisible | Resuelto | SUPERSEDED + stale guards |
| M1-M5 | Menores taller | Resuelto | batches `87d9bc4`/`ec74d72` |

## X. factory-report.md / dekopen-review.md — P0/P1/P2 taller

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P0-1 | Migración/consistencia | Resuelto | `2505edf` + batches de piso |
| P0-2 | Stock roto | Resuelto | (= G/P0-1) |
| P1-1..5 | Roles piso / shortage / material en GLAZE / navegación | Resuelto | `2505edf`, `9551ff7`, `87d9bc4` — fase-10 revalidó 4 roles en vivo |
| P2 | Pulido | Resuelto | batches menores |

## Y. framedex-physical-review.md — critical/high/medium/low

| Hallazgo | Estado | Evidencia |
|----------|--------|-----------|
| Face swap en render | Resuelto | (#490) |
| Sliding travel/pull invertido | Resuelto | (#527-528) |
| Umbral de puerta | Resuelto | (#490) |
| Herraje por posición/apertura | Resuelto | (#481-484) |
| Materials/PBR colapsan a negro | Resuelto | env map/stage (`ffc47f5` fase-03 defecto documentado → corregido) |
| Tirador corredera inalcanzable | Resuelto | kit tirador sembrado (`b8bc600`) |
| Demás highs/mediums (bisagras, juntas, vidrio, mano) | Resuelto | pases físicos (tareas 481-490) |

## Z. dekopen_rendering_report.md — P1-1..4, P2-1..8

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P1-1 | Flechas de corredera con dirección real | Resuelto | (#527) |
| P1-2 | Pose Abrir corredera cruza jamb | Resuelto | (#528) |
| P1-3 | SPLIT_H flip vertical en 3D | Resuelto | (#526) |
| P1-4 | Error de emisión sin nombre de posición | Resuelto | (#529) |
| P2-1..8 | Bisagras de puerta en PDF, botones de cara técnica, reset de pose, manilla comercial, colisión statusbar, etc. | Resuelto | (#535) |

## AA. designer-report.md — P0-1/2, P1-1..7, P2

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P0-1 | Recarga pierde diseño en curso | Resuelto | borrador sessionStorage con banner Recuperar/Descartar (`036db2b`, `468355a`) |
| P0-2 | Hit targets de cotas | Resuelto | click-to-edit dims §04 |
| P1-1..7 | Footer conjunto, propagación de split, grips, header reflow, overlay planta, etc. | Resuelto | slices de rescue + §04 |
| P2 | Menores | Resuelto | |

## AB. REPORTs de fase (03–13)

| Fase | Hallazgo | Estado | Evidencia |
|------|----------|--------|-----------|
| 03 | Metales/steel casi negros sin env map | Resuelto | `ffc47f5` env/stage |
| 03 | Tirador corredera no ejercitable | Resuelto | kit sembrado `b8bc600` |
| 03 | Detalle de bisagra sutil | Resuelto | polish de contraste |
| 08 | J7 recepción móvil sin scroll (1089px) | Resuelto | overflow wrap (fase-09/10) |
| 10 | Overflow móvil piso (~867px) | Resuelto | `e5abfb7` 963→500/390 medido |
| 10 | Rechazo QC por operario silencioso | Resuelto | toast fijo |
| 10 | Banner "tiene refabricación" en orden original | Parcial | solo station-board + log enlazan; banner explícito no agregado |
| 11 | 6 defectos de la auditoría | Resuelto | REPORT fase-11 |
| 12 | F12-1 turnos en blanco al restaurar | Resuelto | `544b1be` |
| 12 | F12-2 Descartar registra declined tras applied | Resuelto | `544b1be` |
| 12 | F12-3 fingerprint no cubre splits internos | Resuelto | `544b1be` |
| 12 | F12-4 obediencia a inyección con provider real | Pendiente | MiMo 429 en fase-12; verificado estático (UNTRUSTED_DATA_RULE en todos los prompts) — revalidación en vivo pendiente de cuota de provider |
| 12 | F12-5 regla anti-inyección duplicada | No reproducido | falso positivo (regla aplicada una sola vez) |
| 13 | F13-1 magic link otro origen pierde returnTo | Resuelto | HomeRedirect consume stash (defensa en profundidad); causa raíz = allow-list gotrue documentada |
| 13 | F13-2 inputs de dimensión no commit en blur | Nota | limitación del driver de tests; otras vías commitan bien |
| 13 | F13-3 fixtures de video quedan | Nota | datos demo inocuos |
| 14 | pgTAP 070/123/133/136 rotos tras `20261228000005` | Resuelto | contrato actualizado (cancel-con-arribos legal con evidencia; FULFILLED terminal) — `81ee3e1`/`da24332` |

## AD. report.md — Whole-Product UX Audit (@f32de9f)

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| F-03 | Stepper de ciclo de vida miente sobre el estado | Resuelto | (#530) |
| F-04 | "Nuevo vano" invita trabajo condenado en proyecto congelado | Resuelto | oculto/gateado en no-DRAFT (#531) |
| F-09 | "Links de pago" muestra error y empty a la vez | Resuelto | (#532) |
| F-10 | Tabla de órdenes renderiza claves, no valores | Resuelto | (#533) |
| P2 | Toast dedupe, inspector wrap, bare-route redirects, emit-rename, deep-link de orden | Resuelto | (#534) |

## AE. report.md — Performance + Accessibility audit (@3019d67)

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P0-1 | DB fresca no migra (`supabase start`/`db reset` falla) | Resuelto | orden de migraciones corregido; stacks limpios arrancan (verificado cada fase posterior) |
| P1-1 | Drift de config de proveedor AI silencioso | Resuelto | fallos distinguen `ai_provider_quota`/`_auth`/`_rejected` con copy operador (providers.py:352-369) |
| P1-2 | Project detail dispara el mismo payload 5-6× | Resuelto | hook `useProject` compartido colapsa a una lectura (`74e0b56`) |
| P1-3 | Sin `<title>` por ruta | Resuelto | títulos por ruta desde crumbs (`74e0b56`) |
| P1-4 | Paleta de comandos sin focus trap | Resuelto | focus trap real (`74e0b56`) |
| P1-5 | Contraste falla en chips de estado/assistant | Resuelto | batch de contraste (`74e0b56`) |
| P2-1 | Primer 3D abre en ~2.4s | Parcial | progress indeterminado durante lazy chunk (`74e0b56`); tiempo de carga inherente al bundle 3D |
| P2-2 | Warnings de keys duplicadas | Resuelto | |
| P2-3..5 | Editor axe, hit targets <24px, semántica | Resuelto | batch a11y (`74e0b56` + #438) |

## AF. report.md — DEKOPEN AI whole-product review (mock provider)

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| P0-1 | Jobs `purchase_plan`/`quotation_complete` fallan en worker (RLS role leak) | Resuelto | `worker_claims` con claims por sesión + `tx_aborted` (`a1b08c0`) |
| P0-2 | Orden de migraciones rompe `supabase start` | Resuelto | (= AE/P0-1) |
| P1-1 | Orb/dock desaparece con cualquier job "pressing" | Resuelto | dock con continuidad durable + entrada desacoplada (#476) |
| P1-2 | Flujo ops→apply→Guardar no verificable en mock | Resuelto | mock emite ops/batch_ops (`a1b08c0`); verificado fase-12 |
| P1-3 | Copy de fallo engañoso | Resuelto | mensajes por código (`ai_provider_*` + guardias) |
| P1-4 | Misconfiguración de proveedor silenciosa | Resuelto | status/modelo registrados en fallo + códigos distintos |

## AG. report.md — Document specialist (e9caf4eb)

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | DOC-01 500 en proyectos con puerta | Resuelto | crash `_pt()` string×Decimal (`a3785f7`) |
| 2 | DOC-08 sin formato posible | Resuelto | flatten de spec dicts + renderers (`a3785f7`, #539) |
| 3 | Etiquetas de barra se cortan/colisionan | Resuelto | `_bar_svg` pads/clamps/2-lane (`50dfa6e`) |
| 4 | Guía sin dirección de entrega / RUT vacío | Resuelto | resolución desde client registry + delivery (`a3785f7`) |
| 5 | DOC-07 sin margen | Resuelto | columnas sell/margin (`a3785f7`) |
| 6 | DOC-06 sin identidad de orden/unidad | Resuelto | columna de identidad + línea de OT (`a3785f7`) |
| 7 | NC ignora el monto pedido | Resuelto | NC parcial `credit_amount_gross`/`credit_partial` (`a3785f7`) |
| 8 | Docs de taller sin ubicación/tipología/OT | Resuelto | h2 con location+typology, códigos `Pnn-Umm` (#467, `a3785f7`) |
| 9 | POs a proveedor filtran claves internas | Resuelto | XLSX L01 + sin identidad interna (`50dfa6e`) |
| 10 | DOC-02 PDF → 409 engañoso | Resuelto | constraint check2 ampliado (`3019d67`) |
| 11 | Pares de códigos de pieza ambiguos en segmento | Resuelto | `_join_codes` + códigos por pieza (`ec74d72`) |

## AC. dekopen_workflow_audit.md

Mapa de paridad con incumbentes (benchmark, no hallazgos) — brechas absorbidas por las
fases 03–13 o diferidas al backlog declarado.

## AH. fase 14 — gauntlet de cierre en vivo (hallazgos nuevos)

| ID | Hallazgo | Estado | Evidencia |
|----|----------|--------|-----------|
| F14-1 | Magic link que cae en `/` por mismatch de origen pierde el destino protegido | Resuelto | causa raíz: `additional_redirect_urls` de gotrue solo listaba `127.0.0.1`; ahora incluye `localhost` (config.toml) + `HomeRedirect` consume el stash (`144b22c`) |
| F14-2 | `/purchasing` móvil overflow (scrollWidth 693 @iw500) | Resuelto | wrappers `overflow-x:auto` + min-width en tablas de cobertura/stock/tipo/recepciones (purchasing.css) |
| F14-3 | `/assistant` móvil overflow (scrollWidth 565) | Resuelto | composer con `flex-wrap` + `min-width:0` en selects/textarea (assistant.css) |
| F14-4 | Job cancelado se muestra "Fallido / El proveedor externo no respondió" | Resuelto | `ai_job_canceled`/`ai_job_unclaimable` → copy "Trabajo cancelado"; header solo muestra error_code en estados FAILED* |
| F14-5 | Pago online `flow_not_configured` | Pendiente-externo | requiere credenciales Flow en Ajustes; registro manual de pagos funciona |
| F14-6 | Scroll con 100 posiciones no medido | Parcial | fixture de 100 posiciones perdida en wipe; medición previa fase-5 |
| F14-7 | Provider AI real (MiMo) no verificable — 429 quota | Pendiente-externo | gauntlet estructural bajo MOCK; defensa anti-inyección verificada estáticamente |
| F14-8 | OTP `otp_disabled` para scripts de test | Nota de entorno | password grant es el flujo de fixture; magic link UI sigue operativo |

## Resumen de pendientes reales

| Ref | Qué falta | Por qué / bloqueo |
|-----|-----------|-------------------|
| F23 | Factura condicionada a aprobación del cliente | decisión comercial pendiente |
| F25 | Boleta electrónica B2C | requiere CAF DTE-39 + política SII |
| F26 | Envío fiscal al cliente automatizado | canal de entrega por email/descarga sin automatizar |
| F28 | Moneda UF | política comercial no autorizada |
| C-17 | Cobro de créditos en respuestas descartadas | decisión de facturación |
| F-8 | Modo de planta dedicado | mejoras móviles hechas; celda dedicada no implementada |
| A6-H | Precio unitario de proveedor | no existe fuente autorizada de precios de compra |
| L-7 | Vista de compras cross-proyecto | alcance por proyecto vigente |
| O-P2 | Catálogos sintéticos / MFA forzado sin copy | catálogo real depende de importación de fabricante; copy MFA mejorable |
| 10-banner | Banner explícito de refabricación en orden original | enlaces existen; banner dedicado pendiente |
| F12-4 | Inyección adversarial con provider real | MiMo 429; verificación estática hecha |
| DOC-011/021/024 | SII: capa IT1, campos CAF, RUT bajos | pendiente de ajuste contra spec SII |
