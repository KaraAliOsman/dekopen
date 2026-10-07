"""Authenticated identity and active-organization bootstrap endpoint."""

from __future__ import annotations

from typing import cast

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.rls import authenticated_rls_context
from authentication.serializers import (
    ACTIVE_ORGANIZATION_HEADER,
    AuthMeResponseSerializer,
    ErrorResponseSerializer,
)
from authentication.tenancy import (
    MembershipRepository,
    enforce_owner_mfa,
    resolve_tenant_context,
)
from authentication.types import SupabaseUser, VerifiedSupabaseToken


def verified_request_token(request: Request) -> VerifiedSupabaseToken:
    if not isinstance(request.auth, VerifiedSupabaseToken):
        raise contract_error(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "Authentication is required",
        )
    return request.auth


def authenticated_request_user(request: Request) -> SupabaseUser:
    if not isinstance(request.user, SupabaseUser):
        raise contract_error(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "Authentication is required",
        )
    return cast(SupabaseUser, request.user)


class AuthMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_me",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={
            200: AuthMeResponseSerializer,
            400: OpenApiResponse(ErrorResponseSerializer),
            401: OpenApiResponse(ErrorResponseSerializer),
            403: OpenApiResponse(ErrorResponseSerializer),
            409: OpenApiResponse(ErrorResponseSerializer),
        },
        tags=["auth"],
    )
    def get(self, request: Request) -> Response:
        token = verified_request_token(request)
        user = authenticated_request_user(request)
        with authenticated_rls_context(token.claims):
            # Auto-reclamo: invitaciones pendientes del correo verificado se
            # convierten en membresías activas antes de resolver el tenant.
            from projects.org_settings import claim_own_invitations

            claim_own_invitations(token.email, token.user_id)
            memberships = MembershipRepository().list_active_for_user(token.user_id)
            tenant = resolve_tenant_context(
                memberships,
                request.headers.get("X-Organization-ID"),
            )
            enforce_owner_mfa(tenant, token.aal)

        active = tenant.active_organization
        payload = {
            "user": {"id": str(user.id), "email": user.email},
            "aal": token.aal,
            "active_organization": {
                "id": str(active.organization_id),
                "name": active.organization_name,
                "role": active.role,
            },
            "memberships": [item.public_dict() for item in tenant.memberships],
        }
        return Response(payload, status=status.HTTP_200_OK)
