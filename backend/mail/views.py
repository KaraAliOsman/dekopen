"""API del outbox de correo: estado para Ajustes y vista previa dev."""

from __future__ import annotations

import os

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from mail import service
from mail.serializers import MailPreviewSerializer, MailStatusSerializer
from pricing.views import ERRORS, scope

READ_ROLES = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")
SCHEMA = {"parameters": [ACTIVE_ORGANIZATION_HEADER], "tags": ["mail"]}


def _previews_enabled() -> bool:
    return bool(settings.DEBUG) or os.environ.get("MAIL_DEV_PREVIEWS") == "1"


class MailStatusView(APIView):
    @extend_schema(
        operation_id="mail_status",
        responses={200: MailStatusSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return Response(service.tray_status(org_id=org))


class MailPreviewsView(APIView):
    """Las cinco plantillas con la marca real del org — solo desarrollo.
    /dev/correos las dibuja; en producción el endpoint no existe."""

    @extend_schema(
        operation_id="mail_dev_previews",
        responses={200: MailPreviewSerializer(many=True), **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        if not _previews_enabled():
            raise contract_error(
                404, "mail_previews_disabled", "La vista previa es solo para desarrollo."
            )
        with scope(request, READ_ROLES) as (_, _, org):
            return Response(service.dev_previews(org_id=org))
