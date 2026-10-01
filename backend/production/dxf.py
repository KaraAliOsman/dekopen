"""Minimal DXF (AC1015, millimetres) writer for machine handoff geometry.

No ezdxf dependency: the nesting layouts are axis-aligned rectangles plus
labels, so a deterministic hand-rolled writer keeps the export reproducible
and reviewable. Sheet files carry the sheet outline plus one closed
LWPOLYLINE per placed piece with a TEXT label; the bars file lays each
stock bar out as a horizontal strip with cut marks at cumulative positions.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

_BAR_ROW_HEIGHT = Decimal("80")
_BAR_GAP = Decimal("40")
_LABEL_HEIGHT = Decimal("18")
_SHEET_LABEL_HEIGHT = Decimal("60")


def _fmt(value: object) -> str:
    text = format(Decimal(str(value)).quantize(Decimal("0.001")), "f")
    return text[:-4] if text.endswith(".000") else text


def _pairs(*items: object) -> str:
    return "\n".join(str(item) for item in items) + "\n"


def _ascii(text: str) -> str:
    """AC1015 predates UTF-8 — labels go out ASCII-only so strict CAM
    importers never see mojibake (e.g. '·' arriving as 'Â·')."""
    return (
        text.replace("·", "-").replace("⟳", "(rot)")
        .encode("ascii", "replace").decode("ascii")
    )


def _lwpoly(layer: str, points: Iterable[tuple[Decimal, Decimal]]) -> str:
    pts = list(points)
    out = [
        "0", "LWPOLYLINE", "100", "AcDbEntity", "8", layer,
        "100", "AcDbPolyline", "90", str(len(pts)), "70", "1",
    ]
    for x, y in pts:
        out.extend(("10", _fmt(x), "20", _fmt(y)))
    return "\n".join(out) + "\n"


def _rect(layer: str, x: Decimal, y: Decimal, w: Decimal, h: Decimal) -> str:
    return _lwpoly(
        layer, [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    )


def _line(layer: str, x1: Decimal, y1: Decimal, x2: Decimal, y2: Decimal) -> str:
    return _pairs(
        "0", "LINE", "100", "AcDbEntity", "8", layer, "100", "AcDbLine",
        "10", _fmt(x1), "20", _fmt(y1), "30", "0",
        "11", _fmt(x2), "21", _fmt(y2), "31", "0",
    )


def _text(layer: str, x: Decimal, y: Decimal, height: Decimal, content: str) -> str:
    return _pairs(
        "0", "TEXT", "100", "AcDbEntity", "8", layer, "100", "AcDbText",
        "10", _fmt(x), "20", _fmt(y), "30", "0",
        "40", _fmt(height), "1", _ascii(content), "7", "STANDARD",
    )


def _dxf(entities: str, extmax_x: Decimal, extmax_y: Decimal) -> str:
    header = _pairs(
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1015",
        "9", "$INSUNITS", "70", "4",
        "9", "$EXTMIN", "10", "0", "20", "0", "30", "0",
        "9", "$EXTMAX", "10", _fmt(extmax_x), "20", _fmt(extmax_y), "30", "0",
        "0", "ENDSEC",
    )
    tables = _pairs(
        "0", "SECTION", "2", "TABLES",
        "0", "TABLE", "2", "LTYPE", "70", "1",
        "0", "LTYPE", "2", "CONTINUOUS", "70", "0", "3", "Solid line",
        "72", "65", "73", "0", "40", "0",
        "0", "ENDTAB",
        "0", "TABLE", "2", "LAYER", "70", "4",
        "0", "LAYER", "2", "OUTLINE", "70", "0", "62", "7", "6", "CONTINUOUS",
        "0", "LAYER", "2", "CUT", "70", "0", "62", "1", "6", "CONTINUOUS",
        "0", "LAYER", "2", "LABEL", "70", "0", "62", "3", "6", "CONTINUOUS",
        "0", "LAYER", "2", "MARK", "70", "0", "62", "5", "6", "CONTINUOUS",
        "0", "ENDTAB",
        "0", "TABLE", "2", "STYLE", "70", "1",
        "0", "STYLE", "2", "STANDARD", "70", "0", "40", "0", "41", "1",
        "50", "0", "71", "0", "42", "2.5", "3", "txt", "4", "",
        "0", "ENDTAB",
        "0", "ENDSEC",
    )
    return (
        header
        + tables
        + _pairs("0", "SECTION", "2", "ENTITIES")
        + entities
        + _pairs("0", "ENDSEC", "0", "EOF")
    )


def _placement_code(piece: dict, codes: dict[str, str] | None) -> str:
    """Printed piece identity: the member/infill code when the caller
    resolved one, else a short id — never the raw 64-hex hash wall."""
    piece_id = str(piece.get("piece_id") or "?")
    code = piece_id if len(piece_id) <= 12 else piece_id[:10]
    if codes:
        code = codes.get(str(piece.get("piece_id") or ""), code)
    if piece.get("unit_index") is not None:
        code += f"-U{piece['unit_index']}"
    return code


def _sheet_entities(
    sheet: dict, codes: dict[str, str] | None
) -> tuple[str, Decimal, Decimal]:
    width = Decimal(str(sheet.get("sheet_width_mm") or 0))
    height = Decimal(str(sheet.get("sheet_height_mm") or 0))
    entities = _rect("OUTLINE", Decimal(0), Decimal(0), width, height)
    for placement in sheet.get("placements") or []:
        x = Decimal(str(placement.get("x_mm") or 0))
        y = Decimal(str(placement.get("y_mm") or 0))
        w = Decimal(str(placement.get("width_mm") or 0))
        h = Decimal(str(placement.get("height_mm") or 0))
        entities += _rect("CUT", x, y, w, h)
        piece = _placement_code(placement, codes)
        entities += _text(
            "LABEL", x + _LABEL_HEIGHT, y + h / 2, _SHEET_LABEL_HEIGHT,
            f"{piece} {w}x{h}",
        )
    return entities, width, height


def _bars_entities(
    bars: list[dict], codes: dict[str, str] | None
) -> tuple[str, Decimal]:
    entities = ""
    max_x = Decimal(0)
    for index, bar in enumerate(
        sorted(bars, key=lambda b: int(b.get("bar_index") or 0))
    ):
        base_y = Decimal(index) * (_BAR_ROW_HEIGHT + _BAR_GAP)
        stock = Decimal(str(bar.get("stock_length_mm") or 0))
        entities += _rect("OUTLINE", Decimal(0), base_y, stock, _BAR_ROW_HEIGHT)
        entities += _text(
            "LABEL", Decimal(0), base_y - _LABEL_HEIGHT - Decimal(4),
            _LABEL_HEIGHT,
            f"{bar.get('commercial_sku') or ''} stock {stock}",
        )
        if stock > max_x:
            max_x = stock
        # Same consumption convention as optimize_cut: the head trim is
        # reserved once, then each piece takes its length plus one kerf.
        head = Decimal(str(bar.get("head_trim_mm") or 0))
        kerf = Decimal(str(bar.get("kerf_mm") or 0))
        cursor = head
        if head > 0:
            entities += _line("MARK", head, base_y, head, base_y + _BAR_ROW_HEIGHT)
        for cut in sorted(
            bar.get("cuts") or [], key=lambda c: int(c.get("sequence") or 0)
        ):
            length = Decimal(str(cut.get("length_mm") or 0))
            next_x = cursor + length
            entities += _line(
                "MARK", next_x, base_y, next_x, base_y + _BAR_ROW_HEIGHT
            )
            mid = cursor + length / 2
            angles = "/".join(
                str(a) for a in (cut.get("angle_left"), cut.get("angle_right")) if a
            )
            piece = _placement_code(cut, codes)
            label = f"{piece} {length}"
            if angles:
                label += f" {angles}"
            entities += _text(
                "LABEL", mid - _LABEL_HEIGHT, base_y + Decimal(10),
                _LABEL_HEIGHT, label,
            )
            cursor = next_x + kerf
    return entities, max_x


def dxf_files(
    optimization: dict, codes: dict[str, str] | None = None
) -> dict[str, str]:
    """Deterministic machine files: one ``sheet_<n>.dxf`` per nested sheet and
    a single ``bars.dxf`` when the bar plan exists. ``codes`` optionally
    maps piece_id → workshop piece code (M-xx/I-xx) so labels match the
    printed packs instead of carrying raw hash prefixes."""
    files: dict[str, str] = {}
    for sheet in sorted(
        optimization.get("sheets") or [], key=lambda s: int(s.get("sheet_index") or 0)
    ):
        entities, width, height = _sheet_entities(sheet, codes)
        files[f"sheet_{sheet.get('sheet_index')}.dxf"] = _dxf(entities, width, height)
    bars = (optimization.get("bars") or {}).get("workshop_cut_plan") or []
    if bars:
        entities, max_x = _bars_entities(bars, codes)
        row_count = len(bars)
        files["bars.dxf"] = _dxf(
            entities,
            max_x,
            Decimal(row_count) * (_BAR_ROW_HEIGHT + _BAR_GAP),
        )
    return files
