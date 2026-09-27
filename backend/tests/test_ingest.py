"""Document ingestion: parser, service contract, and extraction job paths."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from authentication.errors import contract_error
from ingest import service
from ingest.extract import kind_for
from ingest.parser import (
    candidates_from_text,
    normalize_opening,
    parse_line,
)


def test_parse_line_finds_label_dimensions_and_opening():
    candidate = parse_line("V-01 oscilobatiente 1200x1000 2 un")
    assert candidate is not None
    assert candidate["label"] == "V-01"
    assert candidate["width_mm"] == "1200"
    assert candidate["height_mm"] == "1000"
    assert candidate["quantity"] == 2
    assert candidate["opening_type"] == "TILT_TURN_LEFT"
    assert candidate["confidence"] == "HIGH"
    assert candidate["warnings"] == []


def test_parse_line_requires_dimensions():
    assert parse_line("ventana sin medidas") is None
    assert parse_line("fijo 0x1000") is None


def test_parse_line_missing_hint_flags_review():
    candidate = parse_line("1500x1200")
    assert candidate is not None
    assert candidate["confidence"] == "REVIEW_REQUIRED"
    assert "import.candidate_no_label" in candidate["warnings"]
    assert "import.candidate_no_opening" in candidate["warnings"]


def test_parse_line_label_digits_do_not_inflate_quantity():
    candidate = parse_line("V-10 fijo 1200x1000")
    assert candidate is not None
    assert candidate["label"] == "V-10"
    assert candidate["quantity"] == 1
    candidate = parse_line("V-10 fijo 1200x1000 3 unidades")
    assert candidate["quantity"] == 3


def test_parse_line_dimension_first_row_keeps_quantity_one():
    # A leading dimension is width, not a count — only a count placed before
    # the dimension may promote into a quantity.
    for line in ("800 x 600 V-1 fijo", "800 × 600 V-1 fijo", "800x600 V-1 fijo"):
        candidate = parse_line(line)
        assert candidate is not None
        assert candidate["quantity"] == 1, line
        assert candidate["width_mm"] == "800"
    assert parse_line("3 V-1 fijo 1200x1000")["quantity"] == 3


def test_candidates_from_text_keys_rows():
    candidates = candidates_from_text("A-1 fijo 1000x1000\nA-2 corredera 1500x1200")
    assert [c["key"] for c in candidates] == ["r0", "r1"]
    assert candidates[1]["opening_type"] == "SLIDING_2L"


def test_normalize_opening_whitelists():
    assert normalize_opening("FIXED") == "FIXED"
    assert normalize_opening("banana") is None
    assert normalize_opening(None) is None


def test_kind_for_extensions():
    assert kind_for("plano.PDF") == "PDF"
    assert kind_for("lista.xlsx") == "XLSX"
    assert kind_for("foto.webp") == "IMAGE"
    assert kind_for("nota.txt") is None


def _import_row(**overrides):
    row = {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "file_name": "lista.pdf",
        "kind": "PDF",
        "storage_path": "imports/o/p/i/lista.pdf",
        "status": "REVIEW_READY",
        "candidates": [
            {
                "key": "r0",
                "label": "V-01",
                "width_mm": "1200",
                "height_mm": "1000",
                "quantity": 1,
                "opening_type": "TILT_TURN_LEFT",
                "confidence": "HIGH",
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
        "key": "r0",
        "label": "V-01",
        "width_mm": "1200.00",
        "height_mm": "1000.00",
        "quantity": 1,
        "opening_type": "TILT_TURN_LEFT",
        "system_id": str(uuid4()),
        "color": "WHITE",
        "glass_thickness_mm": "20.00",
        "glass_spec": "4-12-4",
        "glass_article_sku": "GLASS-A",
    }
    item.update(overrides)
    return item


def _glass_map(spec="4-12-4"):
    return [{"technical_sku": "GLASS-A", "glass_spec": spec}]


def test_confirm_creates_positions_and_stores_result(monkeypatch):
    row = _import_row()
    saved = []
    updates = []

    monkeypatch.setattr(service.projects_service, "project_row", lambda *a, **k: {"id": "p"})
    monkeypatch.setattr(service, "rows", lambda sql, params=None: [])
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda org, proj, data: saved.append(data) or {"id": uuid4()},
    )

    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: (
            updates.append(sql) or [row | {"status": "CONFIRMED", "result": []}]
            if "UPDATE public.document_imports" in sql
            else [row]
            if "FROM public.document_imports" in sql
            else _glass_map()
            if "FROM public.glass_purchase_mappings" in sql
            else []
        ),
    )
    out = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item()],
    )
    assert len(out["created"]) == 1
    assert saved[0]["design"]["parametric_tree"]["opening_type"] == "TILT_TURN_LEFT"
    # The engine's Decimal-purity contract: JSON ints must become Decimal here.
    assert saved[0]["design"]["nominal_width_mm"] == Decimal("1200.00")
    assert any("SET status='CONFIRMED'" in sql for sql in updates)


def test_confirm_replays_confirmed_import(monkeypatch):
    result = [{"key": "r0", "position_id": str(uuid4())}]
    row = _import_row(status="CONFIRMED", result=result)
    monkeypatch.setattr(service, "rows", lambda sql, params=None: [row])
    monkeypatch.setattr(service, "documentary_backend", _backend)
    out = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item()],
    )
    assert out["created"] == result
    assert out["errors"] == []


def test_confirm_refuses_in_flight_import(monkeypatch):
    row = _import_row(status="EXTRACTING")
    monkeypatch.setattr(service, "rows", lambda sql, params=None: [row])
    monkeypatch.setattr(service, "documentary_backend", _backend)
    with pytest.raises(APIException) as failure:
        service.confirm_import(
            org_id=row["org_id"],
            project_id=row["project_id"],
            import_id=row["id"],
            items=[_item()],
        )
    assert failure.value.contract_code == "import_not_review_ready"


def test_confirm_collects_item_errors_without_blocking(monkeypatch):
    row = _import_row()
    monkeypatch.setattr(service.projects_service, "project_row", lambda *a, **k: {"id": "p"})

    def _rows(sql, params=None):
        if "UPDATE public.document_imports" in sql:
            return [row | {"result": params[0]}]
        if "FROM public.document_imports" in sql:
            return [row]
        if "FROM public.glass_purchase_mappings" in sql:
            return _glass_map()
        return []

    monkeypatch.setattr(service, "rows", _rows)
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda *a: (_ for _ in ()).throw(Exception("boom")),
    )
    out = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item(key="r0"), _item(key="ghost")],
    )
    assert out["created"] == []
    assert {e["key"] for e in out["errors"]} == {"r0", "ghost"}
    assert out["errors"][1]["code"] == "import_item_unknown"


def test_confirm_partial_failure_stays_retryable_then_seals(monkeypatch):
    row = _import_row(
        candidates=[
            {"key": "r0", "label": "V-01", "width_mm": "1200", "height_mm": "1000",
             "quantity": 1, "opening_type": "FIXED", "confidence": "HIGH", "warnings": []},
            {"key": "r1", "label": "V-02", "width_mm": "800", "height_mm": "600",
             "quantity": 1, "opening_type": "FIXED", "confidence": "HIGH", "warnings": []},
        ]
    )
    stored = {"result": []}

    def _rows(sql, params=None):
        if "UPDATE public.document_imports" in sql:
            stored["result"] = params[0]
            if "SET status='CONFIRMED'" in sql:
                return [row | {"status": "CONFIRMED", "result": params[0]}]
            return [row | {"result": params[0]}]
        if "FROM public.document_imports" in sql:
            return [row | {"result": stored["result"]}]
        if "FROM public.glass_purchase_mappings" in sql:
            return _glass_map()
        return []

    monkeypatch.setattr(service, "rows", _rows)
    monkeypatch.setattr(service, "documentary_backend", _backend)
    calls = []

    def _save(org, proj, data):
        calls.append(data["location_tag"])
        if data["location_tag"] == "V-01" and calls.count("V-01") == 1:
            raise Exception("catalog rejected")
        return {"id": uuid4()}

    monkeypatch.setattr(service.projects_service, "save_position", _save)

    first = service.confirm_import(
        org_id=row["org_id"], project_id=row["project_id"],
        import_id=row["id"], items=[_item(key="r0", label="V-01"), _item(key="r1", label="V-02")],
    )
    assert first["import"]["status"] == "REVIEW_READY"
    assert [e["key"] for e in first["errors"]] == ["r0"]
    assert [c["key"] for c in first["created"]] == ["r1"]

    second = service.confirm_import(
        org_id=row["org_id"], project_id=row["project_id"],
        import_id=row["id"], items=[_item(key="r0", label="V-01")],
    )
    assert second["import"]["status"] == "CONFIRMED"
    assert second["errors"] == []
    assert {c["key"] for c in second["created"]} == {"r0", "r1"}
    assert calls == ["V-01", "V-02", "V-01"]


def _backend():
    class _Backend:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return None

    return _Backend()


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Service transactions are exercised at SQL level in pgTAP — unit tests
    mock rows/documentary_backend and would hit the no-DB guard on atomic()."""
    monkeypatch.setattr(service, "transaction", _NullAtomic())


