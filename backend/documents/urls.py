from django.urls import path

from documents.views import (
    ArtifactAccessView,
    ArtifactGenerateView,
    ArtifactListView,
    DocumentaryInputsView,
    FreezeRevisionView,
    RevisionCompareView,
)

urlpatterns = [
    path("artifacts/", ArtifactGenerateView.as_view(), name="documentary-artifact-generate"),
    path(
        "artifacts/<uuid:artifact_id>/access/",
        ArtifactAccessView.as_view(),
        name="documentary-artifact-access",
    ),
    path(
        "projects/<uuid:project_id>/artifacts/",
        ArtifactListView.as_view(),
        name="documentary-artifact-list",
    ),
    path(
        "projects/<uuid:project_id>/inputs/",
        DocumentaryInputsView.as_view(),
        name="documentary-inputs",
    ),
    path(
        "projects/<uuid:project_id>/freeze/",
        FreezeRevisionView.as_view(),
        name="documentary-freeze",
    ),
    path(
        "projects/<uuid:project_id>/versions/compare/",
        RevisionCompareView.as_view(),
        name="documentary-versions-compare",
    ),
]
