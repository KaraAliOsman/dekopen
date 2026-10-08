"""Import contracts — strict serializers for the ingestion surface.

Response envelopes expose an `import` key — a Python keyword, so the parent
serializer classes are built via type() with the field declared by string."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from documents.serializers import StrictSerializer
from engine_api.serializers import DecimalStringField
from ingest.catalog_parser import ROLES
from ingest.parser import _OPENING_TYPES
from ingest.spreadsheet import ENTITIES


class ExtractPayloadSerializer(StrictSerializer):
    import_id = serializers.UUIDField()


class ImportUploadSerializer(StrictSerializer):
    file = serializers.FileField()


class ImportResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    file_name = serializers.CharField()
    kind = serializers.CharField()
    status = serializers.CharField()
    candidates = serializers.ListField(child=serializers.DictField())
    warnings = serializers.ListField(child=serializers.CharField())
    result = serializers.ListField(child=serializers.DictField())
    error_code = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


ImportDetailResponseSerializer = type(
    "ImportDetailResponseSerializer",
    (serializers.Serializer,),
    {"import": ImportResponseSerializer()},
)


class ImportListResponseSerializer(serializers.Serializer):
    imports = ImportResponseSerializer(many=True)


ImportCreateResponseSerializer = type(
    "ImportCreateResponseSerializer",
    (serializers.Serializer,),
    {
        "import": ImportResponseSerializer(),
        "job": serializers.DictField(),
    },
)


class ConfirmItemSerializer(StrictSerializer):
    key = serializers.CharField(max_length=40)
    label = serializers.CharField(max_length=100, allow_blank=True)
    width_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("250"))
    height_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("250"))
    quantity = serializers.IntegerField(min_value=1, max_value=999)
    opening_type = serializers.ChoiceField(choices=sorted(_OPENING_TYPES))
    system_id = serializers.UUIDField()
    # Validated against the system's declared finishes downstream
    # (adapter has params; serializers don't).
    color = serializers.CharField(max_length=50)
    glass_thickness_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1"))
    # glass_spec is the physical composition; glass_article_sku is the
    # catalog/technical SKU — a saved position carries both. The spec is
    # optional on the request: the purchase mapping's recipe wins when the
    # catalog declares one, and only a mapping without a spec falls back to
    # this field — so the glazing-bead slot can never masquerade as panes.
    glass_spec = serializers.CharField(max_length=120, required=False, allow_blank=True)
    glass_article_sku = serializers.CharField(max_length=120)
    # Doors need the panel authority — required by the engine for DOOR_ENTRY,
    # enforced at confirm time only for that opening type.
    panel_article_sku = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )


class ImportConfirmSerializer(StrictSerializer):
    items = ConfirmItemSerializer(many=True, min_length=1, max_length=200)


ImportConfirmResponseSerializer = type(
    "ImportConfirmResponseSerializer",
    (serializers.Serializer,),
    {
        "import": ImportResponseSerializer(),
        "created": serializers.ListField(child=serializers.DictField()),
        "errors": serializers.ListField(child=serializers.DictField()),
    },
)


class CatalogImportResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    file_name = serializers.CharField()
    kind = serializers.CharField()
    status = serializers.CharField()
    system_id = serializers.UUIDField(allow_null=True)
    candidates = serializers.ListField(child=serializers.DictField())
    warnings = serializers.ListField(child=serializers.CharField())
    result = serializers.ListField(child=serializers.DictField())
    error_code = serializers.CharField(allow_null=True)
    created_by = serializers.UUIDField(allow_null=True)
    created_by_label = serializers.CharField(allow_null=True, required=False)
    reviewed_by = serializers.UUIDField(allow_null=True)
    reviewed_by_label = serializers.CharField(allow_null=True, required=False)
    reviewed_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogImportEventSerializer(serializers.Serializer):
    """One immutable lifecycle event (UPLOADED/EXTRACTED/CONFIRMED) — the
    audit trail from file upload to catalog publication."""

    id = serializers.UUIDField()
    event = serializers.CharField()
    actor_id = serializers.UUIDField(allow_null=True)
    actor_label = serializers.CharField(allow_null=True)
    detail = serializers.DictField()
    created_at = serializers.DateTimeField()


CatalogImportDetailResponseSerializer = type(
    "CatalogImportDetailResponseSerializer",
    (serializers.Serializer,),
    {
        "import": CatalogImportResponseSerializer(),
        "events": CatalogImportEventSerializer(many=True),
    },
)


class CatalogImportListResponseSerializer(serializers.Serializer):
    imports = CatalogImportResponseSerializer(many=True)


CatalogImportCreateResponseSerializer = type(
    "CatalogImportCreateResponseSerializer",
    (serializers.Serializer,),
    {
        "import": CatalogImportResponseSerializer(),
        "job": serializers.DictField(),
    },
)


class CatalogItemSerializer(StrictSerializer):
    key = serializers.CharField(max_length=40)
    entity = serializers.ChoiceField(
        choices=sorted(ENTITIES), required=False, default="PROFILE"
    )
    fields = serializers.DictField(required=False, default=dict)
    sku = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=255, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=sorted(ROLES), required=False, default="ADDITIONAL")
    face_width_mm = DecimalStringField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.5"),
        required=False, allow_null=True,
    )
    # UNKNOWN is a state: parser-extracted candidates may carry None for any
    # fabrication field the supplier document never stated.
    commercial_length_mm = DecimalStringField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("1"),
        required=False,
        allow_null=True,
    )
    welding_loss_mm = DecimalStringField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
    )
    reinforcement_sku = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=""
    )
    weight_kg_m = DecimalStringField(
        max_digits=8,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        required=False,
        allow_null=True,
    )
    steel_weight_kg_m = DecimalStringField(
        max_digits=8,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        required=False,
        allow_null=True,
    )


class NewSystemSerializer(StrictSerializer):
    code = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=255, allow_blank=True, default="")
    depth_mm = DecimalStringField(max_digits=10, decimal_places=2, min_value=Decimal("1"))
    material = serializers.ChoiceField(choices=["PVC", "ALUMINIUM"])
    system_family = serializers.ChoiceField(
        choices=["CASEMENT", "SLIDING", "LIFT_SLIDE", "DOOR", "FACADE_FIXED"]
    )
    # Fabricación declarada — profile_systems los exige NOT NULL y el motor
    # los consume como autoridad; nunca se inventan en el servidor.
    sliding_glazing_deduction_width_mm = DecimalStringField(
        max_digits=10, decimal_places=2, min_value=Decimal("0")
    )
    sliding_glazing_deduction_height_mm = DecimalStringField(
        max_digits=10, decimal_places=2, min_value=Decimal("0")
    )
    door_leaf_side_clearance_mm = DecimalStringField(
        max_digits=10, decimal_places=2, min_value=Decimal("0")
    )
    finishes = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, default=list
    )


class CatalogImportConfirmSerializer(StrictSerializer):
    system_id = serializers.UUIDField(required=False)
    new_system = NewSystemSerializer(required=False)
    cost_list_id = serializers.UUIDField(required=False)
    items = CatalogItemSerializer(many=True, min_length=1, max_length=200)

    def validate(self, data):
        if not data.get("system_id") and not data.get("new_system"):
            raise serializers.ValidationError(
                {"system_id": "catalog_system_required"}
            )
        return data

    def validate_items(self, value):
        # One candidate seeds at most one article per request — duplicate keys
        # would create two articles from the same reviewed row.
        keys = [item["key"] for item in value]
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError("catalog_duplicate_key")
        return value


CatalogImportConfirmResponseSerializer = type(
    "CatalogImportConfirmResponseSerializer",
    (serializers.Serializer,),
    {
        "import": CatalogImportResponseSerializer(),
        "created": serializers.ListField(child=serializers.DictField()),
        "errors": serializers.ListField(child=serializers.DictField()),
    },
)
