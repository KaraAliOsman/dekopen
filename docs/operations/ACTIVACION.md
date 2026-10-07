# Activacion de integraciones externas diferidas

Este indice no contiene secretos. Los valores reales se cargan como variables de entorno en el proveedor de despliegue o en el entorno local protegido.

## Railway / hosting

| Campo        | Detalle                                                                                                                                                               |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Estado       | No conectado en este programa local.                                                                                                                                  |
| Adaptador    | Configuracion de servicios `railway*.toml` y variables de entorno de Django/Vite.                                                                                     |
| Variables    | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, `SECRET_KEY`, `RAILWAY_GIT_COMMIT_SHA`.    |
| Activacion   | Crear proyecto Railway, conectar repo, configurar servicios frontend/backend/worker, cargar variables por ambiente y ejecutar migraciones/seed segun runbook vigente. |
| Verificacion | `GET /health/ready/`, login real, emision de DOC-01 sandbox y revision de logs backend/worker sin errores.                                                            |

## Flow

| Campo        | Detalle                                                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Estado       | Diferida; el proveedor simulado recorre el flujo de punta a punta hasta que el dueno cargue credenciales reales.                                   |
| Adaptador    | `backend/billing/flow.py::client_for`: con `FLOW_WS_MOCK=1` toda integracion habla con `MockFlowClient` — la pagina de cobro local `GET/POST /api/v1/billing/flow-sim/<token>/` (`billing/sim.py`) deja al pagador pagar o rechazar y la decision entra por el mismo `payment_status` que el webhook real. Sin la env, `FlowClient` real. Enlace con vencimiento: `project_payment_links.expires_at` (TTL de referencia 72 h). |
| Variables    | `FLOW_WS_MOCK` (opt-in del simulador), `FLOW_SIM_ORIGIN` (origen de la pagina simulada; default `http://127.0.0.1:8000`), `FLOW_API_URL`, `FLOW_API_KEY`, `FLOW_SECRET_KEY`, `BILLING_CALLBACK_ORIGIN`, `BILLING_FRONTEND_ORIGIN`, `FLOW_MERCHANT_TIMEZONE`.               |
| Activacion   | Crear comercio sandbox, cargar llaves en Ajustes > Integraciones, configurar URL de retorno/callback, ejecutar pago de prueba y luego repetir con credenciales productivas. Quitar `FLOW_WS_MOCK` al pasar a real: el simulador nunca es fallback silencioso. |
| Verificacion | Crear enlace de pago, completar pago en el checkout simulado (o sandbox real), confirmar idempotencia de callback, `project_payment_id` ligado al link y estado visible en proyecto/portal. |

## SII / DTE

| Campo        | Detalle                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Estado       | Diferida; sin certificado + CAF + adapter `sii-ws` configurado, todo documento se imprime como **«Documento interno — no valido como documento tributario electronico»** y el envio se marca `adapter=mock`. Nunca se dibuja un timbre SII simulado.     |
| Adaptador    | `backend/projects/sii_envio.py::integration_state` resume `{adapter, certificate, caf_available, certified}`; el envio usa `SII_WS_*` reales o, con `SII_WS_ENVIO_MOCK=1` (solo desarrollo), el mock que responde ACCEPTED / OBSERVED («reparos», estado propio P11) / REJECTED segun `SII_WS_ENVIO_MOCK_VERDICT`. |
| Variables    | `SII_CAF_KEK` (cifrado de claves CAF en reposo — sin él la carga del CAF responde 503), `SII_WS_URL`, `SII_WS_STATUS_URL`, `SII_WS_TOKEN`, `SII_WS_ENVIO_MOCK` + `SII_WS_ENVIO_MOCK_VERDICT` (dev), `SII_ENV`, `SII_CERTIFICATE_PASSWORD`, `SII_PROVIDER_*` cuando se conecte el adaptador final.                                                |
| Activacion   | Cargar certificado y CAF autorizados en Ajustes > Integraciones, declarar ambiente certificacion/produccion, configurar `SII_WS_*`, emitir DTE de certificacion y validar respuesta del SII.                                                          |
| Verificacion | `integration_state.certified=true`, DTE aceptado en ambiente de certificacion (envio ACCEPTED/OBSERVED visible en la linea de tiempo de Cobranza), XML/PDF almacenado como documento emitido e historial inmutable.                                    |

## Correo con dominio propio

