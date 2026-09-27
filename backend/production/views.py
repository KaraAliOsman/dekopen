"""HTTP surface for production: work-order release and floor transitions."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from uuid import UUID

from django.db import DatabaseError
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from pydantic import ValidationError as PydanticValidationError

from authentication.errors import contract_error
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from dekopen_engine.cutting import InvalidCutContract
from documents.repository import DocumentaryError
from documents.views import DOCUMENTARY_ERROR_DETAILS, ERRORS, documentary_scope, validate
from engine_api.repository import SystemNotFound
from production import cnc, service
from production.trace import trace_piece, trace_version, trace_work_order
from production.confirmations import confirmation_access, confirm_delivery
from production.dispatch_notes import dispatch_note_access
from projects import sii, sii_envio
from projects.serializers import (
    SiiEnvioAccessSerializer,
    SiiEnvioSendSerializer,
    SiiEnvioSerializer,
)
from production.serializers import (
    ProductionPrepSerializer,
    DeliveryConfirmRequestSerializer,
    DeliveryConfirmResponseSerializer,
    DeliveryConfirmationAccessSerializer,
    DeliveryResponseSerializer,
    DeliveryScheduleRequestSerializer,
    DeliveryTransitionRequestSerializer,
    CncExportSerializer,
    CncGenerateRequestSerializer,
    CncMachineListSerializer,
    CncMachinePatchSerializer,
    CncMachineRequestSerializer,
    CncMachineSerializer,
    CncProgramListSerializer,
    CncProgramSerializer,
    CncReadinessSerializer,
    CncToolListSerializer,
    CncToolPatchSerializer,
    CncToolRequestSerializer,
    CncToolSerializer,
    CncWorkspaceSerializer,
    DxfExportSerializer,
    OpsExportSerializer,
    DispatchNoteAccessSerializer,
    DispatchNoteDteAccessSerializer,
    DispatchNoteDteEmitSerializer,
    DispatchNoteDteSerializer,
    DispatchNoteVoidSerializer,
    DispatchRequestSerializer,
    InstallationRequestSerializer,
    PackingLabelsSerializer,
    PackingManifestSerializer,
    ProductionOrderTraceSerializer,
    ProductionVersionTraceSerializer,
    ProductionPieceTraceSerializer,
    ProductionStationQueueSerializer,
    ProductionOrderDetailSerializer,
    RemakeRequestSerializer,
    ProductionOrderListSerializer,
    ProductionReleaseSerializer,
    StepTransitionRequestSerializer,
    StepTransitionSerializer,
    WorkCenterListSerializer,
    WorkCenterRequestSerializer,
    WorkCenterSerializer,
    WorkOrderOptimizeCompareRequestSerializer,
    WorkOrderOptimizeCompareSerializer,
    WorkOrderOptimizeRequestSerializer,
    WorkOrderOptimizeSerializer,
)

logger = logging.getLogger(__name__)

_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER", "OPERATOR")
_STEP_ACTORS = ("OWNER", "WORKSHOP_MANAGER", "INSTALLER")
# Station steps are workshop authority — INSTALLER's field role ends at
# delivery/installation confirmation, not at weld/glaze/QC sign-off.
_WORKSHOP_STEP_ACTORS = ("OWNER", "WORKSHOP_MANAGER", "OPERATOR")
_LEDGER_WRITERS = ("OWNER", "ESTIMATOR")
_WRITERS = ("OWNER", "WORKSHOP_MANAGER")


@contextmanager
def public_production_errors():
    try:
        yield
    except DocumentaryError as error:
        status_code = 404 if error.code in ("version_not_found", "work_order_not_found", "production_step_not_found", "delivery_not_found", "delivery_confirmation_not_found") else 422
        raise contract_error(
            status_code,
            error.code,
            error.public_detail
            or DOCUMENTARY_ERROR_DETAILS.get(error.code)
            or "La operación de producción fue rechazada; revisa la orden y el paso.",
            error_extra=error.extra or None,
        ) from error
    except (InvalidCutContract, SystemNotFound, PydanticValidationError) as error:
        logger.warning(
            "Production authority resolution failed (%s: %s)",
            type(error).__name__,
            error,
        )
        raise contract_error(
            422,
            "documentary_authority_required",
            "Falta o no coincide una autoridad técnica necesaria para optimizar la orden.",
            error_extra={"reason": str(error)},
        ) from error
    except serializers.ValidationError as error:
        raise contract_error(
            422, "production_payload_invalid", "Revisa los parámetros de producción."
        ) from error
    except DatabaseError as error:
        logger.warning("Production transaction rejected (%s)", type(error).__name__)
        raise contract_error(
            409,
            "production_transaction_rejected",
            "La operación de producción entró en conflicto; reintenta.",
        ) from error


class ProductionPrepView(APIView):
    @extend_schema(
        operation_id="production_prep",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionPrepSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.production_prep(org_id=org_id)
        return Response(output)


class ProductionReleaseView(APIView):
    @extend_schema(
        operation_id="production_release",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionReleaseSerializer, 201: ProductionReleaseSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, version_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.release_production(
                    org_id=org_id, version_id=version_id, actor_id=token.user_id
                )
        return Response(output, status=201 if output["created"] else 200)


class ProductionOrderListView(APIView):
    @extend_schema(
        operation_id="production_orders",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionOrderListSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.list_production_orders(org_id=org_id)
        return Response(output)


class ProductionOrderDetailView(APIView):
    @extend_schema(
        operation_id="production_order_detail",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionOrderDetailSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.get_work_order(org_id=org_id, order_id=order_id)
        return Response(output)


class ProductionStepTransitionView(APIView):
    @extend_schema(
        operation_id="production_step_transition",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=StepTransitionRequestSerializer,
        responses={200: StepTransitionSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, step_id: UUID):
        data = validate(StepTransitionRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WORKSHOP_STEP_ACTORS) as (token, tenant, org_id):
                output = service.transition_step(
                    org_id=org_id,
                    step_id=step_id,
                    action=data["action"],
                    actor_id=token.user_id,
                    actor_role=str(tenant.active_organization.role),
                    note=data.get("note"),
                    qc_result=data.get("qc_result"),
                    qc_check=data.get("qc_check"),
                    qc_item=data.get("qc_item"),
                    ops_done=data.get("ops_done"),
                )
        return Response(output)


class ProductionOrderRemakeView(APIView):
    @extend_schema(
        operation_id="production_order_remake",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=RemakeRequestSerializer,
        responses={201: ProductionOrderDetailSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(RemakeRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.create_remake(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    note=data.get("note"),
                )
        return Response(output, status=201)


class ProductionOrderCncExportView(APIView):
    @extend_schema(
        operation_id="production_order_cnc_export",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={201: CncExportSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.export_cnc_files(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                )
        return Response(output, status=201)


class ProductionOrderCncFileView(APIView):
    @extend_schema(
        operation_id="production_order_cnc_file",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={(200, "text/csv"): OpenApiTypes.STR, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID, filename: str):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                found = service.cnc_file_content(
                    org_id=org_id, order_id=order_id, filename=filename
                )
        if found is None:
            raise contract_error(
                404,
                "cnc_file_not_found",
                "No hay un archivo CNC generado con ese nombre en la orden.",
            )
        download_name, content = found
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{download_name}"'
        return response


class ProductionOrderDxfExportView(APIView):
    @extend_schema(
        operation_id="production_order_dxf_export",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={201: DxfExportSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.export_dxf_files(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                )
        return Response(output, status=201)


class ProductionOrderDxfFileView(APIView):
    @extend_schema(
        operation_id="production_order_dxf_file",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={(200, "application/dxf"): OpenApiTypes.STR, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID, filename: str):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                found = service.dxf_file_content(
                    org_id=org_id, order_id=order_id, filename=filename
                )
        if found is None:
            raise contract_error(
                404,
                "dxf_file_not_found",
                "No hay un archivo DXF generado con ese nombre en la orden.",
            )
        download_name, content = found
        response = HttpResponse(content, content_type="application/dxf")
        response["Content-Disposition"] = f'attachment; filename="{download_name}"'
        return response


class ProductionOrderCutPackView(APIView):
    @extend_schema(
        operation_id="production_order_cut_pack",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={(200, "application/pdf"): OpenApiTypes.STR, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                from production.cut_pack import render_cut_pack

                content, download_name = render_cut_pack(
                    org_id=org_id, order_id=order_id
                )
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{download_name}"'
        )
        return response


class ProductionOrderPackView(APIView):
    @extend_schema(
        operation_id="production_order_pack",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={(200, "application/pdf"): OpenApiTypes.STR, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                from production.pack import render_production_pack

                content, download_name = render_production_pack(
                    org_id=org_id, order_id=order_id
                )
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{download_name}"'
        )
        return response


class ProductionOrderOpsExportView(APIView):
    @extend_schema(
        operation_id="production_order_ops_export",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={201: OpsExportSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.export_operations(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                )
        return Response(output, status=201)


class ProductionOrderOpsFileView(APIView):
    @extend_schema(
        operation_id="production_order_ops_file",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={(200, "application/octet-stream"): OpenApiTypes.STR, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID, filename: str):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                found = service.operations_file_content(
                    org_id=org_id, order_id=order_id, filename=filename
                )
        if found is None:
            raise contract_error(
                404,
                "ops_file_not_found",
                "No hay un archivo de operaciones generado con ese nombre en la orden.",
            )
        download_name, content = found
        content_type = (
            "application/json" if download_name.endswith(".json") else "text/csv"
        )
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{download_name}"'
        return response


class ProductionOrderInstallationView(APIView):
    @extend_schema(
        operation_id="production_order_install",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=InstallationRequestSerializer,
        responses={200: ProductionOrderDetailSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(InstallationRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _STEP_ACTORS) as (token, _, org_id):
                output = service.confirm_installation(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    note=data.get("note"),
                )
        return Response(output)


class ProductionOrderPackingView(APIView):
    @extend_schema(
        operation_id="production_order_packing",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={201: PackingManifestSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.generate_packing_manifest(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                )
        return Response(output, status=201)


class ProductionOrderLabelsView(APIView):
    @extend_schema(
        operation_id="production_order_labels",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: PackingLabelsSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.packing_labels(org_id=org_id, order_id=order_id)
        return Response(output)


class ProductionOrderDispatchView(APIView):
    @extend_schema(
        operation_id="production_order_dispatch",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=DispatchRequestSerializer,
        responses={200: ProductionOrderDetailSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(DispatchRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.dispatch_work_order(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    note=data.get("note"),
                )
        return Response(output)


class ProductionOrderDispatchNoteVoidView(APIView):
    @extend_schema(
        operation_id="production_order_dispatch_note_void",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=DispatchNoteVoidSerializer,
        responses={200: ProductionOrderDetailSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(DispatchNoteVoidSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.void_dispatch_note(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    reason=data.get("reason"),
                )
        return Response(output)


class ProductionOrderDispatchNoteView(APIView):
    @extend_schema(
        operation_id="production_order_dispatch_note",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: DispatchNoteAccessSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = dispatch_note_access(org_id=org_id, order_id=order_id)
        return Response(output)


class ProductionOrderDispatchNoteDteView(APIView):
    @extend_schema(
        operation_id="production_order_dispatch_note_dte_emit",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=DispatchNoteDteEmitSerializer,
        responses={201: DispatchNoteDteSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(DispatchNoteDteEmitSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = sii.emit_dispatch_note_dte(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    ind_traslado=int(data.get("ind_traslado") or 1),
                )
        return Response(output, status=201)

    @extend_schema(
        operation_id="production_order_dispatch_note_dte",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: DispatchNoteDteAccessSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = sii.dispatch_note_dte_access(
                    org_id=org_id, order_id=order_id
                )
        return Response(output)


class ProductionOrderDispatchNoteEnvioView(APIView):
    @extend_schema(
        operation_id="production_order_dispatch_note_dte_envio_send",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=SiiEnvioSendSerializer,
        responses={201: SiiEnvioSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(SiiEnvioSendSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = sii_envio.send_dispatch_note_envio(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    resubmit=bool(data.get("resubmit")),
                )
        return Response(output, status=201)

    @extend_schema(
        operation_id="production_order_dispatch_note_dte_envio",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: SiiEnvioAccessSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = sii_envio.dispatch_note_envio_access(
                    org_id=org_id, order_id=order_id
                )
        return Response(output)


class WorkCenterListView(APIView):
    @extend_schema(
        operation_id="production_work_centers",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: WorkCenterListSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.list_work_centers(org_id=org_id)
        return Response(output)

    @extend_schema(
        operation_id="production_work_centers_create",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=WorkCenterRequestSerializer,
        responses={200: WorkCenterSerializer, 201: WorkCenterSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request):
        data = validate(WorkCenterRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (_, _, org_id):
                output, created = service.create_work_center(
                    org_id=org_id,
                    code=data["code"],
                    name=data["name"],
                    kind=data["kind"],
                    display_order=data.get("display_order", 0),
                )
        return Response(output, status=201 if created else 200)


class ProductionOrderOptimizeView(APIView):
    @extend_schema(
        operation_id="production_order_optimize",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=WorkOrderOptimizeRequestSerializer,
        responses={200: WorkOrderOptimizeSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(WorkOrderOptimizeRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.optimize_work_order(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    color=data.get("color"),
                    cutting_profile_code=data.get("cutting_profile_code"),
                    strategy=data["strategy"],
                )
        return Response(output)


class ProductionOrderOptimizeCompareView(APIView):
    @extend_schema(
        operation_id="production_order_optimize_compare",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=WorkOrderOptimizeCompareRequestSerializer,
        responses={200: WorkOrderOptimizeCompareSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(WorkOrderOptimizeCompareRequestSerializer, request.data)
        with public_production_errors():
            # Preview only — readers can compare, writers still hold the
            # commit authority on an actual plan.
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.compare_optimization_strategies(
                    org_id=org_id,
                    order_id=order_id,
                    color=data.get("color") or "",
                )
        return Response(output)


class ProductionOrderDeliveryView(APIView):
    @extend_schema(
        operation_id="production_order_delivery",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: DeliveryResponseSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(service.get_delivery(org_id=org_id, order_id=order_id))

    @extend_schema(
        operation_id="production_order_delivery_schedule",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=DeliveryScheduleRequestSerializer,
        responses={200: DeliveryResponseSerializer, **ERRORS},
        tags=["production"],
    )
    def put(self, request, order_id: UUID):
        data = validate(DeliveryScheduleRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.schedule_delivery(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    scheduled_date=str(data["scheduled_date"]),
                    time_window=str(data["time_window"]),
                    address=str(data["address"]),
                    contact_name=data.get("contact_name"),
                    contact_phone=data.get("contact_phone"),
                    installer_name=data.get("installer_name"),
                    notes=data.get("notes"),
                )
        return Response(output)


class ProductionOrderDeliveryConfirmView(APIView):
    @extend_schema(
        operation_id="production_order_delivery_confirm",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=DeliveryConfirmRequestSerializer,
        responses={200: DeliveryConfirmResponseSerializer, 201: DeliveryConfirmResponseSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(DeliveryConfirmRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _READERS) as (token, tenant, org_id):
                # A cobro en terreno writes the money ledger + a sealed
                # comprobante — field crews sign PODs, they don't collect.
                if data.get("payment") and tenant.active_organization.role not in _LEDGER_WRITERS:
                    raise contract_error(
                        403,
                        "payment_role_denied",
                        "Registrar un cobro requiere el rol Estimador u Owner.",
                    )
                confirmation = confirm_delivery(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    receiver_name=data["receiver_name"],
                    receiver_rut=data.get("receiver_rut"),
                    signature_b64=data["signature_png"],
                    payment=data.get("payment"),
                )
                output = {
                    "confirmation": confirmation,
                    "delivery": service.get_delivery(
                        org_id=org_id, order_id=order_id
                    )["delivery"],
                }
        return Response(output, status=201)


class ProductionOrderDeliveryConfirmationView(APIView):
    @extend_schema(
        operation_id="production_order_delivery_confirmation",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: DeliveryConfirmationAccessSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = confirmation_access(org_id=org_id, order_id=order_id)
        return Response(output)


class ProductionOrderDeliveryTransitionView(APIView):
    @extend_schema(
        operation_id="production_order_delivery_transition",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=DeliveryTransitionRequestSerializer,
        responses={200: DeliveryResponseSerializer, **ERRORS},
        tags=["production"],
    )
    def post(self, request, order_id: UUID):
        data = validate(DeliveryTransitionRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _STEP_ACTORS) as (token, _, org_id):
                output = service.transition_delivery(
                    org_id=org_id,
                    order_id=order_id,
                    actor_id=token.user_id,
                    to_status=str(data["status"]),
                )
        return Response(output)


class ProductionOrderTraceView(APIView):
    @extend_schema(
        operation_id="production_order_trace",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionOrderTraceSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = trace_work_order(org_id=org_id, order_id=order_id)
        return Response(output)


class ProductionPieceTraceView(APIView):
    @extend_schema(
        operation_id="production_piece_trace",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionPieceTraceSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, piece_id: str):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = trace_piece(org_id=org_id, piece_id=piece_id)
        return Response(output)


class ProductionVersionTraceView(APIView):
    @extend_schema(
        operation_id="production_version_trace",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionVersionTraceSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request, version_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = trace_version(org_id=org_id, version_id=version_id)
        return Response(output)


class ProductionStationQueueView(APIView):
    """Cross-order floor view: open steps grouped by station — what each
    bench/cell has queued, which one is next, which are blocked."""

    @extend_schema(
        operation_id="production_station_queue",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: ProductionStationQueueSerializer, **ERRORS},
        tags=["production"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.station_queue(org_id=org_id)
        return Response(output)


class CncWorkspaceView(APIView):
    @extend_schema(
        operation_id="production_cnc_workspace",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: CncWorkspaceSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = cnc.cnc_workspace(org_id=org_id)
        return Response(output)


class CncToolListView(APIView):
    @extend_schema(
        operation_id="production_cnc_tools",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: CncToolListSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response({"tools": cnc.list_tools(org_id=org_id)})

    @extend_schema(
        operation_id="production_cnc_tool_create",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=CncToolRequestSerializer,
        responses={201: CncToolSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def post(self, request):
        data = validate(CncToolRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = cnc.create_tool(
                    org_id=org_id, actor_id=token.user_id, data=data
                )
        return Response(output, status=201)


class CncToolDetailView(APIView):
    @extend_schema(
        operation_id="production_cnc_tool_update",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=CncToolPatchSerializer,
        responses={200: CncToolSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def patch(self, request, tool_id: UUID):
        data = validate(CncToolPatchSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = cnc.update_tool(
                    org_id=org_id, tool_id=tool_id, data=data
                )
        return Response(output)


class CncMachineListView(APIView):
    @extend_schema(
        operation_id="production_cnc_machines",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: CncMachineListSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def get(self, request):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response({"machines": cnc.list_machines(org_id=org_id)})

    @extend_schema(
        operation_id="production_cnc_machine_create",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=CncMachineRequestSerializer,
        responses={201: CncMachineSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def post(self, request):
        data = validate(CncMachineRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = cnc.create_machine(
                    org_id=org_id, actor_id=token.user_id, data=data
                )
        return Response(output, status=201)


class CncMachineDetailView(APIView):
    @extend_schema(
        operation_id="production_cnc_machine_update",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=CncMachinePatchSerializer,
        responses={200: CncMachineSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def patch(self, request, machine_id: UUID):
        data = validate(CncMachinePatchSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = cnc.update_machine(
                    org_id=org_id, machine_id=machine_id, data=data
                )
        return Response(output)


class CncReadinessView(APIView):
    @extend_schema(
        operation_id="production_order_cnc_readiness",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: CncReadinessSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = cnc.cnc_readiness(org_id=org_id, order_id=order_id)
        return Response(output)


class CncProgramListView(APIView):
    @extend_schema(
        operation_id="production_order_cnc_programs",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: CncProgramListSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def get(self, request, order_id: UUID):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return Response(
                    {"programs": cnc.list_programs(org_id=org_id, order_id=order_id)}
                )

    @extend_schema(
        operation_id="production_order_cnc_program_generate",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=CncGenerateRequestSerializer,
        responses={201: CncProgramSerializer, **ERRORS},
        tags=["production", "cnc"],
    )
    def post(self, request, order_id: UUID):
        data = validate(CncGenerateRequestSerializer, request.data)
        with public_production_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = cnc.generate_program(
                    org_id=org_id,
                    order_id=order_id,
                    machine_id=UUID(data["machine_id"]),
                    member_id=data["member_id"],
                    actor_id=token.user_id,
                )
        return Response(output, status=201)


class CncProgramFileView(APIView):
    @extend_schema(
        operation_id="production_cnc_program_file",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={(200, "application/json"): OpenApiTypes.STR, (200, "text/csv"): OpenApiTypes.STR, **ERRORS},
        tags=["production", "cnc"],
    )
    def get(self, request, program_id: UUID, filename: str):
        with public_production_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                resolved = cnc.program_file(
                    org_id=org_id, program_id=program_id, filename=filename
                )
                if resolved is None:
                    raise DocumentaryError("cnc_file_not_found")
                name, content = resolved
        mime = "text/csv" if filename.endswith(".csv") else "application/json"
        response = HttpResponse(content, content_type=f"{mime}; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
