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
| Familia de sistema         | CASEMENT / SLIDING / SPECIALIZED; la tipologia habilitada depende de la familia y el motor rechaza combinaciones incompatibles | Catalogo > Sistemas               | implementado | D01                       |
| Limites dimensionales      | Por sistema x tipologia con fuente declarada (SEED_SYNTHETIC / MANUAL / AI_GENERATED); sin fila = sin limite verificado | Catalogo > Sistemas               | implementado | D01                       |
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
