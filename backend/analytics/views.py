"""Read-only operational analytics surface."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from documents.views import ERRORS, documentary_scope
from analytics import service, today
from analytics.serializers import OperationalSummarySerializer, TodayQueueSerializer

_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")
# «Hoy» le sirve a los cinco roles — la cola del operario y del instalador
# se arma con los mismos datos de taller que ya pueden leer.
_TODAY_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER", "OPERATOR")


class OperationalSummaryView(APIView):
    @extend_schema(
        operation_id="analytics_operational_summary",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: OperationalSummarySerializer, **ERRORS},
        tags=["analytics"],
    )
    def get(self, request):
        with documentary_scope(request, _READERS) as (_, _, org_id):
            output = service.operational_summary(org_id=org_id)
        # job_runs is a service-owned table: the member-facing RLS context has
        # no grant, so the count runs outside it as the connection owner with
        # the verified org filter — the same pattern as the jobs API.
        output["prep"]["jobs_failed"] = service.failed_jobs_count(org_id=org_id)
        return Response(output)


class TodayQueueView(APIView):
    """La cola «qué tengo que hacer hoy» del rol que entra — una sola
    lectura con los ítems ya fraseados y enlazados por el backend."""

    @extend_schema(
        operation_id="analytics_today_queue",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: TodayQueueSerializer, **ERRORS},
        tags=["analytics"],
    )
    def get(self, request):
        with documentary_scope(request, _TODAY_READERS) as (token, tenant, org_id):
            output = today.today_queue(
                org_id=org_id,
                role=tenant.active_organization.role,
                user_id=token.user_id,
            )
        return Response(output)
