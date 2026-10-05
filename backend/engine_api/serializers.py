"""OpenAPI-visible request and response shapes for engine calculation."""

from rest_framework import serializers

from dekopen_engine.models import HARDWARE_COMPONENT_CATEGORIES


class DecimalStringField(serializers.DecimalField):
    def to_internal_value(self, data: object) -> object:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class EngineCalculateRequestSerializer(serializers.Serializer):
    system_id = serializers.UUIDField()
    nominal_width_mm = DecimalStringField(max_digits=10, decimal_places=2)
    nominal_height_mm = DecimalStringField(max_digits=10, decimal_places=2)
    color = serializers.CharField(max_length=50)
    parametric_tree = serializers.JSONField()


class ProfileCutSerializer(serializers.Serializer):
    sku = serializers.CharField()
    role = serializers.CharField()
    material = serializers.ChoiceField(choices=["PVC", "ALUMINIUM"])
    length_mm = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    angle_left = serializers.DecimalField(max_digits=5, decimal_places=1, coerce_to_string=True)
    angle_right = serializers.DecimalField(max_digits=5, decimal_places=1, coerce_to_string=True)
    qty = serializers.IntegerField()
    bay_id = serializers.CharField(allow_null=True)
    leaf_id = serializers.CharField(allow_null=True)
    sagitta_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )


class ReinforcementSerializer(serializers.Serializer):
    parent_profile_sku = serializers.CharField()
    reinforcement_sku = serializers.CharField(allow_null=True)
    role = serializers.CharField()
    length_mm = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    qty = serializers.IntegerField()
    bay_id = serializers.CharField(allow_null=True)
    leaf_id = serializers.CharField(allow_null=True)
    sagitta_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )


class PlanPointSerializer(serializers.Serializer):
    x_mm = serializers.CharField()
    y_mm = serializers.CharField()


class GlassSurchargeSelectionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["EDGE_POLISH", "DRILL", "PALILLAJE"]
    )
    edges = serializers.ListField(
        child=serializers.ChoiceField(
            choices=["top", "right", "bottom", "left"]
        ),
        allow_null=True,
        required=False,
    )
    count = serializers.IntegerField(allow_null=True, required=False)
    columns = serializers.IntegerField(allow_null=True, required=False)
    rows = serializers.IntegerField(allow_null=True, required=False)


class GlassSafetyFindingSerializer(serializers.Serializer):
    rule_code = serializers.CharField()
    severity = serializers.ChoiceField(choices=["WARNING", "MANDATORY"])
    required_safety = serializers.CharField(allow_null=True)
    message = serializers.CharField()
    source_ref = serializers.CharField(allow_null=True)
    review_pending = serializers.BooleanField()


class GlassPieceSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    width_mm = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    height_mm = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    shape = PlanPointSerializer(many=True, allow_null=True)
    area_m2 = serializers.DecimalField(max_digits=12, decimal_places=4, coerce_to_string=True)
    weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    thickness_net_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    glass_spec = serializers.CharField(allow_null=True)
    article_sku = serializers.CharField(allow_null=True)
    exposed_edges = serializers.ListField(
        child=serializers.CharField(), allow_null=True
    )
    # D02 structured layer stack, surcharges and rule findings. The
    # composition object is the engine-produced dict verbatim.
    composition = serializers.DictField(allow_null=True, required=False)
    thickness_total_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
    )
    requires_exact_cut = serializers.BooleanField(required=False)
    surcharge_selections = GlassSurchargeSelectionSerializer(
        many=True, required=False
    )
    safety_findings = GlassSafetyFindingSerializer(many=True, required=False)


class PanelPieceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    width_mm = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    height_mm = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    area_m2 = serializers.DecimalField(max_digits=12, decimal_places=4, coerce_to_string=True)
    weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )


class ComponentQtyRuleSerializer(serializers.Serializer):
    """Declared quantity rule — D04: puntos de cierre = f(span)."""

    kind = serializers.ChoiceField(choices=["PER_WIDTH", "PER_HEIGHT"])
    per_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    min_qty = serializers.IntegerField()
    max_qty = serializers.IntegerField(allow_null=True)


