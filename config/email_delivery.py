from smtplib import SMTPRecipientsRefused, SMTPResponseException
from typing import Any, Final


class NotificationDeliveryError(Exception):
    """Ошибка доставки email-уведомления, которую Celery может безопасно ретраить."""


EMAIL_TASK_MAX_RETRIES: Final = 5
EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS: Final = 300
EMAIL_TASK_QUEUE: Final = "email"

EMAIL_TASK_AUTORETRY_KWARGS: Final = {
    "bind": True,
    "queue": EMAIL_TASK_QUEUE,
    "autoretry_for": (NotificationDeliveryError,),
    "retry_backoff": True,
    "retry_backoff_max": EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS,
    "retry_jitter": True,
    "retry_kwargs": {"max_retries": EMAIL_TASK_MAX_RETRIES},
}


def is_permanent_email_delivery_error(exc: Exception) -> bool:
    """Return True when SMTP rejected the message for a non-retryable reason."""
    if isinstance(exc, SMTPRecipientsRefused):
        return True

    if isinstance(exc, SMTPResponseException):
        smtp_code = getattr(exc, "smtp_code", None)
        return isinstance(smtp_code, int) and smtp_code >= 500

    return False


def get_email_task_retry_count(task) -> int:
    request = getattr(task, "request", None)
    return int(getattr(request, "retries", 0) or 0)


def build_email_delivery_log_extra(
    *,
    task=None,
    retries: int | None = None,
    reason: str | None = None,
    error_type: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    from django.conf import settings

    request = getattr(task, "request", None)
    task_id = getattr(request, "id", None) if request is not None else None
    if retries is None:
        retries = get_email_task_retry_count(task) if task is not None else 0

    payload = {
        "queue": EMAIL_TASK_QUEUE,
        "smtp_host": getattr(settings, "EMAIL_HOST", ""),
        "email_timeout": getattr(settings, "EMAIL_TIMEOUT", None),
        "retries": retries,
        "task_id": task_id,
        **extra,
    }
    if reason:
        payload["reason"] = reason
    if error_type:
        payload["error_type"] = error_type
    return payload
