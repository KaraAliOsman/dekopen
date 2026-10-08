# P02 — Identificadores humanos y números legibles de punta a punta

**Depende de:** P00 (detectores) y P01 (formateadores `<Money>`, `<Dims>`, `<Qty>`, `<Percent>`, `<EntityCode>` y `domainLabels`).

## Objetivo
Que cada entidad que una persona necesita nombrar en voz alta, en una pantalla, un PDF o una etiqueta física tenga un **código humano estable**, y que **todo número visible** tenga el formato correcto según su naturaleza. Es lo que hace que un jefe de planta diga “la OC 000123 del retazo RT-000045” y no “la PO-D2CFA2D8FD52”.

## Situación actual (verificada en main `b3d1c9b`)
- `backend/purchasing/service.py:593`: `order_code = f"PO-{order_id.hex[:12].upper()}"`, es decir, las órdenes de compra se identifican con un hash.
- Los proyectos ya usan `P-000123` con una secuencia global (`supabase/migrations/20261213000000_project_code_sequence.sql`). Esa decisión fue deliberada (opacidad) y **se mantiene**.
- Recibos (`RC-0001`), guías (`GD-0001`) y facturas (`FAC-0001`) ya tienen código humano (ver `20261009000000_payment_receipts.sql`, `20261010000000_dispatch_notes.sql` y `20261011000000_project_invoices.sql`). Úsalos como patrón.
- (auditoría) Se vieron: OT `OT-P-2EE71A6B787C-REV-B-01` en builds antiguos (hoy `OT-P-000005-REV-A-03`); cantidades `24.0000`; `aprovechamiento 92.5333%`; vidrio `1310.00×1310.00`; `CLP 3462901.00` sin formato; remanentes con ID truncado; y hashes de proyecto en las tarjetas del inicio.

## Alcance
1. **Códigos por organización** para lo que hoy no tiene código humano. Usa el mismo mecanismo que recibos, guías y facturas: contador por `org_id`, seguro bajo concurrencia, nunca reutilizado e inmutable una vez asignado.
   - `OC-000123` para órdenes de compra. El prefijo “OC” es el usual en Chile; si cambiarlo rompe contratos, mantén “PO-” pero numérico y documenta la decisión.
   - `RT-000045` para retazos.
   - `REC-000012` para recepciones de compra, si no existe ya.
   - La migración rellena las filas existentes de forma determinista por `created_at`, con test en `make test-db`.
2. **Identidad de pieza única** en UI, pack de corte PDF, CSV, DXF, etiquetas y QR. El pack de corte ya usa etiquetas como `P01-U02-M03`: conviértelas en la única forma visible. El QR codifica el ID estable más la etiqueta humana. Agrega un test que genere los artefactos de una OT del fixture y compruebe que el conjunto de etiquetas es idéntico en todos.
3. **Barrido de formato** en backend (`backend/documents/renderers.py` y demás renderers) y frontend (usando los formateadores de P01). Aplica esta tabla y documéntala en `docs/ENGINEERING.md`:

   | Magnitud | Formato |
   |---|---|
   | mm | entero, salvo precisión declarada por la autoridad |
   | m, m² | 2 decimales |
   | kg | 1 decimal |
   | unidades | entero |
   | % | 1 decimal |
   | CLP | sin decimales, `$1.435.471` |
   | USD | `US$ 1.234,56` (o el formato que defina el locale; documéntalo) |
   | ángulos | entero salvo que sea fraccionario (`22,5°`) |

   Nunca se muestra un `Decimal` con ceros de cola (`1200.00`).
4. **Sin UUID ni hash visibles** en superficies de cliente y de taller. Los IDs técnicos van solo en “Detalles técnicos” mediante `<EntityCode>`. La huella de plan y documento queda **solo** en el pie de página, abreviada.

## Fuera de alcance
No cambies la numeración de proyectos ni la de cotizaciones; los folios SII de facturación dependen del CAF de SII y no se tocan. No rediseñes pantallas: solo formato e identificadores.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Todas, en especial el jefe de taller y el estimador, que nombran entidades en voz alta (“la OT 000123”) y las leen en papel y etiquetas.
- **Anatomía:** Constitución §3.3 (números y unidades) y §4 (voz). Los códigos van en Mono con `<EntityCode>`; los IDs técnicos solo en “Detalles técnicos”.
- **Momento de firma (preservar o crear):** F2 (la huella en el cajetín) se alimenta de estos códigos: el código humano y la huella aparecen juntos y siempre en el mismo lugar.
- **Idea que sube el techo (obligatoria, con el motor):** El código es una dirección: escribir `OT-000123` o `RT-000045` en la paleta de comandos lleva directo a la entidad, y escanear su QR en el taller abre la misma vista.
- **Slop a eliminar aquí:** Códigos con hash, prefijos en inglés (PO, WO), formatos distintos para la misma magnitud en pantallas distintas, `.00` sobrantes.
- **Preguntas del pase editorial:** ¿Un operario puede dictar cada código por radio sin deletrear? ¿El mismo número se ve idéntico en la pantalla, el PDF, el CSV y la etiqueta?

## Criterios de aceptación
- Test de concurrencia: dos creaciones simultáneas en la misma organización obtienen códigos consecutivos distintos; organizaciones distintas tienen contadores independientes; un rollback no deja huecos visibles (o, si los deja, está documentado y aceptado).
- Test de render de documentos: el texto extraído (PyMuPDF si está disponible en las dependencias de test; si no, verifica el HTML intermedio) no contiene hex de 10 o más caracteres fuera del pie, ni `.0000`, ni `%` con más de 1 decimal.
- `ux:capture` (P00) en las rutas de compras, inventario, producción, proyectos e inicio: **0** hallazgos de UUID/hex/decimales largos.
- Test de igualdad de etiquetas de pieza entre PDF, CSV, DXF y etiquetas para la OT de 12 posiciones del fixture.
- `make test-db` en verde con la migración y el relleno.
