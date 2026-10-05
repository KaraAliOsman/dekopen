"""D01 import confirm on real Postgres+RLS — the sqlite-mocked unit tests
cannot see role/RETURNING failures that only exist in the live gate."""

from __future__ import annotations

import json
from uuid import uuid4

from django.db import connection
import pytest

from authentication.rls import authenticated_rls_context
from backend.tests.integration.test_rls_context_integration import (
    real_rows as real_rows,
)
from documents.repository import documentary_backend
from ingest import catalog_service
from pricing.repository import rows

pytestmark = pytest.mark.rls_integration


@pytest.fixture(autouse=True)
def database_access(django_db_blocker):
    from django.db import transaction

    with django_db_blocker.unblock():
        with transaction.atomic():
            yield
            transaction.set_rollback(True)


def _seed_import(org_id, created_by, candidates):
    # authenticated holds SELECT only — INSERT needs documentary_backend.
    # Runs inside the caller's authenticated_rls_context so the backend
    # policy resolves orgs through request.jwt.claims.
    import_id = uuid4()
    with documentary_backend(), connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.catalog_imports("
            "id, org_id, file_name, kind, storage_path, status, candidates,"
            " warnings, result, created_by)"
            " VALUES(%s,%s,%s,%s,%s,'REVIEW_READY',%s::jsonb,'[]'::jsonb,"
            "'[]'::jsonb,%s)",
            [
                str(import_id),
                str(org_id),
                "catalogo.xlsx",
                "XLSX",
                f"catalog-imports/{org_id}/{import_id}/catalogo.xlsx",
                json.dumps(candidates),
                str(created_by),
            ],
        )
    return import_id


def test_confirm_publishes_system_profile_finish_and_rule(real_rows):
    """A workbook with Sistemas + Perfil + Acabado + Regla rows must confirm
    end to end: org system under catalog_backend, evidence INSERT with
    RETURNING, finishes merge UPDATE with RETURNING."""
    org_id = real_rows.organizations["A"]
    actor = real_rows.tokens["A"].user_id
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE public.tenancy_memberships SET role='WORKSHOP_MANAGER'"
            " WHERE user_id=%s AND org_id=%s",
            [str(actor), str(org_id)],
        )
    candidates = [
        {"key": "s0", "entity": "SYSTEM"},
        {
            "key": "p0",
            "entity": "PROFILE",
            "sku": "MRC-E2E",
            "role": "FRAME",
            "evidence": {
                "fields": {
                    "face_width_mm": {"normalized": "80", "unit": "mm"},
                }
            },
            "source_ref": "hoja 1",
        },
        {"key": "f0", "entity": "FINISH"},
        {"key": "r0", "entity": "CUT_RULE"},
    ]
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        import_id = _seed_import(org_id, actor, candidates)

        out = catalog_service.confirm_catalog_import(
            org_id=org_id,
            actor_id=actor,
            import_id=import_id,
            system_id=None,
            new_system={
                "code": f"E2E-{uuid4().hex[:8]}",
                "name": "Sistema importado E2E",
                "depth_mm": "60.00",
                "material": "PVC",
                "system_family": "CASEMENT",
                "finishes": ["WHITE"],
            },
            items=[
                {"key": "s0", "entity": "SYSTEM"},
                {
                    "key": "p0",
                    "sku": "MRC-E2E",
                    "name": "Marco E2E",
                    "role": "FRAME",
                    "face_width_mm": "80",
                },
                {"key": "f0", "entity": "FINISH", "finish_code": "PINTADO"},
                {
                    "key": "r0",
                    "entity": "CUT_RULE",
                    "fields": {"role": "FRAME", "welded_ends": True},
                },
            ],
        )
    assert out["errors"] == []
    assert out["import"]["status"] == "CONFIRMED"

    created_keys = {entry["key"] for entry in out["created"]}
    assert created_keys == {"s0", "p0", "f0", "r0"}

    system = rows(
        "SELECT id, org_id, system_family, finishes, data_provenance,"
        " review_pending FROM public.profile_systems WHERE org_id=%s"
        " AND code LIKE 'E2E-%%'",
        [str(org_id)],
    )[0]
    assert system["system_family"] == "CASEMENT"
    assert system["data_provenance"] == "IMPORT"
    finishes = system["finishes"]
    if isinstance(finishes, str):
        finishes = json.loads(finishes)
    assert sorted(finishes) == ["PINTADO", "WHITE"]

    article = rows(
        "SELECT id, role, data_provenance, review_pending"
        " FROM public.profile_articles WHERE system_id=%s AND sku='MRC-E2E'",
        [system["id"]],
    )[0]
    assert article["data_provenance"] == "IMPORT"
    assert article["review_pending"] is True

    # Evidence pinned by the confirm — this INSERT crashed the whole
    # transaction on Postgres before the RETURNING fix.
    evidence = rows(
        "SELECT field_name, value_text, source_document"
        " FROM public.catalog_parameter_evidence WHERE row_id=%s",
        [article["id"]],
    )
    assert any(entry["field_name"] == "face_width_mm" for entry in evidence)
    assert all("catalogo.xlsx" in entry["source_document"] for entry in evidence)

    rule = rows(
        "SELECT role, data_provenance, review_pending"
        " FROM public.profile_cut_rules WHERE system_id=%s AND role='FRAME'",
        [system["id"]],
    )[0]
    assert rule["data_provenance"] == "IMPORT"
