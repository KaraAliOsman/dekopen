"""Plantillas transaccionales — HTML compatible con clientes de correo
(tablas + estilos inline; nada de clases externas, flexbox ni imágenes
remotas obligatorias). Dos conchas:

- CLIENT (white-label): la identidad es la de la org emisora — nombre,
  color y contacto del fabricante; la palabra y la marca DEKOPEN no
  aparecen NUNCA en estas plantillas.
- INTERNAL: marca DEKOPEN (la sección como imagen CID + wordmark tipográfico)
  para el equipo del fabricante.

Voz es-CL en «usted», números ya formateados por el llamante.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

_INK = "#161C1F"
_G700 = "#465158"
_G500 = "#727D82"
_G300 = "#CDD5D6"
_PAPER = "#FFFFFF"
_BENCH = "#F5F7F6"
_TEAL_800 = "#075F5A"

_FONT = "'IBM Plex Sans', Arial, Helvetica, sans-serif"
_MONO = "'IBM Plex Mono', 'Courier New', monospace"


@dataclass
class RenderedMail:
    subject: str
    html: str
    text: str
    # cid → bytes: adjuntos embebidos (la marca interna viaja como CID,
    # que sí muestran Gmail/Apple Mail; los data-URI no sobreviven).
    inline_images: dict[str, bytes] = field(default_factory=dict)


def _button(url: str, label: str, accent: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0">'
        f'<tr><td bgcolor="{accent}" style="border-radius:2px">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:12px 24px;'
        f"font-family:{_FONT};font-size:14px;font-weight:600;color:{_PAPER};"
        'text-decoration:none;letter-spacing:0.02em">'
        f"{escape(label)}</a></td></tr></table>"
    )


def _client_shell(*, accent: str, header: str, body: str, footer_lines: str) -> str:
    """White-label: la org presta su nombre y su color; DEKOPEN no aparece."""
    return f"""<!doctype html>
<html lang="es"><body style="margin:0;padding:0;background:{_BENCH}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{_BENCH}">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" bgcolor="{_PAPER}"
  style="max-width:560px;width:100%;border:1px solid {_G300}">
  <tr><td style="padding:28px 32px 8px;font-family:{_FONT};font-size:16px;font-weight:600;color:{accent}">{header}</td></tr>
  <tr><td style="padding:0 32px"><div style="border-top:2px solid {accent};width:56px"></div></td></tr>
  <tr><td style="padding:20px 32px 8px">{body}</td></tr>
  <tr><td style="padding:16px 32px 28px;border-top:1px solid {_G300};
      font-family:{_FONT};font-size:11px;color:{_G500};line-height:1.6">{footer_lines}</td></tr>
</table></td></tr></table></body></html>"""


def _client_body(paragraphs: list[str], button: str = "") -> str:
    rows = "".join(
        f'<p style="margin:0 0 14px;font-family:{_FONT};font-size:14px;'
        f'line-height:1.6;color:{_INK}">{p}</p>'
        for p in paragraphs
    )
    return rows + button


def _internal_shell(*, kicker: str, body: str, accent: str = _TEAL_800) -> str:
    """Marca DEKOPEN: la sección (CID mark.png) + wordmark + cota mono."""
    mark = (
        '<img src="cid:mark.png" width="20" height="20" alt="" '
        'style="display:inline-block;vertical-align:middle;margin-right:8px">'
    )
    header = (
        f"{mark}"
        f'<span style="font-family:{_FONT};font-size:13px;font-weight:600;'
        f'letter-spacing:1.6px;color:{_INK};vertical-align:middle">DEKOPEN</span>'
    )
    return f"""<!doctype html>
<html lang="es"><body style="margin:0;padding:0;background:{_BENCH}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{_BENCH}">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" bgcolor="{_PAPER}"
  style="max-width:560px;width:100%;border:1px solid {_G300}">
  <tr><td style="padding:20px 32px 12px">{header}</td></tr>
  <tr><td style="padding:0 32px"><div style="border-top:2px solid {accent};width:56px"></div></td></tr>
  <tr><td style="padding:14px 32px 4px;font-family:{_MONO};font-size:11px;
      letter-spacing:1.2px;text-transform:uppercase;color:{_G500}">{escape(kicker)}</td></tr>
  <tr><td style="padding:8px 32px 8px">{body}</td></tr>
  <tr><td style="padding:16px 32px 24px;border-top:1px solid {_G300};
      font-family:{_FONT};font-size:11px;color:{_G500};line-height:1.6">
      DEKOPEN · correo interno del sistema · no responder</td></tr>
