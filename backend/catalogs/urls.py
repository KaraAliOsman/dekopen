from django.urls import path

from catalogs import views

urlpatterns = [
    path("systems/", views.SystemCollectionView.as_view(), name="catalog-system-list"),
    path(
        "systems/<uuid:row_id>/",
        views.SystemDetailView.as_view(),
        name="catalog-system-detail",
    ),
    path(
        "systems/<uuid:row_id>/review/",
        views.SystemReviewView.as_view(),
        name="catalog-system-review",
    ),
    path(
        "process-profiles/",
        views.ProcessProfileCollectionView.as_view(),
        name="catalog-process-profiles",
    ),
    path(
        "section-imports/",
        views.SectionImportCollectionView.as_view(),
        name="catalog-section-imports",
    ),
    path(
        "systems/<uuid:row_id>/workspace/",
        views.SystemWorkspaceView.as_view(),
        name="catalog-system-workspace",
    ),
    path("articles/", views.ArticleCollectionView.as_view(), name="catalog-article-list"),
    path(
        "articles/<uuid:row_id>/",
        views.ArticleDetailView.as_view(),
        name="catalog-article-detail",
    ),
    path(
        "articles/<uuid:row_id>/review/",
        views.ArticleReviewView.as_view(),
        name="catalog-article-review",
    ),
    path("glazing/", views.BeadCollectionView.as_view(), name="catalog-bead-list"),
    path(
        "glazing/<uuid:row_id>/",
        views.BeadDetailView.as_view(),
        name="catalog-bead-detail",
    ),
    path(
        "glazing/<uuid:row_id>/review/",
        views.BeadReviewView.as_view(),
        name="catalog-bead-review",
    ),
    path("hardware-kits/", views.KitCollectionView.as_view(), name="catalog-kit-list"),
    path(
        "hardware-kits/<uuid:row_id>/",
        views.KitDetailView.as_view(),
        name="catalog-kit-detail",
    ),
    path(
        "hardware-kits/<uuid:row_id>/review/",
        views.KitReviewView.as_view(),
        name="catalog-kit-review",
    ),
    path("evidence/", views.EvidenceCollectionView.as_view(), name="catalog-evidence-list"),
    path(
        "evidence/<uuid:row_id>/review/",
        views.EvidenceReviewView.as_view(),
        name="catalog-evidence-review",
    ),
]
