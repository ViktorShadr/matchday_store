from uuid import uuid4

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from orders.forms import CheckoutForm
from orders.models import Order
from orders.services import CheckoutError, CheckoutService

# Глобальный экземпляр для обратной совместимости
checkout_service = CheckoutService()
from store.mixins.cart_mixins import CartContextMixin
from store.services.cart_service import CartService

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()


class CheckoutView(LoginRequiredMixin, CartContextMixin, FormView):
    """Страница оформления заказа для MVP-сценария самовывоза."""

    template_name = "orders/checkout.html"
    form_class = CheckoutForm
    checkout_token_session_key = "_checkout_token"
    checkout_processed_session_key = "_checkout_processed"

    def _get_processed_order_for_token(self, request, submitted_token: str):
        """Вернуть уже созданный заказ для повторного submit с тем же токеном."""
        if not submitted_token:
            return None

        processed_checkout = request.session.get(self.checkout_processed_session_key) or {}
        if processed_checkout.get("token") != submitted_token:
            return None

        order_id = processed_checkout.get("order_id")
        if not order_id:
            return None

        try:
            return Order.objects.get(pk=order_id, user=request.user)
        except Order.DoesNotExist:
            return None

    def dispatch(self, request, *args, **kwargs):
        """Не допускать оформление с пустой корзиной."""
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        cart_summary = cart_service.get_cart_summary(request)
        if not cart_summary["items"]:
            if request.method == "POST":
                submitted_token = (request.POST.get("checkout_token") or "").strip()
                processed_order = self._get_processed_order_for_token(request, submitted_token)
                if processed_order:
                    return redirect(reverse("orders:checkout_success", kwargs={"pk": processed_order.pk}))

            messages.warning(request, "Корзина пуста. Добавьте товары перед оформлением заказа.")
            return redirect("main_page:cart")
        self.cart_summary = cart_summary
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Подставить данные пользователя в форму."""
        user = self.request.user
        return {
            "recipient_name": f"{user.first_name} {user.last_name}".strip() or user.email,
            "email": user.email,
            "phone": user.phone or "",
        }

    def get_context_data(self, **kwargs):
        """Сформировать контекст страницы оформления."""
        context = super().get_context_data(**kwargs)
        context.update(self.cart_summary)
        context["checkout_token"] = self._get_or_create_checkout_token()
        context["pickup_location"] = {
            "code": settings.STORE_PICKUP_LOCATION_CODE,
            "name": settings.STORE_PICKUP_LOCATION_NAME,
            "address": settings.STORE_PICKUP_ADDRESS,
            "hours": settings.STORE_PICKUP_HOURS,
            "phone": settings.STORE_PICKUP_PHONE,
        }
        return context

    def _get_or_create_checkout_token(self):
        token = self.request.session.get(self.checkout_token_session_key)
        if not token:
            token = uuid4().hex
            self.request.session[self.checkout_token_session_key] = token
            self.request.session.modified = True
        return token

    def form_valid(self, form):
        """Создать заказ из корзины."""
        session_token = self._get_or_create_checkout_token()
        submitted_token = (self.request.POST.get("checkout_token") or session_token).strip()

        processed_order = self._get_processed_order_for_token(self.request, submitted_token)
        if processed_order:
            return redirect(reverse("orders:checkout_success", kwargs={"pk": processed_order.pk}))

        if submitted_token != session_token:
            form.add_error(None, "Сессия оформления устарела. Обновите страницу и попробуйте снова.")
            return self.form_invalid(form)

        try:
            order = checkout_service.create_order_from_cart(
                self.request, form.cleaned_data, checkout_token=submitted_token
            )
        except CheckoutError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        self.request.session[self.checkout_processed_session_key] = {
            "token": submitted_token,
            "order_id": order.pk,
        }
        self.request.session.pop(self.checkout_token_session_key, None)
        self.request.session.modified = True
        return redirect(reverse("orders:checkout_success", kwargs={"pk": order.pk}))


class CheckoutSuccessView(LoginRequiredMixin, CartContextMixin, TemplateView):
    """Подтверждение успешно оформленного заказа."""

    template_name = "orders/checkout_success.html"

    def get_context_data(self, **kwargs):
        """Вернуть оформленный заказ текущего пользователя."""
        context = super().get_context_data(**kwargs)
        try:
            order = Order.objects.get(pk=self.kwargs["pk"], user=self.request.user)
        except Order.DoesNotExist as exc:
            raise Http404 from exc

        context["order"] = order
        context["pickup_location"] = {
            "name": settings.STORE_PICKUP_LOCATION_NAME,
            "address": settings.STORE_PICKUP_ADDRESS,
            "hours": settings.STORE_PICKUP_HOURS,
            "phone": settings.STORE_PICKUP_PHONE,
        }
        return context
