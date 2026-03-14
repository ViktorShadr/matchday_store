import os

from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from users.forms import UserLoginForm, UserProfileForm, UserRegistrationForm, ProfileDeleteConfirmForm
from users.models import User


class CustomLoginView(LoginView):
    template_name = "login.html"
    form_class = UserLoginForm


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy("main_page:base")


class CustomRegistrationView(CreateView):
    template_name = "registration.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("users:login")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        self.send_welcome_email(user.email)
        return HttpResponseRedirect(self.get_success_url())

    # TODO: Не отправляются письма

    def send_welcome_email(self, user_email):
        subject = "Добро пожаловать в наш магазин"
        message = "Спасибо, что зарегистрировались в Shinnik Fan Shop!"
        recipient_list = [user_email]
        try:
            send_mail(subject, message, from_email=os.getenv("DEFAULT_FROM_EMAIL"), recipient_list=recipient_list)
        except Exception as e:
            print(f"Ошибка отправки email: {e}")


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


class ProfileDeleteView(LoginRequiredMixin, FormView):
    form_class = ProfileDeleteConfirmForm
    template_name = "profile_confirm_delete.html"
    success_url = reverse_lazy("catalog:index")

    def form_valid(self, form):
        password = form.cleaned_data.get("password")
        user = self.request.user

        if not user.check_password(password):
            form.add_error("password", "Неверный пароль")
            return self.form_invalid(form)

        user.delete()
        return super().form_valid(form)
