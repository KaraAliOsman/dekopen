"""Client registry: org-scoped records the project form picks from.

The project keeps its own client_* fields as the address-of-record snapshot —
sealed documents never read this table. The link exists so reuse stays
consistent and the picker can prefill. Clients are deactivated, never deleted:
historic projects may reference them.
"""

from uuid import uuid4

from django.db import IntegrityError

from authentication.errors import contract_error
from pricing.repository import rows

COLUMNS = (
    "id",
    "name",
    "rut",
    "email",
    "phone",
    "address",
    "giro",
    "comuna",
    "notes",
    "is_active",
    "created_at",
    "updated_at",
)
FIELDS = ("name", "rut", "email", "phone", "address", "giro", "comuna", "notes")


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
        **{key: row[key] or "" for key in FIELDS},
        "is_active": row["is_active"],
        "updated_at": row["updated_at"].isoformat(),
    }


def client_public(org_id, client_id):
    return _public(client_row(org_id, client_id))


def list_clients(org_id):
    return [
        _public(row)
        for row in rows(
            f"SELECT {','.join(COLUMNS)} FROM public.clients "
            "WHERE org_id=%s ORDER BY is_active DESC, name, id LIMIT 500",
            [org_id],
        )
    ]


def create_client(org_id, actor_id, data):
    try:
        identity = uuid4()
        rows(
            "INSERT INTO public.clients(id,org_id,created_by,"
            + ",".join(FIELDS)
            + ") VALUES("
            + ",".join(["%s"] * (3 + len(FIELDS)))
            + ") RETURNING id",
            [identity, org_id, actor_id, *[_clean(data.get(key)) for key in FIELDS]],
        )
    except IntegrityError as error:
        raise contract_error(
            409, "client_rut_conflict", "Ya existe un cliente con ese RUT."
        ) from error
    return _public(client_row(org_id, identity))


def update_client(org_id, client_id, data):
    row = client_row(org_id, client_id, lock=True)
    if row["updated_at"] != data["expected_updated_at"]:
        raise contract_error(
            409, "stale_edit", "Otra persona guardó cambios. Recarga antes de reemplazarlos."
        )
    values = {key: _clean(data[key]) for key in FIELDS if key in data}
    if "name" in values and not values["name"]:
        raise contract_error(400, "validation_error", "El nombre del cliente es obligatorio.")
    if not values:
        return _public(row)
    try:
        rows(
            "UPDATE public.clients SET "
            + ",".join(f"{key}=%s" for key in values)
            + ",updated_at=clock_timestamp() WHERE id=%s AND org_id=%s RETURNING id",
            [*values.values(), client_id, org_id],
        )
    except IntegrityError as error:
        raise contract_error(
            409, "client_rut_conflict", "Ya existe un cliente con ese RUT."
        ) from error
    return _public(client_row(org_id, client_id))


def deactivate_client(org_id, client_id):
    row = client_row(org_id, client_id)
    rows(
        "UPDATE public.clients SET is_active=FALSE,updated_at=clock_timestamp() "
        "WHERE id=%s AND org_id=%s RETURNING id",
        [row["id"], org_id],
    )


def linkable_client(org_id, client_id):
    """A project may only link a client that exists in the same org; the
    record may be inactive (historic projects keep their links) but never
    foreign."""
    client_row(org_id, client_id)


def _clean(value):
    text = (value or "").strip()
    return text or None
