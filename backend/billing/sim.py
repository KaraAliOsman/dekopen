"""Página de pago simulada del proveedor Flow (``FLOW_WS_MOCK=1``).

Sólo existe cuando el mock está habilitado — en producción las rutas devuelven
404 y ningún cobro real puede pasar por aquí. El flujo es el del proveedor
real: el link abre esta página, el pagador decide (pagar / rechazar) y la
decisión se entrega al dominio por el mismo camino del webhook — el POST
llama a ``confirm_link``, que re-consulta el estado al cliente como haría el
``urlConfirmation`` de Flow, y luego redirige al ``payer_return_url`` de la
organización.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views import View

from billing.flow import MockFlowClient, mock_enabled
from projects import payment_links


def _charge(token: str) -> dict | None:
    return MockFlowClient._charges.get(token)


def _money(amount) -> str:
    try:
        entero = int(Decimal(str(amount)))
    except Exception:  # noqa: BLE001 — sólo presentación
        entero = 0
    return f"${entero:,}".replace(",", ".")


class FlowSimCheckoutView(View):
    """GET muestra el checkout; POST decide y dispara el retorno.

    La página es deliberadamente mínima y marcada como simulación: un link
    simulado jamás puede parecer una página de cobro real de Flow.
    """

    http_method_names = ["get", "post"]

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        if not mock_enabled():
            return HttpResponse("No encontrado.", status=404)
        charge = _charge(token)
        if charge is None:
            return HttpResponse("Cobro simulado no encontrado o expirado.", status=404)
        subject = escape(str(charge.get("order") or ""))
        amount = _money(charge.get("amount"))
        decided = charge.get("status") != 1
        body = (
            "<p>Este cobro ya fue procesado.</p>"
            if decided
            else f"""<form method="post">
              <p class="amount">{amount} <span class="clp">CLP</span></p>
              <p class="subject">{subject}</p>
              <div class="actions">
                <button type="submit" name="decision" value="pay" class="pay">Pagar</button>
                <button type="submit" name="decision" value="reject" class="reject">Rechazar</button>
              </div>
            </form>"""
        )
        return HttpResponse(
            f"""<!doctype html><html lang="es-CL"><head><meta charset="utf-8">
<title>Pago simulado — DEKOPEN</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,sans-serif;background:#f4f6f5;margin:0;display:flex;
 min-height:100vh;align-items:center;justify-content:center}}
.card{{background:#fff;border:1px solid #dde3e1;border-radius:4px;padding:32px;
 max-width:400px;width:90%}}
.badge{{display:inline-block;background:#fdf2d7;color:#6b5714;border:1px solid #e8d49a;
 border-radius:4px;padding:2px 8px;font-size:12px;letter-spacing:.04em;margin-bottom:16px}}
.amount{{font-size:32px;font-weight:600;margin:8px 0}}
.clp{{font-size:14px;color:#666}}
.subject{{color:#444;font-size:14px;margin:0 0 24px}}
.actions{{display:flex;gap:12px}}
button{{flex:1;padding:12px;border-radius:4px;border:1px solid #0d7377;cursor:pointer;
 font-size:15px}}
.pay{{background:#0d7377;color:#fff}}
.reject{{background:#fff;color:#333}}
</style></head><body><main class="card">
<p class="badge">PAGO SIMULADO — SIN CARGO REAL</p>
{body}
</main></body></html>""",
            content_type="text/html; charset=utf-8",
        )

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        if not mock_enabled():
            return HttpResponse("No encontrado.", status=404)
        charge = _charge(token)
        if charge is None:
            return HttpResponse("Cobro simulado no encontrado o expirado.", status=404)
        if charge.get("status") == 1:
            decision = request.POST.get("decision")
            MockFlowClient.decide(token, 2 if decision == "pay" else 3)
            # El mismo camino del webhook real: la vista pública confirma el
            # link re-consultando el estado al proveedor (aquí, el mock).
            link = payment_links.confirm_simulated(token=token)
            return_url = link.get("payer_return_url") or "/"
            sep = "&" if "?" in return_url else "?"
            return HttpResponseRedirect(f"{return_url}{sep}flow_token={token}")
        return_url = "/"
        return HttpResponseRedirect(return_url)
