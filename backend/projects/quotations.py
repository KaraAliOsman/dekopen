"""Cotizaciones — lista transversal de lo emitido al cliente.

Una fila por proyecto con revisión sellada o estado cotizado: el estado
comercial real (enviada, vista, aprobada, rechazada, vencida o sin enlace)
se calcula aquí, nunca en el frontend. Sigue la revisión vigente
(`current_revision`) — un enlace viejo sobre una revisión reemplazada no
cuenta como «enviada».
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from documents.repository import documentary_backend, rows

_QUOTED_STATUSES = ("QUOTED", "APPROVED", "IN_PRODUCTION", "COMPLETED", "CANCELLED")


def _quote_state(approval: dict[str, Any] | None, now: datetime) -> str:
    """Estado comercial derivado del enlace vigente de la revisión actual."""
    if approval is None:
        return "no_link"
    status = str(approval["status"])
    if status == "APPROVED":
        return "approved"
    if status == "DECLINED":
        return "declined"
    expires = approval.get("expires_at")
    if status == "PENDING" and isinstance(expires, datetime):
        if expires <= now:
            return "expired"
        return "viewed" if int(approval.get("view_count") or 0) > 0 else "sent"
    if status == "REVOKED":
        return "no_link"
    return "sent"


def list_quotations(org_id: UUID) -> dict[str, Any]:
    with transaction.atomic(), documentary_backend():
        projects = rows(
            """
            SELECT p.id, p.code, p.name, p.client_name, p.status::text AS status,
                   p.current_revision, org.currency, p.total_price_gross,
                   p.updated_at,
                   (SELECT count(*) FROM public.project_versions v
                    WHERE v.project_id = p.id AND v.org_id = p.org_id) AS versions_count,
                   (SELECT max(v.emitted_at) FROM public.project_versions v
                    WHERE v.project_id = p.id AND v.org_id = p.org_id) AS last_sealed_at
            FROM public.projects p
            JOIN public.tenancy_organizations org ON org.id = p.org_id
            WHERE p.org_id = %s
              AND (
                  p.status::text = ANY(%s)
                  OR EXISTS (
                      SELECT 1 FROM public.project_versions v
                      WHERE v.project_id = p.id AND v.org_id = p.org_id
                  )
              )
            ORDER BY last_sealed_at DESC NULLS LAST, p.updated_at DESC
            LIMIT 400
            """,
            [str(org_id), list(_QUOTED_STATUSES)],
        )
        if not projects:
            return {"items": []}
        approvals = rows(
            """
            SELECT DISTINCT ON (a.project_id)
                   a.project_id, a.id, a.status::text AS status, a.expires_at,
                   a.view_count, a.first_viewed_at, a.last_viewed_at,
                   a.decided_by, a.decided_at, a.decided_note, a.created_at
            FROM public.customer_approvals a
            JOIN public.project_versions v ON v.id = a.project_version_id
                AND v.org_id = a.org_id
            JOIN public.projects p ON p.id = a.project_id AND p.org_id = a.org_id
            WHERE a.org_id = %s AND a.project_id = ANY(%s)
              AND v.revision_code = p.current_revision
            ORDER BY a.project_id, a.created_at DESC
            """,
            [str(org_id), [str(p["id"]) for p in projects]],
        )
    by_project = {str(a["project_id"]): a for a in approvals}
    now = timezone.now()
    items = []
    for project in projects:
        approval = by_project.get(str(project["id"]))
        approval_public = (
            {
                "id": str(approval["id"]),
                "status": approval["status"],
                "expires_at": approval["expires_at"].isoformat()
                if approval.get("expires_at")
                else None,
                "view_count": int(approval.get("view_count") or 0),
                "first_viewed_at": approval["first_viewed_at"].isoformat()
                if approval.get("first_viewed_at")
                else None,
                "last_viewed_at": approval["last_viewed_at"].isoformat()
                if approval.get("last_viewed_at")
                else None,
                "decided_by": approval.get("decided_by"),
                "decided_at": approval["decided_at"].isoformat()
                if approval.get("decided_at")
                else None,
                "decided_note": approval.get("decided_note"),
                "created_at": approval["created_at"].isoformat(),
            }
            if approval
            else None
        )
        items.append(
            {
                "project_id": str(project["id"]),
                "project_code": project["code"],
                "project_name": project["name"],
                "client_name": project["client_name"],
                "project_status": project["status"],
                "current_revision": project["current_revision"],
                "currency": project["currency"],
                "total_price_gross": str(project["total_price_gross"]),
                "versions_count": int(project["versions_count"]),
                "last_sealed_at": project["last_sealed_at"].isoformat()
                if project.get("last_sealed_at")
                else None,
                "approval": approval_public,
                "quote_state": _quote_state(approval, now),
            }
        )
    return {"items": items}
