from payments.models import Payment
from payments.services import PaymentStatusSyncService


class PaymentWorkflowService:
    """Явный application workflow для изменения платежей и синхронизации заказа."""

    @staticmethod
    def sync_order_payment_status(order):
        return PaymentStatusSyncService.sync_order_payment_status(order)

    @classmethod
    def create_payment(cls, **kwargs) -> Payment:
        payment = Payment.objects.create(**kwargs)
        cls.sync_order_payment_status(payment.order)
        return payment

    @classmethod
    def save_payment(cls, payment: Payment, update_fields=None) -> Payment:
        if update_fields is None:
            payment.save()
        else:
            payment.save(update_fields=update_fields)
        cls.sync_order_payment_status(payment.order)
        return payment

    @classmethod
    def delete_payment(cls, payment: Payment) -> None:
        order = payment.order
        payment.delete()
        cls.sync_order_payment_status(order)
