"""OpenAPI-visible response contracts for authentication."""

from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter

ACTIVE_ORGANIZATION_HEADER = OpenApiParameter(
    name="X-Organization-ID",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Active organization; validated against the JWT user's active memberships.",
)


class UserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField(allow_blank=True)


class MembershipSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    organization_name = serializers.CharField()
    role = serializers.ChoiceField(
        choices=("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER", "OPERATOR")
    )


class ActiveOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.ChoiceField(
        choices=("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER", "OPERATOR")
    )


class AuthMeResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    aal = serializers.ChoiceField(choices=("aal1", "aal2"))
    active_organization = ActiveOrganizationSerializer(allow_null=True)
    memberships = MembershipSerializer(many=True)


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    required_aal = serializers.ChoiceField(choices=("aal2",), required=False)


class ErrorResponseSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()
    memberships = MembershipSerializer(many=True, required=False)
