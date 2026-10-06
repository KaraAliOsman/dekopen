from django.urls import path

from mail.views import MailPreviewsView, MailStatusView

urlpatterns = [
    path("status/", MailStatusView.as_view()),
    path("dev-previews/", MailPreviewsView.as_view()),
]
