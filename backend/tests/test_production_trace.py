"""§11 trace: forward (version → orders → pieces) and backward
(piece_id → order → project) resolution over the sealed plan."""

from __future__ import annotations

import json
from unittest.mock import patch
from uuid import uuid4

from production import trace


ORG = uuid4()
ORDER = uuid4()
VERSION = uuid4()
PROJECT = uuid4()
PIECE = "6a20fcce3837717096c94608e59a133fc846489c7b87c409a57114f27ac102b4"


def _order_payload() -> dict:
    return {
        "position_id": str(uuid4()),
        "optimization": {
            "optimized_at": "2026-09-24T10:00:00+00:00",
            "strategy": "fast",
            "units": 1,
            "bars": {"workshop_cut_plan": [{
                "bar_index": 1,
                "commercial_sku": "COMPRA-MARCO",
                "material": "PVC",
                "color": "BLANCO",
                "stock_length_mm": "6000.00",
                "cuts": [{
                    "piece_id": PIECE,
                    "sequence": 1,
                    "role": "FRAME",
                    "length_mm": "1406.00",
                    "angle_left": "45.0",
                    "angle_right": "45.0",
                    "workshop_sku": "MARCO",
                    "source_kind": "PROFILE",
                    "source_position_id": str(uuid4()),
                    "bay_id": str(uuid4()),
                    "leaf_id": None,
                    "unit_index": 1,
                }],
            }]},
            "sheets": [{
                "sheet_index": 1,
                "purchasing_sku": "DEMO-SHEET-VIDRIO",
                "workshop_sku": "VIDRIO_4MM",
                "sheet_width_mm": "3210.00",
                "sheet_height_mm": "2250.00",
                "source": "NEW",
                "remnant_id": None,
                "yield_pct": "71.23",
                "placements": [{
                    "piece_id": PIECE,
                    "sequence": 1,
                    "workshop_sku": "VIDRIO_4MM",
                    "width_mm": "1100.00",
                    "height_mm": "900.00",
                    "x_mm": "0.00",
                    "y_mm": "0.00",
                    "rotated": False,
                    "source_position_id": str(uuid4()),
                    "bay_id": str(uuid4()),
                    "leaf_id": str(uuid4()),
                    "unit_index": 1,
                }],
            }],
            "stock_reservations": [{
                "kind": "BAR", "sku": "COMPRA-MARCO", "variant_key": "",
                "name": "COMPRA-MARCO", "unit": "BAR", "needed": "1",
                "on_hand": "10", "reserved": "1", "short": "0",
                "consumed_at": None,
            }],
        },
    }


def _one_factory():
    def fake_one(query, params=None, missing=None):
        if "FROM public.orders" in query and "WHERE id" in query:
            return {
                "id": str(ORDER), "order_code": "OT-0001", "status": "IN_PROGRESS",
                "project_id": str(PROJECT), "project_version_id": str(VERSION),
                "order_type": "WORKSHOP_OT",
                "payload_json": json.dumps(_order_payload()),
                "created_at": "t0", "updated_at": "t1",
            }
        if "FROM public.projects" in query:
            return {"id": str(PROJECT), "code": "PR-1", "name": "Casa",
                    "client_name": "Ana", "current_revision": "REV-A"}
        if "FROM public.project_versions" in query:
            return {"id": str(VERSION), "revision_code": "REV-A",
                    "snapshot_sha256": "s" * 64, "bom_hash": "b" * 64,
                    "emitted_at": "t0", "production_allowed": True,
                    "snapshot_json": json.dumps({"manufacturing": []})}
        raise AssertionError(query[:80])
    return fake_one


def _rows_factory():
    def fake_rows(query, params=None):
        if "FROM public.production_steps" in query and "work_center" in query:
            return [{
                "id": str(uuid4()), "sequence": 1, "code": "CUT",
                "label": "Corte", "status": "DONE",
                "work_center_id": str(uuid4()),
                "work_center_code": "SIERRA", "work_center_name": "Sierra 1",
                "started_at": "t0", "finished_at": "t1",
                "actor_id": str(uuid4()), "note": None,
            }]
        if "FROM public.production_step_events" in query:
            return [{"id": str(uuid4()), "step_id": str(uuid4()),
                     "event": "WO_OPTIMIZED", "actor_id": str(uuid4()),
                     "payload": "{}", "created_at": "t0"}]
        if "FROM public.inventory_movements" in query:
            return [{"id": str(uuid4()), "movement_type": "RESERVATION",
                     "quantity": "1", "note": "wo-reserve:BAR",
                     "created_at": "t0", "actor_id": str(uuid4()),
                     "item_id": str(uuid4()), "sku": "COMPRA-MARCO",
                     "variant_key": "", "item_name": "Bar"}]
        if "FROM public.inventory_remnants" in query:
            return []
        raise AssertionError(query[:90])
    return fake_rows


