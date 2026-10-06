"""Flow payment links for cobranza — the provider-verified collection path.

A link is the durable claim for one Flow charge: the org's own Flow credentials
(org_payment_integrations) sign a `payment/create` whose commerceOrder is the
link's operation_key. The public webhook only carries a token — authority comes
from `payment/getStatus` re-queried server-side, never from callback data.
Settlement inserts a project_payments row keyed by the same operation_key, so
the ledger's UNIQUE (org_id, operation_key) dedupes webhook retries, manual
records, and lost-callback recovery identically. Mirrors billing/settlement.py:
no provider mutation is retried after an uncertain outcome — recovery is a GET.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from authentication.errors import contract_error
from billing.flow import FlowClient, FlowError, client_for, mock_enabled
from documents.repository import documentary_backend
from pricing.repository import rows
from projects.payments import _deal
from projects.receipts import issue_receipt
from projects.service import project_row

_LINK_KINDS = ("ANTICIPO", "PARCIAL", "SALDO")
# TTL de referencia del link de pago — decisión registrada en
# docs/decisions/valores-por-defecto.md.
_LINK_TTL = timedelta(hours=72)


def _public_link(row: dict) -> dict:
    expires_at = row.get("expires_at")
    live_statuses = ("DISPATCHING", "PENDING", "UNCERTAIN")
    expired = bool(
        expires_at
        and expires_at <= timezone.now()
        and row["status"] in live_statuses
    )
    return {
        "id": str(row["id"]),
        "operation_key": row["operation_key"],
        "kind": row["kind"],
        "amount": str(row["amount"]),
        "payer_email": row["payer_email"],
        "subject": row["subject"],
        "status": row["status"],
        "environment": row["environment"],
        "url": row["url"],
        "expires_at": expires_at.isoformat()
        if hasattr(expires_at, "isoformat")
        else expires_at,
        "expired": expired,
        "project_payment_id": str(row["project_payment_id"]) if row["project_payment_id"] else None,
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
        "updated_at": row["updated_at"].isoformat()
        if hasattr(row["updated_at"], "isoformat")
        else row["updated_at"],
    }


def _environment(api_url: str) -> str:
    return "sandbox" if api_url == "https://sandbox.flow.cl/api" else "production"


def _client(integration: dict):
    return client_for(integration)


def get_integration(*, org_id: UUID) -> dict:
    """Config status for the settings surface — never leaks the secret."""
    with documentary_backend():
        found = rows(
            "SELECT api_url, api_key, payer_return_url, enabled, updated_at "
            "FROM public.org_payment_integrations WHERE org_id=%s AND provider='FLOW'",
            [str(org_id)],
        )
    if not found:
        return {"configured": False, "provider_mode": "mock" if mock_enabled() else "live"}
    row = found[0]
    return {
        "configured": True,
        "provider_mode": "mock" if mock_enabled() else "live",
        "api_url": row["api_url"],
        "api_key_preview": row["api_key"][:4] + "…" + row["api_key"][-2:],
        "payer_return_url": row["payer_return_url"],
        "enabled": row["enabled"],
        "updated_at": row["updated_at"].isoformat()
        if hasattr(row["updated_at"], "isoformat")
        else row["updated_at"],
    }


def save_integration(*, org_id: UUID, data: dict) -> dict:
    """Upsert the org's Flow credentials. Secret is write-only: omitted on
    update keeps the stored one; it is never returned in any response."""
    api_url = str(data.get("api_url") or "https://sandbox.flow.cl/api")
    with transaction.atomic(), documentary_backend():
        existing = rows(
            "SELECT api_key, secret_key FROM public.org_payment_integrations "
            "WHERE org_id=%s AND provider='FLOW'",
            [str(org_id)],
        )
        secret = data.get("secret_key") or (existing[0]["secret_key"] if existing else None)
        if not secret:
            raise contract_error(
                422, "flow_secret_required", "La clave secreta de Flow es obligatoria."
            )
        api_key = data.get("api_key") or (existing[0]["api_key"] if existing else None)
        if not api_key:
            raise contract_error(
                422, "flow_api_key_required", "La api key de Flow es obligatoria."
            )
        rows(
            """
            INSERT INTO public.org_payment_integrations(
                org_id, provider, api_url, api_key, secret_key, payer_return_url, enabled)
            VALUES (%s, 'FLOW', %s, %s, %s, %s, %s)
            ON CONFLICT (org_id) DO UPDATE SET
                api_url = EXCLUDED.api_url,
                api_key = EXCLUDED.api_key,
                secret_key = EXCLUDED.secret_key,
                payer_return_url = EXCLUDED.payer_return_url,
                enabled = EXCLUDED.enabled,
                updated_at = now()
            RETURNING org_id
            """,
            [
                str(org_id),
                api_url,
                api_key.strip(),
                secret.strip(),
                (data.get("payer_return_url") or "").strip() or None,
                bool(data.get("enabled", True)),
            ],
        )
    return get_integration(org_id=org_id)


_MOCK_INTEGRATION = {
    "api_url": "https://sandbox.flow.cl/api",
    "api_key": "simulated",
    "secret_key": "simulated",
    "payer_return_url": None,
    "enabled": True,
}


def _integration_for_link(link_row: dict) -> dict:
    found = rows(
        "SELECT * FROM public.org_payment_integrations "
        "WHERE org_id=%s AND provider='FLOW' AND enabled",
        [str(link_row["org_id"])],
    )
    if not found:
        # En modo simulado el proveedor ES el mock — no exige credenciales
        # reales de Flow para recorrer el cobro de punta a punta.
        if mock_enabled():
            return dict(_MOCK_INTEGRATION)
        raise FlowError("flow_not_configured")
    return found[0]


def list_links(*, org_id: UUID, project_id: UUID) -> dict:
    project_row(org_id, project_id)
    with documentary_backend():
        found = rows(
            "SELECT * FROM public.project_payment_links "
            "WHERE org_id=%s AND project_id=%s ORDER BY created_at,id",
            [str(org_id), str(project_id)],
        )
    return {"links": [_public_link(row) for row in found]}


def create_link(*, org_id: UUID, project_id: UUID, actor_id: UUID, data: dict) -> dict:
    """One durable dispatch claim per operation_key — a replay returns the
    existing link instead of minting a second charge."""
    project = project_row(org_id, project_id)
    amount = Decimal(str(data["amount"]))
    if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
        raise contract_error(422, "amount_invalid", "El monto debe ser un entero CLP positivo.")
    kind = str(data["kind"]).upper()
    if kind not in _LINK_KINDS:
        raise contract_error(422, "payment_kind_invalid", "Tipo de cobro no válido.")
    subject = (data.get("subject") or "").strip() or f"{project['name']} — pago {kind.lower()}"
    # Freeze the deal the payer agrees to — settlement must be able to seal a
    # comprobante even if pricing is reset while the customer is paying. An
    # unpriced/unsealed project can never produce a charge (F19): a mailed
    # Flow link collects real money against nothing.
    deal = _deal(org_id, project_id, project)
    if deal is None or deal["sealed_revision"] is None:
        raise contract_error(
            422,
            "payment_requires_sealed_deal",
            "Emite una revisión de cotización antes de crear un cobro.",
        )
    # Flow charges CLP — a USD deal would collect the USD number in pesos and
    # write the result into the currency-less payments ledger, corrupting the
    # balance the comprobante and the portal then report.
    if deal["currency"] != "CLP":
        raise contract_error(
            422,
            "payment_currency_unsupported",
            "El cobro online solo está disponible en pesos (CLP); registra el pago manual en Cobranza.",
        )
    with documentary_backend():
        collected = rows(
            "SELECT COALESCE(SUM(amount), 0) AS collected FROM public.project_payments "
            "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
            [str(org_id), str(project_id)],
        )
    balance = deal["total"] - Decimal(str(collected[0]["collected"]))
    if amount > balance:
        raise contract_error(
            422,
            "payment_exceeds_balance",
            "El cobro supera el saldo pendiente del proyecto.",
        )
    deal_total = str(deal["total"])
    deal_currency = deal["currency"]
    with transaction.atomic(), documentary_backend():
        integration = rows(
            "SELECT * FROM public.org_payment_integrations "
            "WHERE org_id=%s AND provider='FLOW' AND enabled",
            [str(org_id)],
        )
        if not integration and mock_enabled():
            # FLOW_WS_MOCK=1 — el proveedor simulado no necesita la fila de
            # credenciales reales; el dominio sigue viendo una integración.
            integration = [dict(_MOCK_INTEGRATION)]
        if not integration:
            raise contract_error(
                422,
                "flow_not_configured",
                "Configura la integración Flow en Ajustes primero.",
            )
        return_url = integration[0]["payer_return_url"] or (
            settings.BILLING_FRONTEND_ORIGIN.rstrip("/") + "/pago/retorno"
            if settings.BILLING_FRONTEND_ORIGIN
            else ""
        )
        if not return_url:
            # A relative return URL handed to Flow leaves the link stuck
            # UNCERTAIN forever — fail before the dispatch claim commits.
            raise contract_error(
                422,
                "payer_return_not_configured",
                "Configura la URL de retorno del pagador (BILLING_FRONTEND_ORIGIN o la integración Flow) antes de crear cobros online.",
            )
        existing = rows(
            "SELECT * FROM public.project_payment_links WHERE org_id=%s AND operation_key=%s",
            [str(org_id), data["operation_key"]],
        )
        if existing:
            link = existing[0]
            if str(link["project_id"]) != str(project_id):
                raise contract_error(
                    409, "payment_operation_conflict", "La operación ya existe en otro proyecto."
                )
            return {"link": _public_link(link)}
        # One live claim per deal: the project slot serializes mints, so the
        # live-link check below can never race a concurrent create. Two
        # outstanding Flow charges on one deal is an over-collection path.
        rows(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            [f"project_payment_links:{org_id}:{project_id}"],
        )
        live = rows(
            "SELECT * FROM public.project_payment_links "
            "WHERE org_id=%s AND project_id=%s "
            "AND status IN ('DISPATCHING','PENDING','UNCERTAIN') "
            "AND (expires_at IS NULL OR expires_at > now()) "
            "ORDER BY created_at, id",
            [str(org_id), str(project_id)],
        )
        if live:
            live_link = live[0]
            # Reuse only a genuinely identical charge: same payer, subject,
            # amount and kind, already minted (PENDING carries the payer URL;
            # DISPATCHING/UNCERTAIN have no usable URL to hand back). Any
            # mismatch means a different request — refusing is safer than
            # handing out a charge meant for someone else.
            reusable = (
                str(live_link["status"]) == "PENDING"
                and live_link["url"]
                and Decimal(str(live_link["amount"])) == amount
                and str(live_link["kind"]) == kind
                and str(live_link["payer_email"]) == data["payer_email"].strip()
                and str(live_link["subject"]) == subject[:200]
            )
            if reusable:
                return {"link": _public_link(live_link)}
            raise contract_error(
                409,
                "payment_link_pending_exists",
                "Ya existe un cobro en línea vigente para este proyecto — "
                "usa el link existente o espera su resultado.",
            )
        link = rows(
            """
            INSERT INTO public.project_payment_links(
                org_id, project_id, operation_key, kind, amount, payer_email,
                subject, status, environment, created_by, deal_total, deal_currency,
                expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'DISPATCHING',%s,%s,%s,%s,%s)
            RETURNING *
            """,
            [
                str(org_id),
                str(project_id),
                data["operation_key"],
                kind,
                str(amount),
                data["payer_email"].strip(),
                subject[:200],
                _environment(integration[0]["api_url"]),
                str(actor_id),
                deal_total,
                deal_currency,
                (timezone.now() + _LINK_TTL).isoformat(),
            ],
        )[0]
        integration = integration[0]
    # The claim is committed — now the provider mutation. An uncertain outcome
    # marks the link UNCERTAIN; recovery is a GET, never a second POST.
    client = _client(integration)
    callback_origin = settings.BILLING_CALLBACK_ORIGIN.rstrip("/")
    try:
        created = client.create_payment(
            order=str(data["operation_key"]),
            subject=subject[:200],
            amount=amount,
            email=data["payer_email"].strip(),
            confirmation_url=f"{callback_origin}/api/v1/projects/flow/confirm/{link['id']}/",
            return_url=return_url,
        )
        redirect = client.redirect_url(created)
        if type(created.get("flowOrder")) is not int or created["flowOrder"] <= 0:
            raise FlowError("flow_invalid_payment", uncertain=True)
    except FlowError as error:
        with transaction.atomic(), documentary_backend():
            rows(
                "UPDATE public.project_payment_links SET status='UNCERTAIN', updated_at=now() "
                "WHERE org_id=%s AND id=%s AND status='DISPATCHING' RETURNING id",
                [str(org_id), str(link["id"])],
            )
        raise contract_error(
            503, "payment_link_dispatch_failed", "Flow no confirmó el link — reintenta verificar."
        ) from error
    with transaction.atomic(), documentary_backend():
        link = rows(
            "UPDATE public.project_payment_links SET status='PENDING', flow_order=%s, "
            "flow_token=%s, url=%s, updated_at=now() "
            "WHERE org_id=%s AND id=%s RETURNING *",
            [str(created["flowOrder"]), str(created.get("token") or ""), redirect,
             str(org_id), str(link["id"])],
        )[0]
    return {"link": _public_link(link)}


def _payment(value: dict) -> dict:
    """Reduce provider data to required authority; mirrors billing's shape check."""
    try:
        if type(value["flowOrder"]) is not int or value["flowOrder"] <= 0:
            raise ValueError()
        if type(value["status"]) is not int or value["status"] not in (1, 2, 3, 4):
            raise ValueError()
        if not isinstance(value["commerceOrder"], str) or not value["commerceOrder"]:
            raise ValueError()
        amount = Decimal(value["amount"])
        if value["currency"] != "CLP" or not amount.is_finite() or amount <= 0:
            raise ValueError()
        return {
            "flowOrder": str(value["flowOrder"]),
            "commerceOrder": value["commerceOrder"],
            "status": value["status"],
            "amount": amount,
        }
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise FlowError("flow_invalid_payment") from None


