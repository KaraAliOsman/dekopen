"""D06 — position extras & project services API surface.

- ``projects/<id>/services/`` GET/PUT: the services the project declares
  (instalación, sellado, retiro, andamio, flete). Selections are catalog
  references; pricing measures them off the positions, never free text.
- ``organization/extras-config/`` GET/PUT: the org's documentary policy
  (sublíneas detalladas o agrupadas) and the default templates —
  extras preselected into new positions, services into new projects.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.views import APIView

from authentication.errors import contract_error
from dekopen_engine.extras import evaluate_service_lines
from dekopen_engine.models import (
    ServiceArticle,
    ServiceKind,
    ServicePositionMeasure,
    ServiceQtyRule,
)
from documents.repository import documentary_backend
from pricing.repository import one, rows, write
from projects.views import READ_ROLES, SCHEMA, WRITE_ROLES, response
from pricing.views import ERRORS, scope

D = Decimal


def _not_found(code: str, detail: str):
    return contract_error(404, code, detail)


def _service_article_json(item: dict, selected_ids: set[str]) -> dict:
    return {
        "id": str(item["id"]),
        "code": item["code"],
        "name": item["name"],
        "kind": item["kind"],
        "qty_rule": item["qty_rule"],
        "unit_price": None if item["unit_price"] is None else str(item["unit_price"]),
        "unit_price_currency": item["unit_price_currency"],
        "unit_cost": None if item["unit_cost"] is None else str(item["unit_cost"]),
        "is_active": bool(item["is_active"]),
        "read_only": item["org_id"] is None,
        "selected": str(item["id"]) in selected_ids,
    }


def _visible_service_articles(org_id: UUID) -> list[dict]:
    return rows(
        "SELECT id, org_id, code, name, kind::text, qty_rule::text,"
        " unit_price, unit_price_currency, unit_cost, is_active"
        " FROM public.service_articles"
        " WHERE org_id = %s OR org_id IS NULL ORDER BY code",
        [str(org_id)],
    )


def _selected_ids(project_id: str, org_id: UUID) -> set[str]:
    return {
        str(item["service_article_id"])
        for item in rows(
            "SELECT service_article_id FROM public.project_service_selections"
            " WHERE project_id = %s AND org_id = %s",
            [project_id, str(org_id)],
        )
    }


def _service_preview(project_id: str, org_id: UUID) -> list[dict]:
    """Read-only engine preview of the measured quantities — the same
    derivation pricing applies; a priceless service still previews its
    quantity with a null total (Sin dato)."""
    selected = rows(
        "SELECT a.code, a.name, a.kind::text, a.qty_rule::text,"
        " a.unit_price, a.unit_price_currency"
        " FROM public.project_service_selections sel"
        " JOIN public.service_articles a ON a.id = sel.service_article_id"
        " WHERE sel.project_id = %s AND sel.org_id = %s ORDER BY a.code",
        [project_id, str(org_id)],
    )
    if not selected:
        return []
    positions = rows(
        "SELECT width_mm, height_mm, quantity FROM public.project_positions"
        " WHERE project_id = %s AND org_id = %s ORDER BY position_index",
        [project_id, str(org_id)],
    )
    articles = [
        ServiceArticle(
            code=str(item["code"]),
            name=str(item["name"]),
            kind=ServiceKind(str(item["kind"])),
            qty_rule=ServiceQtyRule(str(item["qty_rule"])),
            unit_price=(
                None if item["unit_price"] is None else D(str(item["unit_price"]))
            ),
            unit_price_currency=(
                None
                if item["unit_price_currency"] is None
                else str(item["unit_price_currency"])
            ),
        )
        for item in selected
    ]
    measures = [
        ServicePositionMeasure(
            width_mm=D(str(item["width_mm"])),
            height_mm=D(str(item["height_mm"])),
            quantity=int(item["quantity"]),
        )
        for item in positions
    ]
    return [
        {
            "code": line.code,
            "name": line.name,
            "kind": line.kind.value,
            "quantity": str(line.quantity),
            "unit": line.unit,
            "unit_price": (
                None if line.unit_price is None else str(line.unit_price)
            ),
            "unit_price_currency": line.unit_price_currency,
            "total_price": (
                None if line.total_price is None else str(line.total_price)
            ),
            "detail": line.detail,
        }
        for line in evaluate_service_lines(articles, measures)
    ]


class ServiceSelectionWriteSerializer(serializers.Serializer):
    service_article_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=True
    )


class ServiceArticleOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    qty_rule = serializers.CharField()
    unit_price = serializers.CharField(allow_null=True)
    unit_price_currency = serializers.CharField(allow_null=True)
    unit_cost = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    read_only = serializers.BooleanField()
    selected = serializers.BooleanField()


class ServiceLineSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    quantity = serializers.CharField()
    unit = serializers.CharField()
    unit_price = serializers.CharField(allow_null=True)
    unit_price_currency = serializers.CharField(allow_null=True)
    total_price = serializers.CharField(allow_null=True)
    detail = serializers.CharField(allow_null=True)


class ProjectServicesResponseSerializer(serializers.Serializer):
    items = ServiceArticleOptionSerializer(many=True)
    lines = ServiceLineSerializer(many=True)


class ProjectServicesView(APIView):
    @extend_schema(
        operation_id="project_services_read",
        responses={200: ProjectServicesResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request, project_id):
        with scope(request, READ_ROLES) as (_, _, org):
            _require_project(project_id, org)
            selected = _selected_ids(str(project_id), org)
            return response(
                {
                    "items": [
                        _service_article_json(item, selected)
                        for item in _visible_service_articles(org)
                    ],
                    "lines": _service_preview(str(project_id), org),
                }
            )

    @extend_schema(
        operation_id="project_services_update",
        request=ServiceSelectionWriteSerializer,
        responses={200: ProjectServicesResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request, project_id):
        with scope(request, WRITE_ROLES) as (_, _, org):
            project = _require_project(project_id, org)
            if project["status"] != "DRAFT":
                raise contract_error(
                    409,
                    "service_selection_locked",
                    "projects.errors.service_selection_locked",
                )
            validator = ServiceSelectionWriteSerializer(data=request.data)
            if not validator.is_valid():
                raise contract_error(
                    400,
                    "service_selection_invalid",
                    "projects.errors.service_selection_invalid",
                    error_extra={"fields": validator.errors},
                )
            wanted = {
                str(item) for item in validator.validated_data["service_article_ids"]
            }
            visible = {
                str(item["id"]): item
                for item in _visible_service_articles(org)
                if item["is_active"]
            }
            unknown = wanted - set(visible)
            if unknown:
                raise contract_error(
                    400,
                    "service_article_unknown",
                    "projects.errors.service_article_unknown",
                )
            with transaction.atomic():
                write(
                    "DELETE FROM public.project_service_selections"
                    " WHERE project_id = %s AND org_id = %s",
                    [str(project_id), str(org)],
                )
                for service_id in sorted(wanted):
                    write(
                        "INSERT INTO public.project_service_selections"
                        " (project_id, org_id, service_article_id)"
                        " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        [str(project_id), str(org), service_id],
                    )
            selected = _selected_ids(str(project_id), org)
            return response(
                {
                    "items": [
                        _service_article_json(item, selected)
                        for item in _visible_service_articles(org)
                    ],
                    "lines": _service_preview(str(project_id), org),
                }
            )


def _require_project(project_id, org_id: UUID) -> dict:
    row = rows(
        "SELECT id, status FROM public.projects WHERE id = %s AND org_id = %s",
        [str(project_id), str(org_id)],
    )
    if not row:
        raise _not_found("project_not_found", "projects.errors.not_found")
    return row[0]


# ─── org configuration ────────────────────────────────────────────────────


class ExtraTemplateWriteSerializer(serializers.Serializer):
    extra_article_id = serializers.UUIDField()
    sides = serializers.ListField(
        # Same side set the glass-surcharge `edges` field declares — one
        # EdgesEnum in the schema (order matched so spectacular dedupes).
        child=serializers.ChoiceField(choices=["top", "right", "bottom", "left"]),
        required=False,
        allow_empty=True,
    )
    qty = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class ExtrasConfigWriteSerializer(serializers.Serializer):
    extras_display = serializers.ChoiceField(
        choices=["DETAILED", "GROUPED"], required=False
    )
    extra_templates = ExtraTemplateWriteSerializer(many=True, required=False)
    service_templates = serializers.ListField(
        child=serializers.UUIDField(), required=False
    )


class ExtraTemplateResponseSerializer(serializers.Serializer):
    extra_article_id = serializers.UUIDField()
    sku = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    system_id = serializers.UUIDField()
    system_code = serializers.CharField()
    sides = serializers.ListField(child=serializers.CharField())
    qty = serializers.IntegerField(allow_null=True)


class ExtrasConfigResponseSerializer(serializers.Serializer):
    extras_display = serializers.CharField()
    extra_templates = ExtraTemplateResponseSerializer(many=True)
    service_templates = serializers.ListField(child=serializers.UUIDField())


def _extras_config(org_id: UUID) -> dict:
    org = one(
        "SELECT extras_display FROM public.tenancy_organizations WHERE id = %s",
        [str(org_id)],
        "organization_not_found",
    )
    templates = rows(
        "SELECT t.extra_article_id, t.sides, t.qty, a.sku, a.name,"
        " a.system_id, a.kind::text, s.code AS system_code"
        " FROM public.org_extra_templates t"
        " JOIN public.extra_articles a ON a.id = t.extra_article_id"
        " JOIN public.profile_systems s ON s.id = a.system_id"
        " WHERE t.org_id = %s ORDER BY a.sku",
        [str(org_id)],
    )
    services = rows(
        "SELECT service_article_id FROM public.org_service_templates"
        " WHERE org_id = %s ORDER BY service_article_id",
        [str(org_id)],
    )
    return {
        "extras_display": org["extras_display"],
        "extra_templates": [
            {
                "extra_article_id": str(item["extra_article_id"]),
                "sku": item["sku"],
                "name": item["name"],
                "kind": item["kind"],
                "system_id": str(item["system_id"]),
                "system_code": item["system_code"],
                "sides": list(item["sides"] or []),
                "qty": item["qty"],
            }
            for item in templates
        ],
        "service_templates": [str(item["service_article_id"]) for item in services],
    }


class OrganizationExtrasConfigView(APIView):
    @extend_schema(
        operation_id="organization_extras_config_read",
        responses={200: ExtrasConfigResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def get(self, request):
        with scope(request, READ_ROLES) as (_, _, org):
            return response(_extras_config(org))

    @extend_schema(
        operation_id="organization_extras_config_update",
        request=ExtrasConfigWriteSerializer,
        responses={200: ExtrasConfigResponseSerializer, **ERRORS},
        **SCHEMA,
    )
    def put(self, request):
        with scope(request, WRITE_ROLES) as (_, _, org):
            validator = ExtrasConfigWriteSerializer(data=request.data)
            if not validator.is_valid():
                raise contract_error(
                    400,
                    "extras_config_invalid",
                    "projects.errors.extras_config_invalid",
                    error_extra={"fields": validator.errors},
                )
            data = validator.validated_data
            with transaction.atomic():
                if "extras_display" in data:
                    # The org row's branding-update authority governs the
                    # documentary policy — the documentary role owns the
                    # column grant.
                    with documentary_backend():
                        write(
                            "UPDATE public.tenancy_organizations"
                            " SET extras_display = %s, updated_at = now()"
                            " WHERE id = %s",
                            [data["extras_display"], str(org)],
                        )
                if "extra_templates" in data:
                    _replace_extra_templates(org, data["extra_templates"])
                if "service_templates" in data:
                    _replace_service_templates(org, data["service_templates"])
            return response(_extras_config(org))


def _replace_extra_templates(org_id: UUID, templates: list[dict]) -> None:
    """Templates are org defaults preselected into new positions — each
    references a visible extra article; the engine still re-measures every
    selection, so a template can never inject a fabricated number."""
    wanted_ids = {str(item["extra_article_id"]) for item in templates}
    visible = {
        str(item["id"])
        for item in rows(
            "SELECT a.id FROM public.extra_articles a"
            " JOIN public.profile_systems s ON s.id = a.system_id"
            " WHERE (a.org_id = %s OR (a.org_id IS NULL AND s.org_id IS NULL AND s.is_global))",
            [str(org_id)],
        )
    }
    if wanted_ids - visible:
        raise contract_error(
            400,
            "extra_article_unknown",
            "projects.errors.extra_article_unknown",
        )
    write("DELETE FROM public.org_extra_templates WHERE org_id = %s", [str(org_id)])
    for item in templates:
        write(
            "INSERT INTO public.org_extra_templates"
            " (org_id, extra_article_id, sides, qty) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT DO NOTHING",
            [
                str(org_id),
                str(item["extra_article_id"]),
                list(item.get("sides") or []),
                item.get("qty"),
            ],
        )


def _replace_service_templates(org_id: UUID, service_ids: list[str]) -> None:
    wanted = {str(item) for item in service_ids}
    visible = {
        str(item["id"])
        for item in _visible_service_articles(org_id)
        if item["is_active"]
    }
    if wanted - visible:
        raise contract_error(
            400,
            "service_article_unknown",
            "projects.errors.service_article_unknown",
        )
    write("DELETE FROM public.org_service_templates WHERE org_id = %s", [str(org_id)])
    for service_id in sorted(wanted):
        write(
            "INSERT INTO public.org_service_templates"
            " (org_id, service_article_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            [str(org_id), service_id],
        )
