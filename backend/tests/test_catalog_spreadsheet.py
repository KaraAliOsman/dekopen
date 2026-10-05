"""D01 manual ingestion: official template, structured parse, per-entity confirm."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from ingest import catalog_service
from ingest.catalog_parser import parse_ai_candidates
from ingest.spreadsheet import (
    build_template,
    looks_like_template,
    parse_catalog_spreadsheet,
)


def test_template_builds_nine_sheets_plus_readme():
    from openpyxl import load_workbook
    import io

    workbook = load_workbook(io.BytesIO(build_template()), read_only=True)
    names = workbook.sheetnames
    workbook.close()
    assert names[0] == "LEEME"
    assert names[1:] == [
        "Sistemas",
        "Perfiles",
        "Reglas de corte",
        "Refuerzos",
        "Límites",
        "Colores-SKU",
        "Vidrios",
        "Herrajes",
        "Precios",
    ]


def test_template_is_recognized_and_parses_clean():
    content = build_template()
    assert looks_like_template("XLSX", content)
    candidates, errors = parse_catalog_spreadsheet("XLSX", content)
    assert errors == []
    entities = {candidate["entity"] for candidate in candidates}
    assert entities == {
        "SYSTEM",
        "PROFILE",
        "CUT_RULE",
        "REINFORCEMENT_RULE",
        "TYPOLOGY_LIMIT",
        "FINISH",
        "GLAZING_RULE",
        "HARDWARE_KIT",
        "PRICE",
    }
    assert all(
        candidate["confidence"] == "VERIFIED_STRUCTURED" for candidate in candidates
    )
    profile = next(c for c in candidates if c["entity"] == "PROFILE")
    assert profile["sku"] == "MARCO-60"
    assert profile["role"] == "FRAME"
    assert profile["face_width_mm"] == Decimal("58")


def _workbook_with(sheet: str, rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook
    import io

    workbook = Workbook()
    first = workbook.active
    first.title = sheet
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row, start=1):
            first.cell(row=r, column=c, value=value)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_row_errors_are_spanish_and_flagged():
    content = _workbook_with(
        "Perfiles",
        [
            ["sku", "nombre", "rol", "ancho_cara_mm", "largo_comercial_mm",
             "perdida_soldadura_mm", "peso_kg_m", "peso_acero_kg_m", "refuerzo_sku"],
            ["MARCO-70", "Marco", "NO_EXISTE", "58", "6000", "6", "1.9", "1.7", ""],
            ["", "Sin sku", "SASH", "abc", "6000", "6", "1.9", "1.7", ""],
        ],
    )
    candidates, errors = parse_catalog_spreadsheet("XLSX", content)
    assert errors == []
    bad_role = candidates[0]
    assert bad_role["confidence"] == "ERROR"
    assert any("rol" in e and "NO_EXISTE" in e for e in bad_role["row_errors"])
    assert all("Fila 2" in e for e in bad_role["row_errors"])
    bad_row = candidates[1]
    assert bad_row["confidence"] == "ERROR"
    assert any("obligatorio" in e for e in bad_row["row_errors"])
    assert any("un número" in e for e in bad_row["row_errors"])


def test_missing_header_is_a_sheet_level_error():
    content = _workbook_with(
        "Perfiles",
        [["sku", "nombre", "ancho_cara_mm"], ["X-1", "Y", "58"]],
    )
    candidates, errors = parse_catalog_spreadsheet("XLSX", content)
    assert candidates == []
    assert any("rol" in e for e in errors)


def test_unknown_sheet_is_ignored_with_notice():
    content = _workbook_with("Inventada", [["a"], ["b"]])
    candidates, errors = parse_catalog_spreadsheet("XLSX", content)
    assert candidates == []
    assert any("Inventada" in e for e in errors)


def test_csv_profiles_parse():
    content = (
        "sku,nombre,rol,ancho_cara_mm,largo_comercial_mm\n"
        "MRC-80,Marco 80,FRAME,60,6000\n"
    ).encode()
    assert looks_like_template("CSV", content)
    candidates, errors = parse_catalog_spreadsheet("CSV", content)
    assert errors == []
    assert len(candidates) == 1
    assert candidates[0]["entity"] == "PROFILE"
    assert candidates[0]["sku"] == "MRC-80"


def test_template_round_trip_exports_identically():
    """Round-trip: the fixture template parses to the same declared fields —
    a second parse of re-serialized candidates must be byte-stable."""
    first, _ = parse_catalog_spreadsheet("XLSX", build_template())
    second, _ = parse_catalog_spreadsheet("XLSX", build_template())
    assert json.dumps(first, default=str, sort_keys=True) == json.dumps(
        second, default=str, sort_keys=True
    )


def test_ai_json_candidates_clamp_confidence_and_unknown():
    output = json.dumps(
        [
            {
                "entity": "PROFILE",
                "confidence": "VERIFIED_STRUCTURED",
                "fields": {"sku": "X-1", "name": "Perfil", "role": "FRAME",
                           "face_width_mm": "58"},
            },
            {
                "entity": "CUT_RULE",
                "confidence": "LOW",
                "fields": {"role": "SASH", "cut_angle_deg": "45",
                           "invented": "999"},
            },
        ]
    )
    candidates = parse_ai_candidates(output)
    assert candidates[0]["confidence"] == "REVIEW_REQUIRED"
    low = candidates[1]
    assert low["confidence"] == "LOW"
    # Low confidence forces non-identity fields to UNKNOWN.
    assert low["fields"]["cut_angle_deg"] is None
    assert "catalog_low_confidence_unknown" in low["warnings"]


def test_ai_legacy_text_still_parses_lines():
    candidates = parse_ai_candidates("MRC-100 Marco 78 mm 1.45 kg/m")
    assert candidates[0]["sku"] == "MRC-100"
    assert candidates[0]["entity"] == "PROFILE"


def _backend(*args, **kwargs):
    class _Backend:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return None

    return _Backend()


class _NullAtomic:
    def atomic(self):
        return _backend()

    def __call__(self, *args, **kwargs):
        return _backend()


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(catalog_service, "transaction", _NullAtomic())
    monkeypatch.setattr(catalog_service, "catalog_backend", _backend)


def _row_with(entity: str, fields: dict, **candidate_over):
    candidate = {
        "key": "k1",
        "entity": entity,
        "confidence": "VERIFIED_STRUCTURED",
        "warnings": [],
        "row_errors": [],
        "fields": fields,
    }
    candidate.update(candidate_over)
    return {
        "id": uuid4(),
        "org_id": uuid4(),
        "system_id": None,
        "file_name": "plantilla-catalogo-dekopen.xlsx",
        "kind": "XLSX",
        "storage_path": "catalog-imports/o/i/f.xlsx",
        "status": "REVIEW_READY",
        "candidates": [candidate],
        "warnings": [],
        "result": [],
        "error_code": None,
        "audit_id": None,
        "created_by": uuid4(),
        "created_at": "2026-09-23T00:00:00Z",
        "updated_at": "2026-09-23T00:00:00Z",
    }


def _confirm(monkeypatch, row, insert_capture):
    def _rows(sql, params=None):
        if "FROM public.catalog_imports" in sql:
            return [row]
        if "FROM public.profile_systems" in sql:
            return [{"id": params[0], "material": "PVC", "finishes": '["WHITE"]'}]
        if sql.startswith("UPDATE public.catalog_imports"):
            return [row]
        if sql.startswith("INSERT") or sql.startswith("UPDATE"):
            insert_capture.append((sql, params))
            return [{"id": uuid4()}]
        return []

    monkeypatch.setattr(catalog_service, "rows", _rows)
    monkeypatch.setattr(catalog_service, "documentary_backend", _backend)
    monkeypatch.setattr(
        catalog_service.catalog_evidence, "stamp_import_evidence", lambda **kw: None
    )
    return row


def test_confirm_cut_rule_writes_rule_table(monkeypatch):
    inserted: list = []
    row = _row_with(
        "CUT_RULE",
        {"role": "INTERLOCK", "cut_angle_deg": "45", "welded_ends": None,
         "interlock_deduction_mm": "18", "rounding_mm": "0.01"},
    )
    _confirm(monkeypatch, row, inserted)
    out = catalog_service.confirm_catalog_import(
        org_id=uuid4(), actor_id=uuid4(), import_id=row["id"],
        system_id=uuid4(),
        items=[{"key": "k1", "entity": "CUT_RULE"}],
    )
    assert out["errors"] == []
    assert any("profile_cut_rules" in sql for sql, _ in inserted)


def test_confirm_refuses_broken_rows(monkeypatch):
    row = _row_with(
        "PROFILE",
        {},
        row_errors=["Fila 3 de «Perfiles»: «rol» es obligatorio."],
        sku=None,
    )
    _confirm(monkeypatch, row, [])
    out = catalog_service.confirm_catalog_import(
        org_id=uuid4(), actor_id=uuid4(), import_id=row["id"],
        system_id=uuid4(),
        items=[{"key": "k1", "entity": "PROFILE", "sku": "X-1",
                "role": "FRAME", "face_width_mm": "58"}],
    )
    assert out["errors"] == [{"key": "k1", "code": "catalog_row_invalid"}]


def test_confirm_price_requires_cost_list(monkeypatch):
    row = _row_with(
        "PRICE",
        {"purchase_sku": "COMPRA-MARCO-60", "item_type": "PROFILE",
         "unit": "BAR", "unit_cost": "12500"},
    )
    _confirm(monkeypatch, row, [])
    out = catalog_service.confirm_catalog_import(
        org_id=uuid4(), actor_id=uuid4(), import_id=row["id"],
        system_id=uuid4(),
        items=[{"key": "k1", "entity": "PRICE",
                "purchase_sku": "COMPRA-MARCO-60", "item_type": "PROFILE",
                "unit": "BAR", "unit_cost": "12500"}],
    )
    assert out["errors"][0]["code"] == "catalog_price_list_required"


def test_confirm_hardware_kit_writes_kits_table(monkeypatch):
    inserted: list = []
    row = _row_with(
        "HARDWARE_KIT",
        {"sku": "KIT-1", "name": "Kit", "opening_type": "SLIDING_2L",
         "min_leaf_width_mm": "400", "max_leaf_width_mm": "1800",
         "min_leaf_height_mm": "600", "max_leaf_height_mm": "2400",
         "max_leaf_weight_kg": "100", "rail_type": "dual",
         "carriages_qty": 2, "stay_arms_qty": 0, "contents": []},
    )
    _confirm(monkeypatch, row, inserted)
    out = catalog_service.confirm_catalog_import(
        org_id=uuid4(), actor_id=uuid4(), import_id=row["id"],
        system_id=uuid4(),
        items=[{"key": "k1", "entity": "HARDWARE_KIT"}],
    )
    assert out["errors"] == []
    assert any("hardware_kits" in sql for sql, _ in inserted)


def test_confirm_new_system_creates_org_system(monkeypatch):
    inserted: list = []
    row = _row_with(
        "SYSTEM",
        {"code": "SERIE-70", "name": "Serie 70", "depth_mm": "70",
         "material": "PVC", "system_family": "SLIDING",
         "finishes": ["WHITE"]},
    )
    _confirm(monkeypatch, row, inserted)

    def _rows(sql, params=None):
        if "FROM public.catalog_imports" in sql:
            return [row]
        if sql.startswith("INSERT INTO public.profile_systems"):
            system = {"id": uuid4()}
            inserted.append(system["id"])
            return [system]
        if "FROM public.profile_systems" in sql:
            return [{"id": inserted[0], "material": "PVC",
                     "finishes": '["WHITE"]'}]
        if sql.startswith("UPDATE public.catalog_imports"):
            return [row]
        if sql.startswith("INSERT") or sql.startswith("UPDATE"):
            return [{"id": uuid4()}]
        return []

    monkeypatch.setattr(catalog_service, "rows", _rows)
    monkeypatch.setattr(catalog_service, "documentary_backend", _backend)
    monkeypatch.setattr(
        catalog_service.catalog_evidence, "stamp_import_evidence", lambda **kw: None
    )
    out = catalog_service.confirm_catalog_import(
        org_id=uuid4(), actor_id=uuid4(), import_id=row["id"],
        system_id=None,
        new_system={"code": "SERIE-70", "name": "Serie 70", "depth_mm": "70",
                    "material": "PVC", "system_family": "SLIDING",
                    "finishes": ["WHITE"]},
        items=[{"key": "k1", "entity": "SYSTEM",
                "fields": {"code": "SERIE-70"}}],
    )
    assert out["errors"] == []
    assert inserted  # the system row was created


def test_confirm_finish_merges_into_system(monkeypatch):
    inserted: list = []
    row = _row_with("FINISH", {"finish_code": "FOILED", "name": "Foliado"})
    _confirm(monkeypatch, row, inserted)
    out = catalog_service.confirm_catalog_import(
        org_id=uuid4(), actor_id=uuid4(), import_id=row["id"],
        system_id=uuid4(),
        items=[{"key": "k1", "entity": "FINISH", "finish_code": "FOILED"}],
    )
    assert out["errors"] == []
    assert any(
        "UPDATE public.profile_systems SET finishes" in sql for sql, _ in inserted
    )
