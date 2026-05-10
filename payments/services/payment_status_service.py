from orders.models import Order
from payments.models import Payment


class PaymentStatusSyncService:
    """
    Сервис синхронизации статуса платежа с заказом.

    Обеспечивает согласованность статуса оплаты между объектом платежа
    и заказом. Отмененный заказ не должен оживать из-за позднего
    прямого сохранения Payment, поэтому cancellation имеет приоритет над
    пересчетом по связанным платежам.
    """

    @staticmethod
    def resolve_order_payment_status(order: Order) -> str:
        """
        Определить статус оплаты заказа на основе его платежей.

        Логика определения:
        1. Если есть возвращенные платежи -> REFUNDED
        2. Если есть успешные платежи -> SUCCEEDED
        3. Иначе статус последнего платежа

        Args:
            order (Order): Заказ для анализа

        Returns:
            str: Определенный статус оплаты
        """
        payments = order.payments.order_by("-updated_at", "-created_at", "-pk")
        latest_payment = payments.first()

        if latest_payment is None:
            return Order.PaymentStatus.PENDING

        if payments.filter(status=Payment.Status.REFUNDED).exists():
            return Order.PaymentStatus.REFUNDED

        if payments.filter(status=Payment.Status.SUCCEEDED).exists():
            return Order.PaymentStatus.SUCCEEDED

        return latest_payment.status

    @classmethod
    def sync_order_payment_status(cls, order: Order) -> str:
        """
        Синхронизировать статус оплаты заказа.

        Определяет актуальный статус и сохраняет его в заказ,
        если изменился.

        Args:
            order (Order): Заказ для синхронизации

        Returns:
            str: Актуальный статус оплаты
        """
        if order.status == Order.Status.CANCELLED:
            payment_status = Order.PaymentStatus.CANCELLED
        else:
            payment_status = cls.resolve_order_payment_status(order)

        if order.payment_status != payment_status:
            order.payment_status = payment_status
            order.save(update_fields=["payment_status", "updated_at"])

        return payment_status
