"""Explicit monetary strings and typed S09 input/output schemas."""

from decimal import Decimal
import json

from rest_framework import serializers

from dekopen_engine.commercial import PricingMode
from engine_api.serializers import EngineCalculateRequestSerializer
from projects.typology import COMMERCIAL_TYPOLOGIES

MODES = [mode.value for mode in PricingMode]


def money(**kwargs):
    return serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal('0'), **kwargs)


def fraction(**kwargs):
    return serializers.DecimalField(max_digits=6,decimal_places=4,min_value=Decimal('0'),max_value=Decimal('1'),**kwargs)


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data,dict) or set(data)-set(self.fields):
            raise serializers.ValidationError('Unknown input fields')
        return super().to_internal_value(data)


class CostListSerializer(StrictSerializer):
    supplier_name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False,allow_blank=True)
    currency = serializers.ChoiceField(choices=['CLP','USD'])
    valid_from = serializers.DateField()
    valid_to = serializers.DateField(required=False,allow_null=True)
    is_active = serializers.BooleanField(default=True)


class CostItemSerializer(StrictSerializer):
    cost_list_id = serializers.UUIDField()
    sku = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False,allow_blank=True,max_length=1000)
    item_type = serializers.CharField(max_length=50)
    unit = serializers.ChoiceField(choices=['BAR','M','M2','KIT','UNIT','EA'])
    unit_cost = serializers.DecimalField(max_digits=14,decimal_places=4,min_value=Decimal('0'))


class RulesSerializer(StrictSerializer):
    pricing_mode = serializers.ChoiceField(choices=MODES)
    default_margin_pct = fraction()
    tax_rate_pct = fraction()
    waste_factor_pct = serializers.DecimalField(max_digits=6,decimal_places=4,
        min_value=Decimal('0.08'),max_value=Decimal('0.08'))
    labor_rate_per_m2 = serializers.DecimalField(max_digits=14,decimal_places=2,min_value=Decimal('0'))
    installation_rate_per_m2 = serializers.DecimalField(max_digits=14,decimal_places=2,min_value=Decimal('0'))


class ConfigurationSerializer(StrictSerializer):
    context_code = serializers.CharField(max_length=100)
    typology = serializers.ChoiceField(choices=COMMERCIAL_TYPOLOGIES)
    pricing_mode = serializers.ChoiceField(choices=MODES)
    currency = serializers.ChoiceField(choices=['CLP','USD'])
    rate_per_m2 = money(required=False,allow_null=True)
    base_glass_sku = serializers.CharField(max_length=100,required=False,allow_null=True)
    catalog_price = money(required=False,allow_null=True)
    is_active = serializers.BooleanField(default=True)


class MatrixCellSerializer(StrictSerializer):
    configuration_id = serializers.UUIDField()
    width_mm = serializers.IntegerField(min_value=600,max_value=2400)
    height_mm = serializers.IntegerField(min_value=600,max_value=2400)
    price = money()


class FxSerializer(StrictSerializer):
    base_currency = serializers.ChoiceField(choices=['USD'])
    quote_currency = serializers.ChoiceField(choices=['CLP'])
    observed_rate = serializers.DecimalField(max_digits=20,decimal_places=8,min_value=Decimal('0.00000001'))
    observed_date = serializers.DateField()
    effective_date = serializers.DateField()
    source = serializers.CharField(max_length=300)


class AdminWriteSerializer(StrictSerializer):
    id = serializers.UUIDField(required=False)
    reason = serializers.CharField(max_length=1000)
    values = serializers.DictField()


class AdminResponseSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField())


class ExtraChargeSerializer(StrictSerializer):
    """A project-level priced charge — instalación, traslado, otro — that
    adds to the net after position discounts and is taxed with the sale."""
    label = serializers.CharField(max_length=120, trim_whitespace=True)
    kind = serializers.ChoiceField(
        choices=['INSTALLATION', 'FREIGHT', 'OTHER'], default='OTHER')
    amount = money()

    def validate_label(self, value):
        if not value:
            raise serializers.ValidationError('Cargo requiere nombre')
        return value


class PriceRequestSerializer(StrictSerializer):
    project_id = serializers.UUIDField()
    pricing_mode = serializers.ChoiceField(choices=MODES)
    context_code = serializers.CharField(default='DEFAULT',max_length=100)
    currency = serializers.ChoiceField(choices=['CLP','USD'])
    effective_date = serializers.DateField()
    fx_snapshot_id = serializers.UUIDField(required=False,allow_null=True)
    discount_pct = fraction(default=Decimal('0'))
    target_margin = fraction(default=Decimal('0.35'))
    segment = serializers.ChoiceField(choices=['RETAIL','ARCHITECT','CONSTRUCTION'],default='RETAIL')
    extras = serializers.ListField(
        child=ExtraChargeSerializer(), required=False, default=list, max_length=10)
    confirmed = serializers.BooleanField(default=False)
    reason = serializers.CharField(max_length=1000)


class ApplySerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)
    confirmed = serializers.BooleanField(default=False)
    reject = serializers.BooleanField(default=False)


class WithdrawSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)


class LineResponseSerializer(serializers.Serializer):
    position_index = serializers.IntegerField()
    line_net = serializers.CharField()
    quantity = serializers.IntegerField(allow_null=True, required=False)
    unit_price = serializers.CharField(allow_null=True, required=False)
    discount_pct = serializers.CharField(allow_null=True, required=False)


