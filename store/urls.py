from django.urls import path

from store.views import MainView

app_name = "main_page"

urlpatterns = [
    path("", MainView.as_view(), name="base"),
]
