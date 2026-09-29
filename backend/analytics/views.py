"""Read-only operational analytics surface."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from documents.views import ERRORS, documentary_scope
from analytics import service
from analytics.serializers import OperationalSummarySerializer

_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")


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
