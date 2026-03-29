from django.contrib import admin
from django.contrib.auth.models import Group, Permission


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'permissions_count']
    search_fields = ['name']

    def permissions_count(self, obj):
        return obj.permissions.count()

    permissions_count.short_description = 'Количество прав'


def create_moderator_group():
    """
    Создает группу 'Модераторы' с правами на управление товарами.
    """
    group, created = Group.objects.get_or_create(name='Модераторы')

    if created:
        # Получаем права для управления товарами
        product_permissions = Permission.objects.filter(
            content_type__app_label='store',
            content_type__model='product'
        )

        # Добавляем права: просмотр, добавление, изменение, удаление
        allowed_codenames = ['view_product', 'add_product', 'change_product', 'delete_product']
        for permission in product_permissions.filter(codename__in=allowed_codenames):
            group.permissions.add(permission)

        print(f"Группа 'Модераторы' создана с правами: {', '.join(allowed_codenames)}")
    else:
        print("Группа 'Модераторы' уже существует")


# Автоматическое создание группы при регистрации админки
create_moderator_group()
