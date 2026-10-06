from django.urls import path

from analytics.views import OperationalSummaryView, TodayQueueView

urlpatterns = [
    path("summary/", OperationalSummaryView.as_view(), name="analytics-summary"),
    path("today/", TodayQueueView.as_view(), name="analytics-today"),
]
