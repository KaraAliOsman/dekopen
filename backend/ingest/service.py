"""Document ingestion service: upload → extract → review → confirm.

The mandate's trust boundary: candidates are review data only. Nothing becomes
a position — let alone a BOM — without the estimator's explicit confirm, and
every confirmed item carries the system's real authority (system_id + glass)
chosen by the human, not inferred by the parser."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID, uuid4

from django.db import transaction

from authentication.errors import ContractAPIException, contract_error
from documents.repository import documentary_backend
from documents.storage import SupabaseDocumentStorage
from ingest.extract import extract, kind_for, safe_file_name, sniffed_kind
from ingest.parser import candidates_from_rows, candidates_from_text
from jobs import service as jobs_service
from pricing.repository import rows
from projects import service as projects_service

MAX_UPLOAD_BYTES = 15_000_000
MAX_CANDIDATES = 200
JOB_TYPE = "ingest.document.extract"


class ImportError_(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value) if value else []
    return list(value)


def _public(row: dict) -> dict:
    def _stamp(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    return {
        "id": str(row["id"]),
        "file_name": row["file_name"],
        "kind": row["kind"],
        "status": row["status"],
        "candidates": _as_list(row["candidates"]),
        "warnings": _as_list(row["warnings"]),
        "result": _as_list(row["result"]),
        "error_code": row["error_code"],
        "created_at": _stamp(row["created_at"]),
        "updated_at": _stamp(row["updated_at"]),
    }


def _get(org_id: UUID, project_id: UUID, import_id: UUID, *, backend: bool = False) -> dict:
    def _fetch():
        return rows(
            "SELECT * FROM public.document_imports "
            "WHERE org_id=%s AND project_id=%s AND id=%s",
            [str(org_id), str(project_id), str(import_id)],
        )

    found = _fetch() if not backend else _fetch_under_backend(_fetch)
    if not found:
        raise ImportError_("import_not_found")
    return found[0]


def _fetch_under_backend(fetch):
    with documentary_backend():
        return fetch()


def create_import(
    *, org_id: UUID, project_id: UUID, actor_id: UUID, file_name: str,
    content: bytes, content_type: str,
) -> dict:
    kind = kind_for(file_name)
    if kind is None:
        raise contract_error(
            422,
            "import_kind_unsupported",
            "Formato no soportado. Sube un PDF, XLSX o imagen (png, jpg, webp).",
        )
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise contract_error(
            422, "import_file_invalid", "El archivo está vacío o supera 15 MB."
        )
    if len(file_name) > 200 or len(file_name) == 0:
        raise contract_error(
            422,
            "import_file_invalid",
            "El nombre del archivo es demasiado largo o está vacío.",
        )
    if not safe_file_name(file_name):
        raise contract_error(
            422,
            "import_file_invalid",
            "El nombre del archivo contiene caracteres no permitidos.",
        )
    if not sniffed_kind(kind, content):
        raise contract_error(
            422,
            "import_file_mismatch",
            "El contenido del archivo no coincide con su extensión.",
        )
    # Fast-fail before the storage write; the authoritative gate re-locks the
    # row inside the atomic block below.
    projects_service.editable(org_id, project_id)
    import_id = uuid4()
    storage_path = f"imports/{org_id}/{project_id}/{import_id}/{file_name}"
    storage = SupabaseDocumentStorage()
    storage.upload_immutable(
        storage_path, content, content_type or "application/octet-stream"
    )
    try:
        with transaction.atomic():
            # The editable gate is part of the committed decision: its
            # FOR UPDATE holds the project row so a concurrent pricing or
            # revision transition cannot strand a paid extraction.
            projects_service.editable(org_id, project_id)
            with documentary_backend():
                row = rows(
                    "INSERT INTO public.document_imports("
                    "id, org_id, project_id, file_name, kind, storage_path, created_by)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                    [str(import_id), str(org_id), str(project_id), file_name, kind,
                     storage_path, str(actor_id)],
                )[0]
            # job_runs is a service-owned table — only service_role holds its
            # grants; job_backend switches role inside the atomic so the row
            # and the job still commit together.
            with jobs_service.job_backend():
                job, _ = jobs_service.enqueue(
                    org_id=org_id,
                    job_type=JOB_TYPE,
                    payload={"import_id": str(import_id)},
                    idempotency_key=f"import-extract:{import_id}",
                    created_by=actor_id,
                )
    except Exception:
        # The row or the enqueue failed — the immutable upload would orphan.
        try:
            storage.delete_object(storage_path)
        except Exception:
            pass
        raise
    return {"import": _public(row), "job": job}


def list_imports(*, org_id: UUID, project_id: UUID) -> dict:
    projects_service.project_row(org_id, project_id)
    found = rows(
        "SELECT * FROM public.document_imports "
        "WHERE org_id=%s AND project_id=%s ORDER BY created_at DESC, id DESC",
        [str(org_id), str(project_id)],
    )
    return {"imports": [_public(row) for row in found]}


def get_import(*, org_id: UUID, project_id: UUID, import_id: UUID) -> dict:
    return {"import": _public(_get(org_id, project_id, import_id))}


def extract_for_import(*, org_id: UUID, import_id: UUID, actor_id: UUID) -> dict:
    """The worker body: bytes → text → candidates. Deterministic first (PDF
    text layer, XLSX rows); a text-less source goes through the vision_ocr
    capability — debited under the org wallet, audited, idempotent on the
    import id so a job retry never double-charges."""
    found = rows(
        "SELECT * FROM public.document_imports WHERE id=%s AND org_id=%s",
        [str(import_id), str(org_id)],
    )
    if not found:
        raise ImportError_("import_not_found")
    row = found[0]
    # Claim in its own transaction: the provider call below must commit its
    # audit+debit independently of candidate writes, or a retry re-bills the
    # wallet. `documentary_backend` needs a live transaction for SET LOCAL ROLE.
    with transaction.atomic():
        # Paid OCR must not outlive the drafting contract — re-check inside the
        # claim transaction so a pricing application that raced the upload
        # still wins before the job's first charge. Confirm re-locks the
        # project authoritatively; this window is the worker's own creation.
        try:
            projects_service.editable(org_id, row["project_id"])
        except ContractAPIException as error:
            raise ImportError_("import_project_closed") from error
        with documentary_backend():
            claimed = rows(
                "UPDATE public.document_imports SET status='EXTRACTING', updated_at=now() "
                "WHERE id=%s AND status='UPLOADED' RETURNING *",
                [str(import_id)],
            )
    if not claimed:
        # A job retry on an already-extracted import replays its stored state —
        # never rewrites candidates a reviewer may have seen nor reverts a
        # confirmed import.
        current = rows(
            "SELECT * FROM public.document_imports WHERE id=%s",
            [str(import_id)],
        )[0]
        if current["status"] in ("REVIEW_READY", "CONFIRMED"):
            stored = _as_list(current["candidates"])
            return {
                "import": _public(current),
                "candidate_count": len(stored),
            }
        if current["status"] != "EXTRACTING":
            raise ImportError_("import_status_invalid")
    content = SupabaseDocumentStorage().download(row["storage_path"])
    warnings: list[str] = []
    audit_id = None
    try:
        text, sheet_rows = extract(row["kind"], content)
    except Exception:
        text, sheet_rows = "", None
        warnings.append("import.source_parse_failed")
    if sheet_rows is not None:
        candidates = candidates_from_rows(sheet_rows)
    elif text.strip():
        candidates = candidates_from_text(text)
    else:
        candidates = []
    if not candidates:
        # No deterministic extraction — the vision capability reads the
        # document. The operation key makes a retried job replay its stored
        # response instead of double-charging the wallet.
        from ai_gateway.service import ProviderError, invoke

        try:
            vision = invoke(
                org_id=org_id,
                user_id=actor_id,
                capability="vision_ocr",
                operation_key=f"import:{import_id}:vision",
                input_payload={
                    "file_name": row["file_name"],
                    "kind": row["kind"],
                    # Stable document identity only — the gateway resolves the
                    # row under the active org and signs its canonical object,
                    # so the audited input survives a job retry and replays
                    # the paid OCR instead of minting a new URL.
                    "source": {"kind": "document_import", "id": str(import_id)},
                },
            )
            audit_id = vision["audit_id"]
            vision_candidates = candidates_from_text(str(vision["output"]))
            if vision_candidates:
                candidates = vision_candidates
            else:
                warnings.append("import.vision_no_candidates")
        except ProviderError as error:
            warnings.append(f"import.vision_failed:{error.code}")
        except Exception as error:
            code = getattr(error, "contract_code", "ai_gateway_error")
            warnings.append(f"import.vision_failed:{code}")
    if not candidates:
        warnings.append("import.no_candidates")
    if len(candidates) > MAX_CANDIDATES:
        # A confirm request accepts at most MAX_CANDIDATES items — hold the
        # excess at review instead of letting a subset seal the import.
        candidates = candidates[:MAX_CANDIDATES]
        warnings.append("import.candidates_capped")
    with transaction.atomic():
        with documentary_backend():
            updated = rows(
                "UPDATE public.document_imports SET status='REVIEW_READY', "
                "candidates=%s::jsonb, warnings=%s::jsonb, audit_id=%s, updated_at=now() "
                "WHERE id=%s AND status='EXTRACTING' RETURNING *",
                [
                    json.dumps(candidates),
                    json.dumps(warnings),
                    audit_id,
                    str(import_id),
                ],
            )
    if not updated:
        # The import moved on while this extract ran (a concurrent confirm
        # sealed it, or a newer attempt wrote REVIEW_READY) — replay the
        # committed state instead of overwriting it.
        current = rows(
            "SELECT * FROM public.document_imports WHERE id=%s",
            [str(import_id)],
        )[0]
        if current["status"] in ("REVIEW_READY", "CONFIRMED"):
            return {
                "import": _public(current),
                "candidate_count": len(_as_list(current["candidates"])),
            }
        raise ImportError_("import_status_invalid")
    return {"import": _public(updated[0]), "candidate_count": len(candidates)}


def confirm_import(
    *, org_id: UUID, project_id: UUID, import_id: UUID, items: list[dict]
) -> dict:
    """Human confirm — the only path from candidate to position.

    One transaction: the import row is locked FOR UPDATE, each item saves under
    its own savepoint, and per-key outcomes accumulate in ``result`` — so a
    retried or concurrent confirm replays committed state instead of creating
    duplicates, a partial failure stays retryable, and CONFIRMED only seals
    once every submitted key has an outcome."""
    with transaction.atomic():
        with documentary_backend():
            found = rows(
                "SELECT * FROM public.document_imports "
                "WHERE id=%s AND org_id=%s AND project_id=%s FOR UPDATE",
                [str(import_id), str(org_id), str(project_id)],
            )
        if not found:
            raise ImportError_("import_not_found")
        row = found[0]
        if row["status"] == "CONFIRMED":
            return {
                "import": _public(row),
                "created": _as_list(row["result"]),
                "errors": [],
            }
        if row["status"] not in ("REVIEW_READY", "FAILED"):
            raise contract_error(
                409,
                "import_not_review_ready",
                "La importación aún está procesándose. Espera a que termine.",
            )
        candidate_keys = {
            candidate.get("key") for candidate in _as_list(row["candidates"])
        }
        created = _as_list(row["result"])
        done = {str(entry.get("key")) for entry in created}
        errors: list[dict] = []
        glass_cache: dict[str, dict] = {}
        for item in items:
            key = str(item["key"])
            if key in done:
                continue
            if key not in candidate_keys:
                errors.append({"key": key, "code": "import_item_unknown"})
                continue
            # The technical SKU must resolve against the system's purchase
            # mappings — an unknown article can never seed a BOM.
            sku = str(item["glass_article_sku"]).strip()
            mapping = glass_cache.get(str(item["system_id"]))
            if mapping is None:
                mapping = {
                    str(entry["technical_sku"]): entry.get("glass_spec")
                    for entry in rows(
                        "SELECT DISTINCT ON (technical_sku) technical_sku, glass_spec "
                        "FROM public.glass_purchase_mappings "
                        "WHERE system_id=%s AND (org_id=%s OR org_id IS NULL) "
                        "ORDER BY technical_sku, org_id NULLS LAST, version DESC",
                        [str(item["system_id"]), str(org_id)],
                    )
                }
                glass_cache[str(item["system_id"])] = mapping
            if sku not in mapping:
                errors.append({"key": key, "code": "glass_article_unknown"})
                continue
            # The catalog recipe wins; only a spec-less mapping falls back to
            # the reviewer's submitted spec — never to the slot thickness.
            spec = str(mapping.get(sku) or "").strip() or str(
                item.get("glass_spec") or ""
            ).strip()
            if not spec:
                errors.append({"key": key, "code": "glass_spec_required"})
                continue
            parametric_tree = {
                "id": "imported",
                "type": "BAY",
                "opening_type": item["opening_type"],
                "glass_thickness_mm": item["glass_thickness_mm"],
                "glass_spec": spec,
                "glass_article_sku": sku,
            }
            if item["opening_type"] == "DOOR_ENTRY":
                panel_sku = str(item.get("panel_article_sku") or "").strip()
                if not panel_sku:
                    errors.append({"key": key, "code": "panel_article_required"})
                    continue
                parametric_tree["panel_article_sku"] = panel_sku
            design = {
                "system_id": str(item["system_id"]),
                "nominal_width_mm": Decimal(str(item["width_mm"])),
                "nominal_height_mm": Decimal(str(item["height_mm"])),
                "color": item["color"],
                "parametric_tree": parametric_tree,
            }
            try:
                with transaction.atomic():
                    position = projects_service.save_position(
                        org_id,
                        project_id,
                        {
                            "location_tag": item["label"],
                            "quantity": item["quantity"],
                            "design": design,
                        },
                    )
                created.append({"key": key, "position_id": str(position["id"])})
                done.add(key)
            except Exception as error:
                errors.append(
                    {
                        "key": key,
                        "code": getattr(error, "contract_code", "save_failed"),
                    }
                )
        if errors:
            # Retryable: persist what was created so the next confirm only
            # attempts the still-unresolved keys.
            with documentary_backend():
                updated = rows(
                    "UPDATE public.document_imports SET result=%s::jsonb, "
                    "updated_at=now() WHERE id=%s RETURNING *",
                    [json.dumps(created), str(import_id)],
                )[0]
            return {"import": _public(updated), "created": created, "errors": errors}
        with documentary_backend():
            updated = rows(
                "UPDATE public.document_imports SET status='CONFIRMED', "
                "result=%s::jsonb, updated_at=now() WHERE id=%s RETURNING *",
                [json.dumps(created), str(import_id)],
            )[0]
        return {"import": _public(updated), "created": created, "errors": []}


def mark_import_failed(*, org_id: UUID, import_id: UUID, code: str) -> None:
    """Terminal job failure → a terminal import state so polling stops."""
    with transaction.atomic(), documentary_backend():
        rows(
            "UPDATE public.document_imports SET status='FAILED', error_code=%s, "
            "updated_at=now() WHERE id=%s AND org_id=%s "
            "AND status IN ('UPLOADED','EXTRACTING') RETURNING id",
            [code[:120], str(import_id), str(org_id)],
        )
