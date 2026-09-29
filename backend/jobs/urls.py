from django.urls import path

from jobs.views import JobDetailView, JobListCreateView, JobRetryView

urlpatterns = [
    path("", JobListCreateView.as_view(), name="job-list-create"),
    path("<uuid:job_id>/", JobDetailView.as_view(), name="job-detail"),
    path("<uuid:job_id>/retry/", JobRetryView.as_view(), name="job-retry"),
]
