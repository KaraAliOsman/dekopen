"""Contract serializers for the customer-approval portal."""

from rest_framework import serializers


class ShareQuoteResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    expires_at = serializers.DateTimeField()
    path = serializers.CharField()


class PortalOrganizationSerializer(serializers.Serializer):
    name = serializers.CharField(allow_null=True, allow_blank=True)
    tax_id = serializers.CharField(allow_null=True, allow_blank=True)
    commercial_name = serializers.CharField(allow_null=True, allow_blank=True)
    brand_address = serializers.CharField(allow_null=True, allow_blank=True)
    brand_phone = serializers.CharField(allow_null=True, allow_blank=True)
    brand_email = serializers.CharField(allow_null=True, allow_blank=True)
    brand_logo_url = serializers.CharField(allow_null=True, allow_blank=True)
    brand_color = serializers.CharField(allow_null=True, allow_blank=True)
    dekopen_credit = serializers.BooleanField(default=False)


class PortalPositionSerializer(serializers.Serializer):
    id = serializers.CharField(allow_blank=True)
    position_index = serializers.IntegerField(allow_null=True)
    quantity = serializers.IntegerField(allow_null=True)
    typology = serializers.CharField(allow_null=True, allow_blank=True)
    location_tag = serializers.CharField(allow_null=True, allow_blank=True)
    width_mm = serializers.CharField(allow_blank=True)
    height_mm = serializers.CharField(allow_blank=True)
    color_interior = serializers.CharField(allow_null=True, allow_blank=True)
    color_exterior = serializers.CharField(allow_null=True, allow_blank=True)
    # D05: sealed per-face finish detail (declared render swatch + texture).
    color_interior_detail = serializers.DictField(allow_null=True)
    color_exterior_detail = serializers.DictField(allow_null=True)
    glass_specs = serializers.ListField(child=serializers.CharField())
    finish = serializers.CharField(allow_null=True, allow_blank=True)
    price_net = serializers.CharField(allow_null=True)
    discount_pct = serializers.CharField(allow_null=True, allow_blank=True)
    parametric_tree = serializers.JSONField(allow_null=True)


class PortalPaymentSerializer(serializers.Serializer):
    status = serializers.CharField()
    collected = serializers.CharField()
    balance = serializers.CharField()


class PortalQuoteSerializer(serializers.Serializer):
    schema = serializers.CharField()
    organization = PortalOrganizationSerializer()
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    client_name = serializers.CharField()
    revision_code = serializers.CharField()
    emitted_at = serializers.DateTimeField()
    currency = serializers.CharField()
    payment_terms = serializers.CharField(allow_null=True, allow_blank=True)
    notes_commercial = serializers.CharField(allow_null=True, allow_blank=True)
    total_price_net = serializers.CharField(allow_null=True)
    total_price_tax = serializers.CharField(allow_null=True)
    total_price_gross = serializers.CharField(allow_null=True)
    extras = serializers.ListField(child=serializers.DictField())
    positions = PortalPositionSerializer(many=True)
    payment = PortalPaymentSerializer(allow_null=True)
    payment_url = serializers.CharField(allow_null=True)
    valid_until = serializers.CharField(allow_null=True)
    validity_expired = serializers.BooleanField()
    superseded = serializers.BooleanField()
    expires_at = serializers.DateTimeField()
    approval_status = serializers.CharField()
    decided_by = serializers.CharField(allow_null=True)
    decided_at = serializers.DateTimeField(allow_null=True)
    decided_note = serializers.CharField(allow_null=True)
    quote_pdf_url = serializers.CharField(allow_null=True)


class ApprovalRecordSerializer(serializers.Serializer):
    id = serializers.CharField()
    status = serializers.CharField()
    revision_code = serializers.CharField()
    decided_by = serializers.CharField(allow_null=True)
    decided_at = serializers.DateTimeField(allow_null=True)
    decided_note = serializers.CharField(allow_null=True)
    expires_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)
    view_count = serializers.IntegerField()
    last_viewed_at = serializers.DateTimeField(allow_null=True)


class InternalApprovalSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class InternalApprovalResultSerializer(serializers.Serializer):
    project_status = serializers.CharField()


class DecideRequestSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "DECLINED"])
    decided_by = serializers.CharField(max_length=255)
    decided_rut = serializers.CharField(required=False, allow_blank=True, max_length=32)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_decided_by(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("required")
        return trimmed
