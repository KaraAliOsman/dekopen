"""Project and position routes."""

from django.urls import path

from projects.views import (
    ClientView,
    ClientsView,
    FlowPaymentConfirmView,
    ProjectCollectionReminderSendView,
    ProjectCollectionReminderView,
    OrganizationBrandingLogoView,
    OrganizationBrandingView,
    ProjectCloneView,
    ProjectPaymentIntegrationView,
    ProjectPaymentLinkRecoverView,
    ProjectPaymentLinksView,
    ProjectCreditNoteAccessView,
    ProjectCreditNoteDteEnvioView,
    ProjectCreditNoteDteView,
    ProjectCreditNotesView,
    ProjectInvoiceAccessView,
    ProjectInvoiceDteView,
    ProjectInvoicesView,
    ProjectPaymentReceiptView,
    ProjectPaymentsView,
    ProjectPaymentView,
    ProjectPositionsView,
    ProjectSuccessorView,
    ProjectResetPricingView,
    ProjectView,
    ProjectsView,
    QuotationsView,
    PositionDesignAlternativesView,
    PositionDesignAssistView,
    PositionMeasurementConfirmView,
    PositionMeasurementResolveView,
    PositionMoveView,
    PositionView,
    SiiCafsView,
    SiiCertificateView,
    ProjectInvoiceDteEnvioView,
)
from projects.extras_api import (
    OrganizationExtrasConfigView,
    ProjectServicesView,
)
from projects.options import DesignOptionsView

urlpatterns = [
    path("projects/design-options/<uuid:system_id>/", DesignOptionsView.as_view()),
    path("projects/flow/confirm/<uuid:link_id>/", FlowPaymentConfirmView.as_view()),
    path("organization/branding/", OrganizationBrandingView.as_view()),
    path("organization/branding/logo/", OrganizationBrandingLogoView.as_view()),
    path("organization/extras-config/", OrganizationExtrasConfigView.as_view()),
    path(
        "projects/<uuid:project_id>/services/",
        ProjectServicesView.as_view(),
    ),
    path("projects/payment-integration/", ProjectPaymentIntegrationView.as_view()),
    path("clients/", ClientsView.as_view()),
    path("clients/<uuid:client_id>/", ClientView.as_view()),
    path("projects/", ProjectsView.as_view()),
    path("quotations/", QuotationsView.as_view()),
    path("projects/<uuid:project_id>/", ProjectView.as_view()),
    path("projects/<uuid:project_id>/clone/", ProjectCloneView.as_view()),
    path("projects/<uuid:project_id>/successor/", ProjectSuccessorView.as_view()),
    path("projects/<uuid:project_id>/reset-pricing/", ProjectResetPricingView.as_view()),
    path("projects/<uuid:project_id>/positions/", ProjectPositionsView.as_view()),
    path("projects/<uuid:project_id>/payments/", ProjectPaymentsView.as_view()),
    path(
        "projects/<uuid:project_id>/payments/<uuid:payment_id>/",
        ProjectPaymentView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/payments/<uuid:payment_id>/receipt/",
        ProjectPaymentReceiptView.as_view(),
    ),
    path("projects/<uuid:project_id>/invoices/", ProjectInvoicesView.as_view()),
    path(
        "projects/<uuid:project_id>/invoices/<uuid:invoice_id>/",
        ProjectInvoiceAccessView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/invoices/<uuid:invoice_id>/credit-note/",
        ProjectCreditNotesView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/invoices/<uuid:invoice_id>/dte/",
        ProjectInvoiceDteView.as_view(),
    ),
    path("sii/cafs/", SiiCafsView.as_view()),
    path("sii/certificate/", SiiCertificateView.as_view()),
    path(
        "projects/<uuid:project_id>/invoices/<uuid:invoice_id>/dte-envio/",
        ProjectInvoiceDteEnvioView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/credit-notes/<uuid:credit_note_id>/",
        ProjectCreditNoteAccessView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/invoices/<uuid:invoice_id>/credit-note-dte/",
        ProjectCreditNoteDteView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/credit-notes/<uuid:credit_note_id>/dte-envio/",
        ProjectCreditNoteDteEnvioView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/payment-links/",
        ProjectPaymentLinksView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/payment-links/<uuid:link_id>/recover/",
        ProjectPaymentLinkRecoverView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/collection-reminder/",
        ProjectCollectionReminderView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/collection-reminder/send/",
        ProjectCollectionReminderSendView.as_view(),
    ),
    path(
        "projects/<uuid:project_id>/positions/measurement-resolve/",
        PositionMeasurementResolveView.as_view(),
    ),
    path("positions/<uuid:position_id>/", PositionView.as_view()),
    path("positions/<uuid:position_id>/move/", PositionMoveView.as_view()),
    path(
        "positions/<uuid:position_id>/measurement-confirm/",
        PositionMeasurementConfirmView.as_view(),
    ),
    path(
        "positions/<uuid:position_id>/design-assist/",
        PositionDesignAssistView.as_view(),
    ),
    path(
        "positions/<uuid:position_id>/design-alternatives/",
        PositionDesignAlternativesView.as_view(),
    ),
]
