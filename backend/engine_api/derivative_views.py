"""Authenticated derived computations; all technical cuts originate on the server."""

from django.db import DatabaseError
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.rls import authenticated_rls_context
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER, ErrorResponseSerializer
from authentication.tenancy import MembershipRepository, enforce_owner_mfa, resolve_tenant_context
from authentication.views import verified_request_token
from dekopen_engine.cutting import (
    InvalidCutContract, MissingStockAuthority, optimize_cut, pieces_from_result,
)
from dekopen_engine.geometry import compute_geometry
from dekopen_engine.hardware import AmbiguousHardwareKit
from dekopen_engine.inspection_models import (
    InspectionMode, InspectorConfigurationError, InspectorInput, StructuralInput, WorkshopAnnotations,
)
from dekopen_engine.inspector import inspect
from dekopen_engine.snapshot import calculation_response
from engine_api.adapter import calculate_from_api, normalized_root_from_api, UnsupportedEngineContract
from engine_api.cutting_repository import CuttingRepository
from engine_api.derivative_serializers import (
    EngineInspectRequestSerializer, EngineInspectResponseSerializer,
    EngineOptimizeRequestSerializer, EngineOptimizeResponseSerializer,
)
from engine_api.inspection_repository import InspectorRepository
from engine_api.repository import SystemNotFound, SystemParamsRepository, UnsupportedCatalogContract

_CALC_FIELDS = ("system_id", "parametric_tree", "nominal_width_mm", "nominal_height_mm", "color")
_ERRORS = {code: OpenApiResponse(ErrorResponseSerializer) for code in (400, 401, 403, 404, 409, 422, 503)}


def _execute(request: Request, *, inspection: bool) -> Response:
    serializer_type = EngineInspectRequestSerializer if inspection else EngineOptimizeRequestSerializer
    serializer = serializer_type(data=request.data)
    if (not isinstance(request.data, dict) or set(request.data) - set(serializer.fields)
            or not serializer.is_valid()):
        raise contract_error(400, "validation_error", "Revisa los datos del diseño y las observaciones de taller.")
    data = serializer.validated_data
    technical = {name: data[name] for name in _CALC_FIELDS}
    technical["system_id"] = str(technical["system_id"])
    token = verified_request_token(request)
    try:
        with authenticated_rls_context(token.claims):
            memberships = MembershipRepository().list_active_for_user(token.user_id)
            tenant = resolve_tenant_context(memberships, request.headers.get("X-Organization-ID"))
            enforce_owner_mfa(tenant, token.aal)
            org_id = tenant.active_organization.organization_id
            system_id = data["system_id"]
            params = SystemParamsRepository().load_visible(system_id, org_id)
            arguments = {name: data[name] for name in _CALC_FIELDS if name != "system_id"}
            arguments["params"] = params
            stocks = CuttingRepository()
            if not inspection:
                result = calculate_from_api(**arguments)
                authorities = stocks.for_result(result, system_id, org_id, data["color"])
                pieces = pieces_from_result(result, color=data["color"],
                                            reinforcement_skus=authorities.reinforcement_skus)
                output = optimize_cut(pieces, authorities.stocks,
                                      stocks.cutting_profile(org_id, data["cutting_profile_code"]))
                source = calculation_response(technical, result)["calculation_hash"]
                return Response({**output.model_dump(mode="json"), "source_calculation_hash": source})
            config = InspectorRepository().load(system_id, org_id)
            root = normalized_root_from_api(**arguments)
            computation = compute_geometry(
                root, params, diagnostic=True, is_foiled=data["color"] != "WHITE"
            )
            annotations = [WorkshopAnnotations.model_validate(item) for item in data["annotations"]]
            targets = {(o.bay_id, None) for o in computation.openings} | {
                (leaf.bay_id, leaf.leaf_id) for leaf in computation.leaves}
            # A FOILED machining annotation only exists on a foiled design —
            # the finish the design declared is the annotation's ceiling.
            if any((a.bay_id, a.leaf_id) not in targets
                   or (a.finish_class == "FOILED" and data["color"] == "WHITE")
                   for a in annotations):
                raise ValueError("Observation target or finish is outside the active contract")
            structural = [StructuralInput.model_validate(item) for item in data["structural_inputs"]]
            if any(item.target_id not in {span.target_id for span in computation.spans} for item in structural):
                raise ValueError("Structural target is not part of this calculation")
            inertias = {}
            for span in computation.spans:
                try:
                    _, ix = stocks.reinforcement_stock(system_id, org_id, span.parent_profile_sku,
                                                        None, data["color"])
                except MissingStockAuthority:
                    ix = None
                inertias[span.target_id] = ix
            source = (None if computation.result is None else
                      calculation_response(technical, computation.result)["calculation_hash"])
            output = inspect(InspectorInput(
                computation=computation, chamber_clearance_mm=config.chamber_clearance_mm,
                annotations=annotations, structural_inputs=structural,
                reinforcement_ix_by_target=inertias, mode=InspectionMode(data["mode"]),
                source_calculation_hash=source,
            ), config.config)
            return Response(output.model_dump(mode="json"))
    except SystemNotFound as error:
        raise contract_error(404, "system_not_found", "El sistema de perfiles no está disponible para esta organización.") from error
    except (InspectorConfigurationError, AmbiguousHardwareKit) as error:
        raise contract_error(422, "inspector_configuration_error", "La configuración técnica del sistema requiere revisión antes de aprobar para taller.") from error
    except InvalidCutContract as error:
        raise contract_error(422, type(error).__name__, "No se puede preparar el pedido de barras: revisa el stock, su correspondencia y la capacidad de corte.") from error
    except (UnsupportedEngineContract, UnsupportedCatalogContract, NotImplementedError) as error:
        raise contract_error(422, "unsupported_engine_contract", "Este diseño requiere una capacidad técnica que aún no está disponible.") from error
    except ValueError as error:
        raise contract_error(400, "validation_error", "Revisa las dimensiones, el relleno y las observaciones del diseño.") from error
    except DatabaseError as error:
        raise contract_error(503, "catalog_unavailable", "El catálogo no está disponible. Vuelve a intentarlo antes de aprobar para taller.") from error


class EngineInspectView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="engine_inspect", parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=EngineInspectRequestSerializer,
                   responses={200: EngineInspectResponseSerializer, **_ERRORS}, tags=["engine"])
    def post(self, request: Request) -> Response:
        return _execute(request, inspection=True)


class EngineOptimizeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="engine_optimize_cut", parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=EngineOptimizeRequestSerializer,
                   responses={200: EngineOptimizeResponseSerializer, **_ERRORS}, tags=["engine"])
    def post(self, request: Request) -> Response:
        return _execute(request, inspection=False)
