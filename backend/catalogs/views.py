"""Explicit, typed catalog endpoints with one technical-management permission."""

from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID
import json

from django.db import DatabaseError
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.rls import authenticated_rls_context
from authentication.serializers import (
    ACTIVE_ORGANIZATION_HEADER,
    ErrorResponseSerializer,
)
from authentication.tenancy import (
    MembershipRepository,
    enforce_owner_mfa,
    resolve_tenant_context,
)
from authentication.views import verified_request_token
from catalogs import evidence, mounting, service
from projects.serializers import MountingRuleListResponseSerializer
from catalogs.serializers import (
    EvidenceInputSerializer,
    EvidenceListSerializer,
    EvidenceReviewInputSerializer,
    EvidenceRowSerializer,
    ArticleListSerializer,
    ArticleResponseSerializer,
    BeadListSerializer,
    BeadResponseSerializer,
    CatalogFilterSerializer,
    ExtraArticleListSerializer,
    ExtraArticleResponseSerializer,
    KitListSerializer,
    KitResponseSerializer,
    ServiceArticleListSerializer,
    ServiceArticleResponseSerializer,
    SystemListSerializer,
    SystemResponseSerializer,
    ProcessProfileOptionListSerializer,
    SystemWorkspaceSerializer,
    SectionImportResponseSerializer,
)


def _reject_constant(value):
    raise ValueError("Nonfinite JSON number")


class CatalogJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return json.load(
                stream,
                parse_float=Decimal,
                parse_constant=_reject_constant,
            )
        except (ValueError, UnicodeDecodeError) as error:
            raise contract_error(
                400,
                "invalid_json",
                "catalogs.errors.invalid_json",
            ) from error


def _validated(serializer_type, data, *, partial=False):
    serializer = serializer_type(data=data, partial=partial)
    if not serializer.is_valid():
        raise contract_error(
            400,
            "catalog_validation_error",
            "catalogs.errors.validation",
            error_extra={"fields": serializer.errors},
        )
    return serializer.validated_data


READ_ROLES = ("OWNER", "WORKSHOP_MANAGER", "ESTIMATOR")
WRITE_ROLES = ("OWNER", "WORKSHOP_MANAGER")


def _reraise_catalog_error(error):
    sqlstate = getattr(error.__cause__, "sqlstate", None)
    if sqlstate == "23514" and "catalog_authority_referenced" in str(error):
        raise contract_error(409, "catalog_authority_referenced", "catalogs.errors.referenced") from error
    if sqlstate == "42501":
        status, code = 403, "catalog_permission_denied"
    elif sqlstate and (sqlstate.startswith("23") or sqlstate in ("P0001", "40001", "40P01")):
        status, code = 409, "catalog_constraint_conflict"
    else:
        status, code = 503, "catalog_unavailable"
    raise contract_error(status, code, f"catalogs.errors.{code}") from error


@contextmanager
def catalog_scope(request, *, roles=WRITE_ROLES):
    token = verified_request_token(request)
    try:
        with authenticated_rls_context(token.claims):
            tenant = resolve_tenant_context(
                MembershipRepository().list_active_for_user(token.user_id),
                request.headers.get("X-Organization-ID"),
            )
            enforce_owner_mfa(tenant, token.aal)
            if tenant.active_organization.role not in roles:
                raise contract_error(
                    403,
                    "catalog_permission_denied",
                    "catalogs.errors.permission",
                )
            yield tenant.active_organization.organization_id
    except DatabaseError as error:
        _reraise_catalog_error(error)


ERRORS = {code: OpenApiResponse(ErrorResponseSerializer) for code in (400, 401, 403, 404, 409, 503)}
HEADERS = [ACTIVE_ORGANIZATION_HEADER]
WRITE_HEADERS = [*HEADERS, OpenApiParameter(
    "If-Match", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True,
    description="Quoted revision from the most recently read catalog entity.",
)]


