from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):
    help = 'Создает группу "Модераторы" с правами на управление товарами и категориями'

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name='Модераторы')
        
        if created:
            # Права для управления товарами
            product_permissions = Permission.objects.filter(
                content_type__app_label='store',
                content_type__model='product'
            )

            # Права для управления категориями
            category_permissions = Permission.objects.filter(
                content_type__app_label='store',
                content_type__model='category'
            )
            
            # Добавляем права для товаров: просмотр, добавление, изменение, удаление
            product_codenames = ['view_product', 'add_product', 'change_product', 'delete_product']
            for permission in product_permissions.filter(codename__in=product_codenames):
                group.permissions.add(permission)

            # Добавляем права для категорий: просмотр, добавление, изменение, удаление
            category_codenames = ['view_category', 'add_category', 'change_category', 'delete_category']
            for permission in category_permissions.filter(codename__in=category_codenames):
                group.permissions.add(permission)
            
            all_permissions = product_codenames + category_codenames
            self.stdout.write(
                self.style.SUCCESS(
                    f'Группа "Модераторы" создана с правами: {", ".join(all_permissions)}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING('Группа "Модераторы" уже существует')
            )
