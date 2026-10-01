"""Contextual Ask: question + surface → bounded typed context → provider answer.

The trust contract is the mandate's spine: the provider only answers inside a
server-built projection, it can propose navigation but never a mutation, and
an unknown answer is refused rather than invented. """

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import connection

from ai_gateway import service as gateway
from ai_gateway.context import (
    REQUIRED_REFS,
    _ContextError,
    build_context,
    guarded,
    stable_refs,
)
from ai_gateway.jobs import _ai_backend
from authentication.errors import contract_error
from projects.design_assist import _BARE_NUMBER_RE, _MEASURE_RE, _parse_number

# Tokens that carry digits without quantitative meaning — scrubbed before the
# grounding scan so they cannot back an invented number. The third branch
# covers alphanumeric codes (SKUs, order codes like "OT-42", "PER-4590"): a
# word run where a letter precedes a digit is an identifier, not a numeric
# claim — while digit-leading tokens like "1500mm" still count as measures.
_OPAQUE_TOKEN_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|\d{4}-\d{2}-\d{2}(?:[T ][0-9:.]+(?:Z|[+-]\d{2}:?\d{2})?)?"
    r"|[\w-]*[A-Za-z_][\w-]*\d[\w-]*"
)

CAPABILITY = "context_assist"
MAX_QUESTION = 2000
MAX_ANSWER = 4000
MAX_ACTIONS = 4
MAX_LABEL = 80
MAX_WARNINGS = 8
MAX_WARNING = 240

# Actions the surface may propose. v1 is navigate-only — an AI answer can point
# at where the action lives, it can never execute one. Paths are allowlisted to
# the app's own routes so a provider response can never become an open redirect
# or a javascript: URL.
_ALLOWED_PATHS = re.compile(
    r"^/(dashboard|projects|production|purchasing|catalogs|clients|pricing|settings)"
    r"(/[0-9a-zA-Z\-_/]*)?$|^/$"
)
_PATH_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _context_refs(context: Any) -> frozenset[str]:
    """Every entity id literally present in the projection — a navigate action
    may only deep-link to entities the caller's own context already exposes."""
    return frozenset(_PATH_UUID.findall(json.dumps(context, default=str)))

ASK_SYSTEM = """Eres el asistente contextual de DEKOPEN, una aplicación profesional de ventanas y puertas (español chileno).

Recibes un JSON con:
- "question": la pregunta del usuario.
- "surface": la superficie donde el usuario está trabajando.
- "context": una proyección tipada y limitada de los datos reales de su organización — es la ÚNICA fuente de verdad que tienes.

Respondes SOLO un JSON:
{
  "answer": "respuesta breve y concreta en español (máx. ~120 palabras)",
  "actions": [{"kind": "navigate", "path": "/ruta-de-la-app", "label": "qué muestra"}],
  "warnings": ["alertas opcionales si detectas algo relevante en el contexto"]
}

Reglas:
- Responde SOLO con lo que el contexto muestra. Si el dato no está en el contexto, dilo claramente ("no tengo ese dato") y sugiere dónde encontrarlo — nunca inventes medidas, precios, SKU, nombres o estados.
- Los valores técnicos (dimensiones, precios, cantidades) solo pueden citar números que estén literalmente en el contexto o en la pregunta.
- Ejemplo de rechazo correcto — MAL: "El consumo estimado es 3,2 barras" (el contexto no contiene ese número). BIEN: "El contexto no informa consumo de barras; en Producción puedes optimizar la orden para obtenerlo".
- "actions" solo puede proponer navegación dentro de la app (rutas que empiezan con /dashboard, /projects, /production, /purchasing, /catalogs, /clients, /pricing o /settings). Máximo 4.
- "warnings" para problemas reales que el contexto evidencie (ej. escasez de material, una revisión sin congelar). Máximo 8.
- Sin texto fuera del JSON."""

CATALOG_SYSTEM_SUFFIX = """
Contexto de CATÁLOGO — puedes:
- Explicar bloqueos de disponibilidad citando "readiness.levels[].blockers": entidad afectada, autoridad que falta, consecuencia y acción de resolución — con sus palabras exactas.
- Ubicar evidencia: provenance (MANUAL/LEGACY_UNVERIFIED), review_queue y drawing_ref de secciones muestran de dónde salió cada dato.
- Sugerir relaciones entre entidades por su id/SKU (artículos, junquillos, kits, refuerzos, mapeos de compra) — señala el par concreto, no generalidades.
- Detectar duplicados o inconsistencias visibles en los rosters (SKU repetido, nombre idéntico con rol distinto).
- Comparar revisiones cuando el contexto expone "revision" — describe qué campos cambiarían.
NUNCA certifiques un dato técnico que el contexto no muestre literalmente: si falta soldadura, masa o una sección, dilo y apunta al formulario real — la revisión humana es la única autoridad, tú no la eres."""


