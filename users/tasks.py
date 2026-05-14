import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from config.email_delivery import (
    EMAIL_TASK_AUTORETRY_KWARGS,
    NotificationDeliveryError,
    build_email_delivery_log_extra,
)

logger = logging.getLogger(__name__)


def _log_email_delivery_failure(
    email_type: str,
    reason: str,
    exc: Exception,
    *,
    task=None,
    retries: int | None = None,
) -> None:
    logger.exception(
        "Ошибка отправки email",
        extra=build_email_delivery_log_extra(
            task=task,
            retries=retries,
            event="email_send_failed",
            email_type=email_type,
            reason=reason,
            error_type=exc.__class__.__name__,
        ),
    )


def send_welcome_email_sync(
    user_email: str,
    *,
    raise_on_error: bool = False,
    task=None,
    retries: int | None = None,
) -> bool:
    """Синхронная отправка приветственного письма пользователю."""
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        logger.error(
            "Ошибка отправки приветственного email: не настроен DEFAULT_FROM_EMAIL",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="email_default_sender_not_configured",
                email_type="welcome",
            ),
        )
        return False

    subject = "Добро пожаловать в магазин атрибутики ФК Шинник!"
    message = "Спасибо, что зарегистрировались в нашем магазине."
    recipient_list = [user_email]

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info(
            "Приветственное письмо успешно отправлено",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="welcome_email_sent",
                email_type="welcome",
            ),
        )
        return True
    except Exception as exc:
        _log_email_delivery_failure("welcome", "send_mail_failed", exc, task=task, retries=retries)
        if raise_on_error:
            raise NotificationDeliveryError("Не удалось отправить приветственное письмо") from exc
        return False


def send_confirmation_email_sync(
    user_email: str,
    confirmation_token: str,
    *,
    raise_on_error: bool = False,
    task=None,
    retries: int | None = None,
) -> bool:
    """
    Отправка письма с подтверждением email

    Args:
        user_email (str): Email пользователя
        confirmation_token (str): Токен подтверждения
    """
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        logger.error(
            "Ошибка отправки email: не настроен DEFAULT_FROM_EMAIL",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="email_default_sender_not_configured",
                email_type="confirmation",
            ),
        )
        return False

    # Формируем ссылку подтверждения
    confirmation_url = f"{settings.SITE_URL}/users/confirm-email/{confirmation_token}/"

    subject = "Подтверждение email в магазине атрибутики ФК Шинник"
    message = f"""
    Спасибо за регистрацию!

    Для активации вашего аккаунта, пожалуйста, подтвердите ваш email, перейдя по ссылке:
    {confirmation_url}

    Если вы не регистрировались на нашем сайте, просто проигнорируйте это письмо.
    """
    recipient_list = [user_email]

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info(
            "Письмо с подтверждением отправлено",
            extra=build_email_delivery_log_extra(
                task=task,
                retries=retries,
                event="confirmation_email_sent",
                email_type="confirmation",
            ),
        )
        return True
    except Exception as exc:
        _log_email_delivery_failure("confirmation", "send_mail_failed", exc, task=task, retries=retries)
        if raise_on_error:
            raise NotificationDeliveryError("Не удалось отправить письмо с подтверждением email") from exc
        return False


@shared_task(**EMAIL_TASK_AUTORETRY_KWARGS)
def send_confirmation_email(self, user_email: str, confirmation_token: str) -> bool:
    """Celery task для отправки письма с подтверждением email."""
    return send_confirmation_email_sync(user_email, confirmation_token, raise_on_error=True, task=self)


@shared_task(**EMAIL_TASK_AUTORETRY_KWARGS)
def send_welcome_email(self, user_email: str) -> bool:
    """Celery task для отправки приветственного письма."""
    return send_welcome_email_sync(user_email, raise_on_error=True, task=self)
