"""Job handlers del outbox de correo — el lado durable de los cinco
transaccionales. Cada handler re-lee el estado comprometido dentro de su
transacción con claims del actor del evento; el provider por defecto es
sandbox, SMTP se activa por configuración (docs/ACTIVACION.md)."""

from __future__ import annotations

import json
from typing import Any

from django.db import connection, transaction

from documents.repository import DocumentaryError, documentary_backend
from jobs.handlers import _claims_for
from jobs.registry import JobContext, JobPermanentError, ProgressReporter, register
from mail import service
from mail.serializers import (
    PaymentReceivedSerializer,
    QuoteApprovedSerializer,
    QuoteSentSerializer,
    StepBlockedSerializer,
)

_MAIL_ROLES = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")


def _set_claims(context: JobContext) -> None:
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
    _set_claims(context)
    try:
        with transaction.atomic(), documentary_backend():
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
    _set_claims(context)
    try:
        with transaction.atomic(), documentary_backend():
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
    _set_claims(context)
    try:
        with transaction.atomic(), documentary_backend():
            return service.deliver_payment_received(
                org_id=context.org_id,
                project_id=payload["project_id"],
                payment_id=payload["payment_id"],
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
    _set_claims(context)
    try:
        with transaction.atomic(), documentary_backend():
            return service.deliver_step_blocked(
                org_id=context.org_id,
                order_id=payload["order_id"],
                step_label=str(payload["step_label"]),
                note=str(payload["note"]),
                actor_id=context.created_by,
            )
    except DocumentaryError as error:
        raise JobPermanentError(error.code) from error
