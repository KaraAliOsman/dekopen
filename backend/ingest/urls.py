from django.urls import path

from ingest.views import (
    CatalogImportConfirmView,
    CatalogImportTemplateView,
    CatalogImportDetailView,
    CatalogImportsView,
    ProjectImportConfirmView,
    ProjectImportDetailView,
    ProjectImportsView,
)

urlpatterns = [
    path(
        "projects/<uuid:project_id>/imports/",
        ProjectImportsView.as_view(),
        name="project-imports",
    ),
    path(
        "projects/<uuid:project_id>/imports/<uuid:import_id>/",
        ProjectImportDetailView.as_view(),
        name="project-import-detail",
    ),
    path(
        "projects/<uuid:project_id>/imports/<uuid:import_id>/confirm/",
        ProjectImportConfirmView.as_view(),
        name="project-import-confirm",
    ),
    path(
        "catalog-imports/",
        CatalogImportsView.as_view(),
        name="catalog-imports",
    ),
    path(
        "catalog-imports/template/",
        CatalogImportTemplateView.as_view(),
        name="catalog-import-template",
    ),
    path(
        "catalog-imports/<uuid:import_id>/",
        CatalogImportDetailView.as_view(),
        name="catalog-import-detail",
    ),
    path(
        "catalog-imports/<uuid:import_id>/confirm/",
        CatalogImportConfirmView.as_view(),
        name="catalog-import-confirm",
    ),
]
