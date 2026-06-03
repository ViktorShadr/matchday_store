import logging
from dataclasses import dataclass

from django.db import transaction

from config.email_delivery import build_email_delivery_log_extra
from orders.models import Order, OrderNotificationLog
from orders.notification_logs import OrderNotificationLogService
from orders.tasks import (
    STAFF_NEW_ORDER_EVENT_KEY,
    _build_order_notification_content,
    _build_staff_new_order_notification_content,
    _get_staff_order_notification_recipients,
    send_order_notification,
    send_staff_new_order_notification,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManualNotificationResendResult:
    is_enqueued: bool
    message: str
    level: str = "info"


class OrderNotificationService:
    """Прикладной сервис уведомлений по ключевым событиям заказа."""

    CUSTOMER_EVENT_KEYS = (
        OrderNotificationLog.NotificationType.CREATED,
        OrderNotificationLog.NotificationType.CANCELLED,
        OrderNotificationLog.NotificationType.READY,
        OrderNotificationLog.NotificationType.PAID,
    )
    MANUAL_RESEND_RETRYABLE_STATUSES = (
        OrderNotificationLog.Status.FAILED,
        "error",
    )
    MANUAL_RESEND_BLOCKED_STATUS_MESSAGES = {
        OrderNotificationLog.Status.SENT: "Письмо уже отправлено. Повторная отправка не требуется.",
        OrderNotificationLog.Status.PENDING: "Письмо уже ожидает отправки. Дублирующая задача не создана.",
        "queued": "Письмо уже находится в очереди. Дублирующая задача не создана.",
        OrderNotificationLog.Status.SENDING: "Письмо уже отправляется. Дублирующая задача не создана.",
    }

    @staticmethod
    def _get_order_for_log(order_id: int) -> Order | None:
        try:
            return Order.objects.select_related("user").get(pk=order_id)
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
    def _get_staff_order_for_log(order_id: int) -> Order | None:
        try:
            return Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)
        except Order.DoesNotExist:
            logger.warning(
                "order.staff_notification_enqueue_skipped_order_not_found",
                extra=build_email_delivery_log_extra(
                    event="order.staff_notification_enqueue_skipped_order_not_found",
                    order_id=order_id,
                    event_key=STAFF_NEW_ORDER_EVENT_KEY,
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
    def _log_skipped_already_sent(notification_log: OrderNotificationLog) -> None:
        event_name = (
            "order.staff_notification_skipped_already_sent"
            if notification_log.recipient_type == OrderNotificationLog.RecipientType.STAFF
            else "order.notification_skipped_already_sent"
        )
        logger.info(
            event_name,
            extra=build_email_delivery_log_extra(
                event=event_name,
                order_id=notification_log.order_id,
                event_key=notification_log.event_key,
                recipient_type=notification_log.recipient_type,
            ),
        )

    @staticmethod
    def _enqueue_log(notification_log: OrderNotificationLog) -> bool:
        if notification_log.status == OrderNotificationLog.Status.SENT:
            OrderNotificationService._log_skipped_already_sent(notification_log)
            return True
        if notification_log.status != OrderNotificationLog.Status.SENDING:
            notification_log.mark_pending()

        try:
            if notification_log.recipient_type == OrderNotificationLog.RecipientType.STAFF:
                task_result = send_staff_new_order_notification.delay(notification_log_id=notification_log.pk)
            else:
                task_result = send_order_notification.delay(notification_log_id=notification_log.pk)
            OrderNotificationService._store_task_id(notification_log, task_result)
            return True
        except Exception as exc:
            OrderNotificationLogService.mark_failed(notification_log, exc)
            event_name = (
                "order.staff_notification_enqueue_failed"
                if notification_log.recipient_type == OrderNotificationLog.RecipientType.STAFF
                else "order.notification_enqueue_failed"
            )
            logger.exception(
                event_name,
                extra=build_email_delivery_log_extra(
                    event=event_name,
                    order_id=notification_log.order_id,
                    event_key=notification_log.event_key,
                    recipient_type=notification_log.recipient_type,
                    error_type=exc.__class__.__name__,
                ),
            )
            return False

    @staticmethod
    def enqueue(order_id: int, event_key: str, *, triggered_by=None) -> bool:
        order = OrderNotificationService._get_order_for_log(order_id)
        if order is None:
            return False

        notification_log = OrderNotificationLogService.get_or_create_outbox(
            order=order,
            event_key=event_key,
            recipient_type=OrderNotificationLog.RecipientType.CUSTOMER,
            triggered_by=triggered_by,
            recipient_email=order.email or "",
            recipient_list_snapshot=[order.email] if order.email else [],
        )
        if notification_log.status == OrderNotificationLog.Status.SENT:
            OrderNotificationService._log_skipped_already_sent(notification_log)
            return True
        if not order.email:
            notification_log.mark_failed("Email получателя не указан.")
            return False

        if not notification_log.subject or not notification_log.message:
            try:
                subject, message = _build_order_notification_content(order, event_key)
            except ValueError as exc:
                OrderNotificationLogService.mark_failed(notification_log, exc)
                return False
            OrderNotificationLogService.update_snapshot(
                notification_log,
                recipient_email=order.email,
                recipient_list_snapshot=[order.email],
                subject=subject,
                message=message,
                triggered_by=triggered_by,
            )

        return OrderNotificationService._enqueue_log(notification_log)

    @classmethod
    def schedule(cls, order_id: int, event_key: str) -> None:
        transaction.on_commit(lambda: cls.enqueue(order_id, event_key))

    @staticmethod
    def resolve_manual_resend_event_key(order: Order) -> str:
        latest_notification = (
            order.notification_logs.filter(
                event_key__in=OrderNotificationService.CUSTOMER_EVENT_KEYS,
                recipient_type=OrderNotificationLog.RecipientType.CUSTOMER,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if latest_notification is not None:
            return latest_notification.event_key

        if order.status == Order.Status.CANCELLED or order.fulfillment_status == Order.FulfillmentStatus.CANCELLED:
            return OrderNotificationLog.NotificationType.CANCELLED
        if order.fulfillment_status == Order.FulfillmentStatus.RESERVED:
            return OrderNotificationLog.NotificationType.READY
        if order.payment_status == Order.PaymentStatus.SUCCEEDED:
            return OrderNotificationLog.NotificationType.PAID
        return OrderNotificationLog.NotificationType.CREATED

    @classmethod
    def get_manual_customer_notifications(cls, order: Order):
        return order.notification_logs.filter(
            event_key__in=cls.CUSTOMER_EVENT_KEYS,
            recipient_type=OrderNotificationLog.RecipientType.CUSTOMER,
        )

    @classmethod
    def get_latest_manual_customer_notification(cls, order: Order) -> OrderNotificationLog | None:
        return cls.get_manual_customer_notifications(order).order_by("-created_at", "-id").first()

    @classmethod
    def get_retryable_manual_customer_notification(cls, order: Order) -> OrderNotificationLog | None:
        return (
            cls.get_manual_customer_notifications(order)
            .filter(status__in=cls.MANUAL_RESEND_RETRYABLE_STATUSES)
            .order_by("-updated_at", "-id")
            .first()
        )

    @classmethod
    def build_manual_resend_context(cls, order: Order) -> dict[str, bool | str]:
        retryable_notification = cls.get_retryable_manual_customer_notification(order)
        if retryable_notification is not None:
            return {
                "is_available": True,
                "label": "Повторно отправить письмо",
            }

        notification_log = cls.get_latest_manual_customer_notification(order)
        if notification_log is None:
            return {
                "is_available": True,
                "label": "Повторно отправить письмо",
            }

        return {
            "is_available": False,
            "label": cls._get_manual_resend_blocked_message(notification_log),
        }

    @classmethod
    def _get_manual_resend_blocked_message(cls, notification_log: OrderNotificationLog) -> str:
        return cls.MANUAL_RESEND_BLOCKED_STATUS_MESSAGES.get(
            notification_log.status,
            f"Повторная отправка недоступна для статуса «{notification_log.get_status_display()}».",
        )

    @classmethod
    def enqueue_manual_resend(cls, order: Order, *, triggered_by) -> ManualNotificationResendResult:
        retryable_notification = cls.get_retryable_manual_customer_notification(order)
        if retryable_notification is not None:
            OrderNotificationLogService.update_snapshot(retryable_notification, triggered_by=triggered_by)
            if cls._enqueue_log(retryable_notification):
                return ManualNotificationResendResult(
                    is_enqueued=True,
                    message="Письмо поставлено в очередь на отправку.",
                )
            return ManualNotificationResendResult(
                is_enqueued=False,
                message="Не удалось поставить письмо в очередь на отправку. Проверьте настройки email.",
                level="error",
            )

        latest_notification = cls.get_latest_manual_customer_notification(order)
        if latest_notification is not None:
            return ManualNotificationResendResult(
                is_enqueued=False,
                message=cls._get_manual_resend_blocked_message(latest_notification),
                level="warning",
            )

        event_key = cls.resolve_manual_resend_event_key(order)
        if cls.enqueue(order.pk, event_key, triggered_by=triggered_by):
            return ManualNotificationResendResult(
                is_enqueued=True,
                message="Письмо поставлено в очередь на отправку.",
            )
        return ManualNotificationResendResult(
            is_enqueued=False,
            message="Не удалось поставить письмо в очередь на отправку. Проверьте настройки email.",
            level="error",
        )

    @staticmethod
    def enqueue_staff_created(order_id: int) -> bool:
        order = OrderNotificationService._get_staff_order_for_log(order_id)
        if order is None:
            return False

        recipient_list = _get_staff_order_notification_recipients()
        notification_log = OrderNotificationLogService.get_or_create_outbox(
            order=order,
            event_key=STAFF_NEW_ORDER_EVENT_KEY,
            recipient_type=OrderNotificationLog.RecipientType.STAFF,
            recipient_list_snapshot=recipient_list,
        )
        if notification_log.status == OrderNotificationLog.Status.SENT:
            OrderNotificationService._log_skipped_already_sent(notification_log)
            return True
        if not recipient_list and not notification_log.recipient_list_snapshot:
            notification_log.mark_failed("Email получателей не указан.")
            return False

        if not notification_log.subject or not notification_log.message:
            subject, message = _build_staff_new_order_notification_content(order)
            OrderNotificationLogService.update_snapshot(
                notification_log,
                recipient_list_snapshot=recipient_list or notification_log.recipient_list_snapshot,
                subject=subject,
                message=message,
            )

        return OrderNotificationService._enqueue_log(notification_log)

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