class ComponentCutRuleSerializer(serializers.Serializer):
    """Declared cut rule — D04: transmisión = leaf span − X."""

    axis = serializers.ChoiceField(choices=["WIDTH", "HEIGHT"])
    minus_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )


class MachiningDeclarationSerializer(serializers.Serializer):
    """Declared machining operation — status is the engine's verdict:
    EMITTED only when the catalog carried coordinates."""

    kind = serializers.ChoiceField(
        choices=["LOCK_PREP", "HINGE_PREP", "ESPAG_HOUSING", "DRAINAGE", "OTHER"]
    )
    side = serializers.CharField(allow_null=True, required=False)
    u_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
    )
    y_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
    )
    note = serializers.CharField(allow_null=True, required=False)
    status = serializers.ChoiceField(
        choices=["EMITTED", "DECLARED_NOT_EMITTED"], allow_null=True, required=False
    )


class HardwareComponentSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    qty = serializers.CharField(help_text="Exact Decimal quantity serialized as a string")
    unit = serializers.CharField()
    category = serializers.ChoiceField(
        choices=HARDWARE_COMPONENT_CATEGORIES,
        required=False,
        default="OTHER",
    )
    qty_rule = ComponentQtyRuleSerializer(
        allow_null=True, required=False, help_text="Declared rule behind qty"
    )
    cut_rule = ComponentCutRuleSerializer(allow_null=True, required=False)
    weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=3, coerce_to_string=True,
        allow_null=True, required=False,
    )
    cost_clp = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
    )
    machining = MachiningDeclarationSerializer(many=True, required=False)
    length_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
        help_text="Resolved cut length on the emitted BOM line",
    )
    option_sku = serializers.CharField(
        allow_null=True, required=False,
        help_text="Option that brought this component into the leaf BOM",
    )


class HardwareSelectionPriceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    source = serializers.ChoiceField(
        choices=["HANDLE_MODEL", "HANDLE_COLOR", "OPTION"]
    )
    price_delta_clp = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )


class HardwareItemSerializer(serializers.Serializer):
    kit_sku = serializers.CharField()
    name = serializers.CharField()
    qty = serializers.IntegerField()
    unit = serializers.ChoiceField(choices=["kit"])
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    contents = HardwareComponentSerializer(many=True)
    class_label = serializers.CharField(allow_null=True, required=False)
    handle_model_sku = serializers.CharField(allow_null=True, required=False)
    handle_model_name = serializers.CharField(allow_null=True, required=False)
    handle_color_sku = serializers.CharField(allow_null=True, required=False)
    handle_color_name = serializers.CharField(allow_null=True, required=False)
    option_skus = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    option_names = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    handle_height_mm = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
    )
    cost_clp = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
    )
    weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=3, coerce_to_string=True,
        allow_null=True, required=False,
    )
    price_delta_clp = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True,
        allow_null=True, required=False,
    )
    price_deltas = HardwareSelectionPriceSerializer(many=True, required=False)
    machining = MachiningDeclarationSerializer(many=True, required=False)


class FittingPieceSerializer(serializers.Serializer):
    """Counted frameless fitting — patch/clamp/hinge/lock/connector/seal/support."""

    kind = serializers.CharField()
    sku = serializers.CharField()
    qty = serializers.IntegerField()
    bay_id = serializers.CharField(allow_null=True)
    leaf_id = serializers.CharField(allow_null=True)


class LeafWeightSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    leaf_id = serializers.CharField(allow_null=True)
    pvc_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    steel_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    infill_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    hardware_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    total_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, allow_null=True
    )
    weight_unknown_reasons = serializers.ListField(
        child=serializers.CharField(), allow_empty=True
    )


class EngineResultPayloadSerializer(serializers.Serializer):
    profile_cuts = ProfileCutSerializer(many=True)
    reinforcements = ReinforcementSerializer(many=True)
    glasses = GlassPieceSerializer(many=True)
    panels = PanelPieceSerializer(many=True)
    fittings = FittingPieceSerializer(many=True)
    hardware_items = HardwareItemSerializer(many=True)
    leaf_weights = LeafWeightSerializer(many=True)


class EngineCalculateResponseSerializer(EngineResultPayloadSerializer):
    calculation_hash = serializers.RegexField(regex=r"^sha256:[0-9a-f]{64}$")


