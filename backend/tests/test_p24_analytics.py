"""P24 — envoltura de analítica: período, agregado de secciones y CSV.

Las funciones SQL se ejercen en el gate pgTAP (187_p24_analitica.test.sql);
aquí se cubre lo que es puro Python: defaults del período, rechazo de rangos
inválidos, unión de columnas del CSV y el nombre del archivo."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from analytics import decision


class _Query(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def test_period_default_last_30_days() -> None:
    desde, hasta = decision.period_from(_Query())
    assert hasta == date.today()
    assert desde == hasta - timedelta(days=30)


def test_period_explicit_range() -> None:
    desde, hasta = decision.period_from(_Query(desde="2027-09-01", hasta="2027-09-30"))
    assert (desde, hasta) == (date(2027, 9, 1), date(2027, 9, 30))


def test_period_rejects_inverted_range() -> None:
    with pytest.raises(APIException) as error:
        decision.period_from(_Query(desde="2027-09-30", hasta="2027-09-01"))
    assert error.value.status_code == 400


def test_period_rejects_bad_format() -> None:
    with pytest.raises(APIException) as error:
        decision.period_from(_Query(desde="01-09-2027"))
    assert error.value.status_code == 400


def test_overview_returns_schema_period_and_four_sections() -> None:
    calls: list[str] = []

    def fake_rows(sql: str, params: list):
        calls.append(sql)
        return [{"v": {"metrics": {}}}]

    with patch("analytics.decision.rows", side_effect=fake_rows):
        out = decision.overview(uuid4(), date(2027, 9, 1), date(2027, 9, 30))
    assert out["schema"] == "dekopen.analytics.overview.v1"
    assert out["period"] == {"desde": "2027-09-01", "hasta": "2027-09-30"}
    assert set(out["definitions"]) >= {"conversion_pct", "real_margin_pct", "merma_real_mm"}
    assert {"sales", "margins", "production", "field"} <= set(out)
    assert len(calls) == 4


def test_export_csv_unions_columns_and_names_file() -> None:
    items = [
        {"code": "P-1", "net": 100, "extra": {"a": 1}},
        {"code": "P-2", "net": 200, "other": "x"},
    ]
    with patch("analytics.decision.rows", return_value=[{"v": items}]):
        filename, content = decision.export_csv(
            uuid4(), "quotes", date(2027, 9, 1), date(2027, 9, 30)
        )
    assert filename == "dekopen-analitica-quotes-2027-09-01-a-2027-09-30.csv"
    lines = content.strip().splitlines()
    assert lines[0] == "code,net,extra,other"
    assert '"{""a"": 1}"' in lines[1]
    assert len(lines) == 3


def test_export_csv_rejects_unknown_metric() -> None:
    with pytest.raises(APIException) as error:
        decision.export_csv(uuid4(), "naves", date(2027, 9, 1), date(2027, 9, 30))
    assert error.value.status_code == 400


def test_export_csv_empty_still_has_headers() -> None:
    with patch("analytics.decision.rows", return_value=[{"v": []}]):
        _, content = decision.export_csv(
            uuid4(), "ots", date(2027, 9, 1), date(2027, 9, 30)
        )
    assert content.strip() == ""
