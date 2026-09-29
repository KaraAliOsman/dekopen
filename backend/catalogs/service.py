"""Tenant-scoped catalog persistence; callers enter authenticated RLS first."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from hashlib import sha256

from django.db import connection

from authentication.errors import contract_error
from authentication.rls import catalog_backend
from documents.repository import DocumentaryError
from catalogs.serializers import (
    ArticleWriteSerializer,
    BeadWriteSerializer,
    KitWriteSerializer,
    SystemWriteSerializer,
)


@dataclass(frozen=True)
class Resource:
    table: str
    serializer: type
    extra_columns: tuple[str, ...] = ()

    @property
    def fields(self):
        return tuple(self.serializer().fields)

    @property
    def projection(self):
        columns = ("id", "org_id", *self.fields, *self.extra_columns)
        return ", ".join(
            f"{name}::text AS {name}" if name in _JSONB_FIELDS else name for name in columns
        )


_PROVENANCE_COLUMNS = (
    "data_provenance",
    "technical_reviewed_at",
    "technical_reviewed_by",
    "review_pending",
)

SYSTEMS = Resource(
    "profile_systems",
    SystemWriteSerializer,
    ("is_global", "is_demo", *_PROVENANCE_COLUMNS),
)
ARTICLES = Resource(
    "profile_articles",
    ArticleWriteSerializer,
    (
        *_PROVENANCE_COLUMNS,
        "section_revision",
        "section_revised_at",
        "section_revised_by",
    ),
)
BEADS = Resource("glazing_bead_matrix", BeadWriteSerializer, _PROVENANCE_COLUMNS)
KITS = Resource("hardware_kits", KitWriteSerializer, _PROVENANCE_COLUMNS)


def _not_found():
    return contract_error(404, "catalog_not_found", "catalogs.errors.not_found")


def _fetch(resource, where, params, *, lock=False):
    suffix = " FOR UPDATE" if lock else " ORDER BY id"
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {resource.projection} FROM public.{resource.table} WHERE {where}{suffix}",
            params,
        )
        names = [column[0] for column in cursor.description]
        result = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
    for row in result:
        row["read_only"] = (
            row["org_id"] is None or row.get("is_global", False) or row.get("is_demo", False)
        )
        for name in _JSONB_FIELDS:
            if name in row and row[name] is not None:
                row[name] = json.loads(
                    row[name],
                    parse_float=Decimal,
                    parse_int=Decimal,
                )
        row["revision"] = catalog_revision(row)
    return result


def import_section_drawing(*, org_id, file_name, content, content_type):
    """Parse a DXF/SVG section drawing into review candidates.

    The document is stored immutable BEFORE the candidates are returned so a
    confirmed pick can reference real provenance (`drawing_ref`); nothing
    reaches an article until a human PATCHes the chosen polygon in.
    """
    from catalogs import section_import
    from documents.storage import SupabaseDocumentStorage
    from ingest.extract import safe_file_name

    if not safe_file_name(file_name):
        raise contract_error(400, "section_file_name", "catalogs.errors.section_file_name")
    if not content or len(content) > 5_000_000:
        raise contract_error(400, "section_file_size", "catalogs.errors.section_file_size")
    try:
        result = section_import.import_section(file_name, content)
    except section_import.SectionImportError as error:
        raise contract_error(400, error.code, f"catalogs.errors.{error.code}") from error
    path = section_import.storage_key(str(org_id), file_name)
    try:
        SupabaseDocumentStorage().upload_immutable(
            path, content, content_type or "application/octet-stream"
        )
    except DocumentaryError as error:
        raise contract_error(503, "section_storage_failed", "catalogs.errors.section_storage") from error
    return {
        "document_path": path,
        "format": result.format,
        "parser_version": section_import.PARSER_VERSION,
        "mm_per_unit": result.mm_per_unit,
        "candidates": result.candidates,
        "warnings": result.warnings,
    }


def catalog_revision(row):
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)
    return "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()


def require_revision(current, expected):
    if expected != '"' + current["revision"] + '"':
        raise contract_error(409, "catalog_stale_edit", "catalogs.errors.stale_edit")


def visibility_sql(*, child: bool, alias: str | None = None) -> str:
    """Canonical catalog visibility — the ONLY definition of who sees what.

    A row is visible when it belongs to the caller's org, or when it is a
    NULL-org row scoped to a global system (the system itself for
    ``child=False``). Every consumer — catalog service, global search,
    future surfaces — resolves visibility through this function so the
    rules can never diverge.
    """
    org_col = f"{alias}.org_id" if alias else "org_id"
    if not child:
        return f"({org_col} = %s OR ({org_col} IS NULL AND {alias + '.' if alias else ''}is_global))"
    system_col = f"{alias}.system_id" if alias else "system_id"
    return (
        f"({org_col} = %s OR ({org_col} IS NULL AND {system_col} IN "
        "(SELECT id FROM public.profile_systems "
        "WHERE org_id IS NULL AND is_global)))"
    )


def _visibility(resource):
    return visibility_sql(child=resource is not SYSTEMS)


def list_rows(resource, org_id, system_id=None):
    where = _visibility(resource)
    params = [org_id]
    if system_id is not None:
        where += " AND system_id = %s"
        params.append(system_id)
    values = _fetch(resource, where, params)
    if resource is SYSTEMS:
        from catalogs.readiness import catalog_readiness
        for value in values:
            value["readiness"] = catalog_readiness(value["id"], org_id)
    return values


def retrieve(resource, org_id, row_id, *, lock=False):
    records = _fetch(
        resource,
        f"id = %s AND {_visibility(resource)}",
        [row_id, org_id],
        lock=lock,
    )
    if not records:
        raise _not_found()
    if resource is SYSTEMS:
        from catalogs.readiness import catalog_readiness
        records[0]["readiness"] = catalog_readiness(records[0]["id"], org_id)
    return records[0]


def _require_owned(row, org_id):
    if row["org_id"] != org_id or row["read_only"]:
        raise contract_error(
            403,
            "catalog_read_only",
            "catalogs.errors.read_only",
        )


def _bind_parent(resource, org_id, values):
    if resource is SYSTEMS:
        return

    system_id = values["system_id"]
    if system_id is None and resource is KITS:
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT (org_id IS NULL AND is_global) "
            "FROM public.profile_systems "
            "WHERE id = %s AND (org_id = %s OR "
            "(org_id IS NULL AND is_global))",
            [system_id, org_id],
        )
        parent = cursor.fetchone()
        if parent is None:
            raise _not_found()

        if resource is BEADS:
            cursor.execute(
                "SELECT id FROM public.profile_articles "
                "WHERE id = %s AND system_id = %s "
                "AND role = 'GLAZING_BEAD' "
                "AND (org_id = %s OR (org_id IS NULL AND %s))",
                [
                    values["bead_article_id"],
                    system_id,
                    org_id,
                    parent[0],
                ],
            )
            if cursor.fetchone() is None:
                raise contract_error(
                    400,
                    "invalid_bead_binding",
                    "catalogs.errors.invalid_bead",
                )


def _contents_json(components):
    # Emit qty as a JSON number, preserving Decimal exactly.
    # Strings remain escaped by the standard JSON encoder.
    encoded = []
    for component in components:
        encoded.append(
            '{"sku":'
            + json.dumps(component["sku"])
            + ',"name":'
            + json.dumps(component["name"])
            + ',"qty":'
            + str(component["qty"])
            + ',"unit":'
            + json.dumps(component["unit"])
            + "}"
        )
    return "[" + ",".join(encoded) + "]"


_JSONB_FIELDS = {"contents", "section", "finishes"}


def _json_value(value):
    """Serialize with Decimals as numeric literals so the stored JSONB keeps
    exact numbers for the repository's parse_float=Decimal decode. Dict keys
    are sorted so a stored jsonb row (key order by length,bytewise) compares
    equal to a freshly validated payload (serializer field order)."""
    if isinstance(value, dict):
        items = (
            json.dumps(str(key)) + ":" + _json_value(value[key])
            for key in sorted(value, key=str)
        )
        return "{" + ",".join(items) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_json_value(item) for item in value) + "]"
    if isinstance(value, Decimal):
        return str(value)
    return json.dumps(value)


def _jsonb(value):
    return None if value is None else _json_value(value)


def _parameters(values):
    return [
        _contents_json(value)
        if name == "contents"
        else _jsonb(value)
        if name in ("section", "finishes")
        else value
        for name, value in values.items()
    ]


def _check_drawing_ref(org_id, section):
    """DXF_REFERENCE provenance must name a stored section import owned by
    this org — the org-scoped storage prefix is what a member can claim; an
    arbitrary string or another tenant's path is not evidence."""
    if not isinstance(section, dict) or section.get("source") != "DXF_REFERENCE":
        return
    ref = (section.get("drawing_ref") or "").strip()
    if not ref.startswith(f"section-imports/{org_id}/"):
        raise contract_error(
            400,
            "catalog_section_ref_invalid",
            "catalogs.errors.section_ref_invalid",
        )


