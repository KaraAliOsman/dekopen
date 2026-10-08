"""§10 cut pack — printable workshop pack bound to the live optimization."""

import json

import pytest

from documents.repository import DocumentaryError
from production.cut_pack import render_cut_pack


def _order(payload):
    return {
        "id": "order-1",
        "order_code": "OT-7",
        "status": "RELEASED",
        "project_version_id": "ver-1",
        "payload_json": json.dumps(payload),
    }


def _version():
    return {
        "snapshot_json": json.dumps({
            "manufacturing": [
                {
                    "members": [
                        {
                            "member_id": "mem-1",
                            "bay_id": "bay-1",
                            "identity": {
                                "position_id": "pos-1",
                                "role": "FRAME",
                            },
                        }
                    ],
                    "reinforcements": [],
                    "infills": [{"infill_id": "inf-1", "bay_id": "bay-1"}],
                    "handles": [],
                    "leaves": [{"leaf_id": "leaf-1", "bay_id": "bay-1"}],
                }
            ],
            "positions": [{"id": "pos-1", "position_index": 1}],
        })
    }


_OPTIMIZATION = {
    "color": "BLANCO",
    "units": 1,
    "strategy": "AUTO",
    "bars": {
        "metrics": {
            "bars": 1,
            "cuts": 2,
            "process_waste_mm": "120",
            "reusable_remnant_mm": "800",
        },
        "workshop_cut_plan": [
            {
                "bar_index": 1,
                "commercial_sku": "DEKO-MARCO-60",
                "material": "PVC",
                "color": "BLANCO",
                "stock_length_mm": "6000",
                "head_trim_mm": "20",
                "tail_trim_mm": "20",
                "kerf_mm": "5",
                "kerf_total_mm": "5",
                "productive_length_mm": "5155",
                "process_consumed_mm": "45",
                "remainder_mm": "800",
                "remainder_reusable": True,
                "waste_mm": "45",
                "yield_pct": "85.92",
                "waste_pct": "0.75",
                "source": "NEW",
                "cuts": [
                    {
                        "sequence": 1,
                        "piece_id": "mem-1",
                        "source_kind": "PROFILE",
                        "workshop_sku": "DEMO_60",
                        "material": "PVC",
                        "color": "BLANCO",
                        "length_mm": "2500",
                        "role": "FRAME",
                        "unit_index": 1,
                        "angle_left": "45",
                        "angle_right": "45",
                        "source_position_id": "pos-1",
                        "bay_id": "bay-1",
                        "leaf_id": "leaf-1",
                        "sagitta_mm": None,
                    },
                    {
                        "sequence": 2,
                        "piece_id": "hashpiece",
                        "source_kind": "PROFILE",
                        "workshop_sku": "DEMO_60",
                        "material": "PVC",
                        "color": "BLANCO",
                        "length_mm": "2655",
                        "role": "FRAME",
                        "unit_index": 1,
                        "angle_left": "45",
                        "angle_right": "45",
                        "source_position_id": "pos-1",
                        "bay_id": "bay-1",
                        "leaf_id": None,
                        "sagitta_mm": None,
                    },
                ],
            }
        ],
    },
    "sheets": [
        {
            "sheet_index": 1,
            "purchasing_sku": "DVH-4/12/4",
            "sheet_width_mm": "2600",
            "sheet_height_mm": "1600",
            "yield_pct": "71.5",
            "placements": [
                {
                    "piece_id": "inf-1",
                    "x_mm": "0",
                    "y_mm": "0",
                    "width_mm": "1400",
                    "height_mm": "1300",
                    "rotated": False,
                    "bay_id": "bay-1",
                    "leaf_id": None,
                }
            ],
            "produced_remnants": [
                {"x_mm": "1400", "y_mm": "0", "width_mm": "1200", "height_mm": "1600"}
            ],
        }
    ],
    "unnested": [],
}


def _install_db(monkeypatch, order_payload):
    import contextlib

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        if "public.orders" in lowered:
            return _order(order_payload)
        if "project_versions" in lowered:
            return _version()
        if "tenancy_organizations" in lowered:
            return {
                "doc_paper_size": "LETTER",
                "workshop_label_format": "GRID",
            }
        raise AssertionError(lowered)

    monkeypatch.setattr("production.cut_pack.one", fake_one)
    # _bar_context looks up article/remnant facts — the fixture catalog has
    # no mapping rows, so the lookup returns empty.
    monkeypatch.setattr("production.cut_pack.rows", lambda *a, **k: [])
    monkeypatch.setattr(
        "production.cut_pack.documentary_backend", contextlib.nullcontext
    )
    monkeypatch.setattr(
        "production.cut_pack.transaction.atomic", contextlib.nullcontext
    )


def test_cut_pack_renders_pdf(monkeypatch) -> None:
    _install_db(monkeypatch, {"optimization": _OPTIMIZATION})
    content, name = render_cut_pack(org_id="org", order_id="order-1")
    assert content.startswith(b"%PDF-")
    assert name == "OT-7-pack-corte.pdf"


