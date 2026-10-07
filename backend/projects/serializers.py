"""Typed project metadata and engine-owned position inputs."""

from decimal import Decimal, InvalidOperation

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
    # P18 — declaración térmica OGUC 4.1.10 (PATCH del proyecto).
    thermal_zone = serializers.ChoiceField(
        choices=("A", "B", "C", "D", "E", "F", "G", "H", "I"),
        required=False, allow_null=True,
    )
    thermal_use = serializers.ChoiceField(
        choices=("RESIDENTIAL", "EQUIPMENT"), required=False
    )
    thermal_wall_areas = serializers.DictField(
        required=False, allow_null=True, allow_empty=True
    )

    def validate_thermal_wall_areas(self, value):
        """{N|OP|S|OGT: m² expuestos} — claves de orientación de la norma,
        superficies numéricas positivas."""
        if value is None:
            return value
        allowed = {"N", "OP", "S", "OGT"}
        for key, area in value.items():
            if key not in allowed:
                raise serializers.ValidationError(
                    f"orientación inválida: {key}"
                )
            try:
                number = Decimal(str(area))
            except (InvalidOperation, ValueError) as error:
                raise serializers.ValidationError(
                    f"superficie no numérica en {key}"
                ) from error
            if number <= 0 or number > Decimal("100000"):
                raise serializers.ValidationError(
                    f"superficie fuera de rango en {key}"
                )
        return value


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
    # Validated against the system's declared finishes downstream
    # (adapter has params; serializers don't).
    color = serializers.CharField(max_length=50)


class VanoRecordSerializer(StrictSerializer):
    """Registro del vano de obra: 1–3 medidas por eje (manda la menor),
    tipo de muro y escuadra/desplome si se midió."""
    width_points_mm = serializers.ListField(
        child=DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1")),
        min_length=1, max_length=3,
    )
    height_points_mm = serializers.ListField(
        child=DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1")),
        min_length=1, max_length=3,
    )
    wall_type = serializers.ChoiceField(
        choices=("MASONRY", "CONCRETE", "PARTITION", "WOOD"),
        required=False, allow_null=True,
    )
    square_mm = DecimalStringField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    plumb_mm = DecimalStringField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)


class FabricationLockSerializer(StrictSerializer):
    """Fijación manual de la medida de fabricación — queda registrada."""
    width_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1"))
    height_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1"))
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PositionMeasurementSerializer(StrictSerializer):
    vano = VanoRecordSerializer(required=False, allow_null=True)
    mounting_rule_id = serializers.UUIDField(required=False, allow_null=True)
    fabrication_lock = FabricationLockSerializer(required=False, allow_null=True)


class PositionWriteSerializer(StrictSerializer):
    location_tag = serializers.CharField(max_length=100, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, max_value=2147483647)
    design = PositionDesignSerializer()
    measurement = PositionMeasurementSerializer(required=False, allow_null=True)
    thermal_orientation = serializers.ChoiceField(
        choices=("N", "OP", "S", "OGT", "ROOF"),
        required=False, allow_null=True,
    )


class PositionUpdateSerializer(PositionWriteSerializer):
    expected_updated_at = serializers.DateTimeField()


class MeasurementBreakdownSerializer(serializers.Serializer):
    side = serializers.CharField()
    label = serializers.CharField()
    mm = serializers.CharField()


class MeasurementWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class MeasurementResolutionSerializer(serializers.Serializer):
    vano_width_mm = serializers.CharField(allow_null=True)
    vano_height_mm = serializers.CharField(allow_null=True)
    width_spread_mm = serializers.CharField()
    height_spread_mm = serializers.CharField()
    fabrication_width_mm = serializers.CharField()
    fabrication_height_mm = serializers.CharField()
    fabrication_source = serializers.ChoiceField(
        choices=("DERIVED", "MANUAL_LOCK", "DECLARED")
    )
    used_width_mm = serializers.CharField()
    used_height_mm = serializers.CharField()
    coherent = serializers.BooleanField()
    breakdown = MeasurementBreakdownSerializer(many=True)
    warnings = MeasurementWarningSerializer(many=True)


class MountingRuleResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    system_id = serializers.UUIDField()
    org_id = serializers.UUIDField(allow_null=True)
    code = serializers.ChoiceField(
        choices=("EN_VANO", "PREMARCO", "SOBRE_VANO", "TRASLAPADO", "RENOVACION")
    )
    version = serializers.IntegerField()
    label = serializers.CharField()
    authority = serializers.DictField()
    data_provenance = serializers.ChoiceField(
        choices=("SEED_SYNTHETIC", "MANUAL", "IMPORT", "LEGACY_UNVERIFIED")
    )
    review_pending = serializers.BooleanField()


class MountingRuleListResponseSerializer(serializers.Serializer):
    items = MountingRuleResponseSerializer(many=True)


class MeasurementResponseSerializer(serializers.Serializer):
    state = serializers.ChoiceField(
        choices=("CLIENT_DECLARED", "SITE_RECTIFIED", "CONFIRMED")
    )
    confirmed_at = serializers.DateTimeField(allow_null=True)
    confirmed_by = serializers.UUIDField(allow_null=True)
    vano = VanoRecordSerializer(allow_null=True)
    mounting_rule = MountingRuleResponseSerializer(allow_null=True)
    fabrication_lock = serializers.DictField(allow_null=True)
    resolution = MeasurementResolutionSerializer(allow_null=True)


class MeasurementResolveSerializer(StrictSerializer):
    """Preview del desglose vano → fabricación: mismo motor que el guardado."""
    system_id = serializers.UUIDField()
    vano = VanoRecordSerializer(required=False, allow_null=True)
    mounting_rule_id = serializers.UUIDField(required=False, allow_null=True)
    fabrication_lock = FabricationLockSerializer(required=False, allow_null=True)
    width_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1"))
    height_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1"))


class MeasurementResolveResponseSerializer(serializers.Serializer):
    resolution = MeasurementResolutionSerializer()
    mounting_rule = MountingRuleResponseSerializer(allow_null=True)


class MeasurementConfirmSerializer(StrictSerializer):
    confirmed = serializers.BooleanField()


class PositionResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    position_index = serializers.IntegerField()
    location_tag = serializers.CharField(allow_null=True)
    quantity = serializers.IntegerField()
    typology = serializers.CharField()
    price_net = serializers.CharField()
    discount_pct = serializers.CharField()
    thermal_orientation = serializers.ChoiceField(
        choices=("N", "OP", "S", "OGT", "ROOF"), allow_null=True
    )
    design = PositionDesignSerializer()
    bom = EngineCalculateResponseSerializer()
    measurement = MeasurementResponseSerializer()
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
    sealed_price_net = serializers.CharField(allow_null=True, required=False)
    sealed_price_tax = serializers.CharField(allow_null=True, required=False)
    sealed_price_gross = serializers.CharField(allow_null=True, required=False)
    sealed_currency = serializers.CharField(allow_null=True, required=False)


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


class QuotationApprovalSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    expires_at = serializers.DateTimeField(allow_null=True)
    view_count = serializers.IntegerField()
    first_viewed_at = serializers.DateTimeField(allow_null=True)
    last_viewed_at = serializers.DateTimeField(allow_null=True)
    decided_by = serializers.CharField(allow_null=True)
    decided_at = serializers.DateTimeField(allow_null=True)
    decided_note = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class QuotationItemSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    client_name = serializers.CharField()
    project_status = serializers.CharField()
    current_revision = serializers.CharField()
    currency = serializers.CharField()
    total_price_gross = serializers.CharField()
    versions_count = serializers.IntegerField()
    last_sealed_at = serializers.DateTimeField(allow_null=True)
    approval = QuotationApprovalSerializer(allow_null=True)
    quote_state = serializers.CharField()


class QuotationListResponseSerializer(serializers.Serializer):
    items = QuotationItemSerializer(many=True)


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


