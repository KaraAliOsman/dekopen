# Valores por defecto del programa DEKOPEN v1

Fuente inicial: `docs/design/CONSTITUCION.md`, seccion 11. Los encargos siguientes deben mantener esta tabla cuando implementen o cambien un valor configurable.

| Decision                   | Valor por defecto                                                                                               | Donde se cambia                   | Estado      | Encargo que la implementa |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------- | ----------- | ------------------------- |
| Papel de los documentos    | Carta                                                                                                           | Ajustes > Documentos              | por defecto | P09                       |
| Anticipo                   | 50 % al aprobar, saldo contra entrega                                                                           | Ajustes > Condiciones comerciales | por defecto | P08                       |
| Validez de la cotizacion   | 15 dias corridos                                                                                                | Ajustes > Condiciones comerciales | por defecto | P08                       |
| Garantia                   | Texto plantilla editable, sin plazo inventado: "[completar plazo]" visible solo en Ajustes, nunca impreso vacio | Ajustes > Condiciones comerciales | por defecto | P08                       |
| Plazo de entrega           | Calculado desde la carga de produccion si existe; si no, campo obligatorio por cotizacion                       | Cotizacion                        | por defecto | P08                       |
| Banda de margen            | Objetivo 35 %, minimo 25 %; bajo el minimo requiere aprobacion del dueno                                        | Ajustes > Precios                 | por defecto | P07                       |
| IVA                        | 19 %, precios netos en la app y total con IVA en el documento                                                   | Ajustes > Impuestos               | por defecto | P07                       |
| Pie "Generado con DEKOPEN" | Oculto en documentos del cliente (white-label); visible solo en el portal, discreto                             | Ajustes > Documentos              | por defecto | P09                       |
| Nombre del asistente       | "Asistente DEKOPEN" con el Orb. No se usa "STARWIN"                                                             | Ajustes > Marca                   | por defecto | P17                       |
| Marca de la app            | Direccion B del estudio de identidad (`DEKOPEN` con la O como seccion de perfil)                                | P25                               | por defecto | P25                       |
| Moneda                     | CLP; USD y UF opcionales                                                                                        | Ajustes > Moneda                  | por defecto | P07                       |
| Catalogo                   | Demo con precios aleatorios de semilla fija, marcado DEMO en todas partes                                       | Catalogo > Importar               | por defecto | D01/P16                   |
| Familia de sistema         | CASEMENT / SLIDING / LIFT_SLIDE / DOOR / FACADE_FIXED; la tipologia habilitada depende de la familia y el motor rechaza combinaciones incompatibles | Catalogo > Sistemas               | implementado | D01                       |
| Limites dimensionales      | Por sistema x tipologia con fuente declarada (SEED_SYNTHETIC / MANUAL / IMPORT / LEGACY_UNVERIFIED); sin fila = sin limite verificado | Catalogo > Sistemas               | implementado | D01                       |
| Refuerzo                   | Acero declarado como dato (ix_cm4, tornillos por metro); los tornillos entran a la BOM como fittings (TORNILLO-4X16) | Catalogo > Sistemas > Refuerzos   | implementado | D01                       |
| Ingesta de catalogo        | Dos vias (plantilla XLSX/CSV y candidatos IA) que convergen en la misma revision humana; nada se publica sin confirmar | Catalogo > Importar               | implementado | D01                       |

## Decisiones de implementacion — P01 (sistema de diseno v2)

Registradas al implementar la Constitucion como codigo. No son configurables por el usuario; viven en el codigo y en los tests que las fijan.

| Decision | Valor adoptado | Donde vive | Notas |
| --- | --- | --- | --- |
| `--text-muted` (tema claro) | `#666f74` | `frontend/src/styles/tokens.css` | Sube el muting un escalon para que la unidad al 85 % mantenga AA sobre `--surface-panel`. |
| Signo negativo en `formatMoney` | `-$1.234` (signo antes del simbolo) | `frontend/src/format.ts` | convencion CL: el simbolo queda pegado al numero. |
| Moneda `UF` | `Intl.NumberFormat` no la conoce: se formatea como numero con `UF` de prefijo textual | `frontend/src/format.ts` | USD y CLP usan `Intl` nativo; UF cae en el camino documentado. |
| `<Timestamp>` relativo | `hoy`/`ayer`/`anteayer`; mas de 2 dias fecha corta; `title` siempre fecha+hora completa | `frontend/src/ui/format.tsx` | "auto" nunca reemplaza el dato exacto: el tooltip conserva la precision. |
| Validacion en espanol | hook global `installSpanishValidation` (capture-phase) + `data-pattern` para patrones | `frontend/src/validation.ts`, `main.tsx` | un solo punto de verdad: cualquier `<form novalidate>` nuevo hereda los mensajes es-CL, incluido RUT modulo-11. |
| Particion CSS | cortes contiguos por seccion: `index.css` → `styles/{base,auth,onboarding,shell,dashboard,settings,responsive,jobs,clients,a11y}.css`; `ui.css` → `ui/styles/*` (13 parciales); `canvas.css` → `canvas-{base,editor,views,technical}.css` | `frontend/src/styles/`, `frontend/src/ui/styles/`, `frontend/src/features/canvas/` | cortes = orden de cascada intacto, cero riesgo visual; la reduccion del ~30 % queda para P03+ (hay duplicados chip/status entre index/ui que hoy se componen entre si). |
| Alias `--theme-*` | conservados como alias a los roles canonicos; codigo nuevo usa roles | `frontend/src/styles/tokens.css` | migracion sin ruptura: los alias resuelven, el guard cuenta usos nuevos. |
| Baseline de guards | `scripts/guards-baseline.txt` con conteos por regla; `--write-baseline` regenera | `scripts/check_guards.py` | ratchet: una regla nueva o un conteo que sube falla el lint; bajar siempre es legal. |
| `src/dev/` exento de guards | el banco de pruebas (/dev/ui/mal) viola §9.3 a proposito | `scripts/check_guards.py` | exclusion explicita en `_frontend_sources` y en `check_no_hex_in_frontend`. |

