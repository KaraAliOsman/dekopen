# Entradas bloqueantes — fase 00

Lo que falta para pasar de "base verificable" a "transformación integral",
con el bloqueo concreto (no "podría ser útil"):

## Catálogo con autoridad de fabricación real

**Bloqueo:** la única familia completa del seed es `DEMO_60` — sintética, con
bandera explícita de demostración. No tiene secciones de perfil declaradas con
`provenance`, ni `process_profile` completo, ni autoridad de curvado/paneles.
**Consecuencia:** las posiciones cotizan pero `MANUFACTURING`/`CNC` readiness
muestran bloqueos — correctamente, por diseño.
**Necesario:** datos reales de una familia de fabricante (marco/hoja/jamba/
poste/acero/vidrios/kits/paneles + secciones DXF + reglas de proceso). El
importador de catálogo (`/catalogs/imports`) acepta CSV/PDF/DXF y deja la
revisión humana en la cola — el flujo existe; falta el material de origen.

## Secretos de proveedores externos (no necesarios para esta fase)

- **Flow** (pagos en línea): `FLOW_API_KEY`/`FLOW_SECRET` — sin ellos el botón
  de pago del portal responde `payment_provider_unavailable` (comportamiento
  intencional y visible; documentado, no falla en silencio).
- **SII** (DTE): certificado digital de la empresa + CAF por tipo de DTE.
  Sin ellos, timbraje devuelve `sii_certificate_missing`/`sii_caf_exhausted`.
- **Proveedor IA**: `OPENAI_API_KEY` (o MiMo) — sin clave, los jobs de IA
  quedan disponibles pero el provider responde unavailable de forma visible.
- **MiMo `sk-` key**: pendiente del backlog (llave del servicio, no bloquea).

## Aprobación humana de migraciones nuevas

Cualquier migración escrita en esta cola necesita `supabase db reset` limpio +
pgTAP — el gate ya lo verifica; lo pendiente es revisión humana del diff antes
de mergear (fuera de esta fase por instrucción del mandato).

## Datos de fabricante para golden cases de producción

El pack de cortes exportable usa `DEMO_60` — sus barras, despieces y UPF son
correctos según el engine pero no corresponden a un perfil comercial real.
Para validar contra un corte de taller real se necesita una familia con
geometría declarada (rebayo, junquillo, refuerzo) medida.

## Capturas no verificables sin estado comercial completo

Las capturas de cotización emitida y pack de cortes requieren el camino
posición → pricing → emisión → release → OT → optimizar. El fixture lo deja
todo listo hasta `DRAFT`; emitir exige que el engine valide `VALID` y que
`pricing` aplique — ambos verificables en local con los datos del fixture.

## Inventario de autoridad faltante — fase 04 (catalogo)

Medido sobre el seed actual (`DEMO_60`, `ALU_65`, `GLASS_45`). Todo dato
presente es `SEED_SYNTHETIC` — valido para demostrar, no para fabricar.
Ningun hueco fue rellenado con numeros de demostracion.

| Dato real faltante | Tabla/campo | Estado actual | Fuente esperada |
|---|---|---|---|
| Secciones de perfil (poligono DXF del fabricante) | `profile_articles.section` | 29/33 articulos sin seccion (todos los MULLION/COUPLER/THRESHOLD/GLAZING_BEAD; 2/3 FRAME y SASH) | DXF de planos del fabricante (ej. Aluprof MB-86), revision humana |
| Procedencia documental por parametro | `catalog_parameter_evidence` | Tabla creada, 0 filas — toda autoridad declarada sin fuente registrada | Fichas tecnicas del fabricante con pagina; sellado por import o declaracion manual |
| Prestaciones certificadas (U, acustica, seguridad) | `profile_systems` — sin columnas | No modeladas: los documentos comerciales omiten prestaciones por diseño | Certificados de ensayo (IFT/CSI), pagina del ensayo |
| Foto/imagen por articulo | — sin modelo | No existe ninguna foto ni de demostracion | Fotografia del sistema o render aprobado por el fabricante |
| Datos de proveedor real | `purchase_mappings.manufacturer_name` etc. | Valores sinteticos (proveedor demo) | Tarifario/contrato con proveedor, condiciones comerciales firmadas |
| Lead-times de compra | — sin modelo | Sin autoridad; compras no prometen fechas | Historial de compras real o SLA del proveedor |
| Peso nominal de kit por variante | `hardware_kits.weight_kg` | Poblado con valor demo (2.5 kg) en todos los kits | Catalogo de herrajes (ej. Siegenia Titan AF) con masa declarada |
| Refuerzo por caso (viento/limites) | `reinforcement_cut_policies` | 3 filas demo; sin criterio estructural real | Memoria de calculo del fabricante / estudio de viento |
| Geometria de sellado/juntas | — | Junta visual aproximada | Catalogo de gomas del sistema |
| Herrajes por apertura exotica (plegable, oscilo-paralela) | `hardware_kits` | Sin kits; apertura no seleccionable | Ficha del proveedor de herrajes |

Fuera de catalogo pero del mismo mandato: certificado SII, CAF por tipo de
DTE, credenciales Flow, clave de proveedor IA — detallados arriba; sin ellos
los flujos responden errores nombrados, no silencio.
