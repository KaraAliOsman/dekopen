"""Typed project metadata and engine-owned position inputs."""

from decimal import Decimal

from rest_framework import serializers

from engine_api.serializers import (
    EngineCalculateRequestSerializer,
    EngineCalculateResponseSerializer,
    DecimalStringField,
)
from pricing.serializers import StrictSerializer


class ProjectWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255)
    client_name = serializers.CharField(max_length=255)
    client_rut = serializers.CharField(max_length=50, required=False, allow_blank=True)
    client_email = serializers.EmailField(required=False, allow_blank=True)
    client_phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    client_giro = serializers.CharField(max_length=80, required=False, allow_blank=True)
    client_comuna = serializers.CharField(max_length=20, required=False, allow_blank=True)
    client_address = serializers.CharField(max_length=70, required=False, allow_blank=True)
    client_id = serializers.UUIDField(required=False, allow_null=True)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    notes_commercial = serializers.CharField(required=False, allow_blank=True)
    notes_internal = serializers.CharField(required=False, allow_blank=True)


class ResetPricingSerializer(StrictSerializer):
    expected_operation_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=2000, allow_blank=False)
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation required")
        return value


class ProjectUpdateSerializer(ProjectWriteSerializer):
    expected_updated_at = serializers.DateTimeField()


class PositionDesignSerializer(EngineCalculateRequestSerializer, StrictSerializer):
    nominal_width_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("250"))
    nominal_height_mm = DecimalStringField(
        max_digits=10, decimal_places=2, min_value=Decimal("250")
    )
    color = serializers.ChoiceField(choices=["WHITE"])


class PositionWriteSerializer(StrictSerializer):
    location_tag = serializers.CharField(max_length=100, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, max_value=2147483647)
    design = PositionDesignSerializer()


class PositionUpdateSerializer(PositionWriteSerializer):
    expected_updated_at = serializers.DateTimeField()


class PositionResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    position_index = serializers.IntegerField()
    location_tag = serializers.CharField(allow_null=True)
    quantity = serializers.IntegerField()
    typology = serializers.CharField()
    price_net = serializers.CharField()
    discount_pct = serializers.CharField()
    design = PositionDesignSerializer()
    bom = EngineCalculateResponseSerializer()
    updated_at = serializers.DateTimeField()


class ClientWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255, allow_blank=False)
    rut = serializers.CharField(max_length=50, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    giro = serializers.CharField(max_length=80, required=False, allow_blank=True)
    comuna = serializers.CharField(max_length=20, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ClientUpdateSerializer(ClientWriteSerializer):
    expected_updated_at = serializers.DateTimeField()


class ClientResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    rut = serializers.CharField()
    email = serializers.CharField()
    phone = serializers.CharField()
    address = serializers.CharField()
    giro = serializers.CharField(allow_null=True)
    comuna = serializers.CharField(allow_null=True)
    notes = serializers.CharField()
    is_active = serializers.BooleanField()
    updated_at = serializers.DateTimeField()


class ClientListResponseSerializer(serializers.Serializer):
    items = ClientResponseSerializer(many=True)


class ProjectVersionResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision_code = serializers.RegexField(r"^REV-[A-Z]+$")
    authority_version = serializers.CharField()
    bom_hash = serializers.RegexField(r"^[0-9a-f]{64}$", allow_null=True)
    snapshot_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$", allow_null=True)
    production_allowed = serializers.BooleanField(allow_null=True)
    documentary_complete = serializers.BooleanField(allow_null=True)
    emitted_at = serializers.DateTimeField()


class ProjectResponseSerializer(ProjectWriteSerializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(
        choices=[
            "DRAFT",
            "QUOTED",
            "APPROVED",
            "IN_PRODUCTION",
            "COMPLETED",
            "CANCELLED",
        ]
    )
    current_revision = serializers.RegexField(r"^REV-[A-Z]+$")
    total_price_net = serializers.CharField()
    total_price_tax = serializers.CharField()
    total_price_gross = serializers.CharField()
    pricing_current = serializers.BooleanField()
    current_pricing_operation_id = serializers.UUIDField(allow_null=True)
    currency = serializers.ChoiceField(choices=("CLP", "USD"))
    position_count = serializers.IntegerField()
    updated_at = serializers.DateTimeField()
    positions = PositionResponseSerializer(many=True, required=False)
    versions = ProjectVersionResponseSerializer(many=True, required=False)


class ProjectListResponseSerializer(serializers.Serializer):
    items = ProjectResponseSerializer(many=True)


class CloneProjectSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255, required=False)
    expected_updated_at = serializers.DateTimeField()


class SuccessorRequestSerializer(StrictSerializer):
    confirmed = serializers.BooleanField()
    expected_current_revision = serializers.RegexField(r"^REV-[A-Z]+$")

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("Successor confirmation required")
        return value


class DeletePositionSerializer(StrictSerializer):
    expected_updated_at = serializers.DateTimeField()


class PaymentRecordSerializer(StrictSerializer):
    operation_key = serializers.CharField(min_length=8, max_length=80)
    kind = serializers.ChoiceField(choices=("ANTICIPO", "PARCIAL", "SALDO"))
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=("TRANSFER", "CASH", "CARD", "CHECK", "OTHER"))
    reference = serializers.CharField(max_length=200, required=False, allow_blank=True)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    recorded_at = serializers.DateTimeField(required=False)


class PaymentVoidSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PaymentReceiptSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    receipt_code = serializers.CharField()
    payment_id = serializers.UUIDField()
    created_at = serializers.CharField()


class PaymentReceiptAccessSerializer(PaymentReceiptSerializer):
    signed_url = serializers.CharField()
    expires_in = serializers.IntegerField()


class ProjectPaymentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    receipt_id = serializers.UUIDField(allow_null=True)
    receipt_code = serializers.CharField(allow_null=True)
    kind = serializers.CharField()
    amount = serializers.CharField()
    method = serializers.CharField()
    reference = serializers.CharField(allow_null=True)
    note = serializers.CharField(allow_null=True)
    recorded_by = serializers.CharField(allow_null=True)
    recorded_at = serializers.CharField()
    voided_at = serializers.CharField(allow_null=True)
    void_reason = serializers.CharField(allow_null=True)
    created_at = serializers.CharField()


class ProjectDteEnvioSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    track_id = serializers.CharField(allow_null=True)
    attempted = serializers.BooleanField()


class ProjectDteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    dte_type = serializers.IntegerField()
    folio = serializers.IntegerField()
    issued_at = serializers.CharField()
    envio = ProjectDteEnvioSerializer(allow_null=True, required=False)


class ProjectDteAccessSerializer(ProjectDteSerializer):
    signed_url = serializers.CharField()
    tributario_signed_url = serializers.CharField(allow_null=True)
    expires_in = serializers.IntegerField()


class ProjectCreditNoteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    credit_code = serializers.CharField()
    invoice_id = serializers.UUIDField()
    invoice_code = serializers.CharField(allow_null=True)
    project_id = serializers.UUIDField()
    dte = ProjectDteSerializer(allow_null=True, required=False)
    created_at = serializers.CharField()


class ProjectCreditNoteAccessSerializer(ProjectCreditNoteSerializer):
    signed_url = serializers.CharField()
    tributario_signed_url = serializers.CharField(allow_null=True)
    expires_in = serializers.IntegerField()


class ProjectCreditNoteEmitSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


class ProjectInvoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_code = serializers.CharField()
    project_id = serializers.UUIDField()
    revision_code = serializers.CharField(allow_null=True)
    credit_note = ProjectCreditNoteSerializer(allow_null=True)
    dte = ProjectDteSerializer(allow_null=True, required=False)
    created_at = serializers.CharField()


class ProjectInvoiceAccessSerializer(ProjectInvoiceSerializer):
    signed_url = serializers.CharField()
    tributario_signed_url = serializers.CharField(allow_null=True)
    expires_in = serializers.IntegerField()


class SiiCafSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    tipo_dte = serializers.IntegerField()
    folio_desde = serializers.IntegerField()
    folio_hasta = serializers.IntegerField()
    folio_actual = serializers.IntegerField()
    remaining = serializers.IntegerField()
    rut_emisor = serializers.CharField()
    razon_social = serializers.CharField()
    acteco = serializers.IntegerField(allow_null=True)
    created_at = serializers.CharField()


class SiiCafListSerializer(serializers.Serializer):
    items = SiiCafSerializer(many=True)


class SiiCafUploadSerializer(serializers.Serializer):
    caf_xml = serializers.CharField(max_length=131072)
    giro_emis = serializers.CharField(max_length=80, required=False, allow_blank=True)
    dir_origen = serializers.CharField(max_length=70, required=False, allow_blank=True)
    cmna_origen = serializers.CharField(max_length=20, required=False, allow_blank=True)
    # ActECO is the 6-digit economic-activity code the SII validates against the
    # emisor's registered activity; the CAF does not carry it, so it is
    # operator-typed — a format bound is the only honest local check.
    acteco = serializers.IntegerField(
        required=False, allow_null=True, min_value=100000, max_value=999999
    )


class SiiCertificateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    subject = serializers.CharField()
    rut_firma = serializers.CharField()
    serial_number = serializers.CharField(allow_null=True)
    valid_from = serializers.CharField()
    valid_to = serializers.CharField()
    nro_resol = serializers.IntegerField()
    fch_resol = serializers.CharField()
    active = serializers.BooleanField()
    created_at = serializers.CharField()


class SiiCertificateStatusSerializer(serializers.Serializer):
    certificate = SiiCertificateSerializer(allow_null=True)


class SiiCertificateUploadSerializer(serializers.Serializer):
    pfx_b64 = serializers.CharField(max_length=90000)
    password = serializers.CharField(max_length=200, required=False, allow_blank=True)
    nro_resol = serializers.IntegerField(min_value=0)
    fch_resol = serializers.CharField(max_length=10)


class SiiEnvioSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    dte_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=("PENDING", "ACCEPTED", "REJECTED"))
    track_id = serializers.CharField(allow_null=True)
    glosa = serializers.CharField(allow_null=True)
    sent_at = serializers.CharField()
    attempted = serializers.BooleanField()


