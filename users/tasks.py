import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


@shared_task
def send_welcome_email(user_email):
    """
    Отправка приветственного письма пользователю
    """
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        logger.error(
            "Ошибка отправки email: не настроен DEFAULT_FROM_EMAIL",
            extra={"event": "email_default_sender_not_configured", "email_type": "welcome"},
        )
        return False

    subject = "Добро пожаловать в наш магазин"
    message = "Спасибо, что зарегистрировались в Shinnik Fan Shop!"
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
            "Письмо успешно отправлено на %s",
            user_email,
            extra={"event": "welcome_email_sent", "email_type": "welcome"},
        )
        return True
    except Exception:
        logger.exception(
            "Ошибка отправки email на %s",
            user_email,
            extra={"event": "welcome_email_send_failed", "email_type": "welcome"},
        )
        return False


def send_confirmation_email_sync(user_email, confirmation_token):
    """
    Отправка письма с подтверждением email

    Args:
        user_email (str): Email пользователя
        confirmation_token (str): Токен подтверждения
    """
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        logger.error(
            "Ошибка отправки email: не настроен DEFAULT_FROM_EMAIL",
            extra={"event": "email_default_sender_not_configured", "email_type": "confirmation"},
        )
        return False

    # Формируем ссылку подтверждения
    confirmation_url = f"{settings.SITE_URL}/users/confirm-email/{confirmation_token}/"

    subject = "Подтверждение email в Shinnik Fan Shop"
    message = f"""
    Спасибо за регистрацию в Shinnik Fan Shop!

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
            "Письмо с подтверждением отправлено на %s",
            user_email,
            extra={"event": "confirmation_email_sent", "email_type": "confirmation"},
        )
        return True
    except Exception:
        logger.exception(
            "Ошибка отправки email с подтверждением на %s",
            user_email,
            extra={"event": "confirmation_email_send_failed", "email_type": "confirmation"},
        )
        return False


@shared_task
def send_confirmation_email(user_email, confirmation_token):
    """Celery task для отправки письма с подтверждением email."""
    return send_confirmation_email_sync(user_email, confirmation_token)
