# Fase 14 — validación completa del producto en vivo (CIERRE)

HEAD `23b3b45` (`devin/1790335313-commercial-workspace`). Stack dev real: Vite `localhost:5173`, Django `127.0.0.1:8000` (`--noreload`), Supabase `supabase_db_dekopen` (138 migraciones + `seed.sql` + `scripts/dev_fixture.py`), Mailpit, Chrome CDP :9333.

**Incidente de entorno (relevante para evidencia):** a mitad de la corrida el stack se reinició dos veces (el lead corría `make test-db`, que hace `db reset`+`stop`). Toda la fixture se borró. Reconstruí: `supabase start` → `dev_fixture.py` → factor TOTP reinsertado (`auth.mfa_factors` para demo-owner, uid nuevo `f170805e`). El lead confirmó que no volverá a resetear hasta que termine. Todo lo reportado abajo se re-verificó DESPUÉS del último wipe sobre los datos reconstruidos.

**Nota de auth:** `POST /auth/v1/otp` ahora responde `otp_disabled` con `create_user:false` — los magic links siguen siendo el flujo UI (verificado en fase 13), pero para el API usé password grant (`token?grant_type=password`, la fixture define `Demo-Fixture-2026!` para todos los roles).

---

## Recorrido 1 — cuenta nueva → cotización emitida — ✅ PASA (compuesto)

- Onboarding wizard (7 pasos: identidad→sistema→datos→cliente→proyecto→vano→cotización) verificado en fase 13 a HEAD `875655d`; el código del wizard no cambió desde entonces (diff a `23b3b45` no toca `features/onboarding`). Evidencia: `captures/phase13/*`.
- El paso **cotización emitida** se verificó en vivo esta fase: proyecto P-000004 "Venta Completa F14" → pricing apply → `POST documents/projects/<id>/freeze/` → **REV-A emitida** (`emitted_at` real) → DOC-01 PDF 38KB `COT-P-000004-REV-A`.

## Recorrido 2 — venta completa — ✅ PASA (pago = PENDIENTE-EXTERNO)

Proyecto P-000004, 12 posiciones / 14 unidades (qty 2 en Living y Baño), tipologías mixtas (FIXED, TILT_TURN_LEFT/RIGHT, SPLIT_V con hoja oscilobatiente), extras $350.000 instalación + $80.000 flete, alternativa de diseño verificada vía `positions/<id>/design-alternatives/` (200, retorna alternativas con rationale).

- `POST pricing/preview` TARGET_GROSS_MARGIN_PROJECT 35% → neto $1.406.238 / IVA $267.185 / **bruto $1.673.423**; apply → APPLIED; freeze → REV-A.
- Portal público: `POST projects/<id>/quote-link/` → token; `GET portal/quotes/<token>/` sin auth → propuesta completa con totales, condiciones, items con desglose unitario.
- `POST portal/quotes/<token>/decide/` APPROVED (decided_by+rut) → 200, re-decide idempotente 200. Proyecto → status APPROVED.
- Pago: `projects/payment-integration/` → `{configured:false}`; `POST payment-links/` → **422 `flow_not_configured`** → **PENDIENTE-EXTERNO** (requisito: credenciales Flow en Ajustes). Registro manual de anticipo funciona: `POST payments/` ANTICIPO $500.000 → receipt RC-0001; sobrepago rechazado (`payment_exceeds_balance`).
- Capturas: `10-project-detail-revB.png`, `11-portal-quote.png`, `12-portal-approved.png`.

## Recorrido 3 — cambio/revisión — ✅ PASA