def _stamp_section(values, current, actor_id):
    """§8 revision tracking for the section payload: geometry changes bump
    `section_revision` and record who/when. The stamp lives on real columns —
    inside the JSONB it would ride the same payload it claims to audit."""
    section = values["section"]
    if current is None:
        changed = section is not None
        next_revision = 1
    else:
        prior = current.get("section")
        changed = _json_value(prior) != _json_value(section)
        next_revision = (
            (int(current.get("section_revision") or 0) + 1)
            if prior is not None
            else 1
        )
    if not changed:
        return
    values["section_revision"] = next_revision
    values["section_revised_at"] = datetime.now(timezone.utc)
    values["section_revised_by"] = str(actor_id) if actor_id else None


# Every non-bead, non-coupler role resolves to a single effective article per
# system; glazing beads stay multi-valued per thickness and couplers are
# multi-valued per system (assemblies resolve any catalog SKU).
SINGLETON_ROLES = {
    "FRAME",
    "SASH",
    "MULLION_V",
    "MULLION_H",
    "INVERSOR",
    "ADDITIONAL",
    "THRESHOLD",
}


def _lock_singleton_role(system_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            [str(system_id)],
        )


def create(resource, org_id, values, actor_id=None):
    _bind_parent(resource, org_id, values)
    if resource is SYSTEMS:
        _check_process_profile(org_id, values)
    if resource is ARTICLES and "section" in values:
        _check_drawing_ref(org_id, values["section"])
        _stamp_section(values, None, actor_id)
    if resource is ARTICLES and values.get("role") in SINGLETON_ROLES:
        _lock_singleton_role(values["system_id"])
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id FROM public.profile_articles "
                f"WHERE system_id = %s AND role = %s AND {_visibility(ARTICLES)}",
                [values["system_id"], values["role"], org_id],
            )
            if cursor.fetchone() is not None:
                raise contract_error(
                    409,
                    "catalog_write_conflict",
                    "catalogs.errors.catalog_constraint_conflict",
                )
    columns = tuple(values)
    placeholders = ["%s::jsonb" if name in _JSONB_FIELDS else "%s" for name in columns]
    with connection.cursor() as cursor, catalog_backend():
        cursor.execute(
            f"INSERT INTO public.{resource.table} "
            f"(org_id, {', '.join(columns)}) "
            f"VALUES (%s, {', '.join(placeholders)}) RETURNING id",
            [org_id, *_parameters(values)],
        )
        row_id = cursor.fetchone()[0]
    return retrieve(resource, org_id, row_id)


