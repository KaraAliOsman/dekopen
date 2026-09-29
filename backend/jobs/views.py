"""HTTP surface for the durable job queue: enqueue, status, recent list."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from uuid import UUID

from django.db import DatabaseError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.rls import authenticated_rls_context
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from authentication.tenancy import (
    MembershipRepository,
    enforce_owner_mfa,
    resolve_tenant_context,
)
from authentication.views import verified_request_token
from jobs import registry, service
from jobs.serializers import (
    JobEnqueueSerializer,
    JobListQuerySerializer,
    JobRunSerializer,
)

logger = logging.getLogger(__name__)


def validate(serializer_type, data):
    serializer = serializer_type(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


@contextmanager
def public_job_errors():
    try:
        yield
    except service.JobServiceError as error:
        if error.code == "job_type_unknown":
            raise contract_error(
                422, error.code, "Tipo de trabajo no disponible."
            ) from error
        if error.code == "job_permission_denied":
            raise contract_error(
                403, error.code, "Tu rol no permite encolar este trabajo."
            ) from error
        if error.code == "job_not_found":
            raise contract_error(
                404, error.code, "Trabajo no encontrado."
            ) from error
        if error.code == "job_not_terminal":
            raise contract_error(
                409,
                error.code,
                "Solo se reintenta un trabajo fallido o cancelado.",
            ) from error
        raise contract_error(
            422, error.code, "Revisa los parámetros del trabajo."
        ) from error
    except serializers.ValidationError as error:
        raise contract_error(
            422, "job_payload_invalid", "Revisa los parámetros del trabajo."
        ) from error
    except DatabaseError as error:
        logger.warning("Job transaction rejected (%s)", type(error).__name__)
        raise contract_error(
            409,
            "job_transaction_rejected",
            "El trabajo entró en conflicto; reintenta la operación.",
        ) from error


@contextmanager
def job_scope(request, allowed: tuple[str, ...] | None = None):
    """Verify the token + tenant inside RLS, then yield OUTSIDE it: job_runs
    is a service-owned table reached as the connection owner with an explicit
    org filter (same pattern as payment_events)."""
    token = verified_request_token(request)
    with authenticated_rls_context(token.claims):
        tenant = resolve_tenant_context(
            MembershipRepository().list_active_for_user(token.user_id),
            request.headers.get("X-Organization-ID"),
        )
        enforce_owner_mfa(tenant, token.aal)
        if allowed is not None and tenant.active_organization.role not in allowed:
            raise contract_error(
                403,
                "job_permission_denied",
                "Tu rol no permite realizar esta operación.",
            )
    yield token, tenant, tenant.active_organization.organization_id


# Read-side gate: job payloads and results are service-owned JSON that may
# embed commercial detail, so reads are limited to the roles every job spec
# is authorized for (no spec is ever enqueued as INSTALLER).
_JOB_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")


class JobListCreateView(APIView):
    @extend_schema(
        operation_id="jobs_list",
        parameters=[ACTIVE_ORGANIZATION_HEADER, JobListQuerySerializer],
        request=None,
        responses={200: JobRunSerializer(many=True)},
        tags=["jobs"],
    )
    def get(self, request):
        query = validate(JobListQuerySerializer, request.query_params)
        with public_job_errors():
            with job_scope(request, _JOB_READERS) as (_, _, org_id):
                items = service.list_recent(
                    org_id=org_id,
                    job_type=query.get("type"),
                    state=query.get("state"),
                    limit=query.get("limit", 50),
                    offset=query.get("offset", 0),
                )
        return Response(JobRunSerializer(items, many=True).data)

    @extend_schema(
        operation_id="jobs_enqueue",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=JobEnqueueSerializer,
        responses={200: JobRunSerializer, 201: JobRunSerializer},
        tags=["jobs"],
    )
    def post(self, request):
        data = validate(JobEnqueueSerializer, request.data)
        spec = registry.spec_for(data["type"])
        if spec is None:
            raise contract_error(
                422, "job_type_unknown", "Tipo de trabajo no disponible."
            )
        with public_job_errors():
            with job_scope(request) as (token, tenant, org_id):
                if tenant.active_organization.role not in spec.roles:
                    raise contract_error(
                        403,
                        "job_permission_denied",
                        "Tu rol no permite encolar este trabajo.",
                    )
                job, created = service.enqueue(
                    org_id=org_id,
                    job_type=data["type"],
                    payload=data["payload"],
                    idempotency_key=data.get("idempotency_key"),
                    max_attempts=data.get("max_attempts", 3),
                    created_by=token.user_id,
                    role=tenant.active_organization.role,
                )
        return Response(JobRunSerializer(job).data, status=201 if created else 200)


class JobDetailView(APIView):
    @extend_schema(
        operation_id="jobs_get",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: JobRunSerializer},
        tags=["jobs"],
    )
    def get(self, request, job_id: UUID):
        with public_job_errors():
            with job_scope(request, _JOB_READERS) as (_, _, org_id):
                job = service.get(org_id=org_id, job_id=job_id)
        if job is None:
            raise contract_error(404, "job_not_found", "Trabajo no encontrado.")
        return Response(JobRunSerializer(job).data)


class JobRetryView(APIView):
    @extend_schema(
        operation_id="jobs_retry",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: JobRunSerializer},
        tags=["jobs"],
    )
    def post(self, request, job_id: UUID):
        with public_job_errors():
            with job_scope(request) as (token, tenant, org_id):
                job = service.retry(
                    org_id=org_id,
                    job_id=job_id,
                    actor_id=token.user_id,
                    role=tenant.active_organization.role,
                )
        return Response(JobRunSerializer(job).data)
