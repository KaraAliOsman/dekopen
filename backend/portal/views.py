"""HTTP surface for the customer approval portal."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from uuid import UUID

from django.db import DatabaseError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from config.throttling import PortalRateThrottle
from documents.repository import DocumentaryError
from documents.views import ERRORS, documentary_scope, validate
from portal import service
from portal.serializers import (
    ApprovalRecordSerializer,
    DecideRequestSerializer,
    InternalApprovalResultSerializer,
    InternalApprovalSerializer,
    PortalQuoteSerializer,
    ShareQuoteResponseSerializer,
)

logger = logging.getLogger(__name__)

_WRITERS = ("OWNER", "ESTIMATOR")


@contextmanager
def public_portal_errors():
    try:
        yield
    except DocumentaryError as error:
        if error.code in (
            "project_not_found",
            "version_not_found",
            "quote_not_found",
            "approval_not_found",
        ):
            raise contract_error(404, error.code, "El enlace de cotización no existe.") from error
        if error.code == "quote_revoked":
            raise contract_error(
                410, error.code, "Este enlace fue revocado; solicita uno nuevo."
            ) from error
        if error.code == "approval_not_pending":
            raise contract_error(
                409, error.code, "Este enlace ya fue respondido y no puede revocarse."
            ) from error
        if error.code in ("quote_expired", "quote_validity_expired"):
            raise contract_error(
                410, error.code, "Esta cotización ya no está vigente; solicita un enlace nuevo."
            ) from error
        if error.code == "quote_approve_revision_mismatch":
            raise contract_error(
                409, error.code, "Esta cotización fue reemplazada por una revisión nueva."
            ) from error
        if error.code == "quote_link_stale":
            raise contract_error(
                409, error.code, "Esta cotización fue reemplazada por una revisión nueva."
            ) from error
        if error.code == "quote_already_decided":
            raise contract_error(
                409, error.code, "Esta cotización ya fue respondida."
            ) from error
        raise contract_error(
            422, error.code, "La acción sobre la cotización fue rechazada."
        ) from error
    except serializers.ValidationError as error:
        raise contract_error(
            400, "portal_payload_invalid", "Revisa la decisión ingresada."
        ) from error
    except DatabaseError as error:
        logger.warning("Portal transaction rejected (%s)", type(error).__name__)
        raise contract_error(
            409, "portal_transaction_rejected", "La operación fue rechazada por la base."
        ) from error


class ProjectQuoteLinkView(APIView):
    @extend_schema(
        operation_id="project_quote_link_create",
        description="Mint a customer-approval link for the latest sealed version.",
        request=None,
        responses={200: ShareQuoteResponseSerializer, **ERRORS},
    )
    def post(self, request, project_id: UUID):
        with public_portal_errors(), documentary_scope(request, _WRITERS) as (
            token,
            tenant,
            org_id,
        ):
            output = service.share_quote(
                org_id=org_id,
                project_id=project_id,
                actor_id=token.user_id,
                role=tenant.active_organization.role,
            )
            output["path"] = f"/cotizacion/{output['token']}"
            return Response(output)

    @extend_schema(
        operation_id="project_quote_links_list",
        description="Every approval link minted for the project, newest first.",
        request=None,
        responses={200: ApprovalRecordSerializer(many=True), **ERRORS},
    )
    def get(self, request, project_id: UUID):
        with public_portal_errors(), documentary_scope(
            request, ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")
        ) as (_, _, org_id):
            return Response(
                ApprovalRecordSerializer(
                    service.list_approvals(org_id=org_id, project_id=project_id),
                    many=True,
                ).data
            )


class ProjectQuoteLinkRevokeView(APIView):
    @extend_schema(
        operation_id="project_quote_link_revoke",
        description="Revoke a PENDING customer-approval link — the token dies immediately.",
        request=None,
        responses={200: ApprovalRecordSerializer(many=True), **ERRORS},
    )
    def post(self, request, project_id: UUID, approval_id: UUID):
        with public_portal_errors(), documentary_scope(request, _WRITERS) as (
            token,
            _,
            org_id,
        ):
            service.revoke_link(
                org_id=org_id,
                project_id=project_id,
                approval_id=approval_id,
                actor_id=token.user_id,
            )
            return Response(
                ApprovalRecordSerializer(
                    service.list_approvals(org_id=org_id, project_id=project_id),
                    many=True,
                ).data
            )


class ProjectQuoteApproveView(APIView):
    @extend_schema(
        operation_id="project_quote_approve_internal",
        description=(
            "Staff records that the customer approved the quote off-channel — "
            "same audit trail and project transition as a portal decision."
        ),
        request=InternalApprovalSerializer,
        responses={200: InternalApprovalResultSerializer, **ERRORS},
    )
    def post(self, request, project_id: UUID):
        with public_portal_errors(), documentary_scope(request, _WRITERS) as (
            token,
            _,
            org_id,
        ):
            payload = validate(InternalApprovalSerializer, request.data or {})
            return Response(
                service.approve_internal(
                    org_id=org_id,
                    project_id=project_id,
                    actor_id=token.user_id,
                    actor_label=token.email or str(token.user_id),
                    note=payload.get("note"),
                )
            )


class PortalQuoteView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PortalRateThrottle]

    @extend_schema(
        operation_id="portal_quote_retrieve",
        description="Public quote summary behind a share token.",
        responses={200: PortalQuoteSerializer, **ERRORS},
    )
    def get(self, request, token: str):
        with public_portal_errors():
            return Response(service.portal_quote(token))


class PortalQuoteDecisionView(APIView):
    authentication_classes = []
    throttle_classes = [PortalRateThrottle]
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="portal_quote_decide",
        description="Customer approves or declines the shared quote.",
        request=DecideRequestSerializer,
        responses={200: PortalQuoteSerializer, **ERRORS},
    )
    def post(self, request, token: str):
        data = validate(DecideRequestSerializer, request.data)
        with public_portal_errors():
            output = service.decide_quote(
                token=token,
                decision=str(data["decision"]),
                decided_by=str(data["decided_by"]).strip(),
                note=str(data.get("note") or "").strip() or None,
                decided_rut=str(data.get("decided_rut") or "").strip() or None,
            )
            return Response(output)
