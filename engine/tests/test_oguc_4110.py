"""P18 — prueba de transcripción de las tablas OGUC 4.1.10.

El fixture JSON es una segunda entrada independiente del texto oficial
(Diario Oficial N° 43.860, 27-05-2024, CVE 2494861): cualquier desvío
entre el código y la doble entrada falla aquí. La corrección de la tabla
exige editar ambos lados — a propósito.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from dekopen_engine.oguc_4110 import (
    AIR_CLASS_MIN,
    EQUIPMENT_WINDOW_U_MAX,
    ORIENTATION_RANGES_DEG,
    ROOF_WINDOW_U_MAX,
    ROOF_WINDOW_ZONES,
    U_THRESHOLDS,
    WINDOW_MAX_PCT,
    orientation_group,
    u_threshold_index,
    window_max_pct,
)

FIXTURE = Path(__file__).parent / "fixtures" / "oguc_4110_tabla3.json"


def _fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def test_u_thresholds_match_official_columns() -> None:
    fixture = _fixture()
    assert [str(t) for t in U_THRESHOLDS] == fixture["u_thresholds"]


def test_tabla3_cell_by_cell() -> None:
    """Cada celda de la Tabla 3 del código iguala la doble entrada."""
    fixture = _fixture()["tabla3"]
    assert set(WINDOW_MAX_PCT) == set(fixture)
    for zone, orientations in fixture.items():
        assert set(WINDOW_MAX_PCT[zone]) == set(orientations)
        for orientation, row in orientations.items():
            assert tuple(row) == WINDOW_MAX_PCT[zone][orientation], (
                f"Tabla 3 {zone}/{orientation}"
            )


def test_tabla4_orientation_ranges() -> None:
    fixture = _fixture()["tabla4_degrees"]
    for orientation, (low, high) in fixture.items():
        assert ORIENTATION_RANGES_DEG[orientation] == (Decimal(low), Decimal(high))


def test_tabla9_16_air_class_minimums() -> None:
    fixture = _fixture()["tabla9_y_16_aire"]
    for zone, value in fixture.items():
        assert AIR_CLASS_MIN[zone] == value


def test_tabla12_equipment_u_max() -> None:
    fixture = _fixture()["tabla12_equipamiento_u_max"]
    for zone, value in fixture.items():
        assert EQUIPMENT_WINDOW_U_MAX[zone] == Decimal(value)


def test_roof_window_rule() -> None:
    fixture = _fixture()["techumbre"]
    assert ROOF_WINDOW_U_MAX == Decimal(fixture["u_max"])
    assert set(ROOF_WINDOW_ZONES) == set(fixture["zones"])


def test_orientation_group_boundaries() -> None:
    assert orientation_group(Decimal("0")) == "N"
    assert orientation_group(Decimal("44.9")) == "N"
    assert orientation_group(Decimal("45")) == "OP"
    assert orientation_group(Decimal("90")) == "OP"
    assert orientation_group(Decimal("134.9")) == "OP"
    assert orientation_group(Decimal("135")) == "S"
    assert orientation_group(Decimal("180")) == "S"
    assert orientation_group(Decimal("224.9")) == "S"
    assert orientation_group(Decimal("225")) == "OP"
    assert orientation_group(Decimal("270")) == "OP"
    assert orientation_group(Decimal("314.9")) == "OP"
    assert orientation_group(Decimal("315")) == "N"


def test_u_threshold_index() -> None:
    assert u_threshold_index(Decimal("0.6")) == 0
    assert u_threshold_index(Decimal("0.61")) == 1
    assert u_threshold_index(Decimal("1.40")) == 3
    assert u_threshold_index(Decimal("5.8")) == 11
    assert u_threshold_index(Decimal("5.81")) is None


def test_window_max_pct() -> None:
    assert window_max_pct("I", "N", Decimal("1.40")) == 67
    assert window_max_pct("I", "S", Decimal("1.40")) == 23
    assert window_max_pct("I", "S", Decimal("6.0")) is None
    assert window_max_pct("A", "OGT", Decimal("5.8")) == 25
