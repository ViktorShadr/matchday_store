from orders.repositories.interfaces import IPaymentRepository
from payments.models import Payment


class PaymentRepository(IPaymentRepository):
    """Реализация репозитория для работы с платежами."""

    def get_payment_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        """Получить платеж по idempotency_key."""
        try:
            return Payment.objects.select_related("order").get(idempotency_key=idempotency_key)
        except Payment.DoesNotExist:
            return None