def _settle(*, org_id: UUID, link_id: UUID, verified: dict, client: FlowClient) -> dict:
    """Fold a verified provider observation into link + ledger, idempotently."""
    with transaction.atomic(), documentary_backend():
        found = rows(
            "SELECT * FROM public.project_payment_links "
            "WHERE org_id=%s AND id=%s FOR UPDATE",
            [str(org_id), str(link_id)],
        )
        if not found:
            raise contract_error(404, "payment_link_not_found", "El link de pago no existe.")
        link = found[0]
        if (
            link["operation_key"] != verified["commerceOrder"]
            or Decimal(str(link["amount"])) != verified["amount"]
            or link["flow_order"] not in (None, verified["flowOrder"])
            or link["environment"] != _environment(client.api_url)
        ):
            raise FlowError("flow_payment_binding_mismatch")
        if str(link["status"]) == "PAID":
            return {"link": _public_link(link)}
        if verified["status"] == 1:
            rows(
                "UPDATE public.project_payment_links SET status='PENDING', "
                "flow_order=%s, updated_at=now() "
                "WHERE org_id=%s AND id=%s AND status='DISPATCHING' RETURNING id",
                [verified["flowOrder"], str(org_id), str(link_id)],
            )
            return {"link": _public_link(link)}
        if verified["status"] in (3, 4):
            link = rows(
                "UPDATE public.project_payment_links SET status='FAILED', "
                "flow_order=%s, updated_at=now() "
                "WHERE org_id=%s AND id=%s AND status<>'PAID' RETURNING *",
                [verified["flowOrder"], str(org_id), str(link_id)],
            )[0]
            return {"link": _public_link(link)}
        # status 2 — settled. The ledger's UNIQUE (org_id, operation_key) is the
        # dedup boundary: webhook retries and recoveries converge on one row.
        # The project row lock serializes against a manual payment landing
        # between link mint and provider settle — the mint-time balance cap is
        # stale by then. The money did arrive (provider-verified) so the ledger
        # must record it; if the balance shrank under the link amount the
        # receipt documents the excess instead of silently over-collecting.
        project = project_row(org_id, link["project_id"], lock=True)
        live_deal = _deal(org_id, link["project_id"], project)
        over = Decimal("0")
        if live_deal is not None:
            collected = rows(
                "SELECT COALESCE(SUM(amount), 0) AS collected FROM public.project_payments "
                "WHERE org_id=%s AND project_id=%s AND voided_at IS NULL",
                [str(org_id), str(link["project_id"])],
            )[0]["collected"]
            over = Decimal(str(link["amount"])) - (
                Decimal(str(live_deal["total"])) - Decimal(str(collected))
            )
        note = "Cobro en línea — link de pago"
        if over > 0:
            note += f" — excede el saldo por {over} (conciliar devolución)"
        payment = rows(
            """
            INSERT INTO public.project_payments(
                org_id, project_id, operation_key, kind, amount, method,
                reference, note, recorded_by, recorded_at)
            VALUES (%s,%s,%s,%s,%s,'OTHER',%s,%s,%s,%s)
            ON CONFLICT (org_id, operation_key) DO NOTHING
            RETURNING *
            """,
            [
                str(org_id),
                str(link["project_id"]),
                str(link["operation_key"]),
                str(link["kind"]),
                str(Decimal(str(link["amount"]))),
                f"FLOW {verified['flowOrder']}",
                note,
                link["created_by"],
                timezone.now(),
            ],
        )
        if not payment:
            payment = rows(
                "SELECT * FROM public.project_payments WHERE org_id=%s AND operation_key=%s",
                [str(org_id), str(link["operation_key"])],
            )
        # Every ledger payment seals a comprobante — manual and online alike.
        # A replayed settle finds the existing receipt via UNIQUE(payment_id).
        # A verified payment must never be rejected over missing pricing
        # authority: the comprobante always reflects the total the link
        # presented to the payer — the deal frozen at creation — then the
        # live deal for links minted before the freeze, else an empty
        # snapshot. (project/live_deal resolved above, inside the row lock.)
        if link.get("deal_total") is not None:
            deal = {
                "total": Decimal(str(link["deal_total"])),
                "currency": link["deal_currency"] or "CLP",
            }
        elif live_deal is not None:
            deal = live_deal
        else:
            deal = {"total": None, "currency": "CLP"}
        issue_receipt(
            org_id=org_id,
            project=project,
            payment=payment[0],
            actor_id=link["created_by"] or org_id,
            deal=deal,
        )
        link = rows(
            "UPDATE public.project_payment_links SET status='PAID', flow_order=%s, "
            "project_payment_id=%s, updated_at=now() "
            "WHERE org_id=%s AND id=%s RETURNING *",
            [verified["flowOrder"], str(payment[0]["id"]), str(org_id), str(link_id)],
        )[0]
        # §08: the provider-verified settle queues the commercial refresh the
        # same way a manual payment does — inside the tx, keyed to the
        # payment row it minted.
        from automations.service import emit

        emit(
            "automation.commercial_refresh",
            org_id=org_id,
            actor_id=link["created_by"],
            idempotency_key=f"auto:comm:{link['project_id']}:{payment[0]['id']}",
            project_id=str(link["project_id"]),
            payment_id=str(payment[0]["id"]),
        )
    return {"link": _public_link(link)}


