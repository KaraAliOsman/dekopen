"""HTTP surface for document ingestion: upload, review, confirm."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from django.db import DatabaseError
from drf_spectacular.utils import extend_schema
from pydantic import ValidationError as PydanticValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER
from dekopen_engine.inspection_models import InspectorConfigurationError
from documents.repository import DocumentaryError
from documents.views import ERRORS, documentary_scope, validate
from engine_api.repository import SystemNotFound

from ingest import catalog_service, service
from ingest.catalog_service import CatalogImportError
from ingest.service import ImportError_
from ingest.serializers import (
    CatalogImportConfirmResponseSerializer,
    CatalogImportConfirmSerializer,
    CatalogImportCreateResponseSerializer,
    CatalogImportDetailResponseSerializer,
    CatalogImportListResponseSerializer,
    ImportConfirmResponseSerializer,
    ImportConfirmSerializer,
    ImportCreateResponseSerializer,
    ImportDetailResponseSerializer,
    ImportListResponseSerializer,
    ImportUploadSerializer,
)

logger = logging.getLogger(__name__)

_READERS = ("OWNER", "ESTIMATOR", "WORKSHOP_MANAGER")
_WRITERS = ("OWNER", "ESTIMATOR")
# Catalog imports belong to the workshop's catalog administration — the same
# writer set CatalogPage uses for article editing.
_CATALOG_WRITERS = ("OWNER", "WORKSHOP_MANAGER")


def _payload(output: dict):
    return Response(json.loads(json.dumps(output, default=str)))


def _translate(error: Exception):
    code = getattr(error, "code", None) or getattr(error, "contract_code", "import_failed")
    known = {
        "import_not_found": (404, "import_not_found", "La importación no existe."),
        "import_kind_unsupported": (
            422, "import_kind_unsupported",
            "Formato no soportado. Sube un PDF, XLSX o imagen.",
        ),
        "import_file_invalid": (422, "import_file_invalid", "Archivo vacío o demasiado grande."),
    }
    if code in known:
        status, contract, message = known[code]
        raise contract_error(status, contract, message)
    raise error


class ProjectImportsView(APIView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="project_imports_list",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: ImportListResponseSerializer, **ERRORS},
        tags=["projects"],
    )
    def get(self, request, project_id: UUID):
        try:
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return _payload(service.list_imports(org_id=org_id, project_id=project_id))
        except (ImportError_, DocumentaryError) as error:
            _translate(error)

    @extend_schema(
        operation_id="project_imports_create",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=ImportUploadSerializer,
        responses={200: ImportCreateResponseSerializer, **ERRORS},
        tags=["projects"],
    )
    def post(self, request, project_id: UUID):
        try:
            with documentary_scope(request, _WRITERS) as (token, _, org_id):
                data = validate(ImportUploadSerializer, request.data)
                upload = data["file"]
                return _payload(
                    service.create_import(
                        org_id=org_id,
                        project_id=project_id,
                        actor_id=token.user_id,
                        file_name=upload.name,
                        content=upload.read(service.MAX_UPLOAD_BYTES + 1),
                        content_type=upload.content_type or "",
                    )
                )
        except (ImportError_, DocumentaryError) as error:
            _translate(error)


class ProjectImportDetailView(APIView):
    @extend_schema(
        operation_id="project_import_get",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: ImportDetailResponseSerializer, **ERRORS},
        tags=["projects"],
    )
    def get(self, request, project_id: UUID, import_id: UUID):
        try:
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return _payload(
                    service.get_import(
                        org_id=org_id, project_id=project_id, import_id=import_id
                    )
                )
        except (ImportError_, DocumentaryError) as error:
            _translate(error)


class ProjectImportConfirmView(APIView):
    @extend_schema(
        operation_id="project_import_confirm",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=ImportConfirmSerializer,
        responses={200: ImportConfirmResponseSerializer, **ERRORS},
        tags=["projects"],
    )
    def post(self, request, project_id: UUID, import_id: UUID):
        try:
            with documentary_scope(request, _WRITERS) as (_, _, org_id):
                data = validate(ImportConfirmSerializer, request.data)
                return _payload(
                    service.confirm_import(
                        org_id=org_id,
                        project_id=project_id,
                        import_id=import_id,
                        items=data["items"],
                    )
                )
        except (
            ImportError_,
            DocumentaryError,
            DatabaseError,
            SystemNotFound,
            InspectorConfigurationError,
            PydanticValidationError,
        ) as error:
            _translate(error)


def _translate_catalog(error: Exception):
    code = getattr(error, "code", None) or getattr(
        error, "contract_code", "catalog_import_failed"
    )
    known = {
        "catalog_import_not_found": (
            404, "catalog_import_not_found", "La importación no existe.",
        ),
        "catalog_import_status_invalid": (
            409, "catalog_import_status_invalid",
            "La importación cambió de estado. Recarga e intenta de nuevo.",
        ),
        "catalog_membership_revoked": (
            403, "catalog_membership_revoked",
            "Tu membresía en esta organización fue revocada.",
        ),
    }
    if code in known:
        status, contract, message = known[code]
        raise contract_error(status, contract, message)
    raise error


class CatalogImportsView(APIView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="catalog_imports_list",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: CatalogImportListResponseSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def get(self, request):
        try:
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return _payload(catalog_service.list_catalog_imports(org_id=org_id))
        except (CatalogImportError, DocumentaryError) as error:
            _translate_catalog(error)

    @extend_schema(
        operation_id="catalog_imports_create",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=ImportUploadSerializer,
        responses={200: CatalogImportCreateResponseSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def post(self, request):
        try:
            with documentary_scope(request, _CATALOG_WRITERS) as (token, _, org_id):
                data = validate(ImportUploadSerializer, request.data)
                upload = data["file"]
                return _payload(
                    catalog_service.create_catalog_import(
                        org_id=org_id,
                        actor_id=token.user_id,
                        file_name=upload.name,
                        content=upload.read(catalog_service.MAX_UPLOAD_BYTES + 1),
                        content_type=upload.content_type or "",
                    )
                )
        except (CatalogImportError, DocumentaryError) as error:
            _translate_catalog(error)


class CatalogImportDetailView(APIView):
    @extend_schema(
        operation_id="catalog_import_get",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        responses={200: CatalogImportDetailResponseSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def get(self, request, import_id: UUID):
        try:
            with documentary_scope(request, _READERS) as (_, _, org_id):
                return _payload(
                    catalog_service.get_catalog_import(
                        org_id=org_id, import_id=import_id
                    )
                )
        except (CatalogImportError, DocumentaryError) as error:
            _translate_catalog(error)


class CatalogImportConfirmView(APIView):
    @extend_schema(
        operation_id="catalog_import_confirm",
        parameters=[ACTIVE_ORGANIZATION_HEADER],
        request=CatalogImportConfirmSerializer,
        responses={200: CatalogImportConfirmResponseSerializer, **ERRORS},
        tags=["catalogs"],
    )
    def post(self, request, import_id: UUID):
        try:
            with documentary_scope(request, _CATALOG_WRITERS) as (token, _, org_id):
                data = validate(CatalogImportConfirmSerializer, request.data)
                return _payload(
                    catalog_service.confirm_catalog_import(
                        org_id=org_id,
                        actor_id=token.user_id,
                        import_id=import_id,
                        system_id=data["system_id"],
                        items=data["items"],
                    )
                )
        except (CatalogImportError, DocumentaryError, DatabaseError) as error:
            _translate_catalog(error)
