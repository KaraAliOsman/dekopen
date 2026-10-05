# Diagnóstico IA1 — arnés de evaluación por resultado

Este directorio mide la IA de DEKOPEN **por resultado, no por texto**: cada
caso carga un contexto fixture, envía el prompt por **la misma ruta que usa la
UI** (`design_assist.assist`, `agent._act`, `assist.ask`), aplica las
operaciones propuestas en un **sandbox** con el mismo reducer del canvas
(`applyDesignOps` de `frontend/src/features/canvas/designOps.ts`, vía Node +
esbuild, sin persistir nada) y compara la **estructura resultante** — medidas
exactas en mm, aperturas, SKU de vidrio — contra la expectativa del caso.

No arregla la IA: construye la vara para medirla. IA2 e IA3 corrigen contra
esta misma vara.

## Cómo correr

```bash
# Desde la raíz del repo (suite MOCK determinista, sin red ni credenciales):
make test-ai-evals PY=.venv/bin/python
# o directo:
python scripts/ai_evals.py --provider MOCK --out docs/ai/evals/<fecha>-mock.json

# Proveedor real configurado en el entorno
# (AI_GATEWAY_<P>_API_KEY + AI_GATEWAY_<P>_BASE_URL):
cd backend && python -m ai_gateway.evals.run --provider MIMO --out ../docs/ai/evals/<fecha>-mimo.json

# Todos los proveedores configurados + MOCK:
python scripts/ai_evals.py --provider auto --out docs/ai/evals/<fecha>.json
```

El comando **nunca bloquea**: los casos fallidos son el diagnóstico (exit 0);
sólo un error del propio arnés sale con código 1. CI corre la suite MOCK en el
job `AI Evals (MOCK, non-blocking)` (`continue-on-error: true`) y sube el JSON
como artefacto.

## Piezas

| Pieza | Archivo | Rol |
| --- | --- | --- |
| Runner | `backend/ai_gateway/evals/run.py` | CLI `--provider/--out/--cases-dir`, corre la suite, escribe el informe JSON |
| Rutas | `backend/ai_gateway/evals/harness.py` | `run_case` parchea sólo los bordes de I/O (gateway, context, catálogo, position_row, batch positions) y llama a la función real de cada ruta |
| Fixtures | `backend/ai_gateway/evals/fixtures.py` | Mundo DEMO_60: editor (posición vacía/dividida/oscilobatiente), proyecto VIVIENDA con 12 posiciones, proyecto cotizado (REV-A/REV-B), producción, OT con faltante, plan de compras, dashboard |
| Casos | `backend/ai_gateway/evals/cases/*.yaml` | 26 casos con prompt verbatim, expectativa y aserciones declarativas |
| Evaluación | `backend/ai_gateway/evals/expect.py` | Aserciones por resultado: `product` (estructura aplicada) + `behavior` (ops, pasos, artefactos, preguntas, texto citable). El check `batch` verifica cobertura, las ops por posición (`ops_each`) y el producto resultante de cada una (`product_each`, contra `sandbox.batch_results`) |
| Proyección | `backend/ai_gateway/evals/projection.py` | Aplana el producto (sobre `assembly` o bare tree) a módulos/bahías/splits con Decimal |
| Sandbox | `backend/ai_gateway/evals/sandbox.py` + `sandbox_apply_entry.ts` | Esbuild-bundla `applyDesignOps` real y la corre en Node — jamás una reimplementación en Python |
| Taxonomía | `backend/ai_gateway/evals/taxonomy.py` | Las 10 categorías del encargo, en árbol de decisión determinista |
| Broker | `harness.ProviderBroker` | Misma firma que `service.invoke` (audit/model/latencia/tokens) menos wallet/audit/replay |

### Taxonomía de fallos (árbol de decisión)

1. `proveedor_no_configurado` — la credencial/ruta no existe
   (`ai_provider_unavailable`, `ai_provider_mock_disabled`).
2. `proveedor_error` — el proveedor respondió error (`ai_provider_quota`,
   `ai_provider_auth`, `ai_provider_rejected`, timeout, …).
3. `formato_invalido` — salida no parseable / no conforme al contrato
   (`*_bad_output`).
4. `grounding_rechazo` — la capa de grounding rechazó números/referencias
   (`*_ungrounded`).
5. `contexto_insuficiente` — el caso declara `context_gap` (el dato no está
   en la proyección) o la ruta falló con `ai_context_*`.
6. `op_no_soportada` — el caso declara `op_gap` (el vocabulario no puede
   expresar la transformación pedida).
