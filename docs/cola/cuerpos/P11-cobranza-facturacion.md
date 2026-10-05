# P11 — Cobranza, pagos y facturación: correcto, legible y honesto sobre SII

**Depende de:** P01 y P02. Coordina con P10 (CTA de pago).

## Objetivo
Que el dueño sepa en todo momento **cuánto le deben, cuánto ha cobrado y qué documento respalda cada movimiento**, sin ambigüedad sobre qué es un documento tributario válido y qué no.

## Situación actual
- Archivos: `frontend/src/features/projects/ProjectPaymentsPanel.tsx` (línea 610, `pattern=` con mensaje nativo en inglés; P01 lo corrige), `ProjectPaymentLinksPanel.tsx` y `frontend/src/features/billing/`; backend en `backend/billing`; motor en `engine/src/dekopen_engine/billing.py`. El PR #112 ya corrigió el determinismo de DTE, la idempotencia de facturas y enlaces, y la carrera de PDF anulado.
- (auditoría) “No pudimos cargar los links de pago” en Cobranza; la factura FAC-0001 trae emisor, receptor y detalle, pero no es claro si es un DTE válido. En Ajustes existen las secciones “Facturación electrónica SII” y “Certificado digital” (video A-Z, minuto 25). Flow no está configurado en el entorno de pruebas (fase 14: PENDIENTE-EXTERNO).

## Alcance
1. **Panel de Cobranza del proyecto:**
   - Calendario derivado del acuerdo sellado: anticipo y saldo con sus montos y vencimientos.
   - Cobrado y saldo, con `<Money>`.
   - Registro de pago manual (MoneyField CLP entero, medio, referencia y fecha) → recibo `RC-xxxx` en PDF.
   - Enlaces de pago Flow con estado, vencimiento y monto menor o igual al saldo.
   - Línea de tiempo de movimientos con actor.
2. **Causa raíz** de “No pudimos cargar los links de pago”: reprodúcela, corrígela y agrega un test.
3. **Facturas, boletas y notas de crédito:** lista con estado, enlace al PDF y “anular con nota de crédito” si ya existe en el backend. PDF con emisor completo, receptor, detalle por línea (cantidad, descripción humana, unitario neto y total neto), neto, IVA y total.
4. **Honestidad tributaria:** si la integración SII no está activa y certificada para la organización, todo documento lleva la leyenda visible “Documento interno — no válido como documento tributario electrónico”, y **no se imita** el timbre electrónico de SII. Si la integración está activa, muestra el estado SII real (aceptado, reparos o rechazado) que devuelve el backend. **No construyas una integración SII nueva** en este encargo.
5. **Etiquetas:** Neto, IVA 19 % y Total siempre explícitos; moneda real; descuento como línea aparte.

## Fuera de alcance
El portal (P10). **SII y Flow son integraciones diferidas** (las conecta el dueño después de aceptar el producto): verifica qué existe hoy en el repo y deja ambas **completas detrás de un adaptador**, con un proveedor simulado que recorra el flujo de punta a punta (emisión de DTE con folio simulado y estados aceptado/reparos/rechazado; pago con retorno y webhook simulados). No implementes firma ni certificación SII propias: el adaptador apunta a la interfaz que ya exista (o a una genérica de proveedor DTE) y `docs/operations/ACTIVACION.md` documenta qué falta para activarlo. Ajustes › Integraciones muestra ambos como “No conectado”.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El dueño revisando la plata. Debe sentir: “sé cuánto me deben y qué lo respalda”.
- **Anatomía:** `DataTable` con saldos en Mono, calendario de cuotas como `Stepper`, cada movimiento con su documento. Flow en sandbox detrás del adaptador (integración diferida).
- **Momento de firma (preservar o crear):** F6 aplicada a saldos: cada saldo explica de qué movimientos sale.
- **Idea que sube el techo (obligatoria, con el motor):** La cobranza vencida aparece en “Hoy” del dueño con el mensaje al cliente ya redactado (IA, solo preparado; enviar requiere clic).
- **Slop a eliminar aquí:** Estados de pago solo por color, documentos tributarios ambiguos, enlaces de pago con error crudo.
- **Preguntas del pase editorial:** ¿Queda claro qué es un documento tributario válido y qué no? ¿El saldo cuadra siempre con los movimientos?

## Criterios de aceptación
- e2e: la cotización aprobada genera un calendario 50/50 → se registra el anticipo (recibo RC) → se crea un enlace de pago por el saldo (con el proveedor simulado de Flow; se indica en el PR) → un intento de pago mayor al saldo se rechaza (backend) → saldo 0 → estado “Pagado”.
- Test de la leyenda “Documento interno…” cuando SII no está activo.
- Sin mensajes nativos en inglés (captura de validación en español). Capturas de Cobranza en 1440 y 1024.
