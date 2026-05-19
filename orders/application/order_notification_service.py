import logging

from django.db import transaction

from config.email_delivery import build_email_delivery_log_extra
from orders.tasks import send_order_notification, send_staff_new_order_notification

logger = logging.getLogger(__name__)


class OrderNotificationService:
    """Прикладной сервис уведомлений по ключевым событиям заказа."""

    @staticmethod
    def enqueue(order_id: int, event_key: str) -> bool:
        try:
            send_order_notification.delay(order_id, event_key)
            return True
        except Exception as exc:
            logger.exception(
                "order.notification_enqueue_failed",
                extra=build_email_delivery_log_extra(
                    event="order.notification_enqueue_failed",
                    order_id=order_id,
                    event_key=event_key,
                    error_type=exc.__class__.__name__,
                ),
            )
            return False

    @classmethod
    def schedule(cls, order_id: int, event_key: str) -> None:
        transaction.on_commit(lambda: cls.enqueue(order_id, event_key))

    @staticmethod
    def enqueue_staff_created(order_id: int) -> bool:
        try:
            send_staff_new_order_notification.delay(order_id)
            return True
        except Exception as exc:
            logger.exception(
                "order.staff_notification_enqueue_failed",
                extra=build_email_delivery_log_extra(
                    event="order.staff_notification_enqueue_failed",
                    order_id=order_id,
                    event_key="staff_created",
                    error_type=exc.__class__.__name__,
                ),
            )
            return False

    @classmethod
    def schedule_staff_created(cls, order_id: int) -> None:
        transaction.on_commit(lambda: cls.enqueue_staff_created(order_id))

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
