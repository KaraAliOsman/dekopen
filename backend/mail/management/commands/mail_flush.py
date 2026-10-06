"""Reintenta correos QUEUED/FAILED del outbox — corre como comando, no job,
porque el proveedor es lo único que pudo fallar.

Desarrollo:    python backend/manage.py mail_flush --org <uuid>
Producción:    python backend/manage.py mail_flush
"""

from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import transaction

from authentication.rls import worker_claims
from documents.repository import documentary_backend
from mail import service
from pricing.repository import rows


def _principal_for(org_id: UUID) -> UUID | None:
    """Primer miembro activo del org — el rol solo necesita claims válidas,
    la fila es la evidencia y el org de la fila es el límite tenant."""
    members = rows(
        "SELECT user_id FROM public.tenancy_memberships"
        " WHERE org_id=%s AND is_active ORDER BY created_at LIMIT 1",
        [str(org_id)],
    )
    return UUID(str(members[0]["user_id"])) if members else None


class Command(BaseCommand):
    help = "Redespacha filas QUEUED/FAILED de public.mail_messages."

    def add_arguments(self, parser):
        parser.add_argument("--org", type=UUID)
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        pending_orgs = rows(
            "SELECT DISTINCT org_id FROM public.mail_messages"
            " WHERE status IN ('QUEUED','FAILED')"
            + (" AND org_id=%s" if options["org"] else "")
            + " ORDER BY org_id",
            [str(options["org"])] if options["org"] else [],
        )
        flushed = 0
        for record in pending_orgs:
            org_id = UUID(str(record["org_id"]))
            principal = _principal_for(org_id)
            if principal is None:
                self.stderr.write(f"{org_id}: sin miembros activos — omitida")
                continue
            claims = {
                "sub": str(principal),
                "aud": "authenticated",
                "role": "authenticated",
            }
            with worker_claims(claims):
                with transaction.atomic(), documentary_backend():
                    flushed += service.flush_pending(org_id=org_id, limit=options["limit"])
        self.stdout.write(f"mail_flush: {flushed} correo(s) despachado(s)")
