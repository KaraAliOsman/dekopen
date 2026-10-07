"""Manual project API using the existing verified JWT and RLS boundary."""

import json
from datetime import datetime

from django.db import connection
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.parsers import FormParser
from rest_framework.permissions import AllowAny

from ai_gateway import invocations
from ai_gateway.providers import ProviderError
from authentication.errors import ContractAPIException, contract_error
from engine_api.repository import SystemNotFound, UnsupportedCatalogContract
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from billing.flow import FlowError
from billing.serializers import FlowAcknowledgementSerializer, FlowConfirmationSerializer
from pricing.repository import encode
from pricing.views import DecimalJSONParser, ERRORS, scope, validate
from projects import (
    clients,
    credit_notes,
    design_alternatives,
    design_assist,
    invoices,
    measurement,
    org_branding,
    org_settings,
    payment_links,
    payments,
    quotations,
    receipts,
    reminders,
    service,
    sii,
    sii_envio,
)
from projects.serializers import (
    ClientDetailResponseSerializer,
    ClientDuplicatesResponseSerializer,
    ClientListResponseSerializer,
    ClientMergeSerializer,
    ClientNoteWriteSerializer,
    ClientResponseSerializer,
    ClientUpdateSerializer,
    ClientWriteSerializer,
    CollectionReminderDraftResponseSerializer,
    CollectionReminderPrepareSerializer,
    CollectionReminderSendResponseSerializer,
    CollectionReminderSendSerializer,
    OrgBrandingSerializer,
    OrgBrandingWriteSerializer,
    OrgCommercialSettingsSerializer,
    OrgCompanySettingsSerializer,
    OrgDocumentPreviewResponseSerializer,
    OrgDocumentPreviewSerializer,
    OrgDocumentsSettingsSerializer,
    OrgIntegrationsResponseSerializer,
    OrgInviteSerializer,
    OrgInvitationSerializer,
    OrgMemberUpdateSerializer,
    OrgMembersResponseSerializer,
    OrgNumberingResponseSerializer,
    OrgProductionSettingsSerializer,
    OrgSectionResponseSerializer,
    OrgSecuritySettingsSerializer,
    OrgSettingsResponseSerializer,
    PaymentIntegrationSerializer,
    PaymentIntegrationStatusSerializer,
    PaymentLinkCreateSerializer,
    PaymentLinkResponseSerializer,
    PaymentLinksResponseSerializer,
    PaymentReceiptAccessSerializer,
    PaymentRecordResponseSerializer,
    PaymentRecordSerializer,
    PaymentsSummarySerializer,
    PaymentVoidSerializer,
    ProjectCreditNoteAccessSerializer,
    ProjectCreditNoteEmitSerializer,
    ProjectCreditNoteSerializer,
    ProjectDteAccessSerializer,
    ProjectDteSerializer,
    ProjectInvoiceAccessSerializer,
    ProjectInvoiceSerializer,
    SiiCafListSerializer,
    SiiCafSerializer,
    SiiCafUploadSerializer,
    SiiCertificateSerializer,
    SiiCertificateStatusSerializer,
    SiiCertificateUploadSerializer,
    SiiEnvioAccessSerializer,
    SiiEnvioSendSerializer,
    SiiEnvioSerializer,
    CloneProjectSerializer,
    DeletePositionSerializer,
    DesignAlternativesRequestSerializer,
    DesignAlternativesResponseSerializer,
    DesignAssistRequestSerializer,
    DesignAssistResponseSerializer,
    MeasurementConfirmSerializer,
    MeasurementResolveResponseSerializer,
    MeasurementResolveSerializer,
    PositionMoveSerializer,
    PositionResponseSerializer,
    PositionUpdateSerializer,
    PositionWriteSerializer,
    ProjectListResponseSerializer,
    ProjectThermalSerializer,
    ThermalAlternativesResponseSerializer,
    ProjectResponseSerializer,
    QuotationListResponseSerializer,
    ProjectUpdateSerializer,
    ProjectWriteSerializer,
    ResetPricingSerializer,
    SuccessorRequestSerializer,
)

READ_ROLES = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")
WRITE_ROLES = ("OWNER", "ESTIMATOR")
SCHEMA = {"parameters": [ACTIVE_ORGANIZATION_HEADER], "tags": ["projects"]}


def response(value, *, status=200):
    def public_encode(item):
        return item.isoformat() if isinstance(item, datetime) else encode(item)

    return Response(
        json.loads(json.dumps(value, default=public_encode, allow_nan=False)), status=status
    )


class ProjectsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="projects_list",
        responses={200: ProjectListResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response({"items": service.list_projects(org)})

    @extend_schema(
        operation_id="projects_create",
        request=ProjectWriteSerializer,
        responses={201: ProjectResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request):
        data = validate(ProjectWriteSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(service.create_project(org, token.user_id, data), status=201)


class QuotationsView(APIView):
    """Lista transversal de cotizaciones: estado comercial real por
    proyecto, incluyendo «vista por el cliente» del enlace vigente.
    Comercial puro — el taller no cotiza (READ_ROLES menos WM)."""

    @extend_schema(
        operation_id="quotations_list",
        responses={200: QuotationListResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, ("OWNER", "ESTIMATOR")) as (_, _, org):
            return response(quotations.list_quotations(org))


class ProjectView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="projects_retrieve",
        responses={200: ProjectResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                service.project_public(org, service.project_row(org, project_id), detail=True)
            )

    @extend_schema(
        operation_id="projects_update",
        request=ProjectUpdateSerializer,
        responses={200: ProjectResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def patch(self, request, project_id):
        if not isinstance(request.data, dict) or "expected_updated_at" not in request.data:
            raise contract_error(400, "validation_error", "expected_updated_at es obligatorio.")
        data = validate(ProjectUpdateSerializer, request.data, partial=True)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(service.update_project(org, project_id, data))


class ProjectPositionsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="positions_create",
        request=PositionWriteSerializer,
        responses={201: PositionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(PositionWriteSerializer, request.data)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(service.save_position(org, project_id, data), status=201)


class ProjectCloneView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="projects_clone",
        request=CloneProjectSerializer,
        responses={201: ProjectResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(CloneProjectSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(service.clone_project(org, token.user_id, project_id, data), status=201)


class ProjectSuccessorView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="projects_start_successor",
        request=SuccessorRequestSerializer,
        responses={200: ProjectResponseSerializer, 201: ProjectResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        with scope(request, WRITE_ROLES) as (_, _, org):
            data = validate(SuccessorRequestSerializer, request.data)
            value = service.start_successor(org, project_id, data["expected_current_revision"])
        created = value.pop("successor_created")
        return response(value, status=201 if created else 200)


class ProjectResetPricingView(APIView):
    @extend_schema(
        operation_id="projects_reset_pricing",
        request=ResetPricingSerializer,
        responses={200: ProjectResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(ResetPricingSerializer, request.data)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(
                service.reset_draft_pricing(
                    org,
                    project_id,
                    data["expected_operation_id"],
                    data["reason"],
                )
            )


class PositionView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="positions_retrieve",
        responses={200: PositionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, position_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(service.position_public(service.position_row(org, position_id)))

    @extend_schema(
        operation_id="positions_update",
        request=PositionUpdateSerializer,
        responses={200: PositionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request, position_id):
        data = validate(PositionUpdateSerializer, request.data)
        with scope(request, WRITE_ROLES) as (_, _, org):
            existing = service.position_row(org, position_id)
            return response(
                service.save_position(org, existing["project_id"], data, position_id=position_id)
            )

    @extend_schema(
        operation_id="positions_destroy",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "expected_updated_at",
                OpenApiTypes.DATETIME,
                OpenApiParameter.QUERY,
                required=True,
            ),
        ],
        tags=["projects"],
        responses={204: None, **ERRORS},
    )
    def delete(self, request, position_id):
        data = validate(DeletePositionSerializer, request.query_params)
        with scope(request, WRITE_ROLES) as (_, _, org):
            service.delete_position(org, position_id, data["expected_updated_at"])
        return Response(status=204)


class PositionMoveView(APIView):
    """Explicit reorder — the estimator arranges the print order of the
    quotation lines; the service rewrites the whole 1..N run atomically."""

    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="positions_move",
        request=PositionMoveSerializer,
        responses={200: PositionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, position_id):
        data = validate(PositionMoveSerializer, request.data)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(
                service.move_position(
                    org, position_id, data["to_index"], data["expected_updated_at"]
                )
            )


class PositionMeasurementResolveView(APIView):
    """Live vano→fabricación preview for the editor — engine resolves, nothing persists."""

    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="positions_measurement_resolve",
        request=MeasurementResolveSerializer,
        responses={200: MeasurementResolveResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(MeasurementResolveSerializer, request.data)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(
                measurement.resolve_measurement_preview(
                    org,
                    system_id=data["system_id"],
                    vano_payload=data.get("vano"),
                    mounting_rule_id=data.get("mounting_rule_id"),
                    lock_payload=data.get("fabrication_lock"),
                    position_width_mm=data["width_mm"],
                    position_height_mm=data["height_mm"],
                )
            )


class PositionMeasurementConfirmView(APIView):
    """Explicit human confirmation of the fabrication measure — the
    production gate evidence."""

    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="positions_measurement_confirm",
        request=MeasurementConfirmSerializer,
        responses={200: PositionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, position_id):
        data = validate(MeasurementConfirmSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            existing = service.position_row(org, position_id)
            return response(
                service.position_public(
                    measurement.confirm_measurement(
                        org,
                        existing["project_id"],
                        position_id,
                        token.user_id,
                        confirmed=data["confirmed"],
                    )
                )
            )


class PositionDesignAssistView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="positions_design_assist",
        request=DesignAssistRequestSerializer,
        responses={200: DesignAssistResponseSerializer, 502: ERRORS[503], **ERRORS},
        **SCHEMA,
    )
    def post(self, request, position_id):
        data = validate(DesignAssistRequestSerializer, request.data)
        try:
            with scope(request, WRITE_ROLES) as (token, _, org):
                try:
                    position = service.position_row(org, position_id)
                    # Ops validate against the position's own catalog authority —
                    # the client's system_id is only the fallback for a position
                    # that doesn't declare one yet (review AI-11).
                    return response(
                        design_assist.assist(
                            org_id=org,
                            user_id=token.user_id,
                            position=position,
                            product=data["product"],
                            prompt=str(data["prompt"]),
                            operation_key=str(data["operation_key"]),
                            system_id=position.get("system_id") or data["system_id"],
                        )
                    )
                except SystemNotFound as error:
                    raise contract_error(
                        404,
                        "system_not_found",
                        "La serie no está disponible para este taller.",
                    ) from error
                except UnsupportedCatalogContract as error:
                    raise contract_error(
                        422,
                        "technical_authority_required",
                        "Revisa las compatibilidades del catálogo de esta serie.",
                    ) from error
        except ProviderError as error:
            # §IA3 — outside the scope so the failed call records AFTER the
            # request transaction rolled back (entry rides error.invocation).
            invocations.record_attached(error)
            raise contract_error(
                503,
                error.code,
                "El proveedor de IA no está disponible en este momento.",
            ) from None
        except ContractAPIException as error:
            invocations.record_attached(error)
            raise


class PositionDesignAlternativesView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="positions_design_alternatives",
        request=DesignAlternativesRequestSerializer,
        responses={
            200: DesignAlternativesResponseSerializer,
            502: ERRORS[503],
            **ERRORS,
        },
        **SCHEMA,
    )
    def post(self, request, position_id):
        data = validate(DesignAlternativesRequestSerializer, request.data)
        try:
            with scope(request, WRITE_ROLES) as (token, _, org):
                try:
                    return response(
                        design_alternatives.alternatives(
                            org_id=org,
                            user_id=token.user_id,
                            position=service.position_row(org, position_id),
                            brief=str(data["brief"]),
                            count=int(data.get("count") or 2),
                            operation_key=str(data["operation_key"]),
                            system_id=data["system_id"],
                            width_mm=data.get("width_mm"),
                            height_mm=data.get("height_mm"),
                        )
                    )
                except SystemNotFound as error:
                    raise contract_error(
                        404,
                        "system_not_found",
                        "La serie no está disponible para este taller.",
                    ) from error
                except UnsupportedCatalogContract as error:
                    raise contract_error(
                        422,
                        "technical_authority_required",
                        "Revisa las compatibilidades del catálogo de esta serie.",
                    ) from error
        except ProviderError as error:
            invocations.record_attached(error)
            raise contract_error(
                503,
                error.code,
                "El proveedor de IA no está disponible en este momento.",
            ) from None
        except ContractAPIException as error:
            invocations.record_attached(error)
            raise


class ProjectPaymentsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_payments_list",
        responses={200: PaymentsSummarySerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(payments.list_payments(org_id=org, project_id=project_id))

    @extend_schema(
        operation_id="project_payments_record",
        request=PaymentRecordSerializer,
        responses={201: PaymentRecordResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(PaymentRecordSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(
                payments.record_payment(
                    org_id=org, project_id=project_id, actor_id=token.user_id, data=data
                ),
                status=201,
            )


class ProjectPaymentLinksView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_payment_links_list",
        responses={200: PaymentLinksResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(payment_links.list_links(org_id=org, project_id=project_id))

    @extend_schema(
        operation_id="project_payment_link_create",
        request=PaymentLinkCreateSerializer,
        responses={201: PaymentLinkResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(PaymentLinkCreateSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(
                payment_links.create_link(
                    org_id=org, project_id=project_id, actor_id=token.user_id, data=data
                ),
                status=201,
            )


class ProjectPaymentLinkRecoverView(APIView):
    @extend_schema(
        operation_id="project_payment_link_recover",
        request=None,
        responses={200: PaymentLinkResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id, link_id):
        with scope(request, WRITE_ROLES) as (_, _, org):
            try:
                return response(payment_links.recover_link(org_id=org, link_id=link_id))
            except FlowError as error:
                raise contract_error(
                    503, error.code, "El link requiere verificación del proveedor."
                ) from None


# Provider credentials (API key / webhook secret) are owner-level data —
# estimators operate the ledger, not the payment plumbing.
_OWNER_ONLY = ("OWNER",)


class ProjectPaymentIntegrationView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_payment_integration_status",
        responses={200: PaymentIntegrationStatusSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, _OWNER_ONLY) as (_, _, org):
            return response(payment_links.get_integration(org_id=org))

    @extend_schema(
        operation_id="project_payment_integration_save",
        request=PaymentIntegrationSerializer,
        responses={200: PaymentIntegrationStatusSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        data = validate(PaymentIntegrationSerializer, request.data)
        with scope(request, _OWNER_ONLY) as (_, _, org):
            return response(payment_links.save_integration(org_id=org, data=data))


class FlowPaymentConfirmView(APIView):
    """Flow urlConfirmation webhook — public, verified server-side."""

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [FormParser]

    @extend_schema(
        operation_id="project_payment_flow_confirm",
        tags=["projects"],
        request=FlowConfirmationSerializer,
        responses={200: FlowAcknowledgementSerializer, **ERRORS},
    )
    def post(self, request, link_id):
        data = FlowConfirmationSerializer(data=request.data)
        if not data.is_valid() or len(request.data.getlist("token")) != 1:
            raise contract_error(
                400, "invalid_flow_callback", "La confirmación requiere un token válido."
            )
        try:
            payment_links.confirm_link(link_id=link_id, token=data.validated_data["token"])
        except FlowError as error:
            raise contract_error(
                404 if error.code == "payment_link_not_found" else 503,
                error.code,
                "El cobro requiere confirmación del proveedor.",
            ) from None
        return response({"received": True})


class ProjectCollectionReminderView(APIView):
    """IA prepara el mensaje — jamás envía. El clic de enviar vive aparte."""

    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_collection_reminder_prepare",
        request=CollectionReminderPrepareSerializer,
        responses={200: CollectionReminderDraftResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(CollectionReminderPrepareSerializer, request.data)
        try:
            with scope(request, WRITE_ROLES) as (token, _, org):
                return response(
                    reminders.draft_reminder(
                        org_id=org,
                        project_id=project_id,
                        actor_id=token.user_id,
                        operation_key=str(data["operation_key"]),
                    )
                )
        except ProviderError as error:
            invocations.record_attached(error)
            raise contract_error(
                503,
                error.code,
                "El proveedor de IA no está disponible en este momento.",
            ) from None
        except ContractAPIException as error:
            invocations.record_attached(error)
            raise


class ProjectCollectionReminderSendView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_collection_reminder_send",
        request=CollectionReminderSendSerializer,
        responses={200: CollectionReminderSendResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        data = validate(CollectionReminderSendSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(
                reminders.send_reminder(
                    org_id=org,
                    project_id=project_id,
                    actor_id=token.user_id,
                    subject=str(data["subject"]),
                    body=str(data["body"]),
                )
            )


class OrganizationBrandingView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_branding_get",
        responses={200: OrgBrandingSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(org_branding.get_branding(org_id=org))

    @extend_schema(
        operation_id="organization_branding_save",
        request=OrgBrandingWriteSerializer,
        responses={200: OrgBrandingSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        data = validate(OrgBrandingWriteSerializer, request.data)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(org_branding.save_branding(org_id=org, data=data))


class OrganizationBrandingLogoView(APIView):
    @extend_schema(
        operation_id="organization_branding_logo_upload",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        },
        responses={200: OrgBrandingSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        file_obj = request.FILES.get("file") if hasattr(request, "FILES") else None
        if file_obj is None:
            raise contract_error(400, "brand_logo_missing", "Adjunta un archivo PNG, JPEG o WebP.")
        content = file_obj.read()
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(org_branding.save_logo(org_id=org, content=content))

    @extend_schema(
        operation_id="organization_branding_logo_read",
        responses={200: {"type": "string", "format": "binary"}, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            content, content_type = org_branding.logo_bytes(org_id=org)
        # HttpResponse, no DRF Response — el renderer JSON no sabe serializar
        # bytes crudos y devuelve 500 en lugar de la imagen.
        return HttpResponse(
            content,
            content_type=content_type,
            headers={"Cache-Control": "private, max-age=300"},
        )

    @extend_schema(
        operation_id="organization_branding_logo_delete",
        responses={200: OrgBrandingSerializer, **ERRORS},
        **SCHEMA,
    )
    def delete(self, request):
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(org_branding.clear_logo(org_id=org))


class ProjectPaymentView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_payment_void",
        request=PaymentVoidSerializer,
        responses={200: PaymentsSummarySerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id, payment_id):
        data = validate(PaymentVoidSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(
                payments.void_payment(
                    org_id=org,
                    project_id=project_id,
                    payment_id=payment_id,
                    actor_id=token.user_id,
                    data=data,
                )
            )


class ProjectPaymentReceiptView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_payment_receipt",
        responses={200: PaymentReceiptAccessSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id, payment_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                receipts.receipt_access(org_id=org, project_id=project_id, payment_id=payment_id)
            )


class ProjectInvoicesView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_invoice_emit",
        request=None,
        responses={201: ProjectInvoiceSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id):
        with scope(request, WRITE_ROLES) as (token, _, org):
            project = service.project_row(org, project_id)
            return response(
                invoices.issue_invoice(org_id=org, project=project, actor_id=token.user_id),
                status=201,
            )


class ProjectInvoiceAccessView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_invoice_access",
        responses={200: ProjectInvoiceAccessSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id, invoice_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                invoices.invoice_access(org_id=org, project_id=project_id, invoice_id=invoice_id)
            )


class ProjectCreditNotesView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_credit_note_emit",
        request=ProjectCreditNoteEmitSerializer,
        responses={201: ProjectCreditNoteSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id, invoice_id):
        data = validate(ProjectCreditNoteEmitSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            project = service.project_row(org, project_id)
            return response(
                credit_notes.issue_credit_note(
                    org_id=org,
                    project=project,
                    invoice_id=invoice_id,
                    actor_id=token.user_id,
                    reason=data.get("reason"),
                    amount=data.get("amount"),
                ),
                status=201,
            )


class ProjectCreditNoteAccessView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_credit_note_access",
        responses={200: ProjectCreditNoteAccessSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id, credit_note_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                credit_notes.credit_note_access(
                    org_id=org,
                    project_id=project_id,
                    credit_note_id=credit_note_id,
                )
            )


class ProjectInvoiceDteView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_invoice_dte_emit",
        request=None,
        responses={201: ProjectDteSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id, invoice_id):
        with scope(request, WRITE_ROLES) as (token, _, org):
            project = service.project_row(org, project_id)
            return response(
                sii.emit_dte(
                    org_id=org,
                    project=project,
                    invoice_id=invoice_id,
                    actor_id=token.user_id,
                ),
                status=201,
            )

    @extend_schema(
        operation_id="project_invoice_dte_access",
        responses={200: ProjectDteAccessSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id, invoice_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                sii.dte_access(org_id=org, project_id=project_id, invoice_id=invoice_id)
            )


class ProjectCreditNoteDteView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_credit_note_dte_emit",
        request=ProjectCreditNoteEmitSerializer,
        responses={201: ProjectDteSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id, invoice_id):
        data = validate(ProjectCreditNoteEmitSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            project = service.project_row(org, project_id)
            return response(
                sii.emit_credit_note_dte(
                    org_id=org,
                    project=project,
                    invoice_id=invoice_id,
                    actor_id=token.user_id,
                    reason=data.get("reason"),
                    amount=data.get("amount"),
                ),
                status=201,
            )

    @extend_schema(
        operation_id="project_credit_note_dte_access",
        responses={200: ProjectDteAccessSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id, invoice_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                sii.credit_note_dte_access(
                    org_id=org,
                    project_id=project_id,
                    invoice_id=invoice_id,
                )
            )


class ProjectCreditNoteDteEnvioView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_credit_note_dte_envio_send",
        request=SiiEnvioSendSerializer,
        responses={201: SiiEnvioSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id, credit_note_id):
        data = validate(SiiEnvioSendSerializer, request.data)
        with scope(request, ("OWNER", "WORKSHOP_MANAGER")) as (token, _, org):
            return response(
                sii_envio.send_credit_note_envio(
                    org_id=org,
                    project_id=project_id,
                    credit_note_id=credit_note_id,
                    actor_id=token.user_id,
                    resubmit=bool(data.get("resubmit")),
                ),
                status=201,
            )

    @extend_schema(
        operation_id="project_credit_note_dte_envio_access",
        responses={200: SiiEnvioAccessSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id, credit_note_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                sii_envio.credit_note_envio_access(
                    org_id=org,
                    project_id=project_id,
                    credit_note_id=credit_note_id,
                )
            )


class SiiCafsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="sii_cafs_list",
        responses={200: SiiCafListSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response({"items": sii.list_cafs(org_id=org)})

    @extend_schema(
        operation_id="sii_caf_register",
        request=SiiCafUploadSerializer,
        responses={201: SiiCafSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request):
        data = validate(SiiCafUploadSerializer, request.data)
        # CAF registration installs fiscal signing keys — owner-only, never
        # the estimator scope that manages quotes and documents.
        with scope(request, ("OWNER",)) as (token, _, org):
            return response(
                sii.register_caf(
                    org_id=org,
                    actor_id=token.user_id,
                    caf_xml=data["caf_xml"],
                    giro_emis=data.get("giro_emis"),
                    dir_origen=data.get("dir_origen"),
                    cmna_origen=data.get("cmna_origen"),
                    acteco=data.get("acteco"),
                ),
                status=201,
            )


class SiiCertificateView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="sii_certificate_status",
        responses={200: SiiCertificateStatusSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                {
                    "certificate": sii_envio.certificate_status(org_id=org),
                    # La misma verdad que la leyenda de los PDF: adaptador,
                    # certificado vigente y folios — «No conectado» se decide
                    # con esto, no con la presencia del certificado solo.
                    "integration": sii_envio.integration_state(org_id=org),
                }
            )

    @extend_schema(
        operation_id="sii_certificate_upload",
        request=SiiCertificateUploadSerializer,
        responses={201: SiiCertificateSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request):
        data = validate(SiiCertificateUploadSerializer, request.data)
        # The digital certificate signs every envío sent to the SII —
        # installing it is owner-only, never the estimator scope.
        with scope(request, ("OWNER",)) as (token, _, org):
            return response(
                sii_envio.upload_certificate(
                    org_id=org,
                    actor_id=token.user_id,
                    pfx_b64=data["pfx_b64"],
                    password=data.get("password") or None,
                    nro_resol=data["nro_resol"],
                    fch_resol=data["fch_resol"],
                ),
                status=201,
            )


class ProjectInvoiceDteEnvioView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="project_invoice_dte_envio_send",
        request=SiiEnvioSendSerializer,
        responses={201: SiiEnvioSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, project_id, invoice_id):
        data = validate(SiiEnvioSendSerializer, request.data)
        # An envío submits signed fiscal documents with the org's certificate —
        # the production side, never the estimator's commercial scope.
        with scope(request, ("OWNER", "WORKSHOP_MANAGER")) as (token, _, org):
            return response(
                sii_envio.send_invoice_envio(
                    org_id=org,
                    project_id=project_id,
                    invoice_id=invoice_id,
                    actor_id=token.user_id,
                    resubmit=bool(data.get("resubmit")),
                ),
                status=201,
            )

    @extend_schema(
        operation_id="project_invoice_dte_envio_access",
        responses={200: SiiEnvioAccessSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id, invoice_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                sii_envio.invoice_envio_access(
                    org_id=org, project_id=project_id, invoice_id=invoice_id
                )
            )


class ClientsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="clients_list",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "q",
                str,
                description="Búsqueda por nombre o RUT (normalizado).",
            ),
            OpenApiParameter(
                "filtro",
                str,
                enum=["activos", "saldo"],
                description="activos = con proyectos activos; saldo = con saldo pendiente.",
            ),
        ],
        tags=["projects"],
        responses={200: ClientListResponseSerializer, **ERRORS},
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            query = request.query_params.get("q") or None
            raw_filter = request.query_params.get("filtro")
            filter_kind = {"activos": "active", "saldo": "balance"}.get(raw_filter)
            return response(
                {
                    "items": clients.list_clients(
                        org, query=query, filter_kind=filter_kind
                    )
                }
            )

    @extend_schema(
        operation_id="clients_create",
        request=ClientWriteSerializer,
        responses={201: ClientResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request):
        data = validate(ClientWriteSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(clients.create_client(org, token.user_id, data), status=201)


class ClientView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="clients_retrieve",
        responses={200: ClientDetailResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, client_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(clients.client_detail(org, client_id))

    @extend_schema(
        operation_id="clients_update",
        request=ClientUpdateSerializer,
        responses={200: ClientResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def patch(self, request, client_id):
        if not isinstance(request.data, dict) or "expected_updated_at" not in request.data:
            raise contract_error(400, "validation_error", "expected_updated_at es obligatorio.")
        data = validate(ClientUpdateSerializer, request.data, partial=True)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(clients.update_client(org, client_id, data))

    @extend_schema(
        operation_id="clients_deactivate",
        responses={204: None, **ERRORS},
        **SCHEMA,
    )
    def delete(self, request, client_id):
        with scope(request, WRITE_ROLES) as (_, _, org):
            clients.deactivate_client(org, client_id)
            return Response(status=204)


class ClientNotesView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="clients_add_note",
        request=ClientNoteWriteSerializer,
        responses={201: ClientDetailResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, client_id):
        data = validate(ClientNoteWriteSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            clients.add_note(
                org, client_id, token.user_id, token.email or "—", data["body"]
            )
            return response(clients.client_detail(org, client_id), status=201)


class ClientDuplicatesView(APIView):
    @extend_schema(
        operation_id="clients_duplicates",
        responses={200: ClientDuplicatesResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response({"items": clients.duplicates(org)})


class ClientMergeView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="clients_merge",
        request=ClientMergeSerializer,
        responses={200: ClientDetailResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request, client_id):
        data = validate(ClientMergeSerializer, request.data)
        with scope(request, WRITE_ROLES) as (token, _, org):
            return response(
                clients.merge_clients(
                    org,
                    data["survivor_id"],
                    client_id,
                    token.user_id,
                    token.email or "—",
                )
            )


# ---------------------------------------------------------------------------
# P22 — Ajustes por dominio.


class OrganizationSettingsView(APIView):
    @extend_schema(
        operation_id="organization_settings_read",
        responses={200: OrgSettingsResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(org_settings.settings_snapshot(org))


class OrganizationCompanySettingsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_settings_company_update",
        request=OrgCompanySettingsSerializer,
        responses={200: OrgSettingsResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        data = validate(OrgCompanySettingsSerializer, request.data, partial=True)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(org_settings.save_company(org, data))


class OrganizationCommercialSettingsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_settings_commercial_update",
        request=OrgCommercialSettingsSerializer,
        responses={200: OrgSectionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        data = validate(OrgCommercialSettingsSerializer, request.data, partial=True)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(org_settings.save_commercial(org, data))


class OrganizationDocumentsSettingsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_settings_documents_update",
        request=OrgDocumentsSettingsSerializer,
        responses={200: OrgSectionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        data = validate(OrgDocumentsSettingsSerializer, request.data, partial=True)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(org_settings.save_documents(org, data))


class OrganizationProductionSettingsView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_settings_production_update",
        request=OrgProductionSettingsSerializer,
        responses={200: OrgSectionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        data = validate(OrgProductionSettingsSerializer, request.data, partial=True)
        with scope(request, WRITE_ROLES) as (_, _, org):
            return response(org_settings.save_production(org, data))


class OrganizationSecurityView(APIView):
    """El interruptor 2FA de la org es decisión del dueño — la plantilla
    no lo mueve (OWNER explícito, no WRITE_ROLES)."""

    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_security_update",
        request=OrgSecuritySettingsSerializer,
        responses={200: OrgSectionResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        data = validate(OrgSecuritySettingsSerializer, request.data)
        with scope(request, ("OWNER",)) as (_, _, org):
            return response(org_settings.save_security(org, data))


class OrganizationNumberingView(APIView):
    @extend_schema(
        operation_id="organization_numbering_read",
        responses={200: OrgNumberingResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(org_settings.numbering(org))


class OrganizationIntegrationsView(APIView):
    @extend_schema(
        operation_id="organization_integrations_read",
        responses={200: OrgIntegrationsResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(org_settings.integrations(org))


class OrganizationMembersView(APIView):
    """Usuarios y roles: la membresía la administra el dueño; invitar usa el
    correo como identificador (nunca un UUID visible)."""

    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_members_list",
        responses={200: OrgMembersResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, ("OWNER",)) as (_, _, org):
            return response(org_settings.list_members(org))

    @extend_schema(
        operation_id="organization_members_invite",
        request=OrgInviteSerializer,
        responses={201: OrgInvitationSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request):
        data = validate(OrgInviteSerializer, request.data)
        with scope(request, ("OWNER",)) as (token, _, org):
            return response(
                org_settings.invite_member(
                    org, data["email"], data["role"],
                    token.user_id, token.email or "—",
                ),
                status=201,
            )


class OrganizationMemberView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_member_update",
        request=OrgMemberUpdateSerializer,
        responses={200: OrgMembersResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def patch(self, request, membership_id):
        data = validate(OrgMemberUpdateSerializer, request.data, partial=True)
        with scope(request, ("OWNER",)) as (token, _, org):
            return response(
                org_settings.update_member(org, membership_id, data, token.user_id)
            )


class OrganizationDocumentPreviewView(APIView):
    """Vista previa real del papel con el borrador de marca/documentos —
    responde el HTML del render DOC-01 (mini hoja), no una aproximación."""

    parser_classes = [DecimalJSONParser]

    @extend_schema(
        operation_id="organization_document_preview",
        request=OrgDocumentPreviewSerializer,
        responses={200: OrgDocumentPreviewResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def post(self, request):
        data = validate(OrgDocumentPreviewSerializer, request.data, partial=True)
        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                {"html": org_settings.document_preview(org, data)}
            )


class ProjectThermalView(APIView):
    """P18 — panel de cumplimiento térmico OGUC 4.1.10 del proyecto."""

    @extend_schema(
        operation_id="projects_thermal",
        responses={200: ProjectThermalSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id):
        from projects import thermal

        with scope(request, READ_ROLES) as (_, _, org):
            return response(thermal.project_thermal(org, project_id))


class PositionThermalAlternativesView(APIView):
    """P18 §8 — alternativa más barata que sí cumple para la posición."""

    @extend_schema(
        operation_id="position_thermal_alternatives",
        responses={200: ThermalAlternativesResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, position_id):
        from projects import thermal

        with scope(request, READ_ROLES) as (_, _, org):
            return response(
                thermal.thermal_alternatives(
                    org_id=org,
                    position_id=position_id,
                    price_lookup=_thermal_price_lookup(org),
                )
            )


def _thermal_price_lookup(org):
    """Δ neto entre la posición guardada y un diseño candidato — la misma
    composición honesta de §08-WC (position_cost + margen declarado);
    devuelve None cuando la regla no permite un precio unitario honesto."""
    from datetime import date
    from decimal import Decimal as D

    from authentication.rls import tx_aborted
    from dekopen_engine.commercial import PricingError
    from django.db import transaction
    from django.db.utils import DatabaseError
    from pricing.repository import PricingRepository, json_text, one
    from pricing.service import _design_net_price, position_cost

    try:
        with transaction.atomic():  # savepoint: la negación RLS no aborta el resto
            rules = one(
                "SELECT * FROM public.pricing_rules WHERE org_id=%s",
                [org],
                "pricing_rules_not_found",
            )
    except (PricingError, DatabaseError):
        # pricing_rules no es legible por todos los roles con lectura de
        # proyectos (p. ej. ESTIMATOR bajo RLS). El §8 conserva las
        # alternativas y declara Δ «Sin dato» en vez de tumbar la vista.
        return lambda position, system_id, tree: None
    organization = one(
        "SELECT currency FROM public.tenancy_organizations WHERE id=%s",
        [org],
        "organization_not_found",
    )
    repo = PricingRepository(org, date.today(), organization["currency"], None)
    calculation_rules = {
        **rules,
        "labor_rate_per_m2": repo.convert(rules["labor_rate_per_m2"], organization["currency"]),
        "installation_rate_per_m2": repo.convert(
            rules["installation_rate_per_m2"], organization["currency"]
        ),
    }

    def lookup(position, system_id, tree):
        pseudo = {
            "system_id": system_id,
            "parametric_tree": json_text(tree),
            "width_mm": D(str(position["width_mm"])),
            "height_mm": D(str(position["height_mm"])),
            "color_interior": position["color_interior"],
            "color_exterior": position["color_exterior"],
        }
        try:
            before, before_area, _, before_formation = position_cost(
                repo, position, calculation_rules
            )
            after, after_area, _, after_formation = position_cost(repo, pseudo, calculation_rules)
            before_net = _design_net_price(
                before,
                before_area,
                before_formation,
                rules,
                width=position["width_mm"],
                height=position["height_mm"],
                foil=position["color_interior"] != "WHITE" or position["color_exterior"] != "WHITE",
            )
            after_net = _design_net_price(
                after,
                after_area,
                after_formation,
                rules,
                width=pseudo["width_mm"],
                height=pseudo["height_mm"],
                foil=pseudo["color_interior"] != "WHITE" or pseudo["color_exterior"] != "WHITE",
            )
            if before_net is None or after_net is None:
                return None
            return after_net - before_net
        except Exception:  # noqa: BLE001 — sin precio honesto, «Sin dato»
            return None
        finally:
            # position_cost deja el rol ambiente en pricing_backend; el
            # contexto del endpoint corre como authenticated.
            if not tx_aborted():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE authenticated")

    return lookup
