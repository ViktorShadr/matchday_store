from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


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
        user = self.request.user
        return user.is_staff and user.groups.filter(name="Модераторы").exists()
