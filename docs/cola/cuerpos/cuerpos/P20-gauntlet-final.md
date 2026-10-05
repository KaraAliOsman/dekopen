# P20 — Aceptación final de punta a punta, pase editorial del producto completo y entrega al dueño

**Depende de:** todos los encargos anteriores mergeados en `integracion/v1`. Va al final, solo. Adjunta: `CONSTITUCION-DISENO.md`.

## Objetivo
Demostrar con evidencia que DEKOPEN está **100 % listo para que el dueño lo revise**: cada flujo funciona de punta a punta con datos realistas, los números son confiables, la presentación es la de la constitución en todas las superficies y no queda nada de demo salvo el catálogo marcado DEMO. Luego, abrir **el único PR hacia `main`** con una guía de revisión que permita al dueño comprobarlo todo por su cuenta.

**Este encargo corrige todo lo que encuentre.** Lo pequeño se corrige en este PR; si una corrección supera ~300 líneas, ábrela como PR propio hacia `integracion/v1` dentro de esta misma sesión, mergéala al pasar CI y vuelve a correr los recorridos afectados. Nada se “reporta para después” si se puede arreglar.

## 1. Recorridos (fixture de P00, usuarios reales por rol, navegador real, 1440 y 390 donde aplique)
1. Cuenta nueva → onboarding → primer proyecto → primera posición → precio → emisión.
2. Proyecto de 12 posiciones (incluye bow y acoplado) → precio con aprobación de margen → emisión REV-A → portal → cambios solicitados → cambio global → REV-B → aprobación → anticipo (Flow en sandbox o simulado, declarado).
3. Revisión nueva con documentos inmutables y comparación REV-A ↔ REV-B.
4. Compra → recepción parcial con dañado → cancelación y recompra → stock y retazos.
5. Liberación → tablero → operario en tablet (corte, mecanizado, …, QC FAIL → remake → QC PASS) → embalaje con etiquetas → despacho.
6. CNC: una máquina compatible (PASS o WARN) y una incompatible (BLOCK con causa); operaciones declaradas no emitidas visibles.
7. IA en el editor: propuesta → vista previa → aplicar → deshacer → auditoría; cancelación y reintento.
8. Roles y aislamiento: OWNER, ESTIMATOR, WORKSHOP_MANAGER, OPERATOR e INSTALLER; dos organizaciones; IDs adivinados → 404 o 403 sin filtrar existencia.
9. Cobranza: calendario → pago manual → enlace de pago (sandbox) → saldo 0.
10. Catálogo: **ingesta por IA** de una ficha PDF y de una planilla → revisión → publicación → readiness igual al gate; importación manual con plantilla.
11. Dominio: una posición de cada tipología (D03, D08) con cada familia de vidrio (D02), bicolor (D05), con extras (D06) y del vano a la fabricación (D07): cortes, BOM, herrajes y precio coherentes en el editor, el PDF, el portal, la OT y el 3D.
12. IA: suite de IA1 con el proveedor real (`AI_GATEWAY_MIMO_*`) ≥ 85 % en los casos E y J, **0** números inventados y **0** acciones consecuentes ejecutadas.
13. Terreno: medición → rectificación → revisión → producción → instalación con firma → incidencia → postventa (P23).
14. Analítica (P24): margen real vs. cotizado de una obra cerrada con la causa de la diferencia.

## 2. Pase editorial del producto completo (constitución §9)
No por pantalla: **por persona**. Recorre un día completo de cada persona del §1.2 (estimador, dueño, jefe de taller, operario, instalador y cliente final) y para cada uno:
- pasa la rúbrica R1–R20 en todas las superficies que usa, en ambos temas;
- verifica la **coherencia entre superficies**: el mismo componente, el mismo término, el mismo formato de número y la misma simbología en el editor, el PDF, el portal, la OT, la etiqueta y el 3D;
- confirma que cada superficie conserva su **momento de firma** (§7) y que su **idea del §8** funciona con el motor;
- elimina todo lo que no justifique su existencia y corrige lo que falle.

## 3. Verificaciones globales
- `ux:capture` completo (todas las rutas, roles, anchos y temas): **0 hallazgos** críticos y de slop; lista explícita de los menores que quedan, con justificación de cada uno.
- axe en todas las rutas: 0 *serious* y *critical*.
- Guardas de P01: línea base reducida respecto del inicio del programa (reporta el delta por guarda).
- Rendimiento: abrir una posición, recalcular un precio, abrir una OT de 100 posiciones y cargar el portal en móvil (4G simulada). Reporta p50/p95 y corrige lo que supere 1 s (interacción) o 3 s (carga del portal).
- Búsqueda de residuos de demo: ninguna aparición visible de “MOCK”, “Devin”, “Test Org”, “lorem”, “Próximamente”, “TODO” ni rutas DEV en el build de producción (test automatizado).
- `docs/redesign/phase14-findings-registry.md`: cada hallazgo marcado como resuelto (con evidencia), vigente o descartado (con motivo).
- `docs/decisions/valores-por-defecto.md` y `docs/operations/ACTIVACION.md` completos y coherentes con lo construido.

## 4. Entrega al dueño
1. **`docs/GUIA-REVISION.md`** (en español, para el dueño, no técnico): cómo levantar el producto localmente o en una preview, con qué usuario entrar en cada rol, y un **recorrido guiado de 30 minutos** por cada flujo con qué mirar y qué debería pasar; la lista de decisiones por defecto que puede cambiar en Ajustes; y la lista de integraciones a conectar (Railway, Flow, SII, correo) con el enlace a `ACTIVACION.md`.
2. **Informe** `docs/redesign/acceptance-<aaaa-mm-dd>.md`: tabla de recorridos (PASA / PASA con observaciones / FALLA), evidencia (capturas y artefactos), rúbrica por superficie, correcciones hechas en esta fase, problemas abiertos priorizados (solo los que de verdad no se pudieron resolver, con causa) y lo que depende del dueño.
3. Actualiza `docs/wiki/state/current-reality.md` con el mapa de capacidades verificado en tu SHA.
4. **Abre el PR `integracion/v1` → `main`** con el resumen del programa completo (encargos incluidos, PRs mergeados, capturas clave de cada superficie, guía de revisión y riesgos). **No lo mergees**: ese clic es del dueño.

## Criterios de aceptación
- Los 14 recorridos en PASA (los que dependen de una integración diferida, en PASA con el sandbox declarado).
- Rúbrica R1–R20 en PASA en todas las superficies, con la tabla en el informe.
- `ux:capture` y axe en 0 críticos; test anti-residuos de demo en verde.
- `GUIA-REVISION.md` probada siguiendo sus propios pasos desde un stack limpio.
- PR hacia `main` abierto, con los 4 checks en verde.
