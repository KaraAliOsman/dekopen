"""P02 — the physical piece code is ONE identity across every artifact.

La OT imprime ``P02-U01-M01`` en el pack de corte, el CSV de la sierra, el
DXF del nesting y las etiquetas — el conjunto de códigos debe ser literal
el mismo en todos, o el taller no puede reconciliar una pieza en mano con
su línea de programa.
"""

from __future__ import annotations

import re

from documents.renderers import (
    _cut_member_map,
    _infill_code_map,
    _infill_key,
    _piece_labels,
    _cut_key,
)
from production.dxf import dxf_files
from production import service
from production.cut_pack import _pack_html

from tests.test_production import _cutpack_optimization, _cutpack_snapshot

_PIECE_RE = re.compile(r"P\d+-U\d+-[A-Z]+\d+(?:·R)?")
_INFILL_RE = re.compile(r"P\d+-U\d+-I\d+")
# AC1015 DXF is ASCII-only: '·R' travels as '-R' on machine text — same
# piece identity, transport glyph. Normalize before comparing sets.
_DXF_RE = re.compile(r"P\d+-U\d+-[A-Z]+\d+(?:[-·]R)?|P\d+-U\d+-I\d+")


def _dxf_codes(text: str) -> set[str]:
    return {code.replace("-R", "·R") for code in _DXF_RE.findall(text)}


def _visible_text(html: str) -> str:
    """Rendered text minus tags/attributes (SVG geometry, CSS, QR payloads
    are machine data, not readable copy). The titleblock IS the footer —
    its abbreviated fingerprint is allowed there by the encargo, and at
    8 hex it can never trip the ≥10 detector either way."""
    no_style = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", no_style)


def _with_sheet(snapshot: dict, optimization: dict) -> None:
    """Add one nested infill so sheet artifacts join the label contract."""
    infill_id = "9" * 64
    snapshot["manufacturing"][0]["infills"] = [
        {
            "infill_id": infill_id,
            "position_id": "pos-1",
            "bay_id": "B1",
            "leaf_id": "L1",
            "rect": {"width_mm": "800.00", "height_mm": "600.00"},
        }
    ]
    optimization["sheets"] = [
        {
            "sheet_index": 1,
            "purchasing_sku": "GLASS-4",
            "sheet_width_mm": "3210",
            "sheet_height_mm": "2250",
            "yield_pct": "91.0",
            "placements": [
                {
                    "piece_id": "spec-i1",
                    "x_mm": "50",
                    "y_mm": "40",
                    "width_mm": "800",
                    "height_mm": "600",
                    "rotated": False,
                    "unit_index": 1,
                    "bay_id": "B1",
                    "leaf_id": "L1",
                    "source_position_id": "pos-1",
                }
            ],
        }
    ]


def test_piece_labels_are_identical_across_artifacts() -> None:
    snapshot = _cutpack_snapshot()
    optimization = _cutpack_optimization()
    _with_sheet(snapshot, optimization)

    labels = _piece_labels(snapshot)
    cut_map = _cut_member_map(snapshot, labels)
    infill_map = _infill_code_map(snapshot, labels)

    # --- cut-pack HTML (PDF source) --------------------------------------
    html = _pack_html(
        order={"order_code": "OT-000001"},
        optimization=optimization,
        snapshot=snapshot,
        labels=labels,
        cut_map=cut_map,
        infills=infill_map,
        bar_meta={},
        remnant_racks={},
        fingerprint="f" * 64,
    )
    pack_codes = set(_PIECE_RE.findall(html)) | set(_INFILL_RE.findall(html))

    # --- CNC CSVs ----------------------------------------------------------
    bars_csv = service._cnc_bars_csv(optimization, cut_map=cut_map)
    csv_codes = set(_PIECE_RE.findall(bars_csv))
    sheets_csv = service._cnc_sheets_csv(optimization, infill_map=infill_map)
    csv_codes |= set(_INFILL_RE.findall(sheets_csv))
    # the sheet row must resolve the same code the pack prints — a missing
    # label would leave the cell empty and break the reconciliation.
    assert "P02-U01-I01" in sheets_csv

    # --- DXF ----------------------------------------------------------------
    codes: dict[str, str] = {}
    for bar in optimization["bars"]["workshop_cut_plan"]:
        for cut in bar["cuts"]:
            code = cut_map.get(_cut_key(cut))
            if code:
                codes[str(cut["piece_id"])] = code
    for sheet in optimization["sheets"]:
        for placement in sheet["placements"]:
            codes[str(placement["piece_id"])] = infill_map.get(
                _infill_key(placement), str(placement["piece_id"])
            )
    files = dxf_files(optimization, codes=codes)
    dxf_codes = set()
    for text in files.values():
        dxf_codes |= _dxf_codes(text)

    assert dxf_codes == pack_codes == csv_codes
    assert {
        "P02-U01-M01", "P02-U01-M02", "P02-U02-M01", "P02-U02-M02",
        "P02-U01-M02·R", "P02-U02-M02·R", "P02-U01-I01",
    } == pack_codes


def test_artifacts_print_no_raw_hex_or_bad_format() -> None:
    """El plan y los documentos no muestran: hex ≥10 fuera del pie de página,
    decimales de máquina (`.0000`), ni porcentajes con más de un decimal."""
    snapshot = _cutpack_snapshot()
    optimization = _cutpack_optimization()
    _with_sheet(snapshot, optimization)

    labels = _piece_labels(snapshot)
    html = _pack_html(
        order={"order_code": "OT-000001"},
        optimization=optimization,
        snapshot=snapshot,
        labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={},
        remnant_racks={},
        fingerprint="f" * 64,
    )
    # Long hex outside the running footer — the titleblock is the footer.
    # Geometry lives in SVG attributes; the rule binds visible text only.
    text = _visible_text(html)
    assert not re.findall(r"[0-9a-fA-F]{10,}", text), re.findall(
        r"[0-9a-fA-F]{10,}", text
    )[:3]
    assert not re.search(r"\d+\.\d{4}", text)
    assert not re.search(r"\d+[\.,]\d{2,}\s?%", text)


def test_documents_print_no_raw_hex_or_bad_format() -> None:
    """DOC-02..DOC-07 surfaces follow the same render contract."""
    from documents.renderers import _doc01, _doc02, _doc03, _doc06, _doc07
    from tests.test_documents_contract import order_snapshot, revision_snapshot

    renders = [
        (lambda: _doc01(revision_snapshot()), "_doc01"),
        (lambda: _doc02(order_snapshot("SUPPLIER_GLASS_PO")), "_doc02"),
        (lambda: _doc03(revision_snapshot()), "_doc03"),
        (lambda: _doc06(revision_snapshot()), "_doc06"),
        (lambda: _doc07(revision_snapshot()), "_doc07"),
    ]
    for render, name in renders:
        text = _visible_text(render())
        leaked = re.findall(r"[0-9a-fA-F]{10,}", text)
        assert not leaked, f"{render.__name__}: {leaked[:3]}"
        assert not re.search(r"\d+\.\d{4}", text)
        assert not re.search(r"\d+[\.,]\d{2,}\s?%", text)


def test_bar_csv_uses_canonical_machine_decimals() -> None:
    """El CSV de sierra es contrato de máquina: punto decimal y precisión
    plana — el formato §3.3 (espacio fino, coma) es solo para humanos."""
    optimization = _cutpack_optimization()
    csv = service._cnc_bars_csv(optimization, cut_map={})
    assert "1000.00" in csv
    assert "1\u2009000" not in csv
    assert "45.00" in csv
