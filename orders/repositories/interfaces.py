from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Optional
from django.db.models import QuerySet

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

    @abstractmethod
    def get_order_by_pk(self, pk: int) -> Optional[Order]:
        """Получить заказ по первичному ключу."""
        pass


class IPaymentRepository(ABC):
    """Абстрактный репозиторий для работы с платежами."""

    @abstractmethod
    def create_payment(self, **kwargs) -> Payment:
        """Создать платеж."""
        pass
