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
| Estado       | Diferida; usar sandbox hasta aprobacion del dueno.                                                                                               |
| Adaptador    | `backend/billing` con proveedor Flow configurado por entorno.                                                                                    |
| Variables    | `FLOW_API_URL`, `FLOW_API_KEY`, `FLOW_SECRET_KEY`, `BILLING_CALLBACK_ORIGIN`, `BILLING_FRONTEND_ORIGIN`, `FLOW_MERCHANT_TIMEZONE`.               |
| Activacion   | Crear comercio sandbox, cargar llaves, configurar URL de retorno/callback, ejecutar pago de prueba y luego repetir con credenciales productivas. |
| Verificacion | Crear enlace de pago, completar pago sandbox, confirmar idempotencia de callback y estado visible en proyecto/portal.                            |

## SII / DTE

| Campo        | Detalle                                                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Estado       | Diferida; no hay emision real sin certificados/CAF del contribuyente.                                                                      |
| Adaptador    | `backend/billing` y tablas de CAF/certificados/DTE.                                                                                        |
| Variables    | Nombres reservados por proveedor DTE/SII: `SII_ENV`, `SII_CERTIFICATE_PASSWORD`, `SII_PROVIDER_*` cuando se conecte el adaptador final.    |
| Activacion   | Cargar certificado y CAF autorizados, declarar ambiente certificacion/produccion, emitir DTE de certificacion y validar respuesta del SII. |
| Verificacion | DTE aceptado en ambiente de certificacion, XML/PDF almacenado como documento emitido e historial inmutable.                                |

## Correo con dominio propio

| Campo        | Detalle                                                                                                               |
| ------------ | --------------------------------------------------------------------------------------------------------------------- |
| Estado       | Diferida; Mailpit cubre local.                                                                                        |
| Adaptador    | Backend de notificaciones/correo que use el proveedor elegido.                                                        |
| Variables    | `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_FROM`, `EMAIL_USE_TLS`. |
| Activacion   | Verificar dominio, SPF/DKIM/DMARC, cargar credenciales del proveedor y probar magic link/cotizacion enviada.          |
| Verificacion | Correo recibido en bandeja externa, enlaces validos y sin secretos en logs.                                           |

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
