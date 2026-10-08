"""P13 — pack de corte imprimible: presupuesto de páginas a escala
(1/12/100 posiciones), sin colisión de texto, cierre exacto por barra,
DXF UTF-8 parseable con ezdxf, y consistencia de etiquetas entre artefactos.
"""

from __future__ import annotations

import io
import math
import re
from decimal import Decimal

import fitz  # PyMuPDF — pinned test dependency (requirements-dev.txt)
import pytest

from documents.renderers import (
    _bar_assignments,
    _cut_member_map,
    _cut_key,
    _infill_code_map,
    _infill_key,
    _piece_labels,
    _sheet_assignments,
)
from production import service
from production.cut_pack import _pack_html
from production.dxf import dxf_files


def _scaled_fixture(n_positions: int) -> tuple[dict, dict]:
    """n posiciones × 1 unidad: 2 perfiles 45/45 + 1 refuerzo 90/90 +
    1 vidrio 800×600 por posición. Barras balanceadas al mm exacto."""
    positions = [
        {"id": f"pos-{i}", "position_index": i} for i in range(1, n_positions + 1)
    ]
    manufacturing = []
    member_cuts: list[dict] = []
    reinf_cuts: list[dict] = []
    placements: list[dict] = []
    for i in range(1, n_positions + 1):
        pos = f"pos-{i}"
        mid1 = f"{i:02x}" + "a" * 62
        mid2 = f"{i:02x}" + "b" * 62
        rid = f"{i:02x}" + "c" * 62
        iid = f"{i:02x}" + "d" * 62
        manufacturing.append(
            {
                "position_id": pos,
                "position_index": i,
                "repetition_index": 1,
                "nominal_width_mm": "1000.00",
                "nominal_height_mm": "1000.00",
                "members": [
                    {
                        "member_id": mid, "bay_id": "B1",
                        "workshop_sku": "MARCO-60",
                        "cut_length_mm": "1000.00",
                        "angle_left": "45.00", "angle_right": "45.00",
                        "identity": {"role": "FRAME", "position_id": pos},
                    }
                    for mid in (mid1, mid2)
                ],
                "reinforcements": [
                    {
                        "reinforcement_id": rid,
                        "parent_member_id": mid2,
                        "workshop_sku": "ACERO",
                        "cut_length_mm": "940.00",
                        "angle_left": "90.00", "angle_right": "90.00",
                    }
                ],
                "infills": [
                    {
                        "infill_id": iid,
                        "position_id": pos,
                        "bay_id": "B1",
                        "leaf_id": "L1",
                        "rect": {"width_mm": "800.00", "height_mm": "600.00"},
                        "composition": "DVH 4-9-4",
                    }
                ],
                "leaves": [], "handles": [], "relationships": [],
            }
        )
        member_cuts.extend(
            {
                "piece_id": f"spec-{pos}-m{j}",
                "source_kind": "PROFILE", "workshop_sku": "MARCO-60",
                "length_mm": "1000.00",
                "angle_left": "45.00", "angle_right": "45.00",
                "role": "FRAME", "bay_id": "B1", "leaf_id": "",
                "source_position_id": pos, "unit_index": 1,
            }
            for j in range(2)
        )
        reinf_cuts.append(
            {
                "piece_id": f"spec-{pos}-r",
                "source_kind": "REINFORCEMENT", "workshop_sku": "ACERO",
                "length_mm": "940.00",
                "angle_left": "90.00", "angle_right": "90.00",
                "role": "FRAME", "bay_id": "B1", "leaf_id": "",
                "source_position_id": pos, "unit_index": 1,
            }
        )
        placements.append(
            {
                "piece_id": f"spec-{pos}-i",
                "width_mm": "800", "height_mm": "600",
                "rotated": False, "unit_index": 1,
                "bay_id": "B1", "leaf_id": "L1",
                "source_position_id": pos,
            }
        )
    bars = []
    seq = 0
    for group_start in range(0, len(member_cuts), 6):
        chunk = member_cuts[group_start : group_start + 6]
        for cut in chunk:
            seq += 1
            cut["sequence"] = seq
        pieces = Decimal(1000 * len(chunk))
        kerf_total = Decimal(5 * len(chunk))
        stock = Decimal("6500.00")
        remainder = stock - pieces - kerf_total - Decimal("30")
        bars.append(
            {
                "bar_index": len(bars) + 1, "commercial_sku": "COMPRA-MARCO",
                "material": "PVC", "color": "WHITE", "source": "NEW",
                "stock_authority_id": "auth-perfil",
                "stock_length_mm": str(stock), "head_trim_mm": "15.00",
                "tail_trim_mm": "15.00", "kerf_mm": "5.00",
                "kerf_total_mm": str(kerf_total),
                "remainder_mm": str(remainder),
                "remainder_reusable": True,
                "yield_pct": "92.0",
                "cuts": chunk,
            }
        )
    for group_start in range(0, len(reinf_cuts), 2):
        chunk = reinf_cuts[group_start : group_start + 2]
        for cut in chunk:
            seq += 1
            cut["sequence"] = seq
        pieces = Decimal(940 * len(chunk))
        kerf_total = Decimal(5 * len(chunk))
        stock = Decimal("2000.00")
        remainder = stock - pieces - kerf_total - Decimal("30")
        bars.append(
            {
                "bar_index": len(bars) + 1, "commercial_sku": "COMPRA-ACERO",
                "material": "STEEL", "color": "WHITE", "source": "NEW",
                "stock_authority_id": "auth-acero",
                "stock_length_mm": str(stock), "head_trim_mm": "15.00",
                "tail_trim_mm": "15.00", "kerf_mm": "5.00",
                "kerf_total_mm": str(kerf_total),
                "remainder_mm": str(remainder),
                "remainder_reusable": remainder >= 300,
                "yield_pct": "94.0",
                "cuts": chunk,
            }
        )
    sheets = []
    for group_start in range(0, len(placements), 6):
        chunk = placements[group_start : group_start + 6]
        for index, piece in enumerate(chunk):
            piece["sequence"] = index + 1
            piece["x_mm"] = str(50 + (index % 3) * 900)
            piece["y_mm"] = str(40 + (index // 3) * 800)
        sheets.append(
            {
                "sheet_index": len(sheets) + 1,
                "purchasing_sku": "GLASS-4", "workshop_sku": "DVH-4-9-4",
                "sheet_width_mm": "3210", "sheet_height_mm": "2250",
                "yield_pct": "88.0", "placements": chunk,
                "produced_remnants": [
                    {
                        "x_mm": "2750", "y_mm": "40",
                        "width_mm": "410", "height_mm": "1600",
                    }
                ],
            }
        )
    optimization = {
        "color": "WHITE", "units": n_positions, "strategy": "FAST",
        "stats": {
            "bars_new": len(bars), "bars_remnant": 0,
            "cuts_total": seq, "unnested_count": 0,
        },
        "bars": {
            "metrics": {
                "bars": len(bars), "cuts": seq,
                "process_waste_mm": "0", "reusable_remnant_mm": "0",
                "productive_length_mm": "0",
            },
            "workshop_cut_plan": bars,
        },
        "sheets": sheets,
    }
    return {"positions": positions, "manufacturing": manufacturing}, optimization


def _pack_pdf(n_positions: int) -> fitz.Document:
    from weasyprint import HTML

    snapshot, optimization = _scaled_fixture(n_positions)
    labels = _piece_labels(snapshot)
    html = _pack_html(
        order={"order_code": "OT-SCALE"},
        optimization=optimization,
        snapshot=snapshot,
        labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={},
        remnant_racks={},
        fingerprint="f" * 64,
        payload={
            "routing": ["CUT", "MACHINING", "WELD", "CLEAN", "CRIMP",
                        "ASSEMBLE", "GLAZE", "QC", "PACK"],
            "process_authority": {"operation_station_map": {"MILL": "MACHINING"}},
        },
    )
    return fitz.open(
        stream=HTML(string=html).write_pdf(), filetype="pdf"
    )


def _intersect(a: tuple, b: tuple, eps: float = 0.4) -> bool:
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return ix > eps and iy > eps


SCALE_CASES = (1, 12, 100)


@pytest.mark.parametrize("n", SCALE_CASES)
def test_pack_renders_bounded_and_exact(n: int) -> None:
    """OTs de 1/12/100 posiciones: el pack crece acotado — la lista de corte
    no supera ceil(barras/2) páginas apaisadas y cada barra cierra exacto."""
    snapshot, optimization = _scaled_fixture(n)
    doc = _pack_pdf(n)
    n_bars = len(optimization["bars"]["workshop_cut_plan"])
    n_pieces = sum(
        len(b["cuts"]) for b in optimization["bars"]["workshop_cut_plan"]
    ) + sum(len(s["placements"]) for s in optimization["sheets"])
    try:
        # Cada barra imprime su línea de cierre exacta — ni una menos.
        all_text = "".join(page.get_text() for page in doc)
        flat = re.sub(r"\s+", " ", all_text)
        assert flat.count("cierra exacto") == n_bars
        assert "diferencia sin asignar" not in flat
        # Y cada una declara su origen — el fixture solo produce barras
        # nuevas; una barra de retazo imprimiría «retazo RT-…».
        assert flat.count("BARRA NUEVA") == n_bars
        # Presupuesto de páginas: barras ~2/página en apaisado + etiquetas
        # ~12 por plana + secciones fijas (agrupados, refuerzos, vidrios,
        # láminas, identidad).
        bound = math.ceil(n_bars / 2) + math.ceil(n_pieces / 12) + 12
        assert len(doc) <= bound, f"{len(doc)} páginas > {bound} para n={n}"
    finally:
        doc.close()


@pytest.mark.parametrize("n", SCALE_CASES)
def test_pack_no_text_overlap(n: int) -> None:
    """Ningún par de palabras se solapa — las etiquetas del diagrama y las
    tablas empaquetan con niveles, nunca colisionan."""
    doc = _pack_pdf(n)
    try:
        for index, page in enumerate(doc):
            words = page.get_text("words")
            for i in range(len(words)):
                for j in range(i + 1, len(words)):
                    assert not _intersect(words[i], words[j]), (
                        f"colisión pág. {index + 1} (n={n}): "
                        f"{words[i][4]!r} × {words[j][4]!r}"
                    )
    finally:
        doc.close()


def test_pack_body_text_at_least_8pt() -> None:
    """El texto de cuerpo del PDF impreso no baja de 8 pt (encargo P13)."""
    doc = _pack_pdf(1)
    try:
        for index, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        # Los textos SVG del diagrama/lámina escalan con el
                        # dibujo; la regla manda sobre el cuerpo (fuentes del
                        # documento, no del trazado vectorial).
                        if span["size"] < 7.9:
                            pytest.fail(
                                f"span {span['text']!r} a {span['size']}pt "
                                f"en página {index + 1}"
                            )
    finally:
        doc.close()


def test_labels_page_is_portrait_with_grid_or_roll() -> None:
    snapshot, optimization = _scaled_fixture(2)
    labels = _piece_labels(snapshot)
    html_grid = _pack_html(
        order={"order_code": "OT-1"}, optimization=optimization,
        snapshot=snapshot, labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={}, remnant_racks={}, fingerprint="f" * 64,
        label_format="GRID", label_paper="A4",
    )
    assert 'class="labels-grid"' in html_grid
    assert "@page piece-labels" in html_grid
    assert "a4 portrait" in html_grid
    html_roll = _pack_html(
        order={"order_code": "OT-1"}, optimization=optimization,
        snapshot=snapshot, labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={}, remnant_racks={}, fingerprint="f" * 64,
        label_format="THERMAL_100X50", label_paper="A4",
    )
    assert 'class="label-roll"' in html_roll
    assert "100mm 50mm" in html_roll


def test_grouped_view_lists_every_label() -> None:
    """La vista agrupada agrega cortes idénticos pero lista cada etiqueta —
    la trazabilidad no se pierde al agrupar."""
    snapshot, optimization = _scaled_fixture(3)
    labels = _piece_labels(snapshot)
    html = _pack_html(
        order={"order_code": "OT-1"}, optimization=optimization,
        snapshot=snapshot, labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={}, remnant_racks={}, fingerprint="f" * 64,
    )
    assert "Cortes agrupados" in html
    # 3 posiciones × 2 miembros idénticos → una fila con 6 etiquetas.
    section = html.split("Cortes agrupados", 1)[1]
    assert section.count("P01-U01-M0") + section.count("P02-U01-M0") + \
        section.count("P03-U01-M0") >= 6


def test_reinforcement_parent_and_glass_destination() -> None:
    snapshot, optimization = _scaled_fixture(1)
    labels = _piece_labels(snapshot)
    html = _pack_html(
        order={"order_code": "OT-1"}, optimization=optimization,
        snapshot=snapshot, labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={}, remnant_racks={}, fingerprint="f" * 64,
    )
    # Refuerzo muestra a su padre; el vidrio dice lámina de destino.
    assert "P01-U01-M02·R" in html
    assert "Lámina 1" in html


def test_unnested_explains_action() -> None:
    snapshot, optimization = _scaled_fixture(1)
    optimization["unnested"] = [
        {
            "kind": "GLASS", "group": "DVH",
            "width_mm": "1500", "height_mm": "900",
            "reason": "no_declared_sheet",
            "bay_id": "B1", "leaf_id": "L1", "piece_id": "spec-x",
        }
    ]
    labels = _piece_labels(snapshot)
    html = _pack_html(
        order={"order_code": "OT-1"}, optimization=optimization,
        snapshot=snapshot, labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={}, remnant_racks={}, fingerprint="f" * 64,
    )
    assert "Sin formato de lámina declarado en el catálogo" in html
    assert "Catálogo › Vidrios › Formatos" in html


def test_produced_remnant_folio_shared_between_bar_and_label() -> None:
    snapshot, optimization = _scaled_fixture(1)
    key = (
        "BAR", "auth-perfil",
        str(Decimal("6500.00") - Decimal(1000 * 2) - Decimal(10) - Decimal("30")),
    )
    labels = _piece_labels(snapshot)
    html = _pack_html(
        order={"order_code": "OT-1"}, optimization=optimization,
        snapshot=snapshot, labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={}, remnant_racks={}, fingerprint="f" * 64,
        produced_folios={key: ["RT-000099"]},
    )
    # La línea de la barra y la etiqueta de retazo imprimen el MISMO folio.
    assert html.count("RT-000099") == 2
    assert "RT-000099 · devolver a stock" in html
    # La barra de acero — sin retazo producido registrado — conserva la
    # línea genérica; solo el retazo ya emitido muestra folio real.
    assert "folio RT- al cerrar" in html


def test_dxf_is_utf8_ac1027_with_spanish_text() -> None:
    """ezdxf parsea el archivo y el texto en español viaja intacto —
    'Junquillo' con su tilde implícita y 'Ñ' de un SKU no se degradan."""
    ezdxf = pytest.importorskip("ezdxf")
    snapshot, optimization = _scaled_fixture(1)
    # Un SKU con Ñ y un corte de junquillo para forzar texto español.
    optimization["bars"]["workshop_cut_plan"][0]["commercial_sku"] = "MARCO-AÑO"
    optimization["bars"]["workshop_cut_plan"][0]["cuts"].append(
        {
            "sequence": 99, "piece_id": "spec-bead",
            "source_kind": "PROFILE", "workshop_sku": "JUNQ-15",
            "length_mm": "800.00",
            "angle_left": "45.00", "angle_right": "45.00",
            "role": "GLAZING_BEAD", "bay_id": "B1", "leaf_id": "L1",
            "source_position_id": "pos-1", "unit_index": 1,
        }
    )
    files = dxf_files(optimization)
    text = files["bars.dxf"]
    doc = ezdxf.read(io.StringIO(text))
    assert doc.dxfversion == "AC1027"
    texts = [
        e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"
    ]
    assert any("AÑO" in t for t in texts)
    assert any("800" in t and "45" in t for t in texts)
    # Sin mojibake ni '?': cada TEXT sale en UTF-8 limpio.
    assert not any("?" in t or "Â" in t for t in texts)


def test_same_codes_in_pdf_csv_dxf_and_labels() -> None:
    """La misma pieza lleva el mismo nombre en PDF, CSV, DXF y etiqueta."""
    snapshot, optimization = _scaled_fixture(4)
    labels = _piece_labels(snapshot)
    cut_map = _cut_member_map(snapshot, labels)
    infill_map = _infill_code_map(snapshot, labels)
    bars = optimization["bars"]["workshop_cut_plan"]
    sheets = optimization["sheets"]
    bar_codes = {
        key: code
        for key, (code, _e) in _bar_assignments(
            snapshot, labels, cut_map, bars
        ).items()
    }
    sheet_codes = {
        key: code
        for key, (code, _e) in _sheet_assignments(
            snapshot, labels, sheets
        ).items()
    }
    html = _pack_html(
        order={"order_code": "OT-1"}, optimization=optimization,
        snapshot=snapshot, labels=labels, cut_map=cut_map,
        infills=infill_map, bar_meta={}, remnant_racks={},
        fingerprint="f" * 64,
    )
    bars_csv = service._cnc_bars_csv(
        optimization, cut_map=cut_map, bar_codes=bar_codes
    )
    sheets_csv = service._cnc_sheets_csv(
        optimization, infill_map=infill_map, sheet_codes=sheet_codes
    )
    codes_fallback: dict[str, str] = {}
    for bar in bars:
        for cut in bar["cuts"]:
            code = cut_map.get(_cut_key(cut))
            if code:
                codes_fallback[str(cut["piece_id"])] = code
    for sheet in sheets:
        for placement in sheet["placements"]:
            codes_fallback[str(placement["piece_id"])] = infill_map.get(
                _infill_key(placement), str(placement["piece_id"])
            )
    files = dxf_files(
        optimization,
        codes=codes_fallback,
        bar_instance=bar_codes,
        sheet_instance=sheet_codes,
    )
    piece_re = re.compile(r"P\d+-U\d+-[MI]\d+(?:·R)?")
    pack_codes = set(piece_re.findall(html))
    csv_codes = set(piece_re.findall(bars_csv)) | set(
        piece_re.findall(sheets_csv)
    )
    dxf_codes = set()
    for content in files.values():
        dxf_codes |= set(piece_re.findall(content))
    # (bar_index, seq) y (sheet_index, seq) son espacios de clave distintos
    # — se unen por conjunto, nunca por dict-merge.
    label_codes = (
        {c for c in bar_codes.values() if c}
        | {c for c in sheet_codes.values() if c}
    )
    assert pack_codes == csv_codes == dxf_codes == label_codes
    assert len(pack_codes) == 4 * 4  # 4 posiciones × (2M + 1R + 1I)


def test_roll_mode_prints_one_label_per_100x50_page() -> None:
    from weasyprint import HTML

    snapshot, optimization = _scaled_fixture(2)
    labels = _piece_labels(snapshot)
    html = _pack_html(
        order={"order_code": "OT-P13-ROLL"},
        optimization=optimization,
        snapshot=snapshot,
        labels=labels,
        cut_map=_cut_member_map(snapshot, labels),
        infills=_infill_code_map(snapshot, labels),
        bar_meta={},
        remnant_racks={},
        fingerprint="a" * 64,
        produced_folios={},
        payload=None,
        label_format="THERMAL_100X50",
        label_paper="LETTER",
    )
    doc = fitz.open(stream=HTML(string=html).write_pdf(), filetype="pdf")
    roll = [
        p
        for p in doc
        if abs(p.rect.width - 283.46) < 1 and abs(p.rect.height - 141.73) < 1
    ]
    assert roll, "rollo térmico sin páginas 100×50"
    for page in roll:
        text = page.get_text()
        # Una etiqueta = un código; sin cajetín ni título ocupando la
        # etiqueta.
        assert "ORDEN DE TRABAJO" not in text
        assert "Etiquetas de pieza" not in text
        assert len(re.findall(r"P\d{2}-U\d{2}-(?:M|I)\d{2}", text)) <= 1
