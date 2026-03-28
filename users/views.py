from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from config.celery import send_welcome_email
from users.forms import UserLoginForm, UserProfileForm, UserRegistrationForm, ProfileDeleteConfirmForm
from users.models import User


class CustomLoginView(LoginView):
    template_name = "login.html"
    form_class = UserLoginForm


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy("store:base")


class CustomRegistrationView(CreateView):
    template_name = "registration.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("users:login")

    def form_valid(self, form):
        user = form.save()
        self.object = user
        login(self.request, user)
        # Отправка приветственного письма через Celery с обработкой ошибок
        try:
            send_welcome_email.delay(user.email)
        except Exception as e:
            # Логируем ошибку, но не прерываем регистрацию
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при отправке приветственного письма пользователю {user.email}: {e}")
        return HttpResponseRedirect(self.get_success_url())


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = User
    template_name = "profile_detail.html"
    context_object_name = "user"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.pk != self.request.user.pk and not self.request.user.is_staff:
            raise PermissionDenied("Можно просматривать только свой профиль")
        return obj


class ProfileList(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = User
    template_name = "profile_list.html"
    context_object_name = "users"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = "profile_form.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse_lazy("users:profile_detail", kwargs={"pk": self.request.user.pk})

    def form_valid(self, form):
        if self.request.POST.get("clear_avatar"):
            self.request.user.avatar.delete(save=False)
            self.request.user.avatar = None
        return super().form_valid(form)


class ProfileDeleteView(LoginRequiredMixin, FormView):
    form_class = ProfileDeleteConfirmForm
    template_name = "profile_confirm_delete.html"
    success_url = reverse_lazy("main_page:base")

    def form_valid(self, form):
        password = form.cleaned_data.get("password")
        user = self.request.user

        if not user.check_password(password):
            form.add_error("password", "Неверный пароль")
            return self.form_invalid(form)

        user.delete()
        return super().form_valid(form)
