from django.urls import path

from ai_gateway.views import (
    AiAgentView,
    AiAskView,
    AiInvokeView,
    AiJobCollectionView,
    AiJobMessagesView,
    AiJobOutcomeView,
    AiJobRetryView,
    AiJobView,
    AiMetricsView,
)

urlpatterns = [
    path("invoke/", AiInvokeView.as_view(), name="ai-invoke"),
    path("ask/", AiAskView.as_view(), name="ai-ask"),
    path("agent/", AiAgentView.as_view(), name="ai-agent"),
    path("jobs/", AiJobCollectionView.as_view(), name="ai-jobs"),
    path("jobs/<uuid:job_id>/", AiJobView.as_view(), name="ai-job"),
    path(
        "jobs/<uuid:job_id>/messages/",
        AiJobMessagesView.as_view(),
        name="ai-job-messages",
    ),
    path(
        "jobs/<uuid:job_id>/retry/",
        AiJobRetryView.as_view(),
        name="ai-job-retry",
    ),
    path(
        "jobs/<uuid:job_id>/outcome/",
        AiJobOutcomeView.as_view(),
        name="ai-job-outcome",
    ),
    path("metrics/", AiMetricsView.as_view(), name="ai-metrics"),
]
