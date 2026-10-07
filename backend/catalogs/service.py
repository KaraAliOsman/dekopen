"""Tenant-scoped catalog persistence; callers enter authenticated RLS first."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from hashlib import sha256

from django.db import connection

from authentication.errors import contract_error
from authentication.rls import catalog_backend
from catalogs.section_check import section_check_failures, section_checks
from documents.repository import DocumentaryError
from catalogs.serializers import (
    ArticleWriteSerializer,
    BeadWriteSerializer,
    ExtraArticleWriteSerializer,
    KitWriteSerializer,
    ServiceArticleWriteSerializer,
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
    ("is_global", "is_demo", "system_family", *_PROVENANCE_COLUMNS),
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
EXTRA_ARTICLES = Resource(
    "extra_articles", ExtraArticleWriteSerializer, _PROVENANCE_COLUMNS
)
# service_articles is org data without a system parent: its visibility is
# the org/global split only (NULL org = the shared seed catalogue).
SERVICE_ARTICLES = Resource(
    "service_articles", ServiceArticleWriteSerializer, _PROVENANCE_COLUMNS
)


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


def visibility_sql(*, child: bool, alias: str | None = None, unscoped: bool = False) -> str:
    """Canonical catalog visibility — the ONLY definition of who sees what.

    A row is visible when it belongs to the caller's org, or when it is a
    NULL-org row scoped to a global system (the system itself for
    ``child=False``). Every consumer — catalog service, global search,
    future surfaces — resolves visibility through this function so the
    rules can never diverge.
    """
    org_col = f"{alias}.org_id" if alias else "org_id"
    if unscoped:
        # No system parent — NULL-org rows are the shared catalogue.
        return f"({org_col} = %s OR {org_col} IS NULL)"
    if not child:
        return f"({org_col} = %s OR ({org_col} IS NULL AND {alias + '.' if alias else ''}is_global))"
    system_col = f"{alias}.system_id" if alias else "system_id"
    return (
        f"({org_col} = %s OR ({org_col} IS NULL AND {system_col} IN "
        "(SELECT id FROM public.profile_systems "
        "WHERE org_id IS NULL AND is_global)))"
    )


def _visibility(resource):
    return visibility_sql(
        child=resource is not SYSTEMS,
        unscoped=resource is SERVICE_ARTICLES,
    )


def list_rows(resource, org_id, system_id=None):
    where = _visibility(resource)
    params = [org_id]
    if system_id is not None and resource is not SERVICE_ARTICLES:
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
    if resource is SYSTEMS or resource is SERVICE_ARTICLES:
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
    "SLIDING_SASH",
    "DOOR_SASH",
    "MULLION_V",
    "MULLION_H",
    "INVERSOR",
    "ADDITIONAL",
    "INTERLOCK",
    "RAIL",
    "FRAME_EXTENSION",
    "SILL",
    "COVER_TRIM",
    "SKIRT",
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
    if resource is SERVICE_ARTICLES and "system_id" in values:
        values.pop("system_id")
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
    not a review of what you read. P16: an article whose declared section
    fails its validations cannot be verified — the geometry must be fixed
    before the stamp is written."""
    current = retrieve(resource, org_id, row_id, lock=True)
    _require_owned(current, org_id)
    require_revision(current, expected_revision)
    if resource is ARTICLES:
        failures = section_check_failures(current.get("section"))
        if failures:
            raise contract_error(
                422,
                "catalog_section_invalid",
                "catalogs.errors.section_invalid",
                error_extra={"checks": failures},
            )
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


def _text_list(value) -> list:
    """Normalize a TEXT[] value to a Python list — psycopg usually returns
    native lists, but a driver/cursor path may hand back the literal
    '{A,B}' instead."""
    if isinstance(value, list):
        return value
    text = (value or "").strip()
    if text in ("{}", "{", ""):
        return []
    if text.startswith("{") and text.endswith("}"):
        return [item.strip().strip('"') for item in text[1:-1].split(",") if item.strip()]
    return [text]


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
    kit_ids = [str(kit["id"]) for kit in kits]
    article_checks = {
        str(article["id"]): section_checks(article.get("section"))
        for article in articles
        if article.get("section") is not None
    }
    return {
        "system": system,
        "articles": articles,
        "article_checks": article_checks,
        "beads": beads,
        "kits": kits,
        "reinforcements": reinforcements,
        "purchase_mappings": purchase_mappings,
        "process_profile": process_profile,
        "glass": _system_glass(org_id, system_id),
        "hardware": _system_hardware(org_id, system_id, kit_ids),
        "rules": _system_rules(org_id, system_id),
        "costs": _system_costs(org_id, system_id, article_ids),
        "history": _system_history(org_id, system_id),
    }