class _NullAtomic:
    def atomic(self):
        return _backend()

    def __call__(self, *args, **kwargs):
        return _backend()


class _FakeConnection:
    def cursor(self):
        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def execute(self, *a):
                return None

            def fetchone(self):
                return (1,)

        return _Cursor()


def test_terminal_failure_marks_import_failed(monkeypatch):
    import ingest.handlers as handlers

    calls = []
    monkeypatch.setattr(handlers, "worker_claims", lambda claims: _backend())
    monkeypatch.setattr(handlers, "connection", _FakeConnection())
    monkeypatch.setattr(
        "ingest.service.extract_for_import",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("storage down")),
    )
    monkeypatch.setattr(
        "ingest.service.mark_import_failed", lambda **kw: calls.append(kw)
    )

    ctx = type(
        "Ctx",
        (),
        {
            "created_by": uuid4(),
            "org_id": uuid4(),
            "attempt": 3,
            "max_attempts": 3,
            "job_id": uuid4(),
        },
    )()
    with pytest.raises(RuntimeError):
        handlers.extract_document_job(
            {"import_id": str(uuid4())}, ctx, lambda progress: None
        )
    assert calls[0]["code"] == "import_extract_failed"
    assert str(calls[0]["import_id"]) == calls[0]["import_id"]


