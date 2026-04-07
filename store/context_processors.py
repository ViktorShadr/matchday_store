from store.services import PermissionService


def navigation_permissions(request):
    """Добавляет права пользователя в общий контекст шаблонов."""
    return {
        "navigation_permissions": PermissionService.get_user_permissions(request.user),
    }
