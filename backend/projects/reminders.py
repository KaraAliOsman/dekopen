"""Recordatorio de cobranza — IA prepara el mensaje, el humano decide enviarlo.

El borrador se genera por la ruta ``collection_reminder`` del ai_gateway
(anclada a MIMO como toda ruta — ver ``ai_routes``): la invocación queda
auditada en ``ai_audit_logs`` y el texto se ofrece como borrador. Enviar
es una acción distinta y explícita — un clic del usuario encola el correo
al cliente por la bandeja de salida; nada se envía jamás desde la
preparación.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from ai_gateway import service as gateway
from authentication.errors import contract_error
from documents.repository import documentary_backend
from mail import service as mail_service
from mail import templates
from pricing.repository import rows
from projects import org_branding
from projects.service import project_row

CAPABILITY = "collection_reminder"

_SYSTEM = """Eres la voz comercial de una empresa de ventanas. Redactas el
recordatorio de pago que el dueño envía a su cliente. Reglas:

- Español de Chile, trato de «usted», tono cordial y directo — se cobra sin
  avergonzar.
- Cita el proyecto por su nombre y código, el monto adeudado y la moneda.
- Nunca inventes fechas, montos ni promesas de descuento; usa sólo los datos
  de entrada.
- Firma con el nombre de la empresa, no con el del sistema.
- Responde JSON: {"subject": string, "body": string} — el cuerpo en párrafos
  separados por líneas en blanco, sin HTML."""


def _pending_facts(*, org_id: UUID, project_id: UUID) -> dict:
    """Los números del recordatorio salen del ledger sellado — la IA recibe
    hechos, nunca los calcula."""
    with documentary_backend():
        collected = rows(
            "SELECT COALESCE(SUM(amount),0) AS collected FROM public.project_payments "
            "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
            [str(org_id), str(project_id)],
        )[0]["collected"]
        delivery = rows(
            "SELECT d.scheduled_date, d.status FROM public.deliveries d "
            "JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id "
            "WHERE o.org_id=%s AND o.project_id=%s "
            "ORDER BY d.scheduled_date DESC LIMIT 1",
            [str(org_id), str(project_id)],
        )
        versions = rows(
            "SELECT snapshot_json::text AS snapshot_json "
            "FROM public.project_versions "
            "WHERE org_id=%s AND project_id=%s ORDER BY emitted_at DESC,id DESC LIMIT 1",
            [str(org_id), str(project_id)],
        )
    total = currency = terms = None
    if versions:
        snapshot = versions[0]["snapshot_json"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        sealed = snapshot.get("project") if isinstance(snapshot, dict) else None
        if sealed:
            total = sealed.get("total_price_gross")
            currency = sealed.get("currency") or "CLP"
            terms = sealed.get("payment_terms")
    if total is None:
        raise contract_error(
            422,
            "reminder_requires_deal",
            "El proyecto no tiene un trato sellado para cobrar.",
        )
    balance = Decimal(str(total)) - Decimal(str(collected))
    if balance <= 0:
        raise contract_error(
            409,
            "reminder_no_balance",
            "El proyecto no tiene saldo pendiente que recordar.",
        )
    return {
        "balance": balance,
        "collected": Decimal(str(collected)),
        "total": Decimal(str(total)),
        "currency": currency or "CLP",
        "payment_terms": terms,
        "delivery_date": (
            str(delivery[0]["scheduled_date"]) if delivery else None
        ),
        "delivery_status": delivery[0]["status"] if delivery else None,
    }


def latest_draft(*, org_id: UUID, project_id: UUID) -> dict | None:
    """El último borrador auditado de este proyecto — leído de la bitácora,
    nunca re-invocando (preparar de nuevo es un clic consciente)."""
    with documentary_backend():
        found = rows(
            "SELECT output_payload, model_used, created_at "
            "FROM public.ai_audit_logs "
            "WHERE org_id=%s AND tool_name=%s "
            "AND input_payload->>'project_id' = %s "
            "AND state_hash_before IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 1",
            [str(org_id), CAPABILITY, str(project_id)],
        )
    if not found:
        return None
    output = found[0]["output_payload"]
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return None
    if not isinstance(output, dict):
        return None
    subject, body = output.get("subject"), output.get("body")
    if not subject or not body:
        return None
    return {
        "subject": str(subject),
        "body": str(body),
        "model": found[0]["model_used"],
        "created_at": found[0]["created_at"].isoformat()
        if hasattr(found[0]["created_at"], "isoformat")
        else found[0]["created_at"],
    }


def draft_reminder(
    *, org_id: UUID, project_id: UUID, actor_id: UUID, operation_key: str
) -> dict:
    """Prepara el mensaje con la ruta IA configurada. Sólo prepara — el
    retorno es el borrador en pantalla; el envío vive en ``send_reminder``."""
    project = project_row(org_id, project_id)
    facts = _pending_facts(org_id=org_id, project_id=project_id)
    branding = org_branding.branding_for_snapshot(org_id=org_id)
    envelope = gateway.invoke(
        org_id=org_id,
        user_id=actor_id,
        capability=CAPABILITY,
        operation_key=operation_key,
        tool_name=CAPABILITY,
        provider_options={"system": _SYSTEM, "json_output": True},
        input_payload={
            "project_id": str(project_id),
            "project_code": project["code"],
            "project_name": project["name"],
            "client_name": project["client_name"],
            "client_email": project.get("client_email"),
            "amount_due": str(facts["balance"]),
            "currency": facts["currency"],
            "total": str(facts["total"]),
            "collected": str(facts["collected"]),
            "payment_terms": facts["payment_terms"],
            "delivery_date": facts["delivery_date"],
            "company_name": branding.get("name"),
        },
    )
    try:
        document = json.loads(envelope["output"])
    except (json.JSONDecodeError, TypeError):
        raise contract_error(
            502,
            "collection_reminder_bad_output",
            "La respuesta del asistente no fue un mensaje válido.",
        ) from None
    subject = str(document.get("subject") or "").strip()
    body = str(document.get("body") or "").strip()
    if not subject or not body:
        raise contract_error(
            502,
            "collection_reminder_bad_output",
            "La respuesta del asistente no fue un mensaje válido.",
        )
    return {
        "subject": subject[:200],
        "body": body[:4000],
        "model": envelope["model"],
        "audit_id": envelope["audit_id"],
        "credits_debited": envelope["credits_debited"],
        "client_email": project.get("client_email"),
        "amount_due": str(facts["balance"]),
        "currency": facts["currency"],
    }


def send_reminder(
    *,
    org_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    subject: str,
    body: str,
) -> dict:
    """El clic que envía: encola el correo al cliente por la bandeja de
    salida — la fila mail_messages es la evidencia del envío."""
    project = project_row(org_id, project_id)
    to_email = str(project.get("client_email") or "").strip()
    if not to_email:
        raise contract_error(
            422,
            "reminder_no_client_email",
            "El proyecto no tiene correo de cliente registrado.",
        )
    subject = (subject or "").strip()[:200]
    body = (body or "").strip()
    if not subject or not body:
        raise contract_error(
            422,
            "reminder_empty",
            "El mensaje no puede ir vacío — prepáralo primero.",
        )
    rendered = templates.RenderedMail(
        subject=subject,
        html="",
        text=body,
    )
    with transaction.atomic(), documentary_backend():
        result = mail_service.deliver_client_message(
            org_id=org_id,
            to_email=to_email,
            rendered=rendered,
            template="collection_reminder",
            context={
                "project_id": str(project_id),
                "project_code": project["code"],
                "sent_by": str(actor_id),
                "sent_at": timezone.now().isoformat(),
            },
        )
    return {
        "status": result["status"],
        "to": to_email,
        "mail_id": str(result["id"]) if result.get("id") else None,
    }
