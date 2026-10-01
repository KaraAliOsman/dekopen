# Fase 14 — Validación completa del producto y cierre con evidencia

## Problema inicial

DEKOPEN acumuló 14 fases de trabajo (00–13) sobre
`devin/1790335313-commercial-workspace`: modelo compositional, motor único de
números, workspace comercial, catálogo con autoridad, compras/inventario,
producción por estaciones, CNC con datos declarados, documentos sellados, bot
con identidad propia, landing/onboarding. La fase 14 valida el producto completo
en vivo contra el HEAD vigente, corrige regresiones y entrega una evaluación
honesta de lo que está listo.

## Preparación

- SHA inicial: `da24332` (branch `devin/1790335313-commercial-workspace`);
  el gauntlet en vivo corrió sobre el mismo contenido.
- Entorno: Supabase CLI stack `dekopen` (API :25321, DB :25322, Mailpit :25324),
  Django :8000 (`--noreload`), Vite :5173, worker `runjobs` con
  `AI_GATEWAY_MOCK_ENABLED=1`.
- Catálogo/fixtures: `DEMO_60` + fixtures sintéticos (cliente/proyecto/
  posiciones/pedidos/OTs); roles OWNER/ESTIMATOR/WORKSHOP_MANAGER/OPERATOR/
  INSTALLER + segunda organización aislada creada en vivo.
- Navegador: Chrome CDP :9333 (Playwright); viewports 1440×900, 1280×800, ~500px.
- CI re-consultada: PR #107 — 5/5 checks verdes en `da24332`.
- Incidente de entorno: el wipe de DB a mitad de corrida (por `make test-db`)
  destruyó la fixture; se reconstruyó (`dev_fixture.py` + TOTP owner) y todo lo
  reportado fue re-verificado sobre los datos reconstruidos.

## Recorridos obligatorios — resultado

Evidencia: `docs/redesign/captures/phase14/` (REPORT.md + capturas) y
`/home/ubuntu/phase14-docs/` (artefactos PDF/XLSX/JSON reales + rasters).

| # | Recorrido | Resultado |
|---|-----------|-----------|
| 1 | Cuenta nueva → onboarding → proyecto → posición → precio → cotización | ✅ PASA. Wizard completo verificado (fase 13, código sin cambios); emisión REV-A + DOC-01 verificada en vivo esta fase (P-000004, `COT-P-000004-REV-A`). |
| 2 | Venta 12 posiciones + extras + alternativa → portal → aprobación → pago | ✅ PASA, excepto pago online = **PENDIENTE-EXTERNO** (`flow_not_configured`; requiere credenciales Flow en Ajustes). Portal público con token, aprobación idempotente, registro manual de anticipo con receipt RC-0001, sobrepago rechazado. |
| 3 | Revisión nueva + docs inmutables + diferencias | ✅ PASA. Edición en emitida → 409 `revision_required`; successor REV-B con vidrio/tamaño modificados; `physical_stock_color_mismatch` bloqueó color sin stock (correcto); compare REV-A↔REV-B ambos `VERIFIED`, delta +$32.845, sin totales mixtos; portal sigue sirviendo REV-A sellada. |
| 4 | Compra → recepción parcial → cancelación/recompra → stock | ✅ PASA en vivo. Eligibility→allocations→confirm→send→recepción parcial con dañado (no cuenta usable) → cancel libera exactamente las 4 unidades pendientes → recompra trae exactamente esas 4 → FULFILLED, shortage=0, stock consistente. |
| 5 | Industria → estaciones → QC → rechazo/remake → embalaje → despacho | ✅ PASA. QC FAIL → HOLD + PACK bloqueado `step_sequence_blocked`; remake `OT-…-RM-01` requiere optimización antes de pasos; ciclo completo optimize→pasos→QC PASS→packing→labels→dispatch→DISPATCHED. Guardas de orden verificadas (422 `dispatch_requires_completed`). |
| 6 | CNC completa + incompatible bloqueada | ✅ PASA. Programa generado en CNC-01 con WARN `feature_point_only`; en CNC-SAW → 422 `cnc_program_blocked` con detalle; `manifest.json` hash-verificado byte a byte (sha256 coincide con operations.json/.csv). |
| 7 | IA: explicación, propuesta, aplicación, cancelación, reintento, contexto | ✅ PASA bajo MOCK (provider real = pendiente, F14-7). Ask con refs → 200 con audit; agent run → SUCCEEDED; replay mismo operation_key → mismo job (idempotente); key reciclada → 409; cancel → CANCELED; retry terminal → 409; OPERATOR/INSTALLER → 403. |
| 8 | Roles reales + cliente público + deep links + aislamiento 2 orgs | ✅ PASA. OPERATOR sin acceso comercial (403 write+read+AI), INSTALLER/WM/ESTIMATOR según capacidad; org B ve listas vacías y 404 (no filtra existencia); tokens cruzados → 403 `organization_access_denied`; portal público sin auth. |

