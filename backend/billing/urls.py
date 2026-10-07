from django.urls import path

from billing.sim import FlowSimCheckoutView
from billing.views import WalletView, BillingView, FlowConfirmationView, FlowRegistrationView, FlowRefundView

from billing.commerce_views import (ChangeAbandonView,CommerceView,CheckoutView,ChangePreviewView,ChangeConfirmView,
    BillingSyncView,FlowPlanConfirmationView,RegistrationReturnView)

urlpatterns = [path('wallet/', WalletView.as_view()), path('', BillingView.as_view()),
               path('flow-sim/<str:token>/', FlowSimCheckoutView.as_view()),
               path('flow/confirm/<uuid:order_id>/', FlowConfirmationView.as_view()),
               path('flow/refund/<uuid:operation_id>/', FlowRefundView.as_view()),
               path('flow/register/<uuid:operation_id>/', FlowRegistrationView.as_view())]



urlpatterns += [path('change/abandon/',ChangeAbandonView.as_view()),path('commerce/',CommerceView.as_view()),path('checkout/',CheckoutView.as_view()),
    path('change/preview/',ChangePreviewView.as_view()),path('change/confirm/',ChangeConfirmView.as_view()),
    path('sync/',BillingSyncView.as_view()),path('flow/plan/<uuid:offer_id>/',FlowPlanConfirmationView.as_view()),
    path('flow/registration-return/<uuid:operation_id>/',RegistrationReturnView.as_view())]
