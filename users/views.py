import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.csrf import csrf_failure as default_csrf_failure
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View
from django_ratelimit.decorators import ratelimit

from config.email_delivery import build_email_delivery_log_extra
from config.rate_limits import setting_rate
from orders.application.checkout_session_service import CheckoutSessionService
from orders.application.order_status_policy import OrderStatusPolicy
from orders.models import Order
from orders.services import OrderCancellationError, OrderCancellationService
from store.mixins.cart_mixins import CartContextMixin
from users.application import EmailConfirmationService
from users.forms import ProfileDeleteConfirmForm, UserLoginForm, UserProfileForm, UserRegistrationForm
from users.models import User
from users.tasks import send_welcome_email

logger = logging.getLogger(__name__)

USER_ORDER_STATUS_LABELS = {
    "new": "Новый",
    "processing": "В обработке",
    "ready": "Готов к выдаче",
    "issued": "Выдан",
    "cancelled": "Отменен",
}
USER_PAYMENT_STATUS_LABELS = {
    Order.PaymentStatus.PENDING: "Ожидает оплаты",
    Order.PaymentStatus.SUCCEEDED: "Оплачен",
    Order.PaymentStatus.FAILED: "Ошибка оплаты",
    Order.PaymentStatus.CANCELLED: "Оплата отменена",
    Order.PaymentStatus.REFUNDED: "Возврат выполнен",
}


