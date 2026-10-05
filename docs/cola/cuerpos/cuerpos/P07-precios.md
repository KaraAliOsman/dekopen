# P07 — Workspace de precios v2: actual vs. propuesto, cascada de precio, banda de margen y aprobaciones

**Depende de:** P01 y P02.

## Objetivo
Que el estimador y el dueño **confíen en el número**: ver de dónde sale cada peso, qué cambió y por qué, si el margen está dentro de la banda objetivo, y pedir o dar aprobación sin salir de la pantalla.

## Situación actual
- Rutas: `/projects/:id/pricing`, `/pricing/commercial` (`CommercialPricingPage`) y `/pricing/cost-lists` (`frontend/src/features/pricing/PricingPage.tsx`). Backend en `backend/pricing`; motor en `engine/src/dekopen_engine/pricing.py` y `commercial.py`.
- (auditoría) Empieza con un formulario largo y crudo (Modo de precio, Lista comercial DEFAULT, Moneda, Fecha, Registro FX, Descuento, Segmento, Motivo); después viene una franja de KPIs (Costo total, Margen, Precio lista, Neto, Impuesto, Total) y una tabla. Se vio “No se pudieron cargar los datos” al montar. Las operaciones pendientes son texto denso. El `[object Object]` en las autoridades ya está corregido (`PricingPage.tsx:1108`).

## Diseño objetivo para `/projects/:id/pricing` (“Precio del proyecto”)
1. **Encabezado comparativo**, Actual vs. Propuesto: Neto, IVA, Total, Costo y Margen, con Δ absoluto y Δ % (Δ de margen en **puntos porcentuales**). **Banda de margen** visual frente al objetivo de la organización. Si no existe el ajuste, créalo en Ajustes con permiso solo OWNER: mínimo, objetivo y máximo.
2. **Cascada de precio**, siempre visible, por proyecto y por posición:
   - **Costo:** perfiles, refuerzo, vidrio, herrajes, accesorios, extras y servicios (D06), recargos de color (D05) y de vidrio (D02), merma y proceso o mano de obra.
   - **Hasta el precio:** costo → margen → precio lista → descuento → neto → IVA 19 % → total.
   - Cada barra muestra su procedencia (versión de la lista de costos, snapshot FX con fecha, lista comercial).
   - Todos los valores salen del motor. **La suma cierra exacto** (Decimal).
3. **Tabla por posición:** Pos., Ubicación, Tipología, Dims, Cant., Costo unitario, Precio unitario, Neto línea, Margen %, Δ vs. actual y avisos. **Sin costo → bloqueo explícito**, nunca 0. Al expandir una fila se ve la composición de esa posición.
4. **“¿Por qué cambió?”:** descomposición determinista del Δ por impulsor (cantidad, medidas, vidrio, herrajes, lista de costos, FX, descuento, segmento). Si el motor no expone esta descomposición, impleméntala **en el motor** con golden tests: re-precio con un impulsor aplicado por vez en un orden canónico documentado, de modo que la suma de los aportes sea igual al Δ total.
5. **Panel de control** (derecha): lista comercial, moneda, snapshot FX (select poblado con fecha y valor), descuento, segmento y motivo (obligatorio si el descuento supera el umbral o el margen queda bajo la banda). Botones: “Aplicar” si está dentro de la banda; “Solicitar aprobación” si está fuera; y “Retirar solicitud”.
6. **Aprobaciones:** cola del dueño (también como ítem en “Hoy” de P03 y en la campana), con aprobar o rechazar con comentario. Notifica al solicitante. Queda en auditoría quién, cuándo y qué campos cambiaron.
7. **Historial agrupado por revisión** (REV-A, REV-B…), con actor, cambios por campo y una marca “resultó en emisión”.
8. **Administración de autoridades separada:** `/pricing/*` queda para listas de costo, FX y listas comerciales, con una **vista de cobertura**: SKU emitidos por el catálogo sin costo vigente (conteo, lista y enlace a cargarlos).

## Fuera de alcance
Emisión de la cotización (P08) y documento al cliente (P09).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Estimador y dueño. Deben sentir: “confío en el número y sé qué gano”.
- **Anatomía:** Constitución §5.5 (tablas), `TraceButton` de P01 en cada monto, banda de margen como regla visual (no como color de fondo).
- **Momento de firma (preservar o crear):** F6 (“¿De dónde sale?” en cada peso) y la cascada costo → precio como una sola lectura vertical.
- **Idea que sube el techo (obligatoria, con el motor):** Mover el margen muestra en vivo la utilidad de la obra y su posición en la banda; bajar del mínimo convierte el botón en “Pedir aprobación” con la causa precargada.
- **Slop a eliminar aquí:** Un formulario crudo antes de la información, porcentajes como `92.5333%`, totales sin explicación del Δ, gráficos de torta decorativos.
- **Preguntas del pase editorial:** ¿El dueño entiende por qué subió el precio de la REV-B sin preguntar? ¿Cada número tiene fuente a un clic?

## Criterios de aceptación
- Golden test: la cascada suma exactamente el total del motor en los proyectos de 12 y 100 posiciones del fixture.
- Tests de la semántica unitario vs. línea (cantidad 3 → línea = 3 × unitario; redondeo documentado).
- Test de la descomposición: la suma de los aportes es igual al Δ total exacto.
- e2e: el estimador baja el margen bajo la banda → solicita aprobación → el dueño la ve en “Hoy” → aprueba → el estimador recibe la notificación → la auditoría muestra actor y campos.
- La vista de cobertura lista los SKU sin costo del fixture.
- Sin “No se pudieron cargar los datos” al montar (encuentra la causa raíz y agrega test).
- Capturas antes/después.
