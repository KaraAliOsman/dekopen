"""D02 glazier order — unit tests.

The document renders from sealed evidence only: ``project_versions
.snapshot_json`` manufacturing facts for physical pieces, and each
``public.orders`` WORKSHOP_OT ``payload_json.materials.glasses`` for the
engine BOM enrichment (composition, surcharges, safety findings). Tests
patch the SQL boundary (``one``/``rows``/``documentary_backend``) and pin
the rendered output.
"""

from __future__ import annotations

import csv
import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from documents.repository import DocumentaryError
from production import glass_order
from production import views as production_views


@contextmanager
def _atomic():
    yield


_ORG = uuid4()
_POS_A = str(uuid4())
_POS_B = str(uuid4())
_SYS = str(uuid4())
_BAY = "B1"
_LEAF = "L1"
_INFILL_A = str(uuid4())
_INFILL_B = str(uuid4())
_ORDER_A = uuid4()
_ORDER_B = uuid4()
_VERSION = uuid4()


def _unit(position_id: str, index: int, infill_id: str, *, width: str, height: str, sku: str):
    return {
        "position_id": position_id,
        "position_index": index,
        "repetition_index": 1,
        "members": [],
        "reinforcements": [],
        "handles": [],
        "infills": [
            {
                "infill_id": infill_id,
                "kind": "GLASS",
                "bay_id": _BAY,
                "leaf_id": _LEAF,
                "rect": {"width_mm": width, "height_mm": height},
                "technical_sku": sku,
                "composition": "4 / 16 aire / 4",
            }
        ],
    }


_SNAPSHOT = {
    "project": {"code": "PRJ-01"},
    "positions": [
        {
            "id": _POS_A,
            "position_index": 1,
            "quantity": 1,
            "system_id": _SYS,
            "location_tag": "L01",
            "glass_polishing": [],
        },
        {
            "id": _POS_B,
            "position_index": 2,
            "quantity": 1,
            "system_id": _SYS,
            "location_tag": "L02",
            "glass_polishing": [
                {"bay_id": _BAY, "leaf_id": _LEAF, "edges": ["bottom"]}
            ],
        },
    ],
    "manufacturing": [
        _unit(_POS_A, 1, _INFILL_A, width="800.00", height="600.00", sku="DVH-4-16-4"),
        _unit(_POS_B, 2, _INFILL_B, width="500.00", height="700.00", sku="MONO-6"),
    ],
}


def _bom_glass(width: str, height: str, **extra):
    glass = {
        "bay_id": _BAY,
        "leaf_id": _LEAF,
        "width_mm": width,
        "height_mm": height,
        "technical_sku": "DVH-4-16-4",
        "composition": {"notation": "4 / 16 aire / 4", "layers": []},
        "surcharge_selections": [
            {"kind": "EDGE_POLISH", "edges": ["top", "left"]},
            {"kind": "DRILL", "count": 2},
        ],
        "safety_findings": [
            {
                "rule_code": "NCH135_DOOR",
                "severity": "MANDATORY",
                "required_safety": "TEMPERED",
                "message": "Puerta acristalada exige vidrio de seguridad.",
            }
        ],
    }
    glass.update(extra)
    return glass


def _order_row(order_id, position_id, code, glasses, version=_VERSION):
    return {
        "id": order_id,
        "project_id": uuid4(),
        "project_version_id": version,
        "order_code": code,
        "position_id": position_id,
        "payload_json": json.dumps(
            {"position_id": position_id, "materials": {"glasses": glasses}}
        ),
    }


_ORDERS = {
    str(_ORDER_A): _order_row(
        _ORDER_A, _POS_A, "OT-01", [_bom_glass("800.00", "600.00")]
    ),
    str(_ORDER_B): _order_row(
        _ORDER_B,
        _POS_B,
        "OT-02",
        [
            _bom_glass(
                "500.00",
                "700.00",
                surcharge_selections=[],
                safety_findings=[],
            )
        ],
    ),
}

_VERSION_ROW = {
    "id": _VERSION,
    "revision_code": "REV-C",
    "emitted_at": "2026-09-30T12:00:00Z",
    "snapshot_json": json.dumps(_SNAPSHOT),
}


