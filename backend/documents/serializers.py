"""Strict SHOT-09 documentary input, freeze, artifact, and access contracts."""

from decimal import Decimal

from rest_framework import serializers

from engine_api.serializers import DecimalStringField


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("Unknown input fields")
        return super().to_internal_value(data)


class WorkshopAnnotationSerializer(StrictSerializer):
    bay_id = serializers.CharField(max_length=200)
    leaf_id = serializers.CharField(max_length=200, allow_null=True, required=False, default=None)
    bottom_drain_holes_mm = serializers.ListField(
        child=DecimalStringField(max_digits=14, decimal_places=4), allow_null=True,
        required=False, default=None,
    )
    closing_points_perimeter_mm = serializers.ListField(
        child=DecimalStringField(max_digits=14, decimal_places=4), allow_null=True,
        required=False, default=None,
    )
    continuous_width_mm = DecimalStringField(
        max_digits=14, decimal_places=4, min_value=Decimal("0.0001"),
        allow_null=True, required=False, default=None,
    )
    finish_class = serializers.ChoiceField(
        # WHITE|FOILED is the machining finish domain; whether FOILED is legal
        # on a given design is checked downstream against its declared color.
        choices=["WHITE", "FOILED"], allow_null=True, required=False, default=None
    )
    has_coupler = serializers.BooleanField(allow_null=True, required=False, default=None)


class DocumentaryStructuralInputSerializer(StrictSerializer):
    target_id = serializers.CharField(max_length=200)
    required_ix_cm4 = DecimalStringField(
        max_digits=12, decimal_places=4, min_value=Decimal("0.0001"),
        allow_null=True, required=False, default=None,
    )
    structural_basis = serializers.CharField(
        max_length=1000, allow_null=True, allow_blank=False, required=False, default=None
    )


class PolishingEdgesSerializer(StrictSerializer):
    top = serializers.BooleanField()
    right = serializers.BooleanField()
    bottom = serializers.BooleanField()
    left = serializers.BooleanField()


class GlassPolishingSerializer(StrictSerializer):
    schema_version = serializers.IntegerField(min_value=1, max_value=1, default=1)
    bay_id = serializers.CharField(max_length=200)
    leaf_id = serializers.CharField(max_length=200, allow_null=True, required=False, default=None)
    edges = PolishingEdgesSerializer()


class HandleIntentSerializer(StrictSerializer):
    schema_version = serializers.IntegerField(min_value=1, max_value=1, default=1)
    bay_id = serializers.CharField(max_length=200)
    leaf_id = serializers.CharField(max_length=200, allow_null=True, required=False, default=None)
    handle_domain_slot = serializers.CharField(max_length=100)
    requested_height_mm = DecimalStringField(
        max_digits=14, decimal_places=4, min_value=Decimal("0")
    )
    vertical_reference = serializers.ChoiceField(
        choices=["OUTER_TOP", "OUTER_BOTTOM", "LEAF_TOP", "LEAF_BOTTOM"]
    )


class AccessoryLineSerializer(StrictSerializer):
    obligation_id = serializers.CharField(max_length=200)
    obligation_kind = serializers.ChoiceField(
        choices=["SEALING", "FASTENING", "DRAINAGE", "INSTALLATION_ACCESSORY", "OTHER_DECLARED"]
    )
    technical_sku = serializers.CharField(max_length=200)
    purchasing_sku = serializers.CharField(max_length=200)
    manufacturer_name = serializers.CharField(max_length=300)
    order_type = serializers.ChoiceField(
        choices=[
            "SUPPLIER_PROFILE_PO", "SUPPLIER_GLASS_PO",
            "SUPPLIER_HARDWARE_PO", "SUPPLIER_PANEL_PO",
        ]
    )
    unit = serializers.ChoiceField(choices=["EA"], default="EA")
    quantity_per_position_unit = serializers.IntegerField(min_value=1)
    description = serializers.CharField(max_length=1000)


