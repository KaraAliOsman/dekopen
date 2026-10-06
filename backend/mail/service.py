"""Orquestación del outbox: resolver destinatarios + identidad, encolar la
fila materializada y despachar por el proveedor activo.

Los handlers de jobs llaman ``deliver_*`` dentro de su propia transacción
con claims de servicio — la fila mail_messages queda materializada ANTES
de enviarse y su status es la evidencia del resultado. ``flush_pending``
reintenta filas QUEUED/FAILED (management command mail_flush).
"""

from __future__ import annotations

import base64
import json
import logging
import os
from uuid import UUID

from django.conf import settings

from documents.brand import effective_brand_color
from documents.repository import one, rows
from mail import templates
from mail.providers import ProviderError, configured, from_address, get_provider

logger = logging.getLogger(__name__)

_STAFF_QUOTE_ROLES = ("OWNER", "ESTIMATOR")
_STAFF_WORKSHOP_ROLES = ("OWNER", "WORKSHOP_MANAGER")


def _frontend_origin() -> str:
    origin = (
        os.environ.get("FRONTEND_ORIGIN")
        or getattr(settings, "BILLING_FRONTEND_ORIGIN", "")
        or "http://localhost:5173"
    )
    return str(origin).rstrip("/")


def _project_url(project_id: object) -> str:
    return f"{_frontend_origin()}/projects/{project_id}"


def _workshop_url() -> str:
    return f"{_frontend_origin()}/production"


def staff_emails(*, org_id: UUID, roles: tuple[str, ...]) -> list[str]:
    """Emails de inicio de sesión del personal con esos roles en el org —
    el join con auth.users nunca sale del tenant: la membresía es el límite."""
    found = rows(
        "SELECT u.email::text AS email FROM public.tenancy_memberships m"
        " JOIN auth.users u ON u.id = m.user_id"
        " WHERE m.org_id = %s AND m.is_active AND m.role::text = ANY(%s)"
        " ORDER BY m.created_at",
        [str(org_id), list(roles)],
    )
    return [str(row["email"]) for row in found if row.get("email")]


def _org_mail_brand(*, org_id: UUID) -> dict[str, object]:
    """Identidad white-label para correos al cliente: nombre comercial (o
    razón social), color AA-verificado y línea de contacto. Sin logo URL —
    un enlace firmado caducaría dentro del correo archivado."""
    org = one(
        "SELECT name, commercial_name, brand_color, brand_address,"
        " brand_phone, brand_email FROM public.tenancy_organizations"
        " WHERE id = %s",
        [str(org_id)],
        "organization_not_found",
    )
    name = str(org.get("commercial_name") or org.get("name") or "")
    accent, _ = effective_brand_color(org.get("brand_color"))
    contact = " · ".join(
        part
        for part in (
            str(org.get("brand_address") or ""),
            str(org.get("brand_phone") or ""),
            str(org.get("brand_email") or ""),
        )
        if part
    )
    return {"org_name": name, "accent": accent, "org_contact": contact}


def _project_mail_row(*, org_id: UUID, project_id: UUID) -> dict[str, object]:
    # currency vive en tenancy_organizations — projects guarda los totales
    # en la moneda contable del org, nunca una columna propia.
    return one(
        "SELECT p.code, p.name, p.client_name, p.client_email, p.client_rut,"
        " p.total_price_gross::text AS total_gross, o.currency"
        " FROM public.projects p"
        " JOIN public.tenancy_organizations o ON o.id = p.org_id"
        " WHERE p.id = %s AND p.org_id = %s",
        [str(project_id), str(org_id)],
        "project_not_found",
    )


def _money_label(amount: object, currency: object) -> str | None:
    if amount in (None, ""):
        return None
    from decimal import Decimal, InvalidOperation

    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return None
    if str(currency or "") == "CLP":
        return f"$ {int(value):,}".replace(",", ".")
    return f"{currency or 'CLP'} {value}"


def _enqueue(
    *,
    org_id: UUID,
    audience: str,
    template: str,
    to_email: str,
    rendered: templates.RenderedMail,
    context: dict,
) -> dict:
    return one(
        "INSERT INTO public.mail_messages"
        " (org_id,audience,template,to_email,subject,html_body,text_body,context)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING *",
        [
            str(org_id),
            audience,
            template,
            to_email,
            rendered.subject,
            rendered.html,
            rendered.text,
            json.dumps(context),
        ],
    )


