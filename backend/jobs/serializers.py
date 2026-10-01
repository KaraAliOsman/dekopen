"""OpenAPI-visible contracts for the job queue API."""

from __future__ import annotations

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("Unknown input fields")
        return super().to_internal_value(data)


class JobRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    state = serializers.ChoiceField(
        choices=("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED")
    )
    progress = serializers.DecimalField(max_digits=5, decimal_places=2)
    result = serializers.JSONField(allow_null=True)
    error = serializers.JSONField(allow_null=True)
    attempt = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    # Deep-link target for AI runs — NULL for every other job type.
    ai_job_id = serializers.UUIDField(required=False, allow_null=True)


class JobEnqueueSerializer(StrictSerializer):
    type = serializers.CharField(max_length=120)
    payload = serializers.JSONField()
    idempotency_key = serializers.CharField(
        required=False, allow_null=True, max_length=128
    )
    max_attempts = serializers.IntegerField(
        required=False, min_value=1, max_value=10, default=3
    )


class JobListQuerySerializer(serializers.Serializer):
    type = serializers.CharField(required=False, max_length=120)
    state = serializers.ChoiceField(
        required=False,
        choices=("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED"),
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=50)
    offset = serializers.IntegerField(required=False, min_value=0, default=0)
