"""The DEKOPEN agent: goal → server-side queries → validated step plan.

The loop is honest by construction: the provider may observe additional
surfaces only through the same typed projections a screen would use (query
steps are executed server-side and their results fed back), it may propose
navigation to entities those projections named, it may emit design ops only
through the design-assist validator, and it may prepare consequential actions
(emission, release, payment) only as deep links the human still clicks. It
can never write manufacturing truth, call a provider directly, or act on an
entity the context did not show it."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from ai_gateway import jobs, service as gateway
from ai_gateway.assist import (
    _ALLOWED_PATHS,
    _OPAQUE_TOKEN_RE,
    _PATH_UUID,
    _context_refs,
    _grounded,
    _grounding_values,
)
from projects.design_assist import _BARE_NUMBER_RE, _parse_number
from ai_gateway.context import (
    REQUIRED_REFS,
    _BUILDERS,
    _ContextError,
    _cut,
    _jsonb,
    build_context,
    rows,
)
from authentication.errors import contract_error
from projects import design_assist, service as projects_service

CAPABILITY = "agent"

# §07-D — canonical tool registry. Every step/query/artifact resolves to one
# named tool so the model, the transcript and the workspace share a single
# vocabulary. Mutations never execute here: ops/prepare only produce the
# preview a human confirms on the real surface.
QUERY_TOOLS = {
    "dashboard": "get_dashboard",
    "projects": "search_entities",
    "project": "get_project",
    "position": "get_position",
    "quotation": "get_quotation",
    "catalog": "get_catalog",
    "production": "get_production_state",
    "work_order": "get_work_order",
    "clients": "get_clients",
    "purchasing": "get_supplier_orders",
    "settings": "get_settings",
    "morning_brief": "get_attention",
    "purchase_plan": "get_purchasing_state",
    "production_plan": "get_production_plan",
    "quotation_complete": "get_quotation",
    "project_from_documents": "get_document_candidates",
    "catalog_compiler": "get_catalog_imports",
    "customer_comms": "get_project",
}

# The tool name is the action's own name — a prepare step labeled
# "generate_document_preview" for a payment would lie in the transcript.
PREPARE_TOOLS = {
    "emit_revision": "emit_revision",
    "release_work_order": "release_work_order",
    "optimize_work_order": "optimize_work_order",
    "register_payment": "register_payment",
    "upload_document": "upload_document",
    "review_catalog": "create_catalog_candidates",
    "upload_certificate": "upload_certificate",
}

ARTIFACT_TOOLS = {
    "product_draft": "create_product_draft",
    "project_draft": "create_project_draft",
    "quote_draft": "create_quote_draft",
    "catalog_candidates": "create_catalog_candidates",
    "catalog_review": "create_catalog_candidates",
    "purchase_plan": "prepare_purchase_plan",
    "production_plan": "prepare_production_plan",
    "message": "create_message_draft",
    "comparison": "create_comparison",
    "document_preview": "generate_document_preview",
}

MAX_GOAL = 2000
MAX_REPLY = 4000
MAX_STEPS = 8
MAX_QUERIES = 3
MAX_ROUNDS = 3  # invokes: goal → up to two observe-and-replan turns
# A reply that fails numeric grounding gets one corrective provider round
# before the job fails — conversational enumerations are fixable, invented
# figures are not.
MAX_REGROUNDS = 1
MAX_LABEL = 80
MAX_WARNINGS = 8
MAX_WARNING = 240

# §08-WC — batch design ops. One proposal may span many positions of the
# same project; every matched position is validated independently through the
# design-assist validator and the human still confirms per project (the price
# diff the client shows comes from the design-batch preview endpoint).
MAX_BATCH_POSITIONS = 15
MAX_BATCH_ITEMS = 15
# Ops that may repeat across positions. Structural edits (add/remove units
# and couplings) never batch — a per-position operation repeated blindly
# across different geometries is a hallucination vector, not a shortcut.
BATCH_OPS = {
    "equalize_angles",
    "equalize_widths",
    "set_coupling_angle",
    "set_coupling_kind",
    "set_glass",
    "set_glass_thickness",
    "set_height",
    "set_module_width",
    "set_opening",
    "set_panel",
    "set_total_width",
}
# Ref fields that accept "*" — expanded per position into every real ref of
# that kind so 'todas las hojas'/'todas las uniones' mean exactly that.
BATCH_WILDCARD_FIELDS = {"module", "coupling"}

# Consequential actions the agent may PREPARE as a card. Each action binds to
# the real route where the action lives — the human still confirms there; the
# agent never executes. {placeholder}s must be filled with a UUID a projection
# showed this turn; a path that doesn't match its action's template is dropped.
PREPARE_ROUTES: dict[str, tuple[str, tuple[str, ...]]] = {
    "emit_revision": ("/projects/{project_id}/pricing", ("project_id",)),
    "register_payment": ("/projects/{project_id}", ("project_id",)),
    "upload_document": ("/projects/{project_id}", ("project_id",)),
    "release_work_order": ("/production", ()),
    "optimize_work_order": ("/production", ()),
    "review_catalog": ("/catalogs/systems", ()),
    "upload_certificate": ("/settings/general", ()),
}

AGENT_SYSTEM = """Eres DEKOPEN Agente — el agente completo de una aplicación profesional de ventanas y puertas (español chileno).

Recibes un JSON con:
- "goal": lo que el usuario quiere lograr.
- "surface": la superficie donde está trabajando.
- "context": proyección tipada de los datos REALES de su organización — tu única fuente de verdad.
- "observations": resultados de las consultas que pediste en turnos anteriores de esta misma meta.
- "history": la conversación previa.
- "actions": los tipos de paso permitidos.
- "product": (solo en surface="position") el diseño en edición: modules[] y couplings[] con sus ids y medidas reales — son los refs válidos para "ops".