class PositionMoveSerializer(StrictSerializer):
    """Explicit reorder of the printed position order — `position_index` is
    server-owned, so a PUT can never edit it directly; the move endpoint
    shifts the whole run atomically under the position's optimistic lock."""

    to_index = serializers.IntegerField(min_value=1)
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
    partial = serializers.BooleanField(required=False)
    credit_amount_gross = serializers.CharField(allow_null=True, required=False)
    dte = ProjectDteSerializer(allow_null=True, required=False)
    created_at = serializers.CharField()


class ProjectCreditNoteAccessSerializer(ProjectCreditNoteSerializer):
    signed_url = serializers.CharField()
    tributario_signed_url = serializers.CharField(allow_null=True)
    expires_in = serializers.IntegerField()


class ProjectCreditNoteEmitSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False,
        min_value=Decimal("0.01"),
    )


class ProjectInvoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_code = serializers.CharField()
    project_id = serializers.UUIDField()
    revision_code = serializers.CharField(allow_null=True)
    total_net = serializers.CharField(allow_null=True, required=False)
    total_tax = serializers.CharField(allow_null=True, required=False)
    total_gross = serializers.CharField(allow_null=True, required=False)
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


class SiiIntegrationStateSerializer(serializers.Serializer):
    adapter = serializers.ChoiceField(choices=("sii-ws", "mock", "none"))
    certified = serializers.BooleanField()
    certificate = serializers.BooleanField()
    caf_available = serializers.BooleanField()


class SiiCertificateStatusSerializer(serializers.Serializer):
    certificate = SiiCertificateSerializer(allow_null=True)
    integration = SiiIntegrationStateSerializer()


class SiiCertificateUploadSerializer(serializers.Serializer):
    pfx_b64 = serializers.CharField(max_length=90000)
    password = serializers.CharField(max_length=200, required=False, allow_blank=True)
    nro_resol = serializers.IntegerField(min_value=0)
    fch_resol = serializers.CharField(max_length=10)


class SiiEnvioSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    dte_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=("PENDING", "ACCEPTED", "OBSERVED", "REJECTED")
    )
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


class CollectionQuotaSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=("ANTICIPO", "SALDO"))
    amount = serializers.CharField()
    covered = serializers.CharField()
    due_at = serializers.CharField(allow_null=True)
    due_basis = serializers.CharField()
    pct = serializers.CharField()
    pct_source = serializers.ChoiceField(choices=("terms", "default"))
    state = serializers.ChoiceField(choices=("PENDING", "PAID", "OVERDUE"))


class CollectionMovementSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=("payment", "payment_void", "link", "invoice", "credit_note", "envio")
    )
    id = serializers.UUIDField()
    kind = serializers.CharField(allow_null=True)
    amount = serializers.CharField(allow_null=True)
    method = serializers.CharField(allow_null=True)
    voided = serializers.BooleanField()
    at = serializers.CharField(allow_null=True)
    actor = serializers.CharField(allow_null=True)
    code = serializers.CharField(allow_null=True)
    document_id = serializers.CharField(allow_null=True)
    status = serializers.CharField(allow_null=True)


class ReminderDraftSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body = serializers.CharField()
    model = serializers.CharField(required=False, allow_null=True)
    created_at = serializers.CharField(required=False, allow_null=True)


class PaymentsSummarySerializer(serializers.Serializer):
    payments = ProjectPaymentSerializer(many=True)
    invoices = ProjectInvoiceSerializer(many=True)
    schedule = CollectionQuotaSerializer(many=True)
    movements = CollectionMovementSerializer(many=True)
    sii = SiiIntegrationStateSerializer()
    reminder = ReminderDraftSerializer(allow_null=True)
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
    expires_at = serializers.CharField(allow_null=True)
    expired = serializers.BooleanField(required=False, default=False)
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
    api_key = serializers.CharField(
        min_length=10, max_length=100, required=False, allow_blank=True
    )
    secret_key = serializers.CharField(
        min_length=10, max_length=100, required=False, write_only=True, allow_blank=True
    )
    payer_return_url = serializers.CharField(
        max_length=500, required=False, allow_blank=True
    )
    enabled = serializers.BooleanField(required=False, default=True)


class PaymentIntegrationStatusSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    provider_mode = serializers.ChoiceField(
        choices=("mock", "live"), required=False, allow_null=True
    )
    api_url = serializers.CharField(required=False)
    api_key_preview = serializers.CharField(required=False)
    payer_return_url = serializers.CharField(required=False, allow_null=True)
    enabled = serializers.BooleanField(required=False)
    updated_at = serializers.CharField(required=False)


class CollectionReminderPrepareSerializer(StrictSerializer):
    operation_key = serializers.CharField(min_length=8, max_length=120)


class CollectionReminderDraftResponseSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body = serializers.CharField()
    model = serializers.CharField()
    audit_id = serializers.CharField()
    credits_debited = serializers.IntegerField()
    client_email = serializers.CharField(allow_null=True)
    amount_due = serializers.CharField()
    currency = serializers.CharField()


class CollectionReminderSendSerializer(StrictSerializer):
    subject = serializers.CharField(min_length=1, max_length=200)
    body = serializers.CharField(min_length=1, max_length=4000)


class CollectionReminderSendResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("QUEUED", "SENT", "FAILED", "SKIPPED"))
    to = serializers.CharField()
    mail_id = serializers.CharField(allow_null=True)


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
    # IA2 §3 — pregunta tipada con opciones reales (chips en la UI).
    clarify = serializers.DictField(allow_null=True, required=False)
    # IA2 §4 — proyección estructural post-ops para la vista previa.
    simulation = serializers.DictField(allow_null=True, required=False)


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
    brand_color = serializers.CharField(allow_null=True, allow_blank=True)
    doc_dekopen_credit = serializers.BooleanField()
    vano_spread_tolerance_mm = serializers.DecimalField(
        max_digits=6, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    doc_paper_size = serializers.CharField()
    doc_terms = serializers.DictField(child=serializers.CharField())
    workshop_label_format = serializers.CharField()
    remnant_alert_days = serializers.IntegerField()
    doc_validity_days = serializers.IntegerField()


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
    brand_color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$",
        allow_null=True,
        allow_blank=True,
        required=False,
        max_length=7,
    )
    doc_dekopen_credit = serializers.BooleanField(required=False)
    vano_spread_tolerance_mm = DecimalStringField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        required=False,
        allow_null=True,
    )
    doc_paper_size = serializers.ChoiceField(
        choices=(("LETTER", "Carta"), ("LEGAL", "Oficio"), ("A4", "A4")),
        required=False,
        allow_null=True,
    )
    workshop_label_format = serializers.ChoiceField(
        choices=(
            ("GRID", "Grilla A4/Carta"),
            ("THERMAL_100X50", "Rollo térmico 100×50 mm"),
        ),
        required=False,
        allow_null=True,
    )
    remnant_alert_days = serializers.IntegerField(
        min_value=1, max_value=365, required=False
    )
    doc_terms = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=4000),
        required=False,
        allow_null=True,
    )
    doc_validity_days = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=365,
    )


# ─── P18 — desempeño térmico (OGUC 4.1.10) ─────────────────────────────────

ORIENTATIONS = ("N", "OP", "S", "OGT", "ROOF")
THERMAL_VERDICTS = ("COMPLIES", "FAILS", "INSUFFICIENT_DATA", "NO_REQUIREMENT")


class ThermalMissingSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField(allow_null=True)


class PaneThermalSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    article_sku = serializers.CharField(allow_null=True)
    area_m2 = serializers.CharField()
    perimeter_m = serializers.CharField()
    ug_w_m2k = serializers.CharField(allow_null=True)
    ug_authority = serializers.CharField(allow_null=True)
    psi_w_m_k = serializers.CharField(allow_null=True)
    spacer_code = serializers.CharField(allow_null=True)
    psi_authority = serializers.CharField(allow_null=True)


