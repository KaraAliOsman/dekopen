"""Job handlers del outbox de correo — el lado durable de los cinco
transaccionales. Cada handler re-lee el estado comprometido dentro de su
transacción con claims del actor del evento; el provider por defecto es
sandbox, SMTP se activa por configuración (docs/ACTIVACION.md)."""

from __future__ import annotations

import json
from typing import Any

from django.db import connection, transaction

from documents.repository import DocumentaryError, documentary_backend, rows
from jobs.handlers import _claims_for
from jobs.registry import JobContext, JobPermanentError, ProgressReporter, register
from mail import service
from mail.serializers import (
    PaymentReceivedSerializer,
    PricingDecisionSerializer,
    QuoteApprovedSerializer,
    QuoteSentSerializer,
    StepBlockedSerializer,
)

_MAIL_ROLES = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")


def _set_claims(context: JobContext) -> None:
    """GUC transaccional con los claims del actor — DEBE llamarse dentro del
    transaction.atomic(): set_config(is_local=true) fuera de la transacción
    muere con el statement (autocommit) y las políticas RLS de mail_messages
    rechazan con 42501."""
    if context.created_by is None:
        raise JobPermanentError("mail_actor_required")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            [json.dumps(_claims_for(str(context.created_by), context))],
        )


@register(
    "mail.quote_sent",
    roles=_MAIL_ROLES,
    payload_serializer=QuoteSentSerializer,
    label="Correo de cotización al cliente",
)
def quote_sent(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    try:
        with transaction.atomic(), documentary_backend():
            _set_claims(context)
            return service.deliver_quote_sent(
                org_id=context.org_id,
                project_id=payload["project_id"],
                token=str(payload["token"]),
            )
    except DocumentaryError as error:
        # Entidad ausente o estado inválido no se cura reintentando.
        raise JobPermanentError(error.code) from error


@register(
    "mail.quote_approved",
    roles=_MAIL_ROLES,
    payload_serializer=QuoteApprovedSerializer,
    label="Aviso interno: cotización aprobada",
)
def quote_approved(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    try:
        with transaction.atomic(), documentary_backend():
            _set_claims(context)
            return service.deliver_quote_approved(
                org_id=context.org_id,
                project_id=payload["project_id"],
                decided_by=str(payload["decided_by"]),
            )
    except DocumentaryError as error:
        raise JobPermanentError(error.code) from error


@register(
    "mail.payment_received",
    roles=_MAIL_ROLES,
    payload_serializer=PaymentReceivedSerializer,
    label="Aviso interno: pago registrado",
)
def payment_received(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    try:
        with transaction.atomic(), documentary_backend():
            _set_claims(context)
            return service.deliver_payment_received(
                org_id=context.org_id,
                project_id=payload["project_id"],
                payment_id=payload["payment_id"],
            )
    except DocumentaryError as error:
        raise JobPermanentError(error.code) from error


@register(
    "mail.pricing_decision",
    roles=_MAIL_ROLES,
    payload_serializer=PricingDecisionSerializer,
    label="Aviso al solicitante: decisión de precios",
)
def pricing_decision(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    actor_label = "el equipo"
    if context.created_by is not None:
        found = rows(
            "SELECT email::text AS email FROM auth.users WHERE id = %s",
            [str(context.created_by)],
        )
        if found:
            actor_label = str(found[0]["email"])
    try:
        with transaction.atomic(), documentary_backend():
            _set_claims(context)
            return service.deliver_pricing_decision(
                org_id=context.org_id,
                operation_id=payload["operation_id"],
                outcome=str(payload["outcome"]),
                decided_by=actor_label,
            )
    except DocumentaryError as error:
        raise JobPermanentError(error.code) from error


@register(
    "mail.step_blocked",
    roles=_MAIL_ROLES,
    payload_serializer=StepBlockedSerializer,
    label="Aviso interno: OT bloqueada",
)
def step_blocked(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    try:
        with transaction.atomic(), documentary_backend():
            _set_claims(context)
            return service.deliver_step_blocked(
                org_id=context.org_id,
                order_id=payload["order_id"],
                step_label=str(payload["step_label"]),
                note=str(payload["note"]),
                actor_id=context.created_by,
            )
    except DocumentaryError as error:
        raise JobPermanentError(error.code) from error
