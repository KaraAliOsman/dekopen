"""Tenant-bound HTTP endpoint delegating all mathematics to /engine."""

from __future__ import annotations


from dekopen_engine.snapshot import calculation_response, evaluation_response
from dekopen_engine.weight import MissingFabricationAuthority
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.rls import authenticated_rls_context
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER, ErrorResponseSerializer
from authentication.tenancy import (
    MembershipRepository,
    enforce_owner_mfa,
    resolve_tenant_context,
)
from authentication.views import verified_request_token
from engine_api.adapter import (
    InvalidEngineRequest,
    parse_product_model,
    UnsupportedEngineContract,
    calculate_from_api,
    evaluate_assembly_from_api,
    elevation_envelope,
)
from engine_api.repository import (
    SystemNotFound,
    SystemParamsRepository,
    UnsupportedCatalogContract,
)
from engine_api.serializers import (
    EngineAssemblyCalculateResponseSerializer,
    EngineAssemblyCalculateSerializer,
    EngineLayoutResponseSerializer,
    EngineCalculateRequestSerializer,
    EngineCalculateResponseSerializer,
    EngineSystemsResponseSerializer,
)


class EngineSystemsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="engine_systems",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={
            200: EngineSystemsResponseSerializer,
            400: OpenApiResponse(ErrorResponseSerializer),
            401: OpenApiResponse(ErrorResponseSerializer),
            403: OpenApiResponse(ErrorResponseSerializer),
            409: OpenApiResponse(ErrorResponseSerializer),
        },
        tags=["engine"],
    )
    def get(self, request: Request) -> Response:
        token = verified_request_token(request)
        with authenticated_rls_context(token.claims):
            memberships = MembershipRepository().list_active_for_user(token.user_id)
            tenant = resolve_tenant_context(
                memberships,
                request.headers.get("X-Organization-ID"),
            )
            enforce_owner_mfa(tenant, token.aal)
            systems = SystemParamsRepository().list_visible(
                tenant.active_organization.organization_id
            )
            from catalogs.readiness import catalog_readiness
            items = []
            for system in systems:
                readiness = catalog_readiness(system.id, tenant.active_organization.organization_id)
                items.append({**system.public_dict(), "quote_ready": readiness["quote_ready"],
                              "readiness_reasons": readiness["reasons"]})

        return Response(
            {"systems": items},
            status=status.HTTP_200_OK,
        )


class EngineCalculateView(APIView):
    permission_classes = [IsAuthenticated]

    def build_response(self, data, result, params):
        return calculation_response({**data, "system_id": str(data["system_id"])}, result)

    @extend_schema(
        operation_id="engine_calculate",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=EngineCalculateRequestSerializer,
        responses={
            200: EngineCalculateResponseSerializer,
            400: OpenApiResponse(ErrorResponseSerializer),
            401: OpenApiResponse(ErrorResponseSerializer),
            403: OpenApiResponse(ErrorResponseSerializer),
            404: OpenApiResponse(ErrorResponseSerializer),
            409: OpenApiResponse(ErrorResponseSerializer),
            422: OpenApiResponse(ErrorResponseSerializer),
        },
        tags=["engine"],
    )
    def post(self, request: Request) -> Response:
        request_serializer = EngineCalculateRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            raise contract_error(
                status.HTTP_400_BAD_REQUEST,
                "validation_error",
                "Request validation failed",
            )
        data = request_serializer.validated_data
        token = verified_request_token(request)

        try:
            with authenticated_rls_context(token.claims):
                memberships = MembershipRepository().list_active_for_user(token.user_id)
                tenant = resolve_tenant_context(
                    memberships,
                    request.headers.get("X-Organization-ID"),
                )
                enforce_owner_mfa(tenant, token.aal)
                params = SystemParamsRepository().load_visible(
                    data["system_id"], tenant.active_organization.organization_id
                )
                result = calculate_from_api(
                    parametric_tree=data["parametric_tree"],
                    nominal_width_mm=data["nominal_width_mm"],
                    nominal_height_mm=data["nominal_height_mm"],
                    color=data["color"],
                    params=params,
                )
                response_payload = self.build_response(data, result, params)
        except SystemNotFound as error:
            raise contract_error(
                status.HTTP_404_NOT_FOUND,
                "system_not_found",
                "Profile system does not exist or is not visible",
            ) from error
        except (UnsupportedEngineContract, UnsupportedCatalogContract) as error:
            raise contract_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unsupported_engine_contract",
                "Engine contract is not supported in SHOT-06 Core",
            ) from error
        except MissingFabricationAuthority as error:
            raise contract_error(
                status.HTTP_409_CONFLICT,
                "catalog_authority_missing",
                "catalogs.errors.authority_missing",
            ) from error
        except (InvalidEngineRequest, ValueError) as error:
            raise contract_error(
                status.HTTP_400_BAD_REQUEST,
                "validation_error",
                "Request validation failed",
            ) from error

        return Response(response_payload, status=status.HTTP_200_OK)