def _send_now(message: dict) -> dict:
    """Despacha una fila QUEUED/FAILED por el proveedor activo y sella el
    resultado en la misma fila — la bandeja es la evidencia."""
    try:
        outcome = get_provider().send(
            to=str(message["to_email"]),
            rendered=templates.RenderedMail(
                subject=str(message["subject"]),
                html=str(message["html_body"]),
                text=str(message["text_body"]),
            ),
        )
    except ProviderError as error:
        return one(
            "UPDATE public.mail_messages SET status='FAILED', attempts=attempts+1,"
            " error=%s WHERE id=%s RETURNING id,status",
            [str(error)[:400], str(message["id"])],
        )
    return one(
        "UPDATE public.mail_messages SET status='SENT', attempts=attempts+1,"
        " provider=%s, provider_ref=%s, sent_at=now(), error=NULL"
        " WHERE id=%s RETURNING id,status",
        [outcome.provider, outcome.ref[:255], str(message["id"])],
    )


def _deliver(
    *,
    org_id: UUID,
    audience: str,
    template: str,
    to_email: str,
    rendered: templates.RenderedMail,
    context: dict,
) -> dict:
    message = _enqueue(
        org_id=org_id,
        audience=audience,
        template=template,
        to_email=to_email,
        rendered=rendered,
        context=context,
    )
    result = _send_now(message)
    return {"id": str(message["id"]), "status": result["status"], "to": to_email}


def _deliver_to_staff(
    *, org_id: UUID, template: str, roles: tuple[str, ...], render, context: dict
) -> list[dict]:
    """Un correo interno por destinatario — la bandeja muestra a quién salió."""
    sent: list[dict] = []
    for email in staff_emails(org_id=org_id, roles=roles):
        sent.append(
            _deliver(
                org_id=org_id,
                audience="INTERNAL",
                template=template,
                to_email=email,
                rendered=render,
                context=context,
            )
        )
    return sent


# ——— Casos de uso (los llama el job handler con la tx y claims listos) ———


def deliver_quote_sent(*, org_id: UUID, project_id: UUID, token: str) -> dict:
    """Cliente: enlace de cotización. Sin email de cliente la fila queda
    SKIPPED — evidencia de que el evento no tenía destinatario."""
    project = _project_mail_row(org_id=org_id, project_id=project_id)
    client_email = str(project.get("client_email") or "").strip()
    portal_url = f"{_frontend_origin()}/cotizacion/{token}"
    context = {"project_id": str(project_id), "portal_url": portal_url}
    if not client_email:
        skipped = one(
            "INSERT INTO public.mail_messages"
            " (org_id,audience,template,to_email,subject,html_body,text_body,"
            "  status,error,context)"
            " VALUES (%s,'CLIENT','quote_sent','',%s,'','','SKIPPED',%s,%s::jsonb)"
            " RETURNING id,status",
            [
                str(org_id),
                f"Cotización {project.get('name')}",
                "El proyecto no tiene correo de cliente registrado.",
                json.dumps(context),
            ],
        )
        return {"id": str(skipped["id"]), "status": "SKIPPED"}
    brand = _org_mail_brand(org_id=org_id)
    rendered = templates.quote_sent(
        {
            **brand,
            "client_name": project.get("client_name") or "cliente",
            "project_name": f"{project.get('code') or ''} {project.get('name') or ''}".strip(),
            "project_code": project.get("code"),
            "portal_url": portal_url,
            "total_label": _money_label(project.get("total_gross"), project.get("currency")),
        }
    )
    return _deliver(
        org_id=org_id,
        audience="CLIENT",
        template="quote_sent",
        to_email=client_email,
        rendered=rendered,
        context=context,
    )


def deliver_quote_approved(*, org_id: UUID, project_id: UUID, decided_by: str) -> dict:
    project = _project_mail_row(org_id=org_id, project_id=project_id)
    rendered = templates.quote_approved(
        {
            "project_name": project.get("name"),
            "project_code": project.get("code"),
            "client_name": project.get("client_name"),
            "decided_by": decided_by,
            "total_label": _money_label(project.get("total_gross"), project.get("currency")),
            "project_url": _project_url(project_id),
        }
    )
    sent = _deliver_to_staff(
        org_id=org_id,
        template="quote_approved",
        roles=_STAFF_QUOTE_ROLES,
        render=rendered,
        context={"project_id": str(project_id), "decided_by": decided_by},
    )
    return {"sent": len(sent)}


