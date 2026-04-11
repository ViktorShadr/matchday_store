from abc import ABC, abstractmethod
from typing import Dict, Any

from store.models import Cart, CartItem


class ICartService(ABC):
    """Интерфейс для сервиса работы с корзиной (ISP)."""

    @abstractmethod
    def get_or_create_cart(self, request) -> Cart:
        """Получить или создать корзину."""
        pass

    @abstractmethod
    def get_cart_summary(self, request) -> Dict[str, Any]:
        """Получить сводку по корзине."""
        pass


class ICartMutationService(ABC):
    """Интерфейс для сервиса мутации корзины (ISP)."""

    @abstractmethod
    def add_item(self, request, product_variant_id: int, quantity: int = 1) -> CartItem:
        """Добавить товар в корзину."""
        pass

    @abstractmethod
    def update_item_quantity(self, request, product_variant_id: int, quantity: int) -> CartItem:
        """Обновить количество товара в корзине."""
        pass

    @abstractmethod
    def remove_item(self, request, product_variant_id: int) -> bool:
        """Удалить товар из корзины."""
        pass

    @abstractmethod
    def clear_cart(self, request) -> Cart:
        """Очистить корзину."""
        pass


class ICheckoutService(ABC):
    """Интерфейс для сервиса оформления заказа (ISP)."""

    @abstractmethod
    def create_order_from_cart(self, request, cleaned_data: Dict[str, Any]):
        """Создать заказ из корзины."""
        pass
