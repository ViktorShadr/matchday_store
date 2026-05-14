import logging

from django.db import transaction

from support.tasks import (
    send_support_request_notification,
    send_support_request_notification_sync,
)

logger = logging.getLogger(__name__)


class SupportNotificationService:
    """Прикладной сервис уведомлений по обращениям в поддержку."""

    @staticmethod
    def send_with_fallback(support_request_id: int) -> bool:
        try:
            send_support_request_notification.delay(support_request_id)
            return True
        except Exception:
            logger.exception(
                (
                    "Ошибка постановки задачи уведомления поддержки %s, "
                    "используем sync fallback"
                ),
                support_request_id,
                extra={
                    "event": "support_notification_dispatch_failed",
                    "support_request_id": support_request_id,
                },
            )
            return send_support_request_notification_sync(support_request_id)

    @classmethod
    def schedule(cls, support_request_id: int) -> None:
        transaction.on_commit(
            lambda: cls.send_with_fallback(support_request_id)
        )