class FrameZoneThermalSerializer(serializers.Serializer):
    member_group = serializers.CharField()
    area_m2 = serializers.CharField()
    uf_w_m2k = serializers.CharField(allow_null=True)
    authority = serializers.CharField(allow_null=True)
    source = serializers.CharField(allow_null=True)


class UwComputationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("OK", "UNKNOWN"))
    uw_w_m2k = serializers.CharField(allow_null=True)
    ag_m2 = serializers.CharField()
    af_m2 = serializers.CharField()
    lg_m = serializers.CharField()
    numerator_w_m_k = serializers.CharField(allow_null=True)
    authority = serializers.CharField(allow_null=True)
    panes = PaneThermalSerializer(many=True)
    frame = FrameZoneThermalSerializer(many=True)
    missing = ThermalMissingSerializer(many=True)


class ResolvedClassesSerializer(serializers.Serializer):
    air_class = serializers.IntegerField(allow_null=True)
    water_class = serializers.CharField(allow_null=True)
    wind_class = serializers.CharField(allow_null=True)
    report_ref = serializers.CharField(allow_null=True)
    laboratory = serializers.CharField(allow_null=True)
    tested_on = serializers.CharField(allow_null=True)
    tested_width_mm = serializers.CharField(allow_null=True)
    tested_height_mm = serializers.CharField(allow_null=True)
    authority = serializers.CharField(allow_null=True)
    scope_exceeded = serializers.BooleanField()


class ThermalCauseSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField(allow_null=True)


class PositionThermalSerializer(serializers.Serializer):
    verdict = serializers.ChoiceField(choices=THERMAL_VERDICTS)
    uw = UwComputationSerializer()
    classes = ResolvedClassesSerializer(allow_null=True)
    causes = ThermalCauseSerializer(many=True)
    air_class_required = serializers.IntegerField(allow_null=True)
    roof_u_max = serializers.CharField(allow_null=True)
    u_max = serializers.CharField(allow_null=True)
    window_pct_max = serializers.IntegerField(allow_null=True)


class ThermalPositionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    position_index = serializers.IntegerField()
    location_tag = serializers.CharField(allow_null=True)
    quantity = serializers.IntegerField()
    typology = serializers.CharField()
    thermal_orientation = serializers.ChoiceField(
        choices=ORIENTATIONS, allow_null=True
    )
    width_mm = serializers.CharField()
    height_mm = serializers.CharField()
    surface_m2 = serializers.CharField()
    thermal = PositionThermalSerializer()


class OrientationComplianceSerializer(serializers.Serializer):
    orientation = serializers.ChoiceField(choices=("N", "OP", "S", "OGT"))
    window_area_m2 = serializers.CharField()
    wall_area_m2 = serializers.CharField(allow_null=True)
    actual_pct = serializers.CharField(allow_null=True)
    allowed_pct = serializers.IntegerField(allow_null=True)
    verdict = serializers.ChoiceField(choices=THERMAL_VERDICTS)
    causes = ThermalCauseSerializer(many=True)


class ProjectThermalSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    thermal_zone = serializers.ChoiceField(
        choices=("A", "B", "C", "D", "E", "F", "G", "H", "I"), allow_null=True
    )
    thermal_use = serializers.ChoiceField(choices=("RESIDENTIAL", "EQUIPMENT"))
    thermal_wall_areas = serializers.DictField(allow_null=True)
    positions = ThermalPositionSerializer(many=True)
    orientations = OrientationComplianceSerializer(many=True)
    verdict = serializers.ChoiceField(choices=THERMAL_VERDICTS)


class ThermalAlternativeSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("GLASS", "SYSTEM"))
    label = serializers.CharField()
    glass_sku = serializers.CharField(required=False, allow_null=True)
    system_id = serializers.UUIDField(required=False, allow_null=True)
    uw_w_m2k = serializers.CharField(allow_null=True)
    price_delta_net = serializers.CharField(allow_null=True)


class ThermalAlternativesResponseSerializer(serializers.Serializer):
    position_id = serializers.UUIDField()
    current = PositionThermalSerializer()
    alternatives = ThermalAlternativeSerializer(many=True)