def _reviewer_label(*ids):
    """Resolve reviewer/actor user ids to emails — the member only ever
    sees people inside their own org's rows."""
    found = [str(value) for value in set(ids) if value]
    if not found:
        return {}
    with connection.cursor() as cursor, catalog_backend():
        cursor.execute(
            "SELECT private.user_email(value::uuid) AS email, value "
            "FROM unnest(%s::uuid[]) AS value",
            [found],
        )
        return {str(row[1]): row[0] for row in cursor.fetchall()}


def _system_glass(org_id, system_id):
    """D02 glass catalog for the system tab: compositions (products),
    lamina formats (purchase mappings), surcharges, safety rules and type
    limits. Products bound to another system are hidden; NULL-system rows
    are the org/global fallback catalog."""
    products = _rows_dicts(
        "SELECT g.id,g.org_id,g.system_id,g.sku,g.commercial_name,g.notation,"
        "g.composition::text,g.total_thickness_mm::text,g.safety_class,"
        "g.ug_w_m2k::text,g.g_value::text,g.light_transmission_pct::text,"
        "g.weight_kg_m2::text,g.min_billable_area_m2::text,g.price_tier,"
        "g.supplier_name,g.supplier_sku,g.data_provenance,"
        "g.technical_reviewed_at::text,g.technical_reviewed_by,g.review_pending,"
        "g.is_active,g.created_at::text "
        "FROM public.glass_products g "
        "WHERE (g.system_id=%s OR g.system_id IS NULL) "
        "AND (g.org_id=%s OR g.org_id IS NULL) "
        "ORDER BY g.sku,g.system_id NULLS LAST",
        [system_id, org_id],
    )
    product_ids = [str(product["id"]) for product in products]
    surcharges = (
        _rows_dicts(
            "SELECT s.id,s.org_id,s.product_id,s.kind,s.unit,"
            "s.unit_cost::text,s.currency,s.label,s.is_active,"
            "s.data_provenance,s.technical_reviewed_at::text,"
            "s.technical_reviewed_by,s.review_pending,s.created_at::text "
            "FROM public.glass_product_surcharges s "
            "WHERE s.product_id = ANY(%s::uuid[]) "
            "AND (s.org_id=%s OR s.org_id IS NULL) "
            "ORDER BY s.product_id,s.kind,s.unit",
            [product_ids, org_id],
        )
        if product_ids
        else []
    )
    purchase_mappings = _rows_dicts(
        "SELECT m.id,m.org_id,m.system_id,m.technical_sku,m.purchasing_sku,"
        "m.manufacturer_name,m.purchase_unit,m.version,"
        "m.provenance::text,m.created_at::text "
        "FROM public.glass_purchase_mappings m "
        "WHERE m.system_id=%s AND (m.org_id=%s OR m.org_id IS NULL) "
        "ORDER BY m.technical_sku,m.version",
        [system_id, org_id],
    )
    safety_rules = _rows_dicts(
        "SELECT r.id,r.org_id,r.code,r.title,r.message,"
        "r.applies_openings,r.sill_below_mm::text,r.min_area_m2::text,"
        "r.requires_door,r.requires_adjacent_door,r.required_safety,"
        "r.severity,r.source_ref,r.data_provenance,r.technical_reviewed_at::text,"
        "r.technical_reviewed_by,r.review_pending,r.is_active,"
        "r.created_at::text "
        "FROM public.glass_safety_rules r "
        "WHERE (r.org_id=%s OR r.org_id IS NULL) "
        "ORDER BY r.code",
        [org_id],
    )
    type_limits = _rows_dicts(
        "SELECT l.id,l.org_id,l.code,l.lamina_kind,l.thickness_min_mm::text,"
        "l.thickness_max_mm::text,l.min_side_mm::text,l.max_side_mm::text,"
        "l.min_area_m2::text,l.max_area_m2::text,l.max_aspect_ratio::text,"
        "l.requires_exact_cut,l.severity,l.source_ref,l.data_provenance,"
        "l.technical_reviewed_at::text,l.technical_reviewed_by,"
        "l.review_pending,l.is_active,l.created_at::text "
        "FROM public.glass_type_limits l "
        "WHERE (l.org_id=%s OR l.org_id IS NULL) "
        "ORDER BY l.code",
        [org_id],
    )
    for product in products:
        if product.get("composition") is not None:
            product["composition"] = json.loads(
                product["composition"], parse_float=Decimal, parse_int=Decimal
            )
    for mapping in purchase_mappings:
        if mapping.get("provenance") is not None:
            mapping["provenance"] = json.loads(mapping["provenance"])
    for rule in safety_rules:
        if isinstance(rule.get("applies_openings"), str):
            # TEXT[] comes back as a native list; only decode when a driver
            # returns the Postgres array literal instead.
            rule["applies_openings"] = _text_list(rule["applies_openings"])
    return {
        "products": products,
        "purchase_mappings": purchase_mappings,
        "surcharges": surcharges,
        "safety_rules": safety_rules,
        "type_limits": type_limits,
    }


