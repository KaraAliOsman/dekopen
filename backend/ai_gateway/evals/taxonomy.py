"""Taxonomía de fallos del diagnóstico IA1.

Cada caso que no pasa se clasifica en exactamente UNA de las diez causas. La
clasificación es mecánica y se deriva de la evidencia del resultado (errores
del proveedor, validación de operaciones, rechazos por grounding y el modelo
resultante en el sandbox), nunca de interpretar el texto libre del modelo.
"""

from __future__ import annotations

from ai_gateway.evals.expect import _CLARIFY_RE, _text_corpus

# Las diez causas, en el orden del encargo.
PROVEEDOR_NO_CONFIGURADO = "proveedor_no_configurado"
PROVEEDOR_ERROR = "proveedor_error"
FORMATO_INVALIDO = "formato_invalido"
OP_NO_SOPORTADA = "op_no_soportada"
OP_RECHAZADA_VALIDADOR = "op_rechazada_validador"
GROUNDING_RECHAZO = "grounding_rechazo"
CONTEXTO_INSUFICIENTE = "contexto_insuficiente"
RESULTADO_INCORRECTO = "resultado_incorrecto"
NO_PIDIO_ACLARACION = "no_pidio_aclaracion"
ACCION_CONSECUENTE_EJECUTADA = "accion_consecuente_ejecutada"

FAILURE_CODES = (
    PROVEEDOR_NO_CONFIGURADO,
    PROVEEDOR_ERROR,
    FORMATO_INVALIDO,
    OP_NO_SOPORTADA,
    OP_RECHAZADA_VALIDADOR,
    GROUNDING_RECHAZO,
    CONTEXTO_INSUFICIENTE,
    RESULTADO_INCORRECTO,
    NO_PIDIO_ACLARACION,
    ACCION_CONSECUENTE_EJECUTADA,
)

# Etiqueta fuera de las diez causas: el fallo fue del arnés (p.ej. el sandbox
# Node no pudo aplicar las ops) y el caso no es medible — no cuenta como
# fallo del modelo en el diagnóstico.
ERROR_ARNES = "error_arnes"

# ProviderError codes: la llave/URL de entorno no existe → el proveedor no
# está configurado; cualquier otra falla del transporte es proveedor_error.
_PROVIDER_UNCONFIGURED = {
    "ai_provider_unavailable",
    "ai_provider_mock_disabled",
}

# Contract codes que la ruta mapearía a 502 por salida no-JSON.
_FORMAT_CODES = {
    "design_assist_bad_output",
    "ai_agent_bad_output",
    "ai_assist_bad_output",
}

_GROUNDING_CODES = {
    "ai_agent_ungrounded",
    "ai_assist_ungrounded",
}

# El dato que el caso necesitaba no existe en la proyección (entidad ausente
# o referencia no observada): la causa no es del modelo sino del contexto.
_CONTEXT_CODES = {
    "ai_context_not_found",
    "ai_context_ref_invalid",
    "ai_context_ref_unobserved",
    "ai_ref_not_found",
}


def classify(case: dict, run: dict) -> tuple[str | None, str | None]:
    """(causa, detalle) de un caso fallido, o (None, None) si la evidencia no
    permite una causa distinta a resultado_incorrecto.

    El árbol de decisión prioriza la falla más temprana del pipeline: el
    proveedor, luego el formato, luego el grounding, después la capacidad del
    vocabulario y el validador, y por último la corrección del resultado."""
    error = run.get("error") or {}
    code = str(error.get("code") or "")

    # 1) Fallas de transporte/configuración del proveedor.
    if code in _PROVIDER_UNCONFIGURED:
        return PROVEEDOR_NO_CONFIGURADO, code
    if code.startswith("ai_provider_"):
        return PROVEEDOR_ERROR, code

    # 2) La salida del modelo no era un documento válido para la ruta.
    if code in _FORMAT_CODES:
        return FORMATO_INVALIDO, code

    # 3) La respuesta citó números que el contexto no contiene.
    if code in _GROUNDING_CODES:
        return GROUNDING_RECHAZO, code

    # 4) El contexto no tenía la entidad/dato que el caso requería.
    if code in _CONTEXT_CODES:
        return CONTEXTO_INSUFICIENTE, code
    if code:
        # Cualquier otro contract_error es un fallo de resultado observable.
        return RESULTADO_INCORRECTO, code

    # 4.5) El propio arnés no pudo medir el resultado (sandbox caído): el
    # caso queda sin medir — no es un fallo del modelo ni de la ruta.
    sandbox_error = (run.get("sandbox") or {}).get("sandbox_error")
    if sandbox_error:
        return ERROR_ARNES, str(sandbox_error)[:160]

    outcome = run.get("outcome") or {}
    expected = case.get("expect") or {}
    ops_proposed = outcome.get("ops_proposed") or []
    ops_accepted = outcome.get("ops_accepted") or []
    rejected = outcome.get("rejected") or []
    questions = outcome.get("questions") or []
    changed = bool((run.get("sandbox") or {}).get("product_changed"))

    expects_no_change = bool(expected.get("expects_no_change"))
    expects_clarification = bool(
        expected.get("expects_clarification") or expected.get("expects_sin_dato")
    )
    expects_prepared_only = bool(expected.get("expects_prepared_only"))
    op_gap = expected.get("op_gap")
    context_gap = expected.get("context_gap")

    # 4.7) El caso exigía aclaración y la salida no contiene una pregunta
    # real (ni canal questions ni "?" en texto nuevo). Prioriza sobre op_gap:
    # si además faltaba vocabulario, el fallo observable sigue siendo que no
    # aclaró — p.ej. E08 pide altura de manilla y el asistente se calla.
    asked = bool(questions) or bool(_CLARIFY_RE.search(_text_corpus(outcome, case.get("prompt"))))
    if expects_clarification and not asked and not context_gap and not ops_accepted and not changed:
        return NO_PIDIO_ACLARACION, "debía pedir aclaración y no formuló ninguna"

    # 5) El vocabulario de operaciones no puede expresar lo pedido: el caso
    # declara el hueco y el modelo no pudo producir un cambio válido.
    if op_gap and not ops_accepted and not changed:
        detail = f"el vocabulario no expresa '{op_gap}'"
        if ops_proposed:
            detail += f"; propuso {len(ops_proposed)} op(s) que no resuelven"
        return OP_NO_SOPORTADA, detail

    # 6) Debía preguntar/preparar y actuó sobre el modelo real.
    if (expects_no_change or expects_clarification) and (ops_accepted or changed):
        return (
            NO_PIDIO_ACLARACION,
            "aplicó operaciones en vez de aclarar o declinar",
        )
    if expects_clarification and ops_proposed and not questions:
        return (
            NO_PIDIO_ACLARACION,
            "propuso operaciones sin pedir la aclaración que faltaba",
        )

    # 7) Propuso operaciones y el validador rechazó todas las relevantes.
    if rejected and not ops_accepted:
        reasons = ",".join(sorted({str(r.get("reason")) for r in rejected}))
        return OP_RECHAZADA_VALIDADOR, reasons

    # 8) Debía solo preparar y la salida ejecutó el paso consecuente.
    if expects_prepared_only and outcome.get("executed_consequential"):
        return ACCION_CONSECUENTE_EJECUTADA, "el resultado ejecutó el paso"

    # 9) El contexto nunca tuvo el dato que la respuesta correcta exigía.
    if context_gap:
        return CONTEXTO_INSUFICIENTE, str(context_gap)

    return RESULTADO_INCORRECTO, "el resultado no coincide con lo esperado"