class CostLineResponseSerializer(serializers.Serializer):
    position_index = serializers.IntegerField()
    line_cost = serializers.CharField()


class CompositionLineSerializer(serializers.Serializer):
    kind = serializers.CharField()
    sku = serializers.CharField()
    quantity = serializers.CharField()
    unit = serializers.CharField()
    cost = serializers.CharField()


class PositionBreakdownSerializer(serializers.Serializer):
    position_id = serializers.CharField()
    position_index = serializers.IntegerField(allow_null=True)
    unit_cost = serializers.CharField()
    area_m2 = serializers.CharField()
    materials_cost = serializers.CharField()
    waste_pct = serializers.CharField()
    labor_rate_per_m2 = serializers.CharField()
    installation_rate_per_m2 = serializers.CharField()
    # D04: declared sell delta from hardware selections on this position —
    # added on the unit price, never inside materials_cost.
    hardware_option_delta = serializers.CharField(required=False)
    composition = CompositionLineSerializer(many=True)


class PriceResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    project_code = serializers.CharField(allow_blank=True)
    project_name = serializers.CharField(allow_blank=True)
    client_name = serializers.CharField(allow_blank=True)
    revision_code = serializers.RegexField(r'^REV-[A-Z]+$')
    discount_pct = serializers.CharField()
    pricing_mode = serializers.CharField(allow_blank=True)
    segment = serializers.CharField(allow_blank=True)
    state = serializers.ChoiceField(choices=['PREVIEW','PENDING','APPLIED','REJECTED','WITHDRAWN'])
    currency = serializers.ChoiceField(choices=['CLP','USD'])
    lines = LineResponseSerializer(many=True)
    cost_lines = CostLineResponseSerializer(many=True)
    extras = serializers.ListField(child=serializers.DictField())
    extras_net = serializers.CharField()
    positions_breakdown = PositionBreakdownSerializer(many=True)
    authorities = serializers.ListField(child=serializers.JSONField())
    rules = serializers.DictField()
    total_cost = serializers.CharField()
    project_net = serializers.CharField()
    project_tax = serializers.CharField()
    project_gross = serializers.CharField()
    reason = serializers.CharField()
    requested_by = serializers.CharField()
    requested_by_email = serializers.CharField(allow_null=True)
    approved_by = serializers.CharField(allow_null=True)
    approved_at = serializers.CharField(allow_null=True)
    created_at = serializers.CharField()


class DraftPositionSerializer(EngineCalculateRequestSerializer):
    # Validated against the system's declared finishes downstream
    # (adapter has params; serializers don't).
    color = serializers.CharField(max_length=50)
    position_index = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)
    typology = serializers.CharField(max_length=50)


class DraftProjectSerializer(StrictSerializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=255)
    client_name = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=1000)
    positions = DraftPositionSerializer(many=True,allow_empty=False)


class DraftResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()


class ImportRequestSerializer(StrictSerializer):
    file = serializers.FileField()
    mapping = serializers.CharField(help_text='JSON object mapping sku, description, unit and unit_cost to column names.')
    decimal_separator = serializers.ChoiceField(choices=['.',','],default='.')
    cost_list_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=1000)
    apply = serializers.BooleanField(default=False)

    def validate_mapping(self, value):
        try:
            mapping = json.loads(value)
        except (TypeError, ValueError) as error:
            raise serializers.ValidationError('Invalid mapping') from error
        if not isinstance(mapping, dict):
            raise serializers.ValidationError('Invalid mapping')
        return mapping


class DesignBatchPreviewItemSerializer(StrictSerializer):
    position_id = serializers.UUIDField()
    design = serializers.DictField()

    def validate_design(self, value):
        # Same contract as a position save — imported lazily because
        # projects.serializers already pulls StrictSerializer from this
        # module (top-level import would cycle).
        from projects.serializers import PositionDesignSerializer
        serializer = PositionDesignSerializer(data=value)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class DesignBatchPreviewRequestSerializer(StrictSerializer):
    project_id = serializers.UUIDField()
    effective_date = serializers.DateField()
    items = DesignBatchPreviewItemSerializer(many=True,allow_empty=False,max_length=15)


class DesignBatchPreviewItemResponseSerializer(serializers.Serializer):
    position_id = serializers.UUIDField()
    index = serializers.IntegerField(required=False)
    ok = serializers.BooleanField()
    error_code = serializers.CharField(required=False,allow_null=True)
    error = serializers.CharField(required=False,allow_null=True)
    quantity = serializers.IntegerField(required=False)
    unit_cost_before = serializers.CharField(required=False,allow_null=True)
    unit_cost_after = serializers.CharField(required=False,allow_null=True)
    line_cost_before = serializers.CharField(required=False,allow_null=True)
    line_cost_after = serializers.CharField(required=False,allow_null=True)


class DesignBatchPreviewResponseSerializer(serializers.Serializer):
    currency = serializers.CharField()
    items = DesignBatchPreviewItemResponseSerializer(many=True)


RESOURCE_SERIALIZERS = {
    'cost-lists':CostListSerializer,'cost-items':CostItemSerializer,'rules':RulesSerializer,
    'configurations':ConfigurationSerializer,'matrix-cells':MatrixCellSerializer,'fx':FxSerializer,
}
