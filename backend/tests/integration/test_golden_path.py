"""§12 full-chain scenario: emit → release → optimize → steps → dispatch.

One realistic workshop path executed end-to-end against real PostgreSQL —
the same calls the UI makes — asserting the sealed version releases, the
optimizer reserves declared stock, every routing step completes on reserved
material, and the work order dispatches with a manifest. Nothing is mocked
except object storage.
"""

from uuid import UUID

import pytest
from django.db import transaction

from documents.repository import documentary_backend
from pricing.repository import one, rows
from production import service as production_service

from tests.integration.test_shot09_documentary import (
    FakeStorage,
    _freeze,
    _seed_project,
    as_user,
    documentary_tenant,  # noqa: F401 — pytest resolves the fixture by param name
)

pytestmark = pytest.mark.rls_integration


def _seed_stock(org: UUID, actor: UUID) -> None:
    """Give the org on-hand stock for every DEMO_60 material the plan can
    reserve: bars key by (commercial_sku, physical_stock_identity); unit
    needs (hardware kits, fittings, panels) key by (purchasing_sku, '')."""
    with as_user(actor), documentary_backend():
        bar_items = rows(
            """
            SELECT m.commercial_sku AS sku,
                   m.physical_stock_identity::text AS variant_key
            FROM public.profile_purchase_mappings m
            JOIN public.profile_articles a ON a.id = m.profile_article_id
            JOIN public.profile_systems s ON s.id = a.system_id
            WHERE s.code = 'DEMO_60' AND m.org_id IS NULL
              AND m.physical_stock_identity IS NOT NULL
            UNION ALL
            SELECT r.commercial_sku, r.physical_stock_identity::text
            FROM public.reinforcement_articles r
            JOIN public.profile_systems s ON s.id = r.system_id
            WHERE s.code = 'DEMO_60' AND r.org_id IS NULL
              AND r.physical_stock_identity IS NOT NULL
            """
        )
        unit_skus = rows(
            """
            SELECT m.purchasing_sku AS sku
            FROM public.hardware_purchase_mappings m
            JOIN public.hardware_kits k ON k.id = m.hardware_kit_id
            JOIN public.profile_systems s ON s.id = k.system_id
            WHERE s.code = 'DEMO_60' AND m.org_id IS NULL
            UNION ALL
            SELECT m.purchasing_sku
            FROM public.fitting_purchase_mappings m
            JOIN public.profile_systems s ON s.id = m.system_id
            WHERE s.code = 'DEMO_60' AND m.org_id IS NULL
            UNION ALL
            SELECT m.purchasing_sku
            FROM public.panel_purchase_authorities m
            JOIN public.infill_articles i ON i.id = m.infill_article_id
            JOIN public.profile_systems s ON s.id = i.system_id
            WHERE s.code = 'DEMO_60' AND m.org_id IS NULL
            UNION ALL
            SELECT m.purchasing_sku
            FROM public.glass_purchase_mappings m
            JOIN public.profile_systems s ON s.id = m.system_id
            WHERE s.code = 'DEMO_60' AND m.org_id IS NULL
            """
        )
        for item_row in [
            *bar_items,
            *[{"sku": row["sku"], "variant_key": ""} for row in unit_skus],
        ]:
            item = one(
                """
                INSERT INTO public.inventory_items(
                    org_id, sku, name, category, unit, variant_key)
                VALUES (%s, %s, %s, 'FIXTURE', 'EA', %s)
                ON CONFLICT (org_id, sku, variant_key) DO UPDATE
                    SET name = EXCLUDED.name
                RETURNING id
                """,
                [
                    str(org),
                    str(item_row["sku"]),
                    f"Fixture {item_row['sku']}"[:200],
                    str(item_row["variant_key"]),
                ],
            )
            rows(
                """
                INSERT INTO public.inventory_movements(
                    org_id, item_id, movement_type, quantity, note, actor_id)
                VALUES (%s, %s, 'RECEIPT', %s, 'golden-path stock', %s)
                RETURNING id
                """,
                [str(org), str(item["id"]), "500", str(actor)],
            )


