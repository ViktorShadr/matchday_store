from typing import List

from orders.models import Order, OrderItem
from orders.repositories.interfaces import IOrderRepository


class OrderRepository(IOrderRepository):
    """Реализация репозитория для работы с заказами."""

    def create_order(self, **kwargs) -> Order:
        """Создать заказ."""
        return Order.objects.create(**kwargs)

    def bulk_create_order_items(self, order_items: List[OrderItem]) -> None:
        """Массовое создание элементов заказа."""
        OrderItem.objects.bulk_create(order_items)
