"""Immutable artifact slot generation and tenant-checked signed access."""

from __future__ import annotations

import logging
from uuid import UUID

from django.db import connection, transaction

from dekopen_engine.documentary_canonical import (
    documentary_sha256_v1,
    file_sha256,
    snapshot_sha256_v1,
)

from documents.renderers import render_pdf_document
from documents.repository import DocumentaryError, decoded, documentary_backend, one, rows
from documents.storage import SIGNED_URL_TTL_SECONDS, SupabaseDocumentStorage
from documents.xlsx import render_order_xlsx


logger = logging.getLogger(__name__)

_REVISION_DOCUMENTS = {"DOC-01", "DOC-03", "DOC-05", "DOC-06", "DOC-07"}
_ORDER_DOCUMENTS = {"DOC-02", "DOC-04", "DOC-08"}
_DOCUMENT_ROLES = {
    "DOC-01": {"OWNER", "ESTIMATOR"},
    "DOC-02": {"OWNER", "WORKSHOP_MANAGER"},
    "DOC-03": {"OWNER", "WORKSHOP_MANAGER"},
    "DOC-04": {"OWNER", "WORKSHOP_MANAGER"},
    "DOC-05": {"OWNER", "WORKSHOP_MANAGER"},
    "DOC-06": {"OWNER", "WORKSHOP_MANAGER"},
    "DOC-07": {"OWNER"},
    "DOC-08": {"OWNER", "WORKSHOP_MANAGER"},
}


def _require_document_role(document_type: str, role: str) -> None:
    if role not in _DOCUMENT_ROLES.get(document_type, set()):
        raise DocumentaryError("document_access_denied")


def _metadata(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "artifact_scope": row["artifact_scope"],
        "artifact_scope_id": str(row["artifact_scope_id"]),
        "document_type": row["document_type"],
        "format": row["format"],
        "bom_hash": row["bom_hash"],
        "file_sha256": row["file_sha256"],
        "byte_size": row["byte_size"],
        "created_at": row["created_at"],
    }


def _revision_snapshot(
    project_version_id: UUID, org_id: UUID
) -> tuple[dict[str, object], dict[str, object]]:
    version = one(
        "SELECT id,project_id,org_id,revision_code,authority_version,snapshot_json::text,"
        "bom_hash,snapshot_sha256,production_allowed,documentary_complete,"
        "emitted_by,emitted_at "
        "FROM public.project_versions WHERE id=%s AND org_id=%s",
        [project_version_id, org_id],
        "project_version_not_found",
    )
    if version["authority_version"] not in ("SHOT09_V1", "SHOT10_V1"):
        raise DocumentaryError("legacy_version_not_eligible")
    snapshot = decoded(version["snapshot_json"])
    if not isinstance(snapshot, dict) or not all(isinstance(key, str) for key in snapshot):
        raise DocumentaryError("invalid_frozen_revision_snapshot")
    if snapshot_sha256_v1(snapshot) != str(version["snapshot_sha256"]):
        raise DocumentaryError("frozen_revision_hash_mismatch")
    return version, snapshot


def _order_snapshot(order_id: UUID, project_version_id: UUID, org_id: UUID) -> tuple[
    dict[str, object], dict[str, object]
]:
    order = one(
        "SELECT id,project_id,project_version_id,org_id,order_type::text,order_code,status,"
        "supplier_name,payload_json::text,bom_hash,revision_snapshot_sha256,"
        "order_snapshot_hash,confirmed_at,expected_at,sent_at FROM public.orders "
        "WHERE id=%s AND project_version_id=%s AND org_id=%s",
        [order_id, project_version_id, org_id],
        "order_not_found",
    )
    snapshot = decoded(order["payload_json"])
    if not isinstance(snapshot, dict) or not all(isinstance(key, str) for key in snapshot):
        raise DocumentaryError("invalid_order_snapshot")
    if documentary_sha256_v1(snapshot) != str(order["order_snapshot_hash"]):
        raise DocumentaryError("order_snapshot_hash_mismatch")
    # Live order fields overlay the sealed snapshot for display only — the
    # hash check above already pinned line content; expected_at is set at
    # send time, after the snapshot was sealed at confirmation.
    order_block = snapshot.get("order")
    if isinstance(order_block, dict):
        order_block["expected_at"] = (
            None if order["expected_at"] is None else str(order["expected_at"])
        )
        order_block["sent_at"] = (
            None if order["sent_at"] is None else str(order["sent_at"])
        )
    return order, snapshot