def update(resource, org_id, row_id, values, expected_revision=None, actor_id=None):
    _require_owned(retrieve(resource, org_id, row_id), org_id)
    current = retrieve(resource, org_id, row_id, lock=True)
    _require_owned(current, org_id)
    require_revision(current, expected_revision)
    validator = resource.serializer(instance=current, data=values, partial=True)
    if not validator.is_valid():
        raise contract_error(
            400,
            "catalog_validation_error",
            "catalogs.errors.validation",
            error_extra={"fields": validator.errors},
        )
    values = validator.validated_data
    if resource is ARTICLES and "section" in values:
        _check_drawing_ref(org_id, values["section"])
        _stamp_section(values, current, actor_id)
    if "system_id" in values and values["system_id"] != current["system_id"]:
        raise contract_error(
            400,
            "catalog_parent_immutable",
            "catalogs.errors.parent_immutable",
        )
    target_role = values.get("role", current.get("role"))
    if resource is ARTICLES and target_role in SINGLETON_ROLES:
        target_system_id = values.get("system_id", current.get("system_id"))
        _lock_singleton_role(target_system_id)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id FROM public.profile_articles "
                f"WHERE system_id = %s AND role = %s AND id != %s AND {_visibility(ARTICLES)}",
                [target_system_id, target_role, row_id, org_id],
            )
            if cursor.fetchone() is not None:
                raise contract_error(
                    409,
                    "catalog_write_conflict",
                    "catalogs.errors.catalog_constraint_conflict",
                )
    _bind_parent(resource, org_id, {**current, **values})
    if resource is SYSTEMS:
        _check_process_profile(org_id, values)
    if values:
        assignments = [
            f"{name} = %s::jsonb" if name in _JSONB_FIELDS else f"{name} = %s" for name in values
        ]
        if set(_PROVENANCE_COLUMNS) & set(current):
            # Editing a reviewed technical row re-opens its review — the new
            # values are unverified until reviewed again. review_pending keeps
            # that visible to readiness: a never-reviewed authored row keeps
            # FALSE, a reviewed-then-edited one becomes TRUE.
            assignments += [
                "technical_reviewed_at = NULL",
                "technical_reviewed_by = NULL",
                "review_pending = review_pending OR technical_reviewed_at IS NOT NULL",
            ]
        with connection.cursor() as cursor, catalog_backend():
            cursor.execute(
                f"UPDATE public.{resource.table} SET {', '.join(assignments)} "
                "WHERE id = %s AND org_id = %s",
                [*_parameters(values), row_id, org_id],
            )
            if cursor.rowcount != 1:
                raise contract_error(
                    409, "catalog_write_conflict", "catalogs.errors.catalog_constraint_conflict"
                )
    return retrieve(resource, org_id, row_id)


