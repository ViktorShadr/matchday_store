from abc import ABC, abstractmethod
from typing import Optional, List
from django.db.models import QuerySet

from store.models import Cart, CartItem, ProductVariant


class ICartRepository(ABC):
    """Абстрактный репозиторий для работы с корзиной."""

    @abstractmethod
    def get_or_create_cart_by_user(self, user) -> Cart:
        """Получить или создать корзину по пользователю."""
        pass

    @abstractmethod
    def get_or_create_cart_by_session(self, session_key: str) -> Cart:
        """Получить или создать корзину по сессии."""
        pass

    @abstractmethod
    def get_cart_by_session_key(self, session_key: str) -> Optional[Cart]:
        """Получить корзину по ключу сессии."""
        pass

    @abstractmethod
    def get_cart_items(self, cart: Cart) -> QuerySet[CartItem]:
        """Получить товары корзины с preload связанных данных."""
        pass

    @abstractmethod
    def get_or_create_cart_item(
        self, cart: Cart, product_variant: ProductVariant, defaults: dict
    ) -> tuple[CartItem, bool]:
        """Получить или создать элемент корзины."""
        pass

    @abstractmethod
    def update_or_create_cart_item(
        self, cart: Cart, product_variant: ProductVariant, defaults: dict
    ) -> tuple[CartItem, bool]:
        """Обновить или создать элемент корзины."""
        pass

    @abstractmethod
    def delete_cart_item(self, cart: Cart, product_variant_id: int) -> bool:
        """Удалить элемент корзины."""
        pass

    @abstractmethod
    def delete_cart_items(self, cart: Cart) -> int:
        """Удалить все элементы корзины."""
        pass

    @abstractmethod
    def delete_cart(self, cart: Cart) -> None:
        """Удалить корзину."""
        pass


class IProductVariantRepository(ABC):
    """Абстрактный репозиторий для работы с вариантами товаров."""

    @abstractmethod
    def get_variant_for_update(self, variant_id: int) -> ProductVariant:
        """Получить вариант товара с блокировкой для обновления."""
        pass

    @abstractmethod
    def get_variants_for_update(self, variant_ids: List[int]) -> QuerySet[ProductVariant]:
        """Получить варианты товаров с блокировкой для обновления."""
        pass