def _system_hardware(org_id, system_id, kit_ids):
    """D04 hardware catalog for the system tab: families (kit rules per
    opening type), handle models/colors and options, plus purchase
    identities of the kits bound (or resolvable) for the system."""
    families = _rows_dicts(
        "SELECT f.id,f.org_id,f.system_id,f.opening_type,f.handle_height_rule,"
        "f.handle_height_min_mm::text,f.handle_height_max_mm::text,"
        "f.handle_height_default_mm::text,f.data_provenance,"
        "f.technical_reviewed_at::text,f.technical_reviewed_by,"
        "f.review_pending,f.created_at::text "
        "FROM public.hardware_families f "
        "WHERE f.system_id=%s AND (f.org_id=%s OR f.org_id IS NULL) "
        "ORDER BY f.opening_type",
        [system_id, org_id],
    )
    handle_models = _rows_dicts(
        "SELECT m.id,m.org_id,m.system_id,m.opening_type,m.sku,m.name,m.kind,"
        "m.price_delta_clp::text,m.data_provenance,"
        "m.technical_reviewed_at::text,m.technical_reviewed_by,"
        "m.review_pending,m.created_at::text "
        "FROM public.hardware_handle_models m "
        "WHERE m.system_id=%s AND (m.org_id=%s OR m.org_id IS NULL) "
        "ORDER BY m.opening_type,m.sku",
        [system_id, org_id],
    )
    handle_colors = _rows_dicts(
        "SELECT c.id,c.org_id,c.system_id,c.opening_type,c.sku,c.name,"
        "c.price_delta_clp::text,c.data_provenance,"
        "c.technical_reviewed_at::text,c.technical_reviewed_by,"
        "c.review_pending,c.created_at::text "
        "FROM public.hardware_handle_colors c "
        "WHERE c.system_id=%s AND (c.org_id=%s OR c.org_id IS NULL) "
        "ORDER BY c.opening_type,c.sku",
        [system_id, org_id],
    )
    options = _rows_dicts(
        "SELECT o.id,o.org_id,o.system_id,o.opening_type,o.sku,o.name,o.kind,"
        "o.price_delta_clp::text,o.is_active,o.data_provenance,"
        "o.technical_reviewed_at::text,o.technical_reviewed_by,"
        "o.review_pending,o.created_at::text "
        "FROM public.hardware_options o "
        "WHERE o.system_id=%s AND (o.org_id=%s OR o.org_id IS NULL) "
        "ORDER BY o.opening_type,o.sku",
        [system_id, org_id],
    )
    purchase_mappings = (
        _rows_dicts(
            "SELECT m.id,m.org_id,m.hardware_kit_id,m.purchasing_sku,"
            "m.manufacturer_name,m.purchase_unit,m.version,"
            "m.provenance::text,m.created_at::text "
            "FROM public.hardware_purchase_mappings m "
            "WHERE m.hardware_kit_id = ANY(%s::uuid[]) "
            "AND (m.org_id=%s OR m.org_id IS NULL) "
            "ORDER BY m.hardware_kit_id,m.purchasing_sku,m.version",
            [kit_ids, org_id],
        )
        if kit_ids
        else []
    )
    for mapping in purchase_mappings:
        if mapping.get("provenance") is not None:
            mapping["provenance"] = json.loads(mapping["provenance"])
    return {
        "families": families,
        "handle_models": handle_models,
        "handle_colors": handle_colors,
        "options": options,
        "purchase_mappings": purchase_mappings,
    }


