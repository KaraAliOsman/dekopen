"""SHOT-07 effective stock selection through real authenticated PostgreSQL RLS."""

from collections.abc import Iterator
from decimal import Decimal

from django.db import connection
import pytest
from pytest_django.plugin import DjangoDbBlocker

from authentication.rls import authenticated_rls_context
from backend.tests.integration.test_rls_context_integration import (
    RLSFixtures, real_rows as real_rows,
)
from dekopen_engine.cutting import (
    AmbiguousCuttingProfile, AmbiguousStockAuthority, MissingCuttingProfile,
    MissingStockAuthority,
)
from engine_api.cutting_repository import CuttingRepository
from dekopen_engine.inspection_models import InspectorConfigurationError
from engine_api.inspection_repository import InspectorRepository
from backend.tests.test_engine_api import g1_request
from rest_framework.test import APIClient

pytestmark = pytest.mark.rls_integration


@pytest.fixture(autouse=True)
def database_access(django_db_blocker: DjangoDbBlocker) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


def fixture_cursor():
    """Fixture SQL as postgres — authenticated_rls_context leaves
    SET LOCAL ROLE authenticated for the rest of the transaction, and
    member writes on catalog-authority tables are role-gated now."""
    cursor = connection.cursor()
    cursor.execute("RESET ROLE")
    return cursor


def test_purchase_tenant_precedence_and_ambiguity(real_rows: RLSFixtures) -> None:
    # The global demo system can be technical_locked once positions reference
    # it — tenant mappings run against an org-owned clone carrying the same
    # global-scope authorities.
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog

    repo = CuttingRepository()
    org = real_rows.organizations["A"]
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        global_stock = repo.profile_stock(real_rows.demo_system, org, "MARCO", "WHITE")
        assert global_stock.stock_length_mm == Decimal("6000.00")
        assert global_stock.commercial_sku == "COMPRA-MARCO"
    clone = copy_fixed_catalog(org, global_scope=True)
    with fixture_cursor() as cursor:
        cursor.execute(
            """INSERT INTO public.profile_purchase_mappings
               (profile_article_id,org_id,commercial_sku,manufacturer_name,purchase_unit)
               SELECT id,%s,'TENANT-EXACT','Synthetic test','BAR'
               FROM public.profile_articles WHERE system_id=%s AND sku='MARCO'
               RETURNING id""", [org, clone],
        )
        mapping_id = cursor.fetchone()[0]
    try:
        with authenticated_rls_context(real_rows.tokens["A"].claims):
            chosen = repo.profile_stock(clone, org, "MARCO", "WHITE")
            assert chosen.commercial_sku == "TENANT-EXACT"
            assert chosen.stock_length_mm == global_stock.stock_length_mm
        with fixture_cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.profile_purchase_mappings
                   (profile_article_id,org_id,commercial_sku,manufacturer_name,purchase_unit)
                   SELECT profile_article_id,org_id,'OTHER-PHYSICAL','Synthetic test','BAR'
                   FROM public.profile_purchase_mappings WHERE id=%s RETURNING id""",
                [mapping_id],
            )
            duplicate_id = cursor.fetchone()[0]
        with authenticated_rls_context(real_rows.tokens["A"].claims):
            with pytest.raises(AmbiguousStockAuthority):
                repo.profile_stock(clone, org, "MARCO", "WHITE")
        with fixture_cursor() as cursor:
            cursor.execute("DELETE FROM public.profile_purchase_mappings WHERE id=%s",
                           [duplicate_id])
        with authenticated_rls_context(real_rows.tokens["B"].claims):
            assert repo.profile_stock(real_rows.demo_system, real_rows.organizations["B"],
                                      "MARCO", "WHITE").commercial_sku == global_stock.commercial_sku
    finally:
        with fixture_cursor() as cursor:
            cursor.execute("DELETE FROM public.profile_purchase_mappings WHERE id=%s", [mapping_id])


def test_missing_stock_and_default_steel_exact_authority(real_rows: RLSFixtures) -> None:
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        repo = CuttingRepository()
        org = real_rows.organizations["A"]
        with pytest.raises(MissingStockAuthority):
            repo.profile_stock(real_rows.demo_system, org, "UNKNOWN", "WHITE")
        steel, ix = repo.reinforcement_stock(real_rows.demo_system, org, "MARCO", None)
        assert steel.workshop_sku == "ACERO-MARCO"
        assert steel.material.value == "STEEL"
        assert steel.stock_length_mm == Decimal("6000.00")
        assert ix is None
        explicit, _ = repo.reinforcement_stock(
            real_rows.demo_system, org, "MARCO", steel.workshop_sku)
        assert explicit == steel
        assert steel.color == "WHITE"
        with pytest.raises(MissingStockAuthority):
            repo.reinforcement_stock(real_rows.demo_system, org, "MARCO", "MISSING")


def test_cutting_profile_scope_default_and_explicit_visibility(real_rows: RLSFixtures) -> None:
    repo = CuttingRepository()
    org = real_rows.organizations["A"]
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        profile = repo.cutting_profile(org)
        assert (profile.kerf_mm, profile.head_trim_mm, profile.tail_trim_mm) == (
            Decimal("4.00"), Decimal("15.00"), Decimal("15.00"))
        with pytest.raises(MissingCuttingProfile):
            repo.cutting_profile(org, "UNKNOWN")
        with fixture_cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.cutting_profiles
                   (org_id,code,name,kerf_mm,head_trim_mm,tail_trim_mm,is_default)
                   VALUES (%s,'DEMO','Tenant override',3,10,20,TRUE) RETURNING id""", [org],
            )
            row_id = cursor.fetchone()[0]
        try:
            assert repo.cutting_profile(org).kerf_mm == Decimal("3.00")
            # Explicit code requires exactly one visible row, unlike default scope selection.
            with pytest.raises(AmbiguousCuttingProfile):
                repo.cutting_profile(org, "DEMO")
        finally:
            with fixture_cursor() as cursor:
                cursor.execute("DELETE FROM public.cutting_profiles WHERE id=%s", [row_id])


