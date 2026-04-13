from payments.models import Payment
from orders.repositories.interfaces import IPaymentRepository


class PaymentRepository(IPaymentRepository):
    """Реализация репозитория для работы с платежами."""

    def create_payment(self, **kwargs) -> Payment:
        """Создать платеж."""
        return Payment.objects.create(**kwargs)

    def get_payment_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        """Получить платеж по idempotency_key."""
        try:
            return Payment.objects.select_related("order").get(idempotency_key=idempotency_key)
        except Payment.DoesNotExist:
            return None