def test_non_terminal_failure_leaves_import_pending(monkeypatch):
    import ingest.handlers as handlers

    calls = []
    monkeypatch.setattr(handlers, "worker_claims", lambda claims: _backend())
    monkeypatch.setattr(handlers, "connection", _FakeConnection())
    monkeypatch.setattr(
        "ingest.service.extract_for_import",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("storage down")),
    )
    monkeypatch.setattr(
        "ingest.service.mark_import_failed", lambda **kw: calls.append(kw)
    )

    ctx = type(
        "Ctx",
        (),
        {
            "created_by": uuid4(),
            "org_id": uuid4(),
            "attempt": 1,
            "max_attempts": 3,
            "job_id": uuid4(),
        },
    )()
    with pytest.raises(RuntimeError):
        handlers.extract_document_job(
            {"import_id": str(uuid4())}, ctx, lambda progress: None
        )
    assert calls == []


def test_extract_deterministic_path_never_calls_provider(monkeypatch):
    row = _import_row(kind="PDF")
    updates = []

    class _Storage:
        def download(self, path):
            return b"%PDF fake bytes"

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(
        service, "extract", lambda kind, content: ("V-01 fijo 1200x1000", None)
    )

    class _Backend:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return None

    monkeypatch.setattr(service, "documentary_backend", lambda: _Backend())
    monkeypatch.setattr(service.projects_service, "editable", lambda *a, **k: {"id": "p"})
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: (
            updates.append((sql, params)) or [row | {"status": "REVIEW_READY"}]
            if "UPDATE public.document_imports" in sql and "RETURNING" in sql
            else [row]
            if "FROM public.document_imports" in sql
            else []
        ),
    )

    def _boom(**kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr("ai_gateway.service.invoke", _boom)
    out = service.extract_for_import(
        org_id=row["org_id"], import_id=row["id"], actor_id=uuid4()
    )
    assert out["candidate_count"] == 1
    stored = [p for sql, p in updates if "candidates" in sql][0]
    assert "V-01" in stored[0]


def test_extract_vision_fallback_when_no_text(monkeypatch):
    row = _import_row(kind="IMAGE", storage_path="imports/o/p/i/foto.png")
    seen = []

    class _Storage:
        def download(self, path):
            return b"\x89PNG"

        def signed_url(self, path):
            return "https://files.example/signed/foto.png"

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(service, "extract", lambda kind, content: ("", None))

    class _Backend:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return None

    monkeypatch.setattr(service, "documentary_backend", lambda: _Backend())
    monkeypatch.setattr(service.projects_service, "editable", lambda *a, **k: {"id": "p"})
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: (
            [row | {"status": "REVIEW_READY"}]
            if "UPDATE public.document_imports" in sql and "RETURNING" in sql
            else [row]
            if "FROM public.document_imports" in sql
            else []
        ),
    )
    monkeypatch.setattr(
        "ai_gateway.service.invoke",
        lambda **kwargs: seen.append(kwargs)
        or {"audit_id": str(uuid4()), "output": "A-1 fijo 800x600"},
    )
    out = service.extract_for_import(
        org_id=row["org_id"], import_id=row["id"], actor_id=uuid4()
    )
    assert seen[0]["capability"] == "vision_ocr"
    assert seen[0]["operation_key"] == f"import:{row['id']}:vision"
    # Only stable identity enters the audited input — the gateway resolves
    # the import row under the org and signs its canonical object at wire
    # time, so a job retry replays the paid OCR instead of minting a new URL.
    assert seen[0]["input_payload"]["source"] == {
        "kind": "document_import",
        "id": str(row["id"]),
    }
    assert "storage_path" not in seen[0]["input_payload"]
    assert "document_url" not in seen[0]["input_payload"]
    assert out["candidate_count"] == 1