</table></td></tr></table></body></html>"""


def _internal_body(paragraphs: list[str], facts: list[tuple[str, str]], button: str = "") -> str:
    rows = "".join(
        f'<p style="margin:0 0 14px;font-family:{_FONT};font-size:14px;'
        f'line-height:1.6;color:{_INK}">{p}</p>'
        for p in paragraphs
    )
    if facts:
        cells = "".join(
            f'<tr><td style="padding:6px 0;font-family:{_MONO};font-size:11px;'
            f'color:{_G500};width:160px;vertical-align:top">{escape(k)}</td>'
            f'<td style="padding:6px 0;font-family:{_MONO};font-size:12px;'
            f'color:{_INK}">{escape(v)}</td></tr>'
            for k, v in facts
        )
        rows += (
            f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%"'
            f' style="margin:8px 0 16px;border-top:1px solid {_G300}">{cells}</table>'
        )
    return rows + button


def _mark_png() -> bytes:
    return (Path(__file__).resolve().parent / "assets" / "mark-ink.png").read_bytes()


# ——— Plantillas ———


def quote_sent(ctx: dict) -> RenderedMail:
    """Cliente: su cotización lista en el portal (white-label de la org)."""
    org_name = escape(str(ctx["org_name"]))
    accent = str(ctx["accent"])
    project_name = escape(str(ctx["project_name"]))
    client_name = escape(str(ctx["client_name"]))
    url = str(ctx["portal_url"])
    total = escape(str(ctx.get("total_label") or ""))
    greeting = f"Estimado/a {client_name}:"
    intro = f"{org_name} le comparte la cotización <strong>{project_name}</strong>" + (
        f" por un total de <strong>{total}</strong>." if total else "."
    )
    detail = (
        "Puede revisar el detalle, las posiciones y las condiciones, y "
        "aprobar o comentar la propuesta desde el siguiente enlace:"
    )
    link_note = (
        f"Si el botón no funciona, copie esta dirección en su navegador:<br>"
        f'<span style="font-family:{_MONO};font-size:12px;color:{_G700}">{escape(url)}</span>'
    )
    body = _client_body(
        [greeting, intro, detail],
        _button(url, "Revisar cotización", accent) + _client_body([link_note]),
    )
    contact = str(ctx.get("org_contact") or "")
    footer = (
        (escape(contact) + "<br>" if contact else "")
        + "Este correo fue generado automáticamente; si usted no esperaba "
        "esta cotización, puede ignorarlo."
    )
    html = _client_shell(accent=accent, header=org_name, body=body, footer_lines=footer)
    text = (
        f"{client_name}:\n\n{ctx['org_name']} le comparte la cotización "
        f"{ctx['project_name']}"
        + (f" por un total de {ctx.get('total_label')}.\n" if ctx.get("total_label") else ".\n")
        + f"\nRevísela y respóndala aquí:\n{url}\n"
        + (f"\n{contact}\n" if contact else "")
    )
    return RenderedMail(
        subject=f"{ctx['org_name']} — Cotización {ctx['project_name']}", html=html, text=text
    )


def quote_approved(ctx: dict) -> RenderedMail:
    """Interno: el cliente aprobó la cotización — pasar a producción."""
    project = str(ctx["project_name"])
    decided = str(ctx.get("decided_by") or "el cliente")
    project_url = str(ctx["project_url"])
    body = _internal_body(
        [
            f"El cliente aprobó la cotización <strong>{escape(project)}</strong>"
            f" (decisión registrada por {escape(decided)}). El proyecto está "
            "listo para emitirse a taller.",
        ],
        [
            ("Proyecto", f"{ctx.get('project_code') or '—'} · {project}"),
            ("Cliente", str(ctx.get("client_name") or "—")),
            ("Decisión", decided),
            ("Total", str(ctx.get("total_label") or "—")),
        ],
        _button(project_url, "Abrir proyecto", _TEAL_800),
    )
    html = _internal_shell(kicker="Cotización aprobada", body=body)
    text = f"Cotización aprobada\n\n{project} — decisión de {decided}.\nAbrir: {project_url}\n"
    return RenderedMail(
        subject=f"[DEKOPEN] Cotización aprobada — {project}",
        html=html,
        text=text,
        inline_images={"mark.png": _mark_png()},
    )


def quote_changes_requested(ctx: dict) -> RenderedMail:
    """Interno: el cliente pidió ajustes sin rechazar — la propuesta sigue
    vigente y el estimador debe emitir la siguiente revisión."""
    project = str(ctx["project_name"])
    decided = str(ctx.get("decided_by") or "el cliente")
    note = str(ctx.get("note") or "").strip()
    project_url = str(ctx["project_url"])
    paragraphs = [
        f"El cliente pidió cambios sobre la cotización <strong>{escape(project)}</strong>"
        f" (solicitud de {escape(decided)}). El enlace sigue vigente: ajusta "
        "y emite la siguiente revisión.",
    ]
    if note:
        paragraphs.append(f"Comentario del cliente: <em>«{escape(note)}»</em>")
    body = _internal_body(
        paragraphs,
        [
            ("Proyecto", f"{ctx.get('project_code') or '—'} · {project}"),
            ("Cliente", str(ctx.get("client_name") or "—")),
            ("Solicita", decided),
            ("Total", str(ctx.get("total_label") or "—")),
        ],
        _button(project_url, "Revisar cotización", _TEAL_800),
    )
    html = _internal_shell(kicker="Cambios solicitados", body=body)
    text = (
        f"Cambios solicitados\n\n{project} — {decided} pidió ajustes."
        + (f"\nComentario: «{note}»" if note else "")
        + f"\nAbrir: {project_url}\n"
    )
    return RenderedMail(
        subject=f"[DEKOPEN] Cambios solicitados — {project}",
        html=html,
        text=text,
        inline_images={"mark.png": _mark_png()},
    )


def payment_received(ctx: dict) -> RenderedMail:
    """Interno: cobro registrado contra el proyecto."""
    project = str(ctx["project_name"])
    project_url = str(ctx["project_url"])
    body = _internal_body(
        [f"Se registró un pago en el proyecto <strong>{escape(project)}</strong>."],
        [
            ("Proyecto", f"{ctx.get('project_code') or '—'} · {project}"),
            ("Monto", str(ctx.get("amount_label") or "—")),
            ("Medio", str(ctx.get("method_label") or "—")),
            ("Saldo", str(ctx.get("balance_label") or "—")),
        ],
        _button(project_url, "Ver proyecto", _TEAL_800),
    )
    html = _internal_shell(kicker="Pago registrado", body=body)
    text = (
        f"Pago registrado\n\n{project}: {ctx.get('amount_label') or '—'}"
        f" · saldo {ctx.get('balance_label') or '—'}\nAbrir: {project_url}\n"
    )
    return RenderedMail(
        subject=f"[DEKOPEN] Pago registrado — {project}",
        html=html,
        text=text,
        inline_images={"mark.png": _mark_png()},
    )


def pricing_decision(ctx: dict) -> RenderedMail:
    """Interno: la operación comercial del estimador fue decidida."""
    outcome = str(ctx.get("outcome_label") or "decidida")
    project = str(ctx["project_name"])
    decided = str(ctx.get("decided_by") or "el dueño")
    pricing_url = str(ctx["pricing_url"])
    body = _internal_body(
        [
            f"Tu operación comercial del proyecto <strong>{escape(project)}</strong>"
            f" quedó <strong>{escape(outcome)}</strong>"
            f" (decisión de {escape(decided)}).",
        ],
        [
            ("Proyecto", f"{ctx.get('project_code') or '—'} · {project}"),
            ("Operación", str(ctx.get("operation_label") or "—")),
            ("Decisión", outcome),
            ("Decisor", decided),
            ("Neto", str(ctx.get("net_label") or "—")),
            ("Motivo", str(ctx.get("reason") or "—")),
        ],
        _button(pricing_url, "Abrir precios", _TEAL_800),
    )
    html = _internal_shell(kicker="Decisión de precios", body=body)
    text = (
        f"Decisión de precios\n\n{project} — {outcome} por {decided}.\n"
        f"Abrir: {pricing_url}\n"
    )
    return RenderedMail(
        subject=f"[DEKOPEN] Precios {outcome} — {project}",
        html=html,
        text=text,
        inline_images={"mark.png": _mark_png()},
    )


def work_order_blocked(ctx: dict) -> RenderedMail:
    """Interno: un paso de producción quedó bloqueado — necesita decisión."""
    order_code = str(ctx.get("order_code") or "—")
    step_label = str(ctx.get("step_label") or "paso")
    reason = str(ctx.get("note") or "Sin nota registrada.")
    project_url = str(ctx["project_url"])
    body = _internal_body(
        [
            f"La orden <strong>{escape(order_code)}</strong> quedó bloqueada"
            f" en el paso <strong>{escape(step_label)}</strong> — requiere "
            "una decisión para continuar.",
        ],
        [
            ("Orden", order_code),
            ("Paso", step_label),
            ("Motivo", reason),
            ("Registrado por", str(ctx.get("actor_label") or "—")),
        ],
        _button(project_url, "Abrir taller", _TEAL_800),
    )
    html = _internal_shell(kicker="OT bloqueada", body=body)
    text = f"OT bloqueada\n\n{order_code} · {step_label}\nMotivo: {reason}\nAbrir: {project_url}\n"
    return RenderedMail(
        subject=f"[DEKOPEN] OT bloqueada — {order_code}",
        html=html,
        text=text,
        inline_images={"mark.png": _mark_png()},
    )


_MAGIC_LINK_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "supabase" / "templates" / "magic_link.html"
)


def order_sent(ctx: dict) -> RenderedMail:
    """Proveedor: orden de compra emitida — folio OC, líneas y entrega
    esperada. White-label de la org emisora, como el correo al cliente."""
    org_name = escape(str(ctx["org_name"]))
    accent = str(ctx["accent"])
    order_code = escape(str(ctx["order_code"]))
    supplier_name = escape(str(ctx.get("supplier_name") or "proveedor"))
    lines = ctx.get("lines") or []
    expected = escape(str(ctx.get("expected_label") or ""))
    rows_html = "".join(
        "<tr>"
        f'<td style="padding:4px 8px;border-bottom:1px solid {_G300};'
        f'font-family:{_MONO};font-size:12px;color:{_INK}">{escape(str(line.get("sku") or "—"))}</td>'
        f'<td style="padding:4px 8px;border-bottom:1px solid {_G300};'
        f'font-family:{_MONO};font-size:12px;color:{_INK};text-align:right">'
        f'{escape(str(line.get("qty") or "—"))} {escape(str(line.get("unit") or ""))}</td>'
        + (
            f'<td style="padding:4px 8px;border-bottom:1px solid {_G300};'
            f'font-family:{_MONO};font-size:12px;color:{_INK};text-align:right">'
            f'{escape(str(line["line_total"]))}</td>'
            if line.get("line_total") else "<td></td>"
        )
        + "</tr>"
        for line in lines[:60]
    )
    table = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%"'
        f' style="margin:8px 0 16px;border-top:1px solid {_G300}">{rows_html}</table>'
    )
    intro = (
        f"{org_name} emite la orden de compra <strong>{order_code}</strong>"
        f" a nombre de <strong>{supplier_name}</strong>."
    )
    delivery = (
        f"La entrega esperada es <strong>{expected}</strong>." if expected else ""
    )
    body = _client_body(
        [f"Estimado/a {supplier_name}:", intro, table + delivery]
    )
    contact = str(ctx.get("org_contact") or "")
    footer = (
        (escape(contact) + "<br>" if contact else "")
        + "Este correo fue generado por el sistema de compras; responda a la "
        "dirección de contacto del emisor."
    )
    html = _client_shell(
        accent=accent, header=f"{org_name} — {order_code}", body=body,
        footer_lines=footer,
    )
    text_lines = "\n".join(
        f"  {line.get('sku') or '—'}  × {line.get('qty') or '—'} {line.get('unit') or ''}"
        + (f"  · {line['line_total']}" if line.get("line_total") else "")
        for line in lines[:60]
    )
    text = (
        f"{supplier_name}:\n\n{ctx['org_name']} emite la orden de compra "
        f"{ctx['order_code']}.\n\n{text_lines}\n"
        + (f"\nEntrega esperada: {expected}\n" if expected else "")
        + (f"\n{contact}\n" if contact else "")
    )
    return RenderedMail(
        subject=f"{ctx['org_name']} — Orden de compra {ctx['order_code']}",
        html=html,
        text=text,
    )


def magic_link(ctx: dict) -> RenderedMail:
    """Vista previa del magic-link real: se renderiza desde la misma
    plantilla que sirve GoTrue (supabase/templates/magic_link.html) con
    valores de muestra — la previsualización nunca diverge del correo."""
    url = str(ctx.get("confirmation_url") or "https://app.dekopen.cl/auth/callback#token")
    email = str(ctx.get("email") or "usuario@fabricante.cl")
    source = _MAGIC_LINK_TEMPLATE_PATH.read_text(encoding="utf8")
    html = (
        source.replace("{{ .ConfirmationURL }}", url)
        .replace("{{ .Email }}", email)
        .replace("{{ .Token }}", "123456")
        .replace("{{ .SiteURL }}", "https://app.dekopen.cl")
    )
    # Go templating remanente (variables que no usamos) — neutro en preview.
    html = re.sub(r"\{\{[^}]*\}\}", "", html)
    text = (
        f"Ingrese a DEKOPEN con este enlace (válido por una hora):\n{url}\n\n"
        "Si usted no solicitó este correo, puede ignorarlo."
    )
    return RenderedMail(subject="DEKOPEN — su enlace de ingreso", html=html, text=text)


RENDERERS = {
    "magic_link": magic_link,
    "quote_sent": quote_sent,
    "quote_approved": quote_approved,
    "payment_received": payment_received,
    "pricing_decision": pricing_decision,
    "work_order_blocked": work_order_blocked,
    "order_sent": order_sent,
}
