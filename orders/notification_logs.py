from __future__ import annotations

import re

from config.logging_utils import _sanitize_string
from orders.models import Order, OrderNotificationLog

GUEST_ORDER_TOKEN_PATH_RE = re.compile(r"(/orders/guest/)[^/\s?]+")


class OrderNotificationLogService:
    """Small helper for customer order notification attempt records."""

    ERROR_MESSAGE_MAX_LENGTH = 240

    @classmethod
    def sanitize_error_message(cls, error: Exception | str | None) -> str:
        raw_message = str(error or "").strip()
        if not raw_message and isinstance(error, Exception):
            raw_message = error.__class__.__name__
        if not raw_message:
            raw_message = "Ошибка отправки уведомления."

        sanitized = _sanitize_string(raw_message)
        sanitized = GUEST_ORDER_TOKEN_PATH_RE.sub(r"\1***", sanitized)
        sanitized = " ".join(sanitized.split())
        if len(sanitized) > cls.ERROR_MESSAGE_MAX_LENGTH:
            return f"{sanitized[: cls.ERROR_MESSAGE_MAX_LENGTH - 3]}..."
        return sanitized

    @staticmethod
    def task_id_from_task(task) -> str | None:
        request = getattr(task, "request", None)
        task_id = getattr(request, "id", None) if request is not None else None
        return str(task_id) if task_id else None

    @classmethod
    def create_pending(
        cls,
        *,
        order: Order,
        event_key: str,
        triggered_by=None,
        task_id: str | None = None,
    ) -> OrderNotificationLog:
        return OrderNotificationLog.objects.create(
            order=order,
            notification_type=event_key,
            recipient_email=order.email or "",
            status=OrderNotificationLog.Status.PENDING,
            triggered_by=triggered_by if getattr(triggered_by, "is_authenticated", False) else None,
            task_id=task_id or None,
        )

    @classmethod
    def prepare_attempt(
        cls,
        *,
        order: Order,
        event_key: str,
        notification_log_id: int | None = None,
        task=None,
    ) -> OrderNotificationLog:
        task_id = cls.task_id_from_task(task)
        if notification_log_id:
            try:
                notification_log = OrderNotificationLog.objects.get(pk=notification_log_id, order=order)
            except OrderNotificationLog.DoesNotExist:
                notification_log = cls.create_pending(order=order, event_key=event_key, task_id=task_id)
            else:
                notification_log.notification_type = event_key
                notification_log.recipient_email = order.email or ""
                notification_log.save(update_fields=["notification_type", "recipient_email", "updated_at"])
                notification_log.mark_pending(task_id=task_id)
            return notification_log

        return cls.create_pending(order=order, event_key=event_key, task_id=task_id)

    @staticmethod
    def mark_failed(notification_log: OrderNotificationLog | None, error: Exception | str | None) -> None:
        if notification_log is None:
            return
        notification_log.mark_failed(OrderNotificationLogService.sanitize_error_message(error))