## Decisiones de implementacion — D02 (vidrios de verdad)

| Decision | Valor adoptado | Donde vive | Notas |
| --- | --- | --- | --- |
| Notacion canonica | `4 / 12 aire / 4`, camaras con gas (`12 Ar`), PVB con `+` (`3 + 3 PVB 0,38`), alias legacy `DVH a-b-c` y `a-b-c` | `engine/.../glass_composition.py` (`parse_glass_notation`, `format_glass_notation`) | Ida-vuelta: format(parse(x)) == x para las 30 notaciones reales del test. |
| Autoridad del espesor | la composicion resuelta SIEMPRE gobierna el paquete (`thickness_source="COMPOSITION"`); el declarado que discrepa se conserva como `thickness_declared_mm` y emite `GLASS-THICKNESS-MISMATCH` (WARNING) | `engine/.../geometry.py` | El junquillo se decide por lo que se pide al vidriero, no por una declaracion que puede ir a la deriva. Deriva registrada = aviso de revision, nunca reescritura silenciosa. |
| Regla de antepecho (piso) | NO se siembra regla por distancia al piso: el modelo conoce el desfase del pano a la base de la unidad, no la cota del piso | `engine/.../glass_safety.py` (`sill_below_mm` + evaluador conservados), `supabase/seed.sql` | Regla sub-determinada (la base de la unidad no es el piso): dispararia en todo pano de altura completa. La columna y el evaluador quedan disponibles para reglas que la organizacion escriba con contexto de instalacion real. |
| UNKNOWN honesto | spec no estructurable → composicion nula, peso desconocido, `glass_review_pending=TRUE` en la posicion | `backend/projects/service.py` (`_glass_resolution`) | La marca es registro para revision; no bloquea calculo, congelado ni produccion. |
| Peso del vidrio | laminas a 2,50 kg/m²·mm + intercapa PVB a 1,07 kg/m²·mm; camaras no pesan | `GlassComposition.weight_kg_m2()` | Intercapas distintas de PVB se declaran por tipo; hoy solo PVB tiene densidad registrada. |
| Unidad de recargo | `M2` (por m² facturable), `M` (por metro de borde expuesto), `EA` (por pieza), `CROSS` (por cruce de palillaje) | `glass_product_surcharges.unit`, `glass_price_lines` | `CROSS` = cruces reales (mullions x traves); sin palillaje seleccionado no se cobra. |
| Seguridad NCh 135 | severidad `WARNING` por defecto: avisa, no bloquea. La organizacion puede endurecer una regla a `MANDATORY` (emite ERROR y bloquea) | `glass_safety_rules.severity` | El motor deduplica hallazgos por (regla, vano, hoja). |
| Datos normativos | reglas y limites semilla son `SEED_SYNTHETIC` con `review_pending=TRUE` | `supabase/seed.sql` | Nada de texto normativo inventado: la norma oficial entra por la ingesta D01 (hojas "Seguridad vidrio" / "Limites vidrio"). Ver `docs/operations/ACTIVACION.md`. |
| Area minima facturable | `min_billable_area_m2` por producto; se factura `max(area real, minimo)` | `glass_price_lines` | Sin minimo declarado se factura el area exacta (piezas conformadas usan el area poligonal real). |
| Pedido al vidriero | medidas de corte en mm enteros, etiqueta `P{pos}-U{unidad}-I{secuencia}`, una fila por pieza (terminales incluidas) | `backend/production/glass_order.py`, ruta `orders/<id>/glass-order/?output=pdf|csv` | `?orders=<uuid,...>` fusiona OT del mismo versionado; piezas `review_pending` se listan aparte, nunca mezcladas con las cortables. |
| Moneda de recargos | la fila declara moneda; conversion via autoridad FX de la org; nunca CLP implicito | `backend/pricing/service.py` | El catalogo trae la moneda del proveedor; el repositorio convierte igual que cualquier costo. |
