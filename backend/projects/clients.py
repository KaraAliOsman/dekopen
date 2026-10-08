"""Client registry: org-scoped records the project form picks from.

The project keeps its own client_* fields as the address-of-record snapshot —
sealed documents never read this table. The link exists so reuse stays
consistent and the picker can prefill. Clients are deactivated, never deleted:
historic projects may reference them.

P22 turns the flat card into a full ficha: persona/empresa, contacts with
role, multiple obra addresses, append-only notes (author + date), duplicate
detection by normalized RUT and an audited merge that repoints every live
reference to the survivor.
"""

from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError, transaction

from authentication.errors import contract_error
from documents.repository import documentary_backend
from pricing.repository import commercial_backend, rows, write
from rut import rut_mod11_valid

COLUMNS = (
    "id",
    "name",
    "rut",
    "email",
    "phone",
    "address",
    "giro",
    "comuna",
    "kind",
    "is_active",
    "merged_into",
    "merged_at",
    "created_at",
    "updated_at",
)
FIELDS = ("name", "rut", "email", "phone", "address", "giro", "comuna", "kind")

ACTIVE_PROJECT_STATUSES = ("DRAFT", "QUOTED", "APPROVED", "IN_PRODUCTION")


def missing():
    raise contract_error(404, "client_not_found", "El cliente no está disponible.")


def client_row(org_id, client_id, *, lock=False):
    result = rows(
        f"SELECT {','.join(COLUMNS)} FROM public.clients "
        "WHERE id=%s AND org_id=%s" + (" FOR UPDATE" if lock else ""),
        [client_id, org_id],
    )
    if not result:
        missing()
    return result[0]


