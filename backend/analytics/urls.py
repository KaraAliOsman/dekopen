from django.urls import path

from analytics.views import (
    AnalyticsExportView,
    AnalyticsMarginBreakdownView,
    AnalyticsOverviewView,
    OperationalSummaryView,
    TodayQueueView,
)

urlpatterns = [
    path("summary/", OperationalSummaryView.as_view(), name="analytics-summary"),
    path("today/", TodayQueueView.as_view(), name="analytics-today"),
    path("overview/", AnalyticsOverviewView.as_view(), name="analytics-overview"),
    path(
        "margin-breakdown/",
        AnalyticsMarginBreakdownView.as_view(),
        name="analytics-margin-breakdown",
    ),
    path("export/", AnalyticsExportView.as_view(), name="analytics-export"),
]