class MountingRuleCollectionView(APIView):
    """D07 mounting rules for a system: read-only authority, org overrides
    the global row of the same code."""
    parser_classes = [CatalogJSONParser]

    @extend_schema(
        operation_id="mounting_rules_list",
        parameters=[
            ACTIVE_ORGANIZATION_HEADER,
            OpenApiParameter(
                "system_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True
            ),
        ],
        responses={200: MountingRuleListResponseSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def get(self, request):
        system_id = request.query_params.get("system_id")
        if not system_id:
            raise contract_error(
                400, "catalog_validation_error", "catalogs.errors.validation"
            )
        with catalog_scope(request, roles=READ_ROLES) as org_id:
            return Response({
                "items": [
                    mounting.mounting_rule_public(row)
                    for row in mounting.mounting_rules_for_system(org_id, system_id)
                ]
            })


class CatalogCollectionView(APIView):
    parser_classes = [CatalogJSONParser]
    resource = None
    response_serializer = None
    list_serializer = None

    def get(self, request):
        with catalog_scope(request, roles=READ_ROLES) as org_id:
            filters = _validated(CatalogFilterSerializer, request.query_params.dict())
            if self.resource is service.SYSTEMS and filters:
                raise contract_error(
                    400,
                    "catalog_validation_error",
                    "catalogs.errors.validation",
                )
            rows = service.list_rows(
                self.resource,
                org_id,
                filters.get("system_id"),
            )
            output = self.list_serializer({"items": rows}).data
        return Response(output)

    def post(self, request):
        with catalog_scope(request) as org_id:
            data = _validated(self.resource.serializer, request.data)
            row = service.create(
                self.resource, org_id, data,
                actor_id=verified_request_token(request).user_id,
            )
            output = self.response_serializer(row).data
        return Response(output, status=201)


class CatalogDetailView(APIView):
    parser_classes = [CatalogJSONParser]
    resource = None
    response_serializer = None

    def get(self, request, row_id):
        with catalog_scope(request, roles=READ_ROLES) as org_id:
            row = service.retrieve(self.resource, org_id, row_id)
            output = self.response_serializer(row).data
        return Response(output)

    def patch(self, request, row_id):
        with catalog_scope(request) as org_id:
            data = _validated(
                self.resource.serializer,
                request.data,
                partial=True,
            )
            row = service.update(
                self.resource, org_id, row_id, data, request.headers.get("If-Match"),
                actor_id=verified_request_token(request).user_id,
            )
            output = self.response_serializer(row).data
        return Response(output)

    def delete(self, request, row_id):
        with catalog_scope(request) as org_id:
            service.delete(self.resource, org_id, row_id, request.headers.get("If-Match"))
        return Response(status=204)


class CatalogReviewView(APIView):
    """POST {resource}/{id}/review/ — a human vouches for the row's technical
    values; flips LEGACY_UNVERIFIED provenance to MANUAL."""

    resource = None
    response_serializer = None

    def post(self, request, row_id):
        token = verified_request_token(request)
        try:
            with authenticated_rls_context(token.claims):
                tenant = resolve_tenant_context(
                    MembershipRepository().list_active_for_user(token.user_id),
                    request.headers.get("X-Organization-ID"),
                )
                enforce_owner_mfa(tenant, token.aal)
                if tenant.active_organization.role not in WRITE_ROLES:
                    raise contract_error(
                        403,
                        "catalog_permission_denied",
                        "catalogs.errors.permission",
                    )
                row = service.review(
                    self.resource,
                    tenant.active_organization.organization_id,
                    row_id,
                    token.user_id,
                    expected_revision=request.headers.get("If-Match"),
                )
                output = self.response_serializer(row).data
        except DatabaseError as error:
            _reraise_catalog_error(error)
        return Response(output)


def _endpoint_classes(name, resource, response_serializer, list_serializer):
    attributes = {
        "__module__": __name__,
        "resource": resource,
        "response_serializer": response_serializer,
        "list_serializer": list_serializer,
    }
    collection = type(
        f"{name}CollectionView",
        (CatalogCollectionView,),
        attributes,
    )
    detail = type(f"{name}DetailView", (CatalogDetailView,), attributes)
    filters = (
        []
        if resource is service.SYSTEMS
        else [
            OpenApiParameter("system_id", OpenApiTypes.UUID, OpenApiParameter.QUERY),
        ]
    )
    collection = extend_schema_view(
        get=extend_schema(
            operation_id=f"catalog_{name.lower()}_list",
            parameters=[*HEADERS, *filters],
            responses={200: list_serializer, **ERRORS},
            tags=["catalogs"],
        ),
        post=extend_schema(
            operation_id=f"catalog_{name.lower()}_create",
            parameters=HEADERS,
            request=resource.serializer,
            responses={201: response_serializer, **ERRORS},
            tags=["catalogs"],
        ),
    )(collection)
    detail = extend_schema_view(
        get=extend_schema(
            operation_id=f"catalog_{name.lower()}_retrieve",
            parameters=HEADERS,
            responses={200: response_serializer, **ERRORS},
            tags=["catalogs"],
        ),
        patch=extend_schema(
            operation_id=f"catalog_{name.lower()}_update",
            parameters=WRITE_HEADERS,
            request=resource.serializer,
            responses={200: response_serializer, **ERRORS},
            tags=["catalogs"],
        ),
        delete=extend_schema(
            operation_id=f"catalog_{name.lower()}_delete",
            parameters=WRITE_HEADERS,
            responses={204: OpenApiResponse(description="Deleted"), **ERRORS},
            tags=["catalogs"],
        ),
    )(detail)
    return collection, detail


def _review_view(name, resource, response_serializer):
    return extend_schema_view(
        post=extend_schema(
            operation_id=f"catalog_{name.lower()}_review",
            parameters=HEADERS,
            request=None,
            responses={200: response_serializer, **ERRORS},
            tags=["catalogs"],
            description=(
                "Mark the row technically reviewed; LEGACY_UNVERIFIED "
                "provenance becomes MANUAL."
            ),
        )
    )(
        type(
            f"{name}ReviewView",
            (CatalogReviewView,),
            {
                "__module__": __name__,
                "resource": resource,
                "response_serializer": response_serializer,
            },
        )
    )


SystemCollectionView, SystemDetailView = _endpoint_classes(
    "System",
    service.SYSTEMS,
    SystemResponseSerializer,
    SystemListSerializer,
)
SystemReviewView = _review_view("System", service.SYSTEMS, SystemResponseSerializer)
ArticleCollectionView, ArticleDetailView = _endpoint_classes(
    "Article",
    service.ARTICLES,
    ArticleResponseSerializer,
    ArticleListSerializer,
)
ArticleReviewView = _review_view("Article", service.ARTICLES, ArticleResponseSerializer)
BeadCollectionView, BeadDetailView = _endpoint_classes(
    "Bead",
    service.BEADS,
    BeadResponseSerializer,
    BeadListSerializer,
)
BeadReviewView = _review_view("Bead", service.BEADS, BeadResponseSerializer)
KitCollectionView, KitDetailView = _endpoint_classes(
    "Kit",
    service.KITS,
    KitResponseSerializer,
    KitListSerializer,
)
KitReviewView = _review_view("Kit", service.KITS, KitResponseSerializer)
ExtraArticleCollectionView, ExtraArticleDetailView = _endpoint_classes(
    "ExtraArticle",
    service.EXTRA_ARTICLES,
    ExtraArticleResponseSerializer,
    ExtraArticleListSerializer,
)
ExtraArticleReviewView = _review_view(
    "ExtraArticle", service.EXTRA_ARTICLES, ExtraArticleResponseSerializer
)
ServiceArticleCollectionView, ServiceArticleDetailView = _endpoint_classes(
    "ServiceArticle",
    service.SERVICE_ARTICLES,
    ServiceArticleResponseSerializer,
    ServiceArticleListSerializer,
)
ServiceArticleReviewView = _review_view(
    "ServiceArticle", service.SERVICE_ARTICLES, ServiceArticleResponseSerializer
)


class SystemWorkspaceView(APIView):
    """GET systems/<id>/workspace/ — the §06 aggregate read: identity +
    readiness + every entity bound to the system in one fetch."""

    @extend_schema(
        operation_id="catalog_system_workspace",
        parameters=HEADERS,
        responses={200: SystemWorkspaceSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def get(self, request, row_id):
        with catalog_scope(request, roles=READ_ROLES) as org_id:
            data = service.system_workspace(org_id, str(row_id))
            output = SystemWorkspaceSerializer(data).data
        return Response(output)


class SectionImportCollectionView(APIView):
    """POST section-imports/ — upload a DXF/SVG drawing, get back the stored
    document path + detected outline candidates for human review."""

    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="catalog_section_import_create",
        parameters=HEADERS,
        request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
        responses={200: SectionImportResponseSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise contract_error(400, "section_file_missing", "catalogs.errors.section_file_missing")
        with catalog_scope(request, roles=WRITE_ROLES) as org_id:
            data = service.import_section_drawing(
                org_id=org_id,
                file_name=upload.name,
                content=upload.read(5_000_001),
                content_type=upload.content_type or "",
            )
        return Response(SectionImportResponseSerializer(data).data)


class ProcessProfileCollectionView(APIView):
    """GET process-profiles/ — the declared process authorities an org may
    bind a system to (global library plus org-owned rows)."""

    @extend_schema(
        operation_id="catalog_process_profile_list",
        parameters=HEADERS,
        responses={200: ProcessProfileOptionListSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def get(self, request):
        with catalog_scope(request, roles=READ_ROLES) as org_id:
            output = ProcessProfileOptionListSerializer(
                {"items": service.process_profile_options(org_id)}
            ).data
        return Response(output)


class EvidenceCollectionView(APIView):
    """GET evidence/?system_id= — the source trail behind a system's
    parameters. POST — a member declares evidence (declared PENDING; the
    review stamp is a separate server-set transition)."""

    parser_classes = [CatalogJSONParser]

    @extend_schema(
        operation_id="catalog_evidence_list",
        parameters=[
            *HEADERS,
            OpenApiParameter(
                "system_id", OpenApiTypes.UUID, OpenApiParameter.QUERY,
                required=True,
                description="System whose authority rows the evidence attests.",
            ),
        ],
        responses={200: EvidenceListSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def get(self, request):
        with catalog_scope(request, roles=READ_ROLES) as org_id:
            system_id = request.query_params.get("system_id")
            try:
                system_uuid = UUID(str(system_id))
            except (TypeError, ValueError) as error:
                raise contract_error(
                    400, "catalog_evidence_query", "catalogs.errors.evidence_query"
                ) from error
            output = EvidenceListSerializer(
                {"items": evidence.list_evidence(org_id=org_id, system_id=system_uuid)}
            ).data
        return Response(output)

    @extend_schema(
        operation_id="catalog_evidence_declare",
        parameters=HEADERS,
        request=EvidenceInputSerializer,
        responses={201: EvidenceRowSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def post(self, request):
        with catalog_scope(request, roles=WRITE_ROLES) as org_id:
            data = _validated(EvidenceInputSerializer, request.data)
            row = evidence.declare_evidence(
                org_id=org_id,
                actor_id=verified_request_token(request).user_id,
                values=data,
            )
        return Response(EvidenceRowSerializer(row).data, status=201)


class EvidenceReviewView(APIView):
    """POST evidence/{id}/review/ — stamp a review verdict. The reviewer
    identity and timestamp come from the request, never from the client."""

    parser_classes = [CatalogJSONParser]

    @extend_schema(
        operation_id="catalog_evidence_review",
        parameters=HEADERS,
        request=EvidenceReviewInputSerializer,
        responses={200: EvidenceRowSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def post(self, request, row_id):
        with catalog_scope(request, roles=WRITE_ROLES) as org_id:
            data = _validated(EvidenceReviewInputSerializer, request.data)
            row = evidence.review_evidence(
                org_id=org_id,
                evidence_id=row_id,
                actor_id=verified_request_token(request).user_id,
                state=data["review_state"],
            )
        return Response(EvidenceRowSerializer(row).data)
