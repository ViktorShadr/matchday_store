from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0008_order_staff_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="guest_manage_token",
            field=models.CharField(blank=True, editable=False, max_length=128, null=True, unique=True),
        ),
    ]