def _fake_one(query, params=(), code=None):
    if "FROM public.orders" in query:
        return _ORDERS[str(params[0])]
    if "public.project_versions" in query:
        return _VERSION_ROW
    raise AssertionError(query)


def _fake_rows(query, params=()):
    if "glass_purchase_mappings" in query:
        return [
            {
                "system_id": _SYS,
                "technical_sku": "DVH-4-16-4",
                "purchasing_sku": "VID-DVH-24",
                "manufacturer_name": "Vidriería Sur",
                "glass_spec": None,
            }
        ]
    if "glass_products" in query:
        return [
            {
                "sku": "DVH-4-16-4",
                "commercial_name": "Termopanel incoloro",
                "notation": "4 / 16 aire / 4",
                "composition": "{}",
                "safety_class": "B",
                "review_pending": False,
            },
            {
                "sku": "MONO-6",
                "commercial_name": "Monolítico 6 mm",
                "notation": "6",
                "composition": "{}",
                "safety_class": None,
                "review_pending": True,
            },
        ]
    return []


def _patch():
    return (
        patch("production.glass_order.one", side_effect=_fake_one),
        patch("production.glass_order.rows", side_effect=_fake_rows),
        patch(
            "production.glass_order.documentary_backend", side_effect=_atomic
        ),
    )


def test_glazier_order_csv_lists_every_piece_with_engine_fields():
    patchers = _patch()
    with patchers[0], patchers[1], patchers[2]:
        content, media_type, name = glass_order.glazier_order(
            org_id=_ORG,
            order_id=_ORDER_A,
            extra_order_ids=[_ORDER_B],
            output_format="csv",
        )
    assert media_type == "text/csv"
    assert name == "pedido-vidriero-REV-C.csv"
    rows_ = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    assert rows_[0] == [
        "orden", "posicion", "codigo_pieza", "sku_compra", "sku_tecnico",
        "composicion", "ancho_mm", "alto_mm", "cantidad", "recargos",
        "seguridad", "proveedor",
    ]
    assert len(rows_) == 3  # header + 2 pieces
    first, second = rows_[1], rows_[2]
    assert first[0] == "OT-01" and first[1] == "L01"
    assert first[3] == "VID-DVH-24" and first[4] == "DVH-4-16-4"
    assert first[5] == "4 / 16 aire / 4"
    assert first[6] == "800" and first[7] == "600" and first[8] == "1"
    assert "Canto pulido (superior, izquierdo)" in first[9]
    assert "Perforaciones ×2" in first[9]
    assert first[10] == "templado"
    assert first[11] == "Vidriería Sur"
    # Second order: no purchase mapping → technical sku falls through, and
    # legacy glass_polishing edges surface as a surcharge line.
    assert second[0] == "OT-02" and second[1] == "L02"
    assert second[3] == "MONO-6"
    assert "Canto pulido (inferior)" in second[9]


def test_glazier_order_rejects_mixed_versions():
    other_version = str(uuid4())
    order_b = dict(_ORDERS[str(_ORDER_B)])
    order_b["project_version_id"] = other_version

    def fake_one(query, params=(), code=None):
        if "FROM public.orders" in query:
            row = dict(_ORDERS[str(params[0])])
            if str(params[0]) == str(_ORDER_B):
                row["project_version_id"] = other_version
            return row
        raise AssertionError(query)

    with patch("production.glass_order.one", side_effect=fake_one), patch(
        "production.glass_order.rows", side_effect=_fake_rows
    ), patch("production.glass_order.documentary_backend", side_effect=_atomic):
        with pytest.raises(DocumentaryError) as error:
            glass_order.glazier_order(
                org_id=_ORG,
                order_id=_ORDER_A,
                extra_order_ids=[_ORDER_B],
                output_format="csv",
            )
    assert error.value.code == "glazier_order_mixed_versions"


def test_glazier_order_empty_batch_raises():
    empty_snapshot = dict(_SNAPSHOT)
    empty_snapshot["manufacturing"] = []
    version = dict(_VERSION_ROW)
    version["snapshot_json"] = json.dumps(empty_snapshot)

    def fake_one(query, params=(), code=None):
        if "FROM public.orders" in query:
            return _ORDERS[str(params[0])]
        if "public.project_versions" in query:
            return version
        raise AssertionError(query)

    with patch("production.glass_order.one", side_effect=fake_one), patch(
        "production.glass_order.rows", side_effect=_fake_rows
    ), patch("production.glass_order.documentary_backend", side_effect=_atomic):
        with pytest.raises(DocumentaryError) as error:
            glass_order.glazier_order(
                org_id=_ORG, order_id=_ORDER_A, extra_order_ids=None,
                output_format="csv",
            )
    assert error.value.code == "glazier_order_no_glass"


