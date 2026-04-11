from payments.models import Payment
from orders.repositories.interfaces import IPaymentRepository


class PaymentRepository(IPaymentRepository):
    """Реализация репозитория для работы с платежами."""

    def create_payment(self, **kwargs) -> Payment:
        """Создать платеж."""
        return Payment.objects.create(**kwargs)