class EngineLayoutView(EngineCalculateView):
    """Expose traversal dimensions without adding a second geometry implementation."""

    @extend_schema(
        operation_id="engine_layout",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=EngineCalculateRequestSerializer,
        responses={200: EngineLayoutResponseSerializer},
        tags=["engine"],
    )
    def post(self, request):
        return super().post(request)

    def build_response(self, data, result, params):
        from dekopen_engine.geometry import compute_geometry
        from dekopen_engine.layout import node_layout
        from engine_api.adapter import normalized_root_from_api

        root = normalized_root_from_api(
            parametric_tree=data["parametric_tree"],
            nominal_width_mm=data["nominal_width_mm"],
            nominal_height_mm=data["nominal_height_mm"], color=data["color"], params=params,
        )
        return {
            "calculation_hash": super().build_response(data, result, params)["calculation_hash"],
            "nodes": node_layout(compute_geometry(root, params)),
        }


class EngineAssemblyCalculateView(APIView):
    """Evaluate a compositional product (modules + couplings).

    Same auth/RLS flow as EngineCalculateView; all mathematics stay in
    /engine. The response separates geometry validity from manufacturing
    completeness and carries plan-view geometry for the editor.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="engine_assembly_calculate",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=EngineAssemblyCalculateSerializer,
        responses={
            200: EngineAssemblyCalculateResponseSerializer,
            400: OpenApiResponse(ErrorResponseSerializer),
            401: OpenApiResponse(ErrorResponseSerializer),
            403: OpenApiResponse(ErrorResponseSerializer),
            404: OpenApiResponse(ErrorResponseSerializer),
            422: OpenApiResponse(ErrorResponseSerializer),
        },
        tags=["engine"],
    )
    def post(self, request: Request) -> Response:
        request_serializer = EngineAssemblyCalculateSerializer(data=request.data)
        if not request_serializer.is_valid():
            raise contract_error(
                status.HTTP_400_BAD_REQUEST,
                "validation_error",
                "Request validation failed",
            )
        data = request_serializer.validated_data
        token = verified_request_token(request)

        try:
            with authenticated_rls_context(token.claims):
                memberships = MembershipRepository().list_active_for_user(token.user_id)
                tenant = resolve_tenant_context(
                    memberships,
                    request.headers.get("X-Organization-ID"),
                )
                enforce_owner_mfa(tenant, token.aal)
                repository = SystemParamsRepository()
                params = repository.load_visible(
                    data["system_id"], tenant.active_organization.organization_id
                )
                coupler_articles = repository.load_coupler_articles(
                    data["system_id"], tenant.active_organization.organization_id
                )
                model = parse_product_model(data["product"])
                envelope_width, envelope_height = elevation_envelope(model.assembly)
                if (
                    data["nominal_width_mm"] != envelope_width
                    or data["nominal_height_mm"] != envelope_height
                ):
                    raise InvalidEngineRequest(
                        "nominal dimensions must equal the assembly envelope "
                        "(width across columns, tallest stacked-column height)"
                    )
                evaluation = evaluate_assembly_from_api(
                    product=model,
                    color=data["color"],
                    params=params,
                    coupler_articles=coupler_articles,
                )
                response_payload = evaluation_response(
                    {**data, "system_id": str(data["system_id"])}, evaluation
                )
        except SystemNotFound as error:
            raise contract_error(
                status.HTTP_404_NOT_FOUND,
                "system_not_found",
                "Profile system does not exist or is not visible",
            ) from error
        except (UnsupportedEngineContract, UnsupportedCatalogContract) as error:
            raise contract_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unsupported_engine_contract",
                "Engine contract is not supported",
            ) from error
        except MissingFabricationAuthority as error:
            raise contract_error(
                status.HTTP_409_CONFLICT,
                "catalog_authority_missing",
                "catalogs.errors.authority_missing",
            ) from error
        except (InvalidEngineRequest, ValueError) as error:
            raise contract_error(
                status.HTTP_400_BAD_REQUEST,
                "validation_error",
                "Request validation failed",
            ) from error

        return Response(response_payload, status=status.HTTP_200_OK)