class AccessoryScheduleSerializer(StrictSerializer):
    schema_version = serializers.IntegerField(min_value=1, max_value=1, default=1)
    coverage = serializers.ChoiceField(choices=["DECLARED", "NONE_REQUIRED"])
    items = AccessoryLineSerializer(many=True)

    def validate(self, attrs):
        if (attrs["coverage"] == "DECLARED") != bool(attrs["items"]):
            raise serializers.ValidationError("Accessory coverage and declared items disagree")
        obligations = [item["obligation_id"] for item in attrs["items"]]
        if len(obligations) != len(set(obligations)):
            raise serializers.ValidationError("Accessory obligations must be unique")
        return attrs


class PositionDocumentaryInputSerializer(StrictSerializer):
    position_id = serializers.UUIDField()
    calculation_hash = serializers.RegexField(r"^sha256:[0-9a-f]{64}$")
    location_tag = serializers.CharField(max_length=100, allow_blank=False, trim_whitespace=True)
    manufacturing_placement_policy_id = serializers.UUIDField()
    handle_requirement_policy_id = serializers.UUIDField()
    reinforcement_cut_policy_id = serializers.UUIDField()
    workshop_annotations = WorkshopAnnotationSerializer(many=True)
    structural_inputs = DocumentaryStructuralInputSerializer(many=True)
    glass_polishing = GlassPolishingSerializer(many=True)
    handle_intents = HandleIntentSerializer(many=True)
    accessory_schedule = AccessoryScheduleSerializer(allow_null=True)
    legacy_handle_migration_confirmed = serializers.BooleanField(default=False)


class DocumentaryInputsSerializer(StrictSerializer):
    payment_terms = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
    quotation_valid_until = serializers.DateField()
    positions = PositionDocumentaryInputSerializer(many=True, allow_empty=False)
    # P08 — ediciones por cotización sobre la plantilla de la organización:
    # claves del documento (plazo_entrega, instalacion, exclusiones,
    # garantia, jurisdiccion); un texto vacío omite la línea.
    doc_terms = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=4000),
        required=False,
    )


class DocumentaryInputsResponseSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    positions_saved = serializers.IntegerField()


class DocumentaryPolicyOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    version = serializers.IntegerField()


class HandleLeafRectSerializer(serializers.Serializer):
    placement_policy_id = serializers.UUIDField()
    leaf_top_from_outer_top_mm = DecimalStringField(
        max_digits=14, decimal_places=4
    )
    leaf_height_mm = DecimalStringField(max_digits=14, decimal_places=4)


class HandleRequirementSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    leaf_label = serializers.CharField()
    opening_type = serializers.CharField()
    handle_domain_slot = serializers.CharField()
    # Null on door rows whose leaf hasn't declared handedness yet — there
    # is no host stile to name until the product says which edge hinges.
    host_member_side = serializers.ChoiceField(
        choices=["LEFT", "RIGHT"], allow_null=True
    )
    requires_handedness = serializers.BooleanField(default=False)
    outer_height_mm = DecimalStringField(max_digits=14, decimal_places=4)
    mounting_min_from_leaf_top_mm = DecimalStringField(
        max_digits=14, decimal_places=4
    )
    mounting_max_from_leaf_top_mm = DecimalStringField(
        max_digits=14, decimal_places=4
    )
    permitted_vertical_references = serializers.ListField(
        child=serializers.ChoiceField(
            choices=["OUTER_TOP", "OUTER_BOTTOM", "LEAF_TOP", "LEAF_BOTTOM"]
        )
    )
    leaf_rects = HandleLeafRectSerializer(many=True)


class HandlePolicyRequirementsSerializer(serializers.Serializer):
    policy_id = serializers.UUIDField()
    requirements = HandleRequirementSerializer(many=True)


class WorkshopBayTargetSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    label = serializers.CharField()
    width_mm = DecimalStringField(max_digits=14, decimal_places=4)


class WorkshopLeafTargetSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    leaf_label = serializers.CharField()


class WorkshopSpanTargetSerializer(serializers.Serializer):
    target_id = serializers.CharField()
    label = serializers.CharField()
    span_mm = DecimalStringField(max_digits=14, decimal_places=4)


class WorkshopGlassTargetSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    label = serializers.CharField()


