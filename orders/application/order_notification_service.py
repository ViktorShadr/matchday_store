import logging

from django.db import transaction

from config.email_delivery import build_email_delivery_log_extra
from orders.models import Order, OrderNotificationLog
from orders.notification_logs import OrderNotificationLogService
from orders.tasks import send_order_notification, send_staff_new_order_notification

logger = logging.getLogger(__name__)


class OrderNotificationService:
    """Прикладной сервис уведомлений по ключевым событиям заказа."""

    @staticmethod
    def _get_order_for_log(order_id: int) -> Order | None:
        try:
            return Order.objects.only("id", "email", "status", "payment_status", "fulfillment_status").get(pk=order_id)
        except Order.DoesNotExist:
            logger.warning(
                "order.notification_enqueue_skipped_order_not_found",
                extra=build_email_delivery_log_extra(
                    event="order.notification_enqueue_skipped_order_not_found",
                    order_id=order_id,
                ),
            )
            return None

    @staticmethod
    def _store_task_id(notification_log: OrderNotificationLog | None, task_result) -> None:
        if notification_log is None:
            return
        task_id = getattr(task_result, "id", None)
        if not task_id:
            return
        notification_log.task_id = str(task_id)
        notification_log.save(update_fields=["task_id", "updated_at"])

    @staticmethod
    def enqueue(order_id: int, event_key: str, *, triggered_by=None) -> bool:
        order = OrderNotificationService._get_order_for_log(order_id)
        notification_log = None
        if order is not None:
            notification_log = OrderNotificationLogService.create_pending(
                order=order,
                event_key=event_key,
                triggered_by=triggered_by,
            )

        try:
            if notification_log is None:
                task_result = send_order_notification.delay(order_id, event_key)
            else:
                task_result = send_order_notification.delay(
                    order_id,
                    event_key,
                    notification_log_id=notification_log.pk,
                )
                OrderNotificationService._store_task_id(notification_log, task_result)
            return True
        except Exception as exc:
            OrderNotificationLogService.mark_failed(notification_log, exc)
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
    def resolve_manual_resend_event_key(order: Order) -> str:
        latest_notification = (
            order.notification_logs.filter(notification_type__in=OrderNotificationLog.NotificationType.values)
            .order_by("-created_at", "-id")
            .first()
        )
        if latest_notification is not None:
            return latest_notification.notification_type

        if order.status == Order.Status.CANCELLED or order.fulfillment_status == Order.FulfillmentStatus.CANCELLED:
            return OrderNotificationLog.NotificationType.CANCELLED
        if order.fulfillment_status == Order.FulfillmentStatus.RESERVED:
            return OrderNotificationLog.NotificationType.READY
        if order.payment_status == Order.PaymentStatus.SUCCEEDED:
            return OrderNotificationLog.NotificationType.PAID
        return OrderNotificationLog.NotificationType.CREATED

    @classmethod
    def enqueue_manual_resend(cls, order: Order, *, triggered_by) -> bool:
        event_key = cls.resolve_manual_resend_event_key(order)
        return cls.enqueue(order.pk, event_key, triggered_by=triggered_by)

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