def _system_rules(org_id, system_id):
    """Compatibility-rule tables bound to this system: cut rules,
    reinforcement rules, typology limits, opening capabilities, mounting
    rules and inspector configs."""
    cut_rules = _rows_dicts(
        "SELECT r.id,r.org_id,r.system_id,r.role,r.cut_angle_deg::text,"
        "r.welded_ends,r.interlock_deduction_mm::text,r.rounding_mm::text,"
        "r.data_provenance,r.technical_reviewed_at::text,"
        "r.technical_reviewed_by,r.review_pending,r.created_at::text "
        "FROM public.profile_cut_rules r "
        "WHERE r.system_id=%s AND (r.org_id=%s OR r.org_id IS NULL) "
        "ORDER BY r.role",
        [system_id, org_id],
    )
    reinforcement_rules = _rows_dicts(
        "SELECT r.id,r.org_id,r.system_id,r.role,r.finish_class,"
        "r.min_length_mm::text,r.mandatory,r.cut_deduction_mm::text,"
        "r.screws_per_m::text,r.data_provenance,"
        "r.technical_reviewed_at::text,r.technical_reviewed_by,"
        "r.review_pending,r.created_at::text "
        "FROM public.profile_reinforcement_rules r "
        "WHERE r.system_id=%s AND (r.org_id=%s OR r.org_id IS NULL) "
        "ORDER BY r.role,r.finish_class,r.min_length_mm",
        [system_id, org_id],
    )
    typology_limits = _rows_dicts(
        "SELECT l.id,l.org_id,l.system_id,l.opening_type,"
        "l.min_leaf_width_mm::text,l.max_leaf_width_mm::text,"
        "l.min_leaf_height_mm::text,l.max_leaf_height_mm::text,"
        "l.max_leaf_weight_kg::text,l.max_aspect_ratio::text,"
        "l.data_provenance,l.technical_reviewed_at::text,"
        "l.technical_reviewed_by,l.review_pending,l.created_at::text "
        "FROM public.system_typology_limits l "
        "WHERE l.system_id=%s AND (l.org_id=%s OR l.org_id IS NULL) "
        "ORDER BY l.opening_type",
        [system_id, org_id],
    )
    opening_capabilities = _rows_dicts(
        "SELECT c.id,c.org_id,c.system_id,c.movement,"
        "c.directions,c.leaf_roles,c.unit_kinds,"
        "c.fixed_in_sash,c.hardware_group,c.data_provenance,"
        "c.technical_reviewed_at::text,c.technical_reviewed_by,"
        "c.review_pending,c.created_at::text "
        "FROM public.system_opening_capabilities c "
        "WHERE c.system_id=%s AND (c.org_id=%s OR c.org_id IS NULL) "
        "ORDER BY c.movement",
        [system_id, org_id],
    )
    mounting_rules = _rows_dicts(
        "SELECT r.id,r.org_id,r.system_id,r.code,r.version,r.label,"
        "r.authority::text,r.data_provenance,r.technical_reviewed_at::text,"
        "r.technical_reviewed_by,r.review_pending,r.created_at::text "
        "FROM public.mounting_rules r "
        "WHERE r.system_id=%s AND (r.org_id=%s OR r.org_id IS NULL) "
        "ORDER BY r.code,r.version",
        [system_id, org_id],
    )
    inspector_configs = _rows_dicts(
        "SELECT c.id,c.org_id,c.system_id,c.rule_id,c.params::text,"
        "c.is_active,c.created_at::text,c.updated_at::text "
        "FROM public.inspector_rule_configs c "
        "WHERE c.system_id=%s AND (c.org_id=%s OR c.org_id IS NULL) "
        "ORDER BY c.rule_id",
        [system_id, org_id],
    )
    for row in (*cut_rules, *reinforcement_rules, *typology_limits,
                *opening_capabilities, *mounting_rules, *inspector_configs):
        for name in ("directions", "leaf_roles", "unit_kinds"):
            if isinstance(row.get(name), str):
                row[name] = _text_list(row[name])
        for name in ("authority", "params"):
            if row.get(name) is not None:
                row[name] = json.loads(row[name], parse_float=Decimal,
                                       parse_int=Decimal)
    return {
        "cut_rules": cut_rules,
        "reinforcement_rules": reinforcement_rules,
        "typology_limits": typology_limits,
        "opening_capabilities": opening_capabilities,
        "mounting_rules": mounting_rules,
        "inspector_configs": inspector_configs,
    }


