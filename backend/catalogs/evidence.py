"""Parameter evidence registry — where a catalog value came from.

Each row attests one (authority_table, row_id, field_name): the value as the
source states it, its unit, the document/page it was read from, an
applicability note, and a review state. Members may declare evidence —
recording a source is documentation, not approval — but the table grants no
member writes: every insert/update runs here under ``catalog_backend`` and
stamps actor identity server-side, mirroring the provenance triple's
authority model.
"""

from typing import Any
from uuid import UUID


from authentication.errors import contract_error
from authentication.rls import catalog_backend
from pricing.repository import rows

EVIDENCE_TABLES = {
    "profile_systems",
    "profile_articles",
    "glazing_bead_matrix",
    "hardware_kits",
    "infill_articles",
    "manufacturing_placement_policies",
    "handle_requirement_policies",
    "reinforcement_cut_policies",
    "glass_purchase_mappings",
    "fitting_purchase_mappings",
    "catalog_imports",
}

# How each authority row reaches its system_id (for scoping an evidence list
# to one system). Rows whose table lacks a system column scope through their
# own id (profile_systems) or are unattached evidence on the import itself.
_SYSTEM_KEY = {
    table: "system_id"
    for table in EVIDENCE_TABLES
    if table not in ("profile_systems", "catalog_imports")
}
_SYSTEM_KEY["profile_systems"] = "id"
_SYSTEM_KEY["catalog_imports"] = "system_id"

_UNITS = ("mm", "mm2", "m", "kg", "kg/m", "kg/m2",
          "unit", "set", "percent", "currency", "text")
_SCOPES = ("SYSTEM", "SERIES", "GLOBAL", "ORG")
_REVIEW_STATES = ("PENDING", "REVIEWED", "REJECTED")

EVIDENCE_UNITS = _UNITS
EVIDENCE_SCOPES = _SCOPES
EVIDENCE_STATES = _REVIEW_STATES

_PUBLIC_FIELDS = (
    "id", "org_id", "authority_table", "row_id", "field_name", "value_text",
    "unit", "scope", "applicability", "source_document", "source_page",
    "source_url", "declared_by", "declared_at", "review_state",
    "reviewed_by", "reviewed_at",
)


def _public(row: dict) -> dict:
    return {field: (str(row[field]) if row[field] is not None else None)
            for field in _PUBLIC_FIELDS}


def list_evidence(*, org_id: UUID, system_id: UUID) -> list[dict]:
    """Evidence rows for every authority row belonging to the system —
    org-declared plus platform-global evidence the member may read."""
    found = rows(
        "SELECT id FROM public.profile_systems WHERE id = %s"
        " AND (org_id = %s OR (org_id IS NULL AND is_global))",
        [str(system_id), str(org_id)],
    )
    if not found:
        raise contract_error(404, "catalog_system_not_found",
                             "catalogs.errors.not_found")
    clauses: list[str] = []
    params: list[Any] = []
    for table, key in _SYSTEM_KEY.items():
        clauses.append(
            f"EXISTS (SELECT 1 FROM public.{table} target"
            f" WHERE target.id = ev.row_id AND target.{key} = %s)"
        )
        params.append(str(system_id))
    found_rows = rows(
        "SELECT * FROM public.catalog_parameter_evidence ev"
        f" WHERE ({' OR '.join(clauses)})"
        " AND (ev.org_id = %s OR ev.org_id IS NULL)"
        " ORDER BY ev.authority_table, ev.field_name, ev.declared_at",
        [*params, str(org_id)],
    )
    return [_public(row) for row in found_rows]


def _authority_row_visible(org_id: UUID, table: str, row_id: UUID) -> dict:
    """The row the evidence points at must exist and be catalog-visible to
    this org (own rows or platform-global). Returns the row."""
    if table not in EVIDENCE_TABLES:
        raise contract_error(400, "catalog_evidence_target_invalid",
                             "catalogs.errors.evidence_target")
    visibility = "org_id IS NULL OR org_id = %s"
    found = rows(
        f"SELECT * FROM public.{table} WHERE id = %s AND ({visibility})",
        [str(row_id), str(org_id)],
    )
    if not found:
        raise contract_error(404, "catalog_evidence_target_missing",
                             "catalogs.errors.evidence_target")
    return found[0]


