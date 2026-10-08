"""HTTP edge for the field/despacho/postventa surface (P23).

Same contract style as production/views.py: documentary_scope for role
gating, public_production_errors for error mapping, StrictSerializer
request/response contracts. Roles:

  _READERS            — todo rol lee planificación, agenda e incidencias.
  _DISPATCH_WRITERS   — OWNER / WORKSHOP_MANAGER planifican viajes,
                        cuadrillas y resuelven incidencias.
  _FIELD_ACTORS       — OWNER / WORKSHOP_MANAGER / INSTALLER escriben
                        mediciones de obra, checklists y evidencia.
  _TICKET_WRITERS     — OWNER / WORKSHOP_MANAGER / ESTIMATOR abren y
                        mueven tickets de postventa.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from documents.views import ERRORS, documentary_scope, validate
from production.serializers import DeliveryResponseSerializer
from production.views import ACTIVE_ORGANIZATION_HEADER, public_production_errors

from . import checklists, incidents, measurements, service, tickets
from .serializers import (
    DispatchPlanSerializer,
    DispatchScheduleSerializer,
    FieldAgendaSerializer,
    FieldCrewListSerializer,
    FieldCrewRequestSerializer,
    FieldOrderCardSerializer,
    IncidentListSerializer,
    IncidentReportResponseSerializer,
    IncidentRequestSerializer,
    IncidentResolveRequestSerializer,
    IncidentResolveResponseSerializer,
    InstallationCheckRequestSerializer,
    InstallationCheckResponseSerializer,
    LoadCheckRequestSerializer,
    LoadCheckResponseSerializer,
    PhotoAccessSerializer,
    PhotoUploadRequestSerializer,
    PhotoUploadResponseSerializer,
    PurchaseRequestListSerializer,
    PurchaseRequestMarkSerializer,
    PurchaseTransitionResponseSerializer,
    ServiceTicketListSerializer,
    ServiceTicketRequestSerializer,
    ServiceTicketResponseSerializer,
    ServiceTicketTransitionSerializer,
    SiteMeasurementRequestSerializer,
    SiteMeasurementResponseSerializer,
)
from .evidence import evidence_access, upload_evidence

_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER", "OPERATOR")
_DISPATCH_WRITERS = ("OWNER", "WORKSHOP_MANAGER")
_FIELD_ACTORS = ("OWNER", "WORKSHOP_MANAGER", "INSTALLER")
_TICKET_WRITERS = ("OWNER", "WORKSHOP_MANAGER", "ESTIMATOR")


def _optional_date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise contract_error(400, "invalid_date", "La fecha debe ser aaaa-mm-dd.")


class FieldCrewsView(APIView):
    @extend_schema(
        operation_id="field_crews_list",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: FieldCrewListSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(service.list_crews(org_id=org_id))

    @extend_schema(
        operation_id="field_crews_save",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=FieldCrewRequestSerializer,
        responses={200: FieldCrewListSerializer, **ERRORS},
        tags=["field"],
    )
    def put(self, request):
        data = validate(FieldCrewRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _DISPATCH_WRITERS) as (_, _, org_id):
                return Response(service.save_crew(org_id=org_id, data=data))


class DispatchPlanView(APIView):
    @extend_schema(
        operation_id="field_dispatch_plan",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "start", OpenApiTypes.DATE, location=OpenApiParameter.QUERY,
                required=False,
                description="Primer día del tablero; hoy por defecto",
            ),
            OpenApiParameter(
                "days", OpenApiTypes.INT, location=OpenApiParameter.QUERY,
                required=False,
                description="Días a proyectar (1-14; 5 por defecto)",
            ),
        ],
        request=None,
        responses={200: DispatchPlanSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request):
        start = _optional_date(request.query_params.get("start"))
        try:
            days = int(request.query_params.get("days") or 5)
        except ValueError:
            days = 5
        days = min(max(days, 1), 14)
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(
                    service.dispatch_plan(org_id=org_id, start=start, days=days)
                )


class DispatchScheduleView(APIView):
    """Atajo del tablero: agenda o reasigna el viaje de una OT sin abrir
    su ficha (mismo primitive que production_delivery_schedule)."""

    @extend_schema(
        operation_id="field_dispatch_schedule",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=DispatchScheduleSerializer,
        responses={200: DeliveryResponseSerializer, **ERRORS},
        tags=["field"],
    )
    def put(self, request):
        data = validate(DispatchScheduleSerializer, request.data)
        from production.service import schedule_delivery

        with public_production_errors():
            with documentary_scope(request, _DISPATCH_WRITERS) as (token, _, org_id):
                output = schedule_delivery(
                    org_id=org_id,
                    order_id=data["order_id"],
                    actor_id=token.user_id,
                    scheduled_date=str(data["scheduled_date"]),
                    time_window=str(data.get("time_window") or "AM"),
                    address=str(data["address"]),
                    contact_name=data.get("contact_name"),
                    contact_phone=data.get("contact_phone"),
                    installer_name=data.get("installer_name"),
                    installer_user_id=data.get("installer_user_id"),
                    crew_id=data.get("crew_id"),
                    route_order=data.get("route_order"),
                    notes=data.get("notes"),
                    unit_indexes=data.get("unit_indexes"),
                )
        return Response(output)


class FieldAgendaView(APIView):
    @extend_schema(
        operation_id="field_agenda",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "day", OpenApiTypes.DATE, location=OpenApiParameter.QUERY,
                required=False, description="Día consultado; hoy por defecto",
            ),
            OpenApiParameter(
                "mine", OpenApiTypes.BOOL, location=OpenApiParameter.QUERY,
                required=False,
                description="true limita a paradas asignadas al usuario",
            ),
        ],
        request=None,
        responses={200: FieldAgendaSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request):
        day = _optional_date(request.query_params.get("day"))
        mine = str(request.query_params.get("mine") or "").lower() in (
            "1", "true", "yes",
        )
        with public_production_errors():
            with documentary_scope(request, _READERS) as (token, _, org_id):
                return Response(
                    service.field_agenda(
                        org_id=org_id,
                        user_id=token.user_id,
                        day=day,
                        mine_only=mine,
                    )
                )


class FieldOrderCardView(APIView):
    @extend_schema(
        operation_id="field_order_card",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: FieldOrderCardSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(
                    service.field_order_card(org_id=org_id, order_id=order_id)
                )


class FieldMeasurementView(APIView):
    @extend_schema(
        operation_id="field_measurement_submit",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=SiteMeasurementRequestSerializer,
        responses={
            200: SiteMeasurementResponseSerializer,
            201: SiteMeasurementResponseSerializer,
            **ERRORS,
        },
        tags=["field"],
    )
    def post(self, request, order_id: UUID):
        data = validate(SiteMeasurementRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _FIELD_ACTORS) as (token, _, org_id):
                output = measurements.submit_measurement(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    position_id=data["position_id"],
                    operation_key=data["operation_key"],
                    vano=data.get("vano"),
                    mounting_rule_id=data.get("mounting_rule_id"),
                    notes=data.get("notes"),
                    photos=data.get("photos"),
                )
        return Response(output, status=200 if output.get("replayed") else 201)


class FieldChecklistView(APIView):
    @extend_schema(
        operation_id="field_checklist_save",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=InstallationCheckRequestSerializer,
        responses={
            200: InstallationCheckResponseSerializer,
            201: InstallationCheckResponseSerializer,
            **ERRORS,
        },
        tags=["field"],
    )
    def put(self, request, order_id: UUID):
        data = validate(InstallationCheckRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _FIELD_ACTORS) as (token, _, org_id):
                output = checklists.save_check(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    unit_index=data.get("unit_index"),
                    items=data.get("items") or {},
                    notes=data.get("notes"),
                    photos=data.get("photos"),
                    operation_key=data.get("operation_key"),
                )
        return Response(output, status=200 if output.get("replayed") else 201)


class FieldLoadCheckView(APIView):
    @extend_schema(
        operation_id="field_load_check",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=LoadCheckRequestSerializer,
        responses={200: LoadCheckResponseSerializer, **ERRORS},
        tags=["field"],
    )
    def post(self, request, delivery_id: UUID):
        data = validate(LoadCheckRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _FIELD_ACTORS) as (token, _, org_id):
                return Response(
                    service.load_check(
                        org_id=org_id,
                        delivery_id=delivery_id,
                        scanned_codes=list(data["scanned_codes"]),
                        actor_id=token.user_id,
                    )
                )


class FieldIncidentsView(APIView):
    @extend_schema(
        operation_id="field_incidents_list",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "status", OpenApiTypes.STR, location=OpenApiParameter.QUERY,
                required=False,
                description="OPEN, IN_PROGRESS, RESOLVED, CANCELLED",
            ),
            OpenApiParameter(
                "kind", OpenApiTypes.STR, location=OpenApiParameter.QUERY,
                required=False,
                description="DAMAGE, WRONG_MEASURE, MISSING, ADJUSTMENT",
            ),
        ],
        request=None,
        responses={200: IncidentListSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(
                    incidents.list_incidents(
                        org_id=org_id,
                        status=request.query_params.get("status"),
                        kind=request.query_params.get("kind"),
                    )
                )


class FieldOrderIncidentsView(APIView):
    """Incidencias de una OT: listado propio y reporte desde terreno."""

    @extend_schema(
        operation_id="field_order_incidents_list",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: IncidentListSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(incidents.list_incidents(org_id=org_id, order_id=order_id))

    @extend_schema(
        operation_id="field_incidents_report",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=IncidentRequestSerializer,
        responses={
            200: IncidentReportResponseSerializer,
            201: IncidentReportResponseSerializer,
            **ERRORS,
        },
        tags=["field"],
    )
    def post(self, request, order_id: UUID):
        data = validate(IncidentRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _FIELD_ACTORS) as (token, _, org_id):
                output = incidents.report_incident(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    kind=data["kind"],
                    operation_key=data["operation_key"],
                    delivery_id=data.get("delivery_id"),
                    unit_index=data.get("unit_index"),
                    piece_code=data.get("piece_code"),
                    note=data.get("note"),
                    photos=data.get("photos"),
                )
        return Response(output, status=200 if output.get("replayed") else 201)


class FieldIncidentResolveView(APIView):
    @extend_schema(
        operation_id="field_incident_resolve",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=IncidentResolveRequestSerializer,
        responses={200: IncidentResolveResponseSerializer, **ERRORS},
        tags=["field"],
    )
    def post(self, request, incident_id: UUID):
        data = validate(IncidentResolveRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _DISPATCH_WRITERS) as (token, _, org_id):
                output = incidents.resolve_incident(
                    org_id=org_id,
                    incident_id=incident_id,
                    actor_id=token.user_id,
                    resolution_kind=data["resolution_kind"],
                    note=data.get("note"),
                    purchase={
                        "item": data.get("purchase_item"),
                        "quantity": data.get("purchase_quantity"),
                        "unit": data.get("purchase_unit"),
                        "supplier_hint": data.get("purchase_supplier_hint"),
                        "needed_at": data.get("purchase_needed_at"),
                    },
                )
        return Response(output)


class FieldPurchaseRequestsView(APIView):
    @extend_schema(
        operation_id="field_purchase_requests_list",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "status", OpenApiTypes.STR, location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        request=None,
        responses={200: PurchaseRequestListSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(
                    incidents.list_purchase_requests(
                        org_id=org_id,
                        status=request.query_params.get("status"),
                    )
                )


class FieldPurchaseRequestTransitionView(APIView):
    @extend_schema(
        operation_id="field_purchase_request_transition",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=PurchaseRequestMarkSerializer,
        responses={200: PurchaseTransitionResponseSerializer, **ERRORS},
        tags=["field"],
    )
    def post(self, request, request_id: UUID):
        data = validate(PurchaseRequestMarkSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _DISPATCH_WRITERS) as (token, _, org_id):
                return Response(
                    incidents.mark_purchase_request(
                        org_id=org_id,
                        request_id=request_id,
                        status=data["status"],
                        actor_id=token.user_id,
                    )
                )


class ServiceTicketsView(APIView):
    @extend_schema(
        operation_id="service_tickets_list",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "status", OpenApiTypes.STR, location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        request=None,
        responses={200: ServiceTicketListSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(
                    tickets.list_tickets(
                        org_id=org_id,
                        status=request.query_params.get("status"),
                    )
                )


class ProjectServiceTicketsView(APIView):
    """Postventa de una obra: listado filtrado y apertura del ticket."""

    @extend_schema(
        operation_id="project_service_tickets_list",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "status", OpenApiTypes.STR, location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        request=None,
        responses={200: ServiceTicketListSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request, project_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(
                    tickets.list_tickets(
                        org_id=org_id,
                        status=request.query_params.get("status"),
                        project_id=project_id,
                    )
                )

    @extend_schema(
        operation_id="service_tickets_create",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=ServiceTicketRequestSerializer,
        responses={
            200: ServiceTicketResponseSerializer,
            201: ServiceTicketResponseSerializer,
            **ERRORS,
        },
        tags=["field"],
    )
    def post(self, request, project_id: UUID):
        data = validate(ServiceTicketRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _TICKET_WRITERS) as (token, _, org_id):
                output = tickets.create_ticket(
                    org_id=org_id,
                    project_id=project_id,
                    actor_id=token.user_id,
                    kind=data["kind"],
                    description=data["description"],
                    operation_key=data["operation_key"],
                    order_id=data.get("order_id"),
                    unit_index=data.get("unit_index"),
                    piece_code=data.get("piece_code"),
                    incident_id=data.get("incident_id"),
                    diagnosis=data.get("diagnosis"),
                    photos=data.get("photos"),
                    scheduled_visit_at=data.get("scheduled_visit_at"),
                    scheduled_crew_id=data.get("scheduled_crew_id"),
                )
        return Response(output, status=200 if output.get("replayed") else 201)


class ServiceTicketTransitionView(APIView):
    @extend_schema(
        operation_id="service_ticket_transition",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=ServiceTicketTransitionSerializer,
        responses={200: ServiceTicketResponseSerializer, **ERRORS},
        tags=["field"],
    )
    def post(self, request, ticket_id: UUID):
        data = validate(ServiceTicketTransitionSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _TICKET_WRITERS) as (token, _, org_id):
                return Response(
                    tickets.transition_ticket(
                        org_id=org_id,
                        ticket_id=ticket_id,
                        actor_id=token.user_id,
                        to_status=data["status"],
                        scheduled_visit_at=data.get("scheduled_visit_at"),
                        scheduled_crew_id=data.get("scheduled_crew_id"),
                        visit_note=data.get("visit_note"),
                        diagnosis=data.get("diagnosis"),
                        close_note=data.get("close_note"),
                    )
                )


class FieldPhotoView(APIView):
    """Evidencia fotográfica: sube al bucket documents bajo
    ``org_<org>/field/`` y registra el hash para validación cruzada."""

    @extend_schema(
        operation_id="field_photo_upload",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=PhotoUploadRequestSerializer,
        responses={201: PhotoUploadResponseSerializer, **ERRORS},
        tags=["field"],
    )
    def post(self, request):
        data = validate(PhotoUploadRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _FIELD_ACTORS) as (token, _, org_id):
                return Response(
                    upload_evidence(
                        org_id=org_id,
                        actor_id=token.user_id,
                        content_b64=data["content_b64"],
                        label=data.get("label"),
                    ),
                    status=201,
                )

    @extend_schema(
        operation_id="field_photo_access",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "key", OpenApiTypes.STR, location=OpenApiParameter.QUERY,
                required=True,
                description="Clave del objeto devuelta por field_photo_upload",
            ),
        ],
        request=None,
        responses={200: PhotoAccessSerializer, **ERRORS},
        tags=["field"],
    )
    def get(self, request):
        key = str(request.query_params.get("key") or "")
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(evidence_access(org_id=org_id, object_key=key))
