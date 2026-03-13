import os

from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView, UpdateView, DeleteView

from users.forms import UserLoginForm, UserRegistrationForm, UserProfileForm
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
        return super().form_valid(form)

# TODO: Не отправляются письма

    def send_welcome_email(self, user_email):
        subject = "Добро пожаловать в наш магазин"
        message = "Спасибо, что зарегистрировались в SkySport!"
        recipient_list = [user_email]
        try:
            send_mail(subject, message, from_email=os.getenv("DEFAULT_FROM_EMAIL"), recipient_list=recipient_list)
        except Exception as e:
            print(f"Ошибка отправки email: {e}")


class ProfileDetailView(LoginRequiredMixin, TemplateView):
    template_name = "profile_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = "profile_form.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse_lazy("users:profile_detail", kwargs={"pk": self.request.user.pk})


class ProfileDeleteView(LoginRequiredMixin, DeleteView):
    model = User
    template_name = "profile_confirm_delete.html"
    success_url = reverse_lazy("catalog:index")

    def get_object(self, queryset=None):
        return self.request.user