_FACT_UNIT = {
    "position_id": "pos-1",
    "position_index": 1,
    "repetition_index": 1,
    "nominal_width_mm": "1400.00",
    "nominal_height_mm": "1500.00",
    "placement_policy_id": "pp",
    "placement_policy_version": 1,
    "handle_policy_id": "hp",
    "handle_policy_version": 2,
    "reinforcement_policy_id": "rp",
    "reinforcement_policy_version": 1,
    "members": [
        {
            "member_id": "a" * 64,
            "semantic_member_id": "mem-1",
            "identity": {
                "position_id": "pos-1",
                "position_index": 1,
                "repetition_index": 1,
                "topology_path": "root/bay",
                "assembly": "A",
                "leaf_slot": None,
                "role": "MULLION_V",
                "physical_member_slot": "m1",
            },
            "bay_id": "bay-1",
            "leaf_id": None,
            "workshop_sku": "DEMO_60",
            "material": "PVC",
            "cut_length_mm": "2500.00",
            "angle_left": "45",
            "angle_right": "45",
            "axis": "VERTICAL",
            "start": {"x_mm": "700", "y_mm": "60"},
            "end": {"x_mm": "700", "y_mm": "1440"},
            "sagitta_mm": None,
        }
    ],
    "reinforcements": [
        {
            "reinforcement_id": "c" * 64,
            "parent_member_id": "a" * 64,
            "workshop_sku": "AC-30",
            "cut_length_mm": "2400.00",
            "angle_left": "90",
            "angle_right": "90",
            "policy_id": "rp",
            "policy_version": 1,
        }
    ],
    "leaves": [
        {
            "leaf_fact_id": "b" * 64,
            "semantic_leaf_id": "leaf-1",
            "position_id": "pos-1",
            "position_index": 1,
            "repetition_index": 1,
            "topology_path": "root/bay/leaf",
            "assembly": "A",
            "bay_id": "bay-1",
            "leaf_id": "leaf-1",
            "leaf_slot": "main",
            "opening_type": "TILT_TURN_LEFT",
            "rect": {"x_mm": "60", "y_mm": "60", "width_mm": "1280", "height_mm": "1380"},
        }
    ],
    "infills": [
        {
            "infill_id": "e" * 64,
            "semantic_infill_id": "inf-1",
            "position_id": "pos-1",
            "position_index": 1,
            "repetition_index": 1,
            "topology_path": "root/bay/leaf/infill",
            "assembly": "A",
            "bay_id": "bay-1",
            "leaf_id": "leaf-1",
            "leaf_slot": "main",
            "kind": "GLASS",
            "technical_sku": "DVH-4/12/4",
            "composition": "4-12-4",
            "rect": {"x_mm": "80", "y_mm": "80", "width_mm": "1240", "height_mm": "1340"},
            "shape": None,
        }
    ],
    "handles": [
        {
            "handle_id": "f" * 64,
            "position_id": "pos-1",
            "position_index": 1,
            "repetition_index": 1,
            "bay_id": "bay-1",
            "leaf_id": "leaf-1",
            "handle_domain_slot": "main",
            "host_member_id": "a" * 64,
            "point": {"x_mm": "700", "y_mm": "1050"},
            "requested_height_mm": "1050",
            "vertical_reference": "LEAF_BOTTOM",
            "policy_id": "hp-1",
            "policy_version": 3,
        }
    ],
    "relationships": [],
}


def _install_db_full(monkeypatch, order_payload, manufacturing):
    import contextlib

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        if "public.orders" in lowered:
            return _order(order_payload)
        if "project_versions" in lowered:
            return {
                "snapshot_json": json.dumps(
                    {
                        "manufacturing": manufacturing,
                        "positions": [
                            {"id": "pos-1", "position_index": 1}
                        ],
                    }
                )
            }
        raise AssertionError(lowered)

    monkeypatch.setattr("production.pack.one", fake_one)
    monkeypatch.setattr(
        "production.pack.documentary_backend", contextlib.nullcontext
    )
    monkeypatch.setattr(
        "production.pack.transaction.atomic", contextlib.nullcontext
    )


def test_production_pack_renders_all_sections(monkeypatch) -> None:
    from production.pack import render_production_pack

    payload = {
        "quantity": 1,
        "optimization": _OPTIMIZATION,
        "materials": {
            "glasses": [
                {
                    "bay_id": "bay-1",
                    "leaf_id": "leaf-1",
                    "width_mm": "1240",
                    "height_mm": "1340",
                    "area_m2": "1.66",
                    "weight_kg": "20.0",
                    "thickness_net_mm": "12",
                    "glass_spec": "4-12-4",
                    "article_sku": "DVH-4/12/4",
                }
            ]
        },
        "glass_polishing": [
            {
                "bay_id": "bay-1",
                "leaf_id": "leaf-1",
                "edges": {"top": True, "bottom": True},
            }
        ],
        "packing": {
            "units": [
                {
                    "unit_index": 1,
                    "label_code": "OT-7-U01",
                    "profiles": 4,
                    "reinforcements": 1,
                    "glasses": 1,
                    "panels": 0,
                    "hardware": 3,
                    "fittings": 0,
                }
            ]
        },
    }
    _install_db_full(monkeypatch, payload, [_FACT_UNIT])
    content, name = render_production_pack(org_id="org", order_id="order-1")
    assert content.startswith(b"%PDF-")
    assert name == "OT-7-pack-produccion.pdf"


def test_production_pack_refuses_invalidated(monkeypatch) -> None:
    from production.pack import render_production_pack

    _install_db_full(
        monkeypatch,
        {"optimization": {**_OPTIMIZATION, "invalidated": True}},
        [_FACT_UNIT],
    )
    with pytest.raises(DocumentaryError, match="plan_invalidated"):
        render_production_pack(org_id="org", order_id="order-1")


def test_cut_pack_requires_optimization(monkeypatch) -> None:
    _install_db(monkeypatch, {})
    with pytest.raises(DocumentaryError, match="cut_pack_requires_optimization"):
        render_cut_pack(org_id="org", order_id="order-1")


def test_cut_pack_refuses_invalidated_plan(monkeypatch) -> None:
    payload = {"optimization": {**_OPTIMIZATION, "invalidated": True}}
    _install_db(monkeypatch, payload)
    with pytest.raises(DocumentaryError, match="plan_invalidated"):
        render_cut_pack(org_id="org", order_id="order-1")