class SiiEnvioSendSerializer(StrictSerializer):
    # Explicit human recovery: a prior submit attempt may have reached the SII
    # without its response reaching us — resending identical bytes is only
    # allowed as a deliberate decision, never an automatic retry.
    resubmit = serializers.BooleanField(required=False, default=False)


class SiiEnvioAccessSerializer(SiiEnvioSerializer):
    signed_url = serializers.CharField()


class PaymentsSummarySerializer(serializers.Serializer):
    payments = ProjectPaymentSerializer(many=True)
    invoices = ProjectInvoiceSerializer(many=True)
    collected = serializers.CharField()
    quote_total_gross = serializers.CharField(allow_null=True)
    balance = serializers.CharField(allow_null=True)
    currency = serializers.ChoiceField(choices=("CLP", "USD"))
    status = serializers.ChoiceField(choices=("NO_DEAL", "PENDING", "PARTIAL", "PAID"))
    sealed_revision = serializers.CharField(allow_null=True)


class PaymentRecordResponseSerializer(PaymentsSummarySerializer):
    payment = ProjectPaymentSerializer()
    receipt = PaymentReceiptSerializer(allow_null=True)


class PaymentLinkCreateSerializer(StrictSerializer):
    operation_key = serializers.CharField(min_length=8, max_length=80)
    kind = serializers.ChoiceField(choices=("ANTICIPO", "PARCIAL", "SALDO"))
    # Accept decimal spellings ("1180000.00") at the edge — the service keeps
    # the authoritative integer-CLP check so "1180.50" still gets a domain 422.
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    payer_email = serializers.EmailField(max_length=200)
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True)


class PaymentLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    operation_key = serializers.CharField()
    kind = serializers.CharField()
    amount = serializers.CharField()
    payer_email = serializers.CharField()
    subject = serializers.CharField()
    status = serializers.ChoiceField(
        choices=("DISPATCHING", "PENDING", "PAID", "FAILED", "UNCERTAIN", "CANCELLED")
    )
    environment = serializers.ChoiceField(choices=("sandbox", "production"))
    url = serializers.CharField(allow_null=True)
    project_payment_id = serializers.CharField(allow_null=True)
    created_at = serializers.CharField()
    updated_at = serializers.CharField()


