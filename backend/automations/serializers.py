"""Payload serializers for the automation job types. Refs only — every handler
re-reads live domain state, so a queued job always computes from the committed
truth rather than a stale request-time snapshot."""

from rest_framework import serializers


class VersionRefsSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()


class OrderRefsSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()


class StepAdvanceSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    step_code = serializers.CharField(max_length=40)


class CommercialRefreshSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    payment_id = serializers.UUIDField(required=False)


class CatalogTaskSerializer(serializers.Serializer):
    system_id = serializers.UUIDField()
    version_id = serializers.UUIDField(required=False)