def test_parse_line_glass_composition_is_not_quantity():
    # "4-12-4" is the insulated-glass recipe, not a count.
    candidate = parse_line("V-01 fijo 1200x1000 vidrio 4-12-4")
    assert candidate is not None
    assert candidate["quantity"] == 1
    candidate = parse_line("V-02 fijo 1200x1000 DVH 4+16+4 3 un")
    assert candidate is not None
    assert candidate["quantity"] == 3


def test_parse_line_technical_numbers_are_not_quantity():
    # A bare thickness tail is ambiguous — never promoted to a count.
    candidate = parse_line("V-01 fijo 1200x1000 2 unidades vidrio 6 mm")
    assert candidate is not None
    assert candidate["quantity"] == 2
    candidate = parse_line("V-02 fijo 1200x1000 espesor 20")
    assert candidate is not None
    assert candidate["quantity"] == 1
    candidate = parse_line("V-03 fijo 1200x1000 vidrio 6")
    assert candidate is not None
    assert candidate["quantity"] == 1
    # Schedule style where the count leads the row.
    candidate = parse_line("3 V-04 fijo 1200x1000")
    assert candidate is not None
    assert candidate["quantity"] == 3


def test_confirm_rejects_items_when_import_has_no_candidates(monkeypatch):
    row = _import_row(candidates=[])
    calls = []
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: (
            [row | {"result": params[0]}]
            if "UPDATE public.document_imports" in sql
            else [row]
        ),
    )
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda *a, **k: calls.append(a) or {"id": uuid4()},
    )
    out = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item()],
    )
    assert calls == []
    assert out["errors"] == [{"key": "r0", "code": "import_item_unknown"}]


def test_confirm_door_requires_panel_and_uses_it(monkeypatch):
    row = _import_row(
        candidates=[
            {
                "key": "r0",
                "label": "P-01",
                "width_mm": "900",
                "height_mm": "2100",
                "quantity": 1,
                "opening_type": "DOOR_ENTRY",
                "confidence": "HIGH",
                "warnings": [],
            }
        ]
    )
    designs = []
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: (
            [row | {"result": params[0]}]
            if "UPDATE public.document_imports" in sql
            else _glass_map()
            if "FROM public.glass_purchase_mappings" in sql
            else [row]
        ),
    )
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda org, proj, data: designs.append(data["design"]) or {"id": uuid4()},
    )
    door = _item(opening_type="DOOR_ENTRY", width_mm="900", height_mm="2100")
    missing = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[door],
    )
    assert missing["errors"] == [{"key": "r0", "code": "panel_article_required"}]
    assert designs == []

    with_panel = dict(door, panel_article_sku="PANEL-40")
    sealed = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[with_panel],
    )
    assert sealed["errors"] == []
    assert designs[0]["parametric_tree"]["panel_article_sku"] == "PANEL-40"


