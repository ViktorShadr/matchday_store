import logging

from django.db import transaction
from django.utils import timezone

from config.email_delivery import build_email_delivery_log_extra
from support.models import SupportRequest
from support.tasks import send_support_request_notification

logger = logging.getLogger(__name__)


class SupportNotificationService:
    """Прикладной сервис уведомлений по обращениям в поддержку."""

    @staticmethod
    def enqueue(support_request_id: int) -> bool:
        try:
            send_support_request_notification.delay(support_request_id)
            return True
        except Exception as exc:
            SupportRequest.objects.filter(pk=support_request_id).update(
                email_sent=False,
                email_error="Не удалось поставить email-задачу в очередь.",
                updated_at=timezone.now(),
            )
            logger.exception(
                "Ошибка постановки email-задачи уведомления поддержки %s",
                support_request_id,
                extra=build_email_delivery_log_extra(
                    event="support_notification_dispatch_failed",
                    support_request_id=support_request_id,
                    email_type="support",
                    error_type=exc.__class__.__name__,
                ),
            )
            return False

    @classmethod
    def schedule(cls, support_request_id: int) -> None:
        transaction.on_commit(lambda: cls.enqueue(support_request_id))
