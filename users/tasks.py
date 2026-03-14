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
