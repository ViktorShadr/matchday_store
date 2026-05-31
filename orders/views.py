from django.contrib import messages
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import FormView, TemplateView
from django_ratelimit.decorators import ratelimit

from analytics.metrika import build_checkout_event, build_purchase_event, is_metrika_enabled, queue_ecommerce_event
from config.rate_limits import setting_rate
from orders.application import CheckoutContext, CheckoutSessionService
from orders.application.order_status_policy import OrderStatusPolicy
from orders.forms import CheckoutForm
from orders.models import Order, OrderItem
from orders.services import (
    CheckoutError,
    CheckoutService,
    OrderAutoCancellationService,
    OrderCancellationError,
    OrderCancellationService,
)
from store.application import CartContextResolver
from store.mixins.cart_mixins import CartContextMixin
from store.services.cart_service import CartService

# Глобальный экземпляр для обратной совместимости
checkout_service = CheckoutService()
cart_service = CartService()
cart_context_resolver = CartContextResolver()

GUEST_ORDER_STATUS_LABELS = {
    "new": "Новый",
    "processing": "В обработке",
    "ready": "Готов к выдаче",
    "issued": "Выдан",
    "cancelled": "Отменен",
}


@method_decorator(
    ratelimit(
        key="ip",
        rate=setting_rate("RATELIMIT_CHECKOUT_IP_RATE"),
        method="POST",
        block=False,
    ),
    name="dispatch",
)
@method_decorator(
    ratelimit(
        key="user_or_ip",
        rate=setting_rate("RATELIMIT_CHECKOUT_USER_RATE"),
        method="POST",
        block=False,
    ),
    name="dispatch",
)
class CheckoutView(CartContextMixin, FormView):
    """Страница оформления заказа для MVP-сценария самовывоза."""

    template_name = "orders/checkout.html"
    form_class = CheckoutForm
    checkout_session_service = CheckoutSessionService()

    def dispatch(self, request, *args, **kwargs):
        """Не допускать оформление с пустой корзиной."""
        if request.method == "POST" and getattr(request, "limited", False):
            messages.error(request, "Слишком много попыток оформления заказа. Повторите чуть позже.")
            return redirect(reverse("orders:checkout"))

        cart_context = cart_context_resolver.resolve_request(request)
        cart_summary = cart_service.get_cart_summary(cart_context)
        if not cart_summary["items"]:
            if request.method == "POST":
                submitted_token = (request.POST.get("checkout_token") or "").strip()
                processed_order = self.checkout_session_service.get_processed_order_for_token(request, submitted_token)
                if processed_order:
                    return redirect(reverse("orders:checkout_success", kwargs={"pk": processed_order.pk}))

            messages.warning(request, "Корзина пуста. Добавьте товары перед оформлением заказа.")
            return redirect("store:cart")
        self.cart_summary = cart_summary
        self.cart_context = cart_context
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Подставить данные пользователя в форму."""
        user = self.request.user
        if not user.is_authenticated:
            return {}

        return {
            "recipient_name": f"{user.first_name} {user.last_name}".strip() or user.email,
            "email": user.email,
            "phone": user.phone or "",
        }

    def get_form_kwargs(self):
        """Передать пользователя в форму, чтобы email checkout был email аккаунта."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user if self.request.user.is_authenticated else None
        return kwargs

    def get_context_data(self, **kwargs):
        """Сформировать контекст страницы оформления."""
        context = super().get_context_data(**kwargs)
        context.update(self.cart_summary)
        context["checkout_token"] = self.checkout_session_service.get_or_create_checkout_token(self.request)
        context["pickup_location"] = self.checkout_session_service.build_pickup_location()
        if is_metrika_enabled():
            metrika_event = build_checkout_event(
                self.cart_summary.get("items", []),
                total_price=self.cart_summary.get("total_price"),
            )
            if metrika_event:
                context["metrika_page_events"] = [metrika_event]
        return context

    def form_valid(self, form):
        """Создать заказ из корзины."""
        session_token = self.checkout_session_service.get_or_create_checkout_token(self.request)
        submitted_token = (self.request.POST.get("checkout_token") or session_token).strip()

        processed_order = self.checkout_session_service.get_processed_order_for_token(self.request, submitted_token)
        if processed_order:
            return redirect(reverse("orders:checkout_success", kwargs={"pk": processed_order.pk}))

        if submitted_token != session_token:
            form.add_error(None, "Сессия оформления устарела. Обновите страницу и попробуйте снова.")
            return self.form_invalid(form)

        try:
            order = checkout_service.create_order_from_cart(
                CheckoutContext(
                    user=self.request.user if self.request.user.is_authenticated else None,
                    cart_context=self.cart_context,
                ),
                form.cleaned_data,
                checkout_token=submitted_token,
            )
        except CheckoutError as exc:
            # Корзина могла измениться в checkout-сервисе (например, недоступные позиции удалены).
            self.cart_summary = cart_service.get_cart_summary(self.cart_context)
            if not self.cart_summary["items"]:
                messages.warning(self.request, str(exc))
                return redirect("store:cart")
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        if is_metrika_enabled():
            order_items = list(order.items.select_related("product_variant__product__category").order_by("pk"))
            metrika_event = build_purchase_event(order, order_items)
            if metrika_event:
                queue_ecommerce_event(self.request, metrika_event)

        self.checkout_session_service.mark_checkout_processed(self.request, submitted_token, order.pk)
        return redirect(reverse("orders:checkout_success", kwargs={"pk": order.pk}))