## Revisión visual

Barrido de las 9 rutas principales a 1440×900 y 1280×800 sin scroll horizontal;
móvil ~500px: `/production` limpio (fix fase 11), `/purchasing` y `/assistant`
con overflow → **corregidos en esta fase y re-verificados en vivo**:

- F14-2 `/purchasing` @500px: `scrollWidth` 693 → **485** (tablas con scroll
  interno, sin overflow de página; captura `purch-iw500.png`).
- F14-3 `/assistant` @500px: `scrollWidth` 565 → **500** (composer envuelve).
- F14-1 magic link hacia `localhost:5173/auth/callback`: allow-list gotrue ya
  incluye localhost; verify real → **303 con access_token** (verificado en vivo).
- F14-4 copia de job cancelado: `ai_job_canceled`/`ai_job_unclaimable` ahora
  muestran "Trabajo cancelado" y el error de proveedor solo aparece en estados
  FAILED reales (`AssistantWorkspacePage`).

Dashboard/proyectos/clientes/settings/catálogos/jobs: jerarquía y estados
vacíos correctos, filtros `?blocked`/`?shortage` operativos. Studio con editor,
dock IA y orb presentes; tipologías TT-LEFT/RIGHT y físico de herrajes cubiertos
en fases 3/10/12 — sin regresión observada.

## Documentos

Familia documental regenerada completa sobre datos sellados reales —
**17 PDFs + 2 XLSX + labels JSON**, 100+ páginas rasterizadas a 110dpi con
auditoría de página vacía/mojibake (`phase14-doc-audit.py`):

- DOC-01 a 1, 3–4, 12 y **100 posiciones** (9 páginas, 48217B; totales
  neto+IVA=total internamente consistentes, agrupación 20 configs × 5 unidades).
- DOC-02/04/08 PDF + XLSX generados a través de un ciclo de compra real
  (eligibility→confirm→send→receive), no fixtures sueltos.
- DOC-03 (12p), DOC-05 (14p), DOC-06, DOC-07 (OWNER, emitido vía aal2 con TOTP
  real inscrito por gotrue factors API).
- Cut-pack ×2, prod-pack ×2 con bultos reales tras packing, guía GD-0001 sellada.
- **QR escaneados**: fingerprint PACK/CUTPACK `46fcdd209edec01c` idéntico en
  ambos documentos; labels de unidad decodifican a `DEKOPEN|<OT>|<label>|<pcs>`
  a ≥260dpi (resolución realista de impresión).
- **Grises**: familia casi monocromática — todas las páginas con tinta medible
  (243–18k px oscuros a 72dpi), ninguna página vacía.
- **XLSX**: ambos parseables, filas/celdas coherentes (12×104, 6×24).

## Fiabilidad, accesibilidad y rendimiento

### Gates del repo en el SHA de entrega

