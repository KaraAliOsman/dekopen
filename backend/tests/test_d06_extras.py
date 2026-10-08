"""D06 extras & services: ingest writers, catalog visibility, hash eras.

Unit-level checks only — the live SQL/RLS behavior is the pgTAP file's
job (supabase/tests/database/177_d06_extras.test.sql under make test-db).
"""

from __future__ import annotations

import io
from uuid import uuid4

from openpyxl import Workbook

from ingest import catalog_service
from ingest.spreadsheet import parse_catalog_spreadsheet


def _workbook_with(sheet: str, rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    first = workbook.active
    first.title = sheet
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row, start=1):
            first.cell(row=r, column=c, value=value)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_extras_sheet_parses_declared_columns() -> None:
    content = _workbook_with(
        "Extras",
        [
            ["sku", "nombre", "tipo", "unidad", "precio", "moneda", "costo",
             "moneda_costo", "perfil_corte", "material_corte", "vuelo_mm",
             "familias", "tipos_unidad", "motivo"],
            ["EXT-VIERT-60", "Vierteaguas", "SILL", "M", "11000", "CLP",
             "5500", "CLP", "VIERT-ALU-60", "ALUMINIUM", "30",
             "CASEMENT", "WINDOW", "Alféizar expuesto"],
        ],
    )
    candidates, errors = parse_catalog_spreadsheet("XLSX", content)
    assert errors == []
    assert len(candidates) == 1
    row = candidates[0]
    assert row["entity"] == "EXTRA_ARTICLE"
    assert row["fields"]["kind"] == "SILL"
    assert row["fields"]["families"] == ["CASEMENT"]
    assert row["fields"]["suggestion_reason"] == "Alféizar expuesto"


def test_services_sheet_parses_qty_rule() -> None:
    content = _workbook_with(
        "Servicios",
        [
            ["codigo", "nombre", "tipo", "regla", "precio", "moneda",
             "costo", "moneda_costo"],
            ["INST-ML", "Instalación por metro lineal", "INSTALLATION",
             "PER_LINEAR_METER", "4500", "CLP", "2800", "CLP"],
        ],
    )
    candidates, errors = parse_catalog_spreadsheet("XLSX", content)
    assert errors == []
    row = candidates[0]
    assert row["entity"] == "SERVICE_ARTICLE"
    assert row["fields"]["qty_rule"] == "PER_LINEAR_METER"


def test_extra_row_error_flags_bad_kind() -> None:
    content = _workbook_with(
        "Extras",
        [
            ["sku", "nombre", "tipo", "unidad", "precio", "moneda", "costo",
             "moneda_costo", "perfil_corte", "material_corte", "vuelo_mm",
             "familias", "tipos_unidad", "motivo"],
            ["X-1", "Roto", "NO_EXISTE", "M", "1", "CLP", "", "", "", "",
             "", "", "", ""],
        ],
    )
    candidates, errors = parse_catalog_spreadsheet("XLSX", content)
    assert errors == []
    assert candidates[0]["confidence"] == "ERROR"


def test_insert_extra_row_writes_system_and_arrays(monkeypatch) -> None:
    inserted: list[tuple[str, list]] = []

    def _rows(sql, params=None):
        inserted.append((sql, params))
        return [{"id": uuid4()}]

    monkeypatch.setattr(catalog_service, "rows", _rows)
    org_id, system_id = uuid4(), uuid4()
    out = catalog_service._insert_entity_row(
        org_id=org_id,
        system_id=system_id,
        entity="EXTRA_ARTICLE",
        fields={
            "sku": "ext-viert-60",
            "name": "Vierteaguas",
            "kind": "SILL",
            "pricing_unit": "M",
            "unit_price": "11000",
            "unit_price_currency": "CLP",
            "cut_profile_sku": "viert-alu-60",
            "cut_material": "ALUMINIUM",
            "vuelo_default_mm": "30",
            "families": ["CASEMENT"],
            "unit_kinds": ["WINDOW"],
        },
    )
    assert out is not None
    sql, params = inserted[0]
    assert "INSERT INTO public.extra_articles" in sql
    assert "system_id" in sql
    # SKU and cut profile normalize to catalog uppercase.
    assert params[2] == "EXT-VIERT-60"
    assert params[10] == "VIERT-ALU-60"
    # TEXT[] predicates travel as lists — psycopg adapts them to the
    # column type; a ::jsonb cast would break at the boundary.
    assert params[13] == ["CASEMENT"]
    assert params[14] == ["WINDOW"]