def review(resource, org_id, row_id, user_id, expected_revision=None):
    """Mark a catalog row technically reviewed. A LEGACY_UNVERIFIED row a
    human has vouched for becomes MANUAL; other provenance stays truthful.
    If-Match is required: approving a revision that was edited under you is
    not a review of what you read."""
    current = retrieve(resource, org_id, row_id, lock=True)
    _require_owned(current, org_id)
    require_revision(current, expected_revision)
    with connection.cursor() as cursor, catalog_backend():
        cursor.execute(
            f"UPDATE public.{resource.table} SET "
            "technical_reviewed_at = now(), technical_reviewed_by = %s, "
            "review_pending = FALSE, "
            "data_provenance = CASE WHEN data_provenance = 'LEGACY_UNVERIFIED' "
            "THEN 'MANUAL' ELSE data_provenance END "
            "WHERE id = %s AND org_id = %s",
            [str(user_id), row_id, org_id],
        )
        if cursor.rowcount != 1:
            raise contract_error(
                409, "catalog_write_conflict", "catalogs.errors.catalog_constraint_conflict"
            )
    return retrieve(resource, org_id, row_id)


def delete(resource, org_id, row_id, expected_revision=None):
    _require_owned(retrieve(resource, org_id, row_id), org_id)
    current = retrieve(resource, org_id, row_id, lock=True)
    _require_owned(current, org_id)
    require_revision(current, expected_revision)
    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM public.{resource.table} WHERE id = %s AND org_id = %s",
            [row_id, org_id],
        )
        if cursor.rowcount != 1:
            raise contract_error(
                409, "catalog_write_conflict", "catalogs.errors.catalog_constraint_conflict"
            )


_WORKSPACE_JSONB = (
    "stations",
    "operation_station_map",
    "optional_operations",
    "machine_neutral_machining",
    "provenance",
)


