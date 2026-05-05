from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):
    """Команда управления проектом."""

    help = 'Создает/обновляет группу "Модераторы" с правами для каталога, заказов и оплаты'

    PERMISSIONS_BY_MODEL = {
        ("store", "product"): ("view_product", "add_product", "change_product", "delete_product"),
        ("store", "category"): ("view_category", "add_category", "change_category", "delete_category"),
        ("orders", "order"): ("view_order", "change_order"),
        ("orders", "orderitem"): ("view_orderitem",),
        ("payments", "payment"): ("view_payment", "add_payment", "change_payment"),
    }

    def handle(self, *args, **options):
        """Выполняет основную логику команды."""
        group, created = Group.objects.get_or_create(name="Модераторы")
        assigned_codenames = []

        for (app_label, model), codenames in self.PERMISSIONS_BY_MODEL.items():
            permissions = Permission.objects.filter(
                content_type__app_label=app_label,
                content_type__model=model,
                codename__in=codenames,
            )
            for permission in permissions:
                group.permissions.add(permission)
                assigned_codenames.append(permission.codename)

        assigned_codenames = sorted(set(assigned_codenames))
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Группа "Модераторы" создана с правами: {", ".join(assigned_codenames)}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Группа "Модераторы" обновлена. Актуальные права: {", ".join(assigned_codenames)}')
            )
