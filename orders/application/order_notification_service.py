import logging

from django.db import transaction

from orders.tasks import (
    send_order_notification,
    send_order_notification_sync,
    send_staff_new_order_notification,
    send_staff_new_order_notification_sync,
)

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
                extra={
                    "event": "order_notification_dispatch_failed",
                    "order_id": order_id,
                    "event_key": event_key,
                },
            )
            return send_order_notification_sync(order_id, event_key)

    @classmethod
    def schedule(cls, order_id: int, event_key: str) -> None:
        transaction.on_commit(lambda: cls.send_with_fallback(order_id, event_key))

    @staticmethod
    def send_staff_new_order_with_fallback(order_id: int) -> bool:
        try:
            send_staff_new_order_notification.delay(order_id)
            return True
        except Exception:
            logger.exception(
                "Ошибка постановки staff-задачи уведомления о новом заказе %s, используем sync fallback",
                order_id,
                extra={
                    "event": "staff_order_notification_dispatch_failed",
                    "order_id": order_id,
                },
            )
            return send_staff_new_order_notification_sync(order_id)

    @classmethod
    def schedule_staff_created(cls, order_id: int) -> None:
        transaction.on_commit(lambda: cls.send_staff_new_order_with_fallback(order_id))

    @classmethod
    def schedule_created(cls, order_id: int) -> None:
        cls.schedule(order_id, "created")
        cls.schedule_staff_created(order_id)

    @classmethod
    def schedule_cancelled(cls, order_id: int) -> None:
        cls.schedule(order_id, "cancelled")

    @classmethod
    def schedule_ready(cls, order_id: int) -> None:
        cls.schedule(order_id, "ready")

    @classmethod
    def schedule_paid(cls, order_id: int) -> None:
        cls.schedule(order_id, "paid")
