from payments.application.payment_sync_context import suppress_payment_signal_sync
from payments.models import Payment
from payments.services import PaymentStatusSyncService


class PaymentWorkflowService:
    """
    Явный application workflow для бизнес-сценариев изменения платежей.

    Workflow является основным механизмом синхронизации `Order.payment_status`.
    Signals остаются fallback для admin/direct ORM изменений, поэтому workflow
    подавляет signal-sync и сам вызывает синхронизацию ровно один раз.
    """

    @staticmethod
    def sync_order_payment_status(order):
        return PaymentStatusSyncService.sync_order_payment_status(order)

    @classmethod
    def create_payment(cls, **kwargs) -> Payment:
        with suppress_payment_signal_sync():
            payment = Payment.objects.create(**kwargs)
        cls.sync_order_payment_status(payment.order)
        return payment

    @classmethod
    def save_payment(cls, payment: Payment, update_fields=None) -> Payment:
        with suppress_payment_signal_sync():
            if update_fields is None:
                payment.save()
            else:
                payment.save(update_fields=update_fields)
        cls.sync_order_payment_status(payment.order)
        return payment

    @classmethod
    def delete_payment(cls, payment: Payment) -> None:
        order = payment.order
        with suppress_payment_signal_sync():
            payment.delete()
        cls.sync_order_payment_status(order)
