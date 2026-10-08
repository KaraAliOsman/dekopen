# P24 — Analítica que sirve para decidir: conversión, margen real vs. cotizado, merma y tiempos

**Depende de:** P12, P15 y P23 (datos de producción, consumo e instalación). Va al final.

## Objetivo
Que el dueño responda con datos del propio sistema: ¿cuánto cotizo y cuánto cierro? ¿Gano lo que creo que gano? ¿Cuánta merma tengo de verdad? ¿Dónde se atrasa la planta?

## Reglas de corrección (críticas)
- Cada métrica tiene una **definición escrita** en `docs/analytics/metricas.md`: fórmula, tablas y columnas fuente, filtros, tratamiento de nulos y período, y **una consulta SQL versionada** con su test sobre el fixture con valores esperados calculados a mano.
- Las métricas sin datos suficientes muestran “Sin datos suficientes” y la causa. **Nunca una cifra con datos parciales sin advertirlo.**
- Todo con RLS por organización; sin agregaciones entre organizaciones.

## Métricas
1. **Ventas:** cotizaciones emitidas, aprobadas y rechazadas; tasa de conversión por período, por estimador y por tipología; tiempo medio de emisión a decisión; motivos de rechazo; monto en pipeline por fase.
2. **Margen:** margen cotizado (motor, en la revisión aprobada) vs. **margen real**, donde el costo real sale de los consumos reales de material del inventario, de las horas por estación si existen y de los remakes. Desviación por proyecto y por tipología.
3. **Producción:** merma real vs. plan del optimizador, aprovechamiento de barras, uso de retazos, tiempos por estación (desde los timestamps de los pasos), OTs a tiempo vs. atrasadas y remakes por causa.
4. **Instalación y postventa:** instalaciones a tiempo, incidencias por tipo y por tipología, y garantías abiertas.

## UI
Página Analítica (OWNER y quien tenga permiso): selector de período, tarjetas solo con métricas que tienen datos, gráficos sobrios con los tokens de P01, tabla de detalle exportable a CSV y, en cada cifra, el enlace “¿Cómo se calcula?” a su definición.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño decidiendo. Debe sentir: “sé dónde gano y dónde pierdo, y por qué”.
- **Anatomía:** Pocas vistas con decisión asociada: conversión, margen real vs. cotizado por obra, merma real, tiempos por estación. Cada gráfico con su pregunta como título y su fuente.
- **Momento de firma (preservar o crear):** F6: cada cifra se abre hasta las obras, OT y movimientos que la componen.
- **Idea que sube el techo (obligatoria, con el motor):** La diferencia de margen de una obra se descompone en causas (merma, remake, horas, descuento) con el monto de cada una y el enlace al origen.
- **Slop a eliminar aquí:** Dashboards de 12 gráficos, tortas, KPI sin decisión, colores por serie fuera de la paleta.
- **Preguntas del pase editorial:** ¿Cada gráfico responde una pregunta que el dueño hace de verdad? ¿Se puede llegar del número a su causa en 2 clics?

## Criterios de aceptación
- Un test SQL por métrica con el valor esperado calculado a mano sobre el fixture (documentado en el test).
- Test de RLS (la organización B no ve datos de la A).
- Test de “sin datos suficientes”. Capturas.
