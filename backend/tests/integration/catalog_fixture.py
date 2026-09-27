"""Independent unreferenced technical catalog for destructive negative fixtures."""

import json
from uuid import uuid4
from pricing.repository import one, rows, json_text


def _jsonb_columns(table):
    # rows() returns jsonb as raw text — re-decode before re-encoding, or the
    # copied row stores a JSON string instead of the original object.
    return {
        row["column_name"]
        for row in rows(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s AND data_type='jsonb'",
            [table],
        )
    }


def decode_jsonb_columns(table: str, row: dict) -> dict:
    """Re-decode a `rows()` dict's jsonb columns before `json_text`
    re-encoding — every clone helper must pass through this."""
    for column in _jsonb_columns(table):
        if isinstance(row.get(column), str):
            row[column] = json.loads(row[column])
    return row


def copy_fixed_catalog(org, code="DEMO_60", global_scope=False):
    """Clone a global system into an unreferenced, unlocked copy.

    global_scope=False (default): the copy is org-owned — children are stamped
    with ``org`` so tenant RLS sees them (NULL-org children are only visible
    under ``is_global`` systems).
    global_scope=True: the copy stays ``is_global`` and children keep
    ``org_id NULL`` — the global-authority shape the source system has, so
    tenant-override precedence tests can write their own org rows on top.
    """
    scope_org = None if global_scope else org
    source = one("SELECT * FROM public.profile_systems WHERE code=%s AND is_global", [code])
    target = uuid4()

    def insert(table, row):
        for column in _jsonb_columns(table):
            if isinstance(row.get(column), str):
                row[column] = json.loads(row[column])
        one(f"INSERT INTO public.{table} SELECT (jsonb_populate_record(NULL::public.{table},"
            "%s::jsonb)).* RETURNING id", [json_text(row)])

    insert("profile_systems", {**source, "id": target, "org_id": scope_org,
        "code": f"TEST-{target.hex}", "is_global": global_scope, "is_demo": False,
        "technical_locked": False})
    identities = {}
    for article in rows("SELECT * FROM public.profile_articles WHERE system_id=%s AND org_id IS NULL", [source["id"]]):
        identities[article["id"]] = uuid4()
        insert("profile_articles", {**article, "id": identities[article["id"]], "system_id": target, "org_id": scope_org})
    for table in ("glazing_bead_matrix", "reinforcement_articles"):
        for row in rows(f"SELECT * FROM public.{table} WHERE system_id=%s AND org_id IS NULL", [source["id"]]):
            value = {**row, "id": uuid4(), "system_id": target, "org_id": scope_org}
            for key in ("bead_article_id", "parent_profile_article_id"):
                if key in value:
                    value[key] = identities[value[key]]
            insert(table, value)
    infill_ids = {}
    kit_ids = {}
    for table in ("hardware_kits", "infill_articles", "inspector_rule_configs",
                  "glass_purchase_mappings", "fitting_purchase_mappings"):
        for row in rows(f"SELECT * FROM public.{table} WHERE system_id=%s AND org_id IS NULL", [source["id"]]):
            value = {**row, "id": uuid4(), "system_id": target, "org_id": scope_org}
            if table == "infill_articles":
                infill_ids[row["id"]] = value["id"]
            if table == "hardware_kits":
                kit_ids[row["id"]] = value["id"]
            insert(table, value)
    for old, new in infill_ids.items():
        for row in rows("SELECT * FROM public.panel_purchase_authorities WHERE infill_article_id=%s AND org_id IS NULL", [old]):
            insert("panel_purchase_authorities", {**row, "id": uuid4(), "infill_article_id": new, "org_id": scope_org})
    for old, new in identities.items():
        for row in rows("SELECT * FROM public.profile_purchase_mappings WHERE profile_article_id=%s AND org_id IS NULL", [old]):
            insert("profile_purchase_mappings", {**row, "id": uuid4(), "profile_article_id": new, "org_id": scope_org})
    for old, new in kit_ids.items():
        for row in rows("SELECT * FROM public.hardware_purchase_mappings WHERE hardware_kit_id=%s AND org_id IS NULL", [old]):
            insert("hardware_purchase_mappings", {**row, "id": uuid4(), "hardware_kit_id": new, "org_id": scope_org})
    return target