- Edición en proyecto emitido → 409 `revision_required` (inmutable ✓). `POST projects/<id>/successor/` `{confirmed,expected_current_revision:'REV-A'}` → 201, status DRAFT, `current_revision=REV-B` (APPROVED revisable — decisión documentada en código; órdenes en producción lo bloquearían).
- Modifiqué Terraza fijo 1000×1500→1200×1800. Intenté también color FOILED → freeze rechazó `physical_stock_color_mismatch` — **correcto**: el stock físico DEMO_60 es solo WHITE; revertí vía `reset-pricing` + edición.
- Re-inputs → preview REV-B → apply → freeze → **REV-B emitida** (`5de28a1a`).
- Compare `versions/compare?base=REV-A&head=REV-B` → ambos `integrity:VERIFIED`, base neto 1.406.238 vs head 1.433.839, `changed:1, unchanged:11`, `price_gross_delta:+32.845`. Sin totales mixtos.
- Observación (no defecto): el link de portal sigue sirviendo REV-A aprobada con sello "Revisión A" — inmutable ✓.

## Recorrido 4 — compra — ✅ PASA (en vivo)

Versión de compra de P-000001: 14 líneas de requerimiento (6 vidrio en shortage, perfiles/hardware cubiertos por stock 500).
- `POST purchasing/suppliers/` → Vidriería Cordillera Ltda.; `versions/<v>/eligibilities/` → eligibility; `requirements/<id>/allocation/` ×6; `versions/<v>/confirm/` → PO-8A8ED6D3E02E DRAFT → `send/` → SENT.
- Recepción parcial `inventory/orders/<po>/receipts/` (5 líneas, 1 con dañado) → status **PARTIALLY_RECEIVED**, outstanding 4 unidades (dañado no cuenta como usable ✓).
- `purchasing/orders/<po>/cancel/` en PARTIALLY_RECEIVED → **CANCELLED**, liberó exactamente las 4 unidades no recibidas (received-damaged queda cubierto por el material físico).
- Re-compra: re-confirm → PO-95E658A7EC5D DRAFT con **exactamente 4 unidades** (sin duplicar lo recibido) → send → recepción total → **FULFILLED**. Cobertura final: `shortage=0` en las 6 líneas; stock glass muestra 4 piezas on-hand (dañada excluida).
- Conservación verificada: recibido usable = requerido; órdenes CANCELLED+FULFILLED coexisten como evidencia.

## Recorrido 5 — industria — ✅ PASA (en vivo)

OT-P-000001-REV-A-04 (RELEASED): CUT→WELD→CLEAN→GLAZE transiciones START/COMPLETE OK; **QC COMPLETE con `qc_result:FAIL`** → orden **HOLD**, QC BLOCKED, PACK rechazado `step_sequence_blocked` ✓.
- Remake: `POST orders/<id>/remake/` → **OT-…-04-RM-01** RELEASED con remake_reason; pasos bloqueados hasta `optimize/` (`work_order_plan_missing` — plan de corte requerido en remake ✓).
- Remake completo: optimize → 6 pasos DONE → QC PASS → PACK → `packing/` 201 + `labels/` (`-U01`, 13 piezas) → `dispatch/` → **DISPATCHED**.
- Orden original queda HOLD documentada. Guards: dispatch sobre orden incompleta → 422 `dispatch_requires_completed` (verificado con MGR).

## Recorrido 6 — CNC — ✅ PASA (en vivo)

- Fixture recreado: tools saw/drill/end_mill (kind enum correcto: SAW_BLADE/DRILL_BIT/END_MILL — el SKILL.md anterior decía MILLING, corregido), CNC-01 (full kinds+faces) y CNC-SAW (solo SAW_CUT/TOP_EDGE).
- Readiness OT-01 member P01-U01-M10 (HANDLE_PREP): **WARN `feature_point_only`** en CNC-01; **BLOCK `unsupported_kind`** en CNC-SAW.
- Generate en CNC-01 → programa `OT-P-000001-REV-A-01-P01U01M10-CNC-01-01` (WARN); generate en CNC-SAW → **422 `cnc_program_blocked`** con detalle físico.
- `manifest.json` descargado y **hash-verificado byte a byte** (sha256+bytes de operations.json/.csv coinciden). Botón UI de manifest verificado en fase 11 (`8216180`).

