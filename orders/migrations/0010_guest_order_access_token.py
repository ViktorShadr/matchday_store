from datetime import timedelta
from hashlib import sha256

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def _hash_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


def migrate_guest_manage_tokens(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    GuestOrderAccessToken = apps.get_model("orders", "GuestOrderAccessToken")

    now = timezone.now()
    expires_at = now + timedelta(days=getattr(settings, "GUEST_ORDER_TOKEN_TTL_DAYS", 30))
    migrated_order_ids = []

    legacy_orders = (
        Order.objects.exclude(guest_manage_token__isnull=True)
        .exclude(guest_manage_token="")
        .only("id", "guest_manage_token")
    )
    for order in legacy_orders.iterator():
        GuestOrderAccessToken.objects.get_or_create(
            token_hash=_hash_token(order.guest_manage_token),
            defaults={
                "order_id": order.id,
                "purpose": "guest_manage",
                "created_at": now,
                "expires_at": expires_at,
                "revoked_at": None,
                "last_used_at": None,
            },
        )
        migrated_order_ids.append(order.id)

    if migrated_order_ids:
        Order.objects.filter(id__in=migrated_order_ids).update(guest_manage_token=None)


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_order_guest_manage_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="guest_manage_token",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text=(
                    "Deprecated legacy raw token. New guest management access is stored in "
                    "GuestOrderAccessToken.token_hash."
                ),
                max_length=128,
                null=True,
                unique=True,
            ),
        ),
        migrations.CreateModel(
            name="GuestOrderAccessToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                (
                    "purpose",
                    models.CharField(
                        choices=[("guest_manage", "Guest order management")],
                        db_index=True,
                        default="guest_manage",
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_access_tokens",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "verbose_name": "Токен гостевого доступа к заказу",
                "verbose_name_plural": "Токены гостевого доступа к заказам",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="guestorderaccesstoken",
            index=models.Index(
                fields=["order", "purpose", "revoked_at", "expires_at"],
                name="guest_token_lookup_idx",
            ),
        ),
        migrations.RunPython(migrate_guest_manage_tokens, migrations.RunPython.noop),
    ]