class CheckoutSuccessView(CartContextMixin, TemplateView):
    """Подтверждение успешно оформленного заказа."""

    template_name = "orders/checkout_success.html"

    def get_context_data(self, **kwargs):
        """Вернуть оформленный заказ текущего пользователя."""
        context = super().get_context_data(**kwargs)
        try:
            order = Order.objects.prefetch_related(
                Prefetch(
                    "items",
                    queryset=OrderItem.objects.select_related("product_variant__product__category").order_by("pk"),
                )
            ).get(pk=self.kwargs["pk"])
        except Order.DoesNotExist as exc:
            raise Http404 from exc

        if not CheckoutSessionService().can_access_order(self.request, order):
            raise Http404

        order_items = list(order.items.all())
        context["order"] = order
        context["order_items"] = order_items
        context["pickup_location"] = CheckoutSessionService.build_pickup_location()
        return context


class GuestOrderAccessMixin:
    """Поиск гостевого заказа строго по защищённому токену."""

    cancellation_service = OrderCancellationService()

    def get_guest_order(self):
        token = (self.kwargs.get("token") or "").strip()
        if not token:
            raise Http404

        queryset = Order.objects.filter(user__isnull=True).prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related("product_variant__product__category").order_by("pk"),
            )
        )
        return get_object_or_404(queryset, guest_manage_token=token)


class GuestOrderDetailView(GuestOrderAccessMixin, CartContextMixin, TemplateView):
    """Страница просмотра гостевого заказа по защищённому токену."""

    template_name = "orders/guest_order_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.order = self.get_guest_order()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_key = OrderStatusPolicy.get_status_key(self.order)
        context["order"] = self.order
        context["order_items"] = list(self.order.items.all())
        context["status_label"] = GUEST_ORDER_STATUS_LABELS[status_key]
        context["payment_status_label"] = self.order.get_payment_status_display()
        context["can_cancel"] = OrderCancellationService.can_be_cancelled(self.order)
        if self.order.delivery_method == Order.DeliveryMethod.PICKUP:
            context["pickup_location"] = CheckoutSessionService.build_pickup_location()
            context["pickup_deadline"] = OrderAutoCancellationService.get_pickup_deadline(self.order)
        return context


class GuestOrderCancelView(GuestOrderAccessMixin, View):
    """Отмена гостевого заказа по защищённому токену."""

    def post(self, request, *args, **kwargs):
        order = self.get_guest_order()
        if not OrderCancellationService.can_be_cancelled(order):
            messages.error(request, "Этот заказ уже нельзя отменить.")
            return redirect("orders:guest_order_detail", token=order.guest_manage_token)

        try:
            self.cancellation_service.cancel_order(order_id=order.pk)
        except OrderCancellationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Заказ успешно отменен.")
        return redirect("orders:guest_order_detail", token=order.guest_manage_token)