def test_trace_work_order_assembles_full_chain() -> None:
    with patch("production.trace.one", side_effect=_one_factory()), \
         patch("production.trace.rows", side_effect=_rows_factory()), \
         patch("production.trace.documentary_backend"):
        report = trace.trace_work_order(org_id=ORG, order_id=ORDER)

    assert report["work_order"]["order_code"] == "OT-0001"
    assert report["project"]["code"] == "PR-1"
    assert report["version"]["revision_code"] == "REV-A"
    (bar,) = report["plan"]["bars"]
    (cut,) = bar["cuts"]
    assert cut["piece_id"] == PIECE
    assert cut["source_position_id"]
    (sheet,) = report["plan"]["sheets"]
    assert sheet["width_mm"] == "3210.00"
    (placement,) = sheet["pieces"]
    assert placement["piece_id"] == PIECE
    assert placement["x_mm"] == "0.00"
    assert report["steps"][0]["code"] == "CUT"
    assert report["stock"]["movements"][0]["movement_type"] == "RESERVATION"
    assert report["stock"]["reservations"][0]["reserved"] == "1"


def test_trace_piece_walks_backward() -> None:
    def fake_rows(query, params=None):
        if "FROM public.orders" in query and "LIKE" in query:
            return [{
                "id": str(ORDER), "order_code": "OT-0001",
                "status": "IN_PROGRESS",
                "project_id": str(PROJECT),
                "project_version_id": str(VERSION),
                "payload_json": json.dumps(_order_payload()),
            }]
        if "FROM public.production_steps" in query:
            return [{"sequence": 1, "code": "CUT", "label": "Corte",
                     "status": "DONE"}]
        raise AssertionError(query[:90])

    with patch("production.trace.rows", side_effect=fake_rows), \
         patch("production.trace.one", side_effect=_one_factory()), \
         patch("production.trace.documentary_backend"):
        report = trace.trace_piece(org_id=ORG, piece_id=PIECE)

    bar_match, sheet_match = report["matches"]
    assert bar_match["location"]["kind"] == "BAR"
    assert bar_match["location"]["bar_index"] == 1
    assert bar_match["location"]["piece"]["piece_id"] == PIECE
    assert sheet_match["location"]["kind"] == "SHEET"
    assert sheet_match["location"]["sheet_index"] == 1
    assert sheet_match["location"]["workshop_sku"] == "VIDRIO_4MM"
    assert bar_match["steps"][0]["status"] == "DONE"


def test_trace_piece_unknown_returns_empty() -> None:
    with patch("production.trace.rows", return_value=[]):
        report = trace.trace_piece(org_id=ORG, piece_id="nope")
    assert report["matches"] == []


def test_trace_version_lists_orders_with_piece_counts() -> None:
    def fake_one(query, params=None, missing=None):
        if "FROM public.project_versions" in query:
            return {"id": str(VERSION), "project_id": str(PROJECT),
                    "revision_code": "REV-A", "snapshot_sha256": "s" * 64,
                    "bom_hash": "b" * 64, "emitted_at": "t0",
                    "production_allowed": True}
        if "FROM public.projects" in query:
            return {"id": str(PROJECT), "code": "PR-1", "name": "Casa",
                    "client_name": "Ana"}
        raise AssertionError(query[:80])

    def fake_rows(query, params=None):
        if "FROM public.orders" in query and "project_version_id" in query:
            return [{
                "id": str(ORDER), "order_code": "OT-0001",
                "status": "RELEASED", "order_type": "WORKSHOP_OT",
                "payload_json": json.dumps(_order_payload()),
                "created_at": "t0",
            }]
        raise AssertionError(query[:90])

    with patch("production.trace.one", side_effect=fake_one), \
         patch("production.trace.rows", side_effect=fake_rows):
        report = trace.trace_version(org_id=ORG, version_id=VERSION)

    (wo,) = report["work_orders"]
    assert wo["work_order"]["order_code"] == "OT-0001"
    assert wo["pieces"] == 2
    assert wo["sheets"] == 1
    assert wo["positions_cut"]  # traced back to the frozen position