def _webhook_scope(*, link_id: UUID | None = None, flow_token: str | None = None) -> dict | None:
    """Resolve the webhook's tenant + delegating actor through the SECURITY
    DEFINER lookup — the public callback carries no JWT, so the org-scoped
    policy cannot see the row until claims are asserted."""
    found = rows(
        "SELECT * FROM private.payment_link_public_scope(%s, %s)",
        [str(link_id) if link_id else None, flow_token],
    )
    return found[0] if found else None


def _delegate_claims(created_by) -> None:
    """The callback proves itself via the opaque link id; the settle then
    runs with the link creator's membership — the same delegation the
    portal approval transition asserts on the decision's creator."""
    if not created_by:
        raise FlowError("payment_link_not_found")
    claims = json.dumps({"sub": str(created_by)}, separators=(",", ":"))
    rows("SELECT set_config('request.jwt.claims', %s, true)", [claims])


def confirm_link(*, link_id: UUID, token: str) -> dict:
    """Public webhook: resolve the org through the opaque link id, then verify
    server-side with the org's own credentials — callback fields are untrusted.

    One outer transaction: the delegated claims are transaction-local, so the
    verified settle must commit inside the same tx that asserted them."""
    with transaction.atomic(), documentary_backend():
        scope = _webhook_scope(link_id=link_id)
        if scope is None:
            raise FlowError("payment_link_not_found")
        _delegate_claims(scope["created_by"])
        found = rows(
            "SELECT * FROM public.project_payment_links WHERE org_id=%s AND id=%s",
            [str(scope["org_id"]), str(link_id)],
        )
        if not found:
            raise FlowError("payment_link_not_found")
        link = found[0]
        org_id = link["org_id"]
        integration = _integration_for_link(link)
        client = _client(integration)
        verified = _payment(client.payment_status(token))
        return _settle(org_id=org_id, link_id=link_id, verified=verified, client=client)


