from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def backfill_email_token_created_at(apps, schema_editor):
    """Set email_token_created_at for users with NULL to expire their legacy tokens."""
    User = apps.get_model("users", "User")
    # Устанавливаем дату в прошлом, чтобы легаси-токены считались истёкшими
    expired_date = timezone.now() - timedelta(days=365)
    User.objects.filter(
        email_token__isnull=False,
        email_token_created_at__isnull=True,
    ).update(email_token_created_at=expired_date)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_alter_user_avatar_alter_user_city_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email_token",
            field=models.CharField(
                "Токен подтверждения email",
                blank=True,
                db_index=True,
                max_length=64,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_email_token_created_at, migrations.RunPython.noop),
    ]