class PaymentLinksResponseSerializer(serializers.Serializer):
    links = PaymentLinkSerializer(many=True)


class PaymentLinkResponseSerializer(serializers.Serializer):
    link = PaymentLinkSerializer()


class PaymentIntegrationSerializer(StrictSerializer):
    api_url = serializers.ChoiceField(
        choices=("https://sandbox.flow.cl/api", "https://www.flow.cl/api")
    )
    api_key = serializers.CharField(min_length=10, max_length=100)
    secret_key = serializers.CharField(
        min_length=10, max_length=100, required=False, write_only=True, allow_blank=True
    )
    payer_return_url = serializers.CharField(
        max_length=500, required=False, allow_blank=True
    )
    enabled = serializers.BooleanField(required=False, default=True)


class PaymentIntegrationStatusSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    api_url = serializers.CharField(required=False)
    api_key_preview = serializers.CharField(required=False)
    payer_return_url = serializers.CharField(required=False, allow_null=True)
    enabled = serializers.BooleanField(required=False)
    updated_at = serializers.CharField(required=False)


class DesignAlternativesRequestSerializer(serializers.Serializer):
    brief = serializers.CharField(max_length=2000, trim_whitespace=True)
    count = serializers.IntegerField(min_value=1, max_value=3, required=False, default=2)
    system_id = serializers.UUIDField()
    operation_key = serializers.CharField(max_length=120)
    width_mm = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    height_mm = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )

    def validate_brief(self, value):
        if not value.strip():
            raise serializers.ValidationError("Escribe una intención de diseño.")
        return value

    def validate_operation_key(self, value):
        if not value.strip():
            raise serializers.ValidationError("Falta la clave de operación.")
        return value


class DesignAlternativesResponseSerializer(serializers.Serializer):
    audit_id = serializers.CharField()
    model = serializers.CharField()
    credits_debited = serializers.IntegerField()
    alternatives = serializers.ListField(child=serializers.DictField())
    rejected = serializers.ListField(child=serializers.DictField())
    notes = serializers.CharField(allow_null=True, required=False)


class DesignAssistRequestSerializer(serializers.Serializer):
    prompt = serializers.CharField(min_length=2, max_length=2000)
    operation_key = serializers.CharField(min_length=8, max_length=120)
    product = serializers.DictField()
    # The live system the product is being edited under — may lead the
    # persisted position's system until the estimator saves.
    system_id = serializers.UUIDField()


class DesignAssistResponseSerializer(serializers.Serializer):
    audit_id = serializers.CharField()
    model = serializers.CharField()
    credits_debited = serializers.IntegerField()
    ops = serializers.ListField(child=serializers.DictField())
    rejected = serializers.ListField(child=serializers.DictField())
    notes = serializers.CharField(allow_null=True)


class OrgBrandingSerializer(serializers.Serializer):
    """Org white-label identity rendered on emitted documents."""

    name = serializers.CharField()
    tax_id = serializers.CharField(allow_null=True, allow_blank=True)
    commercial_name = serializers.CharField(allow_null=True, allow_blank=True)
    giro = serializers.CharField(allow_null=True, allow_blank=True)
    brand_address = serializers.CharField(allow_null=True, allow_blank=True)
    brand_phone = serializers.CharField(allow_null=True, allow_blank=True)
    brand_email = serializers.CharField(allow_null=True, allow_blank=True)
    brand_logo_key = serializers.CharField(allow_null=True, allow_blank=True)
    brand_logo_sha256 = serializers.CharField(allow_null=True, allow_blank=True)


class OrgBrandingWriteSerializer(StrictSerializer):
    commercial_name = serializers.CharField(
        allow_null=True, allow_blank=True, required=False, max_length=255
    )
    giro = serializers.CharField(
        allow_null=True, allow_blank=True, required=False, max_length=255
    )
    brand_address = serializers.CharField(
        allow_null=True, allow_blank=True, required=False, max_length=255
    )
    brand_phone = serializers.CharField(
        allow_null=True, allow_blank=True, required=False, max_length=64
    )
    brand_email = serializers.CharField(
        allow_null=True, allow_blank=True, required=False, max_length=255
    )
