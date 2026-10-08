# Guía de revisión del dueño — DEKOPEN v1

Esta guía te deja verificar el producto completo con tus propias manos,
en menos de una hora, sobre el stack local. Cada paso señala qué ver y qué
debería pasar. Las credenciales del fixture viven en `.fixture-state.json`
(se genera con `scripts/dev_fixture.py`; contraseña `Demo-Fixture-2026!`).

## 0. Levantar el stack (5 min)

```bash
supabase start                        # postgres + auth + storage + mailpit
.venv/bin/python scripts/dev_fixture.py   # org «Ventanas del Sur SpA» + datos
source .run/env.sh                    # DATABASE_URL, CORS, mocks declarados
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
.venv/bin/python backend/manage.py runjobs --poll 1.5   # trabajos asíncronos
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
```

Entra a http://127.0.0.1:5173 — la portada es pública; «Entrar» lleva al
login por magic-link (el correo llega a Mailpit en http://127.0.0.1:25324).

Roles del fixture (mismo password): `demo-owner@` (propietario, exige
autenticador TOTP), `demo-estimator@`, `demo-manager@` (jefe de taller),
`demo-operator@`, `demo-installer@`, `demo-multi@fixture.dekopen.local`.

## 1. Recorridos que vale la pena ver a mano

| # | Qué hacer | Qué deberías ver |
|---|-----------|------------------|
| 1 | Entra como `demo-estimator`, abre **Inicio**. | «Hoy» muestra la bandeja real: cotización con cambios pedidos, una rechazada, varias abiertas sin decidir, margen aprobado listo para emitir. |
| 2 | **Proyectos → Casa Ríos — vitrina de 12 posiciones.** | Pipeline Cotizada→Enviada→Aprobada→Anticipo→Saldo→Liberada; grilla con miniaturas 3D reales, precio por posición y total con IVA. |
| 3 | Abre la **cotización del portal** (link «vigente» del fixture, ruta `/cotizacion/<token>`). | Propuesta con la marca del taller (logo, RUT, dirección, colores), productos con renders y medidas, totales NETO/IVA/TOTAL, validez «quedan 31 días». Aprobar pide nombre + RUT + aceptación literal. |
| 4 | En **Cobranza** del proyecto: «Nuevo enlace de pago» (anticipo). | Genera un link `sandbox` marcado como tal; abrirlo muestra la página «Pago simulado — DEKOPEN»; al pagar, el pago aparece solo en Cobranza con folio RC-. |
| 5 | Entra como `demo-manager` → **Producción**. | Tablero por estaciones con conteos reales (listas/en curso/bloqueadas). |
| 6 | Como `demo-operator` → **Producción** en una tablet/ventana angosta. | Se elige estación una vez («queda guardada en esta tablet»); la cola muestra piezas con códigos M-/V-/I-. |
| 7 | **Analítica** como `demo-owner`. | Ventas (emitidas/aprobadas/rechazadas/conversión), pipeline por fase, conversión por tipología; cada cifra lleva «¿Cómo se calcula?». Con estimador la sección muestra «Sin acceso» (honesto, no roto). |
| 8 | **Catálogo técnico → Importar** (adjunta un XLSX con la plantilla de la propia pantalla). | La importación queda en revisión con candidatos y evidencia; publicar exige resolver cada clave — la compuerta es visible. |
| 9 | **Mi agenda** como `demo-installer`. | Paradas con dirección, contacto, ventana AM/PM, estado de medición y checklist. |
| 10 | En un proyecto aprobado, pestaña **Documentos → Revisiones**. | Comparación REV-A ↔ REV-B con diff estructurado; los documentos emitidos son inmutables. |

## 2. Lo que está declarado como sandbox

- **Pagos Flow**: `FLOW_WS_MOCK=1` → proveedor simulado con checkout local
  propio; el pago entra por el mismo camino de webhook real.
- **SII/DTE**: `SII_WS_ENVIO_MOCK=1` → respuestas ACCEPTED/OBSERVED/REJECTED
  según `SII_WS_ENVIO_MOCK_VERDICT`.
- **IA**: en el entorno del encargo la clave MiMo devolvía 429 de cuota; con
  `AI_GATEWAY_MOCK_ENABLED=1` el asistente corre el pipeline real con
  contenido simulado, marcado «Proveedor de prueba» en la barra superior.

Todo lo demás — precios, planos de corte, OT, etiquetas, portal, agenda,
postventa — es código de producto real contra la base de datos real.

## 3. Si algo falla al levantar

- `login` no manda correo: faltan `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY`
  en el entorno de `npm run dev` (están en `.run/env.sh`).
- La IA responde «proveedor no disponible»: revisa `ai_routes` (`MOCK` o la
  key MiMo con cuota).
- Los pagos no generan link: falta `BILLING_FRONTEND_ORIGIN`.

Los detalles de activación productiva de cada integración están en
`docs/operations/ACTIVACION.md`.