def _rows_dicts(query, params):
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def system_workspace(org_id, system_id):
    """§06 system home — one aggregate read for the workspace: the system
    (with readiness), its articles, beads, kits, reinforcement profiles,
    purchase mappings and bound process profile. Same visibility canon as
    every other catalog read — an org sees its own rows plus NULL-org rows
    on global authorities."""
    system = retrieve(SYSTEMS, org_id, system_id)
    articles = list_rows(ARTICLES, org_id, system_id)
    beads = list_rows(BEADS, org_id, system_id)
    kits = list_rows(KITS, org_id, system_id)

    article_ids = [str(article["id"]) for article in articles]
    purchase_mappings = (
        _rows_dicts(
            "SELECT m.id,m.org_id,m.profile_article_id,m.commercial_sku,"
            "m.manufacturer_name,m.supplier_name,m.purchase_unit,m.is_active "
            "FROM public.profile_purchase_mappings m "
            "WHERE m.profile_article_id = ANY(%s::uuid[]) "
            "AND (m.org_id = %s OR m.org_id IS NULL) "
            "ORDER BY m.profile_article_id,m.commercial_sku",
            [article_ids, org_id],
        )
        if article_ids
        else []
    )
    reinforcements = _rows_dicts(
        "SELECT r.id,r.org_id,r.system_id,r.parent_profile_article_id,r.sku,"
        "r.commercial_sku,r.name,r.manufacturer_name,r.supplier_name,"
        "r.stock_length_mm::text,r.thickness_mm::text,r.ix_cm4::text,"
        "r.purchase_unit,r.is_default,r.is_active "
        "FROM public.reinforcement_articles r "
        f"WHERE r.system_id = %s AND {visibility_sql(child=True, alias='r')} "
        "ORDER BY r.parent_profile_article_id,r.sku",
        [system_id, org_id],
    )
    process_profile = None
    if system.get("process_profile_id"):
        rows_found = _rows_dicts(
            "SELECT p.id,p.org_id,p.code,p.version,p.label,p.material,"
            "p.product_kind,p.joining_method,p.corner_process,p.cleaning_process,"
            "p.stations::text,p.operation_station_map::text,"
            "p.sash_assembly_required,p.hardware_station,p.glazing,p.qc,"
            "p.packaging,p.optional_operations::text,"
            "p.machine_neutral_machining::text,p.provenance::text "
            "FROM public.manufacturing_process_profiles p "
            "WHERE p.id = %s AND (p.org_id IS NULL OR p.org_id = %s)",
            [system["process_profile_id"], org_id],
        )
        if rows_found:
            process_profile = rows_found[0]
            for name in _WORKSPACE_JSONB:
                if process_profile.get(name) is not None:
                    process_profile[name] = json.loads(
                        process_profile[name], parse_float=Decimal, parse_int=Decimal
                    )
    return {
        "system": system,
        "articles": articles,
        "beads": beads,
        "kits": kits,
        "reinforcements": reinforcements,
        "purchase_mappings": purchase_mappings,
        "process_profile": process_profile,
    }


def _check_process_profile(org_id, values):
    """A system may bind only a global or org-owned process profile — the
    trigger enforces it too, but the API must refuse with a contract error
    before the write reaches the trigger's 500."""
    profile_id = values.get("process_profile_id")
    if not profile_id:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM public.manufacturing_process_profiles "
            "WHERE id = %s AND (org_id IS NULL OR org_id = %s)",
            [str(profile_id), org_id],
        )
        if cursor.fetchone() is None:
            raise contract_error(
                400,
                "invalid_process_profile",
                "catalogs.errors.invalid_process_profile",
            )


def process_profile_options(org_id):
    """Process authorities visible to this org — global rows and its own —
    for the system→profile binding picker. Bounded deliberately: this feeds
    a select, not a bulk export."""
    return _rows_dicts(
        "SELECT id,org_id,code,version,label,material,product_kind "
        "FROM public.manufacturing_process_profiles "
        "WHERE org_id IS NULL OR org_id = %s "
        "ORDER BY org_id NULLS FIRST,code,version DESC LIMIT 200",
        [org_id],
    )
