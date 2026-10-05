"""Read-only technical choices for the manual estimator, without cost information."""

from decimal import Decimal

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.views import APIView

from catalogs.serializers import ProfileSectionSerializer
from dekopen_engine.glass_composition import (
    composition_to_dict,
    format_glass_notation,
)
from engine_api.repository import SystemParamsRepository
from pricing.repository import rows
from pricing.views import ERRORS, scope
from projects.views import READ_ROLES, SCHEMA, response


class ProfileChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    role = serializers.CharField()
    name = serializers.CharField()
    material = serializers.CharField()
    face_width_mm = serializers.CharField()
    section = ProfileSectionSerializer(required=False, allow_null=True)


class CouplerChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    material = serializers.CharField()
    face_width_mm = serializers.CharField()
    section = ProfileSectionSerializer(required=False, allow_null=True)


class GlazingBeadChoiceSerializer(serializers.Serializer):
    glass_thickness_mm = serializers.CharField()
    bead_width_mm = serializers.CharField()
    sku = serializers.CharField()
    section = ProfileSectionSerializer(required=False, allow_null=True)


def _section_json(section):
    return None if section is None else section.model_dump()


def _component_json(component) -> dict:
    """Declared catalog component for the design surface — including the
    qty/cut rules when the catalog carries them (D04)."""
    return {
        "sku": component.sku,
        "name": component.name,
        "qty": None if component.qty is None else str(component.qty),
        "unit": component.unit,
        "category": component.category,
        "qty_rule": (
            None
            if component.qty_rule is None
            else component.qty_rule.model_dump(mode="json")
        ),
        "cut_rule": (
            None
            if component.cut_rule is None
            else component.cut_rule.model_dump(mode="json")
        ),
        "weight_kg": (
            None if component.weight_kg is None else str(component.weight_kg)
        ),
        "cost_clp": (
            None if component.cost_clp is None else str(component.cost_clp)
        ),
        "machining": [
            declaration.model_dump(mode="json")
            for declaration in component.machining
        ],
    }


class KitComponentSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    qty = serializers.CharField(allow_null=True)
    unit = serializers.CharField()
    category = serializers.CharField()
    # Declared rules behind the quantity/cut — the editor mirrors the
    # engine's expansion, it never invents counts.
    qty_rule = serializers.DictField(allow_null=True, required=False)
    cut_rule = serializers.DictField(allow_null=True, required=False)
    weight_kg = serializers.CharField(allow_null=True, required=False)
    cost_clp = serializers.CharField(allow_null=True, required=False)
    machining = serializers.ListField(
        child=serializers.DictField(), required=False
    )


class KitChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    opening_type = serializers.CharField()
    # The leaf envelope the kit is rated for — Studio ranks/selects against
    # these bounds instead of treating every kit as interchangeable.
    min_leaf_width_mm = serializers.CharField()
    max_leaf_width_mm = serializers.CharField()
    min_leaf_height_mm = serializers.CharField()
    max_leaf_height_mm = serializers.CharField()
    max_leaf_weight_kg = serializers.CharField()
    # The kit's own mass — engine adds it to the leaf for the weight axis.
    weight_kg = serializers.CharField(allow_null=True)
    # The declared kit bill — HANDLE/HINGE/LOCK/ROLLER/… lines with real
    # quantities. The design surface uses it to bind visual hardware to the
    # selected kit instead of inventing positions and counts (phase-03).
    contents = KitComponentSerializer(many=True)
    # D04: the class the kit plays inside its family, and the declared
    # restrictions beyond the envelope.
    class_label = serializers.CharField(allow_null=True)
    max_aspect_ratio = serializers.CharField(allow_null=True)
    min_stay_height_mm = serializers.CharField(allow_null=True)


class HandleSlotSerializer(serializers.Serializer):
    opening_type = serializers.CharField()
    leaf_slot = serializers.CharField(allow_null=True)
    leaf_handedness = serializers.CharField(allow_null=True)
    handle_domain_slot = serializers.CharField()
    host_member_side = serializers.CharField()
    horizontal_reference = serializers.CharField()
    horizontal_offset_mm = serializers.CharField()
    permitted_vertical_references = serializers.ListField(child=serializers.CharField())
    mounting_min_from_leaf_top_mm = serializers.CharField()
    mounting_max_from_leaf_top_mm = serializers.CharField()


