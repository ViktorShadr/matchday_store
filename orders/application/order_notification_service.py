import logging

from django.db import transaction

from orders.tasks import send_order_notification, send_order_notification_sync

logger = logging.getLogger(__name__)


class OrderNotificationService:
    """Прикладной сервис уведомлений по ключевым событиям заказа."""

    @staticmethod
    def send_with_fallback(order_id: int, event_key: str) -> bool:
        try:
            send_order_notification.delay(order_id, event_key)
            return True
        except Exception:
            logger.exception(
                "Ошибка постановки задачи уведомления %s для заказа %s, используем sync fallback",
                event_key,
                order_id,
            )
            return send_order_notification_sync(order_id, event_key)

    @classmethod
    def schedule(cls, order_id: int, event_key: str) -> None:
        transaction.on_commit(lambda: cls.send_with_fallback(order_id, event_key))

    @classmethod
    def schedule_created(cls, order_id: int) -> None:
        cls.schedule(order_id, "created")

    @classmethod
    def schedule_cancelled(cls, order_id: int) -> None:
        cls.schedule(order_id, "cancelled")

    @classmethod
    def schedule_ready(cls, order_id: int) -> None:
        cls.schedule(order_id, "ready")

    @classmethod
    def schedule_paid(cls, order_id: int) -> None:
        cls.schedule(order_id, "paid")