def _grounding_values(context: Any, question: str) -> set[Decimal]:
    """Numbers the answer may cite: every numeric token literally present in
    the context projection plus the lengths of its collections, and the
    numbers the user themselves wrote (measures normalized to mm). A number
    outside this set is an invention, not an explanation."""
    values: set[Decimal] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            # Entity collections may ground "cuántos" answers; scalar arrays
            # (coordinates, point pairs) can't launder an invented count.
            if any(isinstance(item, dict) for item in node):
                values.add(Decimal(len(node)))
            for item in node:
                walk(item)

    walk(context)
    # Opaque identifiers and dates look numeric to a bare-digit scan but
    # carry no quantitative meaning — scrub them so '2026-09-30' can't ground
    # '2026 unidades' nor a UUID's hex digits a fabricated measure.
    scrubbed = _OPAQUE_TOKEN_RE.sub(" ", json.dumps(context))
    for match in _BARE_NUMBER_RE.finditer(scrubbed):
        number = _parse_number(match.group(0))
        if number is not None:
            values.add(number)
    for match in _MEASURE_RE.finditer(question):
        number = _parse_number(match.group(1))
        if number is None:
            continue
        unit = match.group(2).lower()
        if unit.startswith("mm") or unit.startswith("mil"):
            factor = Decimal(1)
        elif unit == "cm":
            factor = Decimal(10)
        else:
            factor = Decimal(1000)
        values.add(number * factor)
    scan = _MEASURE_RE.sub("", question)
    for match in _BARE_NUMBER_RE.finditer(scan):
        number = _parse_number(match.group(0))
        if number is not None:
            values.add(number)
    return values


def _grounded(answer: str, values: set[Decimal]) -> bool:
    """Every number in the answer must be citable — within rounding tolerance
    of a grounding value ('el desperdicio es 20%' may cite a 20.4 in context,
    but '3 barras' may not invent a consumption). Opaque tokens are scrubbed
    before scanning: a date or UUID in the text is an identifier, not a
    numeric claim ('entrega 2026-09-30' need not ground '2026')."""
    scan = _OPAQUE_TOKEN_RE.sub(" ", answer)
    for match in _BARE_NUMBER_RE.finditer(scan):
        number = _parse_number(match.group(0))
        if number is None:
            continue
        if not any(abs(number - value) <= Decimal("0.5") for value in values):
            return False
    return True


def _answer(document: Any, context_refs: frozenset[str]) -> dict:
    if not isinstance(document, dict) or not isinstance(document.get("answer"), str):
        raise contract_error(
            502,
            "ai_assist_bad_output",
            "El asistente devolvió una respuesta inválida.",
        )
    answer = document["answer"].strip()
    if not answer:
        raise contract_error(
            502,
            "ai_assist_bad_output",
            "El asistente devolvió una respuesta inválida.",
        )
    actions = []
    raw_actions = document.get("actions")
    if isinstance(raw_actions, list):
        for item in raw_actions:
            # Cap counts *valid* actions — a padded list of junk must not push
            # real ones out of the response.
            if len(actions) >= MAX_ACTIONS:
                break
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            label = item.get("label")
            if (
                item.get("kind") == "navigate"
                and isinstance(path, str)
                and _ALLOWED_PATHS.match(path)
                # Entity routes only when the id is in the served context —
                # otherwise the provider could point at any record.
                and all(ref in context_refs for ref in _PATH_UUID.findall(path))
            ):
                actions.append(
                    {
                        "kind": "navigate",
                        "path": path,
                        "label": (str(label).strip() or path)[:MAX_LABEL],
                    }
                )
    warnings = []
    raw_warnings = document.get("warnings")
    if isinstance(raw_warnings, list):
        for item in raw_warnings:
            if len(warnings) >= MAX_WARNINGS:
                break
            if isinstance(item, str) and item.strip():
                warnings.append(item.strip()[:MAX_WARNING])
    return {
        "answer": answer[:MAX_ANSWER],
        "actions": actions,
        "warnings": warnings,
    }