def confirm_simulated(*, token: str) -> dict:
    """Retorno del checkout simulado (``FLOW_WS_MOCK=1``): el mismo camino
    del ``urlConfirmation`` real — resuelve el link por su token de
    proveedor, re-consulta el estado al cliente (aquí el mock) y liquida
    por ``_settle``, jamás por los campos del POST."""
    if not mock_enabled():
        raise FlowError("flow_payment_not_found")
    with transaction.atomic(), documentary_backend():
        scope = _webhook_scope(flow_token=token)
        if scope is None:
            raise FlowError("payment_link_not_found")
        _delegate_claims(scope["created_by"])
        found = rows(
            "SELECT * FROM public.project_payment_links WHERE flow_token=%s",
            [str(token)],
        )
        if not found:
            raise FlowError("payment_link_not_found")
        link = found[0]
        org_id = link["org_id"]
        integration = _integration_for_link(link)
        return_url = (
            integration.get("payer_return_url")
            or f"{settings.BILLING_FRONTEND_ORIGIN}/pago/retorno"
        )
        client = _client(integration)
        verified = _payment(client.payment_status(token))
        settled = _settle(
            org_id=org_id, link_id=link["id"], verified=verified, client=client
        )
    return {**settled, "payer_return_url": return_url}


def recover_link(*, org_id: UUID, link_id: UUID) -> dict:
    """Recheck a pending/uncertain link via GET by commerceOrder — recovers a
    lost webhook or ambiguous create without issuing another charge."""
    with documentary_backend():
        found = rows(
            "SELECT * FROM public.project_payment_links WHERE org_id=%s AND id=%s",
            [str(org_id), str(link_id)],
        )
        if not found:
            raise contract_error(404, "payment_link_not_found", "El link de pago no existe.")
        link = found[0]
        integration = _integration_for_link(link)
    if str(link["status"]) == "PAID":
        return {"link": _public_link(link)}
    client = _client(integration)
    verified = _payment(client.payment_by_order(str(link["operation_key"])))
    return _settle(org_id=org_id, link_id=link_id, verified=verified, client=client)