def test_create_import_removes_orphaned_upload_on_insert_failure(monkeypatch):
    stored = []
    deleted = []

    class _Storage:
        def upload_immutable(self, key, content, content_type):
            stored.append(key)

        def delete_object(self, key):
            deleted.append(key)

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(
        service.projects_service, "editable", lambda *a, **k: {"id": "p"}
    )
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    with pytest.raises(RuntimeError):
        service.create_import(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            file_name="lista.pdf",
            content=b"%PDF-1.4 fake",
            content_type="application/pdf",
        )
    assert len(stored) == 1
    assert deleted == stored


def test_create_import_rejects_long_filename(monkeypatch):
    uploads = []

    class _Storage:
        def upload_immutable(self, *a):
            uploads.append(a)

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(
        service.projects_service, "editable", lambda *a, **k: {"id": "p"}
    )
    with pytest.raises(Exception) as caught:
        service.create_import(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            file_name="x" * 250 + ".pdf",
            content=b"%PDF-1.4 fake",
            content_type="application/pdf",
        )
    assert getattr(caught.value, "contract_code", None) == "import_file_invalid"
    assert uploads == []


def test_create_import_rejects_path_like_filenames(monkeypatch):
    # The multipart filename lands verbatim in the storage key — traversal or
    # separators would write the object outside the org-scoped prefix.
    uploads = []

    class _Storage:
        def upload_immutable(self, *a):
            uploads.append(a)

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(
        service.projects_service, "editable", lambda *a, **k: {"id": "p"}
    )
    for bad_name in (
        "../escape.pdf",
        "a/b.pdf",
        "a\\b.pdf",
        "lista\t.pdf",
        "x\n.pdf",
        "a%2Fb.pdf",
        "100%.pdf",
    ):
        with pytest.raises(Exception) as caught:
            service.create_import(
                org_id=uuid4(),
                project_id=uuid4(),
                actor_id=uuid4(),
                file_name=bad_name,
                content=b"%PDF-1.4 fake",
                content_type="application/pdf",
            )
        assert getattr(caught.value, "contract_code", None) == "import_file_invalid"
    assert uploads == []


def test_extract_replays_when_row_sealed_during_extract(monkeypatch):
    # Claim won (UPLOADED→EXTRACTING) but a confirm sealed the import before
    # the terminal write — replay the committed state, never overwrite it.
    row = _import_row(status="UPLOADED", candidates=[])
    sealed = row | {
        "status": "CONFIRMED",
        "candidates": [{"key": "r0"}, {"key": "r1"}],
    }

    class _Storage:
        def download(self, path):
            return b"%PDF"

        def signed_url(self, path):
            return "https://files.example/signed/lista.pdf"

    def _rows(sql, params=None):
        if "UPDATE public.document_imports" in sql:
            if "status='REVIEW_READY'" in sql:
                return []  # sealed mid-run — the write is refused
            return [row | {"status": "EXTRACTING"}]
        if "FROM public.document_imports" in sql:
            if "WHERE id=%s AND org_id=%s" in sql:
                return [row]
            return [sealed]
        return []

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(
        service, "extract", lambda kind, content: ("V-01 fijo 1200x1000", None)
    )
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(service, "rows", _rows)
    monkeypatch.setattr(service.projects_service, "editable", lambda *a, **k: {"id": "p"})
    out = service.extract_for_import(
        org_id=row["org_id"], import_id=row["id"], actor_id=uuid4()
    )
    assert out["import"]["status"] == "CONFIRMED"
    assert out["candidate_count"] == 2


def test_create_import_enqueues_under_service_role(monkeypatch):
    # job_runs grants belong to service_role only — the enqueue must run
    # inside job_backend, not the documentary role.
    entered = []
    enqueued = []

    class _Storage:
        def upload_immutable(self, path, content, content_type):
            return None

        def delete_object(self, path):
            return None

    class _Backend:
        def __init__(self, tag):
            self.tag = tag

        def __enter__(self):
            entered.append(self.tag)
            return None

        def __exit__(self, *a):
            return None

    row = _import_row(status="UPLOADED")
    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(service.projects_service, "editable", lambda *a, **k: {"id": "p"})
    monkeypatch.setattr(service, "documentary_backend", lambda: _Backend("doc"))
    monkeypatch.setattr(service.jobs_service, "job_backend", lambda: _Backend("job"))
    monkeypatch.setattr(
        service.jobs_service,
        "enqueue",
        lambda **kw: enqueued.append(kw) or ({"id": uuid4()}, True),
    )
    monkeypatch.setattr(service, "rows", lambda sql, params=None: [row])
    out = service.create_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        actor_id=uuid4(),
        file_name="lista.pdf",
        content=b"%PDF-1.4 fake",
        content_type="application/pdf",
    )
    assert entered == ["doc", "job"]
    assert enqueued[0]["job_type"] == service.JOB_TYPE
    assert out["job"]["id"] is not None