def deliver_payment_received(*, org_id: UUID, project_id: UUID, payment_id: UUID) -> dict:
    project = _project_mail_row(org_id=org_id, project_id=project_id)
    payment = one(
        "SELECT amount, method::text AS method, kind::text AS kind"
        " FROM public.project_payments WHERE id = %s AND org_id = %s",
        [str(payment_id), str(org_id)],
        "payment_not_found",
    )
    balance_row = rows(
        "SELECT COALESCE(SUM(amount),0) AS collected FROM public.project_payments"
        " WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
        [str(org_id), str(project_id)],
    )
    total = project.get("total_gross")
    balance = None
    if total not in (None, ""):
        from decimal import Decimal

        balance = Decimal(str(total)) - Decimal(str(balance_row[0]["collected"]))
    rendered = templates.payment_received(
        {
            "project_name": project.get("name"),
            "project_code": project.get("code"),
            "amount_label": _money_label(payment.get("amount"), project.get("currency")),
            "method_label": payment.get("method"),
            "balance_label": _money_label(balance, project.get("currency")),
            "project_url": _project_url(project_id),
        }
    )
    sent = _deliver_to_staff(
        org_id=org_id,
        template="payment_received",
        roles=_STAFF_QUOTE_ROLES,
        render=rendered,
        context={"project_id": str(project_id), "payment_id": str(payment_id)},
    )
    return {"sent": len(sent)}


def deliver_pricing_decision(*, org_id: UUID, operation_id: UUID, outcome: str, decided_by: str) -> dict:
    """P07 — aviso al estimador que pidió la operación comercial."""
    operation = one(
        "SELECT o.id, o.reason, o.requested_by_email, o.requested_by,"
        " p.code AS project_code, p.name AS project_name, p.id AS project_id,"
        " p.total_price_net::text AS net"
        " FROM public.pricing_operations o"
        " JOIN public.projects p ON p.id=o.project_id AND p.org_id=o.org_id"
        " WHERE o.id=%s AND o.org_id=%s",
        [str(operation_id), str(org_id)],
        "pricing_operation_not_found",
    )
    recipient = str(operation.get("requested_by_email") or "").strip()
    context = {
        "operation_id": str(operation_id),
        "project_id": str(operation["project_id"]),
        "outcome": outcome,
        "decided_by": decided_by,
    }
    if not recipient:
        skipped = one(
            "INSERT INTO public.mail_messages"
            " (org_id,audience,template,to_email,subject,html_body,text_body,"
            "  status,error,context)"
            " VALUES (%s,'INTERNAL','pricing_decision','',%s,'','','SKIPPED',%s,%s::jsonb)"
            " RETURNING id,status",
            [
                str(org_id),
                f"Decisión de precios {operation.get('project_name')}",
                "La operación no registró correo del solicitante.",
                json.dumps(context),
            ],
        )
        return {"id": str(skipped["id"]), "status": "SKIPPED"}
    labels = {"APPLIED": "aprobada", "REJECTED": "rechazada", "WITHDRAWN": "retirada"}
    rendered = templates.pricing_decision(
        {
            "project_name": operation.get("project_name"),
            "project_code": operation.get("project_code"),
            "operation_label": outcome,
            "outcome_label": labels.get(outcome, outcome.lower()),
            "decided_by": decided_by,
            "net_label": operation.get("net"),
            "reason": operation.get("reason"),
            "pricing_url": f"{_frontend_origin()}/projects/{operation['project_id']}/pricing",
        }
    )
    return _deliver(
        org_id=org_id,
        audience="INTERNAL",
        template="pricing_decision",
        to_email=recipient,
        rendered=rendered,
        context=context,
    )


def deliver_step_blocked(
    *, org_id: UUID, order_id: UUID, step_label: str, note: str, actor_id: UUID | None
) -> dict:
    order = one(
        "SELECT order_code FROM public.orders WHERE id = %s AND org_id = %s",
        [str(order_id), str(org_id)],
        "order_not_found",
    )
    actor_label = "—"
    if actor_id is not None:
        actor = rows(
            "SELECT email::text AS email FROM auth.users WHERE id = %s",
            [str(actor_id)],
        )
        if actor:
            actor_label = str(actor[0]["email"])
    rendered = templates.work_order_blocked(
        {
            "order_code": order.get("order_code"),
            "step_label": step_label,
            "note": note,
            "actor_label": actor_label,
            "project_url": _workshop_url(),
        }
    )
    sent = _deliver_to_staff(
        org_id=org_id,
        template="work_order_blocked",
        roles=_STAFF_WORKSHOP_ROLES,
        render=rendered,
        context={"order_id": str(order_id)},
    )
    return {"sent": len(sent)}


