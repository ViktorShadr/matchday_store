from typing import Optional

from django.db.models import QuerySet

from store.models import Cart, CartItem, ProductVariant
from store.repositories.interfaces import ICartRepository


class CartRepository(ICartRepository):
    """Реализация репозитория для работы с корзиной."""

    def get_or_create_cart_by_user(self, user) -> Cart:
        """Получить или создать корзину по пользователю."""
        cart, created = Cart.objects.get_or_create(user=user, defaults={"session_key": None})
        return cart

    def get_or_create_cart_by_session(self, session_key: str) -> Cart:
        """Получить или создать корзину по сессии."""
        cart, created = Cart.objects.get_or_create(
            session_key=session_key, user__isnull=True, defaults={"session_key": session_key}
        )
        return cart

    def get_cart_by_session_key(self, session_key: str) -> Optional[Cart]:
        """Получить корзину по ключу сессии."""
        try:
            return Cart.objects.get(session_key=session_key, user__isnull=True)
        except Cart.DoesNotExist:
            return None

    def get_cart_items(self, cart: Cart) -> QuerySet[CartItem]:
        """Получить товары корзины с preload связанных данных."""
        return cart.items.select_related("product_variant__product").all()

    def get_or_create_cart_item(
        self, cart: Cart, product_variant: ProductVariant, defaults: dict
    ) -> tuple[CartItem, bool]:
        """Получить или создать элемент корзины."""
        return CartItem.objects.get_or_create(cart=cart, product_variant=product_variant, defaults=defaults)

    def update_or_create_cart_item(
        self, cart: Cart, product_variant: ProductVariant, defaults: dict
    ) -> tuple[CartItem, bool]:
        """Обновить или создать элемент корзины."""
        return CartItem.objects.update_or_create(cart=cart, product_variant=product_variant, defaults=defaults)

    def delete_cart_item(self, cart: Cart, product_variant_id: int) -> bool:
        """Удалить элемент корзины."""
        try:
            cart_item = CartItem.objects.get(cart=cart, product_variant_id=product_variant_id)
            cart_item.delete()
            return True
        except CartItem.DoesNotExist:
            return False

    def delete_cart(self, cart: Cart) -> None:
        """Удалить корзину."""
        cart.delete()
