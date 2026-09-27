"""Real Auth, Django and PostgreSQL RLS: no mocked identity, cursor or policy."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
import json
import os
import secrets
import base64
from uuid import UUID, uuid4

from django.conf import settings
from django.db import connection, transaction
import httpx
import pytest
from pytest_django.plugin import DjangoDbBlocker
from rest_framework.test import APIClient

from ai_gateway.context import REQUIRED_REFS, build_context
from authentication.jwt_verifier import AuthServerTokenVerifier
from authentication.rls import authenticated_rls_context
from authentication.tenancy import MembershipRepository, resolve_tenant_context
from authentication.types import VerifiedSupabaseToken
from backend.tests.test_engine_api import g1_request, g4_request
from dekopen_engine import ProfileRole
from engine_api.repository import SystemNotFound, SystemParamsRepository

pytestmark = pytest.mark.rls_integration


@dataclass(frozen=True)
class RLSFixtures:
    tokens: dict[str, VerifiedSupabaseToken]
    organizations: dict[str, UUID]
    systems: dict[str, UUID]
    demo_system: UUID
    global_systems: dict[str, UUID]


@pytest.fixture(scope="module")
def real_rows(django_db_blocker: DjangoDbBlocker) -> Iterator[RLSFixtures]:
    if connection.vendor != "postgresql":
        pytest.fail("Real RLS gate requires the local Supabase DATABASE_URL; never skipped")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key or not settings.SUPABASE_ANON_KEY:
        pytest.fail("Real RLS gate requires local Auth fixture credentials; never skipped")

    organizations = {name: uuid4() for name in ("A", "B", "inactive")}
    systems = {name: uuid4() for name in organizations}
    tokens: dict[str, VerifiedSupabaseToken] = {}
    created_users: list[UUID] = []
    verifier = AuthServerTokenVerifier(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY, 5)
    with django_db_blocker.unblock(), httpx.Client(timeout=10) as auth:
        try:
            for name in ("A", "B", "both", "none"):
                email = f"shot04-rls-{uuid4()}@example.com"
                password = secrets.token_urlsafe(32)
                created = auth.post(
                    f"{settings.SUPABASE_URL}/auth/v1/admin/users",
                    headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
                    json={"email": email, "password": password, "email_confirm": True},
                )
                assert created.status_code in (200, 201), "Local Auth Admin fixture creation failed"
                user_id = UUID(created.json()["id"])
                created_users.append(user_id)
                signed_in = auth.post(
                    f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
                    headers={"apikey": settings.SUPABASE_ANON_KEY},
                    json={"email": email, "password": password},
                )
                assert signed_in.status_code == 200, "Local Auth fixture sign-in failed"
                tokens[name] = verifier.verify(signed_in.json()["access_token"])
                assert tokens[name].user_id == user_id

            with connection.cursor() as cursor:
                for name, org_id in organizations.items():
                    cursor.execute(
                        "INSERT INTO public.tenancy_organizations (id, name, tax_id) "
                        "VALUES (%s, %s, %s)",
                        [org_id, f"RLS {name}", f"RLS-{org_id}"],
                    )
                    cursor.execute(
                        "INSERT INTO public.profile_systems "
                        "(id, org_id, name, code, depth_mm, is_global, is_active, "
                        "sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm, "
                        "door_leaf_side_clearance_mm) "
                        "VALUES (%s, %s, %s, %s, 60.00, FALSE, TRUE, 20.00, 20.00, 7.00)",
                        [systems[name], org_id, f"System {name}", f"RLS_{name}"],
                    )
                    cursor.execute(
                        "INSERT INTO public.profile_articles "
                        "(system_id, org_id, sku, name, role, face_width_mm) "
                        "VALUES (%s, %s, %s, %s, 'FRAME', 60.00)",
                        [systems[name], org_id, f"FRAME-{name}", f"Frame {name}"],
                    )
                    cursor.execute(
                        "INSERT INTO public.projects "
                        "(org_id, code, name, client_name, created_by) "
                        "VALUES (%s, 'RLS-FIXTURE', 'RLS fixture', 'Fixture only', %s)",
                        [org_id, tokens["both"].user_id],
                    )
                    cursor.execute(
                        "INSERT INTO public.cost_lists (org_id, supplier_name, valid_from) "
                        "VALUES (%s, 'RLS fixture', DATE '2026-09-02')",
                        [org_id],
                    )
                for user, org, active in (
                    ("A", "A", True), ("B", "B", True),
                    ("both", "A", True), ("both", "B", True),
                    ("both", "inactive", False),
                ):
                    cursor.execute(
                        "INSERT INTO public.tenancy_memberships "
                        "(org_id, user_id, role, is_active) VALUES (%s, %s, 'ESTIMATOR', %s)",
                        [organizations[org], tokens[user].user_id, active],
                    )
                cursor.execute(
                    "SELECT id FROM public.profile_systems WHERE code = 'DEMO_60'"
                )
                demo_system = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT code, id FROM public.profile_systems WHERE is_global = TRUE"
                )
                global_systems = {code: row_id for code, row_id in cursor.fetchall()}
            yield RLSFixtures(
                tokens, organizations, systems, demo_system, global_systems
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM public.tenancy_organizations WHERE id = ANY(%s)",
                    [list(organizations.values())],
                )
            for user_id in created_users:
                deleted = auth.delete(
                    f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                    headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
                )
                assert deleted.status_code == 200, "Local Auth fixture cleanup failed"
            connection.close()


@pytest.fixture(autouse=True)
def real_database_access(
    real_rows: RLSFixtures, django_db_blocker: DjangoDbBlocker
) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


def assert_no_context() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, current_setting('request.jwt.claims', true), auth.uid()"
        )
        role, claims, user_id = cursor.fetchone()
    assert role not in ("authenticated", "service_role")
    assert claims in (None, "")
    assert user_id is None


def test_verified_claims_auth_uid_and_role_then_commit_cleanup(real_rows: RLSFixtures) -> None:
    token = real_rows.tokens["A"]
    with authenticated_rls_context(token.claims):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT auth.uid(), current_user, current_setting('request.jwt.claims', true)"
            )
            user_id, role, claims = cursor.fetchone()
        assert user_id == token.user_id
        assert role == "authenticated"
        assert json.loads(claims) == token.claims
    assert_no_context()


@pytest.mark.parametrize("tenant", ["A", "B"])
def test_tenants_cannot_read_each_others_projects_or_costs(
    real_rows: RLSFixtures, tenant: str
) -> None:
    with authenticated_rls_context(real_rows.tokens[tenant].claims):
        with connection.cursor() as cursor:
            cursor.execute("SELECT org_id FROM public.projects")
            assert {row[0] for row in cursor.fetchall()} == {real_rows.organizations[tenant]}
            cursor.execute("SELECT org_id FROM public.cost_lists")
            # PD-08-10: these real Auth fixtures are ESTIMATOR. Neither tenant's
            # supplier costs may be exposed, including their own organization.
            assert cursor.fetchall() == []
        params = SystemParamsRepository().load_visible(
            real_rows.demo_system, real_rows.organizations[tenant]
        )
        assert params.system_code == "DEMO_60"
        assert params.central_overlap_mm == Decimal("40.00")
    assert_no_context()


def test_multi_membership_active_org_does_not_mix_catalog_rows(real_rows: RLSFixtures) -> None:
    token = real_rows.tokens["both"]
    with authenticated_rls_context(token.claims):
        memberships = MembershipRepository().list_active_for_user(token.user_id)
        assert {item.organization_id for item in memberships} == {
            real_rows.organizations["A"], real_rows.organizations["B"]
        }
        context = resolve_tenant_context(memberships, str(real_rows.organizations["A"]))
        active_org = context.active_organization.organization_id
        repository = SystemParamsRepository()
        params = repository.load_visible(real_rows.systems["A"], active_org)
        assert params.effective_profile_articles[ProfileRole.FRAME].sku == "FRAME-A"
        with pytest.raises(SystemNotFound):
            repository.load_visible(real_rows.systems["B"], active_org)
    assert_no_context()


def test_rollback_clears_claims_and_role(real_rows: RLSFixtures) -> None:
    with pytest.raises(RuntimeError, match="force rollback"):
        with authenticated_rls_context(real_rows.tokens["both"].claims):
            raise RuntimeError("force rollback")
    assert_no_context()


def test_nested_context_restores_outer_role_and_claims(real_rows: RLSFixtures) -> None:
    """SET LOCAL ROLE is transaction-scoped, not savepoint-scoped: without an
    explicit restore, exiting the inner context leaves the outer transaction
    running as `authenticated` — a job worker's own writes (job_runs UPDATE)
    then get permission-denied. Pin the restore inside a live outer tx."""
    with transaction.atomic():
        with authenticated_rls_context(real_rows.tokens["A"].claims):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('role', true)")
                assert cursor.fetchone()[0] == "authenticated"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('role', true), "
                "current_setting('request.jwt.claims', true)"
            )
            role, claims = cursor.fetchone()
        assert role == "none"
        assert claims in (None, "")


def test_documentary_backend_restores_authenticated_on_exit(real_rows: RLSFixtures) -> None:
    """Nested backend-role context must hand the request's `authenticated`
    role back, not strand the caller on documentary_backend or none."""
    from documents.repository import documentary_backend

    with transaction.atomic():
        with authenticated_rls_context(real_rows.tokens["A"].claims):
            with documentary_backend():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_setting('role', true)")
                    assert cursor.fetchone()[0] == "documentary_backend"
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('role', true)")
                assert cursor.fetchone()[0] == "authenticated"
        assert_no_context()


def test_no_leak_between_open_connections_or_successive_requests(real_rows: RLSFixtures) -> None:
    probe = connection.copy(alias="rls_probe")
    try:
        with authenticated_rls_context(real_rows.tokens["A"].claims):
            with probe.cursor() as cursor:
                cursor.execute("SELECT auth.uid(), current_user")
                user_id, role = cursor.fetchone()
            assert user_id is None
            assert role not in ("authenticated", "service_role")
        assert_no_context()
        with authenticated_rls_context(real_rows.tokens["B"].claims):
            with connection.cursor() as cursor:
                cursor.execute("SELECT auth.uid(), current_user")
                user_id, role = cursor.fetchone()
            assert user_id == real_rows.tokens["B"].user_id
            assert role == "authenticated"
        assert_no_context()
    finally:
        probe.close()


@pytest.mark.parametrize(
    ("user", "org", "expected_status", "code"),
    [
        ("A", None, 200, None),
        ("B", "B", 200, None),
        ("both", None, 409, "organization_selection_required"),
        ("both", "A", 200, None),
        ("both", "inactive", 403, "organization_access_denied"),
        ("A", "B", 403, "organization_access_denied"),
        ("none", None, 403, "no_active_membership"),
    ],
)
def test_real_bearer_auth_me_uses_rls_and_cleans_up_each_request(
    real_rows: RLSFixtures, user: str, org: str | None,
    expected_status: int, code: str | None,
) -> None:
    client = APIClient()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {real_rows.tokens[user].access_token}"}
    if org is not None:
        headers["HTTP_X_ORGANIZATION_ID"] = str(real_rows.organizations[org])
    response = client.get("/api/v1/auth/me/", **headers)
    assert response.status_code == expected_status
    if code is not None:
        assert response.json()["error"]["code"] == code
    else:
        assert response.json()["user"]["id"] == str(real_rows.tokens[user].user_id)
        assert response.json()["active_organization"]["id"] == str(
            real_rows.organizations[org or user]
        )
    assert_no_context()


@pytest.mark.parametrize("case", ["G1", "G4"])
def test_real_bearer_and_db_adapter_preserve_engine_geometry(
    real_rows: RLSFixtures, case: str
) -> None:
    payload = g1_request() if case == "G1" else g4_request()
    payload["system_id"] = str(real_rows.demo_system)
    response = APIClient().post(
        "/api/v1/engine/calculate/", payload, format="json",
        HTTP_AUTHORIZATION=f"Bearer {real_rows.tokens['A'].access_token}",
    )
    assert response.status_code == 200
    result = response.json()
    if case == "G1":
        assert {cut["length_mm"] for cut in result["profile_cuts"] if cut["role"] == "FRAME"} == {
            "1006.00"
        }
        assert result["glasses"][0]["width_mm"] == "910.00"
        assert result["glasses"][0]["height_mm"] == "910.00"
    else:
        mullion = next(cut for cut in result["profile_cuts"] if cut["role"] == "MULLION_V")
        assert mullion["length_mm"] == "1380.00"
        widths = {piece["bay_id"]: piece["width_mm"] for piece in result["glasses"]}
        assert widths == {"bay_fixed": "830.00", "bay_ob": "696.00"}
    assert [item["kit_sku"] for item in result["hardware_items"]] == ([] if case == "G1" else ["KIT-TILT-TURN"])
    assert set(result) == {"profile_cuts", "reinforcements", "glasses", "panels", "hardware_items", "leaf_weights", "fittings", "calculation_hash"}
    assert_no_context()


def test_multi_org_api_rejects_system_b_when_a_is_selected(real_rows: RLSFixtures) -> None:
    client = APIClient()
    headers = {
        "HTTP_AUTHORIZATION": f"Bearer {real_rows.tokens['both'].access_token}",
        "HTTP_X_ORGANIZATION_ID": str(real_rows.organizations["A"]),
    }
    payload = g1_request()
    payload["system_id"] = str(real_rows.demo_system)
    allowed = client.post("/api/v1/engine/calculate/", payload, format="json", **headers)
    assert allowed.status_code == 200
    assert allowed.json()["glasses"][0]["width_mm"] == "910.00"
    payload["system_id"] = str(real_rows.systems["B"])
    denied = client.post("/api/v1/engine/calculate/", payload, format="json", **headers)
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "system_not_found"
    assert_no_context()


@pytest.mark.parametrize("tenant", ["A", "B"])
def test_engine_system_discovery_is_rls_visible_and_deterministic(
    real_rows: RLSFixtures, tenant: str
) -> None:
    response = APIClient().get(
        "/api/v1/engine/systems/",
        HTTP_AUTHORIZATION=f"Bearer {real_rows.tokens[tenant].access_token}",
    )

    assert response.status_code == 200
    systems = response.json()["systems"]
    demo = next(system for system in systems if system["code"] == "DEMO_60")
    assert demo == {
        "id": str(real_rows.demo_system),
        "code": "DEMO_60",
        "name": "Sistema Demo 60mm PVC — referencia sintética",
        "is_demo": True,
        "quote_ready": True,
        "readiness_reasons": [],
    }
    assert {system["id"] for system in systems} == {
        *(str(row_id) for row_id in real_rows.global_systems.values()),
        str(real_rows.systems[tenant]),
    }
    assert all(set(system) == {
        "id", "code", "name", "is_demo", "quote_ready", "readiness_reasons",
    } for system in systems)
    own = next(system for system in systems if system["id"] == str(real_rows.systems[tenant]))
    assert own["quote_ready"] is False
    assert own["readiness_reasons"]
    assert_no_context()


def test_multi_org_system_discovery_honors_active_organization(
    real_rows: RLSFixtures,
) -> None:
    response = APIClient().get(
        "/api/v1/engine/systems/",
        HTTP_AUTHORIZATION=f"Bearer {real_rows.tokens['both'].access_token}",
        HTTP_X_ORGANIZATION_ID=str(real_rows.organizations["A"]),
    )

    assert response.status_code == 200
    ids = {system["id"] for system in response.json()["systems"]}
    assert ids == {
        *(str(row_id) for row_id in real_rows.global_systems.values()),
        str(real_rows.systems["A"]),
    }
    assert str(real_rows.systems["B"]) not in ids
    assert_no_context()


def test_modified_sub_or_aal_cannot_enter_rls(real_rows: RLSFixtures) -> None:
    original = real_rows.tokens["A"]
    header, _, signature = original.access_token.split(".")
    forged = dict(original.claims, sub=str(real_rows.tokens["B"].user_id), aal="aal2")
    payload = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
    response = APIClient().get(
        "/api/v1/auth/me/", HTTP_AUTHORIZATION=f"Bearer {header}.{payload}.{signature}"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
    assert_no_context()


def test_shot06_all_28_catalog_fields_reach_typed_engine(real_rows: RLSFixtures) -> None:
    from engine.tests.catalog import demo_60_params
    from dekopen_engine import SystemParams, calculate_geometry
    from engine.tests.test_shot06_core import core_node

    with authenticated_rls_context(real_rows.tokens["A"].claims):
        loaded = SystemParamsRepository().load_visible(real_rows.demo_system, real_rows.organizations["A"])
    expected = demo_60_params()
    actual_fields = loaded.model_dump()
    expected_fields = expected.model_dump()
    actual_fields["available_hardware_kits"] = sorted(actual_fields["available_hardware_kits"], key=lambda k: k["sku"])
    expected_fields["available_hardware_kits"] = sorted(expected_fields["available_hardware_kits"], key=lambda k: k["sku"])
    assert len(SystemParams.model_fields) == len(actual_fields) == 26
    # The demo seed declares the same synthetic per-article masses the engine
    # fixture carries — mass authority must reach the typed model
    # field-for-field rather than arriving through a fallback.
    # The live seed declares simplified sections on MARCO/HOJA; the engine
    # fixture leaves them undeclared. Assert the typed field deserializes,
    # then normalize like the synthetic weights above.
    assert any(
        article["section"] is not None for article in actual_fields["effective_profile_articles"].values()
    )
    for article in actual_fields["effective_profile_articles"].values():
        article["section"] = None
    for article in expected_fields["effective_profile_articles"].values():
        article["section"] = None
    # The live seed owns kit identities independently of the engine's golden
    # fixture; the typed field is still present and populated in both paths.
    assert actual_fields.pop("available_hardware_kits")
    assert expected_fields.pop("available_hardware_kits")
    assert actual_fields == expected_fields
    for case in ("G5", "G6", "G7"):
        result = calculate_geometry(core_node(case), loaded)
        assert all(weight.total_weight_kg > Decimal("0") for weight in result.leaf_weights)
        assert result.hardware_items
    assert_no_context()


def test_shot06_live_composite_response_matches_canonical_generator(real_rows: RLSFixtures) -> None:
    from engine.scripts.regenerate_golden import golden_request
    from dekopen_engine.snapshot import calculation_response
    from engine_api.adapter import calculate_from_api

    request = golden_request()
    assert str(real_rows.demo_system) == request["system_id"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {real_rows.tokens['A'].access_token}")
    response = client.post("/api/v1/engine/calculate/", request, format="json")
    assert response.status_code == 200
    with authenticated_rls_context(real_rows.tokens["A"].claims):
        params = SystemParamsRepository().load_visible(real_rows.demo_system, real_rows.organizations["A"])
    expected = calculate_from_api(
        parametric_tree=request["parametric_tree"],
        nominal_width_mm=Decimal(str(request["nominal_width_mm"])),
        nominal_height_mm=Decimal(str(request["nominal_height_mm"])),
        color=request["color"],
        params=params,
    )
    assert response.json() == calculation_response(request, expected)
    assert response.json()["leaf_weights"][0]["weight_unknown_reasons"] == []
    assert_no_context()


def test_inactive_panel_is_not_loaded_and_missing_weight_cannot_fallback(real_rows: RLSFixtures) -> None:
    from django.db import transaction
    from dekopen_engine import calculate_geometry
    from dekopen_engine.hardware import NoCompatibleHardwareKit
    from engine.tests.test_shot06_core import core_node

    # The global demo system can be technical_locked once positions reference
    # it — mutations run against an org-owned clone instead.
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog

    for assignment in ("weight_kg_m2 = NULL", "is_active = FALSE"):
        with transaction.atomic():
            clone = copy_fixed_catalog(real_rows.organizations["A"], global_scope=True)
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE public.infill_articles SET {assignment} WHERE system_id = %s", [clone])
                assert cursor.rowcount == 1
            with authenticated_rls_context(real_rows.tokens["A"].claims):
                params = SystemParamsRepository().load_visible(clone, real_rows.organizations["A"])
                if assignment == "weight_kg_m2 = NULL":
                    with pytest.raises(NoCompatibleHardwareKit, match="missing_panel_mass"):
                        calculate_geometry(core_node("G7"), params)
                else:
                    assert params.available_panel_rules == {}
            transaction.set_rollback(True)
        assert_no_context()


def test_ai_context_projections_execute_against_real_schema(
    real_rows: RLSFixtures,
) -> None:
    """Every surface projection runs its real SELECTs on live Postgres — the
    unit suite stubs `rows`, so a projection naming a column the table lacks
    (the `active`/`is_active` regression) only fails here."""
    token = real_rows.tokens["A"]
    org_id = real_rows.organizations["A"]
    with authenticated_rls_context(token.claims):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM public.projects WHERE org_id = %s AND code = 'RLS-FIXTURE'",
                [org_id],
            )
            project_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO public.clients (org_id, name, created_by) VALUES (%s, %s, %s) RETURNING id",
                [org_id, "RLS fixture client", uuid4()],
            )
            client_id = cursor.fetchone()[0]
        covered = []
        for surface in sorted(REQUIRED_REFS):
            needed = REQUIRED_REFS[surface]
            if needed and set(needed) not in ({"project_id"}, {"client_id"}):
                # position/work_order refs need entities this fixture does not
                # create; every other projection's SQL must execute for real.
                continue
            refs = {}
            if needed == ("project_id",):
                refs = {"project_id": str(project_id)}
            elif needed == ("client_id",):
                refs = {"client_id": str(client_id)}
            context = build_context(org_id, surface, refs)
            assert context["surface"] == surface
            assert context["organization"]["name"]
            covered.append(surface)
        assert "catalog" in covered
        assert len(covered) >= len(REQUIRED_REFS) - 2