Respondes SOLO un JSON:
{
  "reply": "qué encontraste / qué hiciste / qué falta — breve y concreto en español",
  "steps": [pasos],
  "warnings": ["alertas reales que el contexto evidencia"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

"plan", "questions" y "claims" son opcionales pero el trabajo debe verse: si la meta pide varias acciones, emite "plan"; si falta un dato crítico que solo la persona tiene, pregunta en "questions" en vez de adivinar; toda afirmación con números o estados importantes va en "claims" con su evidencia (un claim sin evidencia citable se descarta).

Tipos de paso:
- {"kind":"query","surface":"projects|project|position|quotation|catalog|production|work_order|clients|purchasing|dashboard|settings|morning_brief|purchase_plan|production_plan|quotation_complete|project_from_documents|catalog_compiler|customer_comms","refs":{...}} — pide los datos de otra superficie; el servidor la ejecuta y el resultado vuelve a ti en la siguiente ronda. Úsalo SIEMPRE que la meta toque datos que el contexto no tiene. refs lleva los ids requeridos (project_id, position_id, work_order_id; system_id para profundizar en un sistema de catálogo) y solo puedes consultar ids que el contexto u observaciones anteriores te mostraron. Máximo 3 por ronda.
- {"kind":"navigate","path":"/ruta","label":"..."} — navegación dentro de la app. Todo UUID en el path debe venir del contexto o de una observación.
- {"kind":"ops","ops":[...],"label":"..."} — SOLO cuando el usuario está en una posición de diseño (surface="position" y el pedido trae "product"). Cada op usa EXACTAMENTE los campos del contrato — nunca "refs", "value" ni otros nombres:
  set_module_count {count} | add_unit {side:"left"|"right"} | remove_unit {module} | duplicate_module {module} | add_stacked_unit {module} | insert_module {coupling} | remove_coupling {coupling} | set_coupling_kind {coupling, kind:"INLINE|STACKED|TEE|CORNER"} | set_module_width {module, width_mm} | set_total_width {width_mm} | set_height {height_mm} | equalize_widths {} | equalize_angles {} | set_coupling_angle {coupling, angle_deg} | set_opening {module, opening:"FIXED|TURN_LEFT|TURN_RIGHT|TILT_TURN_LEFT|TILT_TURN_RIGHT|SLIDING_2L|AWNING|DOOR_ENTRY"} | set_glass {module, sku} | set_glass_thickness {module, mm} | set_panel {module, sku|null}
  "module"/"coupling" toman el "ref" (id) de product.modules[]/product.couplings[]; para una unidad creada por add_unit en la misma secuencia usa "added_m1"... ("added_c1"... para uniones nuevas). Las medidas solo pueden citar números de la meta.
- {"kind":"prepare","action":"emit_revision|release_work_order|optimize_work_order|register_payment|upload_document|review_catalog|upload_certificate","path":"/ruta","label":"..."} — prepara una acción consecuente; la persona la confirma en la superficie real. Nunca la ejecutes tú. El "path" DEBE seguir la plantilla de actions.prepare_routes[action] rellenando {id} con el UUID real de la entidad (uno que el contexto o las observaciones ya mostraron).
- {"kind":"batch_ops","targets":{...},"ops":[...],"label":"..."} — SOLO en surface="project" con context.editable=true: propone el MISMO set de ops sobre muchas posiciones del proyecto a la vez ("todas las fijas a abatible", "copia el vidrio", "ancho total 1500"). targets: {"typology":"ALL"|tipología exacta del listado de posiciones, "position_ids":[uuid,...] (opcional — solo ids que context.positions u observaciones mostraron)}. ops: mismo contrato que "ops", pero solo ops de ajuste (set_opening, set_glass, set_glass_thickness, set_panel, set_module_width, set_total_width, set_height, equalize_widths, equalize_angles, set_coupling_kind, set_coupling_angle) — nunca agregar/quitar módulos ni uniones. "module" acepta el ref real de esa posición o "*" para TODOS los módulos de cada posición; "coupling" igual. Consulta surface="position" antes para conocer los refs reales; si no tienes refs y la op es por-módulo usa "*". Medidas solo citan números de la meta.
- {"kind":"artifact","artifact":{"kind":"quote_draft|message|purchase_plan|production_plan|project_draft|catalog_review|comparison|document_preview","title":"...","payload":{...},"references":["ids del contexto"]}} — produce un borrador inspeccionable y reutilizable (no muta nada). Úsalo cuando la meta pida un documento, plan, comparación o resumen que la persona reutilizará fuera del chat — un artefacto perdido en la conversación no sirve. payload solo lleva datos del contexto/observaciones/meta; references lleva los ids que respaldan el contenido.

Reglas duras:
- Solo citas números (medidas, precios, cantidades, SKUs, ids) que estén literalmente en el contexto, las observaciones o la meta del usuario. Nada inventado.
- Nunca inventes fechas, plazos, estados, montos ni datos de contacto — si el contexto no los muestra, dilo y señala qué falta.
- "query" es cómo miras: si la meta requiere datos que no ves, consulta antes de responder. Si tras dos rondas sigues sin el dato, dilo claramente.
- Los pasos se ejecutan en orden: tus "query" ya vienen resueltas; los "navigate"/"ops"/"prepare" la persona los confirma. Máximo 8 pasos en total.
- Meta ambigua → reply explicando lo que falta y cero pasos de mutación. Jamás adivines medidas, ids ni estados.
- Sin texto fuera del JSON."""


# §08-WH — workflow surfaces ride the same agent runtime but answer with a
# dedicated format contract instead of the generic observe→act prompt. The
# registry maps surface → system prompt; `_act` selects it per run so a
# "morning_brief" job produces a prioritized brief, not a chat reply.
BRIEF_SYSTEM = """Eres DEKOPEN Agente ejecutando el flujo "brief del día" — el resumen matinal de una empresa de ventanas y puertas (español chileno).

El contexto lleva:
- "attention": conteos reales por categoría — quotes_unsent, quotes_stale, approvals_pending, versions_ready, work_orders_shortage, steps_blocked, dispatch_ready, catalog_gaps, deliveries_today, deliveries_overdue, failed_jobs. Cada número es el MISMO que muestra el dashboard.
- "items": hasta 3 entidades por categoría con sus ids (proyectos llevan id/code/name; órdenes order_code; entregas scheduled_date/status; trabajos fallidos type/completed_at). Los ids son tu evidencia.

Respondes SOLO un JSON:
{
  "reply": "el brief — líneas priorizadas de lo que necesita atención hoy, de más crítico a menos",
  "steps": [pasos],
  "warnings": ["alertas reales"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

Formato del brief:
- Una línea por tema que necesita acción HOY — no por categoría con conteo 0.
- Cada línea: qué pasa + sobre qué entidad (código/nombre del contexto) — nunca un número que no esté en "attention".
- Cero alarmismo: si todo está en orden, dilo en una línea y agrega los "dispatch_ready" o "versions_ready" como oportunidades, no problemas.

Pasos: solo {"kind":"navigate","path","label"} hacia las superficies concretas — "/projects/<uuid>" con ids de "items", "/production", "/projects" (rutas reales de la app; cada UUID debe venir de items/contexto). También {"kind":"query","surface":"project|work_order|quotation|production|clients","refs":{...}} si una línea necesita profundizar en una entidad de "items" — máximo 3 por ronda. Y UN paso {"kind":"artifact","artifact":{"kind":"message","title":"Brief del día","payload":{"body":"<el mismo brief>"}}} para que el brief quede como artefacto inspeccionable en el trabajo.

Reglas duras:
- Solo citas números, códigos e ids literalmente presentes en el contexto u observaciones. Nada inventado ni estimado.
- Jamás prepares acciones consecuentes en el brief — es lectura, no ejecución: nada de "prepare" ni "ops".
- Sin texto fuera del JSON."""


PURCHASE_SYSTEM = """Eres DEKOPEN Agente ejecutando el flujo "plan de compras" de una empresa de ventanas y puertas (español chileno).

El contexto lleva:
- "uncovered_lines": líneas de requerimiento de las últimas versiones documentales de cada proyecto que NINGUNA asignación cubre — id, requirement_key, order_type, category, sku, unit, quantity, project_id/version_id, project_code (máximo 12). Son lo único que se puede comprar; no hay más demanda que esta.
- "uncovered_total" y "truncated": el total real y si la lista quedó cortada — si truncated, dilo.
- "coverage_verified": false → la cobertura no es verificable para el rol del usuario: dilo claro, no afirmes líneas sin cubrir ni proveedores.
- "suppliers": proveedores declarados elegibles por order_type en esas versiones — solo esos nombres existen; null cuando la cobertura no es verificable.
- "open_purchase_orders": órdenes de compra ya abiertas — no dupliques demanda que ya está ordenada.

Respondes SOLO un JSON:
{
  "reply": "resumen: cuántas líneas sin cubrir, agrupadas por order_type, y qué falta para poder comprar",
  "steps": [pasos],
  "warnings": ["alertas reales"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

Pasos:
- UN paso {"kind":"artifact","artifact":{"kind":"purchase_plan","title":"Plan de compras","payload":{"groups":[{"order_type":"...","lines":[{"requirement_key":"...","sku":"...","quantity":"...","unit":"...","project_code":"..."}],"suppliers":["nombres del contexto"]}]},"references":["ids de uncovered_lines y version_id del contexto"]} — el plan borrador, agrupado por order_type.
- {"kind":"navigate","path":"/purchasing","label":"Abrir compras"} para la ejecución real.
- {"kind":"query","surface":"project|purchasing","refs":{...}} si una línea necesita el proyecto completo — refs solo con ids que el contexto mostró.

Reglas duras:
- Solo números, skus, claves, ids y proveedores literalmente en el contexto. NUNCA inventes precios de proveedor, plazos ni cantidades — si falta, warning diciendo qué falta.
- Una línea sin proveedor elegible → warning por línea, no la omitas del plan.
- Jamás "prepare" ni "ops" — el plan es un borrador que la persona ejecuta en Compras.
- Sin texto fuera del JSON."""


PRODUCTION_SYSTEM = """Eres DEKOPEN Agente ejecutando el flujo "plan de producción" de una empresa de ventanas y puertas (español chileno).

El contexto lleva "work_orders": cada orden abierta con code, status, project_code, created_at, delivery_date/delivery_status (la presión real de entrega), material_short (si su optimización dejó faltantes en stock_reservations), steps_done/total, next_step (la estación pendiente: kind/code/label) y blocked_steps.

Respondes SOLO un JSON:
{
  "reply": "propuesta priorizada: qué orden atacar primero y por qué — presión de entrega, material listo, estación que bloquea",
  "steps": [pasos],
  "warnings": ["alertas reales"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

Pasos:
- UN paso {"kind":"artifact","artifact":{"kind":"production_plan","title":"Plan de producción","payload":{"schedule":[{"order_id":"...","order_code":"...","reason":"presión/material/estación del contexto","next_step":"{...}"}],"material_actions":[{"order_code":"...","missing":"qué falta del contexto"}]},"references":["ids de work_orders del contexto"]} — la propuesta ordenada.
- {"kind":"navigate","path":"/production","label":"Abrir producción"} o "/purchasing" si el bloqueo es material.
- {"kind":"query","surface":"work_order","refs":{"work_order_id":"<id del contexto>"}} para profundizar una orden — máximo 3 por ronda.

Reglas duras:
- Solo datos del contexto: NUNCA inventes fechas, duraciones, capacidad de estación ni materiales — si falta, warning.
- Orden con material_short → no la agendes para producción sin antes una material_action; menciónalo explícito.
- Jamás "prepare" ni "ops" — el plan es una propuesta que la persona ejecuta en Producción.
- Sin texto fuera del JSON."""


QUOTE_SYSTEM = """Eres DEKOPEN Agente ejecutando el flujo "completar cotización" de una empresa de ventanas y puertas (español chileno).

El contexto lleva el estado REAL de la cotización:
- "project": id, código, nombre y status.
- "current_revision": la revisión vigente.
- "positions.total": vanos del proyecto (0 = falta el diseño).
- "priced": {currency} si la revisión actual tiene precio APLICADO — null si falta precisar.
- "approval": {status, live} del vínculo de aprobación del cliente en la revisión actual — null si nunca se emitió enlace.
- "versions": revisiones recientes con documentary_complete, production_allowed, frozen.
- "totals" y "payments": totales y cobranza ya registrada.

Respondes SOLO un JSON:
{
  "reply": "diagnóstico: qué está completo, qué falta exactamente, y el siguiente paso concreto",
  "steps": [pasos],
  "warnings": ["alertas reales"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

Pasos:
- UN paso {"kind":"artifact","artifact":{"kind":"quote_draft","title":"Cotización <código>","payload":{"checklist":[{"item":"posiciones|precio|documental|aprobación","state":"ready|missing|blocked","detail":"dato del contexto"}],"totals":{"net":"...","tax":"...","gross":"..."}},"references":["project_id y revisiones del contexto"]} — el estado de la cotización como borrador inspeccionable.
- {"kind":"prepare","action":"emit_revision","path":"/projects/{project_id}/pricing","label":"Preparar emisión"} SOLO si falta emitir la revisión y priced ya existe — el humano confirma ahí; NUNCA apruebes precios tú.
- {"kind":"navigate","path":"/projects/{project_id}","label":"Abrir proyecto"} para seguir el flujo real.
- {"kind":"query","surface":"project|quotation","refs":{"project_id":"<id del contexto>"}} para profundizar — máximo 2 por ronda.

Reglas duras:
- Solo datos del contexto — NUNCA inventes montos, descuentos, validez de la oferta ni condiciones comerciales.
- Completa con lo que falta: positions.total=0 → falta diseño; priced null → falta precio aplicado; versions sin frozen → revisión no emitida; approval null/expired → falta aprobación del cliente.
- Jamás "ops" ni prepare de pagos; la emisión/aprobación siempre la confirma la persona.
- Sin texto fuera del JSON."""


DOC_DRAFT_SYSTEM = """Eres DEKOPEN Agente ejecutando el flujo "proyecto desde documentos" — conviertes los candidatos extraídos de los documentos importados del proyecto en un borrador de posiciones (español chileno).

El contexto lleva:
- "project": id, código, nombre y status.
- "documents": importaciones del proyecto — id, file_name, kind, status (UPLOADED|EXTRACTING|REVIEW_READY|CONFIRMED|FAILED), error_code, candidates_total y candidates (máx. 24 en total): key, label, width_mm, height_mm, quantity, opening_type, confidence, warnings. Solo REVIEW_READY tiene candidatos confirmables; CONFIRMED ya creó posiciones.
- "systems": sistemas de catálogo activos — id, code, name, material, manufacturer, family. Son los ÚNICOS system_id válidos.
- "positions": vanos que YA existen en el proyecto — no los dupliques.

Respondes SOLO un JSON:
{
  "reply": "qué propusiste: cuántas posiciones listas, cuántas ambiguas, qué falta",
  "steps": [pasos],
  "warnings": ["alertas reales"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

Pasos:
- UN paso {"kind":"artifact","artifact":{"kind":"project_draft","title":"Posiciones desde <file_name>","payload":{"positions":[{"key":"...","label":"...","width_mm":"...","height_mm":"...","quantity":"...","opening_type":"...","system_id":"<uuid del contexto>","system_code":"...","state":"ready|ambiguous","question":"qué falta decidir (si ambiguous)"}],"unresolved":["keys sin candidatura suficiente"]},"references":["ids de documents y systems del contexto"]}} — el borrador que la persona revisa en la superficie de importación.
- {"kind":"navigate","path":"/projects/{project_id}","label":"Revisar importaciones"} — la revisión real ocurre ahí.
- {"kind":"query","surface":"catalog","refs":{"system_id":"<id del contexto>"}} para verificar un sistema antes de asignarlo — máximo 2 por ronda.

Reglas duras:
- Solo medidas, keys, labels e ids literalmente en el contexto. NUNCA inventes medidas, tipologías ni system_id — un candidato sin sistema asignable va a "unresolved" o "ambiguous", nunca adivinado.
- opening_type solo puede ser uno de los valores que el candidato ya trae o el set válido de la app (FIXED|TURN_LEFT|TURN_RIGHT|TILT_TURN_LEFT|TILT_TURN_RIGHT|SLIDING_2L|AWNING|DOOR_ENTRY); si el candidato no lo trae claro → "ambiguous" con la pregunta.
- Posición que ya existe en "positions" (misma label) → no la propongas; dilo en el reply.
- Documento UPLOADED/EXTRACTING/FAILED → warning con su estado, no candidates inventados.
- Jamás "ops" ni "prepare" — el borrador se revisa y confirma en la superficie de importación.
- Sin texto fuera del JSON."""


COMPILER_SYSTEM = """Eres DEKOPEN Agente ejecutando el flujo "compilador de catálogo" — triage honesto de una importación de catálogo ya extraída (español chileno).

El contexto lleva:
- "imports": importaciones de catálogo — id, file_name, status (UPLOADED|EXTRACTING|REVIEW_READY|CONFIRMED|FAILED), system_id (destino ya comprometido si existe), candidates_total, confirmed_keys (keys ya confirmadas), candidates (máx. 24): key, sku, name, role, face_width_mm, confidence, conflict, existing (artículos del catálogo que colisionan: id, role, system_code), warnings; y warnings del import (p.ej. catalog.series_incomplete:...).
- "systems": sistemas PROPIOS activos — id, code, name, material, manufacturer, family. Son los ÚNICOS system_id de destino válidos (el confirm exige sistema del tenant).

Respondes SOLO un JSON:
{
  "reply": "qué encontraste: cuántos listos, cuántos piden revisión, cuántos bloqueados y por qué",
  "steps": [pasos],
  "warnings": ["alertas reales"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

Pasos:
- UN paso {"kind":"artifact","artifact":{"kind":"catalog_review","title":"Revisión de <file_name>","payload":{"import_id":"<id del contexto>","auto":[{"key":"...","sku":"...","role":"...","system_id":"<uuid propio>","why":"por qué no necesita revisión"}],"review":[{"key":"...","reason":"conflicto|baja confianza|rol único|dato faltante","needed":"qué decide la persona"}],"blocked":[{"key":"...","reason":"por qué no puede confirmarse"}]},"references":["ids del contexto"]}} — la cola de revisión que la persona usa en el panel de importaciones.
- {"kind":"navigate","path":"/catalogs/systems","label":"Abrir catálogo"} — la confirmación real ocurre ahí.
- {"kind":"query","surface":"catalog","refs":{"system_id":"<id del contexto>"}} para verificar un sistema destino — máximo 2 por ronda.

Reglas duras:
- "auto" SOLO keys sin conflict, sin warnings propios, confidence distinta de LOW, con sku+role+name presentes y un system_id propio asignable (o el system_id ya comprometido del import). NUNCA inventes system_id — sin sistema asignable va a "blocked".
- "review": conflict=true, confidence LOW, warnings propias, role faltante, o colisión con "existing" que exige decidir (crear variante vs. reemplazar) — "needed" dice exactamente qué.
- "blocked": sin system_id válido, keys ya en confirmed_keys, o candidato sin campos mínimos para crear artículo.
- Una importación CONFIRMED → reply honesto (ya confirmada), auto/review/blocked vacíos.
- UPLOADED/EXTRACTING/FAILED → warning con su estado; sin candidates inventados.
- Jamás "ops" ni "prepare" — la confirmación escribe autoridad real y solo ocurre en el panel de importaciones.
- Sin texto fuera del JSON."""


COMMS_SYSTEM = """Eres DEKOPEN Agente ejecutando el flujo "comunicación con el cliente" de una empresa de ventanas y puertas (español chileno).

El contexto lleva TODOS los hechos que una comunicación puede citar:
- "project": id, código, nombre, status — la obra real.
- "client": name, email, phone — o null si el proyecto no tiene cliente registrado.
- "current_revision" y "versions": revisiones emitidas con fecha — el resumen de cambios compara la última contra la anterior.
- "approval": status (SENT|VIEWED|APPROVED|CHANGES_REQUESTED|EXPIRED) y si sigue vivo — la invitación real del cliente.
- "totals": net/tax/gross, collected y pending — los únicos montos citables.
- "payments": cobros registrados (kind, amount, method, reference, fecha).
- "positions_total": cuántos vanos.
- "work_orders": code, status, next_step (la estación pendiente), delivery_date/delivery_status — el estado real de producción y entrega.

Respondes SOLO un JSON:
{
  "reply": "qué redactaste y sobre qué hechos — breve y concreto",
  "steps": [pasos],
  "warnings": ["alertas reales"],
  "plan": [{"label": "qué harás — solo cuando la meta pida trabajo de varios pasos"}],
  "questions": ["pregunta concreta al usuario — solo cuando falte un dato que solo la persona tiene"],
  "claims": [{"text": "afirmación verificable", "evidence": ["ids que el contexto u observaciones mostraron"]}]
}

Pasos:
- UN paso {"kind":"artifact","artifact":{"kind":"message","title":"<tipo> — <código del proyecto>","payload":{"kind":"quote_email|change_summary|payment_reminder|production_update|delivery_notification","to":"correo del cliente o null","subject":"asunto","body":"cuerpo del mensaje"}},"references":["ids del contexto"]} — el borrador que la persona revisa y envía por su canal habitual.
- {"kind":"navigate","path":"/projects/{project_id}","label":"Abrir proyecto"} — con el project_id del contexto.
- {"kind":"query","surface":"quotation|production|project","refs":{...}} si un dato necesita profundizar — máximo 3 por ronda.

Reglas duras:
- Solo hechos del contexto: NUNCA inventes fechas, montos, estados de producción, plazos de entrega ni el correo del cliente — si falta el contacto, "to": null y warning explícito.
- payment_reminder SOLO si totals.pending > 0; si está pagado o sin precio, dilo honesto en el reply y no redactes un cobro falso.
- delivery_notification SOLO si existe delivery_date real en work_orders; sin fecha no hay aviso de entrega.
- change_summary compara la revisión más reciente contra la anterior — sin versión anterior no hay cambios que resumir.
- El cuerpo es español chileno de negocio: cordial, concreto, sin jerga técnica de fábrica ni datos internos (ids internos, estados en inglés).
- Jamás "ops" ni "prepare" — el mensaje es un borrador; enviarlo es decisión humana.
- Sin texto fuera del JSON."""


WORKFLOW_SYSTEM: dict[str, str] = {
    "morning_brief": BRIEF_SYSTEM,
    "purchase_plan": PURCHASE_SYSTEM,
    "production_plan": PRODUCTION_SYSTEM,
    "quotation_complete": QUOTE_SYSTEM,
    "project_from_documents": DOC_DRAFT_SYSTEM,
    "catalog_compiler": COMPILER_SYSTEM,
    "customer_comms": COMMS_SYSTEM,
}


def _query_key(surface: str, refs: dict) -> str:
    """Dedupe identity for a query — (surface, refs), never the surface
    alone: comparing two projects needs `project` queried once per id."""
    normalized = ",".join(f"{key}={refs[key]}" for key in sorted(refs))
    return f"{surface}|{normalized}"


def _queries(
    *,
    org_id: UUID,
    document: Any,
    seen: set[str],
    observed: frozenset[str],
) -> tuple[list[dict], frozenset[str]]:
    """Execute the model's query steps — each is just another typed
    projection under the caller's RLS. Failed lookups return their error code
    as the observation: the model learns the entity doesn't exist for this
    caller instead of crashing the turn. Refs may only name entities an
    earlier projection actually returned — a hallucinated UUID is an error
    observation, not a fetch."""
    steps = document.get("steps") if isinstance(document, dict) else None
    observations: list[dict] = []
    refs_union: frozenset[str] = frozenset()
    for item in steps if isinstance(steps, list) else []:
        if len(observations) >= MAX_QUERIES:
            break
        if not isinstance(item, dict) or item.get("kind") != "query":
            continue
        surface = item.get("surface")
        refs = item.get("refs") or {}
        # Shape validation precedes _query_key — it assumes dict refs, so a
        # malformed value must be rejected before the key is computed.
        if (
            not isinstance(surface, str)
            or surface not in _BUILDERS
            or not isinstance(refs, dict)
            or not all(
                isinstance(key, str)
                and isinstance(value, (str, int))
                and not isinstance(value, bool)
                for key, value in refs.items()
            )
        ):
            continue
        if _query_key(surface, refs) in seen:
            continue
        needed = REQUIRED_REFS.get(surface, ())
        if any(name not in refs for name in needed):
            seen.add(_query_key(surface, refs))
            observations.append(
                {"surface": surface, "refs": refs, "error": "ai_context_ref_invalid"}
            )
            continue
        if not all(str(value) in observed for value in refs.values()):
            # Unobserved is retryable: a later projection can expose the id,
            # so the key is NOT marked seen — only an executed or structurally
            # invalid query is spent.
            observations.append(
                {"surface": surface, "refs": refs, "error": "ai_context_ref_unobserved"}
            )
            continue
        seen.add(_query_key(surface, refs))
        try:
            context = build_context(org_id, surface, refs)
        except _ContextError as error:
            observations.append(
                {"surface": surface, "refs": refs, "error": error.code}
            )
            continue
        refs_union = refs_union | _context_refs(context)
        observations.append({"surface": surface, "refs": refs, "context": context})
    return observations, refs_union


def _prepare_path_valid(action: str, path: str) -> bool:
    """A prepare link must equal its action's route template — every
    {placeholder} filled by a real UUID — so "Ir a la cotización" can never
    resolve to /dashboard."""
    template = PREPARE_ROUTES.get(action)
    if template is None:
        return False
    pattern = re.escape(template[0])
    for name in template[1]:
        pattern = pattern.replace(rf"\{{{name}\}}", _PATH_UUID.pattern)
    return bool(re.fullmatch(pattern, path))


def _key_grounded(key: Any, grounding: set, refs: frozenset[str]) -> bool:
    """A key composed only of numeric/money characters ("999999",
    "$ 60.000") renders as a number claim; identifier keys with letters
    ("item_2") stay structure."""
    if isinstance(key, str):
        if re.search(r"[A-Za-z_]", key):
            return True
        return _grounded(key, grounding)
    return _payload_grounded(key, grounding, refs)


def _ungrounded_numbers(text: str, grounding: set) -> list[str]:
    """The numbers a reply cites that nothing in context/observations/history
    can back — reported to the corrective round so the model knows exactly
    what to drop or rephrase."""
    scan = _OPAQUE_TOKEN_RE.sub(" ", text)
    found: list[str] = []
    for match in _BARE_NUMBER_RE.finditer(scan):
        number = _parse_number(match.group(0))
        if number is None:
            continue
        if not any(abs(number - value) <= Decimal("0.5") for value in grounding):
            found.append(str(number))
    return found[:8]


_LABEL_KEYS = (
    "code",
    "name",
    "order_code",
    "location_tag",
    "sku",
    "project_code",
    "title",
    "label",
    "public_name",
)


def _evidence_labels(*roots: Any) -> dict[str, str]:
    """Map each UUID the context/observations exposed to the human name in
    the same record — the transcript cites ids, the UI renders "OT-42" and
    "Casa Dormitorios" instead of raw UUIDs."""
    labels: dict[str, str] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            name = next(
                (
                    str(node[key]).strip()
                    for key in _LABEL_KEYS
                    if isinstance(node.get(key), str) and str(node[key]).strip()
                ),
                None,
            )
            if name:
                for value in node.values():
                    if isinstance(value, str) and _PATH_UUID.fullmatch(value):
                        labels.setdefault(value, name)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    for root in roots:
        visit(root)
    return labels


def _payload_grounded(node: Any, grounding: set, refs: frozenset[str]) -> bool:
    """An artifact payload is durable output — invented numbers inside a
    quote or purchase plan render as fact, and an invented entity id would
    deep-link to nothing real. Every scalar carries the same citable-numbers
    rule as the reply; strings must also only cite UUIDs the projections
    actually returned. A key that IS a number ("total_999999" renders as
    text) is a claim, not structure — identifier keys containing digits
    stay free."""
    if isinstance(node, dict):
        return all(
            _key_grounded(key, grounding, refs)
            and _payload_grounded(value, grounding, refs)
            for key, value in node.items()
        )
    if isinstance(node, list):
        return all(_payload_grounded(item, grounding, refs) for item in node)
    if isinstance(node, bool) or node is None:
        return True
    if isinstance(node, (int, float, Decimal)):
        return any(
            abs(Decimal(str(node)) - value) <= Decimal("0.5") for value in grounding
        )
    text = str(node)
    if not all(ref in refs for ref in _PATH_UUID.findall(text)):
        return False
    return _grounded(text, grounding)


def _step_out(item: dict, *, context_refs: frozenset[str]) -> dict | None:
    """Navigate / prepare steps survive only when their path is allowlisted
    AND every UUID in it names an entity a projection actually returned."""
    kind = item.get("kind")
    label = str(item.get("label") or "").strip()[:MAX_LABEL]
    if kind not in ("navigate", "prepare"):
        return None
    path = item.get("path")
    if not isinstance(path, str) or not _ALLOWED_PATHS.match(path):
        return None
    if not all(ref in context_refs for ref in _PATH_UUID.findall(path)):
        return None
    if kind == "navigate":
        return {
            "kind": "navigate",
            "tool": "navigate",
            "path": path,
            "label": label or path,
        }
    action = item.get("action")
    if not isinstance(action, str) or not _prepare_path_valid(action, path):
        return None
    return {
        "kind": "prepare",
        "tool": PREPARE_TOOLS.get(action, "prepare_action"),
        "action": action,
        "path": path,
        "label": label or action,
    }


def _batch_positions(
    org_id: UUID,
    project_id: str,
    targets: dict,
    observed_refs: frozenset[str],
) -> tuple[list[dict], str | None]:
    """Resolve batch targets to live position rows of the project. Explicit
    position_ids must be UUIDs the context/observations already showed — an
    unobserved id aborts the whole step rather than silently dropping it,
    because the model claimed to aim at it."""
    position_ids = targets.get("position_ids")
    where = ""
    params: list[Any] = [org_id, project_id]
    if position_ids is not None:
        if not isinstance(position_ids, list) or not position_ids:
            return [], "batch_targets_invalid"
        seen: list[str] = []
        for value in position_ids:
            if (
                not isinstance(value, str)
                or not _PATH_UUID.fullmatch(value)
                or value not in observed_refs
            ):
                return [], "unobserved_ref"
            if value not in seen:
                seen.append(value)
        if len(seen) > MAX_BATCH_POSITIONS:
            return [], "batch_too_large"
        where = "AND p.id = ANY(%s::uuid[])"
        params.append(seen)
    typology = targets.get("typology")
    if typology is not None and (not isinstance(typology, str) or not typology.strip()):
        return [], "batch_targets_invalid"
    wanted = typology.strip().upper() if isinstance(typology, str) else None
    positions = rows(
        "SELECT p.id, p.position_index, p.location_tag, p.typology, "
        "p.width_mm, p.height_mm, p.system_id, p.parametric_tree "
        "FROM public.project_positions p "
        "WHERE p.org_id=%s AND p.project_id=%s " + where + " ORDER BY p.position_index",
        params,
    )
    matched = [
        position
        for position in positions
        if wanted in (None, "ALL") or (position["typology"] or "").upper() == wanted
    ]
    return matched[:MAX_BATCH_POSITIONS], None


def _expand_batch_ops(ops: list, summary: dict) -> tuple[list, str | None]:
    """`module:"*"`/`coupling:"*"` fan out into one op per real ref of that
    position — 'todas las hojas' means every module the position actually
    has. Structural ops never batch: the same op cannot 'add a unit' on
    geometries that differ per row."""
    module_refs = [str(module["ref"]) for module in summary["modules"]]
    coupling_refs = [str(coupling["ref"]) for coupling in summary["couplings"]]
    expanded: list = []
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in BATCH_OPS:
            return [], "batch_op_not_allowed"
        wildcard = next(
            (field for field in BATCH_WILDCARD_FIELDS if op.get(field) == "*"), None
        )
        if wildcard is None:
            expanded.append(op)
            continue
        refs = module_refs if wildcard == "module" else coupling_refs
        if not refs:
            return [], "batch_no_refs"
        expanded.extend({**op, wildcard: ref} for ref in refs)
    return expanded, None


def _batch_ops_step(
    item: dict,
    *,
    surface: str,
    org_id: UUID,
    project_id: str,
    project_editable: bool,
    observed_refs: frozenset[str],
    grounding: set,
    rejected: list[dict],
) -> dict | None:
    """§08-WC — validate a proposed batch edit: the same op set against every
    matched position, each through the design-assist validator on its own
    catalog authority. The step the client renders carries the validated ops
    per position; the human sees the count + price diff and confirms —
    nothing applies here."""
    if surface != "project" or not project_editable:
        return None
    targets = item.get("targets")
    ops = item.get("ops")
    if not isinstance(targets, dict) or not isinstance(ops, list) or not ops:
        rejected.append({"op": "batch_ops", "reason": "batch_targets_invalid"})
        return None
    for entry in ops:
        name = entry.get("op") if isinstance(entry, dict) else None
        if isinstance(name, str) and name not in BATCH_OPS:
            rejected.append({"op": "batch_ops", "reason": f"batch_op_not_allowed:{name}"})
            return None
    positions, error = _batch_positions(org_id, project_id, targets, observed_refs)
    if error is not None:
        rejected.append({"op": "batch_ops", "reason": error})
        return None
    catalogs: dict[str, dict | None] = {}
    items: list[dict] = []
    for position in positions[:MAX_BATCH_ITEMS]:
        at = f"position_{position['position_index']}"
        product = _jsonb(position.get("parametric_tree"))
        summary = design_assist._summary(product)
        if summary is None:
            # Classic (non-assembly) positions can't be batch-edited — the
            # ops contract speaks assembly refs.
            rejected.append({"op": "batch_ops", "reason": f"{at}:unsupported_product"})
            continue
        try:
            system_id = str(UUID(str(position["system_id"])))
        except (TypeError, ValueError):
            # A position with no bound system can't validate against a catalog.
            rejected.append({"op": "batch_ops", "reason": f"{at}:catalog_unavailable"})
            continue
        if system_id not in catalogs:
            catalogs[system_id] = design_assist._catalog(UUID(system_id), org_id)
        catalog = catalogs[system_id]
        if catalog is None:
            rejected.append({"op": "batch_ops", "reason": f"{at}:catalog_unavailable"})
            continue
        expanded, werror = _expand_batch_ops(ops, summary)
        if werror is not None:
            rejected.append({"op": "batch_ops", "reason": f"{at}:{werror}"})
            continue
        accepted, dropped = design_assist._validate_ops(expanded, summary, catalog, grounding)
        for entry in dropped:
            rejected.append({**entry, "reason": f"{at}:{entry['reason']}"})
        if accepted:
            items.append(
                {
                    "position_id": str(position["id"]),
                    "index": int(position["position_index"]),
                    "location": _cut(position["location_tag"]),
                    "typology": position["typology"],
                    "ops": accepted,
                }
            )
    if not items:
        return None
    return {
        "kind": "batch_ops",
        "tool": "preview_commands",
        "items": items,
        "label": str(item.get("label") or "").strip()[:MAX_LABEL]
        or "Edición masiva de diseño",
    }


class JobCanceledError(Exception):
    """A cancel signal arrived while the run was in flight — the caller
    unwinds and marks the job CANCELED instead of finishing it."""


def _act(
    *,
    org_id: UUID,
    user_id: UUID,
    surface: str,
    refs: dict,
    goal: str,
    product: Any,
    history: list,
    operation_key: str,
    history_trusted: bool = False,
    job_id: UUID | None = None,
    progress: Any = None,
) -> dict:
    def _report(value: float) -> None:
        # Progress lands on the job_runs row — the only channel a reader can
        # see while this transaction holds the ai_jobs row uncommitted.
        if callable(progress):
            progress(value)

    _report(15)
    context = build_context(org_id, surface, refs)
    contexts = [context]
    seen_queries = {_query_key(surface, refs)}
    observed_refs = _context_refs(context)
    observations: list[dict] = []
    all_observations: list[dict] = []
    debited = 0
    audit_id = ""
    model = ""
    document: Any = {}
    for round_index in range(MAX_ROUNDS):
        # Cooperative cancel, checked between provider rounds: a cancel that
        # landed mid-run (direct CANCELED write or signal row) stops the
        # loop before the next round burns another provider call.
        if job_id is not None and jobs.cancel_requested(job_id=job_id):
            raise JobCanceledError()
        _report(20 + round_index * 20)
        envelope = gateway.invoke(
            org_id=org_id,
            user_id=user_id,
            capability=CAPABILITY,
            # Each round is its own audited invocation — the suffix keeps
            # round keys distinct so a client retry replays every round
            # instead of the second call replaying the first's output.
            operation_key=f"{operation_key}:r{round_index}",
            tool_name="agent",
            provider_options={
                "system": WORKFLOW_SYSTEM.get(surface, AGENT_SYSTEM),
                "json_output": True,
            },
            input_payload={
                "goal": goal,
                "surface": surface,
                "context": context,
                "observations": observations,
                "history": history,
                "actions": {
                    "query_surfaces": sorted(REQUIRED_REFS),
                    "prepare_actions": sorted(PREPARE_ROUTES),
                    "prepare_routes": {
                        action: route for action, (route, _params) in PREPARE_ROUTES.items()
                    },
                    "ops_available": surface == "position" and product is not None,
                },
                "product": product,
                "product_fields": (
                    "product.modules[].id|width_mm|height_mm|contour|frameless "
                    "y product.couplings[].id|angle_deg|kind|modules|edges"
                    if surface == "position" and product is not None
                    else None
                ),
            },
        )
        debited += int(envelope["credits_debited"])
        audit_id = envelope["audit_id"]
        model = envelope["model"]
        try:
            document = json.loads(envelope["output"])
        except (json.JSONDecodeError, TypeError):
            raise contract_error(
                502,
                "ai_agent_bad_output",
                "El agente devolvió una respuesta inválida.",
            ) from None
        if not isinstance(document, dict):
            raise contract_error(
                502,
                "ai_agent_bad_output",
                "El agente devolvió una respuesta inválida.",
            )
        _report(30 + round_index * 20)
        observations, new_observed = _queries(
            org_id=org_id,
            document=document,
            seen=seen_queries,
            observed=observed_refs,
        )
        observed_refs = observed_refs | new_observed
        all_observations.extend(observations)
        contexts.extend(
            observation["context"]
            for observation in observations
            if isinstance(observation.get("context"), dict)
        )
        # Any observation — success or error — informs the next round; an
        # entity that doesn't exist for this caller is a finding the model
        # should report, not a reason to stop mid-thought.
        if not observations:
            break

    reply = document.get("reply") if isinstance(document.get("reply"), str) else ""
    reply = reply.strip()[:MAX_REPLY]
    if not reply:
        raise contract_error(
            502,
            "ai_agent_bad_output",
            "El agente devolvió una respuesta inválida.",
        )
    _report(80)
    # Multi-turn grounding: numbers in earlier turns of this job stay
    # citable — but only when the history was rebuilt server-side from the
    # stored transcript (resume). A first-run history is arbitrary client
    # input: letting it into the grounding set would let any fabricated
    # figure be restated as fact.
    declared_text = goal + " " + " ".join(
        str(turn.get("text") or turn.get("content") or turn.get("reply") or "")
        for turn in (history if history_trusted else [])
        if isinstance(turn, dict) and turn.get("role") in ("user", "agent")
    )
    grounding = _grounding_values(
        {"context": context, "observations": all_observations}, declared_text
    )
    regrounded = False
    for reground in range(MAX_REGROUNDS):
        if _grounded(reply, grounding):
            break
        # One corrective round: the model is told exactly which numbers
        # aren't citable so it can rephrase instead of the whole job failing
        # on a conversational enumeration. Channels it omits keep the prior
        # document's content — the correction replaces, never erases.
        envelope = gateway.invoke(
            org_id=org_id,
            user_id=user_id,
            capability=CAPABILITY,
            operation_key=f"{operation_key}:g{reground}",
            tool_name="agent",
            provider_options={
                "system": WORKFLOW_SYSTEM.get(surface, AGENT_SYSTEM),
                "json_output": True,
            },
            input_payload={
                "goal": goal,
                "surface": surface,
                "context": context,
                "observations": all_observations,
                "history": history,
                "correction": {
                    "reason": "reply_ungrounded",
                    "uncitable_numbers": _ungrounded_numbers(reply, grounding),
                    "previous_reply": reply[:400],
                    "instruction": (
                        "Reescribe la respuesta citando solo números que "
                        "existan en context, observations o history. Si un "
                        "dato no es comprobable, declara la incertidumbre."
                    ),
                },
            },
        )
        debited += int(envelope["credits_debited"])
        audit_id = envelope["audit_id"]
        model = envelope["model"]
        try:
            corrected = json.loads(envelope["output"])
        except (json.JSONDecodeError, TypeError):
            break
        if not isinstance(corrected, dict):
            break
        # The corrective doc's "queries" never ran — merging them would list
        # tool calls that produced no observation. Every other channel still
        # faces its own downstream validation before it reaches the job.
        document.update(
            {
                k: v
                for k, v in corrected.items()
                if k != "queries" and v not in (None, [], {})
            }
        )
        corrected_reply = corrected.get("reply")
        if isinstance(corrected_reply, str) and corrected_reply.strip():
            reply = corrected_reply.strip()[:MAX_REPLY]
            regrounded = True
    if not _grounded(reply, grounding):
        raise contract_error(
            502,
            "ai_agent_ungrounded",
            "El agente citó datos que no están en el contexto.",
        )
    # Grounding binds every channel the model writes — warnings, plan,
    # questions and artifact payloads face the same citable-numbers rule as
    # the reply. Ungrounded items are dropped and counted, never rephrased.
    dropped_ungrounded = 0
    warnings: list[str] = []
    for item in (document.get("warnings") or [])[:MAX_WARNINGS]:
        if not isinstance(item, str) or not item.strip():
            continue
        text = item.strip()[:MAX_WARNING]
        if not _grounded(text, grounding):
            dropped_ungrounded += 1
            continue
        warnings.append(text)
    if regrounded:
        warnings.append(
            "La respuesta fue reescrita tras citar datos fuera del contexto; "
            "los números comprobables se conservaron."
        )

    context_refs = frozenset().union(*(_context_refs(c) for c in contexts))

    # Ops steps ride the design-assist contract: they only exist when the
    # caller is on a position surface with a live product, and they validate
    # against the position's own catalog authority — never a client field.
    summary = catalog = declared = None
    if surface == "position" and product is not None and "position_id" in refs:
        summary = design_assist._summary(product)
        if summary is not None:
            position = projects_service.position_row(org_id, refs["position_id"])
            try:
                catalog = design_assist._catalog(
                    UUID(str(position["system_id"])), org_id
                )
            except (TypeError, ValueError):
                # A position without a bound system can't validate ops — skip
                # cleanly instead of crashing the whole round on ValueError.
                catalog = None
            declared = design_assist._declared_values(goal)

    steps: list[dict] = []
    rejected: list[dict] = []
    for item in document.get("steps") or []:
        if len(steps) >= MAX_STEPS:
            break
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind == "query":
            continue  # executed above — `queries` reports them as provenance
        if kind == "ops":
            if summary is None or catalog is None or declared is None:
                # The surface can't validate ops (no live product, no bound
                # system) — an ops step that vanishes without a note reads
                # as a clean answer with work silently missing. Surface the
                # refusal as a rejection instead.
                rejected.append(
                    {
                        "op": "ops",
                        "reason": (
                            "product_absent" if summary is None else "catalog_unavailable"
                        ),
                    }
                )
                continue
            ops, dropped = design_assist._validate_ops(
                item.get("ops"), summary, catalog, declared
            )
            rejected.extend(dropped)
            if ops:
                steps.append(
                    {
                        "kind": "ops",
                        "tool": "preview_commands",
                        "ops": ops,
                        "label": str(item.get("label") or "").strip()[:MAX_LABEL]
                        or "Cambios de diseño",
                    }
                )
            continue
        if kind == "batch_ops":
            out = _batch_ops_step(
                item,
                surface=surface,
                org_id=org_id,
                project_id=str(refs.get("project_id") or ""),
                project_editable=bool((context or {}).get("editable")),
                observed_refs=context_refs,
                grounding=grounding,
                rejected=rejected,
            )
            if out is not None:
                steps.append(out)
            continue
        out = _step_out(item, context_refs=context_refs)
        if out is not None:
            steps.append(out)

    context_refs_all = context_refs

    raw_artifacts = [
        item.get("artifact")
        for item in (document.get("steps") or [])
        if isinstance(item, dict) and item.get("kind") == "artifact"
    ]
    validated_artifacts = []
    for artifact in jobs.artifacts(raw_artifacts, context_refs_all):
        # Ungrounded payloads are dropped, not displayed (review AI-02).
        if not _payload_grounded(
            artifact.get("payload") or {}, grounding, context_refs_all
        ):
            dropped_ungrounded += 1
            continue
        validated_artifacts.append(
            {**artifact, "tool": ARTIFACT_TOOLS.get(artifact.get("kind"), "create_draft")}
        )
    claims, references, dropped_claims = jobs.claims_and_references(
        document.get("claims"), context_refs_all
    )
    # An evidence ref must not launder an invented number: claim text faces
    # the same grounding check as the reply and warnings.
    grounded_claims = []
    for claim in claims:
        if _grounded(claim["text"], grounding):
            grounded_claims.append(claim)
        else:
            dropped_claims += 1
            dropped_ungrounded += 1
    claims = grounded_claims
    if dropped_claims:
        warnings.append(
            f"{dropped_claims} afirmación(es) sin evidencia en contexto descartada(s)"
        )
    model_refs = jobs._references(document.get("references"), context_refs_all)
    for ref in model_refs:
        if ref not in references:
            references.append(ref)
    plan = []
    for item in (document.get("plan") or [])[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:200]
        if not label:
            continue
        if not _grounded(label, grounding):
            dropped_ungrounded += 1
            continue
        plan.append({"label": label})
    questions = []
    for item in (document.get("questions") or [])[:3]:
        if not isinstance(item, str) or not item.strip():
            continue
        text = item.strip()[:400]
        if not _grounded(text, grounding):
            dropped_ungrounded += 1
            continue
        questions.append(text)
    if dropped_ungrounded:
        warnings.append(
            f"{dropped_ungrounded} dato(s) del modelo sin evidencia en contexto descartado(s)"
        )

    return {
        "audit_id": audit_id,
        "model": model,
        "credits_debited": debited,
        "reply": reply,
        "plan": plan,
        "claims": claims,
        "references": references,
        "questions": questions,
        "artifacts": validated_artifacts,
        "steps": steps,
        "queries": [
            # The caller's own surface was already consulted — report it as
            # provenance even when the model never queried anything else.
            {
                "surface": surface,
                "tool": QUERY_TOOLS.get(surface, "get_context"),
                "status": "ok",
            },
            *[
                {
                    "surface": observation["surface"],
                    "tool": QUERY_TOOLS.get(observation["surface"], "get_context"),
                    "status": "ok" if "context" in observation else "error",
                }
                for observation in all_observations
            ],
        ],
        "warnings": warnings,
        "rejected": rejected,
        # Human names for the ids claims/reference may cite — the transcript
        # stores ids; the workspace renders the entity behind each one.
        "evidence_labels": _evidence_labels(context, all_observations),
    }


def act(
    *,
    org_id: UUID,
    user_id: UUID,
    surface: str,
    refs: dict,
    goal: str,
    product: Any,
    history: list,
    operation_key: str,
    job: dict | None = None,
    replay: bool = False,
    product_sig: str = "",
    history_trusted: bool = False,
    progress: Any = None,
) -> dict:
    """§07-B — every agent run is a durable job. The transcript carries the
    user's turn plus the model's grounded round; artifacts, claims and
    warnings land on the row so the workspace can inspect them after the
    conversation scrolls. On a failed round the exception propagates: the
    caller records FAILED_RETRYABLE after the request rolls back, so the
    failure itself survives the transaction."""
    job = job or jobs.create_job(
        org_id=org_id, user_id=user_id, surface=surface, refs=refs, goal=goal
    )
    transcript = list(job.get("transcript") or [])
    turn: dict = {"role": "user", "text": goal[:MAX_GOAL]}
    if product_sig:
        # The design the ops validate against — persisted so a restored
        # turn can still refuse to apply onto a changed canvas.
        turn["product_sig"] = product_sig
    if replay:
        # The retry endpoint re-runs the failed round's own message — mark
        # it so the UI shows a retry, not a message the user never wrote
        # again.
        turn["replay"] = True
    transcript.append(turn)
    result = _act(
        org_id=org_id,
        user_id=user_id,
        surface=surface,
        refs=refs,
        goal=goal,
        product=product,
        history=history,
        operation_key=operation_key,
        history_trusted=history_trusted,
        job_id=UUID(job["id"]) if job.get("id") else None,
        progress=progress,
    )

    # Approvals are sticky across rounds: a no-op follow-up must not flip a
    # job whose earlier rounds still have gated steps awaiting a decision.
    # Pending = every proposed gated step with no recorded outcome.
    resolved = {
        (int(o.get("turn_index", -1)), int(o.get("step_index", -1)))
        for o in (job.get("outcomes") or [])
        if isinstance(o, dict)
    }
    pending_approvals = any(
        step.get("kind") in ("prepare", "ops", "batch_ops")
        and (turn_index, step_index) not in resolved
        for turn_index, turn_row in enumerate(transcript)
        for step_index, step in enumerate(turn_row.get("steps") or [])
    ) or any(
        step.get("kind") in ("prepare", "ops", "batch_ops")
        for step in result["steps"]
    )
    state = (
        "WAITING_FOR_USER"
        if result["questions"]
        else "WAITING_FOR_APPROVAL" if pending_approvals else "SUCCEEDED"
    )
    transcript.append(
        {
            "role": "agent",
            "reply": result["reply"],
            "plan": result["plan"],
            "queries": result["queries"],
            "claims": result["claims"],
            "references": result["references"],
            "questions": result["questions"],
            "artifacts": result["artifacts"],
            "steps": result["steps"],
            "warnings": result["warnings"],
            "rejected": result["rejected"],
            "evidence_labels": result["evidence_labels"],
        }
    )
    # The job's artifact shelf accumulates across rounds — a question-only
    # follow-up must not wipe drafts an earlier turn produced. Each turn's
    # own artifacts stay attributed in the transcript entry.
    artifacts = (
        list(job.get("artifacts") or []) + result["artifacts"]
    )[-jobs.MAX_ARTIFACTS_TOTAL:]
    jobs.finish_job(
        job_id=UUID(job["id"]),
        state=state,
        transcript=transcript,
        plan=result["plan"],
        artifacts=artifacts,
        warnings=result["warnings"],
        result=result,
    )
    result["job_id"] = job["id"]
    result["state"] = state
    result["transcript"] = transcript
    # The transcript entry above already captured this round's own list —
    # the response mirrors the accumulated shelf like the job row does.
    result["artifacts"] = artifacts
    return result