7. `op_rechazada_validador` — ops propuestas y todas rechazadas por el
   validador, sin ninguna aceptada.
8. `no_pidio_aclaracion` — el caso esperaba aclaración/sin-cambio y la ruta
   aplicó ops o respondió afirmativamente.
9. `accion_consecuente_ejecutada` — el caso marcado `expects_prepared_only`
   ejecutó una acción consecuente en vez de prepararla.
10. `resultado_incorrecto` — fallback: el resultado no coincide con lo
    esperado por otra razón.

Etiqueta fuera de la taxonomía: `error_arnes` — el propio arnés no pudo
medir (p.ej. el sandbox Node/esbuild no aplicó las ops). No cuenta como
fallo del modelo: el caso queda sin medir hasta que el arnés se repare.
Las comparaciones de medidas son exactas (tolerancia 0,00 mm, como el
motor) y las métricas de llamadas se reportan por caso, no acumuladas.

## Casos

| Id | Vista | Vía | Prompt | Espera |
| --- | --- | --- | --- | --- |
| E01–E13 | Editor | `design_assist` (E09/E10 por `agent`) | edición/pregunta sobre la posición | resultado estructural, aclaración o sin-dato |
| J01–J08 | Proyecto | `agent` (J04 por `ask`) | lote, alta, duplicado, precios, emisión, comparación | batch acotado, artefacto, prepare+deep link, faltantes exactos |
| F01–F03 | Producción/Compras | `agent` | OT bloqueadas, barras, plan de compra | lista exacta, número del plan de corte o sin-dato, artefacto purchase_plan |
| G01–G02 | General | `agent`/`ask` | precio aproximado, oscilobatiente vs abatible | sin invención / explicación correcta |

Las aserciones `expect` admiten grupos alternativos (`any:`): pasa el caso si
**un** grupo entero se cumple — p.ej. "el resultado correcto" **o** "pide
aclaración sin aplicar ops".

## Línea base — 2026-10-05

| Proveedor | Casos | Pasan | Fallos por taxonomía |
| --- | --- | --- | --- |
| MOCK | 26 | **0** | `resultado_incorrecto` 14 · `contexto_insuficiente` 7 · `op_no_soportada` 4 · `no_pidio_aclaracion` 1 |
| MIMO (configurado) | 26 | **0** | `proveedor_error` 26 (`ai_provider_quota`, HTTP 429) |

Artefactos: [`2026-10-05-mock.json`](./2026-10-05-mock.json) ·
[`2026-10-05-mimo.json`](./2026-10-05-mimo.json).

MOCK es el suelo: es un proveedor de eco determinista — ejercita todo el
circuito (ruta → validador → sandbox → evaluación → taxonomía) y sus fallos
muestran exactamente dónde se rompe el contrato por caso. La corrida MIMO
demuestra que la credencial configurada existe pero el proveedor rechaza toda
llamada con **429 — cuota agotada**: la IA real está caída en producción hoy.

## Cinco causas raíz (ordenadas por impacto)

### 1. El proveedor configurado responde 429 en el 100 % de las llamadas — toda superficie IA está caída

`backend/ai_gateway/providers.py:375-376` convierte HTTP 429 en
`ai_provider_quota` → `proveedor_error`. Evidencia:
`2026-10-05-mimo.json` — 26/26 casos con `error.code == "ai_provider_quota"`
y cero llamadas efectivas (la sonda directa repitió 429 durante >2 min, así
que es cuota, no rate-limit transitorio). Impacto: nada de lo demás importa
mientras el proveedor esté agotado — el Orb, el asistente del editor y el
agente devuelven error al usuario final **hoy**. Además: el endpoint vivo de
esta credencial es `https://token-plan-sgp.xiaomimimo.com/v1` con modelo
`mimo-v2.6-pro`; la migración `20261203000000_primalabs_mimo_pin.sql` pina
`primalabs-ai/MiMo-V2.6-Pro-RL`, que este endpoint rechaza con 400 y
`api.primalabs.ai` rechaza la clave con 401 — la ruta pineada y la credencial
real ya divergen.

### 2. `_summary` exige `product["modules"]` plano — toda op sobre una posición persistida muere con `unsupported_product`