def test_extract_caps_candidates_at_confirm_limit(monkeypatch):
    row = _import_row(status="UPLOADED", candidates=[])
    updates = []
    many = [{"key": f"r{i}", "label": f"V-{i}"} for i in range(service.MAX_CANDIDATES + 7)]

    class _Storage:
        def download(self, path):
            return b"%PDF"

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(service, "extract", lambda kind, content: ("x", None))
    monkeypatch.setattr(service, "candidates_from_rows", lambda rows: [])
    monkeypatch.setattr(service, "candidates_from_text", lambda text: many)
    monkeypatch.setattr(service, "documentary_backend", _backend)

    def _rows(sql, params=None):
        if "UPDATE public.document_imports" in sql and "RETURNING" in sql:
            if "status='REVIEW_READY'" in sql:
                updates.append(params)
                return [row | {"status": "REVIEW_READY"}]
            return [row | {"status": "EXTRACTING"}]
        if "FROM public.document_imports" in sql:
            return [row]
        return []

    monkeypatch.setattr(service, "rows", _rows)
    monkeypatch.setattr(service.projects_service, "editable", lambda *a, **k: {"id": "p"})
    out = service.extract_for_import(
        org_id=row["org_id"], import_id=row["id"], actor_id=uuid4()
    )
    written = json.loads(updates[0][0])
    assert len(written) == service.MAX_CANDIDATES
    assert "import.candidates_capped" in json.loads(updates[0][1])
    assert out["candidate_count"] == service.MAX_CANDIDATES


def test_extract_membership_revoked_marks_import_failed(monkeypatch):
    import ingest.handlers as handlers

    calls = []

    class _NoMembership:
        def cursor(self):
            class _Cursor:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return None

                def execute(self, *a):
                    return None

                def fetchone(self):
                    return None

            return _Cursor()

    monkeypatch.setattr(handlers, "worker_claims", lambda claims: _backend())
    monkeypatch.setattr(handlers, "connection", _NoMembership())
    monkeypatch.setattr(
        "ingest.service.extract_for_import",
        lambda **kw: (_ for _ in ()).throw(AssertionError("must not extract")),
    )
    monkeypatch.setattr(
        "ingest.service.mark_import_failed", lambda **kw: calls.append(kw)
    )
    ctx = type(
        "Ctx",
        (),
        {
            "created_by": uuid4(),
            "org_id": uuid4(),
            "attempt": 1,
            "max_attempts": 3,
            "job_id": uuid4(),
        },
    )()
    import pytest as _pytest

    with _pytest.raises(Exception) as raised:
        handlers.extract_document_job(
            {"import_id": str(uuid4())}, ctx, lambda progress: None
        )
    assert raised.type.__name__ == "JobPermanentError"
    assert calls[0]["code"] == "import_membership_revoked"


def test_create_import_rejects_non_editable_project(monkeypatch):
    # A quoted/sealed/priced project must not pay for extraction — confirm
    # would refuse every item anyway, so the gate fires before the upload.
    uploads = []
    deleted = []

    class _Storage:
        def upload_immutable(self, *a):
            uploads.append(a)

        def delete_object(self, key):
            deleted.append(key)

    monkeypatch.setattr(service, "SupabaseDocumentStorage", lambda: _Storage())
    monkeypatch.setattr(
        service.projects_service,
        "editable",
        lambda *a, **k: (_ for _ in ()).throw(
            contract_error(409, "commercial_revision_required", "cerrado")
        ),
    )
    with pytest.raises(APIException) as caught:
        service.create_import(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            file_name="lista.pdf",
            content=b"%PDF-1.4 fake",
            content_type="application/pdf",
        )
    assert caught.value.contract_code == "commercial_revision_required"
    assert uploads == []


