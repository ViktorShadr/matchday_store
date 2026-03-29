from django.views.generic import TemplateView

from store.mixins.cart_mixins import CartContextMixin
from store.services.cart_service import CartService
from store.services import CartDisplayService


class CartView(CartContextMixin, TemplateView):
    """
    Страница корзины.
    
    Отображает все товары в корзине с возможностью изменения количества
    и удаления товаров.
    """
    template_name = "main_page/cart.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        cart_summary = CartService.get_cart_summary(self.request)
        context.update(cart_summary)
        
        # Подготовленные данные для шаблона
        context["items_prepared"] = CartDisplayService.prepare_cart_items(
            cart_summary.get("items", [])
        )
        
        return context