def test_golden_path_emit_release_optimize_steps_dispatch(
    documentary_tenant,  # noqa: F811 — injected fixture, not a redefinition
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "production.dispatch_notes.SupabaseDocumentStorage", FakeStorage
    )
    org, _, users, _ = documentary_tenant
    owner, wm = users["OWNER"], users["WORKSHOP_MANAGER"]
    project_id, _, operation_id = _seed_project(org, owner)

    frozen = _freeze(org, owner, project_id, operation_id)
    version_id = UUID(str(frozen["id"]))
    assert frozen["production_allowed"] is True, (
        "golden path must reach a production-releasable version"
    )

    _seed_stock(org, owner)

    with as_user(wm):
        released = production_service.release_production(
            org_id=org, version_id=version_id, actor_id=wm
        )
    order_ids = [UUID(str(order["id"])) for order in released["orders"]]
    assert order_ids, "release must produce at least one work order"

    for order_id in order_ids:
        with as_user(wm):
            optimized = production_service.optimize_work_order(
                org_id=org, order_id=order_id, actor_id=wm, color="WHITE"
            )
        optimization = optimized["optimization"]
        reservations = optimization["stock_reservations"]
        assert all(row["short"] == "0" for row in reservations), (
            f"declared stock must cover the plan: {reservations}"
        )
        assert optimization["unmapped_stock_skus"] == []

        detail = production_service.get_work_order(org_id=org, order_id=order_id)
        for step in detail["steps"]:
            with as_user(wm):
                production_service.transition_step(
                    org_id=org,
                    step_id=UUID(str(step["id"])),
                    action="START",
                    actor_id=wm,
                    note=None,
                )
                production_service.transition_step(
                    org_id=org,
                    step_id=UUID(str(step["id"])),
                    action="COMPLETE",
                    actor_id=wm,
                    note=None,
                )

        detail = production_service.get_work_order(org_id=org, order_id=order_id)
        assert str(detail["status"]) == "COMPLETED"

        with as_user(wm):
            production_service.generate_packing_manifest(
                org_id=org, order_id=order_id, actor_id=wm
            )
            # A guía is only emitted against a real destination: the delivery
            # must be scheduled (or a hand-off note recorded) before dispatch.
            production_service.schedule_delivery(
                org_id=org,
                order_id=order_id,
                actor_id=wm,
                scheduled_date="2030-01-15",
                time_window="AM",
                address="Obra P-1, parcela 12",
            )
            dispatched = production_service.dispatch_work_order(
                org_id=org, order_id=order_id, actor_id=wm
            )
        assert str(dispatched["status"]) == "DISPATCHED"


def test_golden_path_revision_immutable_after_change(
    documentary_tenant,  # noqa: F811 — injected fixture, not a redefinition
) -> None:
    """§12.4: a repriced successor leaves the sealed revision untouched."""
    org, _, users, _ = documentary_tenant
    owner = users["OWNER"]
    project_id, _, operation_id = _seed_project(org, owner)
    frozen = _freeze(org, owner, project_id, operation_id)
    version_id = UUID(str(frozen["id"]))

    with documentary_backend():
        snapshot_before = one(
            "SELECT snapshot_json::text AS snap FROM public.project_versions WHERE id=%s",
            [str(version_id)],
        )["snap"]
        with pytest.raises(Exception), transaction.atomic():
            rows(
                "UPDATE public.project_versions SET snapshot_json='{}'::jsonb WHERE id=%s",
                [str(version_id)],
            )
        snapshot_after = one(
            "SELECT snapshot_json::text AS snap FROM public.project_versions WHERE id=%s",
            [str(version_id)],
        )["snap"]
    assert snapshot_before == snapshot_after
