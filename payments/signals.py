from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from payments.models import Payment
from payments.services import PaymentStatusSyncService


@receiver(post_save, sender=Payment)
def sync_order_payment_status_on_save(sender, instance, **kwargs):
    """
    Синхронизировать статус платежа заказа при сохранении платежа.

    Args:
        sender: Класс модели (Payment)
        instance: Экземпляр платежа
        **kwargs: Дополнительные параметры сигнала
    """
    PaymentStatusSyncService.sync_order_payment_status(instance.order)


@receiver(post_delete, sender=Payment)
def sync_order_payment_status_on_delete(sender, instance, **kwargs):
    """
    Синхронизировать статус платежа заказа при удалении платежа.

    Args:
        sender: Класс модели (Payment)
        instance: Экземпляр платежа
        **kwargs: Дополнительные параметры сигнала
    """
    PaymentStatusSyncService.sync_order_payment_status(instance.order)
