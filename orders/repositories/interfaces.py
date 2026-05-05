from abc import ABC, abstractmethod
from typing import List, Optional

from orders.models import Order, OrderItem
from payments.models import Payment


class IOrderRepository(ABC):
    """Абстрактный репозиторий для работы с заказами."""

    @abstractmethod
    def create_order(self, **kwargs) -> Order:
        """Создать заказ."""
        pass

    @abstractmethod
    def bulk_create_order_items(self, order_items: List[OrderItem]) -> None:
        """Массовое создание элементов заказа."""
        pass


class IPaymentRepository(ABC):
    """Абстрактный репозиторий для работы с платежами."""

    @abstractmethod
    def create_payment(self, **kwargs) -> Payment:
        """Создать платеж."""
        pass

    @abstractmethod
    def get_payment_by_idempotency_key(self, idempotency_key: str) -> Optional[Payment]:
        """Получить платеж по idempotency_key."""
        pass
