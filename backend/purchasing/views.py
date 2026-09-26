"""S19 tenant boundary for supplier eligibility, allocation, and explicit order actions."""

from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from documents.views import ERRORS, documentary_scope, validate
from purchasing.serializers import (
    AllocationRequestSerializer,
    AllocationResponseSerializer,
    ConfirmBatchRequestSerializer,
    EligibilityRequestSerializer,
    EligibilityResponseSerializer,
    OrderResponseSerializer,
    PurchasingStateSerializer,
    SendOrderRequestSerializer,
)
from purchasing.service import (
    allocate_requirement,
    confirm_order_type_batch,
    create_eligibility,
    purchasing_state,
    send_order,
)

_ALLOWED = ("OWNER", "WORKSHOP_MANAGER")
# The estimator who priced the job needs to see coverage, blockers and what
# is already ordered — read scope is wider than mutation scope (review PU16).
_READERS = _ALLOWED + ("ESTIMATOR",)


class PurchasingVersionsView(APIView):
    @extend_schema(
        operation_id="purchasing_versions",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: PurchasingStateSerializer, **ERRORS},
        tags=["purchasing"],
    )
    def get(self, request):
        with documentary_scope(request, _READERS) as (_, _, org_id):
            output = purchasing_state(org_id)
        return Response(output)


class PurchasingVersionView(APIView):
    @extend_schema(
        operation_id="purchasing_version_state",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: PurchasingStateSerializer, **ERRORS},
        tags=["purchasing"],
    )
    def get(self, request, version_id: UUID):
        with documentary_scope(request, _READERS) as (_, _, org_id):
            output = purchasing_state(org_id, version_id)
        return Response(output)


class SupplierEligibilityView(APIView):
    @extend_schema(
        operation_id="purchasing_create_eligibility",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=EligibilityRequestSerializer,
        responses={201: EligibilityResponseSerializer, **ERRORS},
        tags=["purchasing"],
    )
    def post(self, request, version_id: UUID):
        data = validate(EligibilityRequestSerializer, request.data)
        with documentary_scope(request, _ALLOWED) as (token, _, org_id):
            output = create_eligibility(
                org_id=org_id, actor_id=token.user_id, version_id=version_id, data=data
            )
        return Response(output, status=201)


class RequirementAllocationView(APIView):
    @extend_schema(
        operation_id="purchasing_allocate_requirement",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=AllocationRequestSerializer,
        responses={200: AllocationResponseSerializer, **ERRORS},
        tags=["purchasing"],
    )
    def put(self, request, requirement_id: UUID):
        data = validate(AllocationRequestSerializer, request.data)
        with documentary_scope(request, _ALLOWED) as (token, _, org_id):
            output = allocate_requirement(
                org_id=org_id,
                actor_id=token.user_id,
                requirement_id=requirement_id,
                eligibility_id=data["supplier_eligibility_id"],
            )
        return Response(output)


class ConfirmBatchView(APIView):
    @extend_schema(
        operation_id="purchasing_confirm_order_type",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=ConfirmBatchRequestSerializer,
        responses={200: OrderResponseSerializer(many=True), 201: OrderResponseSerializer(many=True), **ERRORS},
        tags=["purchasing"],
    )
    def post(self, request, version_id: UUID):
        data = validate(ConfirmBatchRequestSerializer, request.data)
        with documentary_scope(request, _ALLOWED) as (token, _, org_id):
            output, created = confirm_order_type_batch(
                org_id=org_id,
                actor_id=token.user_id,
                version_id=version_id,
                order_type=data["order_type"],
                confirmed=data["confirmed"],
            )
        return Response(output, status=201 if created else 200)


class SendOrderView(APIView):
    @extend_schema(
        operation_id="purchasing_send_order",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=SendOrderRequestSerializer,
        responses={200: OrderResponseSerializer, **ERRORS},
        tags=["purchasing"],
    )
    def post(self, request, order_id: UUID):
        data = validate(SendOrderRequestSerializer, request.data)
        with documentary_scope(request, _ALLOWED) as (token, _, org_id):
            output = send_order(
                org_id=org_id,
                actor_id=token.user_id,
                order_id=order_id,
                confirmed=data["confirmed"],
                expected_at=data.get("expected_at"),
            )
        return Response(output)