def test_confirm_positions_carry_glass_article_authority(monkeypatch):
    # glass_spec is the physical composition; glass_article_sku is the
    # technical SKU — the saved tree must carry both or the BOM loses
    # glass weight and pricing authority.
    row = _import_row()
    saved = []
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda org, proj, data: saved.append(data) or {"id": uuid4()},
    )
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: (
            [row | {"status": "CONFIRMED", "result": []}]
            if "UPDATE public.document_imports" in sql
            else _glass_map()
            if "FROM public.glass_purchase_mappings" in sql
            else [row]
        ),
    )
    service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item()],
    )
    tree = saved[0]["design"]["parametric_tree"]
    assert tree["glass_spec"] == "4-12-4"
    assert tree["glass_article_sku"] == "GLASS-A"


def _confirm_rows(row, stored):
    def _rows(sql, params=None):
        if "UPDATE public.document_imports" in sql:
            stored["result"] = params[0]
            if "SET status='CONFIRMED'" in sql:
                return [row | {"status": "CONFIRMED", "result": params[0]}]
            return [row | {"result": params[0]}]
        if "FROM public.document_imports" in sql:
            return [row | {"result": stored["result"]}]
        if "FROM public.glass_purchase_mappings" in sql:
            return stored["glass"]
        return []

    return _rows


def test_confirm_unknown_glass_sku_is_item_error(monkeypatch):
    row = _import_row()
    stored = {"result": [], "glass": _glass_map()}
    saved = []
    monkeypatch.setattr(service, "rows", _confirm_rows(row, stored))
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda org, proj, data: saved.append(data) or {"id": uuid4()},
    )
    out = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item(glass_article_sku="GHOST-SKU")],
    )
    assert out["errors"] == [{"key": "r0", "code": "glass_article_unknown"}]
    assert saved == []


def test_confirm_mapping_spec_wins_over_submitted(monkeypatch):
    # The purchase mapping is the composition authority — a submitted spec
    # can never override the recipe the catalog declares for the SKU.
    row = _import_row()
    stored = {"result": [], "glass": _glass_map("4-20-4")}
    saved = []
    monkeypatch.setattr(service, "rows", _confirm_rows(row, stored))
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda org, proj, data: saved.append(data) or {"id": uuid4()},
    )
    out = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item(glass_spec="bogus-spec")],
    )
    assert out["errors"] == []
    assert saved[0]["design"]["parametric_tree"]["glass_spec"] == "4-20-4"


def test_confirm_specless_mapping_falls_back_to_submitted_spec(monkeypatch):
    row = _import_row()
    stored = {"result": [], "glass": _glass_map(None)}
    saved = []
    monkeypatch.setattr(service, "rows", _confirm_rows(row, stored))
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda org, proj, data: saved.append(data) or {"id": uuid4()},
    )
    service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item(glass_spec="4-12-4")],
    )
    assert saved[0]["design"]["parametric_tree"]["glass_spec"] == "4-12-4"


def test_confirm_specless_mapping_without_submitted_spec_errors(monkeypatch):
    row = _import_row()
    stored = {"result": [], "glass": _glass_map(None)}
    saved = []
    monkeypatch.setattr(service, "rows", _confirm_rows(row, stored))
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service.projects_service,
        "save_position",
        lambda org, proj, data: saved.append(data) or {"id": uuid4()},
    )
    out = service.confirm_import(
        org_id=row["org_id"],
        project_id=row["project_id"],
        import_id=row["id"],
        items=[_item(glass_spec="")],
    )
    assert out["errors"] == [{"key": "r0", "code": "glass_spec_required"}]
    assert saved == []


def test_extract_fails_closed_when_project_closed_before_run(monkeypatch):
    # Pricing applied between upload and job start — the OCR charge must
    # never run; the job turns it into a terminal FAILED import.
    row = _import_row(status="UPLOADED", candidates=[])

    def _closed(*a, **k):
        raise contract_error(409, "commercial_revision_required", "cerrado")

    monkeypatch.setattr(service.projects_service, "editable", _closed)
    monkeypatch.setattr(service, "documentary_backend", _backend)
    monkeypatch.setattr(
        service,
        "rows",
        lambda sql, params=None: [row]
        if "FROM public.document_imports" in sql
        else [],
    )
    with pytest.raises(service.ImportError_) as failure:
        service.extract_for_import(
            org_id=row["org_id"], import_id=row["id"], actor_id=uuid4()
        )
    assert failure.value.code == "import_project_closed"
