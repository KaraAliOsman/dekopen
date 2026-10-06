"""Cobranza ledger for a project's commercial deal.

Payments are recorded by the sales side against the deal amount (the latest
sealed revision's gross total, else the live project totals). Recording is
idempotent on (org_id, operation_key) and a mistake is voided, never deleted —
the ledger keeps the full history.
"""

import json
import re
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from authentication.errors import contract_error
from documents.repository import documentary_backend
from pricing.repository import rows
from projects import sii
from projects import reminders
from projects.receipts import _receipt_public, issue_receipt
from projects.service import project_row


# ── Calendario de cobranza ───────────────────────────────────────────────
# El calendario se deriva del acuerdo sellado (condiciones comerciales de la
# revisión emitida): «50% anticipo, 50% contra entrega» produce dos cuotas —
# anticipo al aprobar y saldo contra la fecha de entrega programada. El
# porcentaje por defecto es el §11 de la Constitución y el patrón que el
# fixture siembra; unas condiciones distintas («30% anticipo») se respetan
# cuando declaran el porcentaje explícito.

def _anticipo_pct(payment_terms) -> tuple[Decimal, str]:
    """«N% anticipo» en las condiciones manda; si no, el default §11 (50%)."""
    if payment_terms:
        found = re.search(r"(\d{1,3})\s*%(?=[^%]*anticipo)", str(payment_terms).lower())
        if found:
            pct = Decimal(found.group(1))
            if Decimal("0") < pct <= Decimal("100"):
                return pct, "terms"
    return Decimal("50"), "default"


