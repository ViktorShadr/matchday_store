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
from store.mixins.cart_mixins import CartContextMixin


class CustomLoginView(CartContextMixin, LoginView):
    """
    Представление входа в систему.

    Переопределяет стандартное представление входа для сохранения
    session_key перед авторизацией, что необходимо для корректного
    слияния корзин анонимного пользователя с корзиной авторизованного.
    """

    template_name = "login.html"
    form_class = UserLoginForm

    def form_valid(self, form):
        """
        Обрабатывает валидную форму входа.

        Сохраняет старый session_key перед авторизацией для последующего
        слияния корзин.

        Args:
            form: Форма входа

        Returns:
            HttpResponse: Результат стандартной авторизации
        """
        # Сохраняем старый session_key перед авторизацией
        old_session_key = self.request.session.session_key
        if old_session_key:
            self.request.session["_pre_login_session_key"] = old_session_key
            self.request.session.modified = True

        # Выполняем стандартную авторизацию
        return super().form_valid(form)


class CustomLogoutView(LogoutView):
    """
    Представление выхода из системы.

    Перенаправляет пользователя на главную страницу после выхода.
    """

    next_page = reverse_lazy("store:base")


class CustomRegistrationView(CartContextMixin, CreateView):
    """
    Представление регистрации нового пользователя.

    Создает новый профиль пользователя, выполняет автоматический вход
    и отправляет приветственное письмо. Также объединяет корзину анонимного
    пользователя с корзиной нового пользователя.
    """

    template_name = "registration.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("users:login")

    def form_valid(self, form):
        """
        Обрабатывает валидную форму регистрации.

        Сохраняет пользователя, выполняет вход, отправляет письмо,
        объединяет корзины.

        Args:
            form: Форма регистрации

        Returns:
            HttpResponse: Редирект на страницу входа
        """
        user = form.save()
        self.object = user

        # Сохраняем старый session_key перед авторизацией
        old_session_key = self.request.session.session_key
        if old_session_key:
            self.request.session["_pre_login_session_key"] = old_session_key
            self.request.session.modified = True

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
    """
    Представление детальной страницы профиля пользователя.

    Показывает полную информацию о профиле пользователя.
    Пользователь может видеть только свой профиль, если он не администратор.
    """

    model = User
    template_name = "profile_detail.html"
    context_object_name = "profile_user"

    def get_object(self, queryset=None):
        """
        Получить объект профиля для отображения.

        Args:
            queryset: QuerySet для поиска (опционально)

        Returns:
            User: Объект пользователя

        Raises:
            PermissionDenied: Если пользователь пытается посмотреть чужой профиль
        """
        obj = super().get_object(queryset)
        if obj.pk != self.request.user.pk and not self.request.user.is_staff:
            raise PermissionDenied("Можно просматривать только свой профиль")
        return obj


class ProfileList(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Представление списка всех пользователей (только для персонала).

    Отображает полный список пользователей. Доступно только сотрудникам.
    """

    model = User
    template_name = "profile_list.html"
    context_object_name = "users"
    raise_exception = True

    def test_func(self):
        """
        Проверяет доступ пользователя к представлению.

        Returns:
            bool: True если пользователь - сотрудник, False иначе
        """
        return self.request.user.is_staff


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """
    Представление редактирования профиля пользователя.

    Позволяет пользователю редактировать информацию своего профиля,
    включая возможность удаления аватара.
    """

    model = User
    form_class = UserProfileForm
    template_name = "profile_form.html"

    def get_object(self, queryset=None):
        """
        Получить объект профиля для редактирования.

        Returns:
            User: Текущий пользователь
        """
        return self.request.user

    def get_success_url(self):
        """
        Возвращает URL для перенаправления после успешного сохранения.

        Returns:
            str: URL страницы профиля
        """
        return reverse_lazy("users:profile_detail", kwargs={"pk": self.request.user.pk})

    def form_valid(self, form):
        """
        Обрабатывает валидную форму редактирования.

        Сохраняет изменения профиля и обрабатывает удаление аватара.

        Args:
            form: Форма редактирования профиля

        Returns:
            HttpResponse: Редирект на страницу профиля
        """
        if self.request.POST.get("clear_avatar"):
            self.request.user.avatar.delete(save=False)
            self.request.user.avatar = None
        return super().form_valid(form)


class ProfileDeleteView(LoginRequiredMixin, FormView):
    """
    Представление удаления профиля пользователя.

    Требует подтверждение пароля для удаления аккаунта.
    """

    form_class = ProfileDeleteConfirmForm
    template_name = "profile_confirm_delete.html"
    success_url = reverse_lazy("store:base")

    def form_valid(self, form):
        """
        Обрабатывает валидную форму подтверждения удаления.

        Проверяет пароль и удаляет профиль пользователя.

        Args:
            form: Форма подтверждения удаления

        Returns:
            HttpResponse: Редирект на главную страницу
        """
        password = form.cleaned_data.get("password")
        user = self.request.user

        if not user.check_password(password):
            form.add_error("password", "Неверный пароль")
            return self.form_invalid(form)

        user.delete()
        return super().form_valid(form)