`backend/projects/design_assist.py:103-115` devuelve `None` salvo que
`product["modules"]` sea una lista plana. El agente, en cambio, carga el
producto desde `parametric_tree` (`backend/ai_gateway/agent.py:688` lo hace
`SELECT`, `:761` lo lee con `_jsonb`), y ese árbol persistido **nunca** tiene
esa forma: es un IntentNode desnudo (posición de un módulo) o un sobre
`{version:"product-v2", assembly:{modules,couplings}}` (documentado en
`backend/ai_gateway/context.py:545-560`). Resultado: `_summary` → `None` →
`agent.py:762-766` rechaza cada posición con
`{"op":"batch_ops","reason":"position_N:unsupported_product"}`. Evidencia en
la corrida MOCK (J02): las **12** posiciones del fixture rechazadas así.
Impacto: el canal más valioso del agente — batch ops "todas las fijas a
abatible", "copia el vidrio al segundo piso" (J01–J03) — está estructuralmente
roto aunque el modelo emita el plan perfecto. El mismo gate opera en
`design_assist.assist` (`design_assist.py:943`) pero ahí el canvas envía el
producto plano en vivo, así que sólo la vía por proyecto está muerta.

### 3. El vocabulario de ops no expresa las transformaciones más pedidas

Las 18 ops de `design_assist` (`design_assist.py:55-74` las documenta) son
todas de ajuste sobre módulos existentes: no hay op para **dividir bahías**
(montante E01/E02/E13, travesaño E04), **crear/duplicar posiciones** (J02/J03)
ni **mover herrajes/manillas** (E08). Evidencia: 5 casos clasificados
`op_no_soportada` en el baseline MOCK. Agravante: `OPENINGS`
(`design_assist.py:23-29`) **sí** incluye `SLIDING_2L`, así que "conviértela
en corredera" (E07) produce una op que el validador acepta — la
incompatibilidad sistema/apertura es invisible para él — y el sandbox la
aplicó con éxito (`product_changed: true`): una acción confiadamente
incorrecta, peor que un rechazo.

### 4. Las proyecciones de contexto no exponen los datos que las preguntas requieren

El grounding funciona (la IA no puede inventar números), pero la proyección
no trae el dato y la única salida honesta es "sin dato": peso por hoja (E09 —
`_position` en `backend/ai_gateway/context.py:529+` proyecta
tipología/medidas/intent, no pesos del motor), bloqueos de validación (E10 —
la respuesta del motor no está en la proyección), precio por posición (J04 —
`_project` en `context.py:437+` sólo expone totales de proyecto), diff entre
revisiones (J08 — sólo `latest_version`), barras del plan de corte (F02 —
`_work_order` en `context.py:965+` sólo pasos/faltantes). Evidencia:
`contexto_insuficiente` ×7 en el baseline.

### 5. `_declared_values` no admite aritmética — las instrucciones relativas son imposibles y las literales absurdas pasan

`backend/projects/design_assist.py:280-313` declara sólo los números que el
usuario escribió (con conversión de unidad); el validador rechaza
`ancho_no_declarado` (`:835`, `:850`). "20 cm más ancha" (E11) exige emitir
**1700** — el modelo lo calcula bien, pero 1700 no está declarado → rechazo;
si emite 200 literal, `ancho_invalido` no lo cubre (200 mm sí está dentro del
rango) → el ancho queda en 200. Toda instrucción relativa ("la mitad", "al
doble", "200 mm más") es inalcanzable por diseño. Relacionado: el contrato de
`design_assist` no tiene canal de aclaración (`questions` no existe en su
salida — sólo `ops`/`rejected`/`notes`), así que E08 "manilla a 1050" jamás
podrá preguntar; el modelo sólo puede narrar en `notes` o no hacer nada.

## Limitaciones del arnés (honestas)

- Las llamadas son in-process a `design_assist.assist` / `agent._act` /
  `assist.ask` con los bordes de I/O parcheados — misma ruta y misma
  maquinaria de validación/grounding que la UI, pero sin HTTP, auth, wallet,
  auditoría ni persistencia de jobs (fuentes ortogonales de fallo, no de
  comportamiento de la IA).
- El estado del agente (`WAITING_FOR_USER`/`WAITING_FOR_APPROVAL`/
  `SUCCEEDED`) se reimplementa con la misma regla de 3 líneas de `agent.act`.
- Aserciones de texto ("lista las opciones", "explica la incompatibilidad")
  se evalúan por presencia de tokens sobre texto **nuevo** (el eco del prompt
  se elimina del corpus — un `¿...?` citado no es pedir aclaración).
- `design_assist` no expone preguntas estructuradas: la aclaración sólo puede
  detectarse vía `notes`.

## Referencia

- Encargo: `docs/cola/prompts/IA1-diagnostico-evals.md`.
- Tests del arnés: `backend/tests/test_ai_evals.py` (8 tests, sin DB ni red).
