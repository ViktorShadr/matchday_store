from django.urls import path

from support.views import SupportRequestView, SupportSuccessView

app_name = "support"

urlpatterns = [
    path("", SupportRequestView.as_view(), name="request"),
    path("success/", SupportSuccessView.as_view(), name="success"),
]