def ask(
    *,
    org_id: UUID,
    user_id: UUID,
    surface: str,
    refs: dict | None,
    question: str,
    operation_key: str,
) -> dict:
    if surface not in REQUIRED_REFS:
        raise contract_error(
            400,
            "ai_surface_unknown",
            "La superficie solicitada no tiene proyección de contexto.",
        )
    missing = [name for name in REQUIRED_REFS[surface] if name not in (refs or {})]
    if missing:
        raise contract_error(
            400,
            "ai_context_ref_required",
            f"Esta superficie requiere la referencia '{missing[0]}'.",
        )
    try:
        context = build_context(org_id, surface, refs)
    except _ContextError as error:
        if error.code == "ai_context_ref_invalid":
            raise contract_error(
                400,
                "ai_context_ref_invalid",
                "La referencia de contexto no es válida.",
            ) from None
        raise contract_error(
            404,
            "ai_context_not_found",
            "El contexto solicitado no existe o no está disponible.",
        ) from None
    envelope = gateway.invoke(
        org_id=org_id,
        user_id=user_id,
        capability=CAPABILITY,
        operation_key=operation_key,
        tool_name="context_assist",
        provider_options={
            "system": guarded(ASK_SYSTEM)
            + (CATALOG_SYSTEM_SUFFIX if surface == "catalog" else ""),
            "json_output": True,
        },
        input_payload={
            "question": question[:MAX_QUESTION],
            "surface": surface,
            "context": context,
        },
    )
    try:
        document = json.loads(envelope["output"])
    except (json.JSONDecodeError, TypeError):
        raise contract_error(
            502,
            "ai_assist_bad_output",
            "El asistente devolvió una respuesta inválida.",
        ) from None
    validated = _answer(document, _context_refs(context))
    values = _grounding_values(context, question)
    if not _grounded(validated["answer"], values):
        raise contract_error(
            502,
            "ai_assist_ungrounded",
            "El asistente citó valores que no constan en el contexto.",
        )
    # Warnings render as system-derived evidence — invented numerics there
    # carry the same weight as an ungrounded answer.
    validated["warnings"] = [
        item for item in validated["warnings"] if _grounded(item, values)
    ]
    result = {
        "audit_id": envelope["audit_id"],
        "model": envelope["model"],
        "credits_debited": envelope["credits_debited"],
        **validated,
    }
    # The durable thread keys on the stable refs — a volatile pointer ref
    # (selection) reaches the context but must not split the conversation
    # into a new thread per canvas click.
    _record_turn(
        org_id=org_id,
        user_id=user_id,
        surface=surface,
        refs=stable_refs(refs or {}),
        question=question[:MAX_QUESTION],
        answer=result,
    )
    return result


def _record_turn(
    *,
    org_id: UUID,
    user_id: UUID,
    surface: str,
    refs: dict,
    question: str,
    answer: dict,
) -> None:
    """Persist the ask turn so the dock restores the conversation across
    reload and later sessions (§3). Writes run under ``ai_backend`` — a
    turn is committed evidence of what the assistant answered, so members
    never mint or edit one through PostgREST. A persistence failure must
    not break the reply the user is already reading."""
    if connection.vendor != "postgresql":
        return
    try:
        with _ai_backend():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.ai_ask_turns
                        (org_id, user_id, surface, refs, question, answer)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb)
                    """,
                    [
                        str(org_id), str(user_id), surface,
                        json.dumps(refs), question, json.dumps(answer),
                    ],
                )
    except Exception:  # noqa: BLE001 — evidence must never break the answer
        # But never silently: a persistent insert failure means restored
        # threads diverge from what the user saw — operators need the log.
        logging.getLogger(__name__).warning(
            "ai_ask_turn persist failed", exc_info=True
        )
        return


def list_turns(
    *, org_id: UUID, user_id: UUID, surface: str, refs: dict
) -> list[dict]:
    """The durable ask thread for (user, surface, stable refs) — newest-last
    so the dock replays it as a conversation. Volatile pointer refs are
    stripped before matching so a canvas click never orphans the thread."""
    if connection.vendor != "postgresql":
        return []
    refs = stable_refs(refs)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT question, answer, created_at
            FROM public.ai_ask_turns
            WHERE org_id = %s AND user_id = %s AND surface = %s
              AND refs = %s::jsonb
            ORDER BY created_at DESC, id DESC
            LIMIT 50
            """,
            [str(org_id), str(user_id), surface, json.dumps(refs)],
        )
        rows_out = cursor.fetchall()
    # Newest-first read window, restored oldest-first so the dock replays
    # the recent tail as a conversation — a >50-turn thread keeps its
    # freshest context instead of permanently dropping the newest turns.
    turns = []
    for q, a, ts in reversed(rows_out):
        # Drivers that don't register jsonb return it as a raw JSON string —
        # the client contract is an object, so decode it back before serving.
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except (json.JSONDecodeError, TypeError):
                continue  # a corrupt turn can't render; skip, don't crash the thread
        turns.append(
            {"question": q, "answer": a, "created_at": ts.isoformat() if ts else None}
        )
    return turns


__all__ = ["ask", "list_turns"]
