"""D07 mounting rules — reglas de montaje por organización y sistema.

Same versioned-authority shape as the shot-09 policy tables: org_id NULL is
the global row, an org-scoped row overrides it per code+version, and the
authority JSONB is immutable (a revised rule lands as a new version row).
"""

from __future__ import annotations

from authentication.errors import contract_error
from pricing.repository import rows
from pricing.service import decoded

_RULE_COLUMNS = (
    "id,system_id,org_id,code,version,label,authority::text AS authority,"
    "data_provenance,review_pending"
)


def _effective_rules(values, org_id):
    """Org-scoped rows override the global (org_id NULL) row of the same
    code — same effective_scope semantics as the policy tables."""
    tenant = [row for row in values if row["org_id"] is not None]
    return tenant if tenant else values


def mounting_rule_row(org_id, rule_id, system_id) -> dict:
    found = rows(
        f"SELECT {_RULE_COLUMNS} FROM public.mounting_rules "
        "WHERE id=%s AND system_id=%s AND (org_id IS NULL OR org_id=%s)",
        [rule_id, system_id, org_id],
    )
    effective = _effective_rules(found, org_id)
    if len(effective) != 1:
        raise contract_error(
            400, "mounting_rule_not_found", "La regla de montaje no existe para este sistema."
        )
    return effective[0]


def mounting_rule_for_code(org_id, system_id, code) -> dict | None:
    found = rows(
        f"SELECT {_RULE_COLUMNS} FROM public.mounting_rules "
        "WHERE system_id=%s AND code=%s AND (org_id IS NULL OR org_id=%s)",
        [system_id, code, org_id],
    )
    effective = _effective_rules(found, org_id)
    return effective[0] if effective else None


def mounting_rules_for_system(org_id, system_id) -> list[dict]:
    """All effective rules for a system: newest version per code, org rows
    overriding the global row of the same code."""
    found = rows(
        f"SELECT {_RULE_COLUMNS} FROM public.mounting_rules "
        "WHERE system_id=%s AND (org_id IS NULL OR org_id=%s) "
        "ORDER BY code,version DESC,id",
        [system_id, org_id],
    )
    by_code: dict[str, dict] = {}
    for row in _effective_rules(found, org_id):
        by_code.setdefault(row["code"], row)
    return list(by_code.values())


def mounting_rule_public(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "system_id": str(row["system_id"]),
        "org_id": None if row["org_id"] is None else str(row["org_id"]),
        "code": row["code"],
        "version": row["version"],
        "label": row["label"],
        "authority": decoded(row["authority"]),
        "data_provenance": row["data_provenance"],
        "review_pending": row["review_pending"],
    }