def declare_evidence(*, org_id: UUID, actor_id: UUID, values: dict) -> dict:
    """Attach a source attestation to a catalog authority row. Declared
    PENDING — review is a separate server-stamped transition."""
    table = str(values["authority_table"])
    _authority_row_visible(org_id, table, values["row_id"])
    unit = values.get("unit")
    if unit is not None and unit not in _UNITS:
        raise contract_error(400, "catalog_evidence_unit_invalid",
                             "catalogs.errors.evidence_unit")
    scope = values.get("scope") or "SYSTEM"
    if scope not in _SCOPES:
        raise contract_error(400, "catalog_evidence_scope_invalid",
                             "catalogs.errors.evidence_scope")
    with catalog_backend():
        # The org always owns its attestations, even when the authority row
        # is platform-global — evidence is an org-local claim.
        inserted = rows(
            "INSERT INTO public.catalog_parameter_evidence ("
            "org_id, authority_table, row_id, field_name, value_text, unit,"
            " scope, applicability, source_document, source_page, source_url,"
            " declared_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " RETURNING *",
            [
                str(org_id), table, str(values["row_id"]),
                str(values["field_name"]),
                values.get("value_text"), unit, scope,
                values.get("applicability"), str(values["source_document"]),
                values.get("source_page"), values.get("source_url"),
                str(actor_id),
            ],
        )
    return _public(inserted[0])


def review_evidence(*, org_id: UUID, evidence_id: UUID, actor_id: UUID,
                    state: str) -> dict:
    """Stamp REVIEWED/REJECTED — server-set reviewer + timestamp. Only the
    catalog-managing roles reach this view (WRITE_ROLES)."""
    if state not in ("REVIEWED", "REJECTED"):
        raise contract_error(400, "catalog_evidence_state_invalid",
                             "catalogs.errors.evidence_state")
    with catalog_backend():
        updated = rows(
            "UPDATE public.catalog_parameter_evidence SET"
            " review_state=%s, reviewed_by=%s, reviewed_at=now()"
            " WHERE id=%s AND org_id=%s AND review_state='PENDING'"
            " RETURNING *",
            [state, str(actor_id), str(evidence_id), str(org_id)],
        )
    if not updated:
        raise contract_error(409, "catalog_evidence_not_pending",
                             "catalogs.errors.evidence_not_pending")
    return _public(updated[0])


def stamp_import_evidence(*, org_id: UUID, actor_id: UUID, import_id: UUID,
                          article_id: UUID, candidate: dict) -> None:
    """Confirm-time hook: turn the parser's per-field evidence into registry
    rows pinned to the created article. Source document = the import's file
    + import id; the line ref rides as applicability context."""
    evidence = candidate.get("evidence") or {}
    fields = evidence.get("fields") or {}
    if not isinstance(fields, dict):
        return
    source_ref = candidate.get("source_ref")
    document = str(candidate.get("source_document") or "")
    if not document:
        document = f"catalog import {import_id}"
    inserts: list[list[Any]] = []
    for field, payload in fields.items():
        if not isinstance(payload, dict) or payload.get("normalized") is None:
            continue
        inserts.append([
            str(org_id), "profile_articles", str(article_id), field,
            str(payload.get("normalized")),
            payload.get("unit") if payload.get("unit") in _UNITS else None,
            "SYSTEM", source_ref, document, str(actor_id),
        ])
    if not inserts:
        return
    with catalog_backend():
        for params in inserts:
            # RETURNING id keeps this inside rows() (SELECT-only helper):
            # without it cursor.description is None and the INSERT crashes.
            rows(
                "INSERT INTO public.catalog_parameter_evidence ("
                "org_id, authority_table, row_id, field_name, value_text,"
                " unit, scope, applicability, source_document, declared_by)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT DO NOTHING RETURNING id",
                params,
            )