def _system_costs(org_id, system_id, article_ids):
    """P07 coverage restricted to this system's purchase SKUs — the same
    UNION the admin panel shows, so the system's cost coverage is exactly
    what pricing sees for it."""
    return _rows_dicts(
        """WITH catalog AS (
            SELECT m.commercial_sku::text AS sku, a.name::text AS name,
                   'PROFILE'::text AS kind, 'M'::text AS required_unit
              FROM public.profile_purchase_mappings m
              JOIN public.profile_articles a ON a.id=m.profile_article_id
             WHERE a.system_id=%s AND (m.org_id=%s OR m.org_id IS NULL)
            UNION ALL
            SELECT r.commercial_sku::text, r.name::text, 'REINFORCEMENT', 'M'
              FROM public.reinforcement_articles r
             WHERE r.system_id=%s AND (r.org_id=%s OR r.org_id IS NULL)
            UNION ALL
            SELECT g.technical_sku::text, g.manufacturer_name::text, 'GLASS', 'M2'
              FROM public.glass_purchase_mappings g
             WHERE g.system_id=%s AND (g.org_id=%s OR g.org_id IS NULL)
            UNION ALL
            SELECT g.purchasing_sku::text, g.manufacturer_name::text, 'GLASS', 'EA'
              FROM public.glass_purchase_mappings g
             WHERE g.system_id=%s AND (g.org_id=%s OR g.org_id IS NULL)
            UNION ALL
            SELECT p.sku::text, p.name::text, 'PANEL', 'M2'
              FROM public.infill_articles p
             WHERE p.system_id=%s AND (p.org_id=%s OR p.org_id IS NULL)
            UNION ALL
            SELECT p.purchasing_sku::text, p.manufacturer_name::text, 'PANEL', 'EA'
              FROM public.panel_purchase_authorities p
              JOIN public.infill_articles ia ON ia.id=p.infill_article_id
             WHERE ia.system_id=%s AND (p.org_id=%s OR p.org_id IS NULL)
            UNION ALL
            SELECT k.sku::text, k.name::text, 'HARDWARE', 'KIT'
              FROM public.hardware_kits k
             WHERE (k.system_id=%s OR k.system_id IS NULL)
               AND (k.org_id=%s OR k.org_id IS NULL)
            UNION ALL
            SELECT h.purchasing_sku::text, h.manufacturer_name::text, 'HARDWARE', 'KIT'
              FROM public.hardware_purchase_mappings h
              JOIN public.hardware_kits hk ON hk.id=h.hardware_kit_id
             WHERE (hk.system_id=%s OR hk.system_id IS NULL)
               AND (h.org_id=%s OR h.org_id IS NULL)
            UNION ALL
            SELECT f.technical_sku::text, f.manufacturer_name::text, 'FITTING', 'EA'
              FROM public.fitting_purchase_mappings f
             WHERE f.system_id=%s AND (f.org_id=%s OR f.org_id IS NULL)
            UNION ALL
            SELECT f.purchasing_sku::text, f.manufacturer_name::text, 'FITTING', 'EA'
              FROM public.fitting_purchase_mappings f
             WHERE f.system_id=%s AND (f.org_id=%s OR f.org_id IS NULL)
        )
        SELECT c.sku, c.name, c.kind, c.required_unit, COUNT(i.id) AS active_cost_items
        FROM catalog c
        LEFT JOIN public.cost_list_items i
          ON i.org_id=%s AND i.sku=c.sku
         AND EXISTS (SELECT 1 FROM public.cost_lists l
                     WHERE l.id=i.cost_list_id AND l.org_id=%s AND l.is_active
                       AND (l.valid_to IS NULL OR l.valid_to>=current_date))
        GROUP BY c.sku, c.name, c.kind, c.required_unit
        ORDER BY COUNT(i.id), c.kind, c.sku""",
        [system_id, org_id] * 10 + [org_id, org_id],
    )


