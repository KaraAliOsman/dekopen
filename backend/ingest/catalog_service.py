"""Catalog ingestion service: upload → extract → review → confirm.

Same trust boundary as document ingestion: candidates are review data only.
Nothing becomes a profile_articles row — let alone catalog authority — without
the estimator's explicit confirm, and the target system must belong to the
organization (articles on a shared/global system would leak to every tenant).
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID, uuid4

from django.db import DatabaseError, transaction

from authentication.errors import contract_error
from authentication.rls import catalog_backend
from dekopen_engine.hardware import normalize_opening_type
from dekopen_engine.models import BayOpeningType
from documents.repository import documentary_backend
from documents.storage import SupabaseDocumentStorage
from catalogs import evidence as catalog_evidence
from ingest.catalog_parser import ROLES, parse_ai_candidates, parse_catalog_lines
from dekopen_engine.glass_composition import (
    composition_to_dict,
    parse_glass_notation,
)
from ingest.extract import extract_tagged, kind_for, safe_file_name, sniffed_kind
from ingest.spreadsheet import (
    ENTITY_CUT_RULE,
    ENTITY_EXTRA,
    ENTITY_FINISH,
    ENTITY_GLAZING,
    ENTITY_GLASS_LIMIT,
    ENTITY_GLASS_PRODUCT,
    ENTITY_GLASS_SAFETY,
    ENTITY_GLASS_SURCHARGE,
    ENTITY_HANDLE_COLOR,
    ENTITY_HANDLE_MODEL,
    ENTITY_HARDWARE,
    ENTITY_HARDWARE_FAMILY,
    ENTITY_HARDWARE_OPTION,
    ENTITY_LIMIT,
    ENTITY_PRICE,
    ENTITY_PROFILE,
    ENTITY_REINFORCEMENT,
    ENTITY_SERVICE,
    ENTITIES,
    looks_like_template,
    parse_catalog_spreadsheet,
)
from jobs import service as jobs_service
from pricing.repository import rows, write

MAX_UPLOAD_BYTES = 15_000_000
MAX_CANDIDATES = 200
JOB_TYPE = "ingest.catalog.extract"

# Missing manufacturing data stays UNKNOWN (NULL) — a supplier document that
# does not state a stock length, welding loss or weight must never gain a
# fabricated value here; downstream consumers refuse or flag instead.


def _numeric_or_none(value: object) -> str | None:
    return None if value is None else str(value)


class CatalogImportError(Exception):
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
        "system_id": str(row["system_id"]) if row["system_id"] else None,
        "candidates": _as_list(row["candidates"]),
        "warnings": _as_list(row["warnings"]),
        "result": _as_list(row["result"]),
        "error_code": row["error_code"],
        "created_at": _stamp(row["created_at"]),
        "updated_at": _stamp(row["updated_at"]),
    }


def _get(org_id: UUID, import_id: UUID) -> dict:
    found = rows(
        "SELECT * FROM public.catalog_imports WHERE org_id=%s AND id=%s",
        [str(org_id), str(import_id)],
    )
    if not found:
        raise CatalogImportError("catalog_import_not_found")
    return found[0]


def create_catalog_import(
    *,
    org_id: UUID,
    actor_id: UUID,
    file_name: str,
    content: bytes,
    content_type: str,
) -> dict:
    kind = kind_for(file_name)
    if kind is None:
        raise contract_error(
            422,
            "catalog_import_kind_unsupported",
            "Formato no soportado. Sube un PDF, XLSX, CSV o imagen (png, jpg, webp).",
        )
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise contract_error(
            422, "catalog_import_file_invalid", "El archivo está vacío o supera 15 MB."
        )
    if len(file_name) > 200 or len(file_name) == 0:
        raise contract_error(
            422,
            "catalog_import_file_invalid",
            "El nombre del archivo es demasiado largo o está vacío.",
        )
    if not safe_file_name(file_name):
        raise contract_error(
            422,
            "catalog_import_file_invalid",
            "El nombre del archivo contiene caracteres no permitidos.",
        )
    if not sniffed_kind(kind, content):
        raise contract_error(
            422,
            "catalog_import_file_mismatch",
            "El contenido del archivo no coincide con su extensión.",
        )
    import_id = uuid4()
    storage_path = f"catalog-imports/{org_id}/{import_id}/{file_name}"
    storage = SupabaseDocumentStorage()
    storage.upload_immutable(storage_path, content, content_type or "application/octet-stream")
    try:
        with transaction.atomic():
            with documentary_backend():
                row = rows(
                    "INSERT INTO public.catalog_imports("
                    "id, org_id, file_name, kind, storage_path, created_by)"
                    " VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                    [str(import_id), str(org_id), file_name, kind, storage_path, str(actor_id)],
                )[0]
            # job_runs is a service-owned table — service_role only, inside the
            # atomic so row and job commit together.
            with jobs_service.job_backend():
                job, _ = jobs_service.enqueue(
                    org_id=org_id,
                    job_type=JOB_TYPE,
                    payload={"import_id": str(import_id)},
                    idempotency_key=f"catalog-extract:{import_id}",
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


def list_catalog_imports(*, org_id: UUID) -> dict:
    found = rows(
        "SELECT * FROM public.catalog_imports WHERE org_id=%s ORDER BY created_at DESC, id DESC",
        [str(org_id)],
    )
    return {"imports": [_public(row) for row in found]}


def get_catalog_import(*, org_id: UUID, import_id: UUID) -> dict:
    return {"import": _public(_get(org_id, import_id))}


# Roles a profile series must cover to be workable; a document missing some
# gets flagged so the reviewer knows which technical sheet to ask for next.
_CORE_ROLES = ("FRAME", "SASH", "MULLION_V", "MULLION_H", "GLAZING_BEAD")


def _reconcile(org_id: UUID, candidates: list[dict]) -> None:
    """Annotate candidates against the org's existing articles: same-SKU rows
    surface as `existing` (current vs proposed) and differ-on-authority rows
    get `conflict` + a review warning — before anything can write."""
    skus = sorted(
        {
            str(c.get("sku"))
            for c in candidates
            if c.get("sku") and c.get("entity") in (None, ENTITY_PROFILE)
        }
    )
    if not skus:
        return
    existing = rows(
        "SELECT a.sku, a.name, a.role, a.face_width_mm, s.code AS system_code "
        "FROM public.profile_articles a "
        "JOIN public.profile_systems s ON s.id = a.system_id "
        "WHERE a.org_id=%s AND s.org_id=%s AND a.sku = ANY(%s)",
        [str(org_id), str(org_id), skus],
    )
    by_sku: dict[str, list[dict]] = {}
    for article in existing:
        by_sku.setdefault(article["sku"], []).append(article)
    for candidate in candidates:
        if candidate.get("entity") not in (None, ENTITY_PROFILE):
            continue
        matches = by_sku.get(candidate.get("sku"), [])
        if not matches:
            continue
        candidate["existing"] = [
            {
                "system_code": match["system_code"],
                "name": match["name"],
                "role": match["role"],
                "face_width_mm": (
                    str(match["face_width_mm"])
                    if match["face_width_mm"] is not None
                    else None
                ),
            }
            for match in matches[:5]
        ]
        candidate_width = candidate.get("face_width_mm")
        differs = any(
            str(match["role"]) != str(candidate.get("role"))
            or (
                match["face_width_mm"] is not None
                and candidate_width is not None
                and Decimal(str(match["face_width_mm"]))
                != Decimal(str(candidate_width))
            )
            for match in matches
        )
        if differs:
            candidate["conflict"] = True
            candidate.setdefault("warnings", []).append("catalog_conflicts_existing")


def _series_gaps(candidates: list[dict]) -> str | None:
    """Roles a workable profile series still lacks in this document."""
    roles = {
        str(candidate.get("role"))
        for candidate in candidates
        if candidate.get("entity") in (None, ENTITY_PROFILE)
    }
    missing = [role for role in _CORE_ROLES if role not in roles]
    return ",".join(missing) if missing and candidates else None


def extract_catalog_import(*, org_id: UUID, import_id: UUID, actor_id: UUID) -> dict:
    """The worker body: bytes → article candidates. Deterministic first; a
    text-less source goes through the catalog_compile capability — debited
    under the org wallet, audited, idempotent on the import id."""
    found = rows(
        "SELECT * FROM public.catalog_imports WHERE id=%s AND org_id=%s",
        [str(import_id), str(org_id)],
    )
    if not found:
        raise CatalogImportError("catalog_import_not_found")
    row = found[0]
    # Claim in its own transaction so the provider call below can commit its
    # audit+debit independently of candidate writes — a retry never re-bills.
    with transaction.atomic():
        with documentary_backend():
            claimed = rows(
                "UPDATE public.catalog_imports SET status='EXTRACTING', updated_at=now() "
                "WHERE id=%s AND status='UPLOADED' RETURNING *",
                [str(import_id)],
            )
    if not claimed:
        current = rows(
            "SELECT * FROM public.catalog_imports WHERE id=%s",
            [str(import_id)],
        )[0]
        if current["status"] in ("REVIEW_READY", "CONFIRMED"):
            return {
                "import": _public(current),
                "candidate_count": len(_as_list(current["candidates"])),
            }
        if current["status"] != "EXTRACTING":
            raise CatalogImportError("catalog_import_status_invalid")
    content = SupabaseDocumentStorage().download(row["storage_path"])
    warnings: list[str] = []
    audit_id = None
    candidates: list[dict] = []
    if row["kind"] in ("XLSX", "CSV") and looks_like_template(row["kind"], content):
        # The manual template is a structured source: per-sheet declared
        # columns, per-row Spanish errors — never routed through prose guesses.
        candidates, sheet_errors = parse_catalog_spreadsheet(row["kind"], content)
        warnings.extend(sheet_errors)
    else:
        try:
            tagged = extract_tagged(row["kind"], content)
        except Exception:
            tagged = None
            warnings.append("catalog.source_parse_failed")
        candidates = parse_catalog_lines(tagged or [])
    if not candidates:
        from ai_gateway.service import ProviderError, invoke

        try:
            vision = invoke(
                org_id=org_id,
                user_id=actor_id,
                capability="catalog_compile",
                operation_key=f"catalog:{import_id}:compile",
                input_payload={
                    # Stable identity only — the gateway resolves the row
                    # under the active org and signs its canonical object, so
                    # the audited input survives a job retry and replays the
                    # paid compile instead of minting a new URL.
                    "file_name": row["file_name"],
                    "kind": row["kind"],
                    "source": {"kind": "catalog_import", "id": str(import_id)},
                    "target": "profile_articles",
                },
            )
            audit_id = vision["audit_id"]
            vision_candidates = parse_ai_candidates(str(vision["output"]))
            if vision_candidates:
                candidates = vision_candidates
            else:
                warnings.append("catalog.compile_no_candidates")
        except ProviderError as error:
            warnings.append(f"catalog.compile_failed:{error.code}")
        except Exception as error:
            code = getattr(error, "contract_code", "ai_gateway_error")
            warnings.append(f"catalog.compile_failed:{code}")
    for candidate in candidates:
        # Evidence's document id = the import row — review can trace every
        # field back to the exact document it was extracted from.
        candidate.setdefault("evidence", {})["document_id"] = str(import_id)
    if not candidates:
        warnings.append("catalog.no_candidates")
    else:
        _reconcile(org_id, candidates)
        missing = _series_gaps(candidates)
        if missing:
            warnings.append(f"catalog.series_incomplete:{missing}")
    if len(candidates) > MAX_CANDIDATES:
        candidates = candidates[:MAX_CANDIDATES]
        warnings.append("catalog.candidates_capped")
    with transaction.atomic():
        with documentary_backend():
            updated = rows(
                "UPDATE public.catalog_imports SET status='REVIEW_READY', "
                "candidates=%s::jsonb, warnings=%s::jsonb, audit_id=%s, updated_at=now() "
                "WHERE id=%s AND status='EXTRACTING' RETURNING *",
                [
                    json.dumps(candidates, default=str),
                    json.dumps(warnings),
                    audit_id,
                    str(import_id),
                ],
            )
    if not updated:
        current = rows(
            "SELECT * FROM public.catalog_imports WHERE id=%s",
            [str(import_id)],
        )[0]
        if current["status"] in ("REVIEW_READY", "CONFIRMED"):
            return {
                "import": _public(current),
                "candidate_count": len(_as_list(current["candidates"])),
            }
        raise CatalogImportError("catalog_import_status_invalid")
    return {"import": _public(updated[0]), "candidate_count": len(candidates)}


def mark_catalog_import_failed(*, org_id: UUID, import_id: UUID, code: str) -> None:
    with transaction.atomic():
        with documentary_backend():
            # Only an in-flight import may fail — a stale retry must never
            # overwrite a REVIEW_READY or CONFIRMED outcome.
            write(
                "UPDATE public.catalog_imports SET status='FAILED', "
                "error_code=%s, updated_at=now() WHERE id=%s AND org_id=%s "
                "AND status IN ('UPLOADED','EXTRACTING')",
                [code[:80], str(import_id), str(org_id)],
            )


def _insert_entity_row(
    *, org_id: UUID, system_id: UUID, entity: str, fields: dict
) -> tuple[str, object] | None:
    """Write one non-PROFILE confirmed item to its authority table.

    Returns (id, result) on insert, None when a uniqueness conflict skipped
    the write — every table here uses NULLS NOT DISTINCT uniques, which an
    ON CONFLICT arbiter cannot name, so conflicts resolve as DO NOTHING +
    empty RETURNING."""
    payload = {key: (_decimal_text(value)) for key, value in fields.items()}
    if entity == ENTITY_CUT_RULE:
        found = rows(
            "INSERT INTO public.profile_cut_rules("
            "system_id, org_id, role, cut_angle_deg, welded_ends,"
            " interlock_deduction_mm, rounding_mm, reinforcement_sku,"
            " data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE) ON CONFLICT DO NOTHING"
            " RETURNING id",
            [
                str(system_id), str(org_id), fields["role"],
                payload.get("cut_angle_deg") or "45.00",
                # welded_ends es INTEGER (0-2): un bool rompe en Postgres
                # ("column is of type integer but expression is of type boolean").
                fields.get("welded_ends") if not isinstance(fields.get("welded_ends"), bool)
                else int(fields["welded_ends"]),
                payload.get("interlock_deduction_mm") or "0.00",
                payload.get("rounding_mm") or "0.01",
                fields.get("reinforcement_sku") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_REINFORCEMENT:
        found = rows(
            "INSERT INTO public.profile_reinforcement_rules("
            "system_id, org_id, role, finish_class, min_length_mm, mandatory,"
            " reinforcement_sku, cut_deduction_mm, screws_per_m, screw_sku,"
            " data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id), fields["role"],
                fields.get("finish_class") or "ALL",
                payload.get("min_length_mm") or "0.00",
                bool(fields.get("mandatory", True)),
                fields.get("reinforcement_sku") or None,
                payload.get("cut_deduction_mm") or "0.00",
                payload.get("screws_per_m"),
                fields.get("screw_sku") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_LIMIT:
        found = rows(
            "INSERT INTO public.system_typology_limits("
            "system_id, org_id, opening_type, min_leaf_width_mm,"
            " max_leaf_width_mm, min_leaf_height_mm, max_leaf_height_mm,"
            " max_leaf_weight_kg, max_aspect_ratio, data_provenance,"
            " review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id), fields["opening_type"],
                payload.get("min_leaf_width_mm"),
                payload.get("max_leaf_width_mm"),
                payload.get("min_leaf_height_mm"),
                payload.get("max_leaf_height_mm"),
                payload.get("max_leaf_weight_kg"),
                payload.get("max_aspect_ratio"),
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_GLAZING:
        bead = rows(
            "SELECT id FROM public.profile_articles"
            " WHERE system_id=%s AND sku=%s"
            " AND (org_id=%s OR org_id IS NULL) AND role='GLAZING_BEAD'",
            [str(system_id), str(fields["bead_sku"]).upper(), str(org_id)],
        )
        if not bead:
            raise CatalogImportError("catalog_bead_unknown")
        found = rows(
            "INSERT INTO public.glazing_bead_matrix("
            "system_id, org_id, glass_thickness_mm, bead_article_id,"
            " bead_width_mm, gasket_interior_mm, gasket_exterior_mm)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (system_id, glass_thickness_mm) DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id), payload["glass_thickness_mm"],
                str(bead[0]["id"]), payload["bead_width_mm"],
                payload.get("gasket_interior_mm") or "3.00",
                payload.get("gasket_exterior_mm") or "3.00",
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_HARDWARE:
        contents = fields.get("contents")
        if not isinstance(contents, list):
            contents = []
        # La hoja lleva la tipología detallada (TILT_TURN_RIGHT); el kit la
        # guarda como familia de herraje (TILT_TURN) — misma normalización
        # del motor, constraint chk_kits_opening_type incluido.
        try:
            opening_family = normalize_opening_type(
                BayOpeningType(str(fields["opening_type"]))
            )
        except (ValueError, KeyError):
            raise CatalogImportError("catalog_opening_type_unknown")
        found = rows(
            "INSERT INTO public.hardware_kits("
            "system_id, org_id, sku, name, opening_type, min_leaf_width_mm,"
            " max_leaf_width_mm, min_leaf_height_mm, max_leaf_height_mm,"
            " max_leaf_weight_kg, rail_type, carriages_qty, stay_arms_qty,"
            " contents, data_provenance, review_pending,"
            " class_label, max_aspect_ratio, min_stay_height_mm)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,"
            " 'IMPORT', TRUE, %s, %s, %s)"
            " ON CONFLICT (system_id, sku) DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id),
                str(fields["sku"]).strip().upper(),
                str(fields.get("name") or fields["sku"]),
                opening_family,
                payload["min_leaf_width_mm"], payload["max_leaf_width_mm"],
                payload["min_leaf_height_mm"], payload["max_leaf_height_mm"],
                payload["max_leaf_weight_kg"],
                str(fields.get("rail_type") or "dual"),
                int(fields.get("carriages_qty") or 0),
                int(fields.get("stay_arms_qty") or 0),
                json.dumps(contents, default=str),
                _class_label(fields.get("class_label")),
                payload.get("max_aspect_ratio"),
                payload.get("min_stay_height_mm"),
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_HARDWARE_FAMILY:
        _opening_family(fields)
        found = rows(
            "INSERT INTO public.hardware_families("
            "system_id, org_id, opening_type, handle_height_rule,"
            " handle_height_min_mm, handle_height_max_mm,"
            " handle_height_default_mm, data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id), str(fields["opening_type"]),
                fields.get("handle_height_rule") or None,
                payload.get("handle_height_min_mm"),
                payload.get("handle_height_max_mm"),
                payload.get("handle_height_default_mm"),
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_HANDLE_MODEL:
        _opening_family(fields)
        found = rows(
            "INSERT INTO public.hardware_handle_models("
            "system_id, org_id, opening_type, sku, name, kind,"
            " price_delta_clp, data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id), str(fields["opening_type"]),
                str(fields["sku"]).strip().upper(),
                str(fields.get("name") or fields["sku"]),
                str(fields["kind"]),
                payload.get("price_delta_clp"),
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_HANDLE_COLOR:
        _opening_family(fields)
        found = rows(
            "INSERT INTO public.hardware_handle_colors("
            "system_id, org_id, opening_type, sku, name, price_delta_clp,"
            " data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id), str(fields["opening_type"]),
                str(fields["sku"]).strip().upper(),
                str(fields.get("name") or fields["sku"]),
                payload.get("price_delta_clp"),
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_HARDWARE_OPTION:
        _opening_family(fields)
        components = fields.get("components")
        if not isinstance(components, list):
            components = []
        found = rows(
            "INSERT INTO public.hardware_options("
            "system_id, org_id, opening_type, sku, name, kind,"
            " price_delta_clp, components, data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id), str(fields["opening_type"]),
                str(fields["sku"]).strip().upper(),
                str(fields.get("name") or fields["sku"]),
                str(fields["kind"]),
                payload.get("price_delta_clp"),
                json.dumps(components, default=str),
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_GLASS_PRODUCT:
        # The sheet declares the notation; the engine derives the structured
        # stack + thickness/weight — supplier-declared numbers are optional
        # columns, never trusted over the computed stack.
        composition = parse_glass_notation(str(fields.get("notation") or ""))
        composition_payload: dict | None = None
        if composition is not None:
            composition_payload = composition_to_dict(composition)
        found = rows(
            "INSERT INTO public.glass_products("
            "system_id, org_id, sku, commercial_name, notation, composition,"
            " total_thickness_mm, safety_class, ug_w_m2k, g_value,"
            " light_transmission_pct, weight_kg_m2, min_billable_area_m2,"
            " price_tier, supplier_name, data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            " 'IMPORT',TRUE) ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id),
                str(fields["sku"]).strip().upper(),
                str(fields.get("name") or fields["sku"]),
                str(fields["notation"]),
                json.dumps(composition_payload, default=str)
                if composition_payload is not None else None,
                str(composition.total_thickness_mm())
                if composition is not None else None,
                fields.get("safety_class") or None,
                payload.get("ug_w_m2k"),
                payload.get("g_value"),
                payload.get("light_transmission_pct"),
                payload.get("weight_kg_m2")
                or (str(composition.weight_kg_m2())
                    if composition is not None else None),
                payload.get("min_billable_area_m2"),
                payload.get("price_tier"),
                str(fields.get("supplier") or "") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_GLASS_SAFETY:
        found = rows(
            "INSERT INTO public.glass_safety_rules("
            "org_id, code, title, message, applies_openings, sill_below_mm,"
            " min_area_m2, requires_door, requires_adjacent_door,"
            " required_safety, severity, source_ref, data_provenance,"
            " review_pending)"
            " VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(org_id),
                str(fields["code"]).strip().upper(),
                str(fields["title"]),
                str(fields.get("message") or "") or None,
                json.dumps(_as_list(fields.get("applies_openings"))),
                payload.get("sill_below_mm"),
                payload.get("min_area_m2"),
                bool(fields.get("requires_door")),
                bool(fields.get("requires_adjacent_door")),
                str(fields["required_safety"]),
                str(fields.get("severity") or "WARNING"),
                str(fields.get("source_ref") or "") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_GLASS_SURCHARGE:
        # Resolve the declared product inside the same org+system scope the
        # engine loader applies (org rows outrank global, system rows
        # outrank cross-system for a sku).
        product = rows(
            "SELECT id FROM public.glass_products "
            "WHERE sku=%s AND is_active=TRUE "
            "AND (org_id=%s OR org_id IS NULL) "
            "AND (system_id=%s OR system_id IS NULL) "
            "ORDER BY org_id NULLS LAST, system_id NULLS LAST LIMIT 1",
            [
                str(fields["product_sku"]).strip().upper(),
                str(org_id), str(system_id),
            ],
        )
        if not product:
            raise CatalogImportError("catalog_glass_product_not_found")
        found = rows(
            "INSERT INTO public.glass_product_surcharges("
            "product_id, org_id, kind, unit, unit_cost, currency, label,"
            " data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(product[0]["id"]), str(org_id),
                str(fields["kind"]), str(fields["unit"]),
                payload.get("unit_cost"),
                str(fields.get("currency") or "") or None,
                str(fields.get("label") or "") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_GLASS_LIMIT:
        found = rows(
            "INSERT INTO public.glass_type_limits("
            "org_id, code, lamina_kind, thickness_min_mm, thickness_max_mm,"
            " min_side_mm, max_side_mm, min_area_m2, max_area_m2,"
            " max_aspect_ratio, requires_exact_cut, severity, source_ref,"
            " data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(org_id),
                str(fields["code"]).strip().upper(),
                str(fields["lamina_kind"]),
                payload.get("thickness_min_mm"),
                payload.get("thickness_max_mm"),
                payload.get("min_side_mm"),
                payload.get("max_side_mm"),
                payload.get("min_area_m2"),
                payload.get("max_area_m2"),
                payload.get("max_aspect_ratio"),
                bool(fields.get("requires_exact_cut")),
                str(fields.get("severity") or "WARNING"),
                str(fields.get("source_ref") or "") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_EXTRA:
        # D06: system-scoped accessory — the engine re-measures every
        # quantity off the product geometry; the sheet declares the
        # article's price/cost, cut profile and suggestion cause.
        found = rows(
            "INSERT INTO public.extra_articles("
            "system_id, org_id, sku, name, kind, pricing_unit,"
            " unit_price, unit_price_currency, unit_cost, unit_cost_currency,"
            " cut_profile_sku, cut_material, vuelo_default_mm,"
            " families, unit_kinds, suggestion_reason,"
            " data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            " %s,'IMPORT',TRUE) ON CONFLICT DO NOTHING RETURNING id",
            [
                str(system_id), str(org_id),
                str(fields["sku"]).strip().upper(),
                str(fields.get("name") or fields["sku"]),
                str(fields["kind"]),
                str(fields["pricing_unit"]),
                payload.get("unit_price"),
                str(fields.get("unit_price_currency") or "") or None,
                payload.get("unit_cost"),
                str(fields.get("unit_cost_currency") or "") or None,
                str(fields.get("cut_profile_sku") or "").strip().upper() or None,
                str(fields.get("cut_material") or "") or None,
                payload.get("vuelo_default_mm"),
                _as_list(fields.get("families")),
                _as_list(fields.get("unit_kinds")),
                str(fields.get("suggestion_reason") or "") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    if entity == ENTITY_SERVICE:
        # D06: org data — a project service is never bound to the importing
        # system; its qty_rule fixes how pricing measures the charge.
        found = rows(
            "INSERT INTO public.service_articles("
            "org_id, code, name, kind, qty_rule,"
            " unit_price, unit_price_currency, unit_cost, unit_cost_currency,"
            " data_provenance, review_pending)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
            " ON CONFLICT DO NOTHING RETURNING id",
            [
                str(org_id),
                str(fields["code"]).strip().upper(),
                str(fields.get("name") or fields["code"]),
                str(fields["kind"]),
                str(fields["qty_rule"]),
                payload.get("unit_price"),
                str(fields.get("unit_price_currency") or "") or None,
                payload.get("unit_cost"),
                str(fields.get("unit_cost_currency") or "") or None,
            ],
        )
        return ("id", found[0]["id"]) if found else None
    return None


def _class_label(value: object) -> str | None:
    text = str(value or "").strip()
    return text[:80] or None


def _opening_family(fields: dict) -> str:
    """D04 entities scope to the normalized opening family; the spreadsheet
    enum already carries it — this just refuses anything else."""
    opening = str(fields.get("opening_type") or "")
    if opening not in ("TURN", "TILT_TURN", "SLIDING", "DOOR", "AWNING"):
        raise CatalogImportError("catalog_opening_type_unknown")
    return opening


def _decimal_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _create_system(
    *, org_id: UUID, fields: dict
) -> UUID:
    """A confirmed Sistemas row becomes an org-owned profile_systems row —
    the only way an import may declare a new series."""
    found = rows(
        "INSERT INTO public.profile_systems("
        "code, name, org_id, depth_mm, material, is_global, is_active,"
        " system_family, finishes, sliding_glazing_deduction_width_mm,"
        " sliding_glazing_deduction_height_mm, door_leaf_side_clearance_mm,"
        " data_provenance, review_pending)"
        " VALUES(%s,%s,%s,%s,%s,FALSE,TRUE,%s,%s::jsonb,%s,%s,%s,'IMPORT',TRUE)"
        " ON CONFLICT DO NOTHING RETURNING id",
        [
            str(fields["code"]).strip().upper(),
            str(fields["name"]).strip() or str(fields["code"]).strip().upper(),
            str(org_id),
            str(fields["depth_mm"]),
            str(fields["material"]),
            str(fields["system_family"]),
            json.dumps(fields.get("finishes") or ["WHITE"]),
            _decimal_text(fields.get("sliding_glazing_deduction_width_mm")) or "0",
            _decimal_text(fields.get("sliding_glazing_deduction_height_mm")) or "0",
            _decimal_text(fields.get("door_leaf_side_clearance_mm")) or "0",
        ],
    )
    if not found:
        existing = rows(
            "SELECT id FROM public.profile_systems"
            " WHERE org_id=%s AND code=%s",
            [str(org_id), str(fields["code"]).strip().upper()],
        )
        if existing:
            raise contract_error(
                409, "catalog_system_exists",
                "Ya existe un sistema con ese código en tu organización.",
            )
        raise contract_error(
            422, "catalog_system_failed",
            "No se pudo crear el sistema. Revisa los datos de la hoja Sistemas.",
        )
    return UUID(str(found[0]["id"]))


def existing_id(found: list[dict]) -> UUID:
    return UUID(str(found[0]["id"]))


def confirm_catalog_import(
    *, org_id: UUID, actor_id: UUID, import_id: UUID, system_id: UUID | None,
    items: list[dict], new_system: dict | None = None,
    cost_list_id: UUID | None = None,
) -> dict:
    """Human confirm — the only path from candidate to catalog authority.

    One transaction: the import row is locked FOR UPDATE, each article inserts
    under its own savepoint, and per-key outcomes accumulate in ``result`` —
    so a retry replays committed state, a partial failure stays retryable,
    and CONFIRMED only seals once every submitted key has an outcome."""
    with transaction.atomic():
        with documentary_backend():
            found = rows(
                "SELECT * FROM public.catalog_imports WHERE id=%s AND org_id=%s FOR UPDATE",
                [str(import_id), str(org_id)],
            )
        if not found:
            raise CatalogImportError("catalog_import_not_found")
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
                "catalog_import_not_review_ready",
                "La importación aún está procesándose. Espera a que termine.",
            )
        # A retried confirm continues the same target: earlier keys already
        # became articles in the stored system, so switching systems now would
        # split one import across two catalogs.
        if row["system_id"] and system_id and str(row["system_id"]) != str(system_id):
            raise contract_error(
                409,
                "catalog_system_changed",
                "La importación ya tiene artículos en otro sistema; "
                "confirma sobre el mismo sistema.",
            )
        if new_system is not None:
            if row["system_id"]:
                raise contract_error(
                    409, "catalog_system_changed",
                    "La importación ya está ligada a un sistema existente.",
                )
            # The Sistemas sheet becomes an org-owned system in the same
            # transaction; every other entity lands on it. catalog_backend:
            # profile_systems is a catalog table (RLS grants live on the
            # catalog role — without it the INSERT fails SQLSTATE 42501).
            with catalog_backend():
                system_id = _create_system(org_id=org_id, fields=new_system)
        if system_id is None:
            raise contract_error(
                422, "catalog_system_required",
                "Indica el sistema destino o declara uno nuevo en la hoja Sistemas.",
            )
        # Articles on a global/shared system would be visible to every tenant
        # (the select policy opens global systems to all members) — the target
        # must be a system the organization owns.
        system = rows(
            "SELECT id, material, finishes FROM public.profile_systems"
            " WHERE id=%s AND org_id=%s",
            [str(system_id), str(org_id)],
        )
        if not system:
            raise contract_error(
                422,
                "catalog_system_not_tenant",
                "El sistema destino debe pertenecer a tu organización.",
            )
        material = system[0]["material"]
        finish_codes = list(_as_list(system[0].get("finishes")) or [])
        candidates_by_key = {
            str(candidate.get("key")): candidate
            for candidate in _as_list(row["candidates"])
        }
        candidate_keys = set(candidates_by_key)
        created = _as_list(row["result"])
        done = {str(entry.get("key")) for entry in created}
        errors: list[dict] = []
        for item in items:
            key = str(item["key"])
            if key in done:
                continue
            if key not in candidate_keys:
                errors.append({"key": key, "code": "catalog_item_unknown"})
                continue
            candidate = candidates_by_key[key]
            if candidate.get("row_errors"):
                # A row that failed parsing can never be confirmed — fix the
                # file and re-upload; the review keeps the error visible.
                errors.append({"key": key, "code": "catalog_row_invalid"})
                continue
            entity = str(item.get("entity") or candidate.get("entity") or ENTITY_PROFILE)
            if entity == ENTITY_PRICE:
                if cost_list_id is None:
                    errors.append({"key": key, "code": "catalog_price_list_required"})
                    continue
                # Las columnas de la hoja Precios viajan dentro de `fields` —
                # el item top-level solo lleva key/entity/sku/name.
                price_fields = dict(item.get("fields") or candidate.get("fields") or {})
                try:
                    with transaction.atomic(), catalog_backend():
                        inserted = rows(
                            "INSERT INTO public.cost_list_items("
                            "cost_list_id, org_id, sku, item_type, unit, unit_cost)"
                            " VALUES(%s,%s,%s,%s,%s,%s)"
                            " ON CONFLICT (cost_list_id, sku) DO NOTHING RETURNING id",
                            [
                                str(cost_list_id), str(org_id),
                                str(
                                    price_fields.get("purchase_sku") or item["sku"]
                                ).strip().upper(),
                                str(price_fields.get("item_type") or "PROFILE"),
                                str(price_fields.get("unit") or "BAR"),
                                str(price_fields["unit_cost"]),
                            ],
                        )
                except (DatabaseError, KeyError):
                    errors.append({"key": key, "code": "catalog_insert_failed"})
                    continue
                if not inserted:
                    errors.append({"key": key, "code": "catalog_sku_conflict"})
                    continue
                created.append({"key": key, "item_id": str(inserted[0]["id"])})
                done.add(key)
                continue
            if entity == ENTITY_FINISH:
                finish_fields = dict(
                    item.get("fields") or candidate.get("fields") or {}
                )
                code = str(
                    finish_fields.get("finish_code") or item.get("sku") or ""
                ).strip().upper()
                if not code:
                    errors.append({"key": key, "code": "catalog_item_unknown"})
                    continue
                finish_codes.append(code)
                created.append({"key": key, "finish_code": code})
                done.add(key)
                continue
            if entity == "SYSTEM":
                # The Sistemas row was realized via new_system before the
                # loop — the item just records the outcome.
                created.append({"key": key, "entity": entity, "id": str(system_id)})
                done.add(key)
                continue
            if entity != ENTITY_PROFILE:
                if entity not in ENTITIES:
                    errors.append({"key": key, "code": "catalog_entity_unknown"})
                    continue
                fields = dict(item.get("fields") or candidate.get("fields") or {})
                try:
                    with transaction.atomic(), catalog_backend():
                        inserted = _insert_entity_row(
                            org_id=org_id, system_id=system_id,
                            entity=entity, fields=fields,
                        )
                except CatalogImportError as error:
                    errors.append({"key": key, "code": error.code})
                    continue
                except (DatabaseError, KeyError, ValueError):
                    errors.append({"key": key, "code": "catalog_insert_failed"})
                    continue
                if inserted is None:
                    errors.append({"key": key, "code": "catalog_sku_conflict"})
                    continue
                created.append({"key": key, "entity": entity, "id": str(inserted[1])})
                done.add(key)
                continue
            sku = str(item.get("sku") or "").strip().upper()
            role = str(item.get("role") or "").upper()
            name = str(item.get("name") or "").strip() or sku
            if not sku or item.get("face_width_mm") is None:
                errors.append({"key": key, "code": "catalog_field_required"})
                continue
            if role not in ROLES:
                errors.append({"key": key, "code": "catalog_role_invalid"})
                continue
            try:
                # The API stamps provenance — members cannot write it, so the
                # insert runs under catalog_backend inside the same org/user
                # RLS claims. review_pending=TRUE keeps the import honest: the
                # confirm matched a parser candidate, but a human has not
                # reviewed the technical row yet — readiness flags it until
                # they do (CAT-10: a confirm click is not a review stamp).
                with transaction.atomic(), catalog_backend():
                    inserted = rows(
                        "INSERT INTO public.profile_articles("
                        "system_id, org_id, sku, name, role, material, face_width_mm,"
                        " commercial_length_mm, welding_loss_mm, reinforcement_sku,"
                        " weight_kg_m, steel_weight_kg_m, data_provenance,"
                        " review_pending)"
                        " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'IMPORT',TRUE)"
                        " ON CONFLICT (system_id, sku) DO NOTHING"
                        " RETURNING id",
                        [
                            str(system_id),
                            str(org_id),
                            sku,
                            name,
                            role,
                            material,
                            str(item["face_width_mm"]),
                            _numeric_or_none(item.get("commercial_length_mm")),
                            _numeric_or_none(item.get("welding_loss_mm")),
                            (str(item["reinforcement_sku"]).strip() or None)
                            if item.get("reinforcement_sku")
                            else None,
                            _numeric_or_none(item.get("weight_kg_m")),
                            _numeric_or_none(item.get("steel_weight_kg_m")),
                        ],
                    )
            except DatabaseError as error:
                code = (
                    "catalog_singleton_role_conflict"
                    if "catalog_singleton_role_conflict" in str(error)
                    else "catalog_insert_failed"
                )
                errors.append({"key": key, "code": code})
                continue
            if not inserted:
                errors.append({"key": key, "code": "catalog_sku_conflict"})
                continue
            article_id = inserted[0]["id"]
            # Pin the parser's per-field evidence to the created article —
            # the confirming member is the declarer, the document the import.
            catalog_evidence.stamp_import_evidence(
                org_id=org_id,
                actor_id=actor_id,
                import_id=import_id,
                article_id=article_id,
                candidate={
                    **(candidates_by_key.get(key) or {}),
                    "source_document": f"{row['file_name']} (import {import_id})",
                },
            )
            created.append({"key": key, "article_id": str(article_id)})
            done.add(key)
        # FINISH items landed as accumulated codes — merge them into the
        # system's declared finishes in the same transaction.
        pending_finishes = sorted(set(finish_codes))
        if any(str(item.get("entity") or "") == ENTITY_FINISH for item in items):
            with catalog_backend():
                # RETURNING id: rows() is SELECT-only — a bare UPDATE crashes
                # on cursor.description=None.
                rows(
                    "UPDATE public.profile_systems SET finishes=%s::jsonb"
                    " WHERE id=%s AND org_id=%s RETURNING id",
                    [json.dumps(pending_finishes), str(system_id), str(org_id)],
                )
        if errors:
            # Retryable: persist what was created so the next confirm only
            # attempts the still-unresolved keys.
            with documentary_backend():
                updated = rows(
                    "UPDATE public.catalog_imports SET result=%s::jsonb, "
                    "system_id=%s, updated_at=now() WHERE id=%s RETURNING *",
                    [json.dumps(created), str(system_id), str(import_id)],
                )[0]
            return {
                "import": _public(updated),
                "created": created,
                "errors": errors,
            }
        with documentary_backend():
            updated = rows(
                "UPDATE public.catalog_imports SET status='CONFIRMED', "
                "result=%s::jsonb, system_id=%s, updated_at=now() "
                "WHERE id=%s RETURNING *",
                [json.dumps(created), str(system_id), str(import_id)],
            )[0]
    return {"import": _public(updated), "created": created, "errors": []}