| Gate | Resultado |
|------|-----------|
| `make lint` (ruff + eslint + prettier + orval sync + source guards) | ✅ PASS |
| `make typecheck` (mypy + django check + tsc) | ✅ PASS |
| `make test` (engine + backend unit + vitest) | ✅ PASS — vitest 477/477 |
| `make build` (vite producción) | ✅ PASS |
| pgTAP | ✅ 921/921 en 68 archivos |
| Integración backend (DB real + RLS) | ✅ 266/266 |
| `make test-db` completo (pgTAP + RLS + auth e2e, stack limpio) | ✅ PASS |
| `make test-mutations` (drill 0.01mm) | ✅ 22/22 |
| CI PR #107 | ✅ 5/5 |

### Corregido durante fase 14

- pgTAP 070/123/133/136 vs contrato nuevo de `guard_order_evidence` — tests
  actualizados al contrato vigente (`81ee3e1`); `col_isnt_unique` ausente →
  consulta `pg_index` (`81ee3e1`); assertion de pricing obsoleta (`81ee3e1`);
  `--orb-spec`/mocks/anotaciones (`da24332`).
- F14-1: `additional_redirect_urls` gana `localhost:5173/auth/callback`
  (`supabase/config.toml`) + defensa en profundidad `HomeRedirect` — verificado
  con verify real 303.
- F14-2: overflow-x + min-widths en tablas de `/purchasing` — verificado 485px.
- F14-3: `.aiws-composer` flex-wrap — verificado 500px sin overflow.
- F14-4: mapeo `ai_job_canceled`/`ai_job_unclaimable` → "Trabajo cancelado";
  copia de proveedor solo en FAILED/FAILED_RETRYABLE.

### Teclado / accesibilidad

Recorrido Tab real (CDP) en `/projects`: skip-link primero → rail → búsqueda →
notificaciones → IA → CTA → filtros → enlaces — orden lógico completo, indicador
de foco visible en todos los elementos. Foco en modales/retorno/errores
anunciados verificados en fases 10–12. **Sin certificación WCAG** — no se corrió
scanner formal.

### Rendimiento (laboratorio, método declarado, medidas únicas)

- Carga `/dashboard` frío (dev-mode Vite, no comparable a producción):
  documento 126ms, contenido ~3.5s, 95 recursos.
- Editor Studio: ~18s primer load (init engine+visor), ~3.0s warm.
- DOC-01 12 posiciones: 633ms primera emisión, 64ms regeneración (cache de
  artifact por contenido).
- Scroll proyecto 100 posiciones (P-000005, recreado post-wipe): página 12.6k px
  con thumbnails reales, scroll programático completo ~2.2s, sin overflow
  (sw=1425 @1440).
- No se inventaron percentiles de usuarios — solo mediciones de laboratorio.

## Limitaciones y externos pendientes

- **Pago online (F14-5)**: `flow_not_configured` — requiere credenciales Flow
  sandbox en Ajustes. Flujo manual de cobranza sí funciona (anticipo, receipt,
  balance).
- **Proveedor AI real (F14-7)**: MiMo responde 429 (cuota); todo el gauntlet AI
  corrió bajo provider MOCK. Defensa anti-inyección verificada estáticamente
  (regla `UNTRUSTED_DATA_RULE` en system prompts), no en vivo con modelo real.
- **Validación física de máquina**: programas CNC verificados por hash/formato;
  ningún programa se declara listo sin validación en máquina real (UNVERIFIED).
- **Escenario Cancel-RUNNING bajo latencia real** y foco-modal completo: cubierto
  parcialmente en fases previas, no re-ejecutado íntegramente.
- Diferido por mandato: §12-2 A–F escenarios largos de negocio, compilador de
  catálogo 2.0 (98), 3D sync (99), photo-match (100), E2E A–K (102).

## Registro consolidado de hallazgos

`docs/redesign/phase14-findings-registry.md` — ~300 hallazgos de todas las
reviews y fases, con estado por hallazgo (resuelto con commit / ya corregido y
revalidado / no reproducido / pendiente con razón). F14-1..8 incluidos.

## SHA final

`da24332` + fixes de fase 14 sobre `devin/1790335313-commercial-workspace`
(SHA exacto en el último commit de la rama y en el PR #107).
