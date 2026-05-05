from django.contrib import admin, messages
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from users.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Настройки админ-интерфейса для User."""

    list_display = ("id", "email", "first_name", "last_name", "is_staff", "is_active", "is_moderator")
    list_filter = ("is_staff", "is_active", "is_superuser", "groups")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    def is_moderator(self, obj):
        """Проверяет, состоит ли пользователь в группе модераторов."""
        return obj.groups.filter(name="Модераторы").exists()

    is_moderator.boolean = True
    is_moderator.short_description = "Модератор"


# Добавляем кастомные действия для управления модераторами
@admin.action(description="Удалить из группы модераторов")
def remove_from_moderators(modeladmin, request, queryset):
    """Удаляет объект в сценарии 'from moderators'."""
    moderator_group = Group.objects.filter(name="Модераторы").first()
    if moderator_group:
        count = 0
        for user in queryset:
            if user.groups.filter(name="Модераторы").exists():
                user.groups.remove(moderator_group)
                count += 1
        messages.success(request, f"{count} пользователей удалены из группы модераторов")
    else:
        messages.error(request, 'Группа "Модераторы" не найдена')


@admin.action(description="Добавить в группу модераторов")
def add_to_moderators(modeladmin, request, queryset):
    """Выполняет логику 'add_to_moderators'."""
    moderator_group = Group.objects.filter(name="Модераторы").first()
    if moderator_group:
        count = 0
        for user in queryset:
            if not user.groups.filter(name="Модераторы").exists():
                user.groups.add(moderator_group)
                count += 1
        messages.success(request, f"{count} пользователей добавлены в группу модераторов")
    else:
        messages.error(request, 'Группа "Модераторы" не найдена')


# Добавляем действия в UserAdmin
UserAdmin.actions = [remove_from_moderators, add_to_moderators]

# Разрегистрируем стандартную GroupAdmin и зарегистрируем нашу
admin.site.unregister(Group)


@admin.register(Group)
class ModeratorGroupAdmin(admin.ModelAdmin):
    """Админка для управления группой модераторов"""

    def get_queryset(self, request):
        # Показываем только группу модераторов
        """Возвращает queryset для текущего представления."""
        return super().get_queryset(request).filter(name="Модераторы")

    def has_add_permission(self, request):
        # Запрещаем добавление новых групп
        """Проверяет право на добавление объектов."""
        return False

    def has_delete_permission(self, request, obj=None):
        # Запрещаем удаление группы
        """Проверяет право на удаление объектов."""
        return False

    def changelist_view(self, request, extra_context=None):
        # Перенаправляем на кастомную страницу управления модераторами
        """Отображает страницу списка объектов в админке."""
        moderator_group = Group.objects.filter(name="Модераторы").first()
        if not moderator_group:
            create_group_command = "python manage.py create_moderator_group"
            messages.error(
                request,
                f'Группа "Модераторы" не найдена. Создайте её с помощью команды: {create_group_command}',
            )
            return super().changelist_view(request, extra_context)

        # Получаем всех модераторов
        moderators = User.objects.filter(groups=moderator_group)

        # Получаем всех пользователей, которые не являются модераторами
        non_moderators = User.objects.exclude(groups=moderator_group).filter(is_staff=True)

        context = {
            **(extra_context or {}),
            "moderators": moderators,
            "non_moderators": non_moderators,
            "moderator_group": moderator_group,
            "title": "Управление группой модераторов",
        }

        return render(request, "templates_moderator/moderator_group_management.html", context)

    def response_add(self, request, obj, post_url_continue=None):
        """Формирует ответ после добавления объекта в админке."""
        return HttpResponseRedirect(reverse("admin:users_user_changelist"))

    def response_change(self, request, obj):
        """Формирует ответ после изменения объекта в админке."""
        return HttpResponseRedirect(reverse("admin:users_user_changelist"))
