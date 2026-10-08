"""Proveedores de correo — el adaptador detrás del outbox.

`sandbox` (por defecto): acepta todo y no entrega — recorre el flujo
completo (encola, marca SENT con referencia de sandbox) sin salir del
sistema. `smtp`: SMTP real por variables de entorno, incluido Mailpit
local (localhost:1025) para ver el correo renderizado de verdad.

Selección: MAIL_PROVIDER=sandbox|smtp (default sandbox).
Activación del proveedor real: docs/ACTIVACION.md §Correo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from django.core.mail import EmailMultiAlternatives, get_connection

from mail.templates import RenderedMail


class ProviderError(Exception):
    """Falla de transporte — la fila queda FAILED con este mensaje."""


@dataclass
class Outcome:
    provider: str
    ref: str


class SandboxProvider:
    """Entrega simulada: el correo queda en mail_messages con un ref
    sandbox — la bandeja misma es la evidencia del envío."""

    name = "sandbox"

    def send(self, *, to: str, rendered: RenderedMail) -> Outcome:
        return Outcome(provider=self.name, ref=f"sandbox:{to}")


class SmtpProvider:
    name = "smtp"

    def send(self, *, to: str, rendered: RenderedMail) -> Outcome:
        host = os.environ.get("MAIL_SMTP_HOST")
        if not host:
            raise ProviderError("mail_smtp_not_configured")
        try:
            connection = get_connection(
                host=host,
                port=int(os.environ.get("MAIL_SMTP_PORT", "25")),
                username=os.environ.get("MAIL_SMTP_USER") or None,
                password=os.environ.get("MAIL_SMTP_PASSWORD") or None,
                use_tls=os.environ.get("MAIL_SMTP_TLS", "1") != "0",
                fail_silently=False,
            )
            message = EmailMultiAlternatives(
                subject=rendered.subject,
                body=rendered.text,
                from_email=from_address(),
                to=[to],
                connection=connection,
            )
            message.attach_alternative(rendered.html, "text/html")
            for cid, content in rendered.inline_images.items():
                from email.mime.image import MIMEImage

                image = MIMEImage(content)
                image.add_header("Content-ID", f"<{cid}>")
                image.add_header("Content-Disposition", "inline", filename=cid)
                message.attach(image)
            message.send()
        except ProviderError:
            raise
        except Exception as error:  # transporte: el caller marca FAILED
            raise ProviderError(str(error)[:400]) from error
        return Outcome(provider=self.name, ref=host)


_PROVIDERS = {
    "sandbox": SandboxProvider,
    "smtp": SmtpProvider,
}


def provider_name() -> str:
    return os.environ.get("MAIL_PROVIDER", "sandbox").strip() or "sandbox"


def get_provider():
    kind = provider_name()
    return _PROVIDERS.get(kind, SandboxProvider)()


def from_address() -> str:
    return os.environ.get("MAIL_FROM", "noreply@dekopen.cl")


def configured() -> bool:
    """¿Hay un proveedor real configurado? sandbox es siempre válido pero
    no 'configurado' — la tarjeta de Ajustes distingue ambos estados."""
    return provider_name() == "smtp" and bool(os.environ.get("MAIL_SMTP_HOST"))
