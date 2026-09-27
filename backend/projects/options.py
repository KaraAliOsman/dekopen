"""Read-only technical choices for the manual estimator, without cost information."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.views import APIView

from catalogs.serializers import ProfileSectionSerializer
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


class KitChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    opening_type = serializers.CharField()


class GlassSpecChoiceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    spec = serializers.CharField(allow_null=True)


class DesignOptionsSerializer(serializers.Serializer):
    profiles = ProfileChoiceSerializer(many=True)
    glazing_thicknesses = serializers.ListField(child=serializers.CharField())
    hardware_kits = KitChoiceSerializer(many=True)
    glass_skus = serializers.ListField(child=serializers.CharField())
    glass_specs = GlassSpecChoiceSerializer(many=True)
    colors = serializers.ListField(child=serializers.CharField())
    coupler_skus = serializers.ListField(child=serializers.CharField())
    coupler_profiles = CouplerChoiceSerializer(many=True)
    glazing_beads = GlazingBeadChoiceSerializer(many=True)
    panel_skus = serializers.ListField(child=serializers.CharField())
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
                        {"sku": item.sku, "name": item.name, "opening_type": item.opening_type}
                        for item in params.available_hardware_kits
                    ],
                    "glass_skus": [item["technical_sku"] for item in glass_rows],
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
                    "rebate_depth_mm": str(params.rebate_depth_mm),
                    "sash_overlap_mm": str(params.sash_overlap_mm),
                    "depth_mm": str(params.depth_mm),
                }
            )