def generate_artifact(
    *, org_id: UUID, actor_id: UUID, role: str, project_version_id: UUID,
    order_id: UUID | None, document_type: str, file_format: str,
) -> tuple[dict[str, object], bool]:
    _require_document_role(document_type, role)
    if document_type in _REVISION_DOCUMENTS:
        if order_id is not None or file_format != "PDF":
            raise DocumentaryError("document_scope_mismatch")
        scope = "PROJECT_REVISION"
        scope_id = project_version_id
    elif document_type in _ORDER_DOCUMENTS:
        if order_id is None or (document_type == "DOC-02" and file_format != "XLSX"):
            raise DocumentaryError("document_scope_mismatch")
        if document_type in ("DOC-04", "DOC-08") and file_format not in ("PDF", "XLSX"):
            raise DocumentaryError("document_scope_mismatch")
        scope = "ORDER"
        scope_id = order_id
    else:
        raise DocumentaryError("document_type_invalid")

    slot = f"{scope_id}:{document_type}:{file_format}"
    storage: SupabaseDocumentStorage | None = None
    object_key: str | None = None
    try:
        with transaction.atomic(), documentary_backend():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    [slot],
                )
            # Authority and binding are validated before any slot reuse: an
            # occupied slot never authorizes the request.
            version, frozen_revision = _revision_snapshot(project_version_id, org_id)
            if document_type in ("DOC-02", "DOC-03", "DOC-04", "DOC-05", "DOC-06", "DOC-08"):
                if version.get("production_allowed") is not True:
                    raise DocumentaryError("production_document_blocked")
                if version.get("documentary_complete") is not True:
                    raise DocumentaryError("manufacturing_document_incomplete")
            order: dict[str, object] | None = None
            frozen: dict[str, object] = frozen_revision
            if order_id is not None:
                order, frozen = _order_snapshot(order_id, project_version_id, org_id)
            existing = rows(
                "SELECT * FROM public.document_artifacts "
                "WHERE org_id=%s AND project_version_id=%s AND artifact_scope=%s "
                "AND artifact_scope_id=%s AND document_type=%s AND format=%s",
                [org_id, project_version_id, scope, scope_id, document_type, file_format],
            )
            if existing:
                if len(existing) != 1:
                    raise DocumentaryError("artifact_slot_ambiguous")
                return _metadata(existing[0]), False
            identifier = (
                str(version["snapshot_sha256"])
                if order is None else str(order["order_snapshot_hash"])
            )
            if file_format == "PDF":
                content, media_type = render_pdf_document(
                    document_type, frozen, pdf_identifier=identifier
                )
                extension = "pdf"
            else:
                content, media_type = render_order_xlsx(document_type, frozen)
                extension = "xlsx"
            content_hash = file_sha256(content)
            object_key = (
                f"org_{org_id}/projects/{version['project_id']}/{version['revision_code']}/"
                f"{document_type.lower()}_{file_format.lower()}_{content_hash}.{extension}"
            )
            storage = SupabaseDocumentStorage()
            storage.upload_immutable(object_key, content, media_type)
            artifact = one(
                "INSERT INTO public.document_artifacts("
                "org_id,project_id,project_version_id,order_id,order_type,artifact_scope,"
                "artifact_scope_id,document_type,format,bom_hash,revision_snapshot_sha256,"
                "storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'documents',%s,%s,%s,%s,%s) "
                "RETURNING *",
                [org_id, version["project_id"], project_version_id, order_id,
                 None if order is None else order["order_type"], scope, scope_id,
                 document_type, file_format, version["bom_hash"], version["snapshot_sha256"],
                 object_key, content_hash, media_type, len(content), actor_id],
            )
            return _metadata(artifact), True
    except Exception:
        if storage is not None and object_key is not None:
            _delete_unreferenced_object(
                org_id=org_id, storage=storage, object_key=object_key, slot=slot
            )
        raise


def _delete_unreferenced_object(
    *, org_id: UUID, storage: SupabaseDocumentStorage, object_key: str, slot: str
) -> None:
    # The compensating delete serializes on the same deterministic slot lock as
    # generation: a committed artifact that references the object wins, an
    # unreferenced orphan is removed, and a later generator re-uploads freely.
    try:
        with transaction.atomic(), documentary_backend():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    [slot],
                )
            referenced = rows(
                "SELECT id FROM public.document_artifacts "
                "WHERE org_id=%s AND storage_object_key=%s",
                [org_id, object_key],
            )
            if referenced:
                return
            storage.delete_object(object_key)
    except Exception as cleanup_error:
        detail = getattr(cleanup_error, "code", None)
        if not isinstance(detail, str):
            detail = getattr(getattr(cleanup_error, "__cause__", None), "sqlstate", None)
        logger.warning(
            "document_artifact_cleanup_failed",
            extra={
                "artifact_slot": slot,
                "storage_object_key": object_key,
                "cleanup_error": (
                    detail if isinstance(detail, str) else type(cleanup_error).__name__
                ),
            },
        )


def signed_artifact_access(
    *, org_id: UUID, artifact_id: UUID, role: str
) -> tuple[dict[str, object], dict[str, object]]:
    with documentary_backend():
        artifact = one(
            "SELECT * FROM public.document_artifacts WHERE id=%s AND org_id=%s",
            [artifact_id, org_id],
            "artifact_not_found",
        )
    _require_document_role(str(artifact["document_type"]), role)
    signed_url = SupabaseDocumentStorage().signed_url(str(artifact["storage_object_key"]))
    return artifact, {
        "artifact_id": str(artifact_id),
        "signed_url": signed_url,
        "expires_in": SIGNED_URL_TTL_SECONDS,
    }
