from django.urls import path

from store.views import MainView

app_name = "store"

urlpatterns = [
    path("", MainView.as_view(), name="base"),
]