def _system_history(org_id, system_id):
    """The system's audit trail: imports that produced its rows, their
    lifecycle events (upload → extraction → review/confirm), and the
    evidence registry attached to the system's authorities."""
    imports = _rows_dicts(
        "SELECT i.id,i.org_id,i.file_name,i.kind,i.status,i.error_code,"
        "i.audit_id,i.created_by,i.reviewed_by,i.reviewed_at::text,"
        "i.created_at::text,i.updated_at::text "
        "FROM public.catalog_imports i "
        "WHERE i.org_id=%s AND i.system_id=%s "
        "ORDER BY i.created_at DESC LIMIT 50",
        [org_id, system_id],
    )
    import_ids = [str(row["id"]) for row in imports]
    events = (
        _rows_dicts(
            "SELECT e.id,e.org_id,e.import_id,e.event,e.actor_id,"
            "e.detail::text,e.created_at::text "
            "FROM public.catalog_import_events e "
            "WHERE e.org_id=%s AND e.import_id = ANY(%s::uuid[]) "
            "ORDER BY e.created_at,e.id",
            [org_id, import_ids],
        )
        if import_ids
        else []
    )
    actors = _reviewer_label(
        *(row["created_by"] for row in imports),
        *(row["reviewed_by"] for row in imports),
        *(row["actor_id"] for row in events),
    )
    for row in imports:
        row["created_by_label"] = actors.get(str(row["created_by"]))
        row["reviewed_by_label"] = actors.get(str(row["reviewed_by"]))
    for row in events:
        if row.get("detail") is not None:
            row["detail"] = json.loads(row["detail"])
        row["actor_label"] = actors.get(str(row["actor_id"]))
    return {"imports": imports, "events": events}


def article_ficha(org_id, article_id):
    """One article's technical ficha: the row, its section validations,
    declared evidence, purchase identities and bound reinforcements —
    everything the reviewer's badge click expands."""
    article = retrieve(ARTICLES, org_id, article_id)
    checks = section_checks(article.get("section"))
    evidence = _rows_dicts(
        "SELECT e.id,e.org_id,e.authority_table,e.row_id,e.field_name,"
        "e.value_text,e.unit,e.scope,e.applicability,e.source_document,"
        "e.source_page,e.source_url,e.declared_by,e.declared_at::text,"
        "e.review_state,e.reviewed_by,e.reviewed_at::text "
        "FROM public.catalog_parameter_evidence e "
        "WHERE e.authority_table='profile_articles' AND e.row_id=%s "
        "AND (e.org_id=%s OR e.org_id IS NULL) "
        "ORDER BY e.field_name,e.declared_at",
        [article_id, org_id],
    )
    purchase_mappings = _rows_dicts(
        "SELECT m.id,m.org_id,m.profile_article_id,m.commercial_sku,"
        "m.manufacturer_name,m.supplier_name,m.purchase_unit,m.is_active "
        "FROM public.profile_purchase_mappings m "
        "WHERE m.profile_article_id=%s AND (m.org_id=%s OR m.org_id IS NULL) "
        "ORDER BY m.commercial_sku",
        [article_id, org_id],
    )
    reinforcements = _rows_dicts(
        "SELECT r.id,r.org_id,r.system_id,r.parent_profile_article_id,r.sku,"
        "r.commercial_sku,r.name,r.manufacturer_name,r.supplier_name,"
        "r.stock_length_mm::text,r.thickness_mm::text,r.ix_cm4::text,"
        "r.purchase_unit,r.is_default,r.is_active "
        "FROM public.reinforcement_articles r "
        "WHERE r.parent_profile_article_id=%s "
        f"AND {visibility_sql(child=True, alias='r')} "
        "ORDER BY r.sku",
        [article_id, org_id],
    )
    labels = _reviewer_label(
        article.get("technical_reviewed_by"),
        article.get("section_revised_by"),
        *(row["declared_by"] for row in evidence),
        *(row["reviewed_by"] for row in evidence),
    )
    if article.get("technical_reviewed_by"):
        article["reviewed_by_label"] = labels.get(
            str(article["technical_reviewed_by"])
        )
    if article.get("section_revised_by"):
        article["section_revised_by_label"] = labels.get(
            str(article["section_revised_by"])
        )
    for row in evidence:
        row["declared_by_label"] = labels.get(str(row["declared_by"]))
        row["reviewed_by_label"] = labels.get(str(row["reviewed_by"]))
    return {
        "article": article,
        "section_checks": checks,
        "evidence": evidence,
        "purchase_mappings": purchase_mappings,
        "reinforcements": reinforcements,
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