def _public(row):
    return {
        "id": str(row["id"]),
        "name": row["name"] or "",
        "rut": row["rut"] or "",
        "email": row["email"] or "",
        "phone": row["phone"] or "",
        "address": row["address"] or "",
        "giro": row["giro"] or "",
        "comuna": row["comuna"] or "",
        "kind": row["kind"],
        "is_active": row["is_active"],
        "merged_into": str(row["merged_into"]) if row["merged_into"] else None,
        "merged_at": row["merged_at"].isoformat() if row["merged_at"] else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def client_public(org_id, client_id):
    return _public(client_row(org_id, client_id))


def _normalized_rut(value):
    """RUT comparisons ignore punctuation and case: «76.123.456-7» and
    «76123456-7» are the same taxpayer."""
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _validate_rut(value):
    rut = _clean(value)
    if rut and not rut_mod11_valid(rut):
        raise contract_error(
            400, "client_rut_invalid", "El RUT no pasa la verificación de dígito."
        )
    return rut


def _deal_aggregates(org_id, client_ids=None):
    """Billed/collected/balance per client. Deal = latest sealed revision's
    gross when one exists, else the live project totals (zero for unpriced
    projects — same verdict `_deal` gives). Runs under documentary_backend:
    project_versions/project_payments are not `authenticated`-readable."""
    params = [str(org_id)]
    scope = ""
    if client_ids is not None:
        scope = "AND p.client_id = ANY(%s::uuid[])"
        params.append([str(item) for item in client_ids])
    with documentary_backend():
        found = rows(
            "SELECT p.client_id,\n"
            "  COUNT(*)::int AS projects_count,\n"
            "  COUNT(*) FILTER (WHERE p.status = ANY(%s::public.project_status[]))::int"
            "    AS active_projects,\n"
            "  COALESCE(SUM(COALESCE(v.gross, p.total_price_gross)), 0) AS billed_total,\n"
            "  COALESCE(SUM(pay.collected), 0) AS collected_total\n"
            "FROM public.projects p\n"
            "LEFT JOIN LATERAL (\n"
            "  SELECT (pv.snapshot_json->'project'->>'total_price_gross')::numeric AS gross\n"
            "  FROM public.project_versions pv\n"
            "  WHERE pv.project_id = p.id AND pv.org_id = p.org_id\n"
            "  ORDER BY pv.emitted_at DESC, pv.id DESC LIMIT 1\n"
            ") v ON TRUE\n"
            "LEFT JOIN LATERAL (\n"
            "  SELECT COALESCE(SUM(pp.amount), 0) AS collected\n"
            "  FROM public.project_payments pp\n"
            "  WHERE pp.project_id = p.id AND pp.org_id = p.org_id AND pp.voided_at IS NULL\n"
            ") pay ON TRUE\n"
            "WHERE p.org_id = %s AND p.client_id IS NOT NULL "
            + scope
            + "\nGROUP BY p.client_id",
            [list(ACTIVE_PROJECT_STATUSES), *params],
        )
    return {str(item["client_id"]): item for item in found}


def list_clients(org_id, *, query=None, filter_kind=None):
    """Lista maestra: búsqueda por nombre o RUT (normalizado) y filtros
    `activos` (al menos un proyecto no cerrado) / `saldo` (por cobrar > 0)."""
    items = rows(
        f"SELECT {','.join(COLUMNS)} FROM public.clients "
        "WHERE org_id=%s AND merged_into IS NULL "
        "ORDER BY is_active DESC, name, id LIMIT 500",
        [org_id],
    )
    needle = (query or "").strip()
    if needle:
        digits = _normalized_rut(needle)
        lowered = needle.lower()
        items = [
            row
            for row in items
            if lowered in (row["name"] or "").lower()
            or (digits and digits in _normalized_rut(row["rut"]))
        ]
    aggregates = _deal_aggregates(org_id)
    result = []
    for row in items:
        agg = aggregates.get(str(row["id"]), {})
        balance = Decimal(str(agg.get("billed_total", 0))) - Decimal(
            str(agg.get("collected_total", 0))
        )
        public = {
            **_public(row),
            "projects_count": int(agg.get("projects_count", 0)),
            "active_projects": int(agg.get("active_projects", 0)),
            "balance": balance,
        }
        if filter_kind == "active" and public["active_projects"] == 0:
            continue
        if filter_kind == "balance" and balance <= 0:
            continue
        result.append(public)
    return result


def _contacts_public(found):
    return [
        {
            "id": str(item["id"]),
            "name": item["name"],
            "role_label": item["role_label"] or "",
            "email": item["email"] or "",
            "phone": item["phone"] or "",
            "is_primary": item["is_primary"],
            "updated_at": item["updated_at"].isoformat(),
        }
        for item in found
    ]


def _addresses_public(found):
    return [
        {
            "id": str(item["id"]),
            "label": item["label"],
            "address": item["address"],
            "comuna": item["comuna"] or "",
            "is_default": item["is_default"],
            "updated_at": item["updated_at"].isoformat(),
        }
        for item in found
    ]


def _replace_contacts(org_id, client_id, contacts):
    """Full-replace semantics like position saves: the ficha sends the whole
    list; each contact is a flat row, so diffing adds nothing."""
    write(
        "DELETE FROM public.client_contacts WHERE org_id=%s AND client_id=%s",
        [org_id, client_id],
    )
    for position, contact in enumerate(contacts or []):
        write(
            "INSERT INTO public.client_contacts"
            "(id,org_id,client_id,name,role_label,email,phone,is_primary,updated_at)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())",
            [
                uuid4(),
                org_id,
                client_id,
                _clean(contact.get("name")) or "—",
                _clean(contact.get("role_label")),
                _clean(contact.get("email")),
                _clean(contact.get("phone")),
                bool(contact.get("is_primary")),
            ],
        )


def _replace_addresses(org_id, client_id, addresses):
    write(
        "DELETE FROM public.client_addresses WHERE org_id=%s AND client_id=%s",
        [org_id, client_id],
    )
    for address in addresses or []:
        write(
            "INSERT INTO public.client_addresses"
            "(id,org_id,client_id,label,address,comuna,is_default,updated_at)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,clock_timestamp())",
            [
                uuid4(),
                org_id,
                client_id,
                _clean(address.get("label")) or "Obra",
                _clean(address.get("address")) or "—",
                _clean(address.get("comuna")),
                bool(address.get("is_default")),
            ],
        )


def create_client(org_id, actor_id, data):
    try:
        identity = uuid4()
        values = {key: _clean(data.get(key)) for key in FIELDS}
        values["rut"] = _validate_rut(data.get("rut"))
        with transaction.atomic():
            rows(
                "INSERT INTO public.clients(id,org_id,created_by,"
                + ",".join(FIELDS)
                + ") VALUES("
                + ",".join(["%s"] * (3 + len(FIELDS)))
                + ") RETURNING id",
                [identity, org_id, actor_id, *[values[key] for key in FIELDS]],
            )
            _replace_contacts(org_id, identity, data.get("contacts"))
            _replace_addresses(org_id, identity, data.get("addresses"))
    except IntegrityError as error:
        raise contract_error(
            409, "client_rut_conflict", "Ya existe un cliente con ese RUT."
        ) from error
    return _public(client_row(org_id, identity))


def update_client(org_id, client_id, data):
    row = client_row(org_id, client_id, lock=True)
    if row["merged_into"]:
        raise contract_error(
            409, "client_merged", "El cliente fue fusionado; edita la ficha sobreviviente."
        )
    if row["updated_at"] != data["expected_updated_at"]:
        raise contract_error(
            409, "stale_edit", "Otra persona guardó cambios. Recarga antes de reemplazarlos."
        )
    values = {key: _clean(data[key]) for key in FIELDS if key in data}
    if "rut" in values:
        values["rut"] = _validate_rut(values["rut"])
    if "name" in values and not values["name"]:
        raise contract_error(400, "validation_error", "El nombre del cliente es obligatorio.")
    try:
        with transaction.atomic():
            if values:
                rows(
                    "UPDATE public.clients SET "
                    + ",".join(f"{key}=%s" for key in values)
                    + ",updated_at=clock_timestamp() WHERE id=%s AND org_id=%s RETURNING id",
                    [*values.values(), client_id, org_id],
                )
            if "contacts" in data:
                _replace_contacts(org_id, client_id, data["contacts"])
            if "addresses" in data:
                _replace_addresses(org_id, client_id, data["addresses"])
    except IntegrityError as error:
        raise contract_error(
            409, "client_rut_conflict", "Ya existe un cliente con ese RUT."
        ) from error
    return _public(client_row(org_id, client_id))


def deactivate_client(org_id, client_id):
    row = client_row(org_id, client_id)
    write(
        "UPDATE public.clients SET is_active=FALSE,updated_at=clock_timestamp() "
        "WHERE id=%s AND org_id=%s",
        [row["id"], org_id],
    )


def linkable_client(org_id, client_id):
    """A project may only link a client that exists in the same org; the
    record may be inactive (historic projects keep their links) but never
    foreign, and never one absorbed by a merge — that client no longer
    exists commercially."""
    row = client_row(org_id, client_id)
    if row["merged_into"]:
        raise contract_error(
            409,
            "client_merged",
            "El cliente fue fusionado; usa la ficha sobreviviente.",
        )


def _notes(org_id, client_id):
    return [
        {
            "id": str(item["id"]),
            "author_label": item["author_label"],
            "body": item["body"],
            "created_at": item["created_at"].isoformat(),
        }
        for item in rows(
            "SELECT id,author_label,body,created_at FROM public.client_notes "
            "WHERE org_id=%s AND client_id=%s ORDER BY created_at DESC, id DESC",
            [org_id, client_id],
        )
    ]


def add_note(org_id, client_id, actor_id, actor_label, body):
    row = client_row(org_id, client_id)
    if row["merged_into"]:
        raise contract_error(409, "client_merged", "El cliente fue fusionado.")
    if not (body or "").strip():
        raise contract_error(400, "validation_error", "La nota no puede ir vacía.")
    write(
        "INSERT INTO public.client_notes(org_id,client_id,author_id,author_label,body)"
        " VALUES(%s,%s,%s,%s,%s)",
        [org_id, row["id"], actor_id, actor_label, body.strip()],
    )


def client_detail(org_id, client_id):
    row = client_row(org_id, client_id)
    contacts = rows(
        "SELECT id,name,role_label,email,phone,is_primary,updated_at "
        "FROM public.client_contacts WHERE org_id=%s AND client_id=%s "
        "ORDER BY is_primary DESC, created_at, id",
        [org_id, client_id],
    )
    addresses = rows(
        "SELECT id,label,address,comuna,is_default,updated_at "
        "FROM public.client_addresses WHERE org_id=%s AND client_id=%s "
        "ORDER BY is_default DESC, created_at, id",
        [org_id, client_id],
    )
    with documentary_backend():
        projects = rows(
            "SELECT p.id, p.code, p.name, p.status, p.delivery_address, p.created_at,\n"
            "  COALESCE(v.gross, p.total_price_gross) AS billed,\n"
            "  COALESCE(pay.collected, 0) AS collected\n"
            "FROM public.projects p\n"
            "LEFT JOIN LATERAL (\n"
            "  SELECT (pv.snapshot_json->'project'->>'total_price_gross')::numeric AS gross\n"
            "  FROM public.project_versions pv\n"
            "  WHERE pv.project_id = p.id AND pv.org_id = p.org_id\n"
            "  ORDER BY pv.emitted_at DESC, pv.id DESC LIMIT 1\n"
            ") v ON TRUE\n"
            "LEFT JOIN LATERAL (\n"
            "  SELECT COALESCE(SUM(pp.amount), 0) AS collected\n"
            "  FROM public.project_payments pp\n"
            "  WHERE pp.project_id = p.id AND pp.org_id = p.org_id AND pp.voided_at IS NULL\n"
            ") pay ON TRUE\n"
            "WHERE p.org_id=%s AND p.client_id=%s\n"
            "ORDER BY p.created_at DESC, p.id DESC LIMIT 200",
            [str(org_id), client_id],
        )
        quotations = rows(
            "SELECT pv.project_id, pv.revision_code, pv.emitted_at,\n"
            "  pv.snapshot_json->'project'->>'total_price_gross' AS gross,\n"
            "  pv.snapshot_json->'project'->>'currency' AS currency\n"
            "FROM public.project_versions pv\n"
            "JOIN public.projects p ON p.id = pv.project_id AND p.org_id = pv.org_id\n"
            "WHERE pv.org_id=%s AND p.client_id=%s\n"
            "ORDER BY pv.emitted_at DESC, pv.id DESC LIMIT 100",
            [str(org_id), client_id],
        )
        payments = rows(
            "SELECT pp.id, pp.project_id, p.code AS project_code, pp.kind, pp.amount,\n"
            "  pp.method, pp.recorded_at, pp.voided_at, pr.receipt_code\n"
            "FROM public.project_payments pp\n"
            "JOIN public.projects p ON p.id = pp.project_id AND p.org_id = pp.org_id\n"
            "LEFT JOIN public.payment_receipts pr\n"
            "  ON pr.payment_id = pp.id AND pr.org_id = pp.org_id\n"
            "WHERE pp.org_id=%s AND p.client_id=%s\n"
            "ORDER BY pp.recorded_at DESC, pp.id DESC LIMIT 200",
            [str(org_id), client_id],
        )
        documents = rows(
            "SELECT da.id, da.project_id, p.code AS project_code, da.document_type,\n"
            "  da.format, da.created_at\n"
            "FROM public.document_artifacts da\n"
            "JOIN public.projects p ON p.id = da.project_id AND p.org_id = da.org_id\n"
            "WHERE da.org_id=%s AND p.client_id=%s\n"
            "ORDER BY da.created_at DESC, da.id DESC LIMIT 100",
            [str(org_id), client_id],
        )
    merges = rows(
        "SELECT id,survivor_id,merged_client_id,actor_label,detail,created_at "
        "FROM public.client_merges "
        "WHERE org_id=%s AND (survivor_id=%s OR merged_client_id=%s) "
        "ORDER BY created_at DESC, id DESC",
        [org_id, client_id, client_id],
    )
    totals = _deal_aggregates(org_id, [client_id]).get(str(client_id), {})
    billed = Decimal(str(totals.get("billed_total", 0)))
    collected = Decimal(str(totals.get("collected_total", 0)))
    return {
        "client": _public(row),
        "contacts": _contacts_public(contacts),
        "addresses": _addresses_public(addresses),
        "notes": _notes(org_id, client_id),
        "projects": [
            {
                "id": str(item["id"]),
                "code": item["code"],
                "name": item["name"],
                "status": item["status"],
                "delivery_address": item["delivery_address"] or "",
                "billed": item["billed"],
                "collected": item["collected"],
                "balance": Decimal(str(item["billed"] or 0))
                - Decimal(str(item["collected"] or 0)),
                "created_at": item["created_at"].isoformat(),
            }
            for item in projects
        ],
        "quotations": [
            {
                "project_id": str(item["project_id"]),
                "revision_code": item["revision_code"],
                "emitted_at": item["emitted_at"].isoformat(),
                "total_price_gross": item["gross"],
                "currency": item["currency"] or "CLP",
            }
            for item in quotations
        ],
        "payments": [
            {
                "id": str(item["id"]),
                "project_id": str(item["project_id"]),
                "project_code": item["project_code"],
                "kind": item["kind"],
                "amount": item["amount"],
                "method": item["method"],
                "receipt_code": item["receipt_code"],
                "voided": item["voided_at"] is not None,
                "recorded_at": item["recorded_at"].isoformat(),
            }
            for item in payments
        ],
        "documents": [
            {
                "id": str(item["id"]),
                "project_id": str(item["project_id"]),
                "project_code": item["project_code"],
                "document_type": item["document_type"],
                "format": item["format"],
                "created_at": item["created_at"].isoformat(),
            }
            for item in documents
        ],
        "merges": [
            {
                "id": str(item["id"]),
                "survivor_id": str(item["survivor_id"]),
                "merged_client_id": str(item["merged_client_id"]),
                "actor_label": item["actor_label"],
                "detail": item["detail"] if isinstance(item["detail"], dict) else {},
                "created_at": item["created_at"].isoformat(),
            }
            for item in merges
        ],
        "totals": {
            "billed": billed,
            "collected": collected,
            "balance": billed - collected,
            "currency": "CLP",
        },
    }


def duplicates(org_id):
    """Groups of still-live clients sharing a normalized RUT — the unique
    index is on the raw text, so «12.345.678-9» and «12345678-9» coexist."""
    found = rows(
        "SELECT id,name,rut,email,created_at FROM public.clients "
        "WHERE org_id=%s AND merged_into IS NULL ORDER BY created_at, id",
        [org_id],
    )
    groups = {}
    for row in found:
        key = _normalized_rut(row["rut"])
        if key:
            groups.setdefault(key, []).append(row)
    return [
        {
            "rut": key,
            "clients": [
                {
                    "id": str(item["id"]),
                    "name": item["name"],
                    "rut": item["rut"],
                    "created_at": item["created_at"].isoformat(),
                }
                for item in members
            ],
        }
        for key, members in groups.items()
        if len(members) > 1
    ]


def merge_clients(org_id, survivor_id, merged_id, actor_id, actor_label):
    """Audited merge: every live reference repoints to the survivor, the
    absorbed client is deactivated and stamped, and `client_merges` records
    who did it and what moved. Sealed documents are untouched — they froze
    their client data at emission."""
    if str(survivor_id) == str(merged_id):
        raise contract_error(400, "validation_error", "Elige dos clientes distintos.")
    with transaction.atomic():
        survivor = client_row(org_id, survivor_id, lock=True)
        merged = client_row(org_id, merged_id, lock=True)
        if survivor["merged_into"] or merged["merged_into"]:
            raise contract_error(
                409, "client_merged", "Uno de los clientes ya fue fusionado."
            )
        moved = {}
        for table in ("projects", "client_contacts", "client_addresses", "client_notes"):
            moved[table] = int(
                one_count(
                    f"SELECT COUNT(*) AS n FROM public.{table} "
                    "WHERE org_id=%s AND client_id=%s",
                    [org_id, merged_id],
                )["n"]
            )
            if table == "projects":
                continue
            write(
                f"UPDATE public.{table} SET client_id=%s "
                "WHERE org_id=%s AND client_id=%s",
                [survivor_id, org_id, merged_id],
            )
        # Los writes sobre projects pasan por guard_commercial_write, que
        # exige el rol de servicio de precios — las tablas de clientes se
        # quedan en `authenticated`, donde viven sus grants.
        with commercial_backend():
            write(
                "UPDATE public.projects SET client_id=%s "
                "WHERE org_id=%s AND client_id=%s",
                [survivor_id, org_id, merged_id],
            )
            # Proyectos heredan la identidad del sobreviviente en sus
            # campos vivos — los documentos ya emitidos conservan la
            # foto sellada.
            write(
                "UPDATE public.projects SET client_name=%s, client_rut=%s, "
                "client_email=%s, client_phone=%s, client_giro=%s, "
                "client_comuna=%s, updated_at=clock_timestamp() "
                "WHERE org_id=%s AND client_id=%s",
                [
                    survivor["name"],
                    survivor["rut"],
                    survivor["email"],
                    survivor["phone"],
                    survivor["giro"],
                    survivor["comuna"],
                    org_id,
                    survivor_id,
                ],
            )
        write(
            "UPDATE public.clients SET is_active=FALSE, merged_into=%s, "
            "merged_at=clock_timestamp(), updated_at=clock_timestamp() "
            "WHERE id=%s AND org_id=%s",
            [survivor_id, merged_id, org_id],
        )
        write(
            "INSERT INTO public.client_merges"
            "(org_id,survivor_id,merged_client_id,actor_id,actor_label,detail)"
            " VALUES(%s,%s,%s,%s,%s,%s::jsonb)",
            [
                org_id,
                survivor_id,
                merged_id,
                actor_id,
                actor_label,
                json_dumps(moved),
            ],
        )
    return client_detail(org_id, survivor_id)


def one_count(sql, params):
    from pricing.repository import one

    return one(sql, params)


def json_dumps(value):
    import json

    return json.dumps(value, default=str)


def _clean(value):
    text = (value or "").strip()
    return text or None