def test_inspector_exact_json_override_and_missing_config(real_rows: RLSFixtures) -> None:
    # The global demo system can be technical_locked once positions reference
    # it — tenant overrides run against an org-owned clone carrying the same
    # global-scope rule configs.
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog

    repo = InspectorRepository()
    org = real_rows.organizations["A"]
    clone = copy_fixed_catalog(org, global_scope=True)
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        assert repo.load(real_rows.demo_system, org).config.R10.tolerance_mm == Decimal("1.50")
        with pytest.raises(InspectorConfigurationError):
            repo.load(real_rows.systems["A"], org)
        with fixture_cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.inspector_rule_configs (system_id,org_id,rule_id,params)
                   VALUES (%s,%s,'R10','{"tolerance_mm":1.5000000000000001}'::jsonb) RETURNING id""",
                [clone, org],
            )
            row_id = cursor.fetchone()[0]
        try:
            assert repo.load(clone, org).config.R10.tolerance_mm == Decimal("1.5000000000000001")
            with fixture_cursor() as cursor:
                cursor.execute("UPDATE public.inspector_rule_configs SET params='{}' WHERE id=%s", [row_id])
            with pytest.raises(InspectorConfigurationError):
                repo.load(clone, org)
        finally:
            with fixture_cursor() as cursor:
                cursor.execute("DELETE FROM public.inspector_rule_configs WHERE id=%s", [row_id])
    with authenticated_rls_context(real_rows.tokens["B"].claims):
        assert repo.load(real_rows.demo_system, real_rows.organizations["B"]).config.R10.tolerance_mm == Decimal("1.50")


@pytest.mark.parametrize("endpoint", ["inspect", "optimize-cut"])
def test_derived_http_real_auth_scope_and_owner_mfa(real_rows: RLSFixtures, endpoint: str) -> None:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {real_rows.tokens['A'].access_token}")
    request = {**g1_request(), "system_id": str(real_rows.demo_system)}
    path = f"/api/v1/engine/{endpoint}/"
    before = client.post("/api/v1/engine/calculate/", request, format="json")
    assert before.status_code == 200
    response = client.post(path, request, format="json")
    assert response.status_code == 200
    assert response.data["source_calculation_hash"] == before.data["calculation_hash"]
    if endpoint == "optimize-cut":
        assert any(line["commercial_sku"] == "COMPRA-MARCO" for line in response.data["purchase_list"])
        assert any(cut["workshop_sku"] == "MARCO" and cut["length_mm"] == "1006.00"
                   for bar in response.data["workshop_cut_plan"] for cut in bar["cuts"])
    assert client.post(path, {**request, "cuts": []}, format="json").status_code == 400
    assert client.post(path, {**request, "system_id": str(real_rows.systems["B"])}, format="json").status_code == 404
    assert client.post(path, request, format="json", HTTP_X_ORGANIZATION_ID=str(real_rows.organizations["B"])).status_code == 403
    with fixture_cursor() as cursor:
        cursor.execute("UPDATE public.tenancy_memberships SET role='OWNER' WHERE org_id=%s AND user_id=%s",
                       [real_rows.organizations["A"], real_rows.tokens["A"].user_id])
    try:
        blocked = client.post(path, request, format="json")
        assert blocked.status_code == 403
        assert blocked.data["error"]["code"] == "mfa_required"
    finally:
        with fixture_cursor() as cursor:
            cursor.execute("UPDATE public.tenancy_memberships SET role='ESTIMATOR' WHERE org_id=%s AND user_id=%s",
                           [real_rows.organizations["A"], real_rows.tokens["A"].user_id])
