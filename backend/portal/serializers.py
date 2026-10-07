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
    dekopen_credit = serializers.BooleanField(required=False)


class PortalPositionSerializer(serializers.Serializer):
    id = serializers.CharField(allow_blank=True)
    position_index = serializers.IntegerField(allow_null=True)
    quantity = serializers.IntegerField(allow_null=True)
    typology = serializers.CharField(allow_null=True, allow_blank=True)
    location_tag = serializers.CharField(allow_null=True, allow_blank=True)
    is_option = serializers.BooleanField(required=False)
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
    payable = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    simulated = serializers.BooleanField()


class DecisionEventSerializer(serializers.Serializer):
    """Evidencia de decisión append-only — pública (sin PII extra) en el
    portal y completa para el estimador; mismo contrato, dos lecturas."""

    decision = serializers.CharField(allow_null=True, required=False)
    decided_by = serializers.CharField(allow_null=True, required=False)
    decided_rut = serializers.CharField(allow_null=True, required=False)
    decided_note = serializers.CharField(allow_null=True, required=False)
    decision_ip = serializers.CharField(allow_null=True, required=False)
    decision_user_agent = serializers.CharField(allow_null=True, required=False)
    acceptance_text = serializers.CharField(allow_null=True, required=False)
    revision_code = serializers.CharField(allow_null=True, required=False)
    bom_hash = serializers.CharField(allow_null=True, required=False)
    positions = serializers.ListField(
        child=serializers.DictField(), required=False, allow_null=True
    )
    created_at = serializers.DateTimeField(allow_null=True, required=False)


class PortalQuoteSerializer(serializers.Serializer):
    schema = serializers.CharField()
    # P10 — el estado honesto del enlace: live/approved/declined/
    # changes_requested/superseded/validity_expired/link_expired/revoked.
    state = serializers.CharField()
    organization = PortalOrganizationSerializer()
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    client_name = serializers.CharField()
    revision_code = serializers.CharField()
    current_revision = serializers.CharField()
    emitted_at = serializers.DateTimeField()
    currency = serializers.CharField()
    payment_terms = serializers.CharField(allow_null=True, allow_blank=True)
    doc_terms = serializers.DictField(required=False)
    notes_commercial = serializers.CharField(allow_null=True, allow_blank=True)
    total_price_net = serializers.CharField(allow_null=True)
    total_price_tax = serializers.CharField(allow_null=True)
    total_price_gross = serializers.CharField(allow_null=True)
    extras = serializers.ListField(child=serializers.DictField())
    positions = PortalPositionSerializer(many=True)
    payment = PortalPaymentSerializer(allow_null=True)
    follow_available = serializers.BooleanField()
    acceptance_text = serializers.CharField(allow_null=True)
    decision_event = DecisionEventSerializer(allow_null=True)
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
    channel = serializers.CharField()
    decided_by = serializers.CharField(allow_null=True)
    decided_at = serializers.DateTimeField(allow_null=True)
    decided_note = serializers.CharField(allow_null=True)
    evidence = DecisionEventSerializer(allow_null=True, required=False)
    expires_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)
    view_count = serializers.IntegerField()
    first_viewed_at = serializers.DateTimeField(allow_null=True)
    last_viewed_at = serializers.DateTimeField(allow_null=True)


class LinkExpirySerializer(serializers.Serializer):
    expires_at = serializers.DateTimeField()


class InternalApprovalSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class InternalApprovalResultSerializer(serializers.Serializer):
    project_status = serializers.CharField()


class DecideRequestSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["APPROVED", "DECLINED", "CHANGES_REQUESTED"]
    )
    decided_by = serializers.CharField(max_length=255)
    decided_rut = serializers.CharField(required=False, allow_blank=True, max_length=32)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    # P10 — aceptación literal obligatoria al aprobar + alternativas que
    # el cliente marcó (ids sellados con is_option; el servicio valida).
    accepted = serializers.BooleanField(required=False, default=False)
    marked_position_ids = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False
    )

    def validate_decided_by(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("required")
        return trimmed

    def validate(self, attrs):
        if attrs.get("decision") == "CHANGES_REQUESTED" and not str(
            attrs.get("note") or ""
        ).strip():
            raise serializers.ValidationError({"note": "required"})
        if attrs.get("decision") == "APPROVED":
            if not str(attrs.get("decided_rut") or "").strip():
                raise serializers.ValidationError({"decided_rut": "required"})
            if not attrs.get("accepted"):
                raise serializers.ValidationError({"accepted": "required"})
        return attrs


class FollowQuoteResultSerializer(serializers.Serializer):
    follow_token = serializers.CharField(allow_null=True)


class PortalPayRequestSerializer(serializers.Serializer):
    payer_email = serializers.EmailField(required=False, allow_blank=True)


class PortalPayResultSerializer(serializers.Serializer):
    payment_url = serializers.CharField(allow_null=True)
    flow_token = serializers.CharField(allow_null=True)
    amount = serializers.CharField(allow_null=True)
    simulated = serializers.BooleanField()


class PortalPaymentStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    amount = serializers.CharField()
    kind = serializers.CharField()
    payer_return_url = serializers.CharField(allow_null=True)
    project_id = serializers.CharField()
