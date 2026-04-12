from django.urls import path

from users.views import (
    CustomLoginView,
    CustomLogoutView,
    CustomRegistrationView,
    ProfileDetailView,
    ProfileUpdateView,
    ProfileDeleteView,
    ProfileList,
    UserOrderListView,
    UserOrderDetailView,
    UserOrderCancelView,
    EmailConfirmationView,
)

app_name = "users"

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path("registration/", CustomRegistrationView.as_view(), name="registration"),
    path("confirm-email/<str:token>/", EmailConfirmationView.as_view(), name="confirm_email"),
    path("profile/<int:pk>/", ProfileDetailView.as_view(), name="profile_detail"),
    path("profile/edit/", ProfileUpdateView.as_view(), name="profile_edit"),
    path("profile/delete/", ProfileDeleteView.as_view(), name="profile_delete"),
    path("orders/", UserOrderListView.as_view(), name="order_list"),
    path("orders/<int:pk>/", UserOrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:pk>/cancel/", UserOrderCancelView.as_view(), name="order_cancel"),
    path("profile_list/", ProfileList.as_view(), name="profile_list"),
]
