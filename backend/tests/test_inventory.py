"""Inventory: stock derivation, receiving flow, movement recording, views."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from documents.repository import DocumentaryError
from inventory import service, views as inventory_views


def test_list_stock_returns_view_rows() -> None:
    org_id = uuid4()
    with patch("inventory.service.rows") as mock_rows:
        mock_rows.return_value = [
            {
                "item_id": uuid4(),
                "sku": "UMBRAL-ALU",
                "name": "Umbral",
                "category": "PROFILE",
                "unit": "MM",
                "variant_key": "",
                "on_hand_qty": Decimal("1200.00"),
                "reserved_qty": Decimal("400.00"),
                "available_qty": Decimal("800.00"),
            }
        ]
        output = service.list_stock(org_id=org_id)
    assert output["items"][0]["available_qty"] == Decimal("800.00")
    mock_rows.assert_called_once()


def test_order_receiving_computes_outstanding() -> None:
    org_id, order_id = uuid4(), uuid4()
    line_id = uuid4()

    def fake_rows(query, params):
        if "order_requirement_lines" in query:
            return [
                {
                    "id": line_id,
                    "quantity": Decimal("10"),
                    "received_qty": Decimal("4"),
                    "damaged_qty": Decimal("1"),
                    "line_snapshot": {"purchasing_sku": "SKU-1", "category": "PROFILE", "unit": "MM"},
                }
            ]
        return []

    with patch("inventory.service.rows", side_effect=fake_rows), patch(
        "inventory.service.one",
        return_value={
            "id": order_id,
            "order_code": "PO-X",
            "order_type": "SUPPLIER_PROFILE_PO",
            "status": "PARTIALLY_RECEIVED",
            "supplier_name": "Vendor",
        },
    ), patch(
        "inventory.service.documentary_backend", return_value=_atomic()
    ):
        output = service.order_receiving(org_id=org_id, order_id=order_id)
    # Damaged goods never fulfill: 4 arrived, 1 of them damaged → 3 good,
    # still owed 7 of the ordered 10.
    assert output["lines"][0]["outstanding_qty"] == Decimal("7")
    assert output["lines"][0]["purchasing_sku"] == "SKU-1"


def test_receive_order_rejects_draft() -> None:
    org_id, order_id = uuid4(), uuid4()
    with patch("inventory.service.rows", return_value=[]), patch(
        "inventory.service.one",
        return_value={"id": order_id, "status": "DRAFT"},
    ), patch("inventory.service.transaction.atomic", return_value=_atomic()), patch(
        "inventory.service.documentary_backend", return_value=_atomic()
    ):
        with pytest.raises(DocumentaryError) as error:
            service.receive_order(
                org_id=org_id,
                actor_id=uuid4(),
                order_id=order_id,
                receipt_key="k1",
                note=None,
                lines=[],
            )
    assert error.value.code == "order_not_sent"


def test_receive_order_rejects_unknown_line() -> None:
    org_id, order_id = uuid4(), uuid4()

    def fake_one(query, params, code=None):
        if "FOR UPDATE" in query:
            return {"id": order_id, "status": "SENT"}
        return {"id": uuid4()}

    with patch("inventory.service.rows", return_value=[]), patch(
        "inventory.service.one", side_effect=fake_one
    ), patch("inventory.service.transaction.atomic", return_value=_atomic()), patch(
        "inventory.service.documentary_backend", return_value=_atomic()
    ):
        with pytest.raises(DocumentaryError) as error:
            service.receive_order(
                org_id=org_id,
                actor_id=uuid4(),
                order_id=order_id,
                receipt_key="k2",
                note=None,
                lines=[{"order_line_id": str(uuid4()), "received_qty": Decimal("2"), "damaged_qty": Decimal("0")}],
            )
    assert error.value.code == "receipt_line_unknown"


def test_receive_order_idempotent_replay() -> None:
    org_id, order_id = uuid4(), uuid4()
    with patch(
        "inventory.service.rows",
        return_value=[{"id": uuid4(), "receipt_key": "dup", "order_id": order_id}],
    ), patch("inventory.service.transaction.atomic", return_value=_atomic()), patch(
        "inventory.service.documentary_backend", return_value=_atomic()
    ), patch(
        "inventory.service.order_receiving", return_value={"order": {}, "lines": [], "receipts": []}
    ) as receiving:
        output, created = service.receive_order(
            org_id=org_id,
            actor_id=uuid4(),
            order_id=order_id,
            receipt_key="dup",
            note=None,
            lines=[],
        )
    assert created is False
    receiving.assert_called_once()


def test_receive_order_takes_receipt_key_lock() -> None:
    org_id, order_id = uuid4(), uuid4()
    queries = []

    def fake_rows(query, params=()):
        queries.append(query)
        return []

    with patch("inventory.service.rows", side_effect=fake_rows), patch(
        "inventory.service.one",
        return_value={"id": order_id, "status": "DRAFT"},
    ), patch("inventory.service.transaction.atomic", return_value=_atomic()), patch(
        "inventory.service.documentary_backend", return_value=_atomic()
    ):
        with pytest.raises(DocumentaryError):
            service.receive_order(
                org_id=org_id,
                actor_id=uuid4(),
                order_id=order_id,
                receipt_key="k-lock",
                note=None,
                lines=[],
            )
    assert any("pg_advisory_xact_lock" in q for q in queries)


def test_next_order_status_fulfilled_per_line() -> None:
    with patch(
        "inventory.service.one", return_value={"fulfilled": True}
    ):
        assert service._next_order_status(org_id=uuid4(), order_id=uuid4()) == "FULFILLED"
    with patch(
        "inventory.service.one", return_value={"fulfilled": False}
    ):
        assert (
            service._next_order_status(org_id=uuid4(), order_id=uuid4())
            == "PARTIALLY_RECEIVED"
        )


def test_record_movement_returns_full_projection() -> None:
    row = {
        "id": uuid4(),
        "item_id": uuid4(),
        "movement_type": "SCRAP",
        "quantity": Decimal("1.00"),
        "order_id": None,
        "order_line_id": None,
        "lot_code": "L1",
        "note": "n",
        "actor_id": uuid4(),
        "created_at": "2026-09-23T00:00:00Z",
    }
    with patch("inventory.service.rows", return_value=[]), patch(
        "inventory.service.one", return_value=row
    ), patch(
        "inventory.service.transaction.atomic", return_value=_atomic()
    ), patch("inventory.service.documentary_backend", return_value=_atomic()):
        output = service.record_movement(
            org_id=uuid4(),
            actor_id=uuid4(),
            item_id=uuid4(),
            movement_type="SCRAP",
            quantity=Decimal("1"),
            lot_code="L1",
            note="n",
        )
    assert output["item_id"] == row["item_id"]
    assert output["order_id"] is None
    assert output["movement_type"] == "SCRAP"


def test_receipt_post_rejects_zero_quantity(monkeypatch) -> None:
    client, _, _ = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")
    response = client.post(
        f"/api/v1/inventory/orders/{uuid4()}/receipts/",
        {
            "receipt_key": "r0",
            "lines": [{"order_line_id": str(uuid4()), "received_qty": "0.00"}],
        },
        format="json",
    )
    assert response.status_code == 400


def test_record_movement_type_gate() -> None:
    with pytest.raises(DocumentaryError) as error:
        service.record_movement(
            org_id=uuid4(),
            actor_id=uuid4(),
            item_id=uuid4(),
            movement_type="CONSUMPTION",
            quantity=1,
            lot_code=None,
            note="x",
        )
    assert error.value.code == "movement_type_not_allowed"


@contextmanager
def _atomic():
    yield


def _tenant(role: str, org_id):
    return SimpleNamespace(
        active_organization=SimpleNamespace(organization_id=org_id, role=role)
    )


def _client_with_scope(monkeypatch, role: str):
    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        assert role in allowed
        yield token, _tenant(role, org_id), org_id

    monkeypatch.setattr(inventory_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True), token=object())
    return client, token, org_id


def test_stock_view_returns_items(monkeypatch) -> None:
    client, _, org_id = _client_with_scope(monkeypatch, "ESTIMATOR")
    monkeypatch.setattr(service, "list_stock", lambda *, org_id: {"items": [{"sku": "S"}]})
    response = client.get("/api/v1/inventory/stock/")
    assert response.status_code == 200
    assert response.data == {"items": [{"sku": "S"}]}


def test_receipt_post_forwards_payload(monkeypatch) -> None:
    client, token, org_id = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")
    seen = {}

    def fake_receive(**kwargs):
        seen.update(kwargs)
        return {"order": {}, "lines": [], "receipts": []}, True

    monkeypatch.setattr(service, "receive_order", fake_receive)
    order_id = uuid4()
    response = client.post(
        f"/api/v1/inventory/orders/{order_id}/receipts/",
        {
            "receipt_key": "r1",
            "lines": [{"order_line_id": str(uuid4()), "received_qty": "3.00"}],
        },
        format="json",
    )
    assert response.status_code == 201
    assert seen["receipt_key"] == "r1"
    assert seen["actor_id"] == token.user_id


def test_receipt_post_denies_estimator(monkeypatch) -> None:
    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        from authentication.errors import contract_error

        if "ESTIMATOR" in allowed and len(allowed) > 1:
            yield token, _tenant("ESTIMATOR", org_id), org_id
        else:
            raise contract_error(403, "documentary_permission_denied", "denied")
            yield

    monkeypatch.setattr(inventory_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True), token=object())
    response = client.post(
        f"/api/v1/inventory/orders/{uuid4()}/receipts/",
        {"receipt_key": "r2", "lines": [{"order_line_id": str(uuid4()), "received_qty": "1.00"}]},
        format="json",
    )
    assert response.status_code == 403


def _remnant_row(remnant_id, order_id):
    from datetime import datetime, timezone

    return {
        "id": remnant_id,
        "kind": "BAR",
        "stock_authority_id": uuid4(),
        "sheet_workshop_sku": None,
        "physical_stock_identity": "AUTH-1",
        "material": "PVC",
        "color": "WHITE",
        "length_mm": Decimal("3000.00"),
        "width_mm": None,
        "height_mm": None,
        "status": "RESERVED",
        "origin": "PURCHASE",
        "origin_order_id": None,
        "reserved_order_id": order_id,
        "consumed_order_id": None,
        "rack_location": None,
        "notes": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def test_unreserve_remnant_evicts_order_plan_claim() -> None:
    # Releasing a RESERVED drop frees the physical remnant — the reserving
    # order's plan must stop claiming it in the same transaction, or a second
    # order could book the drop while the first plan still lists it.
    import json

    from inventory import remnants

    org_id, remnant_id, order_id = uuid4(), uuid4(), uuid4()
    payload = {
        "optimization": {
            "remnants": {
                "consumed": [
                    {"id": str(remnant_id), "kind": "BAR"},
                    {"id": str(uuid4()), "kind": "BAR"},
                ]
            },
            "bars": {
                "workshop_cut_plan": [
                    {"remnant_id": str(remnant_id), "source": "REMNANT", "cuts": []},
                    {"remnant_id": str(uuid4()), "source": "REMNANT", "cuts": []},
                ]
            },
            "sheets": [
                {"remnant_id": str(remnant_id), "source": "REMNANT"},
            ],
        },
        # Exports rendered from the old plan must die with the claim — their
        # fingerprints no longer match and their layout references the drop.
        "cnc_export": {"files": []},
        "dxf_export": {"files": []},
        "operations_export": {"files": []},
    }
    updates: list = []

    def fake_one(query, params=(), code=None):
        if "inventory_remnants" in query:
            return _remnant_row(remnant_id, order_id)
        if "public.orders" in query:
            return {"payload_json": payload}
        raise AssertionError(query)

    def fake_rows(query, params=()):
        updates.append((query, params))
        return [{"id": remnant_id}]

    with patch("inventory.remnants.one", side_effect=fake_one), patch(
        "inventory.remnants.rows", side_effect=fake_rows
    ), patch(
        "inventory.remnants.transaction.atomic", return_value=_atomic()
    ), patch(
        "inventory.remnants.documentary_backend", return_value=_atomic()
    ):
        output = remnants.unreserve_remnant(
            org_id=org_id, remnant_id=remnant_id, actor_id=uuid4()
        )

    assert output["status"] == "RESERVED"  # refreshed stub row
    order_update = next(u for u in updates if "payload_json" in u[0])
    written = json.loads(order_update[1][0])
    optimization = written["optimization"]
    consumed_ids = [e["id"] for e in optimization["remnants"]["consumed"]]
    assert str(remnant_id) not in consumed_ids
    assert len(consumed_ids) == 1
    plan = optimization["bars"]["workshop_cut_plan"]
    evicted = next(b for b in plan if b["source"] == "NEW")
    assert evicted["remnant_id"] is None
    kept = next(b for b in plan if b["source"] == "REMNANT")
    assert kept["remnant_id"] is not None
    assert optimization["sheets"][0]["source"] == "NEW"
    assert optimization["sheets"][0]["remnant_id"] is None
    # The plan's claim on physical stock is gone — the layout can no longer
    # prove the pieces fit real stock, so a consuming step must refuse until
    # a fresh optimize re-reserves (work_order_plan_stale gate).
    assert optimization["invalidated"] is True
    for export_key in ("cnc_export", "dxf_export", "operations_export"):
        assert export_key not in written


def test_unreserve_remnant_refuses_moved_reservation() -> None:
    # Lock order is probe(order) → remnant to match optimize_work_order. If the
    # remnant's reservation moved to a different order between the probe and
    # the lock, the order we locked first is not the plan owner — the write
    # must refuse rather than evict a plan whose lock was never taken.
    from inventory import remnants

    org_id, remnant_id, order_a, order_b = uuid4(), uuid4(), uuid4(), uuid4()
    probe_row = _remnant_row(remnant_id, order_a)
    locked_row = _remnant_row(remnant_id, order_b)
    remnant_reads = iter([probe_row, locked_row])

    def fake_one(query, params=(), code=None):
        if "inventory_remnants" in query:
            return next(remnant_reads)
        if "public.orders" in query:
            return {"id": order_a}
        raise AssertionError(query)

    with patch("inventory.remnants.one", side_effect=fake_one), patch(
        "inventory.remnants.transaction.atomic", return_value=_atomic()
    ), patch(
        "inventory.remnants.documentary_backend", return_value=_atomic()
    ), pytest.raises(DocumentaryError) as error:
        remnants.unreserve_remnant(
            org_id=org_id, remnant_id=remnant_id, actor_id=uuid4()
        )
    assert error.value.code == "remnant_reservation_moved"


def test_cancel_order_requires_attestation() -> None:
    from purchasing import service as purchasing_service

    with pytest.raises(DocumentaryError) as error:
        purchasing_service.cancel_order(
            org_id=uuid4(), actor_id=uuid4(), order_id=uuid4(), confirmed=False
        )
    assert error.value.code == "order_cancel_confirmation_required"


def test_cancel_order_rejects_orders_with_arrivals() -> None:
    from purchasing import service as purchasing_service

    org_id, order_id = uuid4(), uuid4()
    with patch(
        "purchasing.service.one",
        return_value={
            "id": order_id,
            "order_code": "PO-1",
            "order_type": "SUPPLIER_GLASS_PO",
            "status": "PARTIALLY_RECEIVED",
            "supplier_name": "Vendor",
            "order_snapshot_hash": "a" * 64,
        },
    ), patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        with pytest.raises(DocumentaryError) as error:
            purchasing_service.cancel_order(
                org_id=org_id, actor_id=uuid4(), order_id=order_id, confirmed=True
            )
    assert error.value.code == "order_state_invalid"


def test_cancel_order_idempotent_replay() -> None:
    from purchasing import service as purchasing_service

    org_id, order_id = uuid4(), uuid4()
    row = {
        "id": order_id,
        "order_code": "PO-1",
        "order_type": "SUPPLIER_GLASS_PO",
        "status": "CANCELLED",
        "supplier_name": "Vendor",
        "order_snapshot_hash": "a" * 64,
        "cancelled_by": uuid4(),
        "cancelled_at": None,
        "expected_at": None,
    }
    with patch("purchasing.service.one", return_value=row), patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        output = purchasing_service.cancel_order(
            org_id=org_id, actor_id=uuid4(), order_id=order_id, confirmed=True
        )
    assert output["status"] == "CANCELLED"


def test_orders_index_projects_orders_with_received_totals() -> None:
    from purchasing import service as purchasing_service

    org_id = uuid4()
    order_id = uuid4()
    row = {
        "id": order_id,
        "order_code": "OC-GLASS-1",
        "order_type": "SUPPLIER_GLASS_PO",
        "status": "PARTIALLY_RECEIVED",
        "supplier_identity": "76.111-2",
        "supplier_name": "Vendor",
        "expected_at": None,
        "sent_at": None,
        "created_at": None,
        "revision_code": "REV-A",
        "project_version_id": uuid4(),
        "project_id": uuid4(),
        "project_code": "P-01",
        "line_count": 2,
        "total_qty": Decimal("10"),
        "good_qty": Decimal("4"),
    }
    with patch("purchasing.service.rows", return_value=[row]) as query, patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        output = purchasing_service.orders_index(org_id)
    assert output["orders"][0]["outstanding_qty"] == "6"
    assert output["orders"][0]["project_code"] == "P-01"
    assert query.call_args[0][0].count("%s") == 3


def test_trace_labels_map_member_ids_to_workshop_codes() -> None:
    import json

    from purchasing import service as purchasing_service

    version_id, org_id = uuid4(), uuid4()
    member_id = "a" * 64
    bay_id = "b" * 64
    snapshot = {
        "manufacturing": [
            {
                "members": [{"member_id": member_id, "bay_id": bay_id}],
                "reinforcements": [],
                "infills": [],
                "handles": [],
            }
        ],
        "positions": [{"id": "pos-1", "position_index": 1}],
    }
    with patch(
        "purchasing.service.one",
        return_value={"snapshot_json": json.dumps(snapshot)},
    ):
        labels = purchasing_service._trace_labels(version_id, org_id)
    assert labels[member_id] == "M-01"
    assert labels[bay_id] == "V-01"
    assert labels["pos-1"] == "P1"


def test_line_snapshot_aligns_trace_labels_with_entries() -> None:
    import json

    from purchasing import service as purchasing_service

    row = {
        "id": uuid4(),
        "requirement_key": "k" * 64,
        "order_type": "SUPPLIER_GLASS_PO",
        "category": "GLASS_UNIT",
        "technical_identity": json.dumps({"authority_ids": ["a1"], "technical_skus": ["S1"]}),
        "purchasing_sku": "DVE-4-12-4",
        "physical_stock_identity": None,
        "unit": "EA",
        "quantity": Decimal("4"),
        "specification": json.dumps({}),
        "source_trace": json.dumps(["m" * 64, "deadbeef-hash"]),
    }
    output = purchasing_service._line_snapshot(row, {"m" * 64: "I-01"})
    assert output["source_trace_labels"] == ["I-01", None]


def test_allocate_requirement_rejects_expired_eligibility() -> None:
    import json

    from purchasing import service as purchasing_service

    org_id, requirement_id, eligibility_id = uuid4(), uuid4(), uuid4()
    requirement = {
        "id": requirement_id,
        "requirement_key": "a" * 64,
        "project_id": uuid4(),
        "project_version_id": uuid4(),
        "org_id": org_id,
        "order_type": "SUPPLIER_GLASS_PO",
    }
    eligibility = {
        "id": eligibility_id,
        "project_id": requirement["project_id"],
        "project_version_id": requirement["project_version_id"],
        "org_id": org_id,
        "order_type": "SUPPLIER_GLASS_PO",
        "eligible_requirement_keys": json.dumps(["a" * 64]),
        "evidence": json.dumps({"valid_until": "2000-01-01"}),
    }
    with patch(
        "purchasing.service.one", side_effect=[requirement, eligibility]
    ), patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        with pytest.raises(DocumentaryError) as error:
            purchasing_service.allocate_requirement(
                org_id=org_id,
                actor_id=uuid4(),
                requirement_id=requirement_id,
                eligibility_id=eligibility_id,
            )
    assert error.value.code == "supplier_eligibility_expired"


def test_create_eligibility_writes_directory_entry() -> None:

    from purchasing import service as purchasing_service

    org_id, version_id = uuid4(), uuid4()
    version = {
        "id": version_id,
        "project_id": uuid4(),
        "org_id": org_id,
        "revision_code": "REV-A",
        "authority_version": "SHOT09_V1",
        "bom_hash": "b" * 64,
        "snapshot_sha256": "c" * 64,
        "production_allowed": False,
        "documentary_complete": True,
        "emitted_at": None,
        "project_code": "P-01",
    }
    requirement = {"requirement_key": "a" * 64}
    eligibility_row = {"id": uuid4(), "content_hash": "d" * 64}
    supplier_row = {
        "id": uuid4(),
        "tax_id": "76.111-2",
        "name": "Vidrios SPA",
        "details": "{}",
        "updated_at": "2026-09-25",
    }
    data = {
        "order_type": "SUPPLIER_GLASS_PO",
        "supplier_identity": "76.111-2",
        "supplier_name": "Vidrios SPA",
        "supplier_details": {},
        "eligible_requirement_keys": ["a" * 64],
        "evidence": {},
        "version": 1,
        "confirmed": True,
    }
    with patch("purchasing.service._version", return_value=version), patch(
        "purchasing.service._requirements", return_value=[requirement]
    ), patch(
        "purchasing.service.one", side_effect=[eligibility_row, supplier_row]
    ) as mock_one, patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        output = purchasing_service.create_eligibility(
            org_id=org_id, actor_id=uuid4(), version_id=version_id, data=data
        )
    assert output["content_hash"] == "d" * 64
    supplier_sql = mock_one.call_args_list[1][0][0]
    assert "public.suppliers" in supplier_sql
    assert "ON CONFLICT(org_id,tax_id)" in supplier_sql
    assert mock_one.call_args_list[1][0][1][1] == "76.111-2"


def test_suppliers_index_and_upsert_roundtrip() -> None:
    import json

    from purchasing import service as purchasing_service

    org_id = uuid4()
    row = {
        "id": uuid4(),
        "tax_id": "76.111-2",
        "name": "Vidrios SPA",
        "details": json.dumps({"email": "v@spa.cl"}),
        "updated_at": "2026-09-25T00:00:00+00:00",
    }
    with patch("purchasing.service.rows", return_value=[row]), patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        index = purchasing_service.suppliers_index(org_id)
    assert index["suppliers"][0]["tax_id"] == "76.111-2"
    assert index["suppliers"][0]["details"]["email"] == "v@spa.cl"

    upsert_row = dict(row)
    with patch("purchasing.service.one", return_value=upsert_row) as mock_one, patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        output = purchasing_service.create_supplier(
            org_id=org_id,
            actor_id=uuid4(),
            data={"tax_id": "76.111-2", "name": "Vidrios SPA",
                  "details": {"email": "v@spa.cl"}, "confirmed": True},
        )
    assert output["tax_id"] == "76.111-2"
    assert "ON CONFLICT(org_id,tax_id)" in mock_one.call_args[0][0]
