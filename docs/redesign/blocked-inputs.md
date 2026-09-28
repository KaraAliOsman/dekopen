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
