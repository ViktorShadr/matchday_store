from django.urls import path

from users.views import (
    CustomLoginView,
    CustomLogoutView,
    CustomPasswordResetCompleteView,
    CustomPasswordResetConfirmView,
    CustomPasswordResetDoneView,
    CustomPasswordResetView,
    CustomRegistrationView,
    EmailConfirmationView,
    ProfileDeleteView,
    ProfileDetailView,
    ProfileList,
    ProfileUpdateView,
    ResendOwnConfirmationEmailView,
    UserOrderCancelView,
    UserOrderDetailView,
    UserOrderListView,
)

app_name = "users"

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path("password-reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        CustomPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("password-reset/complete/", CustomPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("registration/", CustomRegistrationView.as_view(), name="registration"),
    path("confirm-email/<str:token>/", EmailConfirmationView.as_view(), name="confirm_email"),
    path("profile/resend-confirmation/", ResendOwnConfirmationEmailView.as_view(), name="resend_confirmation"),
    path("profile/<int:pk>/", ProfileDetailView.as_view(), name="profile_detail"),
    path("profile/edit/", ProfileUpdateView.as_view(), name="profile_edit"),
    path("profile/delete/", ProfileDeleteView.as_view(), name="profile_delete"),
    path("orders/", UserOrderListView.as_view(), name="order_list"),
    path("orders/<int:pk>/", UserOrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:pk>/cancel/", UserOrderCancelView.as_view(), name="order_cancel"),
    path("profile_list/", ProfileList.as_view(), name="profile_list"),
]
