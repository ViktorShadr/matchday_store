from users.models import User


def register_user(form, request):
    """
    Регистрация нового пользователя.

    Выполняет следующие действия:
    1. Сохраняет пользователя из формы
    2. Оставляет пользователя неактивным до подтверждения email

    Args:
        form (UserRegistrationForm): Форма регистрации пользователя
        request (HttpRequest): HTTP запрос объекта

    Returns:
        User: Созданный пользователь

    """
    _ = request
    user = form.save()

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
