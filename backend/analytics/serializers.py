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


class TodayQueueItemSerializer(serializers.Serializer):
    kind = serializers.CharField()
    urgency = serializers.ChoiceField(
        choices=("overdue", "today", "soon", "when_free")
    )
    phrase = serializers.CharField()
    reason = serializers.CharField(allow_null=True)
    entity_code = serializers.CharField(allow_null=True)
    entity_label = serializers.CharField(allow_null=True)
    to = serializers.CharField()
    cta = serializers.CharField()
    count = serializers.IntegerField(allow_null=True)


class TodayQueuePanelRowSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.CharField()
    count = serializers.IntegerField()


class TodayQueuePanelSerializer(serializers.Serializer):
    kind = serializers.CharField()
    title = serializers.CharField()
    rows = TodayQueuePanelRowSerializer(many=True)


class TodayQueueSerializer(serializers.Serializer):
    schema = serializers.CharField()
    role = serializers.CharField()
    date = serializers.CharField()
    items = TodayQueueItemSerializer(many=True)
    panels = TodayQueuePanelSerializer(many=True)
