"""Real PostgreSQL SHOT-09 freeze, evidence, order, and artifact invariants."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from datetime import date
from decimal import Decimal
import logging
from threading import Event, local
from uuid import UUID, uuid4

from django.db import close_old_connections, connection, DatabaseError, transaction
from django.db.backends.utils import CursorWrapper
from django.db.utils import OperationalError
import pytest
from psycopg import errors as psycopg_errors
from rest_framework.test import APIClient

from authentication.errors import ContractAPIException
from authentication.rls import authenticated_rls_context
from authentication.types import (
    Membership,
    SupabaseUser,
    TenantContext,
    VerifiedSupabaseToken,
)
from dekopen_engine.documentary_canonical import documentary_sha256_v1
from dekopen_engine.snapshot import calculation_response
from engine_api.adapter import calculate_from_api
from engine_api.repository import SystemParamsRepository
from pricing.repository import admin_write, audit_reason, commercial_backend, json_text, one, rows
from pricing.service import apply_operation, preview

import documents.artifacts as artifacts_module
import documents.service as documents_service
import documents.views as documents_views
from documents.artifacts import generate_artifact
from documents.repository import DocumentaryError, decoded, documentary_backend
from documents.renderers import _doc01
from documents.service import (
    freeze_revision_a,
    revision_snapshot,
    save_documentary_inputs,
)
from purchasing.service import (
    allocate_requirement,
    confirm_order_type_batch,
    create_eligibility,
    purchasing_state,
    send_order,
)

pytestmark = pytest.mark.rls_integration
D = Decimal


@contextmanager
def as_user(user_id: UUID):
    with authenticated_rls_context({"sub": str(user_id), "role": "authenticated", "aal": "aal2"}):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", [str(user_id)])
        audit_reason("SHOT-09 integration authority")
        yield


@pytest.fixture
def documentary_tenant(django_db_blocker):
    with django_db_blocker.unblock():
        if connection.vendor != "postgresql":
            pytest.fail("SHOT-09 requires real PostgreSQL; never skipped")
        with transaction.atomic():
            org, other = uuid4(), uuid4()
            users = {
                role: uuid4()
                for role in ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER")
            }
            other_user = uuid4()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO public.tenancy_organizations(id,name,tax_id) VALUES(%s,%s,%s),(%s,%s,%s)",
                    [org, "Documentary A", str(org), other, "Documentary B", str(other)],
                )
                for role, user_id in users.items():
                    cursor.execute(
                        "INSERT INTO public.tenancy_memberships(org_id,user_id,role) VALUES(%s,%s,%s)",
                        [org, user_id, role],
                    )
                cursor.execute(
                    "INSERT INTO public.tenancy_memberships(org_id,user_id,role) VALUES(%s,%s,'OWNER')",
                    [other, other_user],
                )
            yield org, other, users, other_user
            transaction.set_rollback(True)


def _tenant(org: UUID, role: str) -> TenantContext:
    membership = Membership(organization_id=org, organization_name="Fixture", role=role)
    return TenantContext(active_organization=membership, memberships=(membership,))


def _seed_project(
    org: UUID, owner: UUID, *, valid_annotations: bool = True, apply_pricing: bool = True
) -> tuple[UUID, UUID, UUID]:
    system_id = UUID(str(one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")["id"]))
    project_id = UUID(str(one(
        "INSERT INTO public.projects(org_id,code,name,client_name,client_rut,client_email,"
        "client_phone,delivery_address,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        [org, f"P-{uuid4().hex[:8]}", "Proyecto documental", "Cliente Demo", "1-9",
         "cliente@example.test", "+56900000000", "Obra Norte", owner],
    )["id"]))
    tree = {
        "id": "B1",
        "type": "BAY",
        "opening_type": "FIXED",
        "glass_spec": "4-16-4 Float Incoloro",
        "glass_thickness_mm": "24.00",
        "glass_article_sku": "VIDRIO-BASE",
    }
    with as_user(owner):
        params = SystemParamsRepository().load_visible(system_id, org)
        result = calculate_from_api(
            parametric_tree=tree,
            nominal_width_mm=D("1000.00"),
            nominal_height_mm=D("1000.00"),
            color="WHITE",
            params=params,
        )
    position_id = UUID(str(one(
        "INSERT INTO public.project_positions(org_id,project_id,position_index,location_tag,quantity,"
        "typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot) "
        "VALUES(%s,%s,1,NULL,2,'FIXED',%s,1000.00,1000.00,%s::jsonb,%s::jsonb) RETURNING id",
        [org, project_id, system_id, json_text(tree), result.model_dump_json()],
    )["id"]))
    with as_user(owner):
        if not rows("SELECT id FROM public.pricing_rules WHERE org_id=%s", [org]):
            cost_list = admin_write(
                "cost-lists", org,
                {"supplier_name": "Fixture", "currency": "CLP", "valid_from": date(2026, 9, 1)},
                "SHOT-09 fixture list",
            )
            for sku, unit in (
                ("COMPRA-MARCO", "BAR"),
                ("COMPRA-JQ-10", "BAR"),
                ("COMPRA-ACERO-MARCO", "BAR"),
                ("TORNILLO-4X16", "EA"),
                ("VIDRIO-BASE", "M2"),
            ):
                admin_write(
                    "cost-items", org,
                    {"cost_list_id": cost_list["id"], "sku": sku, "item_type": "FIXTURE",
                     "unit": unit, "unit_cost": D("100.0000")},
                    "SHOT-09 fixture item",
                )
            admin_write(
                "rules", org,
                {"pricing_mode": "COST_PLUS_MARGIN", "default_margin_pct": D("0.3500"),
                 "tax_rate_pct": D("0.1900"), "waste_factor_pct": D("0.0800"),
                 "labor_rate_per_m2": D("15.00"), "installation_rate_per_m2": D("12.00")},
                "SHOT-09 fixture rules",
            )
        with commercial_backend():
            operation = preview(org, _tenant(org, "OWNER"), {
                "project_id": project_id,
                "pricing_mode": "COST_PLUS_MARGIN",
                "currency": "CLP",
                "effective_date": date(2026, 9, 10),
                "context_code": "DEFAULT",
                "discount_pct": D("0"),
                "target_margin": D("0.35"),
                "segment": "RETAIL",
                "confirmed": False,
                "reason": "SHOT-09 exact preview",
                "_actor_id": owner,
            })
            if apply_pricing:
                apply_operation(
                    org, owner, "OWNER", UUID(operation["id"]),
                    "SHOT-09 exact apply", False,
                )
    operation_id = UUID(operation["id"])
    with as_user(owner), documentary_backend():
        policies = one(
            "SELECT placement.id AS placement_id,handles.id AS handle_id,steel.id AS steel_id "
            "FROM public.profile_systems system "
            "JOIN public.manufacturing_placement_policies placement ON placement.system_id=system.id "
            "JOIN public.handle_requirement_policies handles ON handles.system_id=system.id "
            "JOIN public.reinforcement_cut_policies steel ON steel.system_id=system.id "
            "WHERE system.id=%s AND placement.org_id IS NULL AND handles.org_id IS NULL "
            "AND steel.org_id IS NULL "
            "AND placement.version=(SELECT max(p2.version) FROM public.manufacturing_placement_policies p2 "
            "WHERE p2.system_id=placement.system_id AND p2.org_id IS NULL) "
            "AND steel.version=(SELECT max(s2.version) FROM public.reinforcement_cut_policies s2 "
            "WHERE s2.system_id=steel.system_id AND s2.org_id IS NULL) "
            "AND handles.version=(SELECT max(h2.version) FROM public.handle_requirement_policies h2 "
            "WHERE h2.system_id=handles.system_id AND h2.org_id IS NULL) ",
            [system_id],
        )
        annotations = ([{
            "bay_id": "B1",
            "leaf_id": None,
            "bottom_drain_holes_mm": [D("100"), D("500"), D("900")],
            "closing_points_perimeter_mm": None,
            "continuous_width_mm": D("1000"),
            "finish_class": "WHITE",
            "has_coupler": False,
        }] if valid_annotations else [])
        save_documentary_inputs(
            org_id=org,
            actor_id=owner,
            project_id=project_id,
            data={
                "payment_terms": "50% anticipo, 50% contra entrega",
                "quotation_valid_until": date(2026, 10, 14),
                "positions": [{
                    "position_id": position_id,
                    "calculation_hash": calculation_response({"system_id": str(system_id),
                        "parametric_tree": tree, "nominal_width_mm": D("1000"),
                        "nominal_height_mm": D("1000"), "color": "WHITE"}, result)["calculation_hash"],
                    "location_tag": "FACHADA-NORTE",
                    "manufacturing_placement_policy_id": policies["placement_id"],
                    "handle_requirement_policy_id": policies["handle_id"],
                    "reinforcement_cut_policy_id": policies["steel_id"],
                    "workshop_annotations": annotations,
                    "structural_inputs": [],
                    "glass_polishing": [{
                        "schema_version": 1,
                        "bay_id": "B1",
                        "leaf_id": None,
                        "edges": {"top": False, "right": False, "bottom": False, "left": False},
                    }],
                    "handle_intents": [],
                    "accessory_schedule": {
                        "schema_version": 1, "coverage": "NONE_REQUIRED", "items": [],
                    },
                    "legacy_handle_migration_confirmed": False,
                }],
            },
        )
    return project_id, position_id, operation_id


def _freeze(org: UUID, owner: UUID, project_id: UUID, operation_id: UUID):
    with as_user(owner):
        return freeze_revision_a(
            org_id=org, actor_id=owner, project_id=project_id,
            pricing_operation_id=operation_id, confirmed=True,
        )


def test_exact_applied_freeze_is_idempotent_immutable_and_tenant_bound(documentary_tenant) -> None:
    org, other, users, other_user = documentary_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    unapplied_project, _, unapplied_operation = _seed_project(
        org, users["OWNER"], apply_pricing=False
    )
    with pytest.raises(DocumentaryError, match="applied_pricing_authority_required"):
        _freeze(org, users["OWNER"], unapplied_project, unapplied_operation)
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    assert frozen["created"] is True and frozen["revision_code"] == "REV-A"
    assert frozen["bom_hash"] != frozen["snapshot_sha256"]
    again = _freeze(org, users["OWNER"], project_id, operation_id)
    assert again["created"] is False and again["id"] == frozen["id"]
    with pytest.raises(DatabaseError), transaction.atomic(), as_user(users["OWNER"]):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE public.project_versions SET snapshot_json='{}' WHERE id=%s",
                [frozen["id"]],
            )
    with pytest.raises(DatabaseError), transaction.atomic(), as_user(users["OWNER"]), commercial_backend():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE public.pricing_operations SET reason='drift' WHERE id=%s",
                [operation_id],
            )
    with as_user(users["OWNER"]):
        version, snapshot = revision_snapshot(UUID(frozen["id"]), org)
    assert version["bom_hash"] == snapshot["bom_hash"]
    assert snapshot["pricing"]["operation_id"] == str(operation_id)
    assert snapshot["realized_waste"] == {"status": "NOT_RECORDED", "value": None}
    with as_user(other_user), pytest.raises(DocumentaryError, match="project_version_not_found"):
        revision_snapshot(UUID(frozen["id"]), other)


def test_stored_default_green_is_ignored_and_red_blocks_freeze(documentary_tenant) -> None:
    org, _, users, _ = documentary_tenant
    project_id, position_id, operation_id = _seed_project(
        org, users["OWNER"], valid_annotations=False
    )
    assert one("SELECT inspector_status::text FROM public.project_positions WHERE id=%s", [position_id])[
        "inspector_status"
    ] == "GREEN"
    with pytest.raises(DocumentaryError, match="inspector_red_blocks"):
        _freeze(org, users["OWNER"], project_id, operation_id)
    assert rows("SELECT id FROM public.project_versions WHERE project_id=%s", [project_id]) == []


def _eligibility_data(order_type: str, keys: list[str], supplier: str) -> dict[str, object]:
    return {
        "order_type": order_type,
        "supplier_identity": supplier,
        "supplier_name": f"Proveedor {supplier}",
        "supplier_details": {"tax_id": "1-9", "email": "supplier@example.test",
                             "phone": "", "address": "Chile"},
        "eligible_requirement_keys": sorted(keys),
        "evidence": {"basis": "Selección humana explícita", "reference": "TEST", "valid_until": None},
        "version": 1,
        "confirmed": True,
    }


class FakeStorage:
    uploads: dict[str, bytes] = {}
    upload_calls = 0
    deleted: list[str] = []

    def upload_immutable(self, object_key: str, content: bytes, content_type: str) -> None:
        FakeStorage.upload_calls += 1
        prior = self.uploads.get(object_key)
        if prior is not None and prior != content:
            raise AssertionError("immutable storage collision")
        self.uploads[object_key] = content

    def delete_object(self, object_key: str) -> None:
        FakeStorage.deleted.append(object_key)
        self.uploads.pop(object_key, None)

    def signed_url(self, object_key: str) -> str:
        return f"http://127.0.0.1:25321/signed/{object_key}"


def test_order_types_confirm_independently_and_artifacts_do_not_send(
    documentary_tenant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, _, users, _ = documentary_tenant
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    with as_user(users["WORKSHOP_MANAGER"]):
        state = purchasing_state(org, version_id)
        original_quantities = {
            item["requirement_key"]: item["quantity"] for item in state["requirements"]
        }
        by_type: dict[str, list[dict[str, object]]] = {}
        for requirement in state["requirements"]:
            by_type.setdefault(requirement["order_type"], []).append(requirement)
        eligibility_ids = {}
        for order_type, requirements in by_type.items():
            eligibility = create_eligibility(
                org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
                data=_eligibility_data(
                    order_type,
                    [str(item["requirement_key"]) for item in requirements],
                    f"SUPPLIER-{order_type}",
                ),
            )
            eligibility_ids[order_type] = UUID(eligibility["id"])
            for requirement in requirements:
                allocate_requirement(
                    org_id=org,
                    actor_id=users["WORKSHOP_MANAGER"],
                    requirement_id=UUID(str(requirement["id"])),
                    eligibility_id=eligibility_ids[order_type],
                )
        glass_orders, glass_created_batch = confirm_order_type_batch(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            order_type="SUPPLIER_GLASS_PO", confirmed=True,
        )
        assert len(glass_orders) == 1 and glass_created_batch is True
        state = purchasing_state(org, version_id)
        assert {item["order_type"] for item in state["orders"]} == {"SUPPLIER_GLASS_PO"}
        profile_orders, profile_created_batch = confirm_order_type_batch(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            order_type="SUPPLIER_PROFILE_PO", confirmed=True,
        )
        assert profile_created_batch is True
        assert confirm_order_type_batch(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            order_type="SUPPLIER_PROFILE_PO", confirmed=True,
        ) == (profile_orders, False)
        assert {
            item["requirement_key"]: item["quantity"]
            for item in purchasing_state(org, version_id)["requirements"]
        } == original_quantities
        with pytest.raises(DatabaseError), transaction.atomic():
            allocate_requirement(
                org_id=org,
                actor_id=users["WORKSHOP_MANAGER"],
                requirement_id=UUID(str(by_type["SUPPLIER_GLASS_PO"][0]["id"])),
                eligibility_id=eligibility_ids["SUPPLIER_GLASS_PO"],
            )

        monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)
        glass_order_id = UUID(glass_orders[0]["id"])
        profile_order_id = UUID(profile_orders[0]["id"])
        glass_artifact, glass_created = generate_artifact(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], role="WORKSHOP_MANAGER",
            project_version_id=version_id, order_id=glass_order_id,
            document_type="DOC-02", file_format="XLSX",
        )
        assert glass_created is True
        repeated, repeated_created = generate_artifact(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], role="WORKSHOP_MANAGER",
            project_version_id=version_id, order_id=glass_order_id,
            document_type="DOC-02", file_format="XLSX",
        )
        assert repeated_created is False and repeated["id"] == glass_artifact["id"]
        generate_artifact(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], role="WORKSHOP_MANAGER",
            project_version_id=version_id, order_id=profile_order_id,
            document_type="DOC-04", file_format="XLSX",
        )
        assert FakeStorage.upload_calls == 2
        with documentary_backend():
            assert one("SELECT status::text FROM public.orders WHERE id=%s", [glass_order_id])[
                "status"
            ] == "DRAFT"
        with pytest.raises(DocumentaryError, match="confirmation"):
            send_order(
                org_id=org, actor_id=users["WORKSHOP_MANAGER"],
                order_id=glass_order_id, confirmed=False,
            )
        sent = send_order(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"],
            order_id=glass_order_id, confirmed=True,
        )
        assert sent["status"] == "SENT"


def test_historical_render_uses_frozen_snapshot_after_catalog_change(documentary_tenant) -> None:
    org, _, users, _ = documentary_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    with as_user(users["OWNER"]):
        _, snapshot = revision_snapshot(UUID(frozen["id"]), org)
    before = _doc01(snapshot)
    with connection.cursor() as cursor:
        # Referenced catalog rows are frozen by guard_referenced_catalog —
        # the only post-freeze mutation the catalog permits is the
        # provenance/review triple, which is exactly the surface this test
        # must prove cannot shift a frozen snapshot.
        cursor.execute(
            "UPDATE public.profile_articles SET data_provenance='LEGACY_UNVERIFIED' "
            "WHERE sku='MARCO'"
        )
    with as_user(users["OWNER"]):
        _, loaded = revision_snapshot(UUID(frozen["id"]), org)
    assert _doc01(loaded) == before
    assert documentary_sha256_v1(loaded) == documentary_sha256_v1(snapshot)


def test_failed_artifact_registration_removes_the_uploaded_object(
    documentary_tenant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, _, users, _ = documentary_tenant
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)
    original_one = artifacts_module.one

    def failing_one(
        query: object, parameters: Sequence[object] = (), code: str = ""
    ) -> dict[str, object]:
        if str(query).lstrip().upper().startswith("INSERT INTO PUBLIC.DOCUMENT_ARTIFACTS"):
            raise DatabaseError("forced_registration_failure")
        return original_one(query, parameters, code)

    monkeypatch.setattr(artifacts_module, "one", failing_one)
    with as_user(users["OWNER"]), pytest.raises(
        DatabaseError, match="forced_registration_failure"
    ):
        generate_artifact(
            org_id=org, actor_id=users["OWNER"], role="OWNER",
            project_version_id=version_id, order_id=None,
            document_type="DOC-01", file_format="PDF",
        )
    assert FakeStorage.upload_calls == 1
    assert len(FakeStorage.deleted) == 1
    with documentary_backend():
        assert not rows(
            "SELECT id FROM public.document_artifacts WHERE storage_object_key=%s",
            [FakeStorage.deleted[0]],
        )


@pytest.fixture
def documentary_committed_tenant(django_db_blocker):
    """Committed tenant rows so independent connections observe the same state."""
    with django_db_blocker.unblock():
        if connection.vendor != "postgresql":
            pytest.fail("SHOT-09 requires real PostgreSQL; never skipped")
        org, other = uuid4(), uuid4()
        users = {
            role: uuid4()
            for role in ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER")
        }
        other_user = uuid4()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.tenancy_organizations(id,name,tax_id) "
                "VALUES(%s,%s,%s),(%s,%s,%s)",
                [org, "Committed A", str(org), other, "Committed B", str(other)],
            )
            for role, user_id in users.items():
                cursor.execute(
                    "INSERT INTO public.tenancy_memberships(org_id,user_id,role) "
                    "VALUES(%s,%s,%s)",
                    [org, user_id, role],
                )
            cursor.execute(
                "INSERT INTO public.tenancy_memberships(org_id,user_id,role) "
                "VALUES(%s,%s,'OWNER')",
                [other, other_user],
            )
        yield org, other, users, other_user
        with suppress(Exception), connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM public.tenancy_organizations WHERE id IN (%s,%s)",
                [org, other],
            )


def _freeze_token(user_id: UUID) -> VerifiedSupabaseToken:
    return VerifiedSupabaseToken(
        access_token="integration-freeze-token",
        claims={"sub": str(user_id), "role": "authenticated", "aal": "aal2"},
        user_id=user_id,
        email="documentary@example.test",
        aal="aal2",
    )


def _freeze_via_retry(
    token: VerifiedSupabaseToken, org: UUID, project_id: UUID, operation_id: UUID
):
    return documents_views._freeze_with_retry(
        token,
        dict(token.claims),
        str(org),
        project_id,
        {"pricing_operation_id": operation_id, "confirmed": True},
    )


def test_freeze_attempt_executes_under_repeatable_read(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_committed_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    observed: list[object] = []
    real_freeze = documents_views.freeze_revision_a

    def observed_freeze(**kwargs):
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_isolation")
            observed.append(cursor.fetchone()[0])
        return real_freeze(**kwargs)

    monkeypatch.setattr(documents_views, "freeze_revision_a", observed_freeze)
    output = _freeze_via_retry(
        _freeze_token(users["OWNER"]), org, project_id, operation_id
    )
    assert output["created"] is True
    assert observed == ["repeatable read"]


def test_freeze_retries_serialization_failure_without_partial_writes(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_committed_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    transactions: list[int] = []
    real_freeze = documents_views.freeze_revision_a

    def flaky_freeze(**kwargs):
        with connection.cursor() as cursor:
            cursor.execute("SELECT txid_current()")
            transactions.append(int(cursor.fetchone()[0]))
        result = real_freeze(**kwargs)
        if len(transactions) == 1:
            raise OperationalError("injected serialization failure") from (
                psycopg_errors.SerializationFailure("injected")
            )
        return result

    monkeypatch.setattr(documents_views, "freeze_revision_a", flaky_freeze)
    output = _freeze_via_retry(
        _freeze_token(users["OWNER"]), org, project_id, operation_id
    )
    assert output["created"] is True
    assert len(transactions) == 2 and len(set(transactions)) == 2
    versions = rows(
        "SELECT id,snapshot_sha256::text FROM public.project_versions WHERE project_id=%s",
        [project_id],
    )
    assert len(versions) == 1
    assert versions[0]["snapshot_sha256"] == output["snapshot_sha256"]
    assert rows(
        "SELECT id FROM public.purchase_projections WHERE project_id=%s", [project_id]
    ) != [] and len(rows(
        "SELECT id FROM public.purchase_projections WHERE project_id=%s", [project_id]
    )) == 1
    assert rows(
        "SELECT id FROM public.purchase_requirement_lines WHERE project_id=%s",
        [project_id],
    ) != []


def test_freeze_retries_deadlock_detected(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_committed_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    calls: list[int] = []
    real_freeze = documents_views.freeze_revision_a

    def flaky_freeze(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("injected deadlock") from (
                psycopg_errors.DeadlockDetected("injected")
            )
        return real_freeze(**kwargs)

    monkeypatch.setattr(documents_views, "freeze_revision_a", flaky_freeze)
    output = _freeze_via_retry(
        _freeze_token(users["OWNER"]), org, project_id, operation_id
    )
    assert output["created"] is True and len(calls) == 2


def test_freeze_retry_stops_after_three_attempts(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_committed_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    calls: list[int] = []
    real_freeze = documents_views.freeze_revision_a

    def always_fail(**kwargs):
        calls.append(1)
        real_freeze(**kwargs)
        raise OperationalError("injected serialization failure") from (
            psycopg_errors.SerializationFailure("injected")
        )

    monkeypatch.setattr(documents_views, "freeze_revision_a", always_fail)
    with pytest.raises(OperationalError, match="injected serialization failure"):
        _freeze_via_retry(_freeze_token(users["OWNER"]), org, project_id, operation_id)
    assert len(calls) == 3
    assert rows(
        "SELECT id FROM public.project_versions WHERE project_id=%s", [project_id]
    ) == []
    assert rows(
        "SELECT id FROM public.purchase_projections WHERE project_id=%s", [project_id]
    ) == []
    assert rows(
        "SELECT id FROM public.purchase_requirement_lines WHERE project_id=%s",
        [project_id],
    ) == []


def test_freeze_does_not_retry_unrelated_sqlstate(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_committed_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    calls: list[int] = []

    def unrelated_failure(**kwargs):
        calls.append(1)
        raise DatabaseError("injected unrelated failure") from (
            psycopg_errors.InsufficientPrivilege("injected")
        )

    monkeypatch.setattr(documents_views, "freeze_revision_a", unrelated_failure)
    with pytest.raises(DatabaseError, match="injected unrelated failure"):
        _freeze_via_retry(_freeze_token(users["OWNER"]), org, project_id, operation_id)
    assert len(calls) == 1


def test_freeze_attempt_denies_rbac_without_retry(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_committed_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    calls: list[int] = []

    def counted_freeze(**kwargs):
        calls.append(1)
        return documents_service.freeze_revision_a(**kwargs)

    monkeypatch.setattr(documents_views, "freeze_revision_a", counted_freeze)
    installer = _freeze_token(users["INSTALLER"])
    with pytest.raises(ContractAPIException) as denied:
        _freeze_via_retry(installer, org, project_id, operation_id)
    assert denied.value.contract_code == "documentary_permission_denied"
    assert calls == []


def test_freeze_repeatable_read_keeps_one_consistent_snapshot(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_committed_tenant
    project_id, position_id, operation_id = _seed_project(org, users["OWNER"])
    inputs_read, mutated = Event(), Event()
    real_one = documents_service.one

    def gating_one(query, parameters=(), code="documentary_authority_not_found"):
        result = real_one(query, parameters, code)
        if "FROM public.project_documentary_inputs" in str(query):
            inputs_read.set()
            assert mutated.wait(timeout=120)
        return result

    monkeypatch.setattr(documents_service, "one", gating_one)
    marker = [{
        "bay_id": "B1",
        "leaf_id": None,
        "bottom_drain_holes_mm": ["42"],
        "closing_points_perimeter_mm": None,
        "continuous_width_mm": "777",
        "finish_class": "WHITE",
        "has_coupler": True,
    }]

    def mutate_annotations() -> None:
        close_old_connections()
        try:
            assert inputs_read.wait(timeout=120)
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE public.position_documentary_inputs "
                    "SET workshop_annotations=%s::jsonb "
                    "WHERE position_id=%s AND org_id=%s",
                    [json_text(marker), position_id, org],
                )
            mutated.set()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        mutator = pool.submit(mutate_annotations)
        output = _freeze_via_retry(
            _freeze_token(users["OWNER"]), org, project_id, operation_id
        )
        mutator.result(timeout=120)
    assert output["created"] is True
    assert decoded(one(
        "SELECT workshop_annotations::text AS value "
        "FROM public.position_documentary_inputs WHERE position_id=%s",
        [position_id],
    )["value"]) == marker
    _, snapshot = revision_snapshot(UUID(output["id"]), org)
    annotations = snapshot["positions"][0]["workshop_annotations"]
    assert annotations[0]["has_coupler"] is False
    assert D(str(annotations[0]["continuous_width_mm"])) == D("1000")


def test_freeze_retries_after_real_concurrent_mutation(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real committed position change after the snapshot forces a 40001 retry."""
    org, _, users, _ = documentary_committed_tenant
    project_id, position_id, operation_id = _seed_project(org, users["OWNER"])
    lock_attempted, mutated = Event(), Event()
    real_execute = CursorWrapper.execute

    def gating_execute(self, sql, params=None):
        if (
            "FROM PUBLIC.PROJECT_POSITIONS" in str(sql).upper()
            and "FOR UPDATE" in str(sql).upper()
        ):
            lock_attempted.set()
            assert mutated.wait(timeout=120)
        return real_execute(self, sql, params)

    monkeypatch.setattr(CursorWrapper, "execute", gating_execute)
    attempts: list[int] = []
    real_freeze = documents_views.freeze_revision_a

    def counted_freeze(**kwargs):
        attempts.append(1)
        return real_freeze(**kwargs)

    monkeypatch.setattr(documents_views, "freeze_revision_a", counted_freeze)

    def mutate_position() -> None:
        close_old_connections()
        try:
            assert lock_attempted.wait(timeout=120)
            with as_user(users["OWNER"]), documentary_backend():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE public.project_positions SET location_tag='FACHADA-SUR' "
                        "WHERE id=%s AND org_id=%s",
                        [position_id, org],
                    )
            mutated.set()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        mutator = pool.submit(mutate_position)
        output = _freeze_via_retry(
            _freeze_token(users["OWNER"]), org, project_id, operation_id
        )
        mutator.result(timeout=120)
    assert len(attempts) == 2 and output["created"] is True
    _, snapshot = revision_snapshot(UUID(output["id"]), org)
    assert snapshot["positions"][0]["location_tag"] == "FACHADA-SUR"


