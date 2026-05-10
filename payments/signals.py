from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from payments.application.payment_sync_context import is_payment_signal_sync_suppressed
from payments.models import Payment
from payments.services import PaymentStatusSyncService


@receiver(post_save, sender=Payment)
def sync_order_payment_status_on_save(sender, instance, **kwargs):
    """
    Fallback-синхронизация для прямых ORM/admin изменений Payment.

    Бизнес-сценарии должны идти через PaymentWorkflowService, где signal-sync
    подавляется и синхронизация вызывается явно один раз.
    """
    if is_payment_signal_sync_suppressed():
        return
    PaymentStatusSyncService.sync_order_payment_status(instance.order)


@receiver(post_delete, sender=Payment)
def sync_order_payment_status_on_delete(sender, instance, **kwargs):
    """
    Fallback-синхронизация для прямого удаления Payment через ORM/admin.
    """
    if is_payment_signal_sync_suppressed():
        return
    PaymentStatusSyncService.sync_order_payment_status(instance.order)
