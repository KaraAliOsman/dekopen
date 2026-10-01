"""OpenAPI-visible contracts for the inventory API."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("Unknown input fields")
        return super().to_internal_value(data)


class InventoryStockItemSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    sku = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    unit = serializers.CharField()
    variant_key = serializers.CharField()
    on_hand_qty = serializers.DecimalField(max_digits=14, decimal_places=2)
    reserved_qty = serializers.DecimalField(max_digits=14, decimal_places=2)
    available_qty = serializers.DecimalField(max_digits=14, decimal_places=2)
    incoming_qty = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, default="0"
    )
    racks = serializers.CharField(allow_null=True, required=False)
    spec_text = serializers.CharField(required=False, allow_blank=True)


class InventoryStockSerializer(serializers.Serializer):
    items = InventoryStockItemSerializer(many=True)


class InventoryMovementSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    item_id = serializers.UUIDField()
    movement_type = serializers.ChoiceField(
        choices=(
            "RECEIPT",
            "RESERVATION",
            "RELEASE",
            "CONSUMPTION",
            "ADJUSTMENT",
            "RETURN",
            "SCRAP",
        )
    )
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2)
    order_id = serializers.UUIDField(allow_null=True)
    order_line_id = serializers.UUIDField(allow_null=True)
    lot_code = serializers.CharField(allow_null=True)
    rack_location = serializers.CharField(allow_null=True, required=False)
    note = serializers.CharField(allow_null=True)
    actor_id = serializers.UUIDField(allow_null=True)
    actor_label = serializers.CharField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()


class InventoryMovementsSerializer(serializers.Serializer):
    movements = InventoryMovementSerializer(many=True)


class MovementListQuerySerializer(StrictSerializer):
    item_id = serializers.UUIDField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)


class ReceiptLineRequestSerializer(StrictSerializer):
    order_line_id = serializers.UUIDField()
    received_qty = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    damaged_qty = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), default=0
    )
    lot_code = serializers.CharField(required=False, allow_null=True, max_length=100)
    rack_location = serializers.CharField(required=False, allow_null=True, max_length=50)
    note = serializers.CharField(required=False, allow_null=True, max_length=500)


class OrderReceiptRequestSerializer(StrictSerializer):
    receipt_key = serializers.CharField(max_length=100)
    note = serializers.CharField(required=False, allow_null=True, max_length=500)
    lines = ReceiptLineRequestSerializer(many=True, allow_empty=False)


class OrderReceivingLineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    ordered_qty = serializers.DecimalField(max_digits=14, decimal_places=2)
    received_qty = serializers.DecimalField(max_digits=14, decimal_places=2)
    damaged_qty = serializers.DecimalField(max_digits=14, decimal_places=2)
    outstanding_qty = serializers.DecimalField(max_digits=14, decimal_places=2)
    purchasing_sku = serializers.CharField(allow_null=True)
    category = serializers.CharField(allow_null=True)
    unit = serializers.CharField(allow_null=True)
    physical_stock_identity = serializers.CharField(allow_null=True)
    specification = serializers.JSONField(allow_null=True)


class OrderReceiptSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    receipt_key = serializers.CharField()
    note = serializers.CharField(allow_null=True)
    received_by = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class OrderReceivingSerializer(serializers.Serializer):
    order = serializers.JSONField()
    lines = OrderReceivingLineSerializer(many=True)
    receipts = OrderReceiptSerializer(many=True)


class InventoryMovementRequestSerializer(StrictSerializer):
    item_id = serializers.UUIDField()
    movement_type = serializers.ChoiceField(choices=("ADJUSTMENT", "RETURN", "SCRAP"))
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
    lot_code = serializers.CharField(required=False, allow_null=True, max_length=100)
    rack_location = serializers.CharField(required=False, allow_null=True, max_length=50)
    note = serializers.CharField(max_length=500)


class RemnantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=("BAR", "SHEET"))
    stock_authority_id = serializers.UUIDField(allow_null=True)
    sheet_workshop_sku = serializers.CharField(allow_null=True)
    physical_stock_identity = serializers.UUIDField(allow_null=True)
    material = serializers.CharField(allow_null=True)
    color = serializers.CharField(allow_null=True)
    length_mm = serializers.DecimalField(
        max_digits=14, decimal_places=2, allow_null=True
    )
    width_mm = serializers.DecimalField(
        max_digits=14, decimal_places=2, allow_null=True
    )
    height_mm = serializers.DecimalField(
        max_digits=14, decimal_places=2, allow_null=True
    )
    status = serializers.ChoiceField(
        choices=("AVAILABLE", "RESERVED", "CONSUMED", "SCRAPPED")
    )
    origin = serializers.ChoiceField(choices=("RECEIPT", "PRODUCTION", "MANUAL"))
    origin_order_id = serializers.UUIDField(allow_null=True)
    reserved_order_id = serializers.UUIDField(allow_null=True)
    consumed_order_id = serializers.UUIDField(allow_null=True)
    rack_location = serializers.CharField(allow_null=True)
    notes = serializers.CharField(allow_null=True)
    reserved_order_code = serializers.CharField(allow_null=True, required=False)
    origin_order_code = serializers.CharField(allow_null=True, required=False)
    article_sku = serializers.CharField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class RemnantListSerializer(serializers.Serializer):
    remnants = RemnantSerializer(many=True)


class BarAuthoritySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    commercial_sku = serializers.CharField()
    physical_stock_identity = serializers.UUIDField(allow_null=True)
    stock_color = serializers.CharField(allow_null=True)
    source = serializers.ChoiceField(choices=("PROFILE", "REINFORCEMENT"))


class BarAuthorityListSerializer(serializers.Serializer):
    authorities = BarAuthoritySerializer(many=True)


class RemnantListQuerySerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=("BAR", "SHEET"), required=False)
    status = serializers.ChoiceField(
        choices=("AVAILABLE", "RESERVED", "CONSUMED", "SCRAPPED"), required=False
    )


class RemnantCreateSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=("BAR", "SHEET"))
    stock_authority_id = serializers.UUIDField(required=False, allow_null=True)
    sheet_workshop_sku = serializers.CharField(
        required=False, allow_null=True, max_length=100
    )
    physical_stock_identity = serializers.UUIDField(required=False, allow_null=True)
    material = serializers.CharField(required=False, allow_null=True, max_length=50)
    color = serializers.CharField(required=False, allow_null=True, max_length=50)
    length_mm = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    width_mm = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    height_mm = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    rack_location = serializers.CharField(
        required=False, allow_null=True, max_length=100
    )
    notes = serializers.CharField(required=False, allow_null=True, max_length=500)

    def validate(self, data):
        data = super().validate(data)
        if data["kind"] == "BAR":
            if not data.get("stock_authority_id") or not data.get("length_mm"):
                raise serializers.ValidationError(
                    "Bar remnants need stock_authority_id and a positive length_mm"
                )
        else:
            if not data.get("sheet_workshop_sku") or not (
                data.get("width_mm") and data.get("height_mm")
            ):
                raise serializers.ValidationError(
                    "Sheet remnants need sheet_workshop_sku and positive width/height"
                )
        return data


class RemnantLabelSerializer(serializers.Serializer):
    remnant = RemnantSerializer()
    identity = serializers.CharField()
    qr_payload = serializers.CharField()
    qr_svg = serializers.CharField()