class WorkshopTargetsSerializer(serializers.Serializer):
    bays = WorkshopBayTargetSerializer(many=True)
    leaves = WorkshopLeafTargetSerializer(many=True)
    spans = WorkshopSpanTargetSerializer(many=True)
    glass = WorkshopGlassTargetSerializer(many=True)


class DocumentaryPreparationPositionSerializer(PositionDocumentaryInputSerializer):
    system_name = serializers.CharField()
    manufacturing_placement_policy_id = serializers.UUIDField(allow_null=True)
    handle_requirement_policy_id = serializers.UUIDField(allow_null=True)
    reinforcement_cut_policy_id = serializers.UUIDField(allow_null=True)
    placement_options = DocumentaryPolicyOptionSerializer(many=True)
    handle_options = DocumentaryPolicyOptionSerializer(many=True)
    reinforcement_options = DocumentaryPolicyOptionSerializer(many=True)
    handle_requirements = HandlePolicyRequirementsSerializer(many=True)
    workshop_targets = WorkshopTargetsSerializer()
    workshop_suggestions = WorkshopAnnotationSerializer(many=True)
    polishing_suggestions = GlassPolishingSerializer(many=True)
    # Pre-emit preview: same inspector the freeze runs, so the UI can state
    # "Sólo cotización" before the estimator clicks Emitir.
    production_ready = serializers.BooleanField()
    documentary_ready = serializers.BooleanField()
    # Regla RED con evaluación FAIL — el freeze la rechaza; el checklist
    # de emisión la declara antes de que el estimador pulse «Emitir».
    inspector_blocked = serializers.BooleanField()


class DocumentaryPreparationResponseSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    revision_code = serializers.RegexField(r"^REV-[A-Z]+$")
    payment_terms = serializers.CharField(allow_blank=True)
    quotation_valid_until = serializers.DateField(allow_null=True)
    # P08 — plantillas de Ajustes y mapa efectivo editable por cotización.
    org_doc_terms = serializers.DictField(child=serializers.CharField())
    default_payment_terms = serializers.CharField(allow_blank=True)
    doc_validity_days = serializers.IntegerField()
    doc_terms = serializers.DictField(child=serializers.CharField())
    emission_missing = serializers.ListField(child=serializers.CharField())
    positions = DocumentaryPreparationPositionSerializer(many=True)


class PositionDocumentaryPreviewSerializer(PositionDocumentaryInputSerializer):
    """En la vista previa la ubicación y las políticas pueden ir vacías — el
    documento imprime '—' y el checklist marca el pendiente; el sello sigue
    exigiéndolas."""

    location_tag = serializers.CharField(
        max_length=100, allow_blank=True, trim_whitespace=True
    )
    manufacturing_placement_policy_id = serializers.UUIDField(allow_null=True)
    handle_requirement_policy_id = serializers.UUIDField(allow_null=True)
    reinforcement_cut_policy_id = serializers.UUIDField(allow_null=True)


class QuotePreviewSerializer(StrictSerializer):
    """Vista previa real del DOC-01: payload del formulario tal cual (aún no
    guardado) + la operación de precios que autoriza la revisión."""

    pricing_operation_id = serializers.UUIDField()
    payment_terms = serializers.CharField(
        max_length=2000, allow_blank=True, trim_whitespace=True, required=False
    )
    quotation_valid_until = serializers.DateField(allow_null=True, required=False)
    doc_terms = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=4000),
        required=False,
    )
    positions = PositionDocumentaryPreviewSerializer(many=True, allow_empty=False)


class QuotePreviewResponseSerializer(serializers.Serializer):
    html = serializers.CharField()
    bom_hash = serializers.RegexField(r"^[0-9a-f]{64}$")
    revision_code = serializers.RegexField(r"^REV-[A-Z]+$")


class FreezeRequestSerializer(StrictSerializer):
    pricing_operation_id = serializers.UUIDField()
    confirmed = serializers.BooleanField()


class FreezeResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    pricing_operation_id = serializers.UUIDField()
    created = serializers.BooleanField()
    revision_code = serializers.RegexField(r"^REV-[A-Z]+$")
    bom_hash = serializers.RegexField(r"^[0-9a-f]{64}$")
    snapshot_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$")
    production_allowed = serializers.BooleanField()
    documentary_complete = serializers.BooleanField()
    emitted_at = serializers.DateTimeField()
    purchase_projection_hash = serializers.RegexField(
        r"^[0-9a-f]{64}$", required=False, allow_null=True
    )


