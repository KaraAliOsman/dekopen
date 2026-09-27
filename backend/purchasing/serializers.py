"""Strict supplier eligibility and order action transports for S19."""

from rest_framework import serializers

from documents.serializers import ArtifactResponseSerializer, StrictSerializer

ORDER_TYPES = [
    "SUPPLIER_PROFILE_PO",
    "SUPPLIER_GLASS_PO",
    "SUPPLIER_HARDWARE_PO",
    "SUPPLIER_PANEL_PO",
]


class SupplierDetailsSerializer(StrictSerializer):
    tax_id = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class EligibilityEvidenceSerializer(StrictSerializer):
    basis = serializers.CharField(max_length=2000, allow_blank=False)
    reference = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    valid_until = serializers.DateField(required=False, allow_null=True, default=None)


class EligibilityRequestSerializer(StrictSerializer):
    order_type = serializers.ChoiceField(choices=ORDER_TYPES)
    supplier_identity = serializers.CharField(max_length=200, allow_blank=False, trim_whitespace=True)
    supplier_name = serializers.CharField(max_length=300, allow_blank=False, trim_whitespace=True)
    supplier_details = SupplierDetailsSerializer()
    eligible_requirement_keys = serializers.ListField(
        child=serializers.RegexField(r"^[0-9a-f]{64}$"), allow_empty=False
    )
    evidence = EligibilityEvidenceSerializer()
    version = serializers.IntegerField(min_value=1)
    confirmed = serializers.BooleanField()

    def validate_eligible_requirement_keys(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Requirement keys must be unique")
        return sorted(value)


class AllocationRequestSerializer(StrictSerializer):
    supplier_eligibility_id = serializers.UUIDField()


class ConfirmBatchRequestSerializer(StrictSerializer):
    order_type = serializers.ChoiceField(choices=ORDER_TYPES)
    confirmed = serializers.BooleanField()


class SendOrderRequestSerializer(StrictSerializer):
    confirmed = serializers.BooleanField()
    expected_at = serializers.DateField(required=False, allow_null=True, default=None)
    sent_to = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=200, default=None
    )


class PurchasingStateSerializer(serializers.Serializer):
    versions = serializers.ListField(child=serializers.DictField(), required=False)
    version = serializers.DictField(required=False)
    requirements = serializers.ListField(child=serializers.DictField(), required=False)
    eligibilities = serializers.ListField(child=serializers.DictField(), required=False)
    allocations = serializers.ListField(child=serializers.DictField(), required=False)
    orders = serializers.ListField(child=serializers.DictField(), required=False)
    artifacts = ArtifactResponseSerializer(many=True, required=False)
    blockers = serializers.ListField(child=serializers.DictField(), required=False)
    coverage = serializers.DictField(required=False)


class EligibilityResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    content_hash = serializers.RegexField(r"^[0-9a-f]{64}$")


class AllocationResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    requirement_line_id = serializers.UUIDField()
    supplier_eligibility_id = serializers.UUIDField()


ORDER_STATUSES = [
    "DRAFT",
    "SENT",
    "PARTIALLY_RECEIVED",
    "FULFILLED",
    "CANCELLED",
]


class OrderResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    order_code = serializers.CharField()
    order_type = serializers.ChoiceField(choices=ORDER_TYPES)
    status = serializers.ChoiceField(choices=ORDER_STATUSES)
    supplier_name = serializers.CharField()
    order_snapshot_hash = serializers.RegexField(r"^[0-9a-f]{64}$")
    confirmed_at = serializers.CharField(required=False, allow_null=True)
    sent_at = serializers.CharField(required=False, allow_null=True)
    expected_at = serializers.DateField(required=False, allow_null=True)
    sent_to = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    cancelled_by = serializers.UUIDField(required=False, allow_null=True)
    cancelled_at = serializers.CharField(required=False, allow_null=True)
    line_count = serializers.CharField(required=False, allow_null=True)
    total_qty = serializers.CharField(required=False, allow_null=True)
    lines_preview = serializers.ListField(
        child=serializers.DictField(), required=False
    )


class OrderIndexItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    order_code = serializers.CharField()
    order_type = serializers.ChoiceField(choices=ORDER_TYPES)
    status = serializers.ChoiceField(choices=ORDER_STATUSES)
    supplier_identity = serializers.CharField(allow_null=True)
    supplier_name = serializers.CharField(allow_null=True)
    expected_at = serializers.DateField(allow_null=True)
    sent_to = serializers.CharField(allow_null=True, allow_blank=True)
    sent_at = serializers.CharField(allow_null=True)
    created_at = serializers.CharField()
    project_id = serializers.UUIDField(allow_null=True)
    project_code = serializers.CharField(allow_null=True)
    project_version_id = serializers.UUIDField(allow_null=True)
    revision_code = serializers.CharField(allow_null=True)
    line_count = serializers.CharField()
    total_qty = serializers.CharField(allow_null=True)
    good_qty = serializers.CharField()
    outstanding_qty = serializers.CharField()


class OrderIndexResponseSerializer(serializers.Serializer):
    orders = OrderIndexItemSerializer(many=True)


class SupplierUpsertSerializer(StrictSerializer):
    tax_id = serializers.CharField(max_length=100, allow_blank=False, trim_whitespace=True)
    name = serializers.CharField(max_length=300, allow_blank=False, trim_whitespace=True)
    details = SupplierDetailsSerializer(required=False, default=dict)
    confirmed = serializers.BooleanField()


class SupplierSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    tax_id = serializers.CharField()
    name = serializers.CharField()
    details = serializers.DictField()
    updated_at = serializers.CharField()


class SuppliersIndexResponseSerializer(serializers.Serializer):
    suppliers = SupplierSerializer(many=True)
