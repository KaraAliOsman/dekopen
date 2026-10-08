from django.urls import path

from portal.views import (
    PortalPaymentStatusView,
    PortalQuoteDecisionView,
    PortalQuoteFollowView,
    PortalQuotePayView,
    PortalQuoteView,
    ProjectQuoteApproveView,
    ProjectQuoteLinkRevokeView,
    ProjectQuoteLinkUpdateView,
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
        "projects/<uuid:project_id>/quote-links/<uuid:approval_id>/",
        ProjectQuoteLinkUpdateView.as_view(),
        name="project-quote-link-update",
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
    path(
        "portal/quotes/<str:token>/follow/",
        PortalQuoteFollowView.as_view(),
        name="portal-quote-follow",
    ),
    path(
        "portal/quotes/<str:token>/pay/",
        PortalQuotePayView.as_view(),
        name="portal-quote-pay",
    ),
    path(
        "portal/payments/<str:flow_token>/",
        PortalPaymentStatusView.as_view(),
        name="portal-payment-status",
    ),
]