class ArtifactRequestSerializer(StrictSerializer):
    document_type = serializers.ChoiceField(
        choices=["DOC-01", "DOC-02", "DOC-03", "DOC-04", "DOC-05", "DOC-06", "DOC-07", "DOC-08"]
    )
    format = serializers.ChoiceField(choices=["PDF", "XLSX"])
    project_version_id = serializers.UUIDField()
    order_id = serializers.UUIDField(required=False, allow_null=True)


class ArtifactResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    artifact_scope = serializers.ChoiceField(choices=["PROJECT_REVISION", "ORDER"])
    artifact_scope_id = serializers.UUIDField()
    document_type = serializers.CharField()
    format = serializers.CharField()
    bom_hash = serializers.RegexField(r"^[0-9a-f]{64}$")
    file_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$")
    byte_size = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class ArtifactListItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    document_type = serializers.CharField()
    format = serializers.CharField()
    artifact_scope = serializers.ChoiceField(choices=["PROJECT_REVISION", "ORDER"])
    project_version_id = serializers.UUIDField()
    order_id = serializers.UUIDField(allow_null=True)
    order_type = serializers.CharField(allow_null=True)
    revision_code = serializers.CharField()
    byte_size = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class ArtifactListResponseSerializer(serializers.Serializer):
    artifacts = ArtifactListItemSerializer(many=True)


class SignedAccessResponseSerializer(serializers.Serializer):
    artifact_id = serializers.UUIDField()
    signed_url = serializers.URLField()
    expires_in = serializers.IntegerField(min_value=3600, max_value=3600)


class RevisionCompareQuerySerializer(serializers.Serializer):
    base = serializers.RegexField(r"^REV-[A-Z]+$")
    head = serializers.RegexField(r"^REV-[A-Z]+$")


class RevisionCompareSideSerializer(serializers.Serializer):
    revision_code = serializers.CharField()
    emitted_at = serializers.CharField()
    integrity = serializers.ChoiceField(
        choices=("VERIFIED", "MISMATCH"), allow_null=True
    )
    currency = serializers.CharField()
    total_price_net = serializers.CharField()
    total_price_tax = serializers.CharField()
    total_price_gross = serializers.CharField()


class RevisionCompareSummarySerializer(serializers.Serializer):
    added = serializers.IntegerField()
    removed = serializers.IntegerField()
    changed = serializers.IntegerField()
    unchanged = serializers.IntegerField()
    price_gross_delta = serializers.CharField(allow_null=True)


class RevisionComparePositionSerializer(serializers.Serializer):
    id = serializers.CharField()
    position_index = serializers.IntegerField()
    location_tag = serializers.CharField()
    typology = serializers.CharField()
    system_id = serializers.CharField()
    quantity = serializers.IntegerField()
    width_mm = serializers.CharField()
    height_mm = serializers.CharField()
    color_interior = serializers.CharField()
    color_exterior = serializers.CharField()
    price_net = serializers.CharField()
    discount_pct = serializers.CharField()
    parametric_tree = serializers.JSONField(allow_null=True)


class RevisionCompareFieldSerializer(serializers.Serializer):
    field = serializers.CharField()
    before = serializers.CharField()
    after = serializers.CharField()


class RevisionCompareEntrySerializer(serializers.Serializer):
    position_index = serializers.IntegerField()
    change = serializers.ChoiceField(choices=("ADDED", "REMOVED", "CHANGED"))
    location_tag = serializers.CharField()
    before = RevisionComparePositionSerializer(allow_null=True)
    after = RevisionComparePositionSerializer(allow_null=True)
    changes = RevisionCompareFieldSerializer(many=True)


class RevisionCompareResponseSerializer(serializers.Serializer):
    project_id = serializers.CharField()
    project_code = serializers.CharField()
    base = RevisionCompareSideSerializer()
    head = RevisionCompareSideSerializer()
    summary = RevisionCompareSummarySerializer()
    positions = RevisionCompareEntrySerializer(many=True)
