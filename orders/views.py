from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView
from django_ratelimit.decorators import ratelimit

from config.rate_limits import setting_rate
from orders.application import CheckoutContext, CheckoutSessionService
from orders.forms import CheckoutForm
from orders.models import Order
from orders.services import CheckoutError, CheckoutService
from store.application import CartContextResolver

# Глобальный экземпляр для обратной совместимости
checkout_service = CheckoutService()
from store.mixins.cart_mixins import CartContextMixin
from store.services.cart_service import CartService

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()
cart_context_resolver = CartContextResolver()


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
class CheckoutView(LoginRequiredMixin, CartContextMixin, FormView):
    """Страница оформления заказа для MVP-сценария самовывоза."""

    template_name = "orders/checkout.html"
    form_class = CheckoutForm
    checkout_session_service = CheckoutSessionService()

    def dispatch(self, request, *args, **kwargs):
        """Не допускать оформление с пустой корзиной."""
        if not request.user.is_authenticated:
            messages.info(request, "Чтобы оформить заказ, войдите в аккаунт или зарегистрируйтесь.")
            return self.handle_no_permission()

        if request.method == "POST" and getattr(request, "limited", False):
            messages.error(request, "Слишком много попыток оформления заказа. Повторите чуть позже.")
            return redirect(reverse("orders:checkout"))

        if not request.user.is_email_confirmed:
            messages.warning(
                request,
                "Подтвердите email в личном кабинете перед оформлением заказа.",
            )
            return redirect(reverse("users:profile_detail", kwargs={"pk": request.user.pk}))

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
        return {
            "recipient_name": f"{user.first_name} {user.last_name}".strip() or user.email,
            "email": user.email,
            "phone": user.phone or "",
        }

    def get_form_kwargs(self):
        """Передать пользователя в форму, чтобы email checkout был email аккаунта."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Сформировать контекст страницы оформления."""
        context = super().get_context_data(**kwargs)
        context.update(self.cart_summary)
        context["checkout_token"] = self.checkout_session_service.get_or_create_checkout_token(self.request)
        context["pickup_location"] = self.checkout_session_service.build_pickup_location()
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
                CheckoutContext(user=self.request.user, cart_context=self.cart_context),
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

        self.checkout_session_service.mark_checkout_processed(self.request, submitted_token, order.pk)
        return redirect(reverse("orders:checkout_success", kwargs={"pk": order.pk}))


class CheckoutSuccessView(LoginRequiredMixin, CartContextMixin, TemplateView):
    """Подтверждение успешно оформленного заказа."""

    template_name = "orders/checkout_success.html"

    def get_context_data(self, **kwargs):
        """Вернуть оформленный заказ текущего пользователя."""
        context = super().get_context_data(**kwargs)
        try:
            order = Order.objects.prefetch_related("items").get(pk=self.kwargs["pk"], user=self.request.user)
        except Order.DoesNotExist as exc:
            raise Http404 from exc

        context["order"] = order
        context["order_items"] = order.items.order_by("pk")
        context["pickup_location"] = CheckoutSessionService.build_pickup_location()
        return context
