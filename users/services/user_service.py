import logging
from django.contrib.auth import login

from config.celery import send_welcome_email
from users.models import User

logger = logging.getLogger(__name__)


def register_user(form, request):
    """
    Регистрация нового пользователя и отправка приветственного письма.

    Выполняет следующие действия:
    1. Сохраняет пользователя из формы
    2. Выполняет вход пользователя в систему
    3. Отправляет приветственное письмо через Celery

    Args:
        form (UserRegistrationForm): Форма регистрации пользователя
        request (HttpRequest): HTTP запрос объекта

    Returns:
        User: Созданный пользователь

    Note:
        Ошибки при отправке письма логируются, но не прерывают процесс регистрации
    """
    user = form.save()
    login(request, user)

    # Отправка приветственного письма через Celery с обработкой ошибок
    try:
        send_welcome_email.delay(user.email)
    except Exception as e:
        logger.error(f"Ошибка при отправке приветственного письма пользователю {user.email}: {e}")

    return user


def get_user_profile_data(user):
    """
    Получение данных профиля пользователя для отображения.

    Args:
        user (User): Объект пользователя

    Returns:
        dict: Словарь с данными профиля:
            - user: объект пользователя
            - email: email пользователя
            - first_name: имя пользователя
            - last_name: фамилия пользователя
    """
    return {
        "user": user,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def update_user_profile(user, form):
    """
    Обновление профиля пользователя.

    Сохраняет данные из формы и возвращает обновленные данные профиля.

    Args:
        user (User): Объект пользователя для обновления
        form (UserProfileForm): Форма с данными профиля

    Returns:
        dict: Обновленные данные профиля (аналогично get_user_profile_data)
    """
    form.save()
    return get_user_profile_data(user)