def flush_pending(*, org_id: UUID | None = None, limit: int = 50) -> int:
    """Reintenta QUEUED/FAILED. mail_flush lo corre con claims del primer
    miembro activo del org de cada fila."""
    query = (
        "SELECT * FROM public.mail_messages WHERE status IN ('QUEUED','FAILED')"
        + (" AND org_id=%s" if org_id else "")
        + " ORDER BY created_at LIMIT %s"
    )
    params: list[object] = ([str(org_id)] if org_id else []) + [limit]
    pending = rows(query, params)
    sent = 0
    for message in pending:
        result = _send_now(message)
        if str(result["status"]) == "SENT":
            sent += 1
    return sent


def tray_status(*, org_id: UUID) -> dict[str, object]:
    counts = rows(
        "SELECT status, COUNT(*)::int AS n FROM public.mail_messages"
        " WHERE org_id=%s AND created_at > now() - interval '7 days'"
        " GROUP BY status",
        [str(org_id)],
    )
    by_status = {str(row["status"]): int(row["n"]) for row in counts}
    return {
        "provider": get_provider().name,
        "configured": configured(),
        "from_address": from_address(),
        "queued": by_status.get("QUEUED", 0),
        "sent_7d": by_status.get("SENT", 0),
        "failed_7d": by_status.get("FAILED", 0),
        "skipped_7d": by_status.get("SKIPPED", 0),
    }


def dev_previews(*, org_id: UUID) -> list[dict[str, str]]:
    """Las cinco plantillas renderizadas con la marca real de la org del
    llamante + datos de muestra — solo para /dev/correos (env-gated)."""
    brand = _org_mail_brand(org_id=org_id)
    sample_client = {
        **brand,
        "client_name": "María Soto",
        "project_name": "PRJ-014 · Casa Echeverría",
        "project_code": "PRJ-014",
        "portal_url": f"{_frontend_origin()}/cotizacion/muestra-dev",
        "total_label": "$ 1.435.471",
    }
    sample_internal = {
        "project_name": "Casa Echeverría",
        "project_code": "PRJ-014",
        "client_name": "María Soto",
        "decided_by": "María Soto · 12.345.678-9",
        "total_label": "$ 1.435.471",
        "amount_label": "$ 435.471",
        "method_label": "TRANSFER",
        "balance_label": "$ 1.000.000",
        "order_code": "OT-0007",
        "step_label": "Corte de perfiles",
        "note": "Falta herraje RH-110 — proveedor despacha el jueves.",
        "actor_label": "jefe.taller@fabricante.cl",
        "project_url": _workshop_url(),
    }
    renders = [
        ("magic_link", templates.magic_link({})),
        ("quote_sent", templates.quote_sent(sample_client)),
        ("quote_approved", templates.quote_approved(sample_internal)),
        ("payment_received", templates.payment_received(sample_internal)),
        ("work_order_blocked", templates.work_order_blocked(sample_internal)),
    ]
    previews: list[dict[str, str]] = []
    for key, rendered in renders:
        # En la vista previa el navegador no resuelve adjuntos CID — la marca
        # interna viaja embebida como data URI para que el iframe la dibuje.
        html = rendered.html
        for cid, content in rendered.inline_images.items():
            uri = "data:image/png;base64," + base64.b64encode(content).decode()
            html = html.replace(f"cid:{cid}", uri)
        previews.append(
            {
                "template": key,
                "audience": "CLIENT" if key == "quote_sent" else "INTERNAL",
                "subject": rendered.subject,
                "html": html,
                "text": rendered.text,
            }
        )
    return previews


__all__ = [
    "deliver_payment_received",
    "deliver_pricing_decision",
    "deliver_quote_approved",
    "deliver_quote_sent",
    "deliver_step_blocked",
    "dev_previews",
    "flush_pending",
    "staff_emails",
    "tray_status",
]