class EngineAssemblyCalculateSerializer(serializers.Serializer):
    system_id = serializers.UUIDField()
    nominal_width_mm = DecimalStringField(max_digits=10, decimal_places=2)
    nominal_height_mm = DecimalStringField(max_digits=10, decimal_places=2)
    color = serializers.CharField(max_length=50)
    product = serializers.JSONField()


class PlanModuleSerializer(serializers.Serializer):
    module_id = serializers.CharField()
    corners = PlanPointSerializer(many=True)


class PlanCouplingSerializer(serializers.Serializer):
    coupling_id = serializers.CharField()
    polygon = PlanPointSerializer(many=True)


class PlanGeometrySerializer(serializers.Serializer):
    front_chain = PlanPointSerializer(many=True)
    modules = PlanModuleSerializer(many=True)
    couplings = PlanCouplingSerializer(many=True)
    min_x_mm = serializers.CharField()
    min_y_mm = serializers.CharField()
    width_mm = serializers.CharField()
    height_mm = serializers.CharField()


class ProductIssueSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=["error", "warning"])
    target = serializers.CharField()
    params = serializers.DictField(child=serializers.CharField())


class SlidingPanelFactsSerializer(serializers.Serializer):
    slot = serializers.CharField()
    kind = serializers.ChoiceField(choices=["MOVING", "FIXED"])
    track = serializers.IntegerField(allow_null=True)
    leaf_id = serializers.CharField(allow_null=True)


class SlidingLayoutFactsSerializer(serializers.Serializer):
    bay_id = serializers.CharField()
    tracks = serializers.IntegerField()
    panels = SlidingPanelFactsSerializer(many=True)


class ModuleEvaluationSerializer(serializers.Serializer):
    module_id = serializers.CharField()
    issues = ProductIssueSerializer(many=True)
    result = EngineResultPayloadSerializer(allow_null=True)
    sliding = SlidingLayoutFactsSerializer(many=True)


class EngineAssemblyCalculateResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["VALID", "MANUFACTURING_INCOMPLETE", "INVALID"]
    )
    issues = ProductIssueSerializer(many=True)
    plan = PlanGeometrySerializer(allow_null=True)
    modules = ModuleEvaluationSerializer(many=True)
    bom = EngineResultPayloadSerializer(allow_null=True)
    calculation_hash = serializers.RegexField(regex=r"^sha256:[0-9a-f]{64}$")


class TypologyLimitSerializer(serializers.Serializer):
    opening_type = serializers.CharField()
    min_leaf_width_mm = serializers.CharField(allow_null=True, required=False)
    max_leaf_width_mm = serializers.CharField(allow_null=True, required=False)
    min_leaf_height_mm = serializers.CharField(allow_null=True, required=False)
    max_leaf_height_mm = serializers.CharField(allow_null=True, required=False)
    max_leaf_weight_kg = serializers.CharField(allow_null=True, required=False)
    max_aspect_ratio = serializers.CharField(allow_null=True, required=False)
    source = serializers.CharField()


class ProfileSystemSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_demo = serializers.BooleanField()
    system_family = serializers.CharField()
    allowed_openings = serializers.ListField(child=serializers.CharField())
    typology_limits = TypologyLimitSerializer(many=True, required=False)
    quote_ready = serializers.BooleanField()
    readiness_reasons = serializers.ListField(child=serializers.CharField())


class EngineSystemsResponseSerializer(serializers.Serializer):
    systems = ProfileSystemSummarySerializer(many=True)


class AxisOffsetsSerializer(serializers.Serializer):
    half = serializers.CharField()
    one_third = serializers.CharField()
    two_thirds = serializers.CharField()


class NodeLayoutSerializer(serializers.Serializer):
    node_id = serializers.CharField()
    width_mm = serializers.CharField()
    height_mm = serializers.CharField()
    vertical = AxisOffsetsSerializer()
    horizontal = AxisOffsetsSerializer()
    child_weights = serializers.ListField(child=serializers.CharField())


class EngineLayoutResponseSerializer(serializers.Serializer):
    calculation_hash = serializers.CharField()
    nodes = NodeLayoutSerializer(many=True)
