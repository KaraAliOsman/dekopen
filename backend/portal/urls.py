from django.urls import path

from portal.views import (
    PortalQuoteDecisionView,
    PortalQuoteView,
    ProjectQuoteApproveView,
    ProjectQuoteLinkRevokeView,
    ProjectQuoteLinkView,
)

urlpatterns = [
    path(
        "projects/<uuid:project_id>/quote-link/",
        ProjectQuoteLinkView.as_view(),
        name="project-quote-link",
    ),
    path(
        "projects/<uuid:project_id>/approve/",
        ProjectQuoteApproveView.as_view(),
        name="project-quote-approve",
    ),
    path(
        "projects/<uuid:project_id>/quote-links/<uuid:approval_id>/revoke/",
        ProjectQuoteLinkRevokeView.as_view(),
        name="project-quote-link-revoke",
    ),
    path("portal/quotes/<str:token>/", PortalQuoteView.as_view(), name="portal-quote"),
    path(
        "portal/quotes/<str:token>/decide/",
        PortalQuoteDecisionView.as_view(),
        name="portal-quote-decide",
    ),
]
