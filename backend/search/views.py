"""Global search surface — read-only, deterministic, org-scoped."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from documents.views import ERRORS, documentary_scope
from search import service
from search.serializers import SearchResponseSerializer

_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER")


class GlobalSearchView(APIView):
    @extend_schema(
        operation_id="global_search",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(name="q", type=str, location="query", required=True),
        ],
        request=None,
        responses={200: SearchResponseSerializer, **ERRORS},
        tags=["search"],
    )
    def get(self, request):
        query = request.query_params.get("q", "")
        with documentary_scope(request, _READERS) as (_, tenant, org_id):
            output = service.search(
                org_id=org_id,
                query=query,
                role=tenant.active_organization.role,
            )
        return Response(output)
