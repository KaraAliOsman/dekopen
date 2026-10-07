from django.urls import path

from . import views

urlpatterns = [
    path("crews/", views.FieldCrewsView.as_view()),
    path("dispatch/plan/", views.DispatchPlanView.as_view()),
    path("dispatch/schedule/", views.DispatchScheduleView.as_view()),
    path("agenda/", views.FieldAgendaView.as_view()),
    path("orders/<uuid:order_id>/", views.FieldOrderCardView.as_view()),
    path("orders/<uuid:order_id>/measurement/", views.FieldMeasurementView.as_view()),
    path("orders/<uuid:order_id>/checklist/", views.FieldChecklistView.as_view()),
    path("deliveries/<uuid:delivery_id>/load-check/", views.FieldLoadCheckView.as_view()),
    path("orders/<uuid:order_id>/incidents/", views.FieldOrderIncidentsView.as_view()),
    path("incidents/", views.FieldIncidentsView.as_view()),
    path("incidents/<uuid:incident_id>/resolve/", views.FieldIncidentResolveView.as_view()),
    path("purchase-requests/", views.FieldPurchaseRequestsView.as_view()),
    path(
        "purchase-requests/<uuid:request_id>/transition/",
        views.FieldPurchaseRequestTransitionView.as_view(),
    ),
    path("service-tickets/", views.ServiceTicketsView.as_view()),
    path("projects/<uuid:project_id>/service-tickets/", views.ProjectServiceTicketsView.as_view()),
    path("service-tickets/<uuid:ticket_id>/transition/", views.ServiceTicketTransitionView.as_view()),
    path("photos/", views.FieldPhotoView.as_view()),
]
