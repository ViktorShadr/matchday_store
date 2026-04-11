from store.services.cart_service import CartService

# Глобальный экземпляр для обратной совместимости
cart_service = CartService()


class CartContextMixin:
    """
    Миксин для добавления информации о корзине в контекст шаблона.

    Автоматически добавляет в контекст количество товаров в корзине
    для текущего пользователя или сессии.

    Context:
        cart_count (int): Количество товаров в корзине
    """

    def get_context_data(self, **kwargs):
        """
        Формирует контекст для шаблона.

        Returns:
            dict: Контекст с информацией о корзине
        """
        context = super().get_context_data(**kwargs)

        # Получаем корзину для текущего запроса (авторизованного или анонимного)
        cart = cart_service.get_or_create_cart(self.request)
        context["cart_count"] = cart.total_items

        return context
