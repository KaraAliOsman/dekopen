# Capturas ux:capture — después de P01

282 capturas · 1673 hallazgos totales · 1370 en superficies de producto
(303 corresponden a `/dev/ui/mal`, la página que viola la constitución
a propósito — sus hallazgos son esperados y demuestran que los
detectores funcionan; `/dev/ui` queda en 0).

## Delta vs `p01-antes` (2291 hallazgos)

- `contrast-aa`: ~356 → 0 en producto. Correcciones: tinta `-ink` sobre
  fondo `-soft` en chips de producción/estado, rampa semántica
  re-declarada por tema para `data-theme-scope`, alias `--theme-*`
  re-declarados en cada scope, `status-released` → `--info-ink`,
  «Cancelar orden» → `--person-ink`.
- `font-too-small`: 1194 → 216 (resto: etiquetas de 7 px en el lienzo
  técnico, deuda intencional registrada).
- `radius-too-big`, `emoji`, `bare-interactive`, `blur`, `exclamation`,
  `english-word`, `contrast-aa`: 0 en producto.
- `touch-too-small` (346), `console-error`/`http-error` (218 c/u),
  `enum-token` (168), `decimal-4plus` (104), `shadow-offscale` (54),
  `gradient` (34), `long-hex` (12): deuda preexistente documentada
  para P03+.

## Top 30 hallazgos de producto (por frecuencia)

| # | Tipo | Detalle | Ruta | Rol | Capturas |
|---|---|---|---|---|---|
| 1 | `console-error` | Failed to load resource: the server responded with a st | `jobs-operator` | operator | 48 |
| 2 | `console-error` | Failed to load resource: the server responded with a st | `production-operator` | operator | 40 |
| 3 | `console-error` | Failed to load resource: the server responded with a st | `dashboard-operator` | operator | 40 |
| 4 | `console-error` | Failed to load resource: the server responded with a st | `portal-revocada` | public | 16 |
| 5 | `http-error` | 410 http://127.0.0.1:5173/api/v1/portal/quotes/Hqx7WGZ- | `portal-revocada` | public | 16 |
| 6 | `console-error` | Failed to load resource: the server responded with a st | `portal-reemplazada` | public | 16 |
| 7 | `http-error` | 410 http://127.0.0.1:5173/api/v1/portal/quotes/OxKfLskJ | `portal-reemplazada` | public | 16 |
| 8 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/ask/?surface=produc | `production-operator` | operator | 16 |
| 9 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/jobs/ | `production-operator` | operator | 16 |
| 10 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/ask/?surface=produc | `dashboard-operator` | operator | 16 |
| 11 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/jobs/ | `dashboard-operator` | operator | 16 |
| 12 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/ask/?surface=jobs&r | `jobs-operator` | operator | 16 |
| 13 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/jobs/ | `jobs-operator` | operator | 16 |
| 14 | `http-error` | 403 http://127.0.0.1:5173/api/v1/jobs/?limit=100&offset | `jobs-operator` | operator | 16 |
| 15 | `console-error` | Failed to load resource: the server responded with a st | `jobs-installer` | installer | 16 |
| 16 | `http-error` | 403 http://127.0.0.1:5173/api/v1/jobs/?limit=100&offset | `jobs-installer` | installer | 16 |
| 17 | `console-error` | Failed to load resource: the server responded with a st | `settings-general` | owner | 12 |
| 18 | `http-error` | 500 http://127.0.0.1:5173/api/v1/organization/branding/ | `settings-general` | owner | 12 |
| 19 | `gradient` | div · VisualTécnica | `portal-vigente` | public | 8 |
| 20 | `gradient` | div · VisualTécnica | `portal-aprobada` | public | 8 |
| 21 | `gradient` | div · VisualTécnica | `portal-expirada` | public | 8 |
| 22 | `decimal-4plus` | 2.9344 | `production-manager` | manager | 8 |
| 23 | `decimal-4plus` | 2.9344 | `production-operator` | operator | 8 |
| 24 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/ask/?surface=work_o | `production-operator` | operator | 8 |
| 25 | `decimal-4plus` | 2.9344 | `dashboard-operator` | operator | 8 |
| 26 | `http-error` | 403 http://127.0.0.1:5173/api/v1/ai/ask/?surface=work_o | `dashboard-operator` | operator | 8 |
| 27 | `decimal-4plus` | 2.9344 | `production-installer` | installer | 8 |
| 28 | `console-error` | Failed to load resource: the server responded with a st | `project-borrador` | estimator | 6 |
| 29 | `http-error` | 403 http://127.0.0.1:5173/api/v1/projects/payment-integ | `project-borrador` | estimator | 6 |
| 30 | `console-error` | Failed to load resource: the server responded with a st | `project-cotizado` | estimator | 6 |