| Campo        | Detalle                                                                                                                                                                                                                                                                        |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Estado       | Diferida; `MAIL_PROVIDER=sandbox` (default) registra cada correo en `public.mail_messages` sin entregarlo — la bandeja es la evidencia. Mailpit cubre local cuando `MAIL_PROVIDER=smtp` apunta a él.                                                                              |
| Adaptador    | `backend/mail/providers.py`: `MAIL_PROVIDER=smtp` entrega vía `EmailMultiAlternatives` con el logo white-label como imagen CID inline. Las plantillas (6 transaccionales, es-CL usted — incluye `order_sent`, el aviso de OC al proveedor) viven en `backend/mail/templates.py`; el magic link de GoTrue en `supabase/templates/magic_link.html`. |
| Variables    | `MAIL_PROVIDER` (`sandbox`\|`smtp`), `MAIL_FROM`, `MAIL_SMTP_HOST`, `MAIL_SMTP_PORT`, `MAIL_SMTP_USER`, `MAIL_SMTP_PASSWORD`, `MAIL_SMTP_TLS` (`1`/`0`), `MAIL_DEV_PREVIEWS` (`1` habilita `/dev/correos` fuera de DEBUG).                                                          |
| Activacion   | Verificar dominio, SPF/DKIM/DMARC, cargar credenciales SMTP en backend y worker `runjobs`, y disparar un envío real (compartir cotización). La bandeja se vacía con `python backend/manage.py mail_flush` o el worker continuo.                                                    |
| Verificacion | Correo recibido en bandeja externa con logo propio y acento de marca (o fallback teal-800 si el color no pasa AA 4.5:1), enlaces válidos, estado `SENT` en `mail_messages` y sin secretos en logs.                                                                                  |

## Webhooks productivos

| Campo        | Detalle                                                                                                  |
| ------------ | -------------------------------------------------------------------------------------------------------- |
| Estado       | Diferida; endpoints locales y jobs deben probarse con payloads firmados antes de produccion.             |
| Adaptador    | Vistas backend por integracion, jobs idempotentes y auditoria.                                           |
| Variables    | `WEBHOOK_SIGNING_SECRET_*`, mas las variables especificas de cada proveedor.                             |
| Activacion   | Registrar endpoints publicos, configurar secreto de firma, activar reintentos del proveedor y monitoreo. |
| Verificacion | Reenvio del mismo evento no duplica efectos y eventos fuera de orden quedan auditados.                   |

## Proveedor de IA

| Campo        | Detalle                                                                                                                       |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Estado       | Conectado por entorno local; no se debe exponer al frontend ni al repo.                                                       |
| Adaptador    | `backend/ai_gateway/providers.py` con convencion `AI_GATEWAY_{PROVIDER}_*`.                                                   |
| Variables    | `AI_GATEWAY_MIMO_API_KEY`, `AI_GATEWAY_MIMO_BASE_URL`, `AI_GATEWAY_MIMO_MODEL`, `AI_GATEWAY_ROUTE_PROVIDER`.                  |
| Activacion   | Cargar variables en backend y worker, seleccionar proveedor MIMO en rutas IA y ejecutar una consulta controlada.              |
| Verificacion | Job IA termina con proveedor real, auditoria queda registrada y ningun valor secreto aparece en logs, HTML o bundle frontend. |
| Desarrollo   | Proveedor MOCK cuando el cupo MIMO esta agotado (429): `AI_GATEWAY_MOCK_ENABLED=1` en el entorno del backend y `UPDATE ai_routes SET provider='MOCK'` en la base local; la extraccion/revision de importaciones corre el mismo pipeline. |

## Reglas de seguridad de vidrio (NCh 135/2)

| Campo        | Detalle                                                                                                                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Estado       | Pendiente de texto oficial: las reglas y limites del seed son `SEED_SYNTHETIC` con `review_pending=TRUE` y `source_ref` marcado; son ejemplos de aviso, no norma.                              |
| Adaptador    | `glass_safety_rules` + `glass_type_limits` (datos por org, RLS) evaluados por el motor; severidad `WARNING` avisa y `MANDATORY` bloquea con ERROR.                                            |
| Variables    | Ninguna externa. Las hojas "Seguridad vidrio" y "Limites vidrio" de la plantilla de catalogo (`make` ingesta D01) cargan las reglas oficiales con `data_provenance='IMPORT'`.                 |
| Activacion   | Revisar las reglas semilla contra la norma oficial, corregir o reemplazar via ingesta/catalogo, bajar `review_pending` y subir severidad a `MANDATORY` solo donde la org lo exija.            |
| Verificacion | pgTAP `176_d02_glass.test.sql`, test de regla de seguridad en `engine/tests/test_glass.py` y finding `GLASS-THICKNESS-MISMATCH` en BOM de posiciones con especificacion heredada ambigua.      |

## Pedido al vidriero (documento de corte)

| Campo        | Detalle                                                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Estado       | Descarga local; el envio al vidriero (correo/portal) queda fuera de alcance y es un click humano futuro, igual que el resto de integraciones externas.         |
| Adaptador    | `GET /api/v1/production/orders/{order_id}/glass-order/?output=pdf|csv`; `?orders=<uuid,...>` fusiona OT de la misma version de proyecto.                       |
| Variables    | Ninguna externa; comparte `DATABASE_URL` y las credenciales de plataforma del documento.                                                                        |
| Activacion   | Ninguna: opera sobre OT confirmadas (`order_type='WORKSHOP_OT'`). El formato CSV abre en Excel/hojas del vidriero con medidas en mm enteros.                   |
| Verificacion | Integracion `test_glazier_order.py` (OT de 12 posiciones == motor), PDF con composicion+recargos+QR de etiqueta, piezas `review_pending` separadas del corte. |
