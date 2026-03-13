from django.urls import path

from users.views import (
    CustomLoginView,
    CustomLogoutView,
    CustomRegistrationView,
    ProfileDetailView,
    ProfileUpdateView,
    ProfileDeleteView,
)

app_name = "users"

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path("registration/", CustomRegistrationView.as_view(), name="registration"),
    path("profile/<int:pk>/", ProfileDetailView.as_view(), name="profile_detail"),
    path("profile/edit/", ProfileUpdateView.as_view(), name="profile_edit"),
    path("profile/delete/", ProfileDeleteView.as_view(), name="profile_delete"),
]
