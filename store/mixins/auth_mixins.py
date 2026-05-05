from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

MODERATOR_GROUP_NAMES = ("Модераторы", "moderators")


def is_moderator_user(user):
    """Проверяет, может ли пользователь работать с модераторским дашбордом."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    return user.groups.filter(name__in=MODERATOR_GROUP_NAMES).exists()


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