def test_grouped_lines_merge_identical_pieces_and_collect_positions():
    pieces = [
        {
            "order_code": "OT-01",
            "position_label": "L01",
            "piece_code": "P01-U01-I01",
            "repetition": 1,
            "purchasing_sku": "VID-DVH-24",
            "technical_sku": "DVH-4-16-4",
            "manufacturer": "Vidriería Sur",
            "product_name": "Termopanel incoloro",
            "notation": "4 / 16 aire / 4",
            "safety_class": "B",
            "width_mm": glass_order.Decimal("800.00"),
            "height_mm": glass_order.Decimal("600.00"),
            "surcharges": ["Canto pulido (superior)"],
            "safety": [],
            "review_pending": False,
        },
        {
            **{
                "order_code": "OT-02",
                "position_label": "L02",
                "piece_code": "P02-U01-I01",
                "repetition": 1,
            },
            **{
                "purchasing_sku": "VID-DVH-24",
                "technical_sku": "DVH-4-16-4",
                "manufacturer": "Vidriería Sur",
                "product_name": "Termopanel incoloro",
                "notation": "4 / 16 aire / 4",
                "safety_class": "B",
                "width_mm": glass_order.Decimal("800.00"),
                "height_mm": glass_order.Decimal("600.00"),
                "surcharges": ["Canto pulido (superior)"],
                "safety": [],
                "review_pending": False,
            },
        },
    ]
    lines = glass_order._grouped_lines(pieces)
    assert len(lines) == 1
    assert lines[0]["qty"] == 2
    assert lines[0]["positions"] == ["L01", "L02"]


def test_surcharge_text_kinds():
    assert glass_order._surcharge_text({"kind": "EDGE_POLISH", "edges": ["top", "bottom"]}) == (
        "Canto pulido (superior, inferior)"
    )
    assert glass_order._surcharge_text({"kind": "DRILL", "count": 3}) == "Perforaciones ×3"
    assert glass_order._surcharge_text({"kind": "PALILLAJE", "columns": 4, "rows": 2}) == (
        "Palillaje 4×2"
    )
    assert glass_order._surcharge_text({"kind": "TEMPERED"}) == "Templado"
    assert glass_order._surcharge_text({"kind": "EXOTIC"}) == "EXOTIC"


def test_glazier_order_pdf_renders_labels_with_qr():
    patchers = _patch()
    with patchers[0], patchers[1], patchers[2]:
        content, media_type, name = glass_order.glazier_order(
            org_id=_ORG,
            order_id=_ORDER_A,
            extra_order_ids=None,
            output_format="pdf",
        )
    assert media_type == "application/pdf"
    assert content.startswith(b"%PDF-")
    assert name == "pedido-vidriero-REV-C.pdf"


def _client_with_scope(monkeypatch, role: str):
    org_id = _ORG
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        assert role in allowed
        yield token, SimpleNamespace(
            active_organization=SimpleNamespace(
                organization_id=org_id, role=role
            )
        ), org_id

    monkeypatch.setattr(production_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(
        user=SimpleNamespace(is_authenticated=True), token=object()
    )
    return client


def test_view_rejects_bad_format_and_batch_ids(monkeypatch):
    client = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")
    response = client.get(
        f"/api/v1/production/orders/{_ORDER_A}/glass-order/?output=xlsx"
    )
    assert response.status_code == 400
    response = client.get(
        f"/api/v1/production/orders/{_ORDER_A}/glass-order/?orders=not-a-uuid"
    )
    assert response.status_code == 400


def test_view_streams_csv(monkeypatch):
    client = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")
    patchers = _patch()
    with patchers[0], patchers[1], patchers[2]:
        response = client.get(
            f"/api/v1/production/orders/{_ORDER_A}/glass-order/?output=csv"
        )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert response["Content-Disposition"].startswith("attachment;")
    assert b"orden" in response.content and b"DVH-4-16-4" in response.content