class HandlePolicySerializer(serializers.Serializer):
    policy_id = serializers.CharField()
    version = serializers.IntegerField()
    slots = HandleSlotSerializer(many=True)


class HandleModelChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    price_delta_clp = serializers.CharField(allow_null=True)


class HandleColorChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    price_delta_clp = serializers.CharField(allow_null=True)


class HardwareFamilySerializer(serializers.Serializer):
    """D04: the family's sellable handle catalogue + declared height rule."""

    opening_type = serializers.CharField()
    handle_models = HandleModelChoiceSerializer(many=True)
    handle_colors = HandleColorChoiceSerializer(many=True)
    handle_height_rule = serializers.CharField(allow_null=True)
    handle_height_min_mm = serializers.CharField(allow_null=True)
    handle_height_max_mm = serializers.CharField(allow_null=True)
    handle_height_default_mm = serializers.CharField(allow_null=True)


class HardwareOptionSerializer(serializers.Serializer):
    """D04: a sellable option — the catalog declares its price delta and
    the components it adds to the leaf BOM."""

    sku = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    opening_type = serializers.CharField()
    price_delta_clp = serializers.CharField(allow_null=True)
    contents = KitComponentSerializer(many=True)


class GlassSpecChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    spec = serializers.CharField(allow_null=True)


class GlassSurchargeChoiceSerializer(serializers.Serializer):
    kind = serializers.CharField()
    unit = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField(allow_null=True)
    label = serializers.CharField(allow_null=True)


class GlassProductChoiceSerializer(serializers.Serializer):
    """D02 structured glass product for the selector cards/composer."""

    sku = serializers.CharField()
    name = serializers.CharField()
    notation = serializers.CharField(allow_null=True)
    composition = serializers.DictField(allow_null=True)
    total_thickness_mm = serializers.CharField(allow_null=True)
    safety_class = serializers.CharField(allow_null=True)
    ug_w_m2k = serializers.CharField(allow_null=True)
    g_value = serializers.CharField(allow_null=True)
    light_transmission_pct = serializers.CharField(allow_null=True)
    weight_kg_m2 = serializers.CharField(allow_null=True)
    min_billable_area_m2 = serializers.CharField(allow_null=True)
    # Declared 1..5 relative-price band — comparability signal only; real
    # money stays in the cost lists.
    price_tier = serializers.IntegerField(allow_null=True)
    surcharges = GlassSurchargeChoiceSerializer(many=True)
    review_pending = serializers.BooleanField()


class PanelChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    thickness_mm = serializers.CharField()


class DesignOptionsSerializer(serializers.Serializer):
    profiles = ProfileChoiceSerializer(many=True)
    glazing_thicknesses = serializers.ListField(child=serializers.CharField())
    hardware_kits = KitChoiceSerializer(many=True)
    hardware_families = HardwareFamilySerializer(many=True)
    hardware_options = HardwareOptionSerializer(many=True)
    # Declared handle-mounting authority for the system — null when no policy
    # is on file. The design surface must not silently invent positions.
    handle_policy = HandlePolicySerializer(allow_null=True)
    glass_skus = serializers.ListField(child=serializers.CharField())
    glass_products = GlassProductChoiceSerializer(many=True)
    glass_specs = GlassSpecChoiceSerializer(many=True)
    colors = serializers.ListField(child=serializers.CharField())
    coupler_skus = serializers.ListField(child=serializers.CharField())
    coupler_profiles = CouplerChoiceSerializer(many=True)
    glazing_beads = GlazingBeadChoiceSerializer(many=True)
    panel_skus = serializers.ListField(child=serializers.CharField())
    panel_choices = PanelChoiceSerializer(many=True)
    rebate_depth_mm = serializers.CharField()
    sash_overlap_mm = serializers.CharField()
    depth_mm = serializers.CharField()


