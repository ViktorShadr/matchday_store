from django.urls import path

from orders.views import CheckoutSuccessView, CheckoutView, GuestOrderCancelView, GuestOrderDetailView

app_name = "orders"

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("checkout/success/<int:pk>/", CheckoutSuccessView.as_view(), name="checkout_success"),
    path("orders/guest/<str:token>/", GuestOrderDetailView.as_view(), name="guest_order_detail"),
    path("orders/guest/<str:token>/cancel/", GuestOrderCancelView.as_view(), name="guest_order_cancel"),
]
