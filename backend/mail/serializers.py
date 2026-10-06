"""Serializers de payloads para los job types de correo y del status API.
Solo refs — el handler re-lee el estado comprometido al ejecutarse."""

from __future__ import annotations

from rest_framework import serializers


class QuoteSentSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    token = serializers.CharField(max_length=200)


class QuoteApprovedSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    decided_by = serializers.CharField(max_length=255)


class PaymentReceivedSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    payment_id = serializers.UUIDField()


class StepBlockedSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    step_label = serializers.CharField(max_length=160)
    note = serializers.CharField(max_length=500)


class PricingDecisionSerializer(serializers.Serializer):
    operation_id = serializers.UUIDField()
    outcome = serializers.ChoiceField(choices=['APPLIED', 'REJECTED', 'WITHDRAWN'])


class MailStatusSerializer(serializers.Serializer):
    provider = serializers.CharField()
    configured = serializers.BooleanField()
    from_address = serializers.CharField()
    queued = serializers.IntegerField()
    sent_7d = serializers.IntegerField()
    failed_7d = serializers.IntegerField()
    skipped_7d = serializers.IntegerField()


class MailPreviewSerializer(serializers.Serializer):
    template = serializers.CharField()
    audience = serializers.CharField()
    subject = serializers.CharField()
    html = serializers.CharField()
    text = serializers.CharField()
