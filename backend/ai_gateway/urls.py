from django.urls import path

from ai_gateway.views import (
    AiActivityView,
    AiAgentView,
    AiAskView,
    AiInvokeView,
    AiJobCollectionView,
    AiJobMessagesView,
    AiJobOutcomeView,
    AiJobRetryView,
    AiJobView,
    AiMetricsView,
    AiOpsContractView,
    AiProviderCheckView,
    AiProviderStatusView,
    AiSettingsView,
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
    path("ops-contract/", AiOpsContractView.as_view(), name="ai-ops-contract"),
    # §IA3 — provider status, owner settings, connection probe, activity.
    path(
        "provider/status/",
        AiProviderStatusView.as_view(),
        name="ai-provider-status",
    ),
    path("settings/", AiSettingsView.as_view(), name="ai-settings"),
    path(
        "provider/check/",
        AiProviderCheckView.as_view(),
        name="ai-provider-check",
    ),
    path("activity/", AiActivityView.as_view(), name="ai-activity"),
]
