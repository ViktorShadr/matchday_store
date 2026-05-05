from django.urls import path

from orders.views import CheckoutSuccessView, CheckoutView

app_name = "orders"

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("checkout/success/<int:pk>/", CheckoutSuccessView.as_view(), name="checkout_success"),
]