def csrf_failure(request, reason="", template_name=None):
    """UX-recovery only for resend-confirmation; default CSRF behavior elsewhere."""
    resolver_match = getattr(request, "resolver_match", None)
    is_resend_confirmation = (
        resolver_match and resolver_match.view_name == "users:resend_confirmation"
    ) or request.path == reverse("users:resend_confirmation")
    if not is_resend_confirmation:
        if template_name is None:
            return default_csrf_failure(request, reason=reason)
        return default_csrf_failure(request, reason=reason, template_name=template_name)

    messages.warning(request, "Страница устарела. Обновите страницу и повторите действие.")
    redirect_url = request.META.get("HTTP_REFERER")
    if redirect_url and url_has_allowed_host_and_scheme(
        url=redirect_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(redirect_url)
    return redirect("store:base")


def apply_user_order_status(order: Order) -> Order:
    """Подготовить витринный статус исполнения заказа для клиентских страниц."""
    status_key = OrderStatusPolicy.get_status_key(order)
    order.user_work_status_key = status_key
    order.user_work_status_label = USER_ORDER_STATUS_LABELS[status_key]
    if status_key in {"ready", "issued"}:
        order.user_work_status_tone = "success"
    elif status_key == "cancelled":
        order.user_work_status_tone = "danger"
    else:
        order.user_work_status_tone = "neutral"

    order.user_payment_status_label = USER_PAYMENT_STATUS_LABELS.get(
        order.payment_status,
        USER_PAYMENT_STATUS_LABELS[Order.PaymentStatus.PENDING],
    )
    if order.payment_status in {Order.PaymentStatus.SUCCEEDED, Order.PaymentStatus.REFUNDED}:
        order.user_payment_status_tone = "success"
    elif order.payment_status in {Order.PaymentStatus.FAILED, Order.PaymentStatus.CANCELLED}:
        order.user_payment_status_tone = "danger"
    elif order.payment_status in {Order.PaymentStatus.PENDING, Order.PaymentStatus.REQUIRES_ACTION}:
        order.user_payment_status_tone = "warning"
    else:
        order.user_payment_status_tone = "neutral"
    return order


def build_user_order_visibility_q(user) -> Q:
    visibility_q = Q(user=user)
    if user.is_email_confirmed and user.email:
        visibility_q |= Q(user__isnull=True, email__iexact=user.email)
    return visibility_q


def build_ratelimit_response(view, request, message: str, status_code: int = 429):
    messages.error(request, message)
    response = view.get(request, *view.args, **view.kwargs)
    response.status_code = status_code
    return response


@method_decorator(
    ratelimit(
        key="ip",
        rate=setting_rate("RATELIMIT_LOGIN_IP_RATE"),
        method="POST",
        block=False,
    ),
    name="dispatch",
)
@method_decorator(
    ratelimit(
        key="post:username",
        rate=setting_rate("RATELIMIT_LOGIN_CREDENTIAL_RATE"),
        method="POST",
        block=False,
    ),
    name="dispatch",
)
class CustomLoginView(CartContextMixin, LoginView):
    """
    Представление входа в систему.

    Переопределяет стандартное представление входа для сохранения
    session_key перед авторизацией, что необходимо для корректного
    слияния корзин анонимного пользователя с корзиной авторизованного.
    """

    template_name = "login.html"
    form_class = UserLoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and getattr(request, "limited", False):
            return build_ratelimit_response(
                self,
                request,
                "Слишком много попыток входа. Подождите и попробуйте снова.",
            )
        return super().dispatch(request, *args, **kwargs)

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


@method_decorator(
    ratelimit(
        key="ip",
        rate=setting_rate("RATELIMIT_REGISTRATION_IP_RATE"),
        method="POST",
        block=False,
    ),
    name="dispatch",
)
@method_decorator(
    ratelimit(
        key="post:email",
        rate=setting_rate("RATELIMIT_REGISTRATION_EMAIL_RATE"),
        method="POST",
        block=False,
    ),
    name="dispatch",
)
class CustomRegistrationView(CartContextMixin, CreateView):
    """
    Представление регистрации нового пользователя.

    Создает нового пользователя, генерирует токен подтверждения email
    и отправляет письмо с подтверждением.
    """

    template_name = "registration.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("users:login")

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and getattr(request, "limited", False):
            return build_ratelimit_response(
                self,
                request,
                "Слишком много попыток регистрации. Попробуйте позже.",
            )
        return super().dispatch(request, *args, **kwargs)

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
        send_result = {"success": False}

        with transaction.atomic():
            user = form.save()
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])
            self.object = user
            EmailConfirmationService.schedule_confirmation_for_new_user(user, send_result)

        if send_result["success"]:
            messages.success(
                self.request,
                "Регистрация успешна! Подтвердите email, чтобы видеть историю заказов, бонусы и новые акции.",
            )
        else:
            messages.warning(
                self.request,
                "Аккаунт создан, но письмо подтверждения пока не отправлено. "
                "Заказы можно оформлять без аккаунта, а письмо потребуется для истории заказов и бонусов.",
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_initial(self):
        initial = super().get_initial()
        email = (self.request.GET.get("email") or "").strip()
        if "@" in email:
            initial["email"] = email
        return initial


class ResendOwnConfirmationEmailView(LoginRequiredMixin, View):
    """Повторная отправка письма подтверждения из личного кабинета."""

    @method_decorator(
        ratelimit(
            key="ip",
            rate=setting_rate("RATELIMIT_CONFIRM_RESEND_IP_RATE"),
            method="POST",
            block=False,
        )
    )
    @method_decorator(
        ratelimit(
            key="user_or_ip",
            rate=setting_rate("RATELIMIT_CONFIRM_RESEND_USER_RATE"),
            method="POST",
            block=False,
        )
    )
    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            messages.error(request, "Слишком много запросов на повторную отправку. Попробуйте позже.")
            return redirect("users:profile_detail", pk=request.user.pk)

        user = request.user

        if user.is_email_confirmed:
            messages.info(request, "Ваша почта уже подтверждена.")
            return redirect("users:profile_detail", pk=user.pk)

        can_resend, seconds_left = EmailConfirmationService.can_resend(user)
        if not can_resend:
            messages.info(request, f"Повторная отправка будет доступна через {seconds_left} сек.")
            return redirect("users:profile_detail", pk=user.pk)

        if not EmailConfirmationService.resend_confirmation(user):
            messages.error(request, "Не удалось отправить письмо подтверждения. Попробуйте позже.")
            return redirect("users:profile_detail", pk=user.pk)

        messages.success(request, "Письмо отправлено. Проверьте почту.")
        return redirect("users:profile_detail", pk=user.pk)


class ProfileDetailView(LoginRequiredMixin, CartContextMixin, DetailView):
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

    def get_context_data(self, **kwargs):
        """Add breadcrumbs to context."""
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": "Профиль", "url": None},
        ]
        context["show_email_confirmation_prompt"] = (
            self.request.user.pk == self.object.pk and not self.request.user.is_email_confirmed
        )
        return context


class ProfileList(LoginRequiredMixin, UserPassesTestMixin, CartContextMixin, ListView):
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

    def get_context_data(self, **kwargs):
        """Add breadcrumbs to context."""
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": "Пользователи", "url": None},
        ]
        return context


