"""Flow API 3.0.1 transport. No entitlement or payment authority from callbacks.

Reference: https://developers.flow.cl/api (checked 2026-09-20).
Callers must persist an operation before a mutation and reconcile ambiguous outcomes.
Flow does not document a general Idempotency-Key contract: never retry POST blindly.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import hashlib
import hmac
import json
import os
import uuid
from urllib.parse import urlencode, urlsplit

import httpx


class FlowError(Exception):
    """Sanitized provider error; deliberately excludes credentials and payloads."""

    def __init__(self, code: str, *, uncertain: bool = False):
        self.code = code
        self.uncertain = uncertain
        super().__init__(code)


def signed_parameters(values: Mapping[str, str], api_key: str, secret_key: str) -> dict[str, str]:
    if "s" in values or "apiKey" in values:
        raise ValueError("Credentials and signatures are transport-owned")
    parameters = {**values, "apiKey": api_key}
    message = "".join(key + parameters[key] for key in sorted(parameters))
    parameters["s"] = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return parameters


class FlowClient:
    """Only documented endpoints; fixed TLS origins, bounded I/O and exact JSON money."""

    def __init__(self, *, api_url: str, api_key: str, secret_key: str,
                 transport: httpx.BaseTransport | None = None):
        if api_url not in {"https://sandbox.flow.cl/api", "https://www.flow.cl/api"}:
            raise ValueError("Unsupported Flow API origin")
        if not api_key or not secret_key:
            raise FlowError("flow_not_configured")
        self.api_url = api_url
        self.api_key = api_key
        self.secret_key = secret_key
        self.transport = transport

    def _request(self, method: str, endpoint: str, values: Mapping[str, str]) -> dict:
        parameters = signed_parameters(values, self.api_key, self.secret_key)
        try:
            with httpx.Client(transport=self.transport, timeout=httpx.Timeout(15, connect=5),
                              follow_redirects=False, trust_env=False) as client:
                if method == "GET":
                    response = client.get(self.api_url + endpoint, params=parameters)
                else:
                    response = client.post(self.api_url + endpoint, data=parameters)
        except httpx.HTTPError:
            raise FlowError("flow_unavailable", uncertain=method == "POST") from None
        if response.status_code != 200:
            # Even an HTTP error can follow a committed remote mutation.
            raise FlowError("flow_rejected", uncertain=method == "POST")
        try:
            value = json.loads(response.content, parse_float=Decimal,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise FlowError("flow_invalid_response", uncertain=method == "POST") from None
        return value

    def payment_status(self, token: str) -> dict:
        return self._request("GET", "/payment/getStatus", {"token": token})

    def payment_by_order(self, order: str) -> dict:
        return self._request("GET", "/payment/getStatusByCommerceId", {"commerceId": order})

    def create_payment(self, *, order: str, subject: str, amount: Decimal, email: str,
                       confirmation_url: str, return_url: str) -> dict:
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
            raise ValueError("Flow CLP payments require positive integral Decimal amounts")
        return self._request("POST", "/payment/create", {
            "commerceOrder": order, "subject": subject, "currency": "CLP",
            "amount": format(amount, ".0f"), "email": email,
            "urlConfirmation": confirmation_url, "urlReturn": return_url,
        })

    def customer(self, customer_id: str) -> dict:
        return self._request("GET", "/customer/get", {"customerId": customer_id})

    def customers(self, *, start: int = 0) -> dict:
        return self._request('GET', '/customer/list', {'start': str(start), 'limit': '100'})

    def create_customer(self, *, external_id: str, name: str, email: str) -> dict:
        return self._request("POST", "/customer/create", {
            "externalId": external_id, "name": name, "email": email,
        })

    def register_customer(self, customer_id: str, return_url: str) -> dict:
        return self._request("POST", "/customer/register", {
            "customerId": customer_id, "url_return": return_url,
        })

    def registration_status(self, token: str) -> dict:
        return self._request("GET", "/customer/getRegisterStatus", {"token": token})

    def subscription(self, subscription_id: str) -> dict:
        return self._request("GET", "/subscription/get", {"subscriptionId": subscription_id})

    def create_subscription(self, *, customer_id: str, plan_id: str,
                            start_date: str | None = None, trial_days: int | None = None) -> dict:
        parameters = {
            "customerId": customer_id, "planId": plan_id,
        }
        if start_date is not None:
            parameters['subscription_start'] = start_date
        if trial_days is not None:
            if type(trial_days) is not int or trial_days < 0:
                raise ValueError('Explicit nonnegative trial days required')
            parameters['trial_period_days'] = str(trial_days)
        return self._request("POST", "/subscription/create", parameters)

    def plan(self, plan_id: str) -> dict:
        return self._request('GET', '/plans/get', {'planId': plan_id})

    def customer_subscriptions(self, customer_id: str, *, start: int = 0) -> dict:
        return self._request('GET', '/customer/getSubscriptions', {
            'customerId': customer_id, 'start': str(start), 'limit': '100',
        })

    def cancel_subscription(self, subscription_id: str, *, at_period_end: bool) -> dict:
        return self._request("POST", "/subscription/cancel", {
            "subscriptionId": subscription_id, "at_period_end": "1" if at_period_end else "0",
        })

    def change_plan_preview(self, subscription_id: str, plan_id: str, *, start_date: str | None = None) -> dict:
        values = {'subscriptionId': subscription_id, 'newPlanId': plan_id}
        if start_date is not None:
            values['startDateOfNewPlan'] = start_date
        return self._request('POST', '/subscription/changePlanPreview', values)

    def change_plan(self, subscription_id: str, plan_id: str, *, start_date: str | None = None) -> dict:
        values = {'subscriptionId': subscription_id, 'newPlanId': plan_id}
        if start_date is not None:
            values['startDateOfNewPlan'] = start_date
        return self._request('POST', '/subscription/changePlan', values)

    def create_refund(self, *, order: str, payment_id: str, amount: Decimal,
                      email: str, callback_url: str) -> dict:
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
            raise ValueError('Refund requires positive integer CLP')
        return self._request('POST', '/refund/create', {
            'refundCommerceOrder': order, 'flowTrxId': payment_id,
            'amount': format(amount, '.0f'), 'receiverEmail': email, 'urlCallBack': callback_url,
        })

    def refund_status(self, token: str) -> dict:
        return self._request('GET', '/refund/getStatus', {'token': token})

    def invoice(self, invoice_id: str) -> dict:
        return self._request("GET", "/invoice/get", {"invoiceId": invoice_id})

    def redirect_url(self, response: Mapping) -> str:
        url, token = response.get("url"), response.get("token")
        if not isinstance(url, str) or not isinstance(token, str) or not token:
            raise FlowError("flow_invalid_redirect", uncertain=True)
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != urlsplit(self.api_url).netloc
                or parsed.query or parsed.fragment or parsed.username):
            raise FlowError("flow_invalid_redirect", uncertain=True)
        return url + "?" + urlencode({"token": token})


def mock_enabled() -> bool:
    """Proveedor simulado — sólo con el opt-in explícito ``FLOW_WS_MOCK=1``,
    nunca como fallback silencioso de una integración real sin llaves."""
    return os.environ.get("FLOW_WS_MOCK", "").strip() == "1"


class MockFlowClient:
    """Proveedor Flow simulado de punta a punta, detrás del mismo contrato
    del cliente real: ``create_payment`` devuelve la orden + token y una URL
    de pago — que en modo simulado apunta a la página de checkout local
    (``flow_sim``), donde el pagador decide pagar o rechazar y la decisión
    entra por el mismo ``payment_status`` que el webhook real.

    El estado vive en memoria del proceso: un cargo desconocido se reporta
    como aún pendiente — nunca como pagado — para que la conciliación por
    ``commerceOrder`` no pueda inventar un pago tras un reinicio."""

    _charges: dict[str, dict] = {}

    def __init__(self, *, api_url: str, api_key: str, secret_key: str):
        self.api_url = api_url or "https://sandbox.flow.cl/api"

    @classmethod
    def checkout_url(cls, *, token: str, base: str) -> str:
        return f"{base.rstrip('/')}/api/v1/billing/flow-sim/{token}/"

    @classmethod
    def decide(cls, token: str, status: int) -> None:
        """La página simulada marca el veredicto del pagador (2 paga, 3
        rechaza); ``payment_status`` lo expone luego igual que Flow."""
        charge = cls._charges.get(token)
        if charge is not None:
            charge["status"] = status

    def create_payment(self, *, order: str, subject: str, amount: Decimal, email: str,
                       confirmation_url: str, return_url: str) -> dict:
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
            raise ValueError("Flow CLP payments require positive integral Decimal amounts")
        token = f"sim-{uuid.uuid4().hex[:20]}"
        flow_order = int(uuid.uuid4().hex[:8], 16) % 9_000_000 + 1_000_000
        self._charges[token] = {
            "order": order,
            "flowOrder": flow_order,
            "amount": amount,
            "status": 1,
        }
        sim_base = os.environ.get("FLOW_SIM_ORIGIN", "").strip() or "http://127.0.0.1:8000"
        return {
            "url": self.checkout_url(token=token, base=sim_base),
            "token": token,
            "flowOrder": flow_order,
        }

    def _resolve(self, token: str) -> dict:
        charge = self._charges.get(token)
        if charge is None:
            raise FlowError("flow_payment_not_found")
        return {
            "flowOrder": charge["flowOrder"],
            "status": charge["status"],
            "commerceOrder": charge["order"],
            "amount": str(charge["amount"]),
            "currency": "CLP",
        }

    def _resolve_by_order(self, order: str) -> dict:
        for charge in self._charges.values():
            if charge["order"] == order:
                return {
                    "flowOrder": charge["flowOrder"],
                    "status": charge["status"],
                    "commerceOrder": charge["order"],
                    "amount": str(charge["amount"]),
                    "currency": "CLP",
                }
        raise FlowError("flow_payment_not_found")

    def payment_status(self, token: str) -> dict:
        return self._resolve(token)

    def payment_by_order(self, order: str) -> dict:
        return self._resolve_by_order(order)

    def redirect_url(self, response: Mapping) -> str:
        url = response.get("url")
        token = response.get("token")
        if not isinstance(url, str) or not url:
            raise FlowError("flow_invalid_redirect", uncertain=True)
        return url if not token else f"{url}?token={token}"


def client_for(integration: dict):
    """Adaptador único: con ``FLOW_WS_MOCK=1`` toda integración habla con el
    proveedor simulado — el resto del dominio (claim, webhook, ledger) no se
    entera de qué transporte está detrás."""
    if mock_enabled():
        return MockFlowClient(
            api_url=integration["api_url"],
            api_key=integration["api_key"],
            secret_key=integration["secret_key"],
        )
    return FlowClient(
        api_url=integration["api_url"],
        api_key=integration["api_key"],
        secret_key=integration["secret_key"],
    )