## Recorrido 7 — IA — ✅ PASA con nota (MOCK)

`ai_routes.provider='MOCK'` + `AI_GATEWAY_MOCK_ENABLED=1` (ambos procesos — el worker runjobs tenía conexión DB muerta tras el wipe; reiniciado → drena `job_runs`).
- Ask con refs → 200 con audit_id, créditos, respuesta contextual.
- Agent run → 202 QUEUED → SUCCEEDED (transcript con plan+reply); **replay mismo operation_key → mismo job_id** (idempotente); key reciclada+goal distinto → 409 `ai_operation_key_conflict`.
- Cancel en QUEUED → CANCELED; retry en terminal → 409 `ai_job_not_retryable`.
- OPERATOR/INSTALLER → 403 `documentary_permission_denied` (ai/agent y ask).
- ⚠️ **Defecto menor nuevo**: el job cancelado aparece en `/jobs` como "Fallido" con copia "El proveedor externo no respondió / ai_job_unclaimable" — la fila job_runs queda QUEUED tras el cancel y el worker la marca FAILED al drenarla. Copia engañosa para el usuario (fue cancelación suya, no fallo de proveedor). CORREGIBLE-EN-COLA.
- ⚠️ Razonamiento a nivel de modelo no ejercido (MOCK); la defensa de prompt contra instrucciones embebidas es estática (verificada en fase 12).

## Recorrido 8 — roles + aislamiento — ✅ PASA

- OPERATOR: write posición → 403 `pricing_permission_denied`; lectura de proyecto → 403 (OPERATOR es rol de piso: sin acceso comercial); ai agent → 403.
- INSTALLER: production orders read 200; ai → 403. WORKSHOP_MANAGER: orders 200; dispatch en HOLD → 422 `dispatch_requires_completed`. ESTIMATOR: project read 200.
- **Aislamiento 2 orgs**: creé Org B (`bbbbbbbb-…-b2`, user owner-b, rol ESTIMATOR). Con header B: projects [] y orders [] (listas vacías); `GET /projects/<P-000004>` → **404** `project_not_found` (no filtra existencia); compare de revisiones de A → 404. Token A con header org B → 403 `organization_access_denied`; token B con header A → 403 igual. ✓
- Portal público: acceso por token sin auth ✓ (ver recorrido 2).

## Revisión visual (route-map)

Capturas en este directorio: 1440×900 (`20-*`–`28-*`), 1280×800 (`30-*`), móvil iw=500 (`40-*`; el window manager piso es ~500px, se usa ancho 500 como proxy del breakpoint móvil — igual que fases 10/11).

- **Sin scroll horizontal** en 1440 ni 1280 en las 9 rutas principales.
- **🔴 `/purchasing` móvil**: `scrollWidth=693` — tablas del índice de órdenes (954px) y otra tabla de 535px sin wrapper de scroll interno. Misma clase de defecto que se corrigió en `.production-*` en fase 11. CORREGIBLE-EN-COLA.
- **🟡 `/assistant` móvil**: `scrollWidth=565` — el botón submit "Ejecutar" de `.aiws-composer` excede el viewport (composer no envuelve). CORREGIBLE-EN-COLA.
- `/production` móvil: limpio (485) — incluye el fix de fase 11 verificado.
- Dashboard/proyectos/clientes/settings/catálogos/jobs: orden visual correcto, jerarquía OK, estados vacíos con texto explicativo ("Requisitos congelados de la revisión…", "cola vacía por estación", filtros `?blocked`/`?shortage`), sin números partidos ni campos sin etiqueta detectados en las capturas.
- Studio: `50-studio-editor.png` (Dormitorio 1 TT-RIGHT), `51-studio-dock-open.png` (dock IA abierto sobre editor, bot presente), `53-studio-tilt-left.png` (Cocina TT-LEFT). Detalle físico de herrajes/bisagras/juntas cubierto exhaustivamente en fase 3 (captures/phase03) — sin regresión observada.
- Bot: orb visible en topbar (`.topbar-ai`) + dock con estados Preguntar/Agente — identidad verificada en fase 12 (`614e7d8`).

