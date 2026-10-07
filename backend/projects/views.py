"""Manual project API using the existing verified JWT and RLS boundary."""

import json
from datetime import datetime

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
    ClientListResponseSerializer,
    ClientResponseSerializer,
    ClientUpdateSerializer,
    ClientWriteSerializer,
    CollectionReminderDraftResponseSerializer,
    CollectionReminderPrepareSerializer,
    CollectionReminderSendResponseSerializer,
    CollectionReminderSendSerializer,
    OrgBrandingSerializer,
    OrgBrandingWriteSerializer,
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
        responses={200: ClientListResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response({"items": clients.list_clients(org)})

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
        responses={200: ClientResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, client_id):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(clients.client_public(org, client_id))

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