def test_insert_service_row_is_unscoped(monkeypatch) -> None:
    inserted: list[tuple[str, list]] = []

    def _rows(sql, params=None):
        inserted.append((sql, params))
        return [{"id": uuid4()}]

    monkeypatch.setattr(catalog_service, "rows", _rows)
    out = catalog_service._insert_entity_row(
        org_id=uuid4(),
        system_id=uuid4(),
        entity="SERVICE_ARTICLE",
        fields={
            "code": "inst-ml",
            "name": "Instalación",
            "kind": "INSTALLATION",
            "qty_rule": "PER_LINEAR_METER",
            "unit_price": "4500",
            "unit_price_currency": "CLP",
        },
    )
    assert out is not None
    sql, params = inserted[0]
    assert "INSERT INTO public.service_articles" in sql
    # Org data — a service is never bound to the importing system.
    assert "system_id" not in sql
    assert params[1] == "INST-ML"
    assert params[3] == "INSTALLATION"
    assert params[4] == "PER_LINEAR_METER"


def test_service_visibility_never_references_a_system() -> None:
    from catalogs.service import visibility_sql

    unscoped = visibility_sql(child=False, unscoped=True)
    assert "profile_systems" not in unscoped
    assert "is_global" not in unscoped
    assert unscoped == "(org_id = %s OR org_id IS NULL)"


def test_era_d06_projection_drops_extra_lines_and_origin() -> None:
    from documents.service import _drop_bom_keys

    current = {
        "profile_cuts": [{"sku": "MARCO-60", "origin": "PRODUCT"}],
        "reinforcements": [],
        "glasses": [],
        "panels": [],
        "fittings": [{"sku": "EXT-MOSQ", "kind": "MOSQUITO_SCREEN",
                      "qty": 1, "origin": "EXTRA"}],
        "hardware_items": [],
        "leaf_weights": [],
        "extra_lines": [{"sku": "EXT-VIERT-60", "total_price": "17160.00"}],
    }
    era = _drop_bom_keys(
        current,
        frozenset({"extra_lines"}),
        {
            "profile_cuts": frozenset({"origin"}),
            "fittings": frozenset({"origin"}),
        },
    )
    assert "extra_lines" not in era
    assert "origin" not in era["profile_cuts"][0]
    assert "origin" not in era["fittings"][0]


def test_identity_hashes_chain_covers_eight_eras() -> None:
    """The additive-key preimage chain must keep positions sealed before
    D06 freezeable — count is the contract (D05's finish era chains in
    front of D06's)."""
    from documents.service import _calculation_identity_hashes
    from dekopen_engine.models import EngineResult

    result = EngineResult(
        profile_cuts=[],
        reinforcements=[],
        glasses=[],
        panels=[],
        fittings=[],
        hardware_items=[],
        leaf_weights=[],
        extra_lines=[],
    )
    hashes = _calculation_identity_hashes({}, result)
    assert len(hashes) == 8


def test_extra_serializer_declares_sides_choices() -> None:
    from projects.extras_api import ExtraTemplateWriteSerializer

    serializer = ExtraTemplateWriteSerializer(data={
        "extra_article_id": str(uuid4()),
        "sides": ["top", "left"],
    })
    assert serializer.is_valid(), serializer.errors
    bad = ExtraTemplateWriteSerializer(data={
        "extra_article_id": str(uuid4()),
        "sides": ["diagonal"],
    })
    assert not bad.is_valid()