## Accesibilidad — ✅ mayormente OK

- Recorrido Tab real (CDP Input.dispatchKeyEvent) en `/projects`: skip-link "Saltar al contenido" primero → rail toggle → búsqueda (Ctrl K) → notificaciones → IA → "Crear proyecto" → filtros → enlaces de proyecto → dock IA. Orden lógico completo.
- **Indicador de foco visible en todos los elementos** (ring box-shadow 2px consistente — aunque `outline:none`, el ring lo suple).
- Foco en modal/retorno y errores anunciados: verificados en fases 10–12; no re-ejecutado íntegramente esta fase (cobertura parcial honesta).

## Rendimiento (laboratorio, dev-mode, método declarado)

Método: CDP `performance` nav timing + tiempo hasta contenido visible (poll de DOM/title), medidas únicas (no promediadas), localhost sin cache-busting salvo primer load.
- **Carga inicial** `/dashboard` (frío, cache limpio): documento 126ms, contenido visible ~3.5s, 95 recursos. Dev-mode Vite — producción sería bundle minificado + CDN, no comparable.
- **Editor de vano** (Studio): primer load ~18s (incluye init del visor/engine); warm ~3.0s.
- **Generación de documento** DOC-01 PDF (12 posiciones): 633ms primera emisión; re-generación (mismo contenido → artifact cache) 64ms.
- **Scroll 100 posiciones**: NO medido — la fixture de 100 posiciones se perdió en el wipe (P-000002 actual tiene 8). Cobertura previa en fase 5. PENDIENTE si se re-siembra.

## Hallazgos

| # | Severidad | Hallazgo | Estado |
|---|-----------|----------|--------|
| F14-1 | 🟡 | `HomeRedirect` consume `dk:returnTo` pero aterriza en /dashboard igualmente (fix `144b22c` ineficaz; 3/3 repro). Solo rompe en el caso borde (magic link cae en `/` por mismatch de origen) — el path normal `/auth/callback` sí funciona. | CORREGIBLE-EN-COLA (defensa en profundidad) |
| F14-2 | 🔴 | `/purchasing` móvil overflow: tablas sin wrapper scroll (sw 693 @ iw 500) | CORREGIBLE-EN-COLA |
| F14-3 | 🟡 | `/assistant` móvil overflow: botón Ejecutar del composer excede viewport (sw 565) | CORREGIBLE-EN-COLA |
| F14-4 | 🟡 | Job cancelado se muestra en `/jobs` como "Fallido / El proveedor externo no respondió" — copia engañosa para una cancelación de usuario | CORREGIBLE-EN-COLA |
| F14-5 | 🟢 | Pago online: `flow_not_configured` — integración Flow requiere credenciales en Ajustes | PENDIENTE-EXTERNO (config Flow + credenciales sandbox) |
| F14-6 | 🟢 | Scroll con 100 posiciones no medido (fixture wipé) | PENDIENTE (re-sembrar 100 posiciones) |
| F14-7 | 🟢 | Live-model AI (MiMo) no verificable — 429 quota; gauntlet estructural bajo MOCK | PENDIENTE-EXTERNO (credencial AI funcional) |
| F14-8 | 🟢 | OTP `otp_disabled` para scripts — usar password grant en tests | Nota de entorno |

## Lista de archivos

`00-returnto-root-consume.png` (F14-1), `10/11/12-*` (REV-B detail + portal + aprobado), `20-*` (1440), `30-*` (1280), `40-*` (móvil 500), `50/51/53-*` (Studio + dock IA).