class DesignOptionsView(APIView):
    @extend_schema(
        operation_id="project_design_options",
        responses={200: DesignOptionsSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, system_id):
        with scope(request, READ_ROLES) as (_, _, org):
            repository = SystemParamsRepository()
            params = repository.load_visible(system_id, org)
            names = repository.load_article_names(system_id, org)
            couplers = repository.load_coupler_articles(system_id, org)
            handle_policy = repository.load_handle_policy(system_id, org)
            # Latest version wins; an org-scoped mapping outranks the global
            # recipe for the same technical SKU — same resolution the confirm
            # endpoint applies when it binds the glass authority.
            glass_rows = rows(
                "SELECT DISTINCT ON (technical_sku) technical_sku, glass_spec "
                "FROM public.glass_purchase_mappings "
                "WHERE system_id=%s AND (org_id=%s OR org_id IS NULL) "
                "ORDER BY technical_sku, org_id NULLS LAST, version DESC",
                [system_id, org],
            )
            return response(
                {
                    "profiles": [
                        {
                            "sku": item.sku,
                            "role": item.role.value,
                            "name": names.get(item.sku, item.sku),
                            "material": item.material.value,
                            "face_width_mm": str(item.face_width_mm),
                            "section": _section_json(item.section),
                        }
                        for item in params.effective_profile_articles.values()
                    ],
                    "glazing_thicknesses": [
                        str(value) for value in sorted(params.glazing_bead_rules)
                    ],
                    "hardware_kits": [
                        {
                            "sku": item.sku,
                            "name": item.name,
                            "opening_type": item.opening_type,
                            "min_leaf_width_mm": str(item.min_leaf_width_mm),
                            "max_leaf_width_mm": str(item.max_leaf_width_mm),
                            "min_leaf_height_mm": str(item.min_leaf_height_mm),
                            "max_leaf_height_mm": str(item.max_leaf_height_mm),
                            "max_leaf_weight_kg": str(item.max_leaf_weight_kg),
                            "weight_kg": None if item.weight_kg is None else str(item.weight_kg),
                            "contents": [_component_json(c) for c in item.contents],
                            "class_label": item.class_label,
                            "max_aspect_ratio": (
                                None
                                if item.max_aspect_ratio is None
                                else str(item.max_aspect_ratio)
                            ),
                            "min_stay_height_mm": (
                                None
                                if item.min_stay_height_mm is None
                                else str(item.min_stay_height_mm)
                            ),
                        }
                        for item in params.available_hardware_kits
                    ],
                    "hardware_families": [
                        {
                            "opening_type": family.opening_type,
                            "handle_models": [
                                {
                                    "sku": model.sku,
                                    "name": model.name,
                                    "kind": model.kind,
                                    "price_delta_clp": (
                                        None
                                        if model.price_delta_clp is None
                                        else str(model.price_delta_clp)
                                    ),
                                }
                                for model in family.handle_models
                            ],
                            "handle_colors": [
                                {
                                    "sku": color.sku,
                                    "name": color.name,
                                    "price_delta_clp": (
                                        None
                                        if color.price_delta_clp is None
                                        else str(color.price_delta_clp)
                                    ),
                                }
                                for color in family.handle_colors
                            ],
                            "handle_height_rule": family.handle_height_rule,
                            "handle_height_min_mm": (
                                None
                                if family.handle_height_min_mm is None
                                else str(family.handle_height_min_mm)
                            ),
                            "handle_height_max_mm": (
                                None
                                if family.handle_height_max_mm is None
                                else str(family.handle_height_max_mm)
                            ),
                            "handle_height_default_mm": (
                                None
                                if family.handle_height_default_mm is None
                                else str(family.handle_height_default_mm)
                            ),
                        }
                        for family in sorted(
                            params.hardware_families.values(),
                            key=lambda family: family.opening_type,
                        )
                    ],
                    "hardware_options": [
                        {
                            "sku": option.sku,
                            "name": option.name,
                            "kind": option.kind.value,
                            "opening_type": option.opening_type,
                            "price_delta_clp": (
                                None
                                if option.price_delta_clp is None
                                else str(option.price_delta_clp)
                            ),
                            "contents": [
                                _component_json(c) for c in option.components
                            ],
                        }
                        for option in sorted(
                            params.hardware_options.values(),
                            key=lambda option: option.sku,
                        )
                    ],
                    "handle_policy": (
                        None
                        if handle_policy is None
                        else {
                            "policy_id": handle_policy.policy_id,
                            "version": handle_policy.version,
                            "slots": [
                                {
                                    "opening_type": slot.opening_type.value,
                                    "leaf_slot": slot.leaf_slot,
                                    "leaf_handedness": slot.leaf_handedness,
                                    "handle_domain_slot": slot.handle_domain_slot,
                                    "host_member_side": slot.host_member_side.value,
                                    "horizontal_reference": slot.horizontal_reference,
                                    "horizontal_offset_mm": str(slot.horizontal_offset_mm),
                                    "permitted_vertical_references": [
                                        reference.value
                                        for reference in slot.permitted_vertical_references
                                    ],
                                    "mounting_min_from_leaf_top_mm": str(
                                        slot.mounting_min_from_leaf_top_mm
                                    ),
                                    "mounting_max_from_leaf_top_mm": str(
                                        slot.mounting_max_from_leaf_top_mm
                                    ),
                                }
                                for slot in handle_policy.slots
                            ],
                        }
                    ),
                    "glass_skus": [item["technical_sku"] for item in glass_rows],
                    # D02 structured products (same scope resolution the
                    # engine repository applies): the selector's card
                    # content — name, notation, thickness/weight, safety
                    # class, declared surcharges and pending-review flag.
                    "glass_products": [
                        {
                            "sku": product.sku,
                            "name": product.name,
                            "notation": (
                                format_glass_notation(product.composition)
                                if product.composition is not None
                                else None
                            ),
                            "composition": (
                                composition_to_dict(product.composition)
                                if product.composition is not None
                                else None
                            ),
                            "total_thickness_mm": (
                                None
                                if product.composition is None
                                else str(
                                    product.composition.total_thickness_mm().quantize(
                                        Decimal("0.01")
                                    )
                                )
                            ),
                            "safety_class": product.safety_class,
                            "ug_w_m2k": (
                                None if product.ug_w_m2k is None else str(product.ug_w_m2k)
                            ),
                            "g_value": (
                                None if product.g_value is None else str(product.g_value)
                            ),
                            "light_transmission_pct": (
                                None
                                if product.light_transmission_pct is None
                                else str(product.light_transmission_pct)
                            ),
                            "weight_kg_m2": (
                                None if product.weight_kg_m2 is None else str(product.weight_kg_m2)
                            ),
                            "min_billable_area_m2": (
                                None if product.min_area_m2 is None else str(product.min_area_m2)
                            ),
                            "price_tier": product.price_tier,
                            "surcharges": [
                                {
                                    "kind": rate.kind,
                                    "unit": rate.unit,
                                    "amount": str(rate.amount),
                                    "currency": rate.currency,
                                    "label": rate.label,
                                }
                                for rate in product.surcharges
                            ],
                            "review_pending": product.review_pending,
                        }
                        for product in params.glass_products.values()
                    ],
                    "glass_specs": [
                        {
                            "sku": item["technical_sku"],
                            "spec": item["glass_spec"],
                        }
                        for item in glass_rows
                    ],
                    "colors": list(params.finishes),
                    "coupler_skus": sorted(couplers),
                    "coupler_profiles": [
                        {
                            "sku": item.sku,
                            "name": names.get(item.sku, item.sku),
                            "material": item.material.value,
                            "face_width_mm": str(item.face_width_mm),
                            "section": _section_json(item.section),
                        }
                        for item in sorted(couplers.values(), key=lambda article: article.sku)
                    ],
                    "glazing_beads": [
                        {
                            "glass_thickness_mm": str(thickness),
                            "bead_width_mm": str(rule.bead_width_mm),
                            "sku": rule.bead_article.sku,
                            "section": _section_json(rule.bead_article.section),
                        }
                        for thickness, rule in sorted(params.glazing_bead_rules.items())
                    ],
                    "panel_skus": sorted(params.available_panel_rules),
                    "panel_choices": [
                        {
                            "sku": item.sku,
                            "name": item.name,
                            "thickness_mm": str(item.thickness_mm),
                        }
                        for item in sorted(
                            params.available_panel_rules.values(),
                            key=lambda panel: panel.sku,
                        )
                    ],
                    "rebate_depth_mm": str(params.rebate_depth_mm),
                    "sash_overlap_mm": str(params.sash_overlap_mm),
                    "depth_mm": str(params.depth_mm),
                }
            )
