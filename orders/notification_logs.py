from __future__ import annotations

import re

from django.db import IntegrityError, transaction
from django.db.models import F

from config.logging_utils import _sanitize_string
from orders.models import Order, OrderNotificationLog

GUEST_ORDER_TOKEN_PATH_RE = re.compile(r"(/orders/guest/)[^/\s?]+")


class OrderNotificationLogService:
    """Helper for order notification outbox records."""

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
        recipient_type: str = OrderNotificationLog.RecipientType.CUSTOMER,
        triggered_by=None,
        task_id: str | None = None,
        recipient_email: str = "",
        recipient_list_snapshot: list[str] | None = None,
        subject: str = "",
        message: str = "",
    ) -> OrderNotificationLog:
        return OrderNotificationLog.objects.create(
            order=order,
            notification_type=event_key,
            event_key=event_key,
            recipient_type=recipient_type,
            recipient_email=recipient_email or order.email or "",
            recipient_list_snapshot=recipient_list_snapshot
            or ([recipient_email or order.email] if recipient_email or order.email else []),
            subject=subject,
            message=message,
            status=OrderNotificationLog.Status.PENDING,
            triggered_by=triggered_by if getattr(triggered_by, "is_authenticated", False) else None,
            task_id=task_id or None,
        )

    @classmethod
    def find_outbox(
        cls,
        *,
        order: Order,
        event_key: str,
        recipient_type: str,
    ) -> OrderNotificationLog | None:
        idempotency_key = OrderNotificationLog.build_idempotency_key(
            order_id=order.pk,
            event_key=event_key,
            recipient_type=recipient_type,
        )
        notification_log = OrderNotificationLog.objects.filter(idempotency_key=idempotency_key).first()
        if notification_log is not None:
            return notification_log

        queryset = OrderNotificationLog.objects.filter(
            order=order,
            event_key=event_key,
            recipient_type=recipient_type,
        )
        notification_log = (
            queryset.filter(status=OrderNotificationLog.Status.SENT).order_by("-sent_at", "-created_at", "-id").first()
        )
        if notification_log is None:
            notification_log = queryset.order_by("-created_at", "-id").first()
        if notification_log is None:
            notification_log = (
                OrderNotificationLog.objects.filter(
                    order=order,
                    notification_type=event_key,
                    recipient_type=recipient_type,
                )
                .order_by("-created_at", "-id")
                .first()
            )
        return notification_log

    @classmethod
    def get_or_create_outbox(
        cls,
        *,
        order: Order,
        event_key: str,
        recipient_type: str,
        triggered_by=None,
        task_id: str | None = None,
        recipient_email: str = "",
        recipient_list_snapshot: list[str] | None = None,
        subject: str = "",
        message: str = "",
    ) -> OrderNotificationLog:
        idempotency_key = OrderNotificationLog.build_idempotency_key(
            order_id=order.pk,
            event_key=event_key,
            recipient_type=recipient_type,
        )
        notification_log = cls.find_outbox(order=order, event_key=event_key, recipient_type=recipient_type)
        if notification_log is not None:
            update_fields: list[str] = []
            if not notification_log.idempotency_key:
                notification_log.idempotency_key = idempotency_key
                update_fields.append("idempotency_key")
            if notification_log.event_key != event_key:
                notification_log.event_key = event_key
                update_fields.append("event_key")
            if notification_log.notification_type != event_key:
                notification_log.notification_type = event_key
                update_fields.append("notification_type")
            if notification_log.recipient_type != recipient_type:
                notification_log.recipient_type = recipient_type
                update_fields.append("recipient_type")
            authenticated_trigger = triggered_by if getattr(triggered_by, "is_authenticated", False) else None
            if authenticated_trigger is not None and notification_log.triggered_by_id != authenticated_trigger.pk:
                notification_log.triggered_by = authenticated_trigger
                update_fields.append("triggered_by")
            if task_id and notification_log.task_id != task_id:
                notification_log.task_id = task_id
                update_fields.append("task_id")
            if update_fields:
                update_fields.append("updated_at")
                try:
                    notification_log.save(update_fields=update_fields)
                except IntegrityError:
                    notification_log = OrderNotificationLog.objects.get(idempotency_key=idempotency_key)
            return notification_log

        try:
            return OrderNotificationLog.objects.create(
                order=order,
                notification_type=event_key,
                event_key=event_key,
                recipient_type=recipient_type,
                recipient_email=recipient_email or "",
                recipient_list_snapshot=recipient_list_snapshot or [],
                subject=subject,
                message=message,
                status=OrderNotificationLog.Status.PENDING,
                triggered_by=triggered_by if getattr(triggered_by, "is_authenticated", False) else None,
                task_id=task_id or None,
                idempotency_key=idempotency_key,
            )
        except IntegrityError:
            return OrderNotificationLog.objects.get(idempotency_key=idempotency_key)

    @classmethod
    def get_by_id(cls, notification_log_id: int) -> OrderNotificationLog | None:
        try:
            return OrderNotificationLog.objects.select_related("order", "order__user").get(pk=notification_log_id)
        except OrderNotificationLog.DoesNotExist:
            return None

    @classmethod
    def prepare_attempt(
        cls,
        *,
        order: Order,
        event_key: str,
        recipient_type: str = OrderNotificationLog.RecipientType.CUSTOMER,
        notification_log_id: int | None = None,
        task=None,
    ) -> OrderNotificationLog:
        task_id = cls.task_id_from_task(task)
        if notification_log_id:
            try:
                notification_log = OrderNotificationLog.objects.get(pk=notification_log_id, order=order)
            except OrderNotificationLog.DoesNotExist:
                notification_log = cls.get_or_create_outbox(
                    order=order,
                    event_key=event_key,
                    recipient_type=recipient_type,
                    task_id=task_id,
                    recipient_email=order.email or "",
                    recipient_list_snapshot=[order.email] if order.email else [],
                )
            else:
                if notification_log.status != OrderNotificationLog.Status.SENT:
                    notification_log.notification_type = event_key
                    notification_log.event_key = event_key
                    notification_log.recipient_type = recipient_type
                    if recipient_type == OrderNotificationLog.RecipientType.CUSTOMER:
                        notification_log.recipient_email = order.email or ""
                        notification_log.recipient_list_snapshot = [order.email] if order.email else []
                    notification_log.save(
                        update_fields=[
                            "notification_type",
                            "event_key",
                            "recipient_type",
                            "recipient_email",
                            "recipient_list_snapshot",
                            "updated_at",
                        ]
                    )
                    notification_log.mark_pending(task_id=task_id)
            return notification_log

        return cls.get_or_create_outbox(
            order=order,
            event_key=event_key,
            recipient_type=recipient_type,
            task_id=task_id,
            recipient_email=order.email or "",
            recipient_list_snapshot=[order.email] if order.email else [],
        )

    @staticmethod
    def update_snapshot(
        notification_log: OrderNotificationLog,
        *,
        recipient_email: str | None = None,
        recipient_list_snapshot: list[str] | None = None,
        subject: str | None = None,
        message: str | None = None,
        triggered_by=None,
    ) -> None:
        update_fields: list[str] = []
        if recipient_email is not None and notification_log.recipient_email != recipient_email:
            notification_log.recipient_email = recipient_email
            update_fields.append("recipient_email")
        if recipient_list_snapshot is not None and notification_log.recipient_list_snapshot != recipient_list_snapshot:
            notification_log.recipient_list_snapshot = recipient_list_snapshot
            update_fields.append("recipient_list_snapshot")
        if subject is not None and notification_log.subject != subject:
            notification_log.subject = subject
            update_fields.append("subject")
        if message is not None and notification_log.message != message:
            notification_log.message = message
            update_fields.append("message")
        authenticated_trigger = triggered_by if getattr(triggered_by, "is_authenticated", False) else None
        if authenticated_trigger is not None and notification_log.triggered_by_id != authenticated_trigger.pk:
            notification_log.triggered_by = authenticated_trigger
            update_fields.append("triggered_by")
        if update_fields:
            update_fields.append("updated_at")
            notification_log.save(update_fields=update_fields)

    @classmethod
    def claim_for_sending(
        cls,
        notification_log_id: int,
        *,
        task=None,
    ) -> tuple[OrderNotificationLog | None, bool, str]:
        task_id = cls.task_id_from_task(task)
        with transaction.atomic():
            try:
                notification_log = OrderNotificationLog.objects.select_for_update().get(pk=notification_log_id)
            except OrderNotificationLog.DoesNotExist:
                return None, False, "missing"

            if notification_log.status == OrderNotificationLog.Status.SENT:
                return notification_log, False, "already_sent"
            if notification_log.status == OrderNotificationLog.Status.SENDING:
                return notification_log, False, "already_sending"

            notification_log.status = OrderNotificationLog.Status.SENDING
            notification_log.last_error = None
            notification_log.error_message = None
            notification_log.sent_at = None
            if task_id:
                notification_log.task_id = task_id
            notification_log.save(
                update_fields=[
                    "status",
                    "last_error",
                    "error_message",
                    "sent_at",
                    "task_id",
                    "updated_at",
                ]
            )
            OrderNotificationLog.objects.filter(pk=notification_log.pk).update(attempts_count=F("attempts_count") + 1)
            notification_log.refresh_from_db()
            return notification_log, True, "claimed"

    @staticmethod
    def mark_failed(notification_log: OrderNotificationLog | None, error: Exception | str | None) -> None:
        if notification_log is None:
            return
        notification_log.mark_failed(OrderNotificationLogService.sanitize_error_message(error))
