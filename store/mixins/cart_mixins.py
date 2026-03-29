from store.services.cart_service import CartService


class CartContextMixin:
    """
    Mixin для добавления информации о корзине в контекст шаблона.
    """
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Получаем корзину для текущего запроса (авторизованного или анонимного)
        cart = CartService.get_or_create_cart(self.request)
        context['cart_count'] = cart.total_items
            
        return context
