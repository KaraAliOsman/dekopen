# Fase 09 — Plan de corte y pack de taller: reporte de aceptación

Caso de referencia: OT-P-000008-REV-A-01 (orden viva, 2 unidades P01, 6 barras).
Muestras sintéticas: `aceptacion-casos.pdf` (matriz de casos), `aceptacion-100pos.pdf`
(60 barras / escala de proyecto de 100 posiciones).

## Antes → después

- `cutpack-ANTES.pdf` — pack del HEAD anterior a la fase.
- `cutpack-DESPUES.pdf` / `pack-DESPUES.pdf` — mismo caso tras la fase.

Defectos del PDF05 histórico que seguían presentes y se corrigieron:

- "M-06 · +3" como única referencia → código físico estable `P01-U01-M07` por pieza
  en diagrama y tabla (especificación compartida, identidad física por unidad).
- Gráficos separados de sus tablas → bloque `.bar-block` indivisible: sección,
  convención de lectura, diagrama y tabla viajan juntos; la tabla lleva renglón
  "Tabla de cortes — Barra N · SKU" que se repite si la página la parte.
- Etiquetas solapadas → carriles alternados + líneas guía con control de solape
  (la barra de 12 piezas cortas de `aceptacion-casos.pdf` p3 lo demuestra).
- Operaciones genéricas → función concreta "Perfil · Marco", "Refuerzo · Marco",
  "Perfil · Junquillo", más "lleva mecanizado" en Obs. cuando aplica.
- Sin conservación → línea por barra `stock = piezas + disco + despuntes +
  remanente — cierra exacto`, o "diferencia sin asignar N mm" en rojo (comprobado
  adrede con un desbalance sintético de 45 mm: se señaló, no se ocultó).
- Retazo sin disposición → "Retazo N mm recuperable — etiquetar y devolver a
  stock" / "Cola N mm — desecho, no retorna a stock".
- Vidrio sin solución → tabla "Piezas no ubicadas" con motivo legible
  ("Vidrio con forma — corte por plantilla", "Sin lámina declarada").
- Vidrio a medida → pedido claro "comprado al tamaño final; no se corta en
  taller" (sin nesting ficticio).
- Etiquetas de bulto → tamaño real 100×50 mm ("imprimir al 100%"), código grande,
  QR con zona de silencio — escaneado con decodificador real (zxing-cpp):
  `DEKOPEN|OT-P-000008-REV-A-01|PACK|78d75a50a9b8c271`, sin credenciales.
- Tamaños bajo el piso → piso operativo verificado: cuerpo ≥ 9.5 pt,
  encabezados de tabla 7 pt, etiquetas de firma/pie 7 pt (antes 6/6.5 pt).

## Medición programática (pypdfium2, rectángulos de texto por página)

- `cutpack-DESPUES.pdf` 4 p · `pack-DESPUES.pdf` 15 p · `aceptacion-casos.pdf`
  5 p · `aceptacion-100pos.pdf` 60 p.
- Solapamientos de texto entre bloques: **0** en las 84 páginas.
- Texto fuera del papel: **0** en las 84 páginas.
- Glifo alfanumérico mínimo: 4.17 pt de altura de caja (rótulos ~9 pt); la
  información operativa nunca depende de 6–7 pt.
- Escala de grises (`cutpack-casos-p3-gray.png`): desecho vs retazo se distinguen
  por texto ("retazo"/"desecho") y trama, no solo por color.

## Invariantes cubiertas por pruebas (`backend/tests/test_production.py`)

- Identidad física por unidad: `P02-U01-M01` … `P02-U02-M02·R` — dos unidades
  idénticas no comparten código de pieza física; cada pieza impresa aparece
  exactamente una vez por cantidad.
- Fallback honesto a código de especificación cuando el plan no trae unidad.
- Conservación por barra impresa bajo la convención declarada.
- Reoptimización: versionado/invalidación de plan (huella por página, plan
  SUPERSEDED al reoptimizar — verificado en fases previas sobre el ledger de
  reservas; reservas de stock y retazos se ajustan atómicamente).

## Guía del operario (resumen — el detalle está impreso en cada página)

1. **Encabezado de barra**: número, SKU comercial, material, acabado, largo bruto
   y sello `BARRA NUEVA` o `RETAZO <id>` (con rack si existe).
2. **Convención**: "extremo inicial a la izquierda, alimentación →"; los ángulos
   izq/der se miden sobre ese extremo visto desde arriba; la marca de esquina
   indica extremo ingleteado. Si la línea dice "Sin sección declarada", la
   orientación se toma solo de la convención — no del dibujo.
3. **Diagrama**: despunte inicial sombreado, piezas en secuencia con código
   `P01-U01-M07`, líneas rojas = pasadas de disco, zona final = retazo
   recuperable o cola de desecho (el texto lo dice explícitamente).
4. **Tabla**: misma secuencia que el diagrama; largo de corte en mm, ángulos por
   extremo, "lleva mecanizado" en Obs. si la pieza continúa a CNC.
5. **Conservación**: si la línea de cierre no dice "cierra exacto", la barra no
   cuadra — reportar antes de cortar.
6. **QR / huella**: cada página lleva la huella corta del plan; el QR del bloque
   de identidad vuelve a la orden. Un plan reoptimizado tiene huella distinta:
   comparar huella, no la hora de impresión.