def _schedule(
    *,
    org_id: UUID,
    project_id: UUID,
    deal: dict | None,
    payments: list,
    payment_terms,
) -> list[dict]:
    """Cuotas del acuerdo sellado con monto, cubierto y vencimiento.

    Un pago cubre primero la cuota de su propio tipo y lo que sobre se
    lleva a la otra abierta — así un anticipo mayor al pactado amortigua
    el saldo y un pago SALDO nunca tapa un anticipo vencido.
    """
    if deal is None or deal.get("sealed_revision") is None:
        return []
    gross = deal["total"]
    pct, source = _anticipo_pct(payment_terms)
    anticipo = (gross * pct / Decimal("100")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    saldo = gross - anticipo
    today = timezone.localdate()
    with documentary_backend():
        approval = rows(
            "SELECT decided_at FROM public.customer_approvals "
            "WHERE org_id=%s AND project_id=%s AND status='APPROVED' "
            "ORDER BY decided_at DESC LIMIT 1",
            [str(org_id), str(project_id)],
        )
        emitted = rows(
            "SELECT emitted_at FROM public.project_versions "
            "WHERE org_id=%s AND project_id=%s ORDER BY emitted_at DESC,id DESC LIMIT 1",
            [str(org_id), str(project_id)],
        )
        delivery = rows(
            "SELECT d.scheduled_date, d.status, o.order_type::text AS order_type "
            "FROM public.deliveries d "
            "JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id "
            "WHERE o.org_id=%s AND o.project_id=%s "
            "ORDER BY d.scheduled_date DESC",
            [str(org_id), str(project_id)],
        )
    # Anticipo vence al aprobar (decisión del cliente) o a la emisión si aún
    # no hay aprobación registrada.
    anticipo_due = None
    if approval and approval[0].get("decided_at"):
        anticipo_due = approval[0]["decided_at"]
    elif emitted and emitted[0].get("emitted_at"):
        anticipo_due = emitted[0]["emitted_at"]
    anticipo_due_date = (
        anticipo_due.date() if hasattr(anticipo_due, "date") else anticipo_due
    )
    # Saldo vence con la entrega: la próxima fecha programada si existe, la
    # última entregada si ya salió, o sin fecha (la cuota no se vence sin
    # entrega programada — «contra entrega» es el ancla declarativa).
    saldo_due = None
    pending_delivery = [
        d for d in delivery if d["status"] in ("SCHEDULED", "ON_ROUTE", "FAILED")
    ]
    delivered = [d for d in delivery if d["status"] == "DELIVERED"]
    if pending_delivery:
        saldo_due = min(d["scheduled_date"] for d in pending_delivery)
    elif delivered:
        saldo_due = delivered[0]["scheduled_date"]

    def _covers() -> tuple[Decimal, Decimal]:
        """(cubierto_anticipo, cubierto_saldo) repartiendo cada pago."""
        covered_a = Decimal("0")
        covered_s = Decimal("0")
        for payment in payments:
            if payment["voided_at"] is not None:
                continue
            amount = Decimal(str(payment["amount"]))
            kind = str(payment["kind"])
            if kind == "SALDO":
                take = min(amount, saldo - covered_s)
                covered_s += take
                covered_a += min(amount - take, anticipo - covered_a)
            else:
                # ANTICIPO y PARCIAL cubren la cuota más antigua primero.
                take = min(amount, anticipo - covered_a)
                covered_a += take
                covered_s += min(amount - take, saldo - covered_s)
        return covered_a, covered_s

    covered_a, covered_s = _covers()

    def _state(amount, covered, due) -> str:
        if covered >= amount:
            return "PAID"
        if due is not None and due < today:
            return "OVERDUE"
        return "PENDING"

    return [
        {
            "key": "ANTICIPO",
            "amount": str(anticipo),
            "covered": str(covered_a),
            "due_at": anticipo_due_date.isoformat()
            if hasattr(anticipo_due_date, "isoformat")
            else anticipo_due_date,
            "due_basis": "al aprobar",
            "pct_source": source,
            "pct": str(pct),
            "state": _state(anticipo, covered_a, anticipo_due_date),
        },
        {
            "key": "SALDO",
            "amount": str(saldo),
            "covered": str(covered_s),
            "due_at": saldo_due.isoformat() if saldo_due else None,
            "due_basis": "contra entrega",
            "pct_source": source,
            "pct": str(Decimal("100") - pct),
            "state": _state(saldo, covered_s, saldo_due),
        },
    ]


def _movements(org_id: UUID, project_id: UUID) -> list[dict]:
    """Línea de tiempo de la cobranza: cada movimiento con su actor y su
    documento respaldo — la aplicación F6 a los saldos."""
    with documentary_backend():
        found = rows(
            """
            SELECT /* p11_movements */ 'payment' AS type, p.id, p.kind,
                   p.amount, p.method,
                   p.voided_at IS NOT NULL AS voided, p.recorded_at AS at,
                   private.user_email(p.recorded_by) AS actor,
                   r.receipt_code AS code, r.id AS document_id
            FROM public.project_payments p
            LEFT JOIN public.payment_receipts r ON r.payment_id = p.id
            WHERE p.org_id=%s AND p.project_id=%s
            UNION ALL
            SELECT 'payment_void', p.id, p.kind, p.amount, p.method,
                   TRUE, p.voided_at, private.user_email(p.voided_by),
                   r.receipt_code, r.id
            FROM public.project_payments p
            LEFT JOIN public.payment_receipts r ON r.payment_id = p.id
            WHERE p.org_id=%s AND p.project_id=%s AND p.voided_at IS NOT NULL
            UNION ALL
            SELECT 'link', l.id, l.kind, l.amount, NULL, FALSE,
                   l.created_at, private.user_email(l.created_by),
                   l.status, NULL
            FROM public.project_payment_links l
            WHERE l.org_id=%s AND l.project_id=%s
            UNION ALL
            SELECT 'invoice', i.id, NULL, NULL, NULL, FALSE, i.created_at,
                   private.user_email(i.created_by), i.invoice_code, i.id
            FROM public.project_invoices i
            WHERE i.org_id=%s AND i.project_id=%s
            UNION ALL
            SELECT 'credit_note', n.id, NULL, NULL, NULL, FALSE, n.created_at,
                   private.user_email(n.created_by), n.credit_code, n.id
            FROM public.project_credit_notes n
            WHERE n.org_id=%s AND n.project_id=%s
            UNION ALL
            SELECT 'envio', e.id, NULL, NULL, NULL, FALSE,
                   COALESCE(e.sent_at, e.created_at),
                   NULL, e.status::text, NULL
            FROM public.sii_envios e
            WHERE e.org_id=%s AND e.project_id=%s
            ORDER BY 7 DESC
            """,
            [
                str(org_id), str(project_id),
                str(org_id), str(project_id),
                str(org_id), str(project_id),
                str(org_id), str(project_id),
                str(org_id), str(project_id),
                str(org_id), str(project_id),
            ],
        )
    return [
        {
            "type": row["type"],
            "id": str(row["id"]),
            "kind": row["kind"],
            "amount": str(row["amount"]) if row["amount"] is not None else None,
            "method": row["method"],
            "voided": bool(row["voided"]),
            "at": row["at"].isoformat()
            if hasattr(row["at"], "isoformat")
            else row["at"],
            "actor": row["actor"],
            "code": row["code"],
            "document_id": str(row["document_id"]) if row["document_id"] else None,
        }
        for row in found
    ]


def _sii_summary(org_id: UUID) -> dict:
    """Estado tributario honesto de la organización para la superficie de
    cobranza — la misma verdad que decide la leyenda en los PDF."""
    from projects import sii_envio

    return sii_envio.integration_state(org_id=org_id)


def _payment_public(row, receipt=None):
    return {
        "id": str(row["id"]),
        "receipt_id": str(receipt["id"]) if receipt else None,
        "receipt_code": receipt["receipt_code"] if receipt else None,
        "kind": row["kind"],
        "amount": str(row["amount"]),
        "method": row["method"],
        "reference": row["reference"],
        "note": row["note"],
        "recorded_by": str(row["recorded_by"]) if row["recorded_by"] else None,
        "recorded_at": row["recorded_at"].isoformat()
        if hasattr(row["recorded_at"], "isoformat")
        else row["recorded_at"],
        "voided_at": row["voided_at"].isoformat()
        if row["voided_at"] and hasattr(row["voided_at"], "isoformat")
        else row["voided_at"],
        "void_reason": row["void_reason"],
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
    }


def _deal(org_id: UUID, project_id: UUID, project: dict) -> dict | None:
    """The commercial deal: latest sealed revision's gross total and currency,
    else live totals when an applied pricing authority proves the project was
    priced. Zero-valued live totals without that authority are not a deal."""
    with documentary_backend():
        versions = rows(
            "SELECT revision_code,snapshot_json::text AS snapshot_json "
            "FROM public.project_versions "
            "WHERE org_id=%s AND project_id=%s ORDER BY emitted_at DESC,id DESC LIMIT 1",
            [str(org_id), str(project_id)],
        )
    if versions:
        snapshot = versions[0]["snapshot_json"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        sealed_project = snapshot.get("project") if isinstance(snapshot, dict) else None
        gross = (sealed_project or {}).get("total_price_gross")
        if gross is not None:
            return {
                "total": Decimal(str(gross)),
                "currency": (sealed_project or {}).get("currency") or "CLP",
                "sealed_revision": versions[0]["revision_code"],
                "payment_terms": (sealed_project or {}).get("payment_terms"),
            }
    with documentary_backend():
        applied = rows(
            "SELECT currency FROM private.applied_pricing_currency(%s,%s)",
            [str(org_id), str(project_id)],
        )
        if not applied:
            return None
        org = rows(
            "SELECT currency FROM public.tenancy_organizations WHERE id=%s", [str(org_id)]
        )
    return {
        "total": Decimal(str(project["total_price_gross"])),
        "currency": applied[0]["currency"] or (org[0]["currency"] if org else "CLP"),
        "sealed_revision": None,
    }


def _summary(org_id: UUID, project_id: UUID, project: dict) -> dict:
    with documentary_backend():
        payments = rows(
            "SELECT * FROM public.project_payments "
            "WHERE org_id=%s AND project_id=%s ORDER BY recorded_at,id",
            [str(org_id), str(project_id)],
        )
        receipts = {
            str(receipt["payment_id"]): receipt
            for receipt in rows(
                "SELECT id,payment_id,receipt_code FROM public.payment_receipts "
                "WHERE org_id=%s AND project_id=%s",
                [str(org_id), str(project_id)],
            )
        }
        credit_notes = {
            str(note["invoice_id"]): {
                "id": str(note["id"]),
                "credit_code": note["credit_code"],
                "invoice_id": str(note["invoice_id"]),
                "created_at": note["created_at"].isoformat()
                if hasattr(note["created_at"], "isoformat")
                else note["created_at"],
            }
            for note in rows(
                "SELECT id,invoice_id,credit_code,created_at "
                "FROM public.project_credit_notes "
                "WHERE org_id=%s AND project_id=%s",
                [str(org_id), str(project_id)],
            )
        }
        dtes = sii.dtes_by_invoice(org_id=org_id, project_id=project_id)
        credit_dtes = sii.dtes_by_credit_note(org_id=org_id, project_id=project_id)
        # The cobranza row is where the envío chip and resubmit live — the
        # summary must carry the same envío badge the invoice listing builds.
        # Queried through this module's rows so the read stays under the
        # caller's claims (and the unit-test stubbing seam).
        envios = {
            str(row["invoice_id"]): {
                "id": str(row["id"]),
                "status": row["status"],
                "track_id": row["track_id"],
                "attempted": bool(row["attempted"]),
            }
            for row in rows(
                "SELECT e.id, e.status, e.track_id, d.invoice_id, "
                "(e.payload_json->'submit_attempted_at' IS NOT NULL) AS attempted "
                "FROM public.sii_envios e "
                "JOIN public.project_dtes d ON d.id = e.dte_id "
                "WHERE e.org_id=%s AND e.project_id=%s AND d.credit_note_id IS NULL",
                [str(org_id), str(project_id)],
            )
        }
        def _invoice_deal(invoice: dict) -> dict:
            payload = (
                invoice["payload_json"]
                if isinstance(invoice["payload_json"], dict)
                else json.loads(invoice["payload_json"])
            )
            return (payload or {}).get("deal") or {}

        invoices = [
            {
                "id": str(invoice["id"]),
                "invoice_code": invoice["invoice_code"],
                "project_id": str(project_id),
                "revision_code": (
                    invoice["payload_json"]
                    if isinstance(invoice["payload_json"], dict)
                    else json.loads(invoice["payload_json"])
                ).get("revision_code"),
                # Neto/IVA/Total explícitos — las mismas cifras selladas en
                # el PDF, para que la lista no obligue a abrir el documento.
                "total_net": _invoice_deal(invoice).get("total_net"),
                "total_tax": _invoice_deal(invoice).get("total_tax"),
                "total_gross": _invoice_deal(invoice).get("total_gross"),
                "credit_note": {
                    **credit_notes[str(invoice["id"])],
                    "invoice_code": invoice["invoice_code"],
                    "project_id": str(project_id),
                    "dte": credit_dtes.get(credit_notes[str(invoice["id"])]["id"]),
                }
                if str(invoice["id"]) in credit_notes
                else None,
                "dte": (
                    {**dtes[str(invoice["id"])], "envio": envios.get(str(invoice["id"]))}
                    if str(invoice["id"]) in dtes
                    else None
                ),
                "created_at": invoice["created_at"].isoformat()
                if hasattr(invoice["created_at"], "isoformat")
                else invoice["created_at"],
            }
            for invoice in rows(
                "SELECT id,invoice_code,payload_json::text AS payload_json,created_at "
                "FROM public.project_invoices "
                "WHERE org_id=%s AND project_id=%s ORDER BY created_at,id",
                [str(org_id), str(project_id)],
            )
        ]
    collected = sum(
        (Decimal(str(p["amount"])) for p in payments if p["voided_at"] is None),
        Decimal("0"),
    )
    deal = _deal(org_id, project_id, project)
    total = deal["total"] if deal else None
    balance = (total - collected) if total is not None else None
    if deal is None:
        status = "NO_DEAL"
    elif collected <= 0:
        status = "PENDING"
    elif balance > 0:
        status = "PARTIAL"
    else:
        status = "PAID"
    return {
        "payments": [
            _payment_public(p, receipts.get(str(p["id"]))) for p in payments
        ],
        "invoices": invoices,
        "schedule": _schedule(
            org_id=org_id,
            project_id=project_id,
            deal=deal,
            payments=payments,
            payment_terms=(deal or {}).get("payment_terms"),
        ),
        "movements": _movements(org_id, project_id),
        "sii": _sii_summary(org_id),
        "reminder": reminders.latest_draft(org_id=org_id, project_id=project_id),
        "collected": str(collected),
        "quote_total_gross": str(total) if total is not None else None,
        "balance": str(balance) if balance is not None else None,
        "currency": deal["currency"] if deal else "CLP",
        "status": status,
        "sealed_revision": deal["sealed_revision"] if deal else None,
    }


def list_payments(*, org_id: UUID, project_id: UUID) -> dict:
    project = project_row(org_id, project_id)
    return _summary(org_id, project_id, project)


def resolve_or_insert_payment(
    *,
    org_id: UUID,
    project_id: UUID,
    project: dict,
    actor_id: UUID,
    data: dict,
) -> tuple[dict, dict | None]:
    """The shared cobranza ledger primitive: replay the
    ``(org_id, operation_key)`` row with a cross-project guard, else validate
    the deal, currency and recorded_at and insert. Cross-domain flows that
    must settle a payment inside their own transaction (e.g. the POD cobro)
    call this instead of re-implementing the rules.

    Returns ``(payment_row, deal)``; ``deal`` is ``None`` on replay since the
    recorded row is returned even when the deal later reset.
    """
    existing = rows(
        "SELECT * FROM public.project_payments WHERE org_id=%s AND operation_key=%s",
        [str(org_id), data["operation_key"]],
    )
    if existing:
        payment = existing[0]
        if str(payment["project_id"]) != str(project_id):
            raise contract_error(
                409,
                "payment_operation_conflict",
                "La operación ya fue registrada en otro proyecto.",
            )
        return payment, None
    deal = _deal(org_id, project_id, project)
    if deal is None:
        raise contract_error(
            422,
            "payment_requires_deal",
            "Registra cobros solo sobre un proyecto cotizado.",
        )
    # The deal must be sealed before money moves — a receipt that freezes
    # live totals can be silently re-priced under the client's feet (F18).
    if deal["sealed_revision"] is None:
        raise contract_error(
            422,
            "payment_requires_sealed_deal",
            "Emite una revisión de cotización antes de registrar cobros.",
        )
    if deal["currency"] == "CLP" and data["amount"] != data[
        "amount"
    ].to_integral_value():
        raise contract_error(
            422,
            "payment_fractional_currency",
            "Los montos en CLP no llevan decimales.",
        )
    recorded_at = data.get("recorded_at")
    if recorded_at is not None and recorded_at > timezone.now():
        raise contract_error(
            422,
            "payment_recorded_in_future",
            "La fecha del cobro no puede ser futura.",
        )
    # Over-collection guard: a payment must fit inside the outstanding
    # balance — the ledger flips PAID on collected >= total and would
    # silently absorb the excess otherwise (F19).
    collected_rows = rows(
        "SELECT COALESCE(SUM(amount), 0) AS collected FROM public.project_payments "
        "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
        [str(org_id), str(project_id)],
    )
    balance = deal["total"] - Decimal(str(collected_rows[0]["collected"]))
    if Decimal(str(data["amount"])) > balance:
        raise contract_error(
            422,
            "payment_exceeds_balance",
            "El cobro supera el saldo pendiente del proyecto.",
        )
    payment = rows(
        "INSERT INTO public.project_payments"
        "(org_id,project_id,operation_key,kind,amount,method,reference,note,"
        " recorded_by,recorded_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (org_id, operation_key) DO NOTHING RETURNING *",
        [
            str(org_id),
            str(project_id),
            data["operation_key"],
            data["kind"],
            data["amount"],
            data["method"],
            data.get("reference") or None,
            data.get("note") or None,
            str(actor_id),
            data.get("recorded_at") or timezone.now(),
        ],
    )
    if not payment:
        # Lost race — the unique key converges on one row.
        payment = rows(
            "SELECT * FROM public.project_payments WHERE org_id=%s AND operation_key=%s",
            [str(org_id), data["operation_key"]],
        )
    payment = payment[0]
    if str(payment["project_id"]) != str(project_id):
        raise contract_error(
            409,
            "payment_operation_conflict",
            "La operación ya fue registrada en otro proyecto.",
        )
    return payment, deal


def record_payment(*, org_id: UUID, project_id: UUID, actor_id: UUID, data: dict) -> dict:
    with transaction.atomic():
        # Same lock order as pricing reset: the project row is the concurrency
        # point so a retired deal can never slip between the check and the insert.
        project = project_row(org_id, project_id, lock=True)
        with documentary_backend():
            payment, deal = resolve_or_insert_payment(
                org_id=org_id,
                project_id=project_id,
                project=project,
                actor_id=actor_id,
                data=data,
            )
            if deal is None:
                # Replay returns the recorded row even if the deal later reset.
                receipt = rows(
                    "SELECT * FROM public.payment_receipts WHERE payment_id=%s AND org_id=%s",
                    [str(payment["id"]), str(org_id)],
                )
                receipt_row = receipt[0] if receipt else None
                return {
                    "payment": _payment_public(payment, receipt_row),
                    "receipt": _receipt_public(receipt_row) if receipt_row else None,
                    **_summary(org_id, project_id, project),
                }
            receipt = issue_receipt(
                org_id=org_id,
                project=project,
                payment=payment,
                actor_id=actor_id,
                deal=deal,
            )
            # §08: a recorded payment queues the commercial-state refresh —
            # inside this tx so the job exists iff the payment does.
            from automations.service import emit

            emit(
                "automation.commercial_refresh",
                org_id=org_id,
                actor_id=actor_id,
                idempotency_key=f"auto:comm:{project_id}:{payment['id']}",
                project_id=str(project_id),
                payment_id=str(payment["id"]),
            )
            # P25: aviso interno de cobro — el handler re-lee el pago
            # comprometido y escribe mail_messages vía outbox.
            emit(
                "mail.payment_received",
                org_id=org_id,
                actor_id=actor_id,
                idempotency_key=f"mail:payment:{payment['id']}",
                project_id=str(project_id),
                payment_id=str(payment["id"]),
            )
    return {
        "payment": _payment_public(payment, receipt),
        "receipt": receipt,
        **_summary(org_id, project_id, project),
    }


def void_payment(*, org_id: UUID, project_id: UUID, payment_id: UUID, actor_id: UUID, data: dict) -> dict:
    project = project_row(org_id, project_id)
    with transaction.atomic(), documentary_backend():
        found = rows(
            "UPDATE public.project_payments SET voided_at=%s, voided_by=%s, void_reason=%s "
            "WHERE org_id=%s AND project_id=%s AND id=%s AND voided_at IS NULL "
            "RETURNING *",
            [
                timezone.now(),
                str(actor_id),
                data.get("reason") or None,
                str(org_id),
                str(project_id),
                str(payment_id),
            ],
        )
        if not found:
            found = rows(
                "SELECT * FROM public.project_payments "
                "WHERE org_id=%s AND project_id=%s AND id=%s",
                [str(org_id), str(project_id), str(payment_id)],
            )
            if not found:
                raise contract_error(404, "payment_not_found", "El pago no está disponible.")
        from automations.service import emit

        emit(
            "automation.commercial_refresh",
            org_id=org_id,
            actor_id=actor_id,
            idempotency_key=f"auto:comm:{project_id}:{payment_id}:void",
            project_id=str(project_id),
            payment_id=str(payment_id),
        )
    return _summary(org_id, project_id, project)
