# Demo integral A→Z — DEKOPEN en vivo

HEAD `a560176` (`devin/1790335313-commercial-workspace`). Grabación única continua en una sola toma: Chrome maximizado en pantalla real 1600×1200 (viewport 1600×1017), Vite `127.0.0.1:5173`, Django `127.0.0.1:8000`, Supabase local, Mailpit real para el magic link.

## Videos

- `demo-a-z.mp4` — **27:52, toma completa en tiempo real** (concatenación de los segmentos raw; el pipeline de edición solo conserva ventanas alrededor de anotaciones).
- `demo-annotated.mp4` — 40s, versión editada por el recorder con los overlays de anotación (sirve como tabla de contenidos visual).

## Recorrido grabado (en orden)

1. **Landing pública** `/` anónima — hero, capturas reales, CTA Entrar.
2. **Acceso real**: `/login` → email → "Revisa tu correo" → Mailpit → magic link → `/auth/callback` → **MFA TOTP** (owner exige aal2) → dashboard como Propietario.
3. **Dashboard** — necesita atención, continuar donde quedaste, pipeline operación, cobranza CLP.
4. **Proyectos** → **P-000005 "Cien posiciones f14"** (100 posiciones, Cotizado $4.051.075, pipeline Cotizada→Enviada→Aprobada→Anticipo→Saldo→Liberada, scroll por los 100 vanos congelados).
5. **Studio** — editor paramétrico del vano (borrador P-000004): árbol del conjunto, serie/hoja/manilla/vidrio, cotas en vivo, **Vista 3D**, tab Técnica, acciones (dividir, modificar con DEKOPEN, generar alternativas).
6. **Cotización comercial** — modos de precio, margen objetivo, lista comercial; sección Cotización del proyecto: revisión actual, enlace enviado, historial inmutable, **DOC-01 PDF emitido** abierto en pantalla.
7. **Portal público** `/cotizacion/<token>` — propuesta con totales, items agrupados con visual/técnica, condiciones de pago; **aprobación en vivo** (Marcela Fuentes, RUT) → "Propuesta aprobada".
8. **Cobranza** — el proyecto pasa a Aprobado en la app; `Registrar pago` → Anticipo $2.025.537 Transferencia → recibo **RC-0001**, saldo recalculado.
9. **Compras** — POs por estado (COMPLETADA/BORRADOR), proveedores, requisitos por revisión congelada.
10. **Inventario** — stock con reservado/disponible, **retazos con trazabilidad** (RET-* ← OT-P-000001-REV-A-01), movimientos, generadores DOC-01/03/05/06/07.
11. **Producción** — colas por estación, liberaciones pendientes, OT-P-000001-REV-A-01 DISPATCHED: resumen de vidrios, plan de corte por patrones (13 barras, 52 cortes, 598mm desperdicio, 99ms), packs PDF, **CNC: "Generar programa" en vivo** → `…-CNC-01-02` generado y `-01` marcado SUPERSEDIDO en pantalla; etiquetas por unidad; 9 pasos con estación; trazabilidad barra→pieza; historial completo (release→optimize→pasos→QC→embalaje→despacho GD-0001).
12. **Asistente IA** — dock: pregunta contextual respondida (proveedor MOCK determinista, créditos debitados); modo Agente: goal ejecutado → job "Consultó proyecto" con enlace "ver trabajo".
13. **Catálogo** (series), **Trabajos** (cola con el job del agente Completado 100%), **Ajustes** (cuenta, MFA activa, rol, **tema oscuro en vivo**, organizaciones, atajos).
14. **Clientes**, **Ventas** (`/pricing/commercial` selector de proyecto) y **rastreo de pieza** `P01-U01-M10` → barra 6, corte, 9/9 pasos.

## Incidencias durante la grabación (resueltas en vivo)

- El proveedor IA falló al primer intento ("proveedor no disponible"): el `runserver` en curso no tenía `AI_GATEWAY_MOCK_ENABLED=1` y las rutas apuntaban a MIMO. Se actualizó `ai_routes.provider='MOCK'` + reinicio de runserver con el flag (y el worker runjobs, que no estaba corriendo). La respuesta MOCK se muestra con la nota honesta "Respuesta determinista del proveedor MOCK".
- Fixture recreada para la demo: máquina CNC-01 + 3 herramientas (saw/drill/end_mill; el plan exige `tool_id` 'drill' — el código del tool debe coincidir), programa CNC generado, posición editable en P-000004 (draft), enlace de portal nuevo para P-000005.

## Estado resultante de datos (post-grabación)

- P-000005: APROBADO con anticipo RC-0001 $2.025.537 registrado; portal muestra "Propuesta aprobada".
- P-000004: posición "Vano demo" (TILT_TURN_RIGHT 1200×1400) agregada.
- CNC: programas `-01` (superseded) y `-02` (current) en OT-P-000001-REV-A-01.
