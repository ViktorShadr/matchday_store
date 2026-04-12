import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View

from config.celery import send_welcome_email
from orders.models import Order
from orders.services import OrderCancellationService, OrderCancellationError
from users.forms import UserLoginForm, UserProfileForm, UserRegistrationForm, ProfileDeleteConfirmForm
from users.models import User
from store.mixins.cart_mixins import CartContextMixin
from users.tasks import send_confirmation_email

logger = logging.getLogger(__name__)


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

    Создает нового пользователя, генерирует токен подтверждения email
    и отправляет письмо с подтверждением.
    """

    template_name = "registration.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("users:login")

    def form_valid(self, form):
        """
        Обрабатывает валидную форму регистрации.

        Сохраняет пользователя, генерирует токен подтверждения
        и отправляет письмо с подтверждением.

        Args:
            form: Форма регистрации

        Returns:
            HttpResponse: Редирект на страницу входа
        """
        user = form.save()
        self.object = user

        # Генерируем токен подтверждения email
        confirmation_token = user.generate_email_token()

        # Отправка письма с подтверждением через Celery с обработкой ошибок
        try:
            send_confirmation_email.delay(user.email, confirmation_token)
        except Exception as e:
            logger.error(f"Ошибка при отправке письма с подтверждением пользователю {user.email}: {e}")

        messages.success(
            self.request,
            "Регистрация успешна! На ваш email отправлено письмо с ссылкой для подтверждения аккаунта."
        )
        return HttpResponseRedirect(self.get_success_url())


class ProfileDetailView(LoginRequiredMixin, DetailView):
    """
    Представление детальной страницы профиля пользователя.

    Показывает полную информацию о профиле пользователя.
    Пользователь может видеть только свой профиль.
    Полный доступ к чужим профилям есть только у суперпользователя.
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
        if obj.pk != self.request.user.pk and not self.request.user.is_superuser:
            raise PermissionDenied("Можно просматривать только свой профиль")
        return obj


class ProfileList(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Представление списка всех пользователей (только для суперпользователя).

    Отображает полный список пользователей.
    """

    model = User
    template_name = "profile_list.html"
    context_object_name = "users"
    raise_exception = True

    def test_func(self):
        """
        Проверяет доступ пользователя к представлению.

        Returns:
            bool: True если пользователь - суперпользователь, False иначе
        """
        return self.request.user.is_superuser


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
    Удаление запрещено, если у пользователя уже есть заказы.
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

        if user.orders.exists():
            form.add_error(None, "Нельзя удалить профиль: у вас есть оформленные заказы.")
            return self.form_invalid(form)

        user.delete()
        return super().form_valid(form)


class UserOrderListView(LoginRequiredMixin, CartContextMixin, ListView):
    """
    Представление списка заказов текущего пользователя.

    Отображает историю заказов пользователя с основной сводной информацией.
    """

    model = Order
    template_name = "user_orders.html"
    context_object_name = "orders"

    def get_queryset(self):
        """
        Получить список заказов текущего пользователя.

        Returns:
            QuerySet: Заказы пользователя с аннотацией количества товаров
        """
        return (
            Order.objects.filter(user=self.request.user)
            .annotate(total_items=Coalesce(Sum("items__quantity"), 0))
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        """Добавить признак доступности отмены заказа в список."""
        context = super().get_context_data(**kwargs)
        for order in context["orders"]:
            order.can_cancel = OrderCancellationService.can_be_cancelled(order)
        return context


class UserOrderCancelView(LoginRequiredMixin, View):
    """Отмена заказа текущего пользователя через доменный сервис."""

    cancellation_service = OrderCancellationService()

    def post(self, request, pk):
        try:
            self.cancellation_service.cancel_order(order_id=pk, user_id=request.user.id)
        except OrderCancellationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Заказ успешно отменен.")
        return redirect("users:order_list")

#TODO: Добавить детализацию заказа
class UserOrderDetailView(LoginRequiredMixin, CartContextMixin, DetailView):
    pass


class EmailConfirmationView(View):
    """
    Представление для подтверждения email пользователя.

    Проверяет токен подтверждения и активирует аккаунт пользователя.
    """

    def get(self, request, token):
        """
        Обрабатывает GET запрос с токеном подтверждения.

        Args:
            request: HTTP запрос
            token (str): Токен подтверждения email

        Returns:
            HttpResponse: Редирект на страницу входа с сообщением об успехе или ошибке
        """
        try:
            user = User.objects.get(email_token=token)
            user.confirm_email()
            try:
                send_welcome_email.delay(user.email)
            except Exception as e:
                logger.error(f"Ошибка при отправке приветственного письма пользователю {user.email}: {e}")
            messages.success(request, "Ваш email успешно подтвержден! Теперь вы можете войти в аккаунт.")
            return redirect("users:login")
        except User.DoesNotExist:
            messages.error(request, "Недействительная ссылка подтверждения или срок действия ссылки истек.")
            return redirect("users:login")
