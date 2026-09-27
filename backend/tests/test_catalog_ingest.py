"""Catalog ingestion: article parser, service contract, confirm lifecycle."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from django.db import DatabaseError

from ingest import catalog_service
from ingest.catalog_parser import parse_article_line, parse_catalog_lines
from ingest.serializers import CatalogImportConfirmSerializer


def test_parse_article_line_full_match():
    candidate = parse_article_line(
        "MRC-100 Marco oscilobatiente 78 mm 1.45 kg/m refuerzo AC-55", "r0"
    )
    assert candidate is not None
    assert candidate["sku"] == "MRC-100"
    assert candidate["role"] == "FRAME"
    assert candidate["face_width_mm"] == Decimal("78")
    assert candidate["confidence"] == "HIGH_CANDIDATE"
    assert candidate["weight_kg_m"] == Decimal("1.45")
    assert candidate["reinforcement_sku"] == "AC-55"


def test_parse_article_line_sash_and_mullion_roles():
    assert parse_article_line("HJA-20 hoja ventana 65mm", "r0")["role"] == "SASH"
    assert parse_article_line("MON-30 montante vertical 40mm", "r0")["role"] == "MULLION_V"
    assert parse_article_line("TRV-40 travesaño horizontal 40mm", "r0")["role"] == "MULLION_H"
    assert parse_article_line("CVD-50 contravidrio 25mm", "r0")["role"] == "GLAZING_BEAD"


def test_parse_article_line_missing_fields_flags_review():
    candidate = parse_article_line("XYZ-9", "r0")
    assert candidate is not None
    assert candidate["confidence"] == "REVIEW_REQUIRED"
    assert "catalog_name_missing" in candidate["warnings"]
    assert "catalog_role_unknown" in candidate["warnings"]
    assert "catalog_face_width_missing" in candidate["warnings"]


def test_parse_article_line_rejects_unusable_sku():
    assert parse_article_line("catalogo general perfiles", "r0") is None
    assert parse_article_line("", "r0") is None


def test_parse_article_line_face_width_bounds():
    assert parse_article_line("ABC-1 marco 400 mm", "r0")["confidence"] == "REVIEW_REQUIRED"
    candidate = parse_article_line("ABC-1 marco 45 mm", "r0")
    assert candidate["face_width_mm"] == Decimal("45")


def test_parse_article_line_ambiguous_measurements_resolve_none():
    # §D: "Marco 70 × 58 mm" never proves face_width=70 — two plausible
    # measurements leave the field empty and degrade the candidate.
    candidate = parse_article_line("MRC-70 Marco 70 × 58 mm", "r0")
    assert candidate is not None
    assert candidate["face_width_mm"] is None
    assert candidate["confidence"] == "LOW"
    assert "catalog_face_width_ambiguous" in candidate["warnings"]
    assert candidate["evidence"]["fields"]["face_width_mm"]["original"] == ["70 × 58 mm"]
    assert candidate["evidence"]["fields"]["face_width_mm"]["normalized"] is None


def test_parse_article_line_equal_pair_dims_still_resolve():
    # "45 × 45 mm" is two measurements of the same value — unambiguous, the
    # candidate keeps it with the pair token as evidence.
    candidate = parse_article_line("MRC-45 Marco 45 x 45 mm", "r0")
    assert candidate["face_width_mm"] == Decimal("45")
    assert "catalog_face_width_ambiguous" not in candidate["warnings"]


def test_parse_article_line_evidence_records_what_the_parser_saw():
    candidate = parse_article_line(
        "MRC-100 Marco oscilobatiente 78 mm 1.45 kg/m refuerzo AC-55", "r0", "fila 9"
    )
    evidence = candidate["evidence"]
    assert evidence["parser_version"].startswith("catalog-parser/")
    assert evidence["source"]["ref"] == "fila 9"
    assert "Marco oscilobatiente" in evidence["source"]["text"]
    assert evidence["fields"]["face_width_mm"] == {
        "normalized": Decimal("78"),
        "original": "78 mm",
        "unit": "mm",
        "source": "measurement_token",
    }
    assert evidence["fields"]["role"]["original"] == "marco"
    assert evidence["fields"]["weight_kg_m"]["unit"] == "kg/m"
    assert evidence["fields"]["reinforcement_sku"]["normalized"] == "AC-55"


def test_parse_article_line_prose_never_exceeds_high_candidate():
    # VERIFIED_STRUCTURED is reserved for explicit structured-table imports —
    # a heuristic prose line can at most be an unconfirmed candidate.
    candidate = parse_article_line("MRC-1 Marco 75 mm", "r0")
    assert candidate["confidence"] == "HIGH_CANDIDATE"
    assert candidate["confidence"] != "VERIFIED_STRUCTURED"


def test_parse_catalog_lines_dedupes_sku():
    lines = ["MRC-1 marco 50mm", "MRC-1 marco 50mm", "HJA-2 hoja 60mm"]
    candidates = parse_catalog_lines(lines)
    assert [c["sku"] for c in candidates] == ["MRC-1", "HJA-2"]
    assert [c["key"] for c in candidates] == ["c0", "c2"]


def _backend():
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


def _import_row(**overrides):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "system_id": None,
        "file_name": "aluprof.pdf",
        "kind": "PDF",
        "storage_path": "catalog-imports/o/i/aluprof.pdf",
        "status": "REVIEW_READY",
        "candidates": [
            {
                "key": "c0",
                "sku": "MRC-100",
                "name": "Marco oscilobatiente",
                "role": "FRAME",
                "face_width_mm": "78",
                "commercial_length_mm": "6000",
                "welding_loss_mm": "6",
                "reinforcement_sku": "AC-55",
                "weight_kg_m": "1.45",
                "steel_weight_kg_m": "1.7",
                "confidence": "HIGH_CANDIDATE",
                "warnings": [],
            }
        ],
        "warnings": [],
        "result": [],
        "error_code": None,
        "audit_id": None,
        "created_by": uuid4(),
        "created_at": "2026-09-23T00:00:00Z",
        "updated_at": "2026-09-23T00:00:00Z",
    }
    row.update(overrides)
    return row


def _item(**overrides):
    item = {
        "key": "c0",
        "sku": "MRC-100",
        "name": "Marco oscilobatiente",
        "role": "FRAME",
        "face_width_mm": "78",
        "commercial_length_mm": "6000",
        "welding_loss_mm": "6",
        "reinforcement_sku": "AC-55",
        "weight_kg_m": "1.45",
        "steel_weight_kg_m": "1.7",
    }
    item.update(overrides)
    return item


def _confirm_patches(monkeypatch, row, system_found=True, insert_return=True):
    article_id = uuid4()
    updates = []
    inserts = []

    def _rows(sql, params=None):
        if "FROM public.catalog_imports" in sql:
            return [row]
        if "FROM public.profile_systems" in sql:
            return [{"id": params[0], "material": "ALUMINIUM"}] if system_found else []
        if "INSERT INTO public.profile_articles" in sql:
            inserts.append(params)
            return [{"id": article_id}] if insert_return else []
        if "UPDATE public.catalog_imports" in sql:
            updates.append(params)
            return [row]
        return []

    monkeypatch.setattr(catalog_service, "rows", _rows)
    monkeypatch.setattr(catalog_service, "documentary_backend", _backend)
    return updates, inserts, article_id


def test_confirm_inserts_articles_and_seals(monkeypatch):
    row = _import_row()
    system_id = uuid4()
    updates, inserts, article_id = _confirm_patches(monkeypatch, row)
    out = catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=system_id,
        items=[_item()],
    )
    assert out["created"] == [{"key": "c0", "article_id": str(article_id)}]
    assert out["errors"] == []
    # Org-scoped insert: org_id written on the article row.
    assert inserts[0][1] == str(row["org_id"])
    # Decimal string passed as text — engine purity preserved.
    assert inserts[0][6] == "78"
    # The article inherits the owned system's material, never the PVC default.
    assert inserts[0][5] == "ALUMINIUM"
    # CONFIRMED is inline in the seal SQL; params carry result, system, import.
    assert updates[0][1] == str(system_id)


def test_confirm_rejects_shared_system(monkeypatch):
    row = _import_row()
    _confirm_patches(monkeypatch, row, system_found=False)
    with pytest.raises(APIException) as failure:
        catalog_service.confirm_catalog_import(
            org_id=row["org_id"],
            import_id=row["id"],
            system_id=uuid4(),
            items=[_item()],
        )
    assert failure.value.contract_code == "catalog_system_not_tenant"


def test_confirm_sku_conflict_surfaces_per_key(monkeypatch):
    row = _import_row()
    _confirm_patches(monkeypatch, row, insert_return=False)
    out = catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=uuid4(),
        items=[_item()],
    )
    assert out["errors"] == [{"key": "c0", "code": "catalog_sku_conflict"}]
    assert out["created"] == []


def test_confirm_rejects_unknown_key(monkeypatch):
    row = _import_row()
    _confirm_patches(monkeypatch, row)
    out = catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=uuid4(),
        items=[_item(key="nope")],
    )
    assert out["errors"] == [{"key": "nope", "code": "catalog_item_unknown"}]


def test_confirm_replays_confirmed_import(monkeypatch):
    result = [{"key": "c0", "article_id": str(uuid4())}]
    row = _import_row(status="CONFIRMED", result=result)
    monkeypatch.setattr(catalog_service, "rows", lambda sql, params=None: [row])
    monkeypatch.setattr(catalog_service, "documentary_backend", _backend)
    out = catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=uuid4(),
        items=[_item()],
    )
    assert out["created"] == result
    assert out["errors"] == []


def test_confirm_missing_fabrication_fields_stay_unknown(monkeypatch):
    """A supplier document that never stated fabrication data must not gain
    invented values — NULL is written so consumers refuse or flag honestly."""
    row = _import_row()
    _, inserts, _ = _confirm_patches(monkeypatch, row)
    item = _item(
        commercial_length_mm=None,
        welding_loss_mm=None,
        weight_kg_m=None,
        steel_weight_kg_m=None,
        reinforcement_sku=None,
    )
    catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=uuid4(),
        items=[item],
    )
    assert inserts[0][7] is None
    assert inserts[0][8] is None
    assert inserts[0][10] is None
    assert inserts[0][11] is None


def test_parse_article_line_threshold_role():
    assert parse_article_line("UMB-10 umbral 30mm", "r0")["role"] == "THRESHOLD"
    assert parse_article_line("THR-30 threshold 45mm", "r1")["role"] == "THRESHOLD"


def test_confirm_serializer_rejects_duplicate_keys():
    serializer = CatalogImportConfirmSerializer(
        data={
            "system_id": str(uuid4()),
            "items": [_item(), _item()],
        }
    )
    assert not serializer.is_valid()


def _failing_insert(monkeypatch, row, error):
    updates = []

    def _rows(sql, params=None):
        if "FROM public.catalog_imports" in sql:
            return [row]
        if "FROM public.profile_systems" in sql:
            return [{"id": params[0], "material": "PVC"}]
        if "INSERT INTO public.profile_articles" in sql:
            raise error
        if "UPDATE public.catalog_imports" in sql:
            updates.append(params)
            return [row]
        return []

    monkeypatch.setattr(catalog_service, "rows", _rows)
    monkeypatch.setattr(catalog_service, "documentary_backend", _backend)
    return updates


def test_confirm_singleton_role_conflict_is_per_key(monkeypatch):
    row = _import_row()
    updates = _failing_insert(
        monkeypatch,
        row,
        DatabaseError("catalog_singleton_role_conflict: FRAME already exists"),
    )
    out = catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=uuid4(),
        items=[_item()],
    )
    assert out["errors"] == [{"key": "c0", "code": "catalog_singleton_role_conflict"}]
    assert out["created"] == []
    # Retryable: the import stays REVIEW_READY — no FAILED seal.
    assert updates[0][0].startswith("[")


def test_confirm_insert_failure_is_per_key(monkeypatch):
    row = _import_row()
    _failing_insert(monkeypatch, row, DatabaseError("constraint exploded"))
    out = catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=uuid4(),
        items=[_item()],
    )
    assert out["errors"] == [{"key": "c0", "code": "catalog_insert_failed"}]


def test_confirm_failed_import_is_reconfirmable(monkeypatch):
    row = _import_row(status="FAILED")
    updates, inserts, article_id = _confirm_patches(monkeypatch, row)
    out = catalog_service.confirm_catalog_import(
        org_id=row["org_id"],
        import_id=row["id"],
        system_id=uuid4(),
        items=[_item()],
    )
    assert out["created"] == [{"key": "c0", "article_id": str(article_id)}]
    assert updates[0][1] != "FAILED"


def test_mark_failed_only_updates_inflight(monkeypatch):
    statements = []

    def _rows(sql, params=None):
        statements.append((sql, params))
        return []

    monkeypatch.setattr(catalog_service, "rows", _rows)

    def _write(sql, params=None):
        statements.append((sql, params))
        return 1

    monkeypatch.setattr(catalog_service, "write", _write)
    monkeypatch.setattr(catalog_service, "documentary_backend", _backend)
    catalog_service.mark_catalog_import_failed(org_id=uuid4(), import_id=uuid4(), code="x" * 200)
    sql, params = statements[0]
    assert "UPLOADED" in sql and "EXTRACTING" in sql
    assert len(params[0]) == 80


def test_parse_article_line_name_strips_measurements():
    candidate = parse_article_line("ABC-1 Marco 78 mm", "r0")
    assert candidate["name"] == "Marco"
    candidate = parse_article_line(
        "MRC-100 Marco oscilobatiente 78 mm 1.45 kg/m refuerzo AC-55", "r1"
    )
    assert candidate["name"] == "Marco oscilobatiente"
    candidate = parse_article_line("MON-2 Montante 1.10 kg/m", "r2")
    assert candidate["name"] == "Montante"


def test_confirm_retry_rejects_other_system(monkeypatch):
    system_a = uuid4()
    row = _import_row(
        system_id=system_a,
        result=[{"key": "c0", "article_id": str(uuid4())}],
    )
    monkeypatch.setattr(catalog_service, "rows", lambda sql, params=None: [row])
    monkeypatch.setattr(catalog_service, "documentary_backend", _backend)
    with pytest.raises(APIException) as failure:
        catalog_service.confirm_catalog_import(
            org_id=row["org_id"],
            import_id=row["id"],
            system_id=uuid4(),
            items=[_item(key="c1")],
        )
    assert failure.value.contract_code == "catalog_system_changed"


def test_source_refs_ride_onto_candidates():
    candidates = parse_catalog_lines(
        [
            ("MRC-100 Marco 78 mm", "página 2"),
            ("HJA-200 Hoja 65 mm", "fila 14"),
        ]
    )
    assert candidates[0]["source_ref"] == "página 2"
    assert candidates[1]["source_ref"] == "fila 14"


def test_reconcile_flags_existing_sku_conflicts(monkeypatch):
    candidates = [
        {"sku": "MRC-100", "role": "FRAME", "face_width_mm": "80", "warnings": []},
        {"sku": "NEW-9", "role": "SASH", "face_width_mm": "60", "warnings": []},
    ]
    monkeypatch.setattr(
        catalog_service,
        "rows",
        lambda *a, **k: [
            {
                "sku": "MRC-100",
                "name": "Marco",
                "role": "FRAME",
                "face_width_mm": "78",
                "system_code": "ALU-60",
            }
        ],
    )
    catalog_service._reconcile(uuid4(), candidates)
    assert candidates[0]["conflict"] is True
    assert "catalog_conflicts_existing" in candidates[0]["warnings"]
    assert candidates[0]["existing"][0]["face_width_mm"] == "78"
    assert candidates[0]["existing"][0]["system_code"] == "ALU-60"
    assert "existing" not in candidates[1]


def test_reconcile_identical_article_is_not_a_conflict(monkeypatch):
    candidates = [
        {"sku": "MRC-100", "role": "FRAME", "face_width_mm": "78", "warnings": []}
    ]
    monkeypatch.setattr(
        catalog_service,
        "rows",
        lambda *a, **k: [
            {
                "sku": "MRC-100",
                "name": "Marco",
                "role": "FRAME",
                "face_width_mm": "78",
                "system_code": "ALU-60",
            }
        ],
    )
    catalog_service._reconcile(uuid4(), candidates)
    assert "conflict" not in candidates[0]
    assert candidates[0]["existing"][0]["role"] == "FRAME"


def test_series_gaps_names_the_missing_roles():
    assert catalog_service._series_gaps([{"role": "FRAME"}]) == (
        "SASH,MULLION_V,MULLION_H,GLAZING_BEAD"
    )
    assert (
        catalog_service._series_gaps(
            [
                {"role": "FRAME"},
                {"role": "SASH"},
                {"role": "MULLION_V"},
                {"role": "MULLION_H"},
                {"role": "GLAZING_BEAD"},
            ]
        )
        is None
    )
    assert catalog_service._series_gaps([]) is None


def test_create_catalog_import_rejects_path_like_filenames():
    # The multipart filename lands verbatim in the storage key — separators or
    # traversal would write the object outside catalog-imports/{org}/.
    for bad_name in (
        "../escape.pdf",
        "a/b.csv",
        "a\\b.pdf",
        "lista\t.pdf",
        "a%2Fb.csv",
    ):
        with pytest.raises(APIException) as caught:
            catalog_service.create_catalog_import(
                org_id=uuid4(),
                actor_id=uuid4(),
                file_name=bad_name,
                content=b"x",
                content_type="text/csv",
            )
        assert (
            getattr(caught.value, "contract_code", None)
            == "catalog_import_file_invalid"
        )