class ProfileUpdateView(LoginRequiredMixin, CartContextMixin, UpdateView):
    """
    Представление редактирования профиля пользователя.

    Позволяет пользователю редактировать информацию своего профиля,
    включая возможность удаления аватара.
    """

    model = User
    form_class = UserProfileForm
    template_name = "profile_form.html"
    context_object_name = "profile_user"

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

    def get_context_data(self, **kwargs):
        """Add breadcrumbs to context."""
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": "Профиль", "url": reverse_lazy("users:profile_detail", kwargs={"pk": self.request.user.pk})},
            {"title": "Редактирование", "url": None},
        ]
        return context

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


class ProfileDeleteView(LoginRequiredMixin, CartContextMixin, FormView):
    """
    Представление удаления профиля пользователя.

    Требует подтверждение пароля для удаления аккаунта.
    Удаление запрещено, если у пользователя уже есть заказы.
    """

    form_class = ProfileDeleteConfirmForm
    template_name = "profile_confirm_delete.html"
    success_url = reverse_lazy("store:base")

    def get_context_data(self, **kwargs):
        """Add breadcrumbs to context."""
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": "Профиль", "url": reverse_lazy("users:profile_detail", kwargs={"pk": self.request.user.pk})},
            {"title": "Удаление", "url": None},
        ]
        return context

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
            Order.objects.filter(build_user_order_visibility_q(self.request.user))
            .annotate(total_items=Coalesce(Sum("items__quantity"), 0))
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        """Добавить признак доступности отмены заказа в список."""
        context = super().get_context_data(**kwargs)
        for order in context["orders"]:
            order.can_cancel = order.user_id == self.request.user.id and OrderCancellationService.can_be_cancelled(
                order
            )
            apply_user_order_status(order)
        return context


class UserOrderCancelView(LoginRequiredMixin, View):
    """Отмена заказа текущего пользователя через доменный сервис."""

    cancellation_service = OrderCancellationService()

    def post(self, request, pk):
        try:
            self.cancellation_service.cancel_order(order_id=pk, user_id=request.user.id, actor=request.user)
        except OrderCancellationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Заказ успешно отменен.")
        return redirect("users:order_list")


class UserOrderDetailView(LoginRequiredMixin, CartContextMixin, DetailView):
    """Детальная страница заказа текущего пользователя."""

    model = Order
    template_name = "user_order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.filter(build_user_order_visibility_q(self.request.user)).prefetch_related("items")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        apply_user_order_status(self.object)
        context["can_cancel"] = (
            self.object.user_id == self.request.user.id and OrderCancellationService.can_be_cancelled(self.object)
        )
        context["order_items"] = self.object.items.order_by("pk")
        if self.object.delivery_method == Order.DeliveryMethod.PICKUP:
            context["pickup_location"] = CheckoutSessionService.build_pickup_location()
        return context


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
            HttpResponse: Редирект в профиль с авто-входом или на страницу входа при ошибке
        """
        try:
            user = User.objects.get(email_token=token)
            if EmailConfirmationService.is_token_expired(user):
                User.objects.filter(pk=user.pk).update(email_token=None, email_token_created_at=None)
                messages.error(request, "Недействительная ссылка подтверждения или срок действия ссылки истек.")
                return redirect("users:login")
            user.confirm_email()
            auth_backend = getattr(user, "backend", None) or settings.AUTHENTICATION_BACKENDS[0]
            # login() ротирует CSRF-токен: формы в других вкладках могут
            # содержать устаревший token до обновления страницы.
            auth_login(request, user, backend=auth_backend)
            try:
                send_welcome_email.delay(user.email)
            except Exception as exc:
                logger.exception(
                    "Ошибка при отправке приветственного письма пользователю %s",
                    user.email,
                    extra=build_email_delivery_log_extra(
                        event="welcome_email_dispatch_failed",
                        user_id=user.id,
                        email_type="welcome",
                        error_type=exc.__class__.__name__,
                    ),
                )
            messages.success(request, "Email подтвержден. Вы автоматически вошли в аккаунт.")
            return redirect("users:profile_detail", pk=user.pk)
        except User.DoesNotExist:
            messages.error(request, "Недействительная ссылка подтверждения или срок действия ссылки истек.")
            return redirect("users:login")
