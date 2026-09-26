from django.urls import path

from inventory.views import (
    BarAuthorityListView,
    InventoryMovementsView,
    InventoryStockView,
    OrderReceiptCreateView,
    OrderReceivingView,
    RemnantListView,
    RemnantReleaseView,
    RemnantScrapView,
)

urlpatterns = [
    path("stock/", InventoryStockView.as_view(), name="inventory-stock"),
    path("movements/", InventoryMovementsView.as_view(), name="inventory-movements"),
    path("remnants/", RemnantListView.as_view(), name="inventory-remnants"),
    path(
        "bar-authorities/",
        BarAuthorityListView.as_view(),
        name="inventory-bar-authorities",
    ),
    path(
        "remnants/<uuid:remnant_id>/scrap/",
        RemnantScrapView.as_view(),
        name="inventory-remnant-scrap",
    ),
    path(
        "remnants/<uuid:remnant_id>/release/",
        RemnantReleaseView.as_view(),
        name="inventory-remnant-release",
    ),
    path(
        "orders/<uuid:order_id>/receiving/",
        OrderReceivingView.as_view(),
        name="inventory-order-receiving",
    ),
    path(
        "orders/<uuid:order_id>/receipts/",
        OrderReceiptCreateView.as_view(),
        name="inventory-order-receipts",
    ),
]