def test_failed_generator_cleanup_preserves_concurrent_registration(
    documentary_committed_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed generator must never delete the object a concurrent winner registered."""
    org, _, users, _ = documentary_committed_tenant
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)
    owner = users["OWNER"]
    roles = local()
    b_lock_held, a_cleanup_attempted = Event(), Event()
    b_ready_to_commit, release_b, a_done, a_failed = (
        Event(), Event(), Event(), Event()
    )
    a_advisory = {"count": 0}
    real_one = artifacts_module.one
    real_execute = CursorWrapper.execute

    def gated_one(query, parameters=(), code=""):
        if (
            str(query).lstrip().upper().startswith("INSERT INTO PUBLIC.DOCUMENT_ARTIFACTS")
            and getattr(roles, "name", None) == "a"
        ):
            a_failed.set()
            raise DatabaseError("forced_registration_failure")
        return real_one(query, parameters, code)

    def gated_execute(self, sql, params=None):
        if "pg_advisory_xact_lock" in str(sql):
            role = getattr(roles, "name", None)
            if role == "b":
                assert a_failed.wait(timeout=120)
                result = real_execute(self, sql, params)
                b_lock_held.set()
                return result
            if role == "a":
                a_advisory["count"] += 1
                if a_advisory["count"] == 2:
                    a_cleanup_attempted.set()
                    assert b_lock_held.wait(timeout=120)
                    result = real_execute(self, sql, params)
                    outcome["a_lock_returned"] = rows(
                        "SELECT count(*) AS n, txid_current() AS tx, "
                        "current_setting('transaction_isolation') AS iso "
                        "FROM public.document_artifacts "
                        "WHERE org_id=%s AND storage_object_key IS NOT NULL",
                        [org],
                    )[0]
                    return result
        return real_execute(self, sql, params)

    monkeypatch.setattr(artifacts_module, "one", gated_one)
    monkeypatch.setattr(CursorWrapper, "execute", gated_execute)
    outcome: dict[str, object] = {}

    def losing_generator() -> None:
        roles.name = "a"
        close_old_connections()
        try:
            with as_user(owner), pytest.raises(
                DatabaseError, match="forced_registration_failure"
            ):
                generate_artifact(
                    org_id=org, actor_id=owner, role="OWNER",
                    project_version_id=version_id, order_id=None,
                    document_type="DOC-01", file_format="PDF",
                )
            a_done.set()
        finally:
            close_old_connections()

    def winning_generator() -> None:
        roles.name = "b"
        close_old_connections()
        try:
            with as_user(owner):
                outcome["artifact"] = generate_artifact(
                    org_id=org, actor_id=owner, role="OWNER",
                    project_version_id=version_id, order_id=None,
                    document_type="DOC-01", file_format="PDF",
                )
                b_ready_to_commit.set()
                assert release_b.wait(timeout=120)
            outcome["b_committed"] = True
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        losing = pool.submit(losing_generator)
        winning = pool.submit(winning_generator)
        assert b_ready_to_commit.wait(timeout=120)
        assert a_cleanup_attempted.wait(timeout=120)
        assert not a_done.wait(timeout=1.0)
        release_b.set()
        losing.result(timeout=120)
        winning.result(timeout=120)
    assert a_done.is_set()
    metadata, created = outcome["artifact"]
    assert created is True
    # A's cleanup serialized behind B's commit and observed the registered row.
    assert outcome.get("a_lock_returned", {}).get("n") == 1, outcome
    artifacts = rows(
        "SELECT storage_object_key FROM public.document_artifacts "
        "WHERE artifact_scope_id=%s AND document_type='DOC-01' AND format='PDF'",
        [version_id],
    )
    assert len(artifacts) == 1
    object_key = str(artifacts[0]["storage_object_key"])
    # The invariant: B's registered immutable object is never deleted by the
    # losing generator. A may still remove its own unreferenced orphan when the
    # rendered bytes differ (PDF metadata is time-varying), which is correct.
    assert object_key not in FakeStorage.deleted
    assert FakeStorage.uploads.get(object_key)
    assert len(FakeStorage.deleted) <= 1


def test_cleanup_failure_is_logged_without_masking_original_error(
    documentary_tenant, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    org, _, users, _ = documentary_tenant
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])

    class FailingDeleteStorage(FakeStorage):
        def delete_object(self, object_key: str) -> None:
            raise DocumentaryError("document_storage_delete_failed")

    monkeypatch.setattr(
        "documents.artifacts.SupabaseDocumentStorage", FailingDeleteStorage
    )
    original_one = artifacts_module.one

    def failing_one(query, parameters=(), code=""):
        if str(query).lstrip().upper().startswith("INSERT INTO PUBLIC.DOCUMENT_ARTIFACTS"):
            raise DatabaseError("forced_registration_failure")
        return original_one(query, parameters, code)

    monkeypatch.setattr(artifacts_module, "one", failing_one)
    with as_user(users["OWNER"]), caplog.at_level(
        logging.WARNING, logger="documents.artifacts"
    ):
        with pytest.raises(DatabaseError, match="forced_registration_failure"):
            generate_artifact(
                org_id=org, actor_id=users["OWNER"], role="OWNER",
                project_version_id=version_id, order_id=None,
                document_type="DOC-01", file_format="PDF",
            )
    records = [
        record for record in caplog.records
        if record.message == "document_artifact_cleanup_failed"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.artifact_slot == f"{version_id}:DOC-01:PDF"
    assert record.storage_object_key in FakeStorage.uploads
    assert record.cleanup_error == "document_storage_delete_failed"
    assert FakeStorage.deleted == []


def test_partial_eligibility_reports_exactly_the_uncovered_requirement_keys(
    documentary_tenant,
) -> None:
    org, _, users, _ = documentary_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    with as_user(users["WORKSHOP_MANAGER"]):
        state = purchasing_state(org, version_id)
        by_type: dict[str, list[dict[str, object]]] = {}
        for requirement in state["requirements"]:
            by_type.setdefault(requirement["order_type"], []).append(requirement)
        order_type, type_lines = max(by_type.items(), key=lambda item: len(item[1]))
        assert len(type_lines) >= 2
        keys = sorted(str(item["requirement_key"]) for item in type_lines)
        covered, uncovered = keys[:1], keys[1:]
        blockers = [
            item for item in state["blockers"] if item["order_type"] == order_type
        ]
        assert {item["code"] for item in blockers} == {
            "SUPPLIER_ELIGIBILITY_REQUIRED",
            "ALLOCATION_REQUIRED",
        }
        partial = create_eligibility(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            data=_eligibility_data(order_type, covered, "SUP-PARTIAL"),
        )
        blockers = [
            item for item in purchasing_state(org, version_id)["blockers"]
            if item["order_type"] == order_type
        ]
        eligibility = [
            item for item in blockers
            if item["code"] == "SUPPLIER_ELIGIBILITY_REQUIRED"
        ]
        assert len(eligibility) == 1
        assert sorted(eligibility[0]["requirement_keys"]) == uncovered
        allocation = [
            item for item in blockers if item["code"] == "ALLOCATION_REQUIRED"
        ]
        assert len(allocation) == 1
        assert sorted(allocation[0]["requirement_keys"]) == keys
        covered_line = next(
            item for item in type_lines if item["requirement_key"] == covered[0]
        )
        allocate_requirement(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"],
            requirement_id=UUID(str(covered_line["id"])),
            eligibility_id=UUID(str(partial["id"])),
        )
        blockers = [
            item for item in purchasing_state(org, version_id)["blockers"]
            if item["order_type"] == order_type
        ]
        assert {
            item["code"]: sorted(item["requirement_keys"]) for item in blockers
        } == {
            "SUPPLIER_ELIGIBILITY_REQUIRED": uncovered,
            "ALLOCATION_REQUIRED": uncovered,
        }
        remainder = create_eligibility(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            data=_eligibility_data(order_type, uncovered, "SUP-REMAINDER"),
        )
        for line in type_lines:
            if line["requirement_key"] in uncovered:
                allocate_requirement(
                    org_id=org, actor_id=users["WORKSHOP_MANAGER"],
                    requirement_id=UUID(str(line["id"])),
                    eligibility_id=UUID(str(remainder["id"])),
                )
        blockers = [
            item for item in purchasing_state(org, version_id)["blockers"]
            if item["order_type"] == order_type
        ]
        assert blockers == []


def test_artifact_endpoint_returns_201_then_200(
    documentary_tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, _, users, _ = documentary_tenant
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)
    user = SupabaseUser(id=users["OWNER"], email="owner@example.test")
    client = APIClient()
    client.force_authenticate(user=user, token=_freeze_token(users["OWNER"]))
    payload = {
        "document_type": "DOC-01",
        "format": "PDF",
        "project_version_id": frozen["id"],
    }
    created = client.post(
        "/api/v1/documents/artifacts/", payload, format="json",
        HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert created.status_code == 201, created.content
    reused = client.post(
        "/api/v1/documents/artifacts/", payload, format="json",
        HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert reused.status_code == 200, reused.content
    assert reused.json()["id"] == created.json()["id"]
    assert FakeStorage.upload_calls == 1


def test_confirm_batch_endpoint_returns_201_then_200(documentary_tenant) -> None:
    org, _, users, _ = documentary_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    with as_user(users["WORKSHOP_MANAGER"]):
        state = purchasing_state(org, version_id)
        by_type: dict[str, list[dict[str, object]]] = {}
        for requirement in state["requirements"]:
            by_type.setdefault(requirement["order_type"], []).append(requirement)
        order_type, type_lines = max(by_type.items(), key=lambda item: len(item[1]))
        keys = sorted(str(item["requirement_key"]) for item in type_lines)
        eligibility = create_eligibility(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            data=_eligibility_data(order_type, keys, "SUP-CONFIRM"),
        )
        for line in type_lines:
            allocate_requirement(
                org_id=org, actor_id=users["WORKSHOP_MANAGER"],
                requirement_id=UUID(str(line["id"])),
                eligibility_id=UUID(str(eligibility["id"])),
            )
    manager = SupabaseUser(id=users["WORKSHOP_MANAGER"], email="manager@example.test")
    client = APIClient()
    client.force_authenticate(
        user=manager, token=_freeze_token(users["WORKSHOP_MANAGER"])
    )
    payload = {"order_type": order_type, "confirmed": True}
    created = client.post(
        f"/api/v1/purchasing/versions/{version_id}/confirm/", payload, format="json",
        HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert created.status_code == 201, created.content
    replayed = client.post(
        f"/api/v1/purchasing/versions/{version_id}/confirm/", payload, format="json",
        HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert replayed.status_code == 200, replayed.content
    assert replayed.json() == created.json()


def test_missing_artifact_and_order_map_to_404(documentary_tenant) -> None:
    org, _, users, _ = documentary_tenant
    manager = SupabaseUser(id=users["WORKSHOP_MANAGER"], email="manager@example.test")
    client = APIClient()
    client.force_authenticate(
        user=manager, token=_freeze_token(users["WORKSHOP_MANAGER"])
    )
    response = client.post(
        f"/api/v1/documents/artifacts/{uuid4()}/access/", {}, format="json",
        HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "artifact_not_found"


def test_purchasing_state_endpoint_reports_partial_eligibility_blocker(
    documentary_tenant,
) -> None:
    org, _, users, _ = documentary_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    with as_user(users["WORKSHOP_MANAGER"]):
        state = purchasing_state(org, version_id)
        by_type: dict[str, list[dict[str, object]]] = {}
        for requirement in state["requirements"]:
            by_type.setdefault(requirement["order_type"], []).append(requirement)
        order_type, type_lines = max(by_type.items(), key=lambda item: len(item[1]))
        keys = sorted(str(item["requirement_key"]) for item in type_lines)
        create_eligibility(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            data=_eligibility_data(order_type, keys[:1], "SUP-PARTIAL"),
        )
    manager = SupabaseUser(id=users["WORKSHOP_MANAGER"], email="manager@example.test")
    client = APIClient()
    client.force_authenticate(
        user=manager, token=_freeze_token(users["WORKSHOP_MANAGER"])
    )
    response = client.get(
        f"/api/v1/purchasing/versions/{version_id}/", HTTP_X_ORGANIZATION_ID=str(org)
    )
    assert response.status_code == 200, response.content
    blockers = [
        item for item in response.json()["blockers"]
        if item["order_type"] == order_type
    ]
    eligibility = [
        item for item in blockers if item["code"] == "SUPPLIER_ELIGIBILITY_REQUIRED"
    ]
    assert len(eligibility) == 1
    assert sorted(eligibility[0]["requirement_keys"]) == keys[1:]


def _order_for_type(
    org: UUID, actor: UUID, version_id: UUID, order_type: str
) -> UUID:
    state = purchasing_state(org, version_id)
    type_lines = [
        item for item in state["requirements"] if item["order_type"] == order_type
    ]
    assert len(type_lines) >= 1
    keys = sorted(str(item["requirement_key"]) for item in type_lines)
    eligibility = create_eligibility(
        org_id=org, actor_id=actor, version_id=version_id,
        data=_eligibility_data(order_type, keys, f"SUP-{order_type}"),
    )
    for line in type_lines:
        allocate_requirement(
            org_id=org, actor_id=actor,
            requirement_id=UUID(str(line["id"])),
            eligibility_id=UUID(str(eligibility["id"])),
        )
    orders, created = confirm_order_type_batch(
        org_id=org, actor_id=actor, version_id=version_id,
        order_type=order_type, confirmed=True,
    )
    assert created is True and len(orders) == 1
    return UUID(orders[0]["id"])


def test_eligibility_canonicalizes_arbitrary_key_order_and_rejects_duplicates(
    documentary_tenant,
) -> None:
    org, _, users, _ = documentary_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    with as_user(users["WORKSHOP_MANAGER"]):
        state = purchasing_state(org, version_id)
        by_type: dict[str, list[dict[str, object]]] = {}
        for requirement in state["requirements"]:
            by_type.setdefault(requirement["order_type"], []).append(requirement)
        order_type, type_lines = max(by_type.items(), key=lambda item: len(item[1]))
        keys = sorted(str(item["requirement_key"]) for item in type_lines)
        assert len(keys) >= 2
        unsorted = list(reversed(keys))
        assert unsorted != keys
        payload = _eligibility_data(order_type, keys, "SUP-UNORDERED")
        payload["eligible_requirement_keys"] = unsorted
        created = create_eligibility(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], version_id=version_id,
            data=payload,
        )
        with documentary_backend():
            stored = one(
                "SELECT eligible_requirement_keys::text "
                "FROM public.supplier_eligibility_versions WHERE id=%s",
                [UUID(created["id"])],
            )
            eligibility = one(
                "SELECT content_hash FROM public.supplier_eligibility_versions WHERE id=%s",
                [UUID(created["id"])],
            )
            version_row = one(
                "SELECT project_id,bom_hash,snapshot_sha256 FROM public.project_versions "
                "WHERE id=%s",
                [version_id],
            )
        assert decoded(stored["eligible_requirement_keys"]) == keys
        canonical = _eligibility_data(order_type, keys, "SUP-UNORDERED")
        canonical["eligible_requirement_keys"] = keys
        expected = documentary_sha256_v1({
            "schema_version": 1,
            "project_id": version_row["project_id"],
            "project_version_id": version_id,
            "bom_hash": version_row["bom_hash"],
            "snapshot_sha256": version_row["snapshot_sha256"],
            "order_type": order_type,
            "supplier_identity": canonical["supplier_identity"],
            "supplier_name": canonical["supplier_name"],
            "supplier_details": canonical["supplier_details"],
            "eligible_requirement_keys": keys,
            "evidence": canonical["evidence"],
            "version": canonical["version"],
        })
        assert str(eligibility["content_hash"]) == expected
        duplicated = _eligibility_data(order_type, keys, "SUP-DUPLICATED")
        duplicated["eligible_requirement_keys"] = [keys[0], keys[0]]
        with pytest.raises(DocumentaryError, match="invalid_supplier_eligibility"):
            create_eligibility(
                org_id=org, actor_id=users["WORKSHOP_MANAGER"],
                version_id=version_id, data=duplicated,
            )


def test_eligibility_endpoint_canonicalizes_unsorted_keys_and_rejects_duplicates(
    documentary_tenant,
) -> None:
    org, _, users, _ = documentary_tenant
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(frozen["id"])
    with as_user(users["WORKSHOP_MANAGER"]):
        state = purchasing_state(org, version_id)
        by_type: dict[str, list[dict[str, object]]] = {}
        for requirement in state["requirements"]:
            by_type.setdefault(requirement["order_type"], []).append(requirement)
        order_type, type_lines = max(by_type.items(), key=lambda item: len(item[1]))
        keys = sorted(str(item["requirement_key"]) for item in type_lines)
    assert len(keys) >= 2
    unsorted = list(reversed(keys))
    manager = SupabaseUser(id=users["WORKSHOP_MANAGER"], email="manager@example.test")
    client = APIClient()
    client.force_authenticate(user=manager, token=_freeze_token(users["WORKSHOP_MANAGER"]))
    payload = _eligibility_data(order_type, keys, "SUP-API-UNORDERED")
    payload["eligible_requirement_keys"] = unsorted
    created = client.post(
        f"/api/v1/purchasing/versions/{version_id}/eligibilities/", payload,
        format="json", HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert created.status_code == 201, created.content
    with as_user(users["WORKSHOP_MANAGER"]), documentary_backend():
        stored = one(
            "SELECT eligible_requirement_keys::text "
            "FROM public.supplier_eligibility_versions WHERE id=%s",
            [UUID(created.json()["id"])],
        )
    assert decoded(stored["eligible_requirement_keys"]) == keys
    duplicated = _eligibility_data(order_type, keys, "SUP-API-DUP")
    duplicated["eligible_requirement_keys"] = [keys[0], keys[0]]
    rejected = client.post(
        f"/api/v1/purchasing/versions/{version_id}/eligibilities/", duplicated,
        format="json", HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert rejected.status_code == 400, rejected.content
    malformed = _eligibility_data(order_type, keys, "SUP-API-MALFORMED")
    malformed["eligible_requirement_keys"] = ["not-a-sha"]
    rejected = client.post(
        f"/api/v1/purchasing/versions/{version_id}/eligibilities/", malformed,
        format="json", HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert rejected.status_code == 400, rejected.content
    empty = _eligibility_data(order_type, keys, "SUP-API-EMPTY")
    empty["eligible_requirement_keys"] = []
    rejected = client.post(
        f"/api/v1/purchasing/versions/{version_id}/eligibilities/", empty,
        format="json", HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert rejected.status_code == 400, rejected.content


def test_artifact_replay_validates_active_org_for_multi_membership_user(
    documentary_tenant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, other, users, _ = documentary_tenant
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    dual_user = users["WORKSHOP_MANAGER"]
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.tenancy_memberships(org_id,user_id,role) "
            "VALUES(%s,%s,'OWNER')",
            [other, dual_user],
        )
    project_id, _, operation_id = _seed_project(other, dual_user)
    frozen = _freeze(other, dual_user, project_id, operation_id)
    version_id = UUID(frozen["id"])
    monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)
    artifact, created = generate_artifact(
        org_id=other, actor_id=dual_user, role="WORKSHOP_MANAGER",
        project_version_id=version_id, order_id=None,
        document_type="DOC-03", file_format="PDF",
    )
    assert created is True
    uploads_after_create = FakeStorage.upload_calls
    # Same user, active organization A, foreign scope identifiers from B: the
    # occupied slot must never bypass active-org/version authority validation.
    with pytest.raises(DocumentaryError):
        generate_artifact(
            org_id=org, actor_id=dual_user, role="WORKSHOP_MANAGER",
            project_version_id=version_id, order_id=None,
            document_type="DOC-03", file_format="PDF",
        )
    assert FakeStorage.upload_calls == uploads_after_create
    manager = SupabaseUser(id=dual_user, email="dual@example.test")
    client = APIClient()
    client.force_authenticate(user=manager, token=_freeze_token(dual_user))
    response = client.post(
        "/api/v1/documents/artifacts/",
        {
            "document_type": "DOC-03",
            "format": "PDF",
            "project_version_id": str(version_id),
        },
        format="json", HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert response.status_code in (403, 404), response.content
    assert artifact["id"] not in response.content.decode()
    access = client.post(
        f"/api/v1/documents/artifacts/{artifact['id']}/access/", {},
        format="json", HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert access.status_code == 404, access.content
    # The same user can still replay under the artifact's real organization.
    replayed, replayed_created = generate_artifact(
        org_id=other, actor_id=dual_user, role="WORKSHOP_MANAGER",
        project_version_id=version_id, order_id=None,
        document_type="DOC-03", file_format="PDF",
    )
    assert replayed_created is False and replayed["id"] == artifact["id"]


def test_artifact_replay_rejects_order_bound_to_a_different_version(
    documentary_tenant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, _, users, _ = documentary_tenant
    FakeStorage.uploads = {}
    FakeStorage.upload_calls = 0
    FakeStorage.deleted = []
    project_x, _, operation_x = _seed_project(org, users["OWNER"])
    frozen_x = _freeze(org, users["OWNER"], project_x, operation_x)
    version_x = UUID(frozen_x["id"])
    project_y, _, operation_y = _seed_project(org, users["OWNER"])
    frozen_y = _freeze(org, users["OWNER"], project_y, operation_y)
    version_y = UUID(frozen_y["id"])
    monkeypatch.setattr("documents.artifacts.SupabaseDocumentStorage", FakeStorage)
    with as_user(users["WORKSHOP_MANAGER"]):
        order_y = _order_for_type(
            org, users["WORKSHOP_MANAGER"], version_y, "SUPPLIER_GLASS_PO"
        )
    artifact, created = generate_artifact(
        org_id=org, actor_id=users["WORKSHOP_MANAGER"], role="WORKSHOP_MANAGER",
        project_version_id=version_y, order_id=order_y,
        document_type="DOC-02", file_format="XLSX",
    )
    assert created is True
    # The DOC-02/XLSX slot for order_y is occupied; replaying it bound to
    # version_x must reject instead of returning the existing artifact.
    with pytest.raises(DocumentaryError, match="order_not_found"):
        generate_artifact(
            org_id=org, actor_id=users["WORKSHOP_MANAGER"], role="WORKSHOP_MANAGER",
            project_version_id=version_x, order_id=order_y,
            document_type="DOC-02", file_format="XLSX",
        )
    manager = SupabaseUser(id=users["WORKSHOP_MANAGER"], email="manager@example.test")
    client = APIClient()
    client.force_authenticate(
        user=manager, token=_freeze_token(users["WORKSHOP_MANAGER"])
    )
    response = client.post(
        "/api/v1/documents/artifacts/",
        {
            "document_type": "DOC-02",
            "format": "XLSX",
            "project_version_id": str(version_x),
            "order_id": str(order_y),
        },
        format="json", HTTP_X_ORGANIZATION_ID=str(org),
    )
    assert response.status_code in (403, 404), response.content
    assert artifact["id"] not in response.content.decode()
    # A consistent replay still resolves the existing artifact idempotently.
    replayed, replayed_created = generate_artifact(
        org_id=org, actor_id=users["WORKSHOP_MANAGER"], role="WORKSHOP_MANAGER",
        project_version_id=version_y, order_id=order_y,
        document_type="DOC-02", file_format="XLSX",
    )
    assert replayed_created is False and replayed["id"] == artifact["id"]
    assert FakeStorage.upload_calls == 1
