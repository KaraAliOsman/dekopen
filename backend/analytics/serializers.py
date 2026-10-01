from rest_framework import serializers


class OperationalSummaryCommercialItemSerializer(serializers.Serializer):
    currency = serializers.CharField()
    quoted = serializers.CharField()
    booked = serializers.CharField()
    collected = serializers.CharField()


class OperationalSummarySerializer(serializers.Serializer):
    schema = serializers.CharField()
    work_orders = serializers.DictField()
    supplier_orders = serializers.DictField()
    throughput_30d = serializers.DictField()
    avg_release_to_dispatch_hours = serializers.FloatField(allow_null=True)
    inventory = serializers.DictField()
    prep = serializers.DictField()
    deliveries = serializers.DictField()
    documents = serializers.DictField()
    projects = serializers.DictField()
    commercial = OperationalSummaryCommercialItemSerializer(many=True)
    recent_events = serializers.ListField()
