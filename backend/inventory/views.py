"""HTTP surface for inventory: derived stock, movement ledger, receiving."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from uuid import UUID

from django.db import DatabaseError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from documents.repository import DocumentaryError
from documents.views import DOCUMENTARY_ERROR_DETAILS, ERRORS, documentary_scope, validate
from inventory import service
from inventory import remnants as remnants_service
from inventory.serializers import (
    InventoryMovementRequestSerializer,
    InventoryMovementSerializer,
    InventoryMovementsSerializer,
    InventoryStockSerializer,
    MovementListQuerySerializer,
    OrderReceiptRequestSerializer,
    OrderReceivingSerializer,
    RemnantCreateSerializer,
    RemnantListQuerySerializer,
    RemnantListSerializer,
    RemnantSerializer,
)

logger = logging.getLogger(__name__)

_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")
_WRITERS = ("OWNER", "WORKSHOP_MANAGER")


@contextmanager
def public_inventory_errors():
    try:
        yield
    except DocumentaryError as error:
        status_code = 404 if error.code in ("order_not_found", "inventory_item_not_found") else 422
        raise contract_error(
            status_code,
            error.code,
            error.public_detail
            or DOCUMENTARY_ERROR_DETAILS.get(error.code)
            or "La operación de inventario fue rechazada; revisa el pedido y las cantidades.",
            error_extra=error.extra or None,
        ) from error
    except serializers.ValidationError as error:
        raise contract_error(
            422, "inventory_payload_invalid", "Revisa los parámetros de inventario."
        ) from error
    except DatabaseError as error:
        logger.warning("Inventory transaction rejected (%s)", type(error).__name__)
        raise contract_error(
            409,
            "inventory_transaction_rejected",
            "El movimiento de inventario entró en conflicto; reintenta la operación.",
        ) from error


class InventoryStockView(APIView):
    @extend_schema(
        operation_id="inventory_stock",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: InventoryStockSerializer, **ERRORS},
        tags=["inventory"],
    )
    def get(self, request):
        with public_inventory_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.list_stock(org_id=org_id)
        return Response(output)


class InventoryMovementsView(APIView):
    @extend_schema(
        operation_id="inventory_movements",
        parameters=[ACTIVE_ORGANIZATION_HEADER, MovementListQuerySerializer],
        request=None,
        responses={200: InventoryMovementsSerializer, **ERRORS},
        tags=["inventory"],
    )
    def get(self, request):
        query = validate(MovementListQuerySerializer, request.query_params)
        with public_inventory_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.list_movements(
                    org_id=org_id,
                    item_id=query.get("item_id"),
                    limit=query.get("limit", 50),
                )
        return Response(output)

    @extend_schema(
        operation_id="inventory_movements_record",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=InventoryMovementRequestSerializer,
        responses={200: InventoryMovementSerializer, **ERRORS},
        tags=["inventory"],
    )
    def post(self, request):
        data = validate(InventoryMovementRequestSerializer, request.data)
        with public_inventory_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output = service.record_movement(
                    org_id=org_id,
                    actor_id=token.user_id,
                    item_id=data["item_id"],
                    movement_type=data["movement_type"],
                    quantity=data["quantity"],
                    lot_code=data.get("lot_code"),
                    note=data["note"],
                )
        return Response(output)


class OrderReceivingView(APIView):
    @extend_schema(
        operation_id="inventory_order_receiving",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: OrderReceivingSerializer, **ERRORS},
        tags=["inventory"],
    )
    def get(self, request, order_id: UUID):
        with public_inventory_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = service.order_receiving(org_id=org_id, order_id=order_id)
        return Response(output)


class OrderReceiptCreateView(APIView):
    @extend_schema(
        operation_id="inventory_order_receive",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=OrderReceiptRequestSerializer,
        responses={200: OrderReceivingSerializer, 201: OrderReceivingSerializer, **ERRORS},
        tags=["inventory"],
    )
    def post(self, request, order_id: UUID):
        data = validate(OrderReceiptRequestSerializer, request.data)
        with public_inventory_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                output, created = service.receive_order(
                    org_id=org_id,
                    actor_id=token.user_id,
                    order_id=order_id,
                    receipt_key=data["receipt_key"],
                    note=data.get("note"),
                    lines=data["lines"],
                )
        return Response(output, status=201 if created else 200)


class RemnantListView(APIView):
    @extend_schema(
        operation_id="inventory_remnants",
        parameters=[ACTIVE_ORGANIZATION_HEADER, RemnantListQuerySerializer],
        request=None,
        responses={200: RemnantListSerializer, **ERRORS},
        tags=["inventory"],
    )
    def get(self, request):
        query = validate(RemnantListQuerySerializer, request.query_params)
        with public_inventory_errors():
            with documentary_scope(request, _READERS) as (_, _, org_id):
                output = remnants_service.list_remnants(
                    org_id=org_id,
                    kind=query.get("kind"),
                    status=query.get("status"),
                )
        return Response(output)

    @extend_schema(
        operation_id="inventory_remnant_create",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=RemnantCreateSerializer,
        responses={201: RemnantSerializer, **ERRORS},
        tags=["inventory"],
    )
    def post(self, request):
        data = validate(RemnantCreateSerializer, request.data)
        with public_inventory_errors():
            with documentary_scope(request, _WRITERS) as (_, _, org_id):
                output = remnants_service.create_remnant(
                    org_id=org_id, **data,
                )
        return Response(output, status=201)


class _RemnantTransitionView(APIView):
    action: str

    def post(self, request, remnant_id: UUID):
        with public_inventory_errors():
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                if self.action == "scrap":
                    output = remnants_service.scrap_remnant(
                        org_id=org_id, remnant_id=remnant_id,
                        actor_id=token.user_id,
                    )
                else:
                    output = remnants_service.unreserve_remnant(
                        org_id=org_id, remnant_id=remnant_id,
                        actor_id=token.user_id,
                    )
        return Response(output)


class RemnantScrapView(_RemnantTransitionView):
    action = "scrap"

    @extend_schema(
        operation_id="inventory_remnant_scrap",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: RemnantSerializer, **ERRORS},
        tags=["inventory"],
    )
    def post(self, request, remnant_id: UUID):
        return super().post(request, remnant_id)


class RemnantReleaseView(_RemnantTransitionView):
    action = "release"

    @extend_schema(
        operation_id="inventory_remnant_release",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=None,
        responses={200: RemnantSerializer, **ERRORS},
        tags=["inventory"],
    )
    def post(self, request, remnant_id: UUID):
        return super().post(request, remnant_id)
