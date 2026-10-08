"""D07 golden cases — del vano de obra a la medida de fabricación.

Each mounting type freezes its exact vano→fabrication math. The values here
are the contract the UI desglose ("Vano 1520 - holgura 10 + 10 = 1500")
and the sealed revision evidence must reproduce byte-for-byte.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine import (
    FabricationLock,
    VanoError,
    VanoInput,
    mounting_rule_from_json,
    resolve_fabrication,
    vano_from_json,
)

MM = Decimal

# The authority bodies mirror the seeded mounting_rules rows; the golden
# cases pin the engine math so a rule edit never changes them silently.
EN_VANO = {
    "code": "EN_VANO",
    "label": "En vano con holgura perimetral",
    "sides": {
        "top": {"mm": "-10.00", "label": "Holgura superior"},
        "right": {"mm": "-10.00", "label": "Holgura derecha"},
        "bottom": {"mm": "-10.00", "label": "Holgura inferior"},
        "left": {"mm": "-10.00", "label": "Holgura izquierda"},
    },
    "fixings": [{"label": "Anclaje perimetral", "qty_per_unit": "8", "note": "Según muro"}],
}

PREMARCO = {
    "code": "PREMARCO",
    "label": "Con premarco",
    "sides": {
        "top": {"mm": "-40.00", "label": "Holgura y premarco superior"},
        "right": {"mm": "-40.00", "label": "Holgura y premarco derecho"},
        "bottom": {"mm": "-40.00", "label": "Holgura y premarco inferior"},
        "left": {"mm": "-40.00", "label": "Holgura y premarco izquierdo"},
    },
}

SOBRE_VANO = {
    "code": "SOBRE_VANO",
    "label": "Sobre vano",
    "sides": {
        "top": {"mm": "20.00", "label": "Solape superior"},
        "right": {"mm": "20.00", "label": "Solape derecho"},
        "bottom": {"mm": "0.00", "label": "Ajuste inferior"},
        "left": {"mm": "20.00", "label": "Solape izquierdo"},
    },
}

TRASLAPADO = {
    "code": "TRASLAPADO",
    "label": "Traslapado",
    "sides": {
        "top": {"mm": "20.00", "label": "Solape superior"},
        "right": {"mm": "20.00", "label": "Solape derecho"},
        "bottom": {"mm": "20.00", "label": "Solape inferior"},
        "left": {"mm": "20.00", "label": "Solape izquierdo"},
    },
}

RENOVACION = {
    "code": "RENOVACION",
    "label": "Renovación sobre marco existente",
    "sides": {
        "top": {"mm": "-5.00", "label": "Holgura superior"},
        "right": {"mm": "-5.00", "label": "Holgura derecha"},
        "bottom": {"mm": "-5.00", "label": "Holgura inferior"},
        "left": {"mm": "-5.00", "label": "Holgura izquierda"},
    },
}


def _vano(width: list[str], height: list[str], **kwargs: object) -> VanoInput:
    return vano_from_json({
        "width_points_mm": width,
        "height_points_mm": height,
        **kwargs,
    })


def test_gold_en_vano_perimeter_clearance() -> None:
    # The canonical desglose: Vano 1520 − holgura 10 + 10 = 1500.
    rule = mounting_rule_from_json(EN_VANO)
    vano = _vano(["1520.00"], ["1220.00"], wall_type="MASONRY")
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1500.00"), position_height_mm=MM("1200.00"),
    )
    assert resolution.fabrication_width_mm == MM("1500.00")
    assert resolution.fabrication_height_mm == MM("1200.00")
    assert resolution.fabrication_source == "DERIVED"
    assert resolution.coherent is True
    assert [item.mm for item in resolution.breakdown] == [
        MM("-10.00"), MM("-10.00"), MM("-10.00"), MM("-10.00")
    ]
    assert resolution.warnings == ()


def test_gold_premarco_deducts_frame_and_clearance() -> None:
    rule = mounting_rule_from_json(PREMARCO)
    vano = _vano(["1640.00"], ["1220.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1560.00"), position_height_mm=MM("1140.00"),
    )
    assert resolution.fabrication_width_mm == MM("1560.00")
    assert resolution.fabrication_height_mm == MM("1140.00")
    assert resolution.coherent is True
    assert [item.mm for item in resolution.breakdown] == [
        MM("-40.00"), MM("-40.00"), MM("-40.00"), MM("-40.00")
    ]


def test_gold_sobre_vano_adds_overlap() -> None:
    # sobre vano: el marco tapa el vano — el producto crece por el solape,
    # sin deducción inferior (apoya sobre el antepecho).
    rule = mounting_rule_from_json(SOBRE_VANO)
    vano = _vano(["1200.00"], ["1100.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1240.00"), position_height_mm=MM("1120.00"),
    )
    assert resolution.fabrication_width_mm == MM("1240.00")
    assert resolution.fabrication_height_mm == MM("1120.00")
    assert resolution.coherent is True
    # bottom 0.00 does not enter the desglose.
    assert [(item.side, item.mm) for item in resolution.breakdown] == [
        ("top", MM("20.00")), ("right", MM("20.00")), ("left", MM("20.00"))
    ]


def test_gold_traslapado_full_overlap() -> None:
    rule = mounting_rule_from_json(TRASLAPADO)
    vano = _vano(["1500.00"], ["1200.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1540.00"), position_height_mm=MM("1240.00"),
    )
    assert resolution.fabrication_width_mm == MM("1540.00")
    assert resolution.fabrication_height_mm == MM("1240.00")
    assert resolution.coherent is True


def test_gold_renovacion_existing_frame() -> None:
    # renovación: el "vano" medido es la luz del marco existente; holgura menor.
    rule = mounting_rule_from_json(RENOVACION)
    vano = _vano(["1180.00"], ["1175.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1170.00"), position_height_mm=MM("1165.00"),
    )
    assert resolution.fabrication_width_mm == MM("1170.00")
    assert resolution.fabrication_height_mm == MM("1165.00")
    assert resolution.coherent is True
    assert [item.mm for item in resolution.breakdown] == [
        MM("-5.00"), MM("-5.00"), MM("-5.00"), MM("-5.00")
    ]


def test_gold_three_point_uses_minimum() -> None:
    # 3 puntos por eje: la menor manda; el desfase ≤ tolerancia no avisa.
    rule = mounting_rule_from_json(EN_VANO)
    vano = _vano(["1520.00", "1518.00", "1522.00"], ["1220.00", "1216.00", "1219.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1498.00"), position_height_mm=MM("1196.00"),
    )
    assert resolution.vano_width_mm == MM("1518.00")
    assert resolution.vano_height_mm == MM("1216.00")
    assert resolution.width_spread_mm == MM("4.00")
    assert resolution.height_spread_mm == MM("4.00")
    assert resolution.fabrication_width_mm == MM("1498.00")
    assert resolution.fabrication_height_mm == MM("1196.00")
    assert resolution.coherent is True
    assert resolution.warnings == ()


def test_gold_three_point_spread_over_tolerance_warns() -> None:
    rule = mounting_rule_from_json(EN_VANO)
    vano = _vano(["1520.00", "1506.00", "1532.00"], ["1220.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1486.00"), position_height_mm=MM("1200.00"),
        spread_tolerance_mm=MM("10.00"),
    )
    assert resolution.vano_width_mm == MM("1506.00")
    assert resolution.width_spread_mm == MM("26.00")
    codes = [warning.code for warning in resolution.warnings]
    assert "VANO_WIDTH_SPREAD" in codes


def test_gold_manual_lock_coherent() -> None:
    # Fijación manual dentro de tolerancia: la fijación es la medida.
    rule = mounting_rule_from_json(EN_VANO)
    vano = _vano(["1520.00"], ["1220.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        lock=FabricationLock(width_mm=MM("1498.00"), height_mm=MM("1200.00")),
        position_width_mm=MM("1498.00"), position_height_mm=MM("1200.00"),
    )
    assert resolution.fabrication_width_mm == MM("1498.00")
    assert resolution.fabrication_source == "MANUAL_LOCK"
    assert resolution.coherent is True
    assert resolution.warnings == ()


def test_gold_manual_lock_incoherent_warns() -> None:
    # Fijación 40 mm bajo lo derivado: se registra y avisa.
    rule = mounting_rule_from_json(EN_VANO)
    vano = _vano(["1520.00"], ["1220.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        lock=FabricationLock(width_mm=MM("1460.00"), height_mm=MM("1200.00")),
        position_width_mm=MM("1460.00"), position_height_mm=MM("1200.00"),
    )
    assert resolution.fabrication_width_mm == MM("1460.00")
    assert resolution.fabrication_source == "MANUAL_LOCK"
    assert resolution.coherent is False
    codes = [warning.code for warning in resolution.warnings]
    assert "FAB_LOCK_DIVERGES" in codes
    assert "FAB_USED_DIVERGES" not in codes


def test_gold_used_diverges_from_derived_warns() -> None:
    # El producto se está fabricando a 1520 pero el vano da 1500.
    rule = mounting_rule_from_json(EN_VANO)
    vano = _vano(["1520.00"], ["1220.00"])
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1520.00"), position_height_mm=MM("1200.00"),
    )
    assert resolution.fabrication_width_mm == MM("1500.00")
    assert resolution.coherent is False
    codes = [warning.code for warning in resolution.warnings]
    assert "FAB_USED_DIVERGES" in codes


def test_gold_declared_no_vano() -> None:
    # Sin registro de vano: la medida del producto es la declarada.
    resolution = resolve_fabrication(
        vano=None, rule=None,
        position_width_mm=MM("1500.00"), position_height_mm=MM("1200.00"),
    )
    assert resolution.fabrication_source == "DECLARED"
    assert resolution.fabrication_width_mm == MM("1500.00")
    assert resolution.vano_width_mm is None
    assert resolution.coherent is True


def test_gold_vano_requires_rule() -> None:
    vano = _vano(["1520.00"], ["1220.00"])
    with pytest.raises(VanoError, match="vano_without_mounting_rule"):
        resolve_fabrication(
            vano=vano, rule=None,
            position_width_mm=MM("1500.00"), position_height_mm=MM("1200.00"),
        )


def test_gold_lock_without_vano() -> None:
    resolution = resolve_fabrication(
        vano=None, rule=None,
        lock=FabricationLock(width_mm=MM("1490.00"), height_mm=MM("1190.00")),
        position_width_mm=MM("1490.00"), position_height_mm=MM("1190.00"),
    )
    assert resolution.fabrication_source == "MANUAL_LOCK"
    assert resolution.fabrication_width_mm == MM("1490.00")
    assert resolution.coherent is True


def test_gold_wall_note_advisory() -> None:
    rule_body = dict(EN_VANO)
    rule_body["wall_notes"] = {"PARTITION": "Tabique liviano: verifica anclaje con el instalador."}
    rule = mounting_rule_from_json(rule_body)
    vano = _vano(["1520.00"], ["1220.00"], wall_type="PARTITION")
    resolution = resolve_fabrication(
        vano=vano, rule=rule,
        position_width_mm=MM("1500.00"), position_height_mm=MM("1200.00"),
    )
    codes = [warning.code for warning in resolution.warnings]
    assert "WALL_NOTE" in codes
    assert resolution.coherent is True
