from django.urls import path

from purchasing.views import (
    PurchasingOrdersIndexView,
    PurchasingSuppliersView,
    CancelOrderView,
    ConfirmBatchView,
    PurchasingVersionsView,
    PurchasingVersionView,
    RequirementAllocationView,
    SendOrderView,
    SupplierEligibilityView,
)

urlpatterns = [
    path("versions/", PurchasingVersionsView.as_view(), name="purchasing-versions"),
    path(
        "versions/<uuid:version_id>/",
        PurchasingVersionView.as_view(),
        name="purchasing-version",
    ),
    path(
        "versions/<uuid:version_id>/eligibilities/",
        SupplierEligibilityView.as_view(),
        name="purchasing-eligibility",
    ),
    path(
        "versions/<uuid:version_id>/confirm/",
        ConfirmBatchView.as_view(),
        name="purchasing-confirm",
    ),
    path(
        "requirements/<uuid:requirement_id>/allocation/",
        RequirementAllocationView.as_view(),
        name="purchasing-allocation",
    ),
    path(
        "orders/<uuid:order_id>/send/",
        SendOrderView.as_view(),
        name="purchasing-send",
    ),
    path(
        "orders/<uuid:order_id>/cancel/",
        CancelOrderView.as_view(),
        name="purchasing-cancel",
    ),
    path(
        "orders/",
        PurchasingOrdersIndexView.as_view(),
        name="purchasing-orders-index",
    ),
    path(
        "suppliers/",
        PurchasingSuppliersView.as_view(),
        name="purchasing-suppliers",
    ),
]
