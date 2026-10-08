"""Read-only operational analytics surface."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID

from django.db import DatabaseError
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from documents.views import ERRORS, documentary_scope
from analytics import decision, service, today
from analytics.serializers import (
    AnalyticsOverviewSerializer,
    OperationalSummarySerializer,
    TodayQueueSerializer,
)

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


# ---------------------------------------------------------------------------
# P24 — Analítica de decisión. Las SQLSTATEs que lanzan las funciones
# ``private.analytics_*`` se traducen al contrato de error del API.

_ANALYTICS_ERRORS = {
    "42501": (403, "analytics_forbidden",
              "Tu rol no permite leer la analítica de esta organización."),
    "P0002": (404, "analytics_project_not_found",
              "La obra no existe en esta organización."),
    "22023": (400, "analytics_metric_unknown",
              "Esa métrica no tiene detalle exportable."),
}

_PERIOD_PARAMS = [
    OpenApiParameter(
        "desde", OpenApiTypes.DATE, OpenApiParameter.QUERY,
        description="Primer día del período (AAAA-MM-DD, inclusive).",
    ),
    OpenApiParameter(
        "hasta", OpenApiTypes.DATE, OpenApiParameter.QUERY,
        description="Último día del período (AAAA-MM-DD, inclusive).",
    ),
]


@contextmanager
def _analytics_errors():
    try:
        yield
    except DatabaseError as error:
        sqlstate = getattr(getattr(error, "__cause__", None), "sqlstate", None)
        mapped = _ANALYTICS_ERRORS.get(sqlstate)
        if mapped is None:
            raise
        status, code, detail = mapped
        raise contract_error(status, code, detail) from error


class AnalyticsOverviewView(APIView):
    """Las cuatro secciones del panel en un viaje: ventas, margen real vs.
    cotizado, producción e instalación/postventa, en el período pedido
    (por defecto los últimos 30 días)."""

    @extend_schema(
        operation_id="analytics_overview",
        parameters=[ACTIVE_ORGANIZATION_HEADER, *_PERIOD_PARAMS],
        request=None,
        responses={200: AnalyticsOverviewSerializer, **ERRORS},
        tags=["analytics"],
    )
    def get(self, request):
        desde, hasta = decision.period_from(request.query_params)
        with documentary_scope(request, decision.READER_ROLES) as (_, _, org_id):
            with _analytics_errors():
                output = decision.overview(org_id=org_id, desde=desde, hasta=hasta)
        return Response(output)


class AnalyticsMarginBreakdownView(APIView):
    """Descomposición del margen de una obra (§8): cada causa de la
    diferencia entre lo cotizado y lo real, con los orígenes enlazados."""

    @extend_schema(
        operation_id="analytics_margin_breakdown",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "project_id", OpenApiTypes.UUID, OpenApiParameter.QUERY,
                description="Obra cuyo margen se descompone.", required=True,
            ),
        ],
        request=None,
        responses={200: dict, **ERRORS},
        tags=["analytics"],
    )
    def get(self, request):
        raw = request.query_params.get("project_id")
        try:
            project_id = UUID(raw) if raw else None
        except (ValueError, AttributeError, TypeError):
            project_id = None
        if project_id is None:
            raise contract_error(
                400, "validation_error", "project_id debe ser un UUID."
            )
        with documentary_scope(request, decision.READER_ROLES) as (_, _, org_id):
            with _analytics_errors():
                output = decision.margin_breakdown(
                    org_id=org_id, project_id=project_id
                )
        return Response(output)


class AnalyticsExportView(APIView):
    """El detalle de una métrica como CSV — las mismas filas del drill-down."""

    @extend_schema(
        operation_id="analytics_export",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "metric", OpenApiTypes.STR, OpenApiParameter.QUERY,
                description=f"Métrica: {', '.join(decision.EXPORTABLE)}.",
                required=True,
            ),
            *_PERIOD_PARAMS,
        ],
        request=None,
        responses={200: OpenApiTypes.BINARY, **ERRORS},
        tags=["analytics"],
    )
    def get(self, request):
        metric = request.query_params.get("metric") or ""
        desde, hasta = decision.period_from(request.query_params)
        with documentary_scope(request, decision.READER_ROLES) as (_, _, org_id):
            with _analytics_errors():
                filename, body = decision.export_csv(
                    org_id=org_id, metric=metric, desde=desde, hasta=hasta
                )
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
