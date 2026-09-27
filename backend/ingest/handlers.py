"""Extraction job — document bytes become reviewable candidates off-request."""

from __future__ import annotations

from typing import Any

from django.db import connection

from authentication.rls import worker_claims
from jobs.handlers import _claims_for
from jobs.registry import JobContext, JobPermanentError, ProgressReporter, register
from ingest.serializers import ExtractPayloadSerializer


# roles mirror the REST writer sets (document extract: _WRITERS; catalog
# extract: _CATALOG_WRITERS) — a job spec must not widen the API's ACL.
@register(
    "ingest.document.extract",
    roles=("OWNER", "ESTIMATOR"),
    payload_serializer=ExtractPayloadSerializer,
    label="Extraer posiciones del documento",
)
def extract_document_job(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    from ingest.service import ImportError_, extract_for_import, mark_import_failed

    if context.created_by is None:
        raise ValueError("job_requires_actor")
    report(10)
    # Claims must live for the whole run — the extract marks the import
    # EXTRACTING/REVIEW_READY under documentary_backend RLS, which reads
    # org_id from auth.uid(). Transaction-local claims evaporate the moment
    # the membership check commits, so the GUC goes session-scoped instead.
    try:
        with worker_claims(_claims_for(str(context.created_by), context)):
            with connection.cursor() as cursor:
                # Any active membership is not enough — a demoted uploader
                # must not spend OCR credits or write imports through a
                # queued job.
                cursor.execute(
                    "SELECT 1 FROM public.tenancy_memberships "
                    "WHERE user_id=%s AND org_id=%s AND is_active "
                    "AND role IN ('OWNER','ESTIMATOR')",
                    [str(context.created_by), str(context.org_id)],
                )
                member = cursor.fetchone()
            if member is None:
                raise ImportError_("import_membership_revoked")
            # The provider call and its audit/debit commit independently —
            # no handler-wide transaction may wrap them, or a retry re-bills
            # OCR.
            output = extract_for_import(
                org_id=context.org_id,
                import_id=payload["import_id"],
                actor_id=context.created_by,
            )
    except Exception as error:
        permanent = isinstance(error, ImportError_)
        if permanent or context.attempt >= context.max_attempts:
            # Terminal failure — the import must reach FAILED so the UI stops
            # polling; recorded outside the failed transaction so it survives.
            code = error.code if permanent else "import_extract_failed"
            try:
                with worker_claims(_claims_for(str(context.created_by), context)):
                    mark_import_failed(
                        org_id=context.org_id,
                        import_id=payload["import_id"],
                        code=code,
                    )
            except Exception:  # noqa: BLE001 — job_runs already records the error
                pass
        if permanent:
            raise JobPermanentError(error.code) from error
        raise
    report(95)
    return output


@register(
    "ingest.catalog.extract",
    roles=("OWNER", "WORKSHOP_MANAGER"),
    payload_serializer=ExtractPayloadSerializer,
    label="Extraer artículos del catálogo",
)
def extract_catalog_job(
    payload: dict[str, Any], context: JobContext, report: ProgressReporter
) -> dict[str, Any]:
    from ingest.catalog_service import (
        CatalogImportError,
        extract_catalog_import,
        mark_catalog_import_failed,
    )

    if context.created_by is None:
        raise ValueError("job_requires_actor")
    report(10)
    # Same session-scoped claims as the document extractor — a closed
    # transaction-local GUC left catalog imports stuck at UPLOADED forever
    # (RLS saw empty org ids and matched zero rows).
    try:
        with worker_claims(_claims_for(str(context.created_by), context)):
            with connection.cursor() as cursor:
                # Any active membership is not enough — a demoted uploader
                # must not spend compile credits or write articles through a
                # queued job.
                cursor.execute(
                    "SELECT 1 FROM public.tenancy_memberships "
                    "WHERE user_id=%s AND org_id=%s AND is_active "
                    "AND role IN ('OWNER','WORKSHOP_MANAGER')",
                    [str(context.created_by), str(context.org_id)],
                )
                member = cursor.fetchone()
            if member is None:
                raise CatalogImportError("catalog_membership_revoked")
            output = extract_catalog_import(
                org_id=context.org_id,
                import_id=payload["import_id"],
                actor_id=context.created_by,
            )
    except Exception as error:
        permanent = isinstance(error, CatalogImportError)
        if permanent or context.attempt >= context.max_attempts:
            code = error.code if permanent else "catalog_extract_failed"
            try:
                with worker_claims(_claims_for(str(context.created_by), context)):
                    mark_catalog_import_failed(
                        org_id=context.org_id,
                        import_id=payload["import_id"],
                        code=code,
                    )
            except Exception:  # noqa: BLE001 — job_runs already records the error
                pass
        if permanent:
            raise JobPermanentError(error.code) from error
        raise
    report(95)
    return output
