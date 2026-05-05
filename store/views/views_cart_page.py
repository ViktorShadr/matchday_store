from django.views.generic import TemplateView

from store.application import CartContextResolver
from store.mixins.cart_mixins import CartContextMixin
from store.services.cart_service import CartService

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()
cart_context_resolver = CartContextResolver()
from store.services import CartDisplayService


class CartView(CartContextMixin, TemplateView):
    """
    Страница корзины.

    Отображает все товары в корзине с возможностью изменения количества
    и удаления товаров.
    """

    template_name = "main_page/cart.html"

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
        context = super().get_context_data(**kwargs)

        cart_context = cart_context_resolver.resolve_request(self.request)
        cart_summary = cart_service.get_cart_summary(cart_context)
        context.update(cart_summary)

        # Подготовленные данные для шаблона
        context["items"] = CartDisplayService.prepare_cart_items(cart_summary.get("items", []))

        return context
