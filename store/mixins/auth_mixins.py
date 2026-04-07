from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


def is_moderator_user(user):
    """Проверяет, может ли пользователь работать с модераторским дашбордом."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["moderators", "Модераторы"]).exists()


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Миксин для ограничения доступа только для персонала.

    Требует, чтобы пользователь был:
    1. Аутентифицирован (LoginRequiredMixin)
    2. Являлся сотрудником (is_staff=True)

    Использование:
        class MyView(StaffRequiredMixin, View):
            # только staff могут получить доступ

    Raises:
        PermissionDenied: Если пользователь не является сотрудником
    """

    def test_func(self):
        """Проверяет доступ пользователя к представлению."""
        return self.request.user.is_staff


class ModeratorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Миксин для ограничения доступа только для модераторов.

    Требует, чтобы пользователь был:
    1. Аутентифицирован (LoginRequiredMixin)
    2. Являлся сотрудником (is_staff=True)
    3. Состоял в группе "Модераторы"

    Использование:
        class MyView(ModeratorRequiredMixin, View):
            # только модераторы могут получить доступ

    Raises:
        PermissionDenied: Если пользователь не является модератором
    """

    def test_func(self):
        """Проверяет доступ пользователя к представлению."""
        return is_moderator_user(self.request.user)
