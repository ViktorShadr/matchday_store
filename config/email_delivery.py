from typing import Final


class NotificationDeliveryError(Exception):
    """Ошибка доставки email-уведомления, которую Celery может безопасно ретраить."""


EMAIL_TASK_MAX_RETRIES: Final = 5
EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS: Final = 300

EMAIL_TASK_AUTORETRY_KWARGS: Final = {
    "bind": True,
    "autoretry_for": (NotificationDeliveryError,),
    "retry_backoff": True,
    "retry_backoff_max": EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS,
    "retry_jitter": True,
    "retry_kwargs": {"max_retries": EMAIL_TASK_MAX_RETRIES},
}
