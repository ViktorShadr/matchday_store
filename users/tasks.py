from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings


@shared_task
def send_welcome_email(user_email):
    """
    Отправка приветственного письма пользователю
    """
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        print("Ошибка отправки email: не настроен DEFAULT_FROM_EMAIL")
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
        print(f"Письмо успешно отправлено на {user_email}")
        return True
    except Exception as e:
        print(f"Ошибка отправки email: {e}")
        return False


@shared_task
def send_confirmation_email(user_email, confirmation_token):
    """
    Отправка письма с подтверждением email

    Args:
        user_email (str): Email пользователя
        confirmation_token (str): Токен подтверждения
    """
    if not settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        print("Ошибка отправки email: не настроен DEFAULT_FROM_EMAIL")
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
        print(f"Письмо с подтверждением отправлено на {user_email}")
        return True
    except Exception as e:
        print(f"Ошибка отправки email с подтверждением: {e}")
        return False
