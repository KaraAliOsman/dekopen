"""Global deterministic search — §7.

One org-scoped query per domain group, plain substring matching (POSITION, so
user input can never act as a LIKE pattern), stable ordering, bounded results.
Read-only: every query runs under the caller's authenticated claims, so RLS
and the explicit org filter agree on what is visible.
"""

from __future__ import annotations

from uuid import UUID

from catalogs.service import visibility_sql
from pricing.repository import rows

MAX_QUERY_LEN = 80
GROUP_LIMIT = 6


def _where(columns: tuple[str, ...]) -> str:
    return " OR ".join(
        f"POSITION(%s IN lower(coalesce({column}::text, ''))) > 0" for column in columns
    )


# Groups an installer must never see: the client registry carries fiscal PII
# (RUT) and the documents group mixes invoices into the result set. Projects
# still surface (dispatch/installation context) minus the commercial subtitle.
_INSTALLER_EXCLUDED_GROUPS = {"clients", "documents"}


def search(org_id: UUID, query: str, role: str = "OWNER") -> dict:
    needle = query.strip().lower()
    if len(needle) < 2 or len(needle) > MAX_QUERY_LEN:
        return {"results": []}

    def org(sql: str, *columns: str, org_params: int = 1) -> list[dict]:
        return rows(
            sql.replace("__WHERE__", _where(columns)),
            [str(org_id)] * org_params + [needle] * len(columns),
        )

    results: list[dict] = []

    for row in org(
        "SELECT id, code, name, client_name FROM public.projects"
        " WHERE org_id=%s AND (__WHERE__)"
        f" ORDER BY updated_at DESC LIMIT {GROUP_LIMIT}",
        "name",
        "code",
        "client_name",
    ):
        results.append(
            {
                "group": "projects",
                "id": str(row["id"]),
                "title": f"{row['code']} · {row['name']}",
                "subtitle": row.get("client_name"),
                "path": f"/projects/{row['id']}",
            }
        )

    for row in org(
        "SELECT id, name, rut FROM public.clients"
        " WHERE org_id=%s AND is_active AND (__WHERE__)"
        f" ORDER BY updated_at DESC LIMIT {GROUP_LIMIT}",
        "name",
        "rut",
        "email",
    ):
        results.append(
            {
                "group": "clients",
                "id": str(row["id"]),
                "title": row["name"],
                "subtitle": row.get("rut"),
                "path": "/clients",
            }
        )

    for row in org(
        "SELECT p.id, p.project_id, p.location_tag, p.typology,"
        " pr.code AS project_code, pr.name AS project_name"
        " FROM public.project_positions p JOIN public.projects pr ON pr.id = p.project_id"
        " WHERE p.org_id=%s AND pr.org_id=%s AND (__WHERE__)"
        f" ORDER BY p.updated_at DESC LIMIT {GROUP_LIMIT}",
        "p.location_tag",
        "p.typology",
        org_params=2,
    ):
        results.append(
            {
                "group": "positions",
                "id": str(row["id"]),
                "title": row.get("location_tag") or row["typology"],
                "subtitle": f"{row['project_code']} · {row['project_name']}",
                "path": f"/projects/{row['project_id']}/positions/{row['id']}/edit",
            }
        )

    for row in org(
        "SELECT id, code, name FROM public.profile_systems"
        f" WHERE {visibility_sql(child=False)} AND (__WHERE__)"
        f" ORDER BY code LIMIT {GROUP_LIMIT}",
        "code",
        "name",
    ):
        results.append(
            {
                "group": "systems",
                "id": str(row["id"]),
                "title": f"{row['code']} · {row['name']}",
                "subtitle": None,
                "path": "/catalogs/systems",
            }
        )

    for row in org(
        "SELECT a.id, a.sku, a.name, s.code AS system_code"
        " FROM public.profile_articles a"
        " JOIN public.profile_systems s ON s.id = a.system_id"
        f" WHERE {visibility_sql(child=True, alias='a')}"
        " AND (s.org_id = %s OR (s.org_id IS NULL AND s.is_global))"
        " AND (__WHERE__)"
        f" ORDER BY a.sku LIMIT {GROUP_LIMIT}",
        "a.sku",
        "a.name",
        org_params=2,
    ):
        results.append(
            {
                "group": "articles",
                "id": str(row["id"]),
                "title": row["sku"],
                "subtitle": f"{row['system_code']} · {row['name']}",
                "path": "/catalogs/systems",
            }
        )

    for row in org(
        "SELECT id, sku, name, kind FROM public.infill_articles"
        f" WHERE {visibility_sql(child=True)} AND (__WHERE__)"
        f" ORDER BY sku LIMIT {GROUP_LIMIT}",
        "sku",
        "name",
    ):
        results.append(
            {
                "group": "articles",
                "id": str(row["id"]),
                "title": row["sku"],
                "subtitle": row["name"],
                "path": "/catalogs/systems",
            }
        )

    for row in org(
        "SELECT id, order_code, order_type::text AS kind, status::text AS status"
        " FROM public.orders"
        " WHERE org_id=%s AND (__WHERE__)"
        f" ORDER BY updated_at DESC LIMIT {GROUP_LIMIT}",
        "order_code",
        "supplier_name",
    ):
        results.append(
            {
                "group": "orders",
                "id": str(row["id"]),
                "title": row["order_code"],
                "subtitle": row["status"],
                "path": "/production" if row["kind"] == "WORKSHOP_OT" else "/purchasing",
            }
        )

    for row in org(
        "SELECT i.id, i.invoice_code, i.project_id, pr.code AS project_code"
        " FROM public.project_invoices i JOIN public.projects pr ON pr.id = i.project_id"
        " WHERE i.org_id=%s AND pr.org_id=%s AND (__WHERE__)"
        f" ORDER BY i.created_at DESC LIMIT {GROUP_LIMIT}",
        "i.invoice_code",
        org_params=2,
    ):
        results.append(
            {
                "group": "documents",
                "id": str(row["id"]),
                "title": row["invoice_code"],
                "subtitle": row["project_code"],
                "path": f"/projects/{row['project_id']}",
            }
        )

    for row in org(
        "SELECT d.id, d.note_code, o.order_code"
        " FROM public.dispatch_notes d JOIN public.orders o ON o.id = d.work_order_id"
        " WHERE d.org_id=%s AND d.voided_at IS NULL AND o.org_id=%s AND (__WHERE__)"
        f" ORDER BY d.created_at DESC LIMIT {GROUP_LIMIT}",
        "d.note_code",
        org_params=2,
    ):
        results.append(
            {
                "group": "documents",
                "id": str(row["id"]),
                "title": row["note_code"],
                "subtitle": row["order_code"],
                "path": "/production",
            }
        )

    for row in org(
        "SELECT id, sku, name, category FROM public.inventory_items"
        " WHERE org_id=%s AND (__WHERE__)"
        f" ORDER BY sku LIMIT {GROUP_LIMIT}",
        "sku",
        "name",
    ):
        results.append(
            {
                "group": "inventory",
                "id": str(row["id"]),
                "title": row["sku"],
                "subtitle": row["name"],
                "path": "/purchasing",
            }
        )

    if role == "INSTALLER":
        results = [
            ({**r, "subtitle": None} if r["group"] == "projects" else r)
            for r in results
            if r["group"] not in _INSTALLER_EXCLUDED_GROUPS
        ]

    return {"results": results}
